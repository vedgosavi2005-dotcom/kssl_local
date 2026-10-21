"""Translate tender titles and descriptions to English with the local LLM (Ollama on this PC; no cloud cost).

    python -m backend.translate_market --selftest
    python -m backend.translate_market [--limit N] [--model gemma4-26b-gpu] [--dry-run] [--fields | --all]

Per tender not yet processed (text_lang IS NULL): an English title (stop words, no non-Latin script) is marked text_lang = 'en' with no
model call. Otherwise the model returns {lang, title_en, description_en}; code checks that every number of the original survives in
the translation (a dropped figure rejects it), then keeps the original in title_localized / description_localized and writes the English
into title / description. Re-runnable; only unprocessed rows are touched.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
DESC_MAX = 2500
EN_WORDS = {"the", "of", "and", "for", "supply", "to", "with", "in", "procurement", "purchase", "services", "maintenance", "spare", "parts",
            "repair", "ammunition", "vehicle", "vehicles", "system", "systems", "equipment", "contract", "framework", "agreement", "delivery",
            "acquisition", "provision", "support", "training", "rifle", "gun", "type", "set", "kit", "assembly"}

# function words of the tender languages (de, fr, es, it, pt, nl, pl, cs, sk, sl, lv, lt, et, ro, hr, da, sv, fi); one is enough to call
# a title foreign unless English words outnumber them
FOREIGN_WORDS = {"der", "die", "das", "und", "fur", "von", "mit", "zur", "zum", "des", "les", "la", "le", "du", "et", "pour", "aux", "una",
                 "el", "los", "las", "del", "para", "y", "con", "di", "della", "delle", "il", "per", "e", "do", "da", "dos", "das", "em",
                 "het", "van", "voor", "een", "en", "na", "za", "w", "z", "dla", "oraz", "pro", "nakup", "dostawa", "sklop", "zakup",
                 "dodavka", "naboji", "un", "ir", "ar", "ja", "ning", "si", "de", "och", "av", "til", "og", "hankinta", "ja", "lot",
                 "salve", "topovske", "ostatni", "kalibra", "bise", "acquisto", "fornitura", "fornecimento", "suministro", "acuerdo", "marco",
                 "accord", "cadre", "aanschaf", "onderhoud", "beschaffung", "lieferung", "rahmenvertrag", "ersatzteile"}
ENGLISH_COUNTRIES = {"India", "United Kingdom", "United States", "Ireland", "Canada", "Australia", "New Zealand", "Singapore", "Malta", None}
SYSTEM = """You translate defence procurement notices into plain English for analysts. Return JSON:
 "lang": the ISO 639-1 code of the original language,
 "title_en": the title in English,
 "description_en": the description in English (empty string if none was given).
Keep every number, code, reference, calibre, unit and part number exactly as written. Keep proper names (ministries, places,
companies) in their usual English form. Do not add, explain or summarise: translate."""


def looks_english(text: str) -> bool:
    t = str(text or "")
    if re.search(r"[Ѐ-ӿͰ-Ͽ֐-׿؀-ۿ一-鿿฀-๿]", t):   # Cyrillic, Greek, Hebrew, Arabic, CJK, Thai
        return False
    if re.search(r"[àâçéèêëîïôûùüÿñæœäöüßąćęłńóśźżčďěňřšťůžőűåøÁÉÍÓÚ]", t, re.I):
        return False
    words = re.findall(r"[a-z]+", t.lower())
    foreign = sum(w in FOREIGN_WORDS for w in words)
    return foreign == 0 or sum(w in EN_WORDS for w in words) > foreign     # codes / English words only: nothing to translate


def numbers(text: str) -> set:
    return set(re.findall(r"\d+(?:[.,]\d+)*", str(text or "")))


def numbers_kept(orig: str, trans: str) -> bool:
    norm = lambda s: {n.replace(",", ".") for n in numbers(s)}  # noqa: E731
    return norm(orig) <= norm(trans) | {n.replace(".", "") for n in norm(trans)}


def ask(model: str, title: str, desc: str) -> dict:
    user = f"TITLE: {title}\nDESCRIPTION: {(desc or '')[:DESC_MAX]}"
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_predict": 1500},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(json.load(r)["message"]["content"])


# ---- --fields: the other displayed market cells (2026-10-22, owner: "some parts are still not translated", Who wins showed ТОВ ...) ----
# (table, key column, column, kind). Award rows are rebuilt from market_tender by backend.market_rollups awards, so they follow.
# Eligibility quotes stay verbatim (they are the evidence the checks match against the document).
FIELDS = [("market_tender", "tender_id", "buyer_name", "name"), ("market_tender", "tender_id", "issuer_display", "name"),
          ("market_tender", "tender_id", "awarded_to", "name"), ("market_tender_source", "source_id", "publisher", "name"),
          ("market_tender", "tender_id", "title", "text"), ("market_tender_requirement", "requirement_id", "description", "text"),
          ("market_tender_requirement", "requirement_id", "equipment_scope", "text")]
BATCH = {"name": 25, "text": 8}
FIELD_SYSTEM = {
    "name": """You give organisation names from defence procurement notices their English form, for analysts. Input: {"items": [{"i", "text"}]}.
