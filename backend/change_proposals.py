"""Changes found in the news (db/setup/41, owner 2026-10-24): what an article says that is NEW or DIFFERENT from our records -- a new
rival product and its specs, a spec figure, a leadership change, a new partner, a new plant, a company fact -- becomes a PROPOSAL.
Nothing touches the records until a reviewer clicks Accept on the review site ("Changes from news"); Accept writes the change into
the review data (staging) with its source, where it shows as a NEW / CHANGED card, and the usual Approve puts it live.

    add(cur, items, competitor_id=, article_url=, article_date=, source_prompt=, source_row_id=)   called by the prompts' loader hook
    pending(cur) / accept(cur, proposal_id, user, value=None) / reject(cur, proposal_id, user, note=None)   the review API
    python -m backend.change_proposals --selftest      (no DB)

An item: {"kind": new_product|spec|leadership|partner|location|company_fact, "subject": ..., "field": ..., "value": ...,
          "unit": ..., "effective_date": ..., "quote": "<the article's sentence>"}
  new_product   subject = product name, field = category (one of ours), value = one line on what it is
  spec          subject = product name, field = spec label ("Range"), value = the figure ("40"), unit ("km")
  leadership    subject = the person, field = the role ("Chief Executive Officer"), value = "appointed" / "left"
  partner       subject = the partner company, field = partner type, value = what the tie is
  location      subject = the place / plant name, field = facility | footprint, value = the country
  company_fact  field = employee_count_text | revenue_text | headquarters | starting_year_text | industry_sector, value = the fact
An item is DROPPED (not proposed) when it is not a change: the "new" product, partner or place is already held, or the value equals
ours. The same fact is proposed once; a rejected fact is not proposed again (fingerprint).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

KINDS = ("new_product", "spec", "leadership", "partner", "location", "company_fact")
FACT_COLS = ("employee_count_text", "revenue_text", "headquarters", "starting_year_text", "industry_sector")
NS = uuid.UUID("c4a9e000-0000-4000-8000-0000000000c1")


def norm(s: Any) -> str:
    """compare text the way a reader would: case, spacing, punctuation and thousands separators do not make a change"""
    t = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", str(s or "").lower())
    return re.sub(r"[^a-z0-9.]+", " ", t).strip()


def fingerprint(kind: str, competitor_id: str, subject: str, field: str | None, value: str) -> str:
    v = "" if kind in ("new_product", "partner", "location") else norm(value)    # a new thing is one proposal, whatever its blurb says
    return "|".join((kind, str(competitor_id), norm(subject), norm(field), v))


# A partner proposal's `field` is the model's own words ("teaming partner", "licence", "defence partner"); the stored
# competitive_partnership.partner_type is the prompts/partnership.yml vocabulary. First rule that matches the field wins, then the
# same rules on the value ("what the tie is"); nothing matched is Other. Order matters: a JV or a stake before the looser words.
PARTNER_TYPES = (
    ("Joint venture", r"joint[- ]?venture|\bjv\b|joint company"),
    ("Acquisition", r"acqui|\bstake\b|shareholder|takeover"),
    ("Teaming", r"teaming|consortium|\bbid\b|joint (?:bid|contract|award|offer)"),
    ("MoU / strategic", r"\bmou\b|memorand|letter of intent|\bloi\b"),
    ("Technology / ToT", r"licen[cs]|technolog|\btot\b|transfer|develop|research|universit|integrat|co-?production|assembl|locali[sz]|manufactur|production partner"),
    ("Supplier", r"suppl|subcontract|vendor|\border|contract|service|maintenance|repair|overhaul|\bmro\b|distribut|dealer|marketing|training"),
    ("MoU / strategic", r"strategic|cooperation|collaborat|alliance|framework"),
)


def partner_type(field: Any, value: Any = None) -> str:
    """the partner_type vocabulary word for a proposal's free-form field (then its value); Other when neither says"""
    for text in (field, value):
        t = str(text or "").lower()
        for word, rx in PARTNER_TYPES:
            if re.search(rx, t):
                return word
    return "Other"


def _one(cur, sql: str, args: tuple) -> dict | None:
    cur.execute(sql, args)
    r = cur.fetchone()
    return dict(r) if r else None


def aliases(name: str) -> set[str]:
    """every name a catalogue entry goes by: "KAAV / KAAV-II" -> kaav, kaav ii; "XM1776 Mobile Tactical Cannon (K9 Mobile Howitzer,
    K9MH)" -> the whole, the part outside brackets, each name inside; "COBRA - Personnel Carrier" -> cobra"""
    s = str(name or "")
    inside = [x for g in re.findall(r"\(([^)]*)\)", s) for x in re.split(r"[,;]", g)]
    outside = re.sub(r"\([^)]*\)", " ", s)
    parts = [s, outside, re.split(r"\s[-–—]\s", outside)[0], *re.split(r"\s/\s", outside), *inside]   # " / " only: "155 mm/52 cal" is one name
    return {norm(p) for p in parts if len(norm(p)) >= 2}


