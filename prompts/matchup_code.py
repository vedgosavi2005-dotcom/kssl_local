"""Code-based matchup engine: every client product x every competitor product of the same category.

    python -m prompts.matchup_code [--category X] [--dictionary-only] [--compare-only] [--dry-run]
                                   [--limit-pairs N] [--selftest] [--report]

Step 1  spec dictionary (the only model step): the spec labels of each category (both sides) are mapped, in batches,
        to a canonical key + unit family + which side is better -> staging.spec_dictionary (db/setup/10_spec_dictionary.sql).
Step 2  value parsing: prompts/spec_values.py (pure functions; a value is compared only when it is an unambiguous number).
Step 3  compare: for every pair of prompts/matchup.yml's subject query (category 'Other' excluded) the specs are joined
        on canonical key and written as competitive_matchup + _specification + _source (+ fact_source), with the same ids
        the matchup PROMPT would use for that pair, so a later AI run of the pair replaces these rows. verdict and
        verdict_headline stay NULL (the AI step fills them for the top pairs). A pair that already has an AI card
        (prompt_run matchup 'loaded', or a matchup row that is not marked "(code comparison)") is never touched.
        Rows written by this engine end their match_basis with "(code comparison)": that is the marker for a re-run.
Step 4  --report: counts, the payload of the `matchups` key and db/excel_reports/matchup_top_pairs.csv.

Local kssl_staging only. Self-check (no DB, no model):  python -m prompts.matchup_code --selftest
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

from prompts import derive, matchup_class, spec_values
from prompts.loader import id_seed, make_id
from prompts.spec_values import Parsed, compare_values, family_ok, parse_multi, parse_value

MODEL = "claude-sonnet-5-5"
MARKER = "(code comparison)"
SKIP_CATEGORIES = {"other"}                  # lower-case; user decision: noise
SEND_SINGLE_USE = True                       # also send competitor labels used on one product only (costs cents; widens the join)
BATCH = 200                                  # labels per model call (<= ~300)
MAX_ROWS = 20                                # spec rows per pair (the matchup prompt's cap)
EQUAL_BAND = float(derive.DEAD_BAND)         # a comparable gap under this percent is 'equal' (derive.py's rule, 3 %)
NEUTRAL_AS_COMPARABLE = False                # True: a neutral key (better 'none') with two numbers is 'comparable' (side None)
REPORT_DIR = Path(__file__).resolve().parent.parent / "db" / "excel_reports"
CALL_LOG = REPORT_DIR / "matchup_dictionary_calls.jsonl"
FAMILIES = ("length", "mass", "speed", "time", "count", "rate", "angle", "power", "ratio", "other", "text")
BETTER = ("higher", "lower", "none")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
PLAIN_FIGURE = re.compile(r"^[<>~]?\s*\d[\d.,]*(?:\s*[-–]\s*\d[\d.,]*)?\s*\+?$")


def norm_label(s) -> str:
    """casefold, punctuation (and stray symbol characters) removed, spaces collapsed."""
    return " ".join(re.sub(r"[^\w\s]|_", " ", (s or "").casefold()).split())


def clean_label(s) -> str:
    return re.sub(r"^[^\w]+", "", (s or "").strip()).rstrip(": ").strip()[:180]


def snake(s: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (s or "").lower())).strip("_")[:60] or "label"


# =====================================================================================================
# step 1: the dictionary
# =====================================================================================================

SYSTEM = """You normalise product-specification labels for a defence-industry product comparison database.
You get the specification labels that appear in ONE product category, taken from two catalogues (the client's own products
and competitor products), with how often each is used, the units seen and a few example values. For each label decide:

  key        a snake_case canonical key (lower case letters, digits, underscore). Labels that measure the same thing
             MUST share one key, whichever catalogue they come from ('Max range', 'Range', 'Maximum firing range' -> max_range).
             Use a different key when the condition differs: ammunition type or special round, loaded/empty,
             day/night, burst/sustained, road/off-road, towed/self-propelled, with/without option. Prefer the keys
             in KNOWN KEYS when one fits; add a new key only when none does. Do not put units in a key unless two keys
             differ only by unit (calibre_mm vs barrel_length_cal).
  family     what the value is measured in: length | mass | speed | time | count | rate | angle | power | ratio | other | text
             (count = a number of things: crew, rounds carried; rate = rounds per minute; ratio = percent or calibres 'L/52';
             other = a number in another unit: temperature, frequency, pressure, energy, volume; text = not a number)
  better     higher | lower | none -- which value a buyer of this product class prefers: higher for range, rate of fire,
             payload, speed, endurance, accuracy; lower for platform weight where mobility matters, reaction / coming-into-action
             time, dispersion, error, cost; none when neither is better or it depends (calibre, crew size, dimensions that
             are not a payload, combat weight of an armoured vehicle where weight also means protection, temperature range).
  comparable true when the label is a measurable parameter two products can be compared on; false for descriptive or
             free-text labels (Role, Note, Configuration, Type, Users, Manufacturer, Variants, Armament description).
  reason     one short sentence: why that side is better, or why neither (leave empty for comparable=false).

Judge from the label and the example values only. Reply with JSON only, no prose:
{"items": [{"id": <id>, "key": "...", "family": "...", "better": "...", "comparable": true|false, "reason": "..."}, ...]}
Exactly one item per label id given; never skip an id and never invent one."""


@dataclass
class Entry:
    category: str
    label: str
    key: str
    family: str
    better: str
    comparable: bool
    reason: str | None
    model: str | None


def validate_items(env: dict, ids: set) -> tuple[dict, list]:
    """(id -> normalised item, problems). An item that fails a check is left out so the gap re-ask picks it up."""
    out, problems = {}, []
    items = env.get("items")
    if not isinstance(items, list):
        return {}, ["no 'items' list"]
    for it in items:
        if not isinstance(it, dict):
            problems.append("item is not an object")
            continue
        try:
            i = int(it.get("id"))
        except (TypeError, ValueError):
            problems.append(f"bad id {it.get('id')!r}")
            continue
        if i not in ids:
            problems.append(f"unknown id {i}")
            continue
        if i in out:
            problems.append(f"id {i} mapped twice")
            continue
        fam, bet = str(it.get("family", "")).strip().lower(), str(it.get("better", "")).strip().lower()
        comp = it.get("comparable")
        key = str(it.get("key", "")).strip().lower()
        if isinstance(comp, str) and comp.lower() in ("true", "false"):
            comp = comp.lower() == "true"
        if fam not in FAMILIES or bet not in BETTER or not isinstance(comp, bool):
            problems.append(f"id {i}: bad family/better/comparable ({fam!r}, {bet!r}, {comp!r})")
            continue
        key = snake(key) if not KEY_RE.match(key) else key
        if fam == "text":
            comp = False
        out[i] = {"key": key, "family": fam, "better": bet, "comparable": comp,
                  "reason": (str(it.get("reason") or "").strip()[:300] or None)}
    return out, problems


def unify_keys(rows: list) -> None:
    """Within a category one canonical key has one family / better / comparable: the majority of its labels."""
    by_key = defaultdict(list)
    for r in rows:
        by_key[r.key].append(r)
    for key, rs in by_key.items():
        votes = Counter((r.family, r.better, r.comparable) for r in rs)
        fam, bet, comp = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        reason = next((r.reason for r in rs if r.reason and (r.family, r.better) == (fam, bet)), None)
        for r in rs:
            r.family, r.better, r.comparable = fam, bet, comp
            if comp:
                r.reason = reason or r.reason


def collect_labels(cur) -> dict:
    """{category_lower: {'name': category as stored on the client, 'labels': {norm: info}}} for categories with a client product."""
    cats: dict = {}
    cur.execute("SELECT DISTINCT category FROM staging.client_product WHERE category IS NOT NULL")
    for r in cur.fetchall():
        c = r["category"].strip()
        if c.lower() not in SKIP_CATEGORIES:
            cats[c.lower()] = {"name": c, "labels": {}}

    def add(cat, label, side, unit, value):
        d = cats.get(cat)
        n = norm_label(label)
        if d is None or not n:
            return
        info = d["labels"].setdefault(n, {"client": 0, "comp": 0, "units": Counter(), "examples": [], "raw": Counter()})
        info[side] += 1
        info["raw"][clean_label(label)] += 1
        if unit:
            info["units"][unit] += 1
        v = str(value if value is not None else "").strip()
        if v and len(info["examples"]) < 3 and v not in info["examples"]:
            info["examples"].append(v[:60])

    cur.execute("""SELECT lower(trim(p.category)) AS cat, s.spec_name AS l, s.unit, coalesce(s.value_text, s.value_numeric::text) AS v
                   FROM staging.client_product_specification s JOIN staging.client_product p USING (client_product_id)""")
    for r in cur.fetchall():
        add(r["cat"], r["l"], "client", r["unit"], r["v"])
    cur.execute("""SELECT lower(trim(p.category)) AS cat, s.spec_label AS l, s.unit, s.spec_value AS v
                   FROM staging.competitive_product_specification s JOIN staging.competitive_product p USING (product_id)""")
    for r in cur.fetchall():
        add(r["cat"], r["l"], "comp", r["unit"], r["v"])
    return cats


def labels_to_send(info: dict) -> tuple[list, list]:
    """(sent, skipped). Sent: every client label, and every competitor label used on >= 2 products. A competitor label
    used once can match nothing but one product: it is stored comparable=false without a model call."""
    send, skip = [], []
    for n, v in info.items():
        (send if SEND_SINGLE_USE or v["client"] > 0 or v["comp"] >= 2 else skip).append(n)
    send.sort(key=lambda n: (-(info[n]["client"] > 0), -(info[n]["client"] + info[n]["comp"]), n))
    return send, sorted(skip)


def prompt_for(category: str, batch: list, info: dict, known: list) -> str:
    lines = []
    for i, n in enumerate(batch, 1):
        v = info[n]
        raw = v["raw"].most_common(1)[0][0]
        ex = " | ".join(v["examples"])
        units = ",".join(u for u, _ in v["units"].most_common(3))
        lines.append(f"{i}\t{raw}\tclient:{v['client']} comp:{v['comp']}\tunits:{units or '-'}\te.g. {ex or '-'}")
    kn = "\n".join(known) if known else "(none yet)"
    return (f"CATEGORY: {category}\n\nKNOWN KEYS (key | family | better), reuse when the label measures the same thing:\n{kn}\n\n"
            f"LABELS (id, label, uses on the client's / on competitors' products, units seen, example values):\n"
            + "\n".join(lines) + "\n\nReturn the JSON now.")


class Budget:
    """Job-wide cap: `limit` is the total for the whole job, so the cost already in the call log counts. per_run=True (the routine,
    --run-budget): `limit` counts only this invocation's calls, so a scheduled run never stalls on what earlier jobs spent."""
    def __init__(self, limit: float, per_run: bool = False):
        prior = 0.0
        if CALL_LOG.exists() and not per_run:
            prior = sum(json.loads(l).get("cost_usd") or 0 for l in CALL_LOG.read_text(encoding="utf-8").splitlines() if l.strip())
        self.limit, self.prior, self.spent, self.calls, self.tin, self.tout = limit, prior, prior, 0, 0, 0

    def check(self):
        if self.spent >= self.limit:
            raise RuntimeError(f"model budget reached: ${self.spent:.2f} >= ${self.limit:.2f}; stopping")


