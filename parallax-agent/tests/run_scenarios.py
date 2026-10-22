"""End-to-end scenario tests for Parallax Analyst, run against a live service.

    python tests/run_scenarios.py [--base http://127.0.0.1:8098] [--only nav,scope] [--parallel 4]

Each scenario sends real questions through POST /api/agent/chat (real model calls -- this
costs money; the full suite is roughly USD 1-1.5 on Sonnet 5.5) and checks the behaviour
from the event stream: scope refusals, which tools ran, the SQL, the widgets of any view,
navigation targets and focus, the answer verifier's verdict. It writes
tests/REPORT.md and tests/report.json.
"""

import argparse
import concurrent.futures as cf
import json
import re
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent

import importlib.util

# the scenarios belong to the product version: adapter/scenarios.py
_spec = importlib.util.spec_from_file_location("adapter_scenarios", HERE.parent / "adapter" / "scenarios.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SCENARIOS = _mod.SCENARIOS

# words that belong to the machinery, not to the business; none may reach the user
LEAK = re.compile(r"\b(r\d{1,3}|result[ _-]?sets?|rows? shown|sample rows?|previews?|sql|quer(?:y|ies)|tool calls?|"
                  r"budget|tokens?|openrouter|claude|sonnet|haiku|[0-9a-f]{12})\b", re.I)


def view_text(v):
    parts = [v.get("title"), v.get("subtitle"), v.get("summary")] + list(v.get("assumptions") or []) + \
        list(v.get("caveats") or []) + list(v.get("followups") or []) + [f.get("label") for f in v.get("filters") or []]
    for w in v.get("widgets") or []:
        parts += [w.get("title"), w.get("subtitle"), w.get("text")]
        parts += [k.get("label") for k in w.get("kpis") or []] + [k.get("note") for k in w.get("kpis") or []]
    return "\n".join(p for p in parts if p)


def run_turn(base, conv_id, question, page):
    t0 = time.time()
    ev_log = []
    with httpx.stream("POST", f"{base}/api/agent/chat", json={"message": question, "conversation_id": conv_id, "page": page},
                      timeout=400) as r:
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.read().decode()[:300]}", "events": [], "secs": 0}
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev_log.append(json.loads(line[6:]))
    secs = round(time.time() - t0, 1)
    out = {"secs": secs, "events": ev_log, "text": "", "queries": [], "views": [], "navigate": [], "notice": None,
           "verify": None, "error": None, "conversation_id": conv_id}
    for ev in ev_log:
        t = ev["type"]
        if t == "meta":
            out["conversation_id"] = ev["conversation_id"]
        elif t == "text":
            out["text"] += ev["text"]
        elif t == "query":
            out["queries"].append(ev)
        elif t == "view":
            out["views"].append({**ev["spec"], "_reopened": bool(ev.get("reopened"))})  # keeps data for checks
        elif t == "navigate":
            out["navigate"].append(ev)
        elif t == "notice":
            out["notice"] = ev
        elif t == "verify":
            out["verify"] = ev
        elif t == "error":
            out["error"] = ev["text"]
    return out


