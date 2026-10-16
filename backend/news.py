"""News job: Google News -> exact article -> source policy -> image -> PostgreSQL (STAGING).

Port of the old-schema pulse job (git branch db-driven, backend/pulse.py) to the v2 schema.
For a competitor (and optionally its products) and a date or date range it
  1. searches Google News RSS with `after:YYYY-MM-DD before:YYYY-MM-DD` (before is exclusive,
     so the query uses to+1) in progressively broader queries,
  2. drops every RSS item whose published date is outside the range (the operators are only a
     hint to Google; the parsed pubDate is the rule),
  3. resolves news.google.com wrapper links to the exact article URL (batchexecute; an item
     that cannot be resolved is dropped -- never stored as a wrapper/homepage link),
  4. applies the source policy (backend/sources.py: allowlist + blocklist) and a relevance
     check (headline, og:title or description must name the company / product),
  5. reads the article page once: canonical URL, og/twitter/JSON-LD image, site name,
  6. downloads the image into media/news/<sha1>.<ext>  (KSSL_MEDIA_DIR overrides media/),
  7. writes every kept item to staging.news_candidate (a holding table, never reviewed or shown).
     `python -m prompts.run news` then groups candidates that report the same story, picks one main
     article per story and writes ONE row per story to the real news tables (prompts/news_merge.py);
     they reach the live UI only after Approve in the review copy.

Date range: `date` (one day) or `from`/`to` (YYYY-MM-DD, inclusive). With none of them: the
last 30 days. Only `from`: up to today. Only `to`: the 30 days ending then.

Where things go (no columns are added to ui/serving tables):
  * staging.news_candidate (db/setup/06_news_candidate.sql): candidate_id (= row_id(url, owner), the id
    the story row gets when this candidate is its main article), competitor_id / product_id (NULL =
    company news), headline, article_url, published_date, publisher, image_url, image_local_path
    (relative to the media dir, e.g. news/<sha1>.jpg), source_tier ("primary" | "independent"),
    pre_group, status 'new'. A URL already stored for the same owner is not re-added (status kept).
  * pre_group: code pre-grouping of obvious copies. A new candidate whose headline is >= 85% similar
    (near_copy) to an earlier candidate of the SAME owner within +-3 days points at it; the model
    run only has to group the rest.
  * staging.competitive_news_article / competitive_product_news and the fact_source rows (article_url,
    image_local_path, also_reported_by, category judgement) are written by prompts/news_merge.py,
    not here; `category` is filled by the prompt run, never invented by this job.

Connection: env KSSL_STAGING_DSN, falling back to KSSL_DSN. Writes go to schema `staging` only
(the GET reads KSSL_SERVING_DSN on the live backend).
Competitor names come from staging.competitive_competitor (display_name, legal_name,
short_name); there is no website column, so company domains are only learnt from the RSS
publisher when it is the company itself (or passed with --domain).

CLI:  python -m backend.news --competitor <uuid|all> [--products] [--date 2026-10-01 |
          --from 2026-09-01 --to 2026-09-30] [--limit N] [--dry-run]
      python -m backend.news --selftest
API:  POST /api/news/refresh?competitor_id=<uuid|all>&products=true&date=... | &from=..&to=..&limit=..
      GET  /api/news?competitor_id=&from=&to=   (reads staging when KSSL_VIEW=review, else serving)
      python -m backend.news --regroup   (pre-group the existing 'new' candidates; one-off after a bulk move)

Stdlib only (urllib, html.parser, json, concurrent.futures) + psycopg2 + FastAPI (router).
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException, Query

from backend.sources import classify_reason, host_of

router = APIRouter()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    # client hints + fetch metadata: several CDNs (e.g. NDTV's) reject requests without them
    "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
EDITION = "hl=en-IN&gl=IN&ceid=IN:en"     # Google News edition (India, English)
TIMEOUT = 10
WORKERS = 12
MAX_PAGE_BYTES = 3_000_000
IMG_MIN, IMG_MAX = 5_000, 8_000_000
MEDIA_DIR = Path(os.getenv("KSSL_MEDIA_DIR", Path(__file__).resolve().parent.parent / "media"))


# ----------------------------------------------------------------------------- HTTP

class _HostGate:
    """Per-host politeness: at most N concurrent requests and a small gap between starts."""

    def __init__(self, per_host=2, gap=0.25, overrides=None):
        self.per_host, self.gap, self.overrides = per_host, gap, overrides or {}
        self.lock = threading.Lock()
        self.sems: dict[str, threading.Semaphore] = {}
        self.last: dict[str, float] = {}

    def __call__(self, host):
        gate = self

        class _Ctx:
            def __enter__(self_):
                with gate.lock:
                    sem = gate.sems.setdefault(host, threading.Semaphore(gate.overrides.get(host, gate.per_host)))
                sem.acquire()
                with gate.lock:
                    wait = gate.last.get(host, 0) + gate.gap - time.monotonic()
                    gate.last[host] = max(time.monotonic(), gate.last.get(host, 0) + gate.gap)
                if wait > 0:
                    time.sleep(wait)
                self_.sem = sem

            def __exit__(self_, *a):
                self_.sem.release()

        return _Ctx()


GATE = _HostGate(overrides={"news.google.com": 8})


@dataclass
class Resp:
    status: int
    url: str
    headers: dict
    body: bytes

    def text(self) -> str:
        ctype = self.headers.get("content-type", "")
        m = re.search(r"charset=([\w-]+)", ctype, re.I)
        enc = m.group(1) if m else None
        if not enc:
            m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", self.body[:4000], re.I)
            enc = m.group(1).decode() if m else "utf-8"
        try:
            return self.body.decode(enc, "replace")
        except LookupError:
            return self.body.decode("utf-8", "replace")


def http(url, *, data=None, headers=None, timeout=TIMEOUT, max_bytes=MAX_PAGE_BYTES) -> Resp:
    """GET/POST with browser headers; never raises for HTTP status (status 0 = network error)."""
    hdrs = dict(BROWSER_HEADERS)
    hdrs.update(headers or {})
    req = Request(url, data=data, headers=hdrs)
    with GATE(host_of(url)):
        try:
            with urlopen(req, timeout=timeout) as r:
                status, final, rh, body = r.status, r.geturl(), r.headers, r.read(max_bytes)
        except HTTPError as e:
            status, final, rh = e.code, e.geturl() or url, e.headers
            try:
                body = e.read(200_000)
            except Exception:
                body = b""
        except (URLError, OSError, ValueError) as e:
            return Resp(0, url, {}, str(e).encode())
    h = {k.lower(): v for k, v in (rh.items() if rh else [])}
    enc = h.get("content-encoding", "")
    try:
        if "gzip" in enc:
            body = gzip.decompress(body)
        elif "deflate" in enc:
            body = zlib.decompress(body, -zlib.MAX_WBITS) if body[:1] != b"x" else zlib.decompress(body)
    except Exception:
        pass
    return Resp(status, final, h, body)


# ----------------------------------------------------------------------------- dates

DEFAULT_DAYS = 30


def _parse_day(s: str, what: str) -> date:
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        raise ValueError(f"{what} must be YYYY-MM-DD, got {s!r}") from None


def date_range(day=None, frm=None, to=None, today: date | None = None) -> tuple[date, date]:
    """Inclusive (start, end). `day` is exclusive with from/to; no input -> last 30 days."""
    today = today or date.today()
    if day and (frm or to):
        raise ValueError("use either date, or from/to")
    if day:
        d = _parse_day(day, "date")
        return d, d
    start = _parse_day(frm, "from") if frm else None
    end = _parse_day(to, "to") if to else None
    if start and not end:
        end = max(today, start)
    if end and not start:
        start = end - timedelta(days=DEFAULT_DAYS - 1)
    if not start:
        start, end = today - timedelta(days=DEFAULT_DAYS - 1), today
    if start > end:
        raise ValueError(f"from ({start}) is after to ({end})")
    return start, end


def in_range(d, rng: tuple[date, date]) -> bool:
    return d is not None and rng[0] <= d <= rng[1]


def date_ops(rng: tuple[date, date]) -> str:
    """Google News search operators; `before:` is exclusive, hence end + 1 day."""
    return f"after:{rng[0].isoformat()} before:{(rng[1] + timedelta(days=1)).isoformat()}"


# ----------------------------------------------------------------------------- RSS

def parse_rss(body: bytes) -> list[dict]:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return []
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = it.find("source")
        source = (src.text or "").strip() if src is not None else ""
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].strip()
        pub = None
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate") or "").date()
        except (TypeError, ValueError):
            pass
        out.append({
            "title": title,
            "link": (it.findtext("link") or "").strip(),
            "source": source,
            "source_url": src.get("url", "") if src is not None else "",
            "date": pub,
        })
    return out


def rss_search(query: str) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={quote(query)}&{EDITION}"
    r = http(url, headers={"Accept": "application/rss+xml,application/xml"})
    return parse_rss(r.body) if r.status == 200 else []


# ----------------------------------------------------------------------------- resolve

def _article_id(link: str) -> str:
    m = re.search(r"news\.google\.com/(?:rss/)?articles/([^?/#]+)", link or "")
    return m.group(1) if m else ""


def _decode_id(aid: str) -> str:
    """Old-style ids embed the URL in the protobuf; new 'AU_yqL' ids do not."""
    try:
        raw = base64.urlsafe_b64decode(aid + "=" * (-len(aid) % 4))
    except (ValueError, base64.binascii.Error):
        return ""
    m = re.search(rb"https?://[\x21-\x7e]+", raw)
    if not m or raw.find(b"AU_yqL") != -1:
        return ""
    return m.group(0).decode("ascii", "ignore")


def _batchexecute(sigs: list[tuple[str, str, str]]) -> dict[str, str]:
    """One POST for many ids: [(aid, ts, sg)] -> {aid: article_url}. The answer is
    ")]}'" + a JSON array of ["wrb.fr", "Fbv4je", "<json [garturlres, url, 1]>", ..., "<req id>"]."""
    if not sigs:
        return {}
    envs = []
    for n, (aid, ts, sg) in enumerate(sigs, 1):
        inner = ["garturlreq",
                 [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
                  "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                 aid, int(ts), sg]
        envs.append(["Fbv4je", json.dumps(inner, separators=(",", ":")), None, str(n)])
    r = http("https://news.google.com/_/DotsSplashUi/data/batchexecute",
             data=urlencode({"f.req": json.dumps([envs], separators=(",", ":"))}).encode(),
             headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                      "Referer": "https://news.google.com/"})
    if r.status != 200:
        return {}
    txt = r.text()
    if txt.startswith(")]}'"):
        txt = txt[4:]
    out = {}
    # body is one JSON array, optionally preceded by chunk-length lines
    for chunk in re.split(r"\n\d+\n", "\n" + txt.strip()):
        chunk = chunk.strip()
        if not chunk.startswith("["):
            continue
        try:
            env = json.loads(chunk)
        except ValueError:
            continue
        for e in env:
            if not (isinstance(e, list) and len(e) > 6 and e[0] == "wrb.fr" and e[1] == "Fbv4je" and e[2]):
                continue
            try:
                res, idx = json.loads(e[2]), int(e[6]) - 1
            except (ValueError, TypeError):
                continue
            if isinstance(res, list) and len(res) > 1 and res[0] == "garturlres"                     and isinstance(res[1], str) and res[1].startswith("http") and 0 <= idx < len(sigs):
                out[sigs[idx][0]] = res[1]
    return out


def _wrapper(aid: str):
    """Fetch the news.google.com wrapper page -> ("url", final) if it redirected off Google,
    ("sig", (aid, ts, sg)) when it carries the batchexecute signature, else ("", None)."""
    page = http(f"https://news.google.com/rss/articles/{aid}?{EDITION}")
    if page.status == 200 and "news.google.com" not in host_of(page.url):
        return "url", page.url
    if page.status == 200:
        body = page.text()
        ts = re.search(r'data-n-a-ts="(\d+)"', body)
        sg = re.search(r'data-n-a-sg="([^"]+)"', body)
        if ts and sg:
            return "sig", (aid, ts.group(1), sg.group(1))
    return "", None


# Google rate-limits wrapper pages to ~4/s per client, so resolved ids are cached on disk:
# a re-run only resolves articles it has not seen before.
CACHE_FILE = Path(os.getenv("KSSL_PULSE_CACHE", Path(__file__).resolve().parent.parent / ".cache" / "pulse_resolve.json"))
_cache_lock = threading.Lock()
_cache: dict[str, str] | None = None


def _cache_get() -> dict[str, str]:
    global _cache
    with _cache_lock:
        if _cache is None:
            try:
                _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _cache = {}
        return _cache


def _cache_put(new: dict[str, str]):
    if not new:
        return
    cache = _cache_get()
    with _cache_lock:
        cache.update(new)
        if len(cache) > 20000:                       # keep the newest entries
            for k in list(cache)[: len(cache) - 20000]:
                del cache[k]
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE_FILE.with_suffix(f".tmp{threading.get_ident()}")
            tmp.write_text(json.dumps(cache), encoding="utf-8")
            os.replace(tmp, CACHE_FILE)
        except OSError:
            pass


def resolve_many(links: list[str], workers=WORKERS) -> dict[str, tuple[str, str]]:
    """{link: (article_url, method)} or {link: ("", reason)}. Never returns a Google URL.
    Wrapper pages are fetched in parallel, then ONE batchexecute call resolves them all
    (Google serialises concurrent batchexecute calls, so batching is ~5x faster).
    Failures get one retry (fresh signature, single call), then the id-decode fallback."""
    out: dict[str, tuple[str, str]] = {}
    ids = {}
    for link in links:
        if "news.google.com" not in (link or ""):
            out[link] = (link, "direct") if (link or "").startswith("http") else ("", "no link")
        elif _article_id(link):
            ids[_article_id(link)] = link
        else:
            out[link] = ("", "no article id")
    cache = _cache_get()
    for aid in list(ids):
        if cache.get(aid):
            out[ids.pop(aid)] = (cache[aid], "cache")
    pending = list(ids)
    for attempt in range(2):
        if not pending:
            break
        with ThreadPoolExecutor(max_workers=workers) as ex:
            wraps = list(ex.map(_wrapper, pending))
        sigs = []
        for aid, (kind, val) in zip(pending, wraps):
            if kind == "url":
                out[ids[aid]] = (val, "redirect")
            elif kind == "sig":
                sigs.append(val)
        got = {}
        for i in range(0, len(sigs), 20):
            got.update(_batchexecute(sigs[i:i + 20]))
        method = "batchexecute" + (" (retry)" if attempt else "")
        for aid, url in got.items():
            if "news.google.com" not in host_of(url):
                out[ids[aid]] = (url, method)
        pending = [a for a in pending if ids[a] not in out]
        if pending and attempt == 0:
            time.sleep(0.5)
    for aid in pending:
        url = _decode_id(aid)
        out[ids[aid]] = (url, "id-decode") if url else ("", "unresolved")
    _cache_put({aid: out[link][0] for aid, link in ids.items() if out.get(link, ("",))[0]})
    return out


def resolve(link: str) -> tuple[str, str]:
    """(article_url, method) or ("", reason) for one link."""
    return resolve_many([link])[link]


TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|ocid|cmpid|igshid|"
                      r"ref|ref_src|smid|s_cid|guccounter|guce_\w+|_ga|_gl|ito|cid|src|"
                      r"from|feature|share|amp|outputType)$", re.I)


def clean_url(url: str) -> str:
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    path = p.path
    if path.endswith("/amp") or path.endswith("/amp/"):
        path = path.rsplit("/amp", 1)[0] or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urlencode(q), ""))


def is_homepage(url: str) -> bool:
    path = urlsplit(url).path.strip("/")
    return path in ("", "index.html", "index.php", "en", "home", "news")


# ----------------------------------------------------------------------------- page parse

class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: list[tuple[str, str]] = []
        self.links: list[tuple[str, str]] = []
        self.ld: list[str] = []
        self.title = ""
        self._in_ld = self._in_title = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").strip().lower()
            if key and "content" in a:
                self.meta.append((key, a["content"].strip()))
        elif tag == "link":
            rel = a.get("rel", "").lower()
            if a.get("href"):
                self.links.append((rel, a["href"].strip()))
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_ld, self._buf = True, []
        elif tag == "title" and not self.title:
            self._in_title, self._buf = True, []

    def handle_data(self, data):
        if self._in_ld or self._in_title:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self.ld.append("".join(self._buf))
            self._in_ld = False
        elif tag == "title" and self._in_title:
            self.title = "".join(self._buf).strip()
            self._in_title = False


def _ld_objects(texts):
    def walk(o):
        if isinstance(o, list):
            for x in o:
                yield from walk(x)
        elif isinstance(o, dict):
            yield o
            for k in ("@graph", "mainEntity", "mainEntityOfPage"):
                if isinstance(o.get(k), (list, dict)):
                    yield from walk(o[k])
    for t in texts:
        try:
            yield from walk(json.loads(t.strip().rstrip(";")))
        except ValueError:
            continue


def _ld_images(img):
    """NewsArticle.image as string / ImageObject / list -> [(url, width)]."""
    out = []
    for x in img if isinstance(img, list) else [img]:
        if isinstance(x, str):
            out.append((x, 0))
        elif isinstance(x, dict):
            u = x.get("url") or x.get("contentUrl") or ""
            try:
                w = int(str(x.get("width") or 0).split(".")[0].replace("px", "") or 0)
            except ValueError:
                w = 0
            if isinstance(u, str) and u:
                out.append((u, w))
    return out


BAD_IMG = re.compile(r"(logo|sprite|placeholder|favicon|icon|blank|pixel|1x1|spacer|avatar|"
                     r"emblem|default[-_]?(image|img|og|share)|fallback|no[-_]?image|og[-_]default)", re.I)


def _int(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


@dataclass
class PageInfo:
    canonical: str = ""
    title: str = ""
    description: str = ""
    site_name: str = ""
    published: str = ""
    image: str = ""
    images: list = field(default_factory=list)


ABS_OR_ROOT = re.compile(r"^(https?://[^/]|//[^/]|/[^/])", re.I)


def parse_page(html_text: str, base: str) -> PageInfo:
    p = _MetaParser()
    try:
        p.feed(html_text)
    except Exception:
        pass
    info = PageInfo()
    meta = p.meta
    first = lambda *keys: next((v for k, v in meta if k in keys and v), "")
    info.title = first("og:title", "twitter:title") or html.unescape(p.title)
    info.description = first("og:description", "description", "twitter:description")
    info.site_name = first("og:site_name")
    info.published = first("article:published_time", "datepublished", "pubdate", "publishdate")
    canon = next((h for r, h in p.links if "canonical" in r.split()), "") or first("og:url")

    # image candidates in priority order: og (largest declared width wins), twitter, JSON-LD, image_src
    og: list[list] = []
    for k, v in meta:
        if k in ("og:image", "og:image:url", "og:image:secure_url"):
            if k == "og:image" or not og:
                og.append([v, 0])
            elif not og[-1][0].startswith("https") and v.startswith("https"):
                og[-1][0] = v
        elif k == "og:image:width" and og:
            og[-1][1] = _int(v)
    cands = [c for c in sorted(og, key=lambda c: -c[1])]
    cands += [[v, 0] for k, v in meta if k in ("twitter:image", "twitter:image:src")]
    for o in _ld_objects(p.ld):
        t = o.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(isinstance(x, str) and ("Article" in x or x == "BlogPosting") for x in types):
            cands += [[u, w] for u, w in _ld_images(o.get("image"))]
            if not info.published and isinstance(o.get("datePublished"), str):
                info.published = o["datePublished"]
            if not info.site_name and isinstance(o.get("publisher"), dict):
                info.site_name = o["publisher"].get("name") or ""
    cands += [[h, 0] for r, h in p.links if "image_src" in r]
    for u, w in cands:
        u = html.unescape(u.strip())
        if not ABS_OR_ROOT.match(u):      # "https:/x" or "www.x/..." are publisher typos
            continue
        u = urljoin(base, u)
        name = urlsplit(u).path.rsplit("/", 1)[-1]
        if name.lower().endswith(".svg") or BAD_IMG.search(name) or 0 < w < 200 or u in info.images:
            continue
        info.images.append(u)
    info.image = info.images[0] if info.images else ""
    canon = html.unescape(canon.strip())
    if canon and ABS_OR_ROOT.match(canon):
        info.canonical = urljoin(base, canon)
    return info


def page_blocked(r: Resp) -> str:
    if r.status in (401, 403, 429, 451) or r.status >= 500:
        return f"http {r.status}"
    if r.status == 0:
        return "network error"
    host = host_of(r.url)
    if host.startswith(("consent.", "guce.")) or "/consent" in urlsplit(r.url).path:
        return "consent page"
    head = r.body[:20000].lower()
    if b"captcha-delivery.com" in head or b"datadome" in head or b"cf-chl-" in head:
        return "bot wall"
    m = re.search(rb"<title[^>]*>([^<]{0,80})", head)
    if m and re.search(rb"access denied|attention required|just a moment|are you a robot|"
                       rb"request rejected|forbidden", m.group(1)):
        return "bot wall"
    return ""


# ----------------------------------------------------------------------------- image

_MAGIC = ((b"\xff\xd8\xff", "jpg"), (b"\x89PNG", "png"), (b"GIF8", "gif"))


def _img_ext(body: bytes, ctype: str) -> str:
    for sig, ext in _MAGIC:
        if body.startswith(sig):
            return ext
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp"
    if body[4:12] in (b"ftypavif", b"ftypavis"):
        return "avif"
    return ""


def download_image(img_url: str, referer: str, save=True) -> tuple[str, str]:
    """(relative path under MEDIA_DIR, "") or ("", reason). save=False validates only."""
    rel = f"news/{hashlib.sha1(img_url.encode()).hexdigest()}"
    for ext in ("jpg", "png", "gif", "webp", "avif"):
        if (MEDIA_DIR / f"{rel}.{ext}").exists():
            return f"{rel}.{ext}", ""
    r = http(img_url, headers={"Referer": referer, "Accept": "image/webp,image/jpeg,image/png,image/gif;q=0.9,*/*;q=0.5",
                               "Accept-Encoding": "identity", "Sec-Fetch-Dest": "image",
                               "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "cross-site"},
             max_bytes=IMG_MAX + 1)
    if r.status != 200:
        return "", f"image http {r.status}"
    ctype = r.headers.get("content-type", "").lower()
    if not ctype.startswith("image/") or "svg" in ctype:
        return "", f"image content-type {ctype or '?'}"
    if not IMG_MIN <= len(r.body) <= IMG_MAX:
        return "", f"image size {len(r.body)}"
    ext = _img_ext(r.body, ctype)
    if not ext:
        return "", "image bytes not jpg/png/gif/webp/avif"
    if not save:
        return f"{rel}.{ext}", ""
    path = MEDIA_DIR / f"{rel}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{ext}.part{threading.get_ident()}")
    tmp.write_bytes(r.body)
    os.replace(tmp, path)
    return f"{rel}.{ext}", ""


# ----------------------------------------------------------------------------- relevance

_SUFFIX = {"limited", "ltd", "pvt", "private", "inc", "incorporated", "corporation", "corp",
           "plc", "sa", "ag", "se", "gmbh", "co", "company", "llc", "the", "kg", "nv", "bv", "oy", "ab", "asa",
           "group", "holding", "holdings"}


def norm(s: str) -> str:
    s = html.unescape(s or "").lower().replace("&", " and ")
    s = re.sub(r"[^\w]+", " ", s)
    return " ".join(s.split())


def name_key(name: str) -> str:
    toks = norm(name).split()
    while toks and toks[-1] in _SUFFIX:
        toks.pop()
    while toks and toks[0] == "the":
        toks.pop(0)
    return " ".join(toks)


def mentions(text: str, names) -> bool:
    t = " " + norm(text) + " "
    compact = t.replace(" ", "")
    for n in names:
        k = name_key(n)
        if not k:
            continue
        if f" {k} " in t:
            return True
        # "K9 Vajra" vs "K-9 Vajra-T": compare without spaces, only for distinctive names
        ck = k.replace(" ", "")
        if (any(c.isdigit() for c in ck) or len(ck) >= 8) and ck in compact:
            return True
    return False


# ----------------------------------------------------------------------------- pipeline

@dataclass
class Item:
    title: str
    link: str
    source: str
    source_url: str
    date: object
    query: str = ""
    url: str = ""
    resolve_method: str = ""
    tier: str | None = None
    publisher: str = ""
    image_url: str = ""
    image_local_path: str = ""
    image_note: str = ""
    image_ok: bool = False
    status: str = "dropped"
    reason: str = ""
    secs: float = 0.0


def process(it: Item, names, company_domains, fetch_images=True) -> Item:
    t0 = time.monotonic()
    try:
        _process(it, names, company_domains, fetch_images)
    except Exception as e:  # one bad page must not stop the run
        it.status, it.reason = "dropped", f"error: {type(e).__name__}: {e}"[:120]
    it.secs = round(time.monotonic() - t0, 1)
    return it


def _process(it: Item, names, company_domains, fetch_images):
    url, method = it.url, it.resolve_method
    if not method:
        url, method = resolve(it.link)
        it.resolve_method = method
    if not url:
        it.reason = f"unresolved ({method})"
        return
    url = clean_url(url)
    if is_homepage(url):
        it.reason = "resolved to a homepage"
        return
    tier, why = classify_reason(url, company_domains)
    if not tier:
        it.url, it.reason = url, f"source: {why}"
        return
    it.url, it.tier = url, tier
    r = http(url)
    if r.status == 0 or r.status >= 500:          # one retry for transient failures
        time.sleep(1)
        r = http(url)
    blocked = page_blocked(r)
    info = PageInfo()
    if not blocked:
        info = parse_page(r.text(), r.url)
        canon = clean_url(info.canonical) if info.canonical else ""
        if canon and not is_homepage(canon) and classify_reason(canon, company_domains)[0]:
            it.url, it.tier = canon, classify_reason(canon, company_domains)[0]
    if not (mentions(it.title, names) or mentions(info.title, names) or mentions(info.description, names)):
        it.reason = "not about " + " / ".join(names[:1])
        return
    it.publisher = it.source or info.site_name or host_of(it.url)
    if not it.date and info.published:
        try:
            it.date = date.fromisoformat(info.published[:10])
        except ValueError:
            pass
    it.image_url = info.image
    if blocked:
        it.image_note = f"page blocked ({blocked})"
    elif not info.image:
        it.image_note = "no image declared"
    else:
        # first candidate that actually downloads as a real image (max 3 tries)
        notes = []
        for cand in info.images[:3]:
            rel, note = download_image(cand, it.url, save=fetch_images)
            if rel:
                it.image_url, it.image_ok = cand, True
                it.image_local_path = rel if fetch_images else ""
                break
            notes.append(note)
        it.image_note = "" if it.image_ok else "; ".join(notes)
        # keep the remote URL only when we were merely refused (a browser may still load it);
        # a 404 / non-image answer means the declared image is broken -> store no image
        if not it.image_ok and not any(re.search(r"http (0|401|403|429)$", n) for n in notes):
            it.image_url = ""
    it.status, it.reason = "kept", ""


def queries_for(name: str, product: str = "", rng: tuple[date, date] | None = None) -> list[str]:
    ops = f" {date_ops(rng)}" if rng else ""
    if product:
        qs = [f'"{product}" "{name}" defence OR defense', f'"{product}" {name}', f'"{product}"']
    else:
        qs = [f'"{name}" defence OR defense', f'"{name}"']
    return [q + ops for q in qs]


def collect(name: str, aliases=(), product: str = "", company_domains=(), limit=10,
            fetch_images=True, workers=WORKERS, rng: tuple[date, date] | None = None) -> list[Item]:
    """Search, resolve and filter news for a company (or one of its products) in `rng`."""
    rng = rng or date_range()
    names = [product] if product else [name, *aliases]
    domains = list(company_domains)
    seen_links, seen_urls, seen_heads = set(), set(), set()
    results: list[Item] = []
    kept = 0
    for q in queries_for(name, product, rng):
        cands = []
        for raw in rss_search(q):
            if raw["link"] in seen_links or not raw["title"]:
                continue
            seen_links.add(raw["link"])
            it = Item(**raw, query=q)
            if not in_range(raw["date"], rng):      # the date range is enforced here, not only by the query
                it.reason = f"outside date range ({raw['date']})"
                results.append(it)
                continue
            # the RSS publisher is the company itself (or its parent group: "Hanwha" for
            # "Hanwha Aerospace") -> its domain counts as a company domain
            src_key = name_key(raw["source"])
            if raw["source_url"] and src_key and any(
                    k == src_key or k.startswith(src_key + " ") for k in (name_key(n) for n in [name, *aliases])):
                domains.append(host_of(raw["source_url"]))
            # cheap pre-filters before any network work: publisher domain and headline
            tier, why = classify_reason(raw["source_url"] or "", domains) if raw["source_url"] else (None, "")
            if raw["source_url"] and not tier:
                it.reason = f"source: {why} (publisher {host_of(raw['source_url'])})"
                results.append(it)
                continue
            hk = norm(it.title)
            if hk in seen_heads:
                it.reason = "duplicate headline"
                results.append(it)
                continue
            seen_heads.add(hk)
            cands.append(it)
        # headlines that already name the subject first; the rest only if still short
        cands.sort(key=lambda i: not mentions(i.title, names))
        # process in waves of ~1.25x what is still missing, so few pages are fetched in vain
        while cands and kept < limit:
            budget = int((limit - kept) * 1.25) + 1
            todo, cands = cands[:budget], cands[budget:]
            resolved = resolve_many([i.link for i in todo], workers)
            for i in todo:
                i.url, i.resolve_method = resolved.get(i.link, ("", "unresolved"))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                done = list(ex.map(lambda i: process(i, names, domains, fetch_images), todo))
            for it in done:
                if it.status == "kept":
                    if not in_range(it.date, rng):
                        it.status, it.reason = "dropped", f"outside date range ({it.date})"
                    elif it.url in seen_urls or kept >= limit:
                        it.status, it.reason = "dropped", ("duplicate url" if it.url in seen_urls else "over limit")
                    else:
                        seen_urls.add(it.url)
                        kept += 1
            results += done
        for it in cands:
            it.reason = "over limit (not processed)"
        results += cands
        if kept >= limit:
            break
    return results


# ----------------------------------------------------------------------------- DB (staging only)

def _connect(serving=False):
    """Writes always go to the staging DB; only the live GET (serving=True) reads the serving DB."""
    import psycopg2
    name = "KSSL_SERVING_DSN" if serving else "KSSL_STAGING_DSN"
    dsn = (os.getenv(name) or os.getenv("KSSL_DSN") or "").strip()
    if not dsn:
        raise RuntimeError(f"{name} (or KSSL_DSN) is not set")
    return psycopg2.connect(dsn, connect_timeout=5)


def row_id(url: str, owner_id: str) -> str:
    """Deterministic id: uuid5(url | competitor_id) for articles, (url | product_id) for product news."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}|{owner_id}"))


