"""The news rows no code rule could categorise (functional test G5, owner-approved prompt run 2026-10-25).

    python -m scripts.categorise_leftover_news --selftest
    python -m scripts.categorise_leftover_news [--estimate | --apply] [--max-usd 3]

Rows: competitive_competitor_moment rows whose category is not one of the news categories, and competitive_news_article rows
with no category (prompts/news_category.py left them). One model call (the news prompt's model, headlines + stored description,
no web search) answers one category per row from the SAME category definitions as prompts/news.yml (read from that file, so
the two never drift). Each answer must be one of the twelve categories; it is stored with a judgement fact_source row holding
the model's one-sentence reason. The call is logged in staging.prompt_run (prompt_id news_leftover). kssl_staging / kssl_test_* only.
"""

from __future__ import annotations

import json
import re
import sys

from prompts.news_category import NEWS_CATEGORIES

PROMPT_ID = "news_leftover"
MAX_USD = 3.0
# Sonnet list prices per million tokens (input, output), for the estimate printed before the call
PRICE = (3.0, 15.0)


def category_block() -> str:
    from prompts import render
    t = render.load_prompt("news")["task"]
    i = t.index("- category: exactly one")
    j = t.index("Give a category for every story")
    return t[i:j].rstrip()


def rows(cur) -> list[dict]:
    cur.execute("""SELECT 'M' || m.moment_id::text AS handle, 'competitive_competitor_moment' AS tbl, m.moment_id::text AS id,
                          m.title AS headline, left(coalesce(m.what_happened, m.description, ''), 400) AS detail,
                          c.display_name AS company, c.origin_country AS home, m.country_name AS where_
                   FROM staging.competitive_competitor_moment m LEFT JOIN staging.competitive_competitor c ON c.competitor_id = m.competitor_id
                   WHERE m.category IS NULL OR NOT (string_to_array(m.category, ' · ') <@ %s::text[])
                   UNION ALL
                   SELECT 'N' || a.article_id::text, 'competitive_news_article', a.article_id::text, a.headline, left(coalesce(a.description, ''), 400),
                          coalesce(c.display_name, ca.client_name), coalesce(c.origin_country, 'India'), NULL
                   FROM staging.competitive_news_article a LEFT JOIN staging.competitive_competitor c ON c.competitor_id = a.competitor_id
                   LEFT JOIN LATERAL (SELECT client_name FROM staging.client_account ORDER BY client_id LIMIT 1) ca ON c.competitor_id IS NULL
                   WHERE coalesce(trim(a.category), '') = ''
                   ORDER BY 1""", (list(NEWS_CATEGORIES),))
    return [dict(r) for r in cur.fetchall()]


SYSTEM = ("You categorise defence-industry news for a database that a human reviews before it is shown. Decide from the headline and "
          "the stored description only. Reply with JSON only, no prose.")


def build_prompt(items: list[dict]) -> str:
    lines = [f'{r["handle"]} | company: {r["company"]} (home country: {r["home"] or "not stated"})'
             + (f' | where: {r["where_"]}' if r.get("where_") else "")
             + f' | headline: {r["headline"]}' + (f' | description: {r["detail"]}' if r.get("detail") else "") for r in items]
    return ("Give each news row below exactly one category from this list, under these rules (the same rules the news prompt uses):\n\n   "
            + category_block() + "\n\nROWS (handle | company | headline | description):\n" + "\n".join(lines)
            + '\n\nReply as JSON: {"<handle>": {"category": "<one of the twelve, written exactly>", "reason": "<one plain sentence>"}, ...} '
              "with every handle once.")


