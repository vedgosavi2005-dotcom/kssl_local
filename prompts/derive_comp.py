"""Derive hooks of the competitive research prompts (partnership, project, geo, matchup verdict).

Kept apart from prompts/derive.py so the shared file stays small; derive.py imports this module at its end, which registers the hooks.
Same contract as derive.py: `@hook(name) def f(cur, ctx)`, run inside the loader transaction after the rows are written.

    partnership_overlap   competitive_partnership.overlap_client_partner_id from a NAME MATCH against client_partner (code first), and the
                          model's overlap_kind kept only when the match supports it (docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md A.1.6).
    project_story         every competitive_project of a run becomes a story (kind programme); each dated timeline event is a story step
                          (what changed, source, stage after it). prompts/story.py rebuilds the label timeline from the stages.
    competitor_qualification  competitive_competitor.qualifies + qualification_reason (spec: same product line AND same market), by code;
                          also `python -m prompts.derive_comp --qualify` after an Excel / product_class change.
    geo_match_code        every competitive_geo_product of a run whose name is a product of the subject gets match rows against the KSSL
                          products that pass the like-for-like gate (no model, no spec invention); geo_rollup then reads them.

Self-check (no DB):  python -m prompts.derive_comp --selftest
"""

from __future__ import annotations

import re
import sys

from prompts.derive import _row, hook, ids

# ---------------------------------------------------------------------------------------------------------------------------
# name matching (pure)
# ---------------------------------------------------------------------------------------------------------------------------

_SUFFIX = {"ltd", "limited", "pvt", "private", "plc", "gmbh", "ag", "sa", "inc", "corp", "corporation", "llc", "co", "company",
           "se", "nv", "bv", "ab", "as", "oy", "spa", "sas", "srl", "kg", "the", "of", "and"}


def norm_org(name) -> str:
    """casefold, text in brackets removed, punctuation removed, legal-form words removed: 'Thales Belgium S.A.' -> 'thales belgium'."""
    s = re.sub(r"\([^)]*\)", " ", str(name or "").casefold())
    s = s.replace(".", "").replace("&", " ")
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t]
    return " ".join(t for t in toks if t not in _SUFFIX)


def org_match(a, b) -> bool:
    """Same organisation by name: equal after normalising, or one is the other plus extra words that name a unit or country
    ('Thales' / 'Thales Belgium') when the shorter name is at least one word of 4+ letters. Never a match on a single short word."""
    x, y = norm_org(a), norm_org(b)
    if not x or not y:
        return False
    if x == y:
        return True
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    return long_.startswith(short + " ") and len(short) >= 4


def find_org(name, candidates: list, name_keys=("partner_name", "legal_name")) -> list:
    return [c for c in candidates if any(org_match(name, c.get(k)) for k in name_keys if c.get(k))]


# ---------------------------------------------------------------------------------------------------------------------------
# partnership_overlap
# ---------------------------------------------------------------------------------------------------------------------------

