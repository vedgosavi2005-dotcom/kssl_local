"""Database layer: structure, keys and relations, data quality, publish consistency and sources -- for every table of both
databases (staging DB: staging / staging_ui / media / activity / ops; serving DB: serving / ui / activity / analytics)."""
from __future__ import annotations

import re

import psycopg2
import pytest

from backend.review import ALT_KEY, GRAPH, SERVING_TABLES
from conftest import CARD_SCHEMA, DSN, UI_SCHEMA, columns, rows, scalar, tables

DBS = ("staging", "serving")
REVIEWED = [t for t, (_, rev, _) in GRAPH.items() if rev]
VOLATILE = {"created_at", "updated_at", "fetched_at", "retrieved_at", "loaded_at", "checked_at"}
URL_COLS = re.compile(r"(^|_)url$|_urls?$")
NOT_SOURCE_URL = {"image_url", "thumbnail_url", "image_source_url", "feed_url", "status_check_url", "portal_url", "url_kind"}
# a whole value that is a leaked program value or a filler, never data
# ("none" is a real code value -- classification none, overlap none -- and "dummy" a real ammunition word: not listed)
PLACEHOLDER = {"undefined", "null", "nan", "[object object]", "lorem ipsum", "tbd", "todo", "placeholder", "xxx"}
BOOKKEEPING_AT = {"created_at", "updated_at", "fetched_at", "retrieved_at", "loaded_at", "checked_at", "received_at", "decided_at",
                  "translated_at", "found_at", "started_at", "ended_at"}
# url columns that are not web addresses by design: fact_source marks model judgements / stored rows with a word, not a url
URL_EXEMPT = {("fact_source", "source_url"): "source_tier NOT IN ('judgement', 'stored')", ("source_document", "feed_url"): "false"}
# domain ranges of numeric columns: (column regex, min, max)
RANGES = [(r"^(probability|impact(_.*)?|value_score|strategic_score|maturity_level)$", 1, 5),
          (r"^decision_level$", 1, 3), (r"^(risk_score|fit_percent|fit_score|edge_score)$", 0, 100),
          (r"(^|_)rank(_position)?$|_rank$", 1, 10_000), (r"(^|_)year$", 1800, 2100),
          (r"_count$|^quantity$|^value_amount$|^amount_value$|^employee_count$", 0, None)]


def _graph_tables(db):
    have = set(tables(db, CARD_SCHEMA[db]))
    return [t for t in GRAPH if t in have]


def _all_tables():
    out = []
    for db in DBS:
        for s in (CARD_SCHEMA[db], UI_SCHEMA[db], "activity", "media", "ops"):
            out += [(db, s, t) for t in tables(db, s)]
    return out


ALL = _all_tables()
ALL_IDS = [f"{db}:{s}.{t}" for db, s, t in ALL]
GRAPH_DB = [(db, t) for db in DBS for t in _graph_tables(db)]
GRAPH_IDS = [f"{db}:{t}" for db, t in GRAPH_DB]
FKS = [(db, t, fk, parent) for db, t in GRAPH_DB for fk, parent in GRAPH[t][2]]


def _key(table, db):
    return GRAPH[table][0], ALT_KEY.get(table)


# ---- structure ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("db", DBS)
def test_schemas_exist(db):
    """DB-001 · Each database holds its schemas
    Steps: list the schemas of the database.
    Expected: staging DB has staging, staging_ui, media, activity, ops; serving DB has serving, ui, activity, analytics."""
    want = {"staging": {"staging", "staging_ui", "media", "activity", "ops"}, "serving": {"serving", "ui", "activity", "analytics"}}[db]
    have = {r["nspname"] for r in rows(db, "SELECT nspname FROM pg_namespace")}
    assert want <= have, f"missing schemas: {sorted(want - have)}"


@pytest.mark.parametrize("table", list(GRAPH))
def test_card_tables_exist_in_both(table):
    """DB-002 · Every card-model table exists in staging and serving
    Steps: for each table of the card model (backend/review.py GRAPH), look it up in staging.* and serving.*.
    Expected: present in both, so Approve can copy it to the live database."""
    missing = [db for db in DBS if table not in tables(db, CARD_SCHEMA[db])]
    assert not missing, f"{table} missing in: {missing}"


