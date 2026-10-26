"""Fill competitive_partnership.region where the partnership prompt left it empty (owner 2026-10-25: the Partnership region view
put 220 of 408 partners under "Unknown" -- "it can be resolved").

    python -m backend.partner_region --selftest
    python -m backend.partner_region [--dry-run] [--no-model] [--model gemma4-26b-gpu] [--web [--limit N]]

Two passes, staging only, a row is only filled when its region is empty:
  1. the same partner elsewhere: another partnership row of that partner with a region, or a tracked competitor of that name
     (names folded: case, "Ltd" / "Limited" / "Pvt" / "Inc" / "AG" / brackets). Source: judgement, naming the row it came from.
  2. the row's own description says where the partner is ("a Utah-based firm", "a regional government in China"): the local model
     (Ollama, no cost) answers a country and the words that say so; code keeps it only when those words are in the description and
     the country is one the data already uses. Source: judgement, with the quote.
  3. --web (paid, owner 2026-10-25: "sourced web lookup"): Claude with web search finds each remaining partner's home country on
     the partner's own site or a registry / news page, with the URL and a quote. Code keeps it only with an http(s) URL that is not
     Wikipedia or a blog, a quote, and a plain country name. Source: the URL (primary when it is the partner's own site).
Anything else stays empty (shown as "Unknown"): no guess from a company's name.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
BATCH = 20
_SUFFIX = re.compile(r"\b(?:ltd|limited|pvt|private|inc|incorporated|corp|corporation|co|plc|ag|gmbh|sa|s\.a|llc|group|the)\b\.?", re.I)
ALIASES = {"usa": "United States", "us": "United States", "u.s.": "United States", "uk": "United Kingdom", "korea": "South Korea",
           "republic of korea": "South Korea", "uae": "United Arab Emirates", "czechia": "Czech Republic"}

SYSTEM = """For each row, say which country the PARTNER (the named company or body) is based in, using ONLY the row's description.
Answer a country only when the description says it: a country, a city or state ("Utah-based", "in Bengaluru"), a nationality
("an Israeli firm"), or a national body ("India's Ministry of Defence", "the Indian Navy" for an Indian state company).
Where the deal or factory is located is NOT where the partner is based. If the description does not say, answer null.
Return JSON: {"rows": [{"id": "<row id>", "country": "<English short country name or null>",
 "quote": "<the exact words from the description that say it, max 10 words>"}]}"""


def fold(name: str) -> str:
    s = re.sub(r"\([^)]*\)", " ", str(name or "")).lower().replace("&", " and ")
    return " ".join(_SUFFIX.sub(" ", s).replace(",", " ").split())


def norm_country(c: str | None, known: set[str]) -> str | None:
    t = " ".join(str(c or "").split()).strip(" .")
    if not t or t.lower() in ("null", "none", "unknown"):
        return None
    t = ALIASES.get(t.lower(), t)
    return next((k for k in known if k.lower() == t.lower()), None)


def check(answer: dict, desc: str, known: set[str]) -> str | None:
    country = norm_country(answer.get("country"), known)
    quote = " ".join(str(answer.get("quote") or "").split()).lower()
    text = " ".join(str(desc or "").split()).lower()
    return country if country and len(quote) >= 3 and quote in text else None


def ask(model: str, rows: list[dict]) -> list[dict]:
    text = "\n".join(f"ROW id={r['id']} | partner: {r['partner']} | description: {' '.join(str(r['description'] or '').split())[:600]}"
                     for r in rows)
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_predict": 2500},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(json.load(r)["message"]["content"])
    return out.get("rows") or [] if isinstance(out, dict) else []


WEB_SYSTEM = """You find where defence-industry partner organisations are headquartered. For each partner, use web search to find
its home country (headquarters) on the organisation's own website (about / contact / imprint page) or, failing that, a company
registry or a reputable news page. Never use Wikipedia, blogs or forums. The description tells you which organisation is meant.
Return ONLY JSON: {"rows": [{"partner": "<the partner name exactly as given>", "country": "<English short country name, or null>",
 "source_url": "<the page that states it>", "own_site": <true if that page is the partner's own website>,
 "quote": "<the words on that page that state the location, max 20 words>"}]}"""
_BAD_SRC = re.compile(r"wikipedia\.org|wikiwand|blogspot|wordpress\.com|medium\.com|substack|reddit\.com|quora\.com|fandom\.com", re.I)
_VAGUE = re.compile(r"^(?:europe|global|international|worldwide|multinational|eu|nato|asia|middle east)$", re.I)


def web_check(a: dict, known: set[str]) -> tuple[str, str, str] | None:
    """(country, url, quote) when a web answer may be stored"""
    url = str(a.get("source_url") or "").strip()
    quote = " ".join(str(a.get("quote") or "").split())
    raw = " ".join(str(a.get("country") or "").split()).strip(" .")
    country = norm_country(raw, known) or (ALIASES.get(raw.lower(), raw) if re.fullmatch(r"[A-Z][A-Za-z .'-]{2,40}", raw) else None)
    if (not country or _VAGUE.match(country) or country.lower() in ("null", "none", "unknown")
            or not re.match(r"https?://", url) or _BAD_SRC.search(url) or len(quote) < 3):
        return None
    return country, url, quote


def web_pass(cur, rows: list[dict], known: set[str], dry: bool, limit: int | None) -> None:
    from prompts.claude_call import call_model
    names: dict[str, dict] = {}
    for r in rows:
        if not (r["region"] or "").strip():
            names.setdefault(r["partner"], r)
    todo = list(names.values())[:limit] if limit else list(names.values())
    cost, kept = 0.0, 0
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        task = "\n".join(f"PARTNER: {r['partner']} | description: {' '.join(str(r['description'] or '').split())[:300]}" for r in batch)
        try:
            res = call_model(WEB_SYSTEM, task, "sonnet", web_search=True)
        except Exception as e:  # noqa: BLE001
            print(f"  web batch {i // 10 + 1}: {e}")
            continue
        cost += res.cost_usd or 0
        m = re.search(r"\{.*\}", res.text, re.S)
        try:
            answers = json.loads(m.group(0)).get("rows") or [] if m else []
        except ValueError:
            answers = []
        for a in answers:
            r = next((x for x in batch if x["partner"].strip().lower() == str(a.get("partner") or "").strip().lower()), None)
            got = r and web_check(a, known)
            if not got:
                if r:
                    print(f"  -                      | {r['partner'][:40]:40} | not kept: {str(a.get('country'))[:20]} {str(a.get('source_url'))[:60]}")
                continue
            country, url, quote = got
            kept += 1
            print(f"  {country:22} | {r['partner'][:40]:40} | {url[:70]}")
            if dry:
                continue
            cur.execute("SELECT relationship_id::text FROM staging.competitive_partnership WHERE partner_name = %s AND coalesce(trim(region), '') = ''",
                        (r["partner"],))
            for (rid,) in [tuple(x.values()) if isinstance(x, dict) else x for x in cur.fetchall()]:
                cur.execute("UPDATE staging.competitive_partnership SET region = %s WHERE relationship_id = %s::uuid", (country, rid))
                cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_partnership' AND column_name = 'region' AND row_id = %s",
                            (rid,))
                cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                               VALUES ('competitive_partnership', %s, 'region', %s, %s, %s)""",
                            (rid, url, "primary" if a.get("own_site") is True else "independent", quote[:400]))
        print(f"web batch {i // 10 + 1}/{(len(todo) + 9) // 10}: kept {kept}, cost so far ${cost:.2f}", flush=True)


