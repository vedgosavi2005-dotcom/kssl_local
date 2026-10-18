"""Technology-pillar derive hooks (kept apart from prompts/derive.py; registered into its REGISTRY when derive is imported).

    tech_glance        technology_overview_fact: the six "at a glance" rows of an article (What, Who, Maturity, Horizon, Touches,
                       KSSL position), written by code from the stored scores. Only "What" comes from the model (transient glance_what).
                       Also forces client_position = unknown when no KSSL product / spec is named (A.3.1: a position needs a spec row).
    innovation_gate    technology_innovation (innovation_discovery): a candidate whose title names a KSSL product or a competitor catalogue
                       product is "a product, not a technology" and is deleted (A.3.2).
    innovation_stance  technology_innovation.stance (innovation_detail): watch / partner / license / develop / ignore by rule from
                       client_position, relevance and the developer type (A.3.2). The model writes the reason; the rule only checks it.
    patent_trend       competitive_patent_trend rolled up by code from the labelled filings (A.3.3).
    technology_metric  technology_metric roll-up counts (docs/audit_v2/DATA_FLOOD_PLAN.md step 4).

Self-check (pure, fictional values): python -m prompts.derive_tech --selftest
"""

from __future__ import annotations

import hashlib
import re
import sys

from prompts.derive import _row, hook, ids  # noqa: F401  (derive imports this module at its end; the names exist by then)

GLANCE = (("what", "What"), ("who", "Who"), ("maturity", "Maturity"), ("horizon", "Horizon"), ("touches", "Touches"), ("position", "{client} position"))
MATURITY = {1: "Concept / research", 2: "Prototype", 3: "Trials", 4: "Production", 5: "Fielded"}          # fallbacks: ui.code_label wins
HORIZON = {"lt_2y": "Under 2 years", "2_5y": "2 to 5 years", "gt_5y": "Over 5 years", "unknown": "Unknown"}
HORIZON_SOURCE = {"stated": "Stated in the source", "rule": "Derived from maturity"}
POSITION = {"behind": "Behind", "parity": "Parity", "ahead": "Ahead", "unknown": "Unknown"}
WHO_MAX = 60


