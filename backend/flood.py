"""Lane A flood driver: raw documents -> news stories -> signal cards.

    python -m backend.flood --selftest
    python -m backend.flood candidates [--dry-run]       source_document (route has 'signal', attributed) -> staging.news_candidate
    python -m backend.flood news [--competitor NAME] [--max N] [--workers 4]     news prompt per competitor-month (newest month first)
    python -m backend.flood signal [--competitor NAME] [--max N] [--budget USD] [--workers 4]   signal prompt per new story (newest first)
    python -m backend.flood status                       counts, spend

Order: competitors in backend/flood_order.PRIORITY (Indian artillery / ammunition rivals first), newest first inside a competitor.
Nothing is sent to a prompt that is not in staging; blocked sources (wikis, blogs) never become candidates. Local kssl_staging only.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend import sources
from backend.flood_order import PRIORITY, order_index

DSN = os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging"
MIN_BODY = 600                      # the signal run reads the raw layer when the text is at least this long (signal.yml documents)
DC_RELEVANCE = 0.9                  # DC corpus: a company counts for a document at this relevance or more
MAX_COMPETITORS_PER_DOC = 2
BODY_ONLY_MAX = 2                   # a document that names competitors only in its body counts for them only when there are at most this many
SIGNAL_COST_CAP = 400.0


def connect():
    import psycopg2
    import psycopg2.extras
    c = psycopg2.connect(DSN)
    c.cursor_factory = psycopg2.extras.RealDictCursor
    return c


# ---- which competitor(s) a document is about --------------------------------------------------------------------

def pick_competitors(source_kind: str, competitor_ids: list, triage: dict) -> list:
    """The competitors a document will be a news candidate for (at most MAX_COMPETITORS_PER_DOC).
    Site documents: where the title / own newsroom names it (attrib 'title' / 'own site'); else, if only the body does and there
    are few, those. DC corpus: companies with relevance >= DC_RELEVANCE (most mentions first); if none, the single attributed one."""
    triage = triage or {}
    cids = [str(c) for c in competitor_ids or []]
    if not cids:
        return []
    if source_kind == "dc_corpus":
        comp = triage.get("companies") or {}
        rated = sorted(((c, v) for c, v in comp.items() if c in cids and float((v or {}).get("relevance") or 0) >= DC_RELEVANCE),
                       key=lambda kv: (-int((kv[1] or {}).get("mentions") or 0), kv[0]))
        if rated:
            return [c for c, _ in rated][:MAX_COMPETITORS_PER_DOC]
        return cids if len(cids) == 1 else []
    attrib = triage.get("attrib") or {}
    strong = [c for c in cids if attrib.get(c) in ("title", "own site")]
    if strong:
        return strong[:MAX_COMPETITORS_PER_DOC]
    return cids if len(cids) <= BODY_ONLY_MAX else []


def candidate_id(competitor_id: str, url: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{competitor_id}|{url}"))


def make_candidate(doc: dict, competitor_id: str) -> tuple:
    via = "dc" if doc["source_kind"] == "dc_corpus" else "site"
    return (candidate_id(competitor_id, doc["url"]), competitor_id, (doc["title"] or "").strip()[:300], doc["url"], doc["published_at"],
            (doc["source_name"] or None) and doc["source_name"][:200], doc["source_tier"], via)


def cmd_candidates(dry_run: bool) -> None:
    import psycopg2.extras
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT doc_id::text AS id, url, source_kind, source_name, source_tier, title, published_at, competitor_ids::text[] AS cids, triage
                   FROM staging.source_document
                   WHERE triage->'route' ? 'signal' AND cardinality(competitor_ids) > 0 AND length(coalesce(body_text, '')) >= %s
                     AND NOT (processed_by ? 'flood_candidate') ORDER BY published_at DESC NULLS LAST""", (MIN_BODY,))
    docs = cur.fetchall()
    rows, ids, skipped = [], [], {"blocked": 0, "no_competitor": 0, "no_title": 0}
    for d in docs:
        if sources.is_blocked(d["url"]):
            skipped["blocked"] += 1
            continue
        if not (d["title"] or "").strip():
            skipped["no_title"] += 1
            continue
        picks = pick_competitors(d["source_kind"], d["cids"], d["triage"])
        if not picks:
            skipped["no_competitor"] += 1
            continue
        rows += [make_candidate(d, c) for c in picks]
        ids.append(d["id"])
    print(f"{len(docs)} routed-signal documents -> {len(rows)} candidates from {len(ids)} documents; skipped {skipped}")
    if dry_run or not rows:
        conn.rollback()
        return
    psycopg2.extras.execute_values(cur, """INSERT INTO staging.news_candidate
        (candidate_id, competitor_id, headline, article_url, published_date, publisher, source_tier, match_via) VALUES %s
        ON CONFLICT DO NOTHING""", rows, page_size=500)
    cur.execute("UPDATE staging.source_document SET processed_by = processed_by || jsonb_build_object('flood_candidate', now()::text) WHERE doc_id = ANY(%s::uuid[])", (ids,))
    conn.commit()
    print("written")


