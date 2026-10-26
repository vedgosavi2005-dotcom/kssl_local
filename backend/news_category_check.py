"""Company news categories, checked with the local model; and the Investments category (owner 2026-10-26).

    python -m backend.news_category_check --selftest
    python -m backend.news_category_check --ask --cache <file.jsonl> [--limit N] [--model gemma4-26b-gpu]
    python -m backend.news_category_check --report --cache <file.jsonl> [--out <file.json>]
    python -m backend.news_category_check --apply --cache <file.jsonl> [--dry-run]

Owner 2026-10-26: "when I click a filter, does each article shown really belong to that filter?", and a new category
Investments. Rows: competitive_news_article and competitive_competitor_moment (both feed the company News list and share the
news categories of prompts/news.yml). Rows already judged not about the company (fact_source not_about_company) are Other by
that rule and are not asked.

--ask   the local model (Ollama, this PC, no cost) reads each row's headline (+ the moment's summary), a batch at a time, without
        the stored category, and answers the best category, a second one that also fits ("" when none) and a quote. Answers go to
        the cache file (one JSON line per row; a re-run asks only rows not in it).
--report per stored category: rows, look right (stored category is one of the model's two), look wrong, unsure (no valid answer
        or the quote is not in the row's own text), with examples.
--apply in kssl_staging only (normal flow: the owner approves on the review site):
        * Investments added (keeping the stored category) when prompts/news_category.investment_rule says "yes", or says "maybe"
          and the model's answer has Investments with a quote found in the headline / summary. Never on a Non-defence business
          or a not-about-the-company row; a lone "Other" becomes Investments. One judgement fact_source row (column category).
        * a stored category is changed only when it is clear-cut wrong: the model's best category and the headline code rule
          (news_category.headline_category, or the signal's move for a moment) agree, and the stored category is neither of the
          model's two. The category's judgement fact_source row is replaced (rule + quote). Everything else is listed only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

from prompts.news_category import (HEADLINE_RULES, INVESTMENTS, MOVE_NEWS, NEWS_CATEGORIES, SEP, cats_of, headline_category,
                                   investment_rule,
                                   join_cats)
from prompts.spec_enrich import norm_text

OLLAMA = "http://127.0.0.1:11434/api/chat"
MODEL = "gemma4-26b-gpu"
BATCH = 25
TAG = "news category check 2026-10-26"


def system_prompt() -> str:
    from scripts.categorise_leftover_news import category_block
    return ("You sort defence-industry news into categories for a database a human reviews. For EACH row decide from its headline "
            "(and summary, when given) only, never from what you know elsewhere. Categorise what the story reports, also when the "
            "company is only one party in it. The categories (the same rules the news prompt uses):\n\n   " + category_block()
            + "\n\nFor each row answer: \"cat\": the one best category, written exactly; \"alt\": a second category that ALSO fits "
              "the same story well, written exactly, or \"\" when none does (e.g. a stated investment in a new plant: cat Facility & "
              "capacity, alt Investments); \"quote\": the exact words of the headline or summary that show cat, max 8 words.\n"
              'Return JSON: {"rows": [{"id": "<the row id exactly>", "cat": "...", "alt": "...", "quote": "..."}]} with one entry '
              "per row.")


def rows(cur) -> list[dict]:
    cur.execute("""SELECT 'competitive_news_article' AS tbl, a.article_id::text AS id, a.headline, ''::text AS summary, a.category,
                          coalesce(c.display_name, ca.client_name) AS company, coalesce(c.origin_country, 'India') AS home,
                          NULL::text AS move, NULL::text AS where_, EXISTS (SELECT 1 FROM staging.fact_source f
                              WHERE f.table_name = 'competitive_news_article' AND f.row_id = a.article_id::text
                                AND f.column_name = 'not_about_company') AS not_about
                   FROM staging.competitive_news_article a LEFT JOIN staging.competitive_competitor c ON c.competitor_id = a.competitor_id
                   LEFT JOIN LATERAL (SELECT client_name FROM staging.client_account ORDER BY client_id LIMIT 1) ca ON c.competitor_id IS NULL
                   UNION ALL
                   SELECT 'competitive_competitor_moment', m.moment_id::text, m.title, left(coalesce(m.what_happened, ''), 400), m.category,
                          c.display_name, c.origin_country, d.glance_move, m.country_name, false
                   FROM staging.competitive_competitor_moment m LEFT JOIN staging.competitive_competitor c ON c.competitor_id = m.competitor_id
                   LEFT JOIN staging.competitive_signal_detail d ON d.signal_id = m.signal_id
                   ORDER BY 1, 2""")
    return [dict(r) for r in cur.fetchall()]


def ask(model: str, batch: list[dict]) -> list[dict]:
    text = "\n".join(f"ROW id={r['h']} | company: {r['company']} (home country: {r['home'] or 'not stated'})"
                     + (f" | where: {r['where_']}" if r.get("where_") else "") + f" | headline: {' '.join(str(r['headline'] or '').split())}"
                     + (f" | summary: {' '.join(r['summary'].split())}" if r.get("summary") else "") for r in batch)
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_predict": 4000},
            "messages": [{"role": "system", "content": system_prompt()}, {"role": "user", "content": text}]}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(json.load(r)["message"]["content"])
    return out.get("rows") or [] if isinstance(out, dict) else []


def canon(c) -> str:
    c = str(c or "").strip().lower()
    return next((x for x in NEWS_CATEGORIES if x.lower() == c), "")


def quote_ok(quote, row) -> bool:
    """The quote is in the row's own headline / summary (case, quotes, dashes folded), or nearly all its words are."""
    own = norm_text(f"{row['headline']} {row.get('summary') or ''}")
    q = norm_text(quote)
    words = [w for w in re.findall(r"[a-z0-9]+", q) if len(w) > 2]
    return bool(q) and (q in own or (len(words) >= 2 and sum(w in own for w in words) / len(words) >= 0.8)
                        or (len(words) == 1 and words[0] in own))


