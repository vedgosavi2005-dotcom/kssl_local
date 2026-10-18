"""Handler of prompts/spec_enrich.yml: ADD specs a competitor product is missing, each one proven by a source document.

    python -m prompts.spec_enrich --selftest         pure checks, fictional values

A spec the model lists is written only if ALL of these hold (otherwise it is dropped and counted in the run's details):
  * its source_url is a harvested document in staging.source_document that is attributed to the product's competitor;
  * the url is not a blocked source (wiki, blog, forum, social media, wire / aggregator ...);
  * the source is credible (v2, user rule 2026-10-18): backend.sources.classify with the maker's own domains is primary / independent, or
    backend/harvest_specs.py stored it as such, or the DC corpus tiers it A_ (official). An unlisted site is dropped, never written;
  * its quote is found in that document's text (whitespace and case folded, quote marks and dashes normalised);
  * the value, as written, is found in the quote;
  * the product has no spec with the same normalised label, and none whose canonical key (staging.spec_dictionary, per category) is the
    key of the new label -- stored specs, the client's Excel-verified ones included, are NEVER changed or deleted;
  * the label is not a generic placeholder (Note, Notes, Other, Description ...).
Written rows: staging.competitive_product_specification (spec_id = uuid5 of product + label, so a re-run never duplicates) and one
staging.fact_source row each (the url, the quote, tier primary / independent / unlisted). Same Result shape as prompts/news_merge.apply.
"""

from __future__ import annotations

import re
import sys
import uuid
from dataclasses import dataclass, field

MAX_PER_PRODUCT = 12
GENERIC_LABELS = {"note", "notes", "other", "description", "details", "remarks", "comment", "comments", "info", "information", "misc", "general"}


@dataclass
class Result:
    rows: int = 0
    loaded: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    skip_reason: str | None = None
    note: str = ""
    details: dict = field(default_factory=dict)


