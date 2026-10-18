"""Area A: client, competitors (Profile, leaders, locations, news), overview signal feeds + drawers
(competitive and technology), Competitor Moment.

Shapes follow docs/ui_port/MAPPING.md section A (the 137Parallax / Cummins dataset field names). Runs first:
other areas read d["competitors"].

Nothing is defaulted: a missing column value is None (or an empty container for a list the UI indexes into),
never a guessed value. Judgement fields that MAPPING marks not-shipped are not served. Sections hidden through
ui.section_visibility (parallax read, strategic positioning, swot, stock) are served; the UI gates them.

Enumerations the UI expects (stored values, compared case-insensitively; anything else is shown as stored):
  competitive_signal.classification : threat | watch | none (rule s2: none is not shipped); competitive_competitor.threat_level : threat | watch | fav
  competitive_signal_evidence.evidence_group : fact (At a glance rows: label/value, quote = tooltip)
                                               | key_point (Key points bullet = value)
                                               | source (extra source chip: label + source_url)
  competitive_leader_record.record_type      : experience | education
  technology_overview_article.classification : competitor_advance | adoptable (other text is shown as stored)
  technology_overview_article.direction      : threat | watch | fav (empty = no dot)
  competitive_competitor_moment.grade        : a level_code of ui.competitive_competitor_moment_level
  competitive_competitor_swot.swot_type      : strength | weakness (opportunity / threat rows are not read)
"""

import re
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


def _shown(n: Any) -> str | None:
    """A stored number printed without a trailing .0 (display format only)."""
    if n is None:
        return None
    return str(int(n)) if n == int(n) else str(round(n, 6))


def lower(value: Any) -> str | None:
    return None if value in (None, "") else str(value).lower()


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
            kind = text(rec.get("record_type")).lower()
            base = {
                "id": text(rec.get("record_id")),
                "text": rec.get("headline"),   # a free-text line (Excel bullets) when role/org are not split out
                "from": rec.get("start_date"),
                "to": rec.get("end_date"),
                "url": rec.get("source_url"),
                "_src": src("competitive_leader_record", "record_id", rec.get("record_id")),
            }
            if kind == "experience":
                experience.append({**base, "company": rec.get("institution_or_employer"), "role": rec.get("role_or_degree")})
            elif kind == "education":
                education.append({**base, "institution": rec.get("institution_or_employer"), "degree": rec.get("role_or_degree")})
        # newest first: a record with no start date sorts last
        experience.sort(key=lambda e: e["from"] or "", reverse=True)
        education.sort(key=lambda e: e["from"] or "", reverse=True)
        leaders[cid].append({
            "id": lid,
            "value": row.get("full_name"),
            "detail": row.get("role_title"),
            "url": row.get("role_source_url"),
            "full_name": row.get("full_name"),
            "org": row.get("organization"),
            "initials": row.get("avatar_initials"),
            "experience": experience,
            "education": education,
            "_src": src("competitive_leader", "leader_id", lid),
        })
    return leaders


def build_swot(database):
    out = defaultdict(lambda: {"strengths": [], "weaknesses": []})
    for row in table(database, "serving", "competitive_competitor_swot"):
        cid = text(row.get("competitor_id"))
        kind = text(row.get("swot_type")).lower()
        if cid and row.get("statement") and kind in ("strength", "weakness"):
            out[cid]["strengths" if kind == "strength" else "weaknesses"].append(row.get("statement"))
    return out


def _sales(row):
    """{text, fy}: the verbatim revenue text, else the stored amount joined with its currency."""
    fy = row.get("financial_year")
    if row.get("revenue_text") not in (None, ""):
        return {"text": row.get("revenue_text"), "fy": fy}
    amount = _shown(row.get("annual_revenue"))
    if amount is None:
        return None
    currency = row.get("revenue_currency")
    return {"text": amount + (f" {str(currency).strip()}" if currency else ""), "fy": fy}


