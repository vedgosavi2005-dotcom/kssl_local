"""The `output:` block of a prompt file, and validation of the model's envelope against it.

    parse_output(output)  -> {table: TableRules}      (extensions: see prompts/FORMAT.md)
    parse_envelope(text)  -> dict                      (strips code fences / prose around the JSON)
    validate(env, prompt_id, output, enums) -> Validated   (Rec trees + rejected rows + warnings)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from backend import review
from backend.sources import is_blocked, is_blog
from prompts import plain_english

GRAPH = review.GRAPH
META_KEYS = ("_sources", "_reason", "_precision")


class EnvelopeError(ValueError):
    """The whole output is unusable (not JSON, wrong prompt_id...)."""


class NotJson(EnvelopeError):
    """The text cannot be parsed as one JSON object (the runner retries the model once)."""


class RowRejected(ValueError):
    """One record (card or child row) is dropped; the message is logged."""


# =====================================================================================================
# output spec
# =====================================================================================================

@dataclass
class TableRules:
    name: str
    card: bool = False
    key: list = field(default_factory=lambda: ["prompt_id", "subject"])
    columns: dict = field(default_factory=dict)       # column -> rules {required,max,enum,enum_from,type,judgement,from_ref}
    loader: dict = field(default_factory=dict)        # column -> token (see prompts/loader.py)
    children: dict = field(default_factory=dict)      # table -> TableRules (model-written)
    loader_children: dict = field(default_factory=dict)   # table -> TableRules (loader_only, built from stored values)
    transient: dict = field(default_factory=dict)     # model field (not stored) -> rules
    refs_decl: dict = field(default_factory=dict)     # extra ref names this table takes -> "table[.col]" or "" (declared only)
    creates: dict = field(default_factory=dict)       # table -> {loader: {...}} find-or-create rows
    rows: list | None = None                          # fixed loader rows
    loader_only: bool = False
    update_only: bool = False
    replace: str | None = None
    top: bool = False
    count: dict | None = None                         # {min, max, where, min_action}: how many rows of this child table a card may have
    dedupe: dict | None = None                        # {column, against, threshold, where}: drop rows that restate a parent column
    reason_pointer: bool = False                      # warn when a judgement's _reason names no sourced fact (A.0.2)

    @property
    def refs(self) -> dict:
        """ref input name -> the column / transient name it fills (a declared-only ref maps to itself)"""
        out = {r["from_ref"]: c for c, r in {**self.columns, **self.transient}.items() if r.get("from_ref")}
        for r in self.refs_decl:
            out.setdefault(r, r)
        return out

    @property
    def plain(self) -> set:
        return {c for c, r in {**self.columns, **self.transient}.items() if not r.get("from_ref")}

    @property
    def model_written(self) -> bool:
        return not (self.loader_only)


RULE_KEYS = ("required", "max", "enum", "enum_from", "type", "judgement", "from_ref", "plain", "unknown_when_empty")
PLAIN_MODES = ("warn", "strict", "off")

# Hard limits of the fixed at-a-glance fields (Fable A.1.2): applied when a prompt does not set its own `max` / `enum`.
BUILTIN_RULES = {
    "glance_who": {"max": 40}, "glance_where": {"max": 40}, "glance_impact": {"max": 40},
    "glance_third_party": {"max": 60}, "glance_when": {"max": 60},
    "glance_move": {"enum": ["Order", "Contract", "Selection", "Delivery", "Induction", "Trial", "Launch", "JV", "MoU", "Acquisition",
                             "Capacity", "Export approval", "Policy", "Supply deal", "Cancellation"]},
    "change_note": {"max": 160}, "kssl_relevance": {"max": 200}, "product_variant": {"max": 60},
}


def _plain_mode(n: str, v) -> str:
    mode = "warn" if v is True else v
    if mode not in PLAIN_MODES:
        raise ValueError(f"column {n}: plain must be true, {', '.join(PLAIN_MODES)} (got {v!r})")
    return mode


def _rule_maps(spec: dict, into: dict) -> dict:
    for n in spec.get("required") or []:
        into.setdefault(n, {})["required"] = True
    for n in spec.get("judgement") or []:
        into.setdefault(n, {})["judgement"] = True
    for rule in ("enum", "max", "type", "from_ref", "enum_from"):
        for n, v in (spec.get(rule) or {}).items():
            into.setdefault(n, {})[rule] = v
    plain = spec.get("plain")
    for n, v in (dict.fromkeys(plain, True) if isinstance(plain, list) else (plain or {})).items():
        into.setdefault(n, {})["plain"] = _plain_mode(n, v)
    for n, v in (spec.get("unknown_when_empty") or {}).items():
        into.setdefault(n, {})["unknown_when_empty"] = v
    return into


def _unknown_rule(col: str, v) -> tuple:
    """`unknown_when_empty: <block>` or `{block: <name>, action: reject|coerce}` -> (block, action)."""
    block, action = (v.get("block"), v.get("action", "reject")) if isinstance(v, dict) else (v, "reject")
    if not isinstance(block, str) or not block or action not in ("reject", "coerce"):
        raise ValueError(f"column {col}: unknown_when_empty must be a context block name or {{block, action: reject|coerce}}")
    return block, action


def _columns(spec: dict) -> tuple:
    """(stored columns, transient fields), each name -> rules; table-level required / judgement / enum /
    max / type / from_ref lists and maps are merged into whichever of the two names the field."""
    cols = spec.get("columns") or {}
    out = {n: {} for n in cols} if isinstance(cols, list) else {n: dict(r or {}) for n, r in cols.items()}
    tr = {n: dict(r or {}) for n, r in (spec.get("transient") or {}).items()}
    for n, r in _rule_maps(spec, {}).items():
        (tr if n in tr else out).setdefault(n, {}).update(r)
    for n, r in {**out, **tr}.items():            # column-level `plain:` / `unknown_when_empty:` are checked like the table-level maps
        if "plain" in r:
            r["plain"] = _plain_mode(n, r["plain"])
        if "unknown_when_empty" in r:
            _unknown_rule(n, r["unknown_when_empty"])
    for n, builtin in BUILTIN_RULES.items():
        if n in out:
            for k, v in builtin.items():
                if k not in out[n] and not ({"enum", "enum_from"} & set(out[n]) and k == "enum"):
                    out[n][k] = v
    return out, tr


def parse_output(output: dict) -> dict:
    """The `output:` block -> {table: TableRules}. Raises ValueError on a malformed spec."""
    from prompts import vocab

    def one(name: str, spec: dict, top: bool) -> TableRules:
        if name not in GRAPH:
            raise ValueError(f"output table '{name}' is not in backend/review.py GRAPH")
        cols, trans = _columns(spec)
        t = TableRules(name, card=bool(spec.get("card", top and not spec.get("loader_only") and not spec.get("update_only"))),
                       columns=cols, loader=dict(spec.get("loader") or {}), top=top, transient=trans,
                       loader_only=bool(spec.get("loader_only")), update_only=bool(spec.get("update_only")),
                       replace=spec.get("replace"), rows=spec.get("rows"))
        if spec.get("key") is not None:
            t.key = list(spec["key"])
        t.reason_pointer = bool(spec.get("reason_pointer"))
        if spec.get("count") is not None:
            c = dict(spec["count"])
            if not {"min", "max"} & set(c) or set(c) - {"min", "max", "where", "min_action"} or c.get("min_action", "reject") not in ("reject", "warn"):
                raise ValueError(f"{name}: count needs min and/or max (+ where, min_action: reject|warn)")
            t.count = c
        if spec.get("dedupe") is not None:
            d = dict(spec["dedupe"])
            if not d.get("column") or not d.get("against") or set(d) - {"column", "against", "threshold", "where"}:
                raise ValueError(f"{name}: dedupe needs column and against (+ threshold, where)")
            d["against"] = [d["against"]] if isinstance(d["against"], str) else list(d["against"])
            t.dedupe = d
        if t.replace not in (None, "all_rows"):
            raise ValueError(f"{name}: unknown replace '{t.replace}' (only all_rows)")
        for r, target in (spec.get("refs") or {}).items():
            if not str(r).startswith("ref_"):
                raise ValueError(f"{name}: refs key '{r}' must start with ref_")
            t.refs_decl[r] = str(target or "")
        for tn, cs in (spec.get("creates") or {}).items():
            t.creates[tn] = dict((cs or {}).get("loader") or {})
        for col, v in t.loader.items():
            vocab.check_token(name, col, v)
        for tn, ts in t.creates.items():
            for col, v in ts.items():
                vocab.check_token(f"{name}.creates.{tn}", col, v)
        for item in t.rows or []:
            for col, v in item.items():
                vocab.check_token(f"{name}.rows", col, v, literal_ok=True)
        for cname, cspec in (spec.get("children") or {}).items():
            cspec = cspec or {}
            c = one(cname, cspec, False)
            (t.loader_children if c.loader_only else t.children)[cname] = c
        return t

    parsed = {name: one(name, spec or {}, True) for name, spec in output.items()}
    # a top-level loader_only table is built under the output table that is its parent in review.GRAPH
    for name, t in list(parsed.items()):
        if t.loader_only:
            parent = next((p for _, p in GRAPH[name][2] if p in parsed and not parsed[p].loader_only), None)
            if parent:
                parsed[parent].loader_children[name] = t
                t.top = False
    return parsed


# =====================================================================================================
# envelope
# =====================================================================================================

def parse_envelope(text: str) -> dict:
    t = (text or "").strip()
    m = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```\s*$", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        env = json.loads(t)
    except ValueError:
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b <= a:
            raise NotJson("output is not JSON") from None
        try:
            env = json.loads(t[a:b + 1])
        except ValueError as e:
            raise NotJson(f"output is not valid JSON ({e})") from None
    if not isinstance(env, dict):
        raise NotJson("output JSON is not an object")
    return env


@dataclass
class Rec:
    rules: TableRules
    values: dict                                       # column -> value (stored columns)
    refs: dict                                         # target name -> (ref input name, name)
    sources: dict
    reasons: dict
    transient: dict = field(default_factory=dict)      # model field (not stored) -> value
    children: list = field(default_factory=list)       # [Rec]
    path: str = ""

    @property
    def table(self) -> str:
        return self.rules.name


@dataclass
class Validated:
    skip_reason: str | None
    recs: list
    rejected: list = field(default_factory=list)       # [str]
    warnings: list = field(default_factory=list)
    not_found: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)


def _date(v: Any) -> date:
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()):
        return date.fromisoformat(v.strip())
    raise ValueError(f"'{v}' is not a YYYY-MM-DD date")


def _number(v: Any) -> Decimal:
    if isinstance(v, bool):
        raise ValueError("a boolean is not a number")
    try:
        return Decimal(str(v).strip())
    except InvalidOperation:
        raise ValueError(f"'{v}' is not a plain number") from None


def _check_value(col: str, v: Any, rule: dict, enums: dict) -> Any:
    """Apply required / enum / enum_from / type / max of one field. Returns the (normalised) value."""
    if isinstance(v, str):
        v = v.strip() or None
    if v is None:
        if rule.get("required"):
            raise RowRejected(f"{col} is required")
        return None
    allowed = None
    if rule.get("enum") is not None:
        allowed = [str(x) for x in rule["enum"]]
    elif rule.get("enum_from"):
        src = rule["enum_from"]
        if src not in enums:
            raise RowRejected(f"{col}: allowed values '{src}' are not available")
        allowed = enums[src]
    if allowed is not None:
        hit = next((a for a in allowed if a.lower() == str(v).strip().lower()), None)
        if hit is None:
            raise RowRejected(f"{col}='{v}' is not one of {allowed}")
        v = hit
    t = rule.get("type")
    try:
        if t == "date":
            _date(v)
        elif t == "number":
            _number(v)
    except ValueError as e:
        raise RowRejected(f"{col}: {e}") from None
    if rule.get("max") and isinstance(v, str) and len(v) > int(rule["max"]):
        raise RowRejected(f"{col} is {len(v)} characters, max {rule['max']}")
    return v


def _sources(raw: Any, path: str, warn: list) -> dict:
    out = {}
    if raw and not isinstance(raw, dict):      # the model sent a list / string instead of {column: [entries]}
        warn.append(f"{path}._sources is not an object; ignored")
        return out
    for col, entries in (raw or {}).items():
        entries = [entries] if isinstance(entries, dict) else entries
        good = []
        for e in entries if isinstance(entries, list) else []:
            url = e.get("url") if isinstance(e, dict) else None
            q = e.get("quote") if isinstance(e, dict) else None
            if isinstance(url, str) and url.startswith(("http://", "https://")) and is_blocked(url):
                warn.append(f"{path}._sources.{col}: {'blog' if is_blog(url) else 'wiki'} source dropped: {url[:100]}")
                continue
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                if isinstance(q, str) and len(q) > 300:
                    warn.append(f"{path}.{col}: quote is {len(q)} characters (max 300)")
                good.append({"url": url.strip(), "quote": q if isinstance(q, str) else None})
            elif url in (None, "") and isinstance(q, str) and q.strip():
                good.append({"url": None, "quote": q.strip()})          # a stored input row, not a web page
            else:
                warn.append(f"{path}._sources.{col}: entry without an http(s) url or a quote ignored")
        if good:
            out[col] = good
    return out


NONE_ON_RECORD = "none on record"


def block_is_empty(text) -> bool:
    """A rendered context block with nothing in it: blank, or only 'none on record' (prompts/render.py)."""
    lines = [ln.strip().lower() for ln in str(text or "").splitlines() if ln.strip()]
    return not lines or all(ln == NONE_ON_RECORD for ln in lines)


def _modifier(col: str, v, rule: dict, enums: dict, warn: list, path: str):
    """`unknown_when_empty`: a modifier that rests on a context block (in_client_market on client_markets...) may only be
    'unknown' while that block is empty. Rejects the record (default) or sets 'unknown' with a warning (action: coerce)."""
    block, action = _unknown_rule(col, rule["unknown_when_empty"])
    empty = enums.get(f"empty.{block}")
    if empty is None:
        warn.append(f"{path}.{col}: context block '{block}' was not checked (validate called without enum_sources)")
        return v
    if not empty or v is None or str(v).lower() == "unknown":
        return v
    if action == "coerce":
        warn.append(f"{path}.{col}: '{v}' set to 'unknown' because the {block} block is empty")
        return "unknown"
    raise RowRejected(f"{col}='{v}' but the {block} context block is empty ('none on record'): the only allowed value is 'unknown'")


def _reason_points_to_fact(reason: str, col: str, values: dict, sources: dict) -> bool:
    """A.0.2 evidence pointer: the reason shares a number, name or word (4+ letters) with a sourced field's value or quote."""
    texts = []
    for c, entries in sources.items():
        if c == col:
            continue
        if c in values:
            texts.append(str(values[c]))
        texts += [str(e.get("quote") or "") for e in entries]
    facts = {w for t in texts for w in plain_english.content_words(t) if len(w) >= 4 or any(ch.isdigit() for ch in w)}
    return bool(facts & plain_english.content_words(reason))


