"""The pipeline log (owner 22 Oct: "log every inch of the flow, harvest to UI, each step, with timestamps"). Tables:
db/setup/33_pipeline_log.sql (staging DB, schema ops). Read on the review site's Pipeline log.

    ops.run / ops.step   one routine run and its steps, or a script run on its own (run kind 'manual')
    ops.record_event     every row written, by a trigger; the step comes from the connection setting kssl.ops_step,
                         which a step puts in PGOPTIONS so every connection its process (and child processes) opens carries it
    ops.note             a script's own decisions in plain words: note("image", "too_small", "Picture 180x90 is under 200x120",
                         subject=page_url)

    from backend import ops_log
    with ops_log.step("harvest_sites", "backend.harvest_sites --from ...", run_id=rid) as st: ...   # the routine
    @ops_log.logged("backend.media_images")                                                         # a script's main()
    ops_log.note(kind, outcome, message, subject=..., tbl=..., rec_id=..., detail=...)              # anywhere inside

The log never breaks the pipeline: a failed log write prints one warning and the work goes on.
    python -m backend.ops_log --selftest      (writes nothing)
"""

from __future__ import annotations

import functools
import json
import os
import socket
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEP_ENV, RUN_ENV = "KSSL_OPS_STEP", "KSSL_OPS_RUN"
_conn = None
_warned = False


def _db():
    """one autocommit connection to the staging DB for the log itself (not tagged with a step: log rows are not data rows)"""
    global _conn
    if _conn is None or _conn.closed:
        import psycopg2
        dsn = (os.getenv("KSSL_STAGING_DSN") or os.getenv("KSSL_DSN") or "").strip()
        _conn = psycopg2.connect(dsn, connect_timeout=5, options="-c kssl.ops_step=")
        _conn.autocommit = True
    return _conn


def _write(sql: str, args: tuple = ()):
    global _warned
    try:
        with _db().cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone() if cur.description else None
    except Exception as exc:  # noqa: BLE001 -- the log must never stop the work
        if not _warned:
            print(f"[ops_log] not logging: {type(exc).__name__}: {str(exc)[:160]}", file=sys.stderr, flush=True)
            _warned = True
        return None


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def tag_env(env: dict, step_id: str, run_id: str | None) -> dict:
    """env for a process that works inside this step: every libpq connection it opens carries kssl.ops_step"""
    opts = " ".join(o for o in (env.get("PGOPTIONS", "") or "").split(" -c ") if o and "kssl.ops_step" not in o).strip()
    env = dict(env)
    env["PGOPTIONS"] = (opts + " " if opts else "") + f"-c kssl.ops_step={step_id}"
    env[STEP_ENV] = step_id
    if run_id:
        env[RUN_ENV] = run_id
    return env


def start_run(kind: str, args: dict | None = None) -> str:
    rid = str(uuid.uuid4())
    _write("SELECT ops.install_triggers()")                 # tables added since the last run get their trigger
    _write("INSERT INTO ops.run (run_id, kind, args, host, git_sha) VALUES (%s, %s, %s, %s, %s)",
           (rid, kind, json.dumps(args or {}), socket.gethostname(), _git_sha()))
    return rid


def end_run(run_id: str, status: str, cost_usd: float | None = None, notes: str | None = None) -> None:
    _write("UPDATE ops.run SET ended_at = clock_timestamp(), status = %s, cost_usd = %s, notes = %s WHERE run_id = %s",
           (status, cost_usd, notes, run_id))


def begin_step(name: str, script: str | None, run_id: str | None) -> str:
    sid = str(uuid.uuid4())
    _write("INSERT INTO ops.step (step_id, run_id, name, script) VALUES (%s, %s, %s, %s)", (sid, run_id, name, script))
    return sid