NEAR_COPY = 0.85            # headline similarity (difflib ratio of norm()) that makes two candidates one story
NEAR_DAYS = 3


def near_copy(a: str, b: str) -> bool:
    """Obvious copies only (one word changed, a publisher suffix); real rewordings are left to the prompt run."""
    a, b = norm(a), norm(b)
    return bool(a and b) and SequenceMatcher(None, a, b).ratio() >= NEAR_COPY


def pre_group_of(headline: str, day, peers) -> str | None:
    """peers = [(candidate_id, headline, published_date, pre_group)] of the same owner, oldest first.
    -> the id of the first near-copy within +-NEAR_DAYS days (its own group root if it has one), else None."""
    if day is None:
        return None
    for cid, h, d, pg in peers:
        if d is not None and abs((d - day).days) <= NEAR_DAYS and near_copy(headline, h):
            return pg or cid
    return None


def _peers(cur, competitor_id: str, product_id: str | None) -> list:
    cur.execute("SELECT candidate_id::text, headline, published_date, pre_group::text FROM staging.news_candidate "
                "WHERE competitor_id = %s AND product_id IS NOT DISTINCT FROM %s ORDER BY found_at, candidate_id",
                (competitor_id, product_id))
    return cur.fetchall()


def save(cur, items: list[Item], competitor_id: str, product_id: str | None = None) -> tuple[int, list[str]]:
    """Insert kept items as candidates (unique per owner + url; a known url is left untouched). Each row in its
    own savepoint so one failure doesn't sink the run. Returns (candidates written, errors)."""
    owner = product_id or competitor_id
    peers = _peers(cur, competitor_id, product_id)
    n, errors = 0, []
    for it in items:
        if it.status != "kept":
            continue
        cid = row_id(it.url, owner)
        publisher = (it.publisher or None) and it.publisher[:200]
        pg = pre_group_of(it.title, it.date, peers)
        cur.execute("SAVEPOINT news_row")
        try:
            cur.execute("INSERT INTO staging.news_candidate (candidate_id, competitor_id, product_id, headline, article_url, "
                        "published_date, publisher, image_url, image_local_path, source_tier, pre_group) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                        (cid, competitor_id, product_id, it.title[:300], it.url, it.date, publisher, it.image_url or None,
                         it.image_local_path or None, it.tier, pg))
            if cur.rowcount:
                n += 1
                peers.append((cid, it.title, it.date, pg))
            else:
                it.reason = "already a candidate"
            cur.execute("RELEASE SAVEPOINT news_row")
        except Exception as e:  # noqa: BLE001
            cur.execute("ROLLBACK TO SAVEPOINT news_row")
            it.status, it.reason = "db-error", str(e).split("\n")[0][:120]
            errors.append(f"{it.url}: {it.reason}")
    return n, errors


