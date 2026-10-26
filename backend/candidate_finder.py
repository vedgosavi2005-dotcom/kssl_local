"""Free candidate finder (code, no model): partnership pairs and geo / project leads from the raw layer, then a targeted search.

    python -m backend.candidate_finder --selftest                       (no DB, no network, fictional names)
    python -m backend.candidate_finder --scan [--dry-run]               (raw layer -> staging.harvest_candidate)
    python -m backend.candidate_finder --search [--limit N] [--no-google] [--no-dc] [--per-pair 6] [--dry-run]
    python -m backend.candidate_finder --report                         (counts per kind / competitor)

Owner 2026-10-25 ("base system -> partners -> source article", done by code). The scan reads staging.source_document (title +
the opening ~2,000 characters of the body, page-furniture lines removed as in backend/attribute_documents.py; blocked pages never):
  pair  a tracked competitor and another company in the HEADLINE or the OPENING PARAGRAPH (first ~700 characters): another
        tracked competitor, a known partner (staging.competitive_partnership.partner_name) or the client (KSSL / Kalyani / Bharat
        Forge). has_existing_row = the pair already has a competitive_partnership row (either direction for two competitors).
  geo   a tracked competitor + a country (staging.country_reference names / aliases + demonyms: "Indian Army" -> India) + a deal
        word (contract, order, plant, subsidiary, JV, delivery ...) in ONE sentence. Company names are blanked before the country
        is looked for ("Munitions India" is not India). has_existing_row = the country already shows for that competitor in
        partnership / project / moment regions or competitor locations.
Rows go to staging.harvest_candidate (db/setup/45_harvest_candidate.sql), one per (kind, competitor, other company / country),
with the documents behind it (newest first), the dates seen and the sentence / headline that names both.

The search (--search): for each pair WITHOUT a partnership row (most documents first) it looks for the source article, free:
  * DC corpus titles naming both ("A" and "B", trigram index on public.documents.title, read-only, per-pair query);
  * Google News RSS '"A" "B"' since 2023-01-01, headline must name both, publisher on the allowlist (backend/sources.py);
    the wrapper link is resolved and the page read once (backend/news.py + backend/harvest_sites.read_page; polite host gate).
Found pages are stored as raw documents (source_kind 'pair_search', status 'new', never a record): url already stored -> skipped;
blogs / wikis / aggregators (sources.is_blocked) never. Run `python -m backend.attribute_documents` afterwards (routine step order).
Local kssl_staging only; the DC is read-only through the tunnel (backend/import_dc_corpus.connect_dc).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date

from backend import news

HEAD_CHARS = 700            # "opening paragraph" for pairs
BODY_CHARS = 2000           # geo sentences: title + the first 2,000 characters (same as attribution)
SEARCH_FROM = date(2023, 1, 1)
MAX_DOC_IDS = 20
HARVESTER = "candidate_finder v1"

# deal words (normalised text, whole words / phrases) -> label stored on the row
DEAL_WORDS = {
    "contract": "contract", "contracts": "contract", "awarded": "contract", "award": "contract", "deal": "contract",
    "order": "order", "orders": "order", "ordered": "order", "procure": "order", "procurement": "order", "purchase": "order",
    "plant": "plant", "factory": "plant", "facility": "plant", "production line": "plant", "manufacturing": "plant",
    "assembly line": "plant", "local production": "plant", "produce locally": "plant",
    "subsidiary": "subsidiary", "office": "subsidiary", "opens": "subsidiary",
    "joint venture": "jv", "jv": "jv",
    "delivery": "delivery", "deliveries": "delivery", "delivered": "delivery", "delivers": "delivery", "handed over": "delivery",
    "export": "export", "exports": "export", "supply": "supply", "supplies": "supply",
    "mou": "agreement", "memorandum of understanding": "agreement", "agreement": "agreement", "licence": "agreement",
    "license": "agreement", "teaming": "agreement", "partnership": "agreement",
}
_DEAL_RX = re.compile(r"(?<!\S)(" + "|".join(sorted((re.escape(k) for k in DEAL_WORDS), key=len, reverse=True)) + r")(?!\S)")

# demonyms / short forms that name a country in defence prose ("Indian Army", "U.S. Navy"); normalised (news.norm) spellings
DEMONYMS = {
    "indian": "India", "polish": "Poland", "german": "Germany", "french": "France", "british": "United Kingdom",
    "uk": "United Kingdom", "u k": "United Kingdom", "britain": "United Kingdom", "american": "United States",
    "u s": "United States", "usa": "United States", "us army": "United States", "us navy": "United States",
    "us air force": "United States", "us marine corps": "United States", "pentagon": "United States",
    "ukrainian": "Ukraine", "israeli": "Israel", "south korean": "South Korea", "korean": "South Korea", "japanese": "Japan",
    "australian": "Australia", "canadian": "Canada", "turkish": "Turkey", "swedish": "Sweden", "norwegian": "Norway",
    "finnish": "Finland", "danish": "Denmark", "dutch": "Netherlands", "italian": "Italy", "spanish": "Spain",
    "brazilian": "Brazil", "saudi": "Saudi Arabia", "emirati": "United Arab Emirates", "uae": "United Arab Emirates",
    "egyptian": "Egypt", "indonesian": "Indonesia", "philippine": "Philippines", "czech": "Czechia", "romanian": "Romania",
    "greek": "Greece", "estonian": "Estonia", "latvian": "Latvia", "lithuanian": "Lithuania", "belgian": "Belgium",
    "swiss": "Switzerland", "austrian": "Austria", "portuguese": "Portugal", "hungarian": "Hungary", "bulgarian": "Bulgaria",
    "slovak": "Slovakia", "thai": "Thailand", "vietnamese": "Vietnam", "malaysian": "Malaysia", "singaporean": "Singapore",
    "pakistani": "Pakistan", "chinese": "China", "russian": "Russia", "armenian": "Armenia", "moroccan": "Morocco",
    "algerian": "Algeria", "nigerian": "Nigeria", "kenyan": "Kenya", "mexican": "Mexico", "chilean": "Chile",
    "colombian": "Colombia", "peruvian": "Peru", "argentine": "Argentina", "qatari": "Qatar", "kuwaiti": "Kuwait",
    "omani": "Oman", "taiwanese": "Taiwan", "croatian": "Croatia", "slovenian": "Slovenia", "serbian": "Serbia",
}
# a "partner" name that is a customer / authority, not a company: never a pair
_NOT_COMPANY = re.compile(r"(?<!\S)(ministry|army|navy|air force|government|department|forces|police|coast guard|marine corps|"
                          r"parliament|cabinet|president|council|nato|european union|eu|un)(?!\S)")
CLIENT_NAMES = ["Kalyani Strategic Systems", "Kalyani Group", "Bharat Forge", "KSSL"]


# ----------------------------------------------------------------------------------------------- pure helpers
def pad(text: str) -> str:
    return " " + news.norm(text) + " "


def sentences(text: str) -> list[str]:
    """Rough sentence split of plain text (headline lines count as sentences)."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if len(p.strip()) >= 12]