def build_competitors(database):
    locations = by_key(table(database, "serving", "competitive_competitor_location"), "competitor_id")
    tickers = {text(r.get("competitor_id")): r.get("ticker") for r in table(database, "serving", "competitive_stock_quote")}
    leaders = build_leaders(database)
    swot = build_swot(database)
    result = {}
    for row in table(database, "serving", "competitive_competitor"):
        cid = text(row.get("competitor_id"))
        if not cid:
            continue
        result[cid] = {
            "id": cid,
            "cid": cid,
            "name": row.get("display_name"),
            "legal": row.get("legal_name"),
            "sector": row.get("industry_sector"),
            "hq": row.get("headquarters"),
            "country": row.get("origin_country"),
            "threat": row.get("threat_level"),
            "assess": row.get("parallax_read"),
            "strategic_positioning": row.get("strategic_positioning"),
            "strengths": swot[cid]["strengths"] if cid in swot else [],
            "weaknesses": swot[cid]["weaknesses"] if cid in swot else [],
            "starting_year": first_nonempty(row, "starting_year_text", "starting_year"),
            "company_size": first_nonempty(row, "employee_count_text", "employee_count"),
            "sales": _sales(row),
            "revenue_filter": row.get("revenue_tier"),
            # spec test by code (prompts/derive_comp.py qualify_competitors): same product line AND same market
            "qualifies": row.get("qualifies"),
            "qualificationReason": row.get("qualification_reason"),
            "global_locations": [l.get("location_name") for l in locations.get(cid, []) if l.get("location_name")],
            "ticker": tickers.get(cid),
            "leadership": leaders.get(cid, []),
            "partners": [],
            "products": [],
            "_src": src("competitive_competitor", "competitor_id", cid),
        }
    return result


def _date_key(item):
    return item["date"] or ""


def build_news(database, competitors):
    """competitorNews: cid -> articles newest first. Plain news rows and Competitor Moment rows (ruling R4: a
    moment row carries level / analysis / country / card / lenses; the Moment page keeps only rows with a level)."""
    news = defaultdict(list)
    for row in table(database, "serving", "competitive_news_article"):
        cid = text(row.get("competitor_id"))
        if not cid or not text(row.get("article_id")):
            continue
        news[cid].append({
            "id": text(row.get("article_id")),
            "title": row.get("headline"),
            "description": row.get("description"),
            "source": row.get("publisher"),
            "date": row.get("published_date"),
            "category": row.get("category"),
            "url": row.get("article_url"),
            "image": row.get("image_url"),
            "_src": src("competitive_news_article", "article_id", row.get("article_id")),
        })
    lenses = by_key(table(database, "serving", "competitive_competitor_moment_analysis"), "moment_id")
    moment_steps = by_key(table(database, "serving", "story_step"), "story_id")
    for row in table(database, "serving", "competitive_competitor_moment"):
        cid = text(row.get("competitor_id"))
        mid = text(row.get("moment_id"))
        if not cid or not mid:
            continue
        news[cid].append({
            "id": mid,
            "title": row.get("title"),
            "description": row.get("what_happened"),
            "source": first_nonempty(row, "source_label", "source_domain"),
            "date": row.get("movement_date"),
            "category": row.get("category"),
            "url": row.get("source_url"),
            "image": row.get("image_url"),
            "level": row.get("grade"),
            "analysis": row.get("kssl_analysis"),
            "country": row.get("country_name"),
            "card": mid,
            "changeNote": row.get("change_note"),
            "signalId": text(row.get("signal_id")) or None,
            "program": row.get("program_name"),
            # the steps of the story this move belongs to (dated, sourced), the same thread the signal shows
            "steps": [{"date": t.get("step_date"), "type": t.get("step_type"), "line": t.get("one_line"), "changed": t.get("changed"),
                       "url": t.get("source_url")}
                      for t in ordered(moment_steps.get(text(row.get("story_id")), []), "step_no")] if row.get("story_id") else [],
            "lenses": [{"view": a.get("view_name"), "text": a.get("analysis_text")}
                       for a in ordered(lenses.get(mid, []), "display_order")],
            "_src": src("competitive_competitor_moment", "moment_id", mid),
        })
    for rows in news.values():
        rows.sort(key=_date_key, reverse=True)
    return dict(news)


def evidence_parts(rows):
    facts, points, srcs = [], [], []
    for ev in ordered(rows, "display_order"):
        group = text(ev.get("evidence_group")).lower()
        if group == "fact":
            facts.append([ev.get("label"), ev.get("value"), ev.get("quote")])
        elif group == "key_point":
            if ev.get("value"):
                points.append([ev.get("label"), ev.get("value")])
        elif group == "source":
            srcs.append({"label": ev.get("label"), "url": ev.get("source_url")})
    return facts, points, srcs


