"""Import scored documents from the data-centre (DC) corpus into staging.source_document (raw layer).

Source : DC Postgres `mallory`, schema document_triage (scored layer) + public.documents (main_text). READ-ONLY.
         Reached through the local tunnel 127.0.0.1:15432. Credentials come from DATA_CENTRE_DSN in the deploy.env
         file (path: env KSSL_DC_ENV_FILE, default C:\\Users\\HARICHANDRA\\Desktop\\deploy.env) or from env KSSL_DC_DSN.
         Host/port are always replaced by KSSL_DC_HOST:KSSL_DC_PORT (default 127.0.0.1:15432); the DSN is never printed.
Target : LOCAL kssl_staging (env KSSL_STAGING_DSN, default the docker kssl-pg on 127.0.0.1:55432), table staging.source_document.

    python -m backend.import_dc_corpus --selftest
    python -m backend.import_dc_corpus --count-only [--competitor NAME] [--from 2026-01-17] [--per-competitor 400] [--min-relevance 0.6]
    python -m backend.import_dc_corpus --dry-run
    python -m backend.import_dc_corpus                       # the real import (idempotent / resumable)

Selection (what a document must satisfy)
  * queue P0-P2, not a near-duplicate (near_dup_of IS NULL), not an exact duplicate (document_duplicate_source),
    html pages only (PDF attachments carry no url / document id and their text lives in S3, not in public.documents);
  * company relevance (document_company_signal_score.relevance) >= --min-relevance for at least one MAPPED competitor.
    Relevance is a tiered score: 0.3 = one passing mention, 0.5 = no mention at all (topical inference), 0.55 = one mention,
    0.6 = repeated mentions, 0.7-0.8 = several / prominent mentions, 0.85+ = company in title / url / owns the domain.
    Default 0.6;
  * date: doc_date >= --from when the corpus has one (and is not in the future); documents WITHOUT a usable date
    are kept only if their crawl date (ingested_at) is >= --from AND their url does not carry an older year
    (/2023/, -2024-, ...) -- the crawl date alone is nearly always inside the window, so the url year is the real guard;
  * per competitor the best --per-competitor documents by priority (the rest are counted as cut).
Idempotency: documents whose url is already in staging.source_document are never re-fetched. Rows written by this
importer are skipped; rows written by another harvester get this triage merged in under triage->'dc_corpus' and the
competitor ids unioned (body_text and the rest of that row are left alone).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

DEFAULT_ENV_FILE = r"C:\Users\HARICHANDRA\Desktop\deploy.env"
DEFAULT_LOCAL_DSN = "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl"
BODY_CAP = 30_000
SIGNALS = ("spec", "deal", "sales_geo", "tech")
SIGNAL_MIN = 0.5            # a company signal "counts" at p >= 0.5 (same as the DC v_company_signal_coverage view)
QUEUES = ("P0", "P1", "P2")

# DC corpus company_id -> staging.competitive_competitor.display_name  (explicit; checked against the DB at run time)
CORPUS_TO_COMPETITOR = {
    "lockheed_martin": "Lockheed Martin",
    "bae_systems": "BAE Systems",
    "rtx": "RTX (Raytheon)",
    "rheinmetall": "Rheinmetall",
    "general_dynamics": "General Dynamics",
    "saab": "SAAB",
    "sig_sauer": "SIG Sauer",
    "mbda": "MBDA",
    "l3harris": "L3Harris",
    "naval_group": "Naval Group",
    "knds": "KNDS Germany",                       # group-level corpus entity; we hold KNDS Germany + Nexter (KNDS France)
    "hanwha_aerospace": "Hanwha Aerospace",
    "kongsberg": "KONGSBERG",
    "elbit_systems": "Elbit Systems",
    "anduril": "Anduril",
    "rafael": "Rafael Advanced Defense Systems",
    "iai": "Israel Aerospace Industries (IAI)",
    "patria": "Patria",
    "diehl_defence": "Diehl Defence",
    "babcock": "Babcock",
    "nexter": "Nexter (KNDS France)",
    "oshkosh_defense": "Oshkosh Defense",
    "otokar": "Otokar",
    "brahmos": "BrahMos Aerospace",
    "bharat_dynamics": "Bharat Dynamics Ltd (BDL)",
    "aerovironment": "AeroVironment",
    "poongsan": "Poongsan",
    "tata_advanced_systems": "Tata Advanced Systems",
    "nammo": "Nammo",
    "supacat": "Supacat",
    "norinco": "NORINCO",
    "larsen_toubro": "Larsen & Toubro",
    "huta_stalowa_wola": "Huta Stalowa Wola (HSW)",
    "idv": "IDV (Iveco Defence)",
    "kalashnikov": "Kalashnikov Concern",
    "uvision": "UVision Air",
    "paramount_group": "Paramount Group",
    "adani_defence": "Adani Defence & Aerospace",
    "aweil": "AWEIL",
    "solar_industries": "Solar Industries",
    "mahindra_defence": "Mahindra Defence",
    "munitions_india": "Munitions India Ltd (MIL)",
    "premier_explosives": "Premier Explosives",
    "roshel": "Roshel",
    "sss_defence": "SSS Defence",
    "plr_systems": "PLR Systems (IWI+Adani)",
}
CLIENT_CORPUS_IDS = {"kssl", "kalyani_strategic_systems", "kalyani_strategic_systems_limited"}


# ----------------------------------------------------------------------------------------------- pure helpers
def norm_name(value) -> str:
    """Name normalisation for matching: lower case, '&'->'and', punctuation/parentheses dropped, corporate suffixes
    and filler words removed, whitespace collapsed.  'Bharat Dynamics Limited' == 'Bharat Dynamics Ltd (BDL)'-ish."""
    s = str(value or "").lower().replace("&", " and ")
    s = re.sub(r"\([^)]*\)", " ", s)                      # drop parenthetical notes: "(BDL)", "(Raytheon)"
    s = re.sub(r"[^a-z0-9]+", " ", s)
    stop = {"limited", "ltd", "corporation", "corp", "inc", "plc", "ag", "ab", "the", "company", "co", "group", "systems",
            "defence", "defense", "industries", "international", "and", "advanced", "technologies", "aerospace",
            "concern", "business", "now"}
    words = [w for w in s.split() if w not in stop]
    return " ".join(words) or s.strip()


def canonical_url(url: str) -> str:
    """Strip the fragment and surrounding whitespace; keep everything else (query strings can identify the page)."""
    u = (url or "").strip()
    try:
        p = urlsplit(u)
    except ValueError:
        return u
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))


def doc_uuid(url: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, canonical_url(url)))


def host_of(url: str) -> str:
    try:
        h = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


_URL_YEAR = re.compile(r"(?<![0-9])(19[89][0-9]|20[0-3][0-9])(?![0-9])")


def url_years(url: str) -> list[int]:
    """Years that appear as a standalone 4-digit token in the url path (not in the host / query)."""
    try:
        path = urlsplit(url).path or ""
    except ValueError:
        return []
    return [int(y) for y in _URL_YEAR.findall(path)]


def parse_day(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def effective_date(doc_date, ingested_at, url: str, start: date, today: date) -> tuple[date | None, str, bool]:
    """(published_at to store, how it was decided, in_window).
    Dated doc: in window iff doc_date >= start (a date in the future is unusable and treated as undated).
    Undated doc: in window iff crawl date >= start and the url path carries no year older than start.year."""
    d = parse_day(doc_date)
    if d is not None and d <= today + timedelta(days=1):
        return d, "doc_date", d >= start
    crawl = parse_day(ingested_at)
    if crawl is None or crawl < start:
        return None, "undated:crawl_before_window", False
    old = [y for y in url_years(url) if y < start.year]
    if old:
        return None, "undated:url_year_%d" % max(old), False
    return None, "undated:crawl_in_window", True


def signals_of(row: dict) -> dict:
    return {k: round(float(row.get("p_" + k) or 0), 3) for k in SIGNALS}


def signal_flags(row: dict) -> list[str]:
    return [k for k in SIGNALS if float(row.get("p_" + k) or 0) >= SIGNAL_MIN]


def hint_list(hints, limit: int = 5) -> list[dict]:
    """Top evidence sentences from the DC hints object -> [{'kind','text'}] (<= limit, each <= 400 chars)."""
    out: list[dict] = []
    if not isinstance(hints, dict):
        return out

    def add(kind, text):
        if isinstance(text, dict):
            text = text.get("text") or text.get("sentence") or text.get("title") or ""
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if text and len(out) < limit and all(text != o["text"] for o in out):
            out.append({"kind": kind, "text": text[:400]})

    for key, kind in (("deal_sentence", "deal"), ("sales_sentence", "sales_geo"), ("tech_sentence", "tech")):
        add(kind, hints.get(key))
    for key, kind in (("spec_examples", "spec"), ("trade_shows", "trade_show"), ("best_pages", "page")):
        v = hints.get(key)
        for item in (v if isinstance(v, list) else []):
            add(kind, item)
    return out


def shape_triage(doc: dict, companies: list[dict]) -> dict:
    """The jsonb stored in staging.source_document.triage.  `doc` = a document_priority_* row (dict), `companies` = the
    mapped competitor rows above the threshold: {competitor_id, name, corpus_id, relevance, mentions, p_*, products}."""
    def lst(v, n=12):
        return [str(x) for x in (v or [])][:n]

    return {
        "source": "dc_corpus",
        "dc_document_key": doc.get("document_key"),
        "dc_document_id": doc.get("document_id"),
        "queue": doc.get("queue"),
        "priority": None if doc.get("priority") is None else round(float(doc["priority"]), 3),
        "priority_rank": doc.get("priority_rank"),
        "doc_type": doc.get("doc_type"),
        "scope": doc.get("scope"),
        "signals": signals_of(doc),
        "info": {k: round(float(doc.get("info_" + k) or 0), 3) for k in SIGNALS},
        "base_score": None if doc.get("base_score") is None else round(float(doc["base_score"]), 3),
        "deal_types": lst(doc.get("deal_types")),
        "countries": lst(doc.get("countries"), 20),
        "counterparties": lst(doc.get("counterparties"), 20),
        "hints": hint_list(doc.get("hints"), 5),
        "date": {"doc_date": str(doc["doc_date"]) if doc.get("doc_date") else None,
                 "source": doc.get("doc_date_source"), "decided": doc.get("date_decision")},
        "dc_source_tier": doc.get("source_tier"),
        "companies": {
            str(c["competitor_id"]): {
                "name": c["name"], "corpus_id": c["corpus_id"],
                "relevance": round(float(c["relevance"]), 3), "mentions": c.get("mentions"),
                "signals": signals_of(c), "products": lst(c.get("products"), 10),
            } for c in companies
        },
    }


def rank_key(r: dict):
    return (-(float(r.get("priority") or 0)), r.get("priority_rank") or 10**9, r.get("document_key") or "")


def select_per_competitor(rows: list[dict], cap: int) -> tuple[set, dict]:
    """rows: one per (document, competitor): {document_key, competitor_id, priority, priority_rank, ...}.
    Returns (selected document keys, {competitor_id: (n_candidates, n_kept)}).  A document kept for any competitor is
    imported once."""
    by_comp: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_comp[r["competitor_id"]].append(r)
    keep: set = set()
    stat = {}
    for cid, lst in by_comp.items():
        lst.sort(key=rank_key)
        best = lst[:cap]
        keep.update(r["document_key"] for r in best)
        stat[cid] = (len(lst), len(best))
    return keep, stat


def merge_triage_sql() -> str:
    return ("UPDATE staging.source_document SET "
            "triage = COALESCE(triage, '{}'::jsonb) || jsonb_build_object('dc_corpus', %s::jsonb), "
            "competitor_ids = (SELECT COALESCE(array_agg(DISTINCT x), '{}') FROM unnest(competitor_ids || %s::uuid[]) x), "
            "status = CASE WHEN status = 'new' THEN 'attributed' ELSE status END "
            "WHERE url = %s AND source_kind <> 'dc_corpus'")


# ----------------------------------------------------------------------------------------------- connections
def dc_dsn() -> str:
    dsn = (os.environ.get("KSSL_DC_DSN") or "").strip()
    if not dsn:
        path = os.environ.get("KSSL_DC_ENV_FILE") or DEFAULT_ENV_FILE
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("DATA_CENTRE_DSN="):
                    dsn = line.split("=", 1)[1].strip().strip("'\"")
                    break
    if not dsn:
        raise RuntimeError("DATA_CENTRE_DSN not found (set KSSL_DC_DSN or KSSL_DC_ENV_FILE)")
    p = urlsplit(dsn)
    userinfo = p.netloc.rsplit("@", 1)[0] + "@" if "@" in p.netloc else ""
    host = os.environ.get("KSSL_DC_HOST", "127.0.0.1")
    port = os.environ.get("KSSL_DC_PORT", "15432")
    return urlunsplit((p.scheme, f"{userinfo}{host}:{port}", p.path, p.query, p.fragment))


def connect_dc():
    import psycopg2
    conn = psycopg2.connect(dc_dsn(), connect_timeout=15,
                            options="-c statement_timeout=120000 -c default_transaction_read_only=on")
    conn.set_session(readonly=True, autocommit=True)
    return conn


def connect_local():
    import psycopg2
    return psycopg2.connect(os.environ.get("KSSL_STAGING_DSN") or DEFAULT_LOCAL_DSN, connect_timeout=5)


# ----------------------------------------------------------------------------------------------- DC queries
CANDIDATE_SQL = """
SELECT c.document_key, c.company_id, c.relevance, c.mentions, c.in_title, c.owns_domain,
       c.p_spec, c.p_deal, c.p_sales_geo, c.p_tech, c.products,
       r.queue, r.priority, r.priority_rank,
       s.document_id, s.url, s.title, s.language, s.doc_date, s.doc_date_source, s.ingested_at, s.doc_type, s.scope,
       s.needs_ocr, s.source_tier, s.domain, s.base_score, s.n_chars, s.hints,
       s.info_spec, s.info_deal, s.info_sales_geo, s.info_tech,
       s.deal_types, s.countries, s.counterparties,
       s.p_spec AS d_p_spec, s.p_deal AS d_p_deal, s.p_sales_geo AS d_p_sales_geo, s.p_tech AS d_p_tech
