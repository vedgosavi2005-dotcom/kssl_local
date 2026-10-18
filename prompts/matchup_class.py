"""Like-for-like gate of the code matchup engine (prompts/matchup_code.py).

Same category is not enough to compare two products: a handgun is not an AK-47, a 60 mm mortar is not a 155 mm howitzer, a
nano quad-rotor is not a large one. One model pass classifies every product (client and competitor) into
    sub_type      a controlled vocabulary per category (VOCAB below)
    calibre_mm    where it applies (guns, small arms, ammunition)
    barrel_cal    barrel length in calibres when stated (52 for L/52): a difference is marked, not a bar
    weight_class  a band of the category's WEIGHT list (combat weight, weapon weight, MTOW, displacement ...)
and a pair is made only when category and sub_type match, the calibre matches where it applies, and the weight
classes are the same or adjacent. Unknown sub_type, a missing calibre where one is needed, or an unknown weight class
where weight bands exist: no pair. The result is stored in staging.product_class (db/setup/10_spec_dictionary.sql).

Self-check:  python -m prompts.matchup_class
"""

from __future__ import annotations

import json
from collections import defaultdict

# ---- vocabularies (defined once, kept consistent: the model must pick from these) ----------------------------

VOCAB = {
    "artillery": {
        "towed_howitzer": "towed gun or howitzer above 105 mm (e.g. 155 mm towed, 122/130 mm towed)",
        "light_gun_105": "light / mountain / ultra-light gun of 105 mm or less, towed or air-portable",
        "self_propelled_tracked": "tracked self-propelled gun / howitzer",
        "self_propelled_wheeled_truck_mounted": "wheeled self-propelled or truck-mounted gun / howitzer (MGS, MArG, Caesar-type)",
        "mortar": "mortar of any calibre, towed, vehicle-mounted or man-portable",
        "mrl_rocket_artillery": "multiple rocket launcher / rocket artillery / tactical ballistic launcher on a truck",
        "support_equipment": "ammunition carrier, fire-control, radar, survey, simulator, command post, other support",
    },
    "small arms": {
        "handgun": "pistol or revolver", "smg": "submachine gun / machine pistol / PDW", "carbine": "carbine (short rifle, rifle calibre or pistol calibre)",
        "assault_rifle": "assault rifle in an intermediate calibre (5.56, 5.45, 7.62x39, 6.8)", "battle_rifle": "full-power rifle (7.62x51) for rifleman use",
        "sniper_rifle": "sniper or designated-marksman rifle, anti-materiel rifle", "lmg": "light machine gun / squad automatic weapon",
        "gpmg": "general-purpose machine gun (7.62x51 belt-fed)", "hmg": "heavy machine gun (12.7 / 14.5 mm)",
        "grenade_launcher": "grenade launcher (underbarrel or standalone, incl. AGL)", "shotgun": "shotgun", "accessory": "optics, suppressor, accessory, training item",
    },
    "uavs & drones": {
        "nano_micro": "nano / micro hand-launched, mini quad or fixed-wing under 2 kg", "small_tactical": "small tactical fixed-wing UAV 2-150 kg",
        "tactical_medium": "tactical UAV 150-600 kg", "male": "medium-altitude long-endurance (MALE)", "hale": "high-altitude long-endurance (HALE)",
        "loitering_munition": "loitering munition / kamikaze drone", "multirotor_small": "VTOL multirotor / helicopter UAV up to 25 kg",
        "multirotor_large": "VTOL multirotor / helicopter UAV above 25 kg", "ucav": "combat / jet-powered UAV, target drone",
        "support_system": "ground control station, payload, counter-UAS, launcher, other support",
    },
    "protected & armoured vehicles": {
        "light_4x4": "light protected 4x4 / tactical vehicle / JLTV class", "mrap": "mine-resistant ambush-protected vehicle",
        "apc_wheeled": "wheeled armoured personnel carrier", "apc_tracked": "tracked armoured personnel carrier", "ifv_wheeled": "wheeled infantry fighting vehicle",
        "ifv_tracked": "tracked infantry fighting vehicle", "mbt": "main battle tank", "light_tank": "light tank / assault gun / fire-support vehicle",
        "recce": "armoured reconnaissance vehicle", "engineering_support": "ARV, bridge-layer, engineer, ambulance, command, other special-role armoured vehicle",
        "logistic_truck": "military cargo / logistics truck, armoured cab or not", "ugv": "unmanned ground vehicle", "turret_weapon_station": "turret, remote weapon station, vehicle kit",
    },
    "ammunition": {
        "small_arms_ammo": "cartridges up to 14.5 mm", "medium_calibre_ammo": "20-57 mm cannon ammunition", "tank_gun_ammo": "100-125 mm tank gun rounds",
        "artillery_ammo": "artillery shells and charges (105 mm and up, incl. guided)", "mortar_ammo": "mortar bombs", "rocket_ammo": "rockets and rocket motors",
        "grenade_ammo": "hand, rifle and launcher grenades (incl. 40 mm)", "bomb_warhead": "aerial bombs, warheads, mines, demolition", "fuze_component": "fuzes, propellant, other components",
    },
    "missiles & air defence": {
        "atgm": "anti-tank guided missile", "manpads": "man-portable air-defence missile", "sam_short": "short-range surface-to-air system (up to ~20 km)",
        "sam_medium": "medium-range surface-to-air system (~20-100 km)", "sam_long": "long-range SAM / ABM above ~100 km", "cruise_missile": "land-attack or sea-skimming cruise missile",
        "ballistic_missile": "tactical or strategic ballistic missile", "air_to_air": "air-to-air missile", "air_to_surface": "air-to-surface missile / guided bomb kit",
        "anti_ship": "anti-ship missile", "gun_air_defence": "gun-based air defence / CIWS", "radar_sensor": "radar, sensor, C2 and other air-defence support",
    },
    "marine / naval": {
        "patrol_craft": "patrol boat / OPV / coast guard vessel / fast attack craft", "corvette_frigate": "corvette or frigate", "destroyer_cruiser": "destroyer or cruiser",
        "submarine": "submarine or midget submarine", "amphibious_auxiliary": "amphibious ship, tanker, supply, auxiliary, survey, hospital ship",
        "carrier": "aircraft carrier or helicopter carrier", "small_boat": "RHIB, interceptor, assault or riverine boat", "unmanned_vessel": "USV / UUV / AUV",
        "naval_weapon": "naval gun, missile launcher, torpedo, mine, CIWS", "naval_sensor_system": "sonar, radar, combat system, EW, other naval equipment",
    },
    "precision components & forgings": {
        "forging": "forged part or forged blank", "machined_component": "machined or turned precision component", "casting": "casting",
        "assembly_subsystem": "assembled sub-system, mechanism or kit", "material_process": "raw material or special process",
    },
    "armoured vehicle mro": {
        "overhaul_service": "overhaul / maintenance / repair service", "upgrade_programme": "upgrade or retrofit programme", "support_service": "spares, training or other support service",
    },
}

