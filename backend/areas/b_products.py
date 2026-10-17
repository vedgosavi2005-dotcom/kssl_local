"""Area B: Products (competitor + client catalogues, specs, programmes, product news) and Product Evaluation
(competitive_matchup*). Gap Analysis is hidden by decision (ui.section_visibility).

Shapes follow docs/ui_port/MAPPING.md section A (competitors[cid].products, matchups, POS_CATS, CAT_KEY, KSSL_CATS).
Runs after area A (reads d["competitors"]).

Everything is served as stored; nothing is defaulted. Evaluation uses competitive_matchup* (not
competitive_product_evaluation*). Edge / parity values are STORED columns (a loader computes them from the
prompt's per-spec better_side); the browser only presents them.

Vocabularies the UI expects (stored values are passed through, compared case-insensitively):
  competitive_matchup_specification.better_side   client | competitor | equal   (NULL = not judged)
  competitive_matchup_specification.comparability_state   comparable | one_sided | not_comparable
  competitive_matchup_advantage.side              client | competitor
  competitive_matchup_specification.gap_value     unsigned percent, abs(client - competitor) / mean * 100
  competitive_matchup.edge_score                  0-100, 50 = parity, higher = the client stronger
"""

from collections import defaultdict
from typing import Any

from backend.common import slug, table, text


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


def _with_unit(value: str | None, unit: Any) -> str | None:
    if value is None:
        return None
    return f"{value} {unit}" if unit not in (None, "") else value


def _src(tbl: str, key: str, row: dict[str, Any]) -> dict[str, Any]:
    return {"t": tbl, "k": key, "id": text(row.get(key))}


def _by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        k = text(row.get(key))
        if k:
            grouped[k].append(row)
    return grouped


def _hi(better_side: Any, cn: Any, kn: Any) -> bool | None:
    """Is a higher value better on this spec? Read off the stored better_side and the two stored numbers:
    True when the better side has the larger number, False when it has the smaller; None when unjudged or equal."""
    side = text(better_side).lower()
    if side not in ("client", "competitor") or cn is None or kn is None or cn == kn:
        return None
    better, worse = (kn, cn) if side == "client" else (cn, kn)
    return better > worse


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
            advantages[mid][side].append(row.get("advantage_text"))

    specs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    spec_rows = sorted(
        table(database, "serving", "competitive_matchup_specification"),
        key=lambda r: (r.get("display_order") or 0),
    )
    for row in spec_rows:
        mid = text(row.get("matchup_id"))
        if not mid:
            continue
        cn, kn = row.get("competitor_value_numeric"), row.get("client_value_numeric")
        specs[mid].append({
            "l": row.get("spec_label"),
            "u": row.get("unit"),
            "cv": _val(row, "competitor_value_text", "competitor_value_numeric"),
            "kv": _val(row, "client_value_text", "client_value_numeric"),
            "cn": cn,
            "kn": kn,
            "hi": _hi(row.get("better_side"), cn, kn),
            # kept on the row for the edge-basis and parity chips
            "group": row.get("spec_group"),
            "win": row.get("better_side"),
            "gap": row.get("gap_value"),
            "state": row.get("comparability_state"),
            "_src": _src("competitive_matchup_specification", "comparison_specification_id", row),
        })

    matchups = {}
    categories = {}
    for row in table(database, "serving", "competitive_matchup"):
        mid = text(row.get("matchup_id"))
        if not mid:
            continue
        category = row.get("category_code")
        if category not in (None, ""):
            categories[slug(category)] = category
        adv = advantages.get(mid, {"client": [], "competitor": []})
        comp_name = row.get("competitor_name")
        comp_product = row.get("competitor_product_name")
        matchups[mid] = {
            "id": mid,
            "cat": category,
            "catKey": slug(category) if category not in (None, "") else None,
            "comp": " · ".join(str(x) for x in (comp_name, comp_product) if x not in (None, "")) or None,
            "compBy": comp_name,
            "bf": row.get("client_product_name"),
            "anchor": row.get("client_product_name"),
            "country": row.get("competitor_country"),
            "reason": row.get("match_basis"),
            "verdictH": row.get("verdict_headline"),
            "verdict": row.get("verdict"),
            "edge": row.get("edge_score"),
            "specDims": row.get("comparable_spec_count"),
            "specDecided": row.get("sourced_spec_count"),
            "specs": specs.get(mid, []),
            "advBf": adv["client"],
            "advComp": adv["competitor"],
            "compId": text(row.get("competitor_id")) or None,
            "compProductId": text(row.get("competitor_product_id")) or None,
            "clientProductId": text(row.get("client_product_id")) or None,
            "_src": _src("competitive_matchup", "matchup_id", row),
        }
    pos_cats = [[key, label] for key, label in sorted(categories.items(), key=lambda item: item[1].lower())]
    return matchups, pos_cats, {label: key for key, label in categories.items()}  # CAT_KEY: label -> key, as MatchupList reads it


