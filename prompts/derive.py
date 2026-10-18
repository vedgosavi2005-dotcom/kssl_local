"""Derive hooks: deterministic loader steps that run after a prompt's rows are inserted (inside the
same transaction). A prompt file names them under `derive:`. No AI, no judgement beyond the fixed
rules written here (docs/audit_v2/ANSWERS.md section 1 and the comments of the prompt files).

Foundations (docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md): the label rules below are PURE functions of stored scores, each with a
rule version stored on the row; the hooks apply them. Order in a prompt's `derive:` list matters:
    competitive signal   [signal_label, product_news_merge, story_link]   (+ moment_grade on a moment prompt, award_to_signal on a tender prompt)
    market assessment    [tender_fit, pursue_label]            (+ requirement_state on a global requirement prompt)
    technology article   [tech_direction, story_link]
    any prompt           [filter_options]                       (rebuilds the three filter-option tables from the stored values)
Self-checks: python -m prompts.derive --selftest   (pure)   |   --selftest-db   (hooks, on a throwaway kssl_test_* database).

    @hook("name") def f(cur, ctx): ...
    ctx = {prompt_id, subject, subject_row, cards: [(table, id)], rows: [(table, id, is_card)],
           transient: {(table, id): {field: value}}, warnings: [], notes: [], today}
"""

from __future__ import annotations

import re
from datetime import date
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


# ---- foundations: labels derived from scores (docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md A.1.1, A.2.1, A.3.1, A.0.5) -----------------
# The model scores and states the modifiers; CODE decides the label, so the same scores always give the same label. Each rule has a
# version that is stored on the row it labelled (rule_version), so a rule change can be re-derived without a model call.

RULE_VERSIONS = {"signal": "s2", "pursue": "p1", "tech": "t2"}   # t2 (2026-10-18): tech has threat / watch only, no fav
IMPACT_DIMENSIONS = ("orders_revenue", "market_standing", "supply_chain", "technology_gap", "partnerships", "policy_export", "funding")
DIMENSION_WORD = {"orders_revenue": "Orders", "market_standing": "Market standing", "supply_chain": "Supply chain",
                  "technology_gap": "Technology", "partnerships": "Partnerships", "policy_export": "Policy", "funding": "Funding"}
MARKET_FREE_DIMS = ("supply_chain", "partnerships", "policy_export", "funding")   # the effect does not need a KSSL market
SUBTYPE_FREE_DIMS = ("supply_chain", "partnerships")                     # ... nor a like-for-like product
NEAR_TERM = ("lt_1y", "1_3y")
TECH_RIVAL_CLASSES = ("competitor_advance", "threat_to_position")
PURSUE_LEAN = {"pursue": "go", "position": "maybe", "monitor": "watch", "pass": "pass"}
MOMENT_GRADE = {"threat": "high", "watch": "watch", "fav": "opportunity"}   # ui.competitive_competitor_moment_level codes
REQUIREMENT_STATUS = {"need_stated": "monitored", "approved_funded": "monitored", "rfi": "open", "rfp_tender": "open", "downselect_prototype": "open",
                      "production_award": "closed", "delivered": "closed", "cancelled": "closed"}   # the old three-word status, from the stage
STALE_MONTHS = {"need_stated": 9, "approved_funded": 9, "rfi": 9, "rfp_tender": 3}


def score(v):
    """A whole number 1-5, else None (a bool, text, a fraction or 0 / 6 is not a score; None never counts)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v).strip())
    except Exception:  # noqa: BLE001
        return None
    return int(d) if d == d.to_integral_value() and 1 <= d <= 5 else None


def _word(v):
    return str(v).strip().lower() if v is not None else ""


def impact_max(scores: dict) -> tuple:
    """{dimension: score} -> (impact, dimension, dimension_2). impact = the highest valid score; its dimension is the first one
    (in IMPACT_DIMENSIONS order) holding it; dimension_2 = the next-highest other dimension when it scores 4 or more, else None."""
    valid = [(d, score(scores.get(d))) for d in IMPACT_DIMENSIONS]
    valid = [(d, s) for d, s in valid if s is not None]
    if not valid:
        return None, None, None
    top = max(s for _, s in valid)
    first = next(d for d, s in valid if s == top)
    rest = sorted(((d, s) for d, s in valid if d != first and s >= 4), key=lambda x: (-x[1], IMPACT_DIMENSIONS.index(x[0])))
    return top, first, (rest[0][0] if rest else None)


def effective_time_to_effect(probability, time_to_effect) -> str:
    """A done event (probability 5: contract signed, delivery made, induction completed, unit or plant opened) affects KSSL now, so an
    empty or 'unknown' time to effect becomes lt_1y. A later effect date the source states (1_3y, gt_3y) is kept. Other cases unchanged."""
    t = _word(time_to_effect)
    if score(probability) == 5 and t in ("", "unknown"):
        return "lt_1y"
    return t or "unknown"


def signal_label(probability, impact, time_to_effect, in_client_market, subtype_match, impact_dimension, direction=None) -> str:
    """threat / watch / none for a competitive signal (rule s2, the user's spec 2026-10-18). Any unknown or missing input fails the
    test it feeds.
        none   = a done event (probability 5) with impact 1-2, or a favourable move that is done: it has materialised and is no
                 threat, so it is not a watch either (stored, not shown on the overview)
        threat = direction not favourable and probability >= 4 and impact >= 4 and time_to_effect in (lt_1y, 1_3y)
                 and (in_client_market = yes or dimension in (supply_chain, partnerships, policy_export, funding))
                 and (subtype_match in (same, adjacent) or dimension in (supply_chain, partnerships))
        watch  = everything else: not yet materialised, or materialised with impact 3+ that may still become significant.
    There is no fav label: the spec has threat and watch only (a rival's loss is never a threat)."""
    p, i = score(probability), score(impact)
    dim = _word(impact_dimension)
    time_to_effect = effective_time_to_effect(probability, time_to_effect)
    favourable = _word(direction) == "favourable"
    if p == 5 and (favourable or (i is not None and i <= 2)):
        return "none"
    if (not favourable and p is not None and p >= 4 and i is not None and i >= 4 and _word(time_to_effect) in NEAR_TERM
            and (_word(in_client_market) == "yes" or dim in MARKET_FREE_DIMS)
            and (_word(subtype_match) in ("same", "adjacent") or dim in SUBTYPE_FREE_DIMS)):
        return "threat"
    return "watch"


def glance_impact(impact, dimension):
    """"Orders · high" (impact 4-5 high, 3 medium, 1-2 low); None without an impact."""
    i = score(impact)
    if i is None:
        return None
    word = DIMENSION_WORD.get(_word(dimension))
    level = "high" if i >= 4 else ("medium" if i == 3 else "low")
    return f"{word} · {level}" if word else level.capitalize()


def moment_grade(label):
    return MOMENT_GRADE.get(_word(label))


def horizon_from_maturity(maturity) -> str:
    """No stated horizon: 5 fielded -> lt_2y, 3-4 trials / production -> 2_5y, 1-2 concept / prototype -> gt_5y (A.3.1)."""
    m = score(maturity)
    return "unknown" if m is None else ("lt_2y" if m == 5 else ("2_5y" if m >= 3 else "gt_5y"))


def tech_direction(classification, relevance, maturity) -> str:
    """threat / watch for a technology article (A.3.1; rule t2, the user's spec 2026-10-18: threat and watch only, no fav):
        threat = classification in (competitor_advance, threat_to_position) and relevance >= 4 and maturity >= 3
        watch  = everything else, adoptable included (the feed shows adoptable cards by classification), and a missing score"""
    c, r, m = _word(classification), score(relevance), score(maturity)
    if c in TECH_RIVAL_CLASSES and r is not None and r >= 4 and m is not None and m >= 3:
        return "threat"
    return "watch"


def _round_half_up(x: float) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))


def attractiveness(value_score, strategic_score):
    """round(mean(value_score, strategic_score)) over the scores given (half rounds up); None when neither is given (A.2.1)."""
    s = [x for x in (score(value_score), score(strategic_score)) if x is not None]
    return _round_half_up(sum(s) / len(s)) if s else None


def eligibility_summary(items: list) -> dict:
    """[{state, fixable}] -> {fixable_not_met, hard_bar, all_fixable}. Only a not_met item counts. fixable 'no' is a hard bar;
    'yes' is fixable; 'unknown' counts against the ability (-1) but does not make the item provably fixable."""
    nm = [i for i in items if _word(i.get("state")) == "not_met"]
    hard = any(_word(i.get("fixable")) == "no" for i in nm)
    return {"fixable_not_met": sum(_word(i.get("fixable")) != "no" for i in nm), "hard_bar": hard,
            "all_fixable": all(_word(i.get("fixable")) == "yes" for i in nm)}


def ability(fit_grade, fit_percent=None, fixable_not_met=0, hard_bar=False, strong_rivals=0, incumbent=False, kssl_present=False):
    """Ability to win 1-5 (A.2.1): strong fit -> 5 when fit_percent >= 75 else 4; partial 3; weak 1 (None when the grade is unknown).
    -1 for each not_met item that is fixable, -2 once for a hard bar, floor 1; then -1 when two or more rivals have a strong fit
    and one is the incumbent; +1 when KSSL or a KSSL partner is present in the buyer's country; clamp 1-5."""
    g = _word(fit_grade)
    if g == "strong":
        w = 5 if fit_percent is not None and fit_percent >= 75 else 4
    elif g == "partial":
        w = 3
    elif g == "weak":
        w = 1
    else:
        return None
    w = max(1, w - int(fixable_not_met) - (2 if hard_bar else 0))
    if strong_rivals >= 2 and incumbent:
        w -= 1
    if kssl_present:
        w += 1
    return max(1, min(5, w))


