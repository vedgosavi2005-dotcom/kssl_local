"""The Flow dashboard (owner 2026-10-24: "a proper dashboard of our Flow, which we run every day ... each and every log").
Read side only, review site (/flow, src/pages/flow/FlowDashboard.jsx), served by /api/review/flow/* (backend/app.py).

    runs      every routine / manual run: status, time, cost, steps, rows written, errors and warnings
    run       one run's steps: timing, rows per table, model spend, error and warning lines, notes
    output    one step's whole console output (ops.step.output, db/setup/39) and its notes
    errors    every failed step, error / warning note, error line in a step's output, and failed model call, with "fixed later"
    models    every prompt: calls, outcomes, retries, tokens, cost; spend per day; the latest failures
    data      rows written per pillar per day, approvals to serving, staging vs serving counts, empty tables
    coverage  harvested documents: the routes triage gave them vs the pillars that actually used them

Sources: ops.run / ops.step / ops.note / ops.record_event (33, 39), staging.prompt_run, staging.source_document, the staging and
serving tables. Every function takes RealDictCursors (st = staging DB, sv = serving DB) and a window in days.
    python -m backend.flow_dashboard --selftest      (no DB)
"""
from __future__ import annotations

import re
from typing import Any

ERROR_LINE = re.compile(r"(Traceback \(most recent call last\)|\b[A-Z][A-Za-z]*(Error|Exception|Violation)\b|\bFAILED\b|\berror:|\bERROR\b)")
WARN_LINE = re.compile(r"(\bWARN(ING)?\b|\bwarning:|\[ops_log\] not logging)", re.I)
MAX_LINES = 40                  # error / warning lines listed per step on the Errors screen

# pillar of a table, by name (the UI's pillars; raw / bookkeeping tables are "Raw" / "Other")
PILLARS = (
    (r"^(source_document|news_candidate|tender_raw|source_link)$", "Raw"),
    (r"^competitive_signal|^story", "Signals"),
    (r"^competitive_news_article", "Company news"),
    (r"product_news$", "Product news"),
    (r"^competitive_competitor_moment", "Competitor movement"),
    (r"^competitive_partnership", "Partnership"),
    (r"^competitive_project", "Projects"),
    (r"^competitive_geo|^competitive_competitor_location", "Geo"),
    (r"patent", "Patent"),
    (r"specification|^competitive_matchup", "Products & specs"),
    (r"^competitive_product|^client_product", "Products & specs"),
    (r"^competitive_", "Competitors"),
    (r"^market_tender", "Tenders"),
    (r"^market_opportunit", "Opportunities"),
    (r"^market_global_requirement", "Global requirements"),
    (r"^market_", "Market"),
    (r"^technology_", "Technology"),
)
# what triage promised (source_document.triage->'route') -> the pillar that should then hold the document's url
ROUTE_PILLAR = {"signal": "Signals", "moment": "Competitor movement", "partnership": "Partnership", "project": "Projects",
                "geo": "Geo", "tech": "Technology", "opportunity": "Opportunities", "global_requirement": "Global requirements",
                "spec": "Products & specs"}


def pillar(table: str) -> str:
    t = table.split(".")[-1]
    return next((p for rx, p in PILLARS if re.search(rx, t)), "Other")


def _lines(text: str | None, rx: re.Pattern) -> list[str]:
    return [ln.strip()[:400] for ln in (text or "").splitlines() if rx.search(ln)][:MAX_LINES]


def _q(cur, sql: str, args: tuple = ()) -> list[dict]:
    cur.execute(sql, args)
    return [dict(r) for r in cur.fetchall()]


def _has(cur, name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (name,))
    return bool(cur.fetchone()["ok"])


def _has_col(cur, table: str, col: str) -> bool:
    s, t = table.split(".")
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name = %s", (s, t, col))
    return cur.fetchone() is not None


def _out(cur) -> str:
    """the output column when db/setup/39 is applied, else NULL (a DB from before it still serves the dashboard)"""
    return "s.output" if _has_col(cur, "ops.step", "output") else "NULL::text"


def _lvl(cur) -> str:
    return "n.level" if _has_col(cur, "ops.note", "level") else "'info'::text"


# ---- runs ---------------------------------------------------------------------------------------------------------------------