GLANCE = (("glance_who", "Who"), ("glance_move", "Move"), ("glance_where", "Where"),
          ("glance_impact", "Impact on {client}"), ("glance_third_party", "Third party"), ("glance_when", "When"))


def visible_database(database: dict) -> dict:
    """The tables the dataset is built from, with every competitor that does not qualify taken out (user decision 2026-10-18: the UI
    shows only competitors with competitive_competitor.qualifies = true, plus the client; NULL = not testable = hidden too). The
    database keeps every row: this is a view, and a competitor that starts to qualify appears on the next dataset.
    Removed: rows that name a hidden competitor by id (competitor_id, or company_id of a signal), every row hanging off a removed row
    (review.GRAPH child -> parent links, transitively: products, specs, matchups, signals, partnerships, projects, patents, stories,
    moves ...), rival rows that name one by name (tender competitor fit, opportunity rivals), technology companies of that name and
    the articles they lead; a rival_to_beat / rival_display / selected_competitor_id naming one is emptied."""
    from backend.review import ALT_KEY, GRAPH
    from prompts.derive_comp import norm_org

    serving, ui = database.get("serving", {}), database.get("ui", {})
    comps = serving.get("competitive_competitor", [])
    hidden = {text(r.get("competitor_id")) for r in comps if r.get("qualifies") is not True}
    if not hidden:
        return database
    names = {norm_org(r.get(k)) for r in comps if text(r.get("competitor_id")) in hidden
             for k in ("display_name", "short_name", "legal_name") if r.get(k)} - {""}
    # + every name the news job matches for the company (db/news_aliases.csv: search name, aliases, conditional acronyms such as
    # "HII"), so a technology company stored as "HII" is the same company as "Huntington Ingalls Industries"
    from backend.news import subject_for
    for r in comps:
        if text(r.get("competitor_id")) in hidden:
            sub = subject_for(text(r.get("competitor_id")), r.get("display_name") or "", r.get("legal_name") or "", r.get("short_name") or "")
            names |= {norm_org(n) for n in (*sub.names, *(a for a, _ in sub.cond))} - {""}
    # an alias shared with a company that IS shown is ambiguous ("KNDS" = KNDS Germany, but also "Nexter (KNDS France)"): not used
    shown = set()
    for r in comps:
        if text(r.get("competitor_id")) not in hidden:
            for v in (r.get("display_name"), r.get("short_name"), r.get("legal_name")):
                shown |= {norm_org(v)} | {norm_org(x) for x in re.findall(r"\(([^)]*)\)", str(v or ""))}
    shown -= {""}
    names = {h for h in names if not any(q == h or q.startswith(h + " ") for q in shown)}

    def named(v) -> bool:                    # the text (or its bracketed part: "HII (Huntington Ingalls Industries)") is or starts with a hidden name
        parts = [norm_org(v)] + [norm_org(x) for x in re.findall(r"\(([^)]*)\)", str(v or ""))]
        return any(n and (n == h or n.startswith(h + " ")) for n in parts for h in names if len(h) >= 3)

    key_of = lambda t: ALT_KEY.get(t) or (GRAPH.get(t) or (None,))[0]  # noqa: E731
    gone: dict = {"competitive_competitor": set(hidden)}
    NAME_ROWS = {"market_tender_competitor_fit": "competitor_name", "market_opportunity_fit_assessment": "rival_name"}
    tech_hidden = {text(r.get("company_id")) for r in serving.get("technology_company", []) if named(r.get("display_name"))}
    gone["technology_company"] = tech_hidden

    def direct(t, r) -> bool:
        return (text(r.get("competitor_id")) in hidden
                or (t == "competitive_signal" and text(r.get("company_id")) in hidden)
                or (t in NAME_ROWS and named(r.get(NAME_ROWS[t])))
                or (t in ("technology_overview_company", "technology_innovation_company") and text(r.get("company_id")) in tech_hidden)
                or (t == "technology_overview_article" and text(r.get("primary_company_id")) in tech_hidden))

    out = {t: list(rows) for t, rows in serving.items()}
    changed = True
    while changed:                           # cascade until no table loses another row
        changed = False
        for t, rows in out.items():
            parents = [(fk, p) for fk, p in (GRAPH.get(t) or (None, None, []))[2] if gone.get(p)]
            keep, drop = [], []
            for r in rows:
                (drop if direct(t, r) or any(text(r.get(fk)) in gone[p] for fk, p in parents) else keep).append(r)
            if drop:
                k = key_of(t)
                if k:
                    gone.setdefault(t, set()).update(text(r.get(k)) for r in drop)
                out[t] = keep
                changed = True
    for t in ("market_top_opportunity_tender", "market_top_opportunity_project"):
        out[t] = [{**r, "rival_to_beat": None} if named(r.get("rival_to_beat")) else r for r in out.get(t, [])]
    ui_out = {}
    for t, rows in ui.items():
        rows = [r for r in rows if text(r.get("competitor_id")) not in hidden]
        ui_out[t] = [{**r, **{c: None for c in ("rival_display",) if named(r.get(c))},
                      **{c: None for c in ("selected_competitor_id",) if text(r.get(c)) in hidden}} for r in rows]
    return {**database, "serving": out, "ui": ui_out}


