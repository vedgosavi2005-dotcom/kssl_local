"""What THIS product version's pages show (KSSL_Deploy v2), as searchable documents: the
mapping from the product's own GET /api/dataset (built from the live serving + ui tables) to
blocks of pages.

Every document says where it lives: page = {pillar, view, payload} that opens it on the right
item (None when no single page shows it), block = the section heading or item text to scroll
to. The service (service/agent/product_ui.py) does the fetching, ranking and reading; this
file only knows the dataset's shape. Sections the product hides (dataset["sectionVisibility"]:
a key counts as shown only when it is exactly true) are not indexed, so the agent never
quotes or points at a hidden section.

  KINDS                  the document kinds (search_platform's `kind` filter)
  INTENT                 question words -> the kind (or doc id suffix) that answers them
  build(dataset, m)      -> {doc_id: {id, kind, title, text, page, block, company}}
  meta(dataset)          -> {"companies": {comp_id: name}, "client": name}
  live_news(get, cid, name, meta)   live headlines through the product's /api/pulse
"""

import re

KINDS = ["company", "partners", "products", "sites", "news", "tender", "matchup", "signal", "innovation", "award",
         "patent", "project", "opportunity"]


def _plain(v) -> str:
    s = re.sub(r"<[^>]*>", " ", str(v if v is not None else ""))
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def _join(items, sep=" | ") -> str:
    return sep.join(x for x in (_plain(i) for i in items or []) if x)


def _pairs(rows) -> str:
    """[[label, value(, quote)], ...] or {label: value} -> 'label: value; ...'"""
    if isinstance(rows, dict):
        rows = list(rows.items())
    out = []
    for r in rows or []:
        if isinstance(r, (list, tuple)) and len(r) >= 2 and _plain(r[1]):
            out.append(f"{_plain(r[0])}: {_plain(r[1])}")
        elif isinstance(r, dict) and (r.get("k") or r.get("l")):
            out.append(f"{_plain(r.get('k') or r.get('l'))}: {_plain(r.get('v'))}")
    return "; ".join(out)


def _doc(docs, did, kind, title, lines, page, block, company=None):
    text = "\n".join(x for x in lines if x).strip() if isinstance(lines, (list, tuple)) else str(lines or "").strip()
    if not text:
        return
    docs[did] = {"id": did, "kind": kind, "title": _plain(title), "text": text, "page": page,
                 "block": _plain(block) if block else None, "company": company}


def _shown(d, key) -> bool:
    return (d.get("sectionVisibility") or {}).get(key) is True


def _visible(d, key) -> bool:
    """a section the product shows unless it is switched off (for sections on by default)"""
    return (d.get("sectionVisibility") or {}).get(key) is not False


def _page(pillar, view, **payload):
    return {"pillar": pillar, "view": view, "payload": {k: v for k, v in payload.items() if v not in (None, "")}}


