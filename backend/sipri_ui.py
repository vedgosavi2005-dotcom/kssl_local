"""The two SIPRI setup tables the pages read (db/setup/48_sipri_ui_tables.sql), built from the raw copy (backend/sipri_import.py). No model.

    python -m backend.sipri_ui --selftest       pure checks (entity choice, country names), fictional values
    python -m backend.sipri_ui [--dry-run]      rebuild staging.sipri_arms_company and staging.sipri_milex_country (local staging)

sipri_arms_company   Company profile: a competitor's SIPRI Top-100 figures. MAP names, per competitor, the Top-100 entity that is the
                     company ('own', with its former names: Raytheon Technologies -> RTX, Finmeccanica -> Leonardo, DCNS -> Naval Group),
                     its parent group ('parent': Hanwha Group, KNDS, ThyssenKrupp, Oshkosh Corp., Diehl) or its predecessor
                     ('predecessor': Indian Ordnance Factories, corporatised in 2021 into MIL and AWEIL among others). The entity with
                     the latest year wins (an own figure on a tie); its latest year and up to five earlier ones are kept; an entity
                     last listed before 2019 is not shown. The page names the entity, so a parent's figure never reads as the
                     subsidiary's own.
sipri_milex_country  Geo footprint country panel: a country's military expenditure from 2015, under every name the geo page uses
                     for that country (competitive_geo_location) and the country reference names.
Both tables belong to this step: a run replaces them whole (they are setup tables; one Approve copies each to serving).
"""

from __future__ import annotations

import argparse
import re
import sys

ARMS_URL = "https://www.sipri.org/databases/armsindustry"
ARMS_LABEL = "SIPRI Arms Industry Database"
MILEX_URL = "https://www.sipri.org/databases/milex"
MILEX_LABEL = "SIPRI Military Expenditure Database"
TREND_YEARS = 6                     # the latest year and up to five earlier ones
STALE_BEFORE = 2019                 # an entity last listed before this is not shown
MILEX_FROM = 2015

# competitor display name -> [(relation, SIPRI Top-100 names of ONE entity)]
MAP = {
    "Lockheed Martin": [("own", ("Lockheed Martin Corp.",))],
    "RTX (Raytheon)": [("own", ("RTX", "Raytheon Technologies"))],
    "Northrop Grumman": [("own", ("Northrop Grumman Corp.",))],
    "BAE Systems": [("own", ("BAE Systems",))],
    "General Dynamics": [("own", ("General Dynamics Corp.",))],
    "L3Harris": [("own", ("L3Harris Technologies",))],
    "Leonardo": [("own", ("Leonardo", "Finmeccanica"))],
    "Huntington Ingalls Industries": [("own", ("HII", "Huntington Ingalls Industries"))],
    "NORINCO": [("own", ("NORINCO",))],
    "Rheinmetall": [("own", ("Rheinmetall",))],
    "Elbit Systems": [("own", ("Elbit Systems",))],
    "SAAB": [("own", ("Saab",))],
    "MBDA": [("own", ("MBDA",))],
    "Israel Aerospace Industries (IAI)": [("own", ("Israel Aerospace Industries",))],
    "Rafael Advanced Defense Systems": [("own", ("Rafael",))],
    "Naval Group": [("own", ("Naval Group", "DCNS"))],
    "Babcock": [("own", ("Babcock International Group",))],
    "KONGSBERG": [("own", ("Kongsberg Gruppen",))],
    "Patria": [("own", ("Patria Group",))],
    "Diehl Defence": [("parent", ("Diehl",))],
    "Oshkosh Defense": [("parent", ("Oshkosh Corp.", "Oshkosh Truck Corp."))],
    "Hanwha Aerospace": [("own", ("Hanwha Aerospace",)), ("parent", ("Hanwha Group",))],
    "KNDS Germany": [("own", ("Krauss-Maffei Wegmann",)), ("parent", ("KNDS",))],
    "Nexter (KNDS France)": [("own", ("Nexter",)), ("parent", ("KNDS",))],
    "Thyssenkrupp Marine Systems": [("parent", ("ThyssenKrupp",))],
    "Munitions India Ltd (MIL)": [("predecessor", ("Indian Ordnance Factories",))],
    "AWEIL": [("predecessor", ("Indian Ordnance Factories",))],
}
# SIPRI milex names that the country reference does not know
MILEX_ALIAS = {"united states of america": "United States", "korea, south": "South Korea", "korea, north": "North Korea",
               "congo, dr": "Congo (Democratic Republic)", "congo, republic": "Congo", "viet nam": "Vietnam", "turkiye": "Turkey", "türkiye": "Turkey",
               "czech republic": "Czechia", "cote divoire": "Ivory Coast", "côte divoire": "Ivory Coast", "uae": "United Arab Emirates",
               "bosnia-herzegovina": "Bosnia and Herzegovina", "trinidad & tobago": "Trinidad and Tobago"}


def squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def pick_entity(options: list, rows_by_name: dict) -> tuple[str, list] | None:
    """(relation, rows newest first, at most TREND_YEARS) of the entity with the latest year (own wins a tie); None when none is
    listed since STALE_BEFORE. rows_by_name: SIPRI name -> [{year, ...}]"""
    best = None
    for relation, names in options:
        rows = sorted((r for n in names for r in rows_by_name.get(n, [])), key=lambda r: -r["year"])
        seen, uniq = set(), []
        for r in rows:                                 # one row per year (a renamed company is listed once a year)
            if r["year"] not in seen:
                seen.add(r["year"])
                uniq.append(r)
        if not uniq or uniq[0]["year"] < STALE_BEFORE:
            continue
        uniq = [r for r in uniq if r["year"] > uniq[0]["year"] - TREND_YEARS]     # the trend spans at most TREND_YEARS calendar years
        key = (uniq[0]["year"], relation == "own")
        if best is None or key > best[0]:
            best = (key, relation, uniq[:TREND_YEARS])
    return (best[1], best[2]) if best else None


def build_arms(cur) -> list[dict]:
    names = sorted({n for opts in MAP.values() for _, ns in opts for n in ns})
    cur.execute("""SELECT company, year, rank, arms_revenue_usd_m, total_revenue_usd_m, arms_share, country FROM staging.sipri_top100
                   WHERE company = ANY(%s)""", (names,))
    by_name: dict = {}
    for r in cur.fetchall():
        by_name.setdefault(r["company"], []).append(dict(r))
    cur.execute("SELECT competitor_id::text AS cid, display_name FROM staging.competitive_competitor")
    out = []
    for c in cur.fetchall():
        opts = MAP.get(c["display_name"])
        got = pick_entity(opts, by_name) if opts else None
        if not got:
            continue
        relation, rows = got
        for r in rows:
            out.append({"competitor_id": c["cid"], "year": r["year"], "sipri_company": r["company"], "relation": relation, "rank": r["rank"],
                        "arms_revenue_usd_m": r["arms_revenue_usd_m"], "total_revenue_usd_m": r["total_revenue_usd_m"],
                        "arms_share": r["arms_share"], "sipri_country": r["country"], "source_label": ARMS_LABEL, "source_url": ARMS_URL})
    return out


def canon_factory(cur):
    cur.execute("SELECT country_name, iso2, aliases FROM staging.country_reference")
    canon = {}
    for r in cur.fetchall():
        for a in (r["country_name"], r["iso2"], *(r["aliases"] or [])):
            if a:
                canon[squash(a)] = r["country_name"]
    for k, v in MILEX_ALIAS.items():
        canon.setdefault(squash(k), v)
    return lambda name: canon.get(squash(name), (name or "").strip())