def _filter_rows(kids: list, where: dict | None) -> list:
    return [k for k in kids if all(str(k.values.get(c, "")).lower() == str(v).lower() for c, v in (where or {}).items())]


def _child_rules(rec: "Rec", crules: TableRules, warn: list, path: str) -> None:
    """Table rules that look at all the rows of one child table under a card: `dedupe` (restating rows are dropped, with a
    warning), then `count` (too few rows reject the card, too many are trimmed)."""
    kids = [c for c in rec.children if c.table == crules.name]
    if crules.dedupe:
        d = crules.dedupe
        sel = _filter_rows(kids, d.get("where"))
        against = [str(rec.values.get(c) or "") for c in d["against"]]
        keep, notes = plain_english.drop_restatements([str(k.values.get(d["column"]) or "") for k in sel], against, float(d.get("threshold", 0.6)))
        dropped = [sel[i] for i in range(len(sel)) if i not in keep]
        rec.children = [c for c in rec.children if not any(c is x for x in dropped)]
        warn += [f"{path}.{crules.name}: {n}" for n in notes]
    if crules.count:
        n = crules.count
        sel = _filter_rows([c for c in rec.children if c.table == crules.name], n.get("where"))
        label = crules.name + (f" ({', '.join(f'{k}={v}' for k, v in n['where'].items())})" if n.get("where") else "")
        if n.get("min") is not None and len(sel) < int(n["min"]):
            if n.get("min_action", "reject") == "reject":
                raise RowRejected(f"{label}: {len(sel)} row(s), at least {n['min']} needed")
            warn.append(f"{path}.{label}: {len(sel)} row(s), at least {n['min']} wanted")
        if n.get("max") is not None and len(sel) > int(n["max"]):
            extra = sel[int(n["max"]):]
            rec.children = [c for c in rec.children if not any(c is x for x in extra)]
            warn.append(f"{path}.{label}: {len(sel)} rows, only the first {n['max']} kept")


