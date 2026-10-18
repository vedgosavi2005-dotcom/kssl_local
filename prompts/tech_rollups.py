"""Technology-pillar code roll-ups (no model): category labels, technology_metric, patent classification / trend / field assessment.
Everything is computed from rows already in kssl_staging and replaces the previous roll-up rows. Registered as derive hooks
(`patent_trend`, `technology_metric`) and runnable alone:

    python -m prompts.tech_rollups            # rebuild everything (needs KSSL_STAGING_DSN)
    python -m prompts.tech_rollups --selftest # pure rules, fictional values
"""

from __future__ import annotations

import hashlib
import sys
from datetime import date

from prompts.derive import hook

CROWDING = ((30, "locked"), (10, "crowded"), (3, "emerging"), (0, "open"))      # filings on record in a field
METRIC_ORDER = ("rival", "adopt", "trend", "all", "threat", "watch", "fav", "innovations", "patents")


def _bigint(*parts) -> int:
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def crowding_for(filings: int) -> str:
    """open < 3 <= emerging < 10 <= crowded < 30 <= locked."""
    return next(word for floor, word in CROWDING if filings >= floor)


def spike(counts_by_year_month: dict, today) -> bool:
    """A.3.3 spike rule: the last 12 months hold >= 2x the average 12-month count of the 24 months before them, and at least 5 filings.
    counts_by_year_month = {(year, month): n}."""
    def n(lo, hi):
        return sum(c for (y, m), c in counts_by_year_month.items() if lo <= (today.year - y) * 12 + (today.month - m) < hi)
    last, prior = n(0, 12), n(12, 36)
    return last >= 5 and last >= 2 * (prior / 2)


