"""What each competitor catalogue row really is: competitive_product.product_kind (db/setup/43), with the local model; checked by code.

    python -m backend.product_kind --selftest
    python -m backend.product_kind [--limit N] [--company <name part>] [--dry-run] [--redo] [--model gemma4-26b-gpu]

Owner 2026-10-25: "figure out what the actual products are" (the X-62A VISTA, a one-of-a-kind test aircraft, was a Lockheed
Martin product), and "you can run local AI models here, so use it". The local model (Ollama, this PC, no cost) reads each row's
name, category, status and description, a batch at a time, and answers a kind from KINDS with a short reason and a quote. Code:
  - keeps a kind only if it is one of KINDS and its quote is in the row's own name or description (case / quotes / dashes
    folded); anything else leaves the row unclassified (NULL = shown as a product), and is counted as "unsure";
  - writes product_kind, and one staging.fact_source judgement row (column product_kind: reason + quote).
Rows already classified are skipped unless --redo. Only kssl_staging; the client sees a kind after Approve.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

from prompts.spec_enrich import norm_text

OLLAMA = "http://127.0.0.1:11434/api/chat"
KINDS = ("product", "in_development", "service", "test_asset", "programme", "not_product")
BATCH = 20

SYSTEM = """You sort a defence company's catalogue rows. For EACH row decide what it is, from its name, category, status and
description only (never from what you know about it elsewhere). Kinds:
 "product": a product the company offers or that is in service or production (a system, vehicle, weapon, ammunition, component,
     variant, kit, software product). A product that is being upgraded is still a product.
 "in_development": not yet offered or fielded: concept, design study, prototype, demonstrator, in development, in trials,
     unveiled but not yet in production.
 "service": something the company does for customers rather than a thing it sells: maintenance / MRO, repair, overhaul,
     upgrade or retrofit service, painting, training service, engineering or integration service, logistics or support.
 "test_asset": a one-of-a-kind research or test vehicle or rig that is not for sale (an X-plane, a test bed, a test aircraft).
 "programme": ONLY a contract, bid, tender, competition or production plan in which no product of the company is named.
     A named ship class, vehicle, weapon or system being designed or built under a programme is "in_development" (not yet
     delivered) or "product" (delivered / in production), never "programme": e.g. "KDDX destroyer" is in_development.
 "not_product": a facility or plant, a business unit, a partnership note, an index or catalogue page, a "no products" note, or not a
     defence item. A line of manufactured parts, components, structures, forgings or subsystems that the company makes and sells
     (e.g. "155 mm projectile metal parts", "aerostructure wings", "shaft lines and propellers") is a "product", even when it names
     several items.
