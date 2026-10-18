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
The range is searched in 2-day windows (SLICE_DAYS; a window whose query returns the RSS cap of 100 is halved,
down to one day) and merged by link. Limit: a daily run (<= 2 days) keeps DAILY_LIMIT (20) articles per company /
product; a backfill has no limit; an explicit --limit always counts.

Names (db/news_aliases.csv, read by load_aliases / subject_for; the DB supplies display / legal / short name):
  search_name         the quoted name of the Google query; aliases: more accepted names (also searched, in one OR query)
  match_terms_needed  "alias: co-term / co-term | alias: ..." an alias that counts only with a co-term ("Hanwha" + Army)
  exclude_terms       phrases blanked out before matching (sister companies: "Hanwha Ocean", "L&T Finance")
  domains             the company's own sites: tier primary and never "not about" (match_via 'own site')
A product matches loosely ("K9 Vajra-T" ~ "K9 Vajra"). A page that only the page title / description / url names is
kept with match_via 'page' (the news prompt sees it). The client's own domains: backend/sources.py CLIENT_DOMAINS.

Where things go (no columns are added to ui/serving tables):
  * staging.news_candidate (db/setup/06_news_candidate.sql): candidate_id (= row_id(url, owner), the id
    the story row gets when this candidate is its main article), competitor_id / product_id (NULL =
    company news), headline, article_url, published_date, publisher, image_url, image_local_path
    (relative to the media dir, e.g. news/<sha1>.jpg), source_tier ("primary" | "independent"),
    pre_group, match_via, page_note, status 'new'. A URL already stored for the same owner is not re-added (status kept).
  * pre_group: code pre-grouping of obvious copies. A new candidate whose headline is >= 85% similar
    (near_copy) to an earlier candidate of the SAME owner within +-3 days points at it; the model
    run only has to group the rest.
  * staging.competitive_news_article / competitive_product_news and the fact_source rows (article_url,
    image_local_path, also_reported_by, category judgement) are written by prompts/news_merge.py,
    not here; `category` is filled by the prompt run, never invented by this job.

Connection: env KSSL_STAGING_DSN, falling back to KSSL_DSN. Writes go to schema `staging` only
(the GET reads KSSL_SERVING_DSN on the live backend).
Competitor names come from staging.competitive_competitor (display_name, legal_name, short_name) plus the aliases
file above; company domains come from the file, from the RSS publisher when it is the company itself, or --domain.

CLI:  python -m backend.news --competitor <uuid|all> [--products] [--date 2026-10-01 |
          --from 2026-09-01 --to 2026-09-30] [--limit N] [--dry-run]
      python -m backend.news --selftest
API:  POST /api/news/refresh (header X-KSSL-Write: 1)?competitor_id=<uuid|all>&products=true&date=... | &from=..&to=..&limit=..
      GET  /api/news?competitor_id=&from=&to=   (reads staging when KSSL_VIEW=review, else serving)
      python -m backend.news --regroup   (pre-group the existing 'new' candidates; one-off after a bulk move)
      python -m backend.news --renormalise   (https / desktop urls, headline suffixes, match_via of the 'new' candidates)

