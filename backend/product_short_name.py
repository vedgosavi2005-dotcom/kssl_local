"""Short product names (db/setup/47_product_short_name.sql: competitive_product.short_name, client_product.short_name).

    python -m backend.product_short_name --selftest
    python -m backend.product_short_name [--limit N] [--company <name part>] [--dry-run] [--redo] [--min-len 31] [--model gemma4-26b-gpu]

Owner 2026-10-26: "there are still many products which are named long ... wherever the product name shows, shorten them". The rule
in backend/spec_sheet.display_name already drops company / country / status brackets; this pass handles the rest (a spelled-out
role, an alias list, a configuration note) with the local model (Ollama, this PC, no cost), a batch at a time. Code keeps an answer
only when
  - every word of it is a word of the stored name (case and punctuation folded): the model may drop words, never add or reword;
  - it keeps the designation: the first word of the stored name that carries a digit or two capitals ("AGM-114K", "MK 99"), or
    the first word when there is none;
  - it is shorter than the current display name and at most MAX_LEN characters;
  - no other product of the same company gets the same short name in this run (both keep the rule's name instead).
Anything else leaves short_name NULL (the rule's name shows). Only rows whose rule name is longer than --min-len are sent.
Writes staging only, with one fact_source judgement row per name (column short_name); the client sees it after Approve.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from collections import defaultdict

OLLAMA = "http://127.0.0.1:11434/api/chat"
BATCH = 25
MAX_LEN = 40

SYSTEM = """You shorten defence product names for a product catalogue. For EACH row give the short name a defence analyst would use:
keep the model designation and the product's own name (e.g. "Hellfire AGM-114K", "MK 99 Fire Control System", "WESCAM MX-20D",
"Tomahawk Block IV", "AN/TPY-4", "VN11", "Kodiak AEV3"); for ammunition keep calibre and round type ("7.62 x 51 Tracer",
"40mm x 53 HE"). Drop: spelled-out expansions of an acronym, alias lists in brackets, descriptions of the role, customers,
partners, configurations notes, "(e.g. ...)". Leave no stray commas or half brackets; a part or service for a platform keeps its
part word ("Hermes 900 aerostructures", not "Hermes 900"). Use ONLY words that appear in the row's name, in their order; never add, translate
or reword. At most 40 characters. If the name is already short, return it unchanged.
Copy each kept word EXACTLY as written in the name (same spelling, hyphens, capitals, digits); do not join or split words.
If you cannot make it 40 characters or less with the name's own words, return the designation with at most two words around it.
Return JSON: {"rows": [{"id": "<row id exactly>", "short": "<short name>"}]} with one entry per row."""

_PART = re.compile(r"\b(?:aerostructures?|structures?|parts?|components?|fuselages?|wings?|propellants?|motors?|casings?|"
                   r"engines?|radars?|sights?|turrets?|fuzes?|seekers?|launchers?|sensors?|kits?|pods?|barrels?|forgings?|"
                   r"castings?|simulators?|training|ammunition|warheads?)\b", re.I)
_WORD = re.compile(r"[a-z0-9]+(?:[./-][a-z0-9]+)*")


def words(s: str) -> list[str]:
    return _WORD.findall(str(s or "").lower())


def designation(name: str) -> str | None:
    """the first word that names the model: a digit or two capitals ("AGM-114K", "MK", "CAESAR"), else the first word"""
    for w in re.findall(r"[A-Za-z0-9]+(?:[./-][A-Za-z0-9]+)*", str(name or "")):
        if re.search(r"\d", w) or re.search(r"[A-Z].*[A-Z]", w):
            return w.lower()
    ws = words(name)
    return ws[0] if ws else None


_HEAD = {"system", "systems", "suite", "module", "vehicle", "vehicles", "adapter", "amplifier", "hub", "terminal", "intercom", "combat",
         "solution", "solutions", "unit", "kit", "set", "platform", "station", "launcher", "transporter", "carrier"}


def cut_mid_phrase(short: str, name: str) -> bool:
    """the short name is the front of the name with its noun cut off ("HERON 6x6 tactical", "Wolf XM30 Mechanized Infantry"):
    it ends on a lower-case word, or the very next word of the name is the head noun ("... Remote Control | System").
    A designation alone ("Bluefin-12", "HEMTT A4 M983A4") is fine."""
    nm = " ".join(str(name).split())
    if not nm.lower().startswith(short.lower()) or len(nm) == len(short):
        return False
    rest = nm[len(short):]
    if re.match(r"^\s*(\(|/|,|;|-|–|&|and\b|for\b|with\b|$)", rest, re.I):
        return False
    last = short.split()[-1]
    nxt = (re.findall(r"[A-Za-z]+", rest) or [""])[0].lower()
    return bool(re.fullmatch(r"[a-z][a-z-]*", last)) or nxt in _HEAD


def check(short: str, name: str, current: str) -> str | None:
    s = " ".join(str(short or "").split()).strip(" -,;:/")
    if not s or len(s) > MAX_LEN or len(s) >= len(current):
        return None
    own = set(words(name))
    sw = words(s)
    if not sw or any(w not in own for w in sw):
        return None
    d = designation(name)
    if d and d not in sw and not any(d in w or w in d for w in sw if len(w) >= 3):
        return None
    if cut_mid_phrase(s, name):
        return None
    # a part named after its platform keeps its part word: "aerostructures (Hermes 900)" is not the Hermes 900 drone
    head = str(name).split("(")[0]
    parts = {w.lower() for w in _PART.findall(head)}
    if parts and not parts & set(sw):
        return None
    return s


def ask(model: str, rows: list[dict]) -> list[dict]:
    text = "\n".join(f"ROW id={r['id']} | company: {r['company']} | category: {r['category'] or '-'} | name: {r['current']}" for r in rows)
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_predict": 3000},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(json.load(r)["message"]["content"])
    return out.get("rows") or [] if isinstance(out, dict) else []


def _rows(cur, company: str | None, redo: bool) -> list[dict]:
    """every product with its company, category and the rule's display name"""
    from backend import spec_sheet
    cur.execute("""SELECT 'competitive_product' AS t, p.product_id::text AS id, p.product_name AS name, p.category, p.short_name,
                          c.display_name AS company, c.short_name AS co_short, c.legal_name AS co_legal
                   FROM staging.competitive_product p JOIN staging.competitive_competitor c USING (competitor_id)
                   UNION ALL
                   SELECT 'client_product', cp.client_product_id::text, cp.product_name, cp.category, cp.short_name, a.client_name, NULL, NULL
                   FROM staging.client_product cp JOIN staging.client_account a USING (client_id)""")
    out = []
    for r in [dict(x) for x in cur.fetchall()]:
        if company and company.lower() not in str(r["company"]).lower():
            continue
        if r["short_name"] and not redo:
            continue
        co_re = spec_sheet.company_re([n for n in (r["company"], r["co_short"], r["co_legal"], "KSSL", "Kalyani", "Bharat Forge") if n])
        r["current"] = spec_sheet.display_name(r["name"], co_re)
        out.append(r)
    return out


