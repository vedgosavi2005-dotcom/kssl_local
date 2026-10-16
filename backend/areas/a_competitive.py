"""Area A: client, competitors (Profile, leaders, locations, news), overview signal feeds + drawers
(competitive and technology), Competitor Moment.

Audit: docs/audit_v2/A_overview_profile_moment.md. Runs first: other areas read d["competitors"].

Nothing is defaulted: a missing value is "" / None / [] and the UI hides the element.
Hidden by decision and therefore NOT served: competitive_competitor.strategic_positioning,
parallax_read, competitive_competitor_swot, stock tables, product images.

Enumerations the UI expects (stored values, compared case-insensitively; anything else is shown as stored):
  competitive_signal.classification / competitive_competitor.threat_level : threat | watch | fav
  competitive_signal_evidence.evidence_group : fact (At a glance rows: label/value, quote = tooltip)
                                               | key_point (Key points bullet = value, quote = tooltip)
                                               | source (extra source chip: label + source_url)
  competitive_leader_record.record_type      : experience | education
  technology_overview_article.classification : competitor_advance | adoptable (other text is shown as stored)
  technology_overview_article.direction      : threat | watch | fav (colour of the card dot; empty = no dot)
  competitive_competitor_moment.grade        : a level_code of ui.competitive_competitor_moment_level
  ui.competitive_competitor_moment_level.tag_class : threat | watch | fav | opportunity | kssl | neutral
"""

from collections import defaultdict
from typing import Any

from backend.common import first_nonempty, table, text


def src(table_name: str, key: str, value: Any) -> dict:
    return {"t": table_name, "k": key, "id": text(value)}


def by_key(rows, key):
    grouped = defaultdict(list)
    for row in rows:
        k = text(row.get(key))
        if k:
            grouped[k].append(row)
    return grouped


def ordered(rows, *names):
    return sorted(rows, key=lambda r: tuple((r.get(n) is None, r.get(n) if r.get(n) is not None else 0) for n in names))


def build_leaders(database):
    records = by_key(table(database, "serving", "competitive_leader_record"), "leader_id")
    leaders = defaultdict(list)
    for row in table(database, "serving", "competitive_leader"):
        lid = text(row.get("leader_id"))
        cid = text(row.get("competitor_id"))
        if not lid or not cid:
            continue
        experience, education = [], []
        for rec in records.get(lid, []):
            item = {
                "id": text(rec.get("record_id")),
                "role": text(rec.get("role_or_degree")),
                "org": text(rec.get("institution_or_employer")),
                "from": text(rec.get("start_date")),
                "to": text(rec.get("end_date")),
                "url": text(rec.get("source_url")),
                "_src": src("competitive_leader_record", "record_id", rec.get("record_id")),
            }
            kind = text(rec.get("record_type")).lower()
            if kind == "experience":
                experience.append(item)
            elif kind == "education":
                education.append(item)
        # newest first: a record with no start date sorts last
        experience.sort(key=lambda e: e["from"], reverse=True)
        education.sort(key=lambda e: e["from"], reverse=True)
        leaders[cid].append({
            "id": lid,
            "name": text(row.get("full_name")),
            "role": text(row.get("role_title")),
            "org": text(row.get("organization")),
            "initials": text(row.get("avatar_initials")),
            "url": text(row.get("role_source_url")),
            "experience": experience,
            "education": education,
            "_src": src("competitive_leader", "leader_id", lid),
        })
    return leaders


def build_competitors(database):
    locations = by_key(table(database, "serving", "competitive_competitor_location"), "competitor_id")
    leaders = build_leaders(database)
    result = {}
    order = []
    for row in table(database, "serving", "competitive_competitor"):
        cid = text(row.get("competitor_id"))
        if not cid:
            continue
        result[cid] = {
            "id": cid,
            "cid": cid,
            "name": text(row.get("display_name")),
            "short": text(row.get("short_name")),
            "legal": text(row.get("legal_name")),
            "threat": text(row.get("threat_level")),
            "origin": text(row.get("origin_country")),
            "sector": text(row.get("industry_sector")),
            "hq": text(row.get("headquarters")),
            "starting_year": row.get("starting_year"),
            "global_locations": text(row.get("global_locations")),
            "locations": [
                {"id": text(l.get("location_id")), "name": text(l.get("location_name")),
                 "type": text(l.get("location_type")), "country": text(l.get("country")),
                 "url": text(l.get("source_url")),
                 "_src": src("competitive_competitor_location", "location_id", l.get("location_id"))}
                for l in locations.get(cid, [])
            ],
            "company_size": row.get("employee_count"),
            "revenue": row.get("annual_revenue"),
            "revenue_currency": text(row.get("revenue_currency")),
            "revenue_tier": text(row.get("revenue_tier")),
            "leaders": leaders.get(cid, []),
            "partners": [],
            "products": [],
            "_src": src("competitive_competitor", "competitor_id", cid),
        }
        order.append(cid)
    return result, order


