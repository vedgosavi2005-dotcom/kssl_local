"""Area C: Partnerships (+ synthesis reads), Projects, Geo footprint, Patents.

Shapes follow docs/ui_port/MAPPING.md section A (partners, KSSL_PARTNERS, REL_LABEL, COMPSYN, TRACEIDS, FIELDSYN,
projects, projectsConfig, geoComps/geoData/geoPresence/geoCountries/actLabel, PATENTS, techAreaMeta rows for the
patent fields). Every key below is a column of the table named in its `_src`; nothing is defaulted.
"""

from collections import defaultdict

from backend.common import first_nonempty, slug, table, text


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


def _shown(n):
    if n is None:
        return None
    return str(int(n)) if n == int(n) else str(round(n, 6))


def _with_unit(value, unit):
    if value in (None, ""):
        return None
    return f"{value} {unit}" if unit not in (None, "") else value


# --------------------------------------------------------------------------- Partnerships

def build_partners(database, competitors):
    evidence = by(table(database, "serving", "competitive_partnership_evidence"), "relationship_id")
    client_partners = {text(r.get("client_partner_id")): r for r in table(database, "serving", "client_partner")}
    per_comp = defaultdict(list)
    for row in ordered(table(database, "serving", "competitive_partnership"), "partner_name", "relationship_id"):
        cid = text(row.get("competitor_id"))
        rid = text(row.get("relationship_id"))
        if cid not in competitors or not rid:
            continue
        first_url = next((e.get("source_url") for e in ordered(evidence.get(rid, []), "card_number") if e.get("source_url")), None)
        partner_id = text(row.get("partner_id"))
        # the tie as a timeline: its evidence cards, oldest first (each card is one dated step; v3 writes step_type)
        steps = [{"date": e.get("as_of_date"), "step": e.get("step_type"), "label": e.get("relationship_label"), "text": e.get("evidence_text"),
                  "publisher": e.get("source_publisher"), "url": e.get("source_url")}
                 for e in sorted(evidence.get(rid, []), key=lambda e: (text(e.get("as_of_date")) or "9999", e.get("card_number") or 0))]
        kp = client_partners.get(text(row.get("overlap_client_partner_id")))
        per_comp[cid].append({
            "id": rid,
            "cid": partner_id if partner_id in competitors else None,
            "label": row.get("partner_name"),
            "ptype": row.get("partner_type"),
            "rel": slug(row.get("partner_type")) or None,
            "note": row.get("description"),
            "date": row.get("as_of_date"),
            "as_of": row.get("as_of_date"),
            "country": row.get("region"),
            "confidence": row.get("relationship_confidence"),
            "srcnote": row.get("source_note"),
            "verdict": row.get("client_verdict"),      # as stored (threat / watch / ...): the UI shows only threat and watch
            "impact": first_nonempty(row, "kssl_read", "client_impact"),   # the stored read of the tie for the client
            "status": row.get("status"),
            "valueComp": row.get("value_to_competitor"),
            "valuePartner": row.get("value_to_partner"),
            "overlap": ({"kind": row.get("overlap_kind"), "component": row.get("overlap_component"), "effect": row.get("overlap_effect"),
                         "clientPartner": kp.get("partner_name") if kp else None, "clientPartnerId": text(row.get("overlap_client_partner_id")) or None}
                        if row.get("overlap_kind") or kp else None),
            "steps": steps,
            "src": first_url,
            "_src": src("competitive_partnership", "relationship_id", row),
        })
    return per_comp


_CLIENT_REL = {"licensor": "licensing", "mou-teaming": "mou"}


def build_client_partners(database, competitors):
    rels = by(table(database, "serving", "client_partner_relationship"), "client_partner_id")
    names = {}
    for cid, c in competitors.items():
        if c.get("dir") == "client":
            continue
        for n in (c.get("name"), c.get("legal")):
            if n:
                names.setdefault(str(n).strip().lower(), cid)
    out = []
    for row in ordered(table(database, "serving", "client_partner"), "partner_name", "client_partner_id"):
        pid = text(row.get("client_partner_id"))
        if not pid:
            continue
        first_rel = rels.get(pid, [{}])[0]
        pname = row.get("partner_name")
        out.append({
            "id": pid,
            "label": pname,
            "cid": names.get(str(pname).strip().lower()) if pname else None,
            "ptype": row.get("partner_type"),
            # the client's six partner types (client_partner_research) keyed onto the legend's keys / aliases (chrome.js
            # PARTNER_CATEGORIES): "licensor" and "mou-teaming" are not legend keys, so the overlap read lost their kind
            "rel": _CLIENT_REL.get(slug(row.get("partner_type")), slug(row.get("partner_type"))) or None,
            "country": row.get("country"),
            "note": first_rel.get("description"),
            # what the client does with the partner: client_partner_research writes relationship_scope; strategic_role
            # (an Excel column) wins when the client's own list fills it
            "role": first_nonempty(row, "strategic_role", "relationship_scope"),
            "status": row.get("relationship_status"),
            "date": row.get("relationship_start_date"),
            "as_of": row.get("relationship_start_date"),
            "mean": first_rel.get("kssl_read"),
            "insight": first_rel.get("kssl_read"),
            "_src": src("client_partner", "client_partner_id", row),
        })
    return out