def runs(st, days: int = 30) -> dict[str, Any]:
    out = _out(st)
    rows = _q(st, f"""
        SELECT r.run_id, r.kind, r.started_at, r.ended_at, r.status, r.cost_usd, r.git_sha, r.args, r.host,
               count(s.step_id) AS steps, count(*) FILTER (WHERE s.status = 'failed') AS failed_steps,
               count(*) FILTER (WHERE s.status = 'running') AS running_steps,
               round(extract(epoch FROM coalesce(r.ended_at, clock_timestamp()) - r.started_at)::numeric, 0) AS seconds,
               coalesce(sum(s.cost_usd), 0) AS step_cost,
               array_agg({out}) FILTER (WHERE {out} IS NOT NULL) AS outputs,
               jsonb_agg(s.rows) FILTER (WHERE s.rows IS NOT NULL) AS rows
        FROM ops.run r LEFT JOIN ops.step s ON s.run_id = r.run_id
        WHERE r.started_at >= now() - make_interval(days => %s)
        GROUP BY r.run_id ORDER BY r.started_at DESC LIMIT 500""", (days,))
    notes = {str(r["run_id"]): r for r in _q(st, f"""
        SELECT s.run_id, count(*) FILTER (WHERE {_lvl(st)} = 'error') AS err, count(*) FILTER (WHERE {_lvl(st)} = 'warn') AS warn
        FROM ops.note n JOIN ops.step s ON s.step_id = n.step_id
        WHERE n.at >= now() - make_interval(days => %s) GROUP BY 1""", (days,))}
    for r in rows:
        outs = r.pop("outputs") or []
        written = r.pop("rows") or []
        r["error_lines"] = sum(len(_lines(o, ERROR_LINE)) for o in outs)
        r["warn_lines"] = sum(len(_lines(o, WARN_LINE)) for o in outs)
        n = notes.get(str(r["run_id"]), {})
        r["error_notes"], r["warn_notes"] = n.get("err", 0), n.get("warn", 0)
        tot = {"ins": 0, "upd": 0, "del": 0}
        for per_table in written:
            for counts in (per_table or {}).values():
                for k in tot:
                    tot[k] += int((counts or {}).get({"ins": "insert", "upd": "update", "del": "delete"}[k], 0) or 0)
        r["rows_written"] = tot
    daily = _q(st, """
        SELECT d::date AS day,
               (SELECT count(*) FROM ops.run r WHERE r.started_at::date = d::date) AS runs,
               (SELECT count(*) FROM ops.step s WHERE s.started_at::date = d::date AND s.status = 'failed') AS failed_steps,
               (SELECT coalesce(round(sum(cost_usd)::numeric, 2), 0) FROM staging.prompt_run p WHERE p.started_at::date = d::date) AS cost,
               (SELECT count(*) FROM staging.prompt_run p WHERE p.started_at::date = d::date AND p.status = 'failed') AS failed_calls,
               (SELECT count(*) FROM staging.prompt_run p WHERE p.started_at::date = d::date) AS calls
        FROM generate_series(current_date - (%s - 1), current_date, interval '1 day') d ORDER BY 1""", (days,)) \
        if _has(st, "staging.prompt_run") else []
    return {"runs": rows, "daily": daily}


def run(st, run_id: str) -> dict[str, Any]:
    out = _out(st)
    steps = _q(st, f"""
        SELECT s.step_id, s.name, s.script, s.started_at, s.ended_at, s.status, s.exit_code, s.seconds, s.cost_usd, s.rows, s.error,
               s.log_path, {out} AS output,
               (SELECT count(*) FROM ops.note n WHERE n.step_id = s.step_id) AS notes,
               (SELECT count(*) FROM ops.note n WHERE n.step_id = s.step_id AND {_lvl(st)} = 'error') AS error_notes,
               (SELECT count(*) FROM ops.note n WHERE n.step_id = s.step_id AND {_lvl(st)} = 'warn') AS warn_notes
        FROM ops.step s WHERE s.run_id = %s ORDER BY s.started_at""", (run_id,))
    calls = _q(st, """SELECT prompt_id, status, count(*) AS n, round(sum(cost_usd)::numeric, 4) AS cost, min(started_at) AS t0, max(started_at) AS t1
                      FROM staging.prompt_run WHERE started_at BETWEEN (SELECT min(started_at) FROM ops.step WHERE run_id = %s)
                                                         AND coalesce((SELECT max(coalesce(ended_at, now())) FROM ops.step WHERE run_id = %s), now())
                      GROUP BY 1, 2 ORDER BY 1, 2""", (run_id, run_id)) if _has(st, "staging.prompt_run") else []
    for s in steps:
        o = s.pop("output")
        s["output_chars"] = len(o or "")
        s["error_lines"], s["warn_lines"] = _lines(o, ERROR_LINE), _lines(o, WARN_LINE)
    r = _q(st, "SELECT * FROM ops.run WHERE run_id = %s", (run_id,))
    return {"run": r[0] if r else None, "steps": steps, "calls": calls}


