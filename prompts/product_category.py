"""Handler of prompts/product_category.yml: move misplaced competitor products to the right catalogue category.

    python -m prompts.product_category --selftest         pure checks, fictional values

A move is written only if the product_ref is one of the subject batch's products, the category is allowed (the shared categories in
staging.technology_category plus CATALOGUE_ONLY) and differs from the current one. Writes competitive_product.category and category_filter,
recounts category_count for the competitor, and one staging.fact_source row per move (column category, tier judgement, the model's reason
and the old category). Same Result shape as prompts/spec_enrich.
"""

from __future__ import annotations

import sys

from prompts.spec_enrich import Result

CATALOGUE_ONLY = ("Aircraft & Aerostructures", "Sensors & Electro-optics", "C4ISR, Comms & EW", "Training & Simulation")   # user 2026-10-18


def clean(env: dict, allowed: set) -> tuple[list, list]:
    out, problems = [], []
    canon = {a.casefold(): a for a in allowed}
    for r in env.get("records") or []:
        v = (r or {}).get("values") or {} if isinstance(r, dict) else {}
        ref, cat, reason = (" ".join(str(v.get(k) or "").split()) for k in ("product_ref", "category", "reason"))
        if not ref or not cat:
            problems.append(f"incomplete record dropped: {ref or '?'}")
        elif cat.casefold() not in canon:
            problems.append(f"category not allowed, dropped: {cat!r}")
        else:
            out.append({"ref": ref, "category": canon[cat.casefold()], "reason": reason[:140]})
    return out, problems


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    res = Result()
    cur.execute("SELECT category_name FROM staging.technology_category")
    allowed = {r["category_name"] for r in cur.fetchall()} | set(CATALOGUE_ONLY)
    recs, res.warnings = clean(env, allowed)
    cur.execute("""SELECT product_id::text AS ref, category FROM (
                     SELECT product_id, category, (row_number() OVER (ORDER BY product_id) - 1) / 60 AS chunk
                     FROM staging.competitive_product WHERE competitor_id::text = %s) p WHERE chunk = %s""",
                (subject["company_key"], int(subject["chunk"])))
    batch = {r["ref"]: r["category"] for r in cur.fetchall()}
    dropped = {"not_in_batch": 0, "same_category": 0}
    for r in recs:
        old = batch.get(r["ref"])
        if r["ref"] not in batch:
            dropped["not_in_batch"] += 1
            continue
        if (old or "") == r["category"]:
            dropped["same_category"] += 1
            continue
        res.loaded.append(("competitive_product", r["ref"], False))
        if dry_run:
            continue
        cur.execute("UPDATE staging.competitive_product SET category = %s, category_filter = %s WHERE product_id = %s::uuid",
                    (r["category"], r["category"], r["ref"]))
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_product' AND column_name = 'category' AND row_id = %s", (r["ref"],))
        cur.execute("SELECT source_url FROM staging.fact_source WHERE table_name = 'competitive_product' AND column_name = 'product_name' AND row_id = %s "
                    "ORDER BY (source_tier = 'primary') DESC LIMIT 1", (r["ref"],))
        src = cur.fetchone()                      # the page the product rests on (source_url is NOT NULL): the reason is a judgement about it
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote)
                       VALUES ('competitive_product', %s, 'category', %s, 'judgement', NULL, %s)""",
                    (r["ref"], src["source_url"] if src else "", f"{r['reason']} (was {old})"[:300]))
    if res.loaded and not dry_run:
        cur.execute("""UPDATE staging.competitive_product p SET category_count = n.n FROM (
                         SELECT competitor_id, category, count(*) AS n FROM staging.competitive_product WHERE competitor_id::text = %s GROUP BY 1, 2) n
                       WHERE p.competitor_id = n.competitor_id AND p.category = n.category""", (subject["company_key"],))
    res.rows = len(res.loaded)
    res.details = {"batch": len(batch), "offered": len(recs), "moved": res.rows, "dropped": {k: v for k, v in dropped.items() if v}}
    res.note = f"{res.rows} of {len(batch)} products moved" + (f" (dropped: {res.details['dropped']})" if res.details["dropped"] else "")
    if not res.rows:
        res.skip_reason = (env.get("skip_reason") or "every product is in a fitting category")[:300]
    return res


def _selftest() -> None:
    allowed = {"Artillery", "Other", *CATALOGUE_ONLY}
    env = {"records": [{"values": {"product_ref": "a", "category": "sensors & electro-optics", "reason": "A radar."}},
                       {"values": {"product_ref": "b", "category": "Space", "reason": "x"}},
                       {"values": {"product_ref": "", "category": "Other"}}]}
    got, probs = clean(env, allowed)
    assert got == [{"ref": "a", "category": "Sensors & Electro-optics", "reason": "A radar."}] and len(probs) == 2
    print("product_category self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
