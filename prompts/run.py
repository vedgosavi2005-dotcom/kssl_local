"""Run prompts: python -m prompts.run <id> [--subject K] [--limit N] [--print-prompt] [--dry-run] [--rerun]
                    python -m prompts.run --due | --list          (see prompts/FORMAT.md)

One run = one subject: fill the prompt from kssl_staging, call the model, validate, load into
kssl_staging in one transaction, log to staging.prompt_run.  Env: KSSL_STAGING_DSN (or KSSL_DSN).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from prompts import loader, news_merge, render, spec as specmod
from prompts.claude_call import ModelError, ModelResult, call_model

DONE = ("loaded", "skipped", "rejected")          # a subject with one of these at this version is not pending
FAILED_COOLDOWN = timedelta(hours=12)             # a failed subject is not retried by a bulk run before this
CADENCE = {"daily": timedelta(days=1), "weekly": timedelta(days=7), "quarterly": timedelta(days=90)}
LABELS = ("headline", "title", "name", "display_name")
# a routine runs prompts in dependency order (what a later prompt reads must exist; signal reads the stories news writes); others follow alphabetically
ORDER = ["news", "signal", "moment", "partnership", "project", "geo", "matchup", "tender", "tender_assessment", "opportunity",
         "top_opportunity", "global_requirement", "innovation_discovery", "innovation_detail", "tech_article", "patent_classification"]
EVENT_KEYS = ("article_id", "source_id")           # one run per news article / notice: never re-run by cadence


@dataclass
class Outcome:
    status: str = "failed"
    skip_reason: str | None = None
    error: str | None = None
    rows: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None
    seconds: float = 0.0
    note: str = ""
    system: str = ""
    task: str = ""
    raw: str = ""
    unresolved: list = field(default_factory=list)
    loaded: list = field(default_factory=list)
    details: dict = field(default_factory=dict)
    model: str = ""


def connect():
    conn = render.connect()
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


# ---- run log ------------------------------------------------------------------------------------------------

def log_run(conn, spec: dict, subject_key: str | None, o: Outcome) -> None:
    j = psycopg2.extras.Json
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO staging.prompt_run
            (prompt_id, prompt_version, subject_key, model, web_search, seconds, tokens_in, tokens_out, cost_usd, status,
             skip_reason, error, unresolved, rows_loaded, loaded, details, prompt_text, raw_output)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (spec["id"], spec["version"], subject_key, o.model, spec["web_search"], o.seconds, o.tokens_in, o.tokens_out,
                     o.cost, o.status, o.skip_reason, o.error, j(o.unresolved), o.rows, j([{"table": t, "id": i, "card": c} for t, i, c in o.loaded]),
                     j(o.details), f"SYSTEM:\n{o.system}\n\nPROMPT:\n{o.task}" if o.task else None, o.raw or None))
    conn.commit()


def previous_cards(cur, prompt_id: str, subject_key: str, all_runs: bool = False) -> list:
    """Rows written by the last loaded run of this subject (or by every earlier loaded run): [{table, id, card}]."""
    cur.execute("""SELECT loaded FROM staging.prompt_run WHERE prompt_id = %s AND subject_key = %s AND status = 'loaded'
                   ORDER BY started_at DESC""" + ("" if all_runs else " LIMIT 1"), (prompt_id, subject_key))
    seen, out = set(), []
    for r in cur.fetchall():
        for c in r["loaded"] or []:
            if (c["table"], str(c["id"])) not in seen:
                seen.add((c["table"], str(c["id"])))
                out.append({"table": c["table"], "id": c["id"], "card": c.get("card", True)})
    return out


def replaces_history(cur, spec: dict, subject_key: str, rerun: bool) -> bool:
    """Recurring prompts keyed beyond the subject (moment, partnership, project) let their cards build up a
    history across scheduled runs. A forced --rerun or a new prompt version re-evaluates the subject instead:
    every earlier card of it is replaced, so fixing a prompt also clears what the old version got wrong."""
    if rerun:
        return True
    cur.execute("""SELECT prompt_version FROM staging.prompt_run WHERE prompt_id = %s AND subject_key = %s
                   AND status = 'loaded' ORDER BY started_at DESC LIMIT 1""", (spec["id"], subject_key))
    r = cur.fetchone()
    return bool(r) and str(r["prompt_version"]) != str(spec["version"])


def recurring(spec: dict) -> bool:
    """A subject keyed by an entity (competitor, category, pair, tender...) re-runs once its cadence period has
    passed; one keyed by an event (article, notice) never does. `recurring: true|false` in the file overrides."""
    if "recurring" in spec:
        return bool(spec["recurring"])
    return CADENCE.get(spec.get("cadence")) is not None and spec["subject"]["key"] not in EVENT_KEYS


def pending(cur, spec: dict, subs: list[dict]) -> list[dict]:
    cur.execute("""SELECT subject_key, status, started_at FROM staging.prompt_run
                   WHERE prompt_id = %s AND prompt_version = %s AND status IN ('loaded','skipped','rejected','failed')""",
                (spec["id"], spec["version"]))
    now = datetime.now(timezone.utc)
    period = CADENCE.get(spec.get("cadence")) if recurring(spec) else None
    last_done, last_failed = {}, {}
    for r in cur.fetchall():
        d = last_done if r["status"] in DONE else last_failed
        d[r["subject_key"]] = max(d.get(r["subject_key"], r["started_at"]), r["started_at"])
    out = []
    for s in subs:
        k = s["_key"]
        if k in last_done and (period is None or now - last_done[k] < period):
            continue
        if k in last_failed and now - last_failed[k] < FAILED_COOLDOWN:
            continue
        out.append(s)
    return out


def label(s: dict) -> str:
    text = next((str(s[k]) for k in LABELS if s.get(k)), "")
    return f"{s['_key'][:8]} {text[:60]}".strip()


# ---- one run ------------------------------------------------------------------------------------------------

def _norm(t: str) -> str:
    t = (t or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-").replace(" ", " ")
    return " ".join(t.casefold().split())


def quote_check(valid, task: str) -> list[str]:
    """Quotes the model gave that are not in the prompt text (the documents). A quote from a page the model
    read through web search cannot be checked here and is skipped; every other quote must appear verbatim."""
    text, bad = _norm(task), []

    def walk(rec):
        for col, entries in rec.sources.items():
            for e in entries:
                q = e["quote"]
                if not q or e["url"] is None:
                    continue
                if e["url"] not in task and e["url"].split("?")[0] not in task:
                    continue                                  # not one of the fetched documents
                parts = [p for p in re.split(r"\.\.\.|…", q) if len(p.strip()) > 12]
                if parts and not all(_norm(p) in text for p in parts):
                    bad.append(f"{rec.path}.{col}: quote not found in the document: {q[:90]!r}")
        for c in rec.children:
            walk(c)

    for r in valid.recs:
        walk(r)
    return bad


def run_one(conn, spec: dict, subject: dict, client: dict, blocks: dict, dry_run: bool, rerun: bool = False,
            reply: ModelResult | None = None, prompt: tuple[str, str] | None = None) -> Outcome:
    """`reply` (+ `prompt` = (system, task) as exported) replaces the prompt building and the model call:
    prompts/batch.py load validates and loads a reply that was produced elsewhere through this same code."""
    o = Outcome(model=spec["model"])
    t0 = time.monotonic()
    key = subject["_key"]
    if prompt is not None:
        o.system, o.task = prompt
    else:
        try:
            with conn.cursor() as cur:
                docs = render.documents(cur, spec, subject) if "documents" in spec["task"] else ("none on record", [])
                o.system, o.task, urls = render.build_prompt(cur, spec, subject, client, blocks, docs)
            o.details["fetched_urls"] = urls
            conn.rollback()
        except (render.PromptError, psycopg2.Error) as e:
            conn.rollback()
            o.error = f"{type(e).__name__}: {e}"
            o.seconds = round(time.monotonic() - t0, 1)
            return o
    handler = spec.get("handler")                       # a prompt with a handler is applied by its own module, not the loader
    output = enums = None
    if not handler:
        output = loader.parse_output(spec["output"])
        try:
            with conn.cursor() as cur:
                enums = specmod.enum_sources(cur, output, blocks)
            conn.rollback()
        except (ValueError, psycopg2.Error) as e:
            conn.rollback()
            o.error = f"enum_from: {e}"
            o.seconds = round(time.monotonic() - t0, 1)
            return o
    valid = env = None
    for attempt in ((2,) if reply is not None else (1, 2)):         # a reply that is not parseable JSON is asked for once more
        try:
            res = reply if reply is not None else call_model(o.system, o.task, spec["model"], spec["web_search"])
        except ModelError as e:
            o.error = f"model: {e}"
            o.seconds = round(time.monotonic() - t0, 1)
            return o
        o.raw = res.text
        o.tokens_in = (o.tokens_in or 0) + res.tokens_in
        o.tokens_out = (o.tokens_out or 0) + res.tokens_out
        o.cost = (o.cost or 0) + (res.cost_usd or 0)
        o.details["model_seconds"] = round(o.details.get("model_seconds", 0) + res.seconds, 1)
        try:
            env = loader.parse_envelope(res.text)
            valid = None if handler else loader.validate(env, spec["id"], output, enums)
            break
        except loader.NotJson as e:
            o.details["retry"] = f"attempt {attempt}: {e}"
            if attempt == 2:
                o.status, o.error = "rejected", str(e)
                o.seconds = round(time.monotonic() - t0, 1)
                return o
        except loader.EnvelopeError as e:
            o.status, o.error = "rejected", str(e)
            o.seconds = round(time.monotonic() - t0, 1)
            return o
    if handler:
        return _handled(conn, subject, env, o, dry_run, t0)
    valid.warnings += quote_check(valid, o.task)
    o.details.update(warnings=valid.warnings, rejected=valid.rejected, not_found=valid.not_found, conflicts=valid.conflicts)
    try:
        with conn.cursor() as cur:
            ld = loader.Loader(cur, spec["id"], key, output, subject, client)
            if replaces_history(cur, spec, key, rerun):
                ld.force_replace = True
                prev = previous_cards(cur, spec["id"], key, all_runs=True)
            else:
                prev = previous_cards(cur, spec["id"], key)
            if not valid.recs:
                if valid.skip_reason:
                    o.status, o.skip_reason = ("dry_run" if dry_run else "skipped"), valid.skip_reason
                    if not dry_run and ld.uses_previous():
                        ld.delete_previous(prev)           # the re-run says "nothing here": drop the earlier rows
                else:
                    o.status, o.error = "rejected", "no records and no skip_reason" + (f"; {valid.rejected[0]}" if valid.rejected else "")
            else:
                r = ld.load(valid, prev, spec.get("derive") or [])
                o.unresolved, o.rows = r.unresolved, r.rows
                o.loaded = [(t, i, c) for t, i, c in r.written]
                o.details.update(dropped=r.dropped, deleted_previous=r.deleted, created=r.created, load_warnings=r.warnings,
                                 derive_notes=r.notes)
                if r.labels:
                    o.details["labels"] = r.labels
                if r.cards or r.rows:
                    o.status = "dry_run" if dry_run else "loaded"
                    first = valid.recs[0]
                    o.note = " | ".join(str(x) for x in (first.values.get("title") or first.values.get("partner_name")
                                                         or first.values.get("project_title"), first.values.get("classification")
                                                         or first.values.get("grade")) if x)
                    if len(valid.recs) > 1:
                        o.note += f"  (+{len(valid.recs) - 1} more cards)"
                else:
                    o.status = "rejected"
                    o.error = "; ".join((valid.rejected + r.dropped)[:3]) or "no record could be loaded"
        if o.status in ("loaded", "skipped"):
            conn.commit()
        else:
            conn.rollback()                                    # dry_run, rejected
    except Exception as e:  # noqa: BLE001  (a failed load must roll back and still be logged)
        conn.rollback()
        o.status, o.error, o.rows, o.loaded = "failed", f"load: {type(e).__name__}: {str(e).splitlines()[0]}", 0, []
    o.seconds = round(time.monotonic() - t0, 1)
    return o


def _handled(conn, subject: dict, env: dict, o: Outcome, dry_run: bool, t0: float) -> Outcome:
    """Handler prompts (news -> prompts/news_merge.py): same outcome mapping as the loader path."""
    try:
        with conn.cursor() as cur:
            r = news_merge.apply(cur, subject, env, dry_run)
        o.rows, o.loaded, o.note = r.rows, [(t, i, c) for t, i, c in r.loaded], r.note
        o.details.update(warnings=r.warnings, **r.details)
        if r.rows:
            o.status = "dry_run" if dry_run else "loaded"
        elif r.skip_reason:
            o.status, o.skip_reason = ("dry_run" if dry_run else "skipped"), r.skip_reason
        else:
            o.status, o.error = "rejected", "; ".join(r.warnings[:3]) or "no story could be applied"
        if o.status in ("loaded", "skipped"):
            conn.commit()
        else:
            conn.rollback()
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        o.status, o.error, o.rows, o.loaded = "failed", f"load: {type(e).__name__}: {str(e).splitlines()[0]}", 0, []
    o.seconds = round(time.monotonic() - t0, 1)
    return o


def line(prompt_id: str, s: dict, o: Outcome) -> str:
    cost = f"${o.cost:.4f}" if o.cost is not None else "-"
    tok = f"{o.tokens_in}/{o.tokens_out}" if o.tokens_in is not None else "-"
    extra = o.note or o.skip_reason or o.error or ""
    unres = f" unresolved={[u['name'] for u in o.unresolved]}" if o.unresolved else ""
    return f"{prompt_id:10} {label(s)[:44]:44} {o.status:8} rows={o.rows} tokens={tok} {o.seconds}s {cost}  {extra[:140]}{unres}"


# ---- commands -------------------------------------------------------------------------------------------------

def select(conn, spec: dict, args) -> tuple[list[dict], str]:
    """(subjects to run, why none) for this invocation."""
    with conn.cursor() as cur:
        subs = render.subjects(cur, spec)
        if not subs:
            conn.rollback()
            return [], "no subjects yet (the subject query returns no rows)"
        if args.subject:
            subs = [s for s in subs if s["_key"] == str(args.subject)]
            if not subs:
                raise render.PromptError(f"{spec['id']}: no subject with key {args.subject}")
            if not args.rerun and not args.print_prompt and not pending(cur, spec, subs):
                conn.rollback()
                return [], f"subject {args.subject} already ran at version {spec['version']} (use --rerun)"
        elif not args.rerun and not args.print_prompt:
            subs = pending(cur, spec, subs)
    conn.rollback()
    why = "nothing pending: every subject has run at this version" if not subs else ""
    n = args.limit or (1 if args.print_prompt else None)
    return (subs[:n] if n else subs), why


def run_prompt(conn, spec: dict, args) -> int:
    subs, why = select(conn, spec, args)
    if not subs:
        print(f"{spec['id']}: {why}")
        return 0
    with conn.cursor() as cur:
        client = render.client_row(cur)
        blocks = render.context_blocks(cur, client)
    conn.rollback()
    bad = 0
    for s in subs:
        if args.print_prompt:
            with conn.cursor() as cur:
                system, task, urls = render.build_prompt(cur, spec, s, client, blocks)
            conn.rollback()
            print(f"===== {spec['id']} / {label(s)} / model {spec['model']} / web_search {spec['web_search']} / fetched {urls}")
            print("----- SYSTEM\n" + system + "\n----- PROMPT\n" + task + "\n=====")
            continue
        o = run_one(conn, spec, s, client, blocks, args.dry_run, args.rerun)
        log_run(conn, spec, s["_key"], o)
        print(line(spec["id"], s, o), flush=True)
        bad += o.status == "failed"
    return 1 if bad else 0


def last_runs(cur, prompt_id: str):
    cur.execute("SELECT started_at, status FROM staging.prompt_run WHERE prompt_id = %s AND status <> 'dry_run' "
                "ORDER BY started_at DESC LIMIT 1", (prompt_id,))
    return cur.fetchone()


def due(spec: dict, last) -> bool:
    """Is the prompt's cadence period over? (Entity-keyed prompts are gated per subject instead, in pending().)"""
    period = CADENCE.get(spec.get("cadence"))
    if period is None:
        return False                                   # on_demand (or unknown): never by routine
    return recurring(spec) or last is None or datetime.now(timezone.utc) - last["started_at"] >= period