@pytest.mark.parametrize("table", [t for t in list(GRAPH) + list(SERVING_TABLES)])
def test_staging_serving_same_columns(table):
    """DB-003 · Staging and serving tables have the same columns
    Steps: compare the column names of staging.<t> and serving.<t>.
    Expected: identical; Publish copies only shared columns, so a staging-only column never reaches the live site and a
    serving-only column is never filled."""
    st, sv = columns("staging", "staging", table), columns("serving", "serving", table)
    if not st or not sv:
        pytest.skip("table missing in one database (DB-002)")
    only_st, only_sv = sorted(set(st) - set(sv)), sorted(set(sv) - set(st))
    assert not only_st and not only_sv, f"only in staging: {only_st}; only in serving: {only_sv}"


def test_ui_table_sets_match():
    """DB-004 · Every staging_ui table has a live ui twin
    Steps: list staging_ui.* (staging DB) and ui.* (serving DB).
    Expected: the same table names."""
    st, sv = set(tables("staging", "staging_ui")), set(tables("serving", "ui"))
    assert st == sv, f"only staging_ui: {sorted(st - sv)}; only ui: {sorted(sv - st)}"


@pytest.mark.parametrize("table", tables("staging", "staging_ui"))
def test_ui_columns_match(table):
    """DB-005 · ui tables have the same columns in both databases
    Steps: compare columns of staging_ui.<t> and ui.<t>.
    Expected: identical."""
    st, sv = columns("staging", "staging_ui", table), columns("serving", "ui", table)
    if not sv:
        pytest.skip("no live twin (DB-004)")
    assert set(st) == set(sv), f"only staging_ui: {sorted(set(st) - set(sv))}; only ui: {sorted(set(sv) - set(st))}"


@pytest.mark.parametrize("db", DBS)
def test_primary_keys_declared(db):
    """DB-006 · Tables declare a primary key
    Steps: list base tables of the card and ui schemas with no PRIMARY KEY constraint.
    Expected: none; without one the database cannot stop duplicate rows (DB-011 checks the keys in the data instead)."""
    r = rows(db, """SELECT n.nspname || '.' || c.relname AS t FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind = 'r' AND n.nspname IN (%s, %s)
                      AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p') ORDER BY 1""",
             (CARD_SCHEMA[db], UI_SCHEMA[db]))
    assert not r, f"{len(r)} tables without a primary key, e.g. {[x['t'] for x in r[:15]]}"


# ---- keys and relations ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("db,table", GRAPH_DB, ids=GRAPH_IDS)
def test_key_not_null(db, table):
    """DB-010 · Every row has its key
    Steps: count rows whose key column (and alternate key, where the model has one) is NULL.
    Expected: 0."""
    k, alt = _key(table, db)
    cond = f'"{k}" IS NULL' + (f' AND "{alt}" IS NULL' if alt else "")
    n = scalar(db, f'SELECT count(*) FROM {CARD_SCHEMA[db]}."{table}" WHERE {cond}')
    assert n == 0, f"{n} rows with no {k}"


@pytest.mark.parametrize("db,table", GRAPH_DB, ids=GRAPH_IDS)
def test_key_unique(db, table):
    """DB-011 · Keys are unique
    Steps: group rows by key column, count keys used more than once.
    Expected: 0 duplicate keys (a duplicate key makes a card ambiguous to review and to the UI)."""
    k, alt = _key(table, db)
    expr = f'coalesce("{k}"::text, "{alt}"::text)' if alt else f'"{k}"::text'
    dup = rows(db, f'SELECT {expr} AS k, count(*) AS n FROM {CARD_SCHEMA[db]}."{table}" WHERE {expr} IS NOT NULL GROUP BY 1 HAVING count(*) > 1 LIMIT 10')
    assert not dup, f"duplicate keys: {[(d['k'], d['n']) for d in dup]}"


@pytest.mark.parametrize("db,table,fk,parent", FKS, ids=[f"{d}:{t}.{f}->{p}" for d, t, f, p in FKS])
def test_no_orphans(db, table, fk, parent):
    """DB-012 · Child rows point at an existing parent
    Steps: for each parent link of the card model, find child rows whose link value has no parent row (same database).
    Expected: 0 orphans; in serving an orphan is live data whose parent card is not live."""
    s = CARD_SCHEMA[db]
    if parent not in tables(db, s):
        pytest.skip(f"parent {parent} missing")
    pk, alt = _key(parent, db)
    match = f'p."{pk}"::text = c."{fk}"::text' + (f' OR p."{alt}"::text = c."{fk}"::text' if alt else "")
    r = rows(db, f'''SELECT c."{fk}"::text AS v, count(*) AS n FROM {s}."{table}" c WHERE c."{fk}" IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM {s}."{parent}" p WHERE {match}) GROUP BY 1 ORDER BY 2 DESC LIMIT 10''')
    assert not r, f"{sum(x['n'] for x in r)}+ orphan rows, {fk} values: {[x['v'] for x in r[:5]]}"