def _product(cur, competitor_id: str, name: str) -> dict | None:
    """our product of that name: the same name, or a shared alias (a proposed "KAAV-II" is our "KAAV / KAAV-II")"""
    cur.execute("SELECT product_id, product_name FROM staging.competitive_product WHERE competitor_id = %s", (competitor_id,))
    rows = [dict(r) for r in cur.fetchall()]
    want = norm(name)
    return next((r for r in rows if norm(r["product_name"]) == want), None) or \
        next((r for r in rows if aliases(r["product_name"]) & aliases(name)), None)


def resolve(cur, competitor_id: str, it: dict) -> dict | None:
    """{target_table, target_id, current_value} for one item, or None when it is not a change"""
    kind, subject, field, value = it["kind"], it["subject"], it.get("field"), it.get("value")
    if kind == "new_product":
        return None if _product(cur, competitor_id, subject) else {"target_table": "competitive_product", "target_id": None, "current_value": None}
    if kind == "spec":
        p = _product(cur, competitor_id, subject)
        if not p:
            return {"target_table": "competitive_product_specification", "target_id": None, "current_value": None}
        s = _one(cur, """SELECT spec_id, spec_value, unit FROM staging.competitive_product_specification
                         WHERE product_id = %s AND lower(spec_label) = lower(%s) LIMIT 1""", (p["product_id"], field))
        cur_v = " ".join(x for x in ((s or {}).get("spec_value"), (s or {}).get("unit")) if x) or None
        if s and norm(cur_v) == norm(" ".join(x for x in (str(value), it.get("unit") or "") if x)):
            return None
        return {"target_table": "competitive_product_specification", "target_id": str(s["spec_id"]) if s else None, "current_value": cur_v}
    if kind == "leadership":
        held = _one(cur, """SELECT leader_id, full_name FROM staging.competitive_leader
                            WHERE competitor_id = %s AND lower(role_title) = lower(%s) LIMIT 1""", (competitor_id, field))
        if held and norm(held["full_name"]) == norm(subject) and norm(value) != "left":
            return None
        return {"target_table": "competitive_leader", "target_id": str(held["leader_id"]) if held else None,
                "current_value": f"{field} = {held['full_name']}" if held else None}
    if kind == "partner":
        p = _one(cur, "SELECT relationship_id FROM staging.competitive_partnership WHERE competitor_id = %s AND lower(partner_name) = lower(%s) LIMIT 1",
                 (competitor_id, subject))
        return None if p else {"target_table": "competitive_partnership", "target_id": None, "current_value": None}
    if kind == "location":
        p = _one(cur, "SELECT location_id FROM staging.competitive_competitor_location WHERE competitor_id = %s AND lower(location_name) = lower(%s) LIMIT 1",
                 (competitor_id, subject))
        return None if p else {"target_table": "competitive_competitor_location", "target_id": None, "current_value": None}
    if kind == "company_fact":
        if field not in FACT_COLS:
            return None
        c = _one(cur, f"SELECT {field} AS v FROM staging.competitive_competitor WHERE competitor_id = %s", (competitor_id,))
        if c and norm(c["v"]) == norm(value):
            return None
        return {"target_table": "competitive_competitor", "target_id": str(competitor_id), "current_value": (c or {}).get("v")}
    return None


def add(cur, items: list[dict], *, competitor_id: str, article_url: str, article_date=None, source_prompt: str | None = None,
        source_row_id: str | None = None) -> dict:
    """store the items that are real changes as pending proposals; {added, dropped: [why]}"""
    added, dropped = 0, []
    for it in items or []:
        kind, subject, value, quote = it.get("kind"), (it.get("subject") or "").strip(), str(it.get("value") or "").strip(), (it.get("quote") or "").strip()
        if kind not in KINDS or not subject or not quote or (kind not in ("new_product", "partner") and not value):
            dropped.append(f"incomplete: {it}")
            continue
        r = resolve(cur, competitor_id, {**it, "subject": subject, "value": value})
        if r is None:
            dropped.append(f"not a change: {kind} {subject} {it.get('field') or ''} {value}".strip())
            continue
        cur.execute("""INSERT INTO staging.change_proposal (kind, competitor_id, subject, field, proposed_value, unit, target_table, target_id,
                           current_value, effective_date, article_url, quote, article_date, source_prompt, source_row_id, fingerprint)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (fingerprint) DO NOTHING""",
                    (kind, competitor_id, subject, it.get("field"), value or subject, it.get("unit"), r["target_table"], r["target_id"],
                     r["current_value"], it.get("effective_date"), article_url, quote, article_date, source_prompt, source_row_id,
                     fingerprint(kind, competitor_id, subject, it.get("field"), value)))
        added += cur.rowcount
    return {"added": added, "dropped": dropped}