# ---- running the prompts ------------------------------------------------------------------------------------------

def spent(cur, ids=("news", "signal", "triage_route", "client_subtype")) -> float:
    cur.execute("SELECT coalesce(sum(cost_usd), 0) AS s FROM staging.prompt_run WHERE prompt_id = ANY(%s)", (list(ids),))
    return float(cur.fetchone()["s"])


def run_prompt(prompt: str, key: str, extra=()) -> str:
    env = {**os.environ, "KSSL_STAGING_DSN": DSN, "PYTHONIOENCODING": "utf-8"}
    extra = tuple(extra) if "--rerun" in extra else (*extra, "--rerun")      # the caller already chose the subjects; a failed one must not wait out the cooldown
    p = subprocess.run([sys.executable, "-m", "prompts.run", prompt, "--subject", key, *extra], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=1500)
    return (p.stdout.strip().splitlines() or [p.stderr.strip()[-200:]])[-1] if (p.stdout or p.stderr) else "no output"


LIMIT_STOP = threading.Event()          # the model account hit its usage limit: every worker stops cleanly (no hundreds of failed runs)


def hit_limit(out: str) -> bool:
    t = (out or "").lower()
    return "usage limit" in t or "weekly limit" in t or "rate limit" in t or "hit your" in t and "limit" in t


def last_signal_run(cur, key: str):
    cur.execute("SELECT run_id, status, error, details->'rejected' AS rejected, loaded FROM staging.prompt_run WHERE prompt_id = 'signal' AND subject_key = %s "
                "ORDER BY started_at DESC LIMIT 1", (key,))
    return cur.fetchone()


def signal_one(key: str) -> str:
    """One signal run. A run that loaded only product news because the signal card was rejected (for example fewer than 3 key points
    after the restatement check) is tried once more; if it is rejected again the run is logged as 'rejected' with the reason, never as loaded."""
    out = run_prompt("signal", key)
    if hit_limit(out):
        LIMIT_STOP.set()
        return out
    conn = connect()
    try:
        cur = conn.cursor()
        r = last_signal_run(cur, key)
        for attempt in (1, 2):
            if not r or r["status"] != "loaded" or any(c.get("table") == "competitive_signal" for c in (r["loaded"] or [])) or not r["rejected"]:
                return out
            if attempt == 1:
                out = "retry: " + run_prompt("signal", key, ("--rerun",))
                conn.rollback()
                r = last_signal_run(cur, key)
            else:
                cur.execute("UPDATE staging.prompt_run SET status = 'rejected', error = %s WHERE run_id = %s", ("signal card rejected twice: " + "; ".join(r["rejected"])[:300], r["run_id"]))
                conn.commit()
                return out + " [logged as rejected: signal card refused twice]"
        return out
    finally:
        conn.close()


def news_batches(cur, competitor: str | None):
    cur.execute("""SELECT c.display_name AS name, c.competitor_id::text || '@' || to_char(m.month, 'YYYY-MM') || '@' || to_char(m.found, 'YYYYMMDDHH24MISS') AS key,
                          m.month, m.new_count
                   FROM (SELECT n.competitor_id, date_trunc('month', coalesce(n.published_date, n.found_at::date))::date AS month,
                                max(n.found_at) AS found, count(*) AS new_count
                         FROM staging.news_candidate n WHERE n.status = 'new' GROUP BY 1, 2) m
                   JOIN staging.competitive_competitor c ON c.competitor_id = m.competitor_id""")
    rows = [r for r in cur.fetchall() if not competitor or r["name"] == competitor]
    rows.sort(key=lambda r: (order_index(r["name"]), -r["month"].toordinal()))
    return rows


def pending_done(cur, prompt: str, version_sql: str, keys: list) -> set:
    cur.execute("SELECT DISTINCT subject_key FROM staging.prompt_run WHERE prompt_id = %s AND status IN ('loaded','skipped','rejected') AND subject_key = ANY(%s)", (prompt, keys))
    return {r["subject_key"] for r in cur.fetchall()}


