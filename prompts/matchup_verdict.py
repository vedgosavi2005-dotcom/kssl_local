"""Handler of prompts/matchup.yml (v2): the model's verdict WORDS are written onto an existing code matchup.

    python -m prompts.matchup_verdict --selftest         pure checks, fictional values

The code engine (prompts/matchup_code.py) has already stored the pair, every spec row, the units, the gaps, better_side, edge_score and
decision_level. This handler changes none of the numbers. It writes:
  * competitive_matchup.decision_level (v3, kssl-40 2026-10-18): the model's level from the SAME judgement as the verdict words (1 behind /
    2 near parity / 3 ahead), replacing the code's level; the UI badge reads only this column. A verdict without a valid level is rejected;
  * competitive_matchup.verdict_headline, .verdict (and updated_at);
  * competitive_matchup_advantage rows (side, advantage_text), replacing the pair's earlier AI rows;
  * staging.fact_source rows: one per cited input row (the quote is checked against the rows the model was shown) and one `judgement` row
    per reason.
A pair the model calls `nothing_comparable` gets no words: the run is `skipped` with that as the reason, and the pair stays hidden
(comparable_spec_count 0 and no verdict). It has the same Result shape as prompts/news_merge.apply (run.py `_handled`).
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field

from prompts import plain_english

MAX_HEADLINE = 80
MAX_ADVANTAGE = 200
SIDES = ("client", "competitor")
KINDS = ("compared", "stated")
PER_SIDE = 4


@dataclass
class Result:
    rows: int = 0
    loaded: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    skip_reason: str | None = None
    note: str = ""
    details: dict = field(default_factory=dict)


def by_col(v, col: str) -> dict:
    """_reason / _sources per column; a bare sentence or list (the model's shorthand for a one-column record) belongs to `col`."""
    return v if isinstance(v, dict) else ({col: v} if v else {})


def clear_words(cur, mid) -> None:
    """Remove a pair's AI words (verdict, headline, its level, advantage lines and their fact_source rows)."""
    cur.execute("""DELETE FROM staging.fact_source WHERE (table_name = 'competitive_matchup' AND row_id = %s
                     AND column_name IN ('verdict', 'verdict_headline', 'decision_level'))
                   OR (table_name = 'competitive_matchup_advantage' AND row_id IN
                       (SELECT advantage_id::text FROM staging.competitive_matchup_advantage WHERE matchup_id = %s))""", (str(mid), mid))
    cur.execute("DELETE FROM staging.competitive_matchup_advantage WHERE matchup_id = %s", (mid,))
    cur.execute("UPDATE staging.competitive_matchup SET verdict = NULL, verdict_headline = NULL, decision_level = NULL, updated_at = now() "
                "WHERE matchup_id = %s AND verdict IS NOT NULL", (mid,))


def level_of(v) -> int | None:
    """decision_level as the model gives it (1 behind / 2 near parity / 3 ahead, ui.code_label); anything else is None."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if n in (1, 2, 3) else None


def hash63(*parts) -> int:
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def clean(env: dict) -> tuple[dict | None, list, list]:
    """(values, advantages, problems) from the model's envelope, checked. values is None when the envelope has no usable record."""
    problems: list = []
    recs = [r for r in (env.get("records") or []) if isinstance(r, dict)]
    rec = next((r for r in recs if r.get("table") == "competitive_matchup"), None)
    if rec is None:
        return None, [], ["no competitive_matchup record"]
    vals = dict(rec.get("values") or {})
    out = {"nothing_comparable": str(vals.get("nothing_comparable")).strip().lower() in ("true", "1", "yes"),
           "verdict_headline": " ".join(str(vals.get("verdict_headline") or "").split()) or None,
           "verdict": " ".join(str(vals.get("verdict") or "").split()) or None,
           "decision_level": level_of(vals.get("decision_level")),
           "_reason": vals.get("_reason") or {}, "_sources": vals.get("_sources") or {}}
    advs: list = []
    for c in ((rec.get("children") or {}).get("competitive_matchup_advantage") or []):
        side = str(c.get("side") or "").strip().lower()
        kind = str(c.get("kind") or "compared").strip().lower()
        kind = kind if kind in KINDS else "compared"
        text = " ".join(str(c.get("advantage_text") or "").split())
        if side not in SIDES or not text:
            problems.append(f"advantage dropped (side {c.get('side')!r})")
        elif len(text) > MAX_ADVANTAGE:
            problems.append(f"advantage dropped: {len(text)} characters, max {MAX_ADVANTAGE}")
        elif sum(a["side"] == side and a["kind"] == kind for a in advs) >= PER_SIDE:
            problems.append(f"advantage dropped: more than {PER_SIDE} {kind} for {side}")
        else:
            advs.append({"side": side, "kind": kind, "advantage_text": text, "_sources": c.get("_sources") or {}, "_reason": c.get("_reason") or {}})
    if not out["nothing_comparable"]:
        if not out["verdict"]:
            problems.append("no verdict")
        if out["decision_level"] is None:
            problems.append("no verdict: decision_level must be 1, 2 or 3")
        if out["verdict_headline"] and len(out["verdict_headline"]) > MAX_HEADLINE:
            problems.append(f"verdict_headline is {len(out['verdict_headline'])} characters, max {MAX_HEADLINE}")
    return out, advs, problems


def lint_texts(vals: dict, advs: list) -> list:
    """Plain-English findings as warnings; a hard finding in the verdict is a problem (returned with the 'strict:' prefix)."""
    out: list = []
    seen: set = set()
    for name, text in (("verdict_headline", vals.get("verdict_headline")), ("verdict", vals.get("verdict"))):
        if text:
            warn, reject = plain_english.judge(text, "warn", seen)          # long sentences are warnings (a condition makes them long); the prompt asks for 20 words
            out += [f"{name}: {w}" for w in warn] + ([f"strict: {name}: {reject}"] if reject else [])
    for i, a in enumerate(advs):
        out += [f"advantage[{i}]: {w}" for w in plain_english.judge(a["advantage_text"], "warn", seen)[0]]
    return out


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    res = Result()
    mid = subject["matchup_id"]
    vals, advs, problems = clean(env)
    if vals is None:
        res.warnings += problems
        return res
    if vals["nothing_comparable"]:
        res.skip_reason = "nothing comparable under the like-for-like and same-condition rules" + (
            f" ({env.get('skip_reason')})" if env.get("skip_reason") else "")
        if not dry_run:                                                  # an earlier run's words no longer hold: the pair goes hidden
            clear_words(cur, mid)
        return res
    res.warnings += [p for p in problems if not p.startswith("no verdict")]
    lint = lint_texts(vals, advs)
    hard = [x for x in lint if x.startswith("strict:")]
    res.warnings += [x for x in lint if not x.startswith("strict:")]
    if problems and any(p.startswith(("no verdict", "verdict_headline is")) for p in problems) or hard:
        res.warnings += hard
        return res                                                       # rejected: nothing is written
    cur.execute("SELECT matchup_id FROM staging.competitive_matchup WHERE matchup_id = %s", (mid,))
    if cur.fetchone() is None:
        res.warnings.append(f"matchup {mid} no longer exists")
        return res
    cur.execute("UPDATE staging.competitive_matchup SET verdict_headline = %s, verdict = %s, decision_level = %s, updated_at = now() WHERE matchup_id = %s",
                (vals["verdict_headline"], vals["verdict"], vals["decision_level"], mid))
    cur.execute("DELETE FROM staging.competitive_matchup_advantage WHERE matchup_id = %s", (mid,))
    cur.execute("DELETE FROM staging.fact_source WHERE table_name IN ('competitive_matchup', 'competitive_matchup_advantage') "
                "AND column_name IN ('verdict', 'verdict_headline', 'decision_level', 'advantage_text') AND row_id = %s", (str(mid),))
    cur.execute("""DELETE FROM staging.fact_source WHERE table_name = 'competitive_matchup_advantage' AND row_id IN
                   (SELECT advantage_id::text FROM staging.competitive_matchup_advantage WHERE matchup_id = %s)""", (mid,))
    for n, a in enumerate(advs, 1):
        aid = hash63("matchup_verdict", mid, a["side"], n)
        cur.execute("INSERT INTO staging.competitive_matchup_advantage (advantage_id, matchup_id, side, kind, advantage_text, display_order) VALUES (%s,%s,%s,%s,%s,%s)",
                    (aid, mid, a["side"], a["kind"], a["advantage_text"], n))
        a["_id"] = aid
        res.loaded.append(("competitive_matchup_advantage", str(aid), False))
    # sources: the input rows the model cites (kept as 'stored'), and the model's one-sentence reasons ('judgement')
    for col, entries in by_col(vals["_sources"], "verdict").items():
        for e in (entries if isinstance(entries, list) else []):
            if isinstance(e, dict) and e.get("quote"):
                cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                               VALUES ('competitive_matchup', %s, %s, %s, 'stored', %s)""",
                            (str(mid), col if col in ("verdict", "verdict_headline") else "verdict", e.get("url") or "stored row", str(e["quote"])[:300]))
    for col, reason in by_col(vals["_reason"], "verdict").items():
        if reason:
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                           VALUES ('competitive_matchup', %s, %s, 'judgement', 'judgement', %s)""", (str(mid), col, str(reason)[:300]))
    for a in advs:
        for col, reason in by_col(a["_reason"], "advantage_text").items():
            if reason:
                cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                               VALUES ('competitive_matchup_advantage', %s, 'advantage_text', 'judgement', 'judgement', %s)""", (str(a["_id"]), str(reason)[:300]))
        for col, entries in by_col(a["_sources"], "advantage_text").items():
            for e in (entries if isinstance(entries, list) else []):
                if isinstance(e, dict) and e.get("quote"):
                    cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                                   VALUES ('competitive_matchup_advantage', %s, 'advantage_text', %s, 'stored', %s)""",
                                (str(a["_id"]), e.get("url") or "stored row", str(e["quote"])[:300]))
    res.loaded.insert(0, ("competitive_matchup", str(mid), True))
    res.rows = len(res.loaded)
    res.note = f"{vals['verdict_headline'] or 'verdict'} ({len(advs)} advantage lines)"
    res.details = {"advantages": len(advs)}
    return res


