"""Review between the loaders and the live UI: two databases (db/make_databases.sh).

  staging DB  (KSSL_STAGING_DSN)  staging.* / staging_ui.*   everything the loaders, the news job
                                  and hand inserts write; staging.fact_source, staging.review_decision
  serving DB  (KSSL_SERVING_DSN)  serving.* / ui.*           what the live UI shows; only Approve /
                                  Unpublish write here (guard triggers: db/setup/04_serving_db.sql)
  Each DSN falls back to KSSL_DSN, so one database holding all four schemas works too (test DBs).

  live backend   (default)          /api/dataset reads the serving DB
  review backend (KSSL_VIEW=review) /api/dataset reads the staging DB, plus a status per card and
                                    per setup table; POST /api/review* and GET /api/review/trace work

A card is one row of a REVIEWED table in GRAPH. Its bundle = the row + its non-reviewed descendants
(specs, evidence, timeline...). Approve replaces the card's bundle in serving with the staging bundle
(and the matching fact_source rows) in ONE serving-DB transaction; the parent card(s) must be live
first. Unpublish removes the card and everything under it (reviewed descendants too) from serving.
Reject records the rejected version's signature in staging.review_decision: a different later
version is pending again. Setup tables (every ui.* table and the reference tables in SERVING_TABLES)
have no cards: one Approve / Unpublish per table replaces / empties the whole live table.

Card status in the review copy: new (not live) / changed (live, staging differs) / live (same) /
rejected (this version was rejected; `live` says whether an older version is still live).
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2 import sql

C = "competitive_competitor"
# table -> (key column, reviewed?, [(fk column, parent table)]); an fk value equals the parent's key.
# Children (reviewed = False) belong to the card of their parent chain.
GRAPH: dict[str, tuple[str, bool, list[tuple[str, str]]]] = {
    "client_account": ("client_id", True, []),
    "client_product": ("client_product_id", True, [("client_id", "client_account")]),
    "client_product_specification": ("specification_id", False, [("client_product_id", "client_product")]),
    "client_product_program": ("program_id", False, [("client_product_id", "client_product")]),
    "client_product_source": ("source_id", False, [("client_product_id", "client_product")]),
    "client_partner": ("client_partner_id", True, [("client_id", "client_account")]),
    "client_partner_product": ("partner_product_id", False, [("client_partner_id", "client_partner")]),
    "client_partner_relationship": ("relationship_id", False, [("client_partner_id", "client_partner")]),
    "client_partner_source": ("source_id", False, [("client_partner_id", "client_partner")]),
    C: ("competitor_id", True, []),
    "competitive_competitor_location": ("location_id", False, [("competitor_id", C)]),
    "competitive_competitor_swot": ("swot_id", False, [("competitor_id", C)]),
    "competitive_stock_quote": ("stock_id", False, [("competitor_id", C)]),
    "competitive_stock_series": ("series_id", False, [("stock_id", "competitive_stock_quote")]),
    "competitive_patent_portfolio": ("portfolio_id", False, [("competitor_id", C)]),
    "competitive_patent_classification": ("classification_id", False, [("portfolio_id", "competitive_patent_portfolio")]),
    "competitive_leader": ("leader_id", True, [("competitor_id", C)]),
    "competitive_leader_record": ("record_id", False, [("leader_id", "competitive_leader")]),
    "competitive_news_article": ("article_id", True, [("competitor_id", C)]),
    "competitive_product": ("product_id", True, [("competitor_id", C)]),
    "competitive_product_specification": ("spec_id", False, [("product_id", "competitive_product")]),
    "competitive_product_program": ("program_id", False, [("product_id", "competitive_product")]),
    "competitive_product_news": ("product_news_id", True, [("product_id", "competitive_product")]),
    "competitive_matchup": ("matchup_id", True, [
        ("competitor_product_id", "competitive_product"), ("client_product_id", "client_product"), ("competitor_id", C)]),
    "competitive_matchup_specification": ("comparison_specification_id", False, [("matchup_id", "competitive_matchup")]),
    "competitive_matchup_advantage": ("advantage_id", False, [("matchup_id", "competitive_matchup")]),
    "competitive_matchup_source": ("source_id", False, [("matchup_id", "competitive_matchup")]),
    "competitive_partnership": ("relationship_id", True, [("competitor_id", C)]),
    "competitive_partnership_evidence": ("evidence_card_id", False, [("relationship_id", "competitive_partnership")]),
    "competitive_partnership_relationship_detail": ("detail_id", False, [("relationship_id", "competitive_partnership")]),
    "competitive_project": ("project_id", True, [("competitor_id", C)]),
    "competitive_project_source": ("source_id", False, [("project_id", "competitive_project")]),
    "competitive_project_specification": ("project_spec_id", False, [("project_id", "competitive_project")]),
    "competitive_project_stage": ("project_stage_id", False, [("project_id", "competitive_project")]),
    "competitive_project_timeline": ("timeline_id", False, [("project_id", "competitive_project")]),
    "competitive_geo_location": ("location_id", True, []),
    "competitive_geo_company_presence": ("presence_id", True, [
        ("location_id", "competitive_geo_location"), ("competitor_id", C)]),
    "competitive_geo_product": ("geo_product_id", False, [("presence_id", "competitive_geo_company_presence")]),
    "competitive_geo_product_match": ("match_id", False, [("geo_product_id", "competitive_geo_product")]),
    "competitive_geo_product_specification": ("comparison_spec_id", False, [("match_id", "competitive_geo_product_match")]),
    "competitive_geo_product_news": ("news_id", False, [("geo_product_id", "competitive_geo_product")]),
    "competitive_geo_source": ("source_id", False, [("geo_product_id", "competitive_geo_product")]),
    "competitive_patent_filing": ("publication_number", True, [("portfolio_id", "competitive_patent_portfolio")]),
    # prompt rebuild (db/setup/11_foundations.sql): rolled-up patent trend per portfolio, geo layer-2 findings per country
    "competitive_patent_trend": ("trend_id", False, [("portfolio_id", "competitive_patent_portfolio")]),
    "competitive_geo_analysis": ("analysis_id", False, [("location_id", "competitive_geo_location")]),
    "competitive_signal": ("signal_id", True, [("company_id", C)]),
    "competitive_signal_detail": ("signal_id", False, [("signal_id", "competitive_signal")]),
    "competitive_signal_evidence": ("evidence_id", False, [("signal_id", "competitive_signal")]),
    "competitive_competitor_moment": ("moment_id", True, [("competitor_id", C)]),
    "competitive_competitor_moment_analysis": ("analysis_id", False, [("moment_id", "competitive_competitor_moment")]),
    "competitive_competitor_moment_source": ("source_id", False, [("moment_id", "competitive_competitor_moment")]),
    "market_tender": ("tender_id", True, []),
    "market_tender_closing_window": ("closing_window_id", False, [("tender_id", "market_tender")]),
    "market_tender_competitor_fit": ("competitor_fit_id", False, [("tender_id", "market_tender")]),
    "market_tender_fit_assessment": ("assessment_id", False, [("tender_id", "market_tender")]),
    "market_tender_requirement": ("requirement_id", False, [("tender_id", "market_tender")]),
    "market_tender_source": ("source_id", False, [("tender_id", "market_tender")]),
    "market_tender_product_match": ("tender_match_id", False, [("tender_id", "market_tender")]),
    "market_tender_product_match_line": ("match_line_id", False, [("tender_match_id", "market_tender_product_match")]),
    "market_tender_eligibility": ("eligibility_id", False, [("tender_id", "market_tender")]),
    "market_top_opportunity_tender": ("top_opportunity_tender_id", True, [("tender_id", "market_tender")]),
    "market_opportunity": ("opportunity_id", True, []),
    "market_opportunity_fit_assessment": ("assessment_id", False, [("opportunity_id", "market_opportunity")]),
    "market_opportunity_source": ("source_id", False, [("opportunity_id", "market_opportunity")]),
    "market_opportunity_update": ("update_id", False, [("opportunity_id", "market_opportunity")]),
    "market_top_opportunity_project": ("top_opportunity_project_id", True, [("opportunity_id", "market_opportunity")]),
    "market_next_move": ("next_move_id", True, []),
    "market_global_requirement": ("requirement_id", True, []),
    "market_global_requirement_specification": ("requirement_spec_id", False, [("requirement_id", "market_global_requirement")]),
    "market_global_requirement_source": ("requirement_source_id", False, [("requirement_id", "market_global_requirement")]),
    "market_global_requirement_rival": ("rival_id", False, [("requirement_id", "market_global_requirement")]),
    "technology_innovation": ("innovation_id", True, []),
    "technology_innovation_status": ("status_id", False, [("innovation_id", "technology_innovation")]),
    "technology_innovation_company": ("innovation_company_id", False, [("innovation_id", "technology_innovation")]),
    "technology_innovation_source": ("innovation_source_id", False, [("innovation_id", "technology_innovation")]),
    "technology_innovation_analysis": ("analysis_id", False, [("innovation_id", "technology_innovation")]),
    "technology_innovation_milestone": ("milestone_id", False, [("innovation_id", "technology_innovation")]),
    "technology_overview_article": ("overview_article_id", True, []),
    "technology_overview_fact": ("overview_fact_id", False, [("overview_article_id", "technology_overview_article")]),
    "technology_overview_key_point": ("key_point_id", False, [("overview_article_id", "technology_overview_article")]),
    "technology_overview_company": ("overview_company_id", False, [("overview_article_id", "technology_overview_article")]),
    "technology_overview_source": ("overview_source_id", False, [("overview_article_id", "technology_overview_article")]),
    # one thread of events (prompts/story.py): a story is a card of its own, its dated steps are its children
    "story": ("story_id", True, []),
    "story_step": ("step_id", False, [("story_id", "story")]),
    # ui-port tables (db/setup/09_ui_port_tables.sql). The synthesis rows ride on the competitor card; the rest are their own cards.
    "competitive_synthesis": ("competitor_id", False, [("competitor_id", C)]),
    "competitive_synthesis_vulnerability": ("vulnerability_id", False, [("competitor_id", "competitive_synthesis")]),
    "competitive_synthesis_vulnerability_trace": ("trace_id", False, [("vulnerability_id", "competitive_synthesis_vulnerability")]),
    "competitive_field_synthesis": ("synthesis_id", True, []),
    "market_award": ("award_id", True, []),
    "market_segment_assessment": ("segment", True, []),
    "patent_field_assessment": ("area_label", True, []),
}
# Not in GRAPH (no page reads them): competitive_product_evaluation, competitive_product_evaluation_spec.
# A reviewed row whose key column is empty is keyed by its alternate column.
ALT_KEY = {"competitive_patent_filing": "filing_id"}
# Serving reference / summary tables approved as a whole (no cards). Every ui.* table is one too.
SERVING_TABLES = (
    "technology_pillar", "technology_category", "technology_category_ui_label", "technology_company",
    "technology_source", "technology_metric", "market_tender_portal", "market_category_summary",
    "market_filter_option", "market_top_opportunity_metric", "fx_rate",
)
# Bookkeeping columns: a change here alone does not make a card "changed".
VOLATILE = {"created_at", "updated_at", "fetched_at", "retrieved_at"}
# Schema names inside each database: the staging DB has staging / staging_ui, the serving DB serving / ui.
STAGING = {"serving": "staging", "ui": "staging_ui"}
LIVE = {"serving": "serving", "ui": "ui"}


# ---- connections ------------------------------------------------------------------------------

def review_mode() -> bool:
    return os.getenv("KSSL_VIEW", "").strip().lower() == "review"


def serving_dsn() -> str:
    return (os.getenv("KSSL_SERVING_DSN") or os.getenv("KSSL_DSN") or "").strip()


def staging_dsn() -> str:
    return (os.getenv("KSSL_STAGING_DSN") or os.getenv("KSSL_DSN") or "").strip()


@contextmanager
def session():
    """(staging cursor, serving cursor), each in its own transaction. Commit order: serving first,
    then staging (review_decision), so a failure between them never loses an approval."""
    dsns = (staging_dsn(), serving_dsn())
    if not all(dsns):
        raise RuntimeError("KSSL_STAGING_DSN / KSSL_SERVING_DSN (or KSSL_DSN) are not configured")
    conns: list = []
    try:
        for d in dsns:
            conns.append(psycopg2.connect(d, connect_timeout=5))
        st, sv = (c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) for c in conns)
        yield st, sv
        conns[1].commit()
        conns[0].commit()
    except Exception:
        for c in conns:
            c.rollback()
        raise
    finally:
        for c in conns:
            c.close()


# ---- reading ----------------------------------------------------------------------------------

def _kc(table: str, row: dict) -> str:
    alt = ALT_KEY.get(table)
    col = GRAPH[table][0]
    return alt if alt and row.get(col) is None else col


def _kv(table: str, row: dict) -> str | None:
    v = row.get(_kc(table, row))
    return None if v is None else str(v)


def _children(table: str, reviewed_too: bool = False) -> list[tuple[str, str]]:
    return [(child, fk) for child, (_, rev, parents) in GRAPH.items()
            for fk, p in parents if p == table and (reviewed_too or not rev)]


class _Tables:
    """Whole-table reads of one schema, indexed on demand (one request's worth)."""

    def __init__(self, cur, schema: str):
        self.cur, self.schema, self.rows, self.idx = cur, schema, {}, {}

    def all(self, table: str) -> list[dict[str, Any]]:
        if table not in self.rows:
            self.cur.execute(sql.SQL("SELECT * FROM {}.{}").format(sql.Identifier(self.schema), sql.Identifier(table)))
            self.rows[table] = [dict(r) for r in self.cur.fetchall()]
        return self.rows[table]

    def by(self, table: str, col: str, value: Any) -> list[dict[str, Any]]:
        if (table, col) not in self.idx:
            ix: dict[str, list] = {}
            for r in self.all(table):
                ix.setdefault(str(r.get(col)), []).append(r)
            self.idx[(table, col)] = ix
        return self.idx[(table, col)].get(str(value), []) if value is not None else []

    def card(self, table: str, key: Any) -> dict | None:
        if ("card", table) not in self.idx:
            self.idx[("card", table)] = {}
            for r in self.all(table):
                self.idx[("card", table)].setdefault(_kv(table, r), r)
        return self.idx[("card", table)].get(str(key))


# A bundle entry is (table, row, link): link = None for the card row, else (fk column, parent key).
def _bundle(t: _Tables, table: str, row: dict, reviewed_too: bool = False,
            link: tuple[str, str] | None = None, seen: set | None = None) -> list[tuple[str, dict, tuple | None]]:
    seen = set() if seen is None else seen
    if id(row) in seen:  # reached twice through different parents (unpublish cascades)
        return []
    seen.add(id(row))
    out = [(table, row, link)]
    pk = _kv(table, row)
    for child, fk in _children(table, reviewed_too):
        for r in t.by(child, fk, pk):
            out += _bundle(t, child, r, reviewed_too, (fk, pk), seen)
    return out


def _clean(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in VOLATILE}


def _signature(bundle: list) -> str:
    items = sorted(json.dumps([tb, _clean(r)], sort_keys=True, default=str) for tb, r, *_ in bundle)
    return hashlib.md5("\n".join(items).encode()).hexdigest()


def statuses(st_cur, sv_cur) -> dict[str, Any]:
    """{"cards": {table: {key: {"s": new|changed|live|rejected, "live": bool}}},
        "tables": {"ui"|"serving": {table: {"s": new|changed|live, "n": staged rows, "live_n": live rows}}}}"""
    S, V = _Tables(st_cur, "staging"), _Tables(sv_cur, "serving")
    rejected = {(r["table_name"], r["row_key"]): r["signature"] for r in S.all("review_decision")}
    cards: dict[str, dict[str, dict[str, Any]]] = {}
    for table, (_, reviewed, _p) in GRAPH.items():
        if not reviewed:
            continue
        for row in S.all(table):
            key = _kv(table, row)
            sig = _signature(_bundle(S, table, row))
            live = V.card(table, key)
            live_sig = _signature(_bundle(V, table, live)) if live else None
            if sig == live_sig:
                s = "live"
            elif rejected.get((table, key)) == sig:
                s = "rejected"
            else:
                s = "changed" if live else "new"
            cards.setdefault(table, {})[str(key)] = {"s": s, "live": live is not None}
    tables: dict[str, dict[str, dict[str, Any]]] = {"ui": {}, "serving": {}}
    for schema, name in setup_tables(st_cur):
        sr, lr = _Tables(st_cur, STAGING[schema]).all(name), _Tables(sv_cur, LIVE[schema]).all(name)
        same = _table_sig(sr) == _table_sig(lr)
        tables[schema][name] = {"s": "live" if same else ("changed" if lr else "new"), "n": len(sr), "live_n": len(lr)}
    return {"cards": cards, "tables": tables}


def _table_sig(rows: list[dict]) -> str:
    return hashlib.md5("\n".join(sorted(json.dumps(_clean(r), sort_keys=True, default=str) for r in rows)).encode()).hexdigest()


def setup_tables(st_cur) -> list[tuple[str, str]]:
    """[(schema 'ui'|'serving', table)]: every ui table (as listed in staging_ui) + SERVING_TABLES."""
    st_cur.execute("""SELECT table_name FROM information_schema.tables
                      WHERE table_schema = 'staging_ui' AND table_type = 'BASE TABLE' ORDER BY 1""")
    return [("ui", r["table_name"]) for r in st_cur.fetchall()] + [("serving", t) for t in SERVING_TABLES]


# ---- writing to the serving DB ----------------------------------------------------------------

def _check(table: str) -> None:
    if GRAPH.get(table, (None, False))[1] is not True:
        raise ValueError(f"{table} is not a reviewed table")


def _noun(table: str) -> str:
    """The reviewed card a table belongs to, in words ('competitive_competitor' -> 'competitor')."""
    while not GRAPH[table][1] and GRAPH[table][2]:
        table = GRAPH[table][2][0][1]
    return table.replace("competitive_", "").replace("_", " ")


def _row_ids(bundle: list) -> dict[str, set[str]]:
    # fact_source.row_id holds whichever id the loader used for the row: match its id columns
    ids: dict[str, set[str]] = {}
    for tb, r, *_ in bundle:
        for col, v in r.items():
            if v is not None and (col.endswith("_id") or col == GRAPH[tb][0]):
                ids.setdefault(tb, set()).add(str(v))
    return ids


def _delete_specs(bundle: list) -> list[tuple[str, str, str]]:
    """(table, column, value) deletes for a bundle: the card by its key, children by their link."""
    specs: list[tuple[str, str, str]] = []
    for tb, r, link in bundle:
        spec = (tb, *(link if link else (_kc(tb, r), _kv(tb, r))))
        if spec not in specs:
            specs.append(spec)
    return specs


def _live_write(cur) -> None:
    """The live tables refuse writes unless this is set (db/setup/04_serving_db.sql)."""
    cur.execute("SET LOCAL kssl.approve = 'on'")


def _remove(cur, bundle: list) -> None:
    for tb, col, val in _delete_specs(bundle):
        cur.execute(sql.SQL("DELETE FROM serving.{} WHERE {}::text = %s").format(sql.Identifier(tb), sql.Identifier(col)), (val,))
    for tb, ids in _row_ids(bundle).items():
        cur.execute("DELETE FROM serving.fact_source WHERE table_name = %s AND row_id = ANY(%s)", (tb, list(ids)))


def _insert(cur, schema: str, table: str, rows: list[dict]) -> None:
    """Explicit column list in the serving table's order; json / jsonb values need Json()."""
    if not rows:
        return
    cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                   WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position""", (schema, table))
    cols = [(r["column_name"], r["data_type"]) for r in cur.fetchall()]
    if not cols:
        raise ValueError(f"{schema}.{table} does not exist in the serving database")
    data = [tuple(psycopg2.extras.Json(r[c]) if t in ("json", "jsonb") and r.get(c) is not None else r.get(c) for c, t in cols)
            for r in rows]
    psycopg2.extras.execute_values(
        cur, sql.SQL("INSERT INTO {}.{} ({}) VALUES %s").format(
            sql.Identifier(schema), sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(c) for c, _ in cols)).as_string(cur),
        data)


def approve(st, sv, table: str, key: str) -> None:
    """Copy the staging version of a card (bundle + fact_source) over the live one."""
    _check(table)
    S, V = _Tables(st, "staging"), _Tables(sv, "serving")
    row = S.card(table, key)
    if row is None:
        raise ValueError(f"{table} {key} is not in staging")
    for fk, parent in GRAPH[table][2]:
        if row.get(fk) is not None and V.card(parent, row[fk]) is None:
            raise ValueError(f"Approve its {_noun(parent)} first ({parent} {row[fk]} is not live)")
    new = _bundle(S, table, row)
    live = V.card(table, key)
    old = _bundle(V, table, live) if live else []
    _live_write(sv)
    _remove(sv, old + new)
    by_table: dict[str, list[dict]] = {}
    for tb, r, _ in new:
        by_table.setdefault(tb, []).append(r)
    for tb, rows in by_table.items():
        _insert(sv, "serving", tb, rows)
    for tb, ids in _row_ids(new).items():
        st.execute("SELECT * FROM staging.fact_source WHERE table_name = %s AND row_id = ANY(%s)", (tb, list(ids)))
        _insert(sv, "serving", "fact_source", [dict(r) for r in st.fetchall()])
    st.execute("DELETE FROM staging.review_decision WHERE table_name = %s AND row_key = %s", (table, key))


def reject(st, sv, table: str, key: str) -> None:
    """Keep this version out of serving. A later, different version shows as pending again."""
    _check(table)
    S = _Tables(st, "staging")
    row = S.card(table, key)
    if row is None:
        raise ValueError(f"{table} {key} is not in staging")
    st.execute(
        """INSERT INTO staging.review_decision (table_name, row_key, status, signature) VALUES (%s, %s, 'rejected', %s)
           ON CONFLICT (table_name, row_key) DO UPDATE SET signature = EXCLUDED.signature, decided_at = now()""",
        (table, key, _signature(_bundle(S, table, row))))


def undo_reject(st, sv, table: str, key: str) -> None:
    _check(table)
    st.execute("DELETE FROM staging.review_decision WHERE table_name = %s AND row_key = %s", (table, key))


def unpublish(st, sv, table: str, key: str) -> None:
    """Take a card off the live UI with everything under it (a competitor takes its products...)."""
    _check(table)
    V = _Tables(sv, "serving")
    row = V.card(table, key)
    if row is not None:
        _live_write(sv)
        _remove(sv, _bundle(V, table, row, reviewed_too=True))


ACTIONS = {"approve": approve, "reject": reject, "undo": undo_reject, "unpublish": unpublish}


def _check_setup(st, schema: str, name: str) -> None:
    if (schema, name) not in setup_tables(st):
        raise ValueError(f"{schema}.{name} is not a setup table")


def approve_table(st, sv, schema: str, name: str) -> None:
    """Replace the whole live table with the staging table."""
    _check_setup(st, schema, name)
    rows = _Tables(st, STAGING[schema]).all(name)
    _live_write(sv)
    sv.execute(sql.SQL("DELETE FROM {}.{}").format(sql.Identifier(LIVE[schema]), sql.Identifier(name)))
    _insert(sv, LIVE[schema], name, rows)


def unpublish_table(st, sv, schema: str, name: str) -> None:
    _check_setup(st, schema, name)
    _live_write(sv)
    sv.execute(sql.SQL("DELETE FROM {}.{}").format(sql.Identifier(LIVE[schema]), sql.Identifier(name)))


TABLE_ACTIONS = {"approve": approve_table, "unpublish": unpublish_table}


# ---- trace ------------------------------------------------------------------------------------

def _sources(st, table: str, row: dict[str, Any]) -> list[dict[str, Any]]:
    ids = list(_row_ids([(table, row)]).get(table, set()))
    st.execute("""SELECT column_name, source_url, source_tier, publisher, quote, document_id FROM staging.fact_source
                  WHERE table_name = %s AND row_id = ANY(%s) ORDER BY column_name""", (table, ids))
    return [dict(r) for r in st.fetchall()]


def _diff(row: dict, live: dict | None) -> dict[str, Any] | None:
    """Columns whose live value differs: {col: live value}. None = the row is not live."""
    if live is None:
        return None
    return {k: live.get(k) for k in row if k not in VOLATILE and str(live.get(k)) != str(row.get(k))}


def _lit(v) -> str:
    """A value quoted for the DISPLAYED sql (operators paste it into DBeaver); the queries themselves are parameterised."""
    return str(v).replace("'", "''")


def _ident(table: str, row: dict) -> str:
    return _kv(table, row) or json.dumps(_clean(row), sort_keys=True, default=str)


def trace(st, sv, table: str, key: str) -> dict[str, Any]:
    """Where a card's data lives: staging rows, per-field sources, live differences, live rows that
    Approve would remove, the parent cards, and the child tables (a tree)."""
    if table not in GRAPH:
        raise ValueError(f"{table} is not a known table")
    S, V = _Tables(st, "staging"), _Tables(sv, "serving")
    parents = GRAPH[table][2]

    def node(tb: str, srows: list, vrows: list, where: str, depth: int) -> dict[str, Any]:
        live_by = {}
        for r in vrows:
            live_by.setdefault(_ident(tb, r), r)
        rows = [{"row": r, "sources": _sources(st, tb, r),
                 "live": _diff(r, live_by.get(_ident(tb, r)))} for r in srows]
        staged = {_ident(tb, r) for r in srows}
        n = {"table": f"staging.{tb}", "live_table": f"serving.{tb}", "key_column": GRAPH[tb][0],
             "sql": f"SELECT * FROM staging.{tb} WHERE {where};", "rows": rows,
             "removed": [r for r in vrows if _ident(tb, r) not in staged], "children": []}
        if depth < 4:
            pks = {_kv(tb, r) for r in srows} | {_kv(tb, r) for r in vrows}
            pks.discard(None)
            for child, fk in _children(tb):
                cs = [r for pk in sorted(pks) for r in S.by(child, fk, pk)]
                cv = [r for pk in sorted(pks) for r in V.by(child, fk, pk)]
                if cs or cv:
                    shown = sorted(pks)[:8]
                    vals = ", ".join(f"'{_lit(p)}'" for p in shown) + (f", ... ({len(pks)} keys)" if len(pks) > 8 else "")
                    n["children"].append(node(child, cs, cv, f"{fk}::text IN ({vals})", depth + 1))
        return n

    srow, vrow = S.card(table, key), V.card(table, key)
    root = node(table, [srow] if srow else [], [vrow] if vrow else [], f"{_kc(table, srow) if srow else GRAPH[table][0]}::text = '{_lit(key)}'", 0)
    root["key"] = key
    root["parents"] = [{"table": f"staging.{p}", "key_column": GRAPH[p][0], "key": str(srow[fk])}
                       for fk, p in parents if srow and srow.get(fk) is not None]
    return root


if __name__ == "__main__":
    # Self-check on in-memory tables, no DB: bundles, signatures, delete specs, ids, diffs, wording.
    class Fake(_Tables):
        def __init__(self, data):
            super().__init__(None, "x")
            self.rows = {t: [] for t in GRAPH} | data

    s = Fake({C: [{"competitor_id": "c1"}],
              "competitive_competitor_location": [{"location_id": "l1", "competitor_id": "c1"},
                                                  {"location_id": "l2", "competitor_id": "c2"}],
              "competitive_product": [{"product_id": "p1", "competitor_id": "c1"}],
              "competitive_product_specification": [{"spec_id": "s1", "product_id": "p1"}],
              "competitive_patent_filing": [{"publication_number": None, "filing_id": "f1", "portfolio_id": "pf"}]})
    root = s.all(C)[0]
    b = _bundle(s, C, root)
    assert [tb for tb, _, _ in b] == [C, "competitive_competitor_location"], b  # products are their own cards
    bu = _bundle(s, C, root, reviewed_too=True)  # unpublish: the whole cascade
    assert [tb for tb, _, _ in bu] == [C, "competitive_competitor_location", "competitive_product",
                                       "competitive_product_specification"], bu
    assert _signature(b) == _signature(list(reversed(b)))
    changed = [(C, {"competitor_id": "c1", "updated_at": "now"}, None), b[1]]
    assert _signature(changed) == _signature(b)  # bookkeeping columns do not count
    assert _signature(b) != _signature(b[:1])
    assert _delete_specs(bu) == [(C, "competitor_id", "c1"), ("competitive_competitor_location", "competitor_id", "c1"),
                                 ("competitive_product", "competitor_id", "c1"),
                                 ("competitive_product_specification", "product_id", "p1")]
    assert _row_ids(b) == {C: {"c1"}, "competitive_competitor_location": {"l1", "c1"}}
    assert s.card("competitive_patent_filing", "f1") is not None  # key column empty -> filing_id
    assert s.card(C, "c1") is root and s.card(C, "nope") is None
    assert _diff({"a": 1, "b": 2}, {"a": 1, "b": 3}) == {"b": 3} and _diff({"a": 1}, None) is None
    assert _table_sig([{"a": 1, "updated_at": 1}, {"a": 2}]) == _table_sig([{"a": 2}, {"a": 1, "updated_at": 2}])
    assert _noun("competitive_patent_portfolio") == "competitor" and _noun("client_product") == "client product"
    assert all(p in GRAPH for _, _, ps in GRAPH.values() for _, p in ps)
    assert all(len(set(fk for fk, _ in ps)) == len(ps) for _, _, ps in GRAPH.values())
    for t, (_, rev, ps) in GRAPH.items():
        assert rev or ps, f"{t}: a non-reviewed table needs a parent"
    print("review self-check ok")