def regroup(cur) -> int:
    """Set pre_group on every 'new' candidate that has none (oldest first, per owner). Returns rows changed."""
    cur.execute("SELECT candidate_id::text, competitor_id::text, product_id::text, headline, published_date, pre_group::text "
                "FROM staging.news_candidate WHERE status = 'new' ORDER BY found_at, candidate_id")
    seen: dict = {}
    n = 0
    for cid, comp, prod, h, d, pg in cur.fetchall():
        peers = seen.setdefault((comp, prod), [])
        if pg is None:
            pg = pre_group_of(h, d, peers)
            if pg:
                cur.execute("UPDATE staging.news_candidate SET pre_group = %s WHERE candidate_id = %s", (pg, cid))
                n += 1
        peers.append((cid, h, d, pg))
    return n


def _load_subjects(competitor_id: str, products: bool):
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT display_name, legal_name, short_name FROM staging.competitive_competitor "
                        "WHERE competitor_id = %s", (competitor_id,))
            row = cur.fetchone()
            if not row:
                raise LookupError(f"competitor {competitor_id} not found")
            name, legal, short = row
            aliases = []
            for a in (legal, short):
                if a and name_key(a) != name_key(name) and a not in aliases:
                    aliases.append(a)
            prods = []
            if products:
                cur.execute("SELECT product_id::text, product_name FROM staging.competitive_product "
                            "WHERE competitor_id = %s ORDER BY product_name", (competitor_id,))
                prods = cur.fetchall()
            return name, aliases, prods
    finally:
        conn.close()