def run(model: str, dry: bool, use_model: bool, web: bool = False, limit: int | None = None) -> None:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT relationship_id::text AS id, partner_name AS partner, region, description FROM staging.competitive_partnership")
    rows = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT display_name, short_name, legal_name, origin_country FROM staging.competitive_competitor")
    comps = [dict(r) for r in cur.fetchall()]
    known_countries = {r["region"] for r in rows if r["region"]} | {c["origin_country"] for c in comps if c["origin_country"]}
    by_name: dict[str, tuple[str, str]] = {}
    for r in rows:
        if r["region"] and norm_country(r["region"], known_countries):
            by_name.setdefault(fold(r["partner"]), (r["region"], f"same partner, partnership row {r['id']}"))
    for c in comps:
        for n in (c["display_name"], c["short_name"], c["legal_name"]):
            if n and c["origin_country"]:
                by_name.setdefault(fold(n), (c["origin_country"], f"tracked competitor {c['display_name']}"))

    def put(r, country, quote):
        print(f"  {country:22} | {r['partner'][:40]:40} | {quote[:70]}")
        if dry:
            return
        cur.execute("UPDATE staging.competitive_partnership SET region = %s WHERE relationship_id = %s::uuid AND coalesce(trim(region), '') = ''",
                    (country, r["id"]))
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_partnership' AND column_name = 'region' AND row_id = %s",
                    (r["id"],))
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                       VALUES ('competitive_partnership', %s, 'region', 'judgement', 'judgement', %s)""", (r["id"], quote[:400]))

    if web:
        web_pass(cur, rows, known_countries, dry, limit)
        if dry:
            conn.rollback()
        else:
            conn.commit()
        return
    todo = [r for r in rows if not (r["region"] or "").strip()]
    rest = []
    for r in todo:
        hit = by_name.get(fold(r["partner"]))
        if hit:
            put(r, norm_country(hit[0], known_countries) or hit[0], hit[1])     # "UK" (competitor table) -> "United Kingdom"
        else:
            rest.append(r)
    print(f"pass 1 (same partner): {len(todo) - len(rest)} of {len(todo)}")
    filled = 0
    if use_model:
        for i in range(0, len(rest), BATCH):
            batch = rest[i:i + BATCH]
            by_id = {r["id"]: r for r in batch}
            try:
                answers = ask(model, batch)
            except Exception as e:  # noqa: BLE001
                print(f"  batch {i // BATCH + 1}: model error {e}")
                continue
            for a in answers:
                r = by_id.pop(str(a.get("id") or "").strip(), None)
                country = r and check(a, r["description"], known_countries)
                if country:
                    filled += 1
                    put(r, country, f"the description says: \"{' '.join(str(a.get('quote')).split())}\"")
        print(f"pass 2 (description): {filled} of {len(rest)}; still empty: {len(rest) - filled}")
    if dry:
        conn.rollback()
    else:
        conn.commit()


def _selftest() -> None:
    assert fold("Bharat Electronics Ltd (BEL)") == fold("Bharat Electronics Limited") == "bharat electronics"
    assert fold("RENK Group AG") == "renk"
    known = {"United States", "India", "China"}
    assert norm_country("USA", known) == "United States" and norm_country("null", known) is None and norm_country("Mars", known) is None
    d = "Vector is a Utah-based defence technology company that makes small drones."
    assert check({"country": "United States", "quote": "a Utah-based defence"}, d, known) == "United States"
    assert check({"country": "United States", "quote": "an American firm"}, d, known) is None          # not in the text
    assert check({"country": None, "quote": "Utah-based"}, d, known) is None
    ok = {"country": "Germany", "source_url": "https://www.renk-group.com/en/contact", "quote": "RENK Group AG, Augsburg, Germany"}
    assert web_check(ok, known) == ("Germany", ok["source_url"], ok["quote"])                      # a country the data has not used yet
    assert web_check({**ok, "source_url": "https://en.wikipedia.org/wiki/Renk"}, known) is None     # never Wikipedia
    assert web_check({**ok, "country": "Europe"}, known) is None and web_check({**ok, "quote": ""}, known) is None
    assert web_check({**ok, "country": "USA"}, known)[0] == "United States"
    print("partner_region self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-model", action="store_true", help="pass 1 only")
    ap.add_argument("--model", default="gemma4-26b-gpu")
    ap.add_argument("--web", action="store_true", help="pass 3: sourced web lookup with Claude (paid)")
    ap.add_argument("--limit", type=int, help="with --web: only the first N partners")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    run(a.model, a.dry_run, not a.no_model, a.web, a.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