class CountryFinder:
    def __init__(self, rows):
        """rows: [(country_name, [aliases])]."""
        self.terms: dict[str, str] = {}
        for name, aliases in rows:
            for t in [name, *(aliases or [])]:
                k = news.norm(t)
                if k and len(k) >= 3:
                    self.terms[k] = name
        valid = {n for n, _ in rows}
        for k, v in DEMONYMS.items():
            if v in valid:
                self.terms[news.norm(k)] = v
        self.rx = re.compile(r"(?<!\S)(" + "|".join(sorted(map(re.escape, self.terms), key=len, reverse=True)) + r")(?!\S)") if self.terms else None

    def find(self, t_padded: str) -> set[str]:
        return {self.terms[m.group(1)] for m in self.rx.finditer(t_padded)} if self.rx else set()


def deal_words(t_padded: str) -> set[str]:
    return {DEAL_WORDS[m.group(1)] for m in _DEAL_RX.finditer(t_padded)}


def blank_names(t_padded: str, keys) -> str:
    for k in keys:
        if k:
            t_padded = t_padded.replace(f" {k} ", " " * (len(k) + 2))
    return t_padded


def partner_key(name: str) -> str:
    """Normalised partner name for matching; '' when it is not usable (too short, an authority / customer, generic)."""
    s = re.sub(r"\([^)]*\)", " ", name or "")
    k = news.name_key(s)
    if len(k.replace(" ", "")) < 4 or _NOT_COMPANY.search(f" {k} "):
        return ""
    return k