def competitor_ids() -> list[str]:
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT competitor_id::text FROM staging.competitive_competitor ORDER BY display_name")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def refresh(competitor_id: str, products=False, limit=10, dry_run=False, rng=None,
            company_domains=(), log=None) -> dict:
    """Fetch and store news for one competitor (and optionally its products) inside `rng`."""
    t0 = time.monotonic()
    rng = rng or date_range()
    name, aliases, prods = _load_subjects(competitor_id, products)
    runs = []
    for kind, label, pid, product in [("company", name, None, "")] + [("product", pn, pi, pn) for pi, pn in prods]:
        t1 = time.monotonic()
        items = collect(name, aliases, product=product, company_domains=company_domains, limit=limit,
                        fetch_images=not dry_run, rng=rng)
        runs.append((kind, label, pid, items, round(time.monotonic() - t1, 1)))
    out = {"competitor_id": competitor_id, "name": name, "dry_run": dry_run, "runs": []}
    conn = None if dry_run else _connect()
    try:
        for kind, label, pid, items, secs in runs:
            saved, errors = 0, []
            if conn:
                with conn, conn.cursor() as cur:
                    saved, errors = save(cur, items, competitor_id, pid)
            out["runs"].append({"kind": kind, "name": label, "product_id": pid, "seconds": secs,
                                "seen": len(items), "kept": sum(i.status == "kept" for i in items), "saved": saved,
                                "errors": errors, "items": [_item_dict(i) for i in items]})
            if log:
                log(kind, label, items)
    finally:
        if conn:
            conn.close()
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