Return JSON {"items": [{"i", "lang", "en"}]}: lang = ISO 639-1 code of the original ("en" if already English).
Translate the generic words (ministry, military unit, agency, directorate, state enterprise; a limited liability company / ТОВ / Sp. z o.o. /
GmbH-style legal form becomes "LLC" or stays as the short legal form at the end), transliterate proper names into Latin letters (Ukrainian:
the official national transliteration), use the established English name where one exists ("Służba Ochrony Państwa" -> "State Protection
Service"), keep acronyms, numbers and codes exactly. Never add a country or anything not in the name.""",
    "text": """You translate short lines from defence procurement notices (titles, item lines, equipment scope) into plain English. Input:
{"items": [{"i", "text"}]}. Return JSON {"items": [{"i", "lang", "en"}]}: lang = ISO 639-1 code of the original ("en" if already English).
Keep every number, code, reference, calibre, unit and part number exactly as written. Do not add, explain or summarise: translate.""",
}
NON_LATIN = re.compile(r"[Ѐ-ӿͰ-Ͽ֐-׿؀-ۿ一-鿿฀-๿]")


def ask_items(model: str, kind: str, texts: list[str]) -> dict[int, dict]:
    user = json.dumps({"items": [{"i": i, "text": t[:DESC_MAX]} for i, t in enumerate(texts)]}, ensure_ascii=False)
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_predict": 4000},
            "messages": [{"role": "system", "content": FIELD_SYSTEM[kind]}, {"role": "user", "content": user}]}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(json.load(r)["message"]["content"])
    return {int(x["i"]): x for x in out.get("items", []) if isinstance(x, dict) and str(x.get("i", "")).isdigit()}


def wanted(table: str, col: str, v) -> bool:
    if not v or len(str(v).strip()) < 3:
        return False
    if (table, col) == ("market_tender", "title"):      # titles went through run(); only the non-Latin ones it rejected are left
        return bool(NON_LATIN.search(v))
    return not looks_english(v)


FIELD_MODEL = "qwen3.8-27b-32k"   # on 2026-10-22 samples it beat gemma4-26b on names ("State Solution Agency") and Latvian / Czech lines


