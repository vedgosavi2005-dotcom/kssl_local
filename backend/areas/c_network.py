"""Area C: Partnerships, Projects, Geo footprint, Patents.

Audit: docs/audit_v2/C_partners_projects_geo_patents.md.
Every key below is a column of the table named in its `_src`; nothing is defaulted.
"""

from collections import defaultdict

from backend.common import first_nonempty, table, text


def src(tbl: str, key: str, row: dict) -> dict:
    return {"t": tbl, "k": key, "id": text(row.get(key))}


def by(rows, key):
    out = defaultdict(list)
    for row in rows:
        k = text(row.get(key))
        if k:
            out[k].append(row)
    return out


def ordered(rows, *keys):
    """Stable sort on the given columns; nulls last."""
    def k(row):
        return tuple((row.get(c) is None, row.get(c) if row.get(c) is not None else 0) for c in keys)
    return sorted(rows, key=k)


# --------------------------------------------------------------------------- Partnerships

def build_partners(database, competitors):
    evidence = by(table(database, "serving", "competitive_partnership_evidence"), "relationship_id")
    details = {text(r.get("relationship_id")): r for r in table(database, "serving", "competitive_partnership_relationship_detail")}
    per_comp = defaultdict(list)
    for row in ordered(table(database, "serving", "competitive_partnership"), "partner_name", "relationship_id"):
        cid = text(row.get("competitor_id"))
        rid = text(row.get("relationship_id"))
        if cid not in competitors or not rid:
            continue
        ev = [{
            "id": text(e.get("evidence_card_id")),
            "n": e.get("card_number"),
            "text": text(e.get("evidence_text")),
            "type": text(e.get("evidence_type")),
            "label": text(e.get("relationship_label")),
            "scope": text(e.get("scope")),
            "asOf": text(e.get("as_of_date")),
            "basis": text(e.get("basis_for_type")),
            "confidence": text(e.get("confidence")),
            "srcNote": text(e.get("source_note")),
            "srcType": text(e.get("source_type")),
            "publisher": text(e.get("source_publisher")),
            "articleTitle": text(e.get("source_article_title")),
            "articleUrl": text(e.get("source_article_url")),
            "url": text(e.get("source_url")),
            "_src": src("competitive_partnership_evidence", "evidence_card_id", e),
        } for e in ordered(evidence.get(rid, []), "card_number")]
        det = details.get(rid)
        per_comp[cid].append({
            "id": rid,
            "pid": text(row.get("partner_id")),
            "cid": cid,
            "label": text(row.get("partner_name")),
            "ptype": text(row.get("partner_type")),
            "country": text(row.get("region")),
            "confidence": text(row.get("relationship_confidence")),
            "as_of": text(row.get("as_of_date")),
            "date": text(row.get("as_of_date")),
            "scope": text(row.get("relationship_scope")),
            "note": text(row.get("description")),
            "srcnote": text(row.get("source_note")),
            "sourceCount": row.get("source_count"),
            "evidence": ev,
            "detail": None if det is None else {
                "title": text(det.get("relationship_title")),
                "label": text(det.get("detail_label")),
                "type": text(det.get("type")),
                "confidence": text(det.get("confidence")),
                "scope": text(det.get("scope")),
                "basis": text(det.get("basis_for_type")),
                "statedAsOf": text(det.get("stated_as_of")),
                "srcNote": text(det.get("source_note")),
                "publisher": text(det.get("source_publisher_label")),
                "articleUrl": text(det.get("source_article_url")),
                "_src": src("competitive_partnership_relationship_detail", "detail_id", det),
            },
            "_src": src("competitive_partnership", "relationship_id", row),
        })
    return per_comp