def fact_id(article_id, key) -> int:
    return int.from_bytes(hashlib.sha256(f"tech_glance|{article_id}|{key}".encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def clip(text, n):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def distinct_names(names: list) -> list:
    """Names in order without repeats; a name that starts with the first word of an earlier one (Hanwha / Hanwha Defense USA) is the same firm."""
    out, firsts = [], set()
    for n in names:
        n = " ".join(str(n or "").split())
        if not n:
            continue
        f = n.split()[0].casefold().strip(",.")
        if f in firsts:
            continue
        firsts.add(f)
        out.append(n)
    return out


def position_for(client_position, product_id, spec_touched) -> str:
    """A KSSL position other than unknown needs a named KSSL product and a named spec (A.3.1); otherwise unknown."""
    p = str(client_position or "").strip().lower()
    if p not in ("behind", "parity", "ahead"):
        return "unknown"
    return p if product_id not in (None, "") and str(spec_touched or "").strip() else "unknown"


def glance_rows(card: dict, what, developers: list, product_name, labels: dict | None = None, reasons: dict | None = None, *, client: str) -> list:
    """The six fixed rows [{fact_key, ui_label, fact_value, proof_text}]. A field with no value is left out (no placeholder such as
    'None named' or 'Unknown' is stored: the UI prints its own empty word). `labels` = {(column, code): label} from ui.code_label;
    `reasons` = {column: judgement text}; `client` = client_account.client_name (the position row's label)."""
    labels, reasons = labels or {}, reasons or {}

    m = card.get("maturity")
    mat = labels.get(("maturity", str(m))) or MATURITY.get(m)
    hor = card.get("horizon")
    hor_label = None if hor in (None, "", "unknown") else (labels.get(("horizon", hor)) or HORIZON.get(hor, hor))
    src = card.get("horizon_source")
    pos = position_for(card.get("client_position"), card.get("touches_client_product_id"), card.get("spec_touched"))
    pos_label = None if pos == "unknown" else (labels.get(("client_position", pos)) or POSITION[pos])
    touches = f"{product_name} - {card.get('spec_touched')}" if product_name and card.get("spec_touched") else product_name
    who = clip(", ".join(distinct_names(developers)), WHO_MAX) or None
    vals = {
        "what": (clip(what, 60), None),
        "who": (who, None),
        "maturity": (mat, reasons.get("maturity")),
        "horizon": (hor_label, (labels.get(("horizon_source", src)) or HORIZON_SOURCE.get(src)) + (f" ({mat}; no date stated)" if src == "rule" and mat else "")
                    if src == "rule" else (reasons.get("horizon") or labels.get(("horizon_source", src)) or HORIZON_SOURCE.get(src))),
        "touches": (clip(touches, 120) if touches else None, None),
        "position": (pos_label, reasons.get("client_position")),
    }
    return [{"fact_key": k, "ui_label": lbl.format(client=client), "fact_value": vals[k][0], "proof_text": vals[k][1]} for k, lbl in GLANCE if vals[k][0]]


def _labels(cur) -> dict:
    cur.execute("SELECT column_name, code, label FROM staging_ui.code_label WHERE table_name = 'technology_overview_article' AND is_active")
    return {(r["column_name"], str(r["code"])): r["label"] for r in cur.fetchall()}


@hook("tech_glance")
def tech_glance_hook(cur, ctx: dict) -> None:
    """Rebuild the glance rows of every technology_overview_article of this run (replacing earlier fact rows of the card).
    List it AFTER tech_direction (it reads horizon / horizon_source) and before story_link."""
    labels = _labels(cur)
    from prompts.derive import client_name
    client = client_name(cur)
    tr = ctx.get("transient", {})
    for aid in ids(ctx, "technology_overview_article"):
        r = _row(cur, "technology_overview_article", "overview_article_id", aid)
        if r is None:
            continue
        pos = position_for(r.get("client_position"), r.get("touches_client_product_id"), r.get("spec_touched"))
        if pos != (r.get("client_position") or "unknown"):
            ctx["notes"].append(f"tech_glance: {aid}: client_position {r.get('client_position')} -> {pos} (no client product and spec named)")
            # the model's reason argued for the old value: replace it with the rule, so Trace never shows a reason for a value not stored
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'technology_overview_article' AND row_id = %s AND column_name = 'client_position'",
                        (str(r["overview_article_id"]),))
            cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at) VALUES "
                        "('technology_overview_article', %s, 'client_position', 'judgement', 'judgement', %s, now())",
                        (str(r["overview_article_id"]), f"unknown by rule: a position needs a named {client} product and spec; the article names none."))
        cur.execute("UPDATE staging.technology_overview_article SET client_position = %s WHERE overview_article_id = %s", (pos, r["overview_article_id"]))
        cur.execute("""SELECT display_label FROM staging.technology_overview_company WHERE overview_article_id = %s
                       ORDER BY (relationship = 'developer') DESC, display_order""", (r["overview_article_id"],))
        devs = distinct_names([x["display_label"] for x in cur.fetchall()])[:2]
        name = None
        if r.get("touches_client_product_id") is not None:
            cur.execute("SELECT product_name FROM staging.client_product WHERE client_product_id = %s", (r["touches_client_product_id"],))
            p = cur.fetchone()
            name = p["product_name"] if p else None
        cur.execute("""SELECT column_name, quote FROM staging.fact_source WHERE table_name = 'technology_overview_article' AND row_id = %s
                       AND source_tier = 'judgement'""", (str(r["overview_article_id"]),))
        reasons = {x["column_name"]: x["quote"] for x in cur.fetchall()}
        rows = glance_rows(r, (tr.get((("technology_overview_article"), str(aid))) or {}).get("glance_what") or r.get("title"), devs, name, labels, reasons,
                           client=client)
        old = [x["overview_fact_id"] for x in _all(cur, "SELECT overview_fact_id FROM staging.technology_overview_fact WHERE overview_article_id = %s", (r["overview_article_id"],))]
        if old:
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'technology_overview_fact' AND row_id = ANY(%s)", ([str(i) for i in old],))
            cur.execute("DELETE FROM staging.technology_overview_fact WHERE overview_article_id = %s", (r["overview_article_id"],))
        for n, g in enumerate(rows, 1):
            fid = fact_id(r["overview_article_id"], g["fact_key"])
            cur.execute("""INSERT INTO staging.technology_overview_fact
                           (overview_fact_id, fact_id, overview_article_id, article_id, display_order, fact_key, fact_label, ui_label, fact_value, proof_text)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (fid, fid, r["overview_article_id"], r["article_id"], n, g["fact_key"], g["ui_label"], g["ui_label"], g["fact_value"], g["proof_text"]))
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
                           VALUES ('technology_overview_fact', %s, 'fact_value', 'stored row', 'stored', NULL, %s, now())""",
                        (str(fid), f"Computed from the stored scores of the article ({g['fact_key']})."))
        ctx["notes"].append(f"tech_glance: {aid}: {len(rows)} glance rows")