def _programs_competitor(rows):
    return [{
        "id": text(r.get("program_id")),
        "title": r.get("program_title"),
        "authority": r.get("authority"),
        "date": r.get("program_date"),
        "status": r.get("status"),
        "statusColor": r.get("status_color"),
        "description": r.get("description"),
        "_src": _src("competitive_product_program", "program_id", r),
    } for r in rows]


def _programs_client(rows):
    return [{
        "id": text(r.get("program_id")),
        "title": r.get("program_name"),
        "authority": r.get("owner"),
        "status": r.get("status"),
        "date": r.get("start_date"),
        "description": r.get("description"),
        "_src": _src("client_product_program", "program_id", r),
    } for r in rows]


def _first_matchup(ids: list[str]) -> str | None:
    return ids[0] if ids else None


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
    for row in table(database, "serving", "competitive_product"):
        pid = text(row.get("product_id"))
        cid = text(row.get("competitor_id"))
        if not pid or cid not in competitors:
            continue
        spec_rows = sorted(specs.get(pid, []), key=lambda r: text(r.get("spec_label")).lower())
        news_rows = sorted(news.get(pid, []), key=lambda r: text(r.get("published_date")), reverse=True)
        urls = []
        for r in spec_rows:
            if r.get("source_url") and r.get("source_url") not in urls:
                urls.append(r.get("source_url"))
        competitors[cid]["products"].append({
            "id": pid,
            "cid": cid,
            "name": row.get("product_name"),
            "category": row.get("category"),
            "country": row.get("country"),
            "specs": {r.get("spec_label"): _with_unit(r.get("spec_value"), r.get("unit"))
                      for r in spec_rows if r.get("spec_label")},
            "source": None,
            "source_url": urls[0] if urls else None,
            "sources": urls,
            "tier": None,
            "programs": _programs_competitor(programs.get(pid, [])),
            "news": [{
                "id": text(r.get("product_news_id")),
                "title": r.get("headline"),
                "url": r.get("article_url"),
                "date": r.get("published_date"),
                "source": r.get("publisher"),
                "category": r.get("category"),
                "reason": r.get("comparison_reason"),
                "matchupId": text(r.get("matchup_id")) or None,
                "_src": _src("competitive_product_news", "product_news_id", r),
            } for r in news_rows],
            "matchupId": _first_matchup(pair_ids.get(pid, [])),
            "matchupIds": pair_ids.get(pid, []),
            "_src": _src("competitive_product", "product_id", row),
        })


def build_client_products(database, d, matchups):
    """client_product (+ _specification, _program, _source) = the client's own catalogue, on the client row."""
    specs = _by(table(database, "serving", "client_product_specification"), "client_product_id")
    programs = _by(table(database, "serving", "client_product_program"), "client_product_id")
    sources = _by(table(database, "serving", "client_product_source"), "client_product_id")
    pair_ids: dict[str, list[str]] = defaultdict(list)
    for mid, m in matchups.items():
        if m["clientProductId"]:
            pair_ids[m["clientProductId"]].append(mid)

    competitors = d.get("competitors", {})
    for row in table(database, "serving", "client_product"):
        pid = text(row.get("client_product_id"))
        client_id = text(row.get("client_id"))
        if not pid or client_id not in competitors:
            continue
        spec_rows = sorted(specs.get(pid, []), key=lambda r: (r.get("display_order") or 0))
        src_rows = sources.get(pid, [])
        urls = [s.get("source_url") for s in src_rows if s.get("source_url")]
        competitors[client_id]["products"].append({
            "id": pid,
            "cid": client_id,
            "name": row.get("product_name"),
            "category": row.get("category"),
            "country": None,
            "specs": {r.get("spec_name"): _with_unit(_val(r, "value_text", "value_numeric"), r.get("unit"))
                      for r in spec_rows if r.get("spec_name")},
            "source": src_rows[0].get("source_label") if src_rows else None,
            "source_url": urls[0] if urls else None,
            "sources": urls,
            "tier": src_rows[0].get("source_type") if src_rows else None,
            "programs": _programs_client(programs.get(pid, [])),
            "news": [],
            "matchupId": _first_matchup(pair_ids.get(pid, [])),
            "matchupIds": pair_ids.get(pid, []),
            "_src": _src("client_product", "client_product_id", row),
        })


def build(database, d):
    matchups, pos_cats, cat_key = build_matchups(database)
    d.update({"matchups": matchups, "POS_CATS": pos_cats, "CAT_KEY": cat_key})
    build_competitor_products(database, d, matchups)
    build_client_products(database, d, matchups)
    d["KSSL_CATS"] = sorted({r.get("category") for r in table(database, "serving", "client_product") if r.get("category")},
                            key=lambda c: c.lower())