def same_group(names, other: str) -> bool:
    """The other company is the competitor's own group / parent / subsidiary ("KNDS Germany" ~ "Nexter (KNDS France)" share
    KNDS, "General Dynamics" ~ "General Dynamics European Land Systems", "Adani Defence" ~ "Adani Group"): no search needed."""
    ok = news.name_key(re.sub(r"\([^)]*\)", " ", other))
    okb = news.name_key(other)
    for n in names:
        k = news.name_key(n)
        if not k or not ok:
            continue
        if k in ok or ok in k or k.split()[0] == ok.split()[0] or (okb and k.split()[0] in okb.split()):
            return True
    return False


def candidate_key(kind: str, competitor_id: str, other: str) -> str:
    return f"{kind}|{competitor_id}|{news.norm(other)}"


class Finder:
    """subjects: {competitor_id: news.Subject}; partners: [partner name]; countries: CountryFinder."""

    def __init__(self, subjects: dict, partners, countries: CountryFinder, client_names=CLIENT_NAMES):
        from backend.attribute_documents import Matcher
        self.matcher = Matcher(subjects)
        self.subjects = subjects
        self.countries = countries
        comp_keys = {news.name_key(n) for s in subjects.values() for n in s.names}
        self.all_name_keys = sorted({k for k in comp_keys if k} | {partner_key(p) for p in partners if partner_key(p)}, key=len, reverse=True)
        self.partners: dict[str, str] = {}             # key -> display name
        for p in partners:
            k = partner_key(p)
            if k and k not in comp_keys and k not in self.partners:
                self.partners[k] = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", p)).strip()
        self.client = [(news.name_key(n), n) for n in client_names if news.name_key(n)]
        self._prx = re.compile(r"(?<!\S)(" + "|".join(sorted(map(re.escape, self.partners), key=len, reverse=True)) + r")(?!\S)") if self.partners else None

    def comps_in(self, text: str) -> set[str]:
        t = pad(text)
        return {e[0] for e in self.matcher.items if self.matcher.hit(e, t)}

    def pairs(self, title: str, body: str) -> list[tuple]:
        """[(competitor_id, other_name, other_kind, other_competitor_id, where, snippet)] from the headline / opening paragraph."""
        out = []
        for where, text in (("title", title or ""), ("opening", (title or "") + " . " + (body or "")[:HEAD_CHARS])):
            comps = self.comps_in(text)
            if not comps:
                continue
            t = pad(text)
            others: list[tuple] = [(self.subjects[c].display or self.subjects[c].search, "competitor", c) for c in comps]
            if self._prx:
                others += [(self.partners[m.group(1)], "partner", None) for m in self._prx.finditer(t)]
            compact = t.replace(" ", "")
            others += [(disp, "client", None) for k, disp in self.client
                       if (re.search(r"(?<![A-Za-z0-9])KSSL(?![A-Za-z0-9])", text) if k == "kssl" else news._has_name(t, compact, k))]
            for c in comps:
                for name, kind, oc in others:
                    if oc == c:
                        continue
                    out.append((c, name, kind, oc, where, text[:300]))
            if where == "title" and out:
                break                       # the headline already pairs them; the opening paragraph adds nothing new
        seen, uniq = set(), []
        for r in out:
            key = (r[0], news.norm(r[1]))
            if key not in seen:
                seen.add(key)
                uniq.append(r)
        return uniq

    def geo(self, title: str, body: str) -> list[tuple]:
        """[(competitor_id, country, {deal labels}, sentence)] where one sentence names all three."""
        out = {}
        for s in sentences((title or "") + "\n" + (body or "")[:BODY_CHARS]):
            t = pad(s)
            dw = deal_words(t)
            if not dw:
                continue
            comps = {e[0] for e in self.matcher.items if self.matcher.hit(e, t)}
            if not comps:
                continue
            ctry = self.countries.find(blank_names(t, self.all_name_keys))
            for c in comps:
                for k in ctry:
                    if (c, k) not in out:
                        out[(c, k)] = (c, k, dw, s[:400])
                    else:
                        out[(c, k)][2].update(dw)
        return list(out.values())