def build_news(database):
    news = defaultdict(list)
    for row in table(database, "serving", "competitive_news_article"):
        cid = text(row.get("competitor_id"))
        if not cid:
            continue
        news[cid].append({
            "id": text(row.get("article_id")),
            "title": text(row.get("headline")),
            "url": text(row.get("article_url")),
            "source": text(row.get("publisher")),
            "category": text(row.get("category")),
            "date": text(row.get("published_date")),
            "image": text(row.get("image_url")),
            "_src": src("competitive_news_article", "article_id", row.get("article_id")),
        })
    for rows in news.values():
        rows.sort(key=lambda r: r["date"], reverse=True)
    return dict(news)


def evidence_parts(rows):
    facts, points, srcs = [], [], []
    for ev in ordered(rows, "display_order"):
        group = text(ev.get("evidence_group")).lower()
        if group == "fact":
            facts.append([text(ev.get("label")), text(ev.get("value")), text(ev.get("quote"))])
        elif group == "key_point":
            if text(ev.get("value")):
                points.append({"text": text(ev.get("value")), "quote": text(ev.get("quote"))})
        elif group == "source":
            srcs.append({"label": text(ev.get("label")), "url": text(ev.get("source_url"))})
    return facts, points, srcs


def build_signals(database, competitors, details):
    """competitive_signal -> competitive feed cards + drawers."""
    evidence = by_key(table(database, "serving", "competitive_signal_evidence"), "signal_id")
    detail_rows = {text(r.get("signal_id")): r for r in table(database, "serving", "competitive_signal_detail")}
    cards = []
    for row in table(database, "serving", "competitive_signal"):
        sid = text(row.get("signal_id"))
        if not sid:
            continue
        company_id = text(row.get("company_id"))
        company = (competitors.get(company_id) or {}).get("name", "")
        classification = text(row.get("classification"))
        cards.append({
            "id": sid,
            "dir": classification.lower(),
            "classification": classification,
            "seq": row.get("sequence_no"),
            "title": text(row.get("title")),
            "company": company,
            "companyId": company_id,
            "meta": text(row.get("category")),
            "tags": text(row.get("category")),
            "ago": text(row.get("event_date")),
            "sowhat": text(row.get("summary")),
            "sec": [],
            "_src": src("competitive_signal", "signal_id", sid),
        })
        det = detail_rows.get(sid)
        if det is None:
            continue
        facts, points, extra = evidence_parts(evidence.get(sid, []))
        srcs = [{"label": text(det.get("source_name")), "url": text(det.get("source_url"))}] + extra
        details[sid] = {
            "id": sid,
            "dir": classification.lower(),
            "title": text(det.get("drawer_title")),
            "what": text(det.get("what_article_says")),
            "why": text(det.get("why_it_matters")),
            "eyebrow": text(det.get("impact_eyebrow")),
            "provenance": text(det.get("provenance")),
            "image": text(row.get("thumbnail_url")),
            "facts": facts,
            "points": points,
            "srcs": [s for s in srcs if s["url"]],
            "_src": src("competitive_signal", "signal_id", sid),
        }
    return cards


def build_tech_articles(database, details):
    """technology_overview_* -> Technology overview feed cards + drawers."""
    companies = {text(r.get("company_id")): r for r in table(database, "serving", "technology_company")}
    sources = {text(r.get("source_id")): r for r in table(database, "serving", "technology_source")}
    facts_by = by_key(table(database, "serving", "technology_overview_fact"), "article_id")
    points_by = by_key(table(database, "serving", "technology_overview_key_point"), "article_id")
    comps_by = by_key(table(database, "serving", "technology_overview_company"), "article_id")
    srcs_by = by_key(table(database, "serving", "technology_overview_source"), "article_id")
    cards = []
    for row in table(database, "serving", "technology_overview_article"):
        aid = text(row.get("article_id"))
        if not aid:
            continue
        primary = companies.get(text(row.get("primary_company_id"))) or {}
        # technology_overview_article has two date columns; published_on is the stored publication date
        date = text(first_nonempty(row, "published_on", "article_date"))
        classification = text(row.get("classification"))
        cards.append({
            "id": aid,
            "dir": text(row.get("direction")).lower(),
            "classification": classification,
            "seq": row.get("sequence_no"),
            "title": text(row.get("title")),
            "company": text(primary.get("display_name")),
            "meta": text(row.get("category_text")),
            "tags": text(row.get("category_text")),
            "ago": date,
            "sowhat": text(row.get("card_summary")),
            "sec": [],
            "_src": src("technology_overview_article", "overview_article_id", row.get("overview_article_id")),
        })
        co_rows = ordered(comps_by.get(aid, []), "display_order")
        companies_list = []
        for co in co_rows:
            info = companies.get(text(co.get("company_id"))) or {}
            name = text(first_nonempty(co, "display_label")) or text(info.get("display_name"))
            if name:
                companies_list.append({"name": name, "relationship": text(co.get("relationship_type") or co.get("relationship"))})
        src_rows = ordered(srcs_by.get(aid, []), "display_order")
        srcs, statuses = [], []
        for sr in src_rows:
            info = sources.get(text(sr.get("source_id"))) or {}
            url = text(first_nonempty(info, "source_url", "url"))
            if url:
                srcs.append({"label": text(info.get("label")), "url": url})
            status = text(sr.get("provenance_status"))
            if status and status not in statuses:
                statuses.append(status)
        details[aid] = {
            "id": aid,
            "dir": text(row.get("direction")).lower(),
            "title": text(row.get("title")),
            "what": text(row.get("article_says")),
            "why": text(row.get("client_narrative")),
            "eyebrow": "",
            "provenance": " · ".join(statuses),
            "image": text(row.get("image_url")),
            "facts": [[text(f.get("ui_label")), text(f.get("fact_value")), text(f.get("proof_text"))]
                      for f in ordered(facts_by.get(aid, []), "display_order")],
            "points": [{"text": text(p.get("point_text")), "quote": text(p.get("evidence_text"))}
                       for p in ordered(points_by.get(aid, []), "display_order", "point_no")
                       if text(p.get("point_text"))],
            "companies": companies_list,
            "srcs": srcs,
            "_src": src("technology_overview_article", "overview_article_id", row.get("overview_article_id")),
        }
    return cards