def call(budget: Budget, label: str, system: str, prompt: str):
    from prompts import claude_call
    from prompts.spec import parse_envelope
    budget.check()
    last = None
    for attempt in (1, 2):
        try:
            res = claude_call.call_model(system, prompt, MODEL, web_search=False)
        except claude_call.ModelError as e:
            last = e
            print(f"  model error ({e}); attempt {attempt}", flush=True)
            continue
        cost = float(res.cost_usd or 0)
        budget.spent += cost
        budget.calls += 1
        budget.tin += res.tokens_in
        budget.tout += res.tokens_out
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        with CALL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "what": label, "model": MODEL,
                                "tokens_in": res.tokens_in, "tokens_out": res.tokens_out, "cost_usd": cost,
                                "seconds": res.seconds}) + "\n")
        print(f"  {label}: {res.tokens_in} in / {res.tokens_out} out, ${cost:.4f}, {res.seconds}s "
              f"(running total ${budget.spent:.2f} of ${budget.limit:.2f})", flush=True)
        try:
            return parse_envelope(res.text)
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  unreadable reply ({e}); attempt {attempt}", flush=True)
    raise RuntimeError(f"model call failed twice: {last}")


def known_lines(cur, category: str) -> list:
    """The keys already in the dictionary, this category's first, then the most used elsewhere (so keys are shared across categories)."""
    cur.execute("""SELECT canonical_key, unit_family, better, bool_or(category = %s) AS here, count(*) n FROM staging.spec_dictionary
                   WHERE comparable GROUP BY 1, 2, 3 ORDER BY here DESC, n DESC, 1 LIMIT 300""", (category,))
    return [f"{r['canonical_key']} | {r['unit_family']} | {r['better']}" for r in cur.fetchall()]


def build_dictionary(conn, cats: dict, only: str | None, dry: bool, budget: Budget, redo: bool = False) -> dict:
    cur = conn.cursor()
    stats = {}
    for cl, d in sorted(cats.items()):
        if only and cl != only.lower():
            continue
        name, info = d["name"], d["labels"]
        cur.execute("SELECT raw_label_norm FROM staging.spec_dictionary WHERE category = %s AND model IS DISTINCT FROM 'code:skipped'", (name,))
        have = {r["raw_label_norm"] for r in cur.fetchall()}
        send, skip = labels_to_send(info)
        todo = [n for n in send if redo or n not in have]
        skipped_new = [n for n in skip if redo or n not in have]
        batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
        print(f"[{name}] labels {len(info)}: sent {len(send)} ({len(todo)} still to map in {len(batches)} calls), "
              f"skipped single-use competitor labels {len(skip)}", flush=True)
        stats[name] = {"labels": len(info), "sent": len(send), "skipped": len(skip), "calls": len(batches)}
        if dry:
            continue
        rows: list = []
        for bi, batch in enumerate(batches, 1):
            ids = set(range(1, len(batch) + 1))
            got, problems = {}, []
            prompt = prompt_for(name, batch, info, known_lines(cur, name))
            env = call(budget, f"{name} batch {bi}/{len(batches)}", SYSTEM, prompt)
            got, problems = validate_items(env, ids)
            if len(got) < len(ids):                                   # re-ask once for the gaps
                missing = sorted(ids - set(got))
                print(f"  {len(missing)} of {len(ids)} labels missing/invalid ({'; '.join(problems[:3])}); re-asking once", flush=True)
                sub = [batch[i - 1] for i in missing]
                env2 = call(budget, f"{name} batch {bi} gap re-ask", SYSTEM, prompt_for(name, sub, info, known_lines(cur, name)))
                got2, _ = validate_items(env2, set(range(1, len(sub) + 1)))
                for j, i in enumerate(missing, 1):
                    if j in got2:
                        got[i] = got2[j]
            for i, n in enumerate(batch, 1):
                g = got.get(i)
                if g is None:
                    rows.append(Entry(name, n, f"unmapped_{snake(n)}", "text", "none", False, None, "code:unmapped"))
                else:
                    rows.append(Entry(name, n, g["key"], g["family"], g["better"], g["comparable"], g["reason"], MODEL))
            _store(cur, rows)                                          # after every call: a stop loses nothing
            conn.commit()
            rows = []
        for n in skipped_new:
            rows.append(Entry(name, n, f"single_use_{snake(n)}", "text", "none", False, None, "code:skipped"))
        _store(cur, rows)
        cur.execute("SELECT * FROM staging.spec_dictionary WHERE category = %s AND model = %s", (name, MODEL))
        mapped = [Entry(r["category"], r["raw_label_norm"], r["canonical_key"], r["unit_family"], r["better"], r["comparable"],
                        r["reason"], r["model"]) for r in cur.fetchall()]
        unify_keys(mapped)
        _store(cur, mapped)
        conn.commit()
    return stats


MERGE_SYSTEM = """You clean a defence product-specification dictionary. In ONE product category, labels were mapped to canonical keys
in many batches, so some keys are synonyms: two keys that measure exactly the same quantity under exactly the same condition
('towing_speed' and 'max_towing_speed'; 'combat_weight' and 'combat_mass'). You get every key with its unit family, which side is
better, how many labels use it, and example labels. Group the synonyms.

Rules:
  - Merge only keys that measure the same thing under the same condition. Never merge keys whose condition differs: ammunition or
    round type, loaded / empty, day / night, burst / sustained / intense, road / off-road, towed / self-propelled / APU mode, with /
    without an option. A key with a condition is never merged into the key without it (max_range_erfb_bt stays apart from max_range).
  - Never merge keys of different unit families, or different quantities that share a unit (length vs height, empty vs gross weight).
  - keep = the key most labels use (prefer one the client's products use). merge = the others.
  - Only list groups with at least one key to merge. When unsure, leave the keys apart.

Reply with JSON only: {"groups": [{"keep": "<key>", "merge": ["<key>", ...], "reason": "<one short sentence>"}, ...]}"""
MERGE_LOG = REPORT_DIR / "matchup_key_merges.jsonl"


def merge_lines(cur, name: str) -> tuple[list, dict]:
    """(prompt lines, key -> family) for the comparable keys of a category that a stored spec label uses."""
    cur.execute("SELECT raw_label_norm, canonical_key, unit_family, better FROM staging.spec_dictionary WHERE category = %s AND comparable", (name,))
    rows = cur.fetchall()
    cats = collect_labels(cur)
    used = (cats.get(name.lower()) or {}).get("labels", {})
    keys: dict = {}
    for r in rows:
        u = used.get(r["raw_label_norm"])
        if not u:
            continue
        k = keys.setdefault(r["canonical_key"], {"family": r["unit_family"], "better": r["better"], "n": 0, "client": 0, "ex": []})
        k["n"] += 1
        k["client"] += u["client"]
        if len(k["ex"]) < 3:
            k["ex"].append(r["raw_label_norm"])
    lines = [f"{k} | {v['family']} | {v['better']} | labels {v['n']} | client uses {v['client']} | e.g. {'; '.join(v['ex'])}"
             for k, v in sorted(keys.items())]
    return lines, {k: v["family"] for k, v in keys.items()}


def valid_merges(env: dict, families: dict) -> tuple[list, list]:
    """(groups that pass, problems): every key known and comparable here, one unit family per group, each key in one group."""
    out, problems, seen = [], [], set()
    for g in env.get("groups") or []:
        keep, merge = str(g.get("keep") or ""), [str(m) for m in (g.get("merge") or []) if str(m) != str(g.get("keep"))]
        ks = [keep, *merge]
        if not merge or any(k not in families for k in ks):
            problems.append(f"unknown key in {ks}")
        elif len({families[k] for k in ks}) > 1:
            problems.append(f"mixed unit families in {ks}")
        elif seen & set(ks):
            problems.append(f"key in two groups: {ks}")
        else:
            seen |= set(ks)
            out.append({"keep": keep, "merge": merge, "reason": str(g.get("reason") or "")[:200]})
    return out, problems


