"""Sub-types for the categories the matchup classifier has no vocabulary for, so "Compare any two" can offer only products that
can face each other (owner 2026-10-25: "if I choose F-35, that's an aircraft, so the versus list should only list the aircraft
that can fight with it"). Local model (Ollama, this PC, no cost); checked by code.

    python -m backend.versus_class --selftest
    python -m backend.versus_class [--limit N] [--dry-run] [--redo <category>] [--model gemma4-26b-gpu]

Writes staging.product_class rows (sub_type, weight_class 'n/a', model 'local:<model>') for competitor products in VOCAB's
categories that have no row yet. Never overwrites a row (the matchup classifier's rows stay as they are). No client product is
in these categories, so the matchup engine (prompts/matchup_code.py: same category + same sub_type) makes no new pair from them.
Code keeps an answer only if its sub_type is in the category's VOCAB; anything else is left unclassified.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
BATCH = 20
VOCAB = {
    "aircraft & aerostructures": {
        "fighter_multirole": "fighter, multirole combat jet, strike aircraft",
        "trainer_light_combat": "jet or turboprop trainer, light attack / light combat aircraft",
        "transport_tanker": "transport / airlifter, aerial tanker, and their special-operations or rescue versions",
        "special_mission_aircraft": "maritime patrol, ISR, AEW&C, electronic warfare or signals aircraft",
        "attack_helicopter": "attack or armed reconnaissance helicopter",
        "utility_helicopter": "utility, transport, rescue or heavy-lift helicopter",
        "maritime_helicopter": "naval / anti-submarine / maritime helicopter",
        "light_civil_aircraft": "light utility, civil, business or firefighting aircraft",
        "engine_avionics": "aircraft engine, propulsion, avionics, radar or mission system sold on its own (not a whole aircraft)",
        "aerostructure_part": "aircraft structure or part sold on its own (wings, fuselage sections, doors, landing gear, a work share)",
        "aircraft_upgrade_mro": "aircraft upgrade, retrofit, maintenance, fleet support or training service",
    },
    "c4isr, comms & ew": {
        "tactical_radio": "tactical / handheld / manpack / vehicle radio",
        "satcom": "satellite communication terminal or system",
        "battle_management_c2": "command and control, battle management, mission or fire-control software / system",
        "electronic_warfare": "jammer, electronic attack or protection, decoy, countermeasure system",
        "sigint_esm": "signals intelligence, COMINT / ELINT, ESM, direction finding",
        "datalink_network": "tactical data link, network, router, encryption device",
        "navigation_identification": "navigation, timing, GPS / inertial system, IFF",
        "cyber_it": "cyber security, IT, software or data product",
    },
    "sensors & electro-optics": {
        "radar": "radar of any kind",
        "eo_ir_gimbal": "stabilised EO/IR turret, gimbal or surveillance camera system",
        "weapon_sight_fcs": "weapon sight, fire-control system, gunner / commander sight",
        "night_vision_thermal": "night vision goggles, handheld or clip-on thermal imager",
        "laser_rangefinder_designator": "laser rangefinder, laser designator, laser target pointer",
        "sonar_underwater": "sonar or underwater acoustic sensor",
        "other_sensor": "another sensor (CBRN, acoustic gunshot, seismic, meteorological ...)",
    },
    "training & simulation": {
        "simulator": "simulator (flight, driving, gunnery, tactical)",
        "live_training_system": "live training system, laser engagement (MILES), range, target system",
        "training_service": "training given as a service, courses, training centre",
    },
}

SYSTEM = """You sort defence products into sub-types. For EACH row pick the ONE sub-type key from the list given for its category,
from the row's name and description only. A whole platform type (fighter, helicopter, ship ...) is only for the platform itself:
an engine, part, upgrade or service FOR that platform takes its own key. If none fits, answer "unknown".
Return JSON: {"rows": [{"id": "<the row id exactly>", "sub_type": "<key>", "reason": "<max 12 words>"}]} with one entry per row."""


def ask(model: str, category: str, rows: list[dict]) -> list[dict]:
    keys = "\n".join(f'  "{k}": {v}' for k, v in VOCAB[category].items())
    text = f"Category: {category}\nSub-types:\n{keys}\n\n" + "\n".join(
        f"ROW id={r['id']} | name: {r['name']} | description: {' '.join(str(r['description'] or '').split())[:400]}" for r in rows)
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_predict": 3000},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(json.load(r)["message"]["content"])
    return out.get("rows") or [] if isinstance(out, dict) else []


def check(answer: dict, category: str) -> str | None:
    """the sub_type when it may be stored, else None"""
    st = str(answer.get("sub_type") or "").strip().lower()
    return st if st in VOCAB.get(category, {}) else None


def run(model: str, limit: int | None, dry: bool, redo: str | None = None) -> None:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    if redo:                                             # only this tool's own rows, never the matchup classifier's
        cur.execute("DELETE FROM staging.product_class WHERE product_side = 'competitor' AND model LIKE 'local:%%' AND category = %s",
                    (redo,))
        print(f"redo {redo}: {cur.rowcount} rows cleared")
    cur.execute(f"""SELECT p.product_id::text AS id, p.product_name AS name, p.description, lower(trim(p.category)) AS category
                    FROM staging.competitive_product p
                    LEFT JOIN staging.product_class pc ON pc.product_side = 'competitor' AND pc.product_id = p.product_id::text
                    WHERE pc.product_id IS NULL AND lower(trim(p.category)) = ANY(%s)
                    ORDER BY 4, 2 {'LIMIT %s' if limit else ''}""", [list(VOCAB)] + ([limit] if limit else []))
    rows = [dict(r) for r in cur.fetchall()]
    tally = {"kept": 0, "unsure": 0}
    for category in VOCAB:
        todo = [r for r in rows if r["category"] == category]
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            by_id = {r["id"]: r for r in batch}
            try:
                answers = ask(model, category, batch)
            except Exception as e:  # noqa: BLE001
                print(f"  {category} batch {i // BATCH + 1}: model error {e}")
                tally["unsure"] += len(batch)
                continue
            for a in answers:
                r = by_id.pop(str(a.get("id") or "").strip(), None)
                if not r:
                    continue
                st = check(a, category)
                if not st:
                    tally["unsure"] += 1
                    continue
                tally["kept"] += 1
                print(f"  {st:28} | {r['name'][:70]}")
                if not dry:
                    cur.execute("""INSERT INTO staging.product_class (product_side, product_id, category, sub_type, weight_class, reason, model)
                                   VALUES ('competitor', %s, %s, %s, 'n/a', %s, %s) ON CONFLICT (product_side, product_id) DO NOTHING""",
                                (r["id"], category, st, str(a.get("reason") or "")[:300], f"local:{model}"))
            tally["unsure"] += len(by_id)
            if not dry:
                conn.commit()
            print(f"{category} batch {i // BATCH + 1}/{(len(todo) + BATCH - 1) // BATCH}: {tally}", flush=True)
    if dry:
        conn.rollback()


def _selftest() -> None:
    assert check({"sub_type": "Fighter_Multirole"}, "aircraft & aerostructures") == "fighter_multirole"
    assert check({"sub_type": "radar"}, "aircraft & aerostructures") is None          # not this category's key
    assert check({"sub_type": "unknown"}, "sensors & electro-optics") is None
    assert check({}, "training & simulation") is None
    print("versus_class self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default="gemma4-26b-gpu")
    ap.add_argument("--redo", choices=list(VOCAB), help="classify this category's rows (this tool's own) again")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    run(a.model, a.limit, a.dry_run, a.redo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