def ordered_ids() -> list[str]:
    ids = render.prompt_ids()
    return [i for i in ORDER if i in ids] + [i for i in ids if i not in ORDER]


def cmd_list(conn) -> None:
    print(f"{'prompt':10} {'ver':4} {'cadence':10} {'model':18} {'last run':20} {'pending':8} title")
    for pid in ordered_ids():
        spec = render.load_prompt(pid)
        with conn.cursor() as cur:
            last = last_runs(cur, pid)
            try:
                n = len(pending(cur, spec, render.subjects(cur, spec)))
            except psycopg2.Error as e:
                conn.rollback()
                n = f"error: {str(e).splitlines()[0][:40]}"
        conn.rollback()
        when = f"{last['started_at']:%Y-%m-%d %H:%M} {last['status']}" if last else "never"
        print(f"{pid:10} {spec['version']:4} {str(spec.get('cadence')):10} {spec['model']:18} {when:20} {str(n):8} {spec.get('title', '')}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prompts.run", description=__doc__.split("\n")[0])
    ap.add_argument("prompt", nargs="?", help="prompt id (prompts/<id>.yml)")
    ap.add_argument("--subject", help="run one subject (its key)")
    ap.add_argument("--limit", type=int, help="at most N subjects (newest first, as the prompt's query orders them)")
    ap.add_argument("--print-prompt", action="store_true", help="print the filled prompt, no model call")
    ap.add_argument("--dry-run", action="store_true", help="call the model and validate; roll back instead of loading")
    ap.add_argument("--rerun", action="store_true", help="run subjects that already ran at this prompt version")
    ap.add_argument("--due", action="store_true", help="routine: every prompt whose cadence has elapsed")
    ap.add_argument("--list", action="store_true", help="prompts, cadence, last run, pending subjects")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not (args.prompt or args.due or args.list):
        ap.error("give a prompt id, --due or --list")
    try:
        conn = connect()
    except (render.PromptError, psycopg2.Error) as e:
        print(f"cannot connect: {e}", file=sys.stderr)
        return 2
    code = 0
    try:
        if args.list:
            cmd_list(conn)
        elif args.due:
            for pid in ordered_ids():
                spec = render.load_prompt(pid)
                with conn.cursor() as cur:
                    last = last_runs(cur, pid)
                conn.rollback()
                if due(spec, last):
                    code |= run_prompt(conn, spec, args)
                else:
                    print(f"{pid}: not due ({spec.get('cadence')}, last {last['started_at']:%Y-%m-%d %H:%M}" if last else f"{pid}: not due ({spec.get('cadence')})")
        else:
            code = run_prompt(conn, render.load_prompt(args.prompt), args)
    except render.PromptError as e:
        print(f"error: {e}", file=sys.stderr)
        code = 2
    finally:
        conn.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