def run(model: str, limit: int | None, company: str | None, dry: bool, redo: bool, min_len: int) -> None:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    rows = [r for r in _rows(cur, company, redo) if len(r["current"]) >= min_len]
    rows = rows[:limit] if limit else rows
    print(f"{len(rows)} names longer than {min_len - 1} characters", flush=True)
    picked: dict[str, tuple[dict, str]] = {}
    unsure = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        by_id = {r["id"]: r for r in batch}
        try:
            answers = ask(model, batch)
        except Exception as e:  # noqa: BLE001
            print(f"  batch {i // BATCH + 1}: model error {e}")
            unsure += len(batch)
            continue
        for a in answers:
            r = by_id.pop(str(a.get("id") or "").strip(), None)
            if not r:
                continue
            s = check(a.get("short"), r["name"], r["current"])
            if s:
                picked[r["id"]] = (r, s)
            else:
                unsure += 1
        unsure += len(by_id)
        print(f"batch {i // BATCH + 1}/{(len(rows) + BATCH - 1) // BATCH}: kept {len(picked)}, unsure {unsure}", flush=True)
    # one company, one short name: a clash keeps neither (both keep the rule's name)
    seen: dict[tuple, list[str]] = defaultdict(list)
    for pid, (r, s) in picked.items():
        seen[(r["company"], s.lower())].append(pid)
    clash = {pid for ids in seen.values() if len(ids) > 1 for pid in ids}
    for pid, (r, s) in sorted(picked.items(), key=lambda kv: kv[1][0]["company"]):
        if pid in clash:
            print(f"  clash   {r['company'][:18]:18} | {r['current'][:60]} -> {s}")
            continue
        print(f"  {r['company'][:18]:18} | {r['current'][:62]:62} -> {s}")
        if dry:
            continue
        key = "product_id" if r["t"] == "competitive_product" else "client_product_id"
        cur.execute(f"UPDATE staging.{r['t']} SET short_name = %s WHERE {key}::text = %s", (s, pid))
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND column_name = 'short_name' AND row_id = %s", (r["t"], pid))
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                       VALUES (%s, %s, 'short_name', 'judgement', 'judgement', %s)""", (r["t"], pid, f"shortened from the stored name: {r['name'][:300]}"))
    print(f"kept {len(picked) - len(clash)}, clashes {len(clash)}, unsure {unsure}")
    conn.rollback() if dry else conn.commit()


def _selftest() -> None:
    n = "Battlefield Awareness and Targeting System - Embedded 1500 (BATS-E 1500)"
    assert check("BATS-E 1500", n, n) == "BATS-E 1500"
    assert check("BATS Embedded", n, n) is None                                    # "bats" alone is not a word of the name
    assert check("Hellfire AGM-114K", "Hellfire AGM-114K (Hellfire II baseline)", "Hellfire AGM-114K (Hellfire II baseline)") == "Hellfire AGM-114K"
    assert check("Hellfire missile", "Hellfire AGM-114K (Hellfire II baseline)", "x" * 50) is None   # a word not in the name
    assert check("Hellfire II", "Hellfire AGM-114K (Hellfire II baseline)", "x" * 50) is None        # the designation dropped
    w = "WESCAM MX-20D EO/IR targeting and designating turret"
    assert check("WESCAM MX-20D turret", w, w) == "WESCAM MX-20D turret" and check("WESCAM MX-20D", w, w) is None   # the type word stays
    assert check("7.62 mm x 51 Tracer", "7.62 mm x 51 NATO Tracer Non Toxic 9", "7.62 mm x 51 NATO Tracer Non Toxic 9") == "7.62 mm x 51 Tracer"
    assert check("A" * 45, "A" * 60, "A" * 60) is None                                               # too long
    assert check("Hermes 900 / Hermes 450", "Carbon-composite aerostructures (Hermes 900 / Hermes 450)", "x" * 60) is None
    assert check("Hermes 900 aerostructures", "Carbon-composite aerostructures (Hermes 900 / Hermes 450)", "x" * 60) == "Hermes 900 aerostructures"
    assert check("HERON 6x6 tactical", "HERON 6x6 tactical multi-role / command vehicle", "x" * 60) is None
    assert check("Wolf XM30 Mechanized Infantry", "Wolf XM30 Mechanized Infantry Combat Vehicle (GDLS)", "x" * 60) is None
    assert check("Bluefin-12", "Bluefin-12 unmanned underwater vehicle (UUV)", "x" * 60) == "Bluefin-12"
    assert check("HEMTT A4 M983A4", "HEMTT A4 M983A4 Light Equipment Transporter (LET)", "x" * 60) == "HEMTT A4 M983A4"
    assert designation("Tomahawk Block IV (TLAM-E / Tactical Tomahawk)") == "iv"
    print("product_short_name self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--company")
    ap.add_argument("--min-len", type=int, default=31)
    ap.add_argument("--model", default="gemma4-26b-gpu")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    run(a.model, a.limit, a.company, a.dry_run, a.redo, a.min_len)
    return 0


if __name__ == "__main__":
    sys.exit(main())