def output(st, step_id: str) -> dict[str, Any]:
    s = _q(st, f"SELECT s.step_id, s.name, s.script, s.status, s.error, s.log_path, {_out(st)} AS output FROM ops.step s WHERE s.step_id = %s",
           (step_id,))
    notes = _q(st, f"""SELECT n.at, {_lvl(st)} AS level, n.kind, n.outcome, n.subject, n.tbl, n.rec_id, n.message
                       FROM ops.note n WHERE n.step_id = %s ORDER BY n.at LIMIT 2000""", (step_id,))
    return {"step": s[0] if s else None, "notes": notes}


# ---- errors -------------------------------------------------------------------------------------------------------------------

def errors(st, days: int = 30) -> dict[str, Any]:
    """every problem in the window, newest first; fixed = the same step name / prompt + subject succeeded later"""
    items: list[dict] = []
    for s in _q(st, f"""
            SELECT s.step_id, s.run_id, s.name, s.started_at AS at, s.status, s.error, {_out(st)} AS output,
                   EXISTS (SELECT 1 FROM ops.step l WHERE l.name = s.name AND l.status = 'ok' AND l.started_at > s.started_at) AS fixed
            FROM ops.step s WHERE s.started_at >= now() - make_interval(days => %s) ORDER BY s.started_at DESC""", (days,)):
        if s["status"] == "failed":
            last = [ln for ln in (s["error"] or "").splitlines() if ln.strip()][-1:] or ["(no message)"]
            items.append({"at": s["at"], "level": "error", "source": "step failed", "where": s["name"], "message": last[0][:400],
                          "step_id": s["step_id"], "run_id": s["run_id"], "fixed": s["fixed"]})
        for lvl, rx in (("error", ERROR_LINE), ("warn", WARN_LINE)):
            for ln in _lines(s["output"], rx):
                items.append({"at": s["at"], "level": lvl, "source": "step output", "where": s["name"], "message": ln,
                              "step_id": s["step_id"], "run_id": s["run_id"], "fixed": s["fixed"] if s["status"] == "failed" else None})
    if _has_col(st, "ops.note", "level"):
        for n in _q(st, """SELECT n.at, n.level, n.kind, n.outcome, n.subject, n.message, n.step_id, s.run_id, coalesce(s.name, n.script) AS name
                           FROM ops.note n LEFT JOIN ops.step s ON s.step_id = n.step_id
                           WHERE n.level <> 'info' AND n.at >= now() - make_interval(days => %s)""", (days,)):
            items.append({"at": n["at"], "level": n["level"], "source": f"note: {n['kind']} / {n['outcome']}", "where": n["name"],
                          "message": n["message"], "subject": n["subject"], "step_id": n["step_id"], "run_id": n["run_id"], "fixed": None})
    if _has(st, "staging.prompt_run"):
        for p in _q(st, """
                SELECT p.started_at AS at, p.prompt_id, p.subject_key, p.error, p.skip_reason,
                       EXISTS (SELECT 1 FROM staging.prompt_run l WHERE l.prompt_id = p.prompt_id AND l.subject_key = p.subject_key
                                 AND l.status IN ('loaded', 'skipped', 'rejected') AND l.started_at > p.started_at) AS fixed
                FROM staging.prompt_run p WHERE p.status = 'failed' AND p.started_at >= now() - make_interval(days => %s)""", (days,)):
            items.append({"at": p["at"], "level": "error", "source": "model call failed", "where": p["prompt_id"],
                          "message": (p["error"] or p["skip_reason"] or "(no message)")[:400], "subject": p["subject_key"], "fixed": p["fixed"]})
    items.sort(key=lambda x: str(x["at"]), reverse=True)
    kinds: dict[str, int] = {}
    for it in items:
        k = _kind(it["message"])
        it["kind"] = k
        if it["level"] == "error" and not it.get("fixed"):
            kinds[k] = kinds.get(k, 0) + 1
    return {"items": items[:3000], "total": len(items), "open_errors": sum(1 for i in items if i["level"] == "error" and not i.get("fixed")),
            "open_by_kind": sorted(kinds.items(), key=lambda kv: -kv[1])}


