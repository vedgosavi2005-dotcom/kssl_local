"""Attribution (code, free): staging.source_document -> competitor_ids / mentions_client / status.

    python -m backend.attribute_documents --selftest            (no DB, fictional names)
    python -m backend.attribute_documents --dry-run             (counts only)
    python -m backend.attribute_documents                       (write: unattributed rows, status 'new')
    python -m backend.attribute_documents --check-dc            (precision / recall against the DC corpus attribution; no write)

Rule (the same as backend/news.py for a headline): a document is about a competitor when its title or the first ~2,000 characters
of its body name the competitor -- an alias from db/news_aliases.csv (+ the names stored in the DB) always counts, a conditional
alias counts only with one of its co-terms, and the masked phrases (sister companies: "Hanwha Ocean", "L&T Finance") are blanked
out first. A company's own newsroom (source_kind newsroom, source_name = the company) always counts for that company.
mentions_client: the text names KSSL / Kalyani / Bharat Forge. status 'attributed' (>= 1 competitor) or 'no_match'.
Rows already 'attributed' (the DC corpus) are never touched. Local kssl_staging only.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter

from backend import news

BODY_CHARS = 2000
# the client: KSSL (an upper-case word, so "kssl" in a URL slug does not count twice), Kalyani, Bharat Forge
CLIENT_NAMES = ["KSSL", "Kalyani Strategic Systems", "Kalyani Group", "Kalyani Defence", "Kalyani Powertrain", "Kalyani", "Bharat Forge", "Baba Kalyani"]


GENERIC = {"naval", "general", "national", "global", "solar", "premier", "military", "land", "air", "sea", "defence", "defense", "united"}


def name_key_safe(name: str) -> str:
    """news.name_key drops a trailing 'Group' ("Naval Group" -> "naval"); when what is left is one ordinary word, keep the whole phrase."""
    k = news.name_key(name)
    return news.norm(name) if k in GENERIC else k


BOILER_MIN_DOCS = 5          # a line that repeats in this many documents of one source is page furniture (a "latest news" side list), not article text
BOILER_MIN_LEN = 12


def line_key(line: str) -> str:
    return " ".join(line.casefold().split())


def boilerplate_lines(rows) -> set:
    """rows: (source_name, body_text). {(source_name, line_key)} of lines seen in >= BOILER_MIN_DOCS documents of that source."""
    seen: Counter = Counter()
    for src, body in rows:
        for k in {line_key(x) for x in (body or "").split("\n")}:
            if len(k) >= BOILER_MIN_LEN:
                seen[(src, k)] += 1
    return {k for k, n in seen.items() if n >= BOILER_MIN_DOCS}


def clean_body(src, body: str, boiler: set) -> str:
    """The body without page-furniture lines (a Army Recognition page opens with a list of the site's latest headlines)."""
    return "\n".join(x for x in (body or "").split("\n") if (src, line_key(x)) not in boiler)


class Matcher:
    """Pre-normalised subjects: one text normalisation per document, then a cheap check per competitor."""

    def __init__(self, subjects: dict[str, news.Subject], client_names=CLIENT_NAMES):
        self.items = []
        for cid, s in subjects.items():
            names = [name_key_safe(n) for n in s.names if news.name_key(n)]
            cond = [(news.name_key(a), [news.norm(t) for t in terms if news.norm(t)]) for a, terms in s.cond if news.name_key(a)]
            mask = [news.norm(m) for m in s.mask if news.norm(m)]
            self.items.append((cid, names, cond, [re.compile(rf"(?<!\S){re.escape(m)}(?!\S)") for m in mask]))
        self.client = [news.name_key(n) for n in client_names if news.name_key(n)]

    @staticmethod
    def _has(t: str, compact: str, key: str) -> bool:
        return news._has_name(t, compact, key)

    def hit(self, entry, t_plain: str) -> bool:
        cid, names, cond, masks = entry
        t = t_plain
        for rx in masks:
            t = rx.sub(" ", t)
        compact = t.replace(" ", "")
        if any(self._has(t, compact, k) for k in names):
            return True
        for key, terms in cond:
            if self._has(t, compact, key) and any(f" {k} " in t or f" {k}s " in t for k in terms):
                return True
        return False

    def competitors(self, title: str, body: str) -> dict[str, str]:
        """{competitor_id: 'title' | 'body'} for the competitors named."""
        tt = " " + news.norm(title) + " "
        full = " " + news.norm((title or "") + " . " + (body or "")[:BODY_CHARS]) + " "
        out = {}
        for entry in self.items:
            if self.hit(entry, tt):
                out[entry[0]] = "title"
            elif self.hit(entry, full):
                out[entry[0]] = "body"
        return out

    def mentions_client(self, title: str, body: str) -> bool:
        text = (title or "") + " . " + (body or "")[:BODY_CHARS]
        t = " " + news.norm(text) + " "
        compact = t.replace(" ", "")
        for k in self.client:
            if k == "kssl":
                if re.search(r"(?<![A-Za-z0-9])KSSL(?![A-Za-z0-9])", text):
                    return True
            elif news._has_name(t, compact, k):
                return True
        return False


def load_subjects(cur) -> tuple[dict[str, news.Subject], dict[str, str]]:
    cur.execute("SELECT competitor_id::text AS cid, display_name, coalesce(legal_name, '') AS legal, coalesce(short_name, '') AS short FROM staging.competitive_competitor")
    rows = cur.fetchall()
    return ({r["cid"]: news.subject_for(r["cid"], r["display_name"], r["legal"], r["short"]) for r in rows},
            {r["cid"]: r["display_name"] for r in rows})


def own_site_competitors(cur, subjects) -> dict[str, str]:
    """{source_name lower: competitor_id} for newsroom sources that are a tracked competitor (source_name matches its names)."""
    cur.execute("SELECT DISTINCT source_name FROM staging.source_document WHERE source_kind = 'newsroom' AND source_name IS NOT NULL")
    m = Matcher(subjects)
    out = {}
    for r in cur.fetchall():
        hits = m.competitors(r["source_name"], "")
        if len(hits) == 1:
            out[r["source_name"].lower()] = next(iter(hits))
    return out


def run(dry_run=False, check_dc=False, batch=500) -> dict:
    import psycopg2
    import psycopg2.extras
    dsn = os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging"
    conn = psycopg2.connect(dsn)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    cur = conn.cursor()
    subjects, names = load_subjects(cur)
    matcher = Matcher(subjects)
    own = own_site_competitors(cur, subjects)
    where = "status = 'new'" if not check_dc else "source_kind = 'dc_corpus'"
    cur.execute(f"SELECT count(*) AS n FROM staging.source_document WHERE {where}")
    total = cur.fetchone()["n"]
    print("pass 1: page-furniture lines ...", flush=True)
    bcur = conn.cursor(name="boiler")
    bcur.itersize = 500
    bcur.execute(f"SELECT source_name, left(body_text, 12000) FROM staging.source_document WHERE {where}")
    boiler = boilerplate_lines((r[0] if not isinstance(r, dict) else r["source_name"], r[1] if not isinstance(r, dict) else r["left"]) for r in bcur)
    bcur.close()
    print(f"  {len(boiler)} furniture lines", flush=True)
    stats = {"docs": 0, "attributed": 0, "no_match": 0, "mentions_client": 0, "per_competitor": Counter(), "title": Counter(), "own_site": Counter()}
    dc = {"tp": 0, "fp": 0, "fn": 0, "docs_agree": 0}
    last = None
    while True:
        cur.execute(f"SELECT doc_id, source_kind, source_name, title, left(body_text, 12000) AS body, competitor_ids::text[] AS existing "
                    f"FROM staging.source_document WHERE {where} AND (%s::uuid IS NULL OR doc_id > %s::uuid) ORDER BY doc_id LIMIT %s", (last, last, batch))
        rows = cur.fetchall()
        if not rows:
            break
        updates = []
        for r in rows:
            last = r["doc_id"]
            body = clean_body(r["source_name"], r["body"] or "", boiler)
            hits = matcher.competitors(r["title"] or "", body)
            if r["source_kind"] == "newsroom" and (r["source_name"] or "").lower() in own:
                hits.setdefault(own[r["source_name"].lower()], "own site")
            mc = matcher.mentions_client(r["title"] or "", body)
            stats["docs"] += 1
            if check_dc:
                have, got = set(r["existing"] or []), set(hits)
                dc["tp"] += len(have & got); dc["fp"] += len(got - have); dc["fn"] += len(have - got)
                dc["docs_agree"] += have == got
                continue
            stats["attributed" if hits else "no_match"] += 1
            stats["mentions_client"] += mc
            for cid, how in hits.items():
                stats["per_competitor"][names[cid]] += 1
                (stats["title"] if how == "title" else stats["own_site"] if how == "own site" else Counter())[names[cid]] += 1
            updates.append((list(hits), mc, "attributed" if hits else "no_match", psycopg2.extras.Json({"attrib": hits}), r["doc_id"]))
        if updates and not dry_run:
            psycopg2.extras.execute_batch(cur, """UPDATE staging.source_document SET competitor_ids = %s::uuid[], mentions_client = %s, status = %s,
                    triage = coalesce(triage, '{}'::jsonb) || %s WHERE doc_id = %s""", updates, page_size=200)
            conn.commit()
        print(f"  {stats['docs']}/{total}", end="\r", flush=True)
    conn.rollback() if dry_run or check_dc else conn.commit()
    conn.close()
    return {"stats": stats, "dc_check": dc}


def _selftest() -> None:
    # fictional companies: Nordvik Defence (alias Nordvik; masked sister Nordvik Foods), Veland Arms (bare 'Veland' needs a co-term)
    rows = {"c-1": {"competitor_id": "c-1", "search_name": "Nordvik Defence", "aliases": "Nordvik | NV Arms", "exclude_terms": "Nordvik Foods | Nordvik Bank"},
            "c-2": {"competitor_id": "c-2", "search_name": "Veland Arms", "match_terms_needed": "Veland: howitzer / army / artillery", "exclude_terms": "Veland Ocean"},
            "c-3": {"competitor_id": "c-3", "search_name": "Kastor Works", "aliases": "Kastor"},
            "c-4": {"competitor_id": "c-4", "search_name": "Land Group"}}
    subj = {cid: news.subject_for(cid, r["search_name"], rows=rows) for cid, r in rows.items()}
    m = Matcher(subj)
    assert m.competitors("Nordvik Defence wins an order", "") == {"c-1": "title"}
    assert m.competitors("Defence order of the week", "The firm Nordvik delivered 12 guns.") == {"c-1": "body"}
    assert m.competitors("Nordvik Foods opens a plant", "Nordvik Bank also reports profit") == {}                        # masked sister companies
    assert m.competitors("Veland Ocean launches a ship", "") == {}                                                         # masked, no co-term
    assert m.competitors("Veland orders guns", "") == {}                                                                  # conditional alias without a co-term
    assert m.competitors("Veland army orders guns", "") == {"c-2": "title"}                                               # with a co-term
    assert m.competitors("Defence digest", "Veland Arms and Kastor Works signed a teaming agreement.") == {"c-2": "body", "c-3": "body"}
    assert m.competitors("Defence digest", "x" * 3000 + " Nordvik") == {}                                                 # only the first 2,000 characters
    assert m.competitors("Kastorama sells flowers", "") == {}                                                              # whole words only
    assert m.competitors("Land forces exercise in the north", "") == {} and m.competitors("Land Group delivers vehicles", "") == {"c-4": "title"}   # 'Group' is not dropped when one common word is left
    assert m.mentions_client("KSSL signs a deal", "") and m.mentions_client("x", "Baba Kalyani said") and m.mentions_client("x", "Bharat Forge Ltd results")
    assert not m.mentions_client("Kssl-style naming in a url", "kssl lower case") and not m.mentions_client("Nordvik wins", "no client here")
    bp = boilerplate_lines([("site", f"Latest headline one is here\nStory number {i} is unique to its page\nWire: Nordvik wins") for i in range(6)] + [("other", "Wire: Nordvik wins")])
    assert ("site", "wire: nordvik wins") in bp and ("other", "wire: nordvik wins") not in bp and not any("unique" in k[1] for k in bp)
    assert clean_body("site", "Wire: Nordvik wins\nVeland army buys guns", bp) == "Veland army buys guns"
    print("attribute_documents self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.attribute_documents", description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-dc", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
        return 0
    out = run(a.dry_run, a.check_dc)
    st, dc = out["stats"], out["dc_check"]
    print()
    if a.check_dc:
        p = dc["tp"] / max(1, dc["tp"] + dc["fp"]); r = dc["tp"] / max(1, dc["tp"] + dc["fn"])
        print(f"DC corpus check: docs {st['docs']}, same set {dc['docs_agree']}, tp {dc['tp']} fp {dc['fp']} fn {dc['fn']}, precision {p:.2f} recall {r:.2f}")
        return 0
    print(f"docs {st['docs']}: attributed {st['attributed']}, no_match {st['no_match']}, mention the client {st['mentions_client']}" + (" (dry run, nothing written)" if a.dry_run else ""))
    for name, n in st["per_competitor"].most_common():
        print(f"  {name:36} {n:6}  (title {st['title'][name]}, own newsroom {st['own_site'][name]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
