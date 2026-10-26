"""More news sources and partner-focused queries -> staging.news_candidate (free, no model).

    python -m backend.news_sources --selftest
    python -m backend.news_sources --source bing|gdelt|dc|google --kind partner,pair,geo[,company] [--competitor NAME|all]
                                   [--from 2026-01-25 --to 2026-10-26] [--max-queries N] [--dry-run]
    python -m backend.news_sources --source google --kind partner,pair,geo --export-jobs jobs.json      (a worker on another host)
    python -m backend.news_sources --job-file jobs.json --to-file out.jsonl                             (that host: no DB needed)
    python -m backend.news_sources --load-file out.jsonl                                                (back here: saved like the rest)
    python -m backend.news_sources --report

Owner 2026-10-26: find partner / company links with every free source, in parallel, with several search runs.
Sources (each its own host, so they run side by side without sharing a rate limit):
  google  Google News RSS (backend/news.py: rss_search, the capped-window halving, wrapper links resolved to the exact URL)
  bing    Bing News RSS (www.bing.com/news/search?format=rss; robots.txt allows /news/search). The result link carries the
          article URL in its `url` parameter. NOTE: the feed's copyright line restricts the results to personal, non-commercial
          use in an RSS reader -- the owner decides whether Bing-found candidates may be kept (news_candidate_origin.source='bing').
  gdelt   GDELT DOC 2.0 API (api.gdeltproject.org, artlist JSON). Its limit: one request every 5 seconds -- kept (GAP_GDELT).
  dc      the data-centre corpus (2.38M crawled pages) by title: trigram index on public.documents.title, read-only.
  wpsearch  the search feeds of 10 WordPress trade-press sites (WP_SEARCH_SITES, robots.txt checked per site): company and
          partner words only (WordPress needs every word to match)
Query types:
  company  "<company>"                                   (thin competitors by default; Google's company runs live in news.py)
  partner  "<company>" + joint venture / MoU / memorandum of understanding / teaming agreement / partnership / licence
           agreement / license agreement / technology transfer / subcontract / supplier / acquires / stake
  pair     "<company>" "<other company>" for every candidate pair of backend/candidate_finder.py still without a
           partnership row (staging.harvest_candidate search_status 'pending'; an unordered pair is searched once)
  geo      "<company>" "<country>" contract / order / delivery, for every country candidate_finder saw with that company
  product  (Google only) the targeted base systems of backend/product_targets.py, saved under the product -- the same queries
           and relevance check as `news.py --product-targets`, for a worker on another host
Every result goes through the SAME path as Google News company news (backend/news.py process / save): the exact article
URL, the source policy (backend/sources.py allowlist + blocklist), the relevance check (the headline or the page must name the
competitor), date inside the range, and staging.news_candidate (unique per owner + url). Each NEW candidate also gets a row in
staging.news_candidate_origin (source, query type, query) so the harvest can be counted per source and query type.
Politeness: at most 2 requests in flight per host (news.GATE), a gap between searches, back-off on 429 / 503, and a source stops
after repeated refusals (the rest of its queries stay for the next run). Local kssl_staging only.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from xml.etree import ElementTree

from backend import news

PARTNER_TERMS = ["joint venture", "MoU", "memorandum of understanding", "teaming agreement", "partnership", "licence agreement",
                 "license agreement", "technology transfer", "subcontract", "supplier", "acquires", "stake"]
GEO_WORDS = ["contract", "order", "delivery"]
GAP = {"bing": 2.0, "gdelt": 5.5, "google": 1.0, "dc": 0.0}
THIN_NEWS = 150                    # company queries by default only for competitors with fewer news candidates than this
WORKERS = 6
MAX_ITEMS_PER_QUERY = 60


# ----------------------------------------------------------------------------------------------- queries
def clean_other(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", name or "")).strip()


def queries_for(kind: str, subj, others=(), countries=()) -> list[tuple[str, dict]]:
    """[(kind, spec)]: spec = {"name", "terms" | "other" | "country"} -- each source renders its own query string."""
    name = subj.search
    if kind == "company":
        return [("company", {"name": n}) for n in [name, *subj.aliases[:2]]]
    if kind == "partner":
        return [("partner", {"name": name, "term": t}) for t in PARTNER_TERMS]
    if kind == "pair":
        return [("pair", {"name": name, "other": clean_other(o)}) for o in others if clean_other(o)]
    if kind == "geo":
        return [("geo", {"name": name, "country": c}) for c in countries]
    raise ValueError(kind)


def render(source: str, spec: dict) -> str:
    """The query string of one source."""
    n = f'"{spec["name"]}"'
    if "term" in spec:
        return f'{n} "{spec["term"]}"' if source != "gdelt" else f'{n} "{spec["term"]}"'
    if "other" in spec:
        return f'{n} "{spec["other"]}"'
    if "country" in spec:
        c = f'"{spec["country"]}"' if " " in spec["country"] or source != "gdelt" else spec["country"]
        return f"{n} {c} (" + " OR ".join(GEO_WORDS) + ")"
    return n


def gdelt_partner_query(name: str) -> str:
    """GDELT refuses phrases that are too short ("MoU"): one OR query of the longer terms."""
    terms = [t for t in PARTNER_TERMS if len(t) >= 5]
    return f'"{name}" (' + " OR ".join(f'"{t}"' if " " in t else t for t in terms) + ")"


# ----------------------------------------------------------------------------------------------- sources
class Refused(Exception):
    pass


_state = Counter()


def _get(host: str, url: str, headers=None, timeout=30) -> news.Resp:
    with news.GATE(host):
        r = news.http(url, headers=headers, timeout=timeout)
    refused = lambda r: r.status in (429, 503) or b"Please limit requests" in r.body[:200]   # noqa: E731
    # GDELT's one-request-per-5-s limit is per IP and shared with anything else on this machine: a few spaced retries;
    # Bing: one long pause
    waits = (8, 12, 20, 30) if host == "api.gdeltproject.org" else (60,)
    for w in waits:
        if not refused(r):
            break
        time.sleep(w)
        with news.GATE(host):
            r = news.http(url, headers=headers, timeout=timeout)
    if refused(r):
        _state[host] += 1
        raise Refused(f"{host}: http {r.status}")
    _state[host] = 0
    return r


def parse_bing(body: bytes) -> list[dict]:
    out = []
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return out
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        q = parse_qs(urlsplit(link).query)
        url = (q.get("url") or [""])[0] or link
        src = ""
        for ch in it:
            if ch.tag.endswith("Source"):
                src = (ch.text or "").strip()
        d = None
        try:
            from email.utils import parsedate_to_datetime
            d = parsedate_to_datetime(it.findtext("pubDate") or "").date()
        except (TypeError, ValueError):
            pass
        out.append({"title": (it.findtext("title") or "").strip(), "link": url, "url": url, "source": src, "source_url": url, "date": d})
    return out


def search_bing(q: str, rng) -> list[dict]:
    r = _get("www.bing.com", f"https://www.bing.com/news/search?q={quote(q)}&format=rss&count=100",
             headers={"Accept": "application/rss+xml,application/xml"})
    if r.status != 200:
        raise Refused(f"bing http {r.status}")
    return parse_bing(r.body)


def gdelt_slices(rng, monthly: bool) -> list[tuple[date, date]]:
    if not monthly:
        return [rng]
    out, d = [], rng[0]
    while d <= rng[1]:
        e = min(date(d.year + (d.month == 12), d.month % 12 + 1, 1) - timedelta(days=1), rng[1])
        out.append((d, e))
        d = e + timedelta(days=1)
    return out


def search_gdelt(q: str, rng, monthly=False) -> list[dict]:
    out = []
    for a, b in gdelt_slices(rng, monthly):
        params = {"query": q + " sourcelang:english", "mode": "artlist", "format": "json", "maxrecords": "250", "sort": "datedesc",
                  "startdatetime": a.strftime("%Y%m%d000000"), "enddatetime": b.strftime("%Y%m%d235959")}
        r = _get("api.gdeltproject.org", "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(params), timeout=60)
        time.sleep(GAP["gdelt"])
        if r.status != 200:
            raise Refused(f"gdelt http {r.status}")
        try:
            arts = json.loads(r.body).get("articles") or []
        except ValueError:                        # GDELT answers plain text for a query it does not accept
            arts = []
        for x in arts:
            d = None
            m = re.match(r"(\d{4})(\d{2})(\d{2})", x.get("seendate") or "")
            if m:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            out.append({"title": x.get("title") or "", "link": x.get("url") or "", "url": x.get("url") or "", "source": x.get("domain") or "",
                        "source_url": x.get("url") or "", "date": d})
    return out


def _like(s: str) -> str:
    return "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_dc(dc, spec: dict, rng) -> list[dict]:
    """Titles in the DC corpus naming the company and the term / other company / country (+ a deal word)."""
    must = [_like(spec["name"])]
    any_ = []
    if "term" in spec:
        # ILIKE is case-blind: "%MoU%" would match "Mounting" / "amount" -- an acronym needs its own word (and its case)
        any_ = [_like(spec["term"])] if spec["term"].lower() != "mou" else ["% MoU %", "% MoU,%", "% MoU:%", "% MoUs %", "%(MoU)%",
                                                                              "MoU %", "% MOU %", "MOU %"]
    elif "other" in spec:
        must.append(_like(spec["other"]))
    elif "country" in spec:
        must.append(_like(spec["country"]))
        any_ = [_like(w) for w in GEO_WORDS + ["deliver", "contract", "deal"]]
    op = "LIKE" if spec.get("term", "").lower() == "mou" else "ILIKE"
    sql = ("SELECT url, title, published_at, ingested_at FROM public.documents WHERE " + " AND ".join(["title ILIKE %s"] * len(must))
           + (f" AND title {op} ANY(%s)" if any_ else "") + " AND url IS NOT NULL AND (left(published_at, 10) >= %s OR "
           "(published_at IS NULL AND left(ingested_at, 10) >= %s)) ORDER BY published_at DESC NULLS LAST LIMIT 80")
    params = [*must] + ([any_] if any_ else []) + [rng[0].isoformat(), rng[0].isoformat()]
    cur = dc.cursor()
    cur.execute(sql, params)
    out = []
    for url, title, pub, ing in cur.fetchall():
        d = None
        try:
            d = date.fromisoformat((pub or "")[:10]) if pub else None
        except ValueError:
            pass
        if d is None:
            from backend.import_dc_corpus import url_years
            if any(y < rng[0].year for y in url_years(url)):
                continue                  # undated, but the url says it is older than the window (same guard as the DC importer)
        out.append({"title": title or "", "link": url, "url": url, "source": news.host_of(url), "source_url": url, "date": d})
    return out


# trade press on WordPress whose search has a feed (/?s=<words>&feed=rss2) and whose robots.txt allows it (probed 2026-10-26;
# defence-industry.eu, joint-forces.com, theprint.in, financialexpress.com, defense-aerospace.com, airandspaceforces.com disallow
# it; army- / naval- / airforce-technology.com answer 403; thedefensepost.com returns HTML)
WP_SEARCH_SITES = ("www.defenceweb.co.za", "www.edrmagazine.eu", "www.navalnews.com", "asianmilitaryreview.com", "defencesecurityasia.com",
                   "www.zona-militar.com", "bharatshakti.in", "euro-sd.com", "www.asiapacificdefencereporter.com",
                   "www.manufacturingtodayindia.com")
WP_TERMS = ("joint venture", "MoU", "partnership", "agreement", "teaming agreement", "technology transfer")
_robots: dict = {}


def wp_words(spec: dict) -> str:
    """WordPress search matches every word: the company name plus the term / other company / country."""
    extra = spec.get("term") or spec.get("other") or spec.get("country") or ""
    return f'{spec["name"]} {extra}'.strip()


def parse_feed_items(body: bytes) -> list[dict]:
    out = []
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return out
    for it in root.iter("item"):
        url = (it.findtext("link") or "").strip()
        d = None
        try:
            from email.utils import parsedate_to_datetime
            d = parsedate_to_datetime(it.findtext("pubDate") or "").date()
        except (TypeError, ValueError):
            pass
        if url:
            out.append({"title": (it.findtext("title") or "").strip(), "link": url, "url": url, "source": news.host_of(url),
                        "source_url": url, "date": d})
    return out


def search_wp(spec: dict, rng, pages: int = 1) -> list[dict]:
    """The same words on every WP_SEARCH_SITES site, sites side by side (one request in flight per site)."""
    from backend.harvest_sites import Robots

    def one(host):
        if host not in _robots:
            r = news.http(f"https://{host}/robots.txt", timeout=20)
            _robots[host] = Robots(r.body.decode("utf-8", "replace") if r.status == 200 else "")
        got = []
        for page in range(1, pages + 1):
            url = f"https://{host}/?s={quote(wp_words(spec))}&feed=rss2" + (f"&paged={page}" if page > 1 else "")
            if not _robots[host].allowed(url):
                return got
            try:
                r = _get(host, url, headers={"Accept": "application/rss+xml,application/xml"})
            except Refused:
                return got
            items = parse_feed_items(r.body) if r.status == 200 else []
            got += items
            if len(items) < 10 or (items and all(i["date"] and i["date"] < rng[0] for i in items)):
                break
        return got

    with ThreadPoolExecutor(max_workers=len(WP_SEARCH_SITES)) as ex:
        return [x for chunk in ex.map(one, WP_SEARCH_SITES) for x in chunk]


def search_google(q: str, rng) -> list[dict]:
    errors: list = []
    raws = news.search_window(lambda r, deep: [q + " " + news.date_ops(r)], rng, errors=errors)
    if errors and not raws:
        raise Refused("google: " + errors[0])
    return raws


# ----------------------------------------------------------------------------------------------- pipeline
def to_items(raws: list[dict], rng, domains, known: set, direct: bool, subj=None) -> list:
    """subj: the headline must name the competitor before the page is read (WordPress search matches words anywhere)."""
    seen, items = set(), []
    for raw in raws:
        key = raw.get("url") or raw.get("link")
        if not key or key in seen or not raw.get("title"):
            continue
        seen.add(key)
        if raw.get("date") and not news.in_range(raw["date"], rng):
            continue
        if subj is not None and not subj.hit(raw["title"]):
            continue
        if direct:
            u = news.clean_url(raw["url"])
            if u in known:
                continue
            tier, _ = news.classify_reason(u, domains)
            if not tier:
                continue
        elif raw.get("source_url"):
            tier, _ = news.classify_reason(raw["source_url"], domains)
            if not tier:
                continue
        it = news.Item(title=raw["title"], link=raw.get("link") or raw.get("url"), source=raw.get("source") or "",
                       source_url=raw.get("source_url") or "", date=raw.get("date"))
        if direct:
            it.url, it.resolve_method = raw["url"], "direct"
        items.append(it)
    return items[:MAX_ITEMS_PER_QUERY]


def process_items(items, subj, domains, fetch_images, known: set) -> list:
    todo = [i for i in items if not i.resolve_method]
    if todo:
        res = news.resolve_many([i.link for i in todo], 4)
        for i in todo:
            i.url, i.resolve_method = res.get(i.link, ("", "unresolved"))
    items = [i for i in items if i.url and news.clean_url(i.url) not in known]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        done = list(ex.map(lambda i: news.process(i, subj, domains, fetch_images), items))
    return [i for i in done if i.status == "kept"]


def run_jobs(jobs: list[dict], source: str, rng, fetch_images=True, emit=None, log=print, max_queries=None, dc=None) -> Counter:
    """jobs: [{competitor_id, subject, queries: [[kind, spec]], known: [urls]}]; emit(job, item, kind, query) for every kept item."""
    stats = Counter()
    n = 0
    for job in jobs:
        subj = news.Subject(**job["subject"])
        domains = list(subj.domains)
        known = set(job.get("known") or [])
        for kind, spec in job["queries"]:
            if max_queries and n >= max_queries:
                return stats
            n += 1
            if kind == "product":
                if source != "google":
                    continue
                st = run_product(job, spec, rng, fetch_images, emit, log)
                stats.update(st)
                if st.get("stopped"):
                    return stats
                continue
            if source == "wpsearch" and (kind not in ("company", "partner") or (kind == "partner" and spec["term"] not in WP_TERMS)):
                continue                               # WordPress search: company + a few partner terms (every word must match)
            q = (gdelt_partner_query(spec["name"]) if source == "gdelt" and kind == "partner" else
                 wp_words(spec) if source == "wpsearch" else render(source, spec))
            try:
                if source == "bing":
                    raws = search_bing(q, rng)
                    time.sleep(GAP["bing"])
                elif source == "gdelt":
                    raws = search_gdelt(q, rng, monthly=kind in ("partner", "company"))
                elif source == "dc":
                    raws = search_dc(dc, spec, rng)
                elif source == "wpsearch":
                    raws = search_wp(spec, rng, pages=3 if kind == "company" else 1)
                    time.sleep(1.0)
                else:
                    raws = search_google(q, rng)
                    time.sleep(GAP["google"])
            except Refused as e:
                stats["refused"] += 1
                log(f"  refused: {e}")
                if max(_state.values() or [0]) >= 3 or news._rss_state["streak"] >= news.RSS_BLOCKED_STREAK:
                    log(f"  {source}: refused repeatedly - stopping this source; the remaining queries stay for the next run")
                    stats["stopped"] = 1
                    return stats
                continue
            except Exception as e:              # a DC timeout / a broken answer: noted, the next query runs
                stats["errors"] += 1
                log(f"  error {type(e).__name__}: {str(e)[:120]} ({q})")
                if dc is not None:
                    try:
                        dc.rollback()
                    except Exception:
                        pass
                continue
            items = to_items(raws, rng, domains, known, direct=source in ("bing", "gdelt", "dc", "wpsearch"),
                             subj=subj if source == "wpsearch" else None)
            kept = process_items(items, subj, domains, fetch_images, known) if items else []
            stats["queries"] += 1
            stats["results"] += len(raws)
            stats["kept"] += len(kept)
            for it in kept:
                known.add(it.url)
                if emit:
                    emit(job, it, kind, q, spec)
            if kept or n % 25 == 0:
                log(f"  [{n}] {subj.display} {kind} {q[:80]!r}: {len(raws)} results, {len(items)} new allowlisted, {len(kept)} kept", flush=True)
    return stats


def run_product(job, spec, rng, fetch_images, emit, log) -> Counter:
    """A targeted product (backend/product_targets.py) on Google News: the queries of news.queries_for (company-qualified for an
    ordinary word / short code), the product's own relevance check, saved under the product (news_candidate.product_id)."""
    stats = Counter()
    subj = news.Subject(**job["subject"])
    psubj = subj.for_product(spec["product"])
    known = set((job.get("known_products") or {}).get(spec["product_id"]) or [])
    raws, failed = [], 0
    for q in news.queries_for(subj.search, spec["product"], None, variants=psubj.names[1:], qualified=spec.get("qualified", False)):
        try:
            raws += search_google(q, rng)
            time.sleep(GAP["google"])
        except Refused as e:
            failed += 1
            log(f"  refused: {e}")
    if failed and not raws and news._rss_state["streak"] >= news.RSS_BLOCKED_STREAK:
        stats["stopped"] = 1
        return stats
    items = to_items(raws, rng, list(subj.domains), known, direct=False)
    kept = process_items(items, psubj, list(subj.domains), fetch_images, known) if items else []
    stats["queries"] += 1
    stats["results"] += len(raws)
    stats["kept"] += len(kept)
    for it in kept:
        if emit:
            emit(job, it, "product", spec["product"], spec)
    if kept:
        log(f"  {subj.display} product {spec['product']!r}: {len(raws)} results, {len(items)} new allowlisted, {len(kept)} kept", flush=True)
    return stats