def build(d: dict, manifest: dict) -> dict:
    """The product's /api/dataset -> {doc_id: doc}. A doc is one block of one page."""
    docs = {}
    comps = d.get("competitors") or {}
    client = d.get("client") or {}
    client_id = str(client.get("id") or "")
    client_name = client.get("name") or "the client"
    names = {cid: c.get("name") or cid for cid, c in comps.items()}

    for cid, c in comps.items():
        name = names[cid]
        is_client = c.get("dir") == "client" or cid == client_id
        profile = None if is_client else _page("competitive", "profile", cid=cid)
        sales = c.get("sales") or {}

        _doc(docs, f"company:{cid}:details", "company", f"{name}: company details", [
            f"Company: {name}" + (" (the client)" if is_client else ""),
            f"Legal name: {_plain(c.get('legal'))}" if c.get("legal") else "",
            f"Starting year: {c.get('starting_year')}" if c.get("starting_year") else "",
            f"Headquarters: {_plain(c.get('hq'))}" if c.get("hq") else "",
            f"Country: {_plain(c.get('country'))}" if c.get("country") else "",
            f"Industry / sector: {_plain(c.get('sector'))}" if c.get("sector") else "",
            f"Company size: {_plain(c.get('company_size'))}" if c.get("company_size") else "",
            (f"Annual revenue / sales: {_plain(sales.get('text'))}" + (f" (FY {sales.get('fy')})" if sales.get("fy") else ""))
            if isinstance(sales, dict) and sales.get("text") else "",
            f"Global locations: {_join(c.get('global_locations'), ', ')}" if c.get("global_locations") else "",
            f"Threat level: {c.get('threat')}" if c.get("threat") else "",
        ], profile, "Company Details", cid)

        # shown only when the product switches these sections on
        if not is_client and (_shown(d, "strategic-positioning") or _shown(d, "parallax-read")):
            _doc(docs, f"company:{cid}:positioning", "company", f"{name}: strategic positioning and Parallax read", [
                _plain(c.get("strategic_positioning")) if _shown(d, "strategic-positioning") else "",
                f"Parallax read: {_plain(c.get('assess'))}" if _shown(d, "parallax-read") and c.get("assess") else "",
            ], profile, "Strategic Positioning" if _shown(d, "strategic-positioning") else "Parallax Read", cid)
        if not is_client and _shown(d, "swot"):
            _doc(docs, f"company:{cid}:read", "company", f"{name}: strengths and weaknesses", [
                f"Strengths: {_join(c.get('strengths'))}" if c.get("strengths") else "",
                f"Weaknesses: {_join(c.get('weaknesses'))}" if c.get("weaknesses") else "",
            ], profile, "Strengths & Weaknesses", cid)

        lead = []
        for p in c.get("leadership") or []:
            if not isinstance(p, dict):
                continue
            past = "; ".join(_plain(x.get("text") or f"{x.get('role')} at {x.get('company')}") for x in (p.get("experience") or [])[:4] if isinstance(x, dict))
            edu = "; ".join(_plain(x.get("text") or f"{x.get('degree')}, {x.get('institution')}") for x in (p.get("education") or [])[:2] if isinstance(x, dict))
            lead.append(f"- {_plain(p.get('value') or p.get('full_name'))}: {_plain(p.get('detail'))}"
                        + (f". Experience: {past}" if past else "") + (f". Education: {edu}" if edu else ""))
        _doc(docs, f"company:{cid}:leadership", "company", f"{name}: leadership team", lead, profile, "Leadership", cid)

        partners = []
        for p in c.get("partners") or []:
            if not isinstance(p, dict):
                continue
            ov = p.get("overlap") or {}
            partners.append(f"- {_plain(p.get('label'))} ({_plain(p.get('ptype') or p.get('rel'))}; {_plain(p.get('country'))}; "
                            f"{_plain(p.get('status'))}): {_plain(p.get('note'))}"
                            + (f" What it means for {client_name}: {_plain(p.get('impact') or p.get('verdict'))}." if p.get("impact") or p.get("verdict") else "")
                            + (f" Overlap with {client_name}: {_plain(ov.get('kind'))} {_plain(ov.get('component'))} {_plain(ov.get('effect'))}." if ov else ""))
        syn = (d.get("COMPSYN") or {}).get(cid) or {}
        if syn.get("thesis") or syn.get("vulns"):
            partners.append(f"Network read: {_plain(syn.get('thesis'))}")
            for v in syn.get("vulns") or []:
                if isinstance(v, dict):
                    partners.append(f"- Vulnerability: {_plain(v.get('title'))}: {_plain(v.get('intel'))}")
        _doc(docs, f"company:{cid}:partners", "partners", f"{name}: partners and alliance network", partners,
             _page("competitive", "partnerships"), name, cid)

        prods = []
        for p in c.get("products") or []:
            if not isinstance(p, dict):
                continue
            prods.append(f"- {_plain(p.get('name'))} ({_plain(p.get('category'))}; {_plain(p.get('status'))}): {_pairs(p.get('specs'))}")
            _doc(docs, f"product:{p.get('id')}", "products", f"{name}: {_plain(p.get('name'))}", [
                f"Product: {_plain(p.get('name'))} by {name}" + (" (the client)" if is_client else ""),
                f"Category: {_plain(p.get('category'))} · status {_plain(p.get('status'))} · country {_plain(p.get('country'))}",
                f"Description: {_plain(p.get('description'))}" if p.get("description") else "",
                f"Technical specifications: {_pairs(p.get('specs'))}" if p.get("specs") else "",
                f"Features and capabilities: {_pairs(p.get('features'))}" if p.get("features") else "",
                "Programs: " + "; ".join(f"{_plain(g.get('title'))} ({_plain(g.get('authority'))}, {g.get('date') or ''}, {_plain(g.get('status'))})"
                                         for g in p.get("programs") or [] if isinstance(g, dict)) if p.get("programs") else "",
                "Product news: " + "; ".join(f"{n.get('date') or ''} {_plain(n.get('title'))}" for n in p.get("news") or [] if isinstance(n, dict))
                if p.get("news") else "",
            ], _page("competitive", "products", cid=cid, productName=p.get("name")), "Technical specifications", cid)
        _doc(docs, f"company:{cid}:products", "products", f"{name}: product portfolio", prods,
             _page("competitive", "products", cid=cid), f"{name} Product Portfolio", cid)

        news, moments = [], []
        for n in (d.get("competitorNews") or {}).get(cid) or []:
            if not isinstance(n, dict):
                continue
            if n.get("level"):
                lens = " | ".join(f"{_plain(x.get('view'))}: {_plain(x.get('text'))}" for x in n.get("lenses") or [] if isinstance(x, dict))
                moments.append(f"- {n.get('date') or ''} [{n.get('level')}] {_plain(n.get('title'))}: {_plain(n.get('description'))}"
                               + (f" What changed: {_plain(n.get('changeNote'))}." if n.get("changeNote") else "")
                               + (f" What it means for {client_name}: {_plain(n.get('analysis'))}" if n.get("analysis") else "")
                               + (f" By view: {lens}" if lens else ""))
            else:
                news.append(f"- {n.get('date') or ''} [{_plain(n.get('category'))}] {_plain(n.get('title'))}: {_plain(n.get('description'))} ({_plain(n.get('source'))})")
        _doc(docs, f"company:{cid}:news", "news", f"{name}: company news", news, profile, "News", cid)
        if _visible(d, "competitor-moment"):
            _doc(docs, f"moment:{cid}", "news", f"{name}: competitor movements (latest moves and what they mean)", moments,
                 _page("competitive", "threat-analysis"), name, cid)

        sites = []
        for country, rows in ((d.get("geoData") or {}).get(cid) or {}).items():
            for s in rows or []:
                if isinstance(s, dict):
                    sites.append(f"- {country}: {_plain(s.get('c'))} · {_plain(s.get('name'))}"
                                 + (f" · quantity {_plain(s.get('qty'))}" if s.get("qty") else "")
                                 + (f" · value {_plain(s.get('val'))}" if s.get("val") else "")
                                 + (f" · customer {_plain(s.get('customer'))}" if s.get("customer") else "")
                                 + (f" · local partner {_plain(s.get('localPartner'))}" if s.get("localPartner") else "")
                                 + (f" · since {_plain(s.get('since'))}" if s.get("since") else "")
                                 + (f". {_plain(s.get('note'))}" if s.get("note") else ""))
        _doc(docs, f"company:{cid}:sites", "sites", f"{name}: footprint by country", sites, _page("competitive", "geo"), name, cid)

    for p in d.get("KSSL_PARTNERS") or []:   # the client's own partners
        if isinstance(p, dict):
            _doc(docs, f"clientpartner:{p.get('id')}", "partners", f"{client_name} partner: {_plain(p.get('label'))}", [
                f"{_plain(p.get('label'))}: {_plain(p.get('ptype') or p.get('rel'))} of {client_name} ({_plain(p.get('country'))}, {_plain(p.get('status'))})",
                _plain(p.get("role")), _plain(p.get("note")),
                f"What it means: {_plain(p.get('mean'))}" if p.get("mean") else "",
                f"Insight: {_plain(p.get('insight'))}" if p.get("insight") else "",
            ], _page("competitive", "partnerships"), _plain(p.get("label")), client_id)

    for country, rows in (d.get("geoAnalysis") or {}).items():
        lines = [f"- {_plain(f.get('kind'))}: {_plain(f.get('comp'))} · {_plain(f.get('finding'))}"
                 + (f" Reasons: {_join(f.get('reasons'), '; ')}." if f.get("reasons") else "")
                 + (f" Hypothesis: {_plain(f.get('hypothesis'))}." if f.get("hypothesis") else "")
                 for f in rows or [] if isinstance(f, dict)]
        _doc(docs, f"geo:{country}", "sites", f"Footprint analysis: {country}", lines, _page("competitive", "geo"), country)

    for t in d.get("tenders") or []:
        req = _pairs(t.get("req"))
        matches = "; ".join(f"{_plain(m.get('n'))} ({m.get('fit')} fit{', ' + str(m.get('pct')) + '%' if m.get('pct') not in (None, '', '—') else ''}): "
                            + " ".join(_plain(l[1]) for l in m.get("lines") or [] if isinstance(l, (list, tuple)) and len(l) > 1)
                            for m in t.get("matches") or [] if isinstance(m, dict))
        rivals = "; ".join(f"{_plain(f.get('company'))} ({_plain(f.get('fit'))}, {_plain(f.get('basis'))}): {_plain(f.get('why'))}"
                           + (f" Products: {_join(f.get('products'), ', ')}." if f.get("products") else "")
                           for f in t.get("competitorFit") or [] if isinstance(f, dict))
        _doc(docs, f"tender:{t.get('id')}", "tender", t.get("title"), [
            f"Tender: {_plain(t.get('title'))}",
            f"Buyer: {_plain(t.get('issuer'))} · Country: {_plain(t.get('country'))} · Category: {_plain(t.get('cat'))} · Status: {t.get('status')}",
            f"Closing: {t.get('closingDate') or _plain(t.get('deadline'))}" if t.get("closingDate") or t.get("deadline") else "",
            f"Quantity: {_plain(t.get('qty'))}" if t.get("qty") else "",
            f"Value stated: {_plain(t.get('value'))}" if t.get("value") else "",
            f"Bid recommendation: {t.get('lean')} - {_plain(t.get('leanTxt'))}" if t.get("lean") or t.get("leanTxt") else "",
            f"{client_name} fit: {t.get('clientFit') or t.get('fit')}" + (f", priority rank #{t.get('rank')}" if t.get("rank") else "")
            + (f", pursue: {t.get('pursue')}" if t.get("pursue") else ""),
            f"Scores: attractiveness {t.get('attractiveness')}, ability {t.get('ability')}, value {t.get('valueScore')}, strategic {t.get('strategicScore')}; time to award {t.get('timeToAward')}"
            if any(t.get(k) is not None for k in ("attractiveness", "ability", "valueScore", "strategicScore")) else "",
            f"Expected revenue (estimate): {_plain(t.get('expectedRevenue'))}" if t.get("expectedRevenue") else "",
            f"Requirements: {req}" if req else "",
            f"Matched {client_name} products: {matches}" if matches else "",
            f"Competitor fit: {rivals}" if rivals else "",
            "Eligibility: " + "; ".join(f"{_plain(e.get('item'))}: {_plain(e.get('state'))}" for e in t.get("eligibility") or [] if isinstance(e, dict))
            if t.get("eligibility") else "",
            "Next steps: " + "; ".join(f"{_plain(a.get('do'))} (by {a.get('due')})" for a in t.get("actions") or [] if isinstance(a, dict))
            if t.get("actions") else "",
            f"Latest milestone: {_plain(t.get('milestone'))}" if t.get("milestone") else "",
            f"Awarded to {_plain(t.get('awardedTo'))} on {t.get('awardDate')} ({_plain(t.get('awardValue'))})" if t.get("awardedTo") else "",
            f"Description: {_plain(t.get('desc'))}" if t.get("desc") else "",
        ], _page("market", "tender", tenderTitle=t.get("title")), "Tender Assessment")

    for mid, m in (d.get("matchups") or {}).items():
        specs = "; ".join(f"{_plain(s.get('l'))}: rival {_plain(s.get('cv'))} vs {client_name} {_plain(s.get('kv'))}{(' ' + s['u']) if s.get('u') else ''}"
                          + (f" (better: {s.get('win')})" if s.get("win") else "")
                          for s in m.get("specs") or [] if isinstance(s, dict))
        _doc(docs, f"matchup:{mid}", "matchup", f"{_plain(m.get('comp'))} vs {_plain(m.get('bf'))}", [
            f"Matchup: {_plain(m.get('comp'))} vs {client_name}'s {_plain(m.get('bf'))}; category {_plain(m.get('cat'))}"
            + (f"; edge {m.get('edge')}/100 from {client_name}'s side (50 = parity)" if m.get("edge") is not None else ""),
            f"Verdict: {_plain(m.get('verdictH'))} {_plain(m.get('verdict'))}",
            f"Rival advantages: {_join(m.get('advComp'))}" if m.get("advComp") else "",
            f"{client_name} advantages: {_join(m.get('advBf'))}" if m.get("advBf") else "",
            f"Specs: {specs}" if specs else "",
        ], _page("competitive", "positioning", matchupId=str(mid)), "Competitor analytics", m.get("compId"))

    details = d.get("details") or {}
    lanes = {"competitiveCards": ("competitive", "overview"), "marketCards": ("market", "m-overview"),
             "techCards": ("technology", "t-overview")}
    for key, (pillar, view) in lanes.items():
        for card in d.get(key) or []:
            det = details.get(card.get("id")) or {}
            lens = " | ".join(f"{_plain(x[0])}: {_plain(x[1])}" for x in det.get("lens") or [] if isinstance(x, (list, tuple)) and len(x) > 1)
            _doc(docs, f"signal:{card.get('id')}", "signal", card.get("title"), [
                f"Signal ({pillar}): {_plain(card.get('title'))} · {_plain(card.get('meta'))}",
                f"Direction: {card.get('dir')} · {_plain(card.get('company'))}" if card.get("dir") or card.get("company") else "",
                f"At a glance: {_pairs(det.get('glance'))}" if det.get("glance") else "",
                f"Facts: {_pairs(det.get('facts'))}" if det.get("facts") else "",
                f"What the article says: {_plain(det.get('what'))}" if det.get("what") else "",
                f"Why it matters to {client_name}: {_plain(det.get('why') or card.get('sowhat'))}" if det.get("why") or card.get("sowhat") else "",
                f"Read by view: {lens}" if lens else "",
            ], _page(pillar, view, cardId=card.get("id")), "At a glance", card.get("companyId"))

    for r in d.get("globalRequirements") or []:
        _doc(docs, f"requirement:{r.get('id')}", "opportunity", r.get("title"), [
            f"Global requirement: {_plain(r.get('title'))} · buyer {_plain(r.get('buyer'))} · {_plain(r.get('country'))} ({_plain(r.get('region'))})",
            f"Category: {_plain(r.get('cat'))} · value {_plain(r.get('value'))} · deadline {_plain(r.get('deadline') or r.get('dl'))} · status {_plain(r.get('status'))}",
            f"{client_name} fit: {_plain(r.get('ksslFit'))}" + (f" with {_plain(r.get('ksslModel'))}" if r.get("ksslModel") else "") if r.get("ksslFit") else "",
            f"Strategic assessment: {_plain(r.get('strategicAssessment'))}" if r.get("strategicAssessment") else "",
            f"Specs: {_pairs(r.get('specs'))}" if r.get("specs") else "",
            _plain(r.get("desc")),
        ], _page("market", "m-overview", cardId=f"req-{r.get('id')}"), "At a glance")

    top = d.get("topOpportunities") or {}
    for key, block, label in (("topTenders", "Top tenders", "Top tenders to act on"),
                              ("projectsBeforeTender", "Projects to win before they tender", "Projects to win before they tender"),
                              ("nextMoves", "Next moves", "Next moves")):
        rows = []
        for r in top.get(key) or []:
            if not isinstance(r, dict):
                continue
            if key == "nextMoves":
                rows.append(f"- {_plain(r.get('action'))} (due {r.get('dueDate') or _plain(r.get('due'))})"
                            + (f" for {_plain(r.get('tenderTitle'))}" if r.get("tenderTitle") else ""))
            else:
                extra = "; ".join(f"{k}: {_plain(v)}" for k, v in r.items() if k not in ("_src", "id", "title", "rank", "tenderId", "opportunityId")
                                  and isinstance(v, (str, int, float)) and _plain(v))
                rows.append(f"- #{r.get('rank')} {_plain(r.get('title'))}: {extra}")
        _doc(docs, f"top:{key}", "opportunity", label, rows, _page("market", "m-overview"), block)

    cats = {str(c.get("id")): c.get("name") for c in d.get("techCats") or []}
    for area, items in (d.get("innovations") or {}).items():
        for it in items or []:
            if not isinstance(it, dict):
                continue
            _doc(docs, f"innovation:{it.get('id') or area}", "innovation", it.get("t"), [
                f"Technology area: {cats.get(str(area), area)}",
                f"Development: {_plain(it.get('t'))} · driver {_plain(it.get('driver'))} · maturity {_plain(it.get('matLabel') or it.get('mat'))} · "
                f"{client_name} position {_plain(it.get('gapLabel') or it.get('gap'))} · horizon {_plain(it.get('horizon'))}",
                _plain(it.get("s")),
                f"Why this matters to {client_name}: {_plain(it.get('impact'))}" if it.get("impact") else "",
                f"What's new: {_plain(it.get('whatsNew'))}" if it.get("whatsNew") else "",
                f"Background: {_plain(it.get('body'))}" if it.get("body") else "",
                f"Competitive note: {_plain(it.get('compNote'))}" if it.get("compNote") else "",
                "Milestones: " + "; ".join(f"{m.get('date') or ''} {_plain(m.get('step') or m.get('note'))}" for m in it.get("milestones") or [] if isinstance(m, dict))
                if it.get("milestones") else "",
            ], _page("technology", "innovation", catId=str(area), title=it.get("t")), _plain(it.get("t")))

    for i, a in enumerate(d.get("awards") or []):
        if isinstance(a, dict):
            _doc(docs, f"award:{a.get('id') or i}", "award", a.get("title"), (
                f"Award {a.get('year') or ''}: {_plain(a.get('title'))} · buyer {_plain(a.get('buyer'))} · winner {_plain(a.get('winner'))}"
                f" · brand {_plain(a.get('brand')) or 'not named'} · segment {_plain(a.get('segment'))} · {_plain(a.get('country'))}"
                f" · value {_plain(a.get('value_text')) or (str(a.get('value')) + ' ' + str(a.get('currency') or '')).strip()}"),
                _page("market", "m-report", section="awarded"), "Past awards")

    _patents(docs, d, names)
    for p in d.get("projects") or []:
        if not isinstance(p, dict):
            continue
        assess = p.get("assessment") or {}
        latest = p.get("latest") or {}
        _doc(docs, f"project:{p.get('id')}", "project", f"{p.get('company') or names.get(p.get('cid'))}: {_plain(p.get('name'))}", [
            f"Project: {_plain(p.get('name'))} · company {_plain(p.get('company'))} · {_plain(p.get('kind'))} · {_plain(p.get('region'))}",
            f"Customer: {_plain(p.get('customer'))} · location {_plain(p.get('location'))}" if p.get("customer") or p.get("location") else "",
            f"Current stage: {_plain(p.get('stage'))}. {_plain(p.get('stageNote'))}",
            f"Latest: {latest.get('date') or ''} {_plain(latest.get('label'))}" if isinstance(latest, dict) and latest.get("label") else "",
            f"What the project is: {_join(p.get('overview'), ' ')}" if p.get("overview") else "",
            f"Strategic assessment ({_plain(assess.get('stance'))}): {_join(assess.get('read'), ' ')}" if assess.get("read") else "",
            f"What {client_name} can do: {_plain(p.get('ksslOption'))}" if p.get("ksslOption") else "",
            f"Specs: {_pairs(p.get('specs'))}" if p.get("specs") else "",
            "Timeline: " + "; ".join(f"{t.get('date')} {_plain(t.get('label'))}{' (expected)' if t.get('expected') else ''}"
                                     for t in p.get("timeline") or [] if isinstance(t, dict)) if p.get("timeline") else "",
        ], _page("competitive", "projects"), _plain(p.get("name")), p.get("cid"))
    return docs


