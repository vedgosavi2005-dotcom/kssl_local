"""Give the KSSL products that still have no sub-type one (so `subtype_match` in the signal prompt can be decided).

    python -m prompts.client_subtype --selftest        (no DB, no model)
    python -m prompts.client_subtype --dry-run         (show what would be written)
    python -m prompts.client_subtype                   (write staging.product_class rows; AI only for what the name rules cannot tell)

A client product has a sub-type when staging.product_class holds a valid one for it (vocabulary: prompts/matchup_class.VOCAB) or
client_product.subcategory is set. For the rest: 1. a ventures / MoU / subsidiary / capability row is left alone (it is not a product,
render.py already moves it to the capabilities block); 2. NAME RULES below (code, free) decide the clear cases; 3. whatever is left
is classified by one small model call with matchup_class's own prompt and validator (unknown stays unknown: nothing is invented).
Categories without a vocabulary (Other) are never classified. Local kssl_staging only.
"""

from __future__ import annotations

import os
import re
import sys

from prompts import matchup_class as mc

CODE_MODEL = "code:name_rules"

# (category lower-case, regex on the product name, sub_type, why). First match wins.
RULES = [
    ("marine / naval", r"underwater vehicle|\bAUV\b|\bUUV\b|\bunmanned underwater\b", "unmanned_vessel", "name says it is an underwater vehicle"),
    ("uavs & drones", r"jet[- ]powered UAV", "ucav", "name says it is a jet-powered UAV (vocabulary: combat / jet-powered UAV, target drone)"),
    ("uavs & drones", r"^loitering munition|\bloitering munition\b(?!s)", "loitering_munition", "name says it is a loitering munition"),
    ("ammunition", r"\bfuz(e|es|ing)\b", "fuze_component", "name says it is a fuze / fuzing system"),
    ("ammunition", r"\bartillery shells?\b|\bready-to-fill shells?\b", "artillery_ammo", "name says artillery shells"),
    ("missiles & air defence", r"^air defence guns", "gun_air_defence", "name says air defence guns"),
    ("marine / naval", r"steering gear|shafting|rudder stock|marine mechanical", "unknown", "ship component; no sub-type in the vocabulary fits (not a sensor or weapon)"),
    ("armoured vehicle mro", r"\b(spares|driveline|powertrain|running gear)\b", "support_service", "spares / component support for armoured vehicles"),
]
# a row that is a venture, collaboration or capability rather than a product (render.py keeps these out of the portfolio)
NOT_A_PRODUCT = re.compile(r"\b(joint venture|JV|MoU|subsidiary|co-development|collaboration|partnership|transfer-of-technology|capability|complex)\b"
                           r"|^(ACIL|Aegis|Aeron|BFIL|Eternus|Zorya|Bharat Forge Aerospace|Agneyastra|KSSL Artificial)", re.I)


def by_rules(category: str, name: str):
    """(sub_type, why) or None."""
    cat = (category or "").strip().lower()
    if NOT_A_PRODUCT.search(name or "") and not re.search(r"^air defence guns", name or "", re.I):
        return None
    for c, rx, st, why in RULES:
        if c == cat and re.search(rx, name or "", re.I) and (st == "unknown" or st in mc.VOCAB.get(cat, {})):
            return st, why
    return None


def weight_for(category: str) -> str:
    cat = category.strip().lower()
    return "n/a" if mc.WEIGHT.get(cat) == mc.NA else "unknown"


def _selftest() -> None:
    assert by_rules("Marine / Naval", "MRAUV - Mine Reconnaissance Autonomous Underwater Vehicle")[0] == "unmanned_vessel"
    assert by_rules("UAVs & Drones", "Omega Nine (jet-powered UAV)")[0] == "ucav"
    assert by_rules("UAVs & Drones", "Omega One (ISR UAS)") is None                                     # size unknown: left to the model
    assert by_rules("Ammunition", "Fuzing systems for artillery and bombs (Kalyani - Junghans Defence) (Collaboration)") is None   # a collaboration
    assert by_rules("Ammunition", "Fuzing systems for bombs")[0] == "fuze_component"
    assert by_rules("Missiles & Air Defence", "Air Defence Guns and Ammunition (Kalyani Group - BAE Systems transfer-of-technology partnership)")[0] == "gun_air_defence"
    assert by_rules("Missiles & Air Defence", "KSSL-IAI joint venture: selected air defence systems") is None
    assert by_rules("Armoured Vehicle MRO", "Driveline (gearbox)")[0] == "support_service" and by_rules("Other", "Driveline") is None
    assert weight_for("Ammunition") == "n/a" and weight_for("Artillery") == "unknown"
    print("client_subtype self-check ok")


