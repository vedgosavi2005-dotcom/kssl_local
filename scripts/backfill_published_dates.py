"""Fill staging.competitive_signal.published_date where it is empty, from the article page's OWN date markers.

    KSSL_STAGING_DSN=postgresql://... python -m scripts.backfill_published_dates          # dry run: prints what it would set
    KSSL_STAGING_DSN=postgresql://... python -m scripts.backfill_published_dates --write  # writes

The stored article record (source_document.published_at) is used first by db/setup/15_signal_published_date.sql's
backfill; this script handles the signals whose article record has no date. It reads, in order:
  1. JSON-LD "datePublished" (else "dateCreated")
     (not a CMS page-data "publishedAt": on knds.com it is the site settings' date, the same for every release)
  2. a published-time meta tag (article:published_time, og:published_time, pubdate, publishdate, publish-date,
     date, dc.date.issued, citation_publication_date, parsely-pub-date, sailthru.date, itemprop=datePublished)
  3. a <time datetime> marked as the publication time, or an element whose class/itemprop names a date
     ("date", "publish", "posted") -- never one named "modified"/"updated" -- whose text is a full date
  4. an element holding nothing but a date, within 1500 characters after the page's first title heading (MBDA)
  5. a press-release dateline, "Lucknow, June 03, 2022:" (place, comma, full date, colon)
  6. a /YYYY/MM/DD/ (or YYYY-MM-DD, or an ANI-style YYYYMMDDhhmmss timestamp) date in the URL
  7. last: a magazine issue line "Issue 2 - 2019" -> the year only (published_precision = 'year')
A page with none of these keeps NULL ("date not known"): nothing is guessed. A date in the future or before 2000 is
ignored. Only NULL values are ever written.

    ... --fix-wrong [--write]    the other direction: a STORED date that the page's own machine date (rules 1, 2 or the URL,
                                 never the looser markup / header rules) contradicts by more than 3 days is replaced. asdnews.com
                                 cards carried the crawl date (2026-08-03) while the page's JSON-LD and URL say 2025-06-20.
"""
import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from html import unescape
from urllib.request import Request, urlopen

import psycopg2

from backend import ops_log

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
MONTHS.update({k[:3]: v for k, v in MONTHS.items()})
META_NAMES = ("article:published_time", "og:published_time", "pubdate", "publishdate", "publish-date", "publish_date",
              "date", "dc.date.issued", "dc.date", "citation_publication_date", "parsely-pub-date", "sailthru.date",
              "datepublished", "article.published")


def parse_date(text):
    """A full calendar date in common forms, else None."""
    t = unescape(str(text or "")).strip()
    m = re.search(r"(20\d{2}|19\d{2})-(\d{1,2})-(\d{1,2})", t) or re.search(r"(20\d{2})/(\d{1,2})/(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", t)          # August 19, 2026
        if m and m.group(1).lower() in MONTHS:
            y, mo, d = int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))
        else:
            m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", t)      # 19 August 2026
            if not (m and m.group(2).lower() in MONTHS):
                return None
            y, mo, d = int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))
    try:
        v = date(y, mo, d)
    except ValueError:
        return None
    return v if date(2000, 1, 1) <= v <= date.today() else None


def from_jsonld(html):
    blocks = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I)
    for key in ("datePublished", "dateCreated"):        # dateCreated: CMSs (Joomla) that write no datePublished
        for block in blocks:
            m = re.search(r'"%s"\s*:\s*"([^"]+)"' % key, block)
            if m and parse_date(m.group(1)):
                return parse_date(m.group(1))
    return None