@pytest.mark.parametrize("db,table", GRAPH_DB, ids=GRAPH_IDS)
def test_no_duplicate_rows(db, table):
    """DB-013 · No row is stored twice under different keys
    Steps: compare rows on every column except the key and bookkeeping timestamps.
    Expected: no two rows identical (a duplicate shows the same fact twice on the site)."""
    k, alt = _key(table, db)
    ids = {c for c in (k, alt) if c and (c.endswith("_id") or c == "publication_number")}   # a text key (area, segment) IS the row
    drop = "ARRAY[" + ",".join(f"'{c}'" for c in {*ids, *VOLATILE}) + "]"
    n = scalar(db, f'''SELECT count(*) - count(DISTINCT md5((to_jsonb(t) - {drop}::text[])::text))
                       FROM {CARD_SCHEMA[db]}."{table}" t''')
    assert n == 0, f"{n} duplicate rows"


# ---- data quality: every table -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("db,schema,table", ALL, ids=ALL_IDS)
def test_no_placeholder_values(db, schema, table):
    """DB-020 · No leaked program values or filler text
    Steps: in every text column, look for whole values like 'undefined', 'null', 'NaN', '[object Object]', 'TBD', 'lorem ipsum'.
    Expected: none (data must never be invented or be a program artefact)."""
    cols = [c for c, t in columns(db, schema, table).items() if t in ("text", "character varying")]
    if not cols:
        pytest.skip("no text columns")
    found = {}
    for c in cols:
        n = scalar(db, f'SELECT count(*) FROM {schema}."{table}" WHERE lower(btrim("{c}")) = ANY(%s)', (sorted(PLACEHOLDER),))
        if n:
            found[c] = n
    assert not found, f"placeholder values: {found}"


@pytest.mark.parametrize("db,schema,table", ALL, ids=ALL_IDS)
def test_urls_are_absolute(db, schema, table):
    """DB-021 · URL columns hold absolute web addresses
    Steps: in every column named *url*, find non-empty values that do not start with http:// or https:// (or the app's own
    /api/image/ path for images).
    Expected: none."""
    cols = [c for c, t in columns(db, schema, table).items() if URL_COLS.search(c) and t in ("text", "character varying")
            and c != "url_kind"]
    if not cols:
        pytest.skip("no url columns")
    bad = {}
    for c in cols:
        only = URL_EXEMPT.get((table, c), "true")
        r = rows(db, f'''SELECT "{c}" AS v FROM {schema}."{table}" WHERE coalesce(btrim("{c}"), '') <> '' AND ({only})
                         AND "{c}" !~* '^https?://[^ ]+$' AND "{c}" !~ '^/api/image/' LIMIT 3''')
        if r:
            bad[c] = [x["v"][:80] for x in r]
    assert not bad, f"not absolute urls: {bad}"


@pytest.mark.parametrize("db,schema,table", ALL, ids=ALL_IDS)
def test_dates_plausible(db, schema, table):
    """DB-022 · Dates are plausible
    Steps: every date / timestamp column: earliest and latest value; bookkeeping columns (*_at) against the DB clock.
    Expected: all dates between 1800 and 2100 (a company's presence can date from the 1800s); no bookkeeping timestamp
    (created / fetched / decided ...) more than a day in the future. Deadlines and due dates may be in the future."""
    cols = {c: t for c, t in columns(db, schema, table).items() if t.startswith(("date", "timestamp"))}
    if not cols:
        pytest.skip("no date columns")
    bad = {}
    for c in cols:
        r = rows(db, f'SELECT min("{c}")::text AS lo, max("{c}")::text AS hi, '
                     f'count(*) FILTER (WHERE "{c}" > now() + interval \'1 day\') AS fut FROM {schema}."{table}"')[0]
        if r["lo"] and (r["lo"] < "1800" or r["hi"] > "2100"):
            bad[c] = f"{r['lo']} .. {r['hi']}"
        elif c in BOOKKEEPING_AT and r["fut"]:
            bad[c] = f"{r['fut']} in the future (max {r['hi']})"
    assert not bad, f"implausible dates: {bad}"