@hook("partnership_overlap")
def partnership_overlap(cur, ctx: dict) -> None:
    """Code first: the partner's name against the client's partners. The model's overlap_kind stands only when the match supports it:
    same_component / same_partner_other_scope need a matched KSSL partner (else they become 'none', logged); a matched KSSL partner
    makes at least same_partner_other_scope (logged) so a shared partner is never hidden."""
    cur.execute("SELECT client_partner_id, partner_name, legal_name FROM staging.client_partner")
    partners = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT competitor_id, display_name, short_name FROM staging.competitive_competitor")
    comps = [dict(r) for r in cur.fetchall()]
    tr = ctx.get("transient", {})
    for rid in ids(ctx, "competitive_partnership"):
        row = _row(cur, "competitive_partnership", "relationship_id", rid)
        if row is None:
            continue
        # a partner that is one of the tracked competitors carries its display name (the dashboard links the tie to the competitor by it)
        same = [c for c in comps if norm_org(c["display_name"]) == norm_org(row.get("partner_name")) and c["display_name"] != row.get("partner_name")]
        if len(same) == 1 and str(same[0]["competitor_id"]) != str(row.get("competitor_id")):
            import uuid
            new = same[0]["display_name"]
            cur.execute("UPDATE staging.competitive_partnership SET partner_name = %s, partner_id = %s WHERE relationship_id::text = %s",
                        (new, str(uuid.uuid5(uuid.NAMESPACE_URL, f"kssl-partner_name|{' '.join(new.casefold().split())}")), str(rid)))
            ctx["notes"].append(f"partnership_overlap: partner '{row.get('partner_name')}' renamed to the competitor's display name '{new}'")
            row["partner_name"] = new
        claimed = (tr.get(("competitive_partnership", str(rid))) or {}).get("overlap_partner")
        by_code = find_org(row.get("partner_name"), partners)
        by_model = find_org(claimed, partners) if claimed else []
        hit = by_code or by_model
        if len({h["client_partner_id"] for h in hit}) > 1:
            ctx["warnings"].append(f"partnership_overlap: {row.get('partner_name')} matches several KSSL partners; no overlap id set")
            hit = []
        kind, comp, effect = row.get("overlap_kind"), row.get("overlap_component"), row.get("overlap_effect")
        cpid = hit[0]["client_partner_id"] if hit else None
        if cpid is None:
            if kind in ("same_component", "same_partner_other_scope"):
                ctx["notes"].append(f"partnership_overlap: {row.get('partner_name')}: '{kind}' dropped, no KSSL partner of that name")
                kind, comp, effect = "none", None, None
        else:
            if by_code and by_model and by_code[0]["client_partner_id"] != by_model[0]["client_partner_id"]:
                ctx["warnings"].append(f"partnership_overlap: {row.get('partner_name')}: the model named a different KSSL partner; the name match wins")
            if kind not in ("same_component", "same_partner_other_scope"):
                ctx["notes"].append(f"partnership_overlap: {row.get('partner_name')} is KSSL partner {hit[0]['partner_name']}: kind {kind} -> same_partner_other_scope")
                kind, comp = "same_partner_other_scope", None
        if kind in ("none", "unknown", "kssl_market", None):
            comp = None
            if kind in ("none", None):
                effect = None
        cur.execute("""UPDATE staging.competitive_partnership SET overlap_client_partner_id = %s, overlap_kind = %s, overlap_component = %s,
                       overlap_effect = %s WHERE relationship_id::text = %s""", (cpid, kind, comp, effect, str(rid)))


# ---------------------------------------------------------------------------------------------------------------------------
# project_story
# ---------------------------------------------------------------------------------------------------------------------------

def step_kind(title) -> str:
    """A story step type from the event title (words only, no model). First match wins, in this order."""
    t = str(title or "").lower()
    for pattern, kind in ((r"deliver|receiv|induct|commission|in service|handed over", "delivery"),
                          (r"contract|award|select|order|signs?|signed|agreement", "contract"),
                          (r"trial|test|prototype|qualif|demonstrat", "trial"),
                          (r"production|assembly|factory|plant|ground ?breaking", "production"),
                          (r"announce|unveil|launch(?:ed|es)?|approv", "announced")):
        if re.search(pattern, t):
            return kind
    return "update"