def parse_answer(text: str, handles: list[str]) -> tuple[dict, list[str]]:
    """{handle: (category, reason)} for valid answers, and the problems (missing handle, unknown category)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}, ["no JSON object in the reply"]
    data = json.loads(m.group(0))
    out, problems = {}, []
    for h in handles:
        v = data.get(h)
        cat = (v or {}).get("category") if isinstance(v, dict) else None
        if cat not in NEWS_CATEGORIES:
            problems.append(f"{h}: {'no answer' if v is None else f'unknown category {cat!r}'}")
            continue
        out[h] = (cat, str(v.get("reason") or "").strip()[:300])
    return out, problems


def estimate(prompt: str) -> float:
    tok_in = (len(prompt) + len(SYSTEM)) / 3.5 + 2000          # characters -> tokens, plus the CLI's own overhead
    tok_out = prompt.count("\n") * 45
    return round(tok_in / 1e6 * PRICE[0] + tok_out / 1e6 * PRICE[1], 3)


def main(apply: bool, max_usd: float) -> None:
    import psycopg2.extras
    from prompts import render
    from prompts.claude_call import call_model
    from prompts.run import connect
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS d")
        db = cur.fetchone()["d"]
        if db != "kssl_staging" and not db.startswith("kssl_test"):
            raise SystemExit(f"refused: database {db} (kssl_staging or kssl_test_* only)")
        items = rows(cur)
        prompt = build_prompt(items)
        est = estimate(prompt)
        print(f"{len(items)} rows; estimated cost ${est} (cap ${max_usd})")
        if not apply:
            conn.rollback()
            return
        if est >= max_usd:
            raise SystemExit("estimate over the cap: not run")
        model = render.load_prompt("news")["model"]
        res = call_model(SYSTEM, prompt, model)
        answers, problems = parse_answer(res.text, [r["handle"] for r in items])
        by = {r["handle"]: r for r in items}
        for h, (cat, why) in answers.items():
            r = by[h]
            key = "moment_id" if r["tbl"] == "competitive_competitor_moment" else "article_id"
            cur.execute(f"UPDATE staging.{r['tbl']} SET category = %s WHERE {key}::text = %s", (cat, r["id"]))
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s AND column_name = 'category'", (r["tbl"], r["id"]))
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at)
                           VALUES (%s, %s, 'category', 'judgement', 'judgement', %s, now())""",
                        (r["tbl"], r["id"], f"{why} (model {model}, news categories of prompts/news.yml, G5 2026-10-25)"))
        cur.execute("""INSERT INTO staging.prompt_run (prompt_id, prompt_version, subject_key, model, web_search, seconds, tokens_in, tokens_out,
                                                       cost_usd, status, error, rows_loaded, loaded, prompt_text, raw_output, finished_at)
                       VALUES (%s, '1', 'G5 leftovers 2026-10-25', %s, false, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                    (PROMPT_ID, model, res.seconds, res.tokens_in, res.tokens_out, res.cost_usd, "loaded" if answers else "failed",
                     "; ".join(problems) or None, len(answers),
                     psycopg2.extras.Json([{"table": by[h]["tbl"], "id": by[h]["id"], "card": False} for h in answers]),
                     f"SYSTEM:\n{SYSTEM}\n\nPROMPT:\n{prompt}", res.text))
        conn.commit()
        print(f"applied {len(answers)} of {len(items)}; problems: {problems or 'none'}; actual cost ${res.cost_usd} "
              f"({res.tokens_in} tokens in, {res.tokens_out} out, {res.seconds} s)")
        for h, (cat, why) in answers.items():
            print(f"  {h[:12]} {cat:26} | {by[h]['headline'][:80]}")
    conn.close()


def _selftest() -> None:
    a, p = parse_answer('x {"M1": {"category": "Export", "reason": "r"}, "M2": {"category": "Marine / Naval"}} y', ["M1", "M2", "M3"])
    assert a == {"M1": ("Export", "r")} and len(p) == 2 and "unknown category" in p[0] and "no answer" in p[1]
    assert parse_answer("no json", ["M1"]) == ({}, ["no JSON object in the reply"])
    blk = category_block()
    assert all(c in blk for c in NEWS_CATEGORIES), "news.yml category list and NEWS_CATEGORIES drifted apart"
    pr = build_prompt([{"handle": "M1", "company": "Nordvik", "home": "Veland", "where_": "Norland", "headline": "H", "detail": ""}])
    assert "M1 | company: Nordvik (home country: Veland) | where: Norland | headline: H" in pr and estimate(pr) < 0.1
    print("categorise_leftover_news self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        cap = float(sys.argv[sys.argv.index("--max-usd") + 1]) if "--max-usd" in sys.argv else MAX_USD
        main(apply="--apply" in sys.argv, max_usd=cap)