def _all(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


# ---- self-check (pure; fictional values) --------------------------------------------------------------------------------------

def selftest() -> None:
    assert position_for("behind", 7, "Maximum range") == "behind"
    assert position_for("behind", None, "Maximum range") == "unknown" and position_for("ahead", 7, " ") == "unknown"
    assert position_for(None, 7, "x") == "unknown" and position_for("maybe", 7, "x") == "unknown"
    card = dict(maturity=3, horizon="2_5y", horizon_source="stated", client_position="behind", touches_client_product_id=7, spec_touched="Maximum range")
    rows = glance_rows(card, "Ramjet-assisted 155 mm shell, 85 km", ["Nordvik Defence", "Nordvik Defence", "Veland Works"], "Zeta-155", None,
                       {"maturity": "3: trial firings.", "client_position": "behind: 48 km vs 85 km."}, client="Acme")
    assert [r["fact_key"] for r in rows] == ["what", "who", "maturity", "horizon", "touches", "position"], rows
    d = {r["fact_key"]: r for r in rows}
    assert distinct_names(["Hanwha Defense USA", "Hanwha", "", "Nordvik"]) == ["Hanwha Defense USA", "Nordvik"]
    assert d["who"]["fact_value"] == "Nordvik Defence, Veland Works" and d["maturity"]["fact_value"] == "Trials" and d["maturity"]["proof_text"] == "3: trial firings."
    assert d["horizon"]["fact_value"] == "2 to 5 years" and d["horizon"]["proof_text"] == "Stated in the source"
    r3 = glance_rows(dict(maturity=1, horizon="gt_5y", horizon_source="rule"), "x", ["A"], None, client="Acme")
    assert [r for r in r3 if r["fact_key"] == "horizon"][0]["proof_text"] == "Derived from maturity (Concept / research; no date stated)"
    assert d["touches"]["fact_value"] == "Zeta-155 - Maximum range" and d["position"]["fact_value"] == "Behind"
    assert d["position"]["ui_label"] == "Acme position"
    rows2 = glance_rows(dict(maturity=1, horizon=None, horizon_source="rule", client_position=None), None, [], None, client="Acme")
    k2 = {r["fact_key"]: r["fact_value"] for r in rows2}
    assert k2 == {"maturity": "Concept / research"}, k2                     # nothing unknown is stored as a placeholder
    assert len(clip("x" * 100, 60)) == 60 and fact_id(1, "what") == fact_id(1, "what") != fact_id(1, "who") and fact_id(1, "what") < 2 ** 63
    _selftest_more()
    print("derive_tech self-check ok")


def _selftest_more() -> None:
    pass


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        print(__doc__)
