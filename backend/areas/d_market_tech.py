"""Area D: Market (tenders, top opportunity, global requirements, awards, market cards) and Technology
(innovations, categories, patent-field meta).

Shapes follow docs/ui_port/MAPPING.md section A (tenders, tpAllCountries, tpAllCats, topOpportunities, awards,
marketCards + details, globalRequirements, innovations, techCats, techAreaMeta). Every value is a stored column;
nothing is defaulted. Numbers are served as numbers, dates as ISO strings, missing values as None. No currency is
ever converted (ruling R9): a tender / award value ships as its stored amount, currency and text.

Enumerations the UI expects (stored text, compared case-insensitively; unknown values are shown as stored):
  market_tender.status          open | closing | awarded | closed   (awarded / closed decide the Awarded / Closed
                                tabs; every other value is an open tender)
  market_tender.lean_code       go | maybe | pass | won | closed    (colour of the bid-assessment band only)
  market_tender.kssl_fit,       strong | partial | weak             (shipped as stored, fields fit and clientFit)
   *.kssl_fit, fit_grade, fit_label
  market_tender.url_kind        notice | portal | award             (label of the "open the tender" button)
  market_tender_product_match_line.line_label   up | down           (loader convention)
  technology_innovation.maturity           free text; lab | dev | prod | fielded only pick a chip colour
  technology_innovation.client_position    behind | parity | ahead (chip colour; the words shown are position_label)
"""

from collections import defaultdict

from backend.common import first_nonempty, slug, table, text


def group(rows, key):
    out = defaultdict(list)
    for row in rows:
        k = row.get(key)
        if k not in (None, ""):
            out[text(k)].append(row)
    return out


def ordered(rows, *keys):
    """Stable sort on the first key present on each row; rows with no value go last."""
    def k(row):
        for name in keys:
            v = row.get(name)
            if v is not None:
                return (0, v)
        return (1, 0)
    return sorted(rows, key=k)


def src(tbl, key, value):
    return {"t": tbl, "k": key, "id": text(value)}


def clean(values):
    return [v for v in values if v not in (None, "")]


def _latest(rows, key):
    return sorted(rows, key=lambda r: text(r.get(key)))[-1:] or [{}]


# ---------------------------------------------------------------- tenders

