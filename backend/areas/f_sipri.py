"""SIPRI figures for the pages, from the two setup tables (db/setup/48_sipri_ui_tables.sql, built by backend/sipri_ui.py).

    sipriArms   competitor id -> the SIPRI Top-100 entity shown for it (the company, its parent group or its predecessor, named),
                its latest year (arms revenue, rank, arms share of total revenue) and the year-by-year trend, with the source
    sipriMilex  country name (as the geo page names it) -> military expenditure of the latest year with data and the trend, with
                the source
Only stored rows; nothing is estimated here.
"""

from collections import defaultdict

from backend.common import table, text

TREND = 6


def _num(v):
    return None if v is None else float(v)


def build_arms(database, competitors):
    rows = defaultdict(list)
    for r in table(database, "serving", "sipri_arms_company"):
        cid = text(r.get("competitor_id"))
        if cid in competitors and r.get("year") is not None:
            rows[cid].append(r)
    out = {}
    for cid, rs in rows.items():
        rs.sort(key=lambda r: r["year"])
        last = rs[-1]
        out[cid] = {
            "entity": last.get("sipri_company"),
            "relation": last.get("relation"),
            "year": last["year"],
            "rank": last.get("rank"),
            "armsUsdM": _num(last.get("arms_revenue_usd_m")),
            "totalUsdM": _num(last.get("total_revenue_usd_m")),
            "share": _num(last.get("arms_share")),
            "trend": [{"year": r["year"], "armsUsdM": _num(r.get("arms_revenue_usd_m")), "rank": r.get("rank"),
                       "entity": r.get("sipri_company")} for r in rs[-TREND:]],
            "source": {"label": last.get("source_label"), "url": last.get("source_url")},
            "_src": {"t": "sipri_arms_company", "k": "competitor_id", "id": cid},
        }
    return out


def build_milex(database):
    rows = defaultdict(list)
    for r in table(database, "serving", "sipri_milex_country"):
        if r.get("country_name") and r.get("year") is not None:
            rows[r["country_name"]].append(r)
    out = {}
    for name, rs in rows.items():
        rs = sorted((r for r in rs if r.get("current_usd_m") is not None or r.get("constant_2024_usd_m") is not None), key=lambda r: r["year"])
        if not rs:
            continue
        last = rs[-1]
        out[name] = {
            "sipriCountry": last.get("sipri_country"),
            "year": last["year"],
            "currentUsdM": _num(last.get("current_usd_m")),
            "constantUsdM": _num(last.get("constant_2024_usd_m")),
            "shareGdp": _num(last.get("share_gdp")),
            "perCapitaUsd": _num(last.get("per_capita_usd")),
            "trend": [{"year": r["year"], "constantUsdM": _num(r.get("constant_2024_usd_m")), "currentUsdM": _num(r.get("current_usd_m"))}
                      for r in rs[-TREND:]],
            "source": {"label": last.get("source_label"), "url": last.get("source_url")},
            "_src": {"t": "sipri_milex_country", "k": "country_name", "id": name},
        }
    return out


def build(database, d):
    d["sipriArms"] = build_arms(database, d.get("competitors") or {})
    d["sipriMilex"] = build_milex(database)
