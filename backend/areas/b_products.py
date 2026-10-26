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

import os
import re
from collections import defaultdict
from typing import Any

from backend.common import slug, table, text
from backend import spec_sheet


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
    """The stored unit, once (audit 2026-10-25: spec_store keeps the unit in the value AND in `unit`, so "12,800 kg kg" was
    on screen 676 times); a value that already states a unit gets none added."""
    if value is None:
        return None
    return spec_sheet.with_unit(value, unit)


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


_LEAD_UNIT = re.compile(r"(?i)^(?:(?:under|over|up to|about|approx(?:imately)?\.?|less than|more than|at least|max(?:imum)?)\s+)?[<>~≈]?\s*[\d.,]+(?:\s*(?:-|–|to)\s*[\d.,]+)?\s*([A-Za-z/°²]+)")


def _unit_in(v: str) -> str | None:
    """the unit of a value's leading figure ("90 cm unprepared" -> "cm"), when it is a known unit"""
    m = _LEAD_UNIT.match(v or "")
    return m.group(1) if m and spec_sheet._unit_of(m.group(1)) else None


def _pair_values(comp: Any, client: Any, unit: Any, category: str, label: Any, maker: Any = None) -> tuple[Any, Any]:
    """A comparison row's two shown values: source notes out (spec_sheet.clean_text; maker = the competitor's spec_sheet.Maker, so
    "(Elbit)" after an Elbit figure goes as a citation), units standardised, and the competitor's figure
    in the client side's unit when the row stores none and the two differ ("13,000 kg" next to "12.5 t" -> "13 t")."""
    def tidy(v: Any, target: Any, mk: Any = None) -> Any:
        if v in (None, ""):
            return v
        items = []
        for i in spec_sheet.clean_text(v, mk):
            n = spec_sheet.normalise_units(i, category, text(label), target)
            target = target or _unit_in(n)         # no stored unit: the first figure's unit holds for the rest of the value
            if n not in items:                     # "90 cm; 900 mm" -> "90 cm" once both are in one unit
                items.append(n)
        return "; ".join(items) if items else None
    k = tidy(client, unit)
    return tidy(comp, unit or (_unit_in(k) if isinstance(k, str) else None), maker), k


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

    cat_of = {text(r.get("matchup_id")): text(r.get("category_code")) for r in table(database, "serving", "competitive_matchup")}
    maker_of = {text(c.get("competitor_id")): spec_sheet.Maker([c.get("display_name"), c.get("legal_name"), c.get("short_name")])
                for c in table(database, "serving", "competitive_competitor")}
    maker_by_mid = {text(r.get("matchup_id")): maker_of.get(text(r.get("competitor_id"))) for r in table(database, "serving", "competitive_matchup")}
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
            "l": re.sub(r",\s*[A-Z][\w&.-]* (?:table|sheet|page)(?=\))", "", text(row.get("spec_label"))) or None,   # "(carbine only, KSSL table)": no source in the label
            "u": row.get("unit"),
            # both sides in one unit and without source notes (owner 2026-10-25: "a centimeter is compared with a meter", sources
            # inside the figures); the numbers cn / kn the edge is computed from are untouched, the sources stay on the row (_src)
            **dict(zip(("cv", "kv"), _pair_values(_val(row, "competitor_value_text", "competitor_value_numeric"),
                                                  _val(row, "client_value_text", "client_value_numeric"),
                                                  row.get("unit"), cat_of.get(mid, ""), row.get("spec_label"), maker_by_mid.get(mid)))),
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
        # like-for-like only, and only what can be compared: a pair with no verdict is not shown -- the verdict prompt found
        # nothing comparable, or has not judged it yet (owner 2026-10-25: no "Not assessed" pairs on Product Evaluation)
        if not text(row.get("verdict")).strip():
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


def _sheet(rows: list[tuple[Any, Any, Any]], product: dict[str, Any], sub_type: Any, companies: Any, maker: Any) -> dict[str, Any]:
    """The client-facing presentation of one product (owner 2026-10-25, backend/spec_sheet.py): displayName = the name only,
    sheet = Description / Key specifications / Other specifications / Armament / Features and capabilities. Additive:
    `name`, `specs` and `features` stay as before (other pages, search and the cards read them; `name` is the join key)."""
    sheet = spec_sheet.present(rows, product.get("category"), product.get("name"), sub_type, maker)
    desc = spec_sheet.clean_description(product.get("description"), maker)
    out = {k: v for k, v in (("description", desc), *sheet.items()) if v}      # an empty section is not sent
    # a stored short name (db/setup/47, backend/product_short_name.py) wins over the rule (owner 2026-10-26)
    return {"displayName": product.get("short") or spec_sheet.display_name(product.get("name"), companies), "sheet": out}


