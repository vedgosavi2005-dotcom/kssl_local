"""Prompt files -> the filled prompt: _shared.yml + <id>.yml, context blocks and documents from
kssl_staging, simple {{placeholder}} replacement (no template library; unknown placeholder = error)."""

from __future__ import annotations

import html
import os
import re
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import yaml

HERE = Path(__file__).resolve().parent
DOC_CAP = 12_000
NONE_ON_RECORD = "none on record"
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w]*(?:\.[\w]+)?)\s*\}\}")


class PromptError(RuntimeError):
    pass


class DocumentError(PromptError):
    pass


# ---- files ---------------------------------------------------------------------------------------

def connect():
    dsn = (os.getenv("KSSL_STAGING_DSN") or os.getenv("KSSL_DSN") or "").strip()
    if not dsn:
        raise PromptError("KSSL_STAGING_DSN (or KSSL_DSN) is not set")
    return psycopg2.connect(dsn, connect_timeout=5)


def prompt_ids() -> list[str]:
    return sorted(p.stem for p in HERE.glob("*.yml") if not p.stem.startswith("_") and p.stem != "sets")   # sets.yml = run sets, not a prompt


def load_prompt(prompt_id: str) -> dict:
    """The prompt file merged over the _shared.yml defaults (model, web_search, system)."""
    f = HERE / f"{prompt_id}.yml"
    if not f.exists():
        raise PromptError(f"no prompt file {f.name}; have: {', '.join(prompt_ids())}")
    shared = yaml.safe_load((HERE / "_shared.yml").read_text(encoding="utf-8")) or {}
    spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    if spec.get("id") != prompt_id:
        raise PromptError(f"{f.name}: id is {spec.get('id')!r}, expected {prompt_id!r}")
    for k in ("task", "output", "subject"):
        if k not in spec:
            raise PromptError(f"{f.name}: missing '{k}'")
    out = {"model": shared.get("model"), "web_search": bool(shared.get("web_search")), "system": shared.get("system", "")}
    out.update(spec)
    out["version"] = str(spec.get("version", "1"))
    out["context_blocks"] = shared.get("context_blocks", {})
    return out


# ---- context blocks (kssl_staging) -----------------------------------------------------------------

def _one(cur, query: str, args=()) -> list[dict]:
    cur.execute(query, args)
    return [dict(r) for r in cur.fetchall()]


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    return str(v)


def _paren(name: str, *bits: str | None) -> str:
    bits = [b for b in bits if b]
    return f"{name} ({'; '.join(bits)})" if bits else name


def client_row(cur) -> dict:
    rows = _one(cur, "SELECT * FROM staging.client_account ORDER BY client_id LIMIT 1")
    if not rows:
        raise PromptError("staging.client_account is empty: the client must be loaded first")
    c = rows[0]
    c["name"] = c.get("client_name")            # the prompt files say {{client.name}}
    c["sector"] = c.get("industry_sector")
    return {k: _s(v) for k, v in c.items()}


# ---- the KSSL lens: portfolio, capabilities, markets, partners, competitors extended ---------------------------------
# Every row cap and character budget is a constant here; nothing is typed about KSSL itself, it all comes from the tables.
# An empty result renders as NONE_ON_RECORD, and the prompts must then answer "unknown" (never guess from general knowledge).

PORTFOLIO_MAX_CHARS = 10_000       # client_portfolio: ~82 products; specs per product drop 3 -> 2 -> 1 -> 0 until it fits
NAME_CAP = 84                      # a product name is cut here (the full name stays in the database)
MARKETS_MAX_ROWS = 40              # client_markets: countries
PARTNERS_MAX_ROWS = 40             # client_partners: partners
PARTNER_LINE_CAP = 360             # characters per partner line
COMP_MAX_CATEGORIES = 3            # competitors_extended: categories listed per competitor
COMP_MAX_SUBTYPES = 3              # ... sub-types listed per category
COMP_MAX_MARKETS = 8               # ... countries listed per competitor
PROVISIONAL = "provisional research (replace with client Excel)"     # prefix of the fact_source quotes the research prompt writes