Stdlib only (urllib, html.parser, json, concurrent.futures) + psycopg2 + FastAPI (router).
"""

from __future__ import annotations

import argparse
import base64
import csv
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

from backend.sources import classify_reason, client_domains, desktop_host, hard_to_fetch, host_of, outlet_rank

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

def strip_publisher(title: str, source: str) -> str:
    """Drop a trailing " - PUBLISHER" from a headline; case-insensitive ("Chosunbiz" vs " - CHOSUNBIZ")."""
    title, source = (title or "").strip(), (source or "").strip()
    if source:
        suffix = " - " + source.lower()
        if title.lower().endswith(suffix) and len(title) > len(suffix):
            return title[: -len(suffix)].strip()
    return title


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
        title = strip_publisher(title, source)
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


class RssError(Exception):
    """Google News RSS refused / failed a search (after retries). A failed search is reported, never read as 'no news'."""


_rss_state = {"streak": 0}          # consecutive failed searches; Google answers 503 "Sorry..." when it rate-limits an IP
RSS_BLOCKED_STREAK = 8              # this many failures in a row: stop the run (refresh_many raises) instead of grinding on


def rss_search(query: str) -> list[dict]:
    """Google News RSS items for a query (max 100). 429 / 5xx are retried (2 s, 6 s; once only while Google keeps
    refusing); then RssError. Never returns [] for a failure."""
    url = f"https://news.google.com/rss/search?q={quote(query)}&{EDITION}"
    attempts = 1 if _rss_state["streak"] >= 3 else 3
    status = 0
    for attempt in range(attempts):
        r = http(url, headers={"Accept": "application/rss+xml,application/xml"})
        status = r.status
        if status == 200:
            _rss_state["streak"] = 0
            return parse_rss(r.body)
        if status not in (0, 429) and status < 500:
            break
        if attempt < attempts - 1:
            time.sleep(2 * 3 ** attempt)
    _rss_state["streak"] += 1
    raise RssError(f"http {status}")


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
    """Tracking parameters, fragment and /amp removed; https preferred; a mobile host (m.economictimes.com) becomes
    the desktop host (economictimes.indiatimes.com)."""
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    path = p.path
    if path.endswith("/amp") or path.endswith("/amp/"):
        path = path.rsplit("/amp", 1)[0] or "/"
    scheme = "https" if p.scheme.lower() == "http" else p.scheme.lower()
    netloc = p.netloc.lower()
    if scheme == "https" and "@" not in netloc:
        host, _, port = netloc.partition(":")
        netloc = desktop_host(host) + (":" + port if port and port != "443" else "")
    return urlunsplit((scheme, netloc, path, urlencode(q), ""))


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
                     r"emblem|default[-_]?(image|img|og|share)|fallback|no[-_]?image|og[-_]default|"
                     r"og[-_]?image|site[-_]?(image|banner)|share[-_]?(image|img))", re.I)
# generic site art that is the same on every page of a site (matched on the whole url, case-insensitive)
BAD_IMG_URLS = ("business-standard.com/assets/web-assets/images/business_standard",
                "thehindu.com/theme/images/",
                "/static/images/logo", "/assets/images/default", "/images/default-", "/default_thumbnail")


def bad_image(u: str) -> bool:
    """A logo / placeholder / site-wide banner, not an article picture."""
    name = urlsplit(u).path.rsplit("/", 1)[-1]
    low = u.lower()
    return name.lower().endswith(".svg") or bool(BAD_IMG.search(name)) or any(x in low for x in BAD_IMG_URLS)


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
            for key in ("datePublished", "dateCreated"):     # dateCreated: Joomla sites (armyrecognition) write no datePublished
                if not info.published and isinstance(o.get(key), str):
                    info.published = o[key]
            if not info.site_name and isinstance(o.get("publisher"), dict):
                info.site_name = o["publisher"].get("name") or ""
    cands += [[h, 0] for r, h in p.links if "image_src" in r]
    for u, w in cands:
        u = html.unescape(u.strip())
        if not ABS_OR_ROOT.match(u):      # "https:/x" or "www.x/..." are publisher typos
            continue
        u = urljoin(base, u)
        if bad_image(u) or 0 < w < 200 or u in info.images:
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


def _mask(t: str, mask) -> str:
    """Blank out whole-word phrases (an excluded sister company: "Hanwha Ocean") in a normalised, space-padded text."""
    for m in mask:
        k = norm(m)
        if k:
            t = re.sub(rf"(?<!\S){re.escape(k)}(?!\S)", " ", t)
    return t


def _has_name(t: str, compact: str, key: str) -> bool:
    if not key:
        return False
    if f" {key} " in t:
        return True
    # "K9 Vajra" vs "K-9 Vajra-T": compare without spaces, only for distinctive names
    ck = key.replace(" ", "")
    return bool((any(c.isdigit() for c in ck) or len(ck) >= 8) and ck in compact)


def mentions(text: str, names, cond=(), mask=()) -> bool:
    """Does `text` name the subject?  names: always accepted (whole words, suffixes like Ltd/Group ignored);
    cond: [(alias, [co-terms])] accepted only when the text also holds one of the co-terms ("Hanwha" + "Army");
    mask: phrases removed first (sister companies that share the name: "Hanwha Ocean")."""
    t = _mask(" " + norm(text) + " ", mask)
    compact = t.replace(" ", "")
    if any(_has_name(t, compact, name_key(n)) for n in names):
        return True
    for alias, terms in cond:
        if _has_name(t, compact, name_key(alias)):
            for term in terms:
                k = norm(term)
                if k and (f" {k} " in t or f" {k}s " in t):
                    return True
    return False


def url_text(url: str) -> str:
    """Words of a url's path ("/hanwha-wins-us-army-mtc-contract" -> "hanwha wins us army mtc contract")."""
    try:
        path = urlsplit(url or "").path
    except ValueError:
        return ""
    return re.sub(r"[-_/+.]+", " ", path).strip()


_VARIANT_TAIL = re.compile(r"^(mk\d*|i{1,3}|iv|vi{0,3}|v\d+|a\d|er|block|ver\d*)$")


def product_names(product: str) -> list[str]:
    """The product name and its looser forms: a trailing variant letter / mark is optional, so "K9 Vajra-T" also
    matches "K9 Vajra" (and "K-9 Vajra"). A form must stay distinctive (two words, a digit, or 6+ letters)."""
    out = [product]
    toks = norm(product).split()
    while len(toks) > 1 and (len(toks[-1]) <= 2 or _VARIANT_TAIL.match(toks[-1])):
        toks.pop()
        cand = " ".join(toks)
        if len(cand) >= 4 and (len(toks) >= 2 or any(c.isdigit() for c in cand) or len(cand) >= 6):
            out.append(cand)
    return list(dict.fromkeys(out))


def _split(s: str, sep: str = " | ") -> list[str]:
    return [x.strip() for x in (s or "").split(sep) if x.strip()]


def _parse_cond(s: str) -> list[tuple[str, list[str]]]:
    """"Hanwha: Aerospace / K9 / Army | KMW: Leopard / tank" -> [("Hanwha", [...]), ("KMW", [...])]"""
    out = []
    for seg in _split(s):
        alias, _, terms = seg.partition(":")
        terms = [t.strip() for t in terms.split("/") if t.strip()]
        if alias.strip() and terms:
            out.append((alias.strip(), terms))
    return out


def query_aliases(search: str, aliases) -> list[str]:
    """Aliases worth their own search: not already covered by the search name or another alias (a quoted phrase
    "Adani Defence" also finds "Adani Defence & Aerospace")."""
    out: list[str] = []
    for a in aliases:
        ka = name_key(a)
        if not ka or any(ka == k or ka.startswith(k + " ") for k in [name_key(search), *map(name_key, out)]):
            continue
        out = [x for x in out if not name_key(x).startswith(ka + " ")]
        out.append(a)
    return out


@dataclass
class Subject:
    """Who a news search is about: the name to search, every accepted name, the conditional names and the masks."""
    search: str                                           # the quoted name used in the Google query
    names: list = field(default_factory=list)             # accepted names
    cond: list = field(default_factory=list)              # [(alias, [co-terms])]: accepted only with a co-term
    mask: list = field(default_factory=list)              # phrases blanked out before matching
    domains: list = field(default_factory=list)           # the company's own domains (tier primary)
    aliases: list = field(default_factory=list)           # extra names to search (unconditional)
    display: str = ""
    competitor_id: str = ""
    product: str = ""

    def hit(self, text: str) -> bool:
        return mentions(text, self.names, self.cond, self.mask)

    def matches(self, headline: str, *page_texts: str) -> str:
        """"headline" when the headline names the subject, "page" when only the page title / description / url do
        (the conditional names may also be completed by the other texts), else ""."""
        if self.hit(headline):
            return "headline"
        texts = [t for t in page_texts if t]
        if any(self.hit(t) for t in texts) or self.hit(" . ".join([headline or "", *texts])):
            return "page"
        return ""

    def company_names(self) -> list[str]:
        return [*self.names, *(a for a, _ in self.cond)]

    def for_product(self, product: str) -> "Subject":
        return Subject(search=self.search, names=product_names(product), domains=self.domains, display=self.display,
                       competitor_id=self.competitor_id, product=product)