def _sub_types(database) -> dict[tuple[str, str], Any]:
    """product_class.sub_type by (side, product id): staging only today, so the review view has it and the live one does not;
    the armament split then falls back to the product name (spec_sheet.is_weapon_product)."""
    return {(text(r.get("product_side")), text(r.get("product_id"))): r.get("sub_type") for r in table(database, "serving", "product_class")}


def _vs_keys(database) -> dict[tuple[str, str], str]:
    """product_class sub_type (+ role) by (side, product id): what "Compare any two" pairs on (owner 2026-10-25: the versus list
    offers only products that can face the chosen one). Unknown sub_type = no key = not offered there."""
    out = {}
    for r in table(database, "serving", "product_class"):
        st = text(r.get("sub_type")).strip().lower()
        if st and st != "unknown":
            out[(text(r.get("product_side")), text(r.get("product_id")))] = "/".join(x for x in (st, text(r.get("role")).strip().lower()) if x)
    return out


def _company_names(database, d) -> Any:
    """Every company name a product name can carry ("(Hanwha Systems)", "(Thales Belgium; ...)"), as one regex."""
    names = {"KSSL", "Kalyani", "Bharat Forge", "DRDO", "BEML", "Thales Belgium", "Hanwha Systems", "Hanwha Aerospace", "Hanwha Ocean"}
    for r in table(database, "serving", "competitive_competitor"):
        names |= {text(r.get(k)) for k in ("display_name", "short_name", "legal_name")}
    for c in (d.get("competitors") or {}).values():
        names |= {text(c.get("name")), text(c.get("legal"))}
    return spec_sheet.company_re(n for n in names if n)


def _makers(database, d) -> dict[str, Any]:
    """{company id: spec_sheet.Maker} -- the company's own names, so "(Elbit)" after an Elbit figure reads as a citation."""
    short = {text(r.get("competitor_id")): text(r.get("short_name")) for r in table(database, "serving", "competitive_competitor")}
    return {cid: spec_sheet.Maker([c.get("name"), c.get("legal"), c.get("short"), short.get(cid)])
            for cid, c in (d.get("competitors") or {}).items()}


def mark_umbrellas(d, companies: Any = None) -> None:
    """Family vs variants (owner 2026-10-25: VARIANT cards only): a family card with variant cards of the same company beside
    it gets "umbrella": true and the Products grid leaves it out. Flagged, not deleted: the record, its id and its matchups
    stay in the payload. Rules: spec_sheet.umbrella_ids (the owner-review list is made by the same function)."""
    for c in (d.get("competitors") or {}).values():
        prods = c.get("products") or []
        hidden = spec_sheet.umbrella_ids(prods, companies)
        for p in prods:
            if p.get("id") in hidden:
                p["umbrella"] = True


HIDDEN_KINDS = {"test_asset", "programme", "not_product"}
_REVIEW = os.environ.get("KSSL_VIEW", "").strip().lower() == "review"


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
    sub_types, companies, makers = _sub_types(database), _company_names(database, d), _makers(database, d)
    vs_keys = _vs_keys(database)
    for row in table(database, "serving", "competitive_product"):
        pid = text(row.get("product_id"))
        cid = text(row.get("competitor_id"))
        if not pid or cid not in competitors:
            continue
        spec_rows = sorted(specs.get(pid, []), key=lambda r: text(r.get("spec_label")).lower())
        raw = [(r.get("spec_label"), r.get("spec_value"), r.get("unit")) for r in spec_rows]
        quant, qual = split_specs(raw)
        if not quant and not qual:                # user 2026-10-18: a product with no spec on record (or only "not published" notes) is not
            continue                              # listed; it shows again once a spec is stored
        if _NOT_A_PRODUCT.search(text(row.get("product_name"))):     # the workbook row says it is a capability / partnership, not a product
            continue
        kind = text(row.get("product_kind")) or None
        if kind in HIDDEN_KINDS and not _REVIEW:  # owner 2026-10-25: a test one-off, a programme or a non-product is not shown to
            continue                              # the client (backend/product_kind.py); the review site keeps it, tagged
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
            "kind": kind,                         # product | in_development | service | test_asset | programme | not_product | None
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
            "vs": vs_keys.get(("competitor", pid)),
            **_sheet(raw, {"name": row.get("product_name"), "category": row.get("category"), "description": row.get("description"),
                           "short": text(row.get("short_name")) or None},
                     sub_types.get(("competitor", pid)), companies, makers.get(cid)),
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
    sub_types, companies, makers = _sub_types(database), _company_names(database, d), _makers(database, d)
    vs_keys = _vs_keys(database)
    for row in table(database, "serving", "client_product"):
        pid = text(row.get("client_product_id"))
        client_id = text(row.get("client_id"))
        if not pid or client_id not in competitors:
            continue
        spec_rows = sorted(specs.get(pid, []), key=lambda r: (r.get("display_order") or 0))
        raw = [(r.get("spec_name"), _val(r, "value_text", "value_numeric"), r.get("unit")) for r in spec_rows]
        quant, qual = split_specs(raw)
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
            "vs": vs_keys.get(("client", pid)),
            **_sheet(raw, {"name": row.get("product_name"), "category": row.get("category"), "description": row.get("description"),
                           "short": text(row.get("short_name")) or None},
                     sub_types.get(("client", pid)), companies, makers.get(client_id)),
        })


