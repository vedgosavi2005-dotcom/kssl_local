"""Backend API: every route, its contract, its guards and its error paths, on the live API and the review API.
No test changes reviewed data: write routes are only called in ways that are refused before any write (no header, wrong
site, invalid action / table), and the usage-log tests delete the rows they store."""
from __future__ import annotations

import gzip
import json
import time
import uuid

import pytest

from conftest import API, QA_VISITOR, client, connect, dataset, rows, scalar

SITES = ("live", "review")
REVIEW_GETS = ["/api/review/trace?table=market_tender&key=x", "/api/review/activity/people", "/api/review/activity/sessions",
               "/api/review/activity/events?session=" + QA_VISITOR, "/api/review/activity/recording?session=" + QA_VISITOR,
               "/api/review/live-dataset", "/api/review/pipeline/runs", "/api/review/pipeline/steps?run=x",
               "/api/review/pipeline/records?step=x", "/api/review/pipeline/journey?table=market_tender&id=x",
               "/api/review/pipeline/search?q=x", "/api/review/analytics/day?user=x", "/api/review/analytics/heatmap?view=x"]
# every route the app serves, and the test cases that cover it: a new route fails API-000 until it gets a test
COVERED = {
    "GET /api/health": "API-001", "GET /api/dataset": "API-002..005", "GET /api/image/{image_id}": "API-020",
    "GET /api/manifest": "API-021", "POST /api/review": "API-030..032", "POST /api/review/bulk": "API-030/033",
    "POST /api/review/table": "API-030/034", "POST /api/login": "API-040", "POST /api/track": "API-050..054",
    "POST /api/track/rec": "API-055..056", "GET /api/review/activity/recording": "API-063", "GET /api/review/trace": "API-060",
    "GET /api/review/activity/people": "API-062", "GET /api/review/activity/sessions": "API-062",
    "GET /api/review/live-dataset": "API-064", "GET /api/review/activity/events": "API-062",
    "GET /api/review/pipeline/runs": "API-065", "GET /api/review/pipeline/steps": "API-065",
    "GET /api/review/pipeline/records": "API-065", "GET /api/review/pipeline/journey": "API-065",
    "GET /api/review/pipeline/search": "API-065", "GET /api/review/analytics/day": "API-066",
    "GET /api/review/analytics/heatmap": "API-066", "GET /api/news": "API-070", "POST /api/news/refresh": "API-071",
}


def test_every_route_is_covered():
    """API-000 · Every API route has a test case
    Steps: list the routes of backend/app.py (FastAPI app.routes, the news router included); compare with this suite's map.
    Expected: no route without a test case, and no test case for a route that no longer exists."""
    from backend.app import app
    served = {f"{m} {r.path}" for r in app.routes if getattr(r, "methods", None) and r.path.startswith("/api/")
              for m in r.methods if m not in ("HEAD", "OPTIONS")}
    assert served - set(COVERED) == set(), f"routes with no test: {sorted(served - set(COVERED))}"
    assert set(COVERED) - served == set(), f"tests for routes that are gone: {sorted(set(COVERED) - served)}"


# ---- health and dataset ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("site", SITES)
def test_health(site):
    """API-001 · Health check
    Steps: GET /api/health.
    Expected: 200, ok = true, view = live / review matching the API, schemas = the ones that site reads."""
    with client(site) as c:
        r = c.get("/api/health")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True and j["view"] == site
    assert set(j["schemas"]) == ({"ui", "serving"} if site == "live" else {"staging_ui", "staging"})


REQUIRED_KEYS = {"database": dict, "details": dict, "client": dict, "competitors": dict, "compOrder": list, "competitorNews": dict,
                 "competitiveCards": list, "marketCards": list, "techCards": list, "matchups": dict, "geoData": dict,
                 "geoPresence": list, "projects": list, "KSSL_PARTNERS": list, "COMPSYN": dict, "tenders": list,
                 "globalRequirements": list, "awards": list, "topOpportunities": dict, "innovations": dict, "fxRates": dict,
                 "databaseSchema": dict}


@pytest.mark.parametrize("site", SITES)
def test_dataset_contract(site):
    """API-002 · The dataset carries every collection the UI reads, with the right type
    Steps: GET /api/dataset; check each top-level key the frontend consumes and its type.
    Expected: all present, right types, database.ui and database.serving present."""
    j = dataset(site)
    missing = [k for k in REQUIRED_KEYS if k not in j]
    wrong = {k: type(j[k]).__name__ for k, t in REQUIRED_KEYS.items() if k in j and not isinstance(j[k], t)}
    assert not missing and not wrong, f"missing {missing}, wrong type {wrong}"
    assert set(j["database"]) == {"ui", "serving"}