ALIASES_FILE = Path(os.getenv("KSSL_NEWS_ALIASES", Path(__file__).resolve().parent.parent / "db" / "news_aliases.csv"))
_alias_rows: dict | None = None


def load_aliases(path=None, fresh=False) -> dict[str, dict]:
    """db/news_aliases.csv -> {competitor_id: row} (search_name, aliases, match_terms_needed, exclude_terms, domains ...)."""
    global _alias_rows
    if path is None and _alias_rows is not None and not fresh:
        return _alias_rows
    try:
        with open(path or ALIASES_FILE, encoding="utf-8", newline="") as f:
            rows = {r["competitor_id"].strip(): r for r in csv.DictReader(f) if (r.get("competitor_id") or "").strip()}
    except OSError:
        rows = {}
    if path is None:
        _alias_rows = rows
    return rows


def subject_for(competitor_id: str, display_name: str, legal_name: str = "", short_name: str = "", rows=None) -> Subject:
    """The Subject of a competitor: its aliases-file row (when it has one) plus the names stored in the DB."""
    row = (load_aliases() if rows is None else rows).get(str(competitor_id)) or {}
    search = (row.get("search_name") or "").strip() or display_name
    aliases = _split(row.get("aliases"))
    names: list[str] = []
    for n in (search, *aliases, display_name, legal_name, short_name):
        if n and name_key(n) and name_key(n) not in [name_key(x) for x in names]:
            names.append(n)
    cond = [(a, t) for a, t in _parse_cond(row.get("match_terms_needed")) if name_key(a) not in [name_key(x) for x in names]]
    return Subject(search=search, names=names, cond=cond, mask=_split(row.get("exclude_terms")),
                   domains=[d.lower() for d in _split(row.get("domains"))],
                   aliases=query_aliases(search, [*aliases, *[x for x in (legal_name, short_name) if x]]),
                   display=display_name, competitor_id=str(competitor_id))


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
    match_via: str = ""            # headline | page | own site: where the subject's name was found
    page_note: str = ""            # why the page could not be read (http 401 ...), "" = read
    status: str = "dropped"
    reason: str = ""
    secs: float = 0.0


def process(it: Item, subj: Subject, company_domains, fetch_images=True) -> Item:
    t0 = time.monotonic()
    try:
        _process(it, subj, company_domains, fetch_images)
    except Exception as e:  # one bad page must not stop the run
        it.status, it.reason = "dropped", f"error: {type(e).__name__}: {e}"[:120]
    it.secs = round(time.monotonic() - t0, 1)
    return it


def _process(it: Item, subj: Subject, company_domains, fetch_images):
    url, method = it.url, it.resolve_method
    if not method:
        url, method = resolve(it.link)
        it.resolve_method = method
    if not url:
        it.reason = f"unresolved ({method})"
        return
    raw_url = url
    url = clean_url(url)
    if is_homepage(url):
        it.reason = "resolved to a homepage"
        return
    tier, why = classify_reason(url, company_domains)
    if not tier:
        it.url, it.reason = url, f"source: {why}"
        return
    it.url, it.tier = url, tier
    own = why == "company domain"
    r = http(url)
    if r.status == 0 and raw_url.lower().startswith("http://") and url.startswith("https://"):
        r = http(raw_url)                                       # the site has no https: keep its http url
        if r.status:
            it.url = url = clean_url(raw_url).replace("https://", "http://", 1)
    if r.status == 0 or r.status >= 500:          # one retry for transient failures
        time.sleep(1)
        r = http(url)
    blocked = page_blocked(r)
    it.page_note = blocked
    info = PageInfo()
    if not blocked:
        info = parse_page(r.text(), r.url)
        canon = clean_url(info.canonical) if info.canonical else ""
        if canon and not is_homepage(canon):
            ctier, cwhy = classify_reason(canon, company_domains)
            if ctier:
                it.url, it.tier, own = canon, ctier, cwhy == "company domain"
    if own:                                       # the company's own site: always about the company
        it.match_via = "own site"
    else:
        it.match_via = subj.matches(it.title, info.title, info.description, url_text(it.url))
        if not it.match_via:
            it.reason = "not about " + subj.search
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


def queries_for(name: str, product: str = "", rng: tuple[date, date] | None = None, aliases=(), cond=(),
                variants=(), lean: bool = False) -> list[str]:
    """Google News queries, in order of priority. Full set: the defence-qualified name, the bare name, the aliases
    in one OR query, the conditional aliases (with a defence word) in another. lean=True drops the defence-qualified
    query (NOT a subset of the bare name's results: measured 5-15% of allowlisted items come only from it, so the
    job does not use lean; kept for tests and quick probes).
    Products: the exact name, its looser forms (`variants`), and with the company name."""
    ops = f" {date_ops(rng)}" if rng else ""
    q = lambda names: "(" + " OR ".join(f'"{a}"' for a in names) + ")"
    if product:
        qs = [f'"{product}"'] if lean else [f'"{product}" "{name}" defence OR defense', f'"{product}" {name}', f'"{product}"']
        qs += [f'"{v}"' for v in variants if v != product]
    else:
        qs = [] if lean else [f'"{name}" defence OR defense']
        qs.append(f'"{name}"')
        if aliases:
            qs.append(q(aliases))
        if cond:
            qs.append(q([a for a, _ in cond]) + " (defence OR defense)")
    return [x + ops for x in qs]


