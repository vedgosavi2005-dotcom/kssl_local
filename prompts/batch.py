"""File-based prompt workflow (routines/): export the pending prompts of a set to files, run them through Claude
(or paste them into claude.ai by hand), load the replies into kssl_staging.  Never touches kssl_serving.

    python -m prompts.batch check  --set set1                          [--db vps|local]
    python -m prompts.batch export --set set1 [--prompt ID] [--limit N] [--rerun] --out DIR
    python -m prompts.batch run    DIR [--prompt ID]                   (claude CLI; skips files that already have a .json)
    python -m prompts.batch load   DIR [--dry-run] [--prompt ID]       (validate + load; files move to DIR/loaded or DIR/rejected)
    python -m prompts.batch auto   --set set1 [--prompt ID] [--limit N] --out DIR     (export -> run -> load, prompt by prompt)
    python -m prompts.batch news   [--db vps] --competitor all --products --from 2026-10-01 --to 2026-10-15   (the news job, see set1 README)
    python -m prompts.batch sql    FILE                                (apply a .sql file, e.g. db/setup/07_page_setup.sql)

--db vps (default) reads KSSL_VPS_STAGING_DSN from .env (or the environment) and needs the SSH tunnel: routines/tunnel.sh.
--db local uses KSSL_STAGING_DSN (environment, then .env) or the local docker default.
export/run/load reuse prompts/run.py (select, pending, run_one, log_run): same checks, same loader, same log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extensions
import yaml

from prompts import render, run
from prompts.claude_call import ModelError, ModelResult, call_model
from prompts.spec import EnvelopeError, parse_envelope

ROOT = Path(__file__).resolve().parent.parent
LOCAL_DEFAULT = "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl"
TUNNEL_PORT = 55460


# ---- database target ------------------------------------------------------------------------------------------

def read_env(path: Path = ROOT / ".env") -> dict[str, str]:
    """KEY=value lines of a .env file (quotes stripped, # comments and blank lines skipped). No expansion."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k, v = k.strip().removeprefix("export ").strip(), v.strip()
        if v[:1] in ("'", '"') and v.endswith(v[:1]) and len(v) >= 2:
            v = v[1:-1]
        elif " #" in v:
            v = v.split(" #", 1)[0].rstrip()
        out[k] = v
    return out


def resolve_dsn(db: str) -> str:
    env = read_env()
    if db == "vps":                       # a plain KSSL_STAGING_DSN is NOT used here: a stale local value must never hit the VPS
        dsn = os.environ.get("KSSL_VPS_STAGING_DSN") or env.get("KSSL_VPS_STAGING_DSN")
        if not dsn:
            raise render.PromptError("KSSL_VPS_STAGING_DSN is not set (kssl_local/.env, see routines/SETUP.md)")
    else:
        dsn = os.environ.get("KSSL_STAGING_DSN") or env.get("KSSL_STAGING_DSN") or LOCAL_DEFAULT
    return dsn.strip()


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host or "127.0.0.1", port), timeout=3):
            return True
    except OSError:
        return False


def connect_db(db: str):
    """Connection to the chosen kssl_staging (RealDictCursor, like the runner). Prints the target, never the password."""
    dsn = resolve_dsn(db)
    p = psycopg2.extensions.parse_dsn(dsn)
    host, port = p.get("host", "127.0.0.1"), int(p.get("port", 5432))
    if db == "vps" and not port_open(host, port):
        raise render.PromptError(f"cannot reach {host}:{port} - open the tunnel first: routines/tunnel.sh")
    os.environ["KSSL_STAGING_DSN"] = dsn          # render.connect() reads it
    os.environ.pop("KSSL_DSN", None)
    print(f"database: {db}  {host}:{port}/{p.get('dbname')}", flush=True)
    return run.connect()


# ---- files ---------------------------------------------------------------------------------------------------

def set_prompts(set_name: str) -> list[str]:
    sets = yaml.safe_load((Path(__file__).parent / "sets.yml").read_text(encoding="utf-8"))
    if set_name not in sets:
        raise render.PromptError(f"unknown set {set_name!r}; have: {', '.join(sets)}")
    return list(sets[set_name]["prompts"])


def file_stem(prompt_id: str, key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key).strip("_")
    if safe != key or len(safe) > 60:
        safe = safe[:50] + "-" + hashlib.sha1(key.encode()).hexdigest()[:6]
    return f"{prompt_id}__{safe}"


SYS_MARK = re.compile(r"^## SYSTEM\n", re.M)
TASK_MARK = re.compile(r"^## PROMPT\n", re.M)