# ----------------------------------------------------------------------------------------------- DB side
def connect():
    import psycopg2
    return psycopg2.connect(os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging")


def build_jobs(cur, kinds, competitor="all", all_companies=False) -> list[dict]:
    cur.execute("SELECT c.competitor_id::text, c.display_name, coalesce(c.legal_name,''), coalesce(c.short_name,''), "
                "(SELECT count(*) FROM staging.news_candidate n WHERE n.competitor_id = c.competitor_id) "
                "FROM staging.competitive_competitor c ORDER BY 5, 2")
    comps = cur.fetchall()
    jobs = []
    pair_seen = set()
    targets_all = []
    if "product" in kinds:
        import psycopg2.extras
        from backend.product_targets import targets
        targets_all, _ = targets(cur.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor))
    for cid, disp, legal, short, n_news in comps:
        if competitor != "all" and competitor.lower() not in disp.lower():
            continue
        subj = news.subject_for(cid, disp, legal, short)
        qs = []
        for kind in kinds:
            if kind == "company":
                if all_companies or n_news < THIN_NEWS:
                    qs += queries_for("company", subj)
            elif kind == "partner":
                qs += queries_for("partner", subj)
            elif kind == "pair":
                cur.execute("""SELECT h.other_name, h.other_competitor_id::text, o.display_name FROM staging.harvest_candidate h
                               LEFT JOIN staging.competitive_competitor o ON o.competitor_id = h.other_competitor_id
                               WHERE h.kind = 'pair' AND h.competitor_id = %s AND h.search_status = 'pending'
                               ORDER BY h.doc_count DESC""", (cid,))
                others = []
                for other, ocid, odisp in cur.fetchall():
                    key = frozenset([cid, ocid or news.norm(other)])
                    if key in pair_seen:
                        continue
                    pair_seen.add(key)
                    if ocid:
                        other = news.subject_for(ocid, odisp).search
                    others.append(other)
                qs += queries_for("pair", subj, others=others)
            elif kind == "geo":
                cur.execute("SELECT country FROM staging.harvest_candidate WHERE kind = 'geo' AND competitor_id = %s ORDER BY doc_count DESC", (cid,))
                qs += queries_for("geo", subj, countries=[r[0] for r in cur.fetchall()])
            elif kind == "product":
                qs += [("product", {"name": subj.search, "product": r["search"], "product_id": r["product_id"], "qualified": r["qualified"]})
                       for r in targets_all if r["competitor_id"] == cid]
        if not qs:
            continue
        cur.execute("SELECT article_url FROM staging.news_candidate WHERE competitor_id = %s AND product_id IS NULL", (cid,))
        job = {"competitor_id": cid, "subject": dataclasses.asdict(subj), "queries": [[k, s] for k, s in qs],
               "known": [r[0] for r in cur.fetchall()]}
        if "product" in kinds:
            cur.execute("SELECT product_id::text, article_url FROM staging.news_candidate WHERE competitor_id = %s AND product_id IS NOT NULL", (cid,))
            kp: dict = {}
            for pid, u in cur.fetchall():
                kp.setdefault(pid, []).append(u)
            job["known_products"] = kp
        jobs.append(job)
    return jobs


