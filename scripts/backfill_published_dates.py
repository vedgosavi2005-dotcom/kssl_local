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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--pages", help="JSON {url: {html}} from scripts/browser_pages.mjs, for sites that block plain requests")
    args = ap.parse_args()
    if args.pages:
        PAGES.update({u: v.get("html") for u, v in json.load(open(args.pages, encoding="utf-8")).items() if v.get("status") == 200})
    dsn = os.environ.get("KSSL_STAGING_DSN")
    if not dsn:
        sys.exit("KSSL_STAGING_DSN is not set")
    con = psycopg2.connect(dsn)
    cur = con.cursor()
    cur.execute("""SELECT s.signal_id, d.source_url FROM staging.competitive_signal s
                   JOIN staging.competitive_signal_detail d USING (signal_id)
                   WHERE s.published_date IS NULL AND d.source_url ~ '^https?://'""")
    rows = cur.fetchall()
    with ThreadPoolExecutor(8) as pool:
        found = list(pool.map(lambda r: (r[0], r[1], *find_date(r[1])), rows))
    hits = [(sid, v, "year" if how == "issue-year" else None) for sid, _, v, how in found if v]
    tally = {}
    for _, url, v, how in found:
        tally[how if v else how.split(":")[0]] = tally.get(how if v else how.split(":")[0], 0) + 1
        print(f"{str(v or '-'):<10} {how:<28} {url[:110]}")
    print(f"\n{len(rows)} signals without a published date; dated now: {len(hits)}; by source: {tally}")
    if args.write and hits:
        cur.executemany("UPDATE staging.competitive_signal SET published_date = %s, published_precision = %s "
                        "WHERE signal_id = %s AND published_date IS NULL", [(v, prec, sid) for sid, v, prec in hits])
        con.commit()
        print(f"written: {len(hits)}")
    con.close()


if __name__ == "__main__":
    main()