def cmd_news(competitor, maxn, workers) -> None:
    conn = connect()
    cur = conn.cursor()
    batches = news_batches(cur, competitor)[: maxn or None]
    conn.rollback()
    print(f"{len(batches)} competitor-month batches")
    by_comp: dict = {}
    for b in batches:
        by_comp.setdefault(b["name"], []).append(b)          # one worker per competitor at a time: months go in order inside it

    def work(name):
        for b in by_comp[name]:
            if LIMIT_STOP.is_set():
                return
            out = run_prompt("news", b["key"])
            if hit_limit(out):
                LIMIT_STOP.set()
                print("MODEL LIMIT reached: stopping the news pass cleanly", flush=True)
            print(f"  {name} {b['month']:%Y-%m} ({b['new_count']}): {out[:150]}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, n) for n in sorted(by_comp, key=order_index)]):
            f.result()


def signal_subjects(cur, competitor: str | None):
    cur.execute("""SELECT n.article_id::text AS key, c.display_name AS name, n.published_date AS day, n.headline
                   FROM staging.competitive_news_article n JOIN staging.competitive_competitor c ON c.competitor_id = n.competitor_id
                   WHERE n.article_url IS NOT NULL AND n.category IS NOT NULL AND n.category NOT IN ('Stock & market', 'Non-defence business', 'Other')
                     AND NOT EXISTS (SELECT 1 FROM staging.fact_source f WHERE f.table_name = 'competitive_news_article' AND f.column_name = 'not_about_company'
                                     AND f.row_id = n.article_id::text)
                     AND NOT EXISTS (SELECT 1 FROM staging.prompt_run r WHERE r.prompt_id = 'signal' AND r.subject_key = n.article_id::text
                                     AND r.status IN ('loaded','skipped','rejected') AND r.prompt_version = %s)""", (SIGNAL_VERSION(),))
    rows = [r for r in cur.fetchall() if not competitor or r["name"] == competitor]
    rows.sort(key=lambda r: (order_index(r["name"]), -(r["day"].toordinal() if r["day"] else 0)))
    return rows


def SIGNAL_VERSION() -> str:
    from prompts import render
    return str(render.load_prompt("signal")["version"])


def cmd_signal(competitor, maxn, workers, budget) -> None:
    conn = connect()
    cur = conn.cursor()
    subs = signal_subjects(cur, competitor)[: maxn or None]
    start = spent(cur)
    conn.rollback()
    print(f"{len(subs)} stories to signal; lane spend so far ${start:.2f}, cap ${budget:.0f}")
    lock = threading.Lock()
    stop = threading.Event()
    state = {"n": 0}

    def work(s):
        if stop.is_set() or LIMIT_STOP.is_set():
            return
        out = signal_one(s["key"])
        with lock:
            state["n"] += 1
            print(f"  [{state['n']}] {s['name'][:22]} {s['day']} {out[:170]}", flush=True)
            if LIMIT_STOP.is_set():
                print("MODEL LIMIT reached: stopping the signal pass cleanly", flush=True)
                stop.set()
            if state["n"] % 10 == 0:
                c2 = connect()
                tot = spent(c2.cursor())
                c2.close()
                if tot >= budget:
                    print(f"BUDGET reached: ${tot:.2f} >= ${budget:.0f}; stopping", flush=True)
                    stop.set()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, subs))


def cmd_status() -> None:
    conn = connect()
    cur = conn.cursor()
    for sql in ("SELECT status, count(*) AS n FROM staging.news_candidate GROUP BY 1",
                "SELECT count(*) AS n FROM staging.competitive_news_article", "SELECT count(*) AS n FROM staging.competitive_signal",
                "SELECT classification, count(*) AS n FROM staging.competitive_signal GROUP BY 1",
                "SELECT count(*) AS n FROM staging.competitive_product_news",
                "SELECT prompt_id, status, count(*) AS n, round(sum(cost_usd)::numeric, 2) AS usd FROM staging.prompt_run WHERE prompt_id IN ('news','signal','triage_route','client_subtype') GROUP BY 1, 2 ORDER BY 1, 2"):
        cur.execute(sql)
        for r in cur.fetchall():
            print("  ", dict(r))
    print(f"lane spend ${spent(cur):.2f}")


def _selftest() -> None:
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    dc = {"companies": {a: {"relevance": 1.0, "mentions": 5}, b: {"relevance": 0.4, "mentions": 9}}}
    assert pick_competitors("dc_corpus", [a, b], dc) == [a]
    assert pick_competitors("dc_corpus", [a], {}) == [a] and pick_competitors("dc_corpus", [a, b], {}) == []
    assert pick_competitors("trade_press", [a, b], {"attrib": {a: "body", b: "title"}}) == [b]
    assert pick_competitors("trade_press", [a], {"attrib": {a: "body"}}) == [a] and pick_competitors("trade_press", [a, b, "c"], {"attrib": {}}) == []
    assert pick_competitors("newsroom", [a], {"attrib": {a: "own site"}}) == [a] and pick_competitors("gov", [], None) == []
    assert candidate_id(a, "https://x.test/1") == candidate_id(a, "https://x.test/1") != candidate_id(b, "https://x.test/1")
    assert make_candidate({"source_kind": "dc_corpus", "title": " T ", "url": "u", "published_at": None, "source_name": "S", "source_tier": "primary"}, a)[-1] == "dc"
    assert make_candidate({"source_kind": "gov", "title": "T", "url": "u", "published_at": None, "source_name": None, "source_tier": None}, a)[-1] == "site"
    assert order_index("Adani Defence & Aerospace") == 0 and order_index("unknown co") == len(PRIORITY)
    print("flood self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.flood", description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", choices=["candidates", "news", "signal", "status"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--competitor")
    ap.add_argument("--max", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=SIGNAL_COST_CAP)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
    elif a.cmd == "candidates":
        cmd_candidates(a.dry_run)
    elif a.cmd == "news":
        cmd_news(a.competitor, a.max, a.workers)
    elif a.cmd == "signal":
        cmd_signal(a.competitor, a.max, a.workers, a.budget)
    elif a.cmd == "status":
        cmd_status()
    else:
        ap.error("give a command")
    return 0


if __name__ == "__main__":
    sys.exit(main())