# Until client_product.product_kind exists (Phase 2 DDL, filled from the client Excel), a venture / capability is recognised by
# its name AND a missing sub-type: a product that the matchup engine classified is always a product.
_VENTURE_NAME = re.compile(r"\b(joint venture|JV|MoU|subsidiary|co-development|collaboration|partnership|transfer-of-technology|"
                           r"capability)\b|^(ACIL|Aegis|Aeron|BFIL|Eternus|Zorya|Bharat Forge Aerospace|Agneyastra|KSSL Artificial)", re.I)


def _has_column(cur, table: str, col: str) -> bool:
    return bool(_one(cur, "SELECT 1 FROM information_schema.columns WHERE table_schema='staging' AND table_name=%s AND column_name=%s",
                     (table, col)))


def _cut(t: str | None, n: int) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _spec_bits(specs: list[dict], n: int) -> list[str]:
    """Up to n key specs: numeric ones first (they are the comparable ones), in the product's own order."""
    ok = [x for x in specs if x["value_numeric"] is not None or (x["value_text"] or "").strip()]
    ok.sort(key=lambda x: (x["value_numeric"] is None, x["display_order"]))
    out = []
    for x in ok[:n]:
        v = _s(x["value_numeric"]) if x["value_numeric"] is not None else _cut(x["value_text"], 40)
        out.append(" ".join(b for b in (_cut(x["spec_name"], 36), v, x["unit"] or "") if b))
    return out


def _client_items(cur) -> list[dict]:
    """client_product rows with their product_class (read only) and kind: product | variant | venture | capability."""
    kind_col = _has_column(cur, "client_product", "product_kind")
    rows = _one(cur, f"""SELECT p.client_product_id, p.product_name, p.category, p.subcategory,
                                {'p.product_kind' if kind_col else 'NULL::text'} AS product_kind,
                                c.sub_type, c.calibre_mm, c.weight_class
                         FROM staging.client_product p
                         LEFT JOIN staging.product_class c ON c.product_side = 'client' AND c.product_id = p.client_product_id::text
                         ORDER BY p.category, p.product_name""")
    specs: dict = {}
    for r in _one(cur, "SELECT client_product_id, spec_name, value_text, value_numeric, unit, display_order "
                       "FROM staging.client_product_specification ORDER BY client_product_id, display_order"):
        specs.setdefault(r["client_product_id"], []).append(r)
    for r in rows:
        sub = r["sub_type"] if r["sub_type"] not in (None, "unknown") else (r["subcategory"] or None)
        r["sub"] = sub
        r["specs"] = specs.get(r["client_product_id"], [])
        kind = (r["product_kind"] or "").strip().lower()
        if not kind:
            kind = "venture" if (not sub and _VENTURE_NAME.search(r["product_name"] or "")) else "product"
        r["kind"] = kind
    return rows


def block_client_portfolio(cur) -> str:
    """`category > sub_type: product (calibre; weight class; key specs)` for products and variants; ventures and capabilities
    are in client_capabilities. Specs per product shrink until the block fits PORTFOLIO_MAX_CHARS."""
    items = [r for r in _client_items(cur) if r["kind"] in ("product", "variant")]
    if not items:
        return NONE_ON_RECORD
    text = ""
    for n_specs in (3, 2, 1, 0):
        lines = []
        for r in items:
            bits = []
            if r["calibre_mm"] is not None:
                bits.append(f"{_s(r['calibre_mm'])} mm")
            if r["weight_class"] and r["weight_class"] not in ("n/a", "unknown"):
                bits.append(r["weight_class"])
            bits += _spec_bits(r["specs"], n_specs)
            head = f"{r['category'] or 'uncategorised'} > {r['sub'] or 'sub-type unknown'}"
            lines.append(f"{head}: {_cut(r['product_name'], NAME_CAP)}" + (f" ({'; '.join(bits)})" if bits else ""))
        text = "\n".join(lines)
        if len(text) <= PORTFOLIO_MAX_CHARS:
            return text
    return text[:PORTFOLIO_MAX_CHARS].rsplit("\n", 1)[0] + f"\n... ({len(items)} products in all; list cut at {PORTFOLIO_MAX_CHARS} characters)"


def _provisional(cur, table: str, ids: list[str]) -> bool:
    if not ids:
        return False
    return bool(_one(cur, "SELECT 1 FROM staging.fact_source WHERE table_name = %s AND row_id = ANY(%s) AND quote LIKE %s LIMIT 1",
                     (table, ids, PROVISIONAL + "%")))