# Second dimension (user rule 2026-10-18): a sub-type that mixes roles / styles is split, and two products of it are compared only
# when their role is the same (a reconnaissance multirotor is not a bomb-dropping one, an ultra-light howitzer is not a 15 t one).
# A product of these sub-types with no role does not pair.
ROLES = {
    ("artillery", "towed_howitzer"): {
        "ultralight_towed": "ultra-light / mountain / air-portable towed howitzer (titanium or light alloy, roughly 4-8 t; M777 class)",
        "standard_towed": "conventional towed field howitzer (roughly 8-20 t; FH-77, Dhanush, ATAGS, TRAJAN, M-71 class)"},
    ("artillery", "self_propelled_wheeled_truck_mounted"): {
        "truck_mounted_open": "gun on a truck chassis worked in the open or from the cab (CAESAR, ATMOS, MArG, Dhanush MGS class)",
        "armoured_turret_wheeled": "gun in an armoured turret or automated module on a wheeled armoured chassis (RCH 155, Archer, Zuzana, G6 class)"},
    ("small arms", "sniper_rifle"): {
        "bolt_action_sniper": "bolt-action sniper rifle in a full-power or magnum cartridge (.308, .300 WM, .338 LM)",
        "semi_auto_marksman": "semi-automatic sniper / designated-marksman rifle (SVD, SVDM, DMR class)",
        "anti_materiel": "anti-materiel rifle (12.7 mm / 14.5 mm / 20 mm)"},
    ("small arms", "carbine"): {
        "rifle_cartridge_carbine": "short rifle in a rifle cartridge (5.56x45, 7.62x39, 5.45x39, 7.62x51)",
        "short_cartridge_carbine": "carbine / PDW in a short or pistol cartridge (5.56x30 MINSAS, 9x19, 4.6x30, 5.7x28)"},
    **{("uavs & drones", st): {
        "isr_surveillance": "surveillance / reconnaissance / target acquisition (camera or sensor payload, no weapon)",
        "logistics_cargo": "cargo / heavy-lift delivery drone",
        "armed_strike": "carries and drops or fires weapons (bomber drone, armed multirotor or UAV)",
        "multi_role_payload": "built to swap between ISR, cargo and weapon payloads (sold as multi-payload / multi-role)",
        "other_mission": "training, target, agriculture, communications relay or another mission"}
       for st in ("multirotor_small", "multirotor_large", "small_tactical")},
    ("ammunition", "rocket_ammo"): {
        "guided_rocket": "guided rocket (laser / GPS / IR guided, e.g. APKWS, FZ275)",
        "unguided_rocket": "unguided aircraft or ground-launched rocket of up to about 90 mm (Hydra-70, FFAR, S-8)",
        "artillery_rocket": "rocket-artillery round of 107 mm and above (122 mm Grad, 214 mm Pinaka, 227 mm GMLRS)",
        "rocket_part": "rocket motor, warhead or fuze sold on its own"},
    ("protected & armoured vehicles", "apc_wheeled"): {
        "apc_4x4": "wheeled APC with 4x4 drive", "apc_6x6_8x8": "wheeled APC with 6x6 or 8x8 drive"},
    ("protected & armoured vehicles", "mrap"): {
        "mrap_4x4": "MRAP / mine-protected vehicle with 4x4 drive", "mrap_6x6_up": "MRAP / mine-protected vehicle with 6x6 or more axles"},
}
BARREL_GAP = 7            # guns: barrel lengths in calibres must be adjacent (39 vs 45, 45 vs 52), never 39 vs 52