# ----------------------------------------------------------------------------------------------- DB
def connect():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging")
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def load_finder(cur) -> tuple[Finder, dict]:
    from backend.attribute_documents import load_subjects
    subjects, names = load_subjects(cur)
    cur.execute("SELECT DISTINCT partner_name FROM staging.competitive_partnership WHERE partner_name IS NOT NULL")
    partners = [r["partner_name"] for r in cur.fetchall()]
    cur.execute("SELECT country_name, aliases FROM staging.country_reference")
    countries = CountryFinder([(r["country_name"], list(r["aliases"] or [])) for r in cur.fetchall()])
    return Finder(subjects, partners, countries), names


def existing_pairs(cur, subjects) -> set:
    """{(competitor_id, normalised other key)} with a partnership row; a pair of two competitors counts both ways."""
    cur.execute("SELECT competitor_id::text AS cid, partner_name FROM staging.competitive_partnership")
    have = set()
    for r in cur.fetchall():
        k = partner_key(r["partner_name"]) or news.name_key(r["partner_name"] or "")
        have.add((r["cid"], k))
        for oc, s in subjects.items():            # the partner is a tracked competitor: count the reverse pair too
            if k and any(news.name_key(n) == k or (len(k) >= 6 and news.name_key(n) in k) for n in s.names):
                have.add((oc, "@" + r["cid"]))
                have.add((r["cid"], "@" + oc))
    return have


def pair_exists(have: set, cid: str, other: str, other_cid: str | None) -> bool:
    k = partner_key(other) or news.name_key(other)
    if (cid, k) in have or (other_cid and (cid, "@" + other_cid) in have):
        return True
    return any(c == cid and len(k) >= 6 and (k in x or x in k) for c, x in have if x and not x.startswith("@") and len(x) >= 6)


def existing_countries(cur) -> dict[str, set]:
    out: dict[str, set] = defaultdict(set)
    for sql in ("SELECT competitor_id::text AS cid, region AS c FROM staging.competitive_partnership",
                "SELECT competitor_id::text AS cid, region AS c FROM staging.competitive_project",
                "SELECT competitor_id::text AS cid, region AS c FROM staging.competitive_competitor_moment",
                "SELECT competitor_id::text AS cid, country AS c FROM staging.competitive_competitor_location"):
        cur.execute(sql)
        for r in cur.fetchall():
            if r["c"]:
                out[r["cid"]].add(r["c"].strip().lower())
    return out


