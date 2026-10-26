"""Targeted product list for the news harvest: base systems in KSSL's categories, with a searchable name (code, free).

    python -m backend.product_targets --selftest
    python -m backend.product_targets [--competitor NAME] [--csv out.csv]      (list + counts; reads kssl_staging, writes nothing)

Owner 2026-10-25: Google News per product only for "base systems" (platforms) and products in KSSL's categories (artillery,
ammunition, armoured / protected vehicles, small arms, barrels / forgings, UAVs / loitering munitions) -- roughly 500-700 names,
not all 4,500 catalogue rows. Rules (code, no model):
  * category in CATEGORIES; product_kind product / in_development / not yet classified (services, programmes, test assets,
    not-a-product rows are left out);
  * search name = the catalogue name without brackets and descriptions ("Puma Infantry Fighting Vehicle" -> "Puma",
    "FL50 / FL50A loitering munition" -> "FL50", "ARMA 8x8 - Armored Personnel Carrier" -> "ARMA 8x8");
  * not searchable: a name that is only a calibre / a standard designation (ammunition "155mm M795", "5.56 x 45 MM M855",
    "MORTAR BOMB 81 MM HE"), a sight / scope / accessory, or nothing left after cleaning;
  * base system: within one competitor, a name that starts with another kept name ("Boxer RCT30" under "Boxer", "K9A1" under
    "K9") is folded into it -- the base name's search finds its variants' news too (news.product_names matches loosely);
  * qualified: a single ordinary word ("Puma", "Terrier", "Boxer") is searched only together with the company name
    (news.queries_for qualified=True), so the bare word does not pull in unrelated news.
backend/news.py --product-targets uses targets() instead of every catalogue row.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter

CATEGORIES = ["Artillery", "Protected & Armoured Vehicles", "UAVs & Drones", "Small Arms", "Ammunition", "Precision Components & Forgings"]
KINDS = ("product", "in_development")

# descriptor words that end a product name ("Terrier armoured engineer vehicle" -> "Terrier"); normalised lower case
DESCRIPTORS = {
    "armoured", "armored", "infantry", "fighting", "vehicle", "vehicles", "personnel", "carrier", "carriers", "main", "battle", "tank",
    "tanks", "engineer", "engineering", "recovery", "repair", "ambulance", "command", "control", "mortar", "mortars", "howitzer",
    "howitzers", "self", "propelled", "towed", "gun", "guns", "cannon", "rocket", "rockets", "launcher", "launchers", "system",
    "systems", "loitering", "munition", "munitions", "unmanned", "uncrewed", "ground", "aerial", "uav", "ugv", "drone", "drones",
    "assault", "rifle", "rifles", "carbine", "pistol", "pistols", "machine", "submachine", "sniper", "light", "medium", "heavy",
    "family", "series", "variant", "version", "prototype", "concept", "next", "generation", "new", "upgrade", "upgraded",
    "modernised", "modernized", "programme", "program", "kit", "module", "turret", "turrets", "remote", "controlled", "weapon",
    "station", "rcws", "protected", "mobility", "patrol", "utility", "tactical", "truck", "trucks", "amphibious", "wheeled",
    "tracked", "multi", "purpose", "role", "range", "long", "short", "extended", "precision", "guided", "projectile",
    "projectiles", "shell", "shells", "round", "rounds", "ammunition", "cartridge", "cartridges", "grenade", "grenades", "bomb",
    "bombs", "fuze", "fuzes", "warhead", "warheads", "barrel", "barrels", "forging", "forgings", "component", "components",
    "and", "with", "for", "the", "of", "a", "an", "mk", "based", "on", "anti", "tank", "air", "defence", "defense", "mrap",
    "apc", "ifv", "mbt", "spg", "sph", "atgm", "mlrs", "lav", "jltv", "x4", "x6", "x8",
    # ammunition wording ("57 mm L70 High Explosive", "Offensive Hand Grenade", "127mm full charge")
    "high", "explosive", "practice", "common", "multipurpose", "offensive", "defensive", "hand", "programming", "unit", "charge",
    "charges", "full", "subsonic", "special", "frangible", "open", "tip", "grain", "naval", "target", "marker", "illumination",
    "illuminating", "training", "general", "point", "detonating", "incendiary", "armour", "armor", "piercing", "discarding",
    "sabot", "fin", "stabilized", "stabilised", "self", "destruct", "airburst", "proximity", "time", "electronic", "mechanical",
    "reconnaissance", "surveillance", "observation", "hybrid", "powered", "jet", "turbojet", "launched", "canister", "lightly",
}
AMMO_GENERIC_FIRST = re.compile(r"^(\d|\.\d|[0-9.]+\s*mm|[0-9]+x[0-9]+|cal\b|hand|offensive|defensive|manual|multi|mortar|tank|rifle|pistol|"
                                r"practice|training|illuminat|smoke|signal|anti|bomb|cartridge|round|shell|charge|primer|propellant|fuze)", re.I)
NOT_PRODUCT = re.compile(r"\b(sight|sights|scope|scopes|optic|optics|lpvo|accessor\w*|holster|suppressor\w*|magazine|spare|parts?|"
                         r"training|simulator|service|services|support|mro|overhaul|conversion|renovation|consult\w*)\b", re.I)
# a subsystem / add-on rather than a platform (owner: "base systems"): turrets, weapon stations, armour kits, launchers, ground
# stations, payloads, engines ... checked on the catalogue name of vehicle / UAV / artillery rows
SUBSYSTEM = re.compile(r"\b(turrets?|rcws|weapon stations?|remote(ly)? (controlled|operated) weapon|armou?r (kit|package|shield)|add-on|"
                       r"reactive armou?r|protection (system|kit)|crew protection|active protection|aps\b|kits?\b|upgrade package|"
                       r"bridge|bridging|trailers?|shelters?|containers?|engines?|transmissions?|tracks?\b|wheels?\b|suspension|"
                       r"filtration|collective protection|launchers?|ground (control )?stations?|gcs\b|payloads?|cameras?|data ?links?|"
                       r"gimbal|fire[- ]control|sensors?|radars?|jammers?|simulat\w*|trainer|mount\b|mounts\b|canisters?|"
                       r"recovery vehicle|repair|ambulance|command post|mortar carrier|ammunition (carrier|resupply))\b", re.I)
CALIBRE = re.compile(r"\b\d+(\.\d+)?\s*(mm|cal|calibre|caliber|x\s*\d+\w*)\b|\b\d+x\d+\w*\b|\.\d{2,3}\b", re.I)
DESIGNATION = re.compile(r"^(k?m\d+[a-z0-9]*|xm\d+[a-z0-9]*|l\d+[a-z0-9]*|dm\d+[a-z0-9]*|ss\d+|he|hei|heat|ap|apfsds|tp|tpt|ball|"
                         r"tracer|blank|ill|smoke|frag|sd|hep|hesh|pfsd|\d+)$", re.I)


def clean_name(name: str) -> str:
    """The searchable head of a catalogue name."""
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", name or "")
    s = re.split(r"\s[-–—:;|]\s|,|\s/\s|/(?=\s*[A-Za-z]{2,}\d)", s)[0]
    m = re.search(r"\s\d+(\.\d+)?\s*(mm|cal)(?![a-z])", s, re.I)
    if m and s[:m.start()].strip():
        s = s[:m.start()]                               # "Trajan 155 mm/52 cal Towed Gun" -> "Trajan"
    words = s.split()
    out = []
    for w in words:
        lw = re.sub(r"[^\w.-]", "", w).lower()
        parts = [p for p in lw.split("-") if p]
        descr = bool(parts) and all(p in DESCRIPTORS for p in parts) and not re.search(r"\d", w)
        if out and (descr or re.fullmatch(r"\d+(\.\d+)?(mm|cal)", lw)):
            break                                       # the description (or a calibre after the name) starts here
        out.append(w)
    while out and re.sub(r"[^\w]", "", out[-1]).lower() in DESCRIPTORS:
        out.pop()
    return " ".join(out).strip(" -/.,")


def searchable(category: str, product_name: str, search: str) -> tuple[bool, str]:
    if not search:
        return False, "nothing left after cleaning"
    if NOT_PRODUCT.search(product_name):
        return False, "sight / accessory / service"
    if category != "Ammunition" and category != "Precision Components & Forgings" and SUBSYSTEM.search(product_name):
        return False, "subsystem / variant role, not a base system"
    rest = CALIBRE.sub(" ", search)
    toks = [t for t in re.split(r"[\s/]+", rest) if t]
    named = [t for t in toks if re.sub(r"[^\w]", "", t) and re.sub(r"[^\w]", "", t).lower() not in DESCRIPTORS
             and not re.fullmatch(r"\d+", re.sub(r"[^\w]", "", t))]
    brand = [t for t in named if not DESIGNATION.match(re.sub(r"[^\w]", "", t))]
    if category == "Ammunition" and (AMMO_GENERIC_FIRST.match(search) or not any(len(re.sub(r"[^A-Za-z]", "", t)) >= 3 for t in brand)):
        return False, "calibre / standard designation only"     # a round named only "M795" / "KM490" is a standard, not a base system
    if not named:
        return False, "calibre / designation only"
    if len(search.replace(" ", "")) < 3:
        return False, "too short"
    return True, ""


def qualified(search: str) -> bool:
    """Search it only with the company name: a single ordinary word ("Puma"), or a short code of <= 4 characters ("T12", "M72",
    "K9": other makers' products and unrelated things share it -- a trial on SSS Defence's "T12" shotgun kept 18 unrelated items)."""
    toks = search.split()
    if len(re.sub(r"[^A-Za-z0-9]", "", search)) <= 4:
        return True
    return len(toks) == 1 and not re.search(r"\d", search) and not (search.isupper() and len(search) >= 3)


def fold_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def base_systems(rows: list[dict]) -> list[dict]:
    """rows of one competitor (with 'search'); a row whose search name starts with another kept name (whole words, or a
    letter/digit suffix: K9 -> K9A1) is folded into the shorter one."""
    rows = sorted(rows, key=lambda r: (len(fold_key(r["search"])), r["search"]))
    kept: list[dict] = []
    for r in rows:
        k = fold_key(r["search"])
        base = next((b for b in kept if k == fold_key(b["search"]) or k.startswith(fold_key(b["search"]) + " ")
                     or (re.match(re.escape(fold_key(b["search"])) + r"[a-z]?\d*[a-z]?$", k) and re.search(r"\d", fold_key(b["search"])))), None)
        if base is None:
            r["variants"] = []
            kept.append(r)
        else:
            base["variants"].append(r["product_name"])
    return kept


GENERIC_FIRST = {"light", "heavy", "medium", "new", "next", "mini", "micro", "tactical", "armoured", "armored", "multi", "the", "anti",
                 "mobile", "remote", "smart", "loitering", "unmanned", "combat", "modular", "advanced", "integrated", "naval", "land"}


def families(rows: list[dict]) -> list[dict]:
    """rows of one competitor after base_systems(): names that share a distinctive first word ("Hermes 650 Spark", "Hermes 900";
    "ZALA T-16", "ZALA Z-16E") become one target searched by that word (with the company name when it is an ordinary word)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        first = r["search"].split()[0]
        key = first.lower()
        if (len(r["search"].split()) > 1 and len(re.sub(r"[^A-Za-z]", "", first)) >= 3 and key not in GENERIC_FIRST
                and key not in DESCRIPTORS and not CALIBRE.search(first) and not re.match(r"[\d.]", first)):
            groups.setdefault(key, []).append(r)
    out = [r for r in rows if not (len(r["search"].split()) > 1 and len(groups.get(r["search"].split()[0].lower(), [])) >= 2)]
    for key, members in groups.items():
        if len(members) < 2:
            continue
        head = dict(members[0])
        head["search"] = members[0]["search"].split()[0]
        head["qualified"] = qualified(head["search"])
        head["variants"] = [m["product_name"] for m in members[1:]] + [v for m in members for v in m.get("variants", [])]
        same = next((r for r in out if fold_key(r["search"]) == fold_key(head["search"])), None)
        if same is not None:                          # the family word is itself a kept product ("Hermes"): fold into it
            same["variants"] += [m["product_name"] for m in members] + head["variants"][len(members) - 1:]
        else:
            out.append(head)
    return out


