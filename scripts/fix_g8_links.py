"""G8 (functional test 2026-10-25): cards whose link is not the article they describe, and one page stored under two titles.

    python -m scripts.fix_g8_links --selftest      (no DB, no network)
    python -m scripts.fix_g8_links                 (dry run: counts and examples, writes nothing)
    python -m scripts.fix_g8_links --apply         (one transaction on kssl_staging; refuses any other database)

What was wrong, and what this repairs (the code that made it is fixed in backend/news.py, backend/flood.py,
backend/triage_routes.py, prompts/news_merge.py and prompts/moment.yml, so a re-run does not bring it back):
  1. Listing pages. naval-group.com/en/news ("News page 1 on 42 | Naval Group") was stored as a document and routed to the
     moment lane, so three Naval Group moves link to the listing, carry its crawl date (22 Sep) and say "the page gives no
     date". -> every stored listing page (backend.news.is_listing_page) is marked triage.listing = true and routed 'none'
     (old route kept in triage.route_before_listing); the three moves get their own press releases (dates and verbatim
     quotes taken from those pages, checked at --apply time).
  2. The TKMS move "Canada picks Thyssenkrupp Marine Systems as preferred bidder" linked to a Shephard article about Hanwha
     Ocean (dated by month only, so "1 Jul"). -> the stored Defense News report of the decision (announced 6 Jul) is the
     source; the Shephard article stays as a second source.
  3. Site names inside news headlines ("... | KNDS Group", "... - CHOSUNBIZ"): the company-news and product-news headline
     becomes the article's own title (backend.news.strip_site_suffix), so a news row and a page's other records read alike.
  4. One page stored twice for one company (http/https, www., :80, trailing slash): the duplicate row goes, its
     fact_source rows move to the kept row when they add a source, the rest are removed; candidates point at the kept row.
Every write is keyed: a second --apply changes nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date

from backend.news import is_listing_page, strip_site_suffix, url_key, host_of

STAGING = "kssl_staging"
DN_TKMS = "https://www.defensenews.com/global/europe/2026/07/07/canada-picks-germanys-tkms-for-historic-submarine-buy-in-nod-to-europe/"
SHEPHARD = "https://www.shephardmedia.com/news/naval-warfare/hanwha-ocean-deepens-us-ties-eyes-saudi-submarine-prospect-after-canada-setback/"
NG_INDEX = ("https://www.naval-group.com/en/news", "https://naval-group.com/en/news")
NG = "https://www.naval-group.com/en/"

# Per move: the new source, the date the source states, verbatim quotes (checked against the page text at --apply),
# and exact text edits (old -> new) that drop what the listing page made untrue ("the page gives no date").
MOVES = {
    7087957935188712177: dict(
        who="Thyssenkrupp Marine Systems", url=DN_TKMS, label="Defense News", kind="news", tier="independent", day=date(2026, 7, 6),
        keep_sources=[SHEPHARD],
        quotes={"title": "Canadian Prime Minister Mark Carney announced July 6 that TKMS has been selected as the winning bidder in the country’s project to acquire the new boats.",
                "movement_date": "Canadian Prime Minister Mark Carney announced July 6 that TKMS has been selected as the winning bidder in the country’s project to acquire the new boats.",
                "what_happened": "TKMS beat out a bid from Hanwha Ocean, which was offering its KSS-III submarine."},
        edits={"what_happened": [(" The article gives only the month, so the first day is used.", "")]},
        analysis={}),
    2228430391392629626: dict(
        who="Naval Group", url=NG + "netherlands-and-naval-group-extend-industrial-cooperation-agreement", label="Naval Group",
        kind="company", tier="primary", day=date(2026, 7, 17), keep_sources=[],
        quotes={"title": "The Netherlands and Naval Group extend the Industrial Cooperation Agreement",
                "movement_date": "On 17th July 2026, the Netherlands Ministry of Economic Affairs and Climate and Naval Group signed an amendment to the Industrial Cooperation Agreement (ICA) related to the Replacement Netherlands Submarine Capability (RNSC) program.",
                "what_happened": "This amendment will enable Naval Group to contract new Dutch companies to contribute to the manufacturing of the Orka-class submarines and F21 heavyweight torpedoes."},
        edits={"card_summary": [("Naval Group's news page reports that the Netherlands", "The Netherlands")],
               "description": [("Naval Group's news page lists an extension", "A Naval Group press release reports an extension"),
                               (" The page gives no date, value or scope.", "")],
               "what_happened": [("The Netherlands and Naval Group extend the Industrial Cooperation Agreement, according to Naval Group's news page. The page gives no date, value or scope.",
                                  "On 17 July 2026 the Netherlands and Naval Group signed an amendment to their Industrial Cooperation Agreement for the Replacement Netherlands Submarine Capability programme. "
                                  "It lets Naval Group contract new Dutch companies to help build the Orka-class submarines and F21 heavyweight torpedoes.")]},
        analysis={"What happened": [("The Netherlands and Naval Group extend the Industrial Cooperation Agreement. The Naval Group news page gives only this headline, with no date, value or scope.",
                                     "On 17 July 2026 the Netherlands and Naval Group signed an amendment to their Industrial Cooperation Agreement for the Replacement Netherlands Submarine Capability programme. "
                                     "It lets Naval Group contract new Dutch companies to help build the Orka-class submarines and F21 heavyweight torpedoes.")]}),
    4236434807364002931: dict(
        who="Naval Group", url=NG + "m941-tournai-has-arrived-zeebruges-marking-new-step-modernization-mine-warfare-belgium", label="Naval Group",
        kind="company", tier="primary", day=date(2026, 9, 22), keep_sources=[],
        quotes={"title": "The M941 Tournai has arrived in Zeebruges, marking a new step in the modernization of mine warfare in Belgium",
                "movement_date": "Press release 22 Sep. 2026",
                "what_happened": "The M941 Tournai, the third ship of the Belgian-Dutch mine countermeasures vessel (rMCM) replacement program and the second destined for the Belgian Navy, has arrived in Zeebruges."},
        edits={"title": [("Naval Group news: M941 Tournai", "M941 Tournai")],
               "card_summary": [("Naval Group's news page reports that the M941 Tournai", "The M941 Tournai")],
               "description": [("Naval Group's news page lists the arrival", "A Naval Group press release reports the arrival"),
                               (" The page gives no further detail.", "")],
               "what_happened": [("Naval Group's news page reports that the M941 Tournai has arrived in Zeebruges. The page calls it a new step in the modernization of mine warfare in Belgium. The page gives no arrival date and no further detail.",
                                  "The M941 Tournai has arrived in Zeebruges. It is the third ship of the Belgian-Dutch mine countermeasures vessel (rMCM) replacement program and the second for the Belgian Navy. "
                                  "The Belgium Naval & Robotics (BNR) consortium hands it to the Belgian State on 25 September 2026.")]},
        analysis={"What happened": [("Naval Group's news page reports the arrival of the M941 Tournai in Zeebruges. It calls the arrival a new step in the modernization of mine warfare in Belgium. No date, value or detail is given.",
                                     "The M941 Tournai has arrived in Zeebruges, the third ship of the Belgian-Dutch rMCM programme and the second for the Belgian Navy. "
                                     "Naval Group calls the arrival a new step in the modernization of mine warfare in Belgium. "
                                     "The Belgium Naval & Robotics (BNR) consortium hands the ship to the Belgian State on 25 September 2026.")]}),
    8769489889773602266: dict(
        who="Naval Group", url=NG + "naval-group-and-nibe-limited-its-group-companies-sign-strategic-mou-high-tech-solution-and", label="Naval Group",
        kind="company", tier="primary", day=date(2026, 9, 18), keep_sources=[],
        quotes={"title": "Naval Group and Nibe Limited with its Group Companies sign strategic MoU for high-tech solution and expertise for Indian shipbuilding",
                "movement_date": "On 18th September 2026, Nibe Group and Naval Group signed a Memorandum of Understanding (MoU)",
                "what_happened": "On 18th September 2026, Nibe Group and Naval Group signed a Memorandum of Understanding (MoU) setting a formal framework for cooperation in a range of technological areas of mutual interest for modern naval technologies in shipbuilding, defence platforms and autonomous systems such as underwater drones, mine countermeasure vessels, underwater submarine systems and technologies, naval weapon launching systems, and their maintenance."},
        edits={"description": [("Naval Group's news page lists a strategic MoU", "A Naval Group press release reports a strategic MoU"),
                               (" The page gives no date or value.", "")],
               "what_happened": [("Naval Group and Nibe Limited with its Group Companies signed a strategic MoU.",
                                  "Naval Group and Nibe Limited with its Group Companies signed a strategic MoU on 18 September 2026."),
                                 (" The news page gives no signing date, value or scope detail.",
                                  " It covers underwater drones, mine countermeasure vessels, submarine systems and naval weapon launching systems.")]},
        analysis={"What happened": [("Naval Group and Nibe Limited, with its Group Companies, signed a strategic MoU.",
                                     "Naval Group and Nibe Limited, with its Group Companies, signed a strategic MoU on 18 September 2026."),
                                    (" The news page gives no date, value or detail.",
                                     " It covers underwater drones, mine countermeasure vessels, submarine systems and naval weapon launching systems. The press release gives no value.")]}),
}


def source_id(moment_id: int, url: str) -> int:
    """A stable bigint id for a moment_source row (a re-run finds the same row)."""
    return int(hashlib.sha1(f"{moment_id}|{url}".encode()).hexdigest()[:15], 16)


def apply_edits(text: str | None, edits) -> str | None:
    """Exact replacements, each applied once when its old text is present (a second run finds none: idempotent)."""
    if text is None:
        return None
    for old, new in edits:
        if old in text:
            text = text.replace(old, new, 1)
    return text


def page_text(html_text: str) -> str:
    import html as H
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html_text, flags=re.S | re.I)
    t = H.unescape(re.sub(r"<[^>]+>", " ", t))
    return " ".join(t.split())


def norm_q(s: str) -> str:
    return " ".join((s or "").replace("’", "'").split())


def keep_rank(r: dict) -> tuple:
    """Which of two rows for one page stays: a date that agrees with a /YYYY/MM/ in the url, a date, an image, more
    sources, https, then the lowest id (deterministic)."""
    m = re.search(r"/(20\d\d)/(\d\d)/", r["article_url"] or "")
    d = r.get("published_date")
    agrees = bool(m and d and (d.year, d.month) == (int(m.group(1)), int(m.group(2))))
    return (not agrees, d is None, not r.get("image_url"), -(r.get("fs") or 0),
            not (r["article_url"] or "").startswith("https://"), r["id"])


# ---- database -------------------------------------------------------------------------------------------------------

def connect():
    import os
    import psycopg2
    import psycopg2.extras
    dsn = os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging"
    c = psycopg2.connect(dsn)
    c.cursor_factory = psycopg2.extras.RealDictCursor
    return c


def guard(cur):
    cur.execute("SELECT current_database() AS db")
    db = cur.fetchone()["db"]
    if db != STAGING:
        raise SystemExit(f"refusing: connected to {db!r}, this script writes only to {STAGING}")


_ROBOTS: dict = {}


def fetch_page(url: str) -> str:
    """robots.txt is honoured (backend.harvest_sites.Robots, wildcards supported); certificates are verified."""
    from backend.news import http
    from backend.harvest_sites import Robots
    from urllib.parse import urlsplit
    import time
    p = urlsplit(url)
    if p.netloc not in _ROBOTS:
        for _ in range(3):
            rb = http(f"{p.scheme}://{p.netloc}/robots.txt")
            if rb.status and rb.status < 500 and rb.status != 429:
                break
            time.sleep(3)
        _ROBOTS[p.netloc] = Robots(rb.text()) if rb.status == 200 else Robots(allow_all=(400 <= rb.status < 500 and rb.status != 429))
    if not _ROBOTS[p.netloc].allowed(url):
        raise SystemExit(f"robots.txt disallows {url} (or robots.txt could not be read)")
    r = http(url)
    if getattr(r, "status", 0) != 200:
        raise SystemExit(f"{url}: http {getattr(r, 'status', 0)}")
    return page_text(r.text())


def stored_text(cur, url: str) -> str | None:
    cur.execute("SELECT body_text, title FROM staging.source_document WHERE url = %s ORDER BY length(body_text) DESC NULLS LAST LIMIT 1", (url,))
    r = cur.fetchone()
    return (r["title"] or "") + " " + (r["body_text"] or "") if r else None


def plan_listing(cur) -> list[dict]:
    cur.execute("SELECT doc_id::text AS id, url, title, triage FROM staging.source_document "
                "WHERE NOT coalesce((triage->>'listing')::boolean, false)")
    return [r for r in cur.fetchall() if is_listing_page(r["url"], r["title"] or "")]


def plan_headlines(cur) -> list[tuple]:
    out = []
    for table, idc in (("competitive_news_article", "article_id"), ("competitive_product_news", "product_news_id")):
        cur.execute(f"SELECT {idc}::text AS id, headline, publisher, article_url FROM staging.{table}")
        for r in cur.fetchall():
            new = strip_site_suffix(r["headline"] or "", r["publisher"] or "", host_of(r["article_url"] or ""))
            if new != (r["headline"] or ""):
                out.append((table, idc, r["id"], r["headline"], new))
    return out


def plan_dupes(cur) -> list[tuple]:
    """[(keep_row, [drop_rows])] for company-news rows of one company whose urls are spellings of one page."""
    cur.execute("""SELECT a.article_id::text AS id, a.competitor_id::text AS cid, a.article_url, a.headline, a.published_date, a.image_url, a.category,
                          (SELECT count(*) FROM staging.fact_source f WHERE f.table_name = 'competitive_news_article' AND f.row_id = a.article_id::text) AS fs
                   FROM staging.competitive_news_article a""")
    groups: dict = {}
    for r in cur.fetchall():
        groups.setdefault((r["cid"], url_key(r["article_url"])), []).append(r)
    out = []
    for rows in groups.values():
        if len(rows) > 1:
            rows = sorted(rows, key=keep_rank)
            out.append((rows[0], rows[1:]))
    return out


def run(apply: bool) -> dict:
    conn = connect()
    cur = conn.cursor()
    guard(cur)
    stats = {}

    # 1. listing pages: no lane reads them
    listing = plan_listing(cur)
    stats["listing_pages_marked"] = len(listing)
    stats["listing_pages_that_had_a_lane"] = sum(1 for r in listing if ((r["triage"] or {}).get("route") or ["none"]) != ["none"])
    for r in listing:
        before = (r["triage"] or {}).get("route")
        patch = {"listing": True, "route": ["none"], "route_before_listing": before,
                 "route_reason": "listing page (index of stories), routed by code", "route_model": "code"}
        cur.execute("UPDATE staging.source_document SET triage = coalesce(triage, '{}'::jsonb) || %s::jsonb "
                    "WHERE doc_id = %s::uuid AND current_database() = %s AND NOT coalesce((triage->>'listing')::boolean, false)",
                    (json.dumps(patch), r["id"], STAGING))

    # 2. the four moves
    stats["moves"] = []
    for mid, mv in MOVES.items():
        cur.execute("SELECT m.*, c.display_name FROM staging.competitive_competitor_moment m JOIN staging.competitive_competitor c USING (competitor_id) "
                    "WHERE m.moment_id = %s", (mid,))
        m = cur.fetchone()
        if m is None:
            stats["moves"].append(f"{mid}: not stored (skipped)")
            continue
        assert m["display_name"] == mv["who"], (mid, m["display_name"])
        text = stored_text(cur, mv["url"]) or (fetch_page(mv["url"]) if apply or m["source_url"] != mv["url"] else "")
        if text:
            for col, q in mv["quotes"].items():
                assert norm_q(q) in norm_q(text), f"{mid} {col}: quote not on {mv['url']}: {q[:80]}"
        new = {col: apply_edits(m[col], mv["edits"].get(col, [])) for col in ("title", "card_summary", "description", "what_happened")}
        img = None if m["source_url"] != mv["url"] else m["image_url"]      # the old picture belonged to the old page
        changed = [k for k in new if new[k] != m[k]] + (["source_url"] if m["source_url"] != mv["url"] else []) \
            + (["movement_date"] if m["movement_date"] != mv["day"] else [])
        stats["moves"].append(f"{mid} {mv['who']}: {m['source_url']} -> {mv['url']}; {m['movement_date']} -> {mv['day']}; changed {changed}")
        cur.execute("""UPDATE staging.competitive_competitor_moment SET source_url = %s, source_label = %s, source_domain = %s, movement_date = %s,
                              title = %s, card_summary = %s, description = %s, what_happened = %s, image_url = %s
                       WHERE moment_id = %s AND current_database() = %s AND source_url IS DISTINCT FROM %s""",
                    (mv["url"], mv["label"], host_of(mv["url"]).removeprefix("www."), mv["day"], new["title"], new["card_summary"],
                     new["description"], new["what_happened"], img, mid, STAGING, mv["url"]))
        cur.execute("""UPDATE staging.competitive_competitor_moment SET movement_date = %s, title = %s, card_summary = %s, description = %s, what_happened = %s
                       WHERE moment_id = %s AND current_database() = %s""",
                    (mv["day"], new["title"], new["card_summary"], new["description"], new["what_happened"], mid, STAGING))
        # moment_source: the new source first, the kept extra sources stay, listing / replaced rows go
        keep = {mv["url"], *mv["keep_sources"]}
        cur.execute("DELETE FROM staging.competitive_competitor_moment_source WHERE moment_id = %s AND current_database() = %s AND NOT (source_url = ANY(%s))",
                    (mid, STAGING, list(keep)))
        cur.execute("""INSERT INTO staging.competitive_competitor_moment_source (source_id, moment_id, publisher, source_domain, source_type, source_url)
                       SELECT %s, %s, %s, %s, %s, %s WHERE current_database() = %s
                         AND NOT EXISTS (SELECT 1 FROM staging.competitive_competitor_moment_source WHERE moment_id = %s AND source_url = %s)""",
                    (source_id(mid, mv["url"]), mid, mv["label"], host_of(mv["url"]).removeprefix("www."), mv["kind"], mv["url"], STAGING, mid, mv["url"]))
        # fact_source: title / movement_date / what_happened rest on the new page (verbatim quotes); extra sources keep their rows
        for col, q in mv["quotes"].items():
            cur.execute("""DELETE FROM staging.fact_source WHERE table_name = 'competitive_competitor_moment' AND row_id = %s AND column_name = %s
                             AND source_url <> 'judgement' AND NOT (source_url = ANY(%s)) AND current_database() = %s""",
                        (str(mid), col, list(keep), STAGING))
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
                           SELECT 'competitive_competitor_moment', %s, %s, %s, %s, %s, %s, now() WHERE current_database() = %s
                             AND NOT EXISTS (SELECT 1 FROM staging.fact_source WHERE table_name = 'competitive_competitor_moment' AND row_id = %s
                                             AND column_name = %s AND source_url = %s)""",
                        (str(mid), col, mv["url"], mv["tier"], mv["label"], q, STAGING, str(mid), col, mv["url"]))
        if mv["keep_sources"]:          # the old article's title / date rows go: it did not state the day nor head the story
            cur.execute("""DELETE FROM staging.fact_source WHERE table_name = 'competitive_competitor_moment' AND row_id = %s
                             AND column_name IN ('title', 'movement_date') AND source_url = ANY(%s) AND current_database() = %s""",
                        (str(mid), mv["keep_sources"], STAGING))
        # analysis lenses that described the listing page
        for view, edits in mv["analysis"].items():
            cur.execute("SELECT analysis_id, analysis_text FROM staging.competitive_competitor_moment_analysis WHERE moment_id = %s AND view_name = %s", (mid, view))
            for a in cur.fetchall():
                t = apply_edits(a["analysis_text"], edits)
                if t != a["analysis_text"]:
                    cur.execute("UPDATE staging.competitive_competitor_moment_analysis SET analysis_text = %s WHERE analysis_id = %s AND current_database() = %s",
                                (t, a["analysis_id"], STAGING))
                    cur.execute("""DELETE FROM staging.fact_source WHERE table_name = 'competitive_competitor_moment_analysis' AND row_id = %s
                                     AND column_name = 'analysis_text' AND source_url = 'judgement' AND quote ILIKE '%%news page%%' AND current_database() = %s""",
                                (str(a["analysis_id"]), STAGING))
                    cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
                                   SELECT 'competitive_competitor_moment_analysis', %s, 'analysis_text', %s, %s, %s, %s, now() WHERE current_database() = %s
                                     AND NOT EXISTS (SELECT 1 FROM staging.fact_source WHERE table_name = 'competitive_competitor_moment_analysis'
                                                     AND row_id = %s AND column_name = 'analysis_text' AND source_url = %s)""",
                                (str(a["analysis_id"]), mv["url"], mv["tier"], mv["label"], mv["quotes"]["what_happened"], STAGING,
                                 str(a["analysis_id"]), mv["url"]))

    # 3. headlines: the article's own title, without the site's name
    heads = plan_headlines(cur)
    stats["headlines_site_suffix_removed"] = {t: sum(1 for h in heads if h[0] == t) for t in ("competitive_news_article", "competitive_product_news")}
    stats["headline_examples"] = [f"{h[3]!r} -> {h[4]!r}" for h in heads[:6]]
    for table, idc, rid, old, new in heads:
        cur.execute(f"UPDATE staging.{table} SET headline = %s WHERE {idc} = %s::uuid AND headline = %s AND current_database() = %s",
                    (new, rid, old, STAGING))

    # 4. one page, two rows for one company
    dupes = plan_dupes(cur)
    stats["duplicate_rows_removed"] = sum(len(d) for _, d in dupes)
    stats["duplicate_examples"] = [f"keep {k['id'][:8]} {k['article_url']} ({k['published_date']}) / drop " +
                                   ", ".join(f"{d['id'][:8]} {d['article_url']} ({d['published_date']})" for d in drops) for k, drops in dupes]
    for keep, drops in dupes:
        for d in drops:
            # its sources move to the kept row when they add one; the rest (and the row) go
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, document_id, retrieved_at)
                           SELECT 'competitive_news_article', %s, 'also_reported_by', f.source_url, f.source_tier, f.publisher, f.quote, f.document_id, f.retrieved_at
                           FROM staging.fact_source f
                           WHERE f.table_name = 'competitive_news_article' AND f.row_id = %s AND f.source_url <> 'judgement' AND current_database() = %s
                             AND f.column_name IN ('article_url', 'also_reported_by')
                             AND NOT EXISTS (SELECT 1 FROM staging.fact_source k WHERE k.table_name = 'competitive_news_article' AND k.row_id = %s
                                             AND k.column_name IN ('article_url', 'also_reported_by')
                                             AND rtrim(regexp_replace(k.source_url, '^https?://(www[.])?', ''), '/') = rtrim(regexp_replace(f.source_url, '^https?://(www[.])?', ''), '/'))""",
                        (keep["id"], d["id"], STAGING, keep["id"]))
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_news_article' AND row_id = %s AND current_database() = %s", (d["id"], STAGING))
            cur.execute("UPDATE staging.news_candidate SET story_id = %s::uuid WHERE story_table = 'competitive_news_article' AND story_id = %s::uuid AND current_database() = %s",
                        (keep["id"], d["id"], STAGING))
            cur.execute("DELETE FROM staging.competitive_news_article WHERE article_id = %s::uuid AND current_database() = %s", (d["id"], STAGING))

    if apply:
        conn.commit()
    else:
        conn.rollback()
    return stats