def pursue_label(fit_grade, attractiveness_score, ability_score, all_not_met_fixable=True, hard_bar=False):
    """pursue / position / monitor / pass (A.2.1). None when the fit grade is unknown.
        pass     = weak fit, or any hard bar
        pursue   = A >= 3 and W >= 4
        position = A >= 3 and W == 3, or A >= 4 and W == 2 with every not_met item fixable
        monitor  = everything else (A <= 2, or W <= 2), and a missing score"""
    g = _word(fit_grade)
    if g == "weak" or hard_bar:
        return "pass"
    if g not in ("strong", "partial"):
        return None
    a, w = score(attractiveness_score), score(ability_score)
    if a is None or w is None:
        return "monitor"
    if a >= 3 and w >= 4:
        return "pursue"
    if a >= 3 and w == 3:
        return "position"
    if a >= 4 and w == 2 and all_not_met_fixable:
        return "position"
    return "monitor"


def _months_ago(today, d) -> float:
    return (today.year - d.year) * 12 + (today.month - d.month) + (today.day - d.day) / 31


def requirement_state(stage, last_confirmed, today) -> str:
    """unconfirmed when the newest source date is older than 9 months for a stage up to rfi, 3 months for rfp_tender (or when there is
    no date); every other stage is current (A.2.3)."""
    limit = STALE_MONTHS.get(_word(stage))
    if limit is None:
        return "current"
    if last_confirmed is None:
        return "unconfirmed"
    return "unconfirmed" if _months_ago(today, last_confirmed) > limit else "current"


def award_signal_scores(fit_grade, in_client_market) -> dict:
    """Scores of the signal an award notice creates (A.2.2, no model): probability 5 (done); orders impact 4 when KSSL assessed the
    tender strong or partial, else 3; time to effect lt_1y (the award itself is the effect); subtype 'same' only when KSSL assessed it."""
    assessed = _word(fit_grade) in ("strong", "partial")
    imp = 4 if assessed else 3
    return {"direction": "adverse", "probability": 5, "impact_orders_revenue": imp, "impact": imp, "impact_dimension": "orders_revenue",
            "time_to_effect": "lt_1y", "subtype_match": "same" if assessed else "unknown", "in_client_market": in_client_market}


# ---- filter options (G.1): option lists rebuilt from the distinct stored values ---------------------------------------------------

def option_id(table: str, filter_type: str, code) -> int:
    import hashlib
    return int.from_bytes(hashlib.sha256(f"option|{table}|{filter_type}|{code}".encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def option_rows(table: str, filter_type: str, counts: list, labels: dict | None = None) -> list:
    """counts = [(code, label-or-None, n)]; labels = {code: (label, display_order)} from ui.code_label. Codes with no rows
    are not listed. Order: the code_label order first, then by count (highest first) and code."""
    labels = labels or {}
    seen: dict = {}
    for code, label, n in counts:
        if code is None or str(code).strip() == "" or not n:
            continue
        code = str(code)
        prev = seen.get(code, (label, 0))
        seen[code] = (prev[0] or label, prev[1] + int(n))
    rows = []
    for code, (label, n) in seen.items():
        lab = labels.get(code) or labels.get(code.lower())
        rows.append({"filter_type": filter_type, "option_code": code, "option_label": (lab[0] if lab else None) or label or code,
                     "record_count": n, "_order": (0, lab[1]) if lab and lab[1] is not None else (1, -n), "_code": code})
    rows.sort(key=lambda r: (r["_order"], r["_code"]))
    out = []
    for i, r in enumerate(rows, 1):
        out.append({"option_id": option_id(table, filter_type, r["option_code"]), "filter_type": filter_type, "option_code": r["option_code"],
                    "option_label": r["option_label"], "record_count": r["record_count"], "sort_order": i, "is_active": True})
    return out


# (filter_type, table, column) -> the stored values counted; or (filter_type, None, None, sql) for a custom query returning code[, label], n.
# {S} = the data schema. Filter types follow Fable G.1 / G.3; market keeps 'country' and 'category' because Tenders.jsx reads them.
FILTERS = {
    "competitive": [
        ("classification", "competitive_signal", "classification"), ("category", "competitive_signal", "category"),
        ("impact_dimension", "competitive_signal", "impact_dimension"), ("time_to_effect", "competitive_signal", "time_to_effect"),
        ("subtype_match", "competitive_signal", "subtype_match"), ("in_client_market", "competitive_signal", "in_client_market"),
        ("move", "competitive_signal_detail", "glance_move"),
        ("story_kind", None, None, "SELECT kind AS code, count(*) AS n FROM {S}.story WHERE pillar = 'competitive' GROUP BY 1"),
        ("product_news_type", "competitive_product_news", "news_type"),
        ("sub_type", None, None, """SELECT sub AS code, count(*) AS n FROM (SELECT subcategory AS sub FROM {S}.client_product
                                    UNION ALL SELECT subcategory FROM {S}.competitive_product) x GROUP BY 1"""),
        ("country", None, None, """SELECT l.country_name AS code, l.country_name AS label, count(*) AS n FROM {S}.competitive_geo_company_presence p
                                   JOIN {S}.competitive_geo_location l ON l.location_id = p.location_id GROUP BY 1, 2"""),
        ("region", "competitive_partnership", "region"), ("partner_type", "competitive_partnership", "partner_type"),
        ("partner_status", "competitive_partnership", "status"), ("overlap_kind", "competitive_partnership", "overlap_kind"),
        ("activity", "competitive_geo_company_presence", "activity_type"), ("overlap", "competitive_geo_company_presence", "overlap_status"),
        ("analysis_kind", "competitive_geo_analysis", "kind"), ("stage", "competitive_project", "stage"),
        ("kssl_option", "competitive_project", "kssl_option"), ("patent_category", "competitive_patent_filing", "category_label"),
    ],
    "technology": [
        ("classification", "technology_overview_article", "classification"), ("maturity", "technology_overview_article", "maturity"),
        ("horizon", "technology_overview_article", "horizon"), ("direction", "technology_overview_article", "direction"),
        ("client_position", "technology_overview_article", "client_position"), ("category", "technology_overview_article", "category_text"),
        ("technology_kind", "technology_innovation", "technology_kind"), ("stance", "technology_innovation", "stance"),
        ("innovation_maturity", "technology_innovation", "maturity_level"), ("innovation_client_position", "technology_innovation", "client_position"),
    ],
    "market": [
        ("pursue_label", "market_tender_fit_assessment", "pursue_label"), ("time_to_award", "market_tender_fit_assessment", "time_to_award"),
        ("fit_grade", "market_tender_fit_assessment", "fit_grade"), ("eligibility_state", "market_tender_eligibility", "state"),
        ("move_kind", "market_next_move", "move_kind"), ("stage", "market_global_requirement", "stage"),
        ("status_state", "market_global_requirement", "status_state"), ("tender_status", "market_tender", "status"),
        ("opportunity_stage", "market_opportunity", "stage"),
        ("country", None, None, """SELECT coalesce(country_code, country_name) AS code, country_name AS label, count(*) AS n FROM {S}.market_tender
                                   WHERE country_name IS NOT NULL GROUP BY 1, 2"""),
        ("category", None, None, """SELECT coalesce(t.category_id::text, t.category_text) AS code, coalesce(c.category_name, t.category_text) AS label, count(*) AS n
                                    FROM {S}.market_tender t LEFT JOIN {S}.technology_category c ON c.category_id = t.category_id
                                    WHERE t.category_id IS NOT NULL OR t.category_text IS NOT NULL GROUP BY 1, 2"""),
    ],
}
FILTER_TABLES = {"competitive": ("{U}", "competitive_filter_option"), "technology": ("{U}", "technology_filter_option"),
                 "market": ("{S}", "market_filter_option")}


# ---- hooks: the foundations rules applied to the rows a run wrote ----------------------------------------------------------------

def _row(cur, table: str, key_col: str, key) -> dict | None:
    cur.execute(f"SELECT * FROM staging.{table} WHERE {key_col}::text = %s", (str(key),))
    r = cur.fetchone()
    return dict(r) if r else None


def _client_presence(cur) -> tuple:
    """(lower-case names of the countries where KSSL or a KSSL partner is on record, whether anything is on record at all)."""
    cur.execute("""SELECT lower(l.country_name) AS c FROM staging.competitive_geo_company_presence p
                   JOIN staging.competitive_geo_location l ON l.location_id = p.location_id WHERE p.company_role = 'client'
                   UNION SELECT lower(country) FROM staging.client_partner WHERE country IS NOT NULL""")
    names = {r["c"] for r in cur.fetchall() if r["c"]}
    return names, bool(names)


def _country_names(cur, name=None, code=None) -> set:
    out = {str(name).lower()} if name else set()
    if code or name:
        cur.execute("SELECT lower(country_name) AS n FROM staging.country_reference WHERE lower(iso2) = lower(%s) OR lower(country_name) = lower(%s)",
                    (code or "", name or ""))
        out |= {r["n"] for r in cur.fetchall()}
    return out


def client_market_state(cur, name=None, code=None) -> str:
    """yes / no / unknown for 'is this country a KSSL market': unknown while no KSSL presence or partner is on record (A.0.1)."""
    names, any_on_record = _client_presence(cur)
    if not any_on_record:
        return "unknown"
    return "yes" if _country_names(cur, name, code) & names else "no"


@hook("signal_label")
def signal_label_hook(cur, ctx: dict) -> None:
    """For every competitive_signal this run wrote: impact = the maximum of the six impact_* scores, impact_dimension (+ _2 when
    a second dimension scores 4 or more), classification = signal_label(...) with rule_version, and the detail's glance_impact.
    A signal with no probability and no dimension score (an old-style card) keeps the label the model gave."""
    for sid in ids(ctx, "competitive_signal"):
        r = _row(cur, "competitive_signal", "signal_id", sid)
        if r is None:
            continue
        dims = {d: r.get(f"impact_{d}") for d in IMPACT_DIMENSIONS}
        if r.get("probability") is None and all(v is None for v in dims.values()):
            if not r.get("classification"):                 # no scores and no label from the model: the safe default
                cur.execute("UPDATE staging.competitive_signal SET classification = 'watch', rule_version = %s WHERE signal_id = %s",
                            (RULE_VERSIONS["signal"], r["signal_id"]))
                cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at) VALUES "
                            "('competitive_signal', %s, 'classification', 'judgement', 'judgement', %s, now())",
                            (str(r["signal_id"]), "watch by rule: the card has no probability and no impact score, so it cannot be a threat."))
                ctx["warnings"].append(f"signal_label: {sid} has no scores: labelled watch")
            else:
                ctx["notes"].append(f"signal_label: {sid}: no scores, label left as written ({r.get('classification')})")
            continue
        impact, d1, d2 = impact_max(dims)
        if impact is None:                                  # no dimension scored: keep a stored impact, if any
            impact, d1, d2 = r.get("impact"), r.get("impact_dimension"), r.get("impact_dimension_2")
        tte = effective_time_to_effect(r.get("probability"), r.get("time_to_effect"))
        if tte == "lt_1y" and _word(r.get("time_to_effect")) in ("", "unknown"):
            cur.execute("UPDATE staging.competitive_signal SET time_to_effect = %s WHERE signal_id = %s", (tte, r["signal_id"]))
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_signal' AND row_id = %s AND column_name = 'time_to_effect' AND source_url = 'judgement'",
                        (str(r["signal_id"]),))
            cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at) VALUES "
                        "('competitive_signal', %s, 'time_to_effect', 'judgement', 'judgement', %s, now())",
                        (str(r["signal_id"]), "lt_1y by rule: the event is done (probability 5), so it already affects the market; the article states no later effect date."))
            ctx["notes"].append(f"signal_label: {sid}: time_to_effect {r.get('time_to_effect')!r} -> lt_1y (done event)")
            r["time_to_effect"] = tte
        label = signal_label(r.get("probability"), impact, r.get("time_to_effect"), r.get("in_client_market"), r.get("subtype_match"), d1, r.get("direction"))
        cur.execute("""UPDATE staging.competitive_signal SET impact = %s, impact_dimension = %s, impact_dimension_2 = %s, classification = %s, rule_version = %s
                       WHERE signal_id = %s""", (impact, d1, d2, label, RULE_VERSIONS["signal"], r["signal_id"]))
        cur.execute("UPDATE staging.competitive_signal_detail SET glance_impact = %s WHERE signal_id = %s", (glance_impact(impact, d1), r["signal_id"]))
        ctx["notes"].append(f"signal_label: {sid}: {label} (p={r.get('probability')}, impact={impact} {d1}, {r.get('time_to_effect')}, "
                            f"market={r.get('in_client_market')}, subtype={r.get('subtype_match')}, direction={r.get('direction')})")


