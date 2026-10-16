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
    has_other = any(d.get("from") != "url" for d in docs)
    for d in docs:
        src = d.get("from")
        if src == "url":
            url = subject.get(d["field"])
            if not url:
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
        else:
            raise PromptError(f"subject.documents: unknown 'from: {src}' (use url or sql)")
    n_url = sum(1 for d in docs if d.get("from") == "url" and subject.get(d["field"]))
    if failures and not has_other and len(failures) == n_url:
        raise DocumentError("; ".join(failures))
    return ("\n\n".join(parts) if parts else NONE_ON_RECORD), urls


# ---- everything for one run ------------------------------------------------------------------------------

def build_prompt(cur, spec: dict, subject: dict, client: dict | None = None, blocks: dict | None = None,
                 docs: tuple[str, list[str]] | None = None) -> tuple[str, str, list[str]]:
    """(system, task text, fetched urls) with every placeholder filled."""
    client = client or client_row(cur)
    blocks = blocks or context_blocks(cur, client)
    ctx = {k: blocks[k] for k in required_context(spec)}
    # a placeholder naming a block the prompt did not list is an error (it would render nothing)
    doc_text, urls = docs if docs is not None else (
        documents(cur, spec, subject) if "{{documents}}" in spec["task"] or "{{ documents }}" in spec["task"] else (NONE_ON_RECORD, []))
    subj = {k: v for k, v in subject.items() if not k.startswith("_")}
    system = fill(spec["system"], client, subj, ctx, doc_text)
    task = fill(spec["task"], client, subj, ctx, doc_text)
    return system, task, urls
