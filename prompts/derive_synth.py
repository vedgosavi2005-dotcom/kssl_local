"""Derive hooks of the synthesis, field-synthesis and SWOT prompts (prompts/synthesis.yml, field_synthesis.yml, swot.yml).

Kept apart from prompts/derive.py; derive.py imports this module at its end, which registers the hooks.
Same contract as derive.py: `@hook(name) def f(cur, ctx)`, run inside the loader transaction after the rows are written.

    synthesis_finish   for the subject competitor's synthesis: each weakness's `from_labels` = the partner names of its trace rows (one per
                       line, the chips the page shows); each trace row gets the url + tier of the best stored evidence of the tie it points
                       at (and a fact_source row quoting that evidence); the weakness and the synthesis take the url of their first trace.
    field_support      competitive_field_synthesis patterns: support_count = how many of the competitors the model named (transient
                       `supporters`, separated by ;) resolve to a competitor that has a stored synthesis; support_total = how many
                       competitors have one. A pattern that fewer than 2 competitors support is deleted (a pattern is more than one case).
    swot_counts        competitive_competitor_swot.record_count = the number of statements of the same type for the same competitor.

Self-check (no DB):  python -m prompts.derive_synth --selftest
"""

from __future__ import annotations

import re
import sys

from prompts.derive import hook

MIN_SUPPORT = 2
QUOTE_MAX = 280


def split_names(text) -> list:
    """'A; B ;C' -> ['A', 'B', 'C'] (also newlines and ' | '), duplicates (case-folded) removed, order kept."""
    out, seen = [], set()
    for n in re.split(r"[;\n|]+", str(text or "")):
        n = n.strip()
        if n and n.casefold() not in seen:
            seen.add(n.casefold())
            out.append(n)
    return out


def chips(names: list) -> str:
    """The `from_labels` text: one partner name per line, each once."""
    return "\n".join(dict.fromkeys(n for n in names if n))


def _fact(cur, table: str, row_id: str, column: str, url: str, tier: str | None, quote: str | None) -> None:
    cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,now())", (table, row_id, column, url, tier or "unlisted", quote))


def _tier(cur, url: str) -> str:
    """The tier already stored for this url (the tie was loaded with its company-domain rule), else the plain allowlist class, else unlisted."""
    from backend.sources import classify
    cur.execute("SELECT source_tier FROM staging.fact_source WHERE source_url = %s AND source_tier IN ('primary', 'independent') LIMIT 1", (url,))
    r = cur.fetchone()
    return (r["source_tier"] if r else None) or classify(url, ()) or "unlisted"


def _best_evidence(cur, relationship_id):
    """The stored evidence row of a tie to cite: official source first, then the most recent."""
    cur.execute("""SELECT source_url, evidence_text FROM staging.competitive_partnership_evidence
                   WHERE relationship_id = %s AND coalesce(source_url, '') <> ''
                   ORDER BY (source_type = 'Official source') DESC, as_of_date DESC NULLS LAST, card_number LIMIT 1""", (str(relationship_id),))
    return cur.fetchone()


@hook("synthesis_finish")
def synthesis_finish(cur, ctx: dict) -> None:
    cid = str(ctx["subject_row"]["competitor_id"])
    cur.execute("SELECT vulnerability_id FROM staging.competitive_synthesis_vulnerability WHERE competitor_id = %s ORDER BY display_order", (cid,))
    first_url = None
    for v in cur.fetchall():
        vid = str(v["vulnerability_id"])
        cur.execute("""SELECT t.trace_id, t.relationship_id, p.partner_name FROM staging.competitive_synthesis_vulnerability_trace t
                       JOIN staging.competitive_partnership p ON p.relationship_id = t.relationship_id
                       WHERE t.vulnerability_id = %s ORDER BY p.partner_name""", (vid,))
        traces = cur.fetchall()
        cur.execute("UPDATE staging.competitive_synthesis_vulnerability SET from_labels = %s WHERE vulnerability_id = %s",
                    (chips([t["partner_name"] for t in traces]) or None, vid))
        v_url = v_tier = None
        for t in traces:
            ev = _best_evidence(cur, t["relationship_id"])
            if not ev:
                continue
            tier = _tier(cur, ev["source_url"])
            cur.execute("UPDATE staging.competitive_synthesis_vulnerability_trace SET source_url = %s, source_tier = %s WHERE trace_id = %s",
                        (ev["source_url"], tier, str(t["trace_id"])))
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_synthesis_vulnerability_trace' AND row_id = %s", (str(t["trace_id"]),))
            _fact(cur, "competitive_synthesis_vulnerability_trace", str(t["trace_id"]), "relationship_id", ev["source_url"], tier,
                  (ev["evidence_text"] or "")[:QUOTE_MAX] or None)
            if v_url is None:
                v_url, v_tier = ev["source_url"], tier
        if v_url:
            cur.execute("UPDATE staging.competitive_synthesis_vulnerability SET source_url = %s, source_tier = %s WHERE vulnerability_id = %s",
                        (v_url, v_tier, vid))
            first_url = first_url or (v_url, v_tier)
    if first_url:
        cur.execute("UPDATE staging.competitive_synthesis SET source_url = %s, source_tier = %s WHERE competitor_id = %s", (*first_url, cid))
    ctx["notes"].append(f"synthesis_finish: {cid}")