def merge_keys(conn, only: str | None, dry: bool, budget: Budget) -> dict:
    """Step 1b: fold synonym keys of a category into one (one model call per category; code checks every group)."""
    cur = conn.cursor()
    stats = {}
    cur.execute("SELECT DISTINCT category FROM staging.client_product WHERE category IS NOT NULL")
    for name in sorted(r["category"].strip() for r in cur.fetchall()):
        if name.lower() in SKIP_CATEGORIES or (only and name.lower() != only.lower()):
            continue
        lines, families = merge_lines(cur, name)
        print(f"[{name}] keys in use {len(lines)}", flush=True)
        if dry or len(lines) < 2:
            continue
        env = call(budget, f"{name} key merge", MERGE_SYSTEM, f"CATEGORY: {name}\n\nKEYS (key | family | better | labels | client uses | example labels):\n"
                   + "\n".join(lines) + "\n\nReturn the JSON now.")
        groups, problems = valid_merges(env, families)
        n = 0
        for g in groups:
            cur.execute("UPDATE staging.spec_dictionary SET canonical_key = %s WHERE category = %s AND canonical_key = ANY(%s)", (g["keep"], name, g["merge"]))
            n += cur.rowcount
        cur.execute("SELECT * FROM staging.spec_dictionary WHERE category = %s", (name,))
        entries = [Entry(r["category"], r["raw_label_norm"], r["canonical_key"], r["unit_family"], r["better"], r["comparable"], r["reason"], r["model"])
                   for r in cur.fetchall()]
        unify_keys(entries)
        _store(cur, entries)
        conn.commit()
        with MERGE_LOG.open("a", encoding="utf-8") as f:
            for g in groups:
                f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "category": name, **g}) + "\n")
        stats[name] = {"keys": len(lines), "groups": len(groups), "labels_moved": n, "refused": problems}
        print(f"  {len(groups)} groups merged ({n} labels moved); refused {len(problems)}: {'; '.join(problems[:4])}", flush=True)
    return stats


PAIR_SYSTEM = """You check candidate synonyms in a defence product-specification dictionary. Each candidate is two canonical keys
of ONE product category that never meet: in like-for-like product comparisons one product states the first and its rival states
the second. Say whether they are the SAME quantity under the SAME condition, so the two values belong on one comparison row.
Same: 'max_towing_speed' / 'towing_speed'; 'top_speed' / 'max_speed_burst' (both the vehicle's maximum road speed); 'combat_weight' /
'gross_vehicle_weight' for an armoured vehicle; 'passenger_capacity' / 'seating_capacity'; 'self_propelled_speed' / 'apu_speed' for
a towed gun. NOT the same: a different ammunition or round, day vs night, burst vs sustained, loaded vs empty, folded vs unfolded
length, kerb vs gross weight, effective vs maximum range, a part vs the whole system. When unsure: false.
Reply with JSON only: {"items": [{"id": <id>, "same": true|false}, ...]}  One item per id."""
PAIR_BATCH = 120


def candidate_pairs(cur, only: str | None) -> dict:
    """{category: Counter((client_key, rival_key))}: keys of opposite one-sided rows of the same matchup, same unit family."""
    by_label, _ = load_dictionary(cur)
    cur.execute("""SELECT m.category_code AS cat, s.matchup_id, s.spec_label, s.client_value_text IS NOT NULL AS client
                   FROM staging.competitive_matchup_specification s JOIN staging.competitive_matchup m USING (matchup_id)
                   WHERE s.comparability_state = 'one_sided' AND position(%s in m.match_basis) > 0""", (MARKER,))
    rows = defaultdict(lambda: ([], []))
    for r in cur.fetchall():
        if only and r["cat"].lower() != only.lower():
            continue
        ki = by_label.get(r["cat"].strip().lower(), {}).get(norm_label(r["spec_label"]))
        if ki and ki.comparable:
            rows[(r["cat"], r["matchup_id"])][0 if r["client"] else 1].append(ki)
    out: dict = defaultdict(Counter)
    for (cat, _mid), (ks, rs) in rows.items():
        for a in ks:
            for b in rs:
                if a.key != b.key and a.family == b.family:
                    out[cat][(a.key, b.key)] += 1
    return out


def merge_pair_keys(conn, only: str | None, dry: bool, budget: Budget) -> dict:
    """Step 3b: the model says yes / no per candidate synonym; the yes pairs are folded into one key (the one more labels use)."""
    cur = conn.cursor()
    stats = {}
    for cat, cands in sorted(candidate_pairs(cur, only).items()):
        cur.execute("SELECT canonical_key, count(*) AS n, string_agg(raw_label_norm, '; ' ORDER BY raw_label_norm) AS ex FROM staging.spec_dictionary "
                    "WHERE category = %s GROUP BY 1", (cat,))
        info = {r["canonical_key"]: (r["n"], r["ex"][:120]) for r in cur.fetchall()}
        todo = [k for k, _ in cands.most_common()]
        print(f"[{cat}] candidate synonym pairs {len(todo)}", flush=True)
        stats[cat] = {"candidates": len(todo)}
        if dry or not todo:
            continue
        yes = []
        for bi in range(0, len(todo), PAIR_BATCH):
            batch = todo[bi:bi + PAIR_BATCH]
            lines = [f"{i}\t{a} (e.g. {info.get(a, (0, ''))[1]})\t{b} (e.g. {info.get(b, (0, ''))[1]})" for i, (a, b) in enumerate(batch, 1)]
            try:
                env = call(budget, f"{cat} synonym pairs {bi // PAIR_BATCH + 1}", PAIR_SYSTEM,
                           f"CATEGORY: {cat}\n\nCANDIDATES (id, key A with example labels, key B with example labels):\n" + "\n".join(lines) + "\n\nReturn the JSON now.")
            except RuntimeError as e:
                print(f"  skipped: {e}", flush=True)
                continue
            got = {int(it["id"]): it.get("same") is True for it in env.get("items") or [] if isinstance(it, dict) and str(it.get("id", "")).isdigit()}
            yes += [batch[i - 1] for i, ok in got.items() if ok and 1 <= i <= len(batch)]
        parent: dict = {}

        def root(k):
            while parent.get(k, k) != k:
                k = parent[k]
            return k
        for a, b in yes:                                  # union, the key more labels use is the root
            ra, rb = root(a), root(b)
            if ra != rb:
                keep, drop = sorted((ra, rb), key=lambda k: (-info.get(k, (0, ""))[0], k))
                parent[drop] = keep
        moved = 0
        for k in list(parent):
            cur.execute("UPDATE staging.spec_dictionary SET canonical_key = %s WHERE category = %s AND canonical_key = %s", (root(k), cat, k))
            moved += cur.rowcount
        cur.execute("SELECT * FROM staging.spec_dictionary WHERE category = %s", (cat,))
        entries = [Entry(r["category"], r["raw_label_norm"], r["canonical_key"], r["unit_family"], r["better"], r["comparable"], r["reason"], r["model"])
                   for r in cur.fetchall()]
        unify_keys(entries)
        _store(cur, entries)
        conn.commit()
        with MERGE_LOG.open("a", encoding="utf-8") as f:
            for a, b in yes:
                f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "category": cat, "pair": [a, b],
                                    "into": root(a)}) + "\n")
        stats[cat].update(same=len(yes), labels_moved=moved)
        print(f"  {len(yes)} of {len(todo)} judged the same; {moved} labels moved", flush=True)
    return stats


def _store(cur, rows: list) -> None:
    if not rows:
        return
    import psycopg2.extras
    psycopg2.extras.execute_values(cur, """
        INSERT INTO staging.spec_dictionary (category, raw_label_norm, canonical_key, unit_family, better, comparable, reason, model)
        VALUES %s ON CONFLICT (category, raw_label_norm) DO UPDATE SET canonical_key = EXCLUDED.canonical_key,
          unit_family = EXCLUDED.unit_family, better = EXCLUDED.better, comparable = EXCLUDED.comparable,
          reason = EXCLUDED.reason, model = EXCLUDED.model, created_at = now()""",
                                   [(r.category, r.label, r.key, r.family, r.better, r.comparable, r.reason, r.model) for r in rows])


# =====================================================================================================
# step 3: comparison (pure part)
# =====================================================================================================

@dataclass
class Raw:
    label: str
    text: str | None
    unit: str | None = None
    url: str | None = None
    group: str | None = None
    order: int = 0


@dataclass
class Side:
    label: str
    text: str | None
    unit: str | None                  # the stored unit column
    parsed: Parsed | None
    url: str | None
    group: str | None
    order: int
    ambiguous: bool = False
    urls: list = field(default_factory=list)
    note: str | None = None           # e.g. 'highest of 3 stated values' (several values in one cell, higher-is-better key)


@dataclass
class KeyInfo:
    key: str
    family: str
    better: str
    comparable: bool
    reason: str | None


def condition_key(base: str, cond: str, keys) -> str | None:
    """The dictionary key for 'base under this condition' (max_range + 'ERFB-BB' -> max_range_erfb_bb): the longest key base_<suffix> whose
    suffix words all occur in the condition. None when the dictionary has none."""
    toks = set(re.findall(r"[a-z0-9]+", (cond or "").lower()))
    best = None
    for k in keys:
        if k.startswith(base + "_"):
            suf = k[len(base) + 1:].split("_")
            if all(t in toks for t in suf) and (best is None or len(suf) > best[0]):
                best = (len(suf), k)
    return best[1] if best else None


def resolve_sides(raws: list, dic: dict) -> dict:
    """key -> Side. `dic` maps norm label -> KeyInfo. A label the dictionary does not know, or marks descriptive, is dropped.
    Several specs of one side under one key: identical parsed values collapse; differing ones make the side ambiguous.
    Several values in one cell ('30 km (HE), 40 km (ERFB-BB)'): each value whose condition matches a dictionary key of the
    category goes to that key (max_range_he, max_range_erfb_bb); the base key takes the highest value when higher is better
    (marked), and nothing otherwise."""
    keys = {ki.key for ki in dic.values() if ki.comparable}
    cand = defaultdict(list)
    for r in raws:
        ki = dic.get(norm_label(r.label))
        if ki is None or not ki.comparable or r.text in (None, ""):
            continue
        cand[ki.key].append((r, parse_value(r.text, r.unit), ki))
    out, extra = {}, {}
    for key, items in cand.items():
        first = items[0][0]
        parsed = [(r, p) for r, p, _ in items if p is not None]
        distinct = {(p.dim, p.lo * p.factor, p.hi * p.factor) for _, p in parsed}
        urls = [r.url for r, _, _ in items if r.url]
        if len(items) == 1 and not parsed:                            # one cell without a single figure: several values?
            r, _, ki = items[0]
            pm = parse_multi(r.text, r.unit)
            if pm:
                for cond, pp, seg in pm:
                    sub = condition_key(key, cond, keys)
                    if sub and sub not in cand and sub not in extra:
                        extra[sub] = Side(f"{r.label} ({cond})", seg, r.unit, pp, r.url, r.group, r.order, False, [r.url] if r.url else [])
                if ki.better == "higher":
                    top = max(pm, key=lambda t: t[1].hi * t[1].factor)
                    out[key] = Side(r.label, r.text, r.unit, top[1], r.url, r.group, r.order, False, urls,
                                    note=f"highest of {len(pm)} stated values ({'; '.join(t[2] for t in pm)})")
                    continue
        if len(items) == 1 or not parsed:                             # one spec, or none holds a figure: the first
            r, p = (parsed[0] if parsed else (first, None))
            out[key] = Side(r.label, r.text, r.unit, p, r.url, r.group, r.order, False, urls)
        elif len(distinct) == 1:                                      # the same figure repeated (duplicate labels): keep it
            r, p = parsed[0]
            out[key] = Side(r.label, r.text, r.unit, p, r.url, r.group, r.order, False, urls)
        else:
            texts = list(dict.fromkeys(r.text for r, _, _ in items))[:3]
            out[key] = Side(first.label, "; ".join(texts), None, None, first.url, first.group, first.order, True, urls)
    for k, sd in extra.items():
        out.setdefault(k, sd)
    return out