def two_title_pairs(cur) -> int:
    """Company + page pairs whose company-news headline and Movement title differ (the triage's "94 pairs" measure)."""
    cur.execute("""WITH u AS (SELECT 'news' t, competitor_id c, article_url url, headline h FROM staging.competitive_news_article
                             UNION ALL SELECT 'moment', competitor_id, source_url, title FROM staging.competitive_competitor_moment)
                   SELECT count(*) AS n FROM (SELECT c, url FROM u WHERE url IS NOT NULL GROUP BY 1, 2
                                              HAVING count(DISTINCT h) > 1 AND count(DISTINCT t) = 2) x""")
    return cur.fetchone()["n"]


def _selftest() -> None:
    assert apply_edits("A. The page gives no date.", [(" The page gives no date.", "")]) == "A."
    assert apply_edits("A.", [(" The page gives no date.", "")]) == "A." and apply_edits(None, [("a", "b")]) is None
    assert source_id(1, "u") == source_id(1, "u") != source_id(2, "u") and 0 < source_id(1, "u") < 2 ** 63
    assert norm_q("the country’s  project") == "the country's project"
    assert page_text("<p>a &amp; b</p><script>x</script>") == "a & b"
    base = dict(image_url=None, fs=0)
    rows = [dict(base, id="b", article_url="https://www.navalnews.com/naval-news/2026/06/f125/", published_date=date(2026, 9, 6), fs=3),
            dict(base, id="a", article_url="https://www.navalnews.com/naval-news/2026/06/f125", published_date=date(2026, 6, 9), fs=2)]
    assert sorted(rows, key=keep_rank)[0]["id"] == "a"            # the date that agrees with /2026/06/ wins over more sources
    rows = [dict(base, id="b", article_url="http://www.supacat.com/", published_date=None),
            dict(base, id="a", article_url="https://supacat.com/", published_date=None)]
    assert sorted(rows, key=keep_rank)[0]["id"] == "a"            # https
    for mid, mv in MOVES.items():
        assert set(mv["quotes"]) == {"title", "movement_date", "what_happened"} and mv["url"].startswith("https://")
        assert not is_listing_page(mv["url"]) and all(not is_listing_page(u) for u in mv["keep_sources"])
    assert all(is_listing_page(u) for u in NG_INDEX)
    print("fix_g8_links self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    conn = connect()
    before = two_title_pairs(conn.cursor())
    conn.close()
    if a.apply:
        from backend import ops_log
        box = {}
        ops_log.logged("scripts.fix_g8_links")(lambda: box.update(run(True)))()     # the log's run status reads None as ok
        stats = box
    else:
        stats = run(False)
    conn = connect()
    stats["two_title_pairs"] = f"{before} -> {two_title_pairs(conn.cursor())}" + ("" if a.apply else " (dry run: unchanged)")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(stats, indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