def build_tenders(database):
    s = "serving"
    windows = group(table(database, s, "market_tender_closing_window"), "tender_id")
    fits = group(table(database, s, "market_tender_fit_assessment"), "tender_id")
    comps = group(table(database, s, "market_tender_competitor_fit"), "tender_id")
    matches = group(table(database, s, "market_tender_product_match"), "tender_id")
    lines = group(table(database, s, "market_tender_product_match_line"), "tender_match_id")
    reqs = group(table(database, s, "market_tender_requirement"), "tender_id")
    sources = group(table(database, s, "market_tender_source"), "tender_id")
    moves = group(table(database, s, "market_next_move"), "tender_id")
    elig = group(table(database, s, "market_tender_eligibility"), "tender_id")

    tenders = []
    for row in table(database, s, "market_tender"):
        tid = text(row.get("tender_id"))
        if not tid:
            continue
        window = _latest(windows.get(tid, []), "as_of_date")[0]
        fit = _latest(fits.get(tid, []), "assessed_at")[0]

        req = []
        for r in ordered(reqs.get(tid, []), "display_order"):
            quantity = r.get("quantity")
            # row key = the source column name (a code the UI maps to its chrome words), or the stored
            # scope_bullet_label; the backend writes no English label (ruling R12)
            req.extend([list(p) for p in [
                ("description", r.get("description")),
                ("scope_text", r.get("scope_text")),
                ("requirement_note", r.get("requirement_note")),
                ("equipment_scope", r.get("equipment_scope")),
                ("rating_band", r.get("rating_band")),
                ("use_case", r.get("use_case")),
                ("quantity", " ".join(clean([text(quantity) if quantity is not None else "", r.get("quantity_unit")])) or None),
                (r.get("scope_bullet_label"), r.get("scope_bullet_value")),
                ("category_text", r.get("category_text")),
                ("source_text", r.get("source_text")),
            ] if p[1]])
        closing = first_nonempty(row, "closing_date") or window.get("closing_date")
        if row.get("published_date"):
            req.append(["published_date", row.get("published_date")])
        if closing:
            req.append(["closing_date", closing])

        product_matches = []
        for m in ordered(matches.get(tid, []), "display_order"):
            pct = m.get("fit_percent")
            product_matches.append({
                "n": m.get("match_label"),
                "fit": m.get("fit_grade"),
                "pct": None if pct is None else f"{int(pct) if pct == int(pct) else pct}%",
                "lines": [[l.get("line_label"), l.get("line_value")]
                          for l in ordered(lines.get(text(m.get("tender_match_id")), []), "display_order")],
                "_src": src("market_tender_product_match", "tender_match_id", m.get("tender_match_id")),
            })

        competitor_fit = [
            {
                "company": c.get("competitor_name"),
                "products": clean([first_nonempty(c, "competitor_product_display", "competitor_products_text")]),
                "fit": c.get("fit_label"),
                "basis": c.get("basis"),
                "why": c.get("fit_rationale"),
                "_src": src("market_tender_competitor_fit", "competitor_fit_id", c.get("competitor_fit_id")),
            }
            for c in ordered(comps.get(tid, []), "rank_position")
        ]

        srcs = []
        for sr in sorted(sources.get(tid, []), key=lambda x: not x.get("is_primary")):
            srcs.append({
                "label": first_nonempty(sr, "portal_name", "publisher"),
                "url": sr.get("source_url"),
                "_src": src("market_tender_source", "source_id", sr.get("source_id")),
            })

        actions = [{"do": m.get("action_text"), "due": m.get("due_date")} for m in ordered(moves.get(tid, []), "sequence")]
        kssl_fit = first_nonempty(row, "kssl_fit") or fit.get("kssl_fit")
        revenue_text = first_nonempty(row, "expected_revenue_text") or fit.get("revenue_estimate_text")
        quantity = row.get("quantity")
        tenders.append({
            "id": tid,
            "_src": src("market_tender", "tender_id", tid),
            "title": first_nonempty(row, "title", "title_localized"),
            "issuer": first_nonempty(row, "issuer_display", "buyer_name"),
            "country": row.get("country_name"),
            "cat": row.get("category_text"),
            "value": row.get("value_text"),
            "valueAmount": row.get("value_amount"),
            "valueCurrency": str(row.get("value_currency")).strip() if row.get("value_currency") else None,
            "qty": " ".join(clean([text(quantity) if quantity is not None else "", row.get("quantity_unit")])) or None,
            "deadline": closing,
            "closingDate": closing,
            "posted": row.get("published_date"),
            "status": row.get("status"),
            "urlKind": row.get("url_kind"),
            "url": row.get("source_url"),
            "srcs": srcs,
            "desc": row.get("description"),
            "req": req,
            "matches": product_matches,
            "rank": row.get("rank_position"),
            "fit": kssl_fit,
            "clientFit": kssl_fit,
            "revenueEstimate": revenue_text,
            "expectedRevenue": revenue_text,
            "lean": row.get("lean_code"),
            "leanTxt": row.get("lean_text"),
            "competitorFit": competitor_fit,
            "actions": actions,
            "milestone": first_nonempty(window, "milestone_text") or row.get("latest_milestone"),
            # prompt rebuild v2 (scores are anchored 1-5 judgements; the label is computed by code, rule version p1)
            "pursue": fit.get("pursue_label"),
            "attractiveness": fit.get("attractiveness"),
            "ability": fit.get("ability"),
            "valueScore": fit.get("value_score"),
            "strategicScore": fit.get("strategic_score"),
            "timeToAward": fit.get("time_to_award"),
            "fitPercent": fit.get("fit_score"),
            "eligibility": [
                {"item": e.get("item"), "state": e.get("state"), "fixable": e.get("fixable"), "note": e.get("note"),
                 "_src": src("market_tender_eligibility", "eligibility_id", e.get("eligibility_id"))}
                for e in ordered(elig.get(tid, []), "display_order")
            ],
            "awardedTo": row.get("awarded_to"),
            "awardDate": row.get("award_date"),
            "awardValue": row.get("award_value_text"),
        })
    return tenders