def _patents(docs, d, names):
    pat = d.get("PATENTS") or {}
    rows = [x for items in (pat.get("byArea") or {}).values() for x in items or [] if isinstance(x, dict)]

    def line(x):
        return (f"- {x.get('no')}: {_plain(x.get('title'))} ({x.get('status')}, filed {x.get('filed')}, {x.get('country')}; "
                f"field: {_plain(x.get('area'))})" + (f" Relevance: {_plain(x.get('relev'))}." if x.get("relev") else ""))

    by_co = {}
    for x in rows:
        by_co.setdefault(str(x.get("comp_id") or x.get("assignee")), []).append(x)
    for cid, items in by_co.items():
        name = names.get(cid, cid)
        areas = sorted({_plain(x.get("area")) for x in items if x.get("area")})
        _doc(docs, f"patent:{cid}", "patent", f"{name}: patent portfolio",
             [f"{name} has {len(items)} tracked patent filings ({sum(x.get('status') == 'granted' for x in items)} granted) in: {', '.join(areas)}."]
             + [line(x) for x in items],
             _page("competitive", "patents-comp", cid=cid) if cid in names else None, f"{name} · patent portfolio",
             cid if cid in names else None)
    by_area = {}
    for x in rows:
        by_area.setdefault(_plain(x.get("area")), []).append(x)
    fields = {(_plain(v.get("area"))): v for k, v in (d.get("techAreaMeta") or {}).items() if str(k).startswith("patent-field-") and isinstance(v, dict)}
    for area, items in by_area.items():
        meta = fields.get(area) or {}
        who = sorted({names.get(str(x.get("comp_id")), _plain(x.get("assignee"))) for x in items})
        _doc(docs, f"patentarea:{area}", "patent", f"Patents in {area}",
             [f"{len(items)} tracked filings in {area}, by {', '.join(who)}."
              + (f" Crowding: {_plain(meta.get('crowding'))}." if meta.get("crowding") else "")
              + (f" {_plain(meta.get('reason'))}" if meta.get("reason") else "")] + [line(x) for x in items],
             _page("competitive", "patents-comp"), "Technology fields")
    fs = d.get("FIELDSYN") or {}
    if fs.get("patterns"):
        _doc(docs, "partners:field-synthesis", "partners", "Patterns across the field (partner networks)", [
            f"- {_plain(p.get('field'))}: {_plain(p.get('pattern'))} Implication: {_plain(p.get('implication'))}"
            for p in fs.get("patterns") or [] if isinstance(p, dict)] + [_plain(fs.get("bottom"))],
             _page("competitive", "partnerships"), "Alliance network")