def check(answer: dict, row: dict) -> tuple[dict | None, str]:
    """({cat, alt, quote}, "") when the answer may be used, else (None, why not)."""
    cat, alt = canon(answer.get("cat")), canon(answer.get("alt"))
    if not cat:
        return None, f"unknown category {answer.get('cat')!r}"
    if str(answer.get("alt") or "").strip() and not alt:
        alt = ""                                                    # a bad second answer is dropped, the first stands
    quote = " ".join(str(answer.get("quote") or "").split())
    if not quote_ok(quote, row):
        return None, "quote not in the row's own text"
    return {"cat": cat, "alt": alt if alt != cat else "", "quote": quote}, ""


def code_category(row) -> str | None:
    """The code rule's category: the signal's move for a moment that has one, else the headline rule."""
    if row["tbl"] == "competitive_competitor_moment" and row.get("move") in MOVE_NEWS:
        return MOVE_NEWS[row["move"]]
    return headline_category(row["headline"])


_RULE = dict(HEADLINE_RULES)


# words that back a stored category beyond the headline rule's own (the headline rule picks one family; these keep a story
# that also fits its stored category from being "fixed"): a production line is a facility, a delay or an operational launch is
# about delivery, a demo is a test, a regulator / court / accident story is Other.
_SUPPORT = {"Facility & capacity": r"\bproduction\b|\bmanufactur\w*|\bsite\b|\bcampus\b|\bshipbuilding\b|\bshipyard\b",
            "Delivery & induction": r"\bdelay\w*|\boperational\b|\bdeliver\w*|\binduct\w*",
            "Product launch & testing": r"\bdemos?\b|\bdemonstrat\w*|\bshowcas\w*|\btest\w*|\btrials?\b",
            "Other": r"\bsebi\b|\bregulator\w*|\bcourt\b|\blawsuit\b|\bprobe\b|\bpenalt\w*|\bfined?\b|\baccident\b|\bexplosion\b|"
                     r"\bblast\b|\bfire\b|\bcrash\w*|\bkilled\b|\bstrike\b|\bhonou?r\w*|\baward(?:ed)? (?:for|as)\b"}