NA = ["n/a"]
WEIGHT = {
    "artillery": ["under 1 t", "1-5 t", "5-20 t", "20-40 t", "over 40 t"],             # weight in action / combat weight / system weight
    "small arms": ["under 1 kg", "1-3 kg", "3-6 kg", "6-12 kg", "over 12 kg"],         # empty weapon
    "uavs & drones": ["under 2 kg", "2-25 kg", "25-150 kg", "150-600 kg", "600-5000 kg", "over 5000 kg"],   # maximum take-off weight
    "protected & armoured vehicles": ["under 6 t", "6-15 t", "15-30 t", "30-50 t", "over 50 t"],           # combat weight / GVW
    "missiles & air defence": ["under 25 kg", "25-150 kg", "150-1000 kg", "1000-5000 kg", "over 5000 kg"],  # the missile (launch mass)
    "marine / naval": ["under 100 t", "100-1000 t", "1000-5000 t", "over 5000 t"],     # full-load displacement
    "ammunition": NA, "precision components & forgings": NA, "armoured vehicle mro": NA,
}
WEIGHT_WHAT = {
    "artillery": "weight in action / combat weight / system weight (a mortar: the whole mortar)", "small arms": "weapon weight, unloaded",
    "uavs & drones": "maximum take-off weight", "protected & armoured vehicles": "combat weight or gross vehicle weight",
    "missiles & air defence": "mass of the missile (the interceptor / round), not the launcher", "marine / naval": "full-load displacement",
}
# categories where the calibre must match; the listed sub-types are exempt (no calibre meaning)
CALIBRE_CATEGORIES = {"artillery": {"support_equipment"}, "small arms": {"accessory"}, "ammunition": {"fuze_component", "bomb_warhead"}}
CALIBRE_TOL_MM, CALIBRE_TOL_REL = 0.06, 0.005


def calibre_ok(category: str, sub_type: str, a, b) -> tuple[bool, bool]:
    """(ok, applies). Calibre applies to guns, small arms and ammunition; both must be known and equal. 155/52 vs 155/39 is the same calibre."""
    if sub_type in CALIBRE_CATEGORIES.get(category, {"": 1}) or category not in CALIBRE_CATEGORIES:
        return True, False
    if a is None or b is None:
        return False, True
    a, b = float(a), float(b)
    return abs(a - b) <= max(CALIBRE_TOL_MM, CALIBRE_TOL_REL * max(a, b)), True


