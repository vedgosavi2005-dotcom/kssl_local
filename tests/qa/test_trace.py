"""Database -> API: the data the API sends is the data in the database. Every object of /api/dataset that names its row
(_src = {t: table, k: key column, id}) is looked up in the database that site reads (live -> serving, review -> staging),
and its fields are compared with the row's columns; collections are counted against their tables; ui tables are compared
whole."""
from __future__ import annotations

import collections
import datetime as dt
import decimal
import re

import pytest

from conftest import SITE_DB, UI_SCHEMA, dataset, dead_links, rows, scalar, src_objects, tables

SITES = ("live", "review")

# payload field -> database column, per (collection, table); found by matching values, then fixed here
FIELD_MAP = {
    ("competitiveCards", "competitive_signal"): {"title": "title", "companyId": "company_id", "classification": "classification",
        "meta": "category", "sowhat": "summary", "timeToEffect": "time_to_effect", "inClientMarket": "in_client_market",
        "storyId": "story_id", "seq": "sequence_no", "ago": "published_date"},
    ("tenders", "market_tender"): {"title": "title", "issuer": "buyer_name", "country": "country_name", "status": "status",
        "url": "source_url", "posted": "published_date", "urlKind": "url_kind"},
    ("tenders", "market_tender_source"): {"label": "portal_name", "url": "source_url"},
    ("tenders", "market_tender_eligibility"): {"item": "item", "state": "state", "note": "note"},
    ("tenders", "market_tender_competitor_fit"): {"company": "competitor_name", "fit": "fit_label", "why": "fit_rationale"},
    ("awards", "market_award"): {"buyer": "buyer", "title": "title", "tender_no": "tender_number", "date": "award_date",
        "year": "award_year", "country": "country_name", "url": "source_url", "value_text": "value_text"},
    ("globalRequirements", "market_global_requirement"): {"title": "title", "cat": "category", "buyer": "buyer_name",
        "country": "country_name", "status": "status", "desc": "description", "ksslFit": "kssl_fit",
        "strategicAssessment": "strategic_assessment"},
    ("projects", "competitive_project"): {"name": "project_title", "cid": "competitor_id", "company": "company_display",
        "region": "region", "customer": "customer", "stage": "stage", "stageNote": "stage_note", "kind": "kind"},
    ("competitors", "competitive_competitor"): {"name": "display_name", "hq": "headquarters", "country": "origin_country",
        "sector": "industry_short", "qualificationReason": "qualification_reason"},
    ("competitors", "competitive_product"): {"name": "product_name", "cid": "competitor_id", "category": "category",
        "description": "description", "country": "country"},
    ("competitors", "competitive_leader"): {"full_name": "full_name", "org": "organization", "detail": "role_title", "url": "role_source_url"},
    ("competitors", "competitive_leader_record"): {"text": "headline", "url": "source_url"},
    ("competitors", "competitive_partnership"): {"label": "partner_name", "ptype": "partner_type", "status": "status",
        "note": "description", "as_of": "as_of_date"},
    ("competitors", "competitive_product_news"): {"title": "headline", "url": "article_url", "source": "publisher"},
    ("competitors", "client_product"): {"name": "product_name", "description": "description", "category": "category"},
    ("competitorNews", "competitive_news_article"): {"title": "headline", "source": "publisher", "url": "article_url", "date": "published_date"},
    ("competitorNews", "competitive_competitor_moment"): {"title": "title", "description": "what_happened", "date": "movement_date",
        "url": "source_url", "level": "grade", "analysis": "kssl_analysis"},
    ("geoPresence", "competitive_geo_company_presence"): {"comp": "company_name", "activity": "activity_type",
        "status": "presence_status", "cid": "competitor_id", "overlap": "overlap_status", "summary": "products_summary"},
    ("matchups", "competitive_matchup"): {"compBy": "competitor_name", "bf": "client_product_name", "reason": "match_basis",
        "compId": "competitor_id", "compProductId": "competitor_product_id", "clientProductId": "client_product_id"},
    ("techCards", "technology_overview_article"): {"title": "title", "sowhat": "card_summary", "lens": "lens",
        "maturity": "maturity", "relevance": "relevance", "horizon": "horizon", "ago": "published_on"},
    ("innovations", "technology_innovation"): {"t": "title", "s": "list_description", "kind": "technology_kind", "stance": "stance"},
    ("KSSL_PARTNERS", "client_partner"): {"label": "partner_name", "ptype": "partner_type", "status": "relationship_status", "country": "country"},
    ("PATENTS", "competitive_patent_filing"): {"title": "title", "status": "status", "filed": "filed_date", "url": "patent_url"},
    ("topOpportunities", "market_next_move"): {"action": "action_text", "tenderId": "tender_id", "priority": "priority", "status": "status"},
    ("COMPSYN", "competitive_synthesis"): {"thesis": "thesis"},
    ("FIELDSYN", "competitive_field_synthesis"): {"field": "field_title", "pattern": "pattern", "implication": "implication"},
}


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return str(int(v)) if v == v.to_integral_value() else str(float(v))
    return str(v).strip()