def distinct_display_names(d) -> None:
    """two products of one company never share a display name: where shortening made two different names one ("SMAW"), both
    keep their stored name (owner review 2026-10-25)"""
    for co in (d.get("competitors") or {}).values():
        seen: dict[str, list] = defaultdict(list)
        for p in co.get("products") or []:
            if isinstance(p, dict) and p.get("displayName"):
                seen[p["displayName"].casefold()].append(p)
        for same in seen.values():
            if len({text(p.get("name")) for p in same}) > 1:
                for p in same:
                    p["displayName"] = p.get("name")


def build(database, d):
    matchups, pos_cats, cat_key = build_matchups(database)
    d.update({"matchups": matchups, "POS_CATS": pos_cats, "CAT_KEY": cat_key})
    build_competitor_products(database, d, matchups)
    build_client_products(database, d, matchups)
    mark_umbrellas(d, _company_names(database, d))
    distinct_display_names(d)
    short = {text(p.get("id")): p.get("displayName") for co in (d.get("competitors") or {}).values()
             for p in co.get("products") or [] if isinstance(p, dict) and p.get("displayName")}
    for m in matchups.values():                  # the short names the Products page shows (display only; comp / bf stay the keys)
        m["compName"] = short.get(text(m.get("compProductId")))
        m["bfName"] = short.get(text(m.get("clientProductId")))
    d["KSSL_CATS"] = sorted({r.get("category") for r in table(database, "serving", "client_product") if r.get("category")},
                            key=lambda c: c.lower())


def _selftest_pairs() -> None:
    assert _pair_values("1.2 m", "90 cm", None, "Protected & Armoured Vehicles", "Fording") == ("120 cm", "90 cm")   # one unit per row
    assert _pair_values("13,000 kg", "12.5 t", None, "Artillery", "Weight") == ("13 t", "12.5 t")
    assert _pair_values("18 t (Army Recognition 2024)", "12.5 t", "t", "Artillery", "Weight")[0] == "18 t"          # no source note
    assert _pair_values(None, "6 to 8", None, "Artillery", "Crew") == (None, "6 to 8")
    assert _pair_values("13,000 kg", "Under 15 t", None, "Artillery", "Weight")[0] == "13 t"                   # "Under 15 t" sets t
    assert _pair_values("1.2 m unprepared", "90 cm; 900 mm", None, "Protected & Armoured Vehicles", "Fording depth") ==         ("120 cm unprepared", "90 cm")


def _selftest() -> None:
    _selftest_pairs()
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
    assert split_specs([("GVW", "12,800 kg", "kg"), ("Range", "48", "km")])[0] == {"GVW": "12,800 kg", "Range": "48 km"}   # the unit once
    spec_sheet._selftest()                     # the spec sheet presenter: units, labels, sections, display names, families
    fam = {"id": "f", "name": "F-35 Lightning II (F-35A / F-35B / F-35C)", "category": "Aircraft & Aerostructures",
           "description": "Program/common-systems row for the F-35 family"}
    d = {"competitors": {"lm": {"products": [fam] + [{"id": v, "name": f"F-35{v} Lightning II", "category": "Aircraft & Aerostructures"} for v in "ABC"]}}}
    mark_umbrellas(d)
    assert [p.get("umbrella") for p in d["competitors"]["lm"]["products"]] == [True, None, None, None]
    print("b_products self-check ok")


if __name__ == "__main__":
    _selftest()                                  # python -m backend.areas.b_products [--selftest]