def build_competitor_moment(database, competitors):
    comps = [
        {"cid": cid, "name": c["name"], "short": c["short"], "threat": c["threat"]}
        for cid, c in competitors.items() if c.get("dir") != "client"
    ]
    analyses = by_key(table(database, "serving", "competitive_competitor_moment_analysis"), "moment_id")
    msources = by_key(table(database, "serving", "competitive_competitor_moment_source"), "moment_id")
    items = []
    for row in table(database, "serving", "competitive_competitor_moment"):
        mid = text(row.get("moment_id"))
        if not mid:
            continue
        items.append({
            "id": mid,
            "cid": text(row.get("competitor_id")),
            "company": text(row.get("company_display")),
            "date": text(row.get("movement_date")),
            "category": text(row.get("category")),
            "country": text(first_nonempty(row, "country_name", "countries")),
            "region": text(row.get("region")),
            "program": text(row.get("program_name")),
            "title": text(row.get("title")),
            "summary": text(row.get("card_summary")),
            "whatHappened": text(row.get("what_happened")),
            "analysis": text(row.get("kssl_analysis")),
            "level": text(row.get("grade")),
            "source": text(first_nonempty(row, "source_label", "source_domain")),
            "url": text(row.get("source_url")),
            "image": text(row.get("image_url")),
            "order": row.get("display_order"),
            "deeper": [{"view": text(a.get("view_name")), "text": text(a.get("analysis_text"))}
                       for a in ordered(analyses.get(mid, []), "display_order")],
            "sources": [{"publisher": text(first_nonempty(s, "publisher", "source_domain")), "url": text(s.get("source_url"))}
                        for s in msources.get(mid, [])],
            "_src": src("competitive_competitor_moment", "moment_id", mid),
        })
    windows = [
        {"id": text(r.get("time_window_code")), "label": text(r.get("time_window_label")),
         "days": r.get("day_count"), "isDefault": bool(r.get("is_default"))}
        for r in ordered(table(database, "ui", "competitive_competitor_moment_time_window"), "display_order")
    ]
    levels = {}
    for r in ordered(table(database, "ui", "competitive_competitor_moment_level"), "display_order"):
        code = text(r.get("level_code")).lower()
        if code:
            levels[code] = {"label": text(r.get("level_label")), "tagClass": text(r.get("tag_class")).lower()}
    return {"competitors": comps, "items": items, "timeWindows": windows, "levels": levels}


def build(database, d):
    account_rows = table(database, "serving", "client_account")
    account = account_rows[0] if account_rows else {}
    client_id = text(account.get("client_id"))
    client_name = text(first_nonempty(account, "client_name", "legal_name", "brand_name"))
    client_short = text(first_nonempty(account, "brand_name", "client_name"))
    competitors, comp_order = build_competitors(database)
    client = {"id": client_id, "name": client_name, "short": client_short,
              "_src": src("client_account", "client_id", client_id) if account else None}
    if client_id and client_id not in competitors:
        competitors[client_id] = {"id": client_id, "cid": client_id, "name": client_name, "short": client_short,
                                  "dir": "client", "partners": [], "products": [], "leaders": [], "locations": []}
    details = d["details"]
    competitive_cards = build_signals(database, competitors, details)
    tech_cards = build_tech_articles(database, details)
    empty_config = {"title": "", "cnt": "", "filters": [], "groups": [], "cards": [], "metrics": [], "dirWord": {}, "badgeClass": {}}
    d.update({
        "client": client,
        "competitors": competitors,
        "compOrder": comp_order,
        "competitorNews": build_news(database),
        # the market lane belongs to area D; it fills marketCards / overviewConfig.market itself
        "overviewConfig": {
            "competitive": {**empty_config, "cards": competitive_cards},
            "market": {**empty_config, "cards": []},
            "technology": {**empty_config, "cards": tech_cards},
        },
        "competitiveCards": competitive_cards,
        "marketCards": [],
        "techCards": tech_cards,
        "competitorMoment": build_competitor_moment(database, competitors),
        "competitorStructure": {},
        "competitorMetrics": {},
    })
