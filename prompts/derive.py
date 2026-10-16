"""Derive hooks: deterministic loader steps that run after a prompt's rows are inserted (inside the
same transaction). A prompt file names them under `derive:`. No AI, no judgement beyond the fixed
rules written here (docs/audit_v2/ANSWERS.md section 1 and the comments of the prompt files).

    @hook("name") def f(cur, ctx): ...
    ctx = {prompt_id, subject, subject_row, cards: [(table, id)], rows: [(table, id, is_card)],
           transient: {(table, id): {field: value}}, warnings: [], notes: [], today}
"""

from __future__ import annotations

import re
from decimal import Decimal

REGISTRY: dict = {}

# edge_score -> decision_level cut-offs (ANSWERS.md section 1): 1 = client behind, 2 = near parity, 3 = client ahead
BEHIND_BELOW, AHEAD_FROM = 42, 58
SCORE_MIN, SCORE_MAX = 2, 98
DEAD_BAND = 3                       # a comparable gap under this percent is "equal" (the old edge.js dead band)
MIN_LINES_FOR_PERCENT = 3           # fit_percent needs at least this many checked lines
LEAN = {"strong": "go", "partial": "maybe", "weak": "pass"}


def hook(name: str):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco


def run(names: list, cur, ctx: dict) -> None:
    for n in names:
        if n not in REGISTRY:
            raise ValueError(f"unknown derive step '{n}' (have {sorted(REGISTRY)})")
        REGISTRY[n](cur, ctx)


def ids(ctx: dict, table: str) -> list:
    return [i for t, i, *_ in ctx.get("rows", []) if t == table] or [i for t, i in ctx.get("cards", []) if t == table]


# ---- pure rules (self-checked in prompts/loader.py) ------------------------------------------------------

NUMBER_WITH_UNIT = re.compile(r"\s*([-+]?\d+(?:\.\d+)?)\s*[A-Za-z%/°µ ]*\Z")


def to_number(v):
    """A plain number, or a number followed only by its unit ("48 km"); anything else is not a number."""
    if v is None:
        return None
    m = NUMBER_WITH_UNIT.match(str(v))
    return Decimal(m.group(1)) if m else None


def gap_value(client, competitor):
    """abs(c - k) / mean * 100 for a numeric pair; None when either is missing or the mean is 0."""
    if client is None or competitor is None:
        return None
    c, k = Decimal(str(client)), Decimal(str(competitor))
    mean = (c + k) / 2
    return None if mean == 0 else round(abs(c - k) / abs(mean) * 100, 2)


def edge_score(client_wins: int, decided: int):
    """50 + (100 * client_wins / decided - 50) * decided / (decided + 1), rounded, clamped 2..98.
    None when nothing is decided."""
    if decided <= 0:
        return None
    raw = 50 + (100 * client_wins / decided - 50) * decided / (decided + 1)
    return max(SCORE_MIN, min(SCORE_MAX, round(raw)))


def decision_level(score):
    if score is None:
        return None
    return 1 if score < BEHIND_BELOW else (3 if score >= AHEAD_FROM else 2)


def fit_percent(met: int, total: int):
    """round(100 * met / all lines); None under MIN_LINES_FOR_PERCENT lines (1 of 2 is not a meaningful 50%)."""
    return None if total < MIN_LINES_FOR_PERCENT else round(100 * met / total)


def lean_code(fit_grade):
    return LEAN.get((fit_grade or "").lower())


def overlap_status(match_statuses: list) -> str:
    s = {(x or "").lower() for x in match_statuses}
    return "confirmed" if "matched" in s else ("category" if "category_only" in s else "none")


def score_sides(sides: list):
    """[better_side...] of the comparable specs -> (edge_score, decision_level)."""
    decided = [s for s in sides if (s or "").lower() in ("client", "competitor")]
    score = edge_score(sum((s or "").lower() == "client" for s in decided), len(decided))
    return score, decision_level(score)


# ---- hooks --------------------------------------------------------------------------------------------------