def run_fields(model: str, dry: bool) -> None:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cells = []                                           # (table, key col, col, kind, row id, value)
    for t, k, c, kind in FIELDS:
        cur.execute(f'SELECT {k}::text AS id, "{c}" AS v FROM staging.{t} WHERE "{c}" IS NOT NULL')
        cells += [(t, k, c, kind, r["id"], r["v"]) for r in cur.fetchall() if wanted(t, c, r["v"])]
    todo = {}
    for t, k, c, kind, _, v in cells:
        todo.setdefault(v, kind)
    cur.execute("SELECT original FROM staging.text_translation WHERE original = ANY(%s)", (list(todo),))
    for r in cur.fetchall():
        todo.pop(r["original"], None)
    print(f"{len(cells)} cells to translate, {len(todo)} distinct texts not in the cache", flush=True)
    stats = {"translated": 0, "english": 0, "rejected": 0, "errors": 0}
    t0 = time.time()
    for kind in ("name", "text"):
        texts = [v for v, kd in todo.items() if kd == kind]
        for s in range(0, len(texts), BATCH[kind]):
            part = texts[s:s + BATCH[kind]]
            try:
                got = ask_items(model, kind, part)
            except Exception as e:  # noqa: BLE001
                stats["errors"] += len(part)
                print(f"  model error ({kind}, {len(part)} items): {str(e)[:120]}", flush=True)
                continue
            for i, orig in enumerate(part):
                a = got.get(i)
                if not a:
                    stats["errors"] += 1
                    continue
                en, lang = str(a.get("en") or "").strip(), str(a.get("lang") or "").strip().lower()[:8] or "xx"
                if en == orig.strip():                       # a name with no English form (Rheinmetall Waffe Munition GmbH)
                    lang = "en"
                ok = bool(en) and numbers_kept(orig, en) and (lang != "en" or not NON_LATIN.search(orig))
                stats["english" if ok and lang == "en" else "translated" if ok else "rejected"] += 1
                if not ok:
                    print(f"  REJECT {kind}: {orig[:60]} -> {en[:60]}", flush=True)
                if not dry:
                    cur.execute("""INSERT INTO staging.text_translation (original, kind, lang, english, ok, model) VALUES (%s,%s,%s,%s,%s,%s)
                                   ON CONFLICT (original) DO NOTHING""", (orig, kind, lang, en or None, ok, model))
            if not dry:
                conn.commit()
            print(f"  {kind} {s + len(part)}/{len(texts)} {time.time() - t0:.0f}s {stats}", flush=True)
    if dry:
        print(json.dumps(stats))
        return
    # apply from the cache: English into the cell, the original into text_original (kept from the first translation)
    n = 0
    for t, k, c, kind, rid, v in cells:
        cur.execute("SELECT english FROM staging.text_translation WHERE original = %s AND ok AND lang <> 'en'", (v,))
        hit = cur.fetchone()
        if not hit:
            continue
        cur.execute("""INSERT INTO staging.text_original (table_name, row_id, column_name, original, lang)
                       SELECT %s, %s, %s, %s, lang FROM staging.text_translation WHERE original = %s ON CONFLICT DO NOTHING""", (t, rid, c, v, v))
        cur.execute(f'UPDATE staging.{t} SET "{c}" = %s WHERE {k}::text = %s AND "{c}" = %s', (hit["english"], rid, v))
        n += cur.rowcount
    conn.commit()
    # tender descriptions written before the names were translated quote them ("The contract went to ТОВ ОРІОН ВОРЛД"): the same English
    # form as the Winner column, longest name first. Codes in Cyrillic letters (cable КППЭблШп-ВП, steel 60С2А) are not names and stay.
    cur.execute("SELECT original, english FROM staging.text_translation WHERE kind = 'name' AND ok AND lang <> 'en' ORDER BY length(original) DESC")
    names = [(r["original"], r["english"]) for r in cur.fetchall()]
    cur.execute("SELECT tender_id::text AS id, description FROM staging.market_tender WHERE description ~ '[Ѐ-ӿͰ-Ͽ]'")
    m = 0
    for r in cur.fetchall():
        d = r["description"]
        for o, e in names:
            d = d.replace(o, e)
        if d != r["description"]:
            cur.execute("""INSERT INTO staging.text_original (table_name, row_id, column_name, original, lang)
                           VALUES ('market_tender', %s, 'description', %s, 'names') ON CONFLICT DO NOTHING""", (r["id"], r["description"]))
            cur.execute("UPDATE staging.market_tender SET description = %s WHERE tender_id::text = %s", (d, r["id"]))
            m += 1
    conn.commit()
    print(json.dumps(stats), f"cells written: {n}", f"descriptions with names replaced: {m}", f"{time.time() - t0:.0f}s", flush=True)


