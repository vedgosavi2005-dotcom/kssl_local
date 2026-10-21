"""Import competitor product specs from the owner's spec store (spec_flow extractions served at KSSL_SPEC_STORE_URL). No model call.

    python -m backend.import_spec_store [--dry-run] [--all] [--limit N]     new / changed store pages only (state file), --all = every page
    python -m backend.import_spec_store --selftest

Per store page (the production run, /prod/pages): only the page's SUBJECT products (role 'subject'), matched to one of our catalogue
products by name AND maker (the store's maker or a listed company must be one of the competitor's name variants). A spec is written
only when it passes the same checks as prompts/spec_enrich.py: credible source (backend.sources, the maker's own site = primary), the
value as written is in its verbatim quote, the label is not generic, and the product has no spec with the same label or canonical key
(stored and Excel-verified specs are never changed or deleted). Status actual / claimed / tested / demonstrated / reported only; figures only (backend.areas.b_products.spec_kind 'quant'),
within plausible bounds; on a page with several products the quote must name the product.
Rows: staging.competitive_product_specification (spec_id = spec_enrich.spec_id, so a re-run replaces its own row) + one fact_source
row each (url, quote, tier). Owner decisions 2026-10-19: janes.com taken (the owner obtained it, not crawled); 19fortyfive.com,
military.africa and indiandefensenews.in accepted for SPECS from this store only (they stay blocked everywhere else).
TLS: the store's self-signed certificate is pinned on first use at .cache/spec_store.pem; verification stays on against that cert.
No KSSL_SPEC_STORE_URL in the environment or .env -> prints a note and exits 0 (the routine step is then a no-op).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISAGREE: list = []
SAMPLE: list = []                                      # dry run: what would be added                                    # examples printed at the end of a run
STATE = ROOT / "db" / "spec_store.state.json"          # gitignored (db/*.state.json): doc_id -> loaded_at already imported
CERT = ROOT / ".cache" / "spec_store.pem"
STATUSES = {"actual", "claimed", "tested", "demonstrated", "reported"}
STORE_ONLY_OK = ("19fortyfive.com", "military.africa", "indiandefensenews.in", "janes.com")   # owner 2026-10-19, specs from the store only
# plausibility bounds per dimension, in the parser's base units (prompts/spec_values: length mm, mass g, speed m/s)
BOUNDS = {"length": (0.01, 2e10), "mass": (0.01, 5e11), "speed": (0.001, 12000), "rate": (0, 1e5), "count": (0, 1e7)}
STOP = {"the", "and", "of", "system", "systems", "vehicle", "gun", "rifle", "new", "family", "series", "mm", "cal"}


def store_url() -> str | None:
    u = os.environ.get("KSSL_SPEC_STORE_URL")
    env = ROOT / ".env"
    if not u and env.exists():
        m = re.search(r"^KSSL_SPEC_STORE_URL=(.*)$", env.read_text(encoding="utf-8"), re.M)
        u = m and m.group(1).strip().strip("\"'")
    return (u or "").rstrip("/") or None


def tls(base: str) -> ssl.SSLContext:
    # The store's Caddy local CA issues 12-hour leaf certificates, so a pinned LEAF breaks twice a day: pin the CA instead.
    # .cache/spec_store.pem = Caddy's root (server: <caddy data>/pki/authorities/local/root.crt, 10 years) or its intermediate (7 days).
    if not CERT.exists():
        raise SystemExit(f"spec store: put the store's Caddy root certificate at {CERT} (never trust a certificate on first use)")
    ctx = ssl.create_default_context(cafile=str(CERT))
    ctx.check_hostname = False                            # the store answers on a bare IP; the pinned certificate is still verified
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN     # a self-signed leaf is its own trust anchor
    return ctx


def get(base, ctx, path):
    return json.load(urllib.request.urlopen(base + path, context=ctx, timeout=180))


# words that may differ between two names of the SAME product (descriptions, not designations). Anything else that differs -- a short
# code (TP, Mk II, ER, (E)), a number (6x6), a ship type, 'airsoft' -- means another product or variant (dry run 2026-10-19: Heron TP
# took the Heron page, I-Derby ER the Derby page, a River-class destroyer the River-class patrol vessel page, a P365 an airsoft replica).
GENERIC_EXTRA = {"vehicle", "vehicles", "protected", "mine", "armoured", "armored", "personnel", "carrier", "howitzer", "gun", "system",
                 "systems", "rifle", "carbine", "pistol", "missile", "rocket", "launcher", "truck", "uav", "drone", "aircraft", "mounted",
                 "towed", "wheeled", "tracked", "self", "propelled", "combat", "infantry", "fighting", "the", "family", "series", "weapon",
                 "unmanned", "aerial", "platform", "machine", "multi", "purpose", "mm", "cal", "calibre", "caliber", "tactical",
                 "helicopter", "maritime", "mission", "multirole", "role", "mbt", "main", "battle", "tank", "mrap", "apc", "ifv", "ugv",
                 "mortar", "drone"}
# labels that are facts about the fleet, the deal or the classification, not a measured property of the product (dry run 2026-10-19:
# 'fleet size 550', 'class: 155mm self-propelled howitzers', 'chassis: Tatra 6x6 chassis')
SKIP_LABEL = re.compile(r"\b(fleet|quantity|units?|orders?|ordered|contract|first flight|year|class|type|role|platform|chassis|variant|"
                        r"family|maker|manufacturer|operator|customer|price|cost|component)\b", re.I)
DESIGNATION = re.compile(r"\b(?=[a-z0-9-]*\d)(?=[a-z0-9-]*[a-z])[a-z0-9]+(?:-[a-z0-9]+)+\b|\b[a-z]{1,4}\d{2,}[a-z]?\b", re.I)
DESC_TOKEN = re.compile(r"^(\d+(\.\d+)?mm|\d+x\d+)$")     # a calibre (155mm) or wheel formula (8x8): descriptive, but it also tells
                                                         # variants apart, so it is accepted only when the match is unambiguous


def norm(s) -> str:
    """Lower case, punctuation to spaces; a parenthetical is dropped when it is a description (2+ words or 5+ letters) and kept when it
    is a variant code like '(E)' or '(Mk2)'."""
    s = re.sub(r"\(([^)]*)\)", lambda m: " " + m.group(1) + " " if len(m.group(1).split()) == 1 and len(m.group(1)) <= 4 else " ",
               str(s or "").casefold())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def name_match(ours: str, theirs: str) -> bool:
    """Same product: equal names, or one name inside the other where every extra word is descriptive (GENERIC_EXTRA):
    'RG21' ~ 'RG21 mine protected vehicle', 'M777' ~ 'M777 howitzer'; but NOT 'CAESAR' / 'CAESAR 6x6', 'Heron' / 'Heron TP'."""
    a, b = norm(ours), norm(theirs)
    if len(a) < 3 or len(b) < 3 or set(a.split()) <= STOP or set(b.split()) <= STOP:
        return False
    if a == b:
        return True
    if f" {a} " in f" {b} " or f" {b} " in f" {a} ":
        return all(w in GENERIC_EXTRA or DESC_TOKEN.match(w) for w in set(a.split()) ^ set(b.split()))
    return False


# the store's maker name -> our competitor(s), for parents, subsidiaries and joint ventures (owner 2026-10-19, checked one by one;
# left out on purpose: Streit Group, GM Defense, Longbow, HavocAI, ZALA, Milkor, Roboteam -- other makers of a same-named product)
MAKER_ALIASES = {
    "kraussmaffeiwegmann": ["KNDS Germany"], "kmw": ["KNDS Germany"], "kndsdeutschland": ["KNDS Germany"],
    "kmwrheinmetall": ["KNDS Germany", "Rheinmetall"], "psm": ["KNDS Germany", "Rheinmetall"],
    "artec": ["Rheinmetall", "KNDS Germany"], "artecgmbh": ["Rheinmetall", "KNDS Germany"],
    "kndsfrance": ["Nexter (KNDS France)"], "nexter": ["Nexter (KNDS France)"], "nextersystems": ["Nexter (KNDS France)"],
    "sikorsky": ["Lockheed Martin"], "sikorskyaircraftcorporation": ["Lockheed Martin"], "sikorskyaircraft": ["Lockheed Martin"],
    "mowag": ["General Dynamics"], "mowaggmbh": ["General Dynamics"], "gdels": ["General Dynamics"], "forceprotection": ["General Dynamics"],
    "eurosam": ["MBDA"], "hanwhadefense": ["Hanwha Aerospace"], "hanwhadefence": ["Hanwha Aerospace"],
    "arcturusuav": ["AeroVironment"], "areai": ["Anduril"], "malloyaeronautics": ["BAE Systems"],
    "tatamotors": ["Tata Advanced Systems"], "thales": ["SAAB"], "defenceresearchanddevelopmentorganisation": ["Bharat Dynamics Ltd (BDL)"],
    "drdo": ["Bharat Dynamics Ltd (BDL)"], "bmc": ["Otokar"], "aeronautics": ["Mahindra Defence", "Rafael Advanced Defense Systems"],
    "aeronauticsltd": ["Mahindra Defence", "Rafael Advanced Defense Systems"], "aeronauticsgroup": ["Mahindra Defence", "Rafael Advanced Defense Systems"],
    "otomelara": ["Leonardo"], "leonardodrs": ["Leonardo"], "leonardospa": ["Leonardo"],          # 2026-10-21: Leonardo / TKMS products loaded
    "tkms": ["Thyssenkrupp Marine Systems"], "thyssenkrupp": ["Thyssenkrupp Marine Systems"], "atlaselektronik": ["Thyssenkrupp Marine Systems"],
    "hydroid": ["Huntington Ingalls Industries"], "hii": ["Huntington Ingalls Industries"],
    "jscconcernkalashnikov": ["Kalashnikov Concern"], "concernkalashnikov": ["Kalashnikov Concern"], "oshkoshdefence": ["Oshkosh Defense"],
}


def _co(x: str) -> str:
    """compact company name with '&' / 'and' dropped ('Adani Defence and Aerospace' = 'Adani Defence & Aerospace')."""
    from prompts.loader import compact_name
    return compact_name(re.sub(r"&|\band\b", " ", str(x or ""), flags=re.I))


def maker_match(variants: set, maker, companies) -> bool:
    from backend.excel_load import name_variants
    raw = [x for x in [maker, *[c.get("name") for c in companies or [] if isinstance(c, dict)]] if x]
    names = {_co(x) for x in raw} | {_co(re.sub(r"\(.*?\)", " ", x)) for x in raw} | {_co(i) for x in raw for i in re.findall(r"\((.*?)\)", x)}
    names.discard("")
    for x in list(names):
        for ours in MAKER_ALIASES.get(x, []):
            names |= {_co(v) for v in name_variants(ours)} | {_co(ours)}
    variants = {_co(v) for v in variants} | set(variants)
    return any(v and n and (v == n or (min(len(v), len(n)) >= 4 and (v in n or n in v))) for v in variants for n in names)


def tier_of(url: str, maker_variants: set) -> str | None:
    from backend.excel_load import company_domains
    from backend.sources import classify, host_of
    t = classify(url, company_domains(url, maker_variants))
    if t:
        return t
    host = host_of(url)
    return "independent" if any(host == d or host.endswith("." + d) for d in STORE_ONLY_OK) else None


def plausible(value: str) -> bool:
    """A parsed figure inside the dimension's bounds, low <= high; text that does not parse as a figure is not judged here."""
    from prompts.spec_values import parse_value
    try:
        p = parse_value(value)
    except Exception:
        return True
    if p is None or p.dim not in BOUNDS:
        return True
    lo, hi = BOUNDS[p.dim]
    a, b = float(p.lo * p.factor), float(p.hi * p.factor)
    return a <= b and lo <= a and b <= hi