@hook("matchup_edge")
def matchup_edge(cur, ctx: dict) -> None:
    """For every competitive_matchup loaded by this run (docs/audit_v2/ANSWERS.md section 1; prompts/matchup.yml):
      gap_value per comparable spec with two numerics; a comparable gap under 3 % makes better_side 'equal' (logged);
      comparable_spec_count = comparable specs; sourced_spec_count = specs with a value on at least one side;
      edge_score over the comparable specs whose better_side is client / competitor; decision_level from it."""
    for mid in ids(ctx, "competitive_matchup"):
        cur.execute("""SELECT comparison_specification_id AS id, spec_label, better_side, comparability_state,
                              client_value_numeric AS cn, competitor_value_numeric AS kn,
                              client_value_text AS ct, competitor_value_text AS kt
                       FROM staging.competitive_matchup_specification WHERE matchup_id::text = %s""", (str(mid),))
        specs = [dict(r) for r in cur.fetchall()]
        for s in specs:
            comparable = (s["comparability_state"] or "").lower() == "comparable"
            gap = gap_value(s["cn"], s["kn"]) if comparable else None
            side = s["better_side"]
            if comparable and gap is not None and gap < DEAD_BAND and (side or "").lower() in ("client", "competitor"):
                ctx["notes"].append(f"matchup_edge: '{s['spec_label']}' gap {gap}% < {DEAD_BAND}%: better_side {side} -> equal")
                side = s["better_side"] = "equal"
            cur.execute("UPDATE staging.competitive_matchup_specification SET gap_value = %s, better_side = %s "
                        "WHERE comparison_specification_id = %s", (gap, side, s["id"]))
        comparable = [s for s in specs if (s["comparability_state"] or "").lower() == "comparable"]
        score, level = score_sides([s["better_side"] for s in comparable])
        sourced = [s for s in specs if any(s[k] not in (None, "") for k in ("cn", "kn", "ct", "kt"))]
        cur.execute("""UPDATE staging.competitive_matchup SET edge_score = %s, decision_level = %s,
                       comparable_spec_count = %s, sourced_spec_count = %s WHERE matchup_id::text = %s""",
                    (score, level, len(comparable), len(sourced), str(mid)))


@hook("geo_match_edge")
def geo_match_edge(cur, ctx: dict) -> None:
    """Geo matches: per-spec gap_value (text), 3 % dead band, and the match's decision_level, by the matchup_edge
    rules. kssl_score, competitor_score and rating_delta stay null."""
    for mid in ids(ctx, "competitive_geo_product_match"):
        cur.execute("""SELECT comparison_spec_id AS id, spec_name, better_side, kssl_value, competitor_value
                       FROM staging.competitive_geo_product_specification WHERE match_id::text = %s""", (str(mid),))
        specs = [dict(r) for r in cur.fetchall()]
        for s in specs:
            c, k = to_number(s["kssl_value"]), to_number(s["competitor_value"])
            gap = gap_value(c, k)
            side = s["better_side"]
            if gap is not None and gap < DEAD_BAND and (side or "").lower() in ("client", "competitor"):
                ctx["notes"].append(f"geo_match_edge: '{s['spec_name']}' gap {gap}% < {DEAD_BAND}%: better_side {side} -> equal")
                side = s["better_side"] = "equal"
            cur.execute("UPDATE staging.competitive_geo_product_specification SET gap_value = %s, better_side = %s "
                        "WHERE comparison_spec_id = %s", (None if gap is None else format(gap, "f"), side, s["id"]))
        _, level = score_sides([s["better_side"] for s in specs])
        cur.execute("UPDATE staging.competitive_geo_product_match SET decision_level = %s WHERE match_id::text = %s", (level, str(mid)))


@hook("geo_rollup")
def geo_rollup(cur, ctx: dict) -> None:
    """Per presence row: overlap_status (confirmed if any match is 'matched', category if any is 'category_only',
    else none; null for the client) and matched_ranges (distinct categories of the matched client products).
    Per location: presence_types (distinct activity_type of all presence rows there) and kssl_presence_summary
    (relationship_text of the client's rows there; null when the client has none)."""
    locations: set = set()
    for pid in ids(ctx, "competitive_geo_company_presence"):
        cur.execute("SELECT company_role, location_id FROM staging.competitive_geo_company_presence WHERE presence_id::text = %s", (str(pid),))
        p = cur.fetchone()
        if p is None:
            continue
        locations.add(p["location_id"])
        if p["company_role"] == "client":
            cur.execute("UPDATE staging.competitive_geo_company_presence SET overlap_status = NULL, matched_ranges = NULL "
                        "WHERE presence_id::text = %s", (str(pid),))
            continue
        cur.execute("""SELECT m.match_status, c.category FROM staging.competitive_geo_product g
                       JOIN staging.competitive_geo_product_match m ON m.geo_product_id = g.geo_product_id
                       LEFT JOIN staging.client_product c ON c.client_product_id = m.kssl_product_id
                       WHERE g.presence_id::text = %s""", (str(pid),))
        ms = cur.fetchall()
        ranges = sorted({r["category"] for r in ms if (r["match_status"] or "").lower() == "matched" and r["category"]})
        cur.execute("UPDATE staging.competitive_geo_company_presence SET overlap_status = %s, matched_ranges = %s WHERE presence_id::text = %s",
                    (overlap_status([r["match_status"] for r in ms]), ", ".join(ranges) or None, str(pid)))
    for loc in locations:
        if loc is None:
            continue
        cur.execute("""SELECT string_agg(DISTINCT activity_type, ', ' ORDER BY activity_type) AS types,
                              (SELECT string_agg(DISTINCT relationship_text, '; ') FROM staging.competitive_geo_company_presence c
                                WHERE c.location_id = p.location_id AND c.company_role = 'client' AND c.relationship_text IS NOT NULL) AS client_text
                       FROM staging.competitive_geo_company_presence p WHERE p.location_id = %s GROUP BY p.location_id""", (loc,))
        r = cur.fetchone()
        cur.execute("UPDATE staging.competitive_geo_location SET presence_types = %s, kssl_presence_summary = %s WHERE location_id = %s",
                    (r["types"] if r else None, r["client_text"] if r else None, loc))