def block_client_capabilities(cur) -> str:
    """What the client makes or does, at line level: per category the sub-types of its products; then ventures, subsidiaries
    and capabilities (client_product rows of kind venture / capability); then what partners supply (client_partner_product)."""
    items = _client_items(cur)
    out = []
    by_cat: dict = {}
    for r in items:
        if r["kind"] in ("product", "variant"):
            by_cat.setdefault(r["category"] or "uncategorised", []).append(r)
    for cat, rs in sorted(by_cat.items()):
        subs: dict = {}
        for r in rs:
            k = r["sub"] or "sub-type unknown"
            subs[k] = subs.get(k, 0) + 1
        out.append(f"LINE {cat}: {len(rs)} products; " + ", ".join(f"{k} x{v}" for k, v in sorted(subs.items(), key=lambda kv: -kv[1])))
    for r in items:
        if r["kind"] not in ("product", "variant"):
            out.append(f"{r['kind'].upper()} ({r['category'] or 'uncategorised'}): {_cut(r['product_name'], 150)}")
    for r in _one(cur, """SELECT p.partner_name, x.activity_type, x.scope, x.market, x.status
                          FROM staging.client_partner_product x JOIN staging.client_partner p USING (client_partner_id)
                          ORDER BY p.partner_name, x.partner_product_id LIMIT 60"""):
        out.append(f"PARTNER {r['partner_name']}: " + _cut("; ".join(b for b in (r["activity_type"], r["scope"], r["market"], r["status"]) if b), 200))
    return "\n".join(out) if out else NONE_ON_RECORD


_ACTIVITY = {"Local production": "manufactures", "Licensed production": "manufactures (licensed)", "Export": "sells (export)",
             "Sales and service": "sells (sales / service site)"}
_TIER_NAME = {0: "client", 1: "primary", 2: "independent", 3: "other"}


def block_client_markets(cur) -> str:
    """`country: activity, activity - products - since year - source tier - note`, one line per country, from the client's geo
    presence rows (company_role client) and the countries of its partners. Export / Sales + Planned reads as 'offered / planned'.
    Capped at MARKETS_MAX_ROWS countries."""
    rows = _one(cur, """SELECT l.country_name, p.presence_id, p.activity_type, p.presence_status, p.relationship_text,
                               (SELECT min(g.since_date) FROM staging.competitive_geo_product g WHERE g.presence_id = p.presence_id) AS since,
                               (SELECT string_agg(DISTINCT g.product_name, '; ') FROM staging.competitive_geo_product g
                                 WHERE g.presence_id = p.presence_id AND g.product_name IS NOT NULL) AS products,
                               (SELECT min(CASE f.source_tier WHEN 'client' THEN 0 WHEN 'primary' THEN 1 WHEN 'independent' THEN 2 ELSE 3 END)
                                  FROM staging.fact_source f WHERE f.table_name = 'competitive_geo_company_presence' AND f.row_id = p.presence_id::text) AS tier
                        FROM staging.competitive_geo_company_presence p
                        JOIN staging.competitive_geo_location l ON l.location_id = p.location_id
                        WHERE p.company_role = 'client' ORDER BY l.country_name, p.presence_id""")
    countries: dict = {}
    ids: list = []
    for r in rows:
        d = countries.setdefault(r["country_name"], {"acts": [], "products": [], "since": None, "tier": None, "note": ""})
        act = _ACTIVITY.get(r["activity_type"], (r["activity_type"] or "active").lower())
        if r["presence_status"] == "Planned":
            act = "offered / planned" if r["activity_type"] in ("Export", "Sales and service", None) else act + " (planned)"
        if act not in d["acts"]:
            d["acts"].append(act)
        for pn in (r["products"] or "").split("; "):
            if pn and pn not in d["products"]:
                d["products"].append(pn)
        if r["since"] and (d["since"] is None or r["since"] < d["since"]):
            d["since"] = r["since"]
        if r["tier"] is not None and (d["tier"] is None or r["tier"] < d["tier"]):
            d["tier"] = r["tier"]
        d["note"] = d["note"] or _cut(r["relationship_text"], 140)
        ids.append(str(r["presence_id"]))
    for r in _one(cur, "SELECT DISTINCT country, (partner_type = 'Customer') AS cust FROM staging.client_partner WHERE country IS NOT NULL AND country <> ''"):
        d = countries.setdefault(r["country"], {"acts": [], "products": [], "since": None, "tier": None, "note": ""})
        act = "customer based here" if r["cust"] else "partner based here"      # a customer is the buyer itself; every other tie is a partner organisation
        if act not in d["acts"]:
            d["acts"].append(act)
    if not countries:
        return NONE_ON_RECORD
    lines = []
    for c, d in sorted(countries.items())[:MARKETS_MAX_ROWS]:
        bits = [f"{c}: {', '.join(d['acts'])}"]
        if d["products"]:
            bits.append(_cut("; ".join(d["products"][:4]), 120))
        if d["since"]:
            bits.append(f"since {d['since'].year}")
        if d["tier"] is not None:
            bits.append(f"source: {_TIER_NAME[d['tier']]}")
        if d["note"]:
            bits.append(d["note"])
        lines.append(" - ".join(bits))
    if len(countries) > MARKETS_MAX_ROWS:
        lines.append(f"... ({len(countries)} countries in all)")
    if _provisional(cur, "competitive_geo_company_presence", ids):
        lines.insert(0, "NOTE: provisional research, to be replaced by the client's Excel")
    return "\n".join(lines)