def about_other(product: str, quote: str) -> bool:
    """The quote names another item's designation (AGM-114R, T700-GE-401C), whether or not it also names this product: the figure may
    be that item's (dry run: 'MH-60R range 0.5-11 km' was the Hellfire's). Strict on purpose; such a figure is dropped."""
    own = norm(product).replace(" ", "")                    # 'MH-60R Seahawk' -> 'mh60rseahawk': its own designation is not another item
    return any(d and d not in own for d in (norm(x).replace(" ", "") for x in DESIGNATION.findall(quote)))


def named_in(product: str, quote: str) -> bool:
    """The quote names the product: one of its distinctive words (a designation with a digit first, else any non-generic word)."""
    words = [w for w in norm(product).split() if w not in STOP and len(w) >= 2]
    q = f" {norm(quote)} "
    key = [w for w in words if re.search(r"\d", w)] or words
    return any(f" {w} " in q for w in key)


def agree(ours: str, theirs: str):
    """True / False when both parse as figures of the same dimension (overlap within 5 %), None when they cannot be compared."""
    from prompts.spec_values import parse_value
    try:
        a, b = parse_value(ours), parse_value(theirs)
    except Exception:
        return None
    if not a or not b or a.dim != b.dim or a.dim.startswith("other"):
        return None
    alo, ahi, blo, bhi = (float(x) for x in (a.lo * a.factor, a.hi * a.factor, b.lo * b.factor, b.hi * b.factor))
    return blo <= ahi * 1.05 and alo <= bhi * 1.05


