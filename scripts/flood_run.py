"""Bulk runner for one prompt: python -m scripts.flood_run <prompt> [--workers 6] [--limit N] [--max-cost USD] [--rerun]
Runs the pending subjects (the prompt's own query order) on a thread pool, one DB connection per worker, each run logged to
staging.prompt_run like prompts.run. Stops taking new subjects when the cost of THIS invocation reaches --max-cost."""
from __future__ import annotations
import argparse, os, sys, threading
from concurrent.futures import ThreadPoolExecutor
from prompts import render, run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt"); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--limit", type=int)
    ap.add_argument("--max-cost", type=float, default=50.0); ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--cards", type=int, help="stop after N new cards or 5N runs")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    conn = run.connect()
    spec = render.load_prompt(a.prompt)
    class A: subject = None; limit = a.limit; rerun = a.rerun; print_prompt = False
    subs, why = run.select(conn, spec, A)
    since = os.environ.get("KSSL_SINCE")       # set by backend/routine --since: an article dated before it waits; undated ones run
    if since and subs:
        # a news batch carries its month: it counts as the month's last day, so the window's own month runs
        # shortcut: "-31" for every month only works for a >= string compare, use a real month-end date if anything else reads it
        d = lambda s: str(s.get("published_date") or s.get("published_at") or "")[:10] or (str(s["month"])[:7] + "-31" if s.get("month") else "")
        n = len(subs)
        dated_only = os.environ.get("KSSL_DATED_ONLY") == "1"      # owner 2026-10-27 "flood those new dated data": undated backlog waits too
        subs = [s for s in subs if (not d(s) and not dated_only) or d(s) >= since]
        why = why or f"all {n} pending subjects are dated before {since}"
        print(f"window from {since}: {len(subs)} of {n} pending subjects", flush=True)
    if not subs:
        print(why); return 0
    with conn.cursor() as cur:
        client = render.client_row(cur); blocks = render.context_blocks(cur, client)
    conn.rollback(); conn.close()
    lock = threading.Lock(); st = {"cost": 0.0, "n": 0, "ok": 0, "skip": 0, "bad": 0, "limit_hit": False, "cards": 0}
    # owner 2026-10-24 "10-15 cards per section, then stop": N new cards (as each run's load reports them), or 5N runs, whichever first
    # ponytail: 5N is the cap for a prompt that makes few or no cards (enrichment, synthesis); raise it if a section comes up short
    enough = lambda: a.cards and (st["cards"] >= a.cards or st["n"] >= 5 * a.cards)     # noqa: E731
    local = threading.local()

    def work(s):
        with lock:
            if st["cost"] >= a.max_cost or st["limit_hit"] or enough():
                return
        if not hasattr(local, "conn"):
            local.conn = run.connect()
        o = run.run_one(local.conn, spec, s, client, blocks, False, a.rerun)
        if o.error and "limit" in o.error.lower() and o.status == "failed":      # usage limit: stop taking subjects, do not log a failed run for it
            with lock:
                st["limit_hit"] = True
                print("!!! usage limit reached: stopping cleanly (this subject is not logged, so it runs next time)", flush=True)
            return
        run.log_run(local.conn, spec, s["_key"], o)
        with lock:
            st["cost"] += o.cost or 0; st["n"] += 1
            st["cards"] += len({(t, i) for t, i, c in (o.loaded or []) if c})
            st["ok" if o.status == "loaded" else "skip" if o.status == "skipped" else "bad"] += 1
            print(run.line(a.prompt, s, o), flush=True)
            if st["n"] % 25 == 0:
                print(f"--- {st['n']} done, loaded {st['ok']}, skipped {st['skip']}, failed/rejected {st['bad']}, cost ${st['cost']:.2f}", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(work, subs))
    print(f"=== finished {st}")
    return 3 if st["limit_hit"] else 0          # 3 = the model account hit its usage limit (backend/routine.py stops model steps)

if __name__ == "__main__":
    sys.exit(main())
