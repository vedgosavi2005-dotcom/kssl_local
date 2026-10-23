"""Article images into the database (media.image) and onto the cards (owner 2026-10-22).

    python -m backend.media_images --selftest
    python -m backend.media_images [--limit N] [--workers 8] [--report | --point | --refind-defaults]

For every page a card points at (news articles, product news, signals, competitor moves, technology articles): the card's own image
link if it has one, else the page's own preview image (og:image, twitter:image, link rel=image_src, else the first large <img> of the
article). The picture is downloaded once (max 4 MB, must decode as an image, at least 200 x 120 px so logos and icons are left out),
stored as bytes in media.image, and the page recorded in media.page_image (also when nothing was found, with the reason). Then each
card's image column is pointed at /api/image/<image_id>; the original link stays in media.image.source_url (Trace).
Resumable: a page already checked is skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import html as htmlmod
import io
import re
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend import ops_log

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
MAX_BYTES = 4_000_000
MIN_W, MIN_H = 200, 120

# card table -> (id column, page url sql, image column); the url comes from the card or its detail / source row
CARDS = {
    "competitive_news_article": ("article_id", "SELECT article_id::text AS id, article_url AS page, image_url AS img FROM staging.competitive_news_article", "image_url"),
    "competitive_signal": ("signal_id", """SELECT s.signal_id::text AS id, d.source_url AS page, s.thumbnail_url AS img FROM staging.competitive_signal s
                                            JOIN staging.competitive_signal_detail d USING (signal_id)""", "thumbnail_url"),
    "competitive_competitor_moment": ("moment_id", "SELECT moment_id::text AS id, source_url AS page, image_url AS img FROM staging.competitive_competitor_moment", "image_url"),
    "technology_overview_article": ("overview_article_id", """SELECT a.overview_article_id::text AS id,
                                            (SELECT coalesce(ts.source_url, ts.url) FROM staging.technology_overview_source s
                                               JOIN staging.technology_source ts ON ts.source_id = s.source_id
                                              WHERE s.article_id = a.article_id AND coalesce(ts.source_url, ts.url) ~ '^https?://'
                                              ORDER BY s.is_primary DESC NULLS LAST, s.display_order LIMIT 1) AS page, a.image_url AS img
                                       FROM staging.technology_overview_article a""", "image_url"),
}
PRODUCT_NEWS = "SELECT DISTINCT article_url AS page FROM staging.competitive_product_news WHERE article_url ~ '^https?://'"


HOST_GAP = 2.0              # seconds between two requests to one site (armyrecognition.com answered 429 to 12 parallel workers)
_host_lock: dict[str, threading.Lock] = {}
_host_last: dict[str, float] = {}
_locks_lock = threading.Lock()


def fetch(url: str, limit: int, accept="*/*", retry=True, referer=None):
    import time
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    from urllib.parse import quote
    url = quote(url.strip(), safe=":/?#[]@!$&'()*+,;=%~")     # spaces / control characters in a site's own links (InvalidURL)
    host = urlsplit(url).hostname or ""
    with _locks_lock:
        lock = _host_lock.setdefault(host, threading.Lock())
    with lock:                                  # one request per site at a time, HOST_GAP apart; other sites run in parallel
        time.sleep(max(0.0, _host_last.get(host, 0.0) + HOST_GAP - time.monotonic()))
        _host_last[host] = time.monotonic()
        try:
            headers = {"User-Agent": UA, "Accept": accept, "Accept-Language": "en", **({"Referer": referer} if referer else {})}
            with urlopen(Request(url, headers=headers), timeout=25) as r:
                return r.read(limit + 1), r.headers.get_content_type(), r.geturl()
        except HTTPError as e:
            if e.code != 429 or not retry:
                raise
            wait = e.headers.get("Retry-After", "")
            time.sleep(min(60, int(wait)) if wait.isdigit() else 30)
    return fetch(url, limit, accept, retry=False, referer=referer)


def find_image(page_html: str, base: str, why: list | None = None):
    """(image url, how) from the page's own markup, else (None, None). `why` (a list) collects each <img> passed over and why,
    for the pipeline log."""
    for how, pat in (("og_image", r'<meta[^>]+(?:property|name)=["\']og:image(?::secure_url|:url)?["\'][^>]*content=["\']([^"\']+)'),
                     ("og_image", r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:image["\']'),
                     ("twitter_image", r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]*content=["\']([^"\']+)'),
                     ("twitter_image", r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*name=["\']twitter:image["\']'),
                     ("link_image_src", r'<link[^>]+rel=["\']image_src["\'][^>]*href=["\']([^"\']+)')):
        m = re.search(pat, page_html, re.I)
        if m:
            return urljoin(base, htmlmod.unescape(m.group(1).strip())), how
    # no preview tag: an <img> of the article, never a logo / banner ad / gif; one declared >= 400 px wide beats the first
    # plain one (armyrecognition.com opens with an ad pixel and four banners before the article photo)
    body = re.search(r"<article\b.*?</article>", page_html, re.I | re.S)
    first = None
    for m in re.finditer(r'<img\b[^>]*>', body.group(0) if body else page_html, re.I):
        src = img_src(m.group(0))
        src = re.match(r"(.+)", src) if src else None
        junk = src and re.search(r"logo|icon|sprite|avatar|pixel|blank|banner|/ads?/|\.svg|\.gif|data:|mode=img", src.group(1), re.I)
        if not src or junk:
            if why is not None:
                why.append({"img": src.group(1)[:200] if src else None,
                            "skipped": f"name looks like a {junk.group(0).strip('/.')}" if junk else "no src"})
            continue
        w = re.search(r'\swidth=["\']?(\d+)', m.group(0), re.I)
        url = urljoin(base, htmlmod.unescape(src.group(1)))
        if w and int(w.group(1)) >= 400:
            return url, "article_img"
        if w and int(w.group(1)) < MIN_W:
            if why is not None:
                why.append({"img": url[:200], "skipped": f"declared {w.group(1)} px wide, under {MIN_W}"})
        elif not first:
            first = url
    return (first, "article_img") if first else (None, None)


def img_src(tag: str):
    """the picture an <img> tag shows: src, else (lazy loading) data-src / data-lazy-src / data-original / the first srcset entry"""
    for attr in ("src", "data-src", "data-lazy-src", "data-original", "srcset", "data-srcset"):
        m = re.search(r'\s%s\s*=\s*["\']([^"\']+)["\']' % attr, tag, re.I)
        v = m.group(1).strip().split(",")[0].strip().split(" ")[0] if m else ""
        if v and not v.startswith("data:") and not re.search(r"placeholder|lazy|blank|spacer|transparent", v, re.I):
            return v
    return None


_JUNK = re.compile(r"logo|icon|sprite|avatar|pixel|blank|banner|/ads?/|\.svg|\.gif|data:|mode=img|piwik|ansprechpartner|contact", re.I)


def body_images(page_html: str, base: str) -> list[str]:
    """The article's own <img> links, in page order, wide ones (declared >= 400 px) first: inside <article> when the page has one,
    else from the first <h1> on (menus and hero banners above the headline are not the story's)."""
    m = re.search(r"<article\b.*?</article>", page_html, re.I | re.S) or re.search(r"<h1\b.*", page_html, re.I | re.S)
    wide, rest = [], []
    for t in re.finditer(r"<img\b[^>]*>", m.group(0) if m else page_html, re.I):
        src = img_src(t.group(0))
        src = re.match(r"(.+)", src) if src else None
        if not src or _JUNK.search(src.group(1)):
            continue
        w = re.search(r'\swidth=["\']?(\d+)', t.group(0), re.I)
        if w and int(w.group(1)) < MIN_W:
            continue
        url = urljoin(base, htmlmod.unescape(src.group(1).strip()))
        (wide if w and int(w.group(1)) >= 400 else rest).append(url)
    return list(dict.fromkeys(wide + rest))


def unique_images(per_page: dict[str, list[str]]) -> dict[str, list[str]]:
    """Per page of ONE site: its images that no other of these pages carries. A template picture (the newsroom's share image,
    a hero banner) is on every page; the story's own photo is on one."""
    from collections import Counter
    n = Counter(u for imgs in per_page.values() for u in set(imgs))
    return {p: [u for u in imgs if n[u] == 1] for p, imgs in per_page.items()}


def refind_defaults(workers=8) -> dict:
    """Pages whose preview picture turned out to be the site's default (status 'site_default', e.g. all 84 Lockheed Martin
    newsroom pages share ryan169.jpg): fetch every such page of a site again and take the first article image that is unique to
    that page. A page with none keeps 'site_default'. Then re-point the cards."""
    import psycopg2.extras
    from urllib.parse import urlsplit
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT page_url FROM media.page_image WHERE status = 'site_default'")
    by_host: dict[str, list[str]] = {}
    for r in cur.fetchall():
        by_host.setdefault(urlsplit(r["page_url"]).netloc, []).append(r["page_url"])
    html: dict[str, list[str]] = {}

    def get(page):
        try:
            raw, _ct, final = fetch(page, 2_000_000, "text/html,*/*")
            return page, body_images(raw.decode("utf-8", "replace"), final)
        except Exception:  # noqa: BLE001
            return page, []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for page, imgs in ex.map(get, [p for ps in by_host.values() for p in ps]):
            html[page] = imgs
    stats: dict[str, int] = {}
    for host, pages in by_host.items():
        uniq = unique_images({p: html.get(p, []) for p in pages})
        for page in pages:
            got = None
            for img_url in uniq[page][:4]:
                try:
                    data, _ct, _ = fetch(img_url, MAX_BYTES, "image/*,*/*", referer=page)
                    ct, w, h = check_image(data)
                    data, ct, w, h = shrink(data, ct, w, h)
                    got = (str(uuid.uuid5(uuid.NAMESPACE_URL, img_url)), img_url, ct, data, len(data), w, h, hashlib.sha256(data).hexdigest())
                    break
                except Exception:  # noqa: BLE001
                    continue
            if got:
                cur.execute("""INSERT INTO media.image (image_id, source_url, content_type, bytes, byte_len, width, height, sha256)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (image_id) DO NOTHING""",
                            (got[0], got[1], got[2], psycopg2.Binary(got[3]), got[4], got[5], got[6], got[7]))
                cur.execute("""UPDATE media.page_image SET image_id = %s, how = 'article_unique', status = 'ok', error = NULL,
                               checked_at = now() WHERE page_url = %s""", (got[0], page))
            stats[host] = stats.get(host, 0) + bool(got)
            ops_log.note("image", "article_unique" if got else "site_default_kept",
                         f"The page's preview image is the site's default picture; took the article image only this page uses ({got[5]}x{got[6]})."
                         if got else f"The page's preview image is the site's default picture, and no article image is unique to this page "
                                     f"(checked against {len(pages) - 1} other {host} pages); left without a picture.",
                         subject=page, tbl="media.page_image", rec_id=page,
                         detail={"image": got[1] if got else None, "candidates": uniq[page][:4]})
        conn.commit()
        print(f"  {host}: {stats[host]} of {len(pages)} pages now have their own picture", flush=True)
    point_cards(conn)
    return stats


HOW_WORDS = {"card_link": "the image link the card already had", "og_image": "the page's preview image (og:image)",
             "twitter_image": "the page's Twitter preview image", "link_image_src": "the page's <link rel=image_src> image",
             "article_img": "the article's own <img> (the page has no preview tag)",
             "article_unique": "the article image no other page of the site uses"}


def image_note(status, how, size, shrunk, err, why) -> str:
    """one sentence for the pipeline log: what the image job did with this page, and why"""
    where = HOW_WORDS.get(how, how or "")
    skipped = f" {len(why)} other <img> passed over ({'; '.join(sorted({w['skipped'] for w in why}))})." if why else ""
    if status == "ok":
        return f"Stored {where}, {size[0]}x{size[1]}" + (f", shrunk to {shrunk[0]}x{shrunk[1]}" if shrunk else "") + "." + skipped
    if status == "no_image":
        return "Page fetched; no preview tag (og:image / twitter:image / image_src) and no usable <img> in the article." + skipped
    if status == "too_small":
        dims = f"{size[0]}x{size[1]}" if size else "too small"
        return f"Found {where}, but it is {dims}, under the {MIN_W}x{MIN_H} minimum (a logo or icon size); not used." + skipped
    if status == "too_large":
        return f"Found {where}, but it is over {MAX_BYTES // 1_000_000} MB; not used."
    if status == "not_image":
        return f"Found {where}, but the link did not return a picture; not used."
    if status == "page_failed":
        return f"Could not fetch the page: {err}."
    return f"Found {where}, but could not download it: {err}."


def check_image(data: bytes):
    """(content_type, width, height) if the bytes decode as a large enough picture, else raise ValueError(reason)."""
    from PIL import Image
    if len(data) > MAX_BYTES:
        raise ValueError("too_large")
    try:
        im = Image.open(io.BytesIO(data))
        im.verify()
        im = Image.open(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise ValueError("not_image") from e
    w, h = im.size
    if w < MIN_W or h < MIN_H:
        e = ValueError("too_small")
        e.size = (w, h)                     # for the pipeline log's note
        raise e
    return Image.MIME.get(im.format, "image/" + (im.format or "jpeg").lower()), w, h


MAX_W, JPEG_Q, SHRINK_OVER = 1200, 82, 250_000


def shrink(data: bytes, ctype: str, w: int, h: int):
    """(bytes, content_type, w, h): a picture wider than MAX_W or heavier than SHRINK_OVER is scaled to MAX_W and stored as JPEG
    (cards show it at under 600 px; ~1 GB for all pages otherwise). Smaller ones are kept as they came."""
    if w <= MAX_W and len(data) <= SHRINK_OVER:
        return data, ctype, w, h
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    if w > MAX_W:
        im = im.resize((MAX_W, max(1, round(h * MAX_W / w))))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=JPEG_Q, optimize=True)
    return b.getvalue(), "image/jpeg", im.size[0], im.size[1]


def _selftest() -> None:
    h = '<html><head><meta property="og:image" content="/img/a.jpg?x=1&amp;y=2"></head></html>'
    assert find_image(h, "https://ex.com/news/1") == ("https://ex.com/img/a.jpg?x=1&y=2", "og_image")
    assert find_image('<meta content="https://c.com/p.png" name="twitter:image">', "https://ex.com")[1] == "twitter_image"
    assert find_image('<article><img src="/logo.svg"><img src="/photos/tank.jpg"></article>', "https://ex.com/a")[0] == "https://ex.com/photos/tank.jpg"
    assert find_image("<p>no picture</p>", "https://ex.com") == (None, None)
    ar = ('<img src="//cdnhst.xyz/code?mode=img&amp;code=4b"><img src="/images/banners/2026/a.jpg" width="728">'
          '<img src="/x/anim.gif" width="300"><img src="/s/flag.png" width="20"><img class="el-image" src="/stories/k9.jpg" width="1920">')
    assert find_image(ar, "https://ar.com/n/1") == ("https://ar.com/stories/k9.jpg", "article_img")
    lm = '<nav><img src="/hero.jpg"></nav><h1>Spike NLOS</h1><img src="/t/ryan169.jpg" width="1200"><img src="/file.php/1/Spike.jpg">'
    assert body_images(lm, "https://n.lm.com/a") == ["https://n.lm.com/t/ryan169.jpg", "https://n.lm.com/file.php/1/Spike.jpg"]
    u = unique_images({"a": ["T", "A1"], "b": ["T", "B1", "B2"], "c": ["T"]})
    assert u == {"a": ["A1"], "b": ["B1", "B2"], "c": []}, u
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (640, 360)).save(b, "JPEG")
    assert check_image(b.getvalue())[1:] == (640, 360)
    tiny = io.BytesIO()
    Image.new("RGB", (40, 40)).save(tiny, "PNG")
    for data, why in ((tiny.getvalue(), "too_small"), (b"<html>", "not_image")):
        try:
            check_image(data)
            raise AssertionError(why)
        except ValueError as e:
            assert str(e) == why
    print("media_images self-check ok")


