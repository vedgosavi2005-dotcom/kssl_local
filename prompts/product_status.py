"""Handler of prompts/product_status.yml: the status column of a company's products (competitive_product, or client_product for 'client').

    python -m prompts.product_status --selftest         pure checks, fictional values

A status is written only if the product_ref is one of the subject company's candidate products, the status is one of STATUSES, and the
quote is in that product's own name or description (whitespace, case, quote marks and dashes folded). The subject's candidate products are
cleared first, so a re-run never leaves an old status behind. One staging.fact_source row per status: the url the product's name rests on,
the quote. Same Result shape as prompts/spec_enrich.
"""

from __future__ import annotations

import sys

from prompts.spec_enrich import Result, norm_text

STATUSES = ("in development", "prototype", "concept", "in trials", "retired", "cancelled")


def clean(env: dict) -> tuple[list, list]:
    out, problems = [], []
    for r in env.get("records") or []:
        v = (r or {}).get("values") or {} if isinstance(r, dict) else {}
        ref, status, quote = (" ".join(str(v.get(k) or "").split()) for k in ("product_ref", "status", "quote"))
        if not ref or not quote:
            problems.append(f"incomplete record dropped: {ref or '?'}")
        elif status.casefold() not in STATUSES:
            problems.append(f"unknown status dropped: {status!r}")
        else:
            out.append({"ref": ref, "status": status.casefold(), "quote": quote[:200]})
    return out, problems


def quote_ok(quote, name, description) -> bool:
    return norm_text(quote) in norm_text(f"{name}\n{description or ''}") or norm_text(quote) in norm_text(f"{name} {description or ''}")


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    import yaml, pathlib
    res = Result()
    recs, res.warnings = clean(env)
    client = subject["company_key"] == "client"
    spec = yaml.safe_load((pathlib.Path(__file__).with_name("product_status.yml")).read_text(encoding="utf-8"))
    q = spec["subject"]["documents"][0]["query"]
    cur.execute(q.replace("{{subject.company_key}}", "%s"), [subject["company_key"]] * q.count("{{subject.company_key}}"))
    cand = {str(r["product_ref"]): r for r in cur.fetchall()}
    table, key = ("client_product", "client_product_id") if client else ("competitive_product", "product_id")
    cast = "bigint" if client else "uuid"
    dropped = {"not_a_candidate": 0, "quote_missing": 0, "duplicate": 0}
    if not dry_run:
        cur.execute(f"UPDATE staging.{table} SET status = NULL WHERE {key}::text = ANY(%s)", (list(cand),))
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND column_name = 'status' AND row_id = ANY(%s)", (table, list(cand)))
    seen = set()
    for r in recs:
        p = cand.get(r["ref"])
        if p is None:
            dropped["not_a_candidate"] += 1
            continue
        if r["ref"] in seen:
            dropped["duplicate"] += 1
            continue
        if not quote_ok(r["quote"], p["product_name"], p["description"]):
            dropped["quote_missing"] += 1
            continue
        seen.add(r["ref"])
        res.loaded.append((table, r["ref"], False))
        if dry_run:
            continue
        cur.execute(f"UPDATE staging.{table} SET status = %s WHERE {key} = %s::{cast}", (r["status"], r["ref"]))
        cur.execute("SELECT source_url, source_tier FROM staging.fact_source WHERE table_name = %s AND column_name = 'product_name' AND row_id = %s "
                    "ORDER BY (source_tier = 'primary') DESC LIMIT 1", (table, r["ref"]))
        src = cur.fetchone() or {}
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote)
                       VALUES (%s, %s, 'status', %s, %s, NULL, %s)""", (table, r["ref"], src.get("source_url"), src.get("source_tier"), r["quote"]))
    res.rows = len(res.loaded)
    res.details = {"candidates": len(cand), "offered": len(recs), "written": res.rows, "dropped": {k: v for k, v in dropped.items() if v}}
    res.note = f"{res.rows} statuses of {len(cand)} candidate products" + (f" (dropped: {res.details['dropped']})" if res.details["dropped"] else "")
    if not res.rows:
        res.skip_reason = (env.get("skip_reason") or "no product with a special status")[:300]
    return res


def _selftest() -> None:
    env = {"records": [{"values": {"product_ref": "a", "status": "Concept", "quote": "concept study"}},
                       {"values": {"product_ref": "b", "status": "unveiled", "quote": "unveiled at AAD"}},
                       {"values": {"product_ref": "", "status": "prototype", "quote": "x"}}]}
    got, probs = clean(env)
    assert got == [{"ref": "a", "status": "concept", "quote": "concept study"}] and len(probs) == 2
    assert quote_ok("Concepts only; no build contract", "Ghost Commander", "Shown at MADEX.\nConcepts only;  no build contract.")
    assert quote_ok("K9A3 (next-generation K9, concept)", "K9A3 (next-generation K9, concept)", None)
    assert not quote_ok("in development", "60mm Mortar", "In production since 2010.")
    print("product_status self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
