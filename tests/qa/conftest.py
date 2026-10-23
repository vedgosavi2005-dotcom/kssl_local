"""QA suite: database -> backend API -> UI, end to end (owner 2026-10-23). Run it all with `python tests/qa/run_qa.py`.

Targets (env, else the local defaults; read from the repo's .env too):
  KSSL_QA_STAGING_DSN / KSSL_QA_SERVING_DSN   else KSSL_STAGING_DSN / KSSL_SERVING_DSN
  KSSL_QA_LIVE_API    http://127.0.0.1:8600      KSSL_QA_REVIEW_API  http://127.0.0.1:8601
  KSSL_QA_REVIEW_AUTH "user:password" for a review site behind basic auth (the VPS)
Database sessions are opened READ ONLY: no test can change real data. The only writes are the usage-log tests
(POST /api/track), which tag their rows visitor = QA_VISITOR and delete them afterwards.

Every test's docstring is its test case: first line "ID · title", then "Steps:" and "Expected:" -- run_qa.py turns
them, with each result, into the QA workbook.
"""
from __future__ import annotations

import functools
import json
import os
import re
import uuid
from pathlib import Path

import httpx
import psycopg2
import psycopg2.extras
import pytest

ROOT = Path(__file__).resolve().parents[2]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))                           # backend.review.GRAPH is the card model the tests check against
OUT = Path(__file__).resolve().parent / "out"
QA_VISITOR = "00000000-0000-4000-8000-00000000a11a"     # every row the suite writes carries this visitor id


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line.strip())
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip().strip("\"'")


_load_env()
DSN = {"staging": os.environ.get("KSSL_QA_STAGING_DSN") or os.environ.get("KSSL_STAGING_DSN", ""),
       "serving": os.environ.get("KSSL_QA_SERVING_DSN") or os.environ.get("KSSL_SERVING_DSN", "")}
API = {"live": os.environ.get("KSSL_QA_LIVE_API", "http://127.0.0.1:8600").rstrip("/"),
       "review": os.environ.get("KSSL_QA_REVIEW_API", "http://127.0.0.1:8601").rstrip("/")}
SITE_DB = {"live": "serving", "review": "staging"}          # which database each site's API reads
CARD_SCHEMA = {"staging": "staging", "serving": "serving"}  # card tables' schema in each database
UI_SCHEMA = {"staging": "staging_ui", "serving": "ui"}


def connect(db: str):
    conn = psycopg2.connect(DSN[db], connect_timeout=10, options="-c default_transaction_read_only=on -c statement_timeout=120000")
    conn.autocommit = True
    return conn


_CONNS: dict[str, object] = {}


def _conn(db: str):
    c = _CONNS.get(db)
    if c is None or c.closed:
        c = _CONNS[db] = connect(db)
    return c


def rows(db: str, sql: str, args=None) -> list[dict]:
    with _conn(db).cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]


def scalar(db: str, sql: str, args=None):
    with _conn(db).cursor() as cur:
        cur.execute(sql, args)
        r = cur.fetchone()
        return r[0] if r else None


@functools.lru_cache(maxsize=None)
def tables(db: str, schema: str) -> list[str]:
    return [r["table_name"] for r in rows(db, """SELECT table_name FROM information_schema.tables
                                                 WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY 1""", (schema,))]


@functools.lru_cache(maxsize=None)
def columns(db: str, schema: str, table: str) -> dict[str, str]:
    return {r["column_name"]: r["data_type"] for r in rows(db, """SELECT column_name, data_type FROM information_schema.columns
                                                                  WHERE table_schema = %s AND table_name = %s""", (schema, table))}


def client(site: str, timeout: float = 180) -> httpx.Client:
    auth = None
    if site == "review" and os.environ.get("KSSL_QA_REVIEW_AUTH"):
        u, _, p = os.environ["KSSL_QA_REVIEW_AUTH"].partition(":")
        auth = (u, p)
    return httpx.Client(base_url=API[site], timeout=timeout, auth=auth)


_DATASETS: dict[str, dict] = {}


def dataset(site: str) -> dict:
    """GET /api/dataset once per site per run (retried once: a deadlock with a running loader answers 503)"""
    if site not in _DATASETS:
        with client(site) as c:
            for _ in range(2):
                r = c.get("/api/dataset")
                if r.status_code == 200:
                    break
        assert r.status_code == 200, f"/api/dataset on {site}: {r.status_code} {r.text[:300]}"
        _DATASETS[site] = r.json()
    return _DATASETS[site]


def src_objects(payload: dict) -> list[tuple[str, dict]]:
    """every (top-level collection, object) in a dataset that names its database row in _src {t, k, id}"""
    out: list[tuple[str, dict]] = []

    def walk(o, top):
        if isinstance(o, dict):
            s = o.get("_src")
            if isinstance(s, dict) and s.get("t"):
                out.append((top, o))
            for k, v in o.items():
                if k != "_src":
                    walk(v, top)
        elif isinstance(o, list):
            for v in o:
                walk(v, top)

    for k, v in payload.items():
        if k not in ("database", "databaseSchema", "review"):
            walk(v, k)
    return out


def dead_links() -> dict[str, str]:
    """{dead source url: archive copy} -- the APIs serve the archive copy in place of the dead url (db/setup/38)"""
    if not scalar("staging", "SELECT to_regclass('staging.source_link') IS NOT NULL"):
        return {}
    return {r["url"]: r["archive_url"] for r in rows("staging", """SELECT url, archive_url FROM staging.source_link
                                                                  WHERE status IN (404, 410) AND archive_url IS NOT NULL""")}


# ---- results for the workbook ----------------------------------------------------------------------------------------------

_RESULTS: list[dict] = []


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        item = _ITEMS.get(report.nodeid, {})
        detail = ""
        if report.outcome == "failed":
            detail = str(getattr(report, "longreprtext", "") or report.longrepr)
            m = re.findall(r"^E\s+(.*)$", detail, re.M)
            detail = "\n".join(m[:12]) if m else detail[-1500:]
        elif report.outcome == "skipped":
            detail = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        _RESULTS.append({**item, "nodeid": report.nodeid, "outcome": report.outcome, "detail": detail[:3000],
                         "seconds": round(report.duration, 2)})


_ITEMS: dict[str, dict] = {}


def pytest_collection_modifyitems(items):
    for it in items:
        doc = (it.function.__doc__ or "").strip()
        head, _, rest = doc.partition("\n")
        tid, _, title = head.partition("·")
        steps = re.search(r"Steps:(.*?)(?:Expected:|$)", rest, re.S)
        exp = re.search(r"Expected:(.*)$", rest, re.S)
        param = it.callspec.id if hasattr(it, "callspec") else ""
        _ITEMS[it.nodeid] = {"id": tid.strip() + (f"[{param}]" if param else ""), "case": tid.strip(), "title": title.strip(),
                             "param": param, "area": it.module.__name__.replace("test_", "").upper(),
                             "steps": " ".join((steps.group(1) if steps else "").split()),
                             "expected": " ".join((exp.group(1) if exp else "").split())}


def pytest_sessionfinish(session):
    OUT.mkdir(exist_ok=True)
    (OUT / "pytest_results.json").write_text(json.dumps(_RESULTS, indent=1, default=str), encoding="utf-8")


@pytest.fixture
def qa_session_id():
    return str(uuid.uuid4())