SLICE_DAYS = 2                 # a backfill is searched in windows of this many days (the RSS cap is 100 items per query)
RSS_CAP = 100
DAILY_LIMIT = 20               # kept articles per company / product on a daily run; a backfill has no limit
WAVE = 60                      # articles resolved + read per round when there is no limit


def day_slices(rng: tuple[date, date], days: int = SLICE_DAYS) -> list[tuple[date, date]]:
    """Inclusive (start, end) windows of `days` days covering rng, oldest first."""
    out, d = [], rng[0]
    while d <= rng[1]:
        e = min(d + timedelta(days=days - 1), rng[1])
        out.append((d, e))
        d = e + timedelta(days=1)
    return out


def effective_limit(limit, rng: tuple[date, date]):
    """An explicit limit always counts; otherwise a daily run (<= SLICE_DAYS days) keeps DAILY_LIMIT, a backfill all."""
    if limit:
        return limit
    return DAILY_LIMIT if (rng[1] - rng[0]).days < SLICE_DAYS else None


def search_window(qfn, rng: tuple[date, date], deep: bool = False, errors: list | None = None) -> list[dict]:
    """RSS items for one window. A query that returns the cap (100) is not trusted: the window is halved (down to
    one day); a capped single day is searched once more with deep=True (qfn may then add queries)."""
    items, capped = [], False
    for q in qfn(rng, deep):
        try:
            got = rss_search(q)
        except RssError as e:                       # recorded, the other queries still run
            if errors is not None:
                errors.append(f"{e}: {q}")
            continue
        items += [{**g, "query": q} for g in got]
        capped = capped or len(got) >= RSS_CAP
    if capped:
        if rng[0] < rng[1]:
            mid = rng[0] + timedelta(days=(rng[1] - rng[0]).days // 2)
            return (items + search_window(qfn, (rng[0], mid), errors=errors)
                    + search_window(qfn, (mid + timedelta(days=1), rng[1]), errors=errors))
        if not deep:
            return items + search_window(qfn, rng, deep=True, errors=errors)
    return items


def collect(name: str, aliases=(), product: str = "", company_domains=(), limit=None,
            fetch_images=True, workers=WORKERS, rng: tuple[date, date] | None = None, spec: Subject | None = None,
            slice_days: int = SLICE_DAYS) -> list[Item]:
    """Search, resolve and filter news for a company (or one of its products) in `rng`.
    spec: the company's Subject (aliases file); without it only `name` + `aliases` count. limit None = everything
    (backfills); the range is searched in `slice_days`-day windows, merged by link."""
    rng = rng or date_range()
    spec = spec or Subject(search=name, names=[name, *aliases])
    subj = spec.for_product(product) if product else spec
    domains = [*spec.domains, *company_domains]
    company_names = [name_key(n) for n in spec.company_names()]
    pq = subj.names[1:] if product else []

    def qfn(r, deep):
        # the defence-qualified query is kept in every window: it finds 5-15% items the bare name does not (measured)
        return queries_for(name, product, r, aliases=spec.aliases, cond=spec.cond, variants=pq, lean=False)

    windows = day_slices(rng, slice_days)
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, len(windows))) as ex:
        raws = [x for chunk in ex.map(lambda w: search_window(qfn, w, errors=errors), windows) for x in chunk]
    seen_links, seen_urls, seen_heads = set(), set(), set()
    # a failed search is visible in the log and the counts, it is not "no news"
    results: list[Item] = [Item(title="(search failed)", link="", source="", source_url="", date=None,
                                reason=f"search failed: {e}"[:200]) for e in errors]
    cands = []
    for raw in raws:
        if raw["link"] in seen_links or not raw["title"]:
            continue
        seen_links.add(raw["link"])
        it = Item(**{k: v for k, v in raw.items()})
        if not in_range(raw["date"], rng):      # the date range is enforced here, not only by the query
            it.reason = f"outside date range ({raw['date']})"
            results.append(it)
            continue
        # the RSS publisher is the company itself (or its parent group: "Hanwha" for
        # "Hanwha Aerospace") -> its domain counts as a company domain
        src_key = name_key(raw["source"])
        if raw["source_url"] and src_key and any(k == src_key or k.startswith(src_key + " ") for k in company_names):
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
    cands.sort(key=lambda i: not subj.hit(i.title))
    kept = 0
    # process in waves (~1.25x what is still missing under a limit), so few pages are fetched in vain
    while cands and (limit is None or kept < limit):
        budget = WAVE if limit is None else int((limit - kept) * 1.25) + 1
        todo, cands = cands[:budget], cands[budget:]
        resolved = resolve_many([i.link for i in todo], workers)
        for i in todo:
            i.url, i.resolve_method = resolved.get(i.link, ("", "unresolved"))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            done = list(ex.map(lambda i: process(i, subj, domains, fetch_images), todo))
        for it in done:
            if it.status == "kept":
                if not in_range(it.date, rng):
                    it.status, it.reason = "dropped", f"outside date range ({it.date})"
                elif it.url in seen_urls or (limit is not None and kept >= limit):
                    it.status, it.reason = "dropped", ("duplicate url" if it.url in seen_urls else "over limit")
                else:
                    seen_urls.add(it.url)
                    kept += 1
        results += done
    for it in cands:
        it.reason = "over limit (not processed)"
    results += cands
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
                        "published_date, publisher, image_url, image_local_path, source_tier, pre_group, match_via, page_note) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                        (cid, competitor_id, product_id, it.title[:300], it.url, it.date, publisher, it.image_url or None,
                         it.image_local_path or None, it.tier, pg, it.match_via or None, it.page_note or None))
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