@hook("project_story")
def project_story(cur, ctx: dict) -> None:
    """Each project of the run = one story (key competitive:<competitor>:<project>:<country>:programme); each dated timeline event = one
    step with `changed` (what changed at this step), the source url and the stage after it (`label_after`, so the stage moves show as
    label_change steps). Planned (expected) events are steps of type 'planned' without a label. The project's story_id is set."""
    from prompts import story
    tr = ctx.get("transient", {})
    for pid in ids(ctx, "competitive_project"):
        proj = _row(cur, "competitive_project", "project_id", pid)
        if proj is None:
            continue
        cur.execute("SELECT display_name, short_name FROM staging.competitive_competitor WHERE competitor_id = %s", (proj["competitor_id"],))
        comp = cur.fetchone() or {}
        iso = ""
        cur.execute("SELECT * FROM staging.competitive_project_timeline WHERE project_id = %s ORDER BY event_date NULLS LAST, display_order", (pid,))
        events = [dict(r) for r in cur.fetchall()]
        if not events:
            continue
        iso = story._country_iso(cur, proj.get("customer") if len(str(proj.get("customer") or "")) < 40 else proj.get("location"))
        key = story.story_key("competitive", comp.get("short_name") or comp.get("display_name"), proj["project_title"], iso, "programme")
        sid = story.upsert_story(cur, key, pillar="competitive", kind="programme", competitor_id=proj["competitor_id"], buyer_name=proj.get("customer"),
                                 country_code=iso or None, title=proj["project_title"])
        cur.execute("UPDATE staging.competitive_project SET story_id = %s WHERE project_id = %s", (sid, pid))
        for ev in events:
            t = tr.get(("competitive_project_timeline", str(ev["timeline_id"]))) or {}
            expected = bool(ev.get("is_expected"))
            line = ev.get("event_title") or ev.get("event_description")
            if not line or ev.get("event_date") is None:
                continue
            st = story.add_step(cur, sid, step_date=ev["event_date"], step_type="planned" if expected else step_kind(ev["event_title"]), one_line=line,
                                source_url=t.get("source_url"), source_table="competitive_project_timeline", source_row_id=str(ev["timeline_id"]),
                                label=None if expected else (t.get("stage_after") or None))
            changed = story.step_line(t.get("changed"))
            if changed:
                cur.execute("UPDATE staging.story_step SET changed = %s WHERE story_id = %s AND source_table = 'competitive_project_timeline' AND source_row_id = %s "
                            "AND step_type <> 'label_change'", (changed, sid, str(ev["timeline_id"])))
        ctx["notes"].append(f"project_story: {proj['project_title']}: story {key} with {len(events)} steps")


# ---------------------------------------------------------------------------------------------------------------------------
# geo_match_code
# ---------------------------------------------------------------------------------------------------------------------------

def _hash63(*parts) -> int:
    import hashlib
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def pick_product(name, products: list):
    """The one competitor product a geo product name means: equal after normalising, else the only catalogue name that starts with it plus a
    space ('K9 Thunder' -> 'K9 Thunder (155 mm SPH)' is handled by norm_org's bracket removal); None when zero or several fit."""
    key = norm_org(name)
    if not key:
        return None
    exact = [p for p in products if norm_org(p["product_name"]) == key]
    if len({p["product_id"] for p in exact}) == 1:
        return exact[0]
    if exact:
        return None
    pre = [p for p in products if norm_org(p["product_name"]).startswith(key + " ")]
    if pre:
        return pre[0] if len({p["product_id"] for p in pre}) == 1 else None
    toks = set(key.split())
    if len(toks) >= 2:                                              # every word of the geo name is a word of exactly one catalogue name
        sub = [p for p in products if toks <= set(norm_org(p["product_name"]).replace("/", " ").split())]
        if len({p["product_id"] for p in sub}) == 1:
            return sub[0]
    return None


LEVEL_WORDS = {3: "{client} ahead on the compared specs", 2: "Near parity on the compared specs", 1: "Rival ahead on the compared specs"}