# ---------------------------------------------------------------- global requirements

def build_requirements(database):
    specs = group(table(database, "serving", "market_global_requirement_specification"), "requirement_id")
    sources = group(table(database, "serving", "market_global_requirement_source"), "requirement_id")
    result = []
    for row in table(database, "serving", "market_global_requirement"):
        rid = text(row.get("requirement_id"))
        if not rid:
            continue
        result.append({
            "id": rid,
            "_src": src("market_global_requirement", "requirement_id", rid),
            "title": row.get("title"),
            "buyer": row.get("buyer_name"),
            "country": row.get("country_name"),
            "region": row.get("region"),
            "cat": row.get("category"),
            "value": row.get("value_text"),
            "dl": row.get("days_remaining"),
            "deadline": row.get("deadline"),
            "stageDate": row.get("stage_date"),
            "status": row.get("status"),
            "desc": row.get("description"),
            "ksslFit": row.get("kssl_fit"),
            "ksslModel": row.get("kssl_model"),
            "strategicAssessment": row.get("strategic_assessment"),
            "specs": [[s.get("spec_label"), s.get("spec_value")] for s in ordered(specs.get(rid, []), "display_order")],
            "sources": [
                {"label": s.get("source_label"), "url": s.get("source_url"), "type": s.get("source_type")}
                for s in ordered(sources.get(rid, []), "display_order")
            ],
        })
    return result


def _join(parts, sep=" · "):
    return sep.join(str(p) for p in parts if p not in (None, "")) or None


def build_market_cards(database, requirements, details):
    """marketCards: one card per global requirement + one per pipeline / demand update (tender cards are built in
    the browser from tenders). Detail panels land in details[card id]."""
    cards = []
    for r in requirements:
        srcs = [{"label": s["label"], "url": s["url"]} for s in r["sources"] if s["url"]]
        cid = "req-" + r["id"]   # card / details id: prefixed per source table; _src.id stays the raw key
        cards.append({
            "id": cid,
            "dir": None,
            "title": r["title"],
            "meta": _join([r["cat"], r["region"], r["deadline"]]),
            "sowhat": r["strategicAssessment"],
            "ago": r["stageDate"],   # the card date is the stored date of the current stage; the deadline (future) stays in meta
            "url": srcs[0]["url"] if srcs else None,
            "_src": r["_src"],
        })
        details[cid] = {
            "id": cid, "dir": None, "title": r["title"],
            "facts": [list(s) for s in r["specs"]],
            "what": r["desc"], "why": r["strategicAssessment"], "lens": [],
            "url": srcs[0]["url"] if srcs else None, "srcs": srcs, "provenance": None, "image": None,
            "ksslImpact": None, "ksslImpactKind": None, "eyebrow": None, "suggest": [],
            "_src": r["_src"],
        }
    opps = {text(o.get("opportunity_id")): o for o in table(database, "serving", "market_opportunity")}
    opp_sources = group(table(database, "serving", "market_opportunity_source"), "opportunity_id")
    categories = {text(o.get("option_code")): o.get("option_label")
                  for o in table(database, "serving", "market_filter_option") if text(o.get("filter_type")).lower() == "category"}
    for u in ordered(table(database, "serving", "market_opportunity_update"), "update_date"):
        raw_uid = text(u.get("update_id"))
        uid = "upd-" + raw_uid if raw_uid else ""
        oid = text(u.get("opportunity_id"))
        opp = opps.get(oid)
        if not uid or opp is None:
            continue
        card_src = src("market_opportunity", "opportunity_id", oid)
        srcs = [{"label": first_nonempty(x, "source_title", "publisher"), "url": x.get("source_url")}
                for x in opp_sources.get(oid, []) if x.get("source_url")]
        cards.append({
            "id": uid,
            "dir": None,
            # what the card IS (it comes from the opportunity pipeline), not a stance; the Perceived
            # Opportunities tile and lane select on it. tags: the stored category label.
            "kind": "opportunity",
            "tags": categories.get(text(opp.get("category_id"))),
            "title": u.get("headline"),
            "meta": _join([u.get("update_type"), opp.get("location_text"), categories.get(text(opp.get("category_id"))),
                           u.get("update_date")]),
            "sowhat": u.get("narrative"),
            "ago": u.get("update_date"),
            "url": srcs[0]["url"] if srcs else None,
            "_src": card_src,
        })
        details[uid] = {
            "id": uid, "dir": None, "title": u.get("headline"), "facts": [],
            "what": u.get("narrative"), "why": None, "lens": [],
            "url": srcs[0]["url"] if srcs else None, "srcs": srcs, "provenance": None, "image": None,
            "ksslImpact": None, "ksslImpactKind": None, "eyebrow": None, "suggest": [],
            "_src": card_src,
        }
    return cards