def shown(side: Side | None, row_unit: str | None) -> str | None:
    """The stored text; a plain figure keeps its own unit when the row's unit is not that unit (the UI appends the row's unit)."""
    if side is None or side.text is None:
        return None
    t = side.text
    own = side.parsed.unit if side.parsed and side.parsed.unit else side.unit
    if PLAIN_FIGURE.match(t.strip()) and own and (row_unit is None or own.strip().lower() != row_unit.strip().lower()):
        return f"{t} {own}"
    return t


def num(x: D | None):
    return None if x is None else x.quantize(D("0.000001"))


@dataclass
class SpecRow:
    key: str
    label: str
    group: str | None
    client_text: str | None
    client_num: D | None
    competitor_text: str | None
    competitor_num: D | None
    unit: str | None
    side: str | None
    state: str
    gap: D | None
    why: str
    client_url: str | None
    competitor_url: str | None
    client_label: str | None
    competitor_label: str | None
    order: int = 0


def compare_key(key: str, ki: KeyInfo, cs: Side | None, ks: Side | None) -> SpecRow:
    label = clean_label((cs or ks).label)
    group = cs.group if cs else None
    base = dict(key=key, label=label, group=group, client_url=cs.url if cs else None, competitor_url=ks.url if ks else None,
                client_label=cs.label if cs else None, competitor_label=ks.label if ks else None,
                order=cs.order if cs else 10_000 + (ks.order if ks else 0))
    if cs is None or ks is None:
        one = cs or ks
        unit = (one.parsed.unit if one.parsed and one.parsed.unit else one.unit) or None
        who = "client" if cs else "competitor"
        return SpecRow(client_text=shown(cs, unit), client_num=None, competitor_text=shown(ks, unit), competitor_num=None,
                       unit=unit, side=None, state="one_sided", gap=None, why=f"only the {who} has a value", **base)
    v = None
    why = None
    if cs.ambiguous or ks.ambiguous:
        why = "a side holds several differing values"
    elif cs.parsed is None or ks.parsed is None:
        why = "a value is not a plain figure (text, qualifier, several figures or unknown unit)"
    elif not (family_ok(ki.family, cs.parsed) and family_ok(ki.family, ks.parsed)) or cs.parsed.dim != ks.parsed.dim:
        why = f"units differ ({cs.parsed.unit or 'no unit'} vs {ks.parsed.unit or 'no unit'}: not the same quantity)"
    else:
        v = compare_values(cs.parsed, ks.parsed, ki.family, ki.better, EQUAL_BAND)
    if v is None:
        unit = None
        return SpecRow(client_text=shown(cs, unit), client_num=None, competitor_text=shown(ks, unit), competitor_num=None,
                       unit=unit, side=None, state="not_comparable", gap=None, why=why or "not comparable", **base)
    if not v.decided:
        return SpecRow(client_text=shown(cs, None), client_num=None, competitor_text=shown(ks, None), competitor_num=None,
                       unit=None, side=None, state="not_comparable", gap=None, why=v.note or "a bound does not decide", **base)
    unit = v.unit or None
    notes = [n for n in (cs.note, ks.note, v.note) if n]
    if ki.better == "none":
        state, side, gap = ("comparable" if NEUTRAL_AS_COMPARABLE else "not_comparable"), None, (v.gap if NEUTRAL_AS_COMPARABLE else None)
        why = f"neither side is better for this parameter{': ' + ki.reason if ki.reason else ''}"
    else:
        state, side, gap = "comparable", v.side, v.gap
        tag = "comparable (bound)" if any("bound" in n for n in notes) else ("comparable (approximate)" if any("approximate" in n for n in notes) else "")
        why = (f"{tag}: " if tag else "") + f"{ki.better} is better{': ' + ki.reason if ki.reason else ''}"
        if notes:
            why += "; " + "; ".join(notes)
    return SpecRow(client_text=shown(cs, unit), client_num=num(v.client_num), competitor_text=shown(ks, unit),
                   competitor_num=num(v.competitor_num), unit=unit, side=side, state=state, gap=gap, why=why, **base)


STATE_RANK = {"comparable": 0, "not_comparable": 1, "one_sided": 2}


TOWED = {"towed_howitzer", "light_gun_105"}
_NOT_SYSTEM_MASS = re.compile(r"barrel|projectile|shell|round|ammo|ammunition|charge|warhead|payload|recoil|breech|cradle|trail")


def towed_rules(keyinfo: dict) -> dict:
    """A towed gun is towed, airlifted and emplaced by its crew: the lighter system is the better one (user rule 2026-10-18). The
    dictionary keeps 'neither' for weight because a self-propelled or armoured system's weight can mean protection."""
    from dataclasses import replace
    return {k: (replace(ki, better="lower", reason="Towed gun: a lighter system is easier to tow, airlift and bring into action.")
                if ki.family == "mass" and ki.better == "none" and not _NOT_SYSTEM_MASS.search(k) else ki) for k, ki in keyinfo.items()}


def compare_pair(csides: dict, ksides: dict, keyinfo: dict, max_rows: int = MAX_ROWS):
    """(rows, comparable_count, sourced_count, edge_score, decision_level) for one pair; the numbers come from derive.py."""
    rows = [compare_key(k, keyinfo[k], csides.get(k), ksides.get(k)) for k in sorted(set(csides) | set(ksides))]
    rows.sort(key=lambda r: (STATE_RANK[r.state], r.order, r.key))
    rows = rows[:max_rows]
    comparable = [r for r in rows if r.state == "comparable"]
    score, level = derive.score_sides([r.side for r in comparable])
    sourced = [r for r in rows if r.client_text not in (None, "") or r.competitor_text not in (None, "")]
    return rows, len(comparable), len(sourced), score, level


def match_basis(basis: str, comparable: int) -> str:
    return f"{basis}; {comparable} comparable specs {MARKER}"


def pair_ids(pair_key: str, n_specs: int, n_sources: int) -> tuple:
    mid = make_id("bigint", id_seed("matchup", pair_key, "competitive_matchup", 0))
    specs = [make_id("bigint", id_seed("matchup", pair_key, "competitive_matchup_specification", n)) for n in range(n_specs)]
    srcs = [make_id("bigint", id_seed("matchup", pair_key, "competitive_matchup_source", n)) for n in range(n_sources)]
    return mid, specs, srcs


# =====================================================================================================
# step 3: database part
# =====================================================================================================

def connect():
    import psycopg2
    import psycopg2.extras
    from prompts import batch
    dsn = batch.resolve_dsn("local")
    p = psycopg2.extensions.parse_dsn(dsn)
    if p.get("host") not in ("127.0.0.1", "localhost", None) or p.get("dbname") != "kssl_staging":
        raise SystemExit(f"refusing: this tool writes only to the local kssl_staging (got {p.get('host')}/{p.get('dbname')})")
    conn = psycopg2.connect(dsn, connect_timeout=5, cursor_factory=psycopg2.extras.RealDictCursor)
    print(f"database: local {p.get('host', '127.0.0.1')}:{p.get('port', 5432)}/{p.get('dbname')}", flush=True)
    return conn


def load_dictionary(cur) -> tuple[dict, dict]:
    """({category_lower: {norm label: KeyInfo}}, {category_lower: {key: KeyInfo}})"""
    cur.execute("SELECT * FROM staging.spec_dictionary")
    by_label, by_key = defaultdict(dict), defaultdict(dict)
    for r in cur.fetchall():
        ki = KeyInfo(r["canonical_key"], r["unit_family"], r["better"], r["comparable"], r["reason"])
        c = r["category"].strip().lower()
        by_label[c][r["raw_label_norm"]] = ki
        if ki.comparable:
            by_key[c].setdefault(ki.key, ki)
    return by_label, by_key


PAIRS_UNGATED_SQL = """
    SELECT cp.client_product_id, p.product_id, c.competitor_id,
           cp.product_name AS client_product, p.product_name AS competitor_product,
           c.display_name AS competitor, c.origin_country AS competitor_country, p.category AS category,
           cp.client_product_id::text || '|' || p.product_id::text AS pair_key
    FROM staging.client_product cp
    JOIN staging.competitive_product p ON lower(trim(p.category)) = lower(trim(cp.category))
    JOIN staging.competitive_competitor c ON c.competitor_id = p.competitor_id
    WHERE EXISTS (SELECT 1 FROM staging.client_product_specification s WHERE s.client_product_id = cp.client_product_id)
      AND EXISTS (SELECT 1 FROM staging.competitive_product_specification s WHERE s.product_id = p.product_id)
    ORDER BY p.category, cp.product_name, c.display_name, p.product_name"""      # matchup.yml's query before the like-for-like gate


