"""Stage 1 of the two-stage triage (cheap): which prompts should read a raw document?

    python -m backend.triage_routes --selftest                 (no DB, no model)
    python -m backend.triage_routes --limit 200 --dry-run      (call the model, print, do not write)
    python -m backend.triage_routes [--limit N] [--workers 6]  (all documents without a route, priority order)
    python -m backend.triage_routes --report                   (counts per route / source)

One Haiku call = many documents (headline + first ~400 characters of the cleaned body). The answer is merged into
staging.source_document.triage (jsonb) under
    route         list of routes from ROUTES (never empty; ['none'] alone when nothing applies)
    route_reason  one short sentence
    route_model   model id
    route_at      timestamp
Existing keys (the DC corpus scores: queue, signals, hints, companies ...) are kept: this is a jsonb merge (||), never an overwrite.
Lanes B, C, D read `route` to pick their documents. Priority: dc_corpus P0/P1, newsroom, gov, trade press, then dc_corpus P2; newest first.
Spend is logged to staging.prompt_run (prompt_id 'triage_route'). Local kssl_staging only. Resumable: a document with a route is skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

MODEL = "claude-haiku-5-5"
PROMPT_VERSION = "1"
ROUTES = ["signal", "moment", "partnership", "project", "geo", "tech", "opportunity", "global_requirement", "spec", "none"]
BATCH = 60
HEAD_CHARS = 400
MAX_ROUTES = 4

SYSTEM = """You sort defence-industry documents for a competitive-intelligence team. The client is KSSL (Kalyani Strategic Systems, an Indian
maker of artillery, ammunition, armoured vehicles, barrels and forgings, small arms). For each numbered document you see its source, date,
headline and the first words of the text. Decide which analysis routes should read the full document. A document can have up to four routes,
strongest first. Use only what is shown; if the opening is not enough to tell, choose the routes the headline supports.

Routes
 signal             a defence company does something concrete: wins or signs a contract or order, is selected, delivers or inducts equipment, trials
                    or tests a product, launches a product, forms a partnership or JV, buys a firm, opens a plant or adds capacity, gets an export
                    approval, cancels or fails, or reports results that state orders, backlog or deliveries.
 moment             a dated move by a named defence company that belongs on that company's recent timeline (anything under signal, and also
                    leadership changes, restructuring, strategy, investments, new subsidiaries).
 partnership        a tie between companies: JV, MoU, teaming for a bid, licence or technology transfer, supplier or sub-supplier deal,
                    co-development, investment.
 project            a step in a named programme or procurement project (concept, trials, contract, production, deliveries, in service).
 geo                shows where a company sells, makes or assembles, or buys from, in a named country (a sale, a delivery, a local plant, a local partner).
 tech               a technology development or capability advance: new system, research, prototype, test of a new technology, patent, materials,
                    energetics, drones, electronic warfare, AI, missiles, propulsion.
 opportunity        a government or armed force announces, approves, plans or tenders a purchase (demand): budget lines, acquisition approvals,
                    stated needs, requests for information or proposals, tenders.
 global_requirement a formal pre-tender requirement step of a country: approved plan with quantities, acceptance of necessity, RFI, RFP, funded
                    programme. Use with opportunity when both fit.
 spec               states technical specifications of a named product (range, calibre, weight, speed, payload), such as a product page or datasheet.
 none               nothing above: stock tips, share prices, opinion with no event, civil business, sport, general politics, obituaries, lists of links.