def weight_ok(category: str, wa: str, wb: str, relaxed: bool = False) -> bool:
    bands = WEIGHT.get(category, NA)
    if bands == NA:
        return True
    if wa not in bands or wb not in bands:
        return relaxed
    return abs(bands.index(wa) - bands.index(wb)) <= 1


def gate(category: str, a: dict, b: dict, relaxed_weight: bool = False) -> bool:
    """a, b: {'sub_type', 'calibre_mm', 'weight_class'} of the client and the competitor product."""
    c = category.strip().lower()
    st = a.get("sub_type")
    if not st or st == "unknown" or st != b.get("sub_type") or st not in VOCAB.get(c, {}):
        return False
    ok, _ = calibre_ok(c, st, a.get("calibre_mm"), b.get("calibre_mm"))
    if (c, st) in ROLES and (not a.get("role") or a.get("role") != b.get("role")):
        return False                                      # same sub-type, different role / style (or not classified yet)
    ba, bb = a.get("barrel_cal"), b.get("barrel_cal")
    if ba is not None and bb is not None and abs(float(ba) - float(bb)) > BARREL_GAP:
        return False
    return ok and weight_ok(c, a.get("weight_class"), b.get("weight_class"), relaxed_weight)


def basis(category: str, a: dict, b: dict) -> str:
    """The gate in words, for match_basis: 'Like-for-like: Artillery / self propelled tracked / 155 mm (barrel 52 vs 39 cal), weight class over 40 t'."""
    c = category.strip().lower()
    st = a["sub_type"].replace("_", " ") + (f" ({a['role'].replace('_', ' ')})" if a.get("role") else "")
    parts = [category, st]
    ok, applies = calibre_ok(c, a["sub_type"], a.get("calibre_mm"), b.get("calibre_mm"))
    if applies:
        cal = f"{float(a['calibre_mm']):g} mm"
        ba, bb = a.get("barrel_cal"), b.get("barrel_cal")
        if ba is not None and bb is not None and float(ba) != float(bb):
            cal += f" (barrel {float(ba):g} vs {float(bb):g} cal)"
        parts.append(cal)
    wa, wb = a.get("weight_class"), b.get("weight_class")
    w = ""
    if WEIGHT.get(c, NA) != NA:
        w = f", weight class {wa}" if wa == wb else f", weight class {wa} vs {wb}"
    return "Like-for-like: " + " / ".join(parts) + w


# ---- the classification pass -------------------------------------------------------------------------------

BATCH_PRODUCTS = 80

SYSTEM = """You classify defence products so that only like-for-like products are compared. For each product you get its id,
maker, name and a few of its specifications. Use the product's name and specs; where the name is a well-known system you may
use your general knowledge of what class it is, but never invent a calibre or weight that neither the specs nor the system's
public identity gives. Reply with JSON only:
{"items": [{"id": <id>, "sub_type": "<one of the allowed sub-types, or unknown>", "calibre_mm": <number or null>,
            "barrel_cal": <number or null>, "weight_class": "<one of the allowed bands, or unknown>", "reason": "<one short sentence>"}, ...]}
Rules: sub_type MUST be one of the allowed list for the product's category; use "unknown" when the product is not clearly one of them
or is not a physical product of that category. calibre_mm: the bore / calibre in millimetres for guns, mortars, rocket launchers, small
arms and ammunition (5.56, 7.62, 9, 12.7, 30, 40, 105, 120, 155 ...; .50 cal = 12.7; convert inches); null otherwise or when not stated.
barrel_cal: barrel length in calibres for guns (52 for L/52 or 52 cal); null otherwise. weight_class: the band that contains the
weight described for the category, or unknown when no weight is given or derivable. One item per id, none missing."""


def prompt_for(category: str, items: list) -> str:
    c = category.strip().lower()
    voc = "\n".join(f"  {k}: {v}" for k, v in VOCAB[c].items())
    bands = WEIGHT[c]
    wt = ("weight_class bands (ascending) for " + WEIGHT_WHAT[c] + ": " + " | ".join(bands)) if bands != NA else 'weight_class: always "n/a" for this category'
    lines = []
    for it in items:
        sp = "; ".join(it["specs"])
        lines.append(f"{it['id']}\t{it['maker'] or '-'}\t{it['name']}\t{sp or '(no specs)'}")
    return (f"CATEGORY: {category}\n\nALLOWED sub_type values:\n{voc}\n\n{wt}\n\nPRODUCTS (id, maker, name, specs):\n" + "\n".join(lines)
            + "\n\nReturn the JSON now.")