# The like-for-like pairs (rule: prompts/matchup_class.py gate(); classes in staging.product_class). It lived in matchup.yml's subject
# until matchup.yml became the verdict prompt over STORED pairs (subject = matchup_id); kept here so the engine needs no prompt file.
PAIRS_GATED_SQL = """WITH wb(cat, band, idx) AS (VALUES
     ('artillery', 'under 1 t', 0),
     ('artillery', '1-5 t', 1),
     ('artillery', '5-20 t', 2),
     ('artillery', '20-40 t', 3),
     ('artillery', 'over 40 t', 4),
     ('small arms', 'under 1 kg', 0),
     ('small arms', '1-3 kg', 1),
     ('small arms', '3-6 kg', 2),
     ('small arms', '6-12 kg', 3),
     ('small arms', 'over 12 kg', 4),
     ('uavs & drones', 'under 2 kg', 0),
     ('uavs & drones', '2-25 kg', 1),
     ('uavs & drones', '25-150 kg', 2),
     ('uavs & drones', '150-600 kg', 3),
     ('uavs & drones', '600-5000 kg', 4),
     ('uavs & drones', 'over 5000 kg', 5),
     ('protected & armoured vehicles', 'under 6 t', 0),
     ('protected & armoured vehicles', '6-15 t', 1),
     ('protected & armoured vehicles', '15-30 t', 2),
     ('protected & armoured vehicles', '30-50 t', 3),
     ('protected & armoured vehicles', 'over 50 t', 4),
     ('missiles & air defence', 'under 25 kg', 0),
     ('missiles & air defence', '25-150 kg', 1),
     ('missiles & air defence', '150-1000 kg', 2),
     ('missiles & air defence', '1000-5000 kg', 3),
     ('missiles & air defence', 'over 5000 kg', 4),
     ('marine / naval', 'under 100 t', 0),
     ('marine / naval', '100-1000 t', 1),
     ('marine / naval', '1000-5000 t', 2),
     ('marine / naval', 'over 5000 t', 3))
SELECT cp.client_product_id, p.product_id, c.competitor_id,
       cp.product_name AS client_product, p.product_name AS competitor_product,
       c.display_name AS competitor, c.origin_country AS competitor_country, p.category AS category,
       cp.client_product_id::text || '|' || p.product_id::text AS pair_key
FROM staging.client_product cp
JOIN staging.competitive_product p ON lower(trim(p.category)) = lower(trim(cp.category))
JOIN staging.competitive_competitor c ON c.competitor_id = p.competitor_id
JOIN staging.product_class kc ON kc.product_side = 'client' AND kc.product_id = cp.client_product_id::text
JOIN staging.product_class kp ON kp.product_side = 'competitor' AND kp.product_id = p.product_id::text
WHERE EXISTS (SELECT 1 FROM staging.client_product_specification s WHERE s.client_product_id = cp.client_product_id)
  AND EXISTS (SELECT 1 FROM staging.competitive_product_specification s WHERE s.product_id = p.product_id)
  AND kc.sub_type <> 'unknown' AND kc.sub_type = kp.sub_type
  AND (lower(trim(cp.category)) NOT IN ('artillery', 'small arms', 'ammunition')
       OR kc.sub_type IN ('support_equipment', 'accessory', 'fuze_component', 'bomb_warhead')
       OR (kc.calibre_mm IS NOT NULL AND kp.calibre_mm IS NOT NULL
           AND abs(kc.calibre_mm - kp.calibre_mm) <= greatest(0.06, 0.005 * greatest(kc.calibre_mm, kp.calibre_mm))))
  AND (NOT EXISTS (SELECT 1 FROM wb WHERE wb.cat = lower(trim(cp.category)))
       OR EXISTS (SELECT 1 FROM wb a JOIN wb b ON b.cat = a.cat
                  WHERE a.cat = lower(trim(cp.category)) AND a.band = kc.weight_class AND b.band = kp.weight_class
                    AND abs(a.idx - b.idx) <= 1))
  AND (kc.barrel_cal IS NULL OR kp.barrel_cal IS NULL OR abs(kc.barrel_cal - kp.barrel_cal) <= {BARREL_GAP})
  AND ((lower(trim(cp.category)), kc.sub_type) NOT IN ({ROLE_SUBTYPES}) OR (kc.role IS NOT NULL AND kc.role = kp.role))
ORDER BY p.category, cp.product_name, c.display_name, p.product_name"""
PAIRS_GATED_SQL = PAIRS_GATED_SQL.replace("{BARREL_GAP}", str(matchup_class.BARREL_GAP)).replace(        # the same rule as matchup_class.gate()
    "{ROLE_SUBTYPES}", ", ".join(f"('{c}', '{st}')" for c, st in matchup_class.ROLES))


def load_pairs(cur, gated_yaml: bool = False) -> list:
    """The like-for-like pairs (gated_yaml) or the same query without the gate (to count what the gate removes)."""
    cur.execute(PAIRS_GATED_SQL if gated_yaml else PAIRS_UNGATED_SQL)
    return [dict(r) for r in cur.fetchall() if (r["category"] or "").strip().lower() not in SKIP_CATEGORIES]


def load_specs(cur, categories: set) -> tuple[dict, dict]:
    """(client_product_id -> [Raw], product_id -> [Raw]) for the given lower-case categories."""
    cur.execute("""SELECT s.client_product_id AS pid, s.spec_name, s.spec_group, s.display_order,
                          coalesce(nullif(s.value_text, ''), s.value_numeric::text) AS v, s.value_numeric, s.unit, src.source_url
                   FROM staging.client_product_specification s
                   JOIN staging.client_product p USING (client_product_id)
                   LEFT JOIN staging.client_product_source src ON src.source_id = s.source_id AND src.client_product_id = s.client_product_id
                   WHERE lower(trim(p.category)) = ANY(%s) ORDER BY s.client_product_id, s.display_order""", (list(categories),))
    cl = defaultdict(list)
    for r in cur.fetchall():
        v = r["v"]
        if r["value_numeric"] is not None and (r["v"] is None or str(r["v"]).strip() == str(r["value_numeric"])):
            v = format(r["value_numeric"].normalize(), "f")
        cl[r["pid"]].append(Raw(r["spec_name"], v, r["unit"], usable_url(r["source_url"]), r["spec_group"], r["display_order"] or 0))
    cur.execute("""SELECT s.product_id AS pid, s.spec_label, s.spec_value, s.unit, s.source_url
                   FROM staging.competitive_product_specification s JOIN staging.competitive_product p USING (product_id)
                   WHERE lower(trim(p.category)) = ANY(%s) ORDER BY s.product_id, s.spec_label""", (list(categories),))
    co = defaultdict(list)
    for r in cur.fetchall():
        co[r["pid"]].append(Raw(r["spec_label"], r["spec_value"], r["unit"], usable_url(r["source_url"]), None, 0))
    return cl, co


def host(url):
    from backend.sources import host_of
    return host_of(url)


BLOCKED_HOSTS = ("idrw.org", "ajaishukla.com")      # blog domains being purged from staging: never used as a source here


def usable_url(url):
    h = host(url) if url else ""
    return None if (not url or any(h == b or h.endswith("." + b) for b in BLOCKED_HOSTS)) else url