def _item_dict(i: Item) -> dict:
    return {"status": i.status, "reason": i.reason, "headline": i.title, "url": i.url,
            "publisher": i.publisher or i.source, "tier": i.tier, "date": str(i.date) if i.date else None,
            "image_url": i.image_url or None, "image_local_path": i.image_local_path or None,
            "image_note": i.image_note or None, "resolve": i.resolve_method}


def refresh_many(competitor_id: str, products=False, limit=10, dry_run=False, rng=None, company_domains=(), log=None):
    ids = competitor_ids() if competitor_id == "all" else [competitor_id]
    return [refresh(c, products, limit, dry_run, rng, company_domains, log) for c in ids]


# ----------------------------------------------------------------------------- API

def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False


@router.post("/api/news/refresh")
def api_refresh(competitor_id: str = "all", products: bool = False, limit: int = Query(10, ge=1, le=50),
                day: str | None = Query(None, alias="date"), from_: str | None = Query(None, alias="from"),
                to: str | None = None, dry_run: bool = False):
    """Fetch news for a competitor (or 'all') and store the kept items as staging.news_candidate rows (`saved` =
    new candidates; the prompt run `news` turns them into story rows). Returns counts + kept items."""
    if os.environ.get("KSSL_VIEW", "").strip().lower() != "review":   # the live site is public: no writes from it
        raise HTTPException(404, "news refresh exists only on the review backend")
    if competitor_id != "all" and not _is_uuid(competitor_id):
        raise HTTPException(400, "competitor_id must be a uuid or 'all'")
    try:
        rng = date_range(day, from_, to)
        results = refresh_many(competitor_id, products, limit, dry_run, rng)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from None
    kept = [(r["name"], run, i) for r in results for run in r["runs"] for i in run["items"] if i["status"] == "kept"]
    return {
        "range": {"from": rng[0].isoformat(), "to": rng[1].isoformat()},
        "dry_run": dry_run,
        "totals": {"competitors": len(results), "kept": len(kept),
                   "saved": sum(run["saved"] for r in results for run in r["runs"]),
                   "with_image": sum(bool(i["image_local_path"]) for _, _, i in kept)},
        "competitors": [{"competitor_id": r["competitor_id"], "name": r["name"], "seconds": r["seconds"],
                         "runs": [{k: run[k] for k in ("kind", "name", "kept", "saved", "errors")}
                                  for run in r["runs"]]} for r in results],
        "rows": [{"competitor": c, "kind": run["kind"], "subject": run["name"], "headline": i["headline"],
                  "date": i["date"], "url": i["url"], "publisher": i["publisher"], "tier": i["tier"],
                  "image_local_path": i["image_local_path"]} for c, run, i in kept],
    }