@hook("geo_match_code")
def geo_match_code(cur, ctx: dict) -> None:
    """KSSL counter-products of the geo products of this run, by code: the competitor product named by the geo product (same name as the
    catalogue) is looked up in staging.product_class; every KSSL product of the same category that passes the like-for-like gate
    (prompts/matchup_class.gate) becomes a competitive_geo_product_match row. match_status 'matched' when a stored matchup of that pair
    has at least one comparable spec, else 'category_only'. Evaluation label, summary and decision level are copied from that stored
    matchup when it has them. Nothing is invented: the basis is the gate in words (matchup_class.basis)."""
    from prompts import matchup_class as mc
    from prompts.derive import client_name
    client = client_name(cur)
    cur.execute("SELECT client_product_id, product_name, category FROM staging.client_product")
    kssl = {str(r["client_product_id"]): dict(r) for r in cur.fetchall()}
    cur.execute("SELECT * FROM staging.product_class WHERE product_side = 'client'")
    kcls = {r["product_id"]: dict(r) for r in cur.fetchall()}
    made = 0
    for gid in ids(ctx, "competitive_geo_product"):
        g = _row(cur, "competitive_geo_product", "geo_product_id", gid)
        pres = _row(cur, "competitive_geo_company_presence", "presence_id", g["presence_id"]) if g else None
        if not g or not pres or pres.get("company_role") != "competitor" or not pres.get("competitor_id"):
            continue
        cur.execute("DELETE FROM staging.competitive_geo_product_match WHERE geo_product_id = %s", (g["geo_product_id"],))
        cur.execute("SELECT product_id, product_name, category FROM staging.competitive_product WHERE competitor_id = %s", (pres["competitor_id"],))
        prod = pick_product(g.get("product_name"), [dict(r) for r in cur.fetchall()])
        if prod is None or not prod.get("category"):
            continue
        cur.execute("SELECT * FROM staging.product_class WHERE product_side = 'competitor' AND product_id = %s", (str(prod["product_id"]),))
        pc = cur.fetchone()
        if pc is None:
            continue
        for kid, kp in kssl.items():
            kc = kcls.get(kid)
            if kc is None or (kp.get("category") or "").strip().lower() != prod["category"].strip().lower():
                continue
            if not mc.gate(prod["category"], dict(kc), dict(pc), relaxed_weight=True):      # sub-type + calibre decide; a weight class not on record is not a bar here
                continue
            cur.execute("""SELECT matchup_id, comparable_spec_count, decision_level, verdict_headline, verdict FROM staging.competitive_matchup
                           WHERE client_product_id::text = %s AND competitor_product_id = %s""", (kid, prod["product_id"]))
            mu = cur.fetchone()
            matched = bool(mu and (mu["comparable_spec_count"] or 0) > 0)
            level = mu["decision_level"] if matched else None
            mid = _hash63("geo_match_code", g["geo_product_id"], kid)
            basis = mc.basis(prod["category"], dict(kc), dict(pc))
            cur.execute("""INSERT INTO staging.competitive_geo_product_match
                           (match_id, geo_product_id, kssl_product_id, kssl_counter_label, comparison_title, match_status, match_basis,
                            evaluation_label, qualitative_summary, decision_level)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (mid, g["geo_product_id"], int(kid), kp["product_name"], f"{kp['product_name']} vs {g.get('product_name')}"[:255],
                         "matched" if matched else "category_only", basis, (LEVEL_WORDS[level].format(client=client) if level in LEVEL_WORDS else None), (mu or {}).get("verdict") if matched else None, level))
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                           VALUES ('competitive_geo_product_match', %s, 'match_basis', 'stored row', 'stored', %s)""",
                        (str(mid), f"product_class: {prod['product_name']} = {pc['sub_type']}, {pc['calibre_mm']} mm, {pc['weight_class']}; "
                                   f"{kp['product_name']} = {kc['sub_type']}, {kc['calibre_mm']} mm, {kc['weight_class']}"))
            ctx["rows"].append(("competitive_geo_product_match", str(mid), False))
            made += 1
    if made:
        ctx["notes"].append(f"geo_match_code: {made} KSSL counter-product rows built from the like-for-like gate")


REASON_CODES = ("incumbency", "offsets_local_content", "financing_g2g", "delivery_time", "local_partner", "after_sales", "politics", "price",
                "performance", "other")


def parse_reasons(text) -> list:
    """'Incumbency, price' -> ['incumbency', 'price']; unknown words dropped; order kept; no repeats."""
    out = []
    for w in re.split(r"[,;|/]+", str(text or "")):
        w = re.sub(r"[^a-z_]+", "_", w.strip().lower()).strip("_")
        if w in REASON_CODES and w not in out:
            out.append(w)
    return out


