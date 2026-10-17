"""Database-backed KSSL dataset API.

The browser cannot connect to PostgreSQL directly. This small API reads the two
schema namespaces, exposes every table under ``database`` for traceable access,
and adapts the domain tables into the contract consumed by the existing React UI.
An empty database therefore produces empty arrays and maps throughout the UI.
"""

import os
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
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


# serving tables the frontend reads straight from data.database (grep src for "serving.<table>")
UI_SERVING_TABLES = ("technology_metric", "market_segment_assessment")


def build_dataset(database):
    """The UI contract. Each area module fills its keys; nothing is defaulted beyond empty."""
    # `database` carries only what the UI reads via uiText(): every ui table (labels, filter options,
    # section visibility) plus the serving tables in UI_SERVING_TABLES. The rest (raw layer, specs,
    # sources) stays server-side; sending it all made the review payload > 500 MB.
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


@app.post("/api/review/table")
def review_table(schema: str, table: str, action: str) -> dict[str, Any]:
    """Approve (replace the whole live table) / unpublish (empty it) one setup table."""
    _review_only()
    if schema not in ("ui", "serving") or action not in review.TABLE_ACTIONS:
        raise HTTPException(status_code=400, detail="schema must be ui|serving, action approve|unpublish")
    return {"schema": schema, "table": table, "action": action,
            "review": _run(review.TABLE_ACTIONS[action], schema, table)}


@app.get("/api/review/trace")
def review_trace(table: str, key: str) -> dict[str, Any]:
    _review_only()
    try:
        with review.session() as (st, sv):
            return json_value(review.trace(st, sv, table, key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
