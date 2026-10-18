"""Tender notice text from the stored API record (staging.tender_raw.raw), for the `tender` prompt.

TED, GeM, UK Find a Tender, Prozorro and the other tender APIs are hard to fetch as web pages (WAF challenge, PDF, login), but the
harvester already stored the API record of every notice. A prompt reads it with a `subject.documents` entry

    - from: tender_raw
      field: raw_id            # subject column holding staging.tender_raw.raw_id
      cap: 12000               # characters kept

`resolve(cur, entry, subject)` returns the notice as `key: value` lines (language maps reduced to English, else the first language;
HTML entities decoded; empty values and the bulky parts of the Prozorro / OCDS records dropped), or "" when the notice has no raw row.
Nothing is added to the record: every line is a field the API returned, so a model quote can be checked against the prompt text.
Only reads; never writes.

    python -m prompts.tender_docs --selftest | --show <source_api> [n]
"""

from __future__ import annotations

import html
import json
import re
import sys

DEFAULT_CAP = 12_000
VALUE_CAP = 1_500
LANG = re.compile(r"^[a-z]{3}$")
EMPTY = {"", "CDL", "null", "None", "[]", "{}"}
# bulky or useless parts of the records (the bid documents of a Prozorro tender, its criteria, complaints, signatures ...)
DROP = {"links", "documents", "criteria", "bids", "complaints", "questions", "contractChangeRationaleTypes", "signatureValue",
        "next_check", "owner", "owner_token", "tender_token", "revisions", "dateCreated", "dateModified", "complaintPeriod",
        "awardPeriod", "qualificationPeriod", "auctionUrl", "auctionPeriod", "plans", "agreements", "causeDetails", "milestones",
        "relatedProcesses", "initiationType", "language", "ocid", "id", "version", "hash", "publisher", "license", "publicationPolicy",
        "mainProcurementCategory", "submissionMethod", "awardCriteria", "enquiryPeriod", "guarantee", "tender_id", "etag",
        "address", "contactPoint", "identifier", "additionalIdentifiers", "unit_id", "scheme", "uri", "legalName"}
KEEP_ID = {"tenderID", "id"}      # `id` is dropped everywhere except where it is the notice number (decp)


def _txt(v) -> str:
    return " ".join(html.unescape(str(v)).replace("\r", " ").split())


def _is_lang_map(d: dict) -> bool:
    return bool(d) and all(LANG.match(str(k)) for k in d)


def _lang_pick(d: dict) -> str:
    for k in ("eng", "ENG", "en"):
        if d.get(k):
            return _scalar(d[k])
    first = next((v for v in d.values() if v), None)
    return _scalar(first) if first is not None else ""