@hook("geo_analysis_finish")
def geo_analysis_finish(cur, ctx: dict) -> None:
    """stated_reasons (the model's comma list) -> the text[] column. A reason counts only with a source url: 'stated' without one becomes
    'not_stated' with no reasons; 'not_stated' keeps no reasons; the hypothesis is kept only when nothing is stated."""
    tr = ctx.get("transient", {})
    for aid in ids(ctx, "competitive_geo_analysis"):
        row = _row(cur, "competitive_geo_analysis", "analysis_id", aid)
        if row is None:
            continue
        reasons = parse_reasons((tr.get(("competitive_geo_analysis", str(aid))) or {}).get("stated_reasons"))
        state = row.get("reason_state")
        if state == "stated" and (not reasons or not row.get("source_url")):
            ctx["warnings"].append(f"geo_analysis_finish: {aid}: 'stated' needs a reason code and a source url; stored as not_stated")
            state, reasons = "not_stated", []
        if state != "stated":
            reasons = []
        hyp = row.get("hypothesis") if state != "stated" else None
        cur.execute("UPDATE staging.competitive_geo_analysis SET reason_state = %s, stated_reasons = %s, hypothesis = %s WHERE analysis_id::text = %s",
                    (state, reasons or None, hyp, str(aid)))


# ---------------------------------------------------------------------------------------------------------------------------
# sources_filter
# ---------------------------------------------------------------------------------------------------------------------------

def blocked_url(url) -> str | None:
    """The reason a source must not be stored (a wiki, a blog, a forum, social media, a wire / aggregator, a market-tips or exam-prep site,
    a google wrapper), or None. An unknown domain is NOT blocked (it may be a company's own site); it only gets the loader's warning."""
    from backend.sources import classify_reason
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    tier, why = classify_reason(str(url))
    return why if tier is None and (why.startswith("blocked") or why == "google wrapper") else None


# card table -> [(child table, url column, id column, parent fk column)]; a card left with none of its sources is removed
_SOURCE_RULES = {
    "competitive_partnership": [("competitive_partnership_evidence", "source_url", "evidence_card_id", "relationship_id")],
    "competitive_project": [("competitive_project_source", "source_url", "source_id", "project_id")],
}


