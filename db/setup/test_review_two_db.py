"""End-to-end test of the review copy with the two-database layout, on THROWAWAY databases only.

  python db/setup/test_review_two_db.py [--keep]

Builds kssl_v2_test_rs (staging layout: staging + staging_ui) and kssl_v2_test_rv (serving layout:
serving + ui + guard triggers) with db/make_databases.sh, loads fictional rows into the staging one,
starts a live backend (:8631, serving DSN = rv) and a review backend (:8632, staging DSN = rs,
serving DSN = rv), runs the checks below with asserts, then stops the servers and drops both
databases (--keep leaves the databases). Never touches kssl_staging / kssl_serving / kssl_frontend.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
RS, RV = "kssl_v2_test_rs", "kssl_v2_test_rv"
assert RS.startswith("kssl_v2_test_") and RV.startswith("kssl_v2_test_")
DSN = "host=127.0.0.1 port=55432 user=kssl password=kssl dbname={}"
LIVE, REVIEW = "http://127.0.0.1:8631", "http://127.0.0.1:8632"
EDS = "11111111-1111-1111-1111-111111111111"
PROD = "c1000000-0000-0000-0000-000000000001"
SIG = "d1000000-0000-0000-0000-000000000001"
# Git Bash, not the WSL bash that may come first on a Windows PATH
BASH = next((b for b in ("C:/Program Files/Git/bin/bash.exe", "/usr/bin/bash") if os.path.exists(b)), "bash")


def sh(*args):
    subprocess.run(args, cwd=ROOT, check=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})


def drop_dbs():
    for db in (RS, RV):
        assert db.startswith("kssl_v2_test_")
        sh("docker", "exec", "kssl-pg", "psql", "-U", "kssl", "-d", "postgres", "-q", "-c",
           f"DROP DATABASE IF EXISTS {db} WITH (FORCE)")


def q(db, query, args=None, fetch=False):
    with psycopg2.connect(DSN.format(db)) as c, c.cursor() as cur:
        cur.execute(query, args)
        return cur.fetchall() if fetch else None


def stg(query, args=None, fetch=False):
    return q(RS, query, args, fetch)


def live(query, args=None):
    return q(RV, query, args, True)


def http(method, url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def act(table, key, action):
    return http("POST", REVIEW + "/api/review", {"table": table, "key": key, "action": action})


def act_table(schema, table, action):
    return http("POST", REVIEW + "/api/review/table", {"schema": schema, "table": table, "action": action})


def st_of(table, key):
    code, body = http("GET", REVIEW + "/api/dataset")
    assert code == 200, body
    return body["review"]["cards"].get(table, {}).get(key)


def tbl_of(schema, table):
    return http("GET", REVIEW + "/api/dataset")[1]["review"]["tables"][schema][table]["s"]


def count(table, where="true"):
    return live(f"SELECT count(*) FROM serving.{table} WHERE {where}")[0][0]


SEED = f"""
INSERT INTO staging.competitive_product (product_id, competitor_id, product_name, category, category_filter, is_collapsed)
VALUES ('{PROD}', '{EDS}', 'EX-155 howitzer', 'artillery', 'artillery', false);
INSERT INTO staging.competitive_product_specification (spec_id, product_id, spec_label, spec_value, unit) VALUES
  ('c2000000-0000-0000-0000-000000000001', '{PROD}', 'Calibre', '155', 'mm'),
  ('c2000000-0000-0000-0000-000000000002', '{PROD}', 'Range', '40', 'km'),
  ('c2000000-0000-0000-0000-000000000003', '{PROD}', 'Crew', '5', NULL);
INSERT INTO staging.competitive_competitor_location (location_id, competitor_id, location_name, location_type, country) VALUES
  ('a1000000-0000-0000-0000-000000000001', '{EDS}', 'Rivertown plant', 'plant', 'Exampleland'),
  ('a1000000-0000-0000-0000-000000000002', '{EDS}', 'Pune office', 'office', 'India');