# ---------------------------------------------------------------- awards

def build_awards(database):
    return [{
        "id": text(r.get("award_id")),
        "segment": r.get("segment"),
        "winner": r.get("winner"),
        "brand": r.get("brand"),
        "buyer": r.get("buyer"),
        "site": r.get("site"),
        "title": r.get("title"),
        "title_ar": r.get("title_local"),
        "programme": r.get("programme"),
        "tender_no": r.get("tender_number"),
        "date": r.get("award_date"),
        "year": r.get("award_year"),
        "value": r.get("value_amount"),
        "currency": r.get("value_currency"),
        "value_text": r.get("value_text"),
        "bids": r.get("bids"),
        "country": r.get("country_name"),
        "url": r.get("source_url"),
        "source": r.get("source_tier"),
        "_src": src("market_award", "award_id", r.get("award_id")),
    } for r in sorted(table(database, "serving", "market_award"),
                    key=lambda r: (r.get("award_date") is None, r.get("award_date") or "", r.get("award_id") or 0))]


# ---------------------------------------------------------------- top opportunity

def build_top_opportunities(database, tenders):
    s = "serving"
    by_tender = {t["id"]: t for t in tenders}
    opps = {text(o.get("opportunity_id")): o for o in table(database, s, "market_opportunity")}
    opp_fits = group(table(database, s, "market_opportunity_fit_assessment"), "opportunity_id")
    opp_updates = group(table(database, s, "market_opportunity_update"), "opportunity_id")
    opp_sources = group(table(database, s, "market_opportunity_source"), "opportunity_id")

    top_tenders = []
    for row in ordered(table(database, s, "market_top_opportunity_tender"), "rank_position"):
        tender = by_tender.get(text(row.get("tender_id")), {})
        top_tenders.append({
            "id": text(row.get("top_opportunity_tender_id")),
            "_src": src("market_top_opportunity_tender", "top_opportunity_tender_id", row.get("top_opportunity_tender_id")),
            "tenderId": text(row.get("tender_id")) or None,
            "rank": row.get("rank_position"),
            "title": tender.get("title"),
            "issuer": tender.get("issuer"),
            "country": tender.get("country"),
            "decides": row.get("decides"),
            "ksslFit": row.get("kssl_fit"),
            "ksslModel": row.get("kssl_model"),
            "rivalToBeat": row.get("rival_to_beat"),
            "revenue": row.get("revenue_text"),
        })

    projects = []
    for row in ordered(table(database, s, "market_top_opportunity_project"), "rank_position"):
        oid = text(row.get("opportunity_id"))
        opp = opps.get(oid, {})
        fit = _latest(opp_fits.get(oid, []), "assessed_at")[0]
        projects.append({
            "id": text(row.get("top_opportunity_project_id")),
            "_src": src("market_top_opportunity_project", "top_opportunity_project_id", row.get("top_opportunity_project_id")),
            "opportunityId": oid or None,
            "rank": row.get("rank_position"),
            "title": opp.get("title"),
            "issuer": first_nonempty(row, "buyer_name") or opp.get("buyer_name"),
            "country": row.get("country_name"),
            "stage": first_nonempty(row, "where_it_stands") or opp.get("current_status") or opp.get("stage"),
            "ksslFit": first_nonempty(row, "kssl_fit") or fit.get("fit_grade"),
            "ksslModel": first_nonempty(row, "kssl_model") or fit.get("client_model_display"),
            "rivalToBeat": first_nonempty(row, "rival_to_beat") or fit.get("rival_name"),
            "revenue": first_nonempty(row, "revenue_text") or fit.get("revenue_display"),
            "updates": [
                {"date": u.get("update_date"), "type": u.get("update_type"), "headline": u.get("headline"),
                 "narrative": u.get("narrative"), "_src": src("market_opportunity_update", "update_id", u.get("update_id"))}
                for u in sorted(opp_updates.get(oid, []), key=lambda u: text(u.get("update_date")), reverse=True)
            ],
            "sources": [
                {"label": first_nonempty(sr, "source_title", "publisher"), "url": sr.get("source_url"),
                 "date": sr.get("source_date"), "type": sr.get("source_type")}
                for sr in sorted(opp_sources.get(oid, []), key=lambda x: text(x.get("source_date")), reverse=True)
            ],
        })

    moves = []
    for row in ordered(table(database, s, "market_next_move"), "sequence"):
        tender = by_tender.get(text(row.get("tender_id")), {})
        moves.append({
            "id": text(row.get("next_move_id")),
            "_src": src("market_next_move", "next_move_id", row.get("next_move_id")),
            "action": row.get("action_text"),
            "due": first_nonempty(row, "due_text", "due_date"),
            "dueDate": row.get("due_date"),
            "tenderId": text(row.get("tender_id")) or None,
            "tenderTitle": first_nonempty(row, "tender_title") or tender.get("title"),
            "opportunityId": text(row.get("opportunity_id")) or None,
            "priority": row.get("priority"),
            "status": row.get("status"),
        })

    metrics = [
        {
            "key": m.get("metric_key"),
            "_src": src("market_top_opportunity_metric", "metric_id", m.get("metric_id")),
            "label": m.get("metric_label"),
            "value": m.get("formatted_value"),
            "amount": first_nonempty(m, "amount_value", "numeric_value"),
            "currency": str(m.get("currency_code")).strip() if m.get("currency_code") else None,
            "note": m.get("note"),
        }
        for m in table(database, s, "market_top_opportunity_metric")
    ]
    view = (table(database, "ui", "market_top_opportunity_view") or [{}])[0]
    notes = {
        "topTenders": view.get("top_tenders_description"),
        "projects": view.get("projects_description"),
        "nextMoves": view.get("next_moves_description"),
    }
    return {"topTenders": top_tenders, "projectsBeforeTender": projects, "nextMoves": moves, "metrics": metrics, "notes": notes}