def validate(env: dict, ids: set, category: str) -> tuple[dict, list]:
    c = category.strip().lower()
    out, problems = {}, []
    for it in env.get("items") or []:
        if not isinstance(it, dict):
            continue
        i = str(it.get("id"))
        if i not in ids or i in out:
            problems.append(f"bad or repeated id {i}")
            continue
        st = str(it.get("sub_type") or "unknown").strip().lower()
        if st not in VOCAB[c]:
            st = "unknown"
        wc = str(it.get("weight_class") or "unknown").strip()
        bands = WEIGHT[c]
        wc = "n/a" if bands == NA else (wc if wc in bands else "unknown")

        def num(x):
            try:
                v = float(x)
                return v if v > 0 else None
            except (TypeError, ValueError):
                return None
        out[i] = {"sub_type": st, "calibre_mm": num(it.get("calibre_mm")), "barrel_cal": num(it.get("barrel_cal")), "weight_class": wc,
                  "reason": (str(it.get("reason") or "").strip()[:300] or None)}
    return out, problems


def pick_specs(raws: list, dic: dict, freq: dict, limit: int = 8) -> list:
    """Up to `limit` 'label: value' strings: dictionary-comparable specs first (most common keys first), then the first others."""
    from prompts.matchup_code import norm_label, clean_label
    scored, rest = [], []
    for r in raws:
        if r.text in (None, ""):
            continue
        ki = dic.get(norm_label(r.label))
        s = f"{clean_label(r.label)}: {str(r.text)[:50]}" + (f" {r.unit}" if r.unit and r.text and r.unit not in str(r.text) else "")
        (scored if ki is not None and ki.comparable else rest).append((-freq.get(ki.key, 0) if ki else 0, s))
    scored.sort(key=lambda t: t[0])
    return [s for _, s in scored][:limit] + [s for _, s in rest][: max(0, min(3, limit - len(scored)))]