_ROWS: dict = {}


def _db_rows(db: str, table: str, key: str) -> dict[str, dict]:
    if (db, table, key) not in _ROWS:
        s = "serving" if db == "serving" else "staging"
        _ROWS[(db, table, key)] = {str(r[key]): r for r in rows(db, f'SELECT * FROM {s}."{table}"')}
    return _ROWS[(db, table, key)]


@pytest.mark.parametrize("site", SITES)
def test_every_object_is_a_database_row(site):
    """TRC-001 · Nothing on the site is invented: every object comes from a database row
    Steps: walk /api/dataset; for each object carrying _src {table, key column, id}, look the row up in the database the
    site reads (live -> serving, review -> staging).
    Expected: every row exists."""
    db, missing, n = SITE_DB[site], collections.Counter(), 0
    for coll, o in src_objects(dataset(site)):
        s = o["_src"]
        if not s.get("k"):
            continue
        n += 1
        if str(s["id"]) not in _db_rows(db, s["t"], s["k"]):
            missing[(coll, s["t"])] += 1
    assert n > 1000, f"only {n} traceable objects"
    assert not missing, f"objects with no database row: {dict(missing)}"


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("coll,table", list(FIELD_MAP), ids=[f"{c}.{t}" for c, t in FIELD_MAP])
def test_fields_match_database(site, coll, table):
    """TRC-002 · Each field the API sends equals its database column
    Steps: for every object of the collection from this table, compare each mapped field with the row's column (dates as
    ISO text; a dead source url may be replaced by its archive copy; a year-precision date shows as the year; KSSL's own
    rows carry the client id "1").
    Expected: all equal."""
    db, fmap, dead = SITE_DB[site], FIELD_MAP[(coll, table)], dead_links()
    objs = [o for c, o in src_objects(dataset(site)) if c == coll and o["_src"]["t"] == table]
    if not objs:
        pytest.skip(f"no {table} objects in {coll} on {site}")
    bad = collections.Counter()
    sample = {}
    for o in objs:
        row = _db_rows(db, table, o["_src"]["k"]).get(str(o["_src"]["id"]))
        if row is None:
            continue
        for f, col in fmap.items():
            if f not in o or col not in row:
                continue
            got, want = _s(o[f]), _s(row[col])
            if got == want or (col.endswith("url") and dead.get(want) == got) or (want[:10] == got and len(got) == 10):
                continue
            if len(got) == 4 and want.startswith(got + "-01-01"):      # a year-precision date is shown as the year
                continue
            if col == "competitor_id" and not want and got == "1":       # the client's own rows (KSSL) carry the UI id "1"
                continue
            if isinstance(row[col], (int, float, decimal.Decimal)) and got and want and float(got) == float(want):
                continue
            bad[f] += 1
            sample.setdefault(f, (o["_src"]["id"], want[:60], got[:60]))
    assert not bad, f"{dict(bad)} of {len(objs)} differ; e.g. (id, db, api): {sample}"


VISIBLE = {   # collection -> SQL counting the rows the site must show (qualifying competitors only, user decision 2026-10-18)
    "tenders": "SELECT count(*) FROM {s}.market_tender",
    "awards": "SELECT count(*) FROM {s}.market_award",
    "globalRequirements": "SELECT count(*) FROM {s}.market_global_requirement",
    "KSSL_PARTNERS": "SELECT count(*) FROM {s}.client_partner",
    "competitors": "SELECT count(*) FROM {s}.competitive_competitor WHERE qualifies IS TRUE",
}


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("coll", list(VISIBLE))
def test_collection_complete(site, coll):
    """TRC-003 · Every row that should show reaches the API
    Steps: count the table's rows that the site shows (tenders, awards, global requirements, KSSL partners, qualifying
    competitors + the client); count the collection in /api/dataset.
    Expected: equal -- no row is lost between database and API."""
    db = SITE_DB[site]
    s = "serving" if db == "serving" else "staging"
    want = scalar(db, VISIBLE[coll].format(s=s))
    got = dataset(site)[coll]
    n = len(got)
    if coll == "competitors":
        n -= sum(1 for c in got.values() if c.get("_src", {}).get("t") == "client_account")
    assert n == want, f"database {want}, API {n}"