def block_client_partners(cur) -> str:
    """`partner (country) - type - relationship type: what it supplies or does with the client - since - status`, one line per partner.
    Capped at PARTNERS_MAX_ROWS partners and PARTNER_LINE_CAP characters per line."""
    partners = _one(cur, "SELECT client_partner_id, partner_name, country, partner_type, relationship_scope, strategic_role, "
                         "relationship_start_date, relationship_status FROM staging.client_partner ORDER BY partner_name")
    if not partners:
        return NONE_ON_RECORD
    rels, prods = {}, {}
    for r in _one(cur, "SELECT client_partner_id, relationship_type, description, territory, status, start_date FROM staging.client_partner_relationship "
                       "ORDER BY client_partner_id, relationship_id"):
        rels.setdefault(r["client_partner_id"], []).append(r)
    for r in _one(cur, "SELECT client_partner_id, activity_type, scope, market FROM staging.client_partner_product ORDER BY client_partner_id, partner_product_id"):
        prods.setdefault(r["client_partner_id"], []).append(r)
    lines = []
    for p in partners[:PARTNERS_MAX_ROWS]:
        pid = p["client_partner_id"]
        what = [f"{r['relationship_type']}: {r['description']}" if r["description"] else r["relationship_type"] for r in rels.get(pid, [])]
        what += [("; ".join(b for b in (r["activity_type"], r["scope"], r["market"]) if b)) for r in prods.get(pid, [])]
        if not what and p["relationship_scope"]:
            what = [p["relationship_scope"]]
        since = p["relationship_start_date"] or next((r["start_date"] for r in rels.get(pid, []) if r["start_date"]), None)
        line = _paren(p["partner_name"], p["country"]) + " - " + (p["partner_type"] or "type not stated") + " - " \
            + ("; ".join(what) if what else "supply or scope not stated")
        if since:
            line += f" - since {since.year}"
        if p["relationship_status"]:
            line += f" - {p['relationship_status']}"
        lines.append(_cut(line, PARTNER_LINE_CAP))
    if len(partners) > PARTNERS_MAX_ROWS:
        lines.append(f"... ({len(partners)} partners in all)")
    if _provisional(cur, "client_partner", [str(p["client_partner_id"]) for p in partners]):
        lines.insert(0, "NOTE: provisional research, to be replaced by the client's Excel")
    return "\n".join(lines)