class Saver:
    def __init__(self, source: str, dry_run=False):
        self.source, self.dry = source, dry_run
        self.conn = None if dry_run else connect()
        self.stats = Counter()

    def __call__(self, job, it, kind, query, spec=None):
        cid = job["competitor_id"]
        pid = (spec or {}).get("product_id")
        if self.dry:
            self.stats[(kind, "kept")] += 1
            return
        cand = news.row_id(it.url, pid or cid)
        with self.conn, self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM staging.news_candidate WHERE candidate_id = %s", (cand,))
            existed = cur.fetchone() is not None
            saved, errors = news.save(cur, [it], cid, pid)
            if saved and not existed:
                cur.execute("INSERT INTO staging.news_candidate_origin (candidate_id, source, query_type, query, competitor_id) "
                            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (cand, self.source, kind, query[:500], cid))
                self.stats[(kind, "new")] += 1
            else:
                self.stats[(kind, "known")] += 1

    def close(self):
        if self.conn:
            self.conn.close()


def item_to_json(job, it, kind, query, source, spec=None) -> str:
    d = dataclasses.asdict(it)
    d["date"] = it.date.isoformat() if isinstance(it.date, date) else it.date
    return json.dumps({"competitor_id": job["competitor_id"], "product_id": (spec or {}).get("product_id"), "kind": kind,
                       "query": query, "source": source, "item": d})