def pending(cur, status: str = "pending", limit: int = 500) -> list[dict]:
    cur.execute("""SELECT p.*, c.display_name AS competitor FROM staging.change_proposal p
                   LEFT JOIN staging.competitive_competitor c ON c.competitor_id = p.competitor_id
                   WHERE %s = 'all' OR p.status = %s ORDER BY p.created_at DESC LIMIT %s""", (status, status, limit))
    return [dict(r) for r in cur.fetchall()]


def _source(cur, table: str, row_id: str, column: str, p: dict) -> None:
    cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at)
                   VALUES (%s, %s, %s, %s, 'article', %s, now())""", (table, str(row_id), column, p["article_url"], p["quote"]))


def accept(cur, proposal_id: str, user: str | None = None, value: str | None = None) -> dict:
    """write the change into the review data (staging) with its source; returns what was written. A reviewer may correct the
    value before accepting (value=)."""
    cur.execute("SELECT * FROM staging.change_proposal WHERE proposal_id = %s FOR UPDATE", (proposal_id,))
    p = cur.fetchone()
    if not p:
        raise ValueError("no such proposal")
    p = dict(p)
    if p["status"] != "pending":
        raise ValueError(f"already {p['status']}")
    v = (value or p["proposed_value"]).strip()
    cid, subj, field, kind = str(p["competitor_id"]), p["subject"], p["field"], p["kind"]
    if kind == "new_product":
        pid = str(uuid.uuid5(NS, f"product|{cid}|{norm(subj)}"))
        cat = field or "Other"
        cur.execute("""INSERT INTO staging.competitive_product (product_id, competitor_id, product_name, category, category_filter, is_collapsed, description, status)
                       VALUES (%s, %s, %s, %s, %s, false, %s, 'announced') ON CONFLICT DO NOTHING""",
                    (pid, cid, subj, cat, cat, None if v == subj else v))
        _source(cur, "competitive_product", pid, "product_name", p)
        applied = {"table": "competitive_product", "id": pid, "action": "insert"}
    elif kind == "spec":
        prod = _product(cur, cid, subj)
        if not prod:
            raise ValueError(f"product '{subj}' is not in the catalogue yet: accept its new-product proposal first")
        cur.execute("SELECT spec_id FROM staging.competitive_product_specification WHERE product_id = %s AND lower(spec_label) = lower(%s) LIMIT 1",
                    (prod["product_id"], field))
        row = cur.fetchone()
        if row:
            sid = str(row["spec_id"])
            cur.execute("UPDATE staging.competitive_product_specification SET spec_value = %s, unit = %s, source_url = %s WHERE spec_id = %s",
                        (v, p["unit"], p["article_url"], sid))
            action = "update"
        else:
            sid = str(uuid.uuid5(NS, f"spec|{prod['product_id']}|{norm(field)}"))
            cur.execute("""INSERT INTO staging.competitive_product_specification (spec_id, product_id, spec_label, spec_value, unit, source_url, source_count)
                           VALUES (%s, %s, %s, %s, %s, %s, 1)""", (sid, prod["product_id"], field, v, p["unit"], p["article_url"]))
            action = "insert"
        _source(cur, "competitive_product_specification", sid, "spec_value", p)
        applied = {"table": "competitive_product_specification", "id": sid, "action": action}
    elif kind == "leadership":
        former = None
        cur.execute("""SELECT leader_id, full_name FROM staging.competitive_leader WHERE competitor_id = %s AND lower(role_title) = lower(%s)""",
                    (cid, field))
        for old in cur.fetchall():                     # the old holder stays on record as "Former <role>" (no end date column; nothing is deleted)
            if norm(old["full_name"]) != norm(subj):
                cur.execute("UPDATE staging.competitive_leader SET role_title = %s WHERE leader_id = %s", (f"Former {field}", old["leader_id"]))
                former = old["full_name"]
        lid = None
        if norm(v) != "left":
            lid = str(uuid.uuid5(NS, f"leader|{cid}|{norm(subj)}"))
            initials = "".join(w[0] for w in subj.split()[:2]).upper()
            cur.execute("""INSERT INTO staging.competitive_leader (leader_id, competitor_id, full_name, role_title, role_source_url, avatar_initials)
                           VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""", (lid, cid, subj, field, p["article_url"], initials))
            _source(cur, "competitive_leader", lid, "role_title", p)
        applied = {"table": "competitive_leader", "id": lid, "action": "appoint" if lid else "left", "former": former}
    elif kind == "partner":
        rid = str(uuid.uuid5(NS, f"partner|{cid}|{norm(subj)}"))
        cur.execute("""INSERT INTO staging.competitive_partnership (relationship_id, partner_id, competitor_id, partner_name, partner_type, description,
                           status, view_relationship_action, as_of_date, source_count, source_note)
                       VALUES (%s, %s, %s, %s, %s, %s, 'announced', false, %s, 1, %s) ON CONFLICT DO NOTHING""",
                    (rid, str(uuid.uuid5(NS, f"partner-id|{norm(subj)}")), cid, subj, partner_type(field, v), None if v == subj else v,
                     p["article_date"], f"From the news: {p['article_url']}"))
        _source(cur, "competitive_partnership", rid, "partner_name", p)
        applied = {"table": "competitive_partnership", "id": rid, "action": "insert"}
    elif kind == "location":
        lid = str(uuid.uuid5(NS, f"location|{cid}|{norm(subj)}"))
        cur.execute("""INSERT INTO staging.competitive_competitor_location (location_id, competitor_id, location_name, location_type, country, source_url)
                       VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""", (lid, cid, subj, field or "facility", v, p["article_url"]))
        _source(cur, "competitive_competitor_location", lid, "location_name", p)
        applied = {"table": "competitive_competitor_location", "id": lid, "action": "insert"}
    elif kind == "company_fact":
        if field not in FACT_COLS:
            raise ValueError(f"not a company fact column: {field}")
        cur.execute(f"UPDATE staging.competitive_competitor SET {field} = %s WHERE competitor_id = %s", (v, cid))
        _source(cur, "competitive_competitor", cid, field, p)
        applied = {"table": "competitive_competitor", "id": cid, "action": "update", "column": field}
    else:
        raise ValueError(f"unknown kind {kind}")
    cur.execute("""UPDATE staging.change_proposal SET status = 'accepted', decided_by = %s, decided_at = now(), applied = %s,
                       proposed_value = %s WHERE proposal_id = %s""", (user, json.dumps(applied), v, proposal_id))
    return applied


def reject(cur, proposal_id: str, user: str | None = None, note: str | None = None) -> None:
    cur.execute("""UPDATE staging.change_proposal SET status = 'rejected', decided_by = %s, decided_at = now(), decision_note = %s
                   WHERE proposal_id = %s AND status = 'pending'""", (user, note, proposal_id))
    if not cur.rowcount:
        raise ValueError("no pending proposal with that id")


def _selftest() -> None:
    assert norm("40,000 km") == norm("40000 KM") == "40000 km"
    assert norm("Chief Executive Officer") == "chief executive officer"
    a = fingerprint("spec", "c1", "K9 Thunder", "Range", "40 km")
    assert a == fingerprint("spec", "c1", "k9  thunder", "range", "40 KM") and a != fingerprint("spec", "c1", "K9 Thunder", "Range", "41 km")
    assert fingerprint("new_product", "c1", "KAAV-II", "Armoured vehicles", "an amphibious vehicle") == \
        fingerprint("new_product", "c1", "KAAV-II", "Armoured vehicles", "a different blurb")
    assert aliases("KAAV / KAAV-II") & aliases("KAAV-II")
    assert aliases("XM1776 Mobile Tactical Cannon (K9 Mobile Howitzer, K9MH)") & aliases("K9MH")
    assert aliases("COBRA - Personnel Carrier (One Manned Turret)") & aliases("COBRA")
    assert not aliases("K9 / K9A1 Thunder") & aliases("K10 ammunition resupply vehicle")
    pt = {"JV": "Joint venture", "joint venture partner": "Joint venture", "teaming partner": "Teaming", "MoU / teaming": "Teaming",
          "licence": "Technology / ToT", "final assembly partner": "Technology / ToT", "research partner (MoU)": "MoU / strategic",
          "supplier": "Supplier", "maintenance, repair and overhaul": "Supplier", "distribution partner": "Supplier",
          "cooperation partner": "MoU / strategic", "supply": "Supplier", "MoU": "MoU / strategic"}
    for f, want in pt.items():
        assert partner_type(f) == want, (f, partner_type(f), want)
    assert partner_type("defence partner", "a 50/50 joint venture for rockets") == "Joint venture"
    assert partner_type("partner type", "signed a deal") == "Other"
    print("change_proposals self-check ok")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