# ---------------------------------------------------------------- technology

def build_innovations(database):
    s = "serving"
    status = {text(r.get("innovation_id")): r for r in table(database, s, "technology_innovation_status")}
    companies = {text(c.get("company_id")): c for c in table(database, s, "technology_company")}
    inno_companies = group(table(database, s, "technology_innovation_company"), "innovation_id")
    inno_sources = group(table(database, s, "technology_innovation_source"), "innovation_id")
    sources = {text(x.get("source_id")): x for x in table(database, s, "technology_source")}

    # maturity_level 1-5 -> the chip class the page already uses (lab / dev / prod / fielded), from ui.code_label (technology_innovation.maturity_level)
    mat_class = {text(c.get("code")): c.get("tag_class") for c in table(database, "ui", "code_label")
                 if c.get("table_name") == "technology_innovation" and c.get("column_name") == "maturity_level"}
    milestones = group(table(database, s, "technology_innovation_milestone"), "innovation_id")

    grouped = defaultdict(list)
    for row in ordered(table(database, s, "technology_innovation"), "sequence_no"):
        if text(row.get("status")) == "candidate":     # innovation_discovery's thin rows: shown once innovation_detail fills them
            continue
        iid = text(row.get("innovation_id"))
        st = status.get(iid, {})
        names = []
        for c in ordered(inno_companies.get(iid, []), "display_order"):
            known = companies.get(text(c.get("company_id")), {})
            name = first_nonempty(c, "display_name") or known.get("display_name")
            if name:
                names.append(str(name))
        srcs = []
        for link in sorted(inno_sources.get(iid, []), key=lambda x: not x.get("is_primary")):
            source = sources.get(text(link.get("source_id")))
            if source:
                srcs.append({"label": first_nonempty(source, "label", "publisher"),
                             "url": first_nonempty(source, "url", "source_url")})
        grouped[text(row.get("category_id"))].append({
            "id": iid,
            "_src": src("technology_innovation", "innovation_id", iid),
            "t": row.get("title"),
            "s": row.get("list_description"),
            "mat": mat_class.get(text(row.get("maturity_level"))) or row.get("maturity"),
            "matLevel": row.get("maturity_level"),
            "kind": row.get("technology_kind"),
            "stance": row.get("stance"),
            "milestones": [{"date": m.get("step_date"), "step": m.get("step_type"), "note": m.get("note"), "url": m.get("source_url")}
                           for m in ordered(milestones.get(iid, []), "step_date")],
            "matLabel": st.get("maturity_label"),
            "gap": row.get("client_position"),
            "gapLabel": st.get("position_label"),
            "driver": ", ".join(names) or None,
            "horizon": first_nonempty(st, "horizon_text") or row.get("horizon_year"),
            "body": row.get("background_what_it_is"),
            "impact": row.get("why_matters_to_kssl"),
            "whatsNew": row.get("whats_new"),
            "compNote": row.get("competitive_note"),
            "sources": ", ".join(str(x["label"]) for x in srcs if x["label"]) or None,
            "url": next((x["url"] for x in srcs if x["url"]), None),
            "srcs": [x for x in srcs if x["url"]],
        })
    return dict(grouped)