def block_competitors_extended(cur, comps: list[dict]) -> str:
    """`display_name (short; country) - sub-types: category: sub x n, ... - sells in: countries`. The sub-types come from product_class
    (the matchup engine's classification, 'unknown' left out); the markets from competitive_geo_company_presence (role competitor).
    Caps: COMP_MAX_CATEGORIES categories, COMP_MAX_SUBTYPES sub-types per category, COMP_MAX_MARKETS countries."""
    if not comps:
        return NONE_ON_RECORD
    cls: dict = {}
    for r in _one(cur, """SELECT p.competitor_id, c.category, c.sub_type, count(*) AS n
                          FROM staging.competitive_product p JOIN staging.product_class c
                            ON c.product_side = 'competitor' AND c.product_id = p.product_id::text
                          WHERE c.sub_type <> 'unknown' GROUP BY 1, 2, 3 ORDER BY n DESC"""):
        cls.setdefault(r["competitor_id"], {}).setdefault(r["category"], []).append((r["sub_type"], r["n"]))
    mk: dict = {}
    for r in _one(cur, """SELECT p.competitor_id, l.country_name FROM staging.competitive_geo_company_presence p
                          JOIN staging.competitive_geo_location l ON l.location_id = p.location_id
                          WHERE p.company_role = 'competitor' AND p.competitor_id IS NOT NULL
                          ORDER BY p.competitor_id, p.display_order NULLS LAST, l.country_name"""):
        if r["country_name"] not in mk.setdefault(r["competitor_id"], []):
            mk[r["competitor_id"]].append(r["country_name"])
    lines = []
    for c in comps:
        bycat = cls.get(c["competitor_id"], {})
        cats = sorted(bycat.items(), key=lambda kv: -sum(n for _, n in kv[1]))[:COMP_MAX_CATEGORIES]
        sub = "; ".join(f"{cat}: " + ", ".join(f"{st} x{n}" for st, n in v[:COMP_MAX_SUBTYPES]) for cat, v in cats) or NONE_ON_RECORD
        mkt = mk.get(c["competitor_id"], [])
        mtxt = (", ".join(mkt[:COMP_MAX_MARKETS]) + (f" (+{len(mkt) - COMP_MAX_MARKETS} more)" if len(mkt) > COMP_MAX_MARKETS else "")) if mkt else NONE_ON_RECORD
        lines.append(f"{_paren(c['display_name'], c['short_name'], c['origin_country'])} - sub-types: {sub} - sells in: {mtxt}")
    return "\n".join(lines)


def context_blocks(cur, client: dict) -> dict[str, str]:
    """Every block of _shared.yml `context_blocks`, rendered as text. An empty list = "none on record"."""
    def lines(items: list[str]) -> str:
        return "\n".join(items) if items else NONE_ON_RECORD

    blocks = {}
    bits = [("name", client.get("name")), ("legal name", client.get("legal_name")),
            ("headquarters", client.get("headquarters")), ("sector", client.get("sector")), ("country", client.get("country"))]
    blocks["client"] = "; ".join(f"{k}: {v}" for k, v in bits if v) or NONE_ON_RECORD
    blocks["client_products"] = lines([
        _paren(r["product_name"], r["category"]) for r in _one(
            cur, "SELECT product_name, category FROM staging.client_product ORDER BY product_name")])
    comps = _one(cur, "SELECT competitor_id, display_name, short_name, origin_country FROM staging.competitive_competitor "
                      "ORDER BY display_name")
    blocks["competitors"] = lines([_paren(c["display_name"], c["short_name"], c["origin_country"]) for c in comps])
    prods = _one(cur, "SELECT competitor_id, product_name, category FROM staging.competitive_product ORDER BY product_name")
    per = []
    for c in comps:
        mine = [_paren(p["product_name"], p["category"]) for p in prods if p["competitor_id"] == c["competitor_id"]]
        per.append(f"{c['display_name']}: {'; '.join(mine) if mine else NONE_ON_RECORD}")
    blocks["competitor_products"] = lines(per) if prods else NONE_ON_RECORD
    blocks["categories"] = lines([r["category_name"] for r in _one(
        cur, "SELECT category_name FROM staging.technology_category ORDER BY display_order, category_name")])
    blocks["moment_levels"] = lines([f"{r['level_code']} = {r['level_label']}" for r in _one(
        cur, "SELECT level_code, level_label FROM staging_ui.competitive_competitor_moment_level ORDER BY display_order")])
    blocks["client_portfolio"] = block_client_portfolio(cur)
    blocks["client_capabilities"] = block_client_capabilities(cur)
    blocks["client_markets"] = block_client_markets(cur)
    blocks["client_partners"] = block_client_partners(cur)
    blocks["competitors_extended"] = block_competitors_extended(cur, comps)
    return blocks


# ---- placeholders -------------------------------------------------------------------------------------

