"""Handler of prompts/client_spec_enrich.yml: ADD specs a KSSL product is missing, each proven by a credible source document.

    python -m prompts.client_spec_enrich --selftest

The same checks as prompts/spec_enrich.py (quote in the document, value in the quote, credible source, not a spec the product already has
by label or canonical key), for the client side: the document must be one backend/harvest_specs.py stored for this product and must
concern the client (mentions_client). Excel-verified specs are never changed or deleted.
Written rows: staging.client_product_specification (ids from backend.excel_load.client_id_for, so a re-run replaces its own rows),
staging.client_product_source (one per url, the Excel loader's id for the same url), staging.fact_source (url, quote, tier).
"""

from __future__ import annotations

import sys

from prompts.spec_enrich import Result, clean, credible_tier, norm_label, quote_in_doc, value_in_quote

TABLE = "client_product_specification"
FIRST_ORDER = 1000                     # after the Excel rows
SOURCE_TYPE = {"primary": "manufacturer", "independent": "defence_press"}


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    from backend.excel_load import client_id_for, numeric_of, publisher_of, spec_group
    from backend.harvest_specs import CLIENT_EXTRA_DOMAINS
    from prompts.derive_comp import blocked_url
    res = Result()
    pid = int(subject["client_product_id"])
    specs, problems = clean(env, TABLE)
    res.warnings += problems
    if not specs:
        res.skip_reason = (env.get("skip_reason") or "no new specification found in the documents")[:300] if not env.get("records") else None
        return res
    cur.execute("SELECT spec_name, display_order FROM staging.client_product_specification WHERE client_product_id = %s", (pid,))
    rows = cur.fetchall()
    have = {norm_label(r["spec_name"]) for r in rows}
    cur.execute("SELECT raw_label_norm, canonical_key FROM staging.spec_dictionary WHERE lower(category) = lower(%s)", (subject.get("category") or "",))
    canon = {r["raw_label_norm"]: r["canonical_key"] for r in cur.fetchall()}
    have_keys = {canon[l] for l in have if l in canon}
    extra = tuple(d for k, ds in CLIENT_EXTRA_DOMAINS.items() if str(subject.get("product_name") or "").startswith(k) for d in ds)
    docs: dict = {}
    dropped = {"not_a_document": 0, "blocked": 0, "not_credible": 0, "quote_missing": 0, "value_not_in_quote": 0, "already_have": 0}
    seen_new: set = set()
    order = max([FIRST_ORDER - 1, *[r["display_order"] or 0 for r in rows]])
    for s in specs:
        url = s["url"]
        if url not in docs:
            cur.execute("SELECT body_text, source_name, source_kind, source_tier, published_at, triage->>'dc_source_tier' AS tier "
                        "FROM staging.source_document WHERE url = %s AND mentions_client AND triage->'spec_products' ? %s", (url, str(pid)))
            row = cur.fetchone()
            docs[url] = dict(row) if row else None
        doc = docs[url]
        nl = norm_label(s["label"])
        if doc is None:
            dropped["not_a_document"] += 1
            continue
        if blocked_url(url):
            dropped["blocked"] += 1
            continue
        tier = credible_tier(url, doc, extra, client=True)
        if not tier:
            dropped["not_credible"] += 1
            continue
        if not quote_in_doc(s["quote"], doc["body_text"]):
            dropped["quote_missing"] += 1
            continue
        if not value_in_quote(s["value"], s["quote"]):
            dropped["value_not_in_quote"] += 1
            continue
        key = canon.get(nl)
        if nl in have or nl in seen_new or (key and key in have_keys):
            dropped["already_have"] += 1
            continue
        seen_new.add(nl)
        if key:
            have_keys.add(key)
        sid = client_id_for("spec", pid, nl, "harvest")
        src = client_id_for("source", pid, url)
        res.loaded.append((TABLE, str(sid), False))
        if dry_run:
            continue
        order += 1
        unit = (s["unit"] or None) and s["unit"][:32]
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s", (TABLE, str(sid)))
        cur.execute("DELETE FROM staging.client_product_specification WHERE specification_id = %s", (sid,))
        cur.execute("""INSERT INTO staging.client_product_specification (specification_id, client_product_id, spec_name, value_text, value_numeric,
                                                                            unit, spec_group, display_order, source_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (sid, pid, s["label"][:150], s["value"], numeric_of(s["value"], unit), unit, spec_group(s["label"]), order, src))
        cur.execute("""INSERT INTO staging.client_product_source (client_product_id, source_id, source_label, source_type, source_url, published_date)
                       SELECT %s, %s, %s, %s, %s, %s
                       WHERE NOT EXISTS (SELECT 1 FROM staging.client_product_source WHERE client_product_id = %s AND source_id = %s)""",
                    (pid, src, f"{publisher_of(url)} - {SOURCE_TYPE[tier].replace('_', ' ')}"[:255], SOURCE_TYPE[tier], url, doc.get("published_at"), pid, src))
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
                       VALUES (%s, %s, 'value_text', %s, %s, %s, %s, now())""", (TABLE, str(sid), url, tier, doc.get("source_name"), s["quote"]))
    res.rows = len(res.loaded)
    res.details = {"offered": len(specs), "added": res.rows, "dropped": {k: v for k, v in dropped.items() if v}}
    res.note = f"{res.rows} of {len(specs)} specs added" + (f" (dropped: {res.details['dropped']})" if res.details["dropped"] else "")
    if not res.rows and not res.skip_reason:
        res.skip_reason = f"none of the {len(specs)} specs passed the checks: {res.details['dropped']}"
    return res


def _selftest() -> None:
    env = {"records": [{"table": TABLE, "values": {"spec_label": "Range", "spec_value": "40 km", "unit": "km", "source_url": "https://kssl.in/a",
                                                   "quote": "Range 40 km"}},
                       {"table": "competitive_product_specification", "values": {"spec_label": "Weight", "spec_value": "3 t", "source_url": "u", "quote": "3 t"}}]}
    got, _ = clean(env, TABLE)
    assert [g["label"] for g in got] == ["Range"]
    assert credible_tier("https://www.kssl.in/small-arms", {}, (), client=True) == "primary"
    assert credible_tier("https://www.thalesgroup.com/en/fz275", {}, ("thalesgroup.com",), client=True) == "primary"
    assert credible_tier("https://www.punekarnews.in/x", {}, (), client=True) is None
    print("client_spec_enrich self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