def write_prompt_file(path: Path, spec: dict, key: str, system: str, task: str) -> None:
    head = (f"<!-- prompt: {spec['id']} | version: {spec['version']} | model: {spec['model']} | "
            f"web_search: {'yes' if spec['web_search'] else 'no'} | subject: {key} -->\n"
            f"<!-- Manual run: paste everything from the line '## SYSTEM' to the end into claude.ai"
            f"{' (turn web search ON)' if spec['web_search'] else ''}; save the reply as {path.stem[:-7]}.json -->\n")
    path.write_text(f"{head}## SYSTEM\n{system}\n\n## PROMPT\n{task}\n", encoding="utf-8")


def read_prompt_file(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    a = SYS_MARK.search(text)
    b = TASK_MARK.search(text, a.end()) if a else None
    if not (a and b):
        raise ValueError(f"{path.name}: no '## SYSTEM' / '## PROMPT' sections")
    return text[a.end():b.start()].strip(), text[b.end():].strip()


def meta_path(prompt_file: Path) -> Path:
    return prompt_file.with_name(prompt_file.name.removesuffix(".prompt.md") + ".meta.json")


def read_meta(prompt_file: Path) -> dict:
    return json.loads(meta_path(prompt_file).read_text(encoding="utf-8"))


def write_meta(prompt_file: Path, meta: dict) -> None:
    meta_path(prompt_file).write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def prompt_files(d: Path, only: str | None) -> list[Path]:
    return [f for f in sorted(d.glob("*.prompt.md")) if not only or f.name.startswith(only + "__")]


# ---- commands ------------------------------------------------------------------------------------------------

def cmd_check(conn, args) -> int:
    print(f"{'prompt':20} {'ver':4} {'model':8} {'web':4} pending")
    for pid in args.ids:
        spec = render.load_prompt(pid)
        with conn.cursor() as cur:
            subs = render.subjects(cur, spec)
            n = len(run.pending(cur, spec, subs)) if subs else 0
        conn.rollback()
        print(f"{pid:20} {spec['version']:4} {spec['model']:8} {'yes' if spec['web_search'] else 'no':4} {n}")
    return 0


def cmd_export(conn, args) -> int:
    out = Path(args.out)
    sel = argparse.Namespace(subject=None, rerun=args.rerun, print_prompt=False, limit=None)
    with conn.cursor() as cur:
        client = render.client_row(cur)
        blocks = render.context_blocks(cur, client)
    conn.rollback()
    total = 0
    for pid in args.ids:
        spec = render.load_prompt(pid)
        subs, why = run.select(conn, spec, sel)
        if not subs:
            print(f"{pid}: {why}")
            continue
        if args.limit == 0:
            print(f"{pid}: {len(subs)} pending")
            continue
        out.mkdir(parents=True, exist_ok=True)
        done = 0
        for s in subs:
            if args.limit and done >= args.limit:              # --limit counts exported files; an unreadable subject does not use it up
                break
            key = s["_key"]
            stem = file_stem(pid, key)
            pf = out / f"{stem}.prompt.md"
            if (out / f"{stem}.json").exists():
                print(f"{pid:10} {run.label(s)[:44]:44} skipped: {stem}.json is already there (load it first)")
                continue
            try:
                with conn.cursor() as cur:
                    docs = render.documents(cur, spec, s) if "documents" in spec["task"] else ("none on record", [])
                    system, task, urls = render.build_prompt(cur, spec, s, client, blocks, docs)
                conn.rollback()
            except Exception as e:  # noqa: BLE001  (one unreadable subject must not stop the export)
                conn.rollback()
                print(f"{pid:10} {run.label(s)[:44]:44} NOT exported: {type(e).__name__}: {str(e)[:150]}")
                continue
            write_prompt_file(pf, spec, key, system.strip(), task.strip())
            if read_prompt_file(pf) != (system.strip(), task.strip()):
                pf.unlink()
                print(f"{pid:10} {run.label(s)[:44]:44} NOT exported: the text contains a '## PROMPT' line")
                continue
            write_meta(pf, {"prompt_id": pid, "version": spec["version"], "subject_key": key,
                            "subject": {k: v for k, v in s.items() if not k.startswith("_")}, "model": spec["model"],
                            "web_search": bool(spec["web_search"]), "rerun": bool(args.rerun), "exported_at": now_iso(),
                            "fetched_urls": urls})
            total += 1
            done += 1
            print(f"{pid:10} {run.label(s)[:44]:44} -> {pf.name}")
    print(f"exported {total} prompt file(s) to {out}")
    return 0


def cmd_run(args) -> int:
    d, ok, bad = Path(args.dir), 0, 0
    files = prompt_files(d, args.prompt)
    if not files:
        print(f"no .prompt.md files in {d}")
    for pf in files:
        stem = pf.name.removesuffix(".prompt.md")
        if (d / f"{stem}.json").exists():
            continue
        if (d / f"{stem}.json.raw").exists():
            print(f"{stem}: has a .json.raw from an earlier try - fix it by hand or delete it to run again")
            continue
        meta = read_meta(pf)
        system, task = read_prompt_file(pf)
        try:
            res = call_model(system, task, meta["model"], bool(meta["web_search"]))
        except ModelError as e:
            bad += 1
            print(f"{stem}: model error: {e}", flush=True)
            continue
        meta["usage"] = {"tokens_in": res.tokens_in, "tokens_out": res.tokens_out, "cost_usd": res.cost_usd,
                         "seconds": res.seconds}
        meta["ran_at"] = now_iso()
        write_meta(pf, meta)
        try:
            env = parse_envelope(res.text)
            (d / f"{stem}.json").write_text(json.dumps(env, indent=2, ensure_ascii=False), encoding="utf-8")
            state, ok = "ok", ok + 1
        except EnvelopeError as e:
            (d / f"{stem}.json.raw").write_text(res.text, encoding="utf-8")
            state, bad = f"NOT JSON ({e}) - saved as .json.raw", bad + 1
        cost = f"${res.cost_usd:.4f}" if res.cost_usd is not None else "-"
        print(f"{stem}: {state}  tokens={res.tokens_in}/{res.tokens_out} {res.seconds}s {cost}", flush=True)
    print(f"done: {ok} reply file(s) written, {bad} problem(s)")
    return 1 if bad else 0


def move(d: Path, stem: str, to: str, err: str | None = None) -> None:
    dest = d / to
    dest.mkdir(exist_ok=True)
    for suffix in (".prompt.md", ".meta.json", ".json"):
        f = d / f"{stem}{suffix}"
        if f.exists():
            shutil.move(str(f), str(dest / f.name))
    if err:
        (dest / f"{stem}.err.txt").write_text(err + "\n", encoding="utf-8")


def cmd_load(conn, args) -> int:
    d = Path(args.dir)
    files = [f for f in sorted(d.glob("*.json")) if not f.name.endswith(".meta.json")
             and (not args.prompt or f.name.startswith(args.prompt + "__"))]
    if not files:
        print(f"no reply .json files in {d}")
        return 0
    with conn.cursor() as cur:
        client = render.client_row(cur)
        blocks = render.context_blocks(cur, client)
    conn.rollback()
    counts: dict[str, int] = {}
    for jf in files:
        stem = jf.stem
        pf = d / f"{stem}.prompt.md"
        try:
            if not pf.exists() or not meta_path(pf).exists():
                raise ValueError(f"{stem}.prompt.md / {stem}.meta.json missing next to the reply")
            meta = read_meta(pf)
            system, task = read_prompt_file(pf)
            spec = render.load_prompt(meta["prompt_id"])
            if str(meta["version"]) != str(spec["version"]):
                raise ValueError(f"exported at prompt version {meta['version']}, the prompt is now {spec['version']}: export again")
            with conn.cursor() as cur:
                subject = next((s for s in render.subjects(cur, spec) if s["_key"] == str(meta["subject_key"])), None)
            conn.rollback()
            if subject is None:
                raise ValueError(f"subject {meta['subject_key']} is no longer returned by the prompt's subject query")
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            print(f"{stem:50} rejected: {e}")
            counts["rejected"] = counts.get("rejected", 0) + 1
            if not args.dry_run:
                move(d, stem, "rejected", str(e))
            continue
        u = meta.get("usage") or {}
        reply = ModelResult(text=jf.read_text(encoding="utf-8-sig"), tokens_in=u.get("tokens_in") or 0,
                            tokens_out=u.get("tokens_out") or 0, cost_usd=u.get("cost_usd"), seconds=u.get("seconds") or 0.0)
        o = run.run_one(conn, spec, subject, client, blocks, args.dry_run, bool(meta.get("rerun")), reply, (system, task))
        o.model = meta.get("model") or o.model
        o.seconds = round(o.seconds + (u.get("seconds") or 0), 1)      # model time (from the run step) + load time
        o.details.update(source=f"batch file {jf.name}", fetched_urls=meta.get("fetched_urls") or [])
        if u.get("tokens_in") is None:
            o.tokens_in = o.tokens_out = o.cost = None        # a hand-pasted reply: no usage to report
        print(run.line(spec["id"], subject, o), flush=True)
        counts[o.status] = counts.get(o.status, 0) + 1
        if args.dry_run:
            continue
        run.log_run(conn, spec, subject["_key"], o)
        if o.status in ("loaded", "skipped"):
            move(d, stem, "loaded")
        else:
            move(d, stem, "rejected", f"{o.status}: {o.error or o.skip_reason}")
    print("result: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) + (" (dry run: nothing written)" if args.dry_run else ""))
    return 1 if counts.get("failed") else 0


def cmd_auto(args) -> int:
    """The whole set, prompt by prompt in the set's order: export -> run (claude CLI) -> load. A later prompt reads what an
    earlier one loaded, so the next export only starts after the previous load. One connection per prompt (runs are long)."""
    code = 0
    for pid in args.ids:
        print(f"\n===== {pid}", flush=True)
        a = argparse.Namespace(**{**vars(args), "ids": [pid], "prompt": pid, "dry_run": False, "dir": args.out})
        for step in ("export", "run", "load"):
            if step == "run":
                code |= cmd_run(a)
                continue
            conn = connect_db(args.db)
            try:
                code |= (cmd_export if step == "export" else cmd_load)(conn, a)
            finally:
                conn.close()
    return code


def cmd_news(args) -> int:
    """The news job (python -m backend.news ...) pointed at the chosen database: batch news [--db vps] --competitor all ..."""
    dsn = resolve_dsn(args.db)
    p = psycopg2.extensions.parse_dsn(dsn)
    if args.db == "vps" and not port_open(p.get("host", "127.0.0.1"), int(p.get("port", 5432))):
        raise render.PromptError("cannot reach the VPS database - open the tunnel first: routines/tunnel.sh")
    os.environ["KSSL_STAGING_DSN"] = dsn
    print(f"database: {args.db}  {p.get('host')}:{p.get('port')}/{p.get('dbname')}", flush=True)
    from backend import news
    return news.main(args.rest) or 0


def cmd_sql(conn, args) -> int:
    sql = Path(args.file).read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"applied {args.file}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prompts.batch", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("--db", choices=("vps", "local"), default="vps", help="kssl_staging to use (default vps = through the tunnel)")
        return p

    p = add("check", help="connect and list the pending subjects per prompt of a set")
    p.add_argument("--set", required=True, dest="set_name")
    p = add("export", help="write the pending prompts of a set as ready-to-run files")
    p.add_argument("--set", required=True, dest="set_name")
    p.add_argument("--prompt", help="only this prompt id")
    p.add_argument("--limit", type=int, help="at most N subjects per prompt (0 = only count)")
    p.add_argument("--rerun", action="store_true", help="also subjects that already ran at this prompt version")
    p.add_argument("--out", required=True)
    p = add("auto", help="export -> run -> load for every prompt of a set, in order")
    p.add_argument("--set", required=True, dest="set_name")
    p.add_argument("--prompt", help="only this prompt id")
    p.add_argument("--limit", type=int, help="at most N subjects per prompt")
    p.add_argument("--rerun", action="store_true")
    p.add_argument("--out", required=True)
    p = add("news", help="run the news job (backend.news) against the chosen database; everything after 'news' is its arguments")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p = add("run", help="run every .prompt.md without a reply through the claude CLI")
    p.add_argument("dir")
    p.add_argument("--prompt")
    p = add("load", help="validate and load the reply .json files into kssl_staging")
    p.add_argument("dir")
    p.add_argument("--prompt")
    p.add_argument("--dry-run", action="store_true", help="validate only: roll back, no log, files stay")
    p = add("sql", help="apply a .sql file to kssl_staging")
    p.add_argument("file")
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["news"]:                          # argparse cannot pass '--x' options through a sub-command: split by hand
        rest, db = argv[1:], "vps"
        if "--db" in rest and rest.index("--db") + 1 < len(rest):
            i = rest.index("--db")
            db = rest[i + 1]
            del rest[i:i + 2]
        argv = ["news", "--db", db] + (["--"] if rest else []) + rest
    args = ap.parse_args(argv)
    if args.cmd == "news" and args.rest[:1] == ["--"]:
        args.rest = args.rest[1:]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.cmd == "run":                         # the model call needs no database
            return cmd_run(args)
        if args.cmd == "news":
            return cmd_news(args)
        if args.cmd in ("check", "export", "auto"):
            args.ids = [args.prompt] if getattr(args, "prompt", None) else set_prompts(args.set_name)
            if getattr(args, "prompt", None) and args.prompt not in set_prompts(args.set_name):
                raise render.PromptError(f"{args.prompt} is not in {args.set_name}: {', '.join(set_prompts(args.set_name))}")
        if args.cmd == "auto":
            return cmd_auto(args)
        conn = connect_db(args.db)
        try:
            return {"check": cmd_check, "export": cmd_export, "load": cmd_load, "sql": cmd_sql}[args.cmd](conn, args)
        finally:
            conn.close()
    except (render.PromptError, psycopg2.Error) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