@router.get("/api/news")
def api_list(competitor_id: str | None = None, from_: str | None = Query(None, alias="from"),
             to: str | None = None, limit: int = Query(200, ge=1, le=1000)):
    """Stored articles from the DB the backend reads (KSSL_VIEW=review -> staging DB, else serving DB)."""
    review_view = os.environ.get("KSSL_VIEW", "").strip().lower() == "review"
    schema = "staging" if review_view else "serving"
    if competitor_id in ("", "all"):
        competitor_id = None
    if competitor_id and not _is_uuid(competitor_id):
        raise HTTPException(400, "competitor_id must be a uuid")
    try:
        start = _parse_day(from_, "from") if from_ else None
        end = _parse_day(to, "to") if to else None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    where, args = [], []
    for cond, val in (("{k} = %s::uuid", competitor_id), ("a.published_date >= %s", start), ("a.published_date <= %s", end)):
        if val:
            where.append(cond)
            args.append(val)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    fact = ("LEFT JOIN {s}.fact_source f ON f.table_name = '{t}' AND f.row_id = a.{i}::text "
            "AND f.column_name = 'image_local_path'")
    sql_a = (f"SELECT a.article_id::text, a.competitor_id::text, c.display_name, a.headline, a.published_date, "
             f"a.publisher, a.article_url, a.image_url, a.category, f.source_url, f.source_tier "
             f"FROM {schema}.competitive_news_article a "
             f"LEFT JOIN {schema}.competitive_competitor c ON c.competitor_id = a.competitor_id "
             + fact.format(s=schema, t="competitive_news_article", i="article_id")
             + " " + w.format(k="a.competitor_id") + " ORDER BY a.published_date DESC NULLS LAST, a.headline LIMIT %s")
    sql_p = (f"SELECT a.product_news_id::text, a.product_id::text, p.product_name, a.headline, a.published_date, "
             f"a.publisher, a.article_url, NULL, a.category, f.source_url, f.source_tier "
             f"FROM {schema}.competitive_product_news a "
             f"LEFT JOIN {schema}.competitive_product p ON p.product_id = a.product_id "
             + fact.format(s=schema, t="competitive_product_news", i="product_news_id")
             + " " + w.format(k="p.competitor_id") + " ORDER BY a.published_date DESC NULLS LAST, a.headline LIMIT %s")
    keys = ("id", "owner_id", "owner_name", "headline", "published_date", "publisher", "article_url",
            "image_url", "category", "image_local_path", "source_tier")
    try:
        conn = _connect(serving=not review_view)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from None
    try:
        with conn, conn.cursor() as cur:
            res = {}
            for label, sql in (("articles", sql_a), ("product_news", sql_p)):
                cur.execute(sql, (*args, limit))
                res[label] = [dict(zip(keys, (str(v) if isinstance(v, date) else v for v in r)))
                              for r in cur.fetchall()]
    finally:
        conn.close()
    return {"schema": schema, "from": str(start) if start else None, "to": str(end) if end else None, **res}