def targets(cur, competitor: str | None = None) -> tuple[list[dict], Counter]:
    """[{product_id, competitor_id, display_name, product_name, category, search, qualified, variants}], drop reasons."""
    cur.execute("""SELECT p.product_id::text, p.competitor_id::text, c.display_name, p.product_name, p.category, p.product_kind
                   FROM staging.competitive_product p JOIN staging.competitive_competitor c USING (competitor_id)
                   WHERE p.category = ANY(%s) AND (p.product_kind IS NULL OR p.product_kind = ANY(%s))
                   ORDER BY c.display_name, p.product_name""", (CATEGORIES, list(KINDS)))
    drop: Counter = Counter()
    by_comp: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        r = dict(r) if not isinstance(r, dict) else r
        if competitor and competitor.lower() not in r["display_name"].lower():
            continue
        s = clean_name(r["product_name"])
        ok, why = searchable(r["category"], r["product_name"], s)
        if not ok:
            drop[why] += 1
            continue
        by_comp.setdefault(r["competitor_id"], []).append({**r, "search": s, "qualified": qualified(s)})
    out = []
    for cid, rows in by_comp.items():
        kept = families(base_systems(rows))
        drop["folded into a base system / family"] += len(rows) - len(kept)
        out += kept
    out.sort(key=lambda r: (r["display_name"], CATEGORIES.index(r["category"]), r["search"]))
    return out, drop