def renormalise(cur) -> dict:
    """One-off for the existing 'new' candidates (run before a re-merge): https + desktop host in article_url (the
    candidate id follows the url), " - PUBLISHER" off the headline, match_via from the headline. -> counts."""
    cur.execute("SELECT candidate_id::text, competitor_id::text, product_id::text, headline, article_url, publisher, "
                "match_via FROM staging.news_candidate WHERE status = 'new' ORDER BY found_at, candidate_id")
    rows = cur.fetchall()
    subjects: dict = {}
    n = {"url": 0, "headline": 0, "match_via": 0, "duplicates_removed": 0}
    for cid, comp, prod, head, url, pub, via in rows:
        if comp not in subjects:
            cur.execute("SELECT display_name, legal_name, short_name FROM staging.competitive_competitor WHERE competitor_id = %s", (comp,))
            subjects[comp] = subject_for(comp, *(x or "" for x in cur.fetchone()))
        subj = subjects[comp]
        if prod:
            cur.execute("SELECT product_name FROM staging.competitive_product WHERE product_id = %s", (prod,))
            subj = subj.for_product(cur.fetchone()[0])
        new_url, new_head = clean_url(url), strip_publisher(head, pub)
        new_via = via or ("own site" if classify_reason(new_url, subj.domains)[1] == "company domain"
                          else ("headline" if subj.hit(new_head) else "page"))
        new_id = row_id(new_url, prod or comp)
        if new_id != cid:
            cur.execute("SELECT 1 FROM staging.news_candidate WHERE candidate_id = %s", (new_id,))
            if cur.fetchone():                                    # the normalised url is already a candidate: drop this copy
                cur.execute("UPDATE staging.news_candidate SET pre_group = %s WHERE pre_group = %s", (new_id, cid))
                cur.execute("DELETE FROM staging.news_candidate WHERE candidate_id = %s", (cid,))
                n["duplicates_removed"] += 1
                continue
            cur.execute("UPDATE staging.news_candidate SET candidate_id = %s, article_url = %s WHERE candidate_id = %s",
                        (new_id, new_url, cid))
            cur.execute("UPDATE staging.news_candidate SET pre_group = %s WHERE pre_group = %s", (new_id, cid))
            n["url"] += 1
        if new_head != head:
            cur.execute("UPDATE staging.news_candidate SET headline = %s WHERE candidate_id = %s", (new_head, new_id))
            n["headline"] += 1
        if new_via != via:
            cur.execute("UPDATE staging.news_candidate SET match_via = %s WHERE candidate_id = %s", (new_via, new_id))
            n["match_via"] += 1
    return n


def load_subject(competitor_id: str, products: bool):
    """(Subject, [(product_id, product_name)]) of a competitor: names from staging.competitive_competitor, aliases,
    co-terms, masks and own domains from db/news_aliases.csv."""
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT display_name, legal_name, short_name FROM staging.competitive_competitor "
                        "WHERE competitor_id = %s", (competitor_id,))
            row = cur.fetchone()
            if not row:
                raise LookupError(f"competitor {competitor_id} not found")
            subj = subject_for(competitor_id, *(x or "" for x in row))
            prods = []
            if products:
                cur.execute("SELECT product_id::text, product_name FROM staging.competitive_product "
                            "WHERE competitor_id = %s ORDER BY product_name", (competitor_id,))
                prods = cur.fetchall()
            return subj, prods
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


def refresh(competitor_id: str, products=False, limit=None, dry_run=False, rng=None,
            company_domains=(), log=None) -> dict:
    """Fetch and store news for one competitor (and optionally its products) inside `rng`.
    limit None: a daily run keeps DAILY_LIMIT per company / product, a backfill has no limit."""
    t0 = time.monotonic()
    rng = rng or date_range()
    subj, prods = load_subject(competitor_id, products)
    name, limit = subj.display or subj.search, effective_limit(limit, rng)
    runs = []
    for kind, label, pid, product in [("company", name, None, "")] + [("product", pn, pi, pn) for pi, pn in prods]:
        t1 = time.monotonic()
        items = collect(subj.search, product=product, company_domains=company_domains, limit=limit,
                        fetch_images=not dry_run, rng=rng, spec=subj)
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
                                "search_failed": sum(i.reason.startswith("search failed") for i in items),
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
            "image_note": i.image_note or None, "resolve": i.resolve_method,
            "match_via": i.match_via or None, "page_note": i.page_note or None}


def refresh_many(competitor_id: str, products=False, limit=None, dry_run=False, rng=None, company_domains=(), log=None):
    ids = competitor_ids() if competitor_id == "all" else [competitor_id]
    out = []
    for c in ids:
        out.append(refresh(c, products, limit, dry_run, rng, company_domains, log))
        if _rss_state["streak"] >= RSS_BLOCKED_STREAK:
            raise RuntimeError(f"Google News is refusing searches (http 503 'Sorry...'): {_rss_state['streak']} in a row after "
                               f"{len(out)} competitor(s). Stop, wait (minutes to hours) and run the same range again; "
                               "candidates already saved are kept.")
    return out


# ----------------------------------------------------------------------------- API

def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False