# ----------------------------------------------------------------------------- CLI

def print_table(kind, label, items: list[Item], file=sys.stdout):
    print(f"\n== {kind}: {label}", file=file)
    for i in items:
        if i.status == "kept":
            img = "img:saved" if i.image_local_path else ("img:ok" if i.image_ok else ("img:url" if i.image_url else "img:none"))
            note = f" ({i.image_note})" if i.image_note else ""
            print(f"  KEPT {i.tier[:4]:4} {img:9} {str(i.date or ''):10} {i.secs:4}s {i.url}{note}\n"
                  f"       {i.title[:110]}", file=file)
        else:
            print(f"  drop [{i.reason}] {i.url or i.source} | {i.title[:80]}", file=file)


def _selftest():
    from backend.sources import classify
    d = date(2026, 10, 16)
    # --- date range
    assert date_range("2026-10-01") == (date(2026, 10, 1), date(2026, 10, 1))
    assert date_range(frm="2026-09-01", to="2026-09-30") == (date(2026, 9, 1), date(2026, 9, 30))
    assert date_range(today=d) == (date(2026, 9, 17), d)                       # default: last 30 days incl. today
    assert date_range(frm="2026-10-01", today=d) == (date(2026, 10, 1), d)
    assert date_range(to="2026-09-30", today=d) == (date(2026, 9, 1), date(2026, 9, 30))
    for bad in (dict(day="2026-10-01", to="2026-10-02"), dict(frm="2026-10-02", to="2026-10-01"),
                dict(day="01/10/2026"), dict(frm="2026-13-01")):
        try:
            date_range(**bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass
    # --- query operators: before is exclusive (end + 1 day), also across month/year ends
    assert date_ops((date(2026, 9, 1), date(2026, 9, 30))) == "after:2026-09-01 before:2026-10-01"
    assert date_ops((date(2026, 12, 31), date(2026, 12, 31))) == "after:2026-12-31 before:2027-01-01"
    assert queries_for("Bharat Forge", "", (date(2026, 10, 1), date(2026, 10, 1)))[0] == \
        '"Bharat Forge" defence OR defense after:2026-10-01 before:2026-10-02'
    assert queries_for("L&T", "K9 Vajra-T", (d, d))[-1].startswith('"K9 Vajra-T" after:')
    # --- range filter is inclusive on both ends and rejects missing dates
    rng = (date(2026, 9, 1), date(2026, 9, 30))
    assert in_range(date(2026, 9, 1), rng) and in_range(date(2026, 9, 30), rng)
    assert not in_range(date(2026, 8, 31), rng) and not in_range(date(2026, 10, 1), rng) and not in_range(None, rng)
    # --- RSS parsing (source suffix stripped from the title, pubDate -> date)
    rss = (b'<rss><channel><item><title>Bharat Forge wins order - The Hindu</title>'
           b'<link>https://news.google.com/rss/articles/CBMiabc?oc=5</link>'
           b'<pubDate>Tue, 15 Sep 2026 23:30:00 GMT</pubDate>'
           b'<source url="https://www.thehindu.com">The Hindu</source></item>'
           b'<item><title>No date</title><link>https://x.test/a</link></item></channel></rss>')
    items = parse_rss(rss)
    assert items[0]["title"] == "Bharat Forge wins order" and items[0]["date"] == date(2026, 9, 15)
    assert items[0]["source"] == "The Hindu" and items[1]["date"] is None
    assert parse_rss(b"not xml") == []
    # --- ids, urls, relevance, source policy, page parsing
    assert row_id("https://a.test/x", "c1") == row_id("https://a.test/x", "c1") != row_id("https://a.test/x", "c2")
    assert clean_url("https://A.test/x/amp?utm_source=y&id=3#f") == "https://a.test/x?id=3"
    assert mentions("L&T unveils K-9 Vajra-T", ["K9 Vajra"]) and not mentions("Forging ahead", ["Bharat Forge"])
    assert classify("https://www.thehindu.com/x") == "independent" and classify("https://news.google.com/x") is None
    assert classify("https://www.reddit.com/r/x") is None
    pg = parse_page('<meta property="og:image" content="/i/a.jpg"><meta property="og:site_name" content="S">'
                    '<link rel="canonical" href="https://s.test/a">', "https://s.test/a?x=1")
    assert pg.image == "https://s.test/i/a.jpg" and pg.site_name == "S" and pg.canonical == "https://s.test/a"
    # --- pre-grouping: obvious copies only, same owner (peers), +-3 days
    assert near_copy("Adani Defence bags AK-203 ammunition order", "Adani Defence bags AK-203 ammunition orders")
    assert near_copy("Adani Defence wins Rs 500 crore Army order - ANI", "Adani Defence wins Rs 500 crore Army order")
    assert not near_copy("Adani bags AK-203 ammunition order", "Army signs deal with Adani Defence for 7.62 mm rounds")
    assert not near_copy("", "") and not near_copy("L&T wins order", "Hanwha unveils K9 upgrade")
    peers = [("a", "Adani bags AK-203 ammunition order", date(2026, 10, 1), None),
             ("b", "Adani bags AK-203 ammunition order!", date(2026, 10, 2), "a")]
    assert pre_group_of("Adani bags AK-203 ammunition order", date(2026, 10, 3), peers) == "a"      # root of the group, not "b"
    assert pre_group_of("Adani bags AK-203 ammunition order", date(2026, 10, 9), peers) is None     # too far apart
    assert pre_group_of("Adani bags AK-203 ammunition order", None, peers) is None
    assert pre_group_of("Something else entirely", date(2026, 10, 2), peers) is None
    print("selftest ok")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m backend.news", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--competitor", help="competitor uuid, or 'all'")
    g.add_argument("--name", help="TEST: search an ad-hoc company name (no DB read/write)")
    g.add_argument("--selftest", action="store_true", help="run the assert-based self-check (no network, no DB)")
    g.add_argument("--regroup", action="store_true", help="pre-group the existing 'new' candidates (one-off after a bulk move)")
    ap.add_argument("--alias", action="append", default=[], help="with --name: other names")
    ap.add_argument("--product", action="append", default=[], help="with --name: product name(s) to search")
    ap.add_argument("--products", action="store_true", help="with --competitor: also fetch news for its products")
    ap.add_argument("--domain", action="append", default=[], help="company's own domain(s) -> tier primary")
    ap.add_argument("--date", help="a single day, YYYY-MM-DD")
    ap.add_argument("--from", dest="frm", help="range start, YYYY-MM-DD (inclusive)")
    ap.add_argument("--to", help="range end, YYYY-MM-DD (inclusive)")
    ap.add_argument("--limit", type=int, default=10, help="max kept articles per company / product")
    ap.add_argument("--dry-run", action="store_true", help="don't write the DB or save images (images are still validated)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
        return 0
    if a.regroup:
        conn = _connect()
        with conn, conn.cursor() as cur:
            print(f"pre_group set on {regroup(cur)} candidates")
        conn.close()
        return 0
    if not (a.competitor or a.name):
        ap.error("one of --competitor / --name / --selftest / --regroup is required")
    try:
        rng = date_range(a.date, a.frm, a.to)
    except ValueError as e:
        ap.error(str(e))
    print(f"date range {rng[0]} .. {rng[1]}  ({date_ops(rng)})")

    if a.name:
        for prod in [""] + a.product:
            items = collect(a.name, a.alias, product=prod, company_domains=a.domain, limit=a.limit,
                            fetch_images=not a.dry_run, rng=rng)
            print_table("product" if prod else "company", prod or a.name, items)
        return 0

    for res in refresh_many(a.competitor, a.products, a.limit, a.dry_run, rng, a.domain, print_table):
        for r in res["runs"]:
            print(f"   {r['kind']} {r['name']}: seen {r['seen']}, kept {r['kept']}, candidates saved {r['saved']}, {r['seconds']}s"
                  + (f", errors {len(r['errors'])}: {r['errors'][:3]}" if r["errors"] else ""))
        print(f"   {res['name']}: {res['seconds']}s")
        if a.json:
            print(json.dumps(res, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