def client_of(database) -> str | None:
    """client_account.client_name of the (single) client row; None when the table is empty."""
    rows = table(database, "serving", "client_account")
    return rows[0].get("client_name") if rows else None


def signal_v2(database, row, det, labels, steps_by, stories, news_by, products):
    """v2 drawer parts (glance, risk, story timeline, product news); {} for a v1 row with no scores."""
    if row.get("probability") is None:
        return {}
    lab = lambda col, code, t="competitive_signal": labels.get((t, col, text(code))) or code  # noqa: E731
    client = client_of(database)
    story_id = text(row.get("story_id"))
    story = stories.get(story_id) or {}
    return {
        "v2": True,
        # the client is named from client_account, never typed (no client row: the label carries no name)
        "glance": [[name.format(client=client) if client else name.replace(" on {client}", ""), det.get(col)]
                   for col, name in GLANCE if det and det.get(col)],
        "story": {
            "title": story.get("title"),
            "label": lab("label_after", story.get("current_label"), "story_step"),
            "steps": [{"date": s.get("step_date"), "type": lab("step_type", s.get("step_type"), "story_step"),
                       "line": s.get("one_line"), "changed": s.get("changed"), "url": s.get("source_url"),
                       "label": lab("label_after", s.get("label_after"), "story_step") if s.get("label_after") else None,
                       "current": bool(det) and s.get("source_url") == det.get("source_url")}
                      for s in ordered(steps_by.get(story_id, []), "step_no")],
        } if story else None,
        "productNews": [{"product": (products.get(text(n.get("product_id"))) or {}).get("product_name"),
                         "productId": text(n.get("product_id")) or None,
                         "type": lab("news_type", n.get("news_type"), "competitive_product_news"),
                         "date": n.get("event_date") or n.get("published_date"),
                         "variant": n.get("product_variant"), "relevance": n.get("kssl_relevance")}
                        for n in news_by.get(story_id, [])],
    }


def published_text(row):
    """The card date: published_date, cut to what the source states (published_precision 'year' -> "2019",
    'month' -> "2019-05"; SP's Land Forces prints only "Issue 2 - 2019"). NULL precision = the full date."""
    cut = {"year": 4, "month": 7}.get(row.get("published_precision"))
    d = row.get("published_date")
    return str(d)[:cut] if cut and d else d