def run_compare(conn, only: str | None, dry: bool, limit: int | None, gated: bool = True, relax_weight: bool = False) -> dict:
    import psycopg2.extras
    from backend.sources import classify
    from prompts import render
    from prompts.loader import Loader
    cur = conn.cursor()
    by_label, by_key = load_dictionary(cur)
    if not by_label:
        raise SystemExit("staging.spec_dictionary is empty: run the dictionary step first")
    pairs = load_pairs(cur)
    if only:
        pairs = [p for p in pairs if (p["category"] or "").strip().lower() == only.strip().lower()]
    if limit:
        pairs = pairs[:limit]
    from prompts import matchup_class
    gate_stats = defaultdict(lambda: {"before": 0, "after": 0, "after_relaxed_weight": 0, "unclassified": 0})
    classes = matchup_class.load_classes(cur)
    all_cats = {p["category"] for p in pairs}                  # every category of this run, also when the gate leaves it no pair
    kept = []
    for p in pairs:
        g = gate_stats[p["category"]]
        g["before"] += 1
        ca = classes.get(("client", str(p["client_product_id"])))
        cb = classes.get(("competitor", str(p["product_id"])))
        if ca is None or cb is None:
            g["unclassified"] += 1
        c = p["category"].strip().lower()
        if ca and cb and matchup_class.gate(c, ca, cb, relaxed_weight=True):
            g["after_relaxed_weight"] += 1
        if gated:
            if not (ca and cb and matchup_class.gate(c, ca, cb, relaxed_weight=relax_weight)):
                continue
            p["basis"] = matchup_class.basis(p["category"], ca, cb)
            p["sub_type"] = ca["sub_type"]
        g["after"] += 1
        kept.append(p)
    pairs = kept
    if gated and not relax_weight and not limit:                 # the YAML query (SQL) and this engine (Python) must apply one rule
        want = {p["pair_key"] for p in load_pairs(cur, gated_yaml=True) if not only or (p["category"] or "").strip().lower() == only.strip().lower()}
        have = {p["pair_key"] for p in pairs}
        print(f"gate check: matchup.yml query {len(want)} pairs, engine {len(have)} pairs, "
              + ("identical" if want == have else f"DIFFERENT ({len(want - have)} only in the query, {len(have - want)} only in the engine)"), flush=True)
    cats = {(p["category"] or "").strip().lower() for p in pairs}
    cl_raw, co_raw = load_specs(cur, cats)
    cur.execute("SELECT subject_key FROM staging.prompt_run WHERE prompt_id = 'matchup' AND status = 'loaded'")
    ai_pairs = {r["subject_key"] for r in cur.fetchall()}
    cur.execute("SELECT matchup_id, match_basis FROM staging.competitive_matchup")
    existing = {r["matchup_id"]: (r["match_basis"] or "") for r in cur.fetchall()}
    loader = Loader(cur, "matchup", "", {}, None, render.client_row(cur))
    tier_cache: dict = {}

    def tier(url):
        if url not in tier_cache:
            t = classify(url, loader.company_domains(url))
            tier_cache[url] = (t or "unlisted", host(url))
        return tier_cache[url]

    side_cache: dict = {}

    def sides(kind, pid, raws, cat):
        k = (kind, pid)
        if k not in side_cache:
            side_cache[k] = resolve_sides(raws, by_label[cat])
        return side_cache[k]

    now = datetime.now(timezone.utc)
    per_cat: dict = defaultdict(lambda: {"pairs": 0, "with_comparable": 0, "specs_compared": 0, "levels": Counter(), "skipped_ai": 0,
                                         "rows": 0, "one_sided": 0, "not_comparable": 0})
    out = defaultdict(lambda: {"m": [], "s": [], "src": [], "fs": [], "ids": set()})
    for p in pairs:
        cat_name = p["category"]
        cat = cat_name.strip().lower()
        st = per_cat[cat_name]
        pair_key = p["pair_key"]
        mid0 = make_id("bigint", id_seed("matchup", pair_key, "competitive_matchup", 0))
        if pair_key in ai_pairs or (mid0 in existing and MARKER not in existing[mid0]):
            st["skipped_ai"] += 1
            continue
        cs = sides("c", p["client_product_id"], cl_raw.get(p["client_product_id"], []), cat)
        ks = sides("k", p["product_id"], co_raw.get(p["product_id"], []), cat)
        rows, ncomp, nsrc, score, level = compare_pair(cs, ks, towed_rules(by_key[cat]) if p.get("sub_type") in TOWED else by_key[cat])
        st["pairs"] += 1
        st["with_comparable"] += ncomp > 0
        st["specs_compared"] += ncomp
        st["levels"][level] += 1
        st["rows"] += len(rows)
        st["one_sided"] += sum(r.state == "one_sided" for r in rows)
        st["not_comparable"] += sum(r.state == "not_comparable" for r in rows)
        urls: dict = {}
        for r in rows:
            for u in (r.client_url, r.competitor_url):
                if u:
                    urls.setdefault(u, None)
        mid, sids, srcids = pair_ids(pair_key, len(rows), len(urls))
        o = out[cat_name]
        o["ids"].add(mid)
        o["m"].append((mid, cat_name, p["client_product_id"], p["client_product"][:240], p["competitor_id"],
                       (p["competitor"] or "")[:240], (p["competitor_country"] or None), p["product_id"],
                       p["competitor_product"][:240], match_basis(p.get("basis") or f"Same category ({cat_name})", ncomp), ncomp, nsrc, score, level, now, now))
        for n, r in enumerate(rows):
            o["s"].append((sids[n], mid, n + 1, r.label[:180], (r.group or None), (r.unit or None) and r.unit[:60],
                           r.client_text, r.client_num, r.competitor_text, r.competitor_num, r.side, r.state, r.gap))
            cv = f"{r.client_label}: {r.client_text}" if r.client_text else "no value"
            kv = f"{r.competitor_label}: {r.competitor_text}" if r.competitor_text else "no value"
            o["fs"].append(("competitive_matchup_specification", str(sids[n]), "better_side", "judgement", "judgement", None,
                            f"code comparison: {r.client_text or '-'} vs {r.competitor_text or '-'}; {r.why}"))
            if r.state == "comparable" and r.side:
                for url, q in ((r.client_url, cv), (r.competitor_url, kv)):
                    if url:
                        t, pub = tier(url)
                        o["fs"].append(("competitive_matchup_specification", str(sids[n]), "better_side", url, t, pub, q))
        for n, u in enumerate(urls):
            o["src"].append((srcids[n], mid, host(u) or u[:240], u, "stored_spec"))
    for c in all_cats:
        per_cat[c]["gate"] = gate_stats[c]
        out[c]                                                   # a category the gate emptied still gets its old code rows removed
    if dry:
        return per_cat
    ins = {
        "m": """INSERT INTO staging.competitive_matchup (matchup_id, category_code, client_product_id, client_product_name, competitor_id,
                competitor_name, competitor_country, competitor_product_id, competitor_product_name, match_basis, comparable_spec_count,
                sourced_spec_count, edge_score, decision_level, created_at, updated_at) VALUES %s""",
        "s": """INSERT INTO staging.competitive_matchup_specification (comparison_specification_id, matchup_id, display_order, spec_label,
                spec_group, unit, client_value_text, client_value_numeric, competitor_value_text, competitor_value_numeric, better_side,
                comparability_state, gap_value) VALUES %s""",
        "src": """INSERT INTO staging.competitive_matchup_source (source_id, matchup_id, source_label, source_url, source_type) VALUES %s""",
        "fs": """INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote)
                 VALUES %s""",
    }
    for cat_name, o in out.items():
        t0 = time.monotonic()
        cur.execute("""CREATE TEMP TABLE IF NOT EXISTS _mc_old (id bigint) ON COMMIT DROP""")
        cur.execute("TRUNCATE _mc_old")
        # this engine's previous rows: the pairs of this run, and (a full-category run) any other code row of the category
        cur.execute("""INSERT INTO _mc_old SELECT matchup_id FROM staging.competitive_matchup
                       WHERE match_basis LIKE %s AND (matchup_id = ANY(%s) OR (%s AND category_code = %s))""",
                    (f"%{MARKER}", list(o["ids"]), not limit, cat_name))
        # the AI words (prompts/matchup_verdict.py writes them onto these code rows) survive a re-run when the pair's compared rows
        # are unchanged; a pair whose rows changed loses them (stale) and needs the matchup prompt again
        cur.execute("""SELECT m.matchup_id, m.verdict, m.verdict_headline, m.decision_level FROM staging.competitive_matchup m JOIN _mc_old d ON d.id = m.matchup_id
                       WHERE m.verdict IS NOT NULL""")
        words = {r["matchup_id"]: r for r in cur.fetchall()}
        cur.execute("""SELECT matchup_id, spec_label, client_value_text, competitor_value_text, comparability_state, better_side
                       FROM staging.competitive_matchup_specification WHERE matchup_id = ANY(%s) ORDER BY matchup_id, display_order""", (list(words),))
        old_sig: dict = defaultdict(list)
        for r in cur.fetchall():
            old_sig[r["matchup_id"]].append((r["spec_label"], r["client_value_text"], r["competitor_value_text"], r["comparability_state"], r["better_side"]))
        cur.execute("SELECT * FROM staging.competitive_matchup_advantage WHERE matchup_id = ANY(%s)", (list(words),))
        advantages: dict = defaultdict(list)
        for r in cur.fetchall():
            advantages[r["matchup_id"]].append(dict(r))
        new_sig: dict = defaultdict(list)
        for s in sorted(o["s"], key=lambda s: (s[1], s[2])):
            new_sig[s[1]].append((s[3], s[6], s[8], s[11], s[10]))
        cur.execute("""DELETE FROM staging.fact_source f USING staging.competitive_matchup_specification s, _mc_old d
                       WHERE f.table_name = 'competitive_matchup_specification' AND f.row_id = s.comparison_specification_id::text
                         AND s.matchup_id = d.id""")
        for t in ("competitive_matchup_specification", "competitive_matchup_source", "competitive_matchup_advantage"):
            cur.execute(f"DELETE FROM staging.{t} x USING _mc_old d WHERE x.matchup_id = d.id")
        cur.execute("DELETE FROM staging.competitive_matchup x USING _mc_old d WHERE x.matchup_id = d.id")
        for k in ("m", "s", "src", "fs"):
            psycopg2.extras.execute_values(cur, ins[k], o[k], page_size=4000)
        kept = [mid for mid in words if mid in o["ids"] and new_sig.get(mid) == old_sig.get(mid)]
        for mid in kept:
            cur.execute("UPDATE staging.competitive_matchup SET verdict = %s, verdict_headline = %s, decision_level = %s WHERE matchup_id = %s",
                        (words[mid]["verdict"], words[mid]["verdict_headline"], words[mid]["decision_level"], mid))
            for a in advantages.get(mid, []):
                cur.execute(f"INSERT INTO staging.competitive_matchup_advantage ({', '.join(a)}) VALUES ({', '.join(['%s'] * len(a))})", list(a.values()))
        conn.commit()
        print(f"  [{cat_name}] wrote {len(o['m'])} matchups, {len(o['s'])} spec rows, {len(o['src'])} sources, "
              f"{len(o['fs'])} fact_source rows in {time.monotonic() - t0:.1f}s; AI verdicts kept {len(kept)}, "
              f"dropped as stale {len(words) - len(kept)}", flush=True)
    return per_cat


def print_stats(per_cat: dict) -> None:
    print("\nlike-for-like gate (pairs of the matchup.yml query, category 'Other' excluded):")
    print(f"{'category':34}{'before':>8}{'after':>8}{'after, weight unknown ok':>26}{'pairs with an unclassified product':>36}")
    for c, s in sorted(per_cat.items()):
        g = s.get("gate")
        if g:
            print(f"{c:34}{g['before']:>8}{g['after']:>8}{g['after_relaxed_weight']:>26}{g['unclassified']:>36}")
    print(f"\n{'category':34}{'pairs':>7}{'>=1 cmp':>9}{'cmp specs':>10}{'rows':>8}  decision levels (1 behind / 2 parity / 3 ahead / none)   AI-kept")
    tot = Counter()
    for c, s in sorted(per_cat.items()):
        lv = s["levels"]
        print(f"{c:34}{s['pairs']:>7}{s['with_comparable']:>9}{s['specs_compared']:>10}{s['rows']:>8}  "
              f"{lv.get(1, 0)} / {lv.get(2, 0)} / {lv.get(3, 0)} / {lv.get(None, 0)}   {s['skipped_ai']}")
        for k in ("pairs", "with_comparable", "specs_compared", "rows"):
            tot[k] += s[k]
        for l in (1, 2, 3, None):
            tot[f"l{l}"] += lv.get(l, 0)
    print(f"{'TOTAL':34}{tot['pairs']:>7}{tot['with_comparable']:>9}{tot['specs_compared']:>10}{tot['rows']:>8}  "
          f"{tot['l1']} / {tot['l2']} / {tot['l3']} / {tot['lNone']}")


# =====================================================================================================
# self-check
# =====================================================================================================