def build_milex(cur) -> list[dict]:
    canon = canon_factory(cur)
    cur.execute("""SELECT country, year, current_usd_m, constant_2024_usd_m, share_gdp, per_capita_usd FROM staging.sipri_milex
                   WHERE year >= %s AND (current_usd_m IS NOT NULL OR constant_2024_usd_m IS NOT NULL OR share_gdp IS NOT NULL)""", (MILEX_FROM,))
    by_country: dict = {}
    for r in cur.fetchall():
        by_country.setdefault(squash(canon(r["country"])), []).append(dict(r))
    cur.execute("""SELECT country_name FROM staging.competitive_geo_location WHERE country_name IS NOT NULL
                   UNION SELECT country_name FROM staging.country_reference""")
    out = []
    for name in sorted({r["country_name"].strip() for r in cur.fetchall() if r["country_name"].strip()}):
        for r in by_country.get(squash(canon(name)), []):
            out.append({"country_name": name, "year": r["year"], "sipri_country": r["country"], "current_usd_m": r["current_usd_m"],
                        "constant_2024_usd_m": r["constant_2024_usd_m"], "share_gdp": r["share_gdp"], "per_capita_usd": r["per_capita_usd"],
                        "source_label": MILEX_LABEL, "source_url": MILEX_URL})
    return out


def write(cur, table: str, rows: list[dict]) -> int:
    from psycopg2.extras import execute_values
    cur.execute(f"DELETE FROM staging.{table}")                 # this step's own setup table, rebuilt whole
    if rows:
        cols = list(rows[0])
        execute_values(cur, f"INSERT INTO staging.{table} ({', '.join(cols)}) VALUES %s", [tuple(r[c] for c in cols) for r in rows])
    return len(rows)


def _selftest() -> None:
    rows = {"Hanwha Aerospace": [{"year": y} for y in (2018, 2019, 2020, 2021, 2022)], "Hanwha Group": [{"year": 2023}, {"year": 2024}],
            "RTX": [{"year": 2023}, {"year": 2024}], "Raytheon Technologies": [{"year": y} for y in (2020, 2021, 2022)],
            "Patria Group": [{"year": 2014}], "Nexter": [{"year": 2020}], "KNDS": [{"year": 2024}]}
    rel, got = pick_entity(MAP["Hanwha Aerospace"], rows)
    assert rel == "parent" and [r["year"] for r in got] == [2024, 2023], got              # the parent is newer: shown as the parent
    rel, got = pick_entity(MAP["RTX (Raytheon)"], rows)
    assert rel == "own" and [r["year"] for r in got] == [2024, 2023, 2022, 2021, 2020]   # a renamed company is one entity
    assert pick_entity(MAP["Patria"], rows) is None                                       # last listed 2014: stale
    assert pick_entity(MAP["Nexter (KNDS France)"], rows)[0] == "parent"
    rel, got = pick_entity([("own", ("A",)), ("parent", ("B",))], {"A": [{"year": 2024}], "B": [{"year": 2024}]})
    assert rel == "own"                                                                   # a tie goes to the company's own figure
    many = {"A": [{"year": y} for y in range(2010, 2025)]}
    assert len(pick_entity([("own", ("A",))], many)[1]) == TREND_YEARS
    gaps = {"A": [{"year": y} for y in (2012, 2013, 2022, 2024)]}
    assert [r["year"] for r in pick_entity([("own", ("A",))], gaps)[1]] == [2024, 2022]    # not 2013 as a 'recent' point
    assert squash("Côte d'Ivoire") == "ctedivoire" and MILEX_ALIAS["korea, south"] == "South Korea"
    print("sipri_ui self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    import psycopg2
    import psycopg2.extras
    from backend.routine import env
    conn = psycopg2.connect(env()["KSSL_STAGING_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            arms, milex = build_arms(cur), build_milex(cur)
            print(f"sipri_arms_company: {write(cur, 'sipri_arms_company', arms)} rows, "
                  f"{len({r['competitor_id'] for r in arms})} competitors")
            print(f"sipri_milex_country: {write(cur, 'sipri_milex_country', milex)} rows, {len({r['country_name'] for r in milex})} country names")
        conn.rollback() if a.dry_run else conn.commit()
        print("dry run: rolled back" if a.dry_run else "committed")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    from backend import ops_log as _ops
    sys.exit(_ops.logged("backend.sipri_ui")(main)())