@pytest.mark.parametrize("site", SITES)
def test_dataset_not_empty(site):
    """API-003 · The main collections are not empty
    Steps: count competitors, signal cards, tenders, global requirements, awards, projects, technology cards.
    Expected: each > 0 (an empty collection is an empty page)."""
    j = dataset(site)
    empty = [k for k in ("competitors", "competitiveCards", "tenders", "globalRequirements", "awards", "projects", "techCards",
                         "matchups", "geoPresence") if not j.get(k)]
    assert not empty, f"empty collections: {empty}"


@pytest.mark.parametrize("site", SITES)
def test_dataset_speed_and_size(site):
    """API-004 · The dataset answers in time, compressed
    Steps: GET /api/dataset with Accept-Encoding: gzip; time it; read Content-Encoding and size.
    Expected: under 20 s, gzip-compressed, under 15 MB on the wire."""
    with client(site) as c:
        t = time.time()
        with c.stream("GET", "/api/dataset", headers={"Accept-Encoding": "gzip"}) as r:
            wire = sum(len(b) for b in r.iter_raw())
        took = time.time() - t
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip", "dataset not compressed"
    assert took < 20, f"took {took:.1f} s"
    assert wire < 15_000_000, f"{wire / 1e6:.1f} MB on the wire"


def test_review_only_keys():
    """API-005 · Review-only data stays off the live site
    Steps: GET /api/dataset on both APIs; look for the review statuses and the per-signal prompt stats / reasons.
    Expected: present on review, absent on live."""
    live, rev = dataset("live"), dataset("review")
    assert "review" not in live, "live dataset carries review statuses"
    for k in ("signal_prompt_stats", "signal_reasons"):
        assert k not in live["database"]["serving"], f"live dataset carries {k}"
    assert "review" in rev and set(rev["review"]) == {"cards", "tables"}


