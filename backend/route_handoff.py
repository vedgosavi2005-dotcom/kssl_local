"""Route hand-off (owner 2026-10-24, routing gap part b): when the signal lane has read an article, the other pillars it touches get it too.

    python -m backend.route_handoff [--dry-run]     (code only, no model; a routine step right after the signal prompt)
    python -m backend.route_handoff --selftest

Triage routes a page from its opening only. The signal prompt reads the whole article and stores what it found: the story's kind
(order, delivery, trial, partnership, technology, demand, ...), its country, and the card's 7 impact scores. From those stored facts
this step adds the routes the article supports to source_document.triage->'route' (never removes one), so the tech, partnership,
project, geo and opportunity lanes read it on their next run. Each addition is noted in the pipeline log with the signal it came from.
"""
from __future__ import annotations

import argparse

from backend import ops_log

# story kind -> routes the article then supports (prompts/signal.yml story_kind)
KIND_ROUTES = {
    "order": ["project", "geo"], "delivery": ["project", "geo"], "programme": ["project"], "trial": ["project", "tech"],
    "partnership": ["partnership", "geo"], "capacity": ["geo"], "technology": ["tech"], "demand": ["opportunity", "project"],
    "policy": [],
}
SCORE_ROUTES = {"impact_technology_gap": "tech", "impact_partnerships": "partnership"}   # a stored impact score >= 3 on that dimension
SCORE_MIN = 3


def routes_for(kind: str | None, country: str | None, scores: dict) -> list[str]:
    """the routes one signal's stored facts support; geo only when the story names a country"""
    out = [r for r in KIND_ROUTES.get(kind or "", []) if r != "geo" or country]
    out += [r for col, r in SCORE_ROUTES.items() if (scores.get(col) or 0) >= SCORE_MIN]
    return list(dict.fromkeys(out))


SQL = """SELECT d.doc_id::text AS doc_id, d.url, coalesce(d.triage->'route', '[]'::jsonb) AS route, s.signal_id::text AS signal_id,
                st.kind, st.country_code, s.impact_technology_gap, s.impact_partnerships
         FROM staging.competitive_signal s
         JOIN staging.competitive_signal_detail sd USING (signal_id)
         JOIN staging.source_document d ON d.url = sd.source_url
         LEFT JOIN staging.story st ON st.story_id = s.story_id"""


def run(dry_run: bool = False) -> dict:
    import psycopg2.extras
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute(SQL)
    found = cur.fetchall()
    conn.rollback()
    add: dict[str, dict] = {}                     # doc -> {"route": current, "new": {route: signal}, "url": ...}
    for r in found:
        have = set(r["route"] or [])
        for route in routes_for(r["kind"], r["country_code"], r):
            if route not in have:
                d = add.setdefault(r["doc_id"], {"route": list(r["route"] or []), "new": {}, "url": r["url"]})
                d["new"].setdefault(route, r["signal_id"])
    stats = {"docs": len(add), "routes_added": sum(len(d["new"]) for d in add.values())}
    for k in ("tech", "partnership", "project", "geo", "opportunity"):
        stats[k] = sum(k in d["new"] for d in add.values())
    if not dry_run and add:
        rows = []
        for doc, d in add.items():
            route = [x for x in d["route"] if x != "none"] + list(d["new"])     # a page a signal read is not 'none'
            rows.append((psycopg2.extras.Json({"route": route, "route_handoff": {k: f"signal {v}" for k, v in d["new"].items()}}), doc))
            ops_log.note("route", "handoff", f"The signal lane read this article in full; added routes {', '.join(d['new'])} "
                         f"(from what signal {next(iter(d['new'].values()))[:8]} stored: its story kind, country and impact scores).",
                         subject=d["url"], tbl="staging.source_document", rec_id=doc, detail={"added": d["new"], "before": d["route"]})
        psycopg2.extras.execute_batch(cur, "UPDATE staging.source_document SET triage = coalesce(triage, '{}'::jsonb) || %s WHERE doc_id = %s::uuid",
                                      rows, page_size=200)
        conn.commit()
    conn.close()
    print(stats)
    return stats


def _selftest() -> None:
    assert routes_for("order", "IN", {}) == ["project", "geo"]
    assert routes_for("order", None, {}) == ["project"], "geo only with a country"
    assert routes_for("partnership", "FR", {"impact_technology_gap": 4}) == ["partnership", "geo", "tech"]
    assert routes_for(None, None, {"impact_partnerships": 3, "impact_technology_gap": 2}) == ["partnership"]
    assert routes_for("policy", "US", {}) == []
    print("route_handoff self-check ok")


@ops_log.logged("backend.route_handoff")
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        return 0
    run(a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