def client_name(cur) -> str:
    """client_account.client_name (what the prompts call {{client.name}}); text that names the client is built from it, never typed."""
    cur.execute("SELECT client_name FROM staging.client_account ORDER BY client_id LIMIT 1")
    r = cur.fetchone()
    name = (r["client_name"] if isinstance(r, dict) else r[0]) if r else None
    if not name:
        raise RuntimeError("staging.client_account has no client_name: load the client first")
    return name


def drop_signal(cur, sid) -> None:
    """Delete one competitive_signal with its detail, evidence and their fact_source rows."""
    cur.execute("SELECT evidence_id FROM staging.competitive_signal_evidence WHERE signal_id::text = %s", (str(sid),))
    ev = [str(r["evidence_id"]) for r in cur.fetchall()]
    cur.execute("DELETE FROM staging.fact_source WHERE (table_name IN ('competitive_signal', 'competitive_signal_detail') AND row_id = %s)"
                " OR (table_name = 'competitive_signal_evidence' AND row_id = ANY(%s))", (str(sid), ev))
    for t in ("competitive_signal_evidence", "competitive_signal_detail", "competitive_signal"):
        cur.execute(f"DELETE FROM staging.{t} WHERE signal_id::text = %s", (str(sid),))


@hook("signal_dedupe")
def signal_dedupe(cur, ctx: dict) -> None:
    """One article, one company, one signal: an article queued once per competitor it names can come back twice for the same
    company. A signal of this run whose article already has a signal for the same company (from another subject) is dropped."""
    for sid in ids(ctx, "competitive_signal"):
        cur.execute("""SELECT s2.signal_id FROM staging.competitive_signal s JOIN staging.competitive_signal_detail d ON d.signal_id = s.signal_id
                       JOIN staging.competitive_signal_detail d2 ON d2.source_url = d.source_url AND d2.signal_id <> d.signal_id
                       JOIN staging.competitive_signal s2 ON s2.signal_id = d2.signal_id AND s2.company_id = s.company_id
                       WHERE s.signal_id::text = %s LIMIT 1""", (str(sid),))
        r = cur.fetchone()
        if r:
            drop_signal(cur, sid)
            ctx["notes"].append(f"signal_dedupe: {sid} dropped: its article already has signal {r['signal_id']} for the same company")


@hook("moment_grade")
def moment_grade_hook(cur, ctx: dict) -> None:
    """competitive_competitor_moment.grade from the label of the signal it points to (threat -> high, watch -> watch, fav -> opportunity)."""
    for mid in ids(ctx, "competitive_competitor_moment"):
        cur.execute("SELECT s.classification FROM staging.competitive_competitor_moment m JOIN staging.competitive_signal s ON s.signal_id = m.signal_id "
                    "WHERE m.moment_id::text = %s", (str(mid),))
        r = cur.fetchone()
        grade = moment_grade(r["classification"]) if r else None
        if grade:
            cur.execute("UPDATE staging.competitive_competitor_moment SET grade = %s WHERE moment_id::text = %s", (grade, str(mid)))
        else:
            ctx["warnings"].append(f"moment_grade: moment {mid} has no signal label; grade left empty")


@hook("product_news_merge")
def product_news_merge(cur, ctx: dict) -> None:
    """A competitive_product_news row this run wrote for a product + article url that the news job already attached is NOT kept twice:
    its news_type / event_date / product_variant / kssl_relevance go onto the existing row (the new values win where given), its
    fact_source rows move over, the new row is deleted, and the run's row list points at the existing row (so story_link links that one).
    List it BEFORE story_link."""
    fields = ("news_type", "event_date", "product_variant", "kssl_relevance")
    swap = {}
    for nid in ids(ctx, "competitive_product_news"):
        r = _row(cur, "competitive_product_news", "product_news_id", nid)
        if r is None or not r.get("article_url"):
            continue
        cur.execute("SELECT product_news_id FROM staging.competitive_product_news WHERE product_id = %s AND article_url = %s AND product_news_id::text <> %s "
                    "ORDER BY product_news_id LIMIT 1", (r["product_id"], r["article_url"], str(nid)))
        o = cur.fetchone()
        if o is None:
            continue
        sets = {c: r[c] for c in fields if r.get(c) is not None}
        if sets:
            cur.execute(f"UPDATE staging.competitive_product_news SET {', '.join(c + ' = %s' for c in sets)} WHERE product_news_id = %s", [*sets.values(), o["product_news_id"]])
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_product_news' AND row_id = %s", (str(o["product_news_id"]),))
        cur.execute("UPDATE staging.fact_source SET row_id = %s WHERE table_name = 'competitive_product_news' AND row_id = %s", (str(o["product_news_id"]), str(nid)))
        cur.execute("DELETE FROM staging.competitive_product_news WHERE product_news_id::text = %s", (str(nid),))
        swap[str(nid)] = str(o["product_news_id"])
        ctx["notes"].append(f"product_news_merge: {nid} was already attached to this article: merged into {o['product_news_id']}")
    if swap:
        ctx["rows"] = [(t, swap.get(str(i), i) if t == "competitive_product_news" else i, *rest) for t, i, *rest in ctx.get("rows", [])]
        ctx["cards"] = [(t, swap.get(str(i), i) if t == "competitive_product_news" else i) for t, i in ctx.get("cards", [])]
        tr = ctx.get("transient", {})
        for old, new in swap.items():
            if ("competitive_product_news", old) in tr:
                tr[("competitive_product_news", new)] = tr.pop(("competitive_product_news", old))