def classify_products(conn, only: str | None, dry: bool, budget, redo: bool = False) -> dict:
    """Classify every product that can take part in a pair (category with a client product, has specs). Resumable."""
    import psycopg2.extras
    from collections import Counter
    from prompts import matchup_code as mc
    cur = conn.cursor()
    by_label, _ = mc.load_dictionary(cur)
    freq = Counter()
    for c, d in by_label.items():
        for ki in d.values():
            if ki.comparable:
                freq[ki.key] += 1
    cur.execute("""SELECT DISTINCT category FROM staging.client_product WHERE category IS NOT NULL""")
    cats = {r["category"].strip().lower(): r["category"].strip() for r in cur.fetchall() if r["category"].strip().lower() not in mc.SKIP_CATEGORIES}
    cats = {k: v for k, v in cats.items() if k in VOCAB and (not only or k == only.strip().lower())}
    cl_raw, co_raw = mc.load_specs(cur, set(cats))
    cur.execute("""SELECT 'client' AS side, p.client_product_id::text AS pid, lower(trim(p.category)) AS cat, NULL AS maker, p.product_name AS name
                   FROM staging.client_product p WHERE EXISTS (SELECT 1 FROM staging.client_product_specification s WHERE s.client_product_id = p.client_product_id)
                   UNION ALL
                   SELECT 'competitor', p.product_id::text, lower(trim(p.category)), c.display_name, p.product_name
                   FROM staging.competitive_product p LEFT JOIN staging.competitive_competitor c USING (competitor_id)
                   WHERE EXISTS (SELECT 1 FROM staging.competitive_product_specification s WHERE s.product_id = p.product_id)""")
    prods = [dict(r) for r in cur.fetchall() if r["cat"] in cats]
    cur.execute("SELECT product_side, product_id FROM staging.product_class")
    have = {(r["product_side"], r["product_id"]) for r in cur.fetchall()}
    stats = {}
    for cat, name in sorted(cats.items()):
        todo = [p for p in prods if p["cat"] == cat and (redo or (p["side"], p["pid"]) not in have)]
        todo.sort(key=lambda p: (p["side"] != "client", p["name"].lower()))
        batches = [todo[i:i + BATCH_PRODUCTS] for i in range(0, len(todo), BATCH_PRODUCTS)]
        print(f"[{name}] products to classify {len(todo)} in {len(batches)} calls", flush=True)
        stats[name] = {"todo": len(todo), "calls": len(batches)}
        if dry:
            continue
        for bi, batch in enumerate(batches, 1):
            items = []
            for p in batch:
                raws = (cl_raw if p["side"] == "client" else co_raw).get(int(p["pid"]) if p["side"] == "client" else p["pid"], [])
                items.append({"id": f"{'C' if p['side'] == 'client' else 'K'}{len(items) + 1}", "maker": p["maker"], "name": p["name"][:120],
                              "specs": pick_specs(raws, by_label[cat], freq), "_p": p})
            ids = {it["id"] for it in items}
            env = mc.call(budget, f"classify {name} {bi}/{len(batches)}", SYSTEM, prompt_for(name, items))
            got, _ = validate(env, ids, name)
            miss = [it for it in items if it["id"] not in got]
            if miss:
                print(f"  {len(miss)} of {len(items)} missing; re-asking once", flush=True)
                env2 = mc.call(budget, f"classify {name} {bi} gaps", SYSTEM, prompt_for(name, miss))
                g2, _ = validate(env2, {it["id"] for it in miss}, name)
                got.update(g2)
            rows = []
            for it in items:
                g = got.get(it["id"]) or {"sub_type": "unknown", "calibre_mm": None, "barrel_cal": None,
                                            "weight_class": "n/a" if WEIGHT[cat] == NA else "unknown", "reason": "no model answer"}
                p = it["_p"]
                rows.append((p["side"], p["pid"], name, g["sub_type"], g["calibre_mm"], g["barrel_cal"], g["weight_class"], g["reason"],
                             mc.MODEL if it["id"] in got else "code:no_answer"))   # a row the model did not answer is not the model's
            psycopg2.extras.execute_values(cur, """INSERT INTO staging.product_class
                (product_side, product_id, category, sub_type, calibre_mm, barrel_cal, weight_class, reason, model) VALUES %s
                ON CONFLICT (product_side, product_id) DO UPDATE SET category = EXCLUDED.category, sub_type = EXCLUDED.sub_type,
                  calibre_mm = EXCLUDED.calibre_mm, barrel_cal = EXCLUDED.barrel_cal, weight_class = EXCLUDED.weight_class,
                  reason = EXCLUDED.reason, model = EXCLUDED.model, created_at = now()""", rows)
            from prompts.derive_comp import qualify_competitors      # product lines changed: re-test every competitor
            qualify_competitors(conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))
            conn.commit()
    return stats


ROLE_SYSTEM = """You sort defence products by role so that only like-for-like products are compared. All products given share one
category and sub-type; you choose each one's ROLE from the allowed list (what it is built to do, or its style / configuration).
Use the product's name, maker and specs; where the name is a well-known system you may use your general knowledge of what it is.
When the product is not clearly one of the roles, answer "unknown" (it is then not compared). Reply with JSON only:
{"items": [{"id": "<id>", "role": "<one allowed role or unknown>", "reason": "<one short sentence>"}, ...]}  One item per id."""
ROLE_BATCH = 40