def norm_text(t) -> str:
    t = str(t or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-").replace(" ", " ")
    return " ".join(t.casefold().split())


def norm_label(s) -> str:
    return " ".join(re.sub(r"[^\w\s]|_", " ", str(s or "").casefold()).split())


def value_in_quote(value, quote) -> bool:
    """The value as written appears in the quote (after folding); a purely numeric value must match on a number boundary."""
    v, q = norm_text(value), norm_text(quote)
    if not v:
        return False
    if re.fullmatch(r"[\d.,]+", v):
        return re.search(r"(?<![\d.,])" + re.escape(v) + r"(?![\d])", q) is not None
    return v in q


def quote_in_doc(quote, body) -> bool:
    parts = [p for p in re.split(r"\.\.\.|…", str(quote or "")) if len(p.strip()) > 8]
    dehyph = lambda t: re.sub(r"(?<=\w)- (?=\w)", "-", t)          # a PDF line break inside a hyphenated word (up- / gunning)
    b = dehyph(norm_text(body))
    return bool(parts) and all(dehyph(norm_text(p)) in b for p in parts)


def clean(env: dict, table: str = "competitive_product_specification") -> tuple[list, list]:
    """(candidate specs, problems) from the envelope: label / value / unit / url / quote, whitespace folded, over-long labels cut out."""
    out, problems = [], []
    for r in env.get("records") or []:
        if not isinstance(r, dict) or r.get("table") != table:
            continue
        v = r.get("values") or {}
        label = " ".join(str(v.get("spec_label") or "").split())
        value = " ".join(str(v.get("spec_value") or "").split())
        unit = " ".join(str(v.get("unit") or "").split())
        url = str(v.get("source_url") or "").strip()
        quote = " ".join(str(v.get("quote") or (((v.get("_sources") or {}).get("spec_value") or [{}])[0].get("quote")) or "").split())
        if not label or not value or not url or not quote:
            problems.append(f"incomplete spec dropped: {label or '?'}")
        elif len(label) > 150:
            problems.append(f"label over 150 characters dropped: {label[:40]}")
        elif norm_label(label) in GENERIC_LABELS:
            problems.append(f"generic label dropped: {label}")
        else:
            out.append({"label": label, "value": value, "unit": unit[:40] or None, "url": url, "quote": quote[:300]})
    return out[:MAX_PER_PRODUCT], problems


def credible_tier(url, doc: dict, company_domains=(), client=False) -> str | None:
    """primary / independent, or None: the source may not back a spec."""
    from backend.sources import classify
    if doc.get("source_kind") == "spec_page" and doc.get("source_tier") in ("primary", "independent"):
        return doc["source_tier"]                   # backend/harvest_specs.py classified it with the maker's real domains
    return classify(url, company_domains, client) or ("primary" if (doc.get("tier") or "").startswith("A_") else None)


def spec_id(product_id, label) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kssl-spec|{product_id}|{norm_label(label)}"))


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    from prompts.derive_comp import blocked_url
    res = Result()
    pid, cid = str(subject["product_id"]), str(subject["competitor_id"])
    specs, problems = clean(env)
    res.warnings += problems
    if not specs:
        res.skip_reason = (env.get("skip_reason") or "no new specification found in the documents")[:300] if not env.get("records") else None
        return res
    cur.execute("SELECT spec_label FROM staging.competitive_product_specification WHERE product_id = %s", (pid,))
    have = {norm_label(r["spec_label"]) for r in cur.fetchall()}
    category = subject.get("category") or ""
    cur.execute("SELECT raw_label_norm, canonical_key FROM staging.spec_dictionary WHERE lower(category) = lower(%s)", (category,))
    canon = {r["raw_label_norm"]: r["canonical_key"] for r in cur.fetchall()}
    have_keys = {canon[l] for l in have if l in canon}
    docs: dict = {}
    dropped = {"not_a_document": 0, "blocked": 0, "not_credible": 0, "quote_missing": 0, "value_not_in_quote": 0, "already_have": 0}
    from backend.excel_load import company_domains, name_variants
    maker = name_variants(subject.get("competitor") or "")
    seen_new: set = set()
    for s in specs:
        url = s["url"]
        if url not in docs:
            cur.execute("SELECT body_text, title, source_name, triage->>'dc_source_tier' AS tier, source_kind, source_tier FROM staging.source_document "
                        "WHERE url = %s AND %s::uuid = ANY(competitor_ids)", (url, cid))
            row = cur.fetchone()
            docs[url] = dict(row) if row else None
        doc = docs[url]
        nl = norm_label(s["label"])
        if doc is None:
            dropped["not_a_document"] += 1
            continue
        if blocked_url(url):
            dropped["blocked"] += 1
            continue
        tier = credible_tier(url, doc, company_domains(url, maker))
        if not tier:
            dropped["not_credible"] += 1
            continue
        if not quote_in_doc(s["quote"], doc["body_text"]):
            dropped["quote_missing"] += 1
            continue
        if not value_in_quote(s["value"], s["quote"]):
            dropped["value_not_in_quote"] += 1
            continue
        key = canon.get(nl)
        if nl in have or nl in seen_new or (key and key in have_keys):
            dropped["already_have"] += 1
            continue
        seen_new.add(nl)
        if key:
            have_keys.add(key)
        sid = spec_id(pid, s["label"])
        if dry_run:
            res.loaded.append(("competitive_product_specification", sid, False))
            continue
        cur.execute("DELETE FROM staging.competitive_product_specification WHERE spec_id = %s", (sid,))      # no unique index on spec_id: a re-run replaces its own row
        cur.execute("""INSERT INTO staging.competitive_product_specification (spec_id, product_id, spec_label, spec_value, unit, source_url, source_count)
                       VALUES (%s,%s,%s,%s,%s,%s,1)""", (sid, pid, s["label"][:150], s["value"], s["unit"], url))
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_product_specification' AND row_id = %s", (sid,))
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote)
                       VALUES ('competitive_product_specification', %s, 'spec_value', %s, %s, %s, %s)""",
                    (sid, url, tier, doc.get("source_name"), s["quote"]))
        res.loaded.append(("competitive_product_specification", sid, False))
    res.rows = len(res.loaded)
    res.details = {"offered": len(specs), "added": res.rows, "dropped": {k: v for k, v in dropped.items() if v}}
    res.note = f"{res.rows} of {len(specs)} specs added" + (f" (dropped: {res.details['dropped']})" if res.details["dropped"] else "")
    if not res.rows and not res.skip_reason:
        res.skip_reason = f"none of the {len(specs)} specs passed the checks: {res.details['dropped']}"
    return res


def _selftest() -> None:
    assert norm_label("Maximum range (HE round)") == "maximum range he round" and norm_label("Note") in GENERIC_LABELS
    assert value_in_quote("30 km", "Maximum range of 30 KM with a plain round.") and not value_in_quote("3", "Range 30 km")
    assert value_in_quote("3", "Weight is 3 kg.") and not value_in_quote("40 km", "Range 30 km")
    assert quote_in_doc("range of 30 km", "The  Range of 30 km is reached.") and not quote_in_doc("range of 40 km", "The range of 30 km")
    assert quote_in_doc("first part of the sentence ... last part of it", "The first part of the sentence and then the last part of it.")
    assert quote_in_doc("by up-gunning the existing gun", "by up-\ngunning the existing gun") and not quote_in_doc("by upgunning the gun", "by up-\ngunning the gun")
    assert spec_id("p1", "Range") == spec_id("p1", " range ") != spec_id("p2", "Range")
    env = {"records": [{"table": "competitive_product_specification", "values": {"spec_label": "Range", "spec_value": "30 km", "unit": "km",
                                                                                 "source_url": "https://x.test/a", "quote": "Range 30 km"}},
                       {"table": "competitive_product_specification", "values": {"spec_label": "Note", "spec_value": "x", "source_url": "u", "quote": "q"}},
                       {"table": "competitive_product_specification", "values": {"spec_label": "Weight", "spec_value": "", "source_url": "u", "quote": "q"}}]}
    got, probs = clean(env)
    assert len(got) == 1 and got[0]["label"] == "Range" and len(probs) == 2
    assert credible_tier("https://en.wikipedia.org/wiki/X", {}) is None and credible_tier("https://modernfirearms.net/x", {}) is None
    assert credible_tier("https://www.janes.com/x", {}) == "independent" and credible_tier("https://roshel.com/p", {}, ("roshel.com",)) == "primary"
    assert credible_tier("https://gdots.com/p", {"source_kind": "spec_page", "source_tier": "primary"}) == "primary"
    print("spec_enrich self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