FROM document_triage.document_company_signal_score c
JOIN document_triage.document_priority_rank r USING (document_key)
JOIN document_triage.document_priority_score s USING (document_key)
WHERE c.company_id = ANY(%(companies)s)
  AND c.relevance >= %(minrel)s
  AND r.queue = ANY(%(queues)s)
  AND r.near_dup_of IS NULL
  AND s.document_kind = 'html_page'
  AND s.url IS NOT NULL AND s.document_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM document_triage.document_duplicate_source d WHERE d.duplicate_document_id = s.document_id)
"""


def fetch_candidates(dc, companies: list[str], minrel: float) -> list[dict]:
    import psycopg2.extras
    cur = dc.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(CANDIDATE_SQL, {"companies": companies, "minrel": minrel, "queues": list(QUEUES)})
    return [dict(r) for r in cur.fetchall()]


def fetch_texts(dc, ids: list[str]) -> dict:
    """document_id -> (main_text capped at BODY_CAP chars, source_id).  Primary-key lookups only."""
    cur = dc.cursor()
    cur.execute("SELECT document_id, left(main_text, %s), source_id FROM public.documents WHERE document_id = ANY(%s)",
                (BODY_CAP, ids))
    return {a: (b, c) for a, b, c in cur.fetchall()}


# ----------------------------------------------------------------------------------------------- main flow
def load_competitor_map(local) -> tuple[dict, list]:
    """corpus company_id -> competitor_id, using CORPUS_TO_COMPETITOR checked against staging.competitive_competitor
    (exact display_name, falling back to norm_name equality).  Returns (map, [problems])."""
    cur = local.cursor()
    cur.execute("SELECT competitor_id, display_name FROM staging.competitive_competitor")
    rows = cur.fetchall()
    exact = {n: str(i) for i, n in rows}
    normed = {norm_name(n): str(i) for i, n in rows}
    out, problems = {}, []
    for cid, name in CORPUS_TO_COMPETITOR.items():
        hit = exact.get(name) or normed.get(norm_name(name))
        if hit:
            out[cid] = hit
        else:
            problems.append((cid, name))
    return out, problems


def corpus_company_names(dc) -> dict:
    cur = dc.cursor()
    cur.execute("SELECT company_id, max(company_name) FROM document_triage.document_company_signal_score GROUP BY 1")
    return dict(cur.fetchall())


def print_table(title, header, rows):
    print("\n" + title)
    w = [max(len(str(x)) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
    print("  " + "  ".join(str(h).ljust(n) for h, n in zip(header, w)))
    for r in rows:
        print("  " + "  ".join(str(x).ljust(n) for x, n in zip(r, w)))


def run(args) -> int:
    start = date.fromisoformat(args.from_date)
    today = date.today()
    local = connect_local()
    dc = connect_dc()
    cmap, problems = load_competitor_map(local)
    names = corpus_company_names(dc)
    cur = local.cursor()
    cur.execute("SELECT competitor_id, display_name FROM staging.competitive_competitor")
    comp_name = {str(i): n for i, n in cur.fetchall()}
    cur.execute("SELECT client_id FROM staging.client_account LIMIT 1")

    print("== name map: corpus company -> staging competitor")
    for cid in sorted(names, key=lambda c: names[c]):
        tgt = cmap.get(cid)
        print(f"  {names[cid]:<46} ({cid}) -> {comp_name[tgt] if tgt else '-- UNMATCHED --'}")
    unmatched_corpus = [c for c in names if c not in cmap]
    if unmatched_corpus:
        print("  corpus companies with no competitor:", [names[c] for c in unmatched_corpus])
    unseen = [c for c in CORPUS_TO_COMPETITOR if c not in names]
    if unseen:
        print("  mapped ids absent from this corpus:", unseen)
    if problems:
        print("  map entries that do not resolve to a competitor row:", problems)
    client_ids = [c for c in names if c in CLIENT_CORPUS_IDS]
    print("  client (KSSL) among corpus companies:", client_ids or "no")
    print("  staging competitors with no corpus company:",
          sorted(n for i, n in comp_name.items() if i not in cmap.values()))

    use = dict(cmap)
    if args.competitor:
        want = norm_name(args.competitor)
        use = {c: i for c, i in cmap.items() if want in (norm_name(comp_name[i]), norm_name(names.get(c, "")), c)}
        if not use:
            print("no mapped competitor matches --competitor", args.competitor)
            return 2
    cand = fetch_candidates(dc, list(use), args.min_relevance)
    from backend.sources import is_blocked
    blocked_docs = {r["document_key"] for r in cand if is_blocked(r["url"])}
    cand = [r for r in cand if r["document_key"] not in blocked_docs]   # before the cap, so the cap refills
    print(f"   skipped 'blocked: blog/wiki' (sources.is_blocked): {len(blocked_docs)} documents")
    for r in cand:
        r["competitor_id"] = use[r["company_id"]]
    print(f"\n== candidates (queue P0-P2, no near/exact dup, html, relevance >= {args.min_relevance}, mapped): "
          f"{len(cand)} (document x competitor) rows, {len({r['document_key'] for r in cand})} documents")

    # unify url duplicates (same canonical url under several document_keys): keep the best-priority key
    best_for_url: dict[str, dict] = {}
    for r in cand:
        u = canonical_url(r["url"])
        cur_best = best_for_url.get(u)
        if cur_best is None or rank_key(r) < rank_key(cur_best):
            best_for_url[u] = r
    url_key = {u: r["document_key"] for u, r in best_for_url.items()}
    key_url = {}
    for u, k in url_key.items():
        key_url[k] = u
    dup_urls = len({r["document_key"] for r in cand}) - len(url_key)

    # date filter
    dec = Counter()
    in_window: list[dict] = []
    for r in cand:
        if key_url.get(r["document_key"]) is None:
            continue     # a lower-priority copy of a url we already hold under another key
        pub, why, ok = effective_date(r["doc_date"], r["ingested_at"], r["url"], start, today)
        r["published_at"], r["date_decision"] = pub, why
        dec[(why if why.startswith("undated") else "dated", ok)] += 1
        if ok:
            in_window.append(r)
    print(f"   url duplicates collapsed: {dup_urls};  date decision (rows): "
          + ", ".join(f"{k[0]}{'+' if k[1] else '-'}:{v}" for k, v in sorted(dec.items())))

    keep, stat = select_per_competitor(in_window, args.per_competitor)

    # counts per competitor x signal
    sel = defaultdict(Counter)
    kept = defaultdict(Counter)
    for r in in_window:
        i = use[r["company_id"]]
        flags = signal_flags(r)
        sel[i]["docs"] += 1
        for f in flags:
            sel[i][f] += 1
    per_comp_rows = defaultdict(list)
    for r in in_window:
        per_comp_rows[use[r["company_id"]]].append(r)
    cut_total = 0
    for i, lst in per_comp_rows.items():
        lst.sort(key=rank_key)
        for r in lst[:args.per_competitor]:
            kept[i]["docs"] += 1
            for f in signal_flags(r):
                kept[i][f] += 1
    rows = []
    for i in sorted(per_comp_rows, key=lambda i: comp_name[i]):
        s, k = sel[i], kept[i]
        cut_total += s["docs"] - k["docs"]
        rows.append((comp_name[i], s["docs"], k["docs"], s["docs"] - k["docs"]) +
                    tuple(f"{s[f]}/{k[f]}" for f in SIGNALS))
    print_table("== per competitor (selected -> kept after cap; signals shown selected/kept, p >= 0.5)",
                ("competitor", "selected", "kept", "cut") + SIGNALS, rows)
    tot_sel = sum(sel[i]["docs"] for i in sel)
    print(f"\n   (document x competitor) rows selected {tot_sel}, cut by cap {cut_total}; "
          f"distinct documents to import {len(keep)}")

    if args.count_only:
        return 0

    # ---- build the import set
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for r in cand:                       # all above-threshold mapped competitors for each kept document
        if r["document_key"] in keep:
            by_doc[r["document_key"]].append(r)
    keys = sorted(by_doc, key=lambda k: rank_key(by_doc[k][0]))
    urls = [canonical_url(by_doc[k][0]["url"]) for k in keys]
    cur = local.cursor()
    cur.execute("SELECT url, source_kind FROM staging.source_document WHERE url = ANY(%s)", (urls,))
    existing = dict(cur.fetchall())
    stats = Counter()
    pending = []
    for k, u in zip(keys, urls):
        if existing.get(u) == "dc_corpus":
            stats["already_imported"] += 1
        else:
            pending.append(k)
    print(f"\n== importing: {len(keys)} documents; {stats['already_imported']} already imported by this importer; "
          f"{sum(1 for u in urls if existing.get(u) not in (None, 'dc_corpus'))} exist from another harvester (merge)")

    from backend.sources import classify
    body_chars = 0
    lang = Counter()
    pubs = Counter()
    examples = []
    BATCH = 100
    for off in range(0, len(pending), BATCH):
        chunk = pending[off:off + BATCH]
        texts = {}
        need = [by_doc[k][0]["document_id"] for k in chunk if existing.get(canonical_url(by_doc[k][0]["url"])) is None]
        if need:
            texts = fetch_texts(dc, need)
        for k in chunk:
            rows_k = by_doc[k]
            d = rows_k[0]
            pub, why, _ = effective_date(d["doc_date"], d["ingested_at"], d["url"], start, today)
            d["published_at"], d["date_decision"] = pub, why
            url = canonical_url(d["url"])
            comps = []
            for r in sorted(rows_k, key=lambda r: -float(r["relevance"])):
                cid = use.get(r["company_id"]) or cmap.get(r["company_id"])
                if cid:
                    comps.append({"competitor_id": cid, "name": comp_name[cid], "corpus_id": r["company_id"],
                                  "relevance": r["relevance"], "mentions": r["mentions"], "products": r["products"],
                                  **{"p_" + s: r["p_" + s] for s in SIGNALS}})
            doc = dict(d)
            for s in SIGNALS:            # document-level p_* (company-level ones live under companies)
                doc["p_" + s] = d["d_p_" + s]
            triage = shape_triage(doc, comps)
            comp_ids = sorted({c["competitor_id"] for c in comps})
            if existing.get(url) is not None:       # another harvester has this url: merge, do not overwrite
                if not args.dry_run:
                    cur.execute(merge_triage_sql(), (json.dumps(triage), comp_ids, url))
                stats["merged_into_existing"] += 1
                continue
            text, source_id = texts.get(d["document_id"], (None, None))
            text = (text or "").replace("\x00", "").strip()
            if not text:
                stats["skipped_no_text" + ("_needs_ocr" if d["needs_ocr"] else "")] += 1
                continue
            host = host_of(url)
            tier = classify(url, ()) or "unlisted"
            body = text[:BODY_CAP]
            body_chars += len(body)
            lang[d["language"] or "?"] += 1
            pubs[("dated" if d["published_at"] else "undated")] += 1
            if len(examples) < 3 and d["published_at"] and triage["hints"]:
                examples.append((d["title"], url, triage["hints"][0]["text"]))
            if not args.dry_run:
                cur.execute(
                    "INSERT INTO staging.source_document (doc_id, url, source_kind, source_name, source_tier, feed_url,"
                    " origin_ref, title, published_at, language, body_text, triage, competitor_ids, mentions_client, status)"
                    " VALUES (%s,%s,'dc_corpus',%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::uuid[],%s,'attributed')"
                    " ON CONFLICT (url) DO NOTHING",
                    (doc_uuid(url), url, host, tier, "dc:mallory/document_triage", d["document_id"],
                     (d["title"] or "")[:1000] or None, d["published_at"], d["language"], body,
                     json.dumps(triage), comp_ids, None))
                stats["inserted" if cur.rowcount else "conflict_ignored"] += 1
            else:
                stats["would_insert"] += 1
        if not args.dry_run:
            local.commit()
        print(f"   .. {min(off + BATCH, len(pending))}/{len(pending)}", flush=True)
    if not args.dry_run:
        local.commit()
    print("\n== result:", dict(stats))
    print("   body text chars:", body_chars, f"({body_chars / 1e6:.1f} MB)")
    print("   dated/undated:", dict(pubs), " language mix:", dict(lang.most_common(12)))
    for t, u, h in examples:
        print("   example:", t, "|", u, "|", h)
    return 0


# ----------------------------------------------------------------------------------------------- selftest
def selftest() -> None:
    assert norm_name("Bharat Dynamics Limited") == norm_name("Bharat Dynamics Ltd (BDL)") == "bharat dynamics"
    assert norm_name("Larsen & Toubro (defence business)") == norm_name("Larsen & Toubro") == "larsen toubro"
    assert norm_name("  ACME  Holdings, Inc. ") == "acme holdings"
    assert norm_name("") == ""
    assert canonical_url(" https://Example.com/a/b?x=1#frag ") == "https://Example.com/a/b?x=1"
    assert doc_uuid("https://example.com/a#x") == doc_uuid("https://example.com/a")
    assert doc_uuid("https://example.com/a") != doc_uuid("https://example.com/b")
    assert host_of("https://www.Example.com/x") == "example.com"
    assert url_years("https://example.com/news/2024/05/x") == [2024]
    assert url_years("https://example.com/news/x-12345-2026") == [2026]
    assert url_years("https://example.com/p?year=2019") == []
    start, today = date(2026, 1, 17), date(2026, 10, 17)
    assert effective_date("2026-03-01", None, "https://e.com/x", start, today) == (date(2026, 3, 1), "doc_date", True)
    assert effective_date(date(2025, 12, 31), "2026-09-01T00:00:00Z", "https://e.com/x", start, today)[2] is False
    assert effective_date("2027-05-01", "2026-09-01T00:00:00Z", "https://e.com/x", start, today) == \
        (None, "undated:crawl_in_window", True)                        # future date -> unusable -> undated rule
    assert effective_date(None, "2026-09-01T10:00:00Z", "https://e.com/x", start, today)[2] is True
    assert effective_date(None, "2026-09-01T10:00:00Z", "https://e.com/2023/x", start, today)[2] is False
    assert effective_date(None, "2025-06-01T10:00:00Z", "https://e.com/x", start, today)[2] is False
    assert effective_date(None, None, "https://e.com/x", start, today)[2] is False
    hints = {"deal_sentence": "Acme ordered 10 widgets.", "sales_sentence": None, "tech_sentence": "Widget uses X.",
             "spec_examples": ["range 5 km", "range 5 km", {"text": "mass 2 t"}], "trade_shows": ["Fair 2026"],
             "best_pages": []}
    hl = hint_list(hints, 5)
    assert [h["kind"] for h in hl] == ["deal", "tech", "spec", "spec", "trade_show"] and len(hl) == 5
    assert hint_list(None) == [] and len(hint_list(hints, 2)) == 2
    doc = {"document_key": "doc_x", "document_id": "doc_x", "queue": "P1", "priority": 71.23456, "priority_rank": 5,
           "doc_type": "news_article", "scope": "corpus_defence", "p_spec": 0.1, "p_deal": 0.7, "p_sales_geo": 0.5,
           "p_tech": 0.0, "base_score": 0.4, "deal_types": ["contract"], "countries": ["XX"], "counterparties": ["Beta"],
           "hints": hints, "doc_date": date(2026, 3, 1), "doc_date_source": "published_at", "date_decision": "doc_date"}
    comp = [{"competitor_id": "00000000-0000-0000-0000-000000000001", "name": "Acme", "corpus_id": "acme",
             "relevance": 0.9, "mentions": 7, "p_spec": 0, "p_deal": 0.8, "p_sales_geo": 0.6, "p_tech": 0.2,
             "products": ["Widget"]}]
    t = shape_triage(doc, comp)
    json.dumps(t)
    assert t["queue"] == "P1" and t["priority"] == 71.235 and t["signals"]["deal"] == 0.7
    assert signal_flags(doc) == ["deal", "sales_geo"]
    c = t["companies"]["00000000-0000-0000-0000-000000000001"]
    assert c["signals"]["deal"] == 0.8 and c["products"] == ["Widget"] and c["relevance"] == 0.9
    assert len(t["hints"]) == 5 and t["date"]["doc_date"] == "2026-03-01"
    rows = [{"document_key": f"d{i}", "competitor_id": "A", "priority": 100 - i, "priority_rank": i} for i in range(6)]
    rows += [{"document_key": "d5", "competitor_id": "B", "priority": 10, "priority_rank": 9},
             {"document_key": "d9", "competitor_id": "B", "priority": 99.5, "priority_rank": 1}]
    keep, stat = select_per_competitor(rows, 3)
    assert keep == {"d0", "d1", "d2", "d5", "d9"} and stat == {"A": (6, 3), "B": (2, 2)}
    assert "dc_corpus" in merge_triage_sql() and "source_kind <> 'dc_corpus'" in merge_triage_sql()
    assert set(CORPUS_TO_COMPETITOR) and len(set(CORPUS_TO_COMPETITOR.values())) == len(CORPUS_TO_COMPETITOR)
    print("selftest ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--competitor", help="only this competitor (display name, corpus name or corpus id)")
    ap.add_argument("--from", dest="from_date", default=(date.today() - timedelta(days=274)).isoformat())     # rolling 9 months
    ap.add_argument("--per-competitor", type=int, default=400)
    ap.add_argument("--min-relevance", type=float, default=0.6)
    ap.add_argument("--dry-run", action="store_true", help="run the whole flow but write nothing")
    ap.add_argument("--count-only", action="store_true", help="print what the selection gives and stop")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")      # titles hold characters a cp1252 console cannot print
    except Exception:
        pass
    if args.selftest:
        selftest()
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
