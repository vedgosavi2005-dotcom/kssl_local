"""Area B: Products (competitor + KSSL catalogues, specs, programmes, product news) and Product
Evaluation (competitive_matchup*). Gap Analysis is hidden by decision.

Audit: docs/audit_v2/B_products_evaluation_gap.md. Runs after area A (reads d["competitors"]).

Everything is served as stored; nothing is defaulted. Evaluation uses competitive_matchup* (not
competitive_product_evaluation*). Edge / parity values are STORED columns (a loader computes them
from the prompt's per-spec better_side); the browser only presents them.

Vocabularies the UI expects (stored values are passed through, compared case-insensitively):
  competitive_matchup.decision_level (integer)   1 = KSSL behind (rival ahead), 2 = near parity,
                                                  3 = KSSL ahead, NULL = no judgement (shows nothing)
  competitive_matchup_specification.better_side   client | competitor | equal   (NULL = not judged)
  competitive_matchup_specification.comparability_state   comparable | one_sided | not_comparable
  competitive_matchup_advantage.side              client | competitor
  competitive_matchup_specification.gap_value     unsigned percent, abs(client - competitor) / mean * 100
  competitive_matchup.edge_score                  0-100, 50 = parity, higher = KSSL stronger
"""

from collections import defaultdict
from typing import Any

from backend.common import first_nonempty, slug, table, text


def _shown(n: Any) -> str | None:
    """A stored numeric printed without a trailing .0 (a display format, not a value change)."""
    if n is None:
        return None
    return str(int(n)) if n == int(n) else str(round(n, 6))


def _val(row: dict[str, Any], text_col: str, num_col: str) -> str | None:
    """The stored text value, else the stored numeric; None when neither exists."""
    t = row.get(text_col)
    if t not in (None, ""):
        return str(t)
    return _shown(row.get(num_col))


def _src(tbl: str, key: str, row: dict[str, Any]) -> dict[str, Any]:
    return {"t": tbl, "k": key, "id": text(row.get(key))}


def _by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        k = text(row.get(key))
        if k:
            grouped[k].append(row)
    return grouped


def build_matchups(database):
    advantages: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"client": [], "competitor": []})
    adv_rows = sorted(
        table(database, "serving", "competitive_matchup_advantage"),
        key=lambda r: (r.get("display_order") or 0),
    )
    for row in adv_rows:
        mid = text(row.get("matchup_id"))
        side = text(row.get("side")).strip().lower()
        if mid and side in ("client", "competitor") and row.get("advantage_text"):
            advantages[mid][side].append(text(row.get("advantage_text")))

    specs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    spec_rows = sorted(
        table(database, "serving", "competitive_matchup_specification"),
        key=lambda r: (r.get("display_order") or 0),
    )
    for row in spec_rows:
        mid = text(row.get("matchup_id"))
        if not mid:
            continue
        specs[mid].append({
            "l": text(row.get("spec_label")),
            "u": text(row.get("unit")),
            "group": text(row.get("spec_group")),
            "cv": _val(row, "competitor_value_text", "competitor_value_numeric"),
            "kv": _val(row, "client_value_text", "client_value_numeric"),
            "cn": row.get("competitor_value_numeric"),
            "kn": row.get("client_value_numeric"),
            "win": text(row.get("better_side")),
            "gap": row.get("gap_value"),
            "state": text(row.get("comparability_state")),
            "_src": _src("competitive_matchup_specification", "comparison_specification_id", row),
        })

    sources: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in table(database, "serving", "competitive_matchup_source"):
        mid = text(row.get("matchup_id"))
        if mid:
            sources[mid].append({
                "id": text(row.get("source_id")),
                "label": text(row.get("source_label")),
                "url": text(row.get("source_url")),
                "type": text(row.get("source_type")),
                "date": text(row.get("published_date")),
                "note": text(row.get("source_note")),
                "_src": {"t": "competitive_matchup_source", "k": "source_id", "id": text(row.get("source_id"))},
            })

    matchups = {}
    categories = {}
    for row in table(database, "serving", "competitive_matchup"):
        mid = text(row.get("matchup_id"))
        if not mid:
            continue
        category = text(row.get("category_code"))
        categories[slug(category)] = category
        adv = advantages.get(mid, {"client": [], "competitor": []})
        comp_name = text(row.get("competitor_name"))
        comp_product = text(row.get("competitor_product_name"))
        decision = row.get("decision_level")
        matchups[mid] = {
            "id": mid,
            "comp": comp_name + (f" · {comp_product}" if comp_product else ""),
            "compProduct": comp_product,
            "compBy": comp_name,
            "compId": text(row.get("competitor_id")),
            "compProductId": text(row.get("competitor_product_id")),
            "bf": text(row.get("client_product_name")),
            "anchor": text(row.get("client_product_name")),
            "clientProductId": text(row.get("client_product_id")),
            "cat": category,
            "country": text(row.get("competitor_country")),
            "matchBasis": text(row.get("match_basis")),
            "specs": specs.get(mid, []),
            "advBf": adv["client"],
            "advComp": adv["competitor"],
            "sources": sources.get(mid, []),
            "verdictH": text(row.get("verdict_headline")),
            "verdict": text(row.get("verdict")),
            "edge": row.get("edge_score"),
            "decision": None if decision in (None, "") else int(float(decision)),
            "comparable": row.get("comparable_spec_count"),
            "sourced": row.get("sourced_spec_count"),
            "_src": _src("competitive_matchup", "matchup_id", row),
        }
    pos_cats = [[key, label] for key, label in sorted(categories.items(), key=lambda item: item[1].lower())]
    return matchups, pos_cats, {label: key for key, label in categories.items()}  # CAT_KEY: label -> key, as MatchupList reads it