@hook("sources_filter")
def sources_filter(cur, ctx: dict) -> None:
    """Drop what rests on a blocked source. Evidence cards / project sources / geo sources / moment sources with a blocked url are deleted
    (with their fact_source rows); a partnership left with no evidence, a project left with no source, a geo product left with no source and
    a moment whose own url is blocked are deleted too. Unknown domains stay."""
    def drop(table, key, rid):
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s", (table, str(rid)))
        cur.execute(f"DELETE FROM staging.{table} WHERE {key}::text = %s", (str(rid),))

    removed = 0
    seen_rows = {(t, str(i)) for t, i, *_ in ctx.get("rows", [])} | {(t, str(i)) for t, i in ctx.get("cards", [])}
    for t, i in sorted(seen_rows):                       # a fact_source row that cites a blocked source is removed (the value keeps its other sources)
        cur.execute("SELECT fact_source_id, source_url FROM staging.fact_source WHERE table_name = %s AND row_id = %s", (t, i))
        for r in cur.fetchall():
            if blocked_url(r["source_url"]):
                cur.execute("DELETE FROM staging.fact_source WHERE fact_source_id = %s", (r["fact_source_id"],))
                removed += 1
    for card, rules in _SOURCE_RULES.items():
        key = {"competitive_partnership": "relationship_id", "competitive_project": "project_id"}[card]
        for cid in ids(ctx, card):
            for child, ucol, icol, fk in rules:
                cur.execute(f"SELECT {icol} AS id, {ucol} AS url FROM staging.{child} WHERE {fk}::text = %s", (str(cid),))
                rows = [dict(r) for r in cur.fetchall()]
                bad = [r for r in rows if blocked_url(r["url"])]
                for r in bad:
                    drop(child, icol, r["id"])
                    ctx["warnings"].append(f"sources_filter: {child} row dropped, blocked source ({blocked_url(r['url'])}): {str(r['url'])[:90]}")
                    removed += 1
                if rows and len(bad) == len(rows):
                    if card == "competitive_partnership":
                        cur.execute("DELETE FROM staging.competitive_partnership_relationship_detail WHERE relationship_id::text = %s", (str(cid),))
                    drop(card, key, cid)
                    ctx["warnings"].append(f"sources_filter: {card} {cid} dropped, every source was blocked")
                elif bad and card == "competitive_partnership":
                    cur.execute("UPDATE staging.competitive_partnership SET source_count = (SELECT count(*) FROM staging.competitive_partnership_evidence WHERE relationship_id = %s) "
                                "WHERE relationship_id = %s", (cid, cid))
    for sid in ids(ctx, "competitive_geo_source"):
        r = _row(cur, "competitive_geo_source", "source_id", sid)
        if r and blocked_url(r.get("source_url")):
            drop("competitive_geo_source", "source_id", sid)
            ctx["warnings"].append(f"sources_filter: geo source dropped, blocked ({blocked_url(r.get('source_url'))}): {str(r.get('source_url'))[:90]}")
            removed += 1
    for gid in ids(ctx, "competitive_geo_product"):
        cur.execute("SELECT count(*) AS n FROM staging.competitive_geo_source WHERE geo_product_id::text = %s", (str(gid),))
        if cur.fetchone()["n"] == 0:
            for t in ("competitive_geo_product_news", "competitive_geo_product_match"):
                cur.execute(f"DELETE FROM staging.{t} WHERE geo_product_id::text = %s", (str(gid),))
            drop("competitive_geo_product", "geo_product_id", gid)
            ctx["warnings"].append(f"sources_filter: geo product {gid} dropped, no usable source left")
            removed += 1
    for pid in ids(ctx, "competitive_geo_company_presence"):
        cur.execute("SELECT count(*) AS n FROM staging.competitive_geo_product WHERE presence_id::text = %s", (str(pid),))
        if cur.fetchone()["n"] == 0:
            drop("competitive_geo_company_presence", "presence_id", pid)
            ctx["warnings"].append(f"sources_filter: presence {pid} dropped, no product with a usable source left")
        else:
            cur.execute("UPDATE staging.competitive_geo_company_presence SET product_count = (SELECT count(*) FROM staging.competitive_geo_product WHERE presence_id::text = %s), "
                        "products_summary = (SELECT string_agg(DISTINCT product_name, '; ') FROM staging.competitive_geo_product WHERE presence_id::text = %s AND product_name IS NOT NULL) "
                        "WHERE presence_id::text = %s", (str(pid), str(pid), str(pid)))
    for mid in ids(ctx, "competitive_competitor_moment"):
        r = _row(cur, "competitive_competitor_moment", "moment_id", mid)
        if r and blocked_url(r.get("source_url")):
            for t in ("competitive_competitor_moment_analysis", "competitive_competitor_moment_source"):
                cur.execute(f"DELETE FROM staging.{t} WHERE moment_id::text = %s", (str(mid),))
            drop("competitive_competitor_moment", "moment_id", mid)
            ctx["warnings"].append(f"sources_filter: moment {mid} dropped, blocked main source ({blocked_url(r.get('source_url'))})")
            continue
        cur.execute("SELECT source_id, source_url FROM staging.competitive_competitor_moment_source WHERE moment_id::text = %s", (str(mid),))
        for x in cur.fetchall():
            if blocked_url(x["source_url"]):
                drop("competitive_competitor_moment_source", "source_id", x["source_id"])
                removed += 1
    if removed:
        ctx["notes"].append(f"sources_filter: {removed} rows dropped for blocked sources")


# ---------------------------------------------------------------------------------------------------------------------------
# competitor qualification (user spec 2026-10-18): same product line AND same market, tested by code on stored rows
# ---------------------------------------------------------------------------------------------------------------------------