def patent_rollup(cur, notes: list | None = None) -> dict:
    """competitive_patent_classification (per portfolio, both lenses), competitive_patent_trend (portfolio, category, year) and
    patent_field_assessment (per area_label: crowding by filing count, a count note) from the stored, labelled filings."""
    notes = notes if notes is not None else []
    cur.execute("SELECT f.portfolio_id, f.category_label, f.area_label, f.filed_date, c.display_name FROM staging.competitive_patent_filing f "
                "JOIN staging.competitive_patent_portfolio p USING (portfolio_id) JOIN staging.competitive_competitor c ON c.competitor_id = p.competitor_id")
    cls, trend, fields = {}, {}, {}
    for r in cur.fetchall():
        if r["category_label"]:
            cls[(r["portfolio_id"], r["category_label"])] = cls.get((r["portfolio_id"], r["category_label"]), 0) + 1
            if r["filed_date"]:
                k = (r["portfolio_id"], r["category_label"], r["filed_date"].year)
                trend[k] = trend.get(k, 0) + 1
        if r["area_label"]:
            f = fields.setdefault(r["area_label"], {"n": 0, "by": {}})
            f["n"] += 1
            f["by"][r["display_name"]] = f["by"].get(r["display_name"], 0) + 1
    cur.execute("DELETE FROM staging.competitive_patent_classification")
    for (pid, lab), n in sorted(cls.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        for lens in ("rival", "field"):
            cur.execute("INSERT INTO staging.competitive_patent_classification (classification_id, portfolio_id, category_label, filing_count, lens) "
                        "VALUES (gen_random_uuid(), %s, %s, %s, %s)", (pid, lab, n, lens))
    cur.execute("DELETE FROM staging.competitive_patent_trend")
    for (pid, lab, y), n in sorted(trend.items(), key=lambda kv: (str(kv[0][0]), kv[0][1], kv[0][2])):
        cur.execute("INSERT INTO staging.competitive_patent_trend (trend_id, portfolio_id, category_label, year, filing_count) VALUES (%s,%s,%s,%s,%s)",
                    (_bigint("patent_trend", pid, lab, y), pid, lab, y, n))
    cur.execute("DELETE FROM staging.patent_field_assessment")
    for area, f in sorted(fields.items()):
        who = ", ".join(f"{k} {v}" for k, v in sorted(f["by"].items(), key=lambda kv: (-kv[1], kv[0])))
        note = f"{f['n']} filings on record in this field ({who})."   # the client's own filings are not queried here, so nothing is said about them
        cur.execute("INSERT INTO staging.patent_field_assessment (area_label, crowding, client_position_note, source_url, source_tier) VALUES (%s,%s,%s,NULL,'computed')",
                    (area, crowding_for(f["n"]), note))
    notes.append(f"patent_rollup: {len(cls)} category counts, {len(trend)} trend rows, {len(fields)} fields")
    return {"classification": len(cls), "trend": len(trend), "fields": len(fields)}


def technology_rollup(cur, notes: list | None = None) -> dict:
    """technology_category_ui_label (both schemas), staging_ui.technology_category and technology_metric (both schemas) from stored rows."""
    notes = notes if notes is not None else []
    cur.execute("SELECT * FROM staging.technology_category ORDER BY display_order")
    cats = cur.fetchall()
    cur.execute("DELETE FROM staging.technology_category_ui_label")
    cur.execute("DELETE FROM staging_ui.technology_category_ui_label")
    cur.execute("DELETE FROM staging_ui.technology_category")
    for c in cats:
        cur.execute("""INSERT INTO staging.technology_category_ui_label (category_id, category_label_id, database_category_id, label_text, locale, short_label, sort_order, tab_number, ui_name)
                       VALUES (%s,%s,%s,%s,'en',%s,%s,%s,%s)""",
                    (c["category_id"], c["category_id"], c["category_code"], c["category_name"], c["category_name"], c["display_order"], c["tab_number"], c["category_name"]))
        cur.execute("SELECT count(*) AS n FROM staging.technology_innovation WHERE category_id = %s AND status = 'active'", (c["category_id"],))
        n = cur.fetchone()["n"]
        cur.execute("UPDATE staging.technology_category SET innovation_count = %s WHERE category_id = %s", (n, c["category_id"]))
        cur.execute("INSERT INTO staging_ui.technology_category_ui_label (database_category_id, tab_number, ui_name) VALUES (%s,%s,%s)",
                    (c["category_code"], c["tab_number"], c["category_name"]))
        cur.execute("INSERT INTO staging_ui.technology_category (category_id, category_name, category_description, display_order, innovation_count, tab_number) VALUES (%s,%s,%s,%s,%s,%s)",
                    (str(c["category_id"]), c["category_name"], c["category_description"], c["display_order"], n, c["tab_number"]))
    cur.execute("""SELECT count(*) FILTER (WHERE classification = 'competitor_advance') AS rival, count(*) FILTER (WHERE classification = 'adoptable') AS adopt,
                          count(*) FILTER (WHERE classification IN ('threat_to_position', 'industry_trend')) AS trend,
                          count(*) FILTER (WHERE direction = 'threat') AS threat, count(*) FILTER (WHERE direction = 'watch') AS watch,
                          count(*) FILTER (WHERE direction = 'fav') AS fav
                   FROM staging.technology_overview_article WHERE status = 'active'""")
    m = dict(cur.fetchone())
    cur.execute("""SELECT count(DISTINCT cid) AS n FROM (SELECT category_id AS cid FROM staging.technology_overview_article WHERE status = 'active'
                   UNION SELECT category_id FROM staging.technology_innovation WHERE status = 'active') x""")
    m["all"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM staging.technology_innovation WHERE status = 'active'")
    m["innovations"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM staging.competitive_patent_filing")
    m["patents"] = cur.fetchone()["n"]
    cur.execute("SELECT code, label FROM staging_ui.code_label WHERE table_name IN ('technology_overview_metric_card', 'technology_metric') AND column_name = 'metric_key' AND is_active")
    labels = {r["code"]: r["label"] for r in cur.fetchall()}
    cur.execute("SELECT pillar_id FROM staging.technology_pillar ORDER BY pillar_id LIMIT 1")
    pid = cur.fetchone()["pillar_id"]
    cur.execute("DELETE FROM staging.technology_metric")
    cur.execute("DELETE FROM staging_ui.technology_metric")
    for n, k in enumerate(METRIC_ORDER, 1):
        unit = "filings" if k == "patents" else "categories" if k == "all" else "innovations" if k == "innovations" else "cards"
        cur.execute("INSERT INTO staging.technology_metric (metric_id, pillar_id, metric_key, metric_label, metric_value, metric_unit, metric_action, display_order, as_of_date) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,current_date)", (_bigint("technology_metric", k), pid, k, labels.get(k, k), m[k], unit, k, n))
        cur.execute("INSERT INTO staging_ui.technology_metric (metric_id, pillar_id, metric_key, metric_label, metric_value, metric_action, display_order) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)", (_bigint("technology_metric", k), str(pid), k, labels.get(k, k), m[k], k, n))
    notes.append(f"technology_rollup: {len(cats)} categories, metrics {m}")
    return m


@hook("patent_trend")
def patent_trend_hook(cur, ctx: dict) -> None:
    patent_rollup(cur, ctx["notes"])


@hook("technology_metric")
def technology_metric_hook(cur, ctx: dict) -> None:
    technology_rollup(cur, ctx["notes"])


def selftest() -> None:
    assert crowding_for(0) == "open" and crowding_for(3) == "emerging" and crowding_for(10) == "crowded" and crowding_for(30) == "locked"
    t = date(2026, 10, 17)
    assert spike({(2026, 9): 6, (2025, 1): 1, (2024, 5): 2}, t)                 # 6 in the last 12 months vs 3 over the 24 before (1.5 a year)
    assert not spike({(2026, 9): 4}, t) and not spike({(2026, 9): 6, (2025, 3): 8, (2024, 3): 8}, t)
    assert _bigint("a", 1) == _bigint("a", 1) != _bigint("a", 2) and _bigint("a", 1) < 2 ** 63
    print("tech_rollups self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        import os
        import psycopg2
        import psycopg2.extras
        dsn = os.environ.get("KSSL_STAGING_DSN") or os.environ["KSSL_DSN"]
        conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
        with conn.cursor() as cur:
            print(patent_rollup(cur))
            print(technology_rollup(cur))
        conn.commit()