def classify_roles(conn, only: str | None, dry: bool, budget, redo: bool = False) -> dict:
    """Fill product_class.role for the products of the sub-types in ROLES (one call per sub-type batch). Resumable."""
    import psycopg2.extras
    from prompts import matchup_code as mc
    cur = conn.cursor()
    by_label, _ = mc.load_dictionary(cur)
    cur.execute("""SELECT pc.product_side AS side, pc.product_id AS pid, lower(pc.category) AS cat, pc.sub_type, pc.role,
                          coalesce(cp.product_name, kp.product_name) AS name, c.display_name AS maker
                   FROM staging.product_class pc
                   LEFT JOIN staging.client_product cp ON pc.product_side = 'client' AND cp.client_product_id::text = pc.product_id
                   LEFT JOIN staging.competitive_product kp ON pc.product_side = 'competitor' AND kp.product_id::text = pc.product_id
                   LEFT JOIN staging.competitive_competitor c ON c.competitor_id = kp.competitor_id""")
    rows = [dict(r) for r in cur.fetchall() if (r["cat"], r["sub_type"]) in ROLES and r["name"] and (redo or not r["role"])
            and (not only or r["cat"] == only.strip().lower())]
    cl_raw, co_raw = mc.load_specs(cur, {r["cat"] for r in rows})
    stats = {}
    for (cat, st), roles in ROLES.items():
        todo = sorted((r for r in rows if (r["cat"], r["sub_type"]) == (cat, st)), key=lambda r: (r["side"] != "client", r["name"].lower()))
        batches = [todo[i:i + ROLE_BATCH] for i in range(0, len(todo), ROLE_BATCH)]
        print(f"[{cat} / {st}] products without a role {len(todo)} in {len(batches)} calls", flush=True)
        stats[f"{cat}/{st}"] = {"todo": len(todo), "calls": len(batches)}
        if dry:
            continue
        allowed = "\n".join(f"  {k}: {v}" for k, v in roles.items())
        for bi, batch in enumerate(batches, 1):
            items = {}
            for r in batch:
                raws = (cl_raw if r["side"] == "client" else co_raw).get(int(r["pid"]) if r["side"] == "client" else r["pid"], [])
                items[f"{'C' if r['side'] == 'client' else 'K'}{len(items) + 1}"] = (r, pick_specs(raws, by_label.get(cat, {}), {}))
            prompt = (f"CATEGORY: {cat} / SUB-TYPE: {st}\n\nALLOWED roles:\n{allowed}\n\nPRODUCTS (id, maker, name, specs):\n"
                      + "\n".join(f"{i}\t{r['maker'] or '-'}\t{r['name'][:120]}\t{'; '.join(sp) or '(no specs)'}" for i, (r, sp) in items.items())
                      + "\n\nReturn the JSON now.")
            try:
                env = mc.call(budget, f"roles {cat}/{st} {bi}/{len(batches)}", ROLE_SYSTEM, prompt)
            except RuntimeError as e:
                print(f"  skipped: {e}", flush=True)
                continue
            got = {str(it.get("id")): it for it in env.get("items") or [] if isinstance(it, dict)}
            out = []
            for i, (r, _sp) in items.items():
                role = str((got.get(i) or {}).get("role") or "").strip().lower()
                role = role if role in roles else None                    # unknown / invalid / missing: no role, the product does not pair
                out.append((role, r["side"], r["pid"]))
            psycopg2.extras.execute_values(cur, "UPDATE staging.product_class pc SET role = v.role FROM (VALUES %s) AS v(role, side, pid) "
                                                "WHERE pc.product_side = v.side AND pc.product_id = v.pid", out)
            conn.commit()
            stats[f"{cat}/{st}"]["roled"] = stats[f"{cat}/{st}"].get("roled", 0) + sum(1 for o in out if o[0])
    return stats


def load_classes(cur) -> dict:
    """{(side, product_id text): {'sub_type', 'calibre_mm', 'barrel_cal', 'weight_class', 'role'}}"""
    cur.execute("SELECT product_side, product_id, sub_type, calibre_mm, barrel_cal, weight_class, role FROM staging.product_class")
    return {(r["product_side"], r["product_id"]): {"sub_type": r["sub_type"], "calibre_mm": r["calibre_mm"], "barrel_cal": r["barrel_cal"],
                                                   "weight_class": r["weight_class"], "role": r["role"]} for r in cur.fetchall()}