@hook("tender_fit")
def tender_fit(cur, ctx: dict) -> None:
    """fit_percent per product match (met lines / all lines, from the transient `check`); fit_score of the
    assessment = the percent of its best product; fit_rank / kssl_fit_rank / rank_position over all OPEN tenders by
    fit_score desc (nulls last), closing_date asc, tender_id; kssl_fit, kssl_model, lean_code, lean_text copied onto
    the tender. A grade that disagrees with the percent is logged (no change)."""
    tr = ctx.get("transient", {})
    for aid in ids(ctx, "market_tender_fit_assessment"):
        cur.execute("SELECT tender_id, fit_grade, kssl_model, assessment_rationale FROM staging.market_tender_fit_assessment "
                    "WHERE assessment_id::text = %s", (str(aid),))
        a = cur.fetchone()
        if a is None:
            continue
        percents = {}
        for mid in ids(ctx, "market_tender_product_match"):
            cur.execute("SELECT match_label FROM staging.market_tender_product_match WHERE tender_match_id::text = %s AND tender_id = %s",
                        (str(mid), a["tender_id"]))
            m = cur.fetchone()
            if m is None:
                continue
            cur.execute("SELECT match_line_id FROM staging.market_tender_product_match_line WHERE tender_match_id::text = %s", (str(mid),))
            checks = [(tr.get(("market_tender_product_match_line", str(r["match_line_id"]))) or {}).get("check") for r in cur.fetchall()]
            pct = fit_percent(sum(c == "met" for c in checks), len(checks))
            percents[m["match_label"]] = pct
            cur.execute("UPDATE staging.market_tender_product_match SET fit_percent = %s WHERE tender_match_id::text = %s", (pct, str(mid)))
        best = percents.get(a["kssl_model"])
        cur.execute("UPDATE staging.market_tender_fit_assessment SET fit_score = %s WHERE assessment_id::text = %s", (best, str(aid)))
        grade = (a["fit_grade"] or "").lower()
        if (grade == "strong" and best is not None and best < 50) or (grade == "weak" and any(p is not None and p >= 50 for p in percents.values())):
            ctx["warnings"].append(f"tender_fit: grade and percent disagree (tender {a['tender_id']}: {grade}, percents {percents})")
        cur.execute("""UPDATE staging.market_tender SET kssl_fit = %s, kssl_model = %s, lean_text = %s, lean_code = %s
                       WHERE tender_id = %s""", (a["fit_grade"], a["kssl_model"], a["assessment_rationale"], lean_code(a["fit_grade"]), a["tender_id"]))
    cur.execute("""SELECT a.assessment_id, a.tender_id FROM staging.market_tender_fit_assessment a
                   JOIN staging.market_tender t ON t.tender_id = a.tender_id WHERE t.status = 'open'
                   ORDER BY a.fit_score DESC NULLS LAST, t.closing_date ASC NULLS LAST, t.tender_id""")
    for rank, r in enumerate(cur.fetchall(), 1):
        cur.execute("UPDATE staging.market_tender_fit_assessment SET fit_rank = %s, kssl_fit_rank = %s WHERE assessment_id = %s",
                    (rank, rank, r["assessment_id"]))
        cur.execute("UPDATE staging.market_tender SET rank_position = %s WHERE tender_id = %s", (rank, r["tender_id"]))


@hook("renumber_signals")
def renumber_signals(cur, ctx: dict) -> None:
    """competitive_signal.sequence_no = days from 2100-01-01 back to event_date (newer = smaller); the stable
    per-row number the loader already writes (rank_by_event_date_desc). Idempotent: touches only rows that differ."""
    cur.execute("""UPDATE staging.competitive_signal SET sequence_no = (date '2100-01-01' - coalesce(event_date, current_date))
                   WHERE sequence_no IS DISTINCT FROM (date '2100-01-01' - coalesce(event_date, current_date))""")
