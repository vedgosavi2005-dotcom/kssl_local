"""Area D: Market (tenders, top opportunity, global requirements) and Technology (innovations).

Audit: docs/audit_v2/D_market_technology.md. Every value is a stored column; nothing is defaulted.
Numbers are served as numbers, dates as ISO strings, missing values as "" / None.

Enumerations the UI expects (stored text, compared case-insensitively; unknown values are shown as stored):
  market_tender.status          open | closing | awarded | closed   (awarded / closed decide the Awarded / Closed
                                tabs; every other value is an open tender)
  market_tender.lean_code       go | maybe | pass | won | closed    (colour of the bid-assessment band only)
  market_tender.kssl_fit,       strong | partial | weak             (bar colour only; the word shown is the stored text)
   *.kssl_fit, fit_grade, fit_label
  market_tender.url_kind        notice | portal | award             (label of the "open the tender" button)
  technology_innovation.maturity           free text; lab | dev | prod | fielded only pick a chip colour
  technology_innovation.client_position    behind | parity | ahead (chip colour; the words shown are position_label)
  technology_innovation.status             free text (record state, not shown)
"""

from collections import defaultdict

from backend.common import first_nonempty, table, text


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
    portals = {text(p.get("portal_name")).lower(): p for p in table(database, s, "market_tender_portal")}

    tenders = []
    for row in table(database, s, "market_tender"):
        tid = text(row.get("tender_id"))
        if not tid:
            continue
        window = sorted(windows.get(tid, []), key=lambda w: text(w.get("as_of_date")))[-1:] or [{}]
        window = window[0]
        fit = sorted(fits.get(tid, []), key=lambda f: text(f.get("assessed_at")))[-1:] or [{}]
        fit = fit[0]

        requirements = []
        for r in ordered(reqs.get(tid, []), "display_order"):
            quantity = r.get("quantity")
            rows = clean([
                ("Description", text(r.get("description"))),
                ("Scope", text(r.get("scope_text"))),
                ("Note", text(r.get("requirement_note"))),
                ("Equipment", text(r.get("equipment_scope"))),
                ("Rating", text(r.get("rating_band"))),
                ("Use case", text(r.get("use_case"))),
                ("Quantity", " ".join(clean([text(quantity) if quantity is not None else "", text(r.get("quantity_unit"))]))),
                (text(r.get("scope_bullet_label")) or "Detail", text(r.get("scope_bullet_value"))),
                ("Category", text(r.get("category_text"))),
                ("Stated in", text(r.get("source_text"))),
            ])
            requirements.append({
                "type": text(r.get("requirement_type")),
                "rows": [list(p) for p in rows if p[1]],
                "_src": src("market_tender_requirement", "requirement_id", r.get("requirement_id")),
            })

        product_matches = []
        for m in ordered(matches.get(tid, []), "display_order"):
            product_matches.append({
                "n": text(m.get("match_label")),
                "fit": text(m.get("fit_grade")),
                "percent": m.get("fit_percent"),
                "lines": [
                    {"label": text(l.get("line_label")), "value": text(l.get("line_value"))}
                    for l in ordered(lines.get(text(m.get("tender_match_id")), []), "display_order")
                ],
                "_src": src("market_tender_product_match", "tender_match_id", m.get("tender_match_id")),
            })

        competitor_fit = [
            {
                "name": text(c.get("competitor_name")),
                "fit": text(c.get("fit_label")),
                "products": text(first_nonempty(c, "competitor_product_display", "competitor_products_text")),
                "rationale": text(c.get("fit_rationale")),
                "rank": c.get("rank_position"),
                "_src": src("market_tender_competitor_fit", "competitor_fit_id", c.get("competitor_fit_id")),
            }
            for c in ordered(comps.get(tid, []), "rank_position")
        ]

        srcs = []
        for sr in sorted(sources.get(tid, []), key=lambda x: not x.get("is_primary")):
            portal = portals.get(text(sr.get("portal_name")).lower())
            srcs.append({
                "label": text(first_nonempty(sr, "portal_name", "publisher")),
                "url": text(sr.get("source_url")),
                "publisher": text(sr.get("publisher")),
                "portal": text(sr.get("portal_name")),
                "kind": text(sr.get("source_type")),
                "primary": bool(sr.get("is_primary")),
                "note": text(sr.get("access_note")),
                "retrievedAt": text(sr.get("retrieved_at")),
                "portalAccess": text(portal.get("access_status")) if portal else "",
                "portalRegistration": portal.get("registration_required") if portal else None,
                "portalSubmission": text(portal.get("submission_method")) if portal else "",
                "_src": src("market_tender_source", "source_id", sr.get("source_id")),
            })

        quantity = row.get("quantity")
        tenders.append({
            "id": tid,
            "_src": src("market_tender", "tender_id", tid),
            "title": text(first_nonempty(row, "title", "title_localized")),
            "issuer": text(first_nonempty(row, "issuer_display", "buyer_name")),
            "country": text(row.get("country_name")),
            "cat": text(row.get("category_text")),
            "desc": text(row.get("description")),
            "closingDate": text(first_nonempty(row, "closing_date") or window.get("closing_date")),
            "deadline": text(row.get("deadline_text")),
            "isLive": row.get("is_live"),
            "value": text(row.get("value_text")),
            "valueAmount": row.get("value_amount"),
            "valueCurrency": text(row.get("value_currency")).strip(),
            "expectedRevenue": text(first_nonempty(row, "expected_revenue_text") or fit.get("revenue_estimate_text")),
            "lean": text(row.get("lean_code")),
            "leanTxt": text(row.get("lean_text")),
            "ksslFit": text(first_nonempty(row, "kssl_fit") or fit.get("kssl_fit")),
            "ksslModel": text(first_nonempty(row, "kssl_model") or fit.get("kssl_model")),
            "rank": row.get("rank_position"),
            "url": text(row.get("source_url")),
            "urlKind": text(row.get("url_kind")),
            "status": text(row.get("status")),
            "posted": text(row.get("published_date")),
            "qty": " ".join(clean([text(quantity) if quantity is not None else "", text(row.get("quantity_unit"))])),
            "noticeRef": text(first_nonempty(row, "notice_reference", "tender_number")),
            "milestone": text(first_nonempty(window, "milestone_text") or row.get("latest_milestone")),
            "extension": window.get("is_extension_confirmed"),
            "submissionMethod": text(row.get("submission_method")),
            "registration": text(row.get("registration_requirement")),
            "localPresence": text(row.get("local_presence_requirement")),
            "frequency": text(row.get("frequency")),
            "fitGrade": text(fit.get("fit_grade")),
            "fitScore": fit.get("fit_score"),
            "fitRank": first_nonempty(fit, "kssl_fit_rank", "fit_rank"),
            "fitNote": text(first_nonempty(fit, "kssl_fit_rationale", "assessment_rationale", "match_summary")),
            "revenueTier": text(fit.get("revenue_tier")),
            "requirements": requirements,
            "matches": product_matches,
            "competitorFit": competitor_fit,
            "srcs": srcs,
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
            "title": text(row.get("title")),
            "buyer": text(row.get("buyer_name")),
            "country": text(row.get("country_name")),
            "region": text(row.get("region")),
            "cat": text(row.get("category")),
            "value": text(row.get("value_text")),
            "dl": row.get("days_remaining"),
            "deadline": text(row.get("deadline")),
            "status": text(row.get("status")),
            "desc": text(row.get("description")),
            "ksslFit": text(row.get("kssl_fit")),
            "ksslModel": text(row.get("kssl_model")),
            "strategicAssessment": text(row.get("strategic_assessment")),
            "specs": [[text(s.get("spec_label")), text(s.get("spec_value"))] for s in ordered(specs.get(rid, []), "display_order")],
            "sources": [
                {"label": text(s.get("source_label")), "url": text(s.get("source_url")), "type": text(s.get("source_type"))}
                for s in ordered(sources.get(rid, []), "display_order")
            ],
        })
    return result


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
            "tenderId": text(row.get("tender_id")),
            "rank": row.get("rank_position"),
            "title": tender.get("title", ""),
            "issuer": tender.get("issuer", ""),
            "country": tender.get("country", ""),
            "decides": text(row.get("decides")),
            "ksslFit": text(row.get("kssl_fit")),
            "ksslModel": text(row.get("kssl_model")),
            "rivalToBeat": text(row.get("rival_to_beat")),
            "revenue": text(row.get("revenue_text")),
        })

    projects = []
    for row in ordered(table(database, s, "market_top_opportunity_project"), "rank_position"):
        oid = text(row.get("opportunity_id"))
        opp = opps.get(oid, {})
        fit = sorted(opp_fits.get(oid, []), key=lambda f: text(f.get("assessed_at")))[-1:] or [{}]
        fit = fit[0]
        projects.append({
            "id": text(row.get("top_opportunity_project_id")),
            "_src": src("market_top_opportunity_project", "top_opportunity_project_id", row.get("top_opportunity_project_id")),
            "opportunityId": oid,
            "rank": row.get("rank_position"),
            "title": text(opp.get("title")),
            "issuer": text(first_nonempty(row, "buyer_name") or opp.get("buyer_name")),
            "country": text(row.get("country_name")),
            "stage": text(first_nonempty(row, "where_it_stands") or opp.get("current_status") or opp.get("stage")),
            "ksslFit": text(first_nonempty(row, "kssl_fit") or fit.get("fit_grade")),
            "ksslModel": text(first_nonempty(row, "kssl_model") or fit.get("client_model_display")),
            "rivalToBeat": text(first_nonempty(row, "rival_to_beat") or fit.get("rival_name")),
            "revenue": text(first_nonempty(row, "revenue_text") or fit.get("revenue_display")),
            "opportunity": {
                "_src": src("market_opportunity", "opportunity_id", oid),
                "kind": text(opp.get("opportunity_kind")),
                "description": text(opp.get("description")),
                "scope": text(opp.get("scope_text")),
                "contractor": text(opp.get("contractor_name")),
                "location": text(opp.get("location_text")),
                "milestone": text(opp.get("latest_milestone")),
                "asOf": text(opp.get("as_of_date")),
                "rationale": text(fit.get("rationale")),
                "rivalProduct": text(fit.get("rival_product_display")),
            } if opp else None,
            "updates": [
                {
                    "date": text(u.get("update_date")), "type": text(u.get("update_type")),
                    "headline": text(u.get("headline")), "narrative": text(u.get("narrative")),
                    "_src": src("market_opportunity_update", "update_id", u.get("update_id")),
                }
                for u in sorted(opp_updates.get(oid, []), key=lambda u: text(u.get("update_date")), reverse=True)
            ],
            "sources": [
                {"label": text(first_nonempty(sr, "source_title", "publisher")), "url": text(sr.get("source_url")),
                 "date": text(sr.get("source_date")), "type": text(sr.get("source_type"))}
                for sr in sorted(opp_sources.get(oid, []), key=lambda x: text(x.get("source_date")), reverse=True)
            ],
        })

    moves = []
    for row in ordered(table(database, s, "market_next_move"), "sequence"):
        tender = by_tender.get(text(row.get("tender_id")), {})
        moves.append({
            "id": text(row.get("next_move_id")),
            "_src": src("market_next_move", "next_move_id", row.get("next_move_id")),
            "action": text(row.get("action_text")),
            "due": text(row.get("due_text")),
            "dueDate": text(row.get("due_date")),
            "tenderId": text(row.get("tender_id")),
            "tenderTitle": text(first_nonempty(row, "tender_title") or tender.get("title")),
            "opportunityId": text(row.get("opportunity_id")),
            "priority": text(row.get("priority")),
            "status": text(row.get("status")),
        })

    metrics = [
        {
            "key": text(m.get("metric_key")),
            "_src": src("market_top_opportunity_metric", "metric_id", m.get("metric_id")),
            "label": text(m.get("metric_label")),
            "value": text(m.get("formatted_value")),
            "amount": first_nonempty(m, "amount_value", "numeric_value"),
            "currency": text(m.get("currency_code")).strip(),
            "note": text(m.get("note")),
        }
        for m in table(database, s, "market_top_opportunity_metric")
    ]
    view = (table(database, "ui", "market_top_opportunity_view") or [{}])[0]
    notes = {
        "topTenders": text(view.get("top_tenders_description")),
        "projects": text(view.get("projects_description")),
        "nextMoves": text(view.get("next_moves_description")),
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
    analysis = group(table(database, s, "technology_innovation_analysis"), "innovation_id")

    grouped = defaultdict(list)
    for row in ordered(table(database, s, "technology_innovation"), "sequence_no"):
        if text(row.get("status")) == "candidate":     # innovation_discovery's thin rows: shown once innovation_detail fills them
            continue
        iid = text(row.get("innovation_id"))
        st = status.get(iid, {})
        names = []
        company_rows = []
        for c in ordered(inno_companies.get(iid, []), "display_order"):
            known = companies.get(text(c.get("company_id")), {})
            name = text(first_nonempty(c, "display_name") or known.get("display_name"))
            if name:
                names.append(name)
                company_rows.append({"name": name, "relationship": text(c.get("relationship")), "type": text(c.get("relationship_type"))})
        srcs = []
        for link in sorted(inno_sources.get(iid, []), key=lambda x: not x.get("is_primary")):
            source = sources.get(text(link.get("source_id")))
            if source:
                srcs.append({
                    "label": text(first_nonempty(source, "label", "publisher")),
                    "url": text(first_nonempty(source, "url", "source_url")),
                    "publisher": text(source.get("publisher")),
                    "kind": text(first_nonempty(source, "source_type", "source_kind")),
                })
        horizon_year = row.get("horizon_year")
        item = {
            "id": iid,
            "_src": src("technology_innovation", "innovation_id", iid),
            "t": text(row.get("title")),
            "s": text(row.get("list_description")),
            "summary": text(row.get("summary")),
            "body": text(row.get("background_what_it_is")),
            "whatsNew": text(row.get("whats_new")),
            "impact": text(row.get("why_matters_to_kssl")),
            "compNote": text(row.get("competitive_note")),
            "mat": text(row.get("maturity")),
            "matLabel": text(first_nonempty(st, "maturity_label") or row.get("maturity")),
            "gap": text(row.get("client_position")),
            "gapLabel": text(first_nonempty(st, "position_label") or row.get("client_position")),
            "badge": text(st.get("assessment_badge")),
            "horizon": text(first_nonempty(st, "horizon_text") or (horizon_year if horizon_year is not None else "")),
            "listStatus": text(row.get("list_status_label")),
            "driver": ", ".join(names),
            "companies": company_rows,
            "srcs": srcs,
            "analysis": [
                {"code": text(a.get("section_code")), "label": text(a.get("section_label")), "text": text(a.get("narrative")),
                 "isClient": bool(a.get("is_client_assessment"))}
                for a in ordered(analysis.get(iid, []), "display_order")
            ],
        }
        grouped[text(row.get("category_id"))].append(item)
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
        name = text(first_nonempty(labels.get(category_id, {}), "ui_name", "label_text") or first_nonempty(row, "category_name", "canonical_name"))
        cats.append({"id": category_id, "name": name, "num": row.get("tab_number")})
        meta[category_id] = {"area": name, "description": text(row.get("category_description"))}
    return cats, meta


def build(database, d):
    tenders = build_tenders(database)
    tech_cats, tech_area_meta = build_technology_categories(database)
    options = defaultdict(list)
    for o in ordered(table(database, "serving", "market_filter_option"), "sort_order"):
        if o.get("is_active") is not False:
            options[text(o.get("filter_type")).lower()].append(text(o.get("option_label")))
    d.update({
        "tenders": tenders,
        "tpAllCountries": options.get("country", []),
        "tpAllCats": options.get("category", []),
        "globalRequirements": build_requirements(database),
        "topOpportunities": build_top_opportunities(database, tenders),
        "innovations": build_innovations(database),
        "techCats": tech_cats,
        "techAreaMeta": tech_area_meta,
    })