def _selftest() -> None:
    from decimal import Decimal as D
    assert set(VOCAB) == set(WEIGHT)
    for c, w in WEIGHT.items():
        assert w == NA or len(set(w)) == len(w) >= 4
    howA = {"sub_type": "self_propelled_tracked", "calibre_mm": D("155"), "barrel_cal": D("52"), "weight_class": "over 40 t"}
    sp = lambda **k: {**howA, **k}
    A = "artillery"
    assert gate(A, {**howA, "weight_class": "20-40 t"}, {**howA, "weight_class": "over 40 t", "barrel_cal": D("45")})      # adjacent bands
    assert not gate(A, {**howA, "weight_class": "5-20 t"}, {**howA, "weight_class": "over 40 t"})                          # two bands apart
    assert not gate(A, sp(sub_type="mortar"), sp(sub_type="towed_howitzer"))                                               # sub-type differs
    assert not gate(A, sp(sub_type="unknown"), sp(sub_type="unknown"))                                                     # unknown never pairs
    assert not gate(A, sp(sub_type="not_in_vocab"), sp(sub_type="not_in_vocab"))
    assert not gate(A, sp(calibre_mm=D("155")), sp(calibre_mm=D("105")))                                                   # different calibre
    assert not gate(A, sp(calibre_mm=None), sp(calibre_mm=D("155")))                                                       # calibre needed, missing
    assert not gate(A, sp(calibre_mm=D("155"), barrel_cal=D("39")), sp(calibre_mm=D("155"), barrel_cal=D("52")))           # 155/39 vs 155/52: not adjacent
    assert gate(A, sp(calibre_mm=D("155"), barrel_cal=D("45")), sp(calibre_mm=D("155"), barrel_cal=D("52")))               # 45 vs 52: adjacent
    tw = {"sub_type": "towed_howitzer", "calibre_mm": D("155"), "barrel_cal": D("39"), "weight_class": "5-20 t"}
    assert gate(A, {**tw, "role": "standard_towed"}, {**tw, "role": "standard_towed"})
    assert not gate(A, {**tw, "role": "ultralight_towed"}, {**tw, "role": "standard_towed"})                             # ULH vs a 15 t gun
    assert not gate(A, {**tw, "role": None}, {**tw, "role": None})                                                       # role needed here
    U = "uavs & drones"
    mr = {"sub_type": "multirotor_large", "weight_class": "25-150 kg"}
    assert not gate(U, {**mr, "role": "isr_surveillance"}, {**mr, "role": "armed_strike"}) and gate(U, {**mr, "role": "armed_strike"}, {**mr, "role": "armed_strike"})
    assert not gate(A, sp(weight_class="unknown"), sp(weight_class="20-40 t"))
    assert gate(A, sp(weight_class="unknown"), sp(weight_class="20-40 t"), relaxed_weight=True)
    assert gate(A, sp(sub_type="support_equipment", calibre_mm=None), sp(sub_type="support_equipment", calibre_mm=None))   # calibre exempt
    SA = "small arms"
    h = {"sub_type": "assault_rifle", "calibre_mm": D("5.56"), "weight_class": "3-6 kg"}
    assert gate(SA, h, {**h, "calibre_mm": D("5.56")}) and not gate(SA, h, {**h, "calibre_mm": D("5.45")}) and not gate(SA, h, {**h, "sub_type": "handgun"})
    assert gate("uavs & drones", {"sub_type": "nano_micro", "weight_class": "under 2 kg"}, {"sub_type": "nano_micro", "weight_class": "2-25 kg"})
    assert not gate("uavs & drones", {"sub_type": "multirotor_small", "weight_class": "under 2 kg"}, {"sub_type": "multirotor_small", "weight_class": "25-150 kg"})
    assert gate("ammunition", {"sub_type": "artillery_ammo", "calibre_mm": D("155"), "weight_class": "n/a"}, {"sub_type": "artillery_ammo", "calibre_mm": D("155.0"), "weight_class": "n/a"})
    assert basis("Artillery", howA, {**howA, "barrel_cal": D("39")}) == \
        "Like-for-like: Artillery / self propelled tracked / 155 mm (barrel 52 vs 39 cal), weight class over 40 t"
    assert basis("Ammunition", {"sub_type": "tank_gun_ammo", "calibre_mm": D("120"), "weight_class": "n/a"}, {"sub_type": "tank_gun_ammo", "calibre_mm": D("120"), "weight_class": "n/a"}) == \
        "Like-for-like: Ammunition / tank gun ammo / 120 mm"
    ok, bad = validate({"items": [{"id": "C1", "sub_type": "Mortar", "calibre_mm": "81", "weight_class": "1-5 t", "reason": "r"},
                                  {"id": "K2", "sub_type": "spaceship", "weight_class": "huge"}, {"id": "Z9", "sub_type": "mortar"}]}, {"C1", "K2"}, "Artillery")
    assert ok["C1"]["sub_type"] == "mortar" and ok["C1"]["calibre_mm"] == 81 and ok["K2"]["sub_type"] == "unknown" and ok["K2"]["weight_class"] == "unknown" and len(bad) == 1
    assert "mortar" in prompt_for("Artillery", [{"id": "C1", "maker": None, "name": "X", "specs": ["Range: 5 km"]}])
    print("matchup_class selftest ok")


if __name__ == "__main__":
    _selftest()
