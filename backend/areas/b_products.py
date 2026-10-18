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
  competitive_matchup_advantage.kind              compared -> advBf / advComp (▲); stated -> advBfQ / advCompQ (◆)
  competitive_matchup_specification.gap_value     unsigned percent, abs(client - competitor) / mean * 100
  competitive_matchup.edge_score                  0-100, 50 = parity, higher = the client stronger
"""

import re
from collections import defaultdict
from typing import Any

from backend.common import slug, table, text


_STATUS_IN_NAME = re.compile(r"develop|prototype|concept|trial|retired|cancel|terminat", re.I)


def _status(row: dict[str, Any]) -> str | None:
    """The lifecycle status for the brackets after the name (prompts/product_status.yml); None when the name already says it."""
    s = row.get("status")
    return s if s and not _STATUS_IN_NAME.search(text(row.get("product_name"))) else None


# ---- spec rows: quantitative (the Technical specifications table) vs qualitative (Features and capabilities, below it) ----------
# User 2026-10-18: the tech-spec table holds measured figures; a descriptive spec goes below it; "not published" lines are not specs.
# A display split of the stored rows: nothing is changed in the database.
_NOTE = re.compile(r"\bnot (?:given|disclosed|published|stated|released|available|public(?:ly)?|specified|provided|found|read)\b|\bundisclosed\b"
                   r"|\bunpublished\b|\bno (?:official |public )?(?:specifications?|specs?|figures?|data|numbers?) (?:published|given|disclosed|available)\b", re.I)
_EXTRA_UNITS = ("rounds/min", "rds/min", "rounds per minute", "rpm", "x", "mp", "db", "dbm", "hz", "khz", "mhz", "ghz", "w", "v", "vdc", "ah", "kwh",
                "l", "litre", "litres", "liter", "liters", "bar", "psi", "kn", "nm", "j", "kj", "moa", "mrad", "°", "°c", "rounds", "shots", "m2", "m3",
                "m²", "m³", "km²", "ton", "tons", "tonnes", "cu in", "cc", "gb", "tb", "mbps", "kbps", "lux", "g", "c")


def _unit_re() -> re.Pattern:
    from prompts.spec_values import UNITS                     # the comparison engine's unit vocabulary, plus display units
    toks = sorted({u for u in (*UNITS, *_EXTRA_UNITS) if u}, key=len, reverse=True)
    return re.compile(r"\d(?:[\d,.]*\d)?\s*-?\s*(?:" + "|".join(re.escape(t) for t in toks) + r")(?![a-z])", re.I)


_UNIT_RE = None
_MACH = re.compile(r"\bmach\s*\d", re.I)
_NOT_A_PRODUCT = re.compile(r"no confirmed (?:\w+ ){0,2}(?:model|product)|platform partnership", re.I)   # e.g. "Small Arms (licensed capability - no confirmed model)"
_CALIBRE_LABEL = re.compile(r"calib(?:re|er)|cartridge|ammunition type", re.I)
_NOT_TECH_LABEL = re.compile(r"contract|order|programme|program\b|delivery|deliveries|history|introduced|in service|timing|customer|"
                             r"operator|user|price|cost|value|workforce|partner|production|status", re.I)   # facts about the deal, not the product
_BARE_NUM = re.compile(r"^[~<>≈≤≥+±-]?\s*\d[\d,.]*(?:\s*(?:-|to|–)\s*\d[\d,.]*)?\s*$")


def spec_kind(label: Any, value: Any, unit: Any = None) -> tuple[str, str | None]:
    """('quant' | 'qual' | 'note', value to show). A clause stating that a figure is not published is dropped; nothing left = note."""
    global _UNIT_RE
    _UNIT_RE = _UNIT_RE or _unit_re()
    keep = [c.strip() for c in re.split(r";\s*", str(value or "")) if c.strip() and not _NOTE.search(c)]
    if not keep or _NOTE.search(str(label or "")) and not any(_UNIT_RE.search(c) for c in keep):
        return "note", None
    v = "; ".join(keep)
    if _NOT_TECH_LABEL.search(str(label or "")):
        return "qual", v
    if (_UNIT_RE.search(v if not unit else f"{v} {unit}") or _MACH.search(v) or (_CALIBRE_LABEL.search(str(label or "")) and re.search(r"\d", v))
            or (_BARE_NUM.match(v) and (unit or not re.search(r"[a-z]", v, re.I)))):
        return "quant", v
    return "qual", v


def split_specs(rows: list[tuple[Any, Any, Any]]) -> tuple[dict, dict]:
    """[(label, value, unit)] -> ({label: value with unit} quantitative, {label: value} qualitative); bullet marks dropped from labels."""
    quant, qual = {}, {}
    for label, value, unit in sorted(rows, key=lambda r: (str(r[0] or ""), str(r[1] or ""))):   # fixed order: both sites show the same
        lab = re.sub(r"^[\s•·*-]+", "", str(label or "")).strip()
        k, v = spec_kind(lab, value, unit)
        if not lab or k == "note":
            continue
        out, val = (quant, _with_unit(v, unit)) if k == "quant" else (qual, v)
        out[lab] = f"{out[lab]}; {val}" if lab in out and val not in out[lab] else out.get(lab, val)   # a repeated label ("Note") keeps every value
    return quant, qual


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
    # ▲ compared leads (kind compared / NULL) and ◆ stated capabilities (kind stated), both written by the matchup prompt only
    advantages: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"client": [], "competitor": [], "client_q": [], "competitor_q": []})
    adv_rows = sorted(
        table(database, "serving", "competitive_matchup_advantage"),
        key=lambda r: (r.get("display_order") or 0),
    )
    for row in adv_rows:
        mid = text(row.get("matchup_id"))
        side = text(row.get("side")).strip().lower()
        if mid and side in ("client", "competitor") and row.get("advantage_text"):
            q = "_q" if text(row.get("kind")).strip().lower() == "stated" else ""
            advantages[mid][side + q].append(row.get("advantage_text"))

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
        # like-for-like only, and only what can be compared: a pair with no comparable spec and no verdict text is not shown
        if not (row.get("comparable_spec_count") or 0) and not row.get("verdict"):
            continue
        category = row.get("category_code")
        if category not in (None, ""):
            categories[slug(category)] = category
        adv = advantages.get(mid, {"client": [], "competitor": [], "client_q": [], "competitor_q": []})
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
            "decision": row.get("decision_level"),   # stored 1 behind / 2 near parity / 3 ahead (ui.code_label); the UI sets no cut-offs
            "specDims": row.get("comparable_spec_count"),
            "specDecided": row.get("sourced_spec_count"),
            "specs": specs.get(mid, []),
            "advBf": adv["client"],
            "advComp": adv["competitor"],
            "advBfQ": adv["client_q"],
            "advCompQ": adv["competitor_q"],
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
        quant, qual = split_specs([(r.get("spec_label"), r.get("spec_value"), r.get("unit")) for r in spec_rows])
        if not quant and not qual:                # user 2026-10-18: a product with no spec on record (or only "not published" notes) is not
            continue                              # listed; it shows again once a spec is stored
        if _NOT_A_PRODUCT.search(text(row.get("product_name"))):     # the workbook row says it is a capability / partnership, not a product
            continue
        news_rows = sorted(news.get(pid, []), key=lambda r: text(r.get("published_date")), reverse=True)
        urls = []
        for r in spec_rows:
            if r.get("source_url") and r.get("source_url") not in urls:
                urls.append(r.get("source_url"))
        competitors[cid]["products"].append({
            "id": pid,
            "cid": cid,
            "name": row.get("product_name"),
            "description": row.get("description"),
            "status": _status(row),
            "category": row.get("category"),
            "country": row.get("country"),
            "specs": quant,                       # measured figures only (Technical specifications)
            "features": qual,                     # descriptive specs (Features and capabilities, below the table)
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
        quant, qual = split_specs([(r.get("spec_name"), _val(r, "value_text", "value_numeric"), r.get("unit")) for r in spec_rows])
        if not quant and not qual:                # the same rule for the client's own catalogue (user 2026-10-18)
            continue
        src_rows = sources.get(pid, [])
        urls = [s.get("source_url") for s in src_rows if s.get("source_url")]
        competitors[client_id]["products"].append({
            "id": pid,
            "cid": client_id,
            "name": row.get("product_name"),
            "description": row.get("description"),
            "status": _status(row),
            "category": row.get("category"),
            "country": None,
            "specs": quant,
            "features": qual,
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


def _selftest() -> None:
    cases = [("Numeric range/weight/accuracy", "not given in primary sources read (secondary reports quote different figures, not used)", None, "note"),
             ("Type", "bolt-on guidance/wing kit for unguided warheads", None, "qual"), ("Range", "250-350 km (CSIS)", None, "quant"),
             ("Search sector", "120", None, "quant"), ("Radar", "ELM-2022/2025 Multi-Mission Radar integrated with IFF", None, "qual"),
             ("Platform", "Bombardier Challenger 650", None, "qual"), ("Max speed", "Towed 70 kmph; Self-propelled 5 kmph", None, "quant"),
             ("Weight", "4.2", "t", "quant"), ("Note", "Weight, payload, speed and range not published", None, "note"),
             ("Rate of fire", "600-800 rds/min", None, "quant"), ("Calibre", "155 mm/52 cal", None, "quant"),
             ("Operating temperature", "-55 C to +85 C", None, "quant"), ("Speed", "up to ~Mach 2.8 (official)", None, "quant"),
             ("Calibre", ".338 Lapua Magnum", None, "quant"), ("Transmission", "Allison 3200SP", None, "qual")]
    for label, value, unit, want in cases:
        assert spec_kind(label, value, unit)[0] == want, (label, value, spec_kind(label, value, unit))
    assert spec_kind("Warhead", "blast fragmentation (MBDA); mass not disclosed") == ("qual", "blast fragmentation (MBDA)")
    assert split_specs([("• Range", "30 km", None), ("Type", "towed", None), ("Note", "not published", None)]) == ({"Range": "30 km"}, {"Type": "towed"})
    assert split_specs([("Note", "Round 200 g", None), ("Note", "Length 146 mm", None)])[0] == {"Note": "Length 146 mm; Round 200 g"}
    print("b_products self-check ok")


if __name__ == "__main__":
    _selftest()