Rules: pick "none" alone when nothing fits (never with other routes). Do not add a route unless the document supports it.
Reply with one line per document and nothing else, in this form (reason: 8 words or fewer, plain words):
<number>|<route>,<route>|<reason>
Example: 3|signal,partnership|Firm signs supply deal with local partner
One line for every number, none missing."""


def clean_snippet(text: str, limit: int = HEAD_CHARS) -> str:
    out = " ".join((text or "").split())
    return out[:limit]


def build_prompt(items: list[dict]) -> str:
    lines = []
    for n, d in enumerate(items, 1):
        who = f" [tracked: {d['who']}]" if d.get("who") else ""
        lines.append(f"{n}. ({d['source']}; {d['date'] or 'undated'}){who} {(d['title'] or '').strip()[:180]}\n   {d['snippet']}")
    return "DOCUMENTS\n" + "\n".join(lines) + "\n\nReturn the JSON now."


def parse_reply(text: str, n: int) -> tuple[dict, list]:
    """Lines "<number>|<route>,<route>|<reason>" -> ({number: (routes, why)}, problems). Unknown route words are dropped; 'none'
    with other routes is dropped; a line with no valid route is a problem (the document is asked for again)."""
    problems, got = [], {}
    for line in (text or "").splitlines():
        parts = [x.strip() for x in line.strip().strip("`").split("|")]
        if len(parts) < 2 or not parts[0].rstrip(".").isdigit():
            continue
        i = int(parts[0].rstrip("."))
        if not 1 <= i <= n or i in got:
            problems.append(f"bad or repeated number {parts[0]}")
            continue
        routes = []
        for r in parts[1].replace(";", ",").replace("/", ",").split(","):
            r = r.strip().lower().replace(" ", "_").replace("-", "_")
            if r in ROUTES and r not in routes:
                routes.append(r)
        if len(routes) > 1 and "none" in routes:
            routes.remove("none")
        if not routes:
            problems.append(f"{i}: no valid route")
            continue
        got[i] = (routes[:MAX_ROUTES], " ".join(" | ".join(parts[2:]).split())[:200] or None)
    return got, problems


def call(system: str, prompt: str):
    """One Haiku call at low effort (no long reasoning: output tokens are what costs). Same CLI and result type as prompts/claude_call."""
    import subprocess
    import tempfile
    from pathlib import Path
    from prompts import claude_call as cc
    args = cc.build_args(MODEL, system, False) + ["--effort", "low"]
    cwd = Path(tempfile.gettempdir()) / "kssl_claude_cwd"
    cwd.mkdir(exist_ok=True)
    t0 = time.monotonic()
    try:
        p = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=cc.TIMEOUT_S, cwd=cwd)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise cc.ModelError(str(e)) from e
    if p.returncode != 0 and not p.stdout.strip():
        raise cc.ModelError(f"claude CLI exit {p.returncode}: {(p.stderr or '').strip()[:300]}")
    res = cc.parse_cli_output(p.stdout)
    res.seconds = round(time.monotonic() - t0, 1)
    return res


def _selftest() -> None:
    g, p = parse_reply("1|Signal, geo, bogus|A contract." + chr(10) + "2|none,tech" + chr(10) + "3. | none | x | y" + chr(10) + "9|tech|z" + chr(10) + "1|tech|dup" + chr(10) + "4||empty" + chr(10) + "chatter", 4)
    assert g[1] == (["signal", "geo"], "A contract.") and g[2] == (["tech"], None) and g[3] == (["none"], "x | y") and 4 not in g and 9 not in g, g
    assert len(p) == 3, p
    assert parse_reply("sorry", 1) == ({}, [])
    assert parse_reply("1|a,signal,moment,geo,tech,spec|r", 1)[0][1][0] == ["signal", "moment", "geo", "tech"]
    pr = build_prompt([{"source": "Wire", "date": "2026-10-01", "title": "Nordvik wins order", "snippet": "text", "who": "Nordvik"},
                       {"source": "Blog", "date": None, "title": "t", "snippet": "s"}])
    assert "1. (Wire; 2026-10-01) [tracked: Nordvik] Nordvik wins order" in pr and "2. (Blog; undated) t" in pr
    assert clean_snippet("a  b\n c" * 200).startswith("a b c") and len(clean_snippet("x" * 900)) == HEAD_CHARS
    print("triage_routes self-check ok")


# ---- database --------------------------------------------------------------------------------------------------------

def connect():
    import psycopg2
    import psycopg2.extras
    c = psycopg2.connect(os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging")
    c.cursor_factory = psycopg2.extras.RealDictCursor
    return c


ORDER_SQL = """CASE WHEN source_kind = 'dc_corpus' AND triage->>'queue' IN ('P0','P1') THEN 1
                    WHEN source_kind = 'newsroom' THEN 2 WHEN source_kind = 'gov' THEN 3 WHEN source_kind = 'trade_press' THEN 4 ELSE 5 END"""


def pending(cur, limit):
    cur.execute(f"""SELECT doc_id::text AS id, source_kind, source_name, title, published_at, competitor_ids::text[] AS cids,
                           left(body_text, 6000) AS body
                    FROM staging.source_document WHERE NOT (coalesce(triage, '{{}}'::jsonb) ? 'route')
                    ORDER BY {ORDER_SQL}, published_at DESC NULLS LAST, doc_id
                    {'LIMIT ' + str(int(limit)) if limit else ''}""")
    return cur.fetchall()


def log_run(conn, key, res, status, error, n, details):
    import psycopg2.extras
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO staging.prompt_run (prompt_id, prompt_version, subject_key, model, web_search, seconds, tokens_in, tokens_out,
                       cost_usd, status, error, rows_loaded, details) VALUES ('triage_route', %s, %s, %s, false, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (PROMPT_VERSION, key, MODEL, getattr(res, "seconds", None), getattr(res, "tokens_in", None), getattr(res, "tokens_out", None),
                     getattr(res, "cost_usd", None), status, error, n, psycopg2.extras.Json(details)))
    conn.commit()


def run(limit=None, workers=6, dry_run=False) -> dict:
    import psycopg2.extras
    from backend import attribute_documents as ad
    from prompts.claude_call import ModelError
    conn = connect()
    cur = conn.cursor()
    names = {r["cid"]: r["n"] for r in (cur.execute("SELECT competitor_id::text cid, display_name n FROM staging.competitive_competitor") or cur.fetchall())}
    print("page-furniture lines ...", flush=True)
    bcur = conn.cursor(name="boiler")
    bcur.itersize = 500
    bcur.execute("SELECT source_name, left(body_text, 12000) AS b FROM staging.source_document")
    boiler = ad.boilerplate_lines((r["source_name"], r["b"]) for r in bcur)
    bcur.close()
    conn.rollback()
    cur = conn.cursor()
    rows = pending(cur, limit)
    conn.rollback()
    docs = []
    for r in rows:
        body = ad.clean_body(r["source_name"], r["body"] or "", boiler)
        docs.append({"id": r["id"], "source": r["source_name"] or r["source_kind"], "date": r["published_at"].isoformat() if r["published_at"] else None,
                     "title": r["title"], "snippet": clean_snippet(body), "who": ", ".join(names[c] for c in (r["cids"] or [])[:3] if c in names)})
    batches = [docs[i:i + BATCH] for i in range(0, len(docs), BATCH)]
    print(f"{len(docs)} documents in {len(batches)} calls ({workers} at a time)" + (" [dry run]" if dry_run else ""), flush=True)
    lock = threading.Lock()
    stats = {"docs": 0, "written": 0, "failed_calls": 0, "cost": 0.0, "missing": 0}
    out_conn = connect()

    def work(bi, batch):
        key = f"batch-{batch[0]['id'][:8]}-{len(batch)}"
        prompt = build_prompt(batch)
        res = None
        try:
            res = call(SYSTEM, prompt)
            got, problems = parse_reply(res.text, len(batch))
            miss = [i for i in range(1, len(batch) + 1) if i not in got]
            if miss:                                            # ask once more for the missing ones
                sub = [batch[i - 1] for i in miss]
                res2 = call(SYSTEM, build_prompt(sub))
                g2, p2 = parse_reply(res2.text, len(sub))
                for k, v in g2.items():
                    got[miss[k - 1]] = v
                res.cost_usd = (res.cost_usd or 0) + (res2.cost_usd or 0)
                res.tokens_in += res2.tokens_in
                res.tokens_out += res2.tokens_out
                problems += p2
        except ModelError as e:
            with lock:
                stats["failed_calls"] += 1
                log_run(out_conn, key, res, "failed", str(e)[:300], 0, {"docs": len(batch)})
            return bi, 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        upd = [(psycopg2.extras.Json({"route": got[i][0], "route_reason": got[i][1], "route_model": MODEL, "route_at": now}), batch[i - 1]["id"])
               for i in sorted(got)]
        with lock:
            if upd and not dry_run:
                with out_conn.cursor() as c2:
                    psycopg2.extras.execute_batch(c2, "UPDATE staging.source_document SET triage = coalesce(triage, '{}'::jsonb) || %s WHERE doc_id = %s::uuid", upd, page_size=100)
                out_conn.commit()
            stats["docs"] += len(batch)
            stats["written"] += len(upd)
            stats["missing"] += len(batch) - len(upd)
            stats["cost"] += res.cost_usd or 0
            log_run(out_conn, key, res, "dry_run" if dry_run else "loaded", None, len(upd), {"docs": len(batch), "problems": problems[:5]})
            if dry_run:
                for i in sorted(got)[:12]:
                    print(f"  {batch[i - 1]['title'][:70]!r:74} -> {got[i][0]}  {got[i][1]}")
        return bi, len(upd)

    t0 = time.monotonic()
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, bi, b) for bi, b in enumerate(batches)]
        for f in as_completed(futs):
            done += 1
            if done % 10 == 0 or done == len(futs):
                print(f"  {done}/{len(futs)} calls, {stats['written']} docs routed, ${stats['cost']:.2f}, {time.monotonic() - t0:.0f}s", flush=True)
    return stats


def report() -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT source_kind, count(*) AS n, count(*) FILTER (WHERE triage ? 'route') AS routed FROM staging.source_document GROUP BY 1 ORDER BY 1""")
    for r in cur.fetchall():
        print(f"{r['source_kind']:12} {r['routed']:6} / {r['n']}")
    cur.execute("""SELECT r AS route, source_kind, count(*) AS n FROM staging.source_document, jsonb_array_elements_text(triage->'route') r
                   WHERE triage ? 'route' GROUP BY 1, 2 ORDER BY 1, 2""")
    tab: dict = {}
    for r in cur.fetchall():
        tab.setdefault(r["route"], {})[r["source_kind"]] = r["n"]
    for route in ROUTES:
        d = tab.get(route, {})
        print(f"  {route:20} total {sum(d.values()):6}  " + "  ".join(f"{k} {v}" for k, v in sorted(d.items())))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.triage_routes", description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
    elif a.report:
        report()
    else:
        print(run(a.limit, a.workers, a.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
