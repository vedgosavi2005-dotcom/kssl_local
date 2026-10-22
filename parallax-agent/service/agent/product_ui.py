"""What the product's pages show, as searchable documents -- each tied to the page and the
block that displays it.

The source is the product's own GET /api/dataset (adapter/product.json product_api.dataset):
the exact payload its React app renders. adapter/ui_index.py maps it to documents; each says
where it lives -- pillar, view, the payload that opens it on the right item, and the
section heading to scroll to -- so the agent can answer from it AND take the user there.

The database (analytics.*) answers counting, ranking and comparing questions; this index
answers "what does the platform say about X" questions. The orchestrator uses both."""

import math
import os
import re
import threading
import time
from collections import Counter

import httpx

from . import adapter

PRODUCT_API = os.environ.get("PRODUCT_API", "http://127.0.0.1:8600").rstrip("/")
TTL_S = 600

_lock = threading.Lock()
_state = {"docs": None, "at": 0.0, "idf": None, "error": None, "meta": {"companies": {}, "news_topic": ""}}

_TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")
_STOP = set("a an and are as at be by for from has have in into is it its of on or that the this to was were will with "
            "what which who whom how does do did their there they them we our you your about show me tell give".split())


def _index():
    return adapter.module("ui_index")


def kinds() -> list:
    return list(_index().KINDS)


_INTENT_OF = {w: k for k, words in _index().INTENT.items() for w in words.split()}


def _company_words() -> dict:
    """company id -> the words that name it in a question (the adapter's companies[].aliases)"""
    return {c["id"]: " ".join(c.get("aliases") or []) for c in adapter.companies()}


def _tokens(s: str) -> list:
    return [t for t in _TOKEN.findall(s.lower()) if t not in _STOP and len(t) > 1]


def _ensure():
    with _lock:
        if _state["docs"] is not None and time.time() - _state["at"] < TTL_S:
            return
    try:
        r = httpx.get(PRODUCT_API + adapter.manifest()["product_api"]["dataset"], timeout=60, headers={"Accept-Encoding": "gzip"})
        r.raise_for_status()
        data = r.json()
        docs = _index().build(data, adapter.manifest())
        _state["meta"] = _index().meta(data)
        df = Counter()
        for doc in docs.values():
            toks = _tokens(doc["title"] + " " + doc["text"])
            doc["_tf"] = Counter(toks)
            doc["_title"] = set(_tokens(doc["title"]))
            doc["_len"] = max(1, len(toks))
            df.update(set(toks))
        n = len(docs)
        idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        with _lock:
            _state.update(docs=docs, idf=idf, at=time.time(), error=None)
        print(f"[agent] product UI index: {n} documents", flush=True)
    except Exception as exc:
        with _lock:
            _state["error"] = str(exc)
            if _state["docs"] is None:
                _state["docs"], _state["idf"] = {}, {}
        print(f"[agent] product UI index unavailable: {exc}", flush=True)


def _where(doc) -> str:
    p = doc.get("page")
    if not p:
        return "not on a single page"
    return f"{p['pillar']} / {p['view']}" + (f" › {doc['block']}" if doc.get("block") else "")


def search(query: str, kind: str = "", company_ids=(), limit: int = 6) -> list:
    _ensure()
    docs, idf = _state["docs"], _state["idf"]
    q = _tokens(query)
    if not q:
        return []
    intents = {_INTENT_OF[t] for t in q if t in _INTENT_OF}
    named = set(company_ids or ()) | {cid for cid, words in _company_words().items() if any(t in words.split() for t in q)}
    scored = []
    for doc in docs.values():
        if kind and kind != "any" and doc["kind"] != kind:
            continue
        score = 0.0
        for t in q:
            tf = doc["_tf"].get(t, 0)
            if tf:
                # BM25-style saturation, title hits weighted up
                score += idf.get(t, 0) * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * doc["_len"] / 400))
            if t in doc["_title"]:
                score += 2.0 * idf.get(t, 0)
        if named and doc.get("company") in named:
            score *= 2.0
        if intents and (doc["kind"] in intents or doc["id"].rsplit(":", 1)[-1] in intents):
            score *= 2.2
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, doc in scored[:limit]:
        snippet = doc["text"]
        # the snippet starts at the first line that mentions a query term
        for line in doc["text"].splitlines():
            if any(t in line.lower() for t in q):
                snippet = line
                break
        out.append({"doc_id": doc["id"], "kind": doc["kind"], "title": doc["title"], "where": _where(doc),
                    "snippet": snippet[:320]})
    return out


def read(doc_id: str, max_chars: int = 7000):
    _ensure()
    doc = _state["docs"].get(doc_id)
    if doc is None:
        return None
    text = doc["text"] if len(doc["text"]) <= max_chars else doc["text"][:max_chars] + "\n…(continues on the page)"
    nav = None
    if doc.get("page"):
        nav = {**doc["page"], "focus": doc.get("block") or ""}
    return {"doc_id": doc_id, "title": doc["title"], "where": _where(doc), "content": text, "navigate_to": nav}


def status() -> dict:
    return {"documents": len(_state["docs"] or {}), "error": _state["error"]}


def warm():
    _ensure()


def live_news(company: str) -> dict:
    """The live headlines the product shows for a company (its live-news panel), fetched
    through the product's own API. Live, not stored data."""
    _ensure()
    q = (company or "").lower().strip()
    names = _state["meta"].get("companies") or {}
    cid = next((k for k, n in names.items() if q and (q == k.lower() or q in n.lower() or n.lower() in q)), None)
    if cid is None:
        cid = next((k for k, words in _company_words().items() if any(w in q.split() for w in words.split())), None)
    if cid is None:
        return {"error": f"unknown company '{company}'", "companies": list(names.values())}
    name = names.get(cid, cid)

    def get(path, params):
        web = os.environ.get("PRODUCT_WEB", "").rstrip("/")
        routes = adapter.manifest()["product_api"].get("web_routes") or []
        base = web if web and any(path == r or path.startswith(r.rstrip("/") + "/") for r in routes) else PRODUCT_API
        r = httpx.get(base + path, params=params, timeout=40)
        r.raise_for_status()
        return r.json()

    out = _index().live_news(get, cid, name, _state["meta"])
    block = adapter.manifest()["product_api"].get("news_block")
    rival = any(c["id"] == cid for c in adapter.rivals())
    shown = ({"pillar": block["pillar"], "view": block["view"], "payload": {block["payload_key"]: cid}, "focus": block["focus"]}
             if block and rival else None)
    return {"company": name, "comp_id": cid, **out, "shown_on": shown}
