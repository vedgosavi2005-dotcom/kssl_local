"""Database access for the agent: the analytics layer, the read-only role, the schema
catalogue the data agent is prompted with, and query execution."""

import datetime as dt
import os
import re
import secrets
import threading
import time
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extensions
import psycopg2.extras
import psycopg2.sql

from . import adapter, config
from .sql_guard import check_sql

# the product's data, as the views the agents query (adapter/analytics.sql)
ANALYTICS_SQL = adapter.path("analytics.sql")

_lock = threading.Lock()
_state = {"agent_dsn": None, "catalog": None, "companies": None, "facts": None, "company_list": None, "error": None}


def _main_dsn() -> str:
    # the same connection string app.py uses (superuser in the compose stack)
    return os.environ.get("KSSL_DSN", "host=127.0.0.1 port=5460 dbname=kssl user=postgres password=kssl")


def ensure_analytics() -> None:
    """Apply analytics.sql and set the agent role's password. Idempotent; runs at startup
    so an existing database volume gets the views without a re-init. Failures are kept
    in _state["error"] and surfaced by /api/agent/status rather than stopping the app."""
    password = config.AGENT_DB_PASSWORD or secrets.token_urlsafe(24)
    try:
        conn = psycopg2.connect(_main_dsn(), connect_timeout=5)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                if config.ENSURE_ANALYTICS:
                    cur.execute(ANALYTICS_SQL.read_text(encoding="utf-8"))
                cur.execute(
                    psycopg2.sql.SQL("ALTER ROLE {} PASSWORD %s").format(
                        psycopg2.sql.Identifier(config.AGENT_DB_ROLE)
                    ),
                    (password,),
                )
        finally:
            conn.close()
        parts = psycopg2.extensions.parse_dsn(_main_dsn())
        parts.update(user=config.AGENT_DB_ROLE, password=password,
                     options="-c default_transaction_read_only=on -c statement_timeout=5000")
        with _lock:
            _state["agent_dsn"] = psycopg2.extensions.make_dsn(**parts)
            _state["catalog"] = None
            _state["companies"] = None
            _state["facts"] = None
            _state["company_list"] = None
            _state["error"] = None
    except Exception as exc:  # the rest of the app must keep serving
        with _lock:
            _state["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[agent] analytics layer unavailable: {exc}", flush=True)


def status() -> dict:
    with _lock:
        return {"ready": _state["agent_dsn"] is not None, "error": _state["error"]}


def _agent_conn():
    dsn = _state["agent_dsn"]
    if not dsn:
        raise RuntimeError(_state["error"] or "analytics layer not initialised")
    conn = psycopg2.connect(dsn, connect_timeout=5)
    conn.set_session(readonly=True, autocommit=True)
    return conn


# ---------------------------------------------------------------- results

_NUMBER_OIDS = {20, 21, 23, 26, 700, 701, 1700}
_DATE_OIDS = {1082, 1114, 1184}
_BOOL_OIDS = {16}


def _col_type(oid: int) -> str:
    if oid in _NUMBER_OIDS:
        return "number"
    if oid in _DATE_OIDS:
        return "date"
    if oid in _BOOL_OIDS:
        return "boolean"
    return "text"


def _jsonable(v):
    if isinstance(v, Decimal):
        f = float(v)
        return int(f) if f.is_integer() and abs(f) < 1e15 else round(f, 6)
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()[:10] if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else v.isoformat()
    if isinstance(v, (list, dict, str, int, bool)) or v is None:
        return v
    return str(v)


def run_query(sql: str) -> dict:
    """Validate and run one SELECT as parallax_agent. Returns columns, rows (lists),
    whether the row cap was hit, and timing. Raises SqlRejected or psycopg2.Error."""
    statement = check_sql(sql)
    t0 = time.monotonic()
    conn = _agent_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
            if cur.description is None:
                raise psycopg2.ProgrammingError("query returned no result set")
            cols = [{"name": d.name, "type": _col_type(d.type_code)} for d in cur.description]
            raw = cur.fetchmany(config.MAX_ROWS + 1)
    finally:
        conn.close()
    truncated = len(raw) > config.MAX_ROWS
    rows = [[_jsonable(v) for v in r] for r in raw[: config.MAX_ROWS]]
    # duplicate column names (two COUNT(*)s) would collide in the frontend's row objects
    seen = {}
    for c in cols:
        if c["name"] in seen:
            seen[c["name"]] += 1
            c["name"] = f'{c["name"]}_{seen[c["name"]]}'
        else:
            seen[c["name"]] = 1
    return {"columns": cols, "rows": rows, "truncated": truncated,
            "ms": int((time.monotonic() - t0) * 1000)}