INSERT INTO staging.competitive_signal (signal_id, company_id, title, classification, sequence_no, summary, event_date)
VALUES ('{SIG}', '{EDS}', 'Example Defence opens a plant', 'watch', 1, 'A fictional plant.', '2026-09-01');
INSERT INTO staging.competitive_signal_detail (signal_id, drawer_title, what_article_says, why_it_matters)
VALUES ('{SIG}', 'Plant opening', 'The article says so.', 'It matters.');
INSERT INTO staging.competitive_signal_evidence (evidence_id, signal_id, evidence_group, display_order, label, quote) VALUES
  ('d2000000-0000-0000-0000-000000000001', '{SIG}', 'article', 1, 'Press release', 'We opened a plant.');
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote) VALUES
  ('competitive_competitor', '{EDS}', 'headquarters', 'https://example.test/eds/about', 'primary', 'Based in Rivertown.'),
  ('competitive_signal', '{SIG}', 'title', 'https://example.test/eds/news', 'independent', 'plant opens');
INSERT INTO staging_ui.competitive_metric (metric_id, display_order, metric_label, metric_value)
VALUES ('e1000000-0000-0000-0000-000000000001', 1, 'Competitors tracked', 3);
INSERT INTO staging_ui.technology_overview_filter (filter_state_id, view_state_id, filter_type, is_active, option_values)
VALUES (1, 1, 'sequence', true, '["newest", "oldest"]'::jsonb);
"""


def wait(url, name, proc):
    for _ in range(80):
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except Exception:  # noqa: BLE001
            assert proc.poll() is None, f"{name} backend exited early (see its log)"
            time.sleep(0.5)
    raise AssertionError(f"{name} backend did not start")


def main(keep=False):
    drop_dbs()
    sh(BASH, "db/make_databases.sh", RS, RV)
    stg((ROOT / "db/test_seed_v2/a_base.sql").read_text(encoding="utf-8"))
    stg(SEED)
    base = {**os.environ, "PYTHONPATH": str(ROOT)}
    tmp = tempfile.mkdtemp(prefix="kssl_review_test_")
    procs = []
    try:
        for port, env in ((8631, {"KSSL_SERVING_DSN": DSN.format(RV)}),
                          (8632, {"KSSL_VIEW": "review", "KSSL_STAGING_DSN": DSN.format(RS), "KSSL_SERVING_DSN": DSN.format(RV)})):
            log = open(os.path.join(tmp, f"{port}.log"), "w")
            procs.append(subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT, env={k: v for k, v in base.items() if not k.startswith("KSSL_")} | env, stdout=log, stderr=log))
        wait(LIVE + "/api/health", "live", procs[0])
        wait(REVIEW + "/api/health", "review", procs[1])
        run_checks()
        print("two-database review test ok")
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait(timeout=15)
        if not keep:
            drop_dbs()
        print("logs:", tmp)


def run_checks():
    # 0. routes: 404 on the live backend; live dataset is empty
    assert http("POST", LIVE + "/api/review", {"table": "competitive_competitor", "key": EDS, "action": "approve"})[0] == 404
    assert http("GET", LIVE + "/api/review/trace", {"table": "competitive_competitor", "key": EDS})[0] == 404
    code, body = http("GET", LIVE + "/api/dataset")
    assert code == 200 and "review" not in body, body
    assert body["database"]["serving"]["competitive_competitor"] == []

    # 1. statuses are all new; the review backend reads the staging DB
    code, body = http("GET", REVIEW + "/api/dataset")
    assert code == 200 and len(body["database"]["serving"]["competitive_competitor"]) == 3
    cards = body["review"]["cards"]
    assert {v["s"] for v in cards[("competitive_competitor")].values()} == {"new"} and len(cards["competitive_competitor"]) == 3
    assert cards["competitive_product"][PROD] == {"s": "new", "live": False}
    assert cards["competitive_signal"][SIG]["s"] == "new" and cards["client_account"]["1"]["s"] == "new"
    assert body["review"]["tables"]["ui"]["competitive_metric"] == {"s": "new", "n": 1, "live_n": 0}
    assert body["review"]["tables"]["serving"]["technology_category"]["s"] == "new"
    assert body["review"]["tables"]["ui"]["competitive_navigation"]["n"] == 0

    # 2. child before parent -> 400 "first"
    code, body = act("competitive_product", PROD, "approve")
    assert code == 400 and "first" in body["detail"] and "competitor" in body["detail"], body
    code, body = act("competitive_signal", SIG, "approve")
    assert code == 400 and "first" in body["detail"], body
    assert act("competitive_competitor", EDS, "bogus")[0] == 400
    assert act("competitive_competitor_location", "x", "approve")[0] == 400  # not a reviewed table
    assert count("competitive_competitor") == 0

    # 3. competitor, then product (with specs), then signal -> the live dataset shows them
    code, body = act("competitive_competitor", EDS, "approve")
    assert code == 200 and body["review"]["cards"]["competitive_competitor"][EDS] == {"s": "live", "live": True}, body
    assert act("competitive_product", PROD, "approve")[0] == 200
    assert act("competitive_signal", SIG, "approve")[0] == 200
    code, body = http("GET", LIVE + "/api/dataset")
    assert code == 200, body
    serving = body["database"]["serving"]
    assert [r["competitor_id"] for r in serving["competitive_competitor"]] == [EDS]
    assert [r["product_name"] for r in serving["competitive_product"]] == ["EX-155 howitzer"]
    assert len(serving["competitive_product_specification"]) == 3
    assert len(serving["competitive_signal_detail"]) == 1 and len(serving["competitive_signal_evidence"]) == 1
    assert count("competitive_competitor_location") == 2  # the competitor's bundle (its locations) came along
    # fact_source rows followed their cards
    assert live("SELECT count(*) FROM serving.fact_source")[0][0] == 2
    # the other competitors stay unpublished; statuses are live
    assert st_of("competitive_competitor", "22222222-2222-2222-2222-222222222222")["s"] == "new"
    assert st_of("competitive_product", PROD)["s"] == "live" and st_of("competitive_signal", SIG)["s"] == "live"

    # 4. edit staging -> changed; trace shows the live diff; a child edit changes the parent card
    stg("UPDATE staging.competitive_competitor SET headquarters = 'Newtown' WHERE competitor_id = %s", (EDS,))
    assert st_of("competitive_competitor", EDS) == {"s": "changed", "live": True}
    code, tr = http("GET", REVIEW + "/api/review/trace", {"table": "competitive_competitor", "key": EDS})
    assert code == 200 and tr["table"] == "staging.competitive_competitor" and tr["live_table"] == "serving.competitive_competitor"
    row = tr["rows"][0]
    assert row["row"]["headquarters"] == "Newtown" and row["live"] == {"headquarters": "Rivertown, Exampleland"}, row["live"]
    assert [s["quote"] for s in row["sources"]] == ["Based in Rivertown."]
    assert "SELECT * FROM staging.competitive_competitor" in tr["sql"]
    assert {c["table"] for c in tr["children"]} == {"staging.competitive_competitor_location"}
    code, tr = http("GET", REVIEW + "/api/review/trace", {"table": "competitive_product", "key": PROD})
    assert tr["parents"] == [{"table": "staging.competitive_competitor", "key_column": "competitor_id", "key": EDS}]
    assert {c["table"] for c in tr["children"]} == {"staging.competitive_product_specification"}
    # live DB still has the old value until Approve
    assert live("SELECT headquarters FROM serving.competitive_competitor WHERE competitor_id = %s", (EDS,))[0][0] == "Rivertown, Exampleland"

    # 5. reject / undo / approve the change
    assert act("competitive_competitor", EDS, "reject")[1]["review"]["cards"]["competitive_competitor"][EDS] == {"s": "rejected", "live": True}
    stg("UPDATE staging.competitive_competitor SET headquarters = 'Newtown 2' WHERE competitor_id = %s", (EDS,))
    assert st_of("competitive_competitor", EDS)["s"] == "changed"  # a different version is pending again
    stg("UPDATE staging.competitive_competitor SET headquarters = 'Newtown' WHERE competitor_id = %s", (EDS,))
    assert st_of("competitive_competitor", EDS)["s"] == "rejected"  # the rejected version is back
    assert act("competitive_competitor", EDS, "undo")[1]["review"]["cards"]["competitive_competitor"][EDS]["s"] == "changed"
    assert act("competitive_competitor", EDS, "approve")[1]["review"]["cards"]["competitive_competitor"][EDS]["s"] == "live"
    assert live("SELECT headquarters FROM serving.competitive_competitor WHERE competitor_id = %s", (EDS,))[0][0] == "Newtown"
    assert count("competitive_competitor") == 1  # replaced, not duplicated

    # 6. remove a child row in staging -> the trace lists it, approve removes it live
    stg("DELETE FROM staging.competitive_product_specification WHERE spec_id = 'c2000000-0000-0000-0000-000000000003'")
    assert st_of("competitive_product", PROD)["s"] == "changed"
    code, tr = http("GET", REVIEW + "/api/review/trace", {"table": "competitive_product", "key": PROD})
    spec = next(c for c in tr["children"] if c["table"] == "staging.competitive_product_specification")
    assert len(spec["rows"]) == 2 and [r["spec_label"] for r in spec["removed"]] == ["Crew"], spec["removed"]
    assert count("competitive_product_specification") == 3
    assert act("competitive_product", PROD, "approve")[0] == 200
    assert count("competitive_product_specification") == 2 and st_of("competitive_product", PROD)["s"] == "live"

    # 7. table-level approve of ui tables (one with a jsonb column)
    assert tbl_of("ui", "competitive_metric") == "new" and tbl_of("ui", "technology_overview_filter") == "new"
    assert live("SELECT count(*) FROM ui.competitive_metric")[0][0] == 0
    code, body = act_table("ui", "competitive_metric", "approve")
    assert code == 200 and body["review"]["tables"]["ui"]["competitive_metric"] == {"s": "live", "n": 1, "live_n": 1}, body
    assert act_table("ui", "technology_overview_filter", "approve")[0] == 200
    assert live("SELECT option_values FROM ui.technology_overview_filter")[0][0] == ["newest", "oldest"]
    assert http("GET", LIVE + "/api/dataset")[1]["database"]["ui"]["competitive_metric"][0]["metric_label"] == "Competitors tracked"
    stg("UPDATE staging_ui.competitive_metric SET metric_value = 4")
    assert tbl_of("ui", "competitive_metric") == "changed"
    assert act_table("ui", "competitive_metric", "approve")[0] == 200
    assert live("SELECT metric_value FROM ui.competitive_metric")[0][0] == 4
    assert act_table("serving", "technology_category", "approve")[0] == 200 and count("technology_category") == 3
    assert act_table("serving", "competitive_competitor", "approve")[0] == 400  # not a setup table
    assert act_table("ui", "competitive_metric", "unpublish")[0] == 200
    assert live("SELECT count(*) FROM ui.competitive_metric")[0][0] == 0 and tbl_of("ui", "competitive_metric") == "new"

    # 8. unpublish the competitor: its products and signals go with it
    code, body = act("competitive_competitor", EDS, "unpublish")
    assert code == 200
    cards = body["review"]["cards"]
    assert cards["competitive_competitor"][EDS] == {"s": "new", "live": False}
    assert cards["competitive_product"][PROD] == {"s": "new", "live": False}
    assert cards["competitive_signal"][SIG] == {"s": "new", "live": False}
    for t in ("competitive_competitor", "competitive_product", "competitive_product_specification",
              "competitive_signal", "competitive_signal_detail", "competitive_signal_evidence", "competitive_competitor_location",
              "fact_source"):
        assert count(t) == 0, t
    assert count("technology_category") == 3  # unrelated live data untouched

    # 9. the guard: direct writes to the serving DB are refused, Approve's SET LOCAL is not
    for stmt in ("INSERT INTO serving.competitive_signal_evidence (evidence_id, signal_id, evidence_group, display_order, label) "
                 "VALUES (gen_random_uuid(), gen_random_uuid(), 'x', 1, 'x')",
                 "UPDATE serving.technology_category SET category_name = 'x'",
                 "DELETE FROM serving.technology_category",
                 "INSERT INTO ui.competitive_metric (metric_id, display_order, metric_label) VALUES (gen_random_uuid(), 1, 'x')"):
        try:
            q(RV, stmt)
        except psycopg2.Error as e:
            assert "Approve only" in str(e), e
        else:
            raise AssertionError(f"direct write was not refused: {stmt}")
    assert count("technology_category") == 3


if __name__ == "__main__":
    main("--keep" in sys.argv)
