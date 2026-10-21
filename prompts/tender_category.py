"""Handler of prompts/tender_category.yml: the category of tender stubs the `tender` prompt has not read yet.

    python -m prompts.tender_category --selftest         pure checks, fictional values

A verdict is applied only when the tender_ref is one of the subject batch's tenders and that tender is still a stub without a category
(category_id NULL, description NULL: the tender prompt's own judgement always wins). A category name is checked against
staging.technology_category; "No category" / "Not defence" leave the category empty. Every applied verdict writes one staging.fact_source
row (market_tender, column category_id, tier judgement, the tender's own notice url, the model's reason): that row is also what takes the
tender out of the next batch. A tender with no notice url is not written (fact_source.source_url is NOT NULL). Same Result shape as
prompts/spec_enrich.
"""

from __future__ import annotations

import sys

from prompts.spec_enrich import Result

NONE = ("No category", "Not defence")


def clean(env: dict, allowed: set) -> tuple[list, list]:
    out, problems = [], []
    canon = {a.casefold(): a for a in (set(allowed) | set(NONE))}
    for r in env.get("records") or []:
        v = (r or {}).get("values") or {} if isinstance(r, dict) else {}
        ref, cat, reason = (" ".join(str(v.get(k) or "").split()) for k in ("tender_ref", "category", "reason"))
        if not ref or not cat or not reason:
            problems.append(f"incomplete record dropped: {ref or '?'}")
        elif cat.casefold() not in canon:
            problems.append(f"category not allowed, dropped: {cat!r}")
        else:
            out.append({"ref": ref, "category": canon[cat.casefold()], "reason": reason[:160]})
    return out, problems


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    res = Result()
    cur.execute("SELECT category_id, category_name FROM staging.technology_category")
    ids = {r["category_name"]: r["category_id"] for r in cur.fetchall()}
    recs, res.warnings = clean(env, set(ids))
    batch_ids = [int(x) for x in str(subject.get("tender_ids") or "").split(",") if x.strip().isdigit()]
    cur.execute("""SELECT t.tender_id::text AS ref, t.category_id, t.description IS NULL AS stub,
                          coalesce(t.source_url, (SELECT s.source_url FROM staging.market_tender_source s
                                                  WHERE s.tender_id = t.tender_id AND s.source_url IS NOT NULL
                                                  ORDER BY s.is_primary DESC NULLS LAST LIMIT 1)) AS url
                   FROM staging.market_tender t WHERE t.tender_id = ANY(%s)""", (batch_ids,))
    batch = {r["ref"]: r for r in cur.fetchall()}
    dropped = {"not_in_batch": 0, "already_categorised": 0, "no_url": 0, "repeat": 0}
    counts, seen = {}, set()
    for r in recs:
        t = batch.get(r["ref"])
        if t is None:
            dropped["not_in_batch"] += 1
            continue
        if r["ref"] in seen:
            dropped["repeat"] += 1
            continue
        seen.add(r["ref"])
        if t["category_id"] is not None or not t["stub"]:
            dropped["already_categorised"] += 1
            continue
        if not t["url"]:
            dropped["no_url"] += 1
            continue
        counts[r["category"]] = counts.get(r["category"], 0) + 1
        res.rows += 1
        cat = r["category"]
        if cat not in NONE:
            res.loaded.append(("market_tender", r["ref"], False))
        if dry_run:
            continue
        if cat not in NONE:
            cur.execute("UPDATE staging.market_tender SET category_id = %s, category_text = %s WHERE tender_id = %s",
                        (ids[cat], cat, int(r["ref"])))
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'market_tender' AND column_name = 'category_id' AND row_id = %s", (r["ref"],))
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote)
                       VALUES ('market_tender', %s, 'category_id', %s, 'judgement', NULL, %s)""",
                    (r["ref"], t["url"], (r["reason"] if cat not in NONE else f"{cat}: {r['reason']}")[:300]))
    missing = len(batch) - len(seen)
    res.details = {"batch": len(batch), "offered": len(recs), "verdicts": res.rows, "by_category": counts,
                   "dropped": {k: v for k, v in dropped.items() if v}, "not_answered": missing}
    res.note = (f"{res.rows} of {len(batch)} judged, {len(res.loaded)} categorised"
                + (f", {missing} not answered" if missing else "") + (f" (dropped: {res.details['dropped']})" if res.details["dropped"] else ""))
    if not res.rows:
        res.skip_reason = (env.get("skip_reason") or "no verdict could be applied")[:300]
    return res


def _selftest() -> None:
    allowed = {"Artillery", "Marine / Naval", "Other"}
    env = {"records": [{"values": {"tender_ref": "1", "category": "marine / naval", "reason": "Spare parts for a frigate."}},
                       {"values": {"tender_ref": "2", "category": "no category", "reason": "Body armour vests."}},
                       {"values": {"tender_ref": "3", "category": "Space", "reason": "x"}},
                       {"values": {"tender_ref": "4", "category": "Artillery"}}]}
    got, probs = clean(env, allowed)
    assert got == [{"ref": "1", "category": "Marine / Naval", "reason": "Spare parts for a frigate."},
                   {"ref": "2", "category": "No category", "reason": "Body armour vests."}], got
    assert len(probs) == 2
    print("tender_category self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
