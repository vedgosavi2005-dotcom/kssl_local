"""Load a third-party KSSL spec workbook line by line -- only what its own sources state (owner 2026-10-22).

    python -m scripts.load_spec_workbook <workbook.xlsx> <recheck_out.xlsx>            (dry run)
    python -m scripts.load_spec_workbook <workbook.xlsx> <recheck_out.xlsx> --write

The workbook ('Master Database': Category | Product | Specifications | Features | Sources) lists sources per PRODUCT, not per
line, and part of it came from an AI-merged workbook. So every bullet is checked against the product's own pages:
  - a page counts only when backend/sources.py accepts it (KSSL / partner sites, government, listed trade press);
  - the line is taken when one page states it: every number in the value, and most of its words; the sentence that
    contains it becomes the fact_source quote;
  - a line the KSSL product already has (same label, or all its numbers already in the product's specs) is not repeated;
  - a product that maps to no single KSSL product is not guessed (it goes to the recheck sheet), except the two the
    workbook adds as new products (NEW_PRODUCTS).
Everything not taken goes to the recheck workbook with the reason and the sources the workbook gave.
Rows are written like prompts/client_spec_enrich.py (deterministic ids, client_product_source, fact_source per value).
"""
from __future__ import annotations

import os
import re
import sys
import time
import unicodedata

import openpyxl
import psycopg2
import psycopg2.extras

from backend.excel_load import client_id_for, publisher_of, spec_group
from backend.news import http, page_blocked
from backend.sources import classify_reason
from prompts.render import page_text

URL = re.compile(r"https?://[^\s,;)\]]+")
PARTNER_DOMAINS = ("arsenal-bg.com", "paramountgroup.com", "fnherstal.com")
SOURCE_TYPE = {"primary": "official", "independent": "trade_press", "listed": "trade_press"}
TAG = "workbook-2026-10-22"
# workbook product (prefix) -> a substring that names exactly ONE KSSL product in staging.client_product
MAP = {"ATAGS": "ATAGS 155", "Bharat 45": "Bharat 45", "Bharat 52": "Bharat 52", "Bharat ULH": "Bharat ULH", "Garuda": "Garuda",
       "MaRG 155-BR": "(BR)", "MaRG 39": "(BR)", "MaRG 45": "MArG 155 mm/45", "MaRG 52": "MArG 155 mm/52", "MaRG ER": "MAG-ER",
       "High Explosive": "Ready-to-fill shells 70", "Illuminating": "Ready-to-fill shells 70", "Incendiary": "Ready-to-fill shells 70",
       "Smoke Artillery": "Ready-to-fill shells 70", "Assault Rifle": "Arsenal JSCo", "Light Machine Gun": "Arsenal JSCo",
       "CQB Carbine": "F90 CQB", "Protective Carbine": "Protective Carbine", "Armoured Personnel": "Armoured Personnel Carrier",
       "Armoured Troops": "Armoured Troops Carrier", "Kalyani M4": "Kalyani M4", "Kalyani Maverick": "Maverick",
       "Light Bullet": "Light Bullet", "Light Tactical": "Light Tactical", "Mine Protected": "Mine Protected", "Simha": "Simha",
       "Ultra-Light Strike": "Ultra-Light Strike", "Driveline": "Driveline (gearbox)", "MRO —": "MRO of all",
       "Ordnance": "Ordnance (barrels", "Powertrain": "Powertrain (", "Running Gear": "Running Gear (", "CSTG": "(CSTG)",
       "EUT": "(EUT)", "Mechanical Products": "Marine Mechanical", "Naval Guns": "Naval Guns", "PSI": "(PSI)", "UMHT": "(UMHT)",
       "Bharat 150": "Bharat 150", "ECARS": "E-CARS"}
NEW_PRODUCTS = {"High Mobility Reconnaissance Vehicle": ("High Mobility Reconnaissance Vehicle (HMRV)", "Protected & Armoured Vehicles"),
                "MaRG TC-20": ("MArG TC-20", "Artillery")}
NOT_MAPPED = {"Sniper Rifles": "the workbook merges six T-5000M calibres in one row: a line cannot be placed on one rifle"}


def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    for a, b in (("×", "x"), ("–", "-"), ("—", "-"), ("’", "'")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s)


def bullets(t):
    for line in str(t or "").split("\n"):
        b = line.strip().lstrip("•").strip()
        if b and not re.fullmatch(r"[•—\-–\s]+", b) and not b.endswith(":"):
            yield b