def qualification(client_lines: dict, rival_lines: dict, client_countries: set, rival_countries: set):
    """(qualifies, reason). client_lines / rival_lines: {sub_type: [product names]} (sub_type 'unknown' left out by the caller);
    countries: lower-case names. None = not testable (the rival has no classed product or no known country)."""
    same = sorted(set(client_lines) & set(rival_lines))
    where = sorted(client_countries & rival_countries)
    if not rival_lines or not rival_countries:
        missing = " and ".join(w for w, x in (("no classed product", rival_lines), ("no known country", rival_countries)) if not x)
        return None, f"Not testable yet: {missing} on record."
    n = sum(len(rival_lines[t]) for t in same)
    line = (f"same line: {', '.join(t.replace('_', ' ') for t in same[:4])} ({n} product{'' if n == 1 else 's'})"
            if same else "no product in a client product line")
    mkt = f"same market: {', '.join(c.title() for c in where[:5])}" if where else "no presence in a client market"
    return bool(same and where), f"{'Qualifies' if same and where else 'Does not qualify'}: {line}; {mkt}."


def qualify_competitors(cur) -> int:
    """competitive_competitor.qualifies / qualification_reason for every competitor, from product_class (sub-type) and the markets:
    client = client geo presence + client_partner countries + the client's own country; rival = geo presence + origin country.
    Every country name goes through staging.country_reference (name, ISO code, aliases), so "US" / "USA" / "United States" are one
    country (an origin stored as "US" never matched a market stored as "United States": Anduril, AeroVironment)."""
    cur.execute("SELECT country_name, iso2, aliases FROM staging.country_reference")
    canon: dict = {}
    for r in cur.fetchall():
        for a in (r["country_name"], r["iso2"], *(r["aliases"] or [])):
            if a:
                canon[str(a).strip().lower()] = r["country_name"].lower()
    cn = lambda c: canon.get(str(c).strip().lower(), str(c).strip().lower()) if c else None  # noqa: E731
    cur.execute("""SELECT pc.sub_type, p.product_name FROM staging.product_class pc
                   JOIN staging.client_product p ON pc.product_side = 'client' AND pc.product_id = p.client_product_id::text
                   WHERE pc.sub_type IS NOT NULL AND pc.sub_type <> 'unknown'""")
    client_lines: dict = {}
    for r in cur.fetchall():
        client_lines.setdefault(r["sub_type"], []).append(r["product_name"])
    cur.execute("""SELECT lower(l.country_name) c FROM staging.competitive_geo_company_presence p
                   JOIN staging.competitive_geo_location l ON l.location_id = p.location_id WHERE p.company_role = 'client'
                   UNION SELECT lower(country) FROM staging.client_partner WHERE coalesce(country, '') <> ''
                   UNION SELECT lower(country) FROM staging.client_account WHERE coalesce(country, '') <> ''""")
    client_countries = {cn(r["c"]) for r in cur.fetchall() if r["c"]}
    cur.execute("""SELECT c.competitor_id::text id, pc.sub_type, cp.product_name FROM staging.competitive_competitor c
                   JOIN staging.competitive_product cp ON cp.competitor_id = c.competitor_id
                   JOIN staging.product_class pc ON pc.product_side = 'competitor' AND pc.product_id = cp.product_id::text
                   WHERE pc.sub_type IS NOT NULL AND pc.sub_type <> 'unknown'""")
    lines: dict = {}
    for r in cur.fetchall():
        lines.setdefault(r["id"], {}).setdefault(r["sub_type"], []).append(r["product_name"])
    cur.execute("""SELECT c.competitor_id::text id, lower(l.country_name) c FROM staging.competitive_competitor c
                   JOIN staging.competitive_geo_company_presence p ON p.competitor_id = c.competitor_id AND p.company_role <> 'client'
                   JOIN staging.competitive_geo_location l ON l.location_id = p.location_id
                   UNION SELECT competitor_id::text, lower(origin_country) FROM staging.competitive_competitor WHERE coalesce(origin_country, '') <> ''""")
    countries: dict = {}
    for r in cur.fetchall():
        if r["c"]:
            countries.setdefault(r["id"], set()).add(cn(r["c"]))
    cur.execute("SELECT competitor_id::text id FROM staging.competitive_competitor")
    ids_ = [r["id"] for r in cur.fetchall()]
    for cid in ids_:
        q, why = qualification(client_lines, lines.get(cid, {}), client_countries, countries.get(cid, set()))
        cur.execute("UPDATE staging.competitive_competitor SET qualifies = %s, qualification_reason = %s WHERE competitor_id::text = %s", (q, why, cid))
    return len(ids_)