def scan(dry_run=False, log=print) -> dict:
    from backend.attribute_documents import boilerplate_lines, clean_body
    conn = connect()
    cur = conn.cursor()
    finder, names = load_finder(cur)
    where = "cardinality(competitor_ids) > 0 AND NOT coalesce(triage ? 'blocked', false)"
    log("pass 1: page-furniture lines ...")
    bc = conn.cursor(name="cf_boiler")
    bc.itersize = 1000
    bc.execute(f"SELECT source_name, left(body_text, 12000) AS b FROM staging.source_document WHERE {where}")
    boiler = boilerplate_lines((r["source_name"], r["b"]) for r in bc)
    bc.close()
    agg: dict[str, dict] = {}

    def add(key, base, doc, snippet, words=()):
        a = agg.setdefault(key, {**base, "docs": [], "words": set(), "snippet": snippet, "sample": (doc["title"], doc["url"])})
        a["docs"].append((doc["published_at"], str(doc["doc_id"])))
        a["words"].update(words)
        if snippet and len(a["docs"]) == 1:
            a["snippet"] = snippet

    n = 0
    sc = conn.cursor(name="cf_scan")
    sc.itersize = 500
    sc.execute(f"SELECT doc_id, url, title, published_at, source_name, left(body_text, 12000) AS b FROM staging.source_document "
               f"WHERE {where} ORDER BY published_at DESC NULLS LAST, doc_id")
    for d in sc:
        n += 1
        body = clean_body(d["source_name"], d["b"] or "", boiler)
        for cid, other, kind, ocid, where_, snip in finder.pairs(d["title"] or "", body):
            add(candidate_key("pair", cid, other), {"kind": "pair", "competitor_id": cid, "other_name": other, "other_kind": kind,
                                                   "other_competitor_id": ocid, "country": None}, d, snip)
        for cid, ctry, words, sent in finder.geo(d["title"] or "", body):
            add(candidate_key("geo", cid, ctry), {"kind": "geo", "competitor_id": cid, "other_name": None, "other_kind": None,
                                                 "other_competitor_id": None, "country": ctry}, d, sent, words)
        if n % 2000 == 0:
            log(f"  {n} documents, {len(agg)} candidates", flush=True)
    sc.close()
    have = existing_pairs(cur, finder.subjects)
    have_ctry = existing_countries(cur)
    rows = []
    for key, a in agg.items():
        docs = sorted(a["docs"], key=lambda x: (x[0] or date.min), reverse=True)
        dates = [x[0] for x in docs if x[0]]
        if a["kind"] == "pair":
            exists = pair_exists(have, a["competitor_id"], a["other_name"], a["other_competitor_id"])
        else:
            exists = a["country"].lower() in have_ctry.get(a["competitor_id"], set())
        rows.append((key, a["kind"], a["competitor_id"], a["other_name"], a["other_kind"], a["other_competitor_id"], a["country"],
                     sorted(a["words"]), len({x[1] for x in docs}), [x[1] for x in docs][:MAX_DOC_IDS],
                     min(dates) if dates else None, max(dates) if dates else None, (a["sample"][0] or "")[:500], a["sample"][1],
                     (a["snippet"] or "")[:500], exists,
                     "pending" if a["kind"] == "pair" and not exists and not same_group(finder.subjects[a["competitor_id"]].names, a["other_name"])
                     else "not_needed"))
    stats = {"documents": n, "pair": sum(r[1] == "pair" for r in rows), "geo": sum(r[1] == "geo" for r in rows),
             "pair_without_row": sum(r[1] == "pair" and not r[15] for r in rows),
             "geo_new_country": sum(r[1] == "geo" and not r[15] for r in rows)}
    if not dry_run:
        import psycopg2.extras
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO staging.harvest_candidate (candidate_key, kind, competitor_id, other_name, other_kind, other_competitor_id, country,
                   deal_words, doc_count, doc_ids, first_seen, last_seen, sample_title, sample_url, snippet, has_existing_row, search_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (candidate_key) DO UPDATE SET deal_words = EXCLUDED.deal_words, doc_count = EXCLUDED.doc_count,
                   doc_ids = EXCLUDED.doc_ids, first_seen = EXCLUDED.first_seen, last_seen = EXCLUDED.last_seen,
                   sample_title = EXCLUDED.sample_title, sample_url = EXCLUDED.sample_url, snippet = EXCLUDED.snippet,
                   has_existing_row = EXCLUDED.has_existing_row,
                   search_status = CASE WHEN staging.harvest_candidate.search_status = 'searched' THEN 'searched' ELSE EXCLUDED.search_status END,
                   updated_at = now()""", rows, page_size=500)
        conn.commit()
    conn.close()
    return stats


# ----------------------------------------------------------------------------------------------- targeted search
def search_name(finder: Finder, cid: str) -> str:
    s = finder.subjects[cid]
    return s.search or s.display


def _like(s: str) -> str:
    return "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _both_named(title: str, a_keys, b_keys) -> bool:
    t = pad(title)
    compact = t.replace(" ", "")
    return any(news._has_name(t, compact, k) for k in a_keys if k) and any(news._has_name(t, compact, k) for k in b_keys if k)


def insert_raw(cur, url, title, published, lang, body, source_name, tier, triage, origin_ref=None, feed_url=None) -> bool:
    cur.execute("INSERT INTO staging.source_document (doc_id, url, source_kind, source_name, source_tier, feed_url, origin_ref, title, "
                "published_at, language, body_text, triage, status) VALUES (%s,%s,'pair_search',%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'new') "
                "ON CONFLICT (url) DO NOTHING",
                (str(uuid.uuid5(uuid.NAMESPACE_URL, url)), url, source_name, tier, feed_url, origin_ref, (title or "")[:1000] or None,
                 published, lang, body or None, json.dumps(triage)))
    return bool(cur.rowcount)


def search_dc(dc, a: str, b: str, a_keys, b_keys, known: set, per_pair: int) -> list[dict]:
    from backend.import_dc_corpus import BODY_CAP, canonical_url, effective_date
    from backend.sources import is_blocked
    cur = dc.cursor()
    cur.execute("SELECT document_id, url, title, published_at, ingested_at, language, left(main_text, %s) FROM public.documents "
                "WHERE title ILIKE %s AND title ILIKE %s AND url IS NOT NULL ORDER BY published_at DESC NULLS LAST LIMIT 40",
                (BODY_CAP, _like(a), _like(b)))
    out = []
    for doc_id, url, title, pub, ing, lang, text in cur.fetchall():
        u = canonical_url(url)
        if u in known or is_blocked(u) or not _both_named(title or "", a_keys, b_keys) or len((text or "").strip()) < 300:
            continue
        d, why, ok = effective_date(pub, ing, u, SEARCH_FROM, date.today())
        if not ok:
            continue
        known.add(u)
        out.append({"url": u, "title": title, "published": d, "lang": lang, "body": (text or "").replace("\x00", "").strip(),
                    "origin_ref": doc_id, "date_decision": why, "via": "dc_title"})
        if len(out) >= per_pair:
            break
    return out


def search_google(a: str, b: str, a_keys, b_keys, known: set, per_pair: int) -> tuple[list[dict], str]:
    from backend.harvest_sites import read_page
    from backend.sources import classify_reason, is_blocked
    q = f'"{a}" "{b}" after:{SEARCH_FROM.isoformat()}'
    try:
        items = news.rss_search(q)
    except news.RssError as e:
        return [], f"google: {e}"
    keep = []
    for it in items:
        if not _both_named(it.get("title") or "", a_keys, b_keys):
            continue
        tier, _ = classify_reason(it["source_url"], ()) if it.get("source_url") else (None, "")
        if not tier:
            continue
        keep.append(it)
    keep.sort(key=lambda i: i.get("date") or date.min, reverse=True)
    keep = keep[:per_pair]
    if not keep:
        return [], f"google: {len(items)} items, none allowlisted naming both"
    resolved = news.resolve_many([i["link"] for i in keep], 4)
    out = []
    for it in keep:
        url = news.clean_url(resolved.get(it["link"], ("", ""))[0] or "")
        if not url or url in known or is_blocked(url) or news.is_homepage(url):
            continue
        tier, _ = classify_reason(url, ())
        if not tier:
            continue
        r = news.http(url)
        page = read_page(r.body.decode("utf-8", "replace"), r.url or url) if r.status == 200 and r.body else None
        known.add(url)
        out.append({"url": url, "title": (page.title if page and page.title else it["title"]), "lang": page.lang if page else None,
                    "published": (page.date if page and page.date else it.get("date")), "body": page.body if page else "",
                    "tier": tier, "via": "google_news", "page_note": "" if page else f"http {r.status}", "publisher": it.get("source")})
    return out, f"google: {len(items)} items, {len(keep)} kept"


def search(limit=None, per_pair=6, use_dc=True, use_google=True, dry_run=False, log=print) -> dict:
    from backend.sources import classify, host_of
    conn = connect()
    cur = conn.cursor()
    finder, names = load_finder(cur)
    cur.execute("SELECT * FROM staging.harvest_candidate WHERE kind = 'pair' AND NOT has_existing_row AND search_status = 'pending' "
                "ORDER BY doc_count DESC, last_seen DESC NULLS LAST, candidate_key" + (" LIMIT %d" % int(limit) if limit else ""))
    cands = cur.fetchall()
    cur.execute("SELECT url FROM staging.source_document")
    known = {r["url"] for r in cur.fetchall()}
    dc = None
    if use_dc:
        from backend.import_dc_corpus import connect_dc
        dc = connect_dc()
    stats = Counter()
    for i, c in enumerate(cands, 1):
        cid = str(c["competitor_id"])
        a = search_name(finder, cid)
        b = search_name(finder, str(c["other_competitor_id"])) if c["other_competitor_id"] else c["other_name"]
        a_keys = [news.name_key(n) for n in finder.subjects[cid].names]
        b_keys = ([news.name_key(n) for n in finder.subjects[str(c["other_competitor_id"])].names] if c["other_competitor_id"]
                  else [partner_key(b) or news.name_key(b)])
        found, notes = [], []
        if dc is not None and len(a) >= 3 and len(b) >= 3:
            try:
                got = search_dc(dc, a, b, a_keys, b_keys, known, per_pair)
                found += got
                notes.append(f"dc: {len(got)}")
            except Exception as e:                       # a slow / failed DC query is noted, the pair stays searchable
                notes.append(f"dc failed: {type(e).__name__}")
                dc.rollback() if not dc.autocommit else None
        if use_google:
            got, note = search_google(a, b, a_keys, b_keys, known, per_pair)
            found += got
            notes.append(note)
            if news._rss_state["streak"] >= 3:
                log("  Google News keeps refusing (503 / 429): stopping the Google part; the rest stays pending")
                use_google = False
        stored = 0
        for f in found:
            tri = {"harvester": HARVESTER, "search": {"pair": [a, b], "via": f["via"], "candidate_key": c["candidate_key"]},
                   "date_decision": f.get("date_decision"), "page_note": f.get("page_note") or None, "publisher": f.get("publisher")}
            if not dry_run:
                stored += insert_raw(cur, f["url"], f["title"], f["published"], f["lang"], f["body"], host_of(f["url"]),
                                     f.get("tier") or classify(f["url"], ()) or "unlisted", tri, f.get("origin_ref"),
                                     "dc:mallory/documents" if f["via"] == "dc_title" else "google_news_rss")
            stats[f["via"]] += 1
        stats["pairs"] += 1
        stats["stored"] += stored
        if not dry_run:
            cur.execute("UPDATE staging.harvest_candidate SET search_status = 'searched', search_found = %s, search_note = %s, updated_at = now() "
                        "WHERE candidate_key = %s", (stored, "; ".join(notes)[:500], c["candidate_key"]))
            conn.commit()
        log(f"  [{i}/{len(cands)}] {a} + {b}: {len(found)} found, {stored} stored ({'; '.join(notes)})", flush=True)
    conn.close()
    if dc is not None:
        dc.close()
    return dict(stats)


def report() -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT c.display_name, count(*) FILTER (WHERE h.kind='pair') pairs, count(*) FILTER (WHERE h.kind='pair' AND NOT h.has_existing_row) pairs_new,
                          count(*) FILTER (WHERE h.kind='geo') geo, count(*) FILTER (WHERE h.kind='geo' AND NOT h.has_existing_row) geo_new,
                          coalesce(sum(h.search_found),0) found
                   FROM staging.competitive_competitor c LEFT JOIN staging.harvest_candidate h USING (competitor_id)
                   GROUP BY 1 ORDER BY 1""")
    print(f"{'competitor':36} pairs  (no row)  geo  (new country)  search stored")
    for r in cur.fetchall():
        print(f"{r['display_name']:36} {r['pairs']:5} {r['pairs_new']:8} {r['geo']:5} {r['geo_new']:13} {r['found']:8}")
    conn.close()