def load_file(path: str, dry_run=False) -> Counter:
    savers: dict[str, Saver] = {}
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            d = row["item"]
            if d.get("date"):
                try:
                    d["date"] = date.fromisoformat(str(d["date"])[:10])
                except ValueError:
                    d["date"] = None
            it = news.Item(**d)
            s = savers.setdefault(row["source"], Saver(row["source"], dry_run))
            s({"competitor_id": row["competitor_id"]}, it, row["kind"], row["query"], {"product_id": row.get("product_id")})
            n += 1
    out = Counter()
    for s in savers.values():
        out.update({f"{s.source}:{k[0]}:{k[1]}": v for k, v in s.stats.items()})
        s.close()
    out["lines"] = n
    return out


def report() -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT source, query_type, count(*) FROM staging.news_candidate_origin GROUP BY 1, 2 ORDER BY 1, 2")
    print("source   query_type  new candidates")
    for s, k, n in cur.fetchall():
        print(f"{s:8} {k:10} {n:8}")
    cur.execute("""SELECT c.display_name, count(*) FILTER (WHERE o.query_type = 'partner'), count(*) FILTER (WHERE o.query_type = 'pair'),
                          count(*) FILTER (WHERE o.query_type = 'geo'), count(*) FILTER (WHERE o.query_type = 'company')
                   FROM staging.competitive_competitor c LEFT JOIN staging.news_candidate_origin o USING (competitor_id) GROUP BY 1 ORDER BY 1""")
    print(f"\n{'competitor':36} partner  pair   geo  company")
    for r in cur.fetchall():
        print(f"{r[0]:36} {r[1]:7} {r[2]:5} {r[3]:5} {r[4]:8}")
    conn.close()