# a fix whose only evidence is one of these words is not clear-cut: "launch" (a programme / operational / production launch),
# "deal" (a partnership is a deal too)
_AMBIGUOUS = {"Product launch & testing": r"\blaunch(?:es|ed|ing)?\b", "Contract & order": r"\bdeal\b"}
# pairs the headline rule cannot tell apart: where the buyer is (Export / Contract), who wrote it (a company report / a broker note)
_PAIRS = ({"Export", "Contract & order"}, {"Stock & market", "Financial results"})


def not_doubtful(stored: str, code: str, row) -> bool:
    """Model + code agreeing is clear-cut only when the code rule can really tell the two apart and nothing backs the stored one:
      * not a pair the headline rule cannot separate (_PAIRS); Investments is never a replacement, only an addition;
      * a Non-defence business row stays (neither the model nor the rule judges the defence angle);
      * an "Other" row is fixed only when its headline names the company (a digest, a sector review or an evergreen page that
        does not is Other by the news prompt's rule);
      * no word of the stored category's family (_RULE, _SUPPORT) is in the headline, and the new category's evidence is more
        than one ambiguous word (_AMBIGUOUS)."""
    from prompts.news_category import names_company
    h = str(row["headline"] or "")
    if {stored, code} in _PAIRS or INVESTMENTS in (stored, code) or stored == "Non-defence business":
        return False
    if stored == "Other" and not names_company(h, row.get("company")):
        return False
    for pat in (_RULE.get(stored), _SUPPORT.get(stored)):
        if pat and re.search(pat, h, re.I):
            return False
    amb = _AMBIGUOUS.get(code)
    if amb:
        rest = re.sub(amb, " ", h, flags=re.I)
        if re.search(amb, h, re.I) and not re.search(_RULE[code], rest, re.I):
            return False
    return True


def model_investment_clear(ans: dict, row, cats: list[str]) -> bool:
    """A "maybe" row gets Investments from the model only when it is the model's best category, or its second one with an amount
    stated in the headline / summary ("an expansion WITH a stated investment amount"). A sale (Contract & order / Export) is
    listed instead: there the money is usually the buyer's, not the company's."""
    from prompts.news_category import _AMOUNT
    if {"Contract & order", "Export"} & set(cats):
        return False
    return ans["cat"] == INVESTMENTS or bool(re.search(_AMOUNT, f"{row['headline']} {row.get('summary') or ''}", re.I))


def load_cache(path: str) -> dict:
    out = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    out[d["key"]] = d
    return out


def key(row) -> str:
    return f"{row['tbl']}:{row['id']}"


def run_ask(model: str, cache: str, limit: int | None) -> None:
    from prompts.run import connect
    conn = connect()
    with conn.cursor() as cur:
        allrows = rows(cur)
    conn.close()
    done = load_cache(cache)
    todo = [r for r in allrows if not r["not_about"] and key(r) not in done][: limit or None]
    print(f"{len(allrows)} rows, {sum(r['not_about'] for r in allrows)} not about the company (not asked), "
          f"{len(done)} answered before, {len(todo)} to ask", flush=True)
    import time
    t0 = time.time()
    with open(cache, "a", encoding="utf-8") as out:
        for i in range(0, len(todo), BATCH):
            batch = [dict(r, h=f"R{j + 1}") for j, r in enumerate(todo[i:i + BATCH])]
            by_h = {r["h"]: r for r in batch}
            try:
                answers = ask(model, batch)
            except Exception as e:  # noqa: BLE001
                print(f"  batch {i // BATCH + 1}: model error {e}", flush=True)
                continue
            for a in answers:
                r = by_h.pop(str(a.get("id") or "").strip(), None)
                if r is not None:
                    out.write(json.dumps({"key": key(r), "answer": {k: a.get(k) for k in ("cat", "alt", "quote")}}, ensure_ascii=False) + "\n")
            out.flush()
            n = min(i + BATCH, len(todo))
            print(f"batch {i // BATCH + 1}/{(len(todo) + BATCH - 1) // BATCH}: {n} asked, {len(by_h)} unanswered, "
                  f"{(time.time() - t0) / n:.2f} s/row", flush=True)


