"""Triage by Claude Haiku vs a local Ollama model on the same sample (owner 2026-10-24: use local models only where a sample matches).

    python -m scripts.compare_local_triage [--n 50] [--models qwen3.8-27b-32k,gemma4:26b] [--seed 7]

Takes N stored pages (1 Aug on, with text), builds the SAME triage v2 prompt (backend/triage_routes), asks Haiku once (cost logged to
prompt_run as 'triage_route_eval') and each local model, and reports per model: exact route-set agreement, Jaccard overlap, recall of
Haiku's routes, 'none' agreement, seconds. Writes nothing to source_document. Prints the disagreements so a person can judge which is right.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

from backend import attribute_documents as ad
from backend import triage_routes as tr
from prompts.run import connect

OLLAMA = "http://127.0.0.1:11434/api/chat"


def sample(n: int, seed: int) -> list[dict]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT competitor_id::text cid, display_name n FROM staging.competitive_competitor")
    names = {r["cid"]: r["n"] for r in cur.fetchall()}
    cur.execute("SELECT setseed(%s)", (seed / 100,))
    cur.execute("""SELECT doc_id::text AS id, source_kind, source_name, title, published_at, competitor_ids::text[] AS cids, left(body_text, 6000) AS body
                   FROM staging.source_document WHERE coalesce(published_at::date, fetched_at::date) >= '2026-08-01' AND length(body_text) > 600
                   ORDER BY random() LIMIT %s""", (n,))
    rows = cur.fetchall()
    conn.rollback()
    return [{"id": r["id"], "source": r["source_name"] or r["source_kind"], "date": r["published_at"].isoformat() if r["published_at"] else None,
             "title": r["title"], "snippet": tr.clean_snippet(ad.clean_body(r["source_name"], r["body"] or "", set())),
             "who": ", ".join(names[c] for c in (r["cids"] or [])[:3] if c in names)} for r in rows]


def ask_local(model: str, prompt: str) -> tuple[str, float]:
    body = {"model": model, "stream": False, "think": False, "options": {"temperature": 0, "num_ctx": 32768, "num_predict": 3000},
            "messages": [{"role": "system", "content": tr.SYSTEM}, {"role": "user", "content": prompt}]}
    t0 = time.monotonic()
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        out = json.loads(r.read())
    return out["message"]["content"], time.monotonic() - t0


def score(ref: dict, got: dict, n: int) -> dict:
    exact = jac = rec = none_ok = 0.0
    for i in range(1, n + 1):
        a, b = set(ref.get(i, (["?"], None))[0]), set(got.get(i, ([], None))[0])
        exact += a == b
        jac += len(a & b) / len(a | b) if a | b else 1
        rec += len(a & b) / len(a) if a else 1
        none_ok += (("none" in a) == ("none" in b))
    return {"exact": round(exact / n, 3), "jaccard": round(jac / n, 3), "recall_of_haiku": round(rec / n, 3), "none_agree": round(none_ok / n, 3),
            "answered": len(got)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--models", default="qwen3.8-27b-32k,gemma4:26b")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    docs = sample(a.n, a.seed)
    batches = [docs[i:i + tr.BATCH] for i in range(0, len(docs), tr.BATCH)]
    ref: dict = {}
    cost = 0.0
    off = 0
    for b in batches:                                   # Haiku: the reference (the routine's own model and prompt)
        res = tr.call(tr.SYSTEM, tr.build_prompt(b))
        got, _ = tr.parse_reply(res.text, len(b))
        ref.update({off + k: v for k, v in got.items()})
        cost += res.cost_usd or 0
        off += len(b)
    print(f"Haiku: {len(ref)} of {len(docs)} answered, ${cost:.3f}")
    report = {"n": len(docs), "haiku_cost": round(cost, 4), "models": {}}
    for m in [x.strip() for x in a.models.split(",") if x.strip()]:
        got, secs, off = {}, 0.0, 0
        for b in batches:
            text, s = ask_local(m, tr.build_prompt(b))
            g, _ = tr.parse_reply(text, len(b))
            got.update({off + k: v for k, v in g.items()})
            secs += s
            off += len(b)
        sc = score(ref, got, len(docs))
        sc["seconds"] = round(secs, 1)
        report["models"][m] = sc
        print(m, sc)
        for i in range(1, len(docs) + 1):
            if set(ref.get(i, ([], 0))[0]) != set(got.get(i, ([], 0))[0]):
                print(f"   {i:>3} haiku={ref.get(i, ([], 0))[0]} {m}={got.get(i, ([], 0))[0]}  {(docs[i - 1]['title'] or '')[:80]}")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