RANGE_KIND = re.compile(r"\b(road|cruising|operating|operational|driving|fuel|endurance|combat radius|ferry)\b", re.I)


def range_label_ok(label: str, quote: str) -> bool:
    """A 'range' figure whose quote speaks of road / cruising / operating range keeps that word in its label; otherwise it could be read
    as a firing range in a comparison (dry run: KRAB 'maximum range 650 km' was the road range)."""
    if "range" not in label.lower():
        return True
    kinds = {m.lower() for m in RANGE_KIND.findall(quote)}
    lab = label.lower()
    vehicle = {"road", "cruising", "operating", "operational", "driving", "fuel"}      # one meaning: how far the vehicle travels
    if kinds & vehicle and any(w in lab for w in vehicle):
        return True
    return not kinds or any(k in lab for k in kinds)


def candidates(specs, stats=None) -> list:
    from backend.areas.b_products import spec_kind
    from prompts.spec_enrich import GENERIC_LABELS, norm_label, value_in_quote
    out = []
    st = stats if stats is not None else {}
    for s in specs or []:
        label = " ".join(str(s.get("parameter") or "").replace("_", " ").split())
        value = " ".join(str(s.get("value_text") or "").split())
        quote = " ".join(str((s.get("evidence") or {}).get("quote") or "").split())
        if not label or not value or not quote or len(label) > 150 or norm_label(label) in GENERIC_LABELS:
            continue
        if s.get("flags"):                                   # the store's own doubt (no_evidence)
            st["store_flagged"] = st.get("store_flagged", 0) + 1
            continue
        if str(s.get("status") or "").lower() not in STATUSES:
            st["status_not_stated_fact"] = st.get("status_not_stated_fact", 0) + 1
            continue
        if not value_in_quote(value, quote):
            st["value_not_in_quote"] = st.get("value_not_in_quote", 0) + 1
            continue
        if not plausible(value):
            st["implausible_figure"] = st.get("implausible_figure", 0) + 1
            continue
        if not range_label_ok(label, quote):
            st["range_label_unclear"] = st.get("range_label_unclear", 0) + 1
            continue
        if SKIP_LABEL.search(label):
            st["not_a_product_property"] = st.get("not_a_product_property", 0) + 1
            continue
        if spec_kind(label, value, None)[0] != "quant":     # figures only (the spec table's own rule): descriptive lines are noise here
            st["not_a_figure"] = st.get("not_a_figure", 0) + 1
            continue
        unit = ((s.get("value") or {}).get("unit") or None) if isinstance(s.get("value"), dict) else None
        out.append({"label": label, "value": value, "unit": unit and str(unit)[:40], "quote": quote[:300],
                    "stated_by": ((s.get("stated_by") or {}).get("name") or None)})
    return out