def split_line(kind, b):
    """'Label: value — commentary' -> (label, value); the workbook's own commentary after ' — ' is not a stated value."""
    if ":" in b and len(b.split(":", 1)[0]) <= 80:
        lab, val = (x.strip() for x in b.split(":", 1))
    else:
        lab, val = ("Capability" if kind == "feature" else "Specification"), b
    val = re.split(r"\s+[—–]\s+", val, maxsplit=1)[0].strip()
    return lab[:150], val


NUM = re.compile(r"\d+(?:[.,]\d+)?")
STOP = {"with", "from", "that", "this", "upto", "publicly", "stated", "reported", "approx", "about"}


WINDOW = 300     # the value's numbers and words must sit together: pages often have no sentence punctuation at all
UNIT = re.compile(r"\s*(km/h|kmph|kph|km|mm|cm|kg|tonnes?|tons?|t\b|hp|kw|nm|%|°|deg|rounds?|rpm|litres?|l\b|m/s|knots?|kn\b|m\b|s\b|min\b|v\b|ah\b|kwh)", re.I)
UNIT_SAME = {"kmph": "km/h", "kph": "km/h", "tonne": "t", "tonnes": "t", "ton": "t", "tons": "t", "litre": "l", "litres": "l",
             "deg": "°", "round": "rounds", "knot": "kn", "knots": "kn"}


def _unit_after(text, start):
    m = UNIT.match(text, start)
    return UNIT_SAME.get(m.group(1).lower(), m.group(1).lower()) if m else None


def _unit_before(text, start, unit):
    """A spec table puts the unit in the label column: 'sighting range m 800', 'rate rounds/min ... single fire up to 40'."""
    head = text[max(0, start - 60):start]
    return any(_unit_after(head, i) == unit for i in range(len(head)) if head[i - 1:i] in (" ", "(", "[", "") or i == 0)


