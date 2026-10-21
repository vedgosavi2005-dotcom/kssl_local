"""Cheap pre-check before the signal prompt (owner 2026-10-21: skipped signal runs cost about $0.20 each, $35 in all).

    python -m backend.signal_gate --selftest                 (no DB, no model)
    python -m backend.signal_gate [--limit N] [--dry-run]    (pending signal articles, newest first)

One Haiku call = BATCH articles (headline, publisher, tracked competitor, the first HEAD_CHARS of the stored text when there is one).
It applies the signal prompt's own three relevance tests (signal.yml STEP 1: a concrete event, a listed competitor acts, the item is in
a KSSL category or touches KSSL) and answers pass / fail per article. When unsure it passes: the full prompt still decides.
  fail -> a staging.prompt_run row for the SIGNAL prompt at its current version, status 'skipped', skip_reason 'pre-check: ...',
          cost 0, so the article is no longer pending and the full prompt never runs on it;
  pass -> a 'signal_gate' row (status 'loaded') so it is not checked again.
The gate's own spend is logged once per call (prompt_id 'signal_gate', subject 'batch-...').
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.triage_routes import MODEL, call, clean_snippet, connect

BATCH = 30
HEAD_CHARS = 1200
GATE_VERSION = "2"

SYSTEM = """You pre-screen defence news for a competitive-intelligence team whose client is KSSL (Kalyani Strategic Systems, India).
A later, careful step reads every article you pass, so you only remove articles that are CLEARLY useless. When in doubt, pass.
Fail an article only for one of these reasons:
 a) it clearly reports no event at all: a board or executive appointment, an obituary, a share price or dividend item, an opinion or
    analysis piece, a trade-show attendance notice. (Trials, tests, unveilings, bids, talks, approvals, results with orders ARE events: pass.)
 b) the tracked competitor in brackets plays no part in the event (not the maker, supplier, partner, bidder or developer of the item).
    If it makes or supplies the item in any way, pass.
 c) the item is clearly outside defence land, naval and munitions business: civilian aircraft or airliners, space and satellites,
    commercial vehicles or rail, energy, mining, IT and cloud, consumer products, real estate or finance deals.
    Military drones, missiles, guns, vehicles, ammunition, naval systems, combat aircraft weapons and their parts: pass.
Reply one line per article and nothing else:  <number>|pass  or  <number>|fail|<a, b or c>|<one short reason>"""


def build_prompt(items: list) -> str:
    out = []
    for n, d in enumerate(items, 1):
        out.append(f"{n}. [{d['who']}] ({d['source']}; {d['date'] or 'undated'}) {(d['title'] or '').strip()[:200]}\n   {d['snippet'] or '(no text stored)'}")
    return "ARTICLES\n" + "\n".join(out) + "\n\nAnswer now."


def parse_reply(text: str, n: int) -> dict:
    """{number: ("pass", None) | ("fail", "c: reason")}; anything unreadable is left out (and so passes later: never a silent fail)."""
    got = {}
    for line in (text or "").splitlines():
        parts = [x.strip() for x in line.strip().strip("`").split("|")]
        if len(parts) < 2 or not parts[0].rstrip(".").isdigit():
            continue
        i = int(parts[0].rstrip("."))
        verdict = parts[1].lower()
        if not 1 <= i <= n or i in got or verdict not in ("pass", "fail"):
            continue
        if verdict == "fail" and len(parts) >= 3 and parts[2].lower()[:1] in ("a", "b", "c"):
            got[i] = ("fail", f"{parts[2].lower()[:1]}: {' '.join(' | '.join(parts[3:]).split())[:200]}")
        else:
            got[i] = ("pass", None)
    return got


def _selftest() -> None:
    g = parse_reply("1|pass\n2|fail|c|satellite launch\n3|fail|x|odd\n2|pass\n9|fail|a|z\nchatter\n4|FAIL|b|only mentioned", 4)
    assert g == {1: ("pass", None), 2: ("fail", "c: satellite launch"), 3: ("pass", None), 4: ("fail", "b: only mentioned")}, g
    p = build_prompt([{"who": "Rheinmetall", "source": "Defense News", "date": "2026-10-01", "title": "Rheinmetall wins order", "snippet": "text"}])
    assert p.startswith("ARTICLES\n1. [Rheinmetall] (Defense News; 2026-10-01) Rheinmetall wins order")
    print("signal_gate self-check ok")


def pending(cur, limit):
    """The signal prompt's own pending subjects (its subject query, not yet run at its version), not yet pre-checked, newest first."""
    from prompts import render
    spec = render.load_prompt("signal")
    cur.execute(f"""WITH s AS ({spec['subject']['query']})
                    SELECT s.article_id::text AS id, s.headline, s.publisher, s.published_date, s.competitor, s.article_url,
                           (SELECT left(d.body_text, 4000) FROM staging.source_document d WHERE d.url = s.article_url LIMIT 1) AS body
                    FROM s
                    WHERE NOT EXISTS (SELECT 1 FROM staging.prompt_run r WHERE r.prompt_id = 'signal' AND r.subject_key = s.article_id::text
                                       AND r.prompt_version = %s AND r.status IN ('loaded', 'skipped', 'rejected'))
                      AND NOT EXISTS (SELECT 1 FROM staging.prompt_run r WHERE r.prompt_id = 'signal_gate' AND r.subject_key = s.article_id::text)
                    ORDER BY s.published_date DESC NULLS LAST {'LIMIT ' + str(int(limit)) if limit else ''}""", (str(spec["version"]),))
    return [dict(r) for r in cur.fetchall()], str(spec["version"])