@hook("story_link")
def story_link(cur, ctx: dict) -> None:
    """Link every competitive_signal / competitive_product_news / market_global_requirement / market_opportunity /
    technology_overview_article of this run to its story and write its step (prompts/story.py). Reads the model's transient
    fields story_ref, story_kind, story_country, story_product. Run it AFTER signal_label / tech_direction (the step stores the label)."""
    from prompts import story
    tr = ctx.get("transient", {})
    signals = ids(ctx, "competitive_signal")
    for table, (key_col, _) in story.CARDS.items():
        for cid in ids(ctx, table):
            if table == "competitive_product_news" and signals:       # the signal of this run owns the story step; its product rows only point at it
                continue
            row = _row(cur, table, key_col, cid)
            if row is not None:
                story.link_card(cur, table, row, tr.get((table, str(cid))), run_id=None, warnings=ctx["warnings"])
    if signals:
        sig = _row(cur, "competitive_signal", "signal_id", signals[0])
        if sig is not None and sig.get("story_id") is not None:
            for pn in ids(ctx, "competitive_product_news"):
                cur.execute("UPDATE staging.competitive_product_news SET story_id = %s WHERE product_news_id::text = %s", (sig["story_id"], str(pn)))


@hook("tech_direction")
def tech_direction_hook(cur, ctx: dict) -> None:
    """technology_overview_article.direction = tech_direction(classification, relevance, maturity); a missing or unknown horizon is
    derived from the maturity and marked horizon_source = rule; a stated horizon is marked stated; rule_version stored."""
    for aid in ids(ctx, "technology_overview_article"):
        r = _row(cur, "technology_overview_article", "overview_article_id", aid)
        if r is None:
            continue
        horizon, source = r.get("horizon"), r.get("horizon_source")
        if horizon in (None, "", "unknown"):
            derived = horizon_from_maturity(r.get("maturity"))
            horizon, source = (derived, "rule") if derived != "unknown" else ("unknown", source)
        elif source is None:
            source = "stated"
        cur.execute("""UPDATE staging.technology_overview_article SET direction = %s, horizon = %s, horizon_source = %s, rule_version = %s
                       WHERE overview_article_id::text = %s""",
                    (tech_direction(r.get("classification"), r.get("relevance"), r.get("maturity")), horizon, source, RULE_VERSIONS["tech"], str(aid)))


@hook("requirement_state")
def requirement_state_hook(cur, ctx: dict) -> None:
    """market_global_requirement.status_state = current | unconfirmed from stage and last_confirmed (A.2.3)."""
    for rid in ids(ctx, "market_global_requirement"):
        r = _row(cur, "market_global_requirement", "requirement_id", rid)
        if r is not None:
            cur.execute("UPDATE staging.market_global_requirement SET status_state = %s, status = coalesce(%s, status) WHERE requirement_id = %s",
                        (requirement_state(r.get("stage"), r.get("last_confirmed"), ctx["today"]), REQUIREMENT_STATUS.get(_word(r.get("stage"))), r["requirement_id"]))


@hook("pursue_label")
def pursue_label_hook(cur, ctx: dict) -> None:
    """For every market_tender_fit_assessment (and market_opportunity_fit_assessment) this run wrote: attractiveness = round(mean(value_score,
    strategic_score)); ability from the fit grade, fit percent, the tender's eligibility checklist, its strong rivals and KSSL's presence
    in the buyer's country; pursue_label; rule_version. A tender's lean_code follows the label (pursue -> go, position -> maybe,
    monitor -> watch, pass -> pass). Run AFTER tender_fit, which sets lean_code from the grade alone."""
    names, _ = _client_presence(cur)
    for kind, table, idcol in (("tender", "market_tender_fit_assessment", "assessment_id"), ("opportunity", "market_opportunity_fit_assessment", "assessment_id")):
        for aid in ids(ctx, table):
            a = _row(cur, table, idcol, aid)
            if a is None:
                continue
            elig, strong, incumbent, country = [], 0, False, set()
            if kind == "tender":
                cur.execute("SELECT state, fixable FROM staging.market_tender_eligibility WHERE tender_id = %s", (a["tender_id"],))
                elig = [dict(x) for x in cur.fetchall()]
                cur.execute("SELECT fit_label, basis FROM staging.market_tender_competitor_fit WHERE tender_id = %s", (a["tender_id"],))
                rivals = [dict(x) for x in cur.fetchall()]
                strong = sum(_word(x["fit_label"]) == "strong" for x in rivals)
                incumbent = any(_word(x["basis"]) in ("presence", "selected") for x in rivals)
                t = _row(cur, "market_tender", "tender_id", a["tender_id"]) or {}
                country = _country_names(cur, t.get("country_name"), t.get("country_code"))
            else:
                o = _row(cur, "market_opportunity", "opportunity_id", a["opportunity_id"]) or {}
                country = _country_names(cur, None, o.get("country_code"))
            es = eligibility_summary(elig)
            att = attractiveness(a.get("value_score"), a.get("strategic_score"))
            fit_pct = a.get("fit_score")
            abl = ability(a.get("fit_grade"), None if fit_pct is None else float(fit_pct), es["fixable_not_met"], es["hard_bar"], strong, incumbent, bool(country & names))
            if abl is not None and fit_pct is None and _word(a.get("fit_grade")) == "partial":
                abl = min(abl, 3)          # no checkable requirement line (fewer than 3): the fit is a product-kind match only, so never "pursue"
            label = pursue_label(a.get("fit_grade"), att, abl, es["all_fixable"], es["hard_bar"])
            over = kind == "tender" and _word(t.get("status")) in ("awarded", "closed")      # the bid is over: no pursue / position advice, lean_code closed
            if over:
                label = None
            cur.execute(f"UPDATE staging.{table} SET attractiveness = %s, ability = %s, pursue_label = %s, rule_version = %s WHERE {idcol} = %s",
                        (att, abl, label, RULE_VERSIONS["pursue"], a[idcol]))
            if over:
                cur.execute("UPDATE staging.market_tender SET lean_code = 'closed' WHERE tender_id = %s", (a["tender_id"],))
            elif kind == "tender" and label:
                cur.execute("UPDATE staging.market_tender SET lean_code = %s WHERE tender_id = %s", (PURSUE_LEAN[label], a["tender_id"]))
            ctx["notes"].append(f"pursue_label: {table} {aid}: {label} (attractiveness={att}, ability={abl}, fit={a.get('fit_grade')})")


@hook("award_to_signal")
def award_to_signal(cur, ctx: dict) -> None:
    """STUB (A.2.2, no model call): a tender with awarded_to that names a tracked competitor becomes a competitive signal by rule.
    Scores: award_signal_scores (probability 5, orders impact 4 when KSSL assessed the tender strong / partial, else 3). The label
    comes from signal_label; the signal gets a detail row (provenance names the tender) and a story step. NOT done: the geo 'Sells'
    row, and a signal when the award names a company that is not a tracked competitor. Idempotent (fixed signal id). Runs for the
    tenders of this run, or for every awarded tender when the run wrote none."""
    import uuid
    from prompts import story
    from prompts.loader import match_name
    wanted = {str(t) for t in ids(ctx, "market_tender")}
    cur.execute("SELECT tender_id FROM staging.market_tender WHERE coalesce(btrim(awarded_to), '') <> ''")
    todo = [r["tender_id"] for r in cur.fetchall() if not wanted or str(r["tender_id"]) in wanted]
    cur.execute("SELECT competitor_id, display_name, short_name, legal_name FROM staging.competitive_competitor")
    comps = [dict(r) for r in cur.fetchall()]
    for tid in todo:
        t = _row(cur, "market_tender", "tender_id", tid)
        hit = match_name(comps, ["display_name", "short_name", "legal_name"], t["awarded_to"])
        if len({h["competitor_id"] for h in hit}) != 1:
            ctx["notes"].append(f"award_to_signal: tender {tid}: '{t['awarded_to']}' is not (one) tracked competitor; no signal")
            continue
        comp = hit[0]
        cur.execute("SELECT fit_grade FROM staging.market_tender_fit_assessment WHERE tender_id = %s ORDER BY fit_score DESC NULLS LAST LIMIT 1", (tid,))
        g = cur.fetchone()
        sc = award_signal_scores(g["fit_grade"] if g else None, client_market_state(cur, t.get("country_name"), t.get("country_code")))
        label = signal_label(sc["probability"], sc["impact"], sc["time_to_effect"], sc["in_client_market"], sc["subtype_match"], sc["impact_dimension"], sc["direction"])
        sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kssl-derive|award_to_signal|{tid}"))
        day = t.get("award_date")
        if not day:                                       # the run date is not the award date: no stated date, no signal
            ctx["notes"].append(f"award_to_signal: tender {tid}: the notice states no award date; no signal")
            continue
        title = f"{comp['display_name']} wins: {t['title']}"[:300]
        summary = f"{comp['display_name']} was awarded this tender" + (f" ({t['award_value_text']})" if t.get("award_value_text") else "") + "."
        cur.execute("DELETE FROM staging.competitive_signal_detail WHERE signal_id = %s", (sid,))
        cur.execute("DELETE FROM staging.competitive_signal WHERE signal_id = %s", (sid,))
        cur.execute("""INSERT INTO staging.competitive_signal (signal_id, company_id, classification, sequence_no, title, summary, category, event_date,
                           direction, probability, impact, impact_dimension, time_to_effect, subtype_match, in_client_market, rule_version, impact_orders_revenue)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (sid, comp["competitor_id"], label, (date(2100, 1, 1) - day).days, title, summary, t.get("category_text"), day, sc["direction"],
                     sc["probability"], sc["impact"], sc["impact_dimension"], sc["time_to_effect"], sc["subtype_match"], sc["in_client_market"],
                     RULE_VERSIONS["signal"], sc["impact_orders_revenue"]))
        cur.execute("""INSERT INTO staging.competitive_signal_detail (signal_id, drawer_title, what_article_says, provenance, source_name, source_url,
                           glance_who, glance_move, glance_where, glance_impact, glance_third_party, glance_when)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (sid, title, summary, f"award_to_signal: market_tender {tid}", t.get("issuer_display") or None, t.get("source_url"),
                     comp["display_name"][:40], "Contract", (t.get("country_name") or "")[:40] or None, glance_impact(sc["impact"], sc["impact_dimension"]),
                     (t.get("buyer_name") or "")[:60] or None, f"{day.day} {day:%b %Y}"))
        # the scores are a rule, not a reading: each one carries its reason (Trace shows it), like signal_label's done-event rule
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_signal' AND row_id = %s", (sid,))
        assessed = sc["subtype_match"] == "same"
        for col, why in (("probability", "5 by rule: the notice reports the contract as awarded (done)."),
                         ("impact_orders_revenue", f"{sc['impact']} by rule: {'the client assessed this tender as a strong or partial fit' if assessed else 'the client did not assess this tender as a fit'}."),
                         ("time_to_effect", "lt_1y by rule: the award itself is the effect."),
                         ("subtype_match", "same by rule: the client assessed a like-for-like product for this tender." if assessed else "unknown by rule: no client product was assessed for this tender.")):
            cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at) VALUES "
                        "('competitive_signal', %s, %s, 'judgement', 'judgement', %s, now())", (sid, col, why))
        row = _row(cur, "competitive_signal", "signal_id", sid)
        story.link_card(cur, "competitive_signal", row, {"story_country": t.get("country_name"), "story_kind": "order"}, warnings=ctx["warnings"])
        ctx["notes"].append(f"award_to_signal: tender {tid} -> signal {sid}: {label}")