@pytest.mark.parametrize("db,schema,table", ALL, ids=ALL_IDS)
def test_numeric_ranges(db, schema, table):
    """DB-023 · Scores, ranks, counts and years are in range
    Steps: numeric columns by name: probability / impact / scores 1-5, decision level 1-3, risk / fit / edge 0-100,
    ranks >= 1, years 1800-2100, counts / quantities / amounts >= 0.
    Expected: no value outside its range."""
    cols = {c: t for c, t in columns(db, schema, table).items() if t in ("integer", "smallint", "bigint", "numeric", "real", "double precision")}
    bad = {}
    for c in cols:
        for rx, lo, hi in RANGES:
            if re.search(rx, c):
                cond = " OR ".join(x for x in (f'"{c}" < {lo}' if lo is not None else "", f'"{c}" > {hi}' if hi is not None else "") if x)
                n = scalar(db, f'SELECT count(*) FROM {schema}."{table}" WHERE {cond}')
                if n:
                    bad[c] = f"{n} outside [{lo}, {hi}]"
                break
    if not cols:
        pytest.skip("no numeric columns")
    assert not bad, f"out of range: {bad}"


# ---- database objects --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("db", DBS)
def test_event_types_match_api(db):
    """DB-030 · The usage log accepts exactly the event types the API stores
    Steps: read the CHECK constraint of activity.event.event_type; compare with TRACK_TYPES in backend/app.py.
    Expected: the same set (a type the API accepts but the table refuses would make every batch fail)."""
    from backend.app import TRACK_TYPES
    d = scalar(db, """SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'event_event_type_check'
                      AND conrelid = 'activity.event'::regclass""")
    assert d, "no event_type CHECK on activity.event"
    assert set(re.findall(r"'(\w+)'", d)) == TRACK_TYPES


@pytest.mark.parametrize("db", DBS)
def test_views_queryable(db):
    """DB-031 · Every view runs
    Steps: SELECT one row from every view of the app schemas (activity, analytics, ops, staging, serving).
    Expected: no view errors (a view left pointing at a dropped column fails here)."""
    vs = rows(db, """SELECT schemaname || '.' || viewname AS v FROM pg_views
                     WHERE schemaname IN ('activity', 'analytics', 'ops', 'staging', 'serving')""")
    bad = {}
    for v in vs:
        try:
            scalar(db, f"SELECT 1 FROM {v['v']} LIMIT 1")
        except psycopg2.Error as e:
            bad[v["v"]] = str(e).splitlines()[0]
    assert vs, "no views found"
    assert not bad, f"failing views: {bad}"


def test_serving_guard_triggers():
    """DB-032 · Live tables can only be written through Approve
    Steps: list serving.* and ui.* tables without the only_via_approve trigger.
    Expected: none."""
    r = rows("serving", """SELECT n.nspname || '.' || c.relname AS t FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                           WHERE c.relkind = 'r' AND n.nspname IN ('serving', 'ui') AND NOT EXISTS (
                             SELECT 1 FROM pg_trigger g WHERE g.tgrelid = c.oid AND g.tgname = 'only_via_approve')""")
    assert not r, f"unguarded live tables: {[x['t'] for x in r]}"


def test_serving_guard_blocks_writes():
    """DB-033 · A direct write to a live table is refused
    Steps: in a transaction that is always rolled back, run DELETE ... WHERE false on serving.fx_rate without the approve flag.
    Expected: the guard trigger raises an error (nothing can be deleted either way)."""
    conn = psycopg2.connect(DSN["serving"], connect_timeout=10)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.Error):
                cur.execute("DELETE FROM serving.fx_rate WHERE false")
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("db", DBS)
def test_app_role_grants(db):
    """DB-034 · The app role can read what the APIs read
    Steps: where the role kssl_app exists (the VPS), check SELECT on every table and view the API reads.
    Expected: no missing grant (a missing one is a 500 on the site)."""
    if not scalar(db, "SELECT count(*) FROM pg_roles WHERE rolname = 'kssl_app'"):
        pytest.skip("no kssl_app role in this database (local); runs on the VPS")
    schemas = ("serving", "ui", "activity", "analytics") if db == "serving" else ("staging", "staging_ui", "media", "activity", "ops")
    r = rows(db, """SELECT table_schema || '.' || table_name AS t FROM information_schema.tables WHERE table_schema = ANY(%s)
                    AND NOT has_table_privilege('kssl_app', quote_ident(table_schema) || '.' || quote_ident(table_name), 'SELECT')""",
             (list(schemas),))
    assert not r, f"kssl_app cannot read: {[x['t'] for x in r[:20]]}"