# ----------------------------------------------------------------------------------------------- selftest
def _selftest() -> None:
    rows = {"c-1": {"search_name": "Nordvik Defence", "aliases": "Nordvik", "exclude_terms": "Nordvik Foods"},
            "c-2": {"search_name": "Veland Arms", "match_terms_needed": "Veland: howitzer / army"},
            "c-3": {"search_name": "Arkadia Industries India"}}
    subj = {cid: news.subject_for(cid, r["search_name"], rows=rows) for cid, r in rows.items()}
    cf = CountryFinder([("India", []), ("Poland", []), ("United States", ["USA"]), ("Netherlands", ["Holland"])])
    f = Finder(subj, ["Kestrel Optics Ltd", "Ministry of Defence (Poland)", "Indian Army"], cf, client_names=["Kalyani Group", "KSSL"])
    assert partner_key("Ministry of Defence (Poland)") == "" and partner_key("Kestrel Optics Ltd") == "kestrel optics"
    assert partner_key("Indian Army") == "" and partner_key("ABC") == ""
    p = f.pairs("Nordvik Defence and Veland Arms sign teaming pact", "")
    assert {(x[0], x[2]) for x in p} == {("c-1", "competitor"), ("c-2", "competitor")} and all(x[4] == "title" for x in p)
    p = f.pairs("Teaming pact signed", "Nordvik and Kestrel Optics will co-develop a sight. " + "x " * 600 + "Veland Arms")
    assert [(x[0], x[1], x[2], x[4]) for x in p] == [("c-1", "Kestrel Optics Ltd", "partner", "opening")]      # Veland is past the opening
    assert f.pairs("Nordvik Foods opens a plant", "") == []                                                  # masked sister company
    p = f.pairs("KSSL and Nordvik Defence form a JV", "")
    assert ("c-1", "KSSL", "client") in [(x[0], x[1], x[2]) for x in p]
    g = f.geo("Nordvik wins a USA order", "The Indian Army has ordered 40 guns from Nordvik Defence. Nordvik also visited Poland.")
    got = {(x[0], x[1]): x[2] for x in g}
    assert got == {("c-1", "United States"): {"order"}, ("c-1", "India"): {"order"}}, got          # Poland: no deal word in that sentence
    g = f.geo("Arkadia Industries India signs a contract", "")
    assert g == []                                                                                  # "India" inside the company name is not a country
    g = f.geo("Arkadia Industries India delivers fuzes to Holland", "")
    assert [(x[0], x[1]) for x in g] == [("c-3", "Netherlands")]
    assert deal_words(pad("a joint venture and an MoU")) == {"jv", "agreement"} and deal_words(pad("orderly")) == set()
    assert candidate_key("geo", "c-1", "United States") == "geo|c-1|united states"
    have = {("c-1", "kestrel optics"), ("c-1", "@c-2"), ("c-2", "@c-1")}
    assert pair_exists(have, "c-1", "Kestrel Optics Ltd", None) and pair_exists(have, "c-2", "Nordvik Defence", "c-1")
    assert pair_exists(have, "c-1", "Kestrel Optics Systems", None) and not pair_exists(have, "c-1", "Falcon Works", None)
    assert same_group(["KNDS Germany", "KNDS"], "Nexter (KNDS France)") and same_group(["General Dynamics"], "General Dynamics European Land Systems")
    assert same_group(["Adani Defence", "Adani Defence & Aerospace"], "Adani Group") and not same_group(["Rheinmetall"], "Leonardo")
    assert _like("50%_x") == "%50\\%\\_x%"
    assert _both_named("Nordvik and Kestrel Optics sign MoU", ["nordvik"], ["kestrel optics"])
    assert not _both_named("Nordvik signs MoU", ["nordvik"], ["kestrel optics"])
    assert len(sentences("One sentence here. Two sentences there!\nHeadline line text")) == 3
    print("candidate_finder self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.candidate_finder", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true")
    g.add_argument("--scan", action="store_true")
    g.add_argument("--search", action="store_true")
    g.add_argument("--report", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--per-pair", type=int, default=6)
    ap.add_argument("--no-dc", action="store_true")
    ap.add_argument("--no-google", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
    elif a.scan:
        print(scan(a.dry_run))
    elif a.search:
        print(search(a.limit, a.per_pair, not a.no_dc, not a.no_google, a.dry_run))
    else:
        report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