def validate_rec(raw: dict, rules: TableRules, path: str, warn: list, rejected: list, enums: dict, state: dict | None = None) -> Rec:
    """One record (card: {table, values, children}; child: flat dict). Raises RowRejected.
    `state` is shared by a card and its children: {seen: acronyms already met, prose: the plain-English text so far}."""
    state = state if state is not None else {"seen": set(), "prose": []}
    if "values" in raw and isinstance(raw["values"], dict):
        values, kids = raw["values"], raw.get("children") or {}
    else:
        values, kids = raw, raw.get("children") or {}
    if not isinstance(values, dict):
        raise RowRejected("values is not an object")
    refs_in = rules.refs
    for k in values:
        if k in META_KEYS or k == "children":
            continue
        if k.startswith("_"):
            warn.append(f"{path}: unknown meta key {k} ignored")
        elif k in refs_in:
            continue
        elif k.startswith("ref_"):
            raise RowRejected(f"{k} is not a reference this table takes (have {sorted(refs_in)})")
        elif k not in rules.plain:
            raise RowRejected(f"column '{k}' is not allowed in {rules.name} (allowed: {sorted(rules.plain | set(refs_in))})")
    out, refs, trans = {}, {}, {}
    for col, rule in {**rules.columns, **rules.transient}.items():
        dest = trans if col in rules.transient else out
        if rule.get("from_ref"):
            r = rule["from_ref"]
            v = _check_value(r, values.get(r), {"required": rule.get("required")}, enums)
            if v is not None:
                refs[col] = (r, str(v))
        else:
            v = _check_value(col, values.get(col), rule, enums)
            if isinstance(v, str) and v.startswith(("http://", "https://")) and is_blocked(v):
                raise RowRejected(f"{col}: a {'blog' if is_blog(v) else 'wiki'} source is not allowed ({v[:80]})")
            if rule.get("unknown_when_empty"):
                v = _modifier(col, v, rule, enums, warn, path)
            if rule.get("plain") and isinstance(v, str):
                ws, why = plain_english.judge(v, rule["plain"], state["seen"], tuple(enums.get("client_names") or plain_english.CLIENT_NAMES))
                warn += [f"{path}.{col}: plain English: {w}" for w in ws]
                if why:
                    raise RowRejected(f"{col}: {why}")
                state["prose"].append(v)
            if v is not None:
                dest[col] = v
    for r in rules.refs_decl:
        if r in values and r not in {x for x in (rr.get("from_ref") for rr in rules.columns.values())}:
            v = _check_value(r, values.get(r), {}, enums)
            if v is not None:
                refs[r] = (r, str(v))
    reasons = {c: r.strip() for c, r in (values.get("_reason") or {}).items() if isinstance(r, str) and r.strip()}
    sources = _sources(values.get("_sources"), path, warn)
    for col, rule in {**rules.columns, **rules.transient}.items():
        key = rule.get("from_ref") or col
        if rule.get("judgement") and (col in out or col in refs or col in trans) and key not in reasons and col not in reasons:
            warn.append(f"{path}.{col}: judgement without _reason")
    facts = [c for c, r in rules.columns.items() if c in out and not r.get("judgement") and not c.endswith("_label")
             and r.get("enum") is None and not r.get("enum_from")]
    carries_source = any("quote" in c or c.endswith("_url") or c.endswith("_text") and "source" in c for c in out)
    if facts and not sources and not carries_source:
        warn.append(f"{path}: facts without _sources")
    tmap = lambda k: rules.refs.get(k, k)
    rec = Rec(rules, out, refs, {tmap(k): v for k, v in sources.items()}, {tmap(k): v for k, v in reasons.items()},
              trans, [], path)
    if rules.reason_pointer:
        for col, why in reasons.items():
            if col in out and not _reason_points_to_fact(why, col, out, sources):
                warn.append(f"{path}.{col}: the _reason names no value or quote of a sourced field")
    if not isinstance(kids, dict):
        raise RowRejected("children is not an object")
    for cname, items in kids.items():
        crules = rules.children.get(cname)
        if crules is None:
            rejected.append(f"{path}.children.{cname}: table not allowed here")
            continue
        for i, item in enumerate(items if isinstance(items, list) else []):
            try:
                rec.children.append(validate_rec(item, crules, f"{path}.{cname}[{i}]", warn, rejected, enums, state))
            except RowRejected as e:
                rejected.append(f"{path}.{cname}[{i}]: {e}")
    for crules in rules.children.values():
        if crules.dedupe or crules.count:
            _child_rules(rec, crules, warn, path)
    return rec