def judge(allrows: list[dict], cache: dict) -> list[dict]:
    """Every row with its verdict: stored cats, model answer (or why not), code category, investment rule, the planned change."""
    out = []
    for r in allrows:
        stored = cats_of(r["category"])
        ans, why = (None, "not asked")
        c = cache.get(key(r))
        if c:
            ans, why = check(c["answer"], r)
        model = {ans["cat"], ans["alt"]} - {""} if ans else set()
        code = code_category(r)
        inv, inv_words = investment_rule(r["headline"], r.get("summary"), r["company"])
        v = dict(r, stored=stored, ans=ans, why=why, model=model, code=code, inv=inv, inv_words=inv_words)
        # the category change (clear-cut wrong only); Investments is judged on its own below
        base = [s for s in stored if s != INVESTMENTS]
        v["verdict"] = {}
        for s in base:
            v["verdict"][s] = ("other-not-about" if r["not_about"] else "unsure" if not ans
                               else "right" if s in model else "wrong")
        v["fix"] = None
        if (not r["not_about"] and ans and len(base) == 1 and base[0] not in model and code and code == ans["cat"]
                and code != base[0] and not_doubtful(base[0], code, r)):
            v["fix"] = code
        # Investments
        new_cats = [v["fix"]] if v["fix"] else list(base)
        add, basis = False, ""
        if not r["not_about"] and "Non-defence business" not in new_cats and INVESTMENTS not in stored:
            if inv == "yes":
                add, basis = True, f"the code rule finds \"{inv_words}\""
            elif inv == "maybe" and ans and INVESTMENTS in model and model_investment_clear(ans, r, new_cats):
                add, basis = True, f"the local model finds an investment (\"{ans['quote']}\"), the code rule an investment word (\"{inv_words}\")"
        v["inv_add"], v["inv_basis"] = add, basis
        v["inv_doubt"] = bool(not add and not r["not_about"] and INVESTMENTS not in stored
                              and ((ans and INVESTMENTS in model and inv != "no" and "Non-defence business" not in new_cats)
                                   or (inv == "maybe" and c and canon(c["answer"].get("cat")) == INVESTMENTS and not ans)))
        if add:
            new_cats = [x for x in new_cats if x != "Other"] + [INVESTMENTS]
        elif INVESTMENTS in stored:
            new_cats = new_cats + [INVESTMENTS]
        v["new"] = join_cats(new_cats)
        out.append(v)
    return out


def report(verdicts: list[dict], out_path: str | None) -> dict:
    per: dict[str, dict] = {}
    for v in verdicts:
        for s, verdict in v["verdict"].items():
            p = per.setdefault(s, {"rows": 0, "right": 0, "wrong": 0, "unsure": 0, "other-not-about": 0, "wrong_examples": [],
                                   "fixed": 0})
            p["rows"] += 1
            p[verdict] += 1
            if verdict == "wrong":
                ex = {"table": v["tbl"], "id": v["id"], "company": v["company"], "headline": v["headline"], "stored": v["category"],
                      "model": f"{v['ans']['cat']}" + (f" / {v['ans']['alt']}" if v["ans"]["alt"] else ""), "quote": v["ans"]["quote"],
                      "code": v["code"], "fix": v["fix"]}
                p["wrong_examples"].append(ex)
            if v["fix"] and s == v["stored"][0]:
                p["fixed"] += 1
    res = {"per_category": per,
           "investments": {"yes_rule": [x for x in verdicts if x["inv_add"] and x["inv"] == "yes"],
                           "maybe_model": [x for x in verdicts if x["inv_add"] and x["inv"] == "maybe"],
                           "doubtful": [x for x in verdicts if x["inv_doubt"]]},
           "fixes": [x for x in verdicts if x["fix"]]}
    print(f"{'category':26} {'rows':>6} {'right':>6} {'wrong':>6} {'unsure':>6} {'not-about':>9} {'fixed':>6}")
    for s in sorted(per, key=lambda k: -per[k]["rows"]):
        p = per[s]
        print(f"{s:26} {p['rows']:6} {p['right']:6} {p['wrong']:6} {p['unsure']:6} {p['other-not-about']:9} {p['fixed']:6}")
    print(f"Investments: {len(res['investments']['yes_rule'])} by the code rule, {len(res['investments']['maybe_model'])} by rule + "
          f"model, {len(res['investments']['doubtful'])} doubtful (listed only); clear-cut fixes: {len(res['fixes'])}")
    if out_path:
        slim = lambda x: {k: (sorted(x[k]) if isinstance(x[k], set) else x[k]) for k in x if k not in ("h",)}  # noqa: E731
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"per_category": per, "investments": {k: [slim(x) for x in v] for k, v in res["investments"].items()},
                       "fixes": [slim(x) for x in res["fixes"]]}, f, ensure_ascii=False, indent=1, default=str)
    return res