def evidence(value, page, label=""):
    """The passage of `page` (<= WINDOW chars around an anchor) that states `value`, else None. It must hold every number (with
    the same unit right after the first one, when the value gives a unit), most of the value's words (70% with numbers, 80%
    without; at least two words when there is no number) and half of the label's words (a bare '70%' is not a gradeability)."""
    v = norm(value)
    nums = [n.replace(",", "") for n in NUM.findall(v)]
    words = [w for w in dict.fromkeys(re.findall(r"[a-z][a-z\-]{3,}", v)) if w not in STOP]
    lwords = [w for w in dict.fromkeys(re.findall(r"[a-z][a-z\-]{3,}", norm(label))) if w not in STOP | {"capability", "specification"}]
    if not nums and len(words) < 2:
        return None
    unit = None
    if nums:
        m0 = NUM.search(v)
        unit = _unit_after(v, m0.end())
    flat = page.replace(",", "")
    anchor = re.escape(nums[0]) if nums else re.escape(min(words, key=lambda w: flat.count(w) or 10**9))
    for m in re.finditer(r"(?<![\d.])" + anchor + (r"(?!\d)" if nums else ""), flat):
        if unit and _unit_after(flat, m.end()) != unit and not _unit_before(flat, m.start(), unit):
            continue
        win = flat[max(0, m.start() - WINDOW // 2): m.end() + WINDOW // 2]
        if nums and not all(re.search(r"(?<![\d.])" + re.escape(n) + r"(?!\d)", win) for n in nums):
            continue
        if words and sum(w in win for w in words) / len(words) < (0.7 if nums else 0.9):
            continue
        if lwords and sum(w in win for w in lwords) / len(lwords) < 0.5:
            continue
        return re.sub(r"\s+", " ", win).strip()
    return None


_cache: dict = {}


def fetch(url):
    if url in _cache:
        return _cache[url]
    txt, err = "", ""
    try:
        r = http(url, max_bytes=25_000_000)
        if r.status == 0 or r.status >= 500:
            time.sleep(2)
            r = http(url, max_bytes=25_000_000)
        blk = page_blocked(r)
        if blk:
            err = f"blocked by the site ({blk})"
        elif r.status != 200:
            err = f"http {r.status}"
        elif "pdf" in r.headers.get("content-type", "").lower() or url.lower().split("?")[0].endswith(".pdf"):
            import fitz
            with fitz.open(stream=r.body, filetype="pdf") as doc:
                txt = "\n".join(p.get_text() for p in doc)
        else:
            title, body = page_text(r.text())
            txt = f"{title}\n{body}"
    except Exception as e:  # noqa: BLE001
        err = f"unreadable ({str(e)[:60]})"
    _cache[url] = (norm(txt), err)
    time.sleep(0.5)
    return _cache[url]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    path, out, write = argv[0], argv[1], "--write" in argv
    dsn = os.environ.get("KSSL_STAGING_DSN") or os.environ.get("KSSL_DSN")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT client_product_id, product_name, category, client_id FROM staging.client_product")
    prods = cur.fetchall()
    client_id = prods[0]["client_id"]
    cur.execute("SELECT client_product_id, spec_name, coalesce(value_text, value_numeric::text, '') v, display_order FROM staging.client_product_specification")
    have = {}
    for r in cur.fetchall():
        h = have.setdefault(r["client_product_id"], {"labels": set(), "blob": "", "order": 999})
        h["labels"].add(norm(r["spec_name"]))
        h["blob"] += " " + norm(r["v"])
        h["order"] = max(h["order"], r["display_order"] or 0)

    def target(name):
        for k, (pname, cat) in NEW_PRODUCTS.items():
            if name.startswith(k):
                return client_id_for("product", pname), pname, cat, True, None
        for k, why in NOT_MAPPED.items():
            if name.startswith(k):
                return None, None, None, False, why
        for k, sub in MAP.items():
            if name.startswith(k) or k in name:
                hits = [p for p in prods if sub in p["product_name"]]
                if len(hits) == 1:
                    return hits[0]["client_product_id"], hits[0]["product_name"], hits[0]["category"], False, None
                return None, None, None, False, f"maps to {len(hits)} KSSL products ('{sub}'): not placed"
        return None, None, None, False, "no matching KSSL product (name and link only in the workbook)"

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(wb["Master Database"].iter_rows(values_only=True))[1:]
    taken, recheck = [], []
    for cat, name, spec, feat, src in rows:
        if not name:
            continue
        urls = list(dict.fromkeys(URL.findall(str(src or ""))))
        judged = [(u, *classify_reason(u, PARTNER_DOMAINS, client=True)) for u in urls]
        listed = "\n".join(f"{u}  [{t or why}]" for u, t, why in judged)
        good = [(u, t) for u, t, _ in judged if t]
        lines = [("spec", b) for b in bullets(spec)] + [("feature", b) for b in bullets(feat)]
        pid, pname, pcat, is_new, why_not = target(str(name))
        if not lines:
            recheck.append((cat, name, "-", "", "No spec or feature in the workbook (only the product name and a link).", listed))
            continue
        pages = [(u, t, *fetch(u)) for u, t in good]
        for kind, b in lines:
            label, value = split_line(kind, b)
            hit = next(((u, t, ev) for u, t, txt, _ in pages if txt and (ev := evidence(value, txt, label))), None)
            if not hit:
                if not good:
                    why = "Every source listed for this product is blocked or not on our source list."
                elif not any(txt for *_, txt, _ in pages):
                    why = "The accepted pages could not be read: " + "; ".join(f"{u} ({e})" for u, _, _, e in pages)
                else:
                    why = "Not stated on any accepted source page listed for this product."
                recheck.append((cat, name, kind, b, why, listed))
                continue
            if pid is None:
                recheck.append((cat, name, kind, b, f"Stated on {hit[0]}, but {why_not}.", listed))
                continue
            h = have.setdefault(pid, {"labels": set(), "blob": "", "order": 999})
            nums = [n.replace(",", "") for n in NUM.findall(value)]
            if norm(label) in h["labels"] and label not in ("Capability", "Specification"):
                continue                                  # the product already has this spec
            if (nums and all(n in h["blob"].replace(",", "") for n in nums)) or norm(value) in h["blob"]:
                continue                                  # ... or this value
            h["labels"].add(norm(label))
            h["blob"] += " " + norm(value)
            h["order"] += 1
            taken.append(dict(pid=pid, pname=pname, pcat=pcat, is_new=is_new, wb_name=name, kind=kind, label=label, value=value,
                              url=hit[0], tier=hit[1], quote=hit[2], order=h["order"]))
        print(f"{str(name)[:48]:48} lines {len(lines):3}  taken so far {len(taken)}", flush=True)

    if write:
        for pname, pcat in NEW_PRODUCTS.values():
            if any(t["pname"] == pname for t in taken):
                pid_new = client_id_for("product", pname)
                cur.execute("""INSERT INTO staging.client_product (client_product_id, client_id, product_name, category, created_at, updated_at)
                               SELECT %s, %s, %s, %s, now(), now()
                               WHERE NOT EXISTS (SELECT 1 FROM staging.client_product WHERE client_product_id = %s)""",
                            (pid_new, client_id, pname, pcat, pid_new))
        for t in taken:
            sid = client_id_for("spec", t["pid"], norm(t["label"]) + "|" + norm(t["value"])[:80], TAG)
            src = client_id_for("source", t["pid"], t["url"])
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'client_product_specification' AND row_id = %s", (str(sid),))
            cur.execute("DELETE FROM staging.client_product_specification WHERE specification_id = %s", (sid,))
            cur.execute("""INSERT INTO staging.client_product_specification (specification_id, client_product_id, spec_name, value_text,
                               value_numeric, unit, spec_group, display_order, source_id) VALUES (%s, %s, %s, %s, NULL, NULL, %s, %s, %s)""",
                        (sid, t["pid"], t["label"], t["value"], spec_group(t["label"]), t["order"], src))
            cur.execute("""INSERT INTO staging.client_product_source (client_product_id, source_id, source_label, source_type, source_url)
                           SELECT %s, %s, %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM staging.client_product_source
                           WHERE client_product_id = %s AND source_id = %s)""",
                        (t["pid"], src, f"{publisher_of(t['url'])} - {SOURCE_TYPE.get(t['tier'], 'other').replace('_', ' ')}"[:255],
                         SOURCE_TYPE.get(t["tier"], "other"), t["url"], t["pid"], src))
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
                           VALUES ('client_product_specification', %s, 'value_text', %s, %s, %s, %s, now())""",
                        (str(sid), t["url"], t["tier"], publisher_of(t["url"]), t["quote"]))
        conn.commit()
    else:
        conn.rollback()

    xb = openpyxl.Workbook()
    ws = xb.active
    ws.title = "Recheck"
    ws.append(["Category", "Product", "Spec or feature", "Line (as in the workbook)", "Why it was not taken", "Sources the workbook listed [our rating]"])
    for r in recheck:
        ws.append(list(r))
    ws2 = xb.create_sheet("Taken")
    ws2.append(["KSSL product", "Workbook product", "Spec or feature", "Label", "Value", "Confirmed on", "Sentence on that page"])
    for t in taken:
        ws2.append([t["pname"] + (" (new product)" if t["is_new"] else ""), t["wb_name"], t["kind"], t["label"], t["value"], t["url"], t["quote"]])
    ws3 = xb.create_sheet("How to recheck")
    for line in ("Each line on 'Recheck' was not loaded. To get it in, send a page that states it (the KSSL site, a KSSL / partner",
                 "brochure or PDF, a government page, or listed defence trade press). Blogs, forums, Scribd uploads, test sites and",
                 "exam-prep sites are not accepted. One link per line is enough; the line is then checked against that page.",
                 f"Taken: {len(taken)} lines. To recheck: {len(recheck)} lines."):
        ws3.append([line])
    for sh, widths in ((ws, (16, 34, 10, 70, 60, 70)), (ws2, (40, 34, 10, 30, 50, 60, 80))):
        for i, wdt in enumerate(widths):
            sh.column_dimensions[chr(65 + i)].width = wdt
    xb.save(out)
    print(f"\n{'WROTE' if write else 'dry run'}: {len(taken)} lines taken, {len(recheck)} to recheck -> {out}")
    return 0


def _selftest():
    assert _unit_after("800 maximum", 3) is None and _unit_after("800 m", 3) == "m"
    assert evidence("70%", "range : < 50 m azimuth : < 70 company", "Gradeability") is None            # a bare number elsewhere
    assert evidence("90 km/h", "charging point efficiency > 90% design", "Cruise speed") is None       # same number, other unit
    assert evidence("1627 Nm", "engine turbo diesel 6 cylinder intercooled 336kw 1627nm power", "Engine torque")
    assert evidence("185 hp", "light bullet proof vehicle powered with 185 hp diesel engine", "Engine power")
    assert evidence("Large internal volume", "burst speed of up to 110km/hour", "Capability") is None
    assert evidence("800 m", "sighting range m 800 maximum range", "Sighting range")                    # table: unit before the number
    assert evidence("up to 40 rounds/min", "practical rate rounds/min automatic fire up to 100 single fire up to 40", "Practical rate - single fire")
    print("load_spec_workbook self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