def candidates(cur) -> list[dict]:
    cur.execute("""SELECT p.client_product_id::text AS pid, p.product_name AS name, p.category, p.subcategory, c.sub_type
                   FROM staging.client_product p
                   LEFT JOIN staging.product_class c ON c.product_side = 'client' AND c.product_id = p.client_product_id::text
                   ORDER BY p.category, p.product_name""")
    out = []
    for r in cur.fetchall():
        cat = (r["category"] or "").strip().lower()
        if cat not in mc.VOCAB:
            continue
        if r["sub_type"] in mc.VOCAB[cat] or (r["subcategory"] or "").strip() in mc.VOCAB[cat]:
            continue
        out.append(dict(r))
    return out


def run(dry_run: bool = False) -> dict:
    import psycopg2
    import psycopg2.extras
    from prompts import matchup_code
    from prompts.claude_call import call_model
    conn = psycopg2.connect(os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging")
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    cur = conn.cursor()
    todo = candidates(cur)
    rows, left = [], []
    for p in todo:
        hit = by_rules(p["category"], p["name"])
        if hit:
            rows.append((p, hit[0], None, None, weight_for(p["category"]), hit[1], CODE_MODEL))
        elif not NOT_A_PRODUCT.search(p["name"]):
            left.append(p)
    report = {"candidates": len(todo), "by_rules": len(rows), "left_for_model": len(left), "model": 0, "unknown_after": 0, "cost": 0.0, "rows": []}
    # the model, for genuine products the name rules cannot place (one call per category)
    for cat in sorted({p["category"] for p in left}):
        grp = [p for p in left if p["category"] == cat]
        cl = matchup_code.load_specs(cur, {cat.strip().lower()})[0]
        items = [{"id": f"C{i}", "maker": None, "name": p["name"][:120], "specs": [f"{r.label}: {str(r.text)[:50]}" for r in cl.get(int(p["pid"]), []) if r.text][:8], "_p": p}
                 for i, p in enumerate(grp, 1)]
        res = call_model(mc.SYSTEM, mc.prompt_for(cat, items), matchup_code.MODEL, False)
        report["cost"] += res.cost_usd or 0
        import json
        try:
            env = json.loads(res.text[res.text.find("{"):res.text.rfind("}") + 1])
        except ValueError:
            env = {}
        got, _ = mc.validate(env, {it["id"] for it in items}, cat)
        for it in items:
            g = got.get(it["id"]) or {"sub_type": "unknown", "calibre_mm": None, "barrel_cal": None, "weight_class": weight_for(cat), "reason": "no model answer"}
            rows.append((it["_p"], g["sub_type"], g["calibre_mm"], g["barrel_cal"], g["weight_class"], g["reason"],
                         matchup_code.MODEL if it["id"] in got else "code:no_answer"))   # a row the model did not answer is not the model's
            report["model"] += 1
    for p, st, cal, bar, wc, why, model in rows:
        report["rows"].append((p["name"][:60], p["category"], st, model))
        report["unknown_after"] += st == "unknown"
    if not dry_run and rows:
        psycopg2.extras.execute_values(cur, """INSERT INTO staging.product_class (product_side, product_id, category, sub_type, calibre_mm, barrel_cal, weight_class, reason, model)
            VALUES %s ON CONFLICT (product_side, product_id) DO UPDATE SET category = EXCLUDED.category, sub_type = EXCLUDED.sub_type,
              calibre_mm = EXCLUDED.calibre_mm, barrel_cal = EXCLUDED.barrel_cal, weight_class = EXCLUDED.weight_class, reason = EXCLUDED.reason,
              model = EXCLUDED.model, created_at = now()""",
                                        [("client", p["pid"], p["category"], st, cal, bar, wc, why, model) for p, st, cal, bar, wc, why, model in rows])
        cur.execute("""INSERT INTO staging.prompt_run (prompt_id, prompt_version, subject_key, model, status, cost_usd, rows_loaded, details)
                       VALUES ('client_subtype', '1', 'client_products', %s, 'loaded', %s, %s, '{}'::jsonb)""", (matchup_code.MODEL, report["cost"], len(rows)))
        from prompts.derive_comp import qualify_competitors      # client product lines changed: re-test every competitor
        qualify_competitors(cur)
        conn.commit()
    else:
        conn.rollback()
    return report


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--selftest" in sys.argv:
        _selftest()
    else:
        r = run("--dry-run" in sys.argv)
        print({k: v for k, v in r.items() if k != "rows"})
        for x in r["rows"]:
            print("  ", x)