def fill(text: str, client: dict, subject: dict, context: dict, documents: str) -> str:
    """Replace {{client.x}} {{subject.x}} {{context.x}} {{documents}}. Unknown -> PromptError."""
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key == "documents":
            return documents
        if "." not in key:
            raise PromptError(f"unknown placeholder {{{{{key}}}}}")
        ns, name = key.split(".", 1)
        table = {"client": client, "subject": subject, "context": context}.get(ns)
        if table is None or name not in table:
            raise PromptError(f"unknown placeholder {{{{{key}}}}}")
        return NONE_ON_RECORD if table[name] is None else _s(table[name])

    return PLACEHOLDER.sub(sub, text)


def required_context(spec: dict) -> list[str]:
    ctx = spec.get("context") or []
    unknown = [c for c in ctx if c not in spec["context_blocks"]]
    if unknown:
        raise PromptError(f"unknown context block(s) {unknown}; _shared.yml has {list(spec['context_blocks'])}")
    return ctx


# ---- subjects -------------------------------------------------------------------------------------------

def subjects(cur, spec: dict) -> list[dict]:
    """All subject rows of the prompt (SQL on kssl_staging), in the query's order."""
    key = spec["subject"]["key"]
    rows = _one(cur, spec["subject"]["query"])
    for r in rows:
        if key not in r:
            raise PromptError(f"subject.key '{key}' is not a column of subject.query")
        r["_key"] = str(r[key])
    return rows


# ---- documents -------------------------------------------------------------------------------------------

class _TextParser(HTMLParser):
    """Readable text: paragraphs / headings / list items; scripts, nav, footers, forms... skipped.
    Text inside <article> is kept apart so it can be preferred."""
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "iframe", "button",
            "select", "template", "figure", "figcaption"}
    BLOCK = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "td", "th", "div"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.article = 0
        self.buf: list[str] = []
        self.all: list[str] = []
        self.art: list[str] = []

    def _flush(self):
        t = " ".join("".join(self.buf).split())
        self.buf = []
        if t:
            self.all.append(t)
            if self.article:
                self.art.append(t)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "article":
            self._flush()
            self.article += 1
        elif tag in self.BLOCK or tag == "br":
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "article":
            self._flush()
            self.article = max(0, self.article - 1)
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def _good_blocks(blocks: list[str]) -> list[str]:
    seen, out = set(), []
    for b in blocks:
        if len(b) < 40 and not b.endswith((".", "!", "?", '"', "”")) and len(b.split()) < 4:
            continue                       # menu items, labels, bylines of one or two words
        if b in seen:
            continue
        seen.add(b)
        out.append(b)
    return out


def page_text(page_html: str) -> tuple[str, str]:
    """(title, readable text) of an HTML page."""
    p = _TextParser()
    try:
        p.feed(page_html)
        p.close()
    except Exception:
        pass
    art, allb = _good_blocks(p.art), _good_blocks(p.all)
    blocks = art if sum(map(len, art)) >= 500 else allb
    text = "\n".join(blocks)
    from backend.news import parse_page, _MetaParser, _ld_objects      # reuse the news job's page parsing
    title = parse_page(page_html, "https://x.invalid/").title
    if len(text) < 400:                  # paywalled / script-rendered pages often carry the body in JSON-LD
        m = _MetaParser()
        try:
            m.feed(page_html)
        except Exception:
            pass
        for o in _ld_objects(m.ld):
            body = o.get("articleBody")
            if isinstance(body, str) and len(body) > len(text):
                text = html.unescape(body)
    return title, text


def fetch_document(url: str, cap: int = DOC_CAP) -> tuple[str, str]:
    """(final url, text) of a web page, capped. DocumentError when it cannot be read."""
    from backend.news import http, page_blocked
    r = http(url)
    if r.status == 0 or r.status >= 500:
        r = http(url)
    blocked = page_blocked(r)
    if blocked:
        raise DocumentError(f"{url}: {blocked}")
    if r.status != 200:
        raise DocumentError(f"{url}: http {r.status}")
    ctype = r.headers.get("content-type", "").lower()
    if ctype and "html" not in ctype and "text" not in ctype and "xml" not in ctype:
        raise DocumentError(f"{url}: content-type {ctype}")
    title, text = page_text(r.text())
    if len(text) < 300:
        raise DocumentError(f"{url}: no readable article text ({len(text)} chars)")
    text = (f"{title}\n" if title and not text.startswith(title) else "") + text
    return r.url, text[:cap]


