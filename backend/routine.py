"""The scheduled flow, end to end, in one place (user 2026-10-18: "a flow which can run on a routine and flood things properly";
"nothing breaks or nothing remains empty").

    python -m backend.routine --plan                 the steps in order and what each would do now (pending subjects); nothing runs
    python -m backend.routine --check                health: every prompt's subject query runs, every prompt is in the routine (or marked
                                                     routine: false), every table a routine prompt fills has rows; exit 1 on a problem
    python -m backend.routine [--budget 60] [--only STEP[,STEP]] [--from-step STEP] [--skip STEP[,STEP]]

Flow (docs: the flood report's "How the flow works"): harvest (free) -> raw layer -> attribution (code) -> triage (cheap model) ->
prompts (one run per subject, cadence + fingerprint keys decide what is pending) -> loader / handlers -> code roll-ups -> staging,
then Review -> Approve -> serving (by a person, never by this file). Every model call is logged with tokens and cost (staging.prompt_run,
or the matchup engine's call log). Nothing is scheduled here: a Windows task or cron line runs `python -m backend.routine` when the
user wants it. A step that fails is logged and the next one runs; when the model account hits its usage limit, model steps stop and
code steps still run. Each run writes db/flood_logs/routine_<stamp>.log + .json and rebuilds the flood report.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "db" / "flood_logs"
PY = sys.executable
CAP = {"tender_assessment": 15, "tender": 15, "signal": 15, "news": 8, "spec_enrich": 8, "tech_article": 10}   # USD per run of a prompt step
DEFAULT_CAP = 6
WORKERS = {"global_requirement": 1, "opportunity": 1}    # these de-duplicate against rows already on record: run one at a time


def _d(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def steps() -> list[tuple[str, str, object]]:
    """(name, kind, what): kind 'cmd' = a python module with args (free unless noted), 'prompt' = a prompt id (prompts/<id>.yml)."""
    return [
        # 1. harvest (free): newest first, short rolling windows (each harvester is idempotent: ON CONFLICT on the url / notice id)
        ("harvest_sites", "cmd", ["-m", "backend.harvest_sites", "--from", _d(14), "--to", date.today().isoformat()]),
        ("google_news", "cmd", ["-m", "backend.news", "--competitor", "all", "--from", _d(7), "--to", date.today().isoformat()]),
        ("dc_corpus", "cmd", ["-m", "backend.import_dc_corpus", "--from", _d(30)]),
        ("tenders_harvest", "cmd", ["-m", "backend.harvest_tenders", "--api", "all", "--from", _d(30)]),
        ("tenders_stage", "cmd", ["-m", "backend.harvest_tenders", "--stage"]),
        ("spec_harvest", "cmd", ["-m", "backend.harvest_specs", "--routine", "30"]),
        # 2. attribution (code) and triage (Haiku, batched, logged as prompt_run 'triage_route')
        ("attribution", "cmd", ["-m", "backend.attribute_documents"]),
        ("triage", "cmd", ["-m", "backend.triage_routes"]),
        ("news_candidates", "cmd", ["-m", "backend.flood", "candidates"]),
        # 3. competitive pillar
        ("news", "prompt", "news"), ("signal", "prompt", "signal"), ("moment", "prompt", "moment"),
        ("partnership", "prompt", "partnership"), ("project", "prompt", "project"), ("product_program", "prompt", "product_program"),
        ("client_product_program", "prompt", "client_product_program"), ("geo", "prompt", "geo"),
        ("geo_code", "cmd", ["-m", "prompts.geo_analysis", "--code"]), ("geo_analysis", "prompt", "geo_analysis"),
        ("stored_fill", "cmd", ["-m", "backend.stored_fill"]),          # programmes from sales rows, movement images (no model)
        ("synthesis", "prompt", "synthesis"), ("field_synthesis", "prompt", "field_synthesis"),
        # 4. product evaluation: classify new products, map new spec labels, compare, extract specs from new documents, re-compare, words
        ("product_category", "prompt", "product_category"),                 # categories first: the like-for-like gate pairs by category
        ("client_subtype", "cmd", ["-m", "prompts.client_subtype"]),
        ("matchup_engine", "cmd", ["-m", "prompts.matchup_code", "--run-budget", "5"]),
        ("spec_enrich", "prompt", "spec_enrich"), ("client_spec_enrich", "prompt", "client_spec_enrich"),
        ("matchup_compare", "cmd", ["-m", "prompts.matchup_code", "--compare-only"]),
        ("matchup", "prompt", "matchup"), ("product_status", "prompt", "product_status"),
        # 5. market pillar
        ("tender", "prompt", "tender"),
        ("market_prune", "cmd", ["-m", "backend.market_rollups", "prune", "merge", "status"]),
        ("tender_assessment", "prompt", "tender_assessment"), ("opportunity", "prompt", "opportunity"),
        ("global_requirement", "prompt", "global_requirement"), ("segment_assessment", "prompt", "segment_assessment"),
        ("fx_rates", "cmd", ["-m", "scripts.load_fx_rates", "--write"]),          # ECB / NBU reference rates -> staging.fx_rate (rupee figures)
        ("market_rollups", "cmd", ["-m", "backend.market_rollups", "all"]),
        ("top_opportunity", "prompt", "top_opportunity"),
        # 6. technology pillar
        ("innovation_discovery", "prompt", "innovation_discovery"), ("innovation_detail", "prompt", "innovation_detail"),
        ("tech_article", "prompt", "tech_article"), ("patent_classification", "prompt", "patent_classification"),
        ("tech_rollups", "cmd", ["-m", "prompts.tech_rollups"]),
        # 7. report
        ("flood_report", "cmd", ["-m", "backend.flood_report"]),
    ]


def env() -> dict:
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    e.setdefault("KSSL_STAGING_DSN", "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl")
    return e


def connect():
    from prompts.run import connect as c
    return c()


def prompt_ids_in_routine() -> set[str]:
    return {w for _, k, w in steps() if k == "prompt"}


def off_routine(pid: str) -> str | None:
    """Why a prompt never runs by routine: `routine: false` in its file (a hidden section) or cadence on_demand."""
    from prompts import render
    spec = render.load_prompt(pid)
    if spec.get("routine") is False:
        return "routine: false"
    if spec.get("cadence") == "on_demand":
        return "cadence on_demand"
    return None


def pending_count(conn, pid: str):
    from prompts import render, run
    spec = render.load_prompt(pid)
    with conn.cursor() as cur:
        try:
            return len(run.pending(cur, spec, render.subjects(cur, spec)))
        except Exception as e:            # noqa: BLE001 - the check reports it
            conn.rollback()
            return f"ERROR {str(e).splitlines()[0][:120]}"
        finally:
            conn.rollback()


def spent_since(conn, t0: datetime) -> float:
    with conn.cursor() as cur:
        cur.execute("SELECT coalesce(sum(cost_usd), 0) AS c FROM staging.prompt_run WHERE started_at >= %s", (t0,))
        c = float(cur.fetchone()["c"])
    conn.rollback()
    log = ROOT / "db" / "excel_reports" / "matchup_dictionary_calls.jsonl"          # the matchup engine's own call log
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            at = r.get("at") or r.get("ts") or ""
            if at and at >= t0.isoformat()[:19]:
                c += float(r.get("cost_usd") or 0)
    return c


# ---- --plan / --check ------------------------------------------------------------------------------------------

def plan_rows(conn) -> list[dict]:
    """The steps as they would run now: name, kind, what, and for a prompt its pending subjects, cap, or why it is skipped."""
    out = []
    for name, kind, what in steps():
        if kind == "cmd":
            out.append({"step": name, "kind": "code", "what": "python " + " ".join(what)})
        else:
            why = off_routine(what)
            out.append({"step": name, "kind": "prompt", "what": what, "skipped": why,
                        "pending": None if why else pending_count(conn, what), "cap": CAP.get(what, DEFAULT_CAP)})
    return out


def cmd_plan() -> int:
    conn = connect()
    for r in plan_rows(conn):
        if r["kind"] == "code":
            print(f"{r['step']:24} code   {r['what']}")
        else:
            print(f"{r['step']:24} prompt {r['what']:22} " + (f"SKIPPED ({r['skipped']})" if r["skipped"] else f"pending {r['pending']}, cap ${r['cap']}"))
    conn.close()
    return 0


def cmd_check() -> int:
    problems, notes = check()
    print("PROBLEMS" if problems else "no problems")
    for p in problems:
        print("  - " + p)
    if notes:
        print("notes")
        for n in notes:
            print("  - " + n)
    return 1 if problems else 0


def check(conn=None) -> tuple[list[str], list[str]]:
    """(problems, notes): what would break a scheduled run or leave a page empty (problems), and what to look at (notes)."""
    from prompts import render
    own = conn is None
    conn = conn or connect()
    problems, notes = [], []
    in_routine = prompt_ids_in_routine()
    for pid in render.prompt_ids():
        why = off_routine(pid)
        if pid not in in_routine and not why:
            problems.append(f"prompt {pid}: not in the routine and not marked `routine: false` (it would never run on schedule)")
        if pid in in_routine and why:
            notes.append(f"prompt {pid}: in the routine but {why} (skipped)")
        n = pending_count(conn, pid)
        if isinstance(n, str):
            problems.append(f"prompt {pid}: subject query fails: {n}")
        spec = render.load_prompt(pid)
        if why:
            continue
        for t in spec.get("fills") or []:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass(%s) AS r", (f"staging.{t}",))
                if cur.fetchone()["r"] is None:
                    problems.append(f"prompt {pid}: fills staging.{t}, which does not exist")
                    conn.rollback()
                    continue
                cur.execute(f"SELECT count(*) AS n FROM staging.{t}")
                if cur.fetchone()["n"] == 0:
                    problems.append(f"prompt {pid}: staging.{t} is EMPTY (pending subjects: {n})")
            conn.rollback()
    with conn.cursor() as cur:
        cur.execute("""SELECT prompt_id, prompt_version, count(*) AS n, left(min(coalesce(error, '')), 140) AS e FROM staging.prompt_run
                       WHERE status = 'failed' AND started_at > now() - interval '7 days' AND coalesce(error, '') NOT ILIKE '%limit%'
                       GROUP BY 1, 2 ORDER BY 3 DESC""")
        ids = set(render.prompt_ids())
        for r in cur.fetchall():
            if r["prompt_id"] in ids and str(r["prompt_version"]) == render.load_prompt(r["prompt_id"])["version"]:   # older versions are history
                notes.append(f"prompt {r['prompt_id']}: {r['n']} failed runs in 7 days at the current version (not the usage limit), e.g. {r['e']}")
    conn.rollback()
    if own:
        conn.close()
    for name, kind, what in steps():
        if kind == "cmd":
            mod = what[1]
            if not (ROOT / (mod.replace(".", "/") + ".py")).exists():
                problems.append(f"step {name}: module {mod} not found")
    return problems, notes


# ---- the run ------------------------------------------------------------------------------------------------------

def run(budget: float, only: set, start: str | None, skip: set) -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    LOGS.mkdir(parents=True, exist_ok=True)
    logf = (LOGS / f"routine_{stamp}.log").open("w", encoding="utf-8")
    t0 = datetime.now(timezone.utc)
    conn = connect()
    results, limit_hit, started = [], False, start is None
    for name, kind, what in steps():
        started = started or name == start
        if not started or (only and name not in only) or name in skip:
            continue
        rec = {"step": name, "kind": kind}
        if kind == "prompt":
            why = off_routine(what)
            spent = spent_since(conn, t0)
            if why or limit_hit or spent >= budget:
                rec["status"] = "skipped: " + (why or ("usage limit" if limit_hit else f"budget ${budget:.0f} reached"))
                results.append(rec)
                print(f"{name:24} {rec['status']}", flush=True)
                continue
            cap = min(CAP.get(what, DEFAULT_CAP), budget - spent)
            args = ["-m", "scripts.flood_run", what, "--workers", str(WORKERS.get(what, 3)), "--max-cost", f"{cap:.2f}"]
        else:
            args = what
        t = time.time()
        logf.write(f"\n===== {name}: python {' '.join(args)}\n")
        logf.flush()
        p = subprocess.run([PY, *args], cwd=ROOT, env=env(), stdout=logf, stderr=subprocess.STDOUT)
        rec.update(seconds=round(time.time() - t, 1), exit=p.returncode)
        rec["status"] = "ok" if p.returncode == 0 else ("usage limit" if p.returncode == 3 else "FAILED (see log)")
        limit_hit = limit_hit or p.returncode == 3
        results.append(rec)
        print(f"{name:24} {rec['status']:18} {rec['seconds']:>7}s  spent so far ${spent_since(conn, t0):.2f}", flush=True)
    total = spent_since(conn, t0)
    conn.close()
    logf.close()
    out = {"started": t0.isoformat(), "budget": budget, "cost_usd": round(total, 2), "steps": results}
    (LOGS / f"routine_{stamp}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"routine done: ${total:.2f}; log db/flood_logs/routine_{stamp}.log")
    return 1 if any(r.get("status", "").startswith("FAILED") for r in results) else 0


def _selftest() -> None:
    names = [s[0] for s in steps()]
    assert len(names) == len(set(names)), "step names must be unique"
    order = {n: i for i, n in enumerate(names)}
    for a, b in (("attribution", "triage"), ("triage", "news"), ("news", "signal"), ("matchup_engine", "spec_enrich"),
                 ("spec_enrich", "matchup_compare"), ("matchup_compare", "matchup"), ("tender", "tender_assessment"),
                 ("market_rollups", "top_opportunity"), ("fx_rates", "market_rollups"), ("geo", "geo_code"), ("partnership", "synthesis"), ("tech_rollups", "flood_report"), ("product_category", "matchup_engine")):
        assert order[a] < order[b], f"{a} must run before {b}"
    assert all(k in ("cmd", "prompt") for _, k, _ in steps())
    print("routine self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--budget", type=float, default=60.0, help="model spend cap for this run, USD (prompt_run + matchup call log)")
    ap.add_argument("--only", default="", help="comma-separated step names")
    ap.add_argument("--from-step")
    ap.add_argument("--skip", default="")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ.update(env())
    if a.selftest:
        _selftest()
        return 0
    if a.plan:
        return cmd_plan()
    if a.check:
        return cmd_check()
    split = lambda s: {x.strip() for x in s.split(",") if x.strip()}
    return run(a.budget, split(a.only), a.from_step, split(a.skip))


if __name__ == "__main__":
    sys.exit(main())