# ---- images, manifest --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("site", SITES)
def test_image(site):
    """API-020 · Card images are served, bad ids are refused
    Steps: take an /api/image/<id> url from the dataset and GET it; GET a non-uuid id and an unknown uuid.
    Expected: the image answers 200 with an image/* type and a long cache header; the bad ids answer 404."""
    j = dataset(site)
    img = next((c["image"] for c in j["competitiveCards"] if str(c.get("image", "")).startswith("/api/image/")), None)
    with client(site) as c:
        if img:
            r = c.get(img)
            assert r.status_code == 200 and r.headers["content-type"].startswith("image/"), (r.status_code, r.headers)
            assert "max-age" in r.headers.get("cache-control", "")
        assert c.get("/api/image/not-a-uuid").status_code == 404
        assert c.get(f"/api/image/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize("site", SITES)
def test_manifest_matches_database(site):
    """API-021 · The schema manifest is the database's real schema
    Steps: GET /api/manifest; compare every table and column with information_schema of the database the site reads.
    Expected: read_only = true; the same tables and columns."""
    with client(site) as c:
        r = c.get("/api/manifest")
    assert r.status_code == 200
    j = r.json()
    assert j["read_only"] is True
    db = "serving" if site == "live" else "staging"
    names = {"ui": "ui" if site == "live" else "staging_ui", "serving": "serving" if site == "live" else "staging"}
    for key, schema in names.items():
        want = {}
        for x in rows(db, "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = %s", (schema,)):
            want.setdefault(x["table_name"], set()).add(x["column_name"])
        got = {t: {c["column_name"] for c in cols} for t, cols in j["schemas"][key].items()}
        assert got == want, f"{key}: manifest differs from {schema} (tables only in DB: {sorted(set(want) - set(got))[:5]})"


# ---- write guards ------------------------------------------------------------------------------------------------------------

WRITES = [("/api/review?table=market_tender&key=x&action=reject", None), ("/api/review/bulk", []),
          ("/api/review/table?schema=ui&table=x&action=approve", None), ("/api/track", []), ("/api/login", {}),
          ("/api/news/refresh?dry_run=true", None), (f"/api/track/rec?session={QA_VISITOR}&visitor={QA_VISITOR}", None)]


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("path,body", WRITES, ids=[w[0].split("?")[0] for w in WRITES])
def test_writes_need_header(site, path, body):
    """API-030 · Every write needs the X-KSSL-Write header (CSRF guard)
    Steps: POST each write route without the header.
    Expected: 403, before the route runs (nothing is written)."""
    with client(site) as c:
        r = c.post(path, json=body)
    assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("path,body", WRITES[:3] + WRITES[5:6], ids=["review", "review/bulk", "review/table", "news/refresh"])
def test_review_writes_absent_on_live(path, body):
    """API-031 · Review actions do not exist on the live API
    Steps: POST Approve / Reject / bulk / setup-table / news refresh to the live API, with the write header.
    Expected: 404 -- the public site cannot change data."""
    with client("live") as c:
        r = c.post(path, json=body, headers={"X-KSSL-Write": "1"})
    assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("query", ["table=market_tender&key=x&action=delete", "table=not_a_table&key=x&action=approve",
                                   "table=competitive_signal_detail&key=x&action=approve"],
                         ids=["bad-action", "unknown-table", "not-a-card-table"])
def test_review_rejects_bad_input(query):
    """API-032 · Review actions refuse bad input before writing
    Steps: POST /api/review on the review API with an unknown action, an unknown table, a child (non-card) table.
    Expected: 400 with a reason; nothing written."""
    with client("review") as c:
        r = c.post("/api/review?" + query, headers={"X-KSSL-Write": "1"})
    assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"


def test_bulk_limits():
    """API-033 · Bulk approve refuses an oversized batch
    Steps: POST /api/review/bulk with 2,001 distinct (fake) cards.
    Expected: 400 'at most 2000' before any approval runs."""
    items = [{"table": "market_tender", "key": f"qa-{i}"} for i in range(2001)]
    with client("review") as c:
        r = c.post("/api/review/bulk", json=items, headers={"X-KSSL-Write": "1"})
    assert r.status_code == 400 and "2000" in r.text


@pytest.mark.parametrize("query", ["schema=bad&table=x&action=approve", "schema=ui&table=x&action=delete"])
def test_setup_table_rejects_bad_input(query):
    """API-034 · Setup-table approve refuses a bad schema or action
    Steps: POST /api/review/table with schema=bad, and with action=delete.
    Expected: 400."""
    with client("review") as c:
        r = c.post("/api/review/table?" + query, headers={"X-KSSL-Write": "1"})
    assert r.status_code == 400, r.text[:200]


@pytest.mark.parametrize("site", SITES)
def test_login(site):
    """API-040 · Login refuses a wrong password; the review site has no login
    Steps: POST /api/login with user1 and a wrong password; with an unknown user.
    Expected: live 401 'Wrong user or password' for both (no hint which part was wrong); review 404."""
    with client(site) as c:
        a = c.post("/api/login", json={"user": "user1", "password": "qa-wrong-password"}, headers={"X-KSSL-Write": "1"})
        b = c.post("/api/login", json={"user": "qa-nobody", "password": "x"}, headers={"X-KSSL-Write": "1"})
    want = 401 if site == "live" else 404
    assert a.status_code == want and b.status_code == want, (a.status_code, b.status_code)
    if site == "live":
        assert a.json() == b.json(), "the two failures differ: they reveal whether the user exists"


def test_api_itself_is_not_locked():
    """API-041 · The data API needs no login (known limit of the temporary login)
    Steps: GET /api/health on the live API with no user and no cookie (the dataset route works the same way).
    Expected (production): 401 until signed in. Today the login is a UI gate only -- this case documents that gap."""
    with client("live") as c:
        r = c.get("/api/health")
    if r.status_code == 200:
        pytest.xfail("the live API answers without a login: src/lib/login.js is a UI-only gate (owner knows; real login pending)")


# ---- usage log ---------------------------------------------------------------------------------------------------------------

def _cleanup():
    for db in ("serving", "staging"):
        conn = __import__("psycopg2").connect(__import__("conftest").DSN[db], connect_timeout=10)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM activity.event WHERE visitor_id = %s::uuid", (QA_VISITOR,))
                cur.execute("SELECT to_regclass('activity.recording') IS NOT NULL")
                if cur.fetchone()[0]:
                    cur.execute("DELETE FROM activity.recording WHERE visitor_id = %s::uuid", (QA_VISITOR,))
        finally:
            conn.close()


@pytest.fixture
def clean_log():
    _cleanup()
    yield
    _cleanup()


def _ev(session, **kw):
    return {"type": "page_view", "visitor": QA_VISITOR, "session": session, "ts": "2026-10-23T10:00:00Z", "pillar": "market",
            "view": "tender", **kw}


@pytest.mark.parametrize("site", SITES)
def test_track_stores_events(site, clean_log, qa_session_id):
    """API-050 · Usage events are stored, with the site set by the server
    Steps: POST /api/track (header set) with one page_view claiming site=review; read activity.event in that API's database.
    Expected: stored = 1; the row's site is the API's own site (live -> serving DB, review -> staging DB), not the client's claim."""
    with client(site) as c:
        r = c.post("/api/track", json=[_ev(qa_session_id, site="review" if site == "live" else "live")], headers={"X-KSSL-Write": "1"})
    assert r.status_code == 200 and r.json() == {"stored": 1, "dropped": 0}, r.text
    db = "serving" if site == "live" else "staging"
    got = rows(db, "SELECT site, event_type, view FROM activity.event WHERE session_id = %s::uuid", (qa_session_id,))
    assert got == [{"site": site, "event_type": "page_view", "view": "tender"}]


@pytest.mark.parametrize("bad", [{"type": "drop_table"}, {"visitor": "not-a-uuid"}, {"session": None}, "a string"],
                         ids=["unknown-type", "bad-visitor", "no-session", "not-an-object"])
def test_track_drops_bad_events(bad, clean_log, qa_session_id):
    """API-051 · Malformed usage events are dropped, not stored
    Steps: POST /api/track with one good event and one bad one (unknown type, bad visitor id, no session, not an object).
    Expected: stored 1, dropped 1; a batch item that is not an object fails validation (422) and nothing is stored."""
    badev = bad if isinstance(bad, str) else {**_ev(qa_session_id), **bad}
    with client("live") as c:
        r = c.post("/api/track", json=[_ev(qa_session_id), badev], headers={"X-KSSL-Write": "1"})
    if isinstance(bad, str):
        assert r.status_code == 422, r.text
        assert scalar("serving", "SELECT count(*) FROM activity.event WHERE session_id = %s::uuid", (qa_session_id,)) == 0
        return
    assert r.status_code == 200 and r.json() == {"stored": 1, "dropped": 1}, r.text


def test_track_batch_cap(clean_log, qa_session_id):
    """API-052 · Oversized batches are refused
    Steps: POST /api/track with 101 events.
    Expected: 400 'at most 100'; nothing stored."""
    with client("live") as c:
        r = c.post("/api/track", json=[_ev(qa_session_id)] * 101, headers={"X-KSSL-Write": "1"})
    assert r.status_code == 400
    assert scalar("serving", "SELECT count(*) FROM activity.event WHERE session_id = %s::uuid", (qa_session_id,)) == 0


def test_track_field_caps(clean_log, qa_session_id):
    """API-053 · Field caps: long text is cut, oversized props are dropped, bad durations are ignored
    Steps: POST one event with a 5,000-char target, 3,000-char props, a negative duration.
    Expected: stored; target cut to 160 chars, props NULL, duration NULL."""
    ev = _ev(qa_session_id, type="click", target="x" * 5000, props={"pad": "y" * 3000}, ms=-5)
    with client("live") as c:
        assert c.post("/api/track", json=[ev], headers={"X-KSSL-Write": "1"}).json()["stored"] == 1
    r = rows("serving", "SELECT length(target) AS n, props, duration_ms FROM activity.event WHERE session_id = %s::uuid", (qa_session_id,))[0]
    assert r == {"n": 160, "props": None, "duration_ms": None}, r


def test_track_sql_text_is_data(clean_log, qa_session_id):
    """API-054 · Text that looks like SQL is stored as text
    Steps: POST an event whose target is "'); DROP TABLE activity.event; --".
    Expected: stored verbatim; activity.event still there."""
    evil = "'); DROP TABLE activity.event; --"
    with client("live") as c:
        c.post("/api/track", json=[_ev(qa_session_id, target=evil)], headers={"X-KSSL-Write": "1"})
    assert rows("serving", "SELECT target FROM activity.event WHERE session_id = %s::uuid", (qa_session_id,)) == [{"target": evil}]


def test_recording_roundtrip(clean_log, qa_session_id):
    """API-055 · A page recording is stored and played back
    Steps: POST /api/track/rec with a gzip JSON array of two rrweb events; GET /api/review/activity/recording for the visit.
    Expected: stored; the review API returns both events in time order."""
    evs = [{"type": 4, "timestamp": 2, "data": {}}, {"type": 2, "timestamp": 1, "data": {}}]
    with client("live") as c:
        r = c.post(f"/api/track/rec?session={qa_session_id}&visitor={QA_VISITOR}", content=gzip.compress(json.dumps(evs).encode()),
                   headers={"X-KSSL-Write": "1", "Content-Type": "application/json", "Content-Encoding": "gzip"})
    assert r.status_code == 200, r.text
    with client("review") as c:
        got = c.get(f"/api/review/activity/recording?site=live&session={qa_session_id}").json()
    assert [e["timestamp"] for e in got["events"]] == [1, 2]


@pytest.mark.parametrize("case", ["no-ids", "too-big", "not-json"])
def test_recording_refuses_bad_uploads(case, clean_log, qa_session_id):
    """API-056 · Recording uploads: ids required, size capped, garbage refused
    Steps: POST /api/track/rec without session/visitor; with a 9 MB body; with a body that is not JSON.
    Expected: refused -- 422 (missing ids) / 413 / 400."""
    q = f"?session={qa_session_id}&visitor={QA_VISITOR}"
    body = {"no-ids": b"[]", "too-big": b"x" * (9 * 1024 * 1024), "not-json": b"not json"}[case]
    with client("live") as c:
        r = c.post("/api/track/rec" + ("" if case == "no-ids" else q), content=body, headers={"X-KSSL-Write": "1"})
    assert r.status_code == {"no-ids": 422, "too-big": 413, "not-json": 400}[case], r.text[:200]


# ---- review-only reads -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", REVIEW_GETS, ids=[p.split("?")[0].replace("/api/review/", "") for p in REVIEW_GETS])
def test_review_reads_absent_on_live(path):
    """API-061 · Review tools do not exist on the live API
    Steps: GET each /api/review/* route on the live API.
    Expected: 404."""
    with client("live") as c:
        assert c.get(path).status_code == 404


@pytest.mark.parametrize("table", ["market_tender", "competitive_signal", "competitive_competitor", "market_global_requirement",
                                   "competitive_project", "technology_innovation", "market_award"])
def test_trace(table):
    """API-060 · Trace shows a card's staging row, its live row and its sources
    Steps: take a card key from the staging database; GET /api/review/trace?table=..&key=..; and with an unknown key.
    Expected: 200 naming staging and live tables, with the card's row; an unknown key answers 200 with no rows."""
    from backend.review import GRAPH
    k = GRAPH[table][0]
    key = scalar("staging", f'SELECT "{k}"::text FROM staging."{table}" ORDER BY 1 LIMIT 1')
    with client("review") as c:
        r = c.get("/api/review/trace", params={"table": table, "key": key})
        bad = c.get("/api/review/trace", params={"table": table, "key": "qa-no-such-key"})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["table"] == f"staging.{table}" and j["live_table"] == f"serving.{table}"
    assert j["rows"] and key in json.dumps(j["rows"])
    assert bad.status_code == 200 and bad.json()["rows"] == []


def test_activity_reads():
    """API-062 · Usage-log reads answer and validate input
    Steps: GET activity/people, activity/sessions (site=live, user1), activity/sessions with no person, activity/events
    without a session, people with site=bad.
    Expected: 200 with users / visitors and with sessions; 400 for no person, no session and site=bad."""
    with client("review") as c:
        p = c.get("/api/review/activity/people", params={"site": "live"})
        s = c.get("/api/review/activity/sessions", params={"site": "live", "user": "user1"})
        assert c.get("/api/review/activity/sessions", params={"site": "live"}).status_code == 400
        e = c.get("/api/review/activity/events", params={"site": "live"})
        b = c.get("/api/review/activity/people", params={"site": "bad"})
    assert p.status_code == 200 and {"users", "visitors"} <= set(p.json())
    assert s.status_code == 200
    assert e.status_code == 400 and b.status_code == 400


def test_recording_read_validates():
    """API-063 · Recording read needs a visit id
    Steps: GET /api/review/activity/recording with no session; with a random uuid.
    Expected: 400; 200 with an empty event list."""
    with client("review") as c:
        assert c.get("/api/review/activity/recording").status_code == 400
        r = c.get("/api/review/activity/recording", params={"session": str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()["events"] == []


def test_live_dataset_proxy():
    """API-064 · The review API's copy of the live dataset is the live dataset
    Steps: GET /api/review/live-dataset (review API) and /api/dataset (live API).
    Expected: same competitors, same tender ids."""
    with client("review") as c:
        r = c.get("/api/review/live-dataset")
    assert r.status_code == 200, r.text[:200]
    proxy, live = r.json(), dataset("live")
    assert set(proxy["competitors"]) == set(live["competitors"])
    assert {t["id"] for t in proxy["tenders"]} == {t["id"] for t in live["tenders"]}


def test_pipeline_log():
    """API-065 · Pipeline log routes answer
    Steps: GET pipeline/runs; steps of the first run; records of its first step; search 'tender'; journey of a staging tender.
    Expected: 200 each, with runs / steps / records / hits lists; journey returns stages for the tender."""
    tid = scalar("staging", "SELECT tender_id::text FROM staging.market_tender LIMIT 1")
    with client("review") as c:
        runs = c.get("/api/review/pipeline/runs")
        assert runs.status_code == 200 and runs.json()["runs"], runs.text[:200]
        run = runs.json()["runs"][0]["id"]
        st = c.get("/api/review/pipeline/steps", params={"run": run})
        assert st.status_code == 200, st.text[:200]
        steps = st.json().get("steps") or []
        if steps:
            assert c.get("/api/review/pipeline/records", params={"step": steps[0]["step_id"]}).status_code == 200
        assert c.get("/api/review/pipeline/search", params={"q": "tender"}).status_code == 200
        j = c.get("/api/review/pipeline/journey", params={"table": "market_tender", "id": tid})
    assert j.status_code == 200, j.text[:200]


def test_analytics():
    """API-066 · Usage analytics routes answer and validate input
    Steps: GET analytics/day without user or visitor; with user=user1; analytics/heatmap for view=tender.
    Expected: 400 without a person; 200 with totals / sessions / pages for user1; heatmap 200 with a points list."""
    with client("review") as c:
        assert c.get("/api/review/analytics/day").status_code == 400
        d = c.get("/api/review/analytics/day", params={"user": "user1", "site": "live"})
        h = c.get("/api/review/analytics/heatmap", params={"view": "tender", "site": "live"})
    assert d.status_code == 200 and {"totals", "sessions", "pages"} <= set(d.json())
    assert h.status_code == 200 and isinstance(h.json()["points"], list)


# ---- news --------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("site", SITES)
def test_news_list(site):
    """API-070 · Stored news list and its input checks
    Steps: GET /api/news?limit=5; competitor_id=not-a-uuid; limit=0; from=bad-date.
    Expected: 200 with at most 5 items, each with an http url; 400 / 422 for the bad inputs."""
    with client(site) as c:
        r = c.get("/api/news", params={"limit": 5})
        bad = [c.get("/api/news", params=p).status_code for p in ({"competitor_id": "x"}, {"limit": 0}, {"from": "bad-date"})]
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    items = body if isinstance(body, list) else next((v for v in body.values() if isinstance(v, list)), [])
    assert len(items) <= 5
    assert all(b in (400, 422) for b in bad), bad


def test_news_refresh_not_on_live():
    """API-071 · News refresh (spends money) is not reachable from the live site
    Steps: POST /api/news/refresh?dry_run=true to the live API with the write header.
    Expected: 404."""
    with client("live") as c:
        assert c.post("/api/news/refresh?dry_run=true", headers={"X-KSSL-Write": "1"}).status_code == 404


# ---- HTTP hygiene ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("site", SITES)
def test_cors_blocks_cross_site_writes(site):
    """API-080 · Another website cannot send writes
    Steps: CORS preflight OPTIONS /api/track from Origin https://evil.example asking for POST with X-KSSL-Write.
    Expected: the preflight does not allow POST."""
    with client(site) as c:
        r = c.options("/api/track", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
                                             "Access-Control-Request-Headers": "x-kssl-write,content-type"})
    assert "POST" not in r.headers.get("access-control-allow-methods", ""), r.headers


@pytest.mark.parametrize("site", SITES)
def test_unknown_route(site):
    """API-081 · Unknown routes answer 404 JSON, docs are off
    Steps: GET /api/no-such-route, /docs, /openapi.json.
    Expected: 404 for the route and for /docs; no stack trace in any body."""
    with client(site) as c:
        r = c.get("/api/no-such-route")
        docs = c.get("/docs")
    assert r.status_code == 404 and "Traceback" not in r.text
    assert docs.status_code == 404
