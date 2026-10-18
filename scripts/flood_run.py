"""Bulk runner for one prompt: python -m scripts.flood_run <prompt> [--workers 6] [--limit N] [--max-cost USD] [--rerun]
Runs the pending subjects (the prompt's own query order) on a thread pool, one DB connection per worker, each run logged to
staging.prompt_run like prompts.run. Stops taking new subjects when the cost of THIS invocation reaches --max-cost."""
from __future__ import annotations
import argparse, sys, threading
from concurrent.futures import ThreadPoolExecutor
from prompts import render, run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt"); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--limit", type=int)
    ap.add_argument("--max-cost", type=float, default=50.0); ap.add_argument("--rerun", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    conn = run.connect()
    spec = render.load_prompt(a.prompt)
    class A: subject = None; limit = a.limit; rerun = a.rerun; print_prompt = False
    subs, why = run.select(conn, spec, A)
    if not subs:
        print(why); return 0
    with conn.cursor() as cur:
        client = render.client_row(cur); blocks = render.context_blocks(cur, client)
    conn.rollback(); conn.close()
    lock = threading.Lock(); st = {"cost": 0.0, "n": 0, "ok": 0, "skip": 0, "bad": 0, "limit_hit": False}
    local = threading.local()

    def work(s):
        with lock:
            if st["cost"] >= a.max_cost or st["limit_hit"]:
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