@router.post("/api/news/refresh")
def api_refresh(competitor_id: str = "all", products: bool = False, limit: int | None = Query(None, ge=1, le=1000),
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
            print(f"  KEPT {i.tier[:4]:4} {img:9} {str(i.date or ''):10} {i.secs:4}s {i.match_via or '-':9} {i.url}{note}\n"
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
    assert classify("https://idrw.org/x/") is None and classify("https://www.ajaishukla.com/2016/x.html") is None     # blocked blogs
    assert classify("https://idrw.org/x/", ("idrw.org",)) is None
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
    # --- publisher suffix: case-insensitive; headline kept when it is only the suffix
    assert strip_publisher("Veland wins order - CHOSUNBIZ", "Chosunbiz") == "Veland wins order"
    assert strip_publisher("Veland wins order - The Hindu", "The Hindu") == "Veland wins order"
    assert strip_publisher("Veland wins order - Other Paper", "The Hindu") == "Veland wins order - Other Paper"
    assert strip_publisher("- CHOSUNBIZ", "Chosunbiz") == "- CHOSUNBIZ" and strip_publisher("", "x") == ""
    assert parse_rss(b"<rss><channel><item><title>Veland tank trial - ETINFRA</title><link>https://x.test/a</link>"
                     b"<source url='https://x.test'>EtInfra</source></item></channel></rss>")[0]["title"] == "Veland tank trial"
    # --- urls: https preferred, mobile host -> desktop host, tracking and amp removed
    assert clean_url("http://www.thehindu.com/x/y") == "https://www.thehindu.com/x/y"
    assert clean_url("https://m.economictimes.com/news/defence/x/articleshow/1.cms?utm_source=a") == \
        "https://economictimes.indiatimes.com/news/defence/x/articleshow/1.cms"
    assert clean_url("http://m.economictimes.com/a") == "https://economictimes.indiatimes.com/a"
    assert clean_url("https://m.unknown-site.test/a") == "https://m.unknown-site.test/a"
    # --- logos / site banners are never article pictures
    for bad in ("https://www.business-standard.com/assets/web-assets/images/Business_Standard_1_685x385.jpg",
                "https://www.thehindu.com/theme/images/og-image.png", "https://x.test/img/logo-big.jpg",
                "https://x.test/img/og_image.jpg", "https://x.test/a/placeholder.png", "https://x.test/a/site-banner.jpg"):
        assert bad_image(bad), bad
    for ok in ("https://image.x.test/12832814.jpg", "https://x.test/uploads/2026/10/howitzer-trial.jpg"):
        assert not bad_image(ok), ok
    assert parse_page('<meta property="og:image" content="/theme/images/og-image.png">'
                      '<meta name="twitter:image" content="https://x.test/i/real.jpg">', "https://x.test/a").image == "https://x.test/i/real.jpg"
    # --- aliases file -> Subject (fictional company): aliases, co-terms, masks, own domain
    rows = {"c1": {"search_name": "Veland", "aliases": "Veland Land Systems | VLS | Veland-Tarn",
                   "match_terms_needed": "Veland: Army / howitzer / Navy | Tarn: howitzer / tank",
                   "exclude_terms": "Veland Ocean | Veland Insurance | VLS Finance", "domains": "veland.test | veland-def.test"},
            "c2": {"search_name": "Orrin Dynamics", "aliases": "", "match_terms_needed": "", "exclude_terms": "", "domains": ""}}
    sv = subject_for("c1", "Veland Aerospace", "Veland Aerospace Co., Ltd.", "", rows)
    assert sv.search == "Veland" and sv.domains == ["veland.test", "veland-def.test"] and sv.mask[0] == "Veland Ocean"
    assert sv.cond == [("Tarn", ["howitzer", "tank"])]        # "Veland" is already an unconditional name (the search name), so it needs no co-term
    assert sv.hit("Veland Land Systems unveils turret") and sv.hit("VLS wins export order") and sv.hit("Veland-Tarn teaming signed")
    assert sv.hit("Veland opens a bakery") and sv.hit("Tarn howitzers delivered") and not sv.hit("Tarn opens a bakery")        # co-term, plural
    assert not sv.hit("Veland Ocean wins Army order") and not sv.hit("Veland Insurance shares rise; Army ties")   # masked sister companies
    assert sv.hit("Veland Ocean and Veland Land Systems sign MoU") and not sv.hit("VLS Finance posts profit")
    assert sv.matches("Veland Land Systems wins order") == "headline"
    assert sv.matches("Army picks howitzer", "Veland to build prototypes") == "page"                  # only the page names it
    assert sv.matches("Tarn picks", "Army buys a howitzer") == "page"                                  # co-term completed from the page
    assert sv.matches("Army picks howitzer", "Something else") == "" and sv.matches("", "") == ""
    assert sv.matches("Army selects a gun", "", "", url_text("https://x.test/news/veland-land-systems-wins-prototypes")) == "page"
    so = subject_for("c2", "Orrin Dynamics Group", rows=rows)
    assert so.hit("Orrin Dynamics Ltd results") and not so.hit("Orrin wins order") and so.cond == []
    zs = subject_for("unknown", "Zed Corp", "Zed Corporation Ltd", "", rows)                           # not in the file: the DB names only
    assert zs.search == "Zed Corp" and zs.hit("Zed Corporation Ltd results") and not zs.mask and not zs.domains
    # a conditional alias needs a co-term (fictional "Hexa" row)
    rows["c3"] = {"search_name": "Hexa Armour", "aliases": "", "match_terms_needed": "Hexa: Army / tank", "exclude_terms": "", "domains": ""}
    sh = subject_for("c3", "Hexa Armour", rows=rows)
    assert sh.hit("Hexa wins Army order") and not sh.hit("Hexa launches phone") and sh.hit("Hexa Armour launches phone")
    # queries: bare name, aliases in one OR query (an alias already covered by the search name is not repeated),
    # conditional aliases in another with a defence word
    assert query_aliases("Veland", ["Veland Land Systems", "VLS", "Veland-Tarn", "VLS Group"]) == ["VLS"]
    assert query_aliases("Adani Defence", ["Adani Defence & Aerospace", "Adani Defense", "Adani-Elbit", "Adani Elbit"]) == ["Adani Defense", "Adani-Elbit"]
    qs = queries_for("Veland", "", (d, d), aliases=["VLS", "Veland-Tarn"], cond=[("KMW", ["tank"])])
    assert qs[0] == '"Veland" defence OR defense after:2026-10-16 before:2026-10-17' and qs[1].startswith('"Veland" after:')
    assert qs[2].startswith('("VLS" OR "Veland-Tarn") after:') and qs[3].startswith('("KMW") (defence OR defense) after:')
    ql = queries_for("Veland", "", (d, d), aliases=["VLS"], lean=True)
    assert len(ql) == 2 and ql[0].startswith('"Veland" after:')                                   # lean: no defence-qualified query
    assert queries_for("Veland", "Zel-9 Falcon-T", (d, d), variants=["zel 9 falcon"], lean=True)[0].startswith('"Zel-9 Falcon-T" after:')
    # --- products: a trailing variant letter / mark is optional ("K9 Vajra-T" ~ "K9 Vajra")
    assert product_names("Zel-9 Falcon-T")[:2] == ["Zel-9 Falcon-T", "zel 9 falcon"]
    assert "pinaka" in product_names("Pinaka Mk-II") and product_names("AK-203") == ["AK-203"] and product_names("T-90") == ["T-90"]
    pn = product_names("Zel-9 Falcon-T")
    assert mentions("300 more Zel-9 Falcon ordered", pn) and mentions("Zel 9 Falcon-T trial", pn) and mentions("Zel9 Falcon fires", pn)
    assert not mentions("Falcon heavy launch", pn)
    # --- search windows: 2-day slices; a capped window is halved; limit only on a daily run
    assert day_slices((date(2026, 10, 1), date(2026, 10, 5))) == [(date(2026, 10, 1), date(2026, 10, 2)),
                                                                   (date(2026, 10, 3), date(2026, 10, 4)), (date(2026, 10, 5), date(2026, 10, 5))]
    assert day_slices((d, d)) == [(d, d)] and len(day_slices((date(2026, 1, 1), date(2026, 9, 30)))) == 137
    assert effective_limit(None, (d, d)) == DAILY_LIMIT and effective_limit(None, (d - timedelta(days=1), d)) == DAILY_LIMIT
    assert effective_limit(None, (d - timedelta(days=29), d)) is None and effective_limit(7, (d - timedelta(days=29), d)) == 7
    calls = []
    real_rss = rss_search
    try:
        def fake_rss(q):
            calls.append(q)
            n = RSS_CAP if "after:2026-10-01 before:2026-10-03" in q else 3
            return [{"title": "x", "link": f"l{len(calls)}-{i}", "source": "", "source_url": "", "date": d} for i in range(n)]
        globals()["rss_search"] = fake_rss
        qf = lambda r, deep: queries_for("Veland", "", r, lean=not deep)
        items = search_window(qf, (date(2026, 10, 1), date(2026, 10, 2)))
        assert len(calls) == 3 and len(items) == RSS_CAP + 3 + 3                 # capped 2-day window -> halved into two 1-day windows
        assert any("after:2026-10-01 before:2026-10-02" in c for c in calls) and any("after:2026-10-02 before:2026-10-03" in c for c in calls)
        calls.clear()
        search_window(qf, (date(2026, 10, 5), date(2026, 10, 6)))
        assert len(calls) == 1                                                 # not capped: one lean query
    finally:
        globals()["rss_search"] = real_rss
    # a failed search is an error that is reported, never an empty answer
    try:
        def failing_rss(q):
            raise RssError("http 503")
        globals()["rss_search"] = failing_rss
        errs: list = []
        assert search_window(qf, (date(2026, 10, 5), date(2026, 10, 6)), errors=errs) == [] and len(errs) == 1 and errs[0].startswith("http 503: ")
    finally:
        globals()["rss_search"] = real_rss
    real_http_rss, real_sleep = http, time.sleep
    try:
        sleeps: list = []
        globals()["http"] = lambda url, **k: Resp(503, url, {}, b"Sorry...")
        time.sleep = lambda x: sleeps.append(x)
        _rss_state["streak"] = 0
        try:
            rss_search('"x"')
            raise AssertionError("503 must raise")
        except RssError as e:
            assert str(e) == "http 503" and sleeps == [2, 6] and _rss_state["streak"] == 1
        _rss_state["streak"] = 3
        sleeps.clear()
        try:
            rss_search('"x"')
        except RssError:
            assert sleeps == []                                          # while Google keeps refusing: one try, no waiting
        globals()["http"] = lambda url, **k: Resp(200, url, {}, b"<rss><channel><item><title>t</title><link>https://x.test/a</link></item></channel></rss>")
        assert len(rss_search('"x"')) == 1 and _rss_state["streak"] == 0
    finally:
        time.sleep = real_sleep
        globals()["http"] = real_http_rss
        _rss_state["streak"] = 0
    # --- a company's own domain is primary and never "not about"; an outsider page must name the subject
    real_http, real_resolve, real_dl = http, resolve, download_image
    page = lambda title: Resp(200, "", {"content-type": "text/html"},
                              f'<html><head><meta property="og:title" content="{title}"></head><body>x</body></html>'.encode())
    try:
        globals()["http"] = lambda url, **k: Resp(200, url, {"content-type": "text/html"}, page("Sustainable Infrastructure Company").body)
        globals()["resolve"] = lambda link: (link, "direct")
        globals()["download_image"] = lambda *a, **k: ("", "image http 404")
        own = process(Item("Sustainable Infrastructure Company", "https://veland.test/news/a", "Veland", "", d), sv, sv.domains, False)
        assert own.status == "kept" and own.tier == "primary" and own.match_via == "own site", (own.status, own.reason)
        out = process(Item("Sustainable Infrastructure Company", "https://www.thehindu.com/a", "The Hindu", "", d), sv, sv.domains, False)
        assert out.status == "dropped" and out.reason.startswith("not about"), out.reason
        globals()["http"] = lambda url, **k: Resp(200, url, {"content-type": "text/html"}, page("Army picks Veland guns").body)
        pg = process(Item("Army picks guns", "https://www.thehindu.com/b", "The Hindu", "", d), sv, sv.domains, False)
        assert pg.status == "kept" and pg.match_via == "page" and pg.tier == "independent"
        globals()["http"] = lambda url, **k: Resp(401, url, {}, b"")
        bl = process(Item("Veland Land Systems wins order", "https://www.reuters.com/c", "Reuters", "", d), sv, sv.domains, False)
        assert bl.status == "kept" and bl.match_via == "headline" and bl.page_note == "http 401"
    finally:
        globals()["http"], globals()["resolve"], globals()["download_image"] = real_http, real_resolve, real_dl
    # --- the real aliases file: the seven default decisions (db/news_aliases_REVIEW.md, "Decisions")
    ar = load_aliases(fresh=True)
    assert len(ar) == 50 and all(r["search_name"] for r in ar.values())
    by_name = {r["display_name"]: subject_for(cid, r["display_name"], rows=ar) for cid, r in ar.items()}
    H = by_name["Hanwha Aerospace"]
    assert H.hit("Hanwha wins MTC contract") and H.hit("Hanwha's KAI review") and not H.hit("Hanwha plans a new office")      # 1 co-term
    assert not H.hit("Hanwha Ocean wins submarine order") and not H.hit("Hanwha Life posts profit")
    L = by_name["Larsen & Toubro"]
    assert L.hit("L&T to invest in Tamil Nadu") and L.hit("L&T bags order") and not L.cond                                      # 2 no co-term
    assert not L.hit("L&T Finance posts profit") and not L.hit("LTIMindtree wins deal") and L.search == "Larsen & Toubro"
    B = by_name["BrahMos Aerospace"]
    assert B.hit("BrahMos missile exports") and "BrahMos" in B.names                                                            # 3 accepted
    K, N = by_name["KNDS Germany"], by_name["Nexter (KNDS France)"]
    assert K.hit("KNDS plans IPO") and not N.hit("KNDS plans IPO") and N.hit("KNDS Leclerc upgrade")                           # 4 group-wide -> Germany
    assert by_name["IDV (Iveco Defence)"].competitor_id != by_name["Leonardo"].competitor_id                                  # 5 separate rows
    P, A = by_name["PLR Systems (IWI+Adani)"], by_name["Adani Defence & Aerospace"]
    assert P.hit("Adani-IWI rifles for the Army") and not A.hit("Adani-IWI rifles for the Army")                                  # 6
    assert A.hit("Adani-Elbit Hermes drones delivered") and not P.hit("Adani-Elbit Hermes drones delivered")
    assert A.hit("Adani Defence wins order") and not A.hit("Adani Ports profit rises")
    R = by_name["RTX (Raytheon)"]
    assert R.search == "Raytheon" and R.hit("Raytheon wins Patriot order") and not R.hit("Collins Aerospace wins seats contract") \
        and not R.hit("Pratt & Whitney GTF engine issue") and not R.hit("RTX GeForce launch")                                  # 7
    assert "hanwha.com" in H.domains and "larsentoubro.com" in L.domains and "adanidefence.com" in A.domains
    # JSON-LD dateCreated when there is no datePublished (armyrecognition)
    assert parse_page('<script type="application/ld+json">{"@type":"NewsArticle","dateCreated":"2026-08-09T10:00:00Z"}</script>',
                      "https://z.test/a").published.startswith("2026-08-09")
    print("selftest ok")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m backend.news", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--competitor", help="competitor uuid, or 'all'")
    g.add_argument("--name", help="TEST: search an ad-hoc company name (no DB read/write)")
    g.add_argument("--selftest", action="store_true", help="run the assert-based self-check (no network, no DB)")
    g.add_argument("--regroup", action="store_true", help="pre-group the existing 'new' candidates (one-off after a bulk move)")
    g.add_argument("--renormalise", action="store_true", help="https / desktop urls, headline suffixes and match_via of the existing 'new' candidates (one-off before a re-merge)")
    ap.add_argument("--alias", action="append", default=[], help="with --name: other names")
    ap.add_argument("--product", action="append", default=[], help="with --name: product name(s) to search")
    ap.add_argument("--products", action="store_true", help="with --competitor: also fetch news for its products")
    ap.add_argument("--domain", action="append", default=[], help="company's own domain(s) -> tier primary")
    ap.add_argument("--client", action="store_true", help="with --name: the subject is the client, so kssl.in / bharatforge.com / kalyanigroup.com are primary")
    ap.add_argument("--date", help="a single day, YYYY-MM-DD")
    ap.add_argument("--from", dest="frm", help="range start, YYYY-MM-DD (inclusive)")
    ap.add_argument("--to", help="range end, YYYY-MM-DD (inclusive)")
    ap.add_argument("--limit", type=int, default=None,
                    help=f"max kept articles per company / product. Default: {DAILY_LIMIT} on a daily run (<= {SLICE_DAYS} days), "
                         "none for a backfill")
    ap.add_argument("--dry-run", action="store_true", help="don't write the DB or save images (images are still validated)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
        return 0
    if a.renormalise:
        conn = _connect()
        with conn, conn.cursor() as cur:
            print("renormalised:", renormalise(cur))
        conn.close()
        return 0
    if a.regroup:
        conn = _connect()
        with conn, conn.cursor() as cur:
            print(f"pre_group set on {regroup(cur)} candidates")
        conn.close()
        return 0
    if not (a.competitor or a.name):
        ap.error("one of --competitor / --name / --selftest / --regroup / --renormalise is required")
    try:
        rng = date_range(a.date, a.frm, a.to)
    except ValueError as e:
        ap.error(str(e))
    print(f"date range {rng[0]} .. {rng[1]}  ({date_ops(rng)})")

    if a.name:
        doms = [*a.domain, *(client_domains() if a.client else ())]
        for prod in [""] + a.product:
            items = collect(a.name, a.alias, product=prod, company_domains=doms, limit=effective_limit(a.limit, rng),
                            fetch_images=not a.dry_run, rng=rng)
            print_table("product" if prod else "company", prod or a.name, items)
        return 0

    for res in refresh_many(a.competitor, a.products, a.limit, a.dry_run, rng, a.domain, print_table):
        for r in res["runs"]:
            print(f"   {r['kind']} {r['name']}: seen {r['seen']}, kept {r['kept']}, candidates saved {r['saved']}, {r['seconds']}s"
                  + (f", SEARCHES FAILED {r['search_failed']} (Google refused: not 'no news', run again)" if r.get("search_failed") else "")
                  + (f", errors {len(r['errors'])}: {r['errors'][:3]}" if r["errors"] else ""))
        print(f"   {res['name']}: {res['seconds']}s")
        if a.json:
            print(json.dumps(res, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