When unsure, answer "product".
Return JSON: {"rows": [{"id": "<the row id exactly>", "kind": "<one kind>", "reason": "<max 15 words>",
 "quote": "<the exact words from that row's name or description that show it, max 12 words>"}]} with one entry per row."""


def ask(model: str, rows: list[dict]) -> list[dict]:
    text = "\n".join(f"ROW id={r['id']} | name: {r['name']} | category: {r['category'] or '-'} | status: {r['status'] or '-'} | "
                     f"description: {' '.join(str(r['description'] or '').split())[:500]}" for r in rows)
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_predict": 3000},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(json.load(r)["message"]["content"])
    return out.get("rows") or [] if isinstance(out, dict) else []


def check(answer: dict, row: dict) -> tuple[str | None, str]:
    """(kind, why) when the answer may be stored, else (None, why not)"""
    kind = str(answer.get("kind") or "").strip().lower()
    quote = " ".join(str(answer.get("quote") or "").split())
    if kind not in KINDS:
        return None, f"unknown kind {kind!r}"
    if kind == "product":
        return kind, ""                                                    # the default needs no proof
    own = norm_text(f"{row['name']} {row['description'] or ''}")
    words = [w for w in re.findall(r"[a-z0-9]+", norm_text(quote)) if len(w) > 2]
    # the exact words, or nearly all of them: the model often re-punctuates a quote ("test bed" / "test-bed")
    if not quote or not (norm_text(quote) in own or (len(words) >= 2 and sum(w in own for w in words) / len(words) >= 0.8)):
        return None, "quote not in the row's own text"
    return kind, ""


def run(model: str, limit: int | None, company: str | None, dry: bool, redo: bool, kind: str | None = None) -> None:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"""SELECT p.product_id::text AS id, p.product_name AS name, p.category, p.status, p.description, c.display_name AS company
                    FROM staging.competitive_product p JOIN staging.competitive_competitor c USING (competitor_id)
                    WHERE (%s OR p.product_kind IS NULL) AND (%s::text IS NULL OR c.display_name ILIKE '%%' || %s || '%%')
                      AND (%s::text IS NULL OR p.product_kind = %s)
                    ORDER BY c.display_name, p.product_name {'LIMIT %s' if limit else ''}""",
                [redo, company, company, kind, kind] + ([limit] if limit else []))
    rows = [dict(r) for r in cur.fetchall()]
    tally: dict[str, int] = {k: 0 for k in KINDS} | {"unsure": 0}
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        by_id = {r["id"]: r for r in batch}
        try:
            answers = ask(model, batch)
        except Exception as e:  # noqa: BLE001
            print(f"  batch {i // BATCH + 1}: model error {e}")
            tally["unsure"] += len(batch)
            continue
        seen = set()
        for a in answers:
            r = by_id.get(str(a.get("id") or "").strip())
            if not r or r["id"] in seen:
                continue
            seen.add(r["id"])
            kind, why = check(a, r)
            if not kind:
                tally["unsure"] += 1
                print(f"  unsure  {r['company'][:18]:18} | {r['name'][:60]} ({why})")
                continue
            tally[kind] += 1
            if kind != "product":
                print(f"  {kind:14} {r['company'][:18]:18} | {r['name'][:60]} | {a.get('reason', '')[:70]}")
            if not dry:
                cur.execute("UPDATE staging.competitive_product SET product_kind = %s WHERE product_id = %s::uuid", (kind, r["id"]))
                cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_product' AND column_name = 'product_kind' "
                            "AND row_id = %s", (r["id"],))
                if kind != "product":
                    cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                                   VALUES ('competitive_product', %s, 'product_kind', 'judgement', 'judgement', %s)""",
                                (r["id"], f"{a.get('reason', '')[:200]} (\"{a.get('quote', '')[:200]}\")"))
        tally["unsure"] += len(set(by_id) - seen)
        if not dry:
            conn.commit()
        print(f"batch {i // BATCH + 1}/{(len(rows) + BATCH - 1) // BATCH}: {tally}", flush=True)
    if dry:
        conn.rollback()


def _selftest() -> None:
    row = {"name": "X-62A VISTA (AI / autonomy test aircraft)", "description": "a one-of-a-kind training/test aircraft developed by Skunk Works"}
    assert check({"kind": "test_asset", "quote": "one-of-a-kind training/test aircraft"}, row) == ("test_asset", "")
    assert check({"kind": "test_asset", "quote": "an experimental X-plane"}, row)[0] is None          # not in the row's text
    assert check({"kind": "test_asset", "quote": "one of a kind training test aircraft"}, row)[0] == "test_asset"   # re-punctuated
    assert check({"kind": "Product", "quote": ""}, row) == ("product", "")                              # the default needs no quote
    assert check({"kind": "weapon", "quote": "test aircraft"}, row)[0] is None                         # not a kind
    assert check({"kind": "service", "quote": "One-Of-A-Kind   training/test"}, row)[0] == "service"  # case and spaces folded
    print("product_kind self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo", action="store_true", help="classify rows that already have a kind again")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--company")
    ap.add_argument("--kind", help="with --redo: only rows of this kind")
    ap.add_argument("--model", default="gemma4-26b-gpu")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    run(a.model, a.limit, a.company, a.dry_run, a.redo, a.kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