def build_rel_label(database):
    # The relationship legend (category and short labels, definitions) is front-end code (src/lib/chrome.js), not a
    # ui table; the key stays in the dataset contract and is empty.
    return {}


def build_synthesis(database):
    """COMPSYN (thesis, vulnerabilities, strategy per competitor), TRACEIDS (partner ties each vulnerability traces
    to), FIELDSYN (the field-level read)."""
    traces = by(table(database, "serving", "competitive_synthesis_vulnerability_trace"), "vulnerability_id")
    vulns = by(table(database, "serving", "competitive_synthesis_vulnerability"), "competitor_id")
    compsyn, traceids = {}, {}
    for row in table(database, "serving", "competitive_synthesis"):
        cid = text(row.get("competitor_id"))
        if not cid:
            continue
        rows = ordered(vulns.get(cid, []), "display_order")
        compsyn[cid] = {
            "thesis": row.get("thesis"),
            "vulns": [{
                "title": v.get("title"),
                "from": [x.strip() for x in str(v.get("from_labels") or "").splitlines() if x.strip()],
                "intel": v.get("intel"),
                "_src": src("competitive_synthesis_vulnerability", "vulnerability_id", v),
            } for v in rows],
            "strat": {"thesis": row.get("strategy_thesis"), "pattern": row.get("strategy_pattern"),
                      "sowhat": row.get("strategy_sowhat")},
            "_src": src("competitive_synthesis", "competitor_id", row),
        }
        traceids[cid] = [[text(t.get("relationship_id")) for t in traces.get(text(v.get("vulnerability_id")), [])
                          if t.get("relationship_id")] for v in rows]
    field_rows = ordered(table(database, "serving", "competitive_field_synthesis"), "display_order")
    bottom_row = next((r for r in field_rows if r.get("row_kind") == "bottom_line" and r.get("bottom_line")), None)
    bottom = bottom_row.get("bottom_line") if bottom_row else None
    fieldsyn = {
        "patterns": [{
            "field": r.get("field_title"), "pattern": r.get("pattern"), "implication": r.get("implication"),
            "n": r.get("support_count"), "total": r.get("support_total"),
            "_src": src("competitive_field_synthesis", "synthesis_id", r),
        } for r in field_rows if r.get("row_kind") == "pattern"],
        "bottom": bottom,
        "bottomSrc": src("competitive_field_synthesis", "synthesis_id", bottom_row) if bottom_row else None,
    }
    return compsyn, traceids, fieldsyn


# --------------------------------------------------------------------------- Projects