def run(limit=None, workers=8, retry=False) -> dict:
    import psycopg2.extras
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    pages: dict[str, str | None] = {}           # page url -> a link the card already has
    for _t, (_c, sql, _col) in CARDS.items():
        cur.execute(sql)
        for r in cur.fetchall():
            if r["page"] and str(r["page"]).startswith("http"):
                img = r["img"] if r["img"] and str(r["img"]).startswith("http") else None
                pages[r["page"]] = pages.get(r["page"]) or img
    cur.execute(PRODUCT_NEWS)
    for r in cur.fetchall():
        pages.setdefault(r["page"], None)
    cur.execute("SELECT page_url FROM media.page_image" + (" WHERE status IN ('ok', 'site_default')" if retry else ""))   # --retry: pages left without a picture again
    done = {r["page_url"] for r in cur.fetchall()}
    todo = [(p, img) for p, img in pages.items() if p not in done][: limit or None]
    print(f"{len(pages)} pages behind the cards; {len(done)} already checked; {len(todo)} to do", flush=True)
    lock = threading.Lock()
    stats: dict[str, int] = {}
    out = connect()

    def one(page, card_img):
        how, img_url, status, err, rec = None, None, "no_image", None, None
        why, size, shrunk = [], None, None
        def candidates():
            """the card's own link, then the page's preview tag, then the article's own photos (owner 2026-10-23: a PIB page's
            og:image did not return a picture while the press release has two photos)"""
            if card_img:
                yield card_img, "card_link"
            raw, _ct, final = fetch(page, 2_000_000, "text/html,*/*")
            text = raw.decode("utf-8", "replace")
            first = find_image(text, final, why)
            if first[0]:
                yield first
            for u in body_images(text, final)[:4]:
                if u != first[0]:
                    yield u, "article_img"
        try:
            last = None
            for img_url, how in candidates():
                try:
                    data, ctype, _ = fetch(img_url, MAX_BYTES, "image/*,*/*", referer=page)
                    ct, w, h = check_image(data)
                except Exception as e:  # noqa: BLE001 -- this candidate is no good: try the next one
                    last = e
                    continue
                size = (w, h)
                data, ct, w, h = shrink(data, ct, w, h)
                shrunk = (w, h) if (w, h) != size else None
                rec = (str(uuid.uuid5(uuid.NAMESPACE_URL, img_url)), img_url, ct, data, len(data), w, h, hashlib.sha256(data).hexdigest())
                status, last = "ok", None
                break
            if last is not None:
                raise last
        except ValueError as e:
            known = str(e) in ("too_large", "not_image", "too_small")    # check_image reasons; other ValueErrors (bad url) are failures
            status, err = (str(e), None) if known else ("image_failed" if img_url else "page_failed", f"ValueError: {str(e)[:150]}")
            size = getattr(e, "size", None)
        except Exception as e:  # noqa: BLE001
            status, err = ("image_failed" if img_url else "page_failed"), f"{type(e).__name__}: {str(e)[:150]}"
        # the pipeline log: what was done with this page, and why (backend/ops_log)
        ops_log.note("image", how if status == "ok" else status, image_note(status, how, size, shrunk, err, why), subject=page,
                     tbl="media.page_image", rec_id=page,
                     detail={"image": img_url, "how": how, "size": size, "stored_size": shrunk, "error": err, "passed_over": why[:12] or None})
        with lock:
            stats[status] = stats.get(status, 0) + 1
            with out.cursor() as c2:
                if rec:
                    c2.execute("""INSERT INTO media.image (image_id, source_url, content_type, bytes, byte_len, width, height, sha256)
                                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (image_id) DO NOTHING""",
                               (rec[0], rec[1], rec[2], psycopg2.Binary(rec[3]), rec[4], rec[5], rec[6], rec[7]))
                c2.execute("""INSERT INTO media.page_image (page_url, image_id, how, status, error) VALUES (%s,%s,%s,%s,%s)
                              ON CONFLICT (page_url) DO UPDATE SET image_id = EXCLUDED.image_id, how = EXCLUDED.how, status = EXCLUDED.status,
                                error = EXCLUDED.error, checked_at = now()""", (page, rec[0] if rec else None, how, status, err))
            out.commit()
            n = sum(stats.values())
            if n % 200 == 0:
                print(f"  {n}/{len(todo)} {stats}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, p, img) for p, img in todo]):
            f.result()
    point_cards(conn)
    print("pages:", stats, flush=True)
    return stats


SITE_DEFAULT_PAGES = 5      # one picture behind this many articles is the site's logo / template image, not the article's


def point_cards(conn) -> None:
    """Each card's image column -> /api/image/<id> of its page's stored picture (cards whose page has none keep what they had).
    A site-default picture (KNDS's logo behind 69 articles) is marked status 'site_default' and its cards get no image."""
    cur = conn.cursor()
    cur.execute("""UPDATE media.page_image p SET status = 'site_default' WHERE status = 'ok' AND image_id IN
                   (SELECT image_id FROM media.page_image WHERE status IN ('ok', 'site_default') GROUP BY 1 HAVING count(*) >= %s)
                   RETURNING page_url, image_id::text,
                     (SELECT count(*) FROM media.page_image q WHERE q.image_id = p.image_id) AS shared""",
                (SITE_DEFAULT_PAGES,))
    marked = cur.fetchall()
    print(f"  {len(marked)} pages only had the site's default picture", flush=True)
    for r in marked:
        ops_log.note("image", "site_default", f"The picture found for this page is also on {r['shared']} other pages of the site "
                     f"(a logo or template image, not the article's); the card shows no picture.",
                     subject=r["page_url"], tbl="media.page_image", rec_id=r["page_url"], detail={"image_id": r["image_id"], "pages": r["shared"]})
    for table, (idcol, sql, col) in CARDS.items():
        cur.execute(f"""UPDATE staging.{table} SET {col} = NULL WHERE {col} IN
                        (SELECT DISTINCT '/api/image/' || image_id FROM media.page_image WHERE status = 'site_default')""")
        # and the original link of that same default picture, where the card carried it itself
        cur.execute(f"""UPDATE staging.{table} SET {col} = NULL WHERE {col} IN
                        (SELECT i.source_url FROM media.image i JOIN media.page_image p USING (image_id) WHERE p.status = 'site_default')""")
        cur.execute(f"""UPDATE staging.{table} t SET {col} = '/api/image/' || p.image_id
                        FROM ({sql}) c JOIN media.page_image p ON p.page_url = c.page AND p.status = 'ok'
                        WHERE t.{idcol}::text = c.id AND t.{col} IS DISTINCT FROM '/api/image/' || p.image_id""")
        print(f"  {table}: {cur.rowcount} cards now show a stored image", flush=True)
    conn.commit()


def report() -> None:
    from prompts.run import connect
    cur = connect().cursor()
    cur.execute("SELECT status, count(*) AS n FROM media.page_image GROUP BY 1 ORDER BY 2 DESC")
    print({r["status"]: r["n"] for r in cur.fetchall()})
    cur.execute("SELECT count(*) AS n, pg_size_pretty(sum(byte_len)) AS size FROM media.image")
    print(dict(cur.fetchone()))


@ops_log.logged("backend.media_images")
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--point", action="store_true", help="only re-point the cards at the stored pictures (no fetching)")
    ap.add_argument("--refind-defaults", action="store_true", help="pages that only had the site's default picture: take the article's own")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--retry", action="store_true", help="check again the pages that ended without a picture (not_image, too_small, failed...)")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
    elif a.report:
        report()
    elif a.refind_defaults:
        refind_defaults(a.workers)
    elif a.point:
        from prompts.run import connect
        point_cards(connect())
    else:
        run(a.limit, a.workers, a.retry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