def validate(env: dict, prompt_id: str, output: dict, enums: dict | None = None) -> Validated:
    """Envelope -> Validated. Raises EnvelopeError when the envelope itself is unusable."""
    enums = enums or {}
    if env.get("prompt_id") != prompt_id:
        raise EnvelopeError(f"prompt_id is {env.get('prompt_id')!r}, expected {prompt_id!r}")
    skip = env.get("skip_reason")
    skip = skip.strip() if isinstance(skip, str) and skip.strip() else None
    recs_in = env.get("records")
    if recs_in is None and skip:
        recs_in = []
    if not isinstance(recs_in, list):
        raise EnvelopeError("records is not a list")
    v = Validated(skip, [], not_found=[str(x) for x in env.get("not_found") or []],
                  conflicts=env.get("conflicts") if isinstance(env.get("conflicts"), list) else [])
    if skip and recs_in:
        v.warnings.append("skip_reason given together with records: records used")
    for i, raw in enumerate(recs_in):
        path = f"records[{i}]"
        try:
            if not isinstance(raw, dict):
                raise RowRejected("record is not an object")
            rules = output.get(raw.get("table"))
            if rules is None or rules.loader_only:
                raise RowRejected(f"table '{raw.get('table')}' is not allowed (output: {sorted(t for t, r in output.items() if not r.loader_only)})")
            state = {"seen": set(), "prose": []}
            v.recs.append(validate_rec(raw, rules, f"{path}({rules.name})", v.warnings, v.rejected, enums, state))
            v.warnings += [f"{path}({rules.name}): plain English: {i}" for i in plain_english.reading_level(state["prose"])]
        except RowRejected as e:
            v.rejected.append(f"{path}: {e}")
    return v