def build_signals(database, competitors, details):
    """competitive_signal -> competitive feed cards + drawers."""
    evidence = by_key(table(database, "serving", "competitive_signal_evidence"), "signal_id")
    detail_rows = {text(r.get("signal_id")): r for r in table(database, "serving", "competitive_signal_detail")}
    labels = {(r.get("table_name"), r.get("column_name"), text(r.get("code"))): r.get("label")
              for r in table(database, "ui", "code_label")}
    stories = {text(r.get("story_id")): r for r in table(database, "serving", "story")}
    steps_by = by_key(table(database, "serving", "story_step"), "story_id")
    news_by = by_key(table(database, "serving", "competitive_product_news"), "story_id")
    products = {text(r.get("product_id")): r for r in table(database, "serving", "competitive_product")}
    cards = []
    for row in ordered(table(database, "serving", "competitive_signal"), "sequence_no"):
        sid = text(row.get("signal_id"))
        if not sid:
            continue
        company_id = text(row.get("company_id"))
        company = (competitors.get(company_id) or {}).get("name")
        classification = row.get("classification")
        if lower(classification) == "none":     # rule s2: happened already, low impact -- stored (stories, Trace), not on the overview
            continue
        det = detail_rows.get(sid)
        facts, points, extra = evidence_parts(evidence.get(sid, []))
        url = det.get("source_url") if det else None
        card = {
            "id": sid,
            "dir": lower(classification),
            "classification": classification,
            "seq": row.get("sequence_no"),
            "title": row.get("title"),
            "company": company,
            "companyId": company_id or None,
            "meta": row.get("category"),
            "tags": row.get("category"),
            # the card date is the article's publication date (db/setup/15_signal_published_date.sql); the date of the
            # event it reports is a different fact, shipped beside it. No publication date -> no card date.
            "ago": published_text(row),
            "eventDate": row.get("event_date"),
            "sowhat": row.get("summary"),
            "url": url,
            "image": row.get("thumbnail_url"),
            # ponytail: risk = probability x impact (1-25), the threat sort key
            "risk": row["probability"] * row["impact"] if row.get("probability") is not None and row.get("impact") is not None else None,
            # the threat tie-breaks after risk: sooner effect, then in a client market (the matrix itself is backend-only)
            "timeToEffect": row.get("time_to_effect"),
            "inClientMarket": row.get("in_client_market"),
            "ksslImpact": det.get("why_it_matters") if det else None,
            "ksslImpactKind": lower(classification),
            "sec": [],
            "_src": src("competitive_signal", "signal_id", sid),
        }
        cards.append(card)
        if det is None:
            continue
        srcs = [{"label": det.get("source_name"), "url": det.get("source_url")}] + extra
        details[sid] = {
            "id": sid,
            "dir": lower(classification),
            "title": det.get("drawer_title"),
            "facts": facts,
            "what": det.get("what_article_says"),
            "why": det.get("why_it_matters"),
            "lens": points,
            "url": det.get("source_url"),
            "srcs": [s for s in srcs if s["url"]],
            "provenance": det.get("provenance"),
            "image": row.get("thumbnail_url"),
            "ksslImpact": det.get("why_it_matters"),
            "ksslImpactKind": lower(classification),
            "eyebrow": det.get("impact_eyebrow"),
            "suggest": [det.get("ask_box_query")] if det.get("ask_box_query") else [],
            "_src": src("competitive_signal", "signal_id", sid),
            **signal_v2(database, row, det, labels, steps_by, stories, news_by, products),
        }
    return cards


TECH_KIND = {"competitor_advance": "rival-advance", "adoptable": "tech-advance", "threat_to_position": "threat", "industry_trend": "trend"}