def _selftest() -> None:
    spec_values._selftest()
    fam = {"towing_speed": "speed", "max_towing_speed": "speed", "max_range": "length", "crew": "count"}
    g, pr = valid_merges({"groups": [{"keep": "towing_speed", "merge": ["max_towing_speed"]}, {"keep": "max_range", "merge": ["crew"]},
                                     {"keep": "x", "merge": ["crew"]}, {"keep": "max_towing_speed", "merge": ["towing_speed"]}]}, fam)
    assert [x["keep"] for x in g] == ["towing_speed"] and len(pr) == 3
    assert norm_label("� Max. Range (km)") == "max range km" and norm_label("Rate-of-fire") == "rate of fire"
    assert clean_label("� Weight:") == "Weight"
    # ids: the scheme the matchup prompt uses for the card (checked against a loaded AI run of ATAGS vs K9 Thunder)
    assert make_id("bigint", id_seed("matchup", "101|796708c1-e374-512b-b9b4-67c3a68f1c2a", "competitive_matchup", 0)) == 3372401693024032672
    mid, sids, srcs = pair_ids("1|x", 3, 2)
    assert len(set(sids + srcs + [mid])) == 6 and mid == pair_ids("1|x", 1, 0)[0]
    # dictionary validation
    env = {"items": [{"id": 1, "key": "Max Range", "family": "length", "better": "higher", "comparable": True, "reason": "Longer reach."},
                     {"id": 2, "key": "note", "family": "text", "better": "none", "comparable": True},
                     {"id": 2, "key": "dup", "family": "text", "better": "none", "comparable": False},
                     {"id": 9, "key": "x", "family": "length", "better": "higher", "comparable": True},
                     {"id": 3, "key": "y", "family": "speed", "better": "faster", "comparable": True}]}
    ok, problems = validate_items(env, {1, 2, 3})
    assert set(ok) == {1, 2} and ok[1]["key"] == "max_range" and ok[2]["comparable"] is False, ok     # text -> not comparable
    assert len(problems) == 3, problems                                                                # dup, unknown, bad better
    es = [Entry("c", "a", "k", "length", "higher", True, "r", "m"), Entry("c", "b", "k", "length", "higher", True, None, "m"),
          Entry("c", "d", "k", "mass", "lower", True, "z", "m")]
    unify_keys(es)
    assert {(e.family, e.better) for e in es} == {("length", "higher")}
    # a fictional pair end to end
    dic = {norm_label(a): KeyInfo(k, f, b, c, r) for a, k, f, b, c, r in [
        ("Max range", "max_range", "length", "higher", True, "Longer reach."), ("Range", "max_range", "length", "higher", True, None),
        ("Weight", "weight", "mass", "lower", True, "Lighter moves easier."), ("Combat weight", "weight", "mass", "lower", True, None),
        ("Calibre", "calibre", "length", "none", True, "Neither is better."), ("Crew", "crew", "count", "none", True, None),
        ("Speed", "speed", "speed", "higher", True, "Faster."), ("Role", "role", "text", "none", False, None),
        ("Burst", "burst", "rate", "higher", True, "Faster fire."), ("Elevation", "elev", "angle", "higher", True, "Wider.")]}
    cr = [Raw("Max range", "30", "km", "https://c/1", "Performance", 1), Raw("Weight", "16 t", None, "https://c/1", "Mobility", 2),
          Raw("Calibre", "155 mm / 52 cal", None, "https://c/2", "Gun", 3), Raw("Role", "Howitzer", None, None, None, 4),
          Raw("Speed", "80 km/h (KSSL page); 60 km/h (Janes)", None, "https://c/2", None, 5), Raw("Crew", "6", None, None, None, 6),
          Raw("Burst", "6 rounds in 30 s", None, None, None, 7)]
    kr = [Raw("� Range", "28000 m", None, "https://k/1"), Raw("Range", "28000 m", None, "https://k/1"), Raw("Combat weight", "46.3 t (src)", None, "https://k/1"),
          Raw("Calibre", "155 mm", None, "https://k/1"), Raw("Speed", "67 km/h", None, "https://k/1"), Raw("Role", "x", None, None),
          Raw("Crew", "over 3", None, None), Raw("Burst", "3 rounds in 15 s", None, "https://k/2"), Raw("Elevation", "-3 to 72 deg", None, None)]
    cs, ks = resolve_sides(cr, dic), resolve_sides(kr, dic)
    assert "role" not in cs and ks["max_range"].text == "28000 m"                 # descriptive dropped; duplicate rows collapse
    ki = {v.key: v for v in dic.values() if v.comparable}
    rows, ncomp, nsrc, score, level = compare_pair(cs, ks, ki)
    by = {r.key: r for r in rows}
    assert by["max_range"].state == "comparable" and by["max_range"].side == "client" and by["max_range"].unit == "km"
    assert by["max_range"].competitor_num == 28 and by["max_range"].competitor_text == "28000 m" and by["max_range"].gap == D("6.90")
    assert by["weight"].side == "client" and by["weight"].client_num == 16 and by["weight"].competitor_num == D("46.3")
    assert by["calibre"].state == "not_comparable" and by["calibre"].side is None and by["calibre"].client_num == 155   # neutral key
    assert by["speed"].state == "comparable" and by["speed"].side == "client" and "highest of 2" in by["speed"].why      # 80 (KSSL) vs 60 (Janes): the highest, marked
    assert by["crew"].state == "not_comparable"                                                                        # 'over 3' is a qualifier
    assert by["burst"].state == "comparable" and by["burst"].side == "equal" and by["burst"].gap == 0                   # 12 vs 12 rounds/min
    assert by["elev"].state == "one_sided" and by["elev"].client_text is None and by["elev"].competitor_text == "-3 to 72 deg"
    assert ncomp == 4 and score == derive.edge_score(3, 3) and level == derive.decision_level(score) == 3, (ncomp, score, level)
    assert [r.state for r in rows] == sorted((r.state for r in rows), key=STATE_RANK.get)
    assert len(compare_pair(cs, ks, ki, max_rows=2)[0]) == 2
    tw = towed_rules({"total_mass": KeyInfo("total_mass", "mass", "none", True, None), "barrel_weight": KeyInfo("barrel_weight", "mass", "none", True, None),
                      "max_range": KeyInfo("max_range", "length", "higher", True, None)})
    assert tw["total_mass"].better == "lower" and tw["barrel_weight"].better == "none" and tw["max_range"].better == "higher"
    # a lower-is-better loss
    r2 = compare_key("weight", ki["weight"], resolve_sides([Raw("Weight", "50 t")], dic)["weight"], resolve_sides([Raw("Weight", "16 t")], dic)["weight"])
    assert r2.side == "competitor" and r2.gap == D("103.03")
    # a plain figure keeps its own unit when the row unit is another
    r3 = compare_key("max_range", ki["max_range"], None, resolve_sides([Raw("Range", "40", "km")], dic)["max_range"])
    assert r3.competitor_text == "40" and r3.unit == "km" and r3.state == "one_sided"
    # qualified and multi-value cells
    dic2 = dict(dic)
    dic2.update({norm_label(a): KeyInfo(k, f, b, c, r) for a, k, f, b, c, r in [
        ("Max range he", "max_range_he", "length", "higher", True, None), ("Max range erfb bb", "max_range_erfb_bb", "length", "higher", True, None),
        ("Coming into action", "coming_into_action", "time", "lower", True, "Faster.")]})
    ki2 = {v.key: v for v in dic2.values() if v.comparable}
    c1 = resolve_sides([Raw("Max range", "40", "km", "https://c/1"), Raw("Max range HE", "30", "km", "https://c/1"),
                        Raw("Coming into action", "2.5 min", None, "https://c/1")], dic2)
    k1 = resolve_sides([Raw("Range", "30 km (HE), 40 km (ERFB-BB)", None, "https://k/1"), Raw("Coming into action", "within 90 s", None)], dic2)
    assert k1["max_range"].parsed.hi == 40 and "highest of 2" in k1["max_range"].note
    assert k1["max_range_erfb_bb"].parsed.hi == 40 and k1["max_range_erfb_bb"].label == "Range (ERFB-BB)" and k1["max_range_he"].parsed.hi == 30
    assert "max_range_he" in c1 and c1["max_range_he"].text == "30"                # an explicit label is not overwritten by a split
    rows2, ncomp2, *_ = compare_pair(c1, k1, ki2)
    by2 = {r.key: r for r in rows2}
    assert by2["max_range"].state == "comparable" and by2["max_range"].side == "equal" and "highest of 2" in by2["max_range"].why
    assert by2["max_range_he"].side == "equal" and by2["max_range_he"].client_url == "https://c/1" and by2["max_range_erfb_bb"].state == "one_sided"
    kb = resolve_sides([Raw("Range", "over 40 km")], dic2)
    cb = resolve_sides([Raw("Max range", "30", "km")], dic2)
    r5 = compare_key("max_range", ki2["max_range"], cb["max_range"], kb["max_range"])
    assert r5.state == "comparable" and r5.side == "competitor" and r5.why.startswith("comparable (bound)") and r5.competitor_num == 40
    cb = resolve_sides([Raw("Max range", "45", "km")], dic2)
    r6 = compare_key("max_range", ki2["max_range"], cb["max_range"], kb["max_range"])
    assert r6.state == "not_comparable" and r6.client_num is None and r6.competitor_num is None and "does not decide" in r6.why
    ka = resolve_sides([Raw("Range", "~38 km")], dic2)
    r7 = compare_key("max_range", ki2["max_range"], resolve_sides([Raw("Max range", "30", "km")], dic2)["max_range"], ka["max_range"])
    assert r7.side == "competitor" and r7.why.startswith("comparable (approximate)") and r7.gap == D("23.53")
    assert match_basis("Same category (Artillery)", 5) == "Same category (Artillery); 5 comparable specs (code comparison)"
    from prompts import matchup_class
    matchup_class._selftest()
    print("matchup_code selftest ok")


# =====================================================================================================
# report: top pairs, payload
# =====================================================================================================