def _kind(message: str) -> str:
    """group an error message: the exception name, the claude CLI's reason, or its first words"""
    m = str(message or "")
    for rx, k in ((r"weekly limit|usage limit|hit your", "model usage limit"), (r"timed out|timeout", "timeout"),
                  (r"Connection closed|ConnectionError|ConnectionReset|RemoteDisconnected", "connection dropped")):
        if re.search(rx, m, re.I):
            return k
    e = re.search(r"\b([A-Z][A-Za-z]*(Error|Exception|Violation|Reference))\b", m)
    return e.group(1) if e else " ".join(m.split()[:4])[:60] or "unknown"


# ---- model calls --------------------------------------------------------------------------------------------------------------

def models(st, days: int = 30) -> dict[str, Any]:
    if not _has(st, "staging.prompt_run"):
        return {"prompts": [], "daily": [], "failures": []}
    prompts = _q(st, """
        SELECT prompt_id, count(*) AS calls,
               count(*) FILTER (WHERE status = 'loaded') AS loaded, count(*) FILTER (WHERE status = 'skipped') AS skipped,
               count(*) FILTER (WHERE status = 'rejected') AS rejected, count(*) FILTER (WHERE status = 'failed') AS failed,
               count(*) FILTER (WHERE coalesce(attempts, 1) > 1) AS retried,
               coalesce(sum(tokens_in), 0) AS tokens_in, coalesce(sum(tokens_out), 0) AS tokens_out,
               round(coalesce(sum(cost_usd), 0)::numeric, 4) AS cost, round(avg(seconds)::numeric, 1) AS avg_seconds,
               coalesce(sum(rows_loaded), 0) AS rows_loaded, array_agg(DISTINCT model) FILTER (WHERE model IS NOT NULL) AS models,
               max(started_at) AS last_call
        FROM staging.prompt_run WHERE started_at >= now() - make_interval(days => %s)
        GROUP BY 1 ORDER BY cost DESC""", (days,))
    for p in prompts:
        p["pillar"] = pillar(p["prompt_id"].replace("tech_article", "technology_").replace("signal", "competitive_signal"))
    daily = _q(st, """SELECT started_at::date AS day, prompt_id, count(*) AS calls, round(sum(cost_usd)::numeric, 4) AS cost
                      FROM staging.prompt_run WHERE started_at >= now() - make_interval(days => %s) GROUP BY 1, 2 ORDER BY 1, 2""", (days,))
    failures = _q(st, """SELECT started_at, prompt_id, subject_key, model, attempts, left(error, 600) AS error
                         FROM staging.prompt_run WHERE status = 'failed' AND started_at >= now() - make_interval(days => %s)
                         ORDER BY started_at DESC LIMIT 200""", (days,))
    return {"prompts": prompts, "daily": daily, "failures": failures}


# ---- data added + coverage ----------------------------------------------------------------------------------------------------

def data(st, sv, days: int = 30) -> dict[str, Any]:
    written: dict[tuple, dict] = {}
    for s in _q(st, """SELECT started_at::date AS day, rows FROM ops.step
                       WHERE rows IS NOT NULL AND started_at >= now() - make_interval(days => %s)""", (days,)):
        for tbl, c in (s["rows"] or {}).items():
            k = (str(s["day"]), pillar(tbl))
            w = written.setdefault(k, {"day": str(s["day"]), "pillar": k[1], "insert": 0, "update": 0, "delete": 0})
            for a in ("insert", "update", "delete"):
                w[a] += int((c or {}).get(a, 0) or 0)
    approvals = _q(st, """SELECT at::date AS day, tbl, action, count(*) AS n FROM ops.record_event
                          WHERE action IN ('approve', 'reject', 'unpublish', 'undo') AND at >= now() - make_interval(days => %s)
                          GROUP BY 1, 2, 3 ORDER BY 1 DESC""", (days,))
    for a in approvals:
        a["pillar"] = pillar(a["tbl"])
    counts = []
    st.execute("""SELECT table_schema || '.' || table_name AS t FROM information_schema.tables
                  WHERE table_schema IN ('staging', 'staging_ui') AND table_type = 'BASE TABLE' ORDER BY 1""")
    staging_tables = [r["t"] for r in st.fetchall()]
    sv.execute("""SELECT table_schema || '.' || table_name AS t FROM information_schema.tables
                  WHERE table_schema IN ('serving', 'ui') AND table_type = 'BASE TABLE'""")
    serving_tables = {r["t"] for r in sv.fetchall()}
    for t in staging_tables:
        live = t.replace("staging_ui.", "ui.").replace("staging.", "serving.")
        st.execute(f'SELECT count(*) AS n FROM {t.split(".")[0]}."{t.split(".")[1]}"')
        n_st = st.fetchone()["n"]
        n_sv = None
        if live in serving_tables:
            sv.execute(f'SELECT count(*) AS n FROM {live.split(".")[0]}."{live.split(".")[1]}"')
            n_sv = sv.fetchone()["n"]
        counts.append({"table": t, "pillar": pillar(t), "staging": n_st, "serving": n_sv})
    return {"written": sorted(written.values(), key=lambda w: (w["day"], w["pillar"]), reverse=True), "approvals": approvals,
            "counts": counts}