# ----------------------------------------------------------------------------------------------- selftest
def _selftest() -> None:
    subj = news.Subject(search="Nordvik Defence", names=["Nordvik Defence", "Nordvik"], aliases=["Nordvik"], display="Nordvik Defence",
                        competitor_id="c-1")
    qp = queries_for("partner", subj)
    assert len(qp) == len(PARTNER_TERMS) and render("bing", qp[0][1]) == '"Nordvik Defence" "joint venture"'
    g = gdelt_partner_query("Nordvik Defence")
    assert '"joint venture"' in g and "MoU" not in g and g.startswith('"Nordvik Defence" (')
    qpair = queries_for("pair", subj, others=["Kestrel Optics (UK)"])
    assert render("google", qpair[0][1]) == '"Nordvik Defence" "Kestrel Optics"'
    qgeo = queries_for("geo", subj, countries=["India", "United States"])
    assert render("bing", qgeo[0][1]) == '"Nordvik Defence" "India" (contract OR order OR delivery)'
    assert render("gdelt", qgeo[0][1]) == '"Nordvik Defence" India (contract OR order OR delivery)'
    assert render("gdelt", qgeo[1][1]).startswith('"Nordvik Defence" "United States"')
    rss = (b'<?xml version="1.0"?><rss xmlns:News="https://www.bing.com/news"><channel><item><title>Nordvik signs JV</title>'
           b'<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.defensenews.com%2fa%2fb&amp;c=1</link>'
           b'<pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate><News:Source>Defense News</News:Source></item></channel></rss>')
    b = parse_bing(rss)
    assert b == [{"title": "Nordvik signs JV", "link": "https://www.defensenews.com/a/b", "url": "https://www.defensenews.com/a/b",
                  "source": "Defense News", "source_url": "https://www.defensenews.com/a/b", "date": date(2026, 10, 5)}], b
    rng = (date(2026, 1, 25), date(2026, 10, 26))
    sl = gdelt_slices(rng, True)
    assert sl[0] == (date(2026, 1, 25), date(2026, 1, 31)) and sl[-1] == (date(2026, 10, 1), date(2026, 10, 26)) and len(sl) == 10
    assert gdelt_slices(rng, False) == [rng]
    raws = b + [{"title": "Old", "link": "https://www.defensenews.com/c", "url": "https://www.defensenews.com/c", "source": "",
                 "source_url": "https://www.defensenews.com/c", "date": date(2025, 1, 1)},
                {"title": "Blog", "link": "https://someblog.blogspot.com/x", "url": "https://someblog.blogspot.com/x", "source": "",
                 "source_url": "https://someblog.blogspot.com/x", "date": date(2026, 5, 1)}]
    items = to_items(raws, rng, [], set(), direct=True)
    assert [i.url for i in items] == ["https://www.defensenews.com/a/b"] and items[0].resolve_method == "direct"
    assert to_items(raws, rng, [], {"https://www.defensenews.com/a/b"}, direct=True) == []
    assert _like("a%b") == "%a\\%b%"
    assert wp_words({"name": "Nordvik", "term": "joint venture"}) == "Nordvik joint venture" and wp_words({"name": "Nordvik"}) == "Nordvik"
    feed = (b'<rss><channel><item><title>Nordvik JV</title><link>https://www.navalnews.com/a/</link>'
            b'<pubDate>Tue, 06 Oct 2026 08:00:00 +0000</pubDate></item></channel></rss>')
    assert parse_feed_items(feed) == [{"title": "Nordvik JV", "link": "https://www.navalnews.com/a/", "url": "https://www.navalnews.com/a/",
                                       "source": "navalnews.com", "source_url": "https://www.navalnews.com/a/", "date": date(2026, 10, 6)}]
    it = news.Item(title="t", link="l", source="s", source_url="u", date=date(2026, 3, 1), url="https://x.test/a")
    row = json.loads(item_to_json({"competitor_id": "c-1"}, it, "product", "q", "google", {"product_id": "p-1"}))
    assert row["product_id"] == "p-1"
    assert row["item"]["date"] == "2026-03-01" and news.Item(**{**row["item"], "date": None}).url == "https://x.test/a"
    print("news_sources self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.news_sources", description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--source", choices=["google", "bing", "gdelt", "dc", "wpsearch"])
    ap.add_argument("--kind", default="partner,pair,geo")
    ap.add_argument("--competitor", default="all")
    ap.add_argument("--all-companies", action="store_true", help="company queries for every competitor (default: thin ones only)")
    ap.add_argument("--from", dest="frm", default=(date.today() - timedelta(days=274)).isoformat())
    ap.add_argument("--to", default=date.today().isoformat())
    ap.add_argument("--max-queries", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--export-jobs")
    ap.add_argument("--job-file")
    ap.add_argument("--to-file")
    ap.add_argument("--load-file")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--per-host", type=int, default=2, help="requests in flight per host (Google's own gate is 8 in news.py)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
        return 0
    if a.report:
        report()
        return 0
    if a.load_file:
        print(dict(load_file(a.load_file, a.dry_run)))
        return 0
    news.GATE.overrides["news.google.com"] = a.per_host
    rng = (date.fromisoformat(a.frm), date.fromisoformat(a.to))
    kinds = [k.strip() for k in a.kind.split(",") if k.strip()]
    if a.job_file:                          # a worker host: no DB, results to a file
        spec = json.load(open(a.job_file, encoding="utf-8"))
        rng = (date.fromisoformat(spec["from"]), date.fromisoformat(spec["to"]))
        with open(a.to_file, "a", encoding="utf-8") as out:
            def emit(job, it, kind, q, qspec=None):
                out.write(item_to_json(job, it, kind, q, spec["source"], qspec) + "\n")
                out.flush()
            st = run_jobs(spec["jobs"], spec["source"], rng, fetch_images=False, emit=emit, max_queries=a.max_queries)
        print(dict(st))
        return 0
    conn = connect()
    with conn.cursor() as cur:
        jobs = build_jobs(cur, kinds, a.competitor, a.all_companies)
    conn.close()
    print(f"{a.source}: {len(jobs)} competitors, {sum(len(j['queries']) for j in jobs)} queries ({', '.join(kinds)}), range {rng[0]}..{rng[1]}", flush=True)
    if a.export_jobs:
        json.dump({"source": a.source, "from": rng[0].isoformat(), "to": rng[1].isoformat(), "jobs": jobs}, open(a.export_jobs, "w", encoding="utf-8"))
        print("jobs written to", a.export_jobs)
        return 0
    dc = None
    if a.source == "dc":
        from backend.import_dc_corpus import connect_dc
        dc = connect_dc()
    saver = Saver(a.source, a.dry_run)
    st = run_jobs(jobs, a.source, rng, fetch_images=not a.dry_run, emit=saver, max_queries=a.max_queries, dc=dc)
    saver.close()
    print(dict(st), {f"{k[0]}:{k[1]}": v for k, v in saver.stats.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
