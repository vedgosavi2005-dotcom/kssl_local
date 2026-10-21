"""Approve test for the tables and columns of db/setup/11_foundations.sql, on a THROWAWAY pair only.

  KSSL_TEST_TAG=f bash db/make_test_pair.sh        # builds kssl_test_staging_f / kssl_test_serving_f with db/test_seed_full (incl. 90_foundations.sql)
  KSSL_TEST_TAG=f python db/setup/test_foundations_approve.py

Approves one card of every kind that carries a new column or child table, then checks with backend.review.statuses that each
is "live" (staging bundle == serving bundle over EVERY column, so a column that Approve did not copy shows as "changed"),
that a later edit of a new column shows as "changed", and that the ui setup tables can be approved. Refuses any database
whose name does not start with kssl_test_.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TAG = os.getenv("KSSL_TEST_TAG", "").strip()
STG = "kssl_test_staging" + (f"_{TAG}" if TAG else "")
SRV = "kssl_test_serving" + (f"_{TAG}" if TAG else "")
assert STG.startswith("kssl_test_staging") and SRV.startswith("kssl_test_serving"), "throwaway databases only"
DSN = "host=127.0.0.1 port=55432 user=kssl password=kssl dbname={}"
os.environ["KSSL_STAGING_DSN"], os.environ["KSSL_SERVING_DSN"] = DSN.format(STG), DSN.format(SRV)

from backend import review  # noqa: E402

C1 = "c0ffee00-0000-4000-8000-000000000001"
C2 = "c0ffee00-0000-4000-8000-000000000002"
C3 = "c0ffee00-0000-4000-8000-000000000003"
CARDS = [                      # (table, key): parents first
    ("client_account", None), ("competitive_competitor", C1), ("competitive_competitor", C2), ("competitive_competitor", C3),
    ("competitive_signal", "a6000000-0000-4000-8000-000000000001"), ("competitive_signal", "a6000000-0000-4000-8000-000000000002"),
    ("story", "91001"), ("story", "91002"),
    ("competitive_geo_location", "50001"), ("competitive_geo_location", "50002"),
    ("market_tender", "60002"), ("market_global_requirement", "62001"),
    ("technology_innovation", "71001"), ("technology_overview_article", "72001"),
]
SETUP = [("ui", "code_label"), ("ui", "competitive_filter_option"), ("ui", "technology_filter_option"), ("ui", "market_tender_filter")]
NEW_CHILD_TABLES = ("story_step", "competitive_patent_trend", "competitive_geo_analysis", "market_tender_eligibility",
                    "market_global_requirement_rival", "technology_innovation_milestone")


def main() -> None:
    with review.session() as (st, sv):
        st.execute("SELECT client_id FROM staging.client_account ORDER BY 1 LIMIT 1")
        client = str(st.fetchone()["client_id"])
        extra = []                                   # one card each of the other kinds that gained columns
        for table, col in (("competitive_partnership", "relationship_id"), ("competitive_product", "product_id"),
                           ("competitive_product_news", "product_news_id"), ("client_product", "client_product_id"),
                           ("competitive_project", "project_id"), ("competitive_competitor_moment", "moment_id")):
            st.execute(f"SELECT {col} AS k FROM staging.{table} ORDER BY 1 LIMIT 1")
            r = st.fetchone()
            if r:
                extra.append((table, str(r["k"])))
        order = [(t, client if t == "client_account" else k) for t, k in CARDS] + extra
        done = set()
        for _ in range(3):                           # parents may come later in `extra`: retry the ones that said "approve its ... first"
            for t, k in order:
                if (t, k) in done:
                    continue
                try:
                    st.execute("SAVEPOINT a")
                    sv.execute("SAVEPOINT a")
                    review.approve(st, sv, t, k)
                    done.add((t, k))
                except ValueError as e:
                    st.execute("ROLLBACK TO SAVEPOINT a")
                    sv.execute("ROLLBACK TO SAVEPOINT a")
                    if "first" not in str(e):
                        raise
        assert len(done) == len(order), f"not approved: {[o for o in order if o not in done]}"
        for schema, name in SETUP:
            review.approve_table(st, sv, schema, name)
        stat = review.statuses(st, sv)
        for t, k in order:
            s = stat["cards"][t][k]["s"]
            assert s == "live", f"{t} {k}: {s} (Approve did not copy every column)"
        for schema, name in SETUP:
            assert stat["tables"][schema][name]["s"] == "live", (schema, name, stat["tables"][schema][name])
        # new children arrived with their cards
        for t in NEW_CHILD_TABLES:
            st.execute(f"SELECT count(*) AS n FROM staging.{t}")
            sv.execute(f"SELECT count(*) AS n FROM serving.{t}")
            a, b = st.fetchone()["n"], sv.fetchone()["n"]
            assert a > 0 and a == b, f"{t}: staging {a} rows, serving {b}"
        # a new column is part of the card's signature: change one in staging -> "changed"
        st.execute("UPDATE staging.competitive_signal SET probability = 4 WHERE signal_id = 'a6000000-0000-4000-8000-000000000001'")
        st.execute("UPDATE staging.market_tender_eligibility SET state = 'met' WHERE eligibility_id = 94001")
        st.execute("UPDATE staging.story_step SET changed = 'edited' WHERE step_id = 91101")
        stat = review.statuses(st, sv)
        assert stat["cards"]["competitive_signal"]["a6000000-0000-4000-8000-000000000001"]["s"] == "changed"
        assert stat["cards"]["market_tender"]["60002"]["s"] == "changed"
        assert stat["cards"]["story"]["91001"]["s"] == "changed"
        # unpublish a story takes its steps with it
        review.unpublish(st, sv, "story", "91002")
        sv.execute("SELECT count(*) AS n FROM serving.story_step WHERE story_id = 91002")
        assert sv.fetchone()["n"] == 0
        st.connection.rollback()                      # staging edits above are not kept
        print(f"approve test ok on {SRV}: {len(done)} cards, {len(SETUP)} setup tables; new columns and child tables copied")


if __name__ == "__main__":
    main()