def run(limit=None, workers=4, dry_run=False) -> dict:
    import psycopg2.extras
    from prompts.claude_call import ModelError
    conn = connect()
    rows, sig_version = pending(conn.cursor(), limit)
    conn.rollback()
    docs = [{"id": r["id"], "who": r["competitor"], "source": r["publisher"], "date": r["published_date"].isoformat() if r["published_date"] else None,
             "title": r["headline"], "snippet": clean_snippet(r["body"] or "", HEAD_CHARS)} for r in rows]
    batches = [docs[i:i + BATCH] for i in range(0, len(docs), BATCH)]
    print(f"{len(docs)} articles in {len(batches)} calls" + (" [dry run]" if dry_run else ""), flush=True)
    lock = threading.Lock()
    stats = {"articles": 0, "pass": 0, "fail": 0, "unanswered": 0, "cost": 0.0, "failed_calls": 0}
    out = connect()

    def log(cur, prompt_id, version, key, status, skip, cost, details, res=None):
        cur.execute("""INSERT INTO staging.prompt_run (prompt_id, prompt_version, subject_key, model, web_search, seconds, tokens_in, tokens_out,
                       cost_usd, status, skip_reason, rows_loaded, details) VALUES (%s, %s, %s, %s, false, %s, %s, %s, %s, %s, %s, 0, %s)""",
                    (prompt_id, version, key, MODEL, getattr(res, "seconds", None), getattr(res, "tokens_in", None), getattr(res, "tokens_out", None),
                     cost, status, skip, psycopg2.extras.Json(details)))

    def work(batch):
        try:
            res = call(SYSTEM, build_prompt(batch))
        except ModelError as e:
            with lock:
                stats["failed_calls"] += 1
                print(f"  call failed: {str(e)[:160]}", flush=True)
            return
        got = parse_reply(res.text, len(batch))
        with lock:
            stats["articles"] += len(batch)
            stats["cost"] += res.cost_usd or 0
            with out.cursor() as cur:
                if not dry_run:
                    log(cur, "signal_gate", GATE_VERSION, f"batch-{batch[0]['id'][:8]}-{len(batch)}", "loaded", None, res.cost_usd,
                        {"articles": len(batch), "fail": sum(1 for v in got.values() if v[0] == "fail")}, res)
                for i, d in enumerate(batch, 1):
                    verdict, why = got.get(i, ("pass", None))
                    stats["unanswered"] += i not in got
                    if verdict == "fail" and why.startswith("a"):
                        # calibration 2026-10-21 (90 cards, 90 skips): 'no event' fails blocked real cards (a US Army visit that is a
                        # threat), so only b (competitor not involved) and c (out of field) remove an article; a is noted, then passed
                        verdict, why = "pass", f"noted, not applied: {why}"
                    stats[verdict] += 1
                    if dry_run:
                        if verdict == "fail":
                            print(f"  FAIL {why[:70]:70} | {d['title'][:70]}")
                        continue
                    if verdict == "fail":
                        log(cur, "signal", sig_version, d["id"], "skipped", f"pre-check: test {why}"[:300], 0, {"pre_check": True, "gate_version": GATE_VERSION})
                    log(cur, "signal_gate", GATE_VERSION, d["id"], "loaded" if verdict == "pass" else "skipped", why, 0, {"verdict": verdict})
            out.commit()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, b) for b in batches]):
            f.result()
    print(json.dumps(stats), flush=True)
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    s = run(a.limit, a.workers, a.dry_run)
    return 1 if s["failed_calls"] else 0


if __name__ == "__main__":
    sys.exit(main())