def build_tech_articles(database, competitors, details):
    """technology_overview_* -> Technology overview feed cards + drawers."""
    companies = {text(r.get("company_id")): r for r in table(database, "serving", "technology_company")}
    sources = {text(r.get("source_id")): r for r in table(database, "serving", "technology_source")}
    facts_by = by_key(table(database, "serving", "technology_overview_fact"), "article_id")
    points_by = by_key(table(database, "serving", "technology_overview_key_point"), "article_id")
    srcs_by = by_key(table(database, "serving", "technology_overview_source"), "article_id")
    cards = []
    for row in ordered(table(database, "serving", "technology_overview_article"), "sequence_no"):
        raw_aid = text(row.get("article_id"))
        if not raw_aid:
            continue
        aid = "tech-" + raw_aid   # card / details id: prefixed per source table; _src.id stays the raw key
        primary = companies.get(text(row.get("primary_company_id"))) or {}
        classification = row.get("classification")
        kind = TECH_KIND.get(text(classification).lower())
        src_rows = ordered(srcs_by.get(raw_aid, []), "display_order")
        srcs, statuses = [], []
        for sr in src_rows:
            info = sources.get(text(sr.get("source_id"))) or {}
            url = first_nonempty(info, "source_url", "url")
            if url:
                srcs.append({"label": info.get("label"), "url": url})
            status = sr.get("provenance_status")
            if status and status not in statuses:
                statuses.append(status)
        # technology_overview_article has two date columns; published_on is the stored publication date
        date = first_nonempty(row, "published_on", "article_date")
        card_src = src("technology_overview_article", "overview_article_id", row.get("overview_article_id"))
        card = {
            "id": aid,
            "dir": lower(row.get("direction")),
            "classification": classification,
            "seq": row.get("sequence_no"),
            "title": row.get("title"),
            "company": primary.get("display_name"),
            "competitor": primary.get("display_name") if kind == "rival-advance" else None,
            "lens": row.get("lens"),
            "meta": row.get("category_text"),
            "tags": row.get("category_text"),
            "ago": date,
            "sowhat": row.get("card_summary"),
            "url": srcs[0]["url"] if srcs else None,
            "image": row.get("image_url"),
            "ksslImpact": row.get("client_narrative"),
            "ksslImpactKind": kind,
            "sec": [],
            "_src": card_src,
            # v2 scores (maturity 1-5, relevance 1-5, horizon, KSSL position) for the maturity x relevance view; the label is `dir`
            "maturity": row.get("maturity"), "relevance": row.get("relevance"), "horizon": row.get("horizon"),
            "horizonSource": row.get("horizon_source"), "clientPosition": row.get("client_position"), "storyId": row.get("story_id"),
        }
        cards.append(card)
        details[aid] = {
            "id": aid,
            "dir": lower(row.get("direction")),
            "title": row.get("title"),
            "facts": [[f.get("ui_label"), f.get("fact_value"), f.get("proof_text")]
                      for f in ordered(facts_by.get(raw_aid, []), "display_order")],
            "what": row.get("article_says"),
            "why": row.get("client_narrative"),
            "lens": [[None, p.get("point_text")] for p in ordered(points_by.get(raw_aid, []), "display_order", "point_no")
                     if p.get("point_text")],
            "url": card["url"],
            "srcs": srcs,
            "provenance": " · ".join(statuses) if statuses else None,
            "image": row.get("image_url"),
            "ksslImpact": row.get("client_narrative"),
            "ksslImpactKind": kind,
            "eyebrow": None,
            "suggest": [],
            "_src": card_src,
        }
    return cards


def build(database, d):
    account_rows = table(database, "serving", "client_account")
    account = account_rows[0] if account_rows else {}
    client_id = text(account.get("client_id"))
    client_name = first_nonempty(account, "client_name", "legal_name", "brand_name")
    client_short = first_nonempty(account, "brand_name", "client_name")
    competitors = build_competitors(database)
    comp_order = sorted(competitors, key=lambda c: (competitors[c]["name"] or "").lower())
    client = {"id": client_id or None, "name": client_name, "short": client_short,
              "_src": src("client_account", "client_id", client_id) if account else None}
    if client_id and client_id not in competitors:
        competitors[client_id] = {
            "id": client_id, "cid": client_id, "name": client_name, "dir": "client",
            "sector": account.get("industry_sector"), "hq": account.get("headquarters"),
            "country": account.get("country"), "strategic_positioning": account.get("strategic_positioning"),
            "leadership": [], "global_locations": [], "partners": [], "products": [],
            "_src": src("client_account", "client_id", client_id),
        }
    details = d["details"]
    competitive_cards = build_signals(database, competitors, details)
    tech_cards = build_tech_articles(database, competitors, details)
    # titles, counts, tiles, groups and pills are labels: the UI reads them from data.database.<ui table> (E)
    # (the lane cards are rebuilt in the browser from competitiveCards / marketCards / techCards: A, overviewConfig)
    lane = {"title": None, "cnt": None, "metrics": [], "groups": [], "filters": [], "dirWord": {}, "badgeClass": {}, "cards": []}
    d.update({
        "client": client,
        "competitors": competitors,
        "compOrder": comp_order,
        "competitorNews": build_news(database, competitors),
        # the market lane belongs to area D; it fills marketCards itself
        "overviewConfig": {"competitive": dict(lane), "market": dict(lane), "technology": dict(lane)},
        "competitiveCards": competitive_cards,
        "marketCards": [],
        "techCards": tech_cards,
    })