def _cite(cur, table: str, row_id: str, quote: str, replace: bool) -> None:
    if replace:
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s AND column_name = 'category'", (table, row_id))
    cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at)
                   VALUES (%s, %s, 'category', 'judgement', 'judgement', %s, now())""", (table, row_id, quote[:1000]))


def run_apply(cache: str, dry: bool, model: str) -> None:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT current_database() AS d")
    db = cur.fetchone()["d"]
    if db != "kssl_staging" and not db.startswith("kssl_test"):
        raise SystemExit(f"refused: database {db} (kssl_staging or kssl_test_* only)")
    verdicts = judge(rows(cur), load_cache(cache))
    changed = 0
    for v in verdicts:
        if v["new"] == SEP.join(v["stored"]) or not v["new"]:
            continue
        idcol = "article_id" if v["tbl"] == "competitive_news_article" else "moment_id"
        cur.execute(f"UPDATE staging.{v['tbl']} SET category = %s WHERE {idcol}::text = %s AND category IS NOT DISTINCT FROM %s",
                    (v["new"], v["id"], v["category"]))
        if cur.rowcount != 1:
            print(f"  skipped (changed meanwhile) {v['id']}")
            continue
        changed += 1
        if v["fix"]:
            how = "the moment's signal move" if v["tbl"] == "competitive_competitor_moment" and v.get("move") in MOVE_NEWS else "the headline code rule"
            _cite(cur, v["tbl"], v["id"], f"{v['fix']}: the local model ({model}) and {how} (prompts/news_category.py) agree "
                                          f"(\"{v['ans']['quote']}\"); was {v['category']} ({TAG}).", replace=True)
        if v["inv_add"]:
            dropped_other = "Other" in v["stored"] and not v["fix"]
            _cite(cur, v["tbl"], v["id"], f"Investments: {v['inv_basis']} (prompts/news_category.py investment_rule"
                                          + (f", local model {model}" if v["inv"] == "maybe" else "") + f"; {TAG})."
                                          + (" Was Other, which is only for when no category fits." if dropped_other else ""),
                  replace=dropped_other)
        print(f"  {v['category'] or '-':28} -> {v['new']:40} | {v['company'][:16]:16} | {str(v['headline'])[:80]}")
    print(f"{changed} rows {'would change (dry run, rolled back)' if dry else 'changed'}")
    conn.rollback() if dry else conn.commit()
    conn.close()


def _selftest() -> None:
    row = {"tbl": "competitive_news_article", "headline": "BAE Systems Invests $135M to Expand US Defense Manufacturing Facilities",
           "summary": "", "company": "BAE Systems", "move": None}
    assert check({"cat": "facility & capacity", "alt": "Investments", "quote": "Invests $135M to Expand"}, row)[0] == \
        {"cat": "Facility & capacity", "alt": "Investments", "quote": "Invests $135M to Expand"}
    assert check({"cat": "Facility & capacity", "alt": "", "quote": "builds a new plant"}, row)[0] is None        # not its words
    assert check({"cat": "Plants", "alt": "", "quote": "Invests"}, row)[0] is None                              # not a category
    assert check({"cat": "Export", "alt": "Export", "quote": "US Defense"}, row)[0]["alt"] == ""                 # alt = cat dropped
    assert quote_ok("invests $135m to expand us defense", row) and not quote_ok("", row)
    base = dict(row, id="x", category="Facility & capacity", not_about=False, where_=None, home="UK")
    cache = {"competitive_news_article:x": {"answer": {"cat": "Facility & capacity", "alt": "Investments", "quote": "Invests $135M"}}}
    v = judge([base], cache)[0]
    assert v["verdict"] == {"Facility & capacity": "right"} and v["inv_add"] and v["new"] == "Facility & capacity · Investments"
    wrong = dict(base, id="y", headline="Nordvik wins Army order for 155 mm shells", category="Other", company="Nordvik")
    cache["competitive_news_article:y"] = {"answer": {"cat": "Contract & order", "alt": "", "quote": "wins Army order"}}
    v = judge([wrong], cache)[0]
    assert v["verdict"] == {"Other": "wrong"} and v["fix"] == "Contract & order" and v["new"] == "Contract & order"
    doubt = dict(wrong, id="z", headline="Nordvik signs Veland order and tests shells", category="Other")
    cache["competitive_news_article:z"] = {"answer": {"cat": "Export", "alt": "", "quote": "signs Veland order"}}
    v = judge([doubt], cache)[0]
    assert v["verdict"] == {"Other": "wrong"} and v["fix"] is None and v["new"] == "Other"                   # code unclear: listed only
    exp = dict(wrong, id="e", headline="Nordvik USA gets U.S. Army order for three howitzers", category="Export")
    cache["competitive_news_article:e"] = {"answer": {"cat": "Contract & order", "alt": "", "quote": "gets U.S. Army order"}}
    assert judge([exp], cache)[0]["fix"] is None                                    # the code rule cannot see the buyer's country
    fac = dict(wrong, id="f", headline="Nordvik opens a test plant for shells", category="Facility & capacity")
    cache["competitive_news_article:f"] = {"answer": {"cat": "Product launch & testing", "alt": "", "quote": "test plant"}}
    assert judge([fac], cache)[0]["fix"] is None                                    # "plant" backs the stored category
    dig = dict(wrong, id="d", headline="June drone digest: landmark CCA contract at Eurosatory", category="Other")
    cache["competitive_news_article:d"] = {"answer": {"cat": "Contract & order", "alt": "", "quote": "landmark CCA contract"}}
    assert judge([dig], cache)[0]["fix"] is None                                    # an "Other" digest that does not name it
    lau = dict(wrong, id="l", headline="Nordvik K9 set for 2027 operational launch", category="Delivery & induction")
    cache["competitive_news_article:l"] = {"answer": {"cat": "Product launch & testing", "alt": "", "quote": "operational launch"}}
    assert judge([lau], cache)[0]["fix"] is None                                    # "operational" backs Delivery; "launch" alone
    sale = dict(wrong, id="s", headline="Nordvik signs deal; investment in radar", category="Contract & order")
    cache["competitive_news_article:s"] = {"answer": {"cat": "Investments", "alt": "", "quote": "investment in radar"}}
    v = judge([sale], cache)[0]
    assert not v["inv_add"] and v["inv_doubt"] and v["new"] == "Contract & order"   # a sale: listed for the owner, not added
    na = dict(wrong, id="n", not_about=True)
    v = judge([na], {})[0]
    assert v["verdict"] == {"Other": "other-not-about"} and v["fix"] is None and v["new"] == "Other"
    civil = dict(base, id="c", headline="Nordvik to invest Rs 25,000 cr in a data centre", category="Non-defence business", company="Nordvik")
    assert judge([civil], {})[0]["new"] == "Non-defence business"
    print("news_category_check self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--ask", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cache", default=os.path.join(os.environ.get("TEMP", "."), "kssl_news_category_check.jsonl"))
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
    elif a.ask:
        run_ask(a.model, a.cache, a.limit)
    elif a.report:
        from prompts.run import connect
        conn = connect()
        with conn.cursor() as cur:
            report(judge(rows(cur), load_cache(a.cache)), a.out)
        conn.close()
    elif a.apply:
        run_apply(a.cache, a.dry_run, a.model)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