def fetch(sql: str, params=()) -> list:
    """Internal, parameterised lookups (navigation targets). Same read-only role; the
    SQL here is ours, never the model's, so it skips the static guard."""
    conn = _agent_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [{k: _jsonable(v) for k, v in r.items()} for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------- catalogue

_CATALOG_SQL = """
SELECT c.relname AS view, obj_description(c.oid, 'pg_class') AS view_comment,
       a.attname AS col, format_type(a.atttypid, a.atttypmod) AS type,
       col_description(c.oid, a.attnum) AS col_comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'analytics'
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE c.relkind = 'v'
ORDER BY c.relname, a.attnum
"""

# views listed first in the prompt, in the order a question usually needs them
_VIEW_ORDER = adapter.manifest()["database"]["catalog_order"]


def schema_catalog() -> str:
    """The analytics schema as prompt text: each view, its purpose, its columns with type
    and meaning, and the actual values of low-cardinality text columns (so the agent
    filters on 'Saudi Arabia', not 'KSA'). Built once from the live database."""
    with _lock:
        if _state["catalog"]:
            return _state["catalog"]
    conn = psycopg2.connect(_main_dsn(), connect_timeout=5)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_CATALOG_SQL)
            rows = cur.fetchall()
            views = {}
            for r in rows:
                v = views.setdefault(r["view"], {"comment": r["view_comment"], "cols": []})
                v["cols"].append(r)
            lines = []
            order = [v for v in _VIEW_ORDER if v in views] + sorted(set(views) - set(_VIEW_ORDER))
            for name in order:
                v = views[name]
                cur.execute(psycopg2.sql.SQL("SELECT count(*) AS n FROM analytics.{}").format(
                    psycopg2.sql.Identifier(name)))
                n = cur.fetchone()["n"]
                lines.append(f"\n## analytics.{name}  ({n} rows)")
                if v["comment"]:
                    lines.append(v["comment"])
                for c in v["cols"]:
                    desc = f"  - {c['col']} {c['type']}"
                    if c["col_comment"]:
                        desc += f" -- {c['col_comment']}"
                    # a comment that already enumerates the values ("a | b | c") is enough
                    if c["type"] == "text" and "|" not in (c["col_comment"] or ""):
                        vals = _distinct_values(cur, name, c["col"])
                        if vals:
                            desc += f"  [values: {vals}]"
                    lines.append(desc)
            text = "\n".join(lines).strip()
    finally:
        conn.close()
    with _lock:
        _state["catalog"] = text
    return text


def _distinct_values(cur, view: str, col: str, limit: int = 14):
    cur.execute(
        psycopg2.sql.SQL(
            "SELECT {c} AS v, count(*) AS n FROM analytics.{v} WHERE {c} IS NOT NULL "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT %s"
        ).format(c=psycopg2.sql.Identifier(col), v=psycopg2.sql.Identifier(view)),
        (limit + 1,),
    )
    vals = cur.fetchall()
    if not vals or len(vals) > limit or any(len(str(r["v"])) > 48 for r in vals):
        return None
    return " | ".join(str(r["v"]) for r in vals)


def companies() -> list:
    """comp_id and display name of every tracked company -- the orchestrator's
    navigation targets for profile/products pages."""
    with _lock:
        if _state["companies"] is not None:
            return _state["companies"]
    out = run_query(adapter.manifest()["database"]["companies_sql"])
    names = [dict(zip([c["name"] for c in out["columns"]], r)) for r in out["rows"]]
    with _lock:
        _state["companies"] = names
    return names


def facts() -> dict:
    """The live figures the prompts quote (adapter/product.json database.facts: name -> SQL
    returning one value), so a new data version never leaves stale counts in a prompt."""
    with _lock:
        if _state["facts"] is not None:
            return _state["facts"]
    out = {}
    for name, sql in adapter.manifest()["database"].get("facts", {}).items():
        try:
            row = fetch(sql)
            out[name] = next(iter(row[0].values())) if row else ""
        except Exception as exc:
            print(f"[agent] fact {name!r} failed: {exc}", flush=True)
    with _lock:
        _state["facts"] = out
    return out


def company_list() -> list:
    """Companies in the shape product.json lists them (id, name, client, known_as, aliases,
    color_slot, color_match), from the data: companies_sql (client first) plus company_alias.
    Used when product.json says "companies": "from_data"."""
    with _lock:
        if _state["company_list"] is not None:
            return _state["company_list"]
    aliases = {}
    try:
        for r in fetch("SELECT comp_id, alias FROM company_alias"):
            aliases.setdefault(str(r["comp_id"]), []).append(str(r["alias"]))
    except Exception:
        pass
    out = []
    for slot, r in enumerate(companies()):
        cid, name = str(r["comp_id"]), str(r["name"])
        words = sorted({name, *aliases.get(cid, [])}, key=len, reverse=True)
        out.append({"id": cid, "name": name, "client": bool(r.get("is_client")), "known_as": name,
                    "aliases": sorted({w.lower() for w in words}), "color_slot": slot,
                    "color_match": "|".join(re.escape(w) for w in words)})
    with _lock:
        _state["company_list"] = out
    return out