def _selftest() -> None:
    assert wanted("market_tender", "buyer_name", "ВІЙСЬКОВА ЧАСТИНА 2382") and wanted("market_tender", "buyer_name", "Ministère de la Défense")
    assert not wanted("market_tender", "title", "Lot 1 - Ballistic helmets") and wanted("market_tender", "title", "Плити перекриття 44110000-4")
    assert not wanted("market_tender", "buyer_name", "Ministry of Defence")
    assert looks_english("Supply of spare parts for armoured vehicles") and looks_english("113TM53238-GEAR FORGING")
    assert not looks_english("Bezpilotní průzkumné multikoptéry UAS-VTOL - nákup") and not looks_english("«Легкові автомобілі»")
    assert not looks_english("Aanschaf en onderhoud - Terreinvoertuigen t.b.v. van Schietr") and not looks_english("Topovske salve")
    assert numbers_kept("naboji 7,62 x 51 mm, 2. sklop", "7.62 x 51 mm rounds, lot 2") and not numbers_kept("7,62 x 51", "rounds")
    print("translate_market self-check ok")


def run(model: str, limit, dry: bool) -> None:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"""SELECT tender_id, country_name, title, description FROM staging.market_tender WHERE text_lang IS NULL AND coalesce(title, '') <> ''
                    ORDER BY (status IN ('open', 'Open', 'closing', 'Closing')) DESC, published_date DESC NULLS LAST {f'LIMIT {int(limit)}' if limit else ''}""")
    rows = [dict(r) for r in cur.fetchall()]
    stats = {"rows": len(rows), "english": 0, "translated": 0, "rejected": 0, "errors": 0}
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        # an English-speaking country with an English-looking title: no model call; every other tender goes to the model, which
        # names the language itself (a word list missed "Unbemannter qualifizierter Patiententransport", 2026-10-22)
        if r.get("country_name") in ENGLISH_COUNTRIES and looks_english(r["title"]) and looks_english((r["description"] or "")[:400]):
            stats["english"] += 1
            if not dry:
                cur.execute("UPDATE staging.market_tender SET text_lang = 'en' WHERE tender_id = %s", (r["tender_id"],))
                conn.commit()
            continue
        try:
            a = ask(model, r["title"], r["description"] or "")
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            print(f"  {r['tender_id']}: model error {str(e)[:120]}", flush=True)
            continue
        te, de = str(a.get("title_en") or "").strip(), str(a.get("description_en") or "").strip()
        lang = str(a.get("lang") or "").strip().lower()[:8] or "xx"
        if not te or not numbers_kept(r["title"], te) or (r["description"] and de and not numbers_kept((r["description"] or "")[:DESC_MAX], de)):
            stats["rejected"] += 1
            print(f"  REJECT {r['tender_id']}: numbers lost | {r['title'][:60]} -> {te[:60]}", flush=True)
            continue
        if lang == "en":
            stats["english"] += 1
            if not dry:
                cur.execute("UPDATE staging.market_tender SET text_lang = 'en' WHERE tender_id = %s", (r["tender_id"],))
                conn.commit()
            continue
        stats["translated"] += 1
        if i <= 5 or i % 50 == 0:
            print(f"  [{i}/{len(rows)} {time.time() - t0:.0f}s] {lang}: {r['title'][:55]} -> {te[:70]}", flush=True)
        if not dry:
            desc_full = r["description"] or ""
            new_desc = (de + (" [translated from the first 2,500 characters]" if len(desc_full) > DESC_MAX else "")) if desc_full else None
            cur.execute("""UPDATE staging.market_tender SET title_localized = %s, description_localized = %s, title = %s, description = %s, text_lang = %s
                           WHERE tender_id = %s""", (r["title"], desc_full or None, te, new_desc, lang, r["tender_id"]))
            conn.commit()
    print(json.dumps(stats), f"{time.time() - t0:.0f}s", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--fields", action="store_true", help="the other displayed market cells (names, award / item lines); see FIELDS")
    ap.add_argument("--all", action="store_true", help="tender titles + descriptions, then --fields (the routine step)")
    ap.add_argument("--model", default="gemma4-26b-gpu")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    if not a.fields:
        run(a.model, a.limit, a.dry_run)
    if a.fields or a.all:
        run_fields(FIELD_MODEL if a.model == "gemma4-26b-gpu" else a.model, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
