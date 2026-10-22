"""Read side of the pipeline log (review site only): runs, a run's steps, a step's records, and one record's journey from
harvest to the live site. The live log is ops.run / ops.step / ops.record_event / ops.note (33_pipeline_log.sql, written by
backend/ops_log.py); history before it is RECONSTRUCTED from the timestamps the tables keep (ops.step_history,
34_pipeline_history.sql), one step per stage per day, flagged reconstructed. Every function takes RealDictCursors:
st = staging DB, sv = serving DB. Served by /api/review/pipeline/* (backend/app.py).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from psycopg2 import sql

from backend import review

TITLE_COLS = ("title", "headline", "name", "product_name", "display_name", "partner_name", "project_name", "spec_name",
              "one_line", "item", "client_name", "legal_name")
SEARCH_TABLES = ("competitive_signal", "competitive_news_article", "market_tender", "competitive_partnership", "competitive_project",
                 "competitive_product", "technology_overview_article", "technology_innovation", "client_product", "competitive_competitor",
                 "market_global_requirement")
LIMIT = 300


def _uuid(v: str) -> str | None:
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, TypeError):
        return None


def runs(st, limit: int = 90) -> list[dict]:
    """Live runs (ops.run) and, for steps outside a run (all reconstructed history), one pseudo-run per day ('day:YYYY-MM-DD')."""
    st.execute("""
        SELECT * FROM (
          SELECT r.run_id::text AS id, r.kind, r.started_at, r.ended_at, r.status, r.cost_usd,
                 (SELECT count(*) FROM ops.step s WHERE s.run_id = r.run_id) AS steps, false AS reconstructed, r.notes
          FROM ops.run r
          UNION ALL
          SELECT 'day:' || h.started_at::date, CASE WHEN bool_and(h.reconstructed) THEN 'reconstructed' ELSE 'day' END,
                 min(h.started_at), max(h.ended_at),
                 CASE WHEN bool_or(h.status = 'failed') THEN 'partial' ELSE 'ok' END, sum(h.cost_usd), count(*), bool_and(h.reconstructed), NULL
          FROM ops.step_history h WHERE h.run_id IS NULL AND h.started_at IS NOT NULL GROUP BY h.started_at::date
        ) t ORDER BY started_at DESC NULLS LAST LIMIT %s""", (limit,))
    return st.fetchall()


def steps(st, run_id: str) -> list[dict]:
    if run_id.startswith("day:"):
        st.execute("SELECT * FROM ops.step_history WHERE run_id IS NULL AND started_at::date = %s::date ORDER BY started_at",
                   (run_id[4:],))
    else:
        if not _uuid(run_id):
            raise ValueError("run is a uuid or day:YYYY-MM-DD")
        st.execute("SELECT * FROM ops.step_history WHERE run_id = %s ORDER BY started_at", (run_id,))
    return st.fetchall()


def step_records(st, step_id: str) -> dict:
    """What one step touched. A live step: its record events and notes. A reconstructed step: the rows behind it."""
    if _uuid(step_id):
        st.execute("SELECT at, tbl, rec_id, action, detail FROM ops.record_event WHERE step_id = %s ORDER BY at LIMIT %s", (step_id, LIMIT))
        events = st.fetchall()
        st.execute("SELECT at, kind, outcome, subject, tbl, rec_id, message, detail FROM ops.note WHERE step_id = %s ORDER BY at LIMIT %s",
                   (step_id, LIMIT))
        return {"kind": "live", "records": events, "notes": st.fetchall()}
    kind, _, rest = step_id.partition(":")
    key, _, day = rest.rpartition(":") if kind in ("harvest", "tenders", "prompt") else ("", "", rest)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""):
        raise ValueError("unknown step id")
    q = {
        "prompt": ("""SELECT started_at AS at, run_id::text, subject_key, status, coalesce(skip_reason, left(error, 200)) AS note, rows_loaded,
                             cost_usd, seconds, (SELECT jsonb_agg(l) FROM jsonb_array_elements(coalesce(loaded, '[]'::jsonb)) l
                                                 WHERE (l->>'card')::boolean) AS cards
                      FROM staging.prompt_run WHERE prompt_id = %s AND started_at::date = %s::date ORDER BY started_at""", (key, day)),
        "harvest": ("""SELECT fetched_at AS at, doc_id::text, url, title, status, source_kind, triage->'route' AS route
                       FROM staging.source_document WHERE coalesce(triage->>'harvester', source_kind) = %s AND fetched_at::date = %s::date
                       ORDER BY fetched_at""", (key, day)),
        "tenders": ("""SELECT fetched_at AS at, notice_id, notice_url AS url, title, country, status, tender_id::text
                       FROM staging.tender_raw WHERE coalesce(source_api, '?') = %s AND fetched_at::date = %s::date ORDER BY fetched_at""", (key, day)),
        "triage": ("""SELECT (triage->>'route_at')::timestamptz AS at, doc_id::text, url, title, triage->'route' AS route, triage->>'route_reason' AS reason
                      FROM staging.source_document WHERE triage ? 'route_at' AND (triage->>'route_at')::date = %s::date ORDER BY 1""", (day,)),
        "news_candidates": ("""SELECT found_at AS at, article_url AS url, headline AS title, status, story_table, story_id::text
                               FROM staging.news_candidate WHERE found_at::date = %s::date ORDER BY found_at""", (day,)),
        "images": ("SELECT fetched_at AS at, source_url AS url, byte_len, width, height FROM media.image WHERE fetched_at::date = %s::date ORDER BY 1", (day,)),
        "translate": ("""SELECT translated_at AS at, table_name AS tbl, row_id AS rec_id, column_name, lang, left(original, 160) AS original
                         FROM staging.text_original WHERE translated_at::date = %s::date ORDER BY 1""", (day,)),
        "review": ("SELECT decided_at AS at, table_name AS tbl, row_key AS rec_id, status FROM staging.review_decision WHERE decided_at::date = %s::date ORDER BY 1", (day,)),
    }.get(kind)
    if not q:
        raise ValueError("unknown step id")
    st.execute(q[0] + " LIMIT %s", (*q[1], LIMIT))
    return {"kind": kind, "records": st.fetchall(), "notes": []}


def _key_col(table: str) -> str:
    review._check(table)
    return review.GRAPH[table][0]


def _cols(cur, schema: str, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s", (schema, table))
    return {r["column_name"] for r in cur.fetchall()}


def _title(row: dict | None) -> str | None:
    for c in TITLE_COLS:
        if row and row.get(c):
            return str(row[c])[:200]
    return None


def journey(st, sv, table: str, rec_id: str) -> dict:
    """One record from harvest to the live site, in time order: the documents it came from (harvested, triaged, processed by
    which prompts), the prompt run that wrote it, its sources, translation, live log events, review decision -- and whether it
    is in serving now. Each event: {at, stage, what, detail}."""
    key = _key_col(table)
    ident = sql.SQL("{}.{}").format(sql.Identifier("staging"), sql.Identifier(table))
    st.execute(sql.SQL("SELECT * FROM {} WHERE {}::text = %s").format(ident, sql.Identifier(key)), (rec_id,))
    row = st.fetchone()
    sv.execute(sql.SQL("SELECT 1 FROM {}.{} WHERE {}::text = %s").format(sql.Identifier("serving"), sql.Identifier(table), sql.Identifier(key)),
               (rec_id,))
    live = bool(sv.fetchone())
    ev: list[dict] = []

    st.execute("""SELECT created_at, column_name, source_url, source_tier, publisher, document_id FROM staging.fact_source
                  WHERE table_name = %s AND row_id = %s ORDER BY created_at""", (table, rec_id))
    facts = st.fetchall()
    grouped: dict = {}
    for f in facts:                                    # one event per write and source, not one per column
        g = grouped.setdefault((f["created_at"], f["source_url"]), {"f": f, "cols": []})
        g["cols"].append(f["column_name"])
    for (at, url), g in grouped.items():
        f, cols = g["f"], g["cols"]
        ev.append({"at": at, "stage": "source", "what": f"source recorded ({len(cols)} field{'s' if len(cols) != 1 else ''})",
                   "detail": {"url": url, "tier": f["source_tier"], "publisher": f["publisher"], "fields": cols}})
    urls = {f["source_url"] for f in facts if (f["source_url"] or "").startswith("http")}
    docs = sorted({f["document_id"] for f in facts if f["document_id"]})
    st.execute("""SELECT run_id::text, prompt_id, model, started_at, status, cost_usd, subject_key, rows_loaded FROM staging.prompt_run
                  WHERE loaded @> %s::jsonb ORDER BY started_at""", (f'[{{"table": "{table}", "id": "{rec_id}"}}]',))
    runs_ = st.fetchall()
    # a prompt's subject is often the news article it read: follow it back to that article's url
    subj = sorted({r["subject_key"] for r in runs_ if _uuid(r["subject_key"] or "")})
    if subj:
        st.execute("SELECT article_url FROM staging.competitive_news_article WHERE article_id::text = ANY(%s) AND article_url LIKE 'http%%'", (subj,))
        urls |= {r["article_url"] for r in st.fetchall()}
    if urls:
        st.execute("""SELECT found_at, decided_at, status, article_url, headline, match_via FROM staging.news_candidate
                      WHERE article_url = ANY(%s) ORDER BY found_at""", (sorted(urls),))
        for n in st.fetchall():
            ev.append({"at": n["found_at"], "stage": "harvest", "what": "news article found (news search)",
                       "detail": {"url": n["article_url"], "title": n["headline"], "via": n["match_via"]}})
            if n["decided_at"]:
                ev.append({"at": n["decided_at"], "stage": "triage", "what": f"news candidate {n['status']}", "detail": {"url": n["article_url"]}})
    urls = sorted(urls)
    if urls or docs:
        st.execute("""SELECT doc_id::text, url, title, source_kind, fetched_at, triage, processed_by FROM staging.source_document
                      WHERE url = ANY(%s) OR doc_id::text = ANY(%s)""", (urls, docs))
        for d in st.fetchall():
            tri = d["triage"] or {}
            ev.append({"at": d["fetched_at"], "stage": "harvest", "what": f"document fetched ({tri.get('harvester') or d['source_kind']})",
                       "detail": {"url": d["url"], "title": d["title"], "doc_id": d["doc_id"]}})
            if tri.get("route_at"):
                ev.append({"at": tri["route_at"], "stage": "triage", "what": "routed to " + ", ".join(tri.get("route") or []),
                           "detail": {"reason": tri.get("route_reason"), "model": tri.get("route_model"), "doc_id": d["doc_id"]}})
            for prompt, at in (d["processed_by"] or {}).items():
                ev.append({"at": at, "stage": "prompt", "what": f"document read by prompt '{prompt}'", "detail": {"doc_id": d["doc_id"]}})
    for r in runs_:
        ev.append({"at": r["started_at"], "stage": "prompt", "what": f"written by prompt '{r['prompt_id']}' ({r['status']})",
                   "detail": {"run_id": r["run_id"], "model": r["model"], "cost_usd": r["cost_usd"], "subject": r["subject_key"]}})
    st.execute("SELECT translated_at, column_name, lang FROM staging.text_original WHERE table_name = %s AND row_id = %s", (table, rec_id))
    for t in st.fetchall():
        ev.append({"at": t["translated_at"], "stage": "translate", "what": f"{t['column_name']} translated from {t['lang']}", "detail": {}})
    st.execute("SELECT at, action, detail, step_id::text FROM ops.record_event WHERE tbl = %s AND rec_id = %s ORDER BY at",
               (f"staging.{table}", rec_id))
    for e in st.fetchall():
        ev.append({"at": e["at"], "stage": "log", "what": e["action"], "detail": {**(e["detail"] or {}), "step_id": e["step_id"]}})
    st.execute("""SELECT at, script, kind, outcome, message, subject FROM ops.note
                  WHERE (tbl IN (%s, %s) AND rec_id = %s) OR subject = ANY(%s) ORDER BY at""", (f"staging.{table}", table, rec_id, urls))
    noted = set()
    for x in st.fetchall():
        noted.add((x["kind"], x["subject"]))
        ev.append({"at": x["at"], "stage": "note", "what": x["message"] or x["outcome"] or x["kind"],
                   "detail": {"script": x["script"], "kind": x["kind"], "outcome": x["outcome"], "url": x["subject"] if str(x["subject"] or "").startswith("http") else None}})
    if urls:   # image decisions made before the live notes existed: the same sentence, rebuilt from media.page_image
        from backend.media_images import image_note
        st.execute("""SELECT p.page_url, p.status, p.how, p.error, p.checked_at, i.width, i.height FROM media.page_image p
                      LEFT JOIN media.image i USING (image_id) WHERE p.page_url = ANY(%s)""", (urls,))
        for p in st.fetchall():
            if ("image", p["page_url"]) in noted:
                continue
            size = (p["width"], p["height"]) if p["width"] else None
            ev.append({"at": p["checked_at"], "stage": "note", "what": image_note(p["status"], p["how"], size, None, p["error"], []),
                       "detail": {"kind": "image", "url": p["page_url"], "reconstructed": True}})
    st.execute("SELECT decided_at, status FROM staging.review_decision WHERE table_name = %s AND row_key = %s", (table, rec_id))
    for d in st.fetchall():
        ev.append({"at": d["decided_at"], "stage": "review", "what": f"review: {d['status']}", "detail": {}})
    ev.sort(key=lambda e: str(e["at"] or ""))
    parents = []
    for fk, parent in review.GRAPH[table][2]:
        if row and row.get(fk) is not None:
            parents.append({"tbl": parent, "id": str(row[fk])})
    return {"tbl": table, "id": rec_id, "title": _title(row), "in_staging": row is not None, "in_serving": live,
            "events": ev, "parents": parents}


def search(st, q: str) -> list[dict]:
    """Find records by 'table:id', by a document url (the records it fed), or by title text in the main card tables."""
    q = (q or "").strip()
    if not q:
        return []
    m = re.fullmatch(r"([a-z_]+):(\S+)", q)
    if m and m.group(1) in review.GRAPH:
        return [{"tbl": m.group(1), "id": m.group(2), "title": None, "via": "id"}]
    out: list[dict] = []
    if q.startswith("http"):
        st.execute("""SELECT DISTINCT table_name AS tbl, row_id AS id FROM staging.fact_source WHERE source_url = %s LIMIT 60""", (q,))
        out += [{**r, "title": None, "via": "source url"} for r in st.fetchall() if r["tbl"] in review.GRAPH]
        return out
    like = f"%{q}%"
    for t in SEARCH_TABLES:
        if t not in review.GRAPH:
            continue
        col = next((c for c in TITLE_COLS if c in _cols(st, "staging", t)), None)
        if not col:
            continue
        st.execute(sql.SQL("SELECT {}::text AS id, {} AS title FROM {}.{} WHERE {} ILIKE %s LIMIT 6").format(
            sql.Identifier(review.GRAPH[t][0]), sql.Identifier(col), sql.Identifier("staging"), sql.Identifier(t), sql.Identifier(col)), (like,))
        out += [{"tbl": t, **r, "via": col} for r in st.fetchall()]
    return out[:60]