@hook("competitor_qualification")
def competitor_qualification(cur, ctx: dict) -> None:
    """Re-test every competitor after a load that changes products or presence (geo, matchup class runs)."""
    ctx["notes"].append(f"competitor_qualification: {qualify_competitors(cur)} competitors re-tested")


def _selftest() -> None:
    assert norm_org("Thales Belgium S.A.") == "thales belgium" and norm_org("Rafael Advanced Defense Systems Ltd (Israel)") == "rafael advanced defense systems"
    assert org_match("Thales", "Thales Belgium") and org_match("Thales Belgium", "THALES")
    assert org_match("BAE Systems", "BAE Systems plc") and not org_match("BAE", "BAE Systems")          # a 3-letter stem is not a match
    assert not org_match("", "x") and not org_match("Nord", "Nordvik Defence")                       # 'nord' is not a whole word prefix of 'nordvik'
    assert find_org("Duma Engineering Group", [{"partner_name": "Duma Engineering Group", "client_partner_id": 1}, {"partner_name": "Other"}])[0]["client_partner_id"] == 1
    cat = [{"product_id": 1, "product_name": "K9 Thunder (155 mm SPH)"}, {"product_id": 2, "product_name": "K9 Vajra-T"}, {"product_id": 3, "product_name": "K9 Vajra-T Mk2"}]
    assert pick_product("K9 Thunder", cat)["product_id"] == 1 and pick_product("K9 Vajra-T", cat)["product_id"] == 2 and pick_product("K9", cat) is None and pick_product("K9 Thunder", [{"product_id": 9, "product_name": "K9 / K9A1 Thunder"}])["product_id"] == 9
    assert parse_reasons("Incumbency, price; made_up | offsets_local_content") == ["incumbency", "price", "offsets_local_content"]
    assert blocked_url("https://en.wikipedia.org/wiki/K9") and blocked_url("https://gktoday.in/x") and blocked_url("https://www.indragroup.com/x") is None
    assert blocked_url("https://www.reuters.com/x") is None and blocked_url(None) is None
    assert step_kind("Prototype trials start") == "trial" and step_kind("Contract signed") == "contract" and step_kind("Something") == "update"
    assert step_kind("Army receives first prototype") == "delivery" and step_kind("First launcher arrives") == "update" and step_kind("Army awards prototype contract") == "contract"
    cl = {"towed_howitzer": ["Bharat 52"], "mounted_gun": ["MArG 155"]}
    q, why = qualification(cl, {"towed_howitzer": ["FH77"], "mlrs": ["X"]}, {"india", "armenia"}, {"armenia", "sweden"})
    assert q is True and why == "Qualifies: same line: towed howitzer (1 product); same market: Armenia.", why
    assert qualification(cl, {"mlrs": ["X"]}, {"india"}, {"india"})[0] is False
    assert qualification(cl, {"towed_howitzer": ["FH77"]}, {"india"}, {"sweden"}) == (False, "Does not qualify: same line: towed howitzer (1 product); no presence in a client market.")
    assert qualification(cl, {}, {"india"}, {"india"}) == (None, "Not testable yet: no classed product on record.")
    print("derive_comp self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--qualify" in sys.argv:              # after an Excel / product_class change:  python -m prompts.derive_comp --qualify
        import os
        import psycopg2
        import psycopg2.extras
        with psycopg2.connect(os.environ["KSSL_STAGING_DSN"], cursor_factory=psycopg2.extras.RealDictCursor) as conn:
            print(f"{qualify_competitors(conn.cursor())} competitors re-tested")
    else:
        print(__doc__)