TENDER_FACT_COLS = ("title", "buyer_name", "country_name", "description", "published_date", "closing_date", "notice_reference", "tender_number",
                    "value_amount", "value_currency", "value_text", "quantity", "quantity_unit", "frequency", "latest_milestone",
                    "local_presence_requirement", "registration_requirement", "submission_method", "awarded_to", "award_date", "award_value_text")


@hook("tender_source_facts")
def tender_source_facts(cur, ctx: dict) -> None:
    """Every stored fact column of a tender the prompt filled without its own _sources gets a fact_source row that names the stored
    API record (staging.tender_raw: source api + notice id) and the notice url. The prompt reads that record, so the record IS the source
    of those values; the quote says so and is not a quotation. Columns the model sourced itself are left alone (A.0.2). No AI."""
    from backend.sources import classify
    for tid in ids(ctx, "market_tender"):
        t = _row(cur, "market_tender", "tender_id", tid)
        if t is None:
            continue
        cur.execute("SELECT source_api, notice_id, notice_url FROM staging.tender_raw WHERE tender_id = %s LIMIT 1", (t["tender_id"],))
        r = cur.fetchone()
        url = t.get("source_url") or (r["notice_url"] if r else None)
        if not url:
            continue
        cur.execute("SELECT column_name FROM staging.fact_source WHERE table_name = 'market_tender' AND row_id = %s", (str(t["tender_id"]),))
        have = {x["column_name"] for x in cur.fetchall()}
        tier = classify(url, ()) or "stored"
        quote = f"stored API record {r['source_api']} {r['notice_id']}" if r else "notice page"
        for col in TENDER_FACT_COLS:
            if t.get(col) not in (None, "") and col not in have:
                cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at) "
                            "VALUES ('market_tender', %s, %s, %s, %s, %s, now())", (str(t["tender_id"]), col, url, tier, quote))


DOC_FACT_COLS = {   # table -> (key column, the stored fact columns the model fills from the document)
    "market_global_requirement": ("requirement_id", ("title", "buyer_name", "country_name", "region", "description", "stage", "stage_date", "last_confirmed", "deadline", "value_text")),
    "market_global_requirement_specification": ("requirement_spec_id", ("spec_label", "spec_value")),
    "market_global_requirement_rival": ("rival_id", ("basis", "note")),
    "market_opportunity": ("opportunity_id", ("title", "opportunity_kind", "buyer_name", "contractor_name", "description", "scope_text", "location_text", "stage",
                                               "current_status", "latest_milestone", "as_of_date")),
    "market_opportunity_update": ("update_id", ("update_type", "update_date", "headline", "narrative")),
}


@hook("doc_source_facts")
def doc_source_facts(cur, ctx: dict) -> None:
    """Every stored fact column the model filled from the run's document without its own _sources gets a fact_source row that names the document
    (url of the subject, from the raw layer's stored text). The quote says so and is not a quotation. Judgements keep their own reason rows. No AI."""
    from backend.sources import classify
    url = (ctx.get("subject_row") or {}).get("article_url")
    if not url:
        return
    tier = classify(url, ()) or "unlisted"
    for table, (keycol, cols) in DOC_FACT_COLS.items():
        for rid in ids(ctx, table):
            r = _row(cur, table, keycol, rid)
            if r is None:
                continue
            cur.execute("SELECT column_name FROM staging.fact_source WHERE table_name = %s AND row_id = %s", (table, str(rid)))
            have = {x["column_name"] for x in cur.fetchall()}
            for col in cols:
                if r.get(col) not in (None, "") and col not in have:
                    cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at) "
                                "VALUES (%s, %s, %s, %s, %s, %s, now())", (table, str(rid), col, url, tier, "stated in the stored text of this document"))


@hook("top_opportunity_finalize")
def top_opportunity_finalize(cur, ctx: dict) -> None:
    """After the top_opportunity prompt wrote its text rows: code decides the list. Ranks (backend/market_rollups.top_candidates / project_candidates),
    fit, model, status and revenue text come from the stored rows; the model's `decides`, `rival_to_beat` and `where_it_stands` are kept for
    rows the code ranked; a row the model missed gets a code default; a row the code did not rank is dropped. Next moves and the four metric tiles are
    written by code. No AI beyond the text the prompt wrote."""
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
    from backend import market_rollups as mr
    n = mr.write_top(cur, keep_text=True)
    mr.metrics(cur)
    ctx["notes"].append(f"top_opportunity_finalize: {n['tenders']} tenders, {n['projects']} projects ranked by code; next moves and metrics rewritten")


def rebuild_filter_options(cur, pillars=("competitive", "technology", "market"), data: str = "staging", ui: str = "staging_ui", live: bool = False) -> dict:
    """Rebuild the filter-option tables from the distinct stored values: competitive_filter_option, technology_filter_option (ui schema)
    and market_filter_option (data schema), with record counts. Labels come from ui.code_label where the column has rows there.
    Every table is replaced as a whole; a filter whose source table or column is missing is skipped and noted. `live=True` is for
    the serving schemas (data='serving', ui='ui'): it sets kssl.approve first, as Approve does. Returns {pillar: {filter_type: rows}}."""
    if live:
        cur.execute("SET LOCAL kssl.approve = 'on'")
    cur.execute(f"SELECT table_name, column_name, code, label, display_order FROM {ui}.code_label WHERE is_active")
    labels: dict = {}
    for r in cur.fetchall():
        labels.setdefault((r["table_name"], r["column_name"]), {})[r["code"]] = (r["label"], r["display_order"])
    result = {}
    for pillar in pillars:
        schema_tpl, table = FILTER_TABLES[pillar]
        target = f"{schema_tpl.format(S=data, U=ui)}.{table}"
        rows, counts_by_type = [], {}
        for spec in FILTERS[pillar]:
            ftype, tbl, col = spec[0], spec[1], spec[2]
            sql = spec[3].format(S=data) if len(spec) > 3 else (
                f"SELECT {col}::text AS code, count(*) AS n FROM {data}.{tbl} WHERE {col} IS NOT NULL AND btrim({col}::text) <> '' GROUP BY 1")
            cur.execute("SAVEPOINT filt")
            try:
                cur.execute(sql)
                got = [(r["code"], r.get("label"), r["n"]) for r in cur.fetchall()]
                cur.execute("RELEASE SAVEPOINT filt")
            except Exception as e:  # noqa: BLE001  a missing table / column skips that one filter
                cur.execute("ROLLBACK TO SAVEPOINT filt")
                counts_by_type[ftype] = f"skipped: {type(e).__name__}"
                continue
            lab = labels.get((tbl, col)) if tbl else None
            made = option_rows(table, ftype, got, lab)
            rows += made
            counts_by_type[ftype] = len(made)
        cur.execute(f"DELETE FROM {target}")
        for r in rows:
            cur.execute(f"INSERT INTO {target} (option_id, filter_type, option_code, option_label, record_count, sort_order, is_active) "
                        "VALUES (%(option_id)s, %(filter_type)s, %(option_code)s, %(option_label)s, %(record_count)s, %(sort_order)s, %(is_active)s)", r)
        result[pillar] = counts_by_type
    return result