# ---- publish consistency (staging -> serving) ------------------------------------------------------------------------------

@pytest.mark.parametrize("table", REVIEWED)
def test_live_cards_exist_in_staging(table):
    """DB-040 · Every live card still exists in staging
    Steps: keys of serving.<card table> minus keys of staging.<card table>.
    Expected: none; a live card with no staging row can no longer be reviewed, changed or traced."""
    k, alt = _key(table, "serving")
    expr = f'coalesce("{k}"::text, "{alt}"::text)' if alt else f'"{k}"::text'
    sv = {r["k"] for r in rows("serving", f'SELECT {expr} AS k FROM serving."{table}"')}
    st = {r["k"] for r in rows("staging", f'SELECT {expr} AS k FROM staging."{table}"')}
    assert not (sv - st), f"{len(sv - st)} live cards missing from staging, e.g. {sorted(sv - st)[:5]}"


@pytest.mark.parametrize("db", DBS)
def test_sources_point_at_existing_rows(db):
    """DB-041 · Source records belong to existing rows
    Steps: fact_source rows whose (table_name, row_id) has no row in that table of the same database.
    Expected: none. A stale source usually means the table was rebuilt with new row ids and its sources were not moved:
    the new rows then show no source."""
    s, bad = CARD_SCHEMA[db], {}
    for t in {r["table_name"] for r in rows(db, f"SELECT DISTINCT table_name FROM {s}.fact_source")}:
        if t not in GRAPH or t not in tables(db, s):
            continue
        k, alt = _key(t, db)
        match = f'x."{k}"::text = f.row_id' + (f' OR x."{alt}"::text = f.row_id' if alt else "")
        n = scalar(db, f'''SELECT count(DISTINCT f.row_id) FROM {s}.fact_source f WHERE f.table_name = %s
                              AND NOT EXISTS (SELECT 1 FROM {s}."{t}" x WHERE {match})''', (t,))
        if n:
            bad[t] = n
    assert not bad, f"row ids with sources but no row: {dict(sorted(bad.items(), key=lambda x: -x[1]))}"


def test_review_decisions_point_at_cards():
    """DB-042 · Review decisions belong to existing cards
    Steps: staging.review_decision rows whose card no longer exists in staging.
    Expected: none."""
    bad = {}
    for t in {r["table_name"] for r in rows("staging", "SELECT DISTINCT table_name FROM staging.review_decision")}:
        if t not in GRAPH:
            bad[t] = "not a card table"
            continue
        k, alt = _key(t, "staging")
        match = f'x."{k}"::text = d.row_key' + (f' OR x."{alt}"::text = d.row_key' if alt else "")
        n = scalar("staging", f'''SELECT count(*) FROM staging.review_decision d WHERE d.table_name = %s
                                  AND NOT EXISTS (SELECT 1 FROM staging."{t}" x WHERE {match})''', (t,))
        if n:
            bad[t] = n
    assert not bad, f"decisions without a card: {bad}"


# ---- sources: data is never invented ---------------------------------------------------------------------------------------

def _sourced_keys(db: str, table: str) -> set[str]:
    """keys of rows with a source of their own: an http url column, or a fact_source row"""
    s = CARD_SCHEMA[db]
    k, alt = _key(table, db)
    kx = f'coalesce(x."{k}"::text, x."{alt}"::text)' if alt else f'x."{k}"::text'
    ucols = [c for c in columns(db, s, table) if URL_COLS.search(c) and c not in NOT_SOURCE_URL]
    own = " OR ".join(f"x.\"{c}\"::text ~* '^https?://'" for c in ucols) or "false"
    return {r["k"] for r in rows(db, f'''SELECT {kx} AS k FROM {s}."{table}" x WHERE {own} OR EXISTS (
                SELECT 1 FROM {s}.fact_source f WHERE f.table_name = %s AND f.row_id = {kx} AND f.source_url ~* '^https?://')''', (table,))}