def _selftest() -> None:
    assert clean_name("Puma Infantry Fighting Vehicle") == "Puma"
    assert clean_name("Terrier armoured engineer vehicle") == "Terrier"
    assert clean_name("FL50 / FL50A loitering munition") == "FL50"
    assert clean_name("ARMA 8x8 - Armored Personnel Carrier") == "ARMA 8x8"
    assert clean_name("M1A2 Abrams (baseline M1A2)") == "M1A2 Abrams"
    assert clean_name("K9A3 (next-generation K9, concept)") == "K9A3"
    assert clean_name("Excalibur (M982 / M982A1) 155mm Precision-Guided Projectile") == "Excalibur"
    assert clean_name("Galil ACE (5.56x45 mm assault rifle / carbine family)") == "Galil ACE"
    assert clean_name("Trajan 155 mm/52 cal Towed Gun System (TGS)") == "Trajan"
    assert clean_name("HERO-120") == "HERO-120" and clean_name("PzH 2000 (Panzerhaubitze 2000)") == "PzH 2000"
    assert searchable("Ammunition", "155mm M795 HE", clean_name("155mm M795 HE"))[0] is False
    assert searchable("Ammunition", "5.56 x 45 MM M855 (NATO)", clean_name("5.56 x 45 MM M855 (NATO)"))[0] is False
    assert searchable("Ammunition", "MORTAR BOMB 81 MM HE", clean_name("MORTAR BOMB 81 MM HE"))[0] is False
    assert searchable("Ammunition", "Excalibur 155mm", "Excalibur")[0] is True
    assert searchable("Artillery", "M777 howitzer", clean_name("M777 howitzer"))[0] is True              # a platform designation is a base system
    assert searchable("Small Arms", "TANGO-MSR LPVO family", "TANGO-MSR")[0] is False                   # an optic
    assert searchable("Protected & Armoured Vehicles", "MIZRAK 25 mm turret", "MIZRAK")[0] is False
    assert searchable("Protected & Armoured Vehicles", "Buffalo armoured recovery vehicle 3", "Buffalo")[0] is False
    assert searchable("UAVs & Drones", "VIPER MCL (Multi-Canister Launcher) and VIPER GCS", "VIPER MCL")[0] is False
    assert searchable("Protected & Armoured Vehicles", "Panther KF51 Main Battle Tank", "Panther KF51")[0] is True
    assert qualified("Puma") and qualified("K9") and qualified("T12") and not qualified("CV9035") and not qualified("ARMA 8x8")
    assert not qualified("ULTRO") and not qualified("HERO-120")
    rows = [{"product_name": n, "search": clean_name(n)} for n in ["Boxer", "Boxer RCT30", "K9", "K9A1", "K9A2 upgrade", "K21 IFV", "Bo"]]
    kept = base_systems(rows)
    assert sorted(r["search"] for r in kept) == ["Bo", "Boxer", "K21", "K9"], [r["search"] for r in kept]
    assert sorted(next(r for r in kept if r["search"] == "K9")["variants"]) == ["K9A1", "K9A2 upgrade"]
    fam = families(base_systems([{"product_name": n, "search": clean_name(n), "qualified": False} for n in
                                 ["Hermes 650 Spark", "Hermes 900", "ZALA T-16", "ZALA Z-16E", "Light Strike", "Skylark I-eVTOL"]]))
    assert sorted(r["search"] for r in fam) == ["Hermes", "Light Strike", "Skylark I-eVTOL", "ZALA"], [r["search"] for r in fam]
    assert next(r for r in fam if r["search"] == "Hermes")["qualified"] and next(r for r in fam if r["search"] == "ZALA")["qualified"]
    assert searchable("Ammunition", "25x137mm HEI-T", clean_name("25x137mm HEI-T"))[0] is False
    assert searchable("Ammunition", "Offensive Hand Grenade HGO115-3.5", clean_name("Offensive Hand Grenade HGO115-3.5"))[0] is False
    assert searchable("Ammunition", "Kitolov-2M (122 mm laser-guided artillery projectile)", "Kitolov-2M")[0] is True
    print("product_targets self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.product_targets", description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--competitor")
    ap.add_argument("--csv")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
        return 0
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging",
                            cursor_factory=psycopg2.extras.RealDictCursor)
    rows, drop = targets(conn.cursor(), a.competitor)
    conn.close()
    print(f"targets {len(rows)} (qualified {sum(r['qualified'] for r in rows)}); dropped: {dict(drop)}")
    for k, n in Counter(r["category"] for r in rows).most_common():
        print(f"  {k:34} {n}")
    for k, n in sorted(Counter(r["display_name"] for r in rows).items()):
        print(f"  {k:34} {n}")
    if a.csv:
        with open(a.csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["competitor", "category", "search_name", "qualified", "product_name", "variants_folded", "product_id"])
            for r in rows:
                w.writerow([r["display_name"], r["category"], r["search"], r["qualified"], r["product_name"], " | ".join(r["variants"]), r["product_id"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