@hook("filter_options")
def filter_options_hook(cur, ctx: dict) -> None:
    """Rebuild competitive_filter_option, technology_filter_option and market_filter_option in staging from the stored values."""
    res = rebuild_filter_options(cur)
    for pillar, counts in res.items():
        ctx["notes"].append(f"filter_options {pillar}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


# ---- self-checks ----------------------------------------------------------------------------------------------------------------------
# python -m prompts.derive --selftest          pure rules, fictional values, every branch of every label rule (no DB)
# python -m prompts.derive --selftest-db       the hooks, on a THROWAWAY database (KSSL_TEST_STAGING_DSN, default kssl_test_staging_f), rolled back

def selftest() -> None:
    S = signal_label
    # -- signal_label: threat needs every test; the base case first
    base = dict(probability=5, impact=5, time_to_effect="1_3y", in_client_market="yes", subtype_match="same", impact_dimension="orders_revenue")
    assert S(**base) == "threat"
    assert S(**{**base, "probability": 4, "impact": 4, "time_to_effect": "lt_1y", "subtype_match": "adjacent"}) == "threat"          # the boundary
    for k, v in (("probability", 3), ("impact", 3), ("time_to_effect", "gt_3y"), ("in_client_market", "no"),
                 ("in_client_market", "unknown"), ("subtype_match", "none"), ("subtype_match", "unknown")):
        assert S(**{**base, k: v}) == "watch", (k, v)                                                                                   # one failed test -> watch
    for k in base:                                                                                                                      # a missing input -> watch
        if k not in ("impact_dimension", "time_to_effect"):                                       # (the dimension only grants exemptions; a missing one is just "no exemption")
            assert S(**{**base, k: None}) == "watch", k
    assert S(**{**base, "impact_dimension": None}) == "threat"
    assert S(**{**base, "probability": 4.5}) == "watch" and S(**{**base, "impact": True}) == "watch" and S(**{**base, "impact": "high"}) == "watch"
    assert S(**{**base, "in_client_market": "YES", "time_to_effect": "LT_1Y"}) == "threat"                                             # case-insensitive
    # dimensions that need no KSSL market: supply_chain, partnerships, policy_export
    for dim in ("supply_chain", "partnerships"):                                                                                         # ... and no like-for-like product
        assert S(5, 5, "1_3y", "no", "none", dim) == "threat" and S(5, 5, "1_3y", "unknown", "unknown", dim) == "threat", dim
        assert S(5, 5, "gt_3y", "no", "none", dim) == "watch" and S(4, 4, "unknown", "yes", "same", dim) == "watch"                     # time still counts (a done event, probability 5, counts as lt_1y)
    assert S(5, 5, "1_3y", "no", "none", "policy_export") == "watch"                                                                    # policy needs a like-for-like product
    assert S(5, 5, "1_3y", "no", "adjacent", "policy_export") == "threat" and S(5, 5, "1_3y", None, "same", "policy_export") == "threat"
    assert S(5, 5, "1_3y", "no", "same", "orders_revenue") == "watch" and S(5, 5, "1_3y", "no", "same", "technology_gap") == "watch"     # outside KSSL's markets
    assert S(5, 5, "1_3y", "yes", "none", "technology_gap") == "watch" and S(5, 5, "1_3y", "yes", "none", "market_standing") == "watch"  # indirect
    assert S(5, 5, "1_3y", "yes", "same", None) == "threat" and S(5, 5, "1_3y", "no", "none", None) == "watch"                          # no dimension: no exemption
    # s2: no fav. A favourable move is never a threat: done -> none, not done -> watch
    assert S(**{**base, "direction": "favourable"}) == ("none" if base["probability"] == 5 else "watch")
    assert S(5, 1, None, None, None, None, "favourable") == "none" and S(4, 5, "lt_1y", "yes", "same", "orders_revenue", "favourable") == "watch"
    assert S(3, 5, "1_3y", "yes", "same", "orders_revenue", "favourable") == "watch"
    # s2: a done event (probability 5) with impact 1-2 has materialised and is no threat -> none; impact 3+ or not done -> watch
    assert S(5, 2, "lt_1y", "yes", "same", "orders_revenue") == "none" and S(5, 1, None, None, None, None) == "none"
    assert S(5, 3, "lt_1y", "no", "same", "orders_revenue") == "watch" and S(4, 1, "lt_1y", "yes", "same", "orders_revenue") == "watch"
    assert S(5, None, "lt_1y", "yes", "same", "orders_revenue") == "watch"                                                              # unknown impact: not proven low
    # funding needs no KSSL market (capital is not tied to a country), but a like-for-like line
    assert S(5, 5, "lt_1y", "no", "same", "funding") == "threat" and S(5, 5, "lt_1y", "no", "none", "funding") == "watch"
    assert S(**{**base, "direction": "adverse"}) == "threat" and S(**{**base, "direction": "unknown"}) == "threat" and S(**{**base, "direction": None}) == "threat"
    assert S(None, None, None, None, None, None) == "watch" and S(*[None] * 7) == "watch"
    # -- impact_max: maximum, its dimension (listed order breaks a tie), a second dimension only at 4 or more
    assert impact_max({}) == (None, None, None) and impact_max({"orders_revenue": None, "supply_chain": "x", "policy_export": 0, "partnerships": 6}) == (None, None, None)
    assert impact_max({"orders_revenue": 5, "market_standing": 4, "supply_chain": 1, "technology_gap": 2, "partnerships": 1, "policy_export": 2}) == (5, "orders_revenue", "market_standing")
    assert impact_max({"orders_revenue": 3, "technology_gap": 3}) == (3, "orders_revenue", None)
    assert impact_max({"supply_chain": 4, "partnerships": 4, "policy_export": 4}) == (4, "supply_chain", "partnerships")
    assert impact_max({"supply_chain": 5, "partnerships": 4, "market_standing": 4}) == (5, "supply_chain", "market_standing")
    assert impact_max({"technology_gap": 2, "orders_revenue": "3"}) == (3, "orders_revenue", None) and impact_max({"orders_revenue": 3.5}) == (None, None, None)
    # -- glance_impact
    assert glance_impact(5, "orders_revenue") == "Orders · high" and glance_impact(4, "policy_export") == "Policy · high"
    assert glance_impact(3, "supply_chain") == "Supply chain · medium" and glance_impact(2, "technology_gap") == "Technology · low" and glance_impact(1, "partnerships") == "Partnerships · low"
    assert glance_impact(4, None) == "High" and glance_impact(None, "orders_revenue") is None and glance_impact(0, "orders_revenue") is None
    assert moment_grade("threat") == "high" and moment_grade("watch") == "watch" and moment_grade("fav") == "opportunity" and moment_grade("x") is None
    # -- technology: horizon from maturity, direction
    assert [horizon_from_maturity(m) for m in (1, 2, 3, 4, 5, None, 7)] == ["gt_5y", "gt_5y", "2_5y", "2_5y", "lt_2y", "unknown", "unknown"]
    T = tech_direction
    assert T("competitor_advance", 5, 3) == "threat" and T("threat_to_position", 4, 5) == "threat" and T("competitor_advance", 4, 3) == "threat"
    assert T("competitor_advance", 3, 5) == "watch" and T("competitor_advance", 5, 2) == "watch" and T("industry_trend", 5, 5) == "watch"
    assert T("adoptable", 3, 1) == "watch" and T("adoptable", 5, 5) == "watch" and T("adoptable", 2, 5) == "watch" and T("Adoptable", "4", 2) == "watch"   # t2: no fav
    assert T("competitor_advance", None, 5) == "watch" and T("competitor_advance", 5, None) == "watch" and T(None, None, None) == "watch" and T("adoptable", None, None) == "watch"
    # -- market: attractiveness, ability, eligibility, pursue_label
    assert [attractiveness(a, b) for a, b in ((4, 4), (4, 3), (3, 2), (2, 2), (5, None), (None, 2), (None, None), (1, 2), (5, 4))] == [4, 4, 3, 2, 5, 2, None, 2, 5]
    assert eligibility_summary([]) == {"fixable_not_met": 0, "hard_bar": False, "all_fixable": True}
    assert eligibility_summary([{"state": "met", "fixable": "no"}, {"state": "unknown", "fixable": "no"}]) == {"fixable_not_met": 0, "hard_bar": False, "all_fixable": True}
    assert eligibility_summary([{"state": "not_met", "fixable": "yes"}, {"state": "not_met", "fixable": "yes"}]) == {"fixable_not_met": 2, "hard_bar": False, "all_fixable": True}
    assert eligibility_summary([{"state": "not_met", "fixable": "unknown"}]) == {"fixable_not_met": 1, "hard_bar": False, "all_fixable": False}
    assert eligibility_summary([{"state": "not_met", "fixable": "no"}, {"state": "not_met", "fixable": "yes"}]) == {"fixable_not_met": 1, "hard_bar": True, "all_fixable": False}
    A = ability
    assert A("strong", 83) == 5 and A("strong", 75) == 5 and A("strong", 74) == 4 and A("strong", None) == 4 and A("partial") == 3 and A("weak") == 1 and A(None) is None and A("odd") is None
    assert A("strong", 83, fixable_not_met=2) == 3 and A("strong", 83, fixable_not_met=9) == 1 and A("partial", fixable_not_met=1) == 2     # -1 each, floor 1
    assert A("strong", 83, hard_bar=True) == 3 and A("partial", hard_bar=True) == 1 and A("strong", 83, fixable_not_met=1, hard_bar=True) == 2
    assert A("strong", 83, strong_rivals=2, incumbent=True) == 4 and A("strong", 83, strong_rivals=1, incumbent=True) == 5 and A("strong", 83, strong_rivals=3) == 5
    assert A("partial", kssl_present=True) == 4 and A("strong", 90, kssl_present=True) == 5 and A("weak", kssl_present=True) == 2           # +1 / clamp 5
    assert A("strong", 90, fixable_not_met=2, strong_rivals=2, incumbent=True, kssl_present=True) == 3                                   # 5 -2 -1 +1
    P = pursue_label
    assert P("weak", 5, 5) == "pass" and P("strong", 5, 5, True, True) == "pass" and P("partial", None, None, True, True) == "pass"       # weak or a hard bar
    assert P(None, 5, 5) is None and P("odd", 5, 5) is None
    assert P("strong", 3, 4) == "pursue" and P("strong", 5, 5) == "pursue" and P("partial", 3, 5) == "pursue"
    assert P("strong", 2, 5) == "monitor" and P("strong", 1, 1) == "monitor"                                                             # unattractive
    assert P("strong", 3, 3) == "position" and P("partial", 5, 3) == "position"
    assert P("strong", 4, 2, True) == "position" and P("strong", 5, 2, True) == "position" and P("strong", 4, 2, False) == "monitor"       # fixable gaps only
    assert P("strong", 3, 2, True) == "monitor" and P("strong", 5, 1, True) == "monitor" and P("partial", 4, 1) == "monitor"
    assert P("strong", None, 4) == "monitor" and P("strong", 4, None) == "monitor" and P("partial", None, None) == "monitor"
    # Fable F.2: strong fit, 83 percent, two fixable gaps (a local partner, portal registration), one strong rival with presence -> ability 3, attractiveness 4 -> position
    es = eligibility_summary([{"state": "not_met", "fixable": "yes"}, {"state": "unknown", "fixable": "yes"}, {"state": "not_met", "fixable": "yes"}])
    abl = A("strong", 83, es["fixable_not_met"], es["hard_bar"], strong_rivals=1, incumbent=True, kssl_present=False)
    assert abl == 3 and attractiveness(4, 4) == 4 and P("strong", 4, abl, es["all_fixable"], es["hard_bar"]) == "position"
    assert PURSUE_LEAN == {"pursue": "go", "position": "maybe", "monitor": "watch", "pass": "pass"}
    # -- requirement staleness
    d = lambda y, m, dd=1: date(y, m, dd)
    today = d(2026, 10, 17)
    assert requirement_state("need_stated", d(2026, 1, 20), today) == "current" and requirement_state("rfi", d(2025, 12, 1), today) == "unconfirmed"
    assert requirement_state("approved_funded", d(2026, 1, 17), today) == "current" and requirement_state("approved_funded", d(2026, 1, 10), today) == "unconfirmed"
    assert requirement_state("rfp_tender", d(2026, 8, 1), today) == "current" and requirement_state("rfp_tender", d(2026, 6, 1), today) == "unconfirmed"
    assert requirement_state("rfi", None, today) == "unconfirmed" and requirement_state("downselect_prototype", None, today) == "current"
    assert requirement_state("downselect_prototype", d(2020, 1, 1), today) == "current" and requirement_state("cancelled", d(2020, 1, 1), today) == "current"
    # -- award_to_signal scores, and the label they give
    a1 = award_signal_scores("strong", "yes")
    assert (a1["impact"], a1["subtype_match"], a1["probability"], a1["time_to_effect"]) == (4, "same", 5, "lt_1y")
    assert signal_label(a1["probability"], a1["impact"], a1["time_to_effect"], a1["in_client_market"], a1["subtype_match"], a1["impact_dimension"], a1["direction"]) == "threat"
    a2 = award_signal_scores(None, "yes")
    assert (a2["impact"], a2["subtype_match"]) == (3, "unknown") and signal_label(5, a2["impact"], "lt_1y", "yes", "unknown", "orders_revenue") == "watch"
    assert S(**{**base, "probability": 4, "time_to_effect": "unknown"}) == "watch"          # not done and no date: still watch
    assert effective_time_to_effect(5, "unknown") == "lt_1y" and effective_time_to_effect(5, None) == "lt_1y" and effective_time_to_effect(5, "gt_3y") == "gt_3y"
    assert effective_time_to_effect(4, "unknown") == "unknown" and effective_time_to_effect(None, None) == "unknown" and effective_time_to_effect(3, "1_3y") == "1_3y"
    assert signal_label(5, 4, "unknown", "yes", "same", "orders_revenue") == "threat" and signal_label(4, 4, "unknown", "yes", "same", "orders_revenue") == "watch"
    assert award_signal_scores("partial", "unknown")["impact"] == 4 and signal_label(5, 4, "lt_1y", "unknown", "same", "orders_revenue") == "watch"
    # -- option rows: counts, labels, ordering, ids
    rows = option_rows("competitive_filter_option", "classification", [("watch", None, 6), ("threat", None, 1), ("fav", None, 0), (None, None, 4), ("", None, 2)],
                       {"threat": ("Threat", 1), "watch": ("Watch", 2), "fav": ("Favourable", 3)})
    assert [(r["option_code"], r["option_label"], r["record_count"], r["sort_order"]) for r in rows] == [("threat", "Threat", 1, 1), ("watch", "Watch", 6, 2)]
    rows = option_rows("market_filter_option", "country", [("PL", "Poland", 1), ("IN", "India", 3), ("AE", None, 3), ("IN", None, 1)])
    assert [(r["option_code"], r["option_label"], r["record_count"]) for r in rows] == [("IN", "India", 4), ("AE", "AE", 3), ("PL", "Poland", 1)]
    assert all(r["is_active"] for r in rows) and len({r["option_id"] for r in rows}) == 3
    assert rows[0]["option_id"] == option_id("market_filter_option", "country", "IN") != option_id("market_filter_option", "category", "IN")
    assert option_rows("t", "x", []) == []
    assert set(REGISTRY) >= {"signal_label", "story_link", "tech_direction", "pursue_label", "filter_options", "award_to_signal", "moment_grade", "requirement_state", "product_news_merge"}
    assert {f[0] for f in FILTERS["market"]} >= {"country", "category", "pursue_label"} and set(FILTER_TABLES) == set(FILTERS)
    print("derive self-check ok")


def selftest_db() -> None:
    """The hooks against a throwaway database (fictional rows from db/test_seed_full/90_foundations.sql), everything rolled back."""
    import os
    import uuid
    import psycopg2
    import psycopg2.extras
    dsn = os.getenv("KSSL_TEST_STAGING_DSN") or "host=127.0.0.1 port=55432 dbname=kssl_test_staging_f user=kssl password=kssl"
    assert "dbname=kssl_test_" in dsn, "throwaway databases only (dbname=kssl_test_*)"
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        ctx = {"warnings": [], "notes": [], "today": date(2026, 10, 17), "rows": [], "cards": [], "transient": {}}
        comp = "c0ffee00-0000-4000-8000-000000000001"
        sid, sid2 = str(uuid.uuid4()), str(uuid.uuid4())
        for s_, title, p, i_o, tte, icm in ((sid, "Borealis wins howitzer order (TEST)", 4, 4, "1_3y", "yes"), (sid2, "Borealis shortlisted (TEST)", 3, 4, "1_3y", "yes")):
            cur.execute("""INSERT INTO staging.competitive_signal (signal_id, company_id, classification, sequence_no, title, event_date, probability, time_to_effect,
                               subtype_match, in_client_market, impact_orders_revenue, impact_market_standing, direction)
                           VALUES (%s,%s,'watch',1,%s,%s,%s,%s,'same',%s,%s,4,'adverse')""",
                        (s_, comp, title, date(2026, 10, 8) if p == 4 else date(2026, 6, 20), p, tte, icm, i_o))
            cur.execute("INSERT INTO staging.competitive_signal_detail (signal_id, drawer_title, glance_move, glance_where, source_url) VALUES (%s,%s,'Order','Norland','https://example.com/t')", (s_, title))
        ctx["rows"] = [("competitive_signal", sid, True), ("competitive_signal", sid2, True)]
        # a re-run of the same hooks must give the same result
        for _ in range(2):
            run(["signal_label"], cur, ctx)
            cur.execute("SELECT signal_id::text AS id, classification, impact, impact_dimension, impact_dimension_2, rule_version FROM staging.competitive_signal WHERE signal_id::text IN (%s,%s)", (sid, sid2))
            got = {r["id"]: r for r in cur.fetchall()}
            assert got[sid]["classification"] == "threat" and got[sid]["impact"] == 4 and got[sid]["impact_dimension"] == "orders_revenue" \
                and got[sid]["impact_dimension_2"] == "market_standing" and got[sid]["rule_version"] == RULE_VERSIONS["signal"], got[sid]
            assert got[sid2]["classification"] == "watch"                                                    # probability 3
            cur.execute("SELECT glance_impact FROM staging.competitive_signal_detail WHERE signal_id = %s", (sid,))
            assert cur.fetchone()["glance_impact"] == "Orders · high"
        # product_news_merge: a row the signal run wrote for a product + url the news job already attached is merged into the old row
        pid_, old_n, new_n = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        cur.execute("INSERT INTO staging.competitive_product (product_id, competitor_id, product_name, category, category_filter, is_collapsed) VALUES (%s,%s,'NV-TEST','Artillery','Artillery',false)", (pid_, comp))
        cur.execute("INSERT INTO staging.competitive_product_news (product_news_id, product_id, headline, article_url) VALUES (%s,%s,'h','https://example.com/pn'),(%s,%s,'h','https://example.com/pn')",
                    (old_n, pid_, new_n, pid_))
        cur.execute("UPDATE staging.competitive_product_news SET news_type = 'programme_order', event_date = '2026-10-08' WHERE product_news_id::text = %s", (new_n,))
        pctx = {**ctx, "rows": [("competitive_product_news", new_n, True)], "cards": [("competitive_product_news", new_n)], "transient": {("competitive_product_news", new_n): {"story_kind": "order"}}}
        run(["product_news_merge"], cur, pctx)
        cur.execute("SELECT product_news_id::text AS id, news_type FROM staging.competitive_product_news WHERE article_url = 'https://example.com/pn'")
        got_pn = cur.fetchall()
        assert [(r["id"], r["news_type"]) for r in got_pn] == [(old_n, "programme_order")], got_pn
        assert pctx["rows"] == [("competitive_product_news", old_n, True)] and ("competitive_product_news", old_n) in pctx["transient"]
        # stories: both signals share the competitor, no product, the country from glance_where (not in country_reference here) -> one key
        ctx["transient"] = {("competitive_signal", sid): {"story_country": "Norway", "story_kind": "order"}, ("competitive_signal", sid2): {"story_country": "Norway", "story_kind": "order"}}
        for _ in range(2):
            run(["story_link"], cur, ctx)
            cur.execute("SELECT s.story_key, s.current_label, s.probability, s.first_step_at, s.last_step_at, s.escalated_at, count(DISTINCT t.step_id) AS n "
                        "FROM staging.competitive_signal c JOIN staging.story s ON s.story_id = c.story_id "
                        "LEFT JOIN staging.story_step t ON t.story_id = s.story_id WHERE c.signal_id::text IN (%s,%s) GROUP BY 1,2,3,4,5,6", (sid, sid2))
            rows = cur.fetchall()
            assert len(rows) == 1, rows                                                                      # one story for both cards
            r = rows[0]
            assert r["story_key"].startswith("competitive:") and r["story_key"].endswith(":order"), r
            assert r["current_label"] == "threat" and r["probability"] == 4 and r["first_step_at"] == date(2026, 6, 20) and r["last_step_at"] == date(2026, 10, 8)
            assert r["escalated_at"] == date(2026, 10, 8) and r["n"] == 3, r                                # 2 steps + 1 label_change
        cur.execute("SELECT changed FROM staging.story_step WHERE step_type = 'label_change' AND source_row_id = %s", (sid,))
        assert cur.fetchone()["changed"].startswith("watch -> threat: probability 3 -> 4"), "label_change text"
        # the candidates block a prompt would get
        from prompts import story
        block = story.stories_block(cur, competitor_id=comp, pillar="competitive", today=date(2026, 10, 17))
        assert block.startswith("T") and "competitive:" in block and "(2026-10-08)" in block, block
        # filter options: counted from the stored values, labelled from code_label, replaced as a whole
        res = rebuild_filter_options(cur)
        cur.execute("SELECT option_code, option_label, record_count FROM staging_ui.competitive_filter_option WHERE filter_type = 'classification' ORDER BY sort_order")
        cls = cur.fetchall()
        assert {"threat", "watch"} <= {r["option_code"] for r in cls} and cls[0]["option_label"] in ("Threat", "Watch"), cls
        assert res["competitive"]["classification"] >= 2 and not isinstance(res["market"].get("country"), str), res
        # tech + market hooks on the seeded rows
        ctx["rows"] = [("technology_overview_article", "72001", True)]
        cur.execute("UPDATE staging.technology_overview_article SET classification='competitor_advance', relevance=5, maturity=3, horizon=NULL, horizon_source=NULL WHERE overview_article_id = 72001")
        run(["tech_direction"], cur, ctx)
        cur.execute("SELECT direction, horizon, horizon_source, rule_version FROM staging.technology_overview_article WHERE overview_article_id = 72001")
        assert dict(cur.fetchone()) == {"direction": "threat", "horizon": "2_5y", "horizon_source": "rule", "rule_version": "t1"}
        cur.execute("SELECT assessment_id, tender_id FROM staging.market_tender_fit_assessment ORDER BY assessment_id LIMIT 1")
        a = cur.fetchone()
        cur.execute("UPDATE staging.market_tender_fit_assessment SET fit_grade='strong', fit_score=83, value_score=4, strategic_score=4 WHERE assessment_id = %s", (a["assessment_id"],))
        cur.execute("DELETE FROM staging.market_tender_eligibility WHERE tender_id = %s", (a["tender_id"],))
        cur.execute("INSERT INTO staging.market_tender_eligibility (eligibility_id, tender_id, item, state, fixable) VALUES (99001,%s,'x','not_met','yes'),(99002,%s,'y','not_met','yes')",
                    (a["tender_id"], a["tender_id"]))
        ctx["rows"] = [("market_tender_fit_assessment", str(a["assessment_id"]), True)]
        run(["pursue_label"], cur, ctx)
        cur.execute("SELECT attractiveness, ability, pursue_label, rule_version FROM staging.market_tender_fit_assessment WHERE assessment_id = %s", (a["assessment_id"],))
        got = dict(cur.fetchone())
        assert got["attractiveness"] == 4 and got["ability"] in (3, 4) and got["pursue_label"] in ("position", "pursue") and got["rule_version"] == "p1", got
        cur.execute("SELECT lean_code FROM staging.market_tender WHERE tender_id = %s", (a["tender_id"],))
        assert cur.fetchone()["lean_code"] == PURSUE_LEAN[got["pursue_label"]]
        ctx["rows"] = [("market_global_requirement", "62001", True)]
        cur.execute("UPDATE staging.market_global_requirement SET stage='rfi', last_confirmed='2025-01-01' WHERE requirement_id = 62001")
        run(["requirement_state"], cur, ctx)
        cur.execute("SELECT status_state FROM staging.market_global_requirement WHERE requirement_id = 62001")
        assert cur.fetchone()["status_state"] == "unconfirmed"
        # award_to_signal: a tender awarded to a tracked competitor becomes a signal (twice = one signal)
        cur.execute("UPDATE staging.market_tender SET awarded_to = 'Borealis', award_date = '2026-09-30', award_value_text = 'NOK 2.1 bn (TEST)' WHERE tender_id = %s", (a["tender_id"],))
        cur.execute("SELECT display_name FROM staging.competitive_competitor WHERE competitor_id = %s", (comp,))
        name = cur.fetchone()["display_name"]
        cur.execute("UPDATE staging.market_tender SET awarded_to = %s WHERE tender_id = %s", (name, a["tender_id"]))
        ctx["rows"] = [("market_tender", str(a["tender_id"]), True)]
        for _ in range(2):
            run(["award_to_signal"], cur, ctx)
        cur.execute("SELECT s.classification, s.probability, s.impact, s.event_date, d.provenance FROM staging.competitive_signal s JOIN staging.competitive_signal_detail d USING (signal_id) "
                    "WHERE d.provenance LIKE %s", (f"award_to_signal: market_tender {a['tender_id']}",))
        rows = cur.fetchall()
        assert len(rows) == 1 and rows[0]["probability"] == 5 and rows[0]["event_date"] == date(2026, 9, 30), rows
        # the whole path: validate -> Loader.load (NOT NULL classification left to the hook, thumbnail token) -> signal_label -> story_link
        from prompts import loader
        out = loader.parse_output({"competitive_signal": {
            "card": True, "columns": {"title": {"required": True}, "event_date": {"type": "date"}, "company_id": {"from_ref": "ref_competitor"},
                                      "direction": {"enum": ["adverse", "favourable"]}, "probability": {"type": "number"},
                                      "time_to_effect": {}, "subtype_match": {}, "in_client_market": {}, "impact_orders_revenue": {"type": "number"}},
            "transient": {"story_ref": {}, "story_country": {}}, "loader": {"classification": "derive.signal_label", "thumbnail_url": "article_image_url",
                                                                           "sequence_no": "rank_by_event_date_desc"},
            "children": {"competitive_signal_detail": {"columns": ["drawer_title", "glance_move"], "required": ["drawer_title"]}}}})
        env = {"prompt_id": "x", "records": [{"table": "competitive_signal", "values": {
            "ref_competitor": name, "title": "Borealis signs a second order (TEST)", "event_date": "2026-10-12", "direction": "adverse", "probability": 5,
            "time_to_effect": "lt_1y", "subtype_match": "same", "in_client_market": "yes", "impact_orders_revenue": 5, "story_ref": "new", "story_country": "Norway"},
            "children": {"competitive_signal_detail": [{"drawer_title": "D", "glance_move": "Order"}]}}]}
        os.environ["KSSL_NO_IMAGE_FETCH"] = "1"
        ld = loader.Loader(cur, "x", "subj", out, {"image_url": "https://i.test/a.jpg"}, {"name": "KSSL"})
        lres = ld.load(loader.validate(env, "x", out, {}), [], ["signal_label", "story_link"])
        assert lres.rows == 2 and not lres.dropped, lres.dropped
        cur.execute("SELECT classification, thumbnail_url, impact, story_id FROM staging.competitive_signal WHERE title LIKE %s", ("Borealis signs a second order%",))
        got = cur.fetchone()
        assert got["classification"] == "threat" and got["thumbnail_url"] == "https://i.test/a.jpg" and got["impact"] == 5 and got["story_id"], got
        print("derive db self-check ok (rolled back):", sum(len(v) for v in res.values()), "filter types,", rows[0]["classification"], "award signal")
    finally:
        conn.rollback()
        conn.close()


from prompts import derive_tech, tech_rollups, tech_innovation_rules  # noqa: E402,F401  (technology-pillar hooks: tech_glance, innovation_gate, innovation_stance, patent_trend, technology_metric)
from prompts import derive_comp  # noqa: E402,F401  (competitive research hooks: partnership_overlap, project_story, geo_match_code)
from prompts import derive_synth  # noqa: E402,F401  (synthesis hooks: synthesis_finish, field_support, swot_counts)

if __name__ == "__main__":
    import sys
    if "--selftest-db" in sys.argv:
        selftest_db()
    elif "--selftest" in sys.argv:
        selftest()
    else:
        print(__doc__)