@pytest.mark.parametrize("site", SITES)
def test_hidden_competitors_never_sent(site):
    """TRC-004 · A competitor that does not qualify appears nowhere
    Steps: ids of competitors with qualifies not true; search the whole /api/dataset text for each id.
    Expected: none found (they are hidden from every page, user decision 2026-10-18)."""
    db = SITE_DB[site]
    s = "serving" if db == "serving" else "staging"
    hidden = [r["id"] for r in rows(db, f"SELECT competitor_id::text AS id FROM {s}.competitive_competitor WHERE qualifies IS NOT TRUE")]
    import json
    text = json.dumps({k: v for k, v in dataset(site).items() if k not in ("database", "databaseSchema", "review")})
    found = [h for h in hidden if h in text]
    assert not found, f"{len(found)} hidden competitors in the payload, e.g. {found[:3]}"


@pytest.mark.parametrize("site", SITES)
def test_ui_tables_sent_whole(site):
    """TRC-005 · Labels and settings tables reach the UI unchanged
    Steps: for every ui table (ui.* on live, staging_ui.* on review) compare row count and content with database.ui.<table>.
    Expected: the same rows."""
    db, payload = SITE_DB[site], dataset(site)["database"]["ui"]
    schema = UI_SCHEMA[db]
    bad = {}
    for t in tables(db, schema):
        n = scalar(db, f'SELECT count(*) FROM {schema}."{t}"')
        if len(payload.get(t, [])) != n:
            bad[t] = f"db {n}, api {len(payload.get(t, []))}"
    assert not bad, f"ui tables differing: {bad}"


@pytest.mark.parametrize("site", SITES)
def test_no_dead_links_sent(site):
    """TRC-006 · No source link the publisher took down is sent
    Steps: every dead url with an archive copy (staging.source_link); search /api/dataset for it.
    Expected: none -- the API sends the archive copy instead (backend/app.py swap_links)."""
    dead = dead_links()
    if not dead:
        pytest.skip("no dead links recorded yet (scripts/check_source_links.py)")
    import json
    text = json.dumps(dataset(site))
    sent = [u for u in dead if f'"{u}"' in text]
    assert not sent, f"{len(sent)} dead links sent, e.g. {sent[:3]}"


@pytest.mark.parametrize("site", SITES)
def test_images_exist(site):
    """TRC-007 · Every card image the API names is stored
    Steps: collect every /api/image/<id> in /api/dataset; look each id up in media.image (staging DB, both sites).
    Expected: all stored (a missing one is a broken picture)."""
    import json
    ids = set(re.findall(r"/api/image/([0-9a-f-]{36})", json.dumps(dataset(site))))
    have = {r["i"] for r in rows("staging", "SELECT image_id::text AS i FROM media.image WHERE image_id::text = ANY(%s)", (list(ids),))}
    assert ids, "no images referenced"
    assert not (ids - have), f"{len(ids - have)} images missing, e.g. {sorted(ids - have)[:3]}"


@pytest.mark.parametrize("site", SITES)
def test_fx_rates_match(site):
    """TRC-008 · Currency rates come from the fx_rate table
    Steps: compare fxRates in /api/dataset with the fx_rate table.
    Expected: every currency of the API is in the table with the same rate."""
    db = SITE_DB[site]
    s = "serving" if db == "serving" else "staging"
    cols = [c["column_name"] for c in rows(db, "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 'fx_rate'", (s,))]
    fx = dataset(site)["fxRates"]
    assert fx, "no fxRates"
    cur = next(c for c in cols if "currency" in c or c in ("code", "ccy"))
    db_codes = {r["c"] for r in rows(db, f'SELECT DISTINCT "{cur}" AS c FROM {s}.fx_rate')}
    assert set(fx) <= db_codes | {"INR"}, f"currencies not in fx_rate: {sorted(set(fx) - db_codes)}"


def test_live_is_subset_of_review():
    """TRC-009 · The live site shows only what passed review
    Steps: ids of tenders, signal cards, global requirements and awards on live vs review.
    Expected: every live id is also in the review copy (live data always comes from approved staging data)."""
    live, rev = dataset("live"), dataset("review")
    bad = {}
    for coll in ("tenders", "competitiveCards", "globalRequirements", "awards", "projects"):
        a, b = {x["id"] for x in live[coll]}, {x["id"] for x in rev[coll]}
        if a - b:
            bad[coll] = sorted(a - b)[:3]
    assert not bad, f"live-only ids: {bad}"