@hook("field_support")
def field_support(cur, ctx: dict) -> None:
    from prompts.loader import match_name
    cur.execute("SELECT competitor_id, display_name, short_name, legal_name FROM staging.competitive_competitor")
    comps = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT competitor_id FROM staging.competitive_synthesis")
    have = {str(r["competitor_id"]) for r in cur.fetchall()}
    for (table, rid), tr in ctx["transient"].items():
        if table != "competitive_field_synthesis":
            continue
        cur.execute("SELECT row_kind FROM staging.competitive_field_synthesis WHERE synthesis_id = %s", (rid,))
        row = cur.fetchone()
        if not row or row["row_kind"] != "pattern":
            continue
        ids, bad = set(), []
        for n in split_names(tr.get("supporters")):
            hit = {str(h["competitor_id"]) for h in match_name(comps, ["display_name", "short_name", "legal_name"], n)}
            if len(hit) == 1 and next(iter(hit)) in have:
                ids |= hit
            else:
                bad.append(n)
        if bad:
            ctx["warnings"].append(f"field_support: not counted (not a competitor with a stored synthesis): {bad}")
        if len(ids) < MIN_SUPPORT:
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_field_synthesis' AND row_id = %s", (rid,))
            cur.execute("DELETE FROM staging.competitive_field_synthesis WHERE synthesis_id = %s", (rid,))
            ctx["notes"].append(f"field_support: pattern {rid} dropped, {len(ids)} supporting competitor(s)")
            continue
        cur.execute("UPDATE staging.competitive_field_synthesis SET support_count = %s, support_total = %s WHERE synthesis_id = %s",
                    (len(ids), len(have), rid))


@hook("swot_counts")
def swot_counts(cur, ctx: dict) -> None:
    """A SWOT is the current state, not a history: rows of the competitor from earlier runs are replaced by this run's. A statement of this run
    with no source row (fact_source other than a judgement) is deleted. Then record_count = statements of the same type."""
    cid = str(ctx["subject_row"]["competitor_id"])
    mine = [i for t, i, *_ in ctx["rows"] if t == "competitive_competitor_swot"]
    cur.execute("SELECT swot_id FROM staging.competitive_competitor_swot WHERE competitor_id = %s", (cid,))
    for r in cur.fetchall():
        sid = str(r["swot_id"])
        stale = sid not in mine
        if not stale:
            cur.execute("SELECT count(*) AS n FROM staging.fact_source WHERE table_name = 'competitive_competitor_swot' AND row_id = %s "
                        "AND source_tier <> 'judgement'", (sid,))
            if cur.fetchone()["n"] == 0:
                stale = True
                ctx["warnings"].append(f"swot_counts: statement {sid} had no source, deleted")
        if stale:
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_competitor_swot' AND row_id = %s", (sid,))
            cur.execute("DELETE FROM staging.competitive_competitor_swot WHERE swot_id = %s", (sid,))
    cur.execute("""UPDATE staging.competitive_competitor_swot s SET record_count = c.n
                   FROM (SELECT swot_type, count(*) AS n FROM staging.competitive_competitor_swot
                         WHERE competitor_id = %s AND coalesce(statement, '') <> '' GROUP BY swot_type) c
                   WHERE s.competitor_id = %s AND s.swot_type = c.swot_type""", (cid, cid))


def _selftest() -> None:
    assert split_names("A; B ;C\nb | D") == ["A", "B", "C", "D"]
    assert split_names(None) == [] and split_names(" ; ") == []
    assert chips(["Thales", "Thales", "", "Nordvik Works"]) == "Thales\nNordvik Works"
    print("derive_synth selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