def from_meta(html):
    for tag in re.findall(r"<meta\b[^>]*>", html, re.I):
        key = re.search(r'(?:property|name|itemprop)\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        val = re.search(r'content\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        if key and val and key.group(1).strip().lower() in META_NAMES and parse_date(val.group(1)):
            return parse_date(val.group(1))
    return None


def from_markup(html):
    for m in re.finditer(r"<time\b[^>]*>", html, re.I):
        tag = m.group(0)
        dt = re.search(r'datetime\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        if dt and re.search(r"publish|pubdate|datePublished|posted", tag, re.I) and not re.search(r"modif|updat", tag, re.I):
            if parse_date(dt.group(1)):
                return parse_date(dt.group(1))
    for m in re.finditer(r'<(\w+)\b[^>]*(?:class|itemprop)\s*=\s*["\']([^"\']*)["\'][^>]*>([^<]{4,60})</\1>', html, re.I):
        name, text = m.group(2).lower(), m.group(3)
        whole = re.fullmatch(r"\s*%s\s*" % FULL_DATE, text)   # "meta_date" holding only a date; not "(Dated: ...)" boxes
        if (re.search(r"\b(date|publish\w*|posted|pubdate|datepublished)\b", name)
                or (whole and re.search(r"_(date|published|posted)$", name))) and not re.search(r"modif|updat", name):
            if parse_date(text) and parse_date(text) != date.today():   # today = the site header's clock, not the article
                return parse_date(text)
    return None


FULL_DATE = r"(?:[A-Za-z]{3,9}\.? \d{1,2},? \d{4}|\d{1,2} [A-Za-z]{3,9},? \d{4}|\d{4}-\d{2}-\d{2})"


def from_header(html):
    """An element holding nothing but a date, right under the page's first title heading (MBDA's date pill)."""
    m = re.search(r"<(h[12])\b[^>]*>([^<]{20,300})</\1>", html, re.I)
    if not m:
        return None
    d = re.search(r">\s*(%s)\s*<" % FULL_DATE, html[m.end():m.end() + 1500])
    return parse_date(d.group(1)) if d else None


def from_dateline(html):
    """A paragraph that opens with a press-release dateline: "Lucknow, June 03, 2022: ..."."""
    m = re.search(r"<p\b[^>]*>(?:\s|<[^>]+>)*[A-Z][A-Za-z .]{2,30}, (%s)\s*:" % FULL_DATE, html)
    return parse_date(m.group(1)) if m else None


def from_url(url):
    m = (re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$|[-_])", url) or re.search(r"(20\d{2})-(\d{2})-(\d{2})", url)
         or re.search(r"(20\d{2})(\d{2})(\d{2})\d{6}(?:$|[/?#])", url) or re.search(r"/(20\d{2})(\d{2})(\d{2})-", url))
    if not m:
        return None
    return parse_date("-".join(m.groups()))


PAGES = {}   # url -> html fetched by a real browser (--pages), for sites that refuse a plain request


def find_date(url):
    """(date, how) or (None, reason)."""
    if PAGES.get(url):
        html = PAGES[url]
    else:
      try:
        with urlopen(Request(url, headers={"User-Agent": UA, "Accept-Language": "en"}), timeout=25) as r:
            html = r.read(1_500_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
      except Exception as exc:  # noqa: BLE001
        v = from_url(url)
        return (v, "url") if v else (None, f"fetch failed: {type(exc).__name__}")
    for how, fn in (("json-ld", from_jsonld), ("meta", from_meta), ("markup", from_markup),
                    ("header", from_header), ("dateline", from_dateline)):
        v = fn(html)
        if v:
            return v, how
    v = from_url(url)
    if v:
        return v, "url"
    y = from_issue(html)
    return (y, "issue-year") if y else (None, "no date marker on the page")


def from_issue(html):
    """A magazine page that states only its issue, "Issue 2 - 2019" (SP's Land Forces): the YEAR, stored as 1 January
    with published_precision = 'year' and shown as the year alone. Last resort, after every full-date rule."""
    m = re.search(r">\s*Issue\s+\d{1,2}\s*[-–]\s*((?:19|20)\d{2})\s*<", html)
    return parse_date(f"{m.group(1)}-01-01") if m else None


# the pipeline log's words for where a date came from (backend/ops_log notes)
HOW_WORDS = {"json-ld": "the page's structured data (JSON-LD datePublished)", "meta": "a published-time <meta> tag",
             "markup": "a <time> / date element on the page", "header": "a date line just under the article's title",
             "dateline": "the press-release dateline", "url": "the date in the article's web address",
             "issue-year": "the magazine's issue line (the year only)"}


def note_date(sid, url, v, how, old=None):
    tbl = "staging.competitive_signal" if TABLE == "signal" else "staging.competitive_news_article"
    if old is not None:
        msg = f"Stored date {old} replaced by {v}: {HOW_WORDS.get(how, how)} says so (the stored date was off by {abs((old - v).days)} days)."
        outcome = "date_corrected"
    elif v:
        msg, outcome = f"Date set to {v}, taken from {HOW_WORDS.get(how, how)}.", "date_" + how.replace("-", "_")
    else:
        msg, outcome = f"No date found ({how}); left as 'date not known' -- nothing is guessed.", "no_date"
    ops_log.note("date", outcome, msg, subject=url, tbl=tbl, rec_id=str(sid), detail={"date": v, "how": how, "old": old})


MACHINE = ("json-ld", "meta", "url")     # sources reliable enough to overrule a stored date; markup / header guesses are not


# --table: signal (default) or news (2026-10-22: 959 undated news rows; asdnews / navalnews news rows carried the crawl date).
# name -> (rows with a date, rows without one, update one row, label). The issue-year rule is not used for news (no precision column);
# a corrected news date is copied to source_document.published_at of the same url.
TABLES = {
    "signal": ("""SELECT s.signal_id, d.source_url, s.published_date FROM staging.competitive_signal s JOIN staging.competitive_signal_detail d USING (signal_id)
                  WHERE s.published_date IS NOT NULL AND d.source_url ~ '^https?://'""",
               """SELECT s.signal_id, d.source_url FROM staging.competitive_signal s JOIN staging.competitive_signal_detail d USING (signal_id)
                  WHERE s.published_date IS NULL AND d.source_url ~ '^https?://'""",
               "UPDATE staging.competitive_signal SET published_date = %s, published_precision = NULL WHERE signal_id = %s", "signals"),
    "news": ("""SELECT article_id, article_url, published_date FROM staging.competitive_news_article
                WHERE published_date IS NOT NULL AND article_url ~ '^https?://'""",
             """SELECT article_id, article_url FROM staging.competitive_news_article WHERE published_date IS NULL AND article_url ~ '^https?://'""",
             "UPDATE staging.competitive_news_article SET published_date = %s WHERE article_id = %s", "news articles"),
}
TABLE = "signal"


def fix_wrong(con, cur, write):
    cur.execute(TABLES[TABLE][0])
    rows = cur.fetchall()
    if TABLE == "news":      # ~3,800 dated news rows: checked against the date in their own URL only (no page fetch)
        found = [(r, (from_url(r[1]), "url")) for r in rows]
    else:
        with ThreadPoolExecutor(8) as pool:
            found = list(pool.map(lambda r: (r, find_date(r[1])), rows))
    wrong =[(sid, url, old, v, how) for (sid, url, old), (v, how) in found if v and how in MACHINE and abs((old - v).days) > 3]
    for sid, url, old, v, how in wrong:
        print(f"{old} -> {v} ({how})  {url[:100]}")
    print(f"\n{len(rows)} dated {TABLES[TABLE][3]} checked; {len(wrong)} contradicted by the page's own date" + ("" if write else "  (dry run: --write to replace)"))
    if write and wrong:
        cur.executemany(TABLES[TABLE][2], [(v, sid) for sid, _, _, v, _ in wrong])
        for sid, url, old, v, how in wrong:
            note_date(sid, url, v, how, old)
        if TABLE == "news":
            cur.executemany("UPDATE staging.source_document SET published_at = %s WHERE url = %s", [(v, url) for _, url, _, v, _ in wrong])
        con.commit()
        print(f"written: {len(wrong)}")
    con.close()


@ops_log.logged("scripts.backfill_published_dates")
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--fix-wrong", action="store_true", help="replace stored dates the page's own machine date contradicts (> 3 days)")
    ap.add_argument("--pages", help="JSON {url: {html}} from scripts/browser_pages.mjs, for sites that block plain requests")
    ap.add_argument("--table", choices=sorted(TABLES), default="signal")
    args = ap.parse_args()
    global TABLE
    TABLE = args.table
    if args.pages:
        PAGES.update({u: v.get("html") for u, v in json.load(open(args.pages, encoding="utf-8")).items() if v.get("status") == 200})
    dsn = os.environ.get("KSSL_STAGING_DSN")
    if not dsn:
        sys.exit("KSSL_STAGING_DSN is not set")
    con = psycopg2.connect(dsn)
    cur = con.cursor()
    if args.fix_wrong:
        return fix_wrong(con, cur, args.write)
    cur.execute(TABLES[TABLE][1])
    rows = cur.fetchall()
    with ThreadPoolExecutor(8) as pool:
        found = list(pool.map(lambda r: (r[0], r[1], *find_date(r[1])), rows))
    hits = [(sid, v, "year" if how == "issue-year" else None) for sid, _, v, how in found if v and not (TABLE == "news" and how == "issue-year")]
    tally = {}
    for _, url, v, how in found:
        tally[how if v else how.split(":")[0]] = tally.get(how if v else how.split(":")[0], 0) + 1
        print(f"{str(v or '-'):<10} {how:<28} {url[:110]}")
    print(f"\n{len(rows)} {TABLES[TABLE][3]} without a published date; dated now: {len(hits)}; by source: {tally}")
    if args.write and hits:
        if TABLE == "news":
            cur.executemany("UPDATE staging.competitive_news_article SET published_date = %s WHERE article_id = %s AND published_date IS NULL",
                            [(v, sid) for sid, v, _ in hits])
        else:
            cur.executemany("UPDATE staging.competitive_signal SET published_date = %s, published_precision = %s "
                            "WHERE signal_id = %s AND published_date IS NULL", [(v, prec, sid) for sid, v, prec in hits])
        con.commit()      # both tables (news used to skip it, so its dates were never saved)
        print(f"written: {len(hits)}")
    if args.write:
        for sid, url, v, how in found:          # every row looked at: the date and where it came from, or why there is none
            note_date(sid, url, v if (v and not (TABLE == "news" and how == "issue-year")) else None, how)
    con.close()


if __name__ == "__main__":
    main()