def url_columns(st) -> list[tuple[str, str]]:
    """(table, column) of every staging column that holds the document a row came from"""
    st.execute(r"""SELECT table_name, column_name FROM information_schema.columns
                   WHERE table_schema = 'staging' AND column_name ~ '(^|_)url$'
                     AND column_name !~ '(image|thumbnail|logo|feed|archive|photo|pdf|website|homepage|careers|linkedin|portal|status_check|patent)'
                     AND table_name NOT IN ('source_document', 'news_candidate', 'tender_raw', 'source_link', 'fact_source', 'fx_rate')""")
    return [(r["table_name"], r["column_name"]) for r in st.fetchall()]


def coverage(st, days: int = 30) -> dict[str, Any]:
    """documents harvested in the window with routes: which promised pillars hold them. A route not fed = the lane has not read
    it yet, judged it not relevant, or failed on it (see Model calls / Errors)."""
    if not _has(st, "staging.source_document"):
        return {"routes": [], "docs": []}
    parts = [f'SELECT DISTINCT "{c}" AS url, \'{pillar(t)}\' AS pillar FROM staging."{t}" WHERE "{c}" IS NOT NULL' for t, c in url_columns(st)]
    docs = _q(st, f"""
        WITH used AS ({' UNION '.join(parts)})
        SELECT d.doc_id, d.url, d.title, d.source_name, coalesce(d.published_at, d.fetched_at::date) AS day,
               d.published_at IS NULL AS undated, d.triage->'route' AS routes,
               coalesce(array_agg(DISTINCT u.pillar) FILTER (WHERE u.pillar IS NOT NULL), '{{}}') AS pillars
        FROM staging.source_document d LEFT JOIN used u ON u.url = d.url
        WHERE d.fetched_at >= now() - make_interval(days => %s) AND jsonb_typeof(d.triage->'route') = 'array'
          AND NOT (d.triage->'route') @> '["none"]'
        GROUP BY d.doc_id""", (days,))
    per_route: dict[str, dict] = {}
    gaps = []
    for d in docs:
        promised = [ROUTE_PILLAR[r] for r in (d["routes"] or []) if r in ROUTE_PILLAR]
        missing = sorted({p for p in promised if p not in d["pillars"]})
        for r in d["routes"] or []:
            if r in ROUTE_PILLAR:
                pr = per_route.setdefault(r, {"route": r, "pillar": ROUTE_PILLAR[r], "routed": 0, "fed": 0})
                pr["routed"] += 1
                pr["fed"] += ROUTE_PILLAR[r] in d["pillars"]
        if missing and d["pillars"]:              # used somewhere, but not everywhere triage said: the hand-off gap
            gaps.append({**d, "missing": missing})
    return {"routes": sorted(per_route.values(), key=lambda r: -r["routed"]), "docs": len(docs),
            "used_anywhere": sum(1 for d in docs if d["pillars"]), "partial": gaps[:1000], "partial_total": len(gaps)}


def _selftest() -> None:
    assert pillar("staging.competitive_signal_detail") == "Signals" and pillar("technology_overview_article") == "Technology"
    assert pillar("staging.competitive_product_news") == "Product news" and pillar("staging.competitive_geo_product_news") == "Product news"
    assert pillar("staging.market_tender_source") == "Tenders" and pillar("staging.source_document") == "Raw"
    assert pillar("staging.competitive_competitor_moment_source") == "Competitor movement"
    assert _lines("ok\nTraceback (most recent call last):\n  x\nValueError: bad\nfine", ERROR_LINE) == \
        ["Traceback (most recent call last):", "ValueError: bad"]
    assert _lines("WARNING: slow\nall good", WARN_LINE) == ["WARNING: slow"]
    assert _kind("model: claude CLI error: You've hit your weekly limit") == "model usage limit"
    assert _kind('load: NotNullViolation: null value in column "source_url"') == "NotNullViolation"
    print("flow_dashboard self-check ok")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