# question words -> the kind of block that answers them (doc id suffix or doc kind)
INTENT = {
    "leadership": "lead leads leader leaders leadership ceo cfo coo chairman chief management executive executives team head heads board",
    "details": "founded headquarters hq size employees headcount revenue sales legal owner ownership sector",
    "news": "news latest recent announcement announcements moves move movement movements update updates moment moments",
    "partners": "partner partners partnership partnerships alliance alliances jv joint venture licence license supplier suppliers network dealer dealers distributor",
    "products": "product products portfolio model models range catalogue catalog system systems platform platforms specs specification specifications",
    "sites": "site sites footprint location locations plant plants factory facility facilities presence country countries production",
    "tender": "tender tenders bid bids rfq rfp procurement contract contracts",
    "matchup": "matchup matchups versus head-to-head compare comparison evaluation",
    "award": "award awards awarded won winner winners",
    "innovation": "technology technologies innovation innovations development developments maturity",
    "patent": "patent patents ip filing filings filed invention inventions intellectual property",
    "project": "project projects building build pursuing pursue programme program",
    "opportunity": "opportunity opportunities requirement requirements pipeline next act",
}


def meta(d: dict) -> dict:
    return {"companies": {cid: c.get("name") or cid for cid, c in (d.get("competitors") or {}).items()},
            "client": (d.get("client") or {}).get("name") or "", "news_topic": ""}


def live_news(get, cid: str, name: str, meta: dict) -> dict:
    """Live headlines through the product's /api/pulse (Google News behind it; served by the
    product's web server in this version, not by its API, and never stored). The platform's
    own pages show stored news; these are extra, live context."""
    d = get("/api/pulse", {"name": name})
    return {"headlines": [{k: t.get(k) for k in ("title", "source", "date", "url")} for t in d.get("trending") or []][:10],
            "share_price": "not tracked on the platform"}