def finish_step(step_id: str, status: str, exit_code: int | None = None, error: str | None = None, log_path: str | None = None) -> None:
    """close the step: seconds, model spend inside it, and rows written per table (from the trigger's events: exact)"""
    _write("""UPDATE ops.step s SET ended_at = clock_timestamp(), status = %s, exit_code = %s, error = %s, log_path = %s,
                     seconds = round(extract(epoch FROM clock_timestamp() - s.started_at)::numeric, 1),
                     cost_usd = (SELECT round(sum(cost_usd)::numeric, 4) FROM staging.prompt_run p
                                 WHERE p.started_at >= s.started_at AND p.started_at <= clock_timestamp()),
                     rows = (SELECT jsonb_object_agg(tbl, c) FROM (
                               SELECT tbl, jsonb_object_agg(action, n) AS c
                               FROM (SELECT tbl, action, count(*) AS n FROM ops.record_event WHERE step_id = s.step_id GROUP BY 1, 2) x
                               GROUP BY tbl) y)
              WHERE s.step_id = %s""", (status, exit_code, (error or "")[-4000:] or None, log_path, step_id))


@contextmanager
def step(name: str, script: str | None = None, run_id: str | None = None):
    """a step run in THIS process: its connections opened inside the block carry the step (PGOPTIONS)"""
    sid = begin_step(name, script, run_id)
    old = {k: os.environ.get(k) for k in ("PGOPTIONS", STEP_ENV, RUN_ENV)}
    os.environ.update(tag_env(dict(os.environ), sid, run_id))
    try:
        yield sid
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        finish_step(sid, "ok" if code == 0 else "failed", code)
        raise
    except BaseException as e:
        finish_step(sid, "failed", 1, f"{type(e).__name__}: {e}")
        raise
    else:
        finish_step(sid, "ok", 0)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def logged(name: str):
    """decorator for a script's main(): inside the routine (KSSL_OPS_STEP set) it only runs; on its own it logs a run of one step"""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*a, **k):
            if os.environ.get(STEP_ENV):
                return fn(*a, **k)
            rid = start_run("manual", {"argv": sys.argv[1:]})
            status = "failed"
            try:
                with step(name, " ".join([name, *sys.argv[1:]]), rid):
                    out = fn(*a, **k)
                status = "ok" if out in (None, 0) else "failed"
                return out
            except SystemExit as e:
                status = "ok" if e.code in (None, 0) else "failed"
                raise
            finally:
                end_run(rid, status)
        return inner
    return wrap


def note(kind: str, outcome: str, message: str, subject: str | None = None, tbl: str | None = None,
         rec_id: str | None = None, detail: dict | None = None, script: str | None = None) -> None:
    """one decision of a script, in plain words, tied to the current step (when there is one) and to what it is about"""
    _write("""INSERT INTO ops.note (step_id, script, kind, outcome, subject, tbl, rec_id, message, detail)
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
           (os.environ.get(STEP_ENV) or None, script or _caller_module(), kind, outcome, (subject or None) and str(subject)[:1000],
            tbl, None if rec_id is None else str(rec_id), str(message)[:2000], json.dumps(detail, default=str) if detail else None))


def review_event(action: str, tbl: str, rec_id: str, detail: dict | None = None, cur=None) -> None:
    """an Approve / Reject / Unpublish / Undo on the review site -- in the review's own transaction when a cursor is given"""
    sql = "INSERT INTO ops.record_event (tbl, rec_id, action, detail) VALUES (%s, %s, %s, %s)"
    args = (tbl if "." in tbl else f"staging.{tbl}", str(rec_id), action, json.dumps(detail, default=str) if detail else None)
    if cur is None:
        _write(sql, args)
        return
    try:
        cur.execute("SAVEPOINT ops_log")
        cur.execute(sql, args)
        cur.execute("RELEASE SAVEPOINT ops_log")
    except Exception:  # noqa: BLE001 -- no ops schema (a DB from before 33): the approval still goes through
        cur.execute("ROLLBACK TO SAVEPOINT ops_log")


def _caller_module() -> str | None:
    f = sys._getframe(2)
    return f.f_globals.get("__name__") if f else None


def _selftest() -> None:
    e = tag_env({"PGOPTIONS": "-c statement_timeout=0 -c kssl.ops_step=old"}, "abc", "run1")
    assert e["PGOPTIONS"] == "-c statement_timeout=0 -c kssl.ops_step=abc", e["PGOPTIONS"]
    assert e[STEP_ENV] == "abc" and e[RUN_ENV] == "run1"
    assert tag_env({}, "x", None)["PGOPTIONS"] == "-c kssl.ops_step=x"
    print("ops_log self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