def build_projects(database, competitors):
    stages = by(table(database, "serving", "competitive_project_stage"), "project_id")
    specs = by(table(database, "serving", "competitive_project_specification"), "project_id")
    timeline = by(table(database, "serving", "competitive_project_timeline"), "project_id")
    sources = by(table(database, "serving", "competitive_project_source"), "project_id")
    # a project is a story: its dated, sourced steps (what changed at each), planned steps included
    steps_of = defaultdict(list)
    for st in ordered(table(database, "serving", "story_step"), "step_no"):
        steps_of[text(st.get("story_id"))].append({"date": st.get("step_date"), "type": st.get("step_type"), "line": st.get("one_line"),
                                                   "changed": st.get("changed"), "url": st.get("source_url"), "label": st.get("label_after")})
    projects = []
    for row in ordered(table(database, "serving", "competitive_project"), "display_order", "project_id"):
        pid = text(first_nonempty(row, "project_id", "id"))
        if not pid:
            continue
        cid = text(row.get("competitor_id"))
        st = ordered(stages.get(pid, []), "stage_order")
        current = next((s for s in st if s.get("is_current")), None)
        read = [x for x in (row.get("assessment_read"), row.get("strategic_assessment")) if x]
        projects.append({
            "id": pid,
            "cid": cid or None,
            "company": first_nonempty(row, "company_display") or (competitors.get(cid) or {}).get("name"),
            "name": row.get("project_title"),
            "kind": row.get("kind"),
            "region": row.get("region"),
            "customer": row.get("customer"),
            "location": row.get("location"),
            "stage": row.get("stage"),
            "stageRank": None if current is None else current.get("stage_order"),
            "stageNote": row.get("stage_note"),
            "specs": [{"k": s.get("spec_label"), "v": _with_unit(s.get("spec_value"), s.get("unit"))}
                      for s in ordered(specs.get(pid, []), "display_order", "project_spec_id")],
            "timeline": [{"date": t.get("event_date"), "label": t.get("event_title"), "expected": t.get("is_expected")}
                         for t in ordered(timeline.get(pid, []), "display_order", "event_date")],
            "latest": {"date": row.get("latest_milestone_date"), "label": row.get("latest_milestone")},
            "overview": [row.get("what_the_project_is")] if row.get("what_the_project_is") else [],
            "assessment": {"stance": row.get("assessment_stance"), "read": read},
            "ksslOption": row.get("kssl_option"),
            "steps": steps_of.get(text(row.get("story_id")), []),
            "sources": [{"label": first_nonempty(s, "source_label", "source_domain"), "url": s.get("source_url")}
                        for s in sources.get(pid, [])],
            "researchedAsOf": row.get("researched_as_of"),
            "_src": src("competitive_project", "project_id", row),
        })
    # The filter and sequence controls are front-end chrome (src/lib/chrome.js). The stage steps are DATA: the stages
    # the projects themselves carry (serving.competitive_project_stage), one step per stage_order, in order.
    steps = {}
    for row in table(database, "serving", "competitive_project_stage"):
        order, name = row.get("stage_order"), row.get("stage_name")
        if order is not None and name and order not in steps:
            steps[order] = name
    stage_steps = [steps[k] for k in sorted(steps)]
    return projects, {"stageSteps": stage_steps}


# --------------------------------------------------------------------------- Geo

def build_geo(database, competitors):
    loc_rows = table(database, "serving", "competitive_geo_location")
    src_by_product = by(table(database, "serving", "competitive_geo_source"), "geo_product_id")
    news = by(table(database, "serving", "competitive_geo_product_news"), "geo_product_id")
    products = by(table(database, "serving", "competitive_geo_product"), "presence_id")

    locations = {}
    for row in loc_rows:
        lid = text(row.get("location_id"))
        name = first_nonempty(row, "country_name", "map_label")
        if lid and name:
            locations[lid] = name

    geo_data = defaultdict(lambda: defaultdict(list))
    geo_presence = []
    geo_comps = []
    seen = set()
    activities = []
    for row in ordered(table(database, "serving", "competitive_geo_company_presence"), "display_order", "presence_id"):
        client = row.get("company_role") == "client"
        company_id = text(row.get("client_id") if client else first_nonempty(row, "competitor_id", "client_id"))
        country = locations.get(text(row.get("location_id")))
        pid = text(row.get("presence_id"))
        if not company_id or not country or not products.get(pid):   # a presence with no product row left has nothing to show
            continue
        geo_presence.append({
            "id": pid,
            "comp": row.get("company_name"),
            "cid": company_id,
            "country": country,
            "activity": row.get("activity_type"),
            "status": row.get("presence_status"),
            "overlap": row.get("overlap_status"),
            "ranges": row.get("matched_ranges"),
            "productCount": row.get("product_count"),
            "summary": row.get("products_summary"),
            "relationship": row.get("relationship_text"),
            "_src": src("competitive_geo_company_presence", "presence_id", row),
        })
        rows = geo_data[company_id][country]
        for p in ordered(products.get(pid, []), "display_order", "geo_product_id"):
            gid = text(p.get("geo_product_id"))
            srcs = [{"label": s.get("source_label"), "url": s.get("source_url")} for s in src_by_product.get(gid, [])]
            if p.get("activity_type") and p.get("activity_type") not in activities:
                activities.append(p.get("activity_type"))
            rows.append({
                "id": gid,
                "presenceId": pid,
                "name": p.get("product_name"),
                "c": p.get("activity_type"),
                "val": p.get("reported_value"),
                "since": p.get("since_date"),
                "qty": p.get("quantity"),
                "stage": row.get("presence_status"),
                "note": p.get("record_note"),
                "customer": p.get("customer_name"),
                "localPartner": p.get("local_partner"),
                "srcnote": srcs[0]["label"] if srcs else None,
                "srcs": srcs,
                "geo_news": [{"title": n.get("headline"), "url": n.get("article_url"), "date": n.get("published_date"),
                              "source": n.get("publisher")}
                             for n in ordered(news.get(gid, []), "display_order", "news_id")],
                "_src": src("competitive_geo_product", "geo_product_id", p),
            })
        if company_id not in seen:
            seen.add(company_id)
            comp = competitors.get(company_id) or {}
            geo_comps.append({"id": company_id, "name": row.get("company_name"), "isBf": client,
                              "dir": comp.get("threat"), "hq": comp.get("hq")})
    countries = sorted(set(locations.values()), key=str.lower)
    act_label = {a: a for a in activities}  # identity map over the stored activity words
    return {k: dict(v) for k, v in geo_data.items()}, geo_presence, geo_comps, countries, act_label


