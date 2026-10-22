"""Database-backed KSSL dataset API.

The browser cannot connect to PostgreSQL directly. This small API reads the two
schema namespaces, exposes every table under ``database`` for traceable access,
and adapts the domain tables into the contract consumed by the existing React UI.
An empty database therefore produces empty arrays and maps throughout the UI.
"""

import json
import os
import uuid as _uuid
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from backend.areas import a_competitive, b_products, c_network, d_market_tech, e_ui_port
from backend import review
from backend.common import json_value

AREAS = (a_competitive, b_products, c_network, d_market_tech, e_ui_port)  # a first: others read competitors


# Two databases (db/make_databases.sh): the live backend reads the serving DB (KSSL_SERVING_DSN,
# schemas ui / serving); the review backend (KSSL_VIEW=review) reads the staging DB
# (KSSL_STAGING_DSN, schemas staging_ui / staging) under the same "ui" / "serving" keys. Each DSN
# falls back to KSSL_DSN (one database holding all four schemas, e.g. the kssl_v2_test* DBs).
REVIEW = os.environ.get("KSSL_VIEW", "").strip().lower() == "review"
SOURCE_SCHEMA = {"ui": "staging_ui", "serving": "staging"} if REVIEW else {"ui": "ui", "serving": "serving"}

app = FastAPI(title="KSSL PostgreSQL Dataset API", docs_url=None, redoc_url=None)
from backend.news import router as news_router; app.include_router(news_router)  # noqa: E402,E702
app.add_middleware(GZipMiddleware, minimum_size=1024)      # the dataset JSON compresses ~5x
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def writes_need_header(request, call_next):
    """CSRF guard: every write is a POST carrying X-KSSL-Write. A custom header forces a CORS preflight, which
    allow_methods=["GET"] refuses, so another website cannot fire a write from an operator's browser (cached
    basic auth on the review host, or 127.0.0.1)."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-kssl-write") != "1":
        return JSONResponse(status_code=403, content={"detail": "writes need the X-KSSL-Write: 1 header"})
    return await call_next(request)


# serving tables the frontend reads straight from data.database (grep src for "serving.<table>")
UI_SERVING_TABLES = ("technology_metric", "market_segment_assessment")


def build_dataset(database):
    """The UI contract. Each area module fills its keys; nothing is defaulted beyond empty."""
    # `database` carries only what the UI reads via uiText(): every ui table (labels, filter options,
    # section visibility) plus the serving tables in UI_SERVING_TABLES. The rest (raw layer, specs,
    # sources) stays server-side; sending it all made the review payload > 500 MB.
    # only competitors that qualify (same product line AND same market) reach the UI; the database keeps them all
    database = a_competitive.visible_database(database)
    sent = {"ui": database.get("ui", {}),
            "serving": {t: database.get("serving", {}).get(t, []) for t in UI_SERVING_TABLES}}
    d = {"database": sent, "details": {}}
    for area in AREAS:
        area.build(database, d)
    return d


def connect():
    dsn = review.staging_dsn() if REVIEW else review.serving_dsn()
    if not dsn:
        raise RuntimeError(
            "KSSL_SERVING_DSN / KSSL_STAGING_DSN (or KSSL_DSN) is not configured. Set it to the PostgreSQL connection string."
        )
    return psycopg2.connect(dsn, connect_timeout=5)


def load_all_tables() -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Read every table in ui and serving without relying on a hardcoded table list."""
    database: dict[str, dict[str, list[dict[str, Any]]]] = {"ui": {}, "serving": {}}
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for schema, source in SOURCE_SCHEMA.items():
                cur.execute(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = %s AND table_type = 'BASE TABLE'
                      AND table_name NOT IN ('fact_source', 'review_decision',
                                             -- raw layer / bookkeeping: prompt inputs, never displayed
                                             'tender_raw', 'source_document', 'news_candidate', 'prompt_run', 'spec_dictionary')
                    ORDER BY table_name
                    """,
                    (source,),
                )
                for name in [r["table_name"] for r in cur.fetchall()]:
                    cur.execute(
                        'SELECT * FROM "{}"."{}"'.format(source, name.replace('"', '""'))
                    )
                    database[schema][name] = [
                        {key: json_value(value) for key, value in dict(row).items()}
                        for row in cur.fetchall()
                    ]
            if REVIEW:          # the review drawer's per-signal prompt cost (db/setup/24_signal_prompt_stats.sql), never the live site
                cur.execute("SELECT to_regclass('staging.signal_prompt_stats') AS v")
                if cur.fetchone()["v"]:
                    cur.execute("SELECT * FROM staging.signal_prompt_stats")
                    database["serving"]["signal_prompt_stats"] = [{k: json_value(v) for k, v in dict(r).items()} for r in cur.fetchall()]
                # the one-sentence reason the signal prompt gave for each judgement (probability, impact per dimension, market,
                # product match, timing): the review drawer explains every risk check with it (owner 22 Oct)
                cur.execute("""SELECT row_id, column_name, quote FROM staging.fact_source
                               WHERE table_name = 'competitive_signal' AND source_tier = 'judgement' AND quote IS NOT NULL""")
                database["serving"]["signal_reasons"] = [dict(r) for r in cur.fetchall()]
    return database


def load_schema_manifest() -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Return every table's column metadata, including when all tables are empty."""
    manifest: dict[str, dict[str, list[dict[str, Any]]]] = {"ui": {}, "serving": {}}
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT table_schema, table_name, column_name, ordinal_position,
                       data_type, udt_name, is_nullable, character_maximum_length,
                       numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema IN %s
                ORDER BY table_schema, table_name, ordinal_position
                """,
                (tuple(SOURCE_SCHEMA.values()),),
            )
            back = {v: k for k, v in SOURCE_SCHEMA.items()}
            for row in cur.fetchall():
                schema = back[row["table_schema"]]
                name = row["table_name"]
                manifest[schema].setdefault(name, []).append({
                    key: json_value(value)
                    for key, value in dict(row).items()
                    if key not in ("table_schema", "table_name")
                })
    return manifest


@app.get("/api/health")
def health():
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"ok": True, "view": "review" if REVIEW else "live", "schemas": list(SOURCE_SCHEMA.values())}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)})


@app.get("/api/dataset")
def dataset():
    try:
        database = load_all_tables()
        payload = build_dataset(database)
        payload["databaseSchema"] = load_schema_manifest()
        if REVIEW:
            with review.session() as (st, sv):
                payload["review"] = review.statuses(st, sv)
        return payload
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"error": f"PostgreSQL dataset unavailable: {exc}"})


@app.get("/api/image/{image_id}")
def image(image_id: str):
    """A stored article image (media.image, backend/media_images.py). Both the live and the review API read it from the STAGING
    database: images are an asset cache, not reviewed content. Cached by the browser for a week (the id is a hash of its source)."""
    import uuid as _uuid
    from fastapi.responses import Response
    try:
        _uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(status_code=404)
    dsn = review.staging_dsn()
    if not dsn:
        raise HTTPException(status_code=404)
    with psycopg2.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("SELECT content_type, bytes FROM media.image WHERE image_id = %s", (image_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404)
    return Response(content=bytes(row[1]), media_type=row[0], headers={"Cache-Control": "public, max-age=604800, immutable"})


@app.get("/api/manifest")
def manifest():
    try:
        schema = load_schema_manifest()
        return {"schemas": schema, "read_only": True}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"error": str(exc)})


# ---- review copy: Approve / Reject / Undo / Unpublish, setup tables, Trace (backend/review.py) ----

def _review_only() -> None:
    # ponytail: access control is "only the review backend has these routes"; run it on
    # localhost/VPN. Add a login before exposing the review copy beyond that.
    if not REVIEW:
        raise HTTPException(status_code=404, detail="review routes exist only on the review backend")


def _run(fn, *args):
    """fn(staging cursor, serving cursor, *args), committed; then the fresh statuses."""
    try:
        with review.session() as (st, sv):
            fn(st, sv, *args)
        with review.session() as (st, sv):
            return review.statuses(st, sv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except psycopg2.Error as exc:
        raise HTTPException(status_code=500, detail=(exc.pgerror or str(exc)).strip()) from None


@app.post("/api/review")
def review_decide(table: str, key: str, action: str) -> dict[str, Any]:
    """Approve / reject / undo / unpublish one card. Returns the fresh statuses."""
    _review_only()
    if action not in review.ACTIONS:
        raise HTTPException(status_code=400, detail=f"action must be one of {sorted(review.ACTIONS)}")
    return {"table": table, "key": key, "action": action, "review": _run(review.ACTIONS[action], table, key)}


@app.post("/api/review/bulk")
def review_bulk(items: list[dict[str, str]] = Body(...)) -> dict[str, Any]:
    """Approve many cards at once (the review banner's "Approve all on this page"): new and changed alike.
    Each card commits on its own; a card whose parent is not live yet ("Approve its ... first") is retried
    after the others, pass after pass while a pass still approves something. Cards still failing are returned."""
    _review_only()
    todo = list({(i.get("table", ""), i.get("key", "")): None for i in items if i.get("table") and i.get("key")})
    if len(todo) > 2000:
        raise HTTPException(status_code=400, detail="at most 2000 cards per bulk approve")
    approved, failed = 0, {}
    while todo:
        left = []
        for t, k in todo:
            try:
                with review.session() as (st, sv):
                    review.approve(st, sv, t, k)
                approved += 1
                failed.pop((t, k), None)
            except (ValueError, psycopg2.Error) as exc:
                failed[(t, k)] = str(getattr(exc, "pgerror", None) or exc).strip()
                left.append((t, k))
        if len(left) == len(todo):
            break                                   # no progress: what is left needs something outside this page
        todo = left
    with review.session() as (st, sv):
        fresh = review.statuses(st, sv)
    return {"approved": approved, "failed": [{"table": t, "key": k, "error": e} for (t, k), e in failed.items()],
            "review": fresh}


@app.post("/api/review/table")
def review_table(schema: str, table: str, action: str) -> dict[str, Any]:
    """Approve (replace the whole live table) / unpublish (empty it) one setup table."""
    _review_only()
    if schema not in ("ui", "serving") or action not in review.TABLE_ACTIONS:
        raise HTTPException(status_code=400, detail="schema must be ui|serving, action approve|unpublish")
    return {"schema": schema, "table": table, "action": action,
            "review": _run(review.TABLE_ACTIONS[action], schema, table)}


# ---- usage log (db/setup/31_user_activity.sql, docs/ui_port/ACTIVITY_LOG.md): written by src/lib/track.js ----

TRACK_TYPES = {"page_view", "leave", "click", "search", "hover", "move", "scroll"}   # move / scroll: review session replay
TRACK_MAX = 100          # events per batch (the client flushes every few seconds)
TRACK_PROPS_MAX = 2000   # chars of props: a mouse path of ~40 points fits


def _uuid_or_none(v: Any) -> str | None:
    try:
        return str(_uuid.UUID(str(v)))
    except (ValueError, TypeError, AttributeError):
        return None


# ---- temporary login (owner 22 Oct; the real login page comes later) ------------------------------------------------
# KSSL_LOGIN_USERS in the gitignored .env: "user1:pbkdf2_sha256.<iterations>.<salt hex>.<hash hex>[,user2:...]" ("." not "$": the .env is read by bash).
# ponytail: checks a password and names the user for the UI and the usage log; no session token, the API is not locked.
def _login_users() -> dict[str, str]:
    out = {}
    for item in os.environ.get("KSSL_LOGIN_USERS", "").split(","):
        name, _, h = item.strip().partition(":")
        if name and h:
            out[name] = h
    return out


def _password_ok(password: str, stored: str) -> bool:
    import hashlib
    import hmac
    try:
        algo, iters, salt, want = stored.split(".")
        if algo != "pbkdf2_sha256":
            return False
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters)).hex()
        return hmac.compare_digest(got, want)
    except (ValueError, TypeError):
        return False


@app.post("/api/login")
def login(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if REVIEW:
        raise HTTPException(status_code=404, detail="the review site has no login")
    user = str(body.get("user") or "").strip()[:60]
    stored = _login_users().get(user)
    if not stored or not _password_ok(str(body.get("password") or ""), stored):
        raise HTTPException(status_code=401, detail="Wrong user or password")
    return {"user": user}


@app.post("/api/track")
def track(request: Request, events: list[dict[str, Any]] = Body(...)) -> dict[str, Any]:
    """A batch of usage events -> activity.event in this API's own DB (live -> serving DB, review -> staging DB). Anonymous:
    random browser / visit ids, no IP. The site is decided here, not by the client. Bad rows are dropped, not stored."""
    # ponytail: no rate limit beyond the batch cap and field caps; add one (per visitor per minute) if the log is abused
    if len(events) > TRACK_MAX:
        raise HTTPException(status_code=400, detail=f"at most {TRACK_MAX} events per batch")
    site = "review" if REVIEW else "live"
    ua = (request.headers.get("user-agent") or "")[:300] or None
    cut = lambda v, n: (str(v)[:n] or None) if v not in (None, "") else None  # noqa: E731
    rows = []
    for e in events:
        if not isinstance(e, dict) or e.get("type") not in TRACK_TYPES:
            continue
        vid, sid = _uuid_or_none(e.get("visitor")), _uuid_or_none(e.get("session"))
        if not vid or not sid:
            continue
        dur = e.get("ms")
        dur = int(dur) if isinstance(dur, (int, float)) and 0 <= dur < 86_400_000 else None
        props = e.get("props") if isinstance(e.get("props"), dict) else None
        if props is not None and len(json.dumps(props)) > TRACK_PROPS_MAX:
            props = None
        rows.append((cut(e.get("ts"), 40), site, vid, sid, e["type"], cut(e.get("pillar"), 40), cut(e.get("view"), 60),
                     cut(e.get("target"), 160), cut(e.get("value"), 300), dur, json.dumps(props) if props else None, ua,
                     cut(e.get("user"), 60)))
    if rows:
        with connect() as conn, conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, """INSERT INTO activity.event (client_ts, site, visitor_id, session_id, event_type, pillar,
                view, target, value, duration_ms, props, user_agent, user_id) VALUES %s""", rows,
                template="(%s::timestamptz, %s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)")
    return {"stored": len(rows), "dropped": len(events) - len(rows)}


@app.get("/api/review/trace")
def review_trace(table: str, key: str) -> dict[str, Any]:
    _review_only()
    try:
        with review.session() as (st, sv):
            return json_value(review.trace(st, sv, table, key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


# ---- session replay (owner 22 Oct): the review site plays back what a person did, from activity.event ----------------------
# The live site's events are in the serving DB, the review site's in the staging DB (see /api/track); site picks which.
REPLAY_USERS = [f"user{i}" for i in range(1, 6)]   # ponytail: the 5 login ids-to-be; renamed when the login lands
REPLAY_MAX_EVENTS = 20000


def _activity_cursor(site: str):
    if site not in ("live", "review"):
        raise HTTPException(status_code=400, detail="site is live or review")
    dsn = review.serving_dsn() if site == "live" else review.staging_dsn()
    conn = psycopg2.connect(dsn, connect_timeout=5)
    conn.set_session(readonly=True)
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _who(user: str | None, visitor: str | None) -> tuple[str, list]:
    """the WHERE part for one person: a login id (user_id, once the login exists) or an anonymous browser (visitor_id)"""
    if user:
        return "user_id = %s", [user]
    if visitor and _uuid_or_none(visitor):
        return "visitor_id = %s::uuid AND user_id IS NULL", [visitor]
    raise HTTPException(status_code=400, detail="user or visitor is required")


@app.get("/api/review/activity/people")
def activity_people(site: str = "live") -> dict[str, Any]:
    """The five users (login ids) and the anonymous browsers seen without a login, each with its event count and last visit."""
    _review_only()
    conn, cur = _activity_cursor(site)
    try:
        users = {u: {"id": u, "label": f"User {u[4:]}", "events": 0, "last": None} for u in REPLAY_USERS}
        cur.execute("""SELECT user_id AS id, count(*) AS events, max(coalesce(client_ts, received_at)) AS last
                       FROM activity.event WHERE user_id IS NOT NULL GROUP BY 1""")
        for r in cur.fetchall():
            users.setdefault(r["id"], {"id": r["id"], "label": r["id"]}).update(events=r["events"], last=r["last"])
        cur.execute("""SELECT visitor_id::text AS id, count(*) AS events, count(DISTINCT session_id) AS sessions,
                               min(coalesce(client_ts, received_at)) AS first, max(coalesce(client_ts, received_at)) AS last,
                               max(user_agent) AS user_agent
                       FROM activity.event WHERE user_id IS NULL GROUP BY 1 ORDER BY last DESC LIMIT 200""")
        return json_value({"site": site, "users": list(users.values()), "visitors": cur.fetchall()})
    finally:
        conn.close()


@app.get("/api/review/activity/sessions")
def activity_sessions(site: str = "live", user: str | None = None, visitor: str | None = None,
                      start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """One person's visits in a time window (ISO times; either end open): start, end, events, pages seen."""
    _review_only()
    conn, cur = _activity_cursor(site)
    try:
        where, args = _who(user, visitor)
        if start:
            where += " AND coalesce(client_ts, received_at) >= %s::timestamptz"
            args.append(start)
        if end:
            where += " AND coalesce(client_ts, received_at) < %s::timestamptz"
            args.append(end)
        cur.execute(f"""SELECT session_id::text AS id, min(coalesce(client_ts, received_at)) AS start,
                               max(coalesce(client_ts, received_at)) AS "end", count(*) AS events,
                               count(*) FILTER (WHERE event_type = 'page_view') AS pages,
                               count(*) FILTER (WHERE event_type = 'click') AS clicks,
                               count(*) FILTER (WHERE event_type = 'search') AS searches
                        FROM activity.event WHERE {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 500""", args)
        return json_value({"site": site, "sessions": cur.fetchall()})
    except psycopg2.DataError as exc:
        raise HTTPException(status_code=400, detail=f"bad time: {exc.pgerror or exc}") from None
    finally:
        conn.close()


@app.get("/api/review/activity/events")
def activity_events(site: str = "live", session: str = "") -> dict[str, Any]:
    """Every event of one visit, in the order it happened: what the player plays."""
    _review_only()
    sid = _uuid_or_none(session)
    if not sid:
        raise HTTPException(status_code=400, detail="session (uuid) is required")
    conn, cur = _activity_cursor(site)
    try:
        cur.execute("""SELECT event_id, coalesce(client_ts, received_at) AS ts, event_type AS type, pillar, view, target, value,
                              duration_ms AS ms, props
                       FROM activity.event WHERE session_id = %s::uuid
                       ORDER BY coalesce(client_ts, received_at), event_id LIMIT %s""", (sid, REPLAY_MAX_EVENTS))
        return json_value({"site": site, "session": sid, "events": cur.fetchall()})
    finally:
        conn.close()


# ---- pipeline log (review site only): runs -> steps -> records, and one record's journey (backend/pipeline_log.py) ----------

def _pipeline(fn, *args):
    _review_only()
    from backend import pipeline_log
    try:
        with review.session() as (st, sv):
            return json_value(getattr(pipeline_log, fn)(st, *args) if fn != "journey" else pipeline_log.journey(st, sv, *args))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.get("/api/review/pipeline/runs")
def pipeline_runs() -> dict[str, Any]:
    """Live runs and, before the live log, one reconstructed run per day (newest first)."""
    return {"runs": _pipeline("runs")}


@app.get("/api/review/pipeline/steps")
def pipeline_steps(run: str) -> dict[str, Any]:
    """A run's steps: run uuid, or day:YYYY-MM-DD for the steps outside a run."""
    return {"run": run, "steps": _pipeline("steps", run)}


@app.get("/api/review/pipeline/records")
def pipeline_records(step: str) -> dict[str, Any]:
    """What one step touched (capped at 300 rows)."""
    return {"step": step, **_pipeline("step_records", step)}


@app.get("/api/review/pipeline/journey")
def pipeline_journey(table: str, id: str) -> dict[str, Any]:  # noqa: A002 -- the query parameter is "id"
    """One record from harvest to the live site, in time order."""
    return _pipeline("journey", table, id)


@app.get("/api/review/pipeline/search")
def pipeline_search(q: str) -> dict[str, Any]:
    """Records by 'table:id', by a source url, or by title text."""
    return {"q": q, "results": _pipeline("search", q)}