def _programs_competitor(rows):
    return [{
        "id": text(r.get("program_id")),
        "title": text(r.get("program_title")),
        "authority": text(r.get("authority")),
        "date": text(r.get("program_date")),
        "status": text(r.get("status")),
        "statusColor": text(r.get("status_color")),
        "description": text(r.get("description")),
        "_src": _src("competitive_product_program", "program_id", r),
    } for r in rows]


def _programs_client(rows):
    return [{
        "id": text(r.get("program_id")),
        "title": text(r.get("program_name")),
        "type": text(r.get("program_type")),
        "authority": text(r.get("owner")),
        "start": text(r.get("start_date")),
        "end": text(r.get("end_date")),
        "status": text(r.get("status")),
        "description": text(r.get("description")),
        "_src": _src("client_product_program", "program_id", r),
    } for r in rows]


def build_competitor_products(database, d, matchups):
    """competitive_product (+ _specification, _program, _news) -> competitors[cid].products."""
    specs = _by(table(database, "serving", "competitive_product_specification"), "product_id")
    programs = _by(table(database, "serving", "competitive_product_program"), "product_id")
    news = _by(table(database, "serving", "competitive_product_news"), "product_id")
    pair_ids: dict[str, list[str]] = defaultdict(list)
    for mid, m in matchups.items():
        if m["compProductId"]:
            pair_ids[m["compProductId"]].append(mid)

    competitors = d.get("competitors", {})
    for cid in competitors:
        competitors[cid]["products"] = []
    for row in table(database, "serving", "competitive_product"):
        pid = text(row.get("product_id"))
        cid = text(row.get("competitor_id"))
        if not pid or cid not in competitors:
            continue
        spec_rows = sorted(specs.get(pid, []), key=lambda r: text(r.get("spec_label")).lower())
        news_rows = sorted(news.get(pid, []), key=lambda r: text(r.get("published_date")), reverse=True)
        competitors[cid]["products"].append({
            "id": pid,
            "cid": cid,
            "name": text(row.get("product_name")),
            "category": text(row.get("category")),
            "country": text(row.get("country")),
            "specs": [{
                "id": text(r.get("spec_id")),
                "label": text(r.get("spec_label")),
                "value": text(r.get("spec_value")),
                "unit": text(r.get("unit")),
                "sourceCount": r.get("source_count"),
                "sourceUrl": text(r.get("source_url")),
                "_src": _src("competitive_product_specification", "spec_id", r),
            } for r in spec_rows],
            "programs": _programs_competitor(programs.get(pid, [])),
            "news": [{
                "id": text(r.get("product_news_id")),
                "title": text(r.get("headline")),
                "url": text(r.get("article_url")),
                "date": text(r.get("published_date")),
                "source": text(r.get("publisher")),
                "category": text(r.get("category")),
                "reason": text(r.get("comparison_reason")),
                "matchupId": text(r.get("matchup_id")),
                "_src": _src("competitive_product_news", "product_news_id", r),
            } for r in news_rows],
            "matchupIds": pair_ids.get(pid, []),
            "_src": _src("competitive_product", "product_id", row),
        })
    # facets the Products sidebar filters on: the stored columns, nothing derived
    d["productFacets"] = {}
    for row in table(database, "serving", "competitive_competitor"):
        cid = text(first_nonempty(row, "competitor_id", "company_id"))
        if cid:
            d["productFacets"][cid] = {
                "country": text(row.get("origin_country")),
                "revenueTier": text(row.get("revenue_tier")),
            }