def _selftest() -> None:
    env = {"records": [{"table": "competitive_matchup", "values": {"nothing_comparable": False, "verdict_headline": "KSSL reaches farther", "decision_level": "3",
                        "verdict": "The MArG reaches 48 km. The rival reaches 40 km. Weight is not stated for the rival.",
                        "_reason": {"verdict": "Range rows."}, "_sources": {"verdict": [{"url": None, "quote": "Max range: 48 km"}]}},
                        "children": {"competitive_matchup_advantage": [
                            {"side": "client", "advantage_text": "Longer range with a plain round: 48 km vs 40 km"},
                            {"side": "both", "advantage_text": "x"}, {"side": "competitor", "advantage_text": "y" * 300}]}}]}
    v, a, p = clean(env)
    assert all(x["kind"] == "compared" for x in a)          # no kind given: compared (the pre-v4 rows)
    assert v["verdict_headline"] == "KSSL reaches farther" and len(a) == 1 and len(p) == 2 and not v["nothing_comparable"]
    assert v["decision_level"] == 3
    no_level = {"records": [{"table": "competitive_matchup", "values": {"verdict_headline": "Level", "verdict": "Fine."}}]}
    assert any("decision_level" in x for x in clean(no_level)[2])
    assert clean({"records": []})[0] is None
    env2 = {"records": [{"table": "competitive_matchup", "values": {"nothing_comparable": "true"}}]}
    assert clean(env2)[0]["nothing_comparable"] is True
    long_head = {"records": [{"table": "competitive_matchup", "values": {"verdict_headline": "h" * 90, "verdict": "Fine."}}]}
    assert any("verdict_headline is 90" in x for x in clean(long_head)[2])
    assert not lint_texts(v, a) or all(not x.startswith("strict:") for x in lint_texts(v, a))
    assert hash63("a", 1) == hash63("a", 1) != hash63("a", 2)
    assert by_col("one reason", "advantage_text") == {"advantage_text": "one reason"} and by_col(None, "x") == {} and by_col({"a": 1}, "x") == {"a": 1}
    assert level_of("2") == 2 and level_of(3) == 3 and level_of(4) is None and level_of("ahead") is None and level_of(None) is None
    st = {"records": [{"table": "competitive_matchup", "values": {"verdict_headline": "Level", "verdict": "Fine.", "decision_level": 2},
                       "children": {"competitive_matchup_advantage": [{"side": "client", "kind": "stated", "advantage_text": "Self-propelled mode up to 21 km/h"},
                                                                     {"side": "client", "kind": "odd", "advantage_text": "x"}]}}]}
    assert [x["kind"] for x in clean(st)[1]] == ["stated", "compared"]
    print("matchup_verdict self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