def _scalar(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return _lang_pick(v) if _is_lang_map(v) else "; ".join(f"{k}={_scalar(x)}" for k, x in v.items() if _scalar(x))
    if isinstance(v, list):
        return "; ".join(s for s in (_scalar(x) for x in v) if s)
    return _txt(v)


def _walk(o, path: str, out: list, depth: int = 0) -> None:
    if depth > 5:
        return
    if isinstance(o, dict) and not _is_lang_map(o):
        for k, v in o.items():
            if k in DROP and not (k == "id" and depth == 0 and path == ""):
                continue
            _walk(v, f"{path}.{k}" if path else str(k), out, depth + 1)
    elif isinstance(o, list) and any(isinstance(x, (dict, list)) for x in o):
        for i, x in enumerate(o[:12]):
            _walk(x, f"{path}[{i + 1}]", out, depth + 1)
        if len(o) > 12:
            out.append(f"{path}: ({len(o)} entries; the first 12 are shown)")
    else:
        s = _scalar(o)
        if s not in EMPTY:
            out.append(f"{path}: {s[:VALUE_CAP]}" + ("..." if len(s) > VALUE_CAP else ""))


def render_record(api: str, raw: dict, cap: int = DEFAULT_CAP) -> str:
    """The notice as text. `api` is staging.tender_raw.source_api."""
    out: list = []
    if api == "prozorro_ua":                        # keep the tender, its items, lots, awards and contracts; drop bids / criteria / documents
        raw = dict(raw)
        for k in ("awards", "contracts"):
            raw[k] = [{kk: vv for kk, vv in a.items() if kk in ("status", "date", "value", "suppliers", "dateSigned", "period", "title",
                                                                    "description", "amount")} for a in (raw.get(k) or [])[:6]]
        raw["cancellations"] = [{"reason": c.get("reason"), "status": c.get("status"), "date": c.get("date")} for c in (raw.get("cancellations") or [])[:3]]
        raw["items"] = [{kk: vv for kk, vv in it.items() if kk in ("description", "quantity", "unit", "classification", "deliveryDate",
                                                                      "deliveryAddress", "additionalClassifications")} for it in (raw.get("items") or [])[:15]]
    elif api == "uk_fts":
        raw = dict(raw)
        raw["parties"] = [{kk: vv for kk, vv in p.items() if kk in ("name", "roles")} for p in (raw.get("parties") or [])[:8]]
    _walk(raw, "", out)
    if api == "decp_fr" and raw.get("id"):
        out.insert(0, f"id: {raw['id']}")
    text = "\n".join(out)
    return text[:cap]


def resolve(cur, entry: dict, subject: dict) -> str:
    """Text of the subject's stored notice, or "" when there is none (the caller then tries the next documents entry)."""
    rid = subject.get(entry.get("field", "raw_id"))
    if not rid:
        return ""
    cur.execute("SELECT source_api, notice_id, notice_url, title, buyer_name, country, published_at, deadline_at, value_text, cpv_codes, raw "
                "FROM staging.tender_raw WHERE raw_id = %s::uuid", (str(rid),))
    r = cur.fetchone()
    if r is None:
        return ""
    r = dict(r)
    head = [f"harvest.source_api: {r['source_api']}", f"harvest.notice_id: {r['notice_id']}"]
    if r.get("notice_url"):
        head.append(f"harvest.notice_url: {r['notice_url']}")
    for col in ("title", "buyer_name", "country", "published_at", "deadline_at", "value_text"):
        if r.get(col) not in (None, ""):
            head.append(f"harvest.{col}: {_txt(r[col])}")
    if r.get("cpv_codes"):
        head.append("harvest.cpv_codes: " + ", ".join(r["cpv_codes"]))
    body = render_record(r["source_api"], r.get("raw") or {}, int(entry.get("cap", DEFAULT_CAP)))
    return "\n".join(head) + "\n" + body


def _selftest() -> None:
    ted = {"buyer-name": {"ron": ["Unitatea Fictiva 1"]}, "notice-title": {"eng": "Veland - Guns - 24 towed guns", "ron": "x"},
           "total-value": 1000, "links": {"html": {"ENG": "u"}}, "classification-cpv": ["35300000"], "empty": [], "x": "CDL",
           "description-lot": {"fra": ["Fourniture de 24 canons"]}}
    t = render_record("ted_eu", ted)
    assert "buyer-name: Unitatea Fictiva 1" in t and "notice-title: Veland - Guns - 24 towed guns" in t and "links" not in t
    assert "description-lot: Fourniture de 24 canons" in t and "x:" not in t and "empty" not in t and "classification-cpv: 35300000" in t
    pz = {"title": "Fictive vehicles", "items": [{"description": "Armoured car", "quantity": 2, "unit": {"name": "pcs"}, "id": "zz"}], "bids": [{"big": "x" * 5000}],
          "criteria": [{"a": 1}], "awards": [{"status": "active", "suppliers": [{"name": "Acme Ltd", "address": {"c": "x"}}], "value": {"amount": 5, "currency": "UAH"}, "secret": 1}]}
    p = render_record("prozorro_ua", pz)
    assert "items[1].description: Armoured car" in p and "items[1].quantity: 2" in p and "bids" not in p and "criteria" not in p
    assert "awards[1].suppliers[1].name: Acme Ltd" in p and "secret" not in p and "address" not in p
    assert len(render_record("canada", {"a": "b " * 9000}, cap=500)) == 500
    assert _txt("A&#8217;B  \r\n C") == "A’B C"
    print("tender_docs self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--show" in sys.argv:
        import psycopg2
        import psycopg2.extras
        from prompts import render
        i = sys.argv.index("--show")
        api, n = sys.argv[i + 1], int(sys.argv[i + 2]) if len(sys.argv) > i + 2 else 1
        conn = render.connect()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT raw_id FROM staging.tender_raw WHERE source_api = %s AND 'kssl_relevant' = ANY(defence_tags) ORDER BY random() LIMIT %s", (api, n))
        for r in cur.fetchall():
            print("=" * 20)
            print(resolve(cur, {"field": "raw_id"}, {"raw_id": r["raw_id"]}))
    else:
        print(__doc__)