def build_geo_analysis(database, competitors):
    """geoAnalysis: country -> layer-2 findings (overlap, anomaly, white space) as stored. A stated reason carries its codes; with none
    stated the question to ask and the labelled analyst hypothesis come through, never a reason."""
    names = {}
    for row in table(database, "serving", "competitive_geo_location"):
        lid, name = text(row.get("location_id")), first_nonempty(row, "country_name", "map_label")
        if lid and name:
            names[lid] = name
    kssl = {text(r.get("client_product_id")): r.get("product_name") for r in table(database, "serving", "client_product")}
    out = defaultdict(list)
    for row in ordered(table(database, "serving", "competitive_geo_analysis"), "display_order", "analysis_id"):
        country = names.get(text(row.get("location_id")))
        if not country:
            continue
        cid = text(row.get("competitor_id"))
        out[country].append({
            "id": text(row.get("analysis_id")),
            "kind": row.get("kind"),
            "cid": cid or None,
            "comp": (competitors.get(cid) or {}).get("name"),
            "ksslProduct": kssl.get(text(row.get("kssl_product_id"))),
            "finding": row.get("finding"),
            "reasons": list(row.get("stated_reasons") or []),
            "reasonState": row.get("reason_state"),
            "hypothesis": row.get("hypothesis"),
            "toFindOut": row.get("to_find_out"),
            "url": row.get("source_url"),
            "_src": src("competitive_geo_analysis", "analysis_id", row),
        })
    return dict(out)


# --------------------------------------------------------------------------- Patents

def build_patents(database, competitors):
    """Flat records grouped byArea / byAssignee, the shape dataset.js adaptPatents reads."""
    portfolios = {text(p.get("portfolio_id")): p for p in table(database, "serving", "competitive_patent_portfolio")}
    by_area, by_assignee, areas, providers = defaultdict(list), defaultdict(list), [], []
    total = 0
    for f in ordered(table(database, "serving", "competitive_patent_filing"), "filed_date", "filing_id"):
        pf = portfolios.get(text(f.get("portfolio_id")))
        if pf is None:
            continue
        cid = text(pf.get("competitor_id"))
        assignee = (competitors.get(cid) or {}).get("name")
        total += 1
        rec = {
            "no": f.get("publication_number"),        # never the internal filing_id: no published number, no number shown
            "title": f.get("title"),
            "assignee": assignee,
            "comp_id": cid or None,
            "status": f.get("status"),
            "filed": f.get("filed_date"),
            "country": f.get("jurisdiction"),
            "ipc": [f.get("classification_code")] if f.get("classification_code") else [],
            "ipcText": f.get("classification_text"),
            "area": f.get("area_label"),
            "threat": f.get("threat_level"),
            "relev": f.get("client_relevance"),
            "url": f.get("patent_url"),
            # keyed like the review graph: publication_number, else filing_id
            "_src": src("competitive_patent_filing", "publication_number" if f.get("publication_number") is not None else "filing_id", f),
        }
        if assignee:
            by_assignee[assignee].append(rec)
        if rec["area"]:
            by_area[rec["area"]].append(rec)
            if rec["area"] not in areas:
                areas.append(rec["area"])
        note = pf.get("data_source_note")
        if note and note not in providers:
            providers.append(note)
    return {"techAreas": sorted(areas, key=str.lower), "byArea": dict(by_area), "byAssignee": dict(by_assignee),
            "_meta": {"total": total, "providers": providers}}


def build(database, d):
    competitors = d["competitors"]
    geo_data, geo_presence, geo_comps, geo_countries, act_label = build_geo(database, competitors)
    projects, projects_config = build_projects(database, competitors)
    for cid, partners in build_partners(database, competitors).items():
        competitors[cid]["partners"] = partners
    compsyn, traceids, fieldsyn = build_synthesis(database)
    d.update({
        "geoData": geo_data, "geoPresence": geo_presence, "geoComps": geo_comps,
        "geoCountries": geo_countries, "actLabel": act_label, "geoAnalysis": build_geo_analysis(database, competitors),
        "projects": projects, "projectsConfig": projects_config,
        "PATENTS": build_patents(database, competitors),
        "KSSL_PARTNERS": build_client_partners(database, competitors),
        "REL_LABEL": build_rel_label(database),
        "COMPSYN": compsyn, "TRACEIDS": traceids, "FIELDSYN": fieldsyn,
    })