def check(res, c, prev_conv=None):
    fails = []
    qs = [q for q in res["queries"] if not q.get("error")]
    new_views = [v for v in res["views"] if not v["_reopened"]]
    widgets = [w["type"] for v in new_views for w in v["widgets"]]
    text = res["text"].lower()
    if res.get("error"):
        fails.append(f"error: {res['error']}")
    if "notice" in c and (not res["notice"] or res["notice"]["kind"] not in c["notice"]):
        fails.append(f"expected a {c['notice']} notice, got {res['notice'] and res['notice']['kind']}")
    if "max_queries" in c and len(res["queries"]) > c["max_queries"]:
        fails.append(f"ran {len(res['queries'])} queries, expected at most {c['max_queries']}")
    if "min_queries" in c and len(qs) < c["min_queries"]:
        fails.append(f"ran {len(qs)} successful queries, expected at least {c['min_queries']}")
    if "min_chars" in c and len(res["text"].strip()) < c["min_chars"]:
        fails.append(f"answer too thin for a question answered in chat ({len(res['text'].strip())} chars)")
    if c.get("text") and not text.strip():
        fails.append("no answer text")
    if c.get("view") and not new_views:
        fails.append("no new view was generated")
    if c.get("no_view") and res["views"]:
        fails.append(f"a view was generated but none was needed: {[v['title'] for v in res['views']]}")
    if c.get("reopened") and not any(v["_reopened"] for v in res["views"]):
        fails.append(f"expected an earlier view to be reopened; got {[(v['title'], v['_reopened']) for v in res['views']]}")
    if "widget_any" in c and new_views and not any(w in c["widget_any"] for w in widgets):
        fails.append(f"widgets {widgets} include none of {c['widget_any']}")
    if "answer_regex" in c and not re.search(c["answer_regex"], res["text"], re.S | re.I):
        fails.append(f"answer does not match /{c['answer_regex']}/")
    if "sql_regex" in c and not any(re.search(c["sql_regex"], q["sql"]) for q in qs):
        fails.append(f"no SQL matched /{c['sql_regex']}/")
    if c.get("categorize") and not any(q.get("kind") == "categorize" for q in qs):
        fails.append("no LLM categorisation ran")
    if c.get("no_fabricated_price") and re.search(r"\$\s?\d+(\.\d+)?\b(?!\s?(m|bn|b|k|million|billion))", res["text"], re.I) and not res["notice"]:
        fails.append("quoted a share price the platform does not have")
    if "subset" in c:
        col, want = c["subset"]
        for v in new_views:
            filters = {f["field"]: f.get("default") for f in v.get("filters") or [] if f.get("default")}
            for w in v["widgets"]:
                if w["type"] in ("text", "kpi"):
                    continue
                res_ = v["data"].get(w["result_id"]) or {}
                names = [c_["name"] for c_ in res_.get("columns", [])]
                if col not in names:
                    continue  # the query itself was limited to the subset
                i = names.index(col)
                rows = res_.get("rows", [])
                if w.get("filter_field"):
                    j = names.index(w["filter_field"]) if w["filter_field"] in names else None
                    rows = [r for r in rows if j is not None and str(r[j]) == str(w["filter_value"])]
                if col in filters:
                    rows = [r for r in rows if str(r[i]) == str(filters[col])]
                shown = {str(r[i]) for r in rows}
                if shown - {want}:
                    fails.append(f"widget '{w['title']}' claims {want} but plots {sorted(shown)[:5]}")
    if c.get("new_conversation") and prev_conv and res.get("conversation_id") == prev_conv:
        fails.append("reset did not start a new conversation")
    if c.get("clean"):
        leaks = sorted({m.group(0) for m in LEAK.finditer(res["text"])} |
                       {m.group(0) for v in new_views for m in LEAK.finditer(view_text(v))})
        if leaks:
            fails.append(f"technical terms reached the user: {leaks}")
    if "navigate" in c:
        pillar, view, payload = c["navigate"]
        hit = [n for n in res["navigate"] if n["pillar"] == pillar and n["view"] == view and
               all(str(v).lower() in str(n["payload"].get(k, "")).lower() for k, v in payload.items())]
        if not hit:
            fails.append(f"expected navigate {pillar}/{view} {payload}, got {[(n['pillar'], n['view'], n['payload']) for n in res['navigate']]}")
        elif "focus_has" in c and not any(c["focus_has"] in (n.get("focus") or "").lower() for n in hit):
            fails.append(f"expected focus on '{c['focus_has']}', got {[n.get('focus') for n in hit]}")
    return fails