SUBJECT_QUOTED = re.compile(r"'\{\{\s*subject\.(\w+)\s*\}\}'")
SUBJECT_BARE = re.compile(r"\{\{\s*subject\.(\w+)\s*\}\}")


def bind_subject(query: str, subject: dict) -> tuple[str, dict]:
    """A subject placeholder inside a documents query becomes a bound SQL parameter, never pasted text:
    '{{subject.x}}' and {{subject.x}} -> %(x)s. Returns (query, params)."""
    args: dict = {}

    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in subject:
            raise PromptError(f"documents query: subject has no column '{name}'")
        args[name] = subject[name]
        return f"%({name})s"

    q = query.replace("%", "%%")
    return SUBJECT_BARE.sub(sub, SUBJECT_QUOTED.sub(sub, q)), args


def sql_document(cur, query: str, subject: dict, cap: int = 24_000) -> str:
    """Rows of `query` as text, one per line: col: value | col: value."""
    q, args = bind_subject(query, {k: v for k, v in subject.items() if not k.startswith("_")})
    rows = _one(cur, q, args) if args else _one(cur, q.replace("%%", "%"), None)
    if not rows:
        return NONE_ON_RECORD
    return "\n".join(" | ".join(f"{k}: {_s(v)}" for k, v in r.items() if v is not None) for r in rows)[:cap]


def documents(cur, spec: dict, subject: dict) -> tuple[str, list[str]]:
    """({{documents}} text, urls fetched). One block per document, each headed by its source. A null url
    field is skipped; with several documents, a page that cannot be read is noted and the run goes on."""
    docs = spec["subject"].get("documents") or []
    parts, urls, failures = [], [], []
    raw_urls: set = set()                           # urls the raw layer already gave: a later `from: url` entry for the same url is not fetched
    has_other = any(d.get("from") != "url" for d in docs)
    for d in docs:
        src = d.get("from")
        if src == "url":
            url = subject.get(d["field"])
            if not url or str(url) in raw_urls:
                continue
            try:
                final, text = fetch_document(str(url))
            except DocumentError as e:
                failures.append(str(e))
                parts.append(f"[SOURCE {url}] could not be read ({e})")
                continue
            urls.append(final)                       # logged; the header keeps the url the task names
            parts.append(f"[SOURCE {url}]\n{text}")
        elif src == "sql":
            parts.append(f"[ROWS]\n{sql_document(cur, d['query'], subject)}")
        elif src == "source_document":              # the raw layer's stored text (prompts/raw_docs.py); [] = nothing usable, the next entry is tried
            from prompts import raw_docs
            blocks = raw_docs.resolve(cur, d, subject)
            raw_urls.update(b.url for b in blocks)
            parts += [f"[SOURCE {b.url}]\n{b.text}" for b in blocks]
        elif src == "tender_raw":                   # the stored API record of a tender notice (prompts/tender_docs.py); "" = no raw row, the next entry is tried
            from prompts import tender_docs
            text = tender_docs.resolve(cur, d, subject)
            if text:
                parts.append(f"[SOURCE {subject.get(d.get('url_field', 'source_url'))}]\n{text}")
        else:
            raise PromptError(f"subject.documents: unknown 'from: {src}' (use url, sql, source_document or tender_raw)")
    n_url = sum(1 for d in docs if d.get("from") == "url" and subject.get(d["field"]) and str(subject.get(d["field"])) not in raw_urls)
    if failures and not has_other and len(failures) == n_url:
        raise DocumentError("; ".join(failures))
    return ("\n\n".join(parts) if parts else NONE_ON_RECORD), urls


# ---- blocks that depend on the subject (the competitor of the article) ------------------------------------------------------------

CATALOGUE_MAX_CHARS = 8_000                         # competitor_catalogue: one competitor's product names
SUBJECT_BLOCKS = ("stories", "competitor_catalogue")