# client_product columns shown as "Product details" rows: (column, label). Labels are chrome.
CLIENT_DETAIL_COLUMNS = (
    ("model_code", "Model code"), ("product_family", "Product family"), ("subcategory", "Subcategory"),
    ("technology", "Technology"), ("status", "Status"), ("market_availability", "Market availability"),
    ("prime_rating", "Prime rating"), ("standby_rating", "Standby rating"), ("fuel_type", "Fuel type"),
)


def build_client_products(database, matchups):
    """client_product (+ _specification, _program, _source) = KSSL's own catalogue."""
    specs = _by(table(database, "serving", "client_product_specification"), "client_product_id")
    programs = _by(table(database, "serving", "client_product_program"), "client_product_id")
    sources = _by(table(database, "serving", "client_product_source"), "client_product_id")
    pair_ids: dict[str, list[str]] = defaultdict(list)
    for mid, m in matchups.items():
        if m["clientProductId"]:
            pair_ids[m["clientProductId"]].append(mid)

    out = []
    for row in table(database, "serving", "client_product"):
        pid = text(row.get("client_product_id"))
        if not pid:
            continue
        spec_rows = sorted(specs.get(pid, []), key=lambda r: (r.get("display_order") or 0))
        details = []
        for col, label in CLIENT_DETAIL_COLUMNS:
            if row.get(col) not in (None, ""):
                details.append({"label": label, "value": text(row.get(col)), "unit": ""})
        power = _shown(row.get("rated_power_value"))
        if power is not None:
            details.append({"label": "Rated power", "value": power, "unit": text(row.get("rated_power_unit"))})
        freq = _shown(row.get("frequency_hz"))
        if freq is not None:
            details.append({"label": "Frequency", "value": freq, "unit": "Hz"})
        out.append({
            "id": pid,
            "name": text(row.get("product_name")),
            "category": text(row.get("category")),
            "details": details,
            "specs": [{
                "id": text(r.get("specification_id")),
                "label": text(r.get("spec_name")),
                "value": _val(r, "value_text", "value_numeric") or "",
                "unit": text(r.get("unit")),
                "group": text(r.get("spec_group")),
                "_src": _src("client_product_specification", "specification_id", r),
            } for r in spec_rows],
            "programs": _programs_client(programs.get(pid, [])),
            "sources": [{
                "id": text(r.get("source_id")),
                "label": text(r.get("source_label")),
                "url": text(r.get("source_url")),
                "type": text(r.get("source_type")),
                "date": text(r.get("published_date")),
            } for r in sources.get(pid, [])],
            "matchupIds": pair_ids.get(pid, []),
            "_src": _src("client_product", "client_product_id", row),
        })
    return out


def build(database, d):
    matchups, pos_cats, cat_key = build_matchups(database)
    d.update({"matchups": matchups, "POS_CATS": pos_cats, "CAT_KEY": cat_key})
    for m in matchups.values():  # the maker's stored short_name (area A serves it on the competitor)
        m["compShort"] = text((d.get("competitors", {}).get(m["compId"]) or {}).get("short"))
    build_competitor_products(database, d, matchups)
    d["clientProducts"] = build_client_products(database, matchups)