def enum_sources(cur, output: dict, blocks: dict) -> dict:
    """Allowed values for every `enum_from` in the spec: context.<block> -> the code left of ' = ' in each
    rendered line; ui.<table>.<col> -> the distinct values of staging_ui.<table>.<col>."""
    found: set = set()
    needed: set = set()

    def walk(t: TableRules):
        for r in list(t.columns.values()) + list(t.transient.values()):
            if r.get("enum_from"):
                found.add(r["enum_from"])
            if r.get("unknown_when_empty"):
                needed.add(_unknown_rule("?", r["unknown_when_empty"])[0])
        for c in list(t.children.values()):
            walk(c)

    for t in output.values():
        walk(t)
    out = {}
    for b in needed:                              # unknown_when_empty: is the context block empty?
        if b not in blocks:
            raise ValueError(f"unknown_when_empty: context block '{b}' is not rendered for this prompt")
        out[f"empty.{b}"] = block_is_empty(blocks[b])
    for src in found:
        kind, _, rest = src.partition(".")
        if kind == "context":
            text = blocks.get(rest, "")
            out[src] = [ln.split(" = ", 1)[0].strip() for ln in text.splitlines() if " = " in ln]
        elif kind == "ui":
            table, _, col = rest.rpartition(".")
            if not re.fullmatch(r"\w+", table) or not re.fullmatch(r"\w+", col):
                raise ValueError(f"enum_from '{src}' is not ui.<table>.<column>")
            cur.execute(f"SELECT DISTINCT {col} AS v FROM staging_ui.{table} WHERE {col} IS NOT NULL ORDER BY 1")
            out[src] = [str(r["v"]) for r in cur.fetchall()]
        elif kind == "code_label":                        # code_label.<table>.<column>: the active codes of ui.code_label, in display order
            table, _, col = rest.rpartition(".")
            if not table or not col:
                raise ValueError(f"enum_from '{src}' is not code_label.<table>.<column>")
            cur.execute("SELECT code FROM staging_ui.code_label WHERE table_name = %s AND column_name = %s AND is_active ORDER BY display_order, code", (table, col))
            out[src] = [str(r["code"]) for r in cur.fetchall()]
            if not out[src]:
                raise ValueError(f"enum_from '{src}': ui.code_label has no rows for {table}.{col}")
        else:
            raise ValueError(f"enum_from '{src}': use context.<block>, ui.<table>.<column> or code_label.<table>.<column>")
    return out