def block_competitor_catalogue(cur, competitor_id) -> str:
    """`category > sub_type: product name` for the products of one competitor (names exactly as stored: a ref_product must match them)."""
    if not competitor_id:
        return NONE_ON_RECORD
    rows = _one(cur, """SELECT p.product_name, p.category, c.sub_type FROM staging.competitive_product p
                        LEFT JOIN staging.product_class c ON c.product_side = 'competitor' AND c.product_id = p.product_id::text
                        WHERE p.competitor_id = %s ORDER BY p.category, c.sub_type, p.product_name""", (str(competitor_id),))
    if not rows:
        return NONE_ON_RECORD
    lines, size = [], 0
    for r in rows:
        sub = r["sub_type"] if r["sub_type"] not in (None, "unknown") else "sub-type unknown"
        line = f"{r['category'] or 'uncategorised'} > {sub}: {r['product_name']}"
        if size + len(line) + 1 > CATALOGUE_MAX_CHARS:
            lines.append(f"... ({len(rows)} products in all; list cut at {CATALOGUE_MAX_CHARS} characters)")
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines)


def subject_block(cur, name: str, subject: dict) -> str:
    """The context blocks that are rendered per subject (they read the subject's competitor_id column)."""
    cid = subject.get("competitor_id")
    if name == "stories":
        if not cid:
            return NONE_ON_RECORD
        from prompts import story
        return story.stories_block(cur, competitor_id=cid, pillar="competitive")
    if name == "competitor_catalogue":
        return block_competitor_catalogue(cur, cid)
    raise PromptError(f"unknown subject block {name}")


# ---- everything for one run ------------------------------------------------------------------------------

def build_prompt(cur, spec: dict, subject: dict, client: dict | None = None, blocks: dict | None = None,
                 docs: tuple[str, list[str]] | None = None) -> tuple[str, str, list[str]]:
    """(system, task text, fetched urls) with every placeholder filled."""
    client = client or client_row(cur)
    blocks = blocks or context_blocks(cur, client)
    ctx = {k: (subject_block(cur, k, subject) if k in SUBJECT_BLOCKS else blocks[k]) for k in required_context(spec)}
    # a placeholder naming a block the prompt did not list is an error (it would render nothing)
    doc_text, urls = docs if docs is not None else (
        documents(cur, spec, subject) if "{{documents}}" in spec["task"] or "{{ documents }}" in spec["task"] else (NONE_ON_RECORD, []))
    subj = {k: v for k, v in subject.items() if not k.startswith("_")}
    system = fill(spec["system"], client, subj, ctx, doc_text)
    task = fill(spec["task"], client, subj, ctx, doc_text)
    return system, task, urls


# ---- check: python -m prompts.render --blocks | --preview <prompt id> ----------------------------------------------------------

LENS_BLOCKS = ["client_portfolio", "client_capabilities", "client_markets", "client_partners", "competitors_extended"]


def _main(argv: list[str]) -> int:
    """--blocks: render every context block and show size + first lines.  --preview <id>: the filled prompt of <id> (first subject)
    with the five lens blocks appended in memory (the prompt file is not touched), to see how Phase 3 will receive them."""
    import argparse
    ap = argparse.ArgumentParser(prog="python -m prompts.render")
    ap.add_argument("--blocks", action="store_true")
    ap.add_argument("--preview", metavar="PROMPT_ID")
    ap.add_argument("--lines", type=int, default=10)
    a = ap.parse_args(argv)
    conn = connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            client = client_row(cur)
            blocks = context_blocks(cur, client)
            if a.blocks or not a.preview:
                for k, v in blocks.items():
                    ls = v.splitlines()
                    print(f"=== {k}: {len(v)} chars, {len(ls)} lines" + ("  (EMPTY)" if v == NONE_ON_RECORD else ""))
                    if k in LENS_BLOCKS:
                        print("\n".join(l[:230] for l in ls[: a.lines]))
            if a.preview:
                spec = load_prompt(a.preview)
                spec["context"] = list(dict.fromkeys([*(spec.get("context") or []), *LENS_BLOCKS]))
                spec["task"] += "".join(f"\n\n{k.upper()}:\n{{{{context.{k}}}}}" for k in LENS_BLOCKS)
                subs = subjects(cur, spec)
                system, task, _ = build_prompt(cur, spec, subs[0], client, blocks, ("none on record", []))
                print(f"=== preview {a.preview} (subject {subs[0]['_key'][:12]}): task {len(task)} chars; the lens blocks as the model would see them:")
                print(task[task.index(LENS_BLOCKS[0].upper() + ":"):][:6000])
    finally:
        conn.rollback()
        conn.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