def report(conn) -> None:
    cur = conn.cursor()
    cur.execute("""SELECT m.matchup_id, m.client_product_id, m.client_product_name, m.competitor_name, m.competitor_product_id,
                          m.competitor_product_name, m.category_code, m.comparable_spec_count, m.sourced_spec_count, m.edge_score,
                          m.decision_level,
                          (SELECT count(*) FROM staging.competitive_matchup_specification s WHERE s.matchup_id = m.matchup_id
                              AND s.comparability_state IN ('comparable', 'not_comparable')) AS both_sided_specs
                   FROM staging.competitive_matchup m WHERE m.match_basis LIKE %s""", (f"%{MARKER}",))
    rows = [dict(r) for r in cur.fetchall()]
    by_client = defaultdict(list)
    for r in rows:
        r["distance"] = abs(float(r["edge_score"]) - 50) if r["edge_score"] is not None else -1
        by_client[r["client_product_id"]].append(r)
    PER, TIER1, TARGET = 5, 150, 300
    # rank inside a client product: comparable specs, then specs present on both sides (the AI can judge the text ones),
    # then |edge - 50|, then sourced specs
    keyf = lambda r: (-(r["comparable_spec_count"] or 0), -(r["both_sided_specs"] or 0), -r["distance"], -(r["sourced_spec_count"] or 0),
                      r["competitor_name"], r["competitor_product_name"])
    out = []
    for cid, rs in by_client.items():
        rs.sort(key=keyf)
        for rank, r in enumerate(rs, 1):
            r["rank_in_client_product"] = rank
            out.append(r)
    eligible = [r for r in out if (r["both_sided_specs"] or 0) >= 1]
    chosen = [r for r in eligible if r["rank_in_client_product"] <= PER]
    chosen.sort(key=lambda r: (r["rank_in_client_product"], keyf(r)))
    proposed = {r["matchup_id"]: i for i, r in enumerate(chosen[:TARGET])}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "matchup_top_pairs.csv"
    cols = ["client_product_id", "client_product_name", "rank_in_client_product", "competitor_name", "competitor_product_name",
            "category_code", "comparable_spec_count", "both_sided_specs", "sourced_spec_count", "edge_score", "decision_level",
            "proposed_for_ai", "matchup_id"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(out, key=lambda r: (r["client_product_name"], r["rank_in_client_product"])):
            i = proposed.get(r["matchup_id"])
            r["proposed_for_ai"] = "" if i is None else ("tier1" if i < TIER1 else "tier2")
            w.writerow(r)
    print(f"{len(out)} code matchups of {len(by_client)} client products; proposed for the AI step: {len(proposed)} "
          f"(tier1 {min(TIER1, len(proposed))}); wrote {path}")
    print("proposed by category:", dict(Counter(r["category_code"] for r in chosen[:TARGET])))


def unclassified_csv(conn) -> None:
    """Products that cannot be paired because the class is incomplete: sub_type unknown, weight class unknown where the category has
    weight bands, or calibre missing where it applies. The client products come first: these are the specs to supply."""
    from prompts import matchup_class as mcl
    cur = conn.cursor()
    cur.execute("""SELECT pc.product_side, pc.product_id, pc.category, pc.sub_type, pc.calibre_mm, pc.weight_class, pc.reason,
                          coalesce(cp.product_name, p.product_name) AS name, k.display_name AS maker,
                          (SELECT count(*) FROM staging.client_product_specification s WHERE pc.product_side = 'client' AND s.client_product_id::text = pc.product_id)
                        + (SELECT count(*) FROM staging.competitive_product_specification s WHERE pc.product_side = 'competitor' AND s.product_id::text = pc.product_id) AS n_specs
                   FROM staging.product_class pc
                   LEFT JOIN staging.client_product cp ON pc.product_side = 'client' AND cp.client_product_id::text = pc.product_id
                   LEFT JOIN staging.competitive_product p ON pc.product_side = 'competitor' AND p.product_id::text = pc.product_id
                   LEFT JOIN staging.competitive_competitor k ON k.competitor_id = p.competitor_id""")
    out = []
    for r in cur.fetchall():
        c = r["category"].strip().lower()
        missing = []
        if r["sub_type"] == "unknown":
            missing.append("sub_type")
        if mcl.WEIGHT.get(c, mcl.NA) != mcl.NA and r["weight_class"] not in mcl.WEIGHT[c]:
            missing.append(f"weight ({mcl.WEIGHT_WHAT.get(c, 'weight')})")
        if c in mcl.CALIBRE_CATEGORIES and r["sub_type"] not in mcl.CALIBRE_CATEGORIES[c] and r["sub_type"] != "unknown" and r["calibre_mm"] is None:
            missing.append("calibre_mm")
        if missing:
            out.append({"product_side": r["product_side"], "category": r["category"], "product_name": r["name"], "maker": r["maker"] or "",
                        "sub_type": r["sub_type"], "calibre_mm": r["calibre_mm"], "weight_class": r["weight_class"],
                        "missing": " | ".join(missing), "n_specs_on_file": r["n_specs"], "classifier_note": r["reason"], "product_id": r["product_id"]})
    out.sort(key=lambda r: (r["product_side"] != "client", r["category"], r["product_name"] or ""))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "matchup_unclassified.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]) if out else ["product_side"])
        w.writeheader()
        w.writerows(out)
    by = Counter((r["product_side"], r["category"]) for r in out)
    print(f"{len(out)} products with an incomplete class -> {path}")
    for (side, cat), n in sorted(by.items()):
        print(f"  {side:11} {cat:34} {n}")
    print("by what is missing:", dict(Counter(m for r in out for m in r["missing"].split(" | "))))


def payload_sizes() -> None:
    """Size of /api/dataset's `matchups` key and of the whole payload, built like backend/app.py (KSSL_VIEW=review)."""
    import os
    from prompts import batch
    os.environ["KSSL_VIEW"] = "review"
    os.environ["KSSL_STAGING_DSN"] = batch.resolve_dsn("local")
    from backend import app as appmod
    t0 = time.monotonic()
    database = appmod.load_all_tables()
    t1 = time.monotonic()
    payload = appmod.build_dataset(database)
    t2 = time.monotonic()
    raw = {k: len(json.dumps(v, default=str, ensure_ascii=False).encode()) for k, v in payload.items()}
    total = sum(raw.values())
    import gzip
    gz_total = len(gzip.compress(json.dumps(payload, default=str, ensure_ascii=False).encode(), 5))
    gz_m = len(gzip.compress(json.dumps(payload.get("matchups"), default=str, ensure_ascii=False).encode(), 5))
    print(f"read tables {t1 - t0:.1f}s, build {t2 - t1:.1f}s; matchups: {len(payload.get('matchups', {}))}")
    print(f"matchups key: {raw.get('matchups', 0) / 1e6:.1f} MB json ({gz_m / 1e6:.1f} MB gzip); whole payload (no review/schema keys): "
          f"{total / 1e6:.1f} MB json ({gz_total / 1e6:.1f} MB gzip)")
    for k, v in sorted(raw.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {k}: {v / 1e6:.2f} MB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--category")
    ap.add_argument("--dictionary-only", action="store_true")
    ap.add_argument("--compare-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="no model calls, no database writes: print what would happen")
    ap.add_argument("--limit-pairs", type=int)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--report", action="store_true", help="top pairs csv (step 4); with --payload also the /api/dataset sizes")
    ap.add_argument("--payload", action="store_true")
    ap.add_argument("--unclassified", action="store_true", help="write db/excel_reports/matchup_unclassified.csv (products with no sub_type / weight class / calibre)")
    ap.add_argument("--redo-dictionary", action="store_true", help="map labels again even when they are in the dictionary")
    ap.add_argument("--budget", type=float, default=50.0, help="model spend cap for the whole job, USD, counting the call log (default 50)")
    ap.add_argument("--run-budget", type=float, help="model spend cap for THIS run only, USD (the routine); replaces --budget")
    ap.add_argument("--classify-only", action="store_true", help="only the product classification pass (like-for-like gate)")
    ap.add_argument("--relax-weight", action="store_true", help="a product whose weight class is unknown may still pair (default: it may not)")
    ap.add_argument("--redo-classes", action="store_true")
    ap.add_argument("--merge-keys", action="store_true", help="after the dictionary: fold synonym keys per category (1 model call each)")
    ap.add_argument("--merge-pairs", action="store_true", help="only: yes/no per key pair that never meets in a compared pair, fold the yes pairs; then re-run the compare")
    ap.add_argument("--no-gate", action="store_true", help="compare without the like-for-like gate (category only): measurement only, never with writes")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        return
    conn = connect()
    if a.unclassified:
        unclassified_csv(conn)
        return
    if a.report or a.payload:
        if a.report:
            report(conn)
        if a.payload:
            payload_sizes()
        return
    b = Budget(a.run_budget, per_run=True) if a.run_budget is not None else Budget(a.budget)
    if a.merge_pairs:
        merge_pair_keys(conn, a.category, a.dry_run, b)
        print(f"model spend this run ${b.spent - b.prior:.4f} ({b.calls} calls, {b.tin} in / {b.tout} out tokens); job total ${b.spent:.2f} of ${b.limit:.2f}")
        return
    if not (a.compare_only or a.classify_only):
        cats = collect_labels(conn.cursor())
        stats = build_dictionary(conn, cats, a.category, a.dry_run, b, a.redo_dictionary)
        print(f"dictionary: {sum(s['calls'] for s in stats.values())} calls planned/made")
        if a.merge_keys:
            merge_keys(conn, a.category, a.dry_run, b)
    if not (a.compare_only or a.dictionary_only):
        from prompts import matchup_class
        st = matchup_class.classify_products(conn, a.category, a.dry_run, b, a.redo_classes)
        print(f"classification: {sum(s['calls'] for s in st.values())} calls planned/made")
        rs = matchup_class.classify_roles(conn, a.category, a.dry_run, b, a.redo_classes)
        print(f"roles: {sum(s['calls'] for s in rs.values())} calls planned/made")
    print(f"model spend this run ${b.spent - b.prior:.4f} ({b.calls} calls, {b.tin} in / {b.tout} out tokens); job total ${b.spent:.2f} of ${b.limit:.2f}")
    if not (a.dictionary_only or a.classify_only):
        per_cat = run_compare(conn, a.category, a.dry_run, a.limit_pairs, gated=not a.no_gate, relax_weight=a.relax_weight)
        print_stats(per_cat)


if __name__ == "__main__":
    main()