def build_technology_categories(database):
    rows = table(database, "ui", "technology_category") or table(database, "serving", "technology_category")
    labels = {}
    for lab in table(database, "serving", "technology_category_ui_label"):
        labels.setdefault(text(lab.get("category_id")), lab)
    cats = []
    meta = {}
    for row in ordered(rows, "display_order", "tab_number"):
        category_id = text(row.get("category_id"))
        if not category_id:
            continue
        name = first_nonempty(labels.get(category_id, {}), "ui_name", "label_text") or first_nonempty(row, "category_name", "canonical_name")
        cats.append({"id": category_id, "name": name, "num": row.get("tab_number")})
        meta[category_id] = {"area": name, "desc": row.get("category_description")}
    # patent fields (the filing's own area_label) carry the client-position note and the crowding grade
    for row in table(database, "serving", "patent_field_assessment"):
        label = row.get("area_label")
        if label:
            meta["patent-field-" + slug(label)] = {"area": label, "reason": row.get("client_position_note"),
                                                   "crowding": row.get("crowding"),
                                                   "_src": src("patent_field_assessment", "area_label", label)}
    return cats, meta


def build(database, d):
    tenders = build_tenders(database)
    tech_cats, tech_area_meta = build_technology_categories(database)
    options = defaultdict(list)
    for o in ordered(table(database, "serving", "market_filter_option"), "sort_order"):
        if o.get("is_active") is not False:
            options[text(o.get("filter_type")).lower()].append(o.get("option_label"))
    requirements = build_requirements(database)
    # the segment recommendation is read straight from database.serving (lib/marketOutlook); each row carries its card key
    for r in table(database, "serving", "market_segment_assessment"):
        r["_src"] = src("market_segment_assessment", "segment", r.get("segment"))
    d.update({
        "tenders": tenders,
        "tpAllCountries": options.get("country", []),
        "tpAllCats": options.get("category", []),
        "globalRequirements": requirements,
        "marketCards": build_market_cards(database, requirements, d["details"]),
        "awards": build_awards(database),
        "topOpportunities": build_top_opportunities(database, tenders),
        "innovations": build_innovations(database),
        "techCats": tech_cats,
        "techAreaMeta": tech_area_meta,
    })