def catalogue(cur) -> list:
    from backend.excel_load import name_variants
    cur.execute("""SELECT p.product_id::text AS pid, p.product_name, p.category, c.display_name, c.short_name
                   FROM staging.competitive_product p JOIN staging.competitive_competitor c USING (competitor_id)""")
    rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["variants"] = name_variants(r["display_name"]) | (name_variants(r["short_name"]) if r["short_name"] else set())
    return rows


def import_page(cur, page: dict, cat: list, tok: dict, dry_run: bool, stats: dict) -> None:
    from prompts.spec_enrich import norm_label, spec_id
    url = page["url"]
    prods = (page.get("data") or {}).get("products") or []
    multi = sum(1 for x in prods if x.get("role") == "subject") > 1 or (page.get("level") or 1) >= 2
    for prod in prods:
        if prod.get("role") != "subject":
            continue
        pool = set()
        for w in set(norm(prod.get("product")).split()) - STOP:
            pool |= tok.get(w, set())
        hits = [o for i in pool for o in [cat[i]] if name_match(o["product_name"], prod.get("product"))
                and maker_match(o["variants"], prod.get("maker"), prod.get("companies"))]
        if not hits and not (prod.get("maker") or "").strip() and not prod.get("companies"):
            named = [cat[i] for i in pool if name_match(cat[i]["product_name"], prod.get("product"))]
            if len(named) == 1 and len(norm(prod.get("product"))) >= 4:   # no maker given: a name that fits ONE product in our catalogue
                hits = named
                stats["matched_without_maker"] += 1
        if not hits:
            stats["subject_unmatched"] += 1
            continue
        exact = [o for o in hits if norm(o["product_name"]) == norm(prod.get("product"))]
        if exact:
            hits = exact
        elif len(hits) > 1:                                 # 'Caesar' fits CAESAR 6x6, 8x8, MK2 ... of one maker: which one is unknown
            stats["ambiguous_name"] += 1
            continue
        specs = candidates(prod.get("specs"), stats)
        other = [x for x in specs if about_other(prod.get("product"), x["quote"])]
        stats["quote_about_other_item"] += len(other)
        specs = [x for x in specs if x not in other]
        if multi:                                           # several subjects on the page: the quote must name this product
            kept = [x for x in specs if named_in(prod.get("product"), x["quote"])]
            stats["product_not_in_quote"] += len(specs) - len(kept)
            specs = kept
        for o in hits:
            tier = tier_of(url, o["variants"])
            if not tier:
                stats["source_not_credible"] += 1
                continue
            stats["products_matched"] += 1
            cur.execute("""SELECT s.spec_label, s.spec_value, EXISTS (SELECT 1 FROM staging.fact_source f WHERE f.table_name = 'competitive_product_specification'
                                  AND f.row_id = s.spec_id::text AND f.document_id LIKE 'spec_store:%%') AS from_store
                           FROM staging.competitive_product_specification s WHERE s.product_id = %s""", (o["pid"],))
            stored = cur.fetchall()
            have = {norm_label(r["spec_label"]) for r in stored}
            cur.execute("SELECT raw_label_norm, canonical_key FROM staging.spec_dictionary WHERE lower(category) = lower(%s)", (o["category"] or "",))
            canon = {r["raw_label_norm"]: r["canonical_key"] for r in cur.fetchall()}
            have_keys = {canon[l] for l in have if l in canon}
            by_key = {}
            for r in stored:                                  # our stored value per label / canonical key, for the agreement check
                if r["from_store"]:                           # never compare the store with itself
                    continue
                k = canon.get(norm_label(r["spec_label"])) or norm_label(r["spec_label"])
                by_key.setdefault(k, r["spec_value"])
            added = 0
            for s in specs:
                nl, key = norm_label(s["label"]), canon.get(norm_label(s["label"]))
                if nl in have or (key and key in have_keys):
                    stats["already_have"] += 1
                    ok = agree(by_key.get(key or nl) or "", s["value"])   # how often the store agrees with what we already hold
                    if ok is not None:
                        stats["agree" if ok else "disagree"] += 1
                        if not ok and len(DISAGREE) < 40:
                            DISAGREE.append((o["product_name"][:40], s["label"][:30], (by_key.get(key or nl) or "")[:40], s["value"][:40], url[:70]))
                    continue
                have.add(nl)
                if key:
                    have_keys.add(key)
                added += 1
                if dry_run:
                    SAMPLE.append((o["product_name"][:40], s["label"][:35], s["value"][:40], s["quote"][:90], url[:60]))
                    continue
                sid = spec_id(o["pid"], s["label"])
                cur.execute("DELETE FROM staging.competitive_product_specification WHERE spec_id = %s", (sid,))
                cur.execute("""INSERT INTO staging.competitive_product_specification (spec_id, product_id, spec_label, spec_value, unit, source_url, source_count)
                               VALUES (%s, %s, %s, %s, %s, %s, 1)""", (sid, o["pid"], s["label"][:150], s["value"], s["unit"], url))
                cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_product_specification' AND row_id = %s", (sid,))
                cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, document_id, retrieved_at)
                               VALUES ('competitive_product_specification', %s, 'spec_value', %s, %s, %s, %s, %s, now())""",
                            (sid, url, tier, s["stated_by"], s["quote"], "spec_store:" + page["doc_id"]))
            stats["specs_added"] += added
            stats["products_gained"] += bool(added)


def run(dry_run=False, everything=False, limit=None) -> int:
    from backend.sources import is_blocked, host_of
    base = store_url()
    if not base:
        print("spec store: KSSL_SPEC_STORE_URL not set, nothing to do")
        return 0
    ctx = tls(base)
    state = {} if everything or not STATE.exists() else json.loads(STATE.read_text(encoding="utf-8"))
    pages, off = [], 0
    while True:
        d = get(base, ctx, f"/prod/pages?limit=200&offset={off}")
        pages += d["pages"]
        off += 200
        if off >= d["total"]:
            break
    todo = [p for p in pages if state.get(p["doc_id"]) != p["loaded_at"]
            and (not is_blocked(p["url"]) or any(host_of(p["url"]).endswith(x) for x in STORE_ONLY_OK))]
    todo = sorted(todo, key=lambda p: (p.get("level") or 9, p["doc_id"]))   # single-product pages first: they win a label
    todo = todo[:limit] if limit else todo
    from prompts.run import connect
    conn = connect()
    stats = {k: 0 for k in ("pages", "products_matched", "products_gained", "specs_added", "already_have", "agree", "disagree",
                            "subject_unmatched", "ambiguous_name", "matched_without_maker", "source_not_credible", "product_not_in_quote",
                            "quote_about_other_item")}
    with conn.cursor() as cur:
        cat = catalogue(cur)
        tok: dict = {}
        for i, o in enumerate(cat):
            for w in set(norm(o["product_name"]).split()) - STOP:
                tok.setdefault(w, set()).add(i)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as ex:                   # fetch in parallel, import in order
          for n, (p, page) in enumerate(zip(todo, ex.map(lambda x: get(base, ctx, "/prod/pages/" + x["doc_id"]), todo)), 1):
            import_page(cur, page, cat, tok, dry_run, stats)
            stats["pages"] += 1
            state[p["doc_id"]] = p["loaded_at"]
            if not dry_run and n % 200 == 0:                # commit in steps: a long first run keeps what it did
                conn.commit()
                STATE.write_text(json.dumps(state), encoding="utf-8")
                print(f"  {n}/{len(todo)} pages, {stats['specs_added']} specs added", flush=True)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
        STATE.write_text(json.dumps(state), encoding="utf-8")
    print(("dry run: " if dry_run else "") + f"spec store: {len(pages)} store pages, {len(todo)} new or changed read; " + json.dumps(stats))
    if stats["agree"] + stats["disagree"]:
        print(f"agreement with values we already hold: {100 * stats['agree'] / (stats['agree'] + stats['disagree']):.1f}% of {stats['agree'] + stats['disagree']} comparable")
    for x in DISAGREE[:15]:
        print("  differs:", x)
    if dry_run and SAMPLE:
        import random
        random.seed(11)
        for x in random.sample(SAMPLE, min(25, len(SAMPLE))):
            print("  would add:", x)
    return 0


def _selftest() -> None:
    assert name_match("RG21 (mine-protected vehicle)", "RG21") and name_match("M777", "M777 howitzer")
    assert name_match("CAESAR 6x6", "CAESAR") and name_match("CAESAR 8x8 (155mm/52-cal)", "CAESAR 8x8")
    assert not name_match("Maverick", "Gun") and not name_match("Gun System", "System")
    assert not name_match("Heron TP", "Heron") and not name_match("Heron MK II", "Heron") and not name_match("I-Derby ER", "Derby")
    assert not name_match("Jackal 3(E) (Jackal 3 Extenda, six-wheel)", "Jackal 3") and not name_match("River-class destroyer (Canada)", "River class")
    assert about_other("MH-60R Seahawk", "The AGM-114R weighs 108 lb (49 kg) and has a range between 0.5 and 11 km")
    assert about_other("MH-60R Seahawk", "The MH-60R carries the AGM-114R") and not about_other("Jaguar", "It reaches 90 km/h on roads")
    assert not about_other("PzH 2000", "The PzH 2000 weighs 55 t") and not about_other("MH-60R Seahawk", "The MH-60R cruises at 270 km/h")
    assert not range_label_ok("maximum range", "The vehicle has a maximum road range of 650km") and range_label_ok("road range", "road range of 650 km")
    assert range_label_ok("maximum range", "It fires to a maximum range of 40 km") and range_label_ok("weight", "road weight")
    assert range_label_ok("operational range km", "a maximum road range of 800 km") and not range_label_ok("Range", "a maximum cruising range of 426 km")
    assert SKIP_LABEL.search("fleet size") and SKIP_LABEL.search("chassis") and not SKIP_LABEL.search("combat weight")
    assert name_match("PLZ-45", "PLZ-45 155mm self-propelled howitzer") and name_match("VN1 (ZBL-09 export) 8x8 wheeled armoured vehicle", "VN1")
    assert name_match("MH-60R SEAHAWK multi-mission maritime helicopter", "MH-60R Seahawk") and not name_match("Piranha III", "PIRANHA")
    assert not name_match("P365 (LE/concealed-carry micro-compact)", "ProForce P365 Airsoft Pistol") and name_match("Jackal 3(E)", "Jackal 3 (E)")
    assert maker_match({"bae", "baesystems"}, "BAE Systems", []) and not maker_match({"elbit"}, "Rafael", [{"name": "IAI"}])
    from backend.excel_load import name_variants as nv
    assert maker_match(nv("KNDS Germany"), "Krauss-Maffei Wegmann (KMW)", []) and maker_match(nv("Lockheed Martin"), "Sikorsky", [])
    assert maker_match(nv("Adani Defence & Aerospace"), "Adani Defence and Aerospace", []) and not maker_match(nv("Otokar"), "Streit Group", [])
    c = candidates([{"parameter": "combat weight", "value_text": "13,800kg", "status": "actual", "value": {"unit": "kg"},
                     "evidence": {"quote": "The combat weight is 13,800kg, while the payload is 5,200kg."}, "stated_by": {"name": "Army Technology"}},
                    {"parameter": "range", "value_text": "150km+", "status": "expected", "evidence": {"quote": "range 150km+"}},
                    {"parameter": "Note", "value_text": "x", "status": "actual", "evidence": {"quote": "x"}},
                    {"parameter": "speed", "value_text": "110 km/h", "status": "claimed", "evidence": {"quote": "it can reach 120 km/h"}}])
    assert [x["label"] for x in c] == ["combat weight"] and c[0]["unit"] == "kg"
    assert plausible("110 km/h") and not plausible("50000 km/h") and plausible("Mine-protected vehicle") and not plausible("-5 kg")
    assert named_in("K9A1 Thunder", "The K9A1 has a range of 40 km") and not named_in("K9A1 Thunder", "The howitzer fires 6 rounds")
    assert agree("48 km", "48,000 m") is True and agree("48 km", "30 km") is False and agree("48 km", "13,800kg") is None
    print("import_spec_store self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="re-read every store page, not only new / changed ones")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    return run(a.dry_run, a.all, a.limit)


if __name__ == "__main__":
    sys.exit(main())