def build_client_partners(database):
    rels = by(table(database, "serving", "client_partner_relationship"), "client_partner_id")
    prods = by(table(database, "serving", "client_partner_product"), "client_partner_id")
    sources = by(table(database, "serving", "client_partner_source"), "client_partner_id")
    out = []
    for row in ordered(table(database, "serving", "client_partner"), "partner_name", "client_partner_id"):
        pid = text(row.get("client_partner_id"))
        if not pid:
            continue
        out.append({
            "id": pid,
            "label": text(row.get("partner_name")),
            "legal": text(row.get("legal_name")),
            "ptype": text(row.get("partner_type")),
            "country": text(row.get("country")),
            "region": text(row.get("region")),
            "confidence": text(row.get("relationship_confidence")),
            "scope": text(row.get("relationship_scope")),
            "start": text(row.get("relationship_start_date")),
            "status": text(row.get("relationship_status")),
            "role": text(row.get("strategic_role")),
            "relationships": [{
                "id": text(r.get("relationship_id")),
                "type": text(r.get("relationship_type")),
                "category": text(r.get("category")),
                "description": text(r.get("description")),
                "territory": text(r.get("territory")),
                "start": text(r.get("start_date")),
                "end": text(r.get("end_date")),
                "status": text(r.get("status")),
                "read": text(r.get("kssl_read")),
                "competitorOverlap": r.get("competitor_overlap"),
            } for r in rels.get(pid, [])],
            "products": [{
                "activity": text(p.get("activity_type")),
                "market": text(p.get("market")),
                "scope": text(p.get("scope")),
                "status": text(p.get("status")),
            } for p in prods.get(pid, [])],
            "sources": [{
                "label": text(s.get("source_label")),
                "url": text(s.get("source_url")),
                "type": text(s.get("source_type")),
                "note": text(s.get("source_note")),
                "asOf": text(s.get("as_of_date")),
            } for s in sources.get(pid, [])],
            "_src": src("client_partner", "client_partner_id", row),
        })
    return out


# --------------------------------------------------------------------------- Projects

def build_projects(database, competitors):
    stages = by(table(database, "serving", "competitive_project_stage"), "project_id")
    specs = by(table(database, "serving", "competitive_project_specification"), "project_id")
    timeline = by(table(database, "serving", "competitive_project_timeline"), "project_id")
    sources = by(table(database, "serving", "competitive_project_source"), "project_id")
    projects = []
    for row in ordered(table(database, "serving", "competitive_project"), "display_order", "project_id"):
        pid = text(first_nonempty(row, "project_id", "id"))
        if not pid:
            continue
        cid = text(row.get("competitor_id"))
        st = ordered(stages.get(pid, []), "stage_order")
        current = next((s for s in st if s.get("is_current")), None)
        projects.append({
            "id": pid,
            "cid": cid,
            "company": text(row.get("company_display")) or text(competitors.get(cid, {}).get("name")),
            "name": text(row.get("project_title")),
            "customer": text(row.get("customer")),
            "location": text(row.get("location")),
            "kind": text(row.get("kind")),
            "region": text(row.get("region")),
            "stage": text(row.get("stage")),
            "stageNote": text(row.get("stage_note")),
            "summary": text(row.get("card_summary")),
            "value": row.get("estimated_value"),
            "grade": text(row.get("grade")),
            "latest": {"date": text(row.get("latest_milestone_date")), "note": text(row.get("latest_milestone"))},
            "assessment": {
                "stance": text(row.get("assessment_stance")),
                "read": text(row.get("assessment_read")),
                "strategic": text(row.get("strategic_assessment")),
            },
            "ksslPlatform": text(row.get("kssl_platform")),
            "ksslAdvantage": text(row.get("kssl_advantage")),
            "overview": text(row.get("what_the_project_is")),
            "researchedAsOf": text(row.get("researched_as_of")),
            "stages": [{"name": text(s.get("stage_name")), "order": s.get("stage_order"), "current": bool(s.get("is_current"))} for s in st],
            "stageRank": None if current is None else current.get("stage_order"),
            "specs": [{"k": text(s.get("spec_label")), "v": text(s.get("spec_value")), "u": text(s.get("unit"))}
                      for s in ordered(specs.get(pid, []), "display_order", "project_spec_id")],
            "timeline": [{"date": text(t.get("event_date")), "label": text(t.get("event_title")),
                          "desc": text(t.get("event_description")), "expected": bool(t.get("is_expected"))}
                         for t in ordered(timeline.get(pid, []), "display_order", "event_date")],
            "sources": [{"label": text(first_nonempty(s, "source_label", "source_domain")), "url": text(s.get("source_url")),
                         "domain": text(s.get("source_domain")), "type": text(s.get("source_type"))}
                        for s in sources.get(pid, [])],
            "_src": src("competitive_project", "project_id", row),
        })
    filters = [{"f": "all", "l": "All"}]
    default_filter = "all"
    for row in ordered(table(database, "ui", "ui_project_filter"), "display_order"):
        code = text(first_nonempty(row, "filter_code", "filter_id"))
        if code and code != "all":
            filters.append({"f": code, "l": text(row.get("filter_label"))})
        if code and row.get("is_default"):
            default_filter = code
    seq = []
    default_seq = None
    for row in ordered(table(database, "ui", "ui_project_sequence_option"), "display_order"):
        if row.get("sequence_code"):
            seq.append([text(row.get("sequence_code")), text(row.get("sequence_label"))])
            if row.get("is_default"):
                default_seq = text(row.get("sequence_code"))
    stage_steps = [text(r.get("stage_name")) for r in ordered(table(database, "ui", "ui_project_stage_step"), "stage_order") if r.get("stage_name")]
    competitor_rows = [
        {"cid": cid, "name": competitors[cid].get("name"), "short": competitors[cid].get("short"), "threat": competitors[cid].get("threat")}
        for cid in sorted({p["cid"] for p in projects if p.get("cid")}) if cid in competitors
    ]
    return projects, {"competitors": competitor_rows, "filters": filters, "defaultFilter": default_filter,
                      "seqOptions": seq, "defaultSeq": default_seq, "stageSteps": stage_steps}


