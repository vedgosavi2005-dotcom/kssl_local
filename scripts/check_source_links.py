"""Find source links the publisher took down, and give each one its Internet Archive copy (owner 2026-10-23: a signal's
source gave 404 -- Army Recognition removed the article after we read it).

    python -m scripts.check_source_links              (check URLs not checked in the last 7 days, then look up archives)
    python -m scripts.check_source_links --days 0     (re-check everything)
    python -m scripts.check_source_links --selftest

Every source URL the sites can show (each *url column of the staging and serving tables, raw layer and images left out) is
fetched once (GET, headers only, at most 2 at a time per site). 404 / 410 = dead: the latest web.archive.org snapshot of
that URL that answered 200 becomes its archive_url. Results go to staging.source_link (db/setup/38); the APIs serve the
archive copy in place of a dead URL (backend/app.py swap_links). Stored source_url values are never changed. 403 / 401 /
no answer are NOT dead (sites that block scripts still work in a browser). Connection: KSSL_STAGING_DSN, KSSL_SERVING_DSN.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import defaultdict
from urllib.parse import urlsplit

import httpx
import psycopg2

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PER_HOST, TOTAL = 2, 48
DEAD = (404, 410)
SKIP_TABLES = ("source_document", "news_candidate", "tender_raw", "source_link")
SKIP_COLS = ("image_url", "thumbnail_url", "feed_url", "image_source_url", "status_check_url", "url_kind")


def urls_of(dsn: str) -> set[str]:
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("""SELECT c.table_schema, c.table_name, c.column_name FROM information_schema.columns c
                       JOIN information_schema.tables t USING (table_schema, table_name)
                       WHERE c.table_schema IN ('staging', 'serving') AND t.table_type = 'BASE TABLE' AND c.column_name LIKE '%%url%%'
                         AND c.data_type IN ('text', 'character varying') AND c.table_name NOT IN %s AND c.column_name NOT IN %s""",
                    (SKIP_TABLES, SKIP_COLS))
        out: set[str] = set()
        for s, t, c in cur.fetchall():
            cur.execute(f'SELECT DISTINCT "{c}" FROM "{s}"."{t}" WHERE "{c}" ~* %s', ("^https?://",))
            out |= {r[0].strip() for r in cur.fetchall()}
        return out


async def statuses(urls: list[str]) -> list[tuple[str, int]]:
    hosts: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(PER_HOST))
    total = asyncio.Semaphore(TOTAL)

    async def one(client, url):
        async with hosts[urlsplit(url).netloc], total:      # host first: a busy site must not hold the shared slots
            for _ in range(2):
                try:
                    async with client.stream("GET", url) as r:
                        return url, r.status_code
                except Exception:  # noqa: BLE001 -- no answer is recorded as 0, never as dead
                    await asyncio.sleep(2)
            return url, 0

    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept": "text/html,*/*"}, follow_redirects=True,
                                 timeout=25, verify=False) as client:
        out = []
        for i, fut in enumerate(asyncio.as_completed([one(client, u) for u in urls]), 1):
            out.append(await fut)
            if i % 1000 == 0:
                print(f"  checked {i}/{len(urls)}", flush=True)
        return out


def snapshot_url(cdx_rows: list) -> tuple[str, str] | None:
    """the newest 200 snapshot from a CDX json answer ([header, [timestamp, original], ...]) -> (archive url, timestamp)"""
    rows = [r for r in cdx_rows[1:] if len(r) >= 2]
    if not rows:
        return None
    ts, original = max(rows)
    return f"https://web.archive.org/web/{ts}/{original}", ts


def archive_of(client: httpx.Client, url: str) -> tuple[str, str] | None:
    for wait in (0, 10, 30):
        time.sleep(wait or 1)                              # the archive allows about one lookup a second
        try:
            r = client.get("https://web.archive.org/cdx/search/cdx",
                           params={"url": url, "output": "json", "fl": "timestamp,original", "filter": "statuscode:200"})
        except httpx.HTTPError:
            continue
        if r.status_code == 429:
            continue
        return snapshot_url(r.json()) if r.status_code == 200 and r.text.strip() else None
    return None


def main() -> None:
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 7
    st = os.environ.get("KSSL_STAGING_DSN") or os.environ["KSSL_DSN"]
    urls = urls_of(st) | (urls_of(os.environ["KSSL_SERVING_DSN"]) if os.environ.get("KSSL_SERVING_DSN") else set())
    with psycopg2.connect(st) as conn, conn.cursor() as cur:
        cur.execute("SELECT url FROM staging.source_link WHERE checked_at > now() - make_interval(days => %s)", (days,))
        fresh = {r[0] for r in cur.fetchall()}
    todo = sorted(urls - fresh)
    print(f"{len(urls)} source urls, {len(todo)} to check")
    results = asyncio.run(statuses(todo))
    with psycopg2.connect(st) as conn, conn.cursor() as cur:
        for url, status in results:
            cur.execute("""INSERT INTO staging.source_link (url, status, checked_at) VALUES (%s, %s, now())
                           ON CONFLICT (url) DO UPDATE SET status = EXCLUDED.status, checked_at = now()""", (url, status))
        cur.execute("SELECT url FROM staging.source_link WHERE status IN %s AND archive_url IS NULL", (DEAD,))
        dead = [r[0] for r in cur.fetchall()]
    print(f"{sum(s in DEAD for _, s in results)} newly dead; looking up {len(dead)} archive copies")
    found = 0
    with httpx.Client(timeout=40, headers={"User-Agent": UA}) as client:
        for i, url in enumerate(dead, 1):
            snap = archive_of(client, url)
            if snap:
                found += 1
                with psycopg2.connect(st) as conn, conn.cursor() as cur:
                    cur.execute("UPDATE staging.source_link SET archive_url = %s, archived_at = to_timestamp(%s, 'YYYYMMDDHH24MISS') WHERE url = %s",
                                (snap[0], snap[1], url))
            if i % 50 == 0:
                print(f"  archives {i}/{len(dead)}: {found} found", flush=True)
    print(f"done: {found} of {len(dead)} dead links have an archive copy")


def _selftest() -> None:
    cdx = [["timestamp", "original"], ["20261001000000", "https://a/x"], ["20261017052256", "https://a/x"]]
    assert snapshot_url(cdx) == ("https://web.archive.org/web/20261017052256/https://a/x", "20261017052256")
    assert snapshot_url([["timestamp", "original"]]) is None and snapshot_url([]) is None
    print("check_source_links self-check ok")


if __name__ == "__main__":
    _selftest() if "--selftest" in sys.argv else main()