def _unsourced_cards(db: str, table: str) -> list[str]:
    """cards of `table` with no source anywhere in their bundle (the card row or any row under it)"""
    s = CARD_SCHEMA[db]
    memo: dict[str, set[str]] = {}

    def sourced(t: str) -> set[str]:          # keys of t sourced by themselves or by a non-reviewed descendant
        if t in memo:
            return memo[t]
        memo[t] = set()
        keys = _sourced_keys(db, t)
        for child, (_, rev, parents) in GRAPH.items():
            if rev or child not in tables(db, s):
                continue
            for fk, p in parents:
                if p == t:
                    ck, calt = _key(child, db)
                    kids = sourced(child)
                    if kids:
                        kx = f'coalesce("{ck}"::text, "{calt}"::text)' if calt else f'"{ck}"::text'
                        keys |= {r["v"] for r in rows(db, f'SELECT DISTINCT "{fk}"::text AS v FROM {s}."{child}" WHERE {kx} = ANY(%s)',
                                                      (list(kids),)) if r["v"]}
        memo[t] = keys
        return keys

    k, alt = _key(table, db)
    kx = f'coalesce("{k}"::text, "{alt}"::text)' if alt else f'"{k}"::text'
    allk = {r["k"] for r in rows(db, f'SELECT {kx} AS k FROM {s}."{table}"')}
    return sorted(allk - sourced(table))


@pytest.mark.parametrize("table", REVIEWED)
def test_review_cards_have_a_source(table):
    """DB-050 · Every card in the review copy has a source
    Steps: for each card of the table (staging), look for a web source on the card row or on any row of its bundle
    (an http url column, or a staging.fact_source row).
    Expected: every card has one -- the review site shows a source on everything, and no data may be invented."""
    miss = _unsourced_cards("staging", table)
    assert not miss, f"{len(miss)} cards with no source, e.g. {miss[:5]}"


NEWS_DERIVED = ["competitive_signal", "competitive_news_article", "competitive_product_news", "competitive_competitor_moment",
                "competitive_project", "competitive_partnership", "competitive_geo_company_presence", "market_tender",
                "market_award", "market_global_requirement", "technology_innovation", "technology_overview_article"]


@pytest.mark.parametrize("table", NEWS_DERIVED)
def test_live_news_cards_have_a_source(table):
    """DB-051 · Every live news-derived card has a source
    Steps: as DB-050, on serving (signals, news, movement, projects, partnerships, geo, tenders, awards, requirements,
    innovations, technology articles).
    Expected: every live card has one -- the live site shows sources on news-derived data."""
    miss = _unsourced_cards("serving", table)
    assert not miss, f"{len(miss)} live cards with no source, e.g. {miss[:5]}"


@pytest.mark.parametrize("db", DBS)
def test_fact_source_rows_valid(db):
    """DB-052 · Source records are complete
    Steps: fact_source rows: table_name is a card-model table, row_id set, source_url absolute (except model judgements),
    source_tier set.
    Expected: no incomplete source record."""
    s = CARD_SCHEMA[db]
    r = rows(db, f"""SELECT count(*) FILTER (WHERE table_name <> ALL(%s)) AS unknown_table,
                            count(*) FILTER (WHERE coalesce(row_id, '') = '') AS no_row,
                            count(*) FILTER (WHERE source_tier IS NULL) AS no_tier,
                            count(*) FILTER (WHERE source_tier NOT IN ('judgement', 'stored') AND coalesce(source_url, '') !~* '^https?://') AS bad_url
                     FROM {s}.fact_source""", (list(GRAPH) + list(SERVING_TABLES),))[0]
    bad = {k: v for k, v in r.items() if v}
    assert not bad, f"incomplete source records: {bad}"


def test_dead_links_have_archive_copies():
    """DB-053 · Every dead source link has an archive copy
    Steps: staging.source_link rows with status 404 / 410 (filled by scripts/check_source_links.py).
    Expected: each has an archive_url; one without is a source that no longer opens anywhere and needs another article."""
    if not scalar("staging", "SELECT to_regclass('staging.source_link') IS NOT NULL"):
        pytest.skip("staging.source_link not created (db/setup/38)")
    r = rows("staging", "SELECT url FROM staging.source_link WHERE status IN (404, 410) AND archive_url IS NULL ORDER BY 1")
    assert not r, f"{len(r)} dead links with no archive copy, e.g. {[x['url'][:90] for x in r[:5]]}"