# --------------------------------------------------------------------------- Geo

def _source_row(s):
    return {"label": text(s.get("source_label")), "url": text(s.get("source_url")), "type": text(s.get("source_type"))}


def build_geo(database, competitors):
    loc_rows = table(database, "serving", "competitive_geo_location")
    src_by_loc = by(table(database, "serving", "competitive_geo_source"), "location_id")
    src_by_product = by(table(database, "serving", "competitive_geo_source"), "geo_product_id")
    src_by_match = by(table(database, "serving", "competitive_geo_source"), "match_id")
    news = by(table(database, "serving", "competitive_geo_product_news"), "geo_product_id")
    specs = by(table(database, "serving", "competitive_geo_product_specification"), "match_id")
    matches = by(table(database, "serving", "competitive_geo_product_match"), "geo_product_id")
    products = by(table(database, "serving", "competitive_geo_product"), "presence_id")

    locations = {}
    geo_locations = []
    for row in loc_rows:
        lid = text(row.get("location_id"))
        name = text(first_nonempty(row, "country_name", "map_label"))
        if not lid or not name:
            continue
        locations[lid] = name
        geo_locations.append({
            "id": lid,
            "name": name,
            "label": text(row.get("map_label")),
            "region": text(row.get("region_name")),
            "lat": row.get("latitude"),
            "lng": row.get("longitude"),
            "presenceTypes": text(row.get("presence_types")),
            "summary": text(row.get("kssl_presence_summary")),
            "srcs": [_source_row(s) for s in src_by_loc.get(lid, [])],
            "_src": src("competitive_geo_location", "location_id", row),
        })
    geo_locations.sort(key=lambda l: l["name"].lower())

    def match_out(m):
        mid = text(m.get("match_id"))
        return {
            "id": mid,
            "title": text(m.get("comparison_title")),
            "kssl": text(m.get("kssl_counter_label")),
            "label": text(m.get("evaluation_label")),
            "level": m.get("decision_level"),
            "kssl_score": m.get("kssl_score"),
            "rival_score": m.get("competitor_score"),
            "delta": m.get("rating_delta"),
            "basis": text(m.get("match_basis")),
            "summary": text(m.get("qualitative_summary")),
            "status": text(m.get("match_status")),
            "specs": [{"name": text(s.get("spec_name")), "group": text(s.get("spec_group")), "kssl": text(s.get("kssl_value")),
                       "rival": text(s.get("competitor_value")), "unit": text(s.get("unit")), "gap": text(s.get("gap_value")),
                       "better": text(s.get("better_side"))}
                      for s in ordered(specs.get(mid, []), "display_order", "comparison_spec_id")],
            "srcs": [_source_row(s) for s in src_by_match.get(mid, [])],
            "_src": src("competitive_geo_product_match", "match_id", m),
        }

    geo_data = defaultdict(lambda: defaultdict(list))
    geo_presence = defaultdict(lambda: defaultdict(list))
    geo_comps = []
    seen = set()
    for row in ordered(table(database, "serving", "competitive_geo_company_presence"), "display_order", "presence_id"):
        client = row.get("company_role") == "client"
        company_id = text(row.get("client_id") if client else first_nonempty(row, "competitor_id", "client_id"))
        country = locations.get(text(row.get("location_id")))
        if not company_id or not country:
            continue
        pid = text(row.get("presence_id"))
        geo_presence[company_id][country].append({
            "id": pid,
            "activity": text(row.get("activity_type")),
            "status": text(row.get("presence_status")),
            "overlap": text(row.get("overlap_status")),
            "ranges": text(row.get("matched_ranges")),
            "productCount": row.get("product_count"),
            "summary": text(row.get("products_summary")),
            "relationship": text(row.get("relationship_text")),
            "_src": src("competitive_geo_company_presence", "presence_id", row),
        })
        rows = geo_data[company_id][country]
        for p in ordered(products.get(pid, []), "display_order", "geo_product_id"):
            gid = text(p.get("geo_product_id"))
            rows.append({
                "id": gid,
                "presenceId": pid,
                "name": text(p.get("product_name")),
                "c": text(p.get("activity_type")),
                "since": text(p.get("since_date")),
                "note": text(p.get("record_note")),
                "value": text(p.get("reported_value")),
                "qty": text(p.get("quantity")),
                "range": text(p.get("product_range")),
                "ratedPower": p.get("rated_power_value"),
                "ratedUnit": text(p.get("rated_power_unit")),
                "fuel": text(p.get("fuel_type")),
                "hz": p.get("frequency_hz"),
                "matches": [match_out(m) for m in ordered(matches.get(gid, []), "match_id")],
                "news": [{"title": text(n.get("headline")), "publisher": text(n.get("publisher")), "date": text(n.get("published_date")),
                          "url": text(n.get("article_url"))} for n in ordered(news.get(gid, []), "display_order", "news_id")],
                "srcs": [_source_row(s) for s in src_by_product.get(gid, [])],
                "_src": src("competitive_geo_product", "geo_product_id", p),
            })
        if company_id not in seen:
            seen.add(company_id)
            geo_comps.append({"id": company_id, "name": text(row.get("company_name")), "isBf": client})
    countries = [l["name"] for l in geo_locations]
    return ({k: dict(v) for k, v in geo_data.items()}, {k: dict(v) for k, v in geo_presence.items()},
            geo_comps, geo_locations, countries)