def run_scenario(base, sc):
    sid, group, turns = sc
    conv, prev_conv = None, None
    out_turns = []
    for q, page, checks in turns:
        if q is None:  # the dock's ↺: forget the conversation server-side, start fresh
            if conv:
                httpx.delete(f"{base}/api/agent/conversation/{conv}", timeout=30)
            prev_conv, conv = conv, None
            out_turns.append({"question": "↺ reset", "pass": True, "fails": []})
            continue
        res = run_turn(base, conv, q, page)
        fails = check(res, checks, prev_conv)
        conv = res.get("conversation_id")
        out_turns.append({
            "question": q, "pass": not fails, "fails": fails, "secs": res["secs"],
            "queries": [{"title": x["title"], "rows": x.get("row_count"), "error": x.get("error"), "sql": x["sql"], "kind": x.get("kind")} for x in res["queries"]],
            "views": [{"title": v["title"], "reopened": v["_reopened"], "widgets": [f"{w['type']}:{w['title']}" for w in v["widgets"]],
                       "filters": [f["field"] for f in v["filters"]]} for v in res["views"]],
            "navigate": [{k: n.get(k) for k in ("pillar", "view", "payload", "focus", "label")} for n in res["navigate"]],
            "notice": res["notice"], "verify": {k: res["verify"].get(k) for k in ("status", "issues")} if res["verify"] else None,
            "answer": res["text"].strip()})
    return {"id": sid, "group": group, "pass": all(t["pass"] for t in out_turns), "turns": out_turns}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8098")
    ap.add_argument("--only", default="")
    ap.add_argument("--parallel", type=int, default=4)
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    todo = [s for s in SCENARIOS if not only or s[0] in only or s[1] in only]
    spent0 = httpx.get(f"{a.base}/api/agent/status", timeout=30).json().get("budget", {}).get("spent_usd")
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.parallel) as ex:
        results = list(ex.map(lambda s: run_scenario(a.base, s), todo))
    spent1 = httpx.get(f"{a.base}/api/agent/status", timeout=30).json().get("budget", {}).get("spent_usd")
    passed = sum(r["pass"] for r in results)
    turns = [t for r in results for t in r["turns"] if t["question"] != "↺ reset"]
    cost = round(spent1 - spent0, 3) if spent0 is not None and spent1 is not None else None

    (HERE / "report.json").write_text(json.dumps(results, indent=2))
    lines = ["# Parallax Analyst scenario report", "",
             f"{passed}/{len(results)} scenarios passed ({sum(t['pass'] for t in turns)}/{len(turns)} turns) · "
             f"wall time {time.time() - t0:.0f}s · cost ${cost}", "",
             "| | Scenario | Turn | Time | What happened |", "|---|---|---|---|---|"]
    for r in results:
        for i, t in enumerate(r["turns"]):
            if t["question"] == "↺ reset":
                lines.append(f"| | {r['id']} | {i + 1}. ↺ reset | | conversation cleared |")
                continue
            did = []
            if t["notice"]:
                did.append(f"refused ({t['notice']['kind']})")
            if t["queries"]:
                did.append(f"{len(t['queries'])} quer{'y' if len(t['queries']) == 1 else 'ies'}")
            for v in t["views"]:
                did.append(("reopened view" if v["reopened"] else "new view") + f" [{', '.join(w.split(':')[0] for w in v['widgets'])}]")
            for n in t["navigate"]:
                did.append(f"opened {n['pillar']}/{n['view']} {json.dumps(n['payload'])}" + (f" → {n['focus']}" if n.get("focus") else ""))
            if not did:
                did.append("answered")
            q = t["question"] if len(t["question"]) < 70 else t["question"][:67] + "..."
            lines.append(f"| {'PASS' if t['pass'] else 'FAIL'} | {r['id']} | {i + 1}. {q} | {t['secs']}s | {'; '.join(did)} |")
    lines.append("")
    for r in results:
        lines += [f"## {r['id']} ({r['group']}): {'PASS' if r['pass'] else 'FAIL'}", ""]
        for i, t in enumerate(r["turns"]):
            if t["question"] == "↺ reset":
                lines += [f"**{i + 1}. ↺ reset** (new conversation)", ""]
                continue
            lines += [f"**{i + 1}. {t['question']}**", ""]
            if t["fails"]:
                lines += ["Failures:"] + [f"- {f}" for f in t["fails"]] + [""]
            if t["notice"]:
                lines += [f"> {t['notice']['text']}", ""]
                if t["notice"].get("suggestions"):
                    lines += [f"> Suggested: {' / '.join(t['notice']['suggestions'])}", ""]
            for v in t["views"]:
                lines += [f"- {'reopened' if v['reopened'] else 'new'} view **{v['title']}**: {', '.join(v['widgets'])}"]
            for n in t["navigate"]:
                lines += [f"- opened {n['label']}" + (f", scrolled to {n['focus']}" if n.get("focus") else "")]
            if t["answer"]:
                lines += ["", t["answer"], ""]
            lines += [""]
    (HERE / "REPORT.md").write_text("\n".join(lines))
    print("\n".join(lines[:len(turns) + len(results) + 8]))


if __name__ == "__main__":
    main()