# --------------------------------------------------------------------------- Patents

def build_patents(database, competitors):
    filings = by(table(database, "serving", "competitive_patent_filing"), "portfolio_id")
    classes = by(table(database, "serving", "competitive_patent_classification"), "portfolio_id")
    by_competitor = {}
    by_tech = {}
    total = 0
    for pf in table(database, "serving", "competitive_patent_portfolio"):
        cid = text(pf.get("competitor_id"))
        pid = text(pf.get("portfolio_id"))
        if not cid or not pid:
            continue
        records = [{
            "id": text(f.get("publication_number")),
            "fid": text(f.get("filing_id")),
            "title": text(f.get("title")),
            "jurisdiction": text(f.get("jurisdiction")),
            "filed": text(f.get("filed_date")),
            "status": text(f.get("status")),
            "code": text(f.get("classification_code")),
            "codeText": text(f.get("classification_text")),
            "url": text(f.get("patent_url")),
            "cid": cid,
            # keyed like the review graph: publication_number, else filing_id
            "_src": src("competitive_patent_filing", "publication_number" if f.get("publication_number") is not None else "filing_id", f),
        } for f in ordered(filings.get(pid, []), "filed_date", "filing_id")]
        total += len(records)
        cats = {}
        for c in classes.get(pid, []):
            label = text(c.get("category_label"))
            if label and label not in cats:  # a label written under two lenses counts once
                cats[label] = {"label": label, "count": c.get("filing_count"), "lens": text(c.get("lens"))}
        by_competitor[cid] = {
            "portfolioId": pid,
            "lens": text(pf.get("lens")),
            "filingCount": pf.get("filing_count"),
            "grantedCount": pf.get("granted_count"),
            "pendingCount": pf.get("pending_count"),
            "grantStatusState": text(pf.get("grant_status_state")),
            "statusNote": text(pf.get("status_note")),
            "emptyMessage": text(pf.get("empty_message")),
            "dataSourceNote": text(pf.get("data_source_note")),
            "categories": list(cats.values()),
            "records": records,
            "_src": src("competitive_patent_portfolio", "portfolio_id", pf),
        }
        for label, cat in cats.items():
            tech = by_tech.setdefault(label, {"count": 0, "holders": [], "records": [], "notes": []})
            tech["count"] += cat["count"] or 0
            tech["holders"].append({"cid": cid, "filings": cat["count"]})
            if text(pf.get("data_source_note")):
                tech["notes"].append(text(pf.get("data_source_note")))
            low = label.lower()
            tech["records"].extend(r for r in records if low in (r["code"].lower(), r["codeText"].lower()))
    return {"byCompetitor": by_competitor, "byTechnology": by_tech, "_meta": {"total": total}}


def build(database, d):
    competitors = d["competitors"]
    geo_data, geo_presence, geo_comps, geo_locations, geo_countries = build_geo(database, competitors)
    projects, projects_config = build_projects(database, competitors)
    for cid, partners in build_partners(database, competitors).items():
        competitors[cid]["partners"] = partners
    d.update({
        "geoData": geo_data, "geoPresence": geo_presence, "geoComps": geo_comps,
        "geoLocations": geo_locations, "geoCountries": geo_countries,
        "projects": projects, "projectsConfig": projects_config,
        "PATENTS": build_patents(database, competitors),
        "KSSL_PARTNERS": build_client_partners(database),
    })
