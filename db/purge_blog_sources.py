"""Remove every source on the blocked blog domains (backend.sources.BLOCKED["blog"]: ajaishukla.com, idrw.org) from the LOCAL kssl_staging.

    python -m db.purge_blog_sources                          dry run (default): prints the plan per table, writes nothing
    python -m db.purge_blog_sources --apply                  runs it, one transaction per table (the matchup recompute last)
    python -m db.purge_blog_sources --drop-text-attributed   also treat a competitor spec whose VALUE TEXT names a blog "(idrw)" as unsupported

Local docker only (127.0.0.1 / localhost, database kssl_staging); never serving, never the VPS.  Idempotent: the plan is recomputed from the
current data, a clean database gives an empty plan.  Rules (same as the client-portfolio clean-up):

  per (table, row, column) that has blog staging.fact_source rows
    - another source exists (source_tier not 'judgement', url not blog)  -> delete only the blog fact_source rows;
    - else the value rests only on a blog:
        detail row (GRAPH reviewed = False: spec, evidence, timeline, advantage, matchup specification, leader record...)
                                       -> delete the row, its descendants and ALL their fact_source rows (judgement ones included);
        parent row (reviewed card)     -> the whole row rests on blogs (no supported column at all): delete it with its descendants;
                                          else set the column NULL if nullable (and drop that column's fact_source rows), report if NOT NULL;
  competitive_product: no non-blog product-level source at all -> product + specs + descendants deleted (refused while a matchup points at it);
  surviving competitive_product_specification / competitive_leader_record rows whose source_url is a blog: repoint to the row's first non-blog
    source (spec: else the product's first non-blog source); none -> row deleted.  competitive_product_specification.source_count = number of its
    remaining non-judgement spec_value fact_source rows.
  deleted competitor spec -> the matchup specification of the same label in the matchups of that product is deleted; affected matchups get
    comparable_spec_count / sourced_spec_count / edge_score / decision_level recomputed with prompts/derive.py (better_side / gap are not touched).
  *_source tables: rows with a blog source_url are deleted (competitive_matchup_advantage.source_id pointing at one is set NULL).
Not touched: staging.prompt_run (the run log), staging.source_document, staging.tender_raw, text that merely mentions a blog (reported).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import psycopg2
import psycopg2.extras
from psycopg2 import sql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.review import GRAPH                      # noqa: E402
from backend.sources import BLOCKED, PURGED, is_blog         # noqa: E402
from prompts import derive                            # noqa: E402

LOCAL_DSN = "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl"
LOOSE = "(" + "|".join(re.escape(d) for k in PURGED for d in BLOCKED[k]) + ")"
SKIP_SCAN = {"prompt_run", "source_document", "tender_raw"}
LABELS = ("spec_label", "spec_name", "headline", "advantage_text", "event_title", "title", "product_name", "project_title",
          "verdict_headline", "source_label", "competitor_product_name")
TEXT_ATTR = re.compile(r"\((?:[^)]*\b)?(idrw|ajaishukla)\b", re.I)


class Plan:
    def __init__(self):
        self.fs = defaultdict(set)              # table -> fact_source ids to delete (fs.table_name)
        self.rows = defaultdict(dict)           # table -> {pk: reason}  rows to delete
        self.nulls = defaultdict(dict)          # table -> {(pk, col): reason}
        self.repoint = defaultdict(dict)        # table -> {pk: (new_url, how)}
        self.counts = {}                        # competitive_product_specification pk -> new source_count
        self.src_rows = defaultdict(dict)       # *_source table -> {pk: url}
        self.recompute = set()                  # matchup ids
        self.report = []                        # manual follow-ups / refusals

    def tables(self):
        return {t for d in (self.fs, self.rows, self.nulls, self.repoint, self.src_rows) for t, v in d.items() if v}

    def empty(self):
        return not (self.tables() or self.recompute)


def connect(dsn):
    p = psycopg2.extensions.parse_dsn(dsn)
    if p.get("host") not in ("127.0.0.1", "localhost") or p.get("dbname") != "kssl_staging":
        raise SystemExit("refusing: this script only runs against the LOCAL kssl_staging (127.0.0.1 / localhost)")
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=5)


def q(cur, text, args=()):
    cur.execute(text, args)
    return cur.fetchall()


def ident(t):
    return sql.Identifier("staging", t)


def pk_of(t):
    return GRAPH[t][0]


def label(cur, t, k):
    if t not in GRAPH:
        return ""
    have = {r["column_name"] for r in q(cur, "SELECT column_name FROM information_schema.columns WHERE table_schema='staging' AND table_name=%s", (t,))}
    for c in LABELS:
        if c in have:
            r = q(cur, sql.SQL("SELECT {} AS v FROM {} WHERE {}::text = %s").format(sql.Identifier(c), ident(t), sql.Identifier(pk_of(t))), (k,))
            if r:
                return f"{c}={str(r[0]['v'])[:70]!r}"
    return ""


def is_ok(f):
    """a supporting source: not a judgement row, not a blog (a stored quote without a url counts)"""
    return f["source_tier"] != "judgement" and not (f["source_url"] and is_blog(f["source_url"]))


def descendants(cur, table, pks, skip=()):
    """{table: {pk}} of the rows under `table`/pks by backend.review.GRAPH (reviewed descendants included), the start rows included."""
    out = {table: set(pks)}
    todo = [(table, set(pks))]
    while todo:
        t, ks = todo.pop()
        for child, (cpk, _rev, parents) in GRAPH.items():
            if child in skip:
                continue
            for fk, p in parents:
                if p != t:
                    continue
                rows = q(cur, sql.SQL("SELECT {}::text AS k FROM {} WHERE {}::text = ANY(%s)").format(
                    sql.Identifier(cpk), ident(child), sql.Identifier(fk)), (list(ks),))
                new = {r["k"] for r in rows} - out.get(child, set())
                if new:
                    out.setdefault(child, set()).update(new)
                    todo.append((child, new))
    return out


def build_plan(cur, drop_text_attributed=False) -> Plan:
    P = Plan()
    meta = {}                                               # table -> {col: nullable}

    def nullable(t, c):
        if t not in meta:
            meta[t] = {r["column_name"]: r["is_nullable"] == "YES" for r in
                       q(cur, "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_schema='staging' AND table_name=%s", (t,))}
        return meta[t].get(c)

    fsrows = q(cur, """SELECT f.* FROM staging.fact_source f JOIN
                         (SELECT DISTINCT table_name, row_id FROM staging.fact_source WHERE source_url ~* %s) k USING (table_name, row_id)
                       ORDER BY f.created_at, f.fact_source_id""", (LOOSE,))
    by_row = defaultdict(lambda: defaultdict(list))         # (table, row) -> col -> [fs]
    for f in fsrows:
        by_row[(f["table_name"], f["row_id"])][f["column_name"]].append(f)
    blog_rows = {k: cols for k, cols in by_row.items() if any(f["source_url"] and is_blog(f["source_url"]) for fl in cols.values() for f in fl)}
    near = sum(1 for fl in by_row.values() for l in fl.values() for f in l if f["source_url"] and re.search(LOOSE, f["source_url"], re.I) and not is_blog(f["source_url"]))
    if near:
        P.report.append(f"{near} fact_source rows mention a blog name in the url but are not on a blocked host (kept)")

    def fs_all(t, k, col=None):
        return [f["fact_source_id"] for c, fl in by_row.get((t, k), {}).items() if col in (None, c) for f in fl]

    def fs_of_row(t, k):                                    # also fact_source of rows with no blog group
        got = q(cur, "SELECT fact_source_id FROM staging.fact_source WHERE table_name=%s AND row_id=%s", (t, k))
        return [r["fact_source_id"] for r in got]

    def exists(t, k):
        return bool(q(cur, sql.SQL("SELECT 1 FROM {} WHERE {}::text = %s").format(ident(t), sql.Identifier(pk_of(t))), (k,)))

    def kill(t, ks, why, skip=()):
        """delete rows t/ks and everything under them, with all their fact_source rows"""
        tree = descendants(cur, t, set(ks), skip)
        for tt, kk in tree.items():
            for k in kk:
                P.rows[tt].setdefault(k, why if tt == t else f"under {t} {', '.join(sorted(ks))[:40]}")
                P.fs[tt].update(fs_of_row(tt, k))
        return tree

    # ---- 1. fact_source groups ------------------------------------------------------------------------------
    for (t, k), cols in sorted(blog_rows.items()):
        blogfs = [f["fact_source_id"] for fl in cols.values() for f in fl if f["source_url"] and is_blog(f["source_url"])]
        P.fs[t].update(blogfs)
        if t not in GRAPH or not exists(t, k):
            if t in GRAPH:
                P.report.append(f"{t} {k}: row not found, only its blog fact_source rows deleted")
            continue
        blog_only = [c for c, fl in cols.items() if any(f["source_url"] and is_blog(f["source_url"]) for f in fl) and not any(is_ok(f) for f in fl)]
        if t == "competitive_product":
            continue                                        # handled below
        if not blog_only:
            continue
        reviewed = GRAPH[t][1]
        if not reviewed:                                    # detail row: its value rests only on a blog
            kill(t, {k}, "value only on a blog: " + ", ".join(blog_only))
            continue
        supported_cols = [c for c, fl in cols.items() if any(is_ok(f) for f in fl)]
        if not supported_cols:                              # by_row holds every fact_source row of the row: nothing but blogs and judgements
            kill(t, {k}, "whole row rests only on blogs (" + ", ".join(blog_only) + ")")
            continue
        for c in blog_only:
            nl = nullable(t, c)
            if nl:
                P.nulls[t][(k, c)] = "only blog sources"
                P.fs[t].update(fs_all(t, k, c))
            elif nl is None:
                P.fs[t].update(fs_all(t, k, c))             # not a real column: just the bookkeeping rows
            else:
                P.report.append(f"REPORT {t} {k}.{c}: NOT NULL column rests only on blogs but the row has other support: not changed")

    # ---- 2. competitive_product: product-level support --------------------------------------------------------
    for (t, k), cols in sorted(blog_rows.items()):
        if t != "competitive_product" or not exists(t, k):
            continue
        if any(is_ok(f) for fl in cols.values() for f in fl):
            if any(c == "product_name" and not any(is_ok(f) for f in fl) and any(is_blog(f["source_url"] or "") for f in fl) for c, fl in cols.items()):
                P.report.append(f"REPORT competitive_product {k}.product_name rests only on blogs but the product has other sources: kept")
            continue
        refs = q(cur, "SELECT matchup_id FROM staging.competitive_matchup WHERE competitor_product_id::text = %s", (k,))
        if refs:
            P.report.append(f"REFUSED competitive_product {k}: only blog sources but matchups {[r['matchup_id'] for r in refs]} point at it")
            continue
        kill(t, {k}, "only product-level sources are blogs")

    # ---- 3. text-attributed competitor specs (option) -------------------------------------------------------------
    attributed = [r for r in q(cur, "SELECT spec_id::text AS k, product_id::text AS p, spec_label, spec_value FROM staging.competitive_product_specification "
                                    "WHERE spec_value ~* '(idrw|ajaishukla)'") if TEXT_ATTR.search(r["spec_value"] or "")]
    if drop_text_attributed:
        for r in attributed:
            kill("competitive_product_specification", {r["k"]}, "value text names a blog")
    else:
        for r in attributed:
            P.report.append(f"TEXT competitive_product_specification {r['k']} ({r['spec_label']}): value says {r['spec_value'][:60]!r}; "
                            f"kept (supported by another source); --drop-text-attributed deletes it")

    # ---- 4. surviving rows whose own source_url is a blog ---------------------------------------------------------
    def first_ok(t, k, col):
        for f in q(cur, "SELECT * FROM staging.fact_source WHERE table_name=%s AND row_id=%s AND column_name=%s ORDER BY created_at, fact_source_id", (t, k, col)):
            if f["fact_source_id"] not in P.fs[t] and f["source_url"] and is_ok(f):
                return f["source_url"]
        return None

    for r in q(cur, "SELECT record_id::text AS k, source_url FROM staging.competitive_leader_record WHERE source_url ~* %s", (LOOSE,)):
        if r["k"] in P.rows["competitive_leader_record"] or not is_blog(r["source_url"]):
            continue
        u = first_ok("competitive_leader_record", r["k"], "headline")
        if u:
            P.repoint["competitive_leader_record"][r["k"]] = (u, "first non-blog headline source")
        else:
            kill("competitive_leader_record", {r["k"]}, "source_url is a blog and no other source")
    spec_t = "competitive_product_specification"
    prod_first = {}
    for r in q(cur, "SELECT spec_id::text AS k, product_id::text AS p, source_url, source_count FROM staging.competitive_product_specification"):
        k = r["k"]
        if k in P.rows[spec_t]:
            continue
        blogfs = any(f["source_url"] and is_blog(f["source_url"]) for f in by_row.get((spec_t, k), {}).get("spec_value", []))
        blogurl = bool(r["source_url"] and is_blog(r["source_url"]))
        if not (blogfs or blogurl):
            continue
        own = [f for f in q(cur, "SELECT * FROM staging.fact_source WHERE table_name=%s AND row_id=%s AND column_name='spec_value' AND source_tier<>'judgement'", (spec_t, k))
               if f["fact_source_id"] not in P.fs[spec_t]]
        new_url = r["source_url"]
        if blogurl:
            new_url = first_ok(spec_t, k, "spec_value")
            how = "spec's first non-blog source"
            if not new_url:
                if r["p"] not in prod_first:
                    prod_first[r["p"]] = next((f["source_url"] for f in q(cur, "SELECT * FROM staging.fact_source WHERE table_name='competitive_product' AND row_id=%s "
                                                                              "ORDER BY created_at, fact_source_id", (r["p"],)) if f["source_url"] and is_ok(f)), None)
                new_url, how = prod_first[r["p"]], "product's first non-blog source"
            if not new_url:
                kill(spec_t, {k}, "source_url is a blog and the product has no other source")
                continue
            P.repoint[spec_t][k] = (new_url, how)
        n = len(own) or (1 if new_url else 0)
        if r["source_count"] != n:
            P.counts[k] = n
    # make every spec touched by a count/repoint visible in the table list
    for k in P.counts:
        P.repoint[spec_t].setdefault(k, (None, "source_count only"))

    # ---- 5. *_source tables ----------------------------------------------------------------------------------------
    for t, (cpk, rev, _p) in GRAPH.items():
        if not t.endswith("_source") or rev:
            continue
        if nullable(t, "source_url") is None:
            continue
        for r in q(cur, sql.SQL("SELECT {}::text AS k, source_url FROM {} WHERE source_url ~* %s").format(sql.Identifier(cpk), ident(t)), (LOOSE,)):
            if is_blog(r["source_url"]) and r["k"] not in P.rows[t]:
                P.src_rows[t][r["k"]] = r["source_url"]
                P.fs[t].update(fs_of_row(t, r["k"]))
    # source rows that disappear with a deleted parent are already in P.rows; keep them out of src_rows
    for t in list(P.src_rows):
        for k in list(P.src_rows[t]):
            if k in P.rows[t]:
                del P.src_rows[t][k]

    # ---- 6. matchup specifications of deleted competitor specs; recompute set ---------------------------------------------
    for k in list(P.rows[spec_t]):
        r = q(cur, "SELECT product_id::text AS p, spec_label FROM staging.competitive_product_specification WHERE spec_id::text = %s", (k,))
        if not r:
            continue
        for m in q(cur, "SELECT s.comparison_specification_id::text AS k, s.matchup_id FROM staging.competitive_matchup_specification s "
                        "JOIN staging.competitive_matchup m USING (matchup_id) WHERE m.competitor_product_id::text = %s AND lower(s.spec_label) = lower(%s)",
                   (r[0]["p"], r[0]["spec_label"])):
            if m["k"] not in P.rows["competitive_matchup_specification"]:
                kill("competitive_matchup_specification", {m["k"]}, f"competitor spec {r[0]['spec_label']!r} deleted")
    for k in P.rows["competitive_matchup_specification"]:
        for r in q(cur, "SELECT matchup_id FROM staging.competitive_matchup_specification WHERE comparison_specification_id::text = %s", (k,)):
            P.recompute.add(r["matchup_id"])
    P.recompute -= {int(k) for k in P.rows["competitive_matchup"]}
    return P


def recompute_matchup(cur, mid):
    """edge / counts of one matchup by the rules of derive.matchup_edge, from the stored better_side (no spec value is touched)."""
    specs = q(cur, "SELECT better_side, comparability_state AS st, client_value_numeric AS cn, competitor_value_numeric AS kn, client_value_text AS ct, "
                   "competitor_value_text AS kt FROM staging.competitive_matchup_specification WHERE matchup_id = %s", (mid,))
    comparable = [s for s in specs if (s["st"] or "").lower() == "comparable"]
    score, level = derive.score_sides([s["better_side"] for s in comparable])
    sourced = [s for s in specs if any(s[c] not in (None, "") for c in ("cn", "kn", "ct", "kt"))]
    return {"edge_score": score, "decision_level": level, "comparable_spec_count": len(comparable), "sourced_spec_count": len(sourced)}


def show(cur, P: Plan):
    print(f"plan: {sum(len(v) for v in P.fs.values())} fact_source rows, {sum(len(v) for v in P.rows.values())} rows deleted, "
          f"{sum(len(v) for v in P.nulls.values())} columns set NULL, {sum(len(v) for v in P.repoint.values())} rows repointed/recounted, "
          f"{sum(len(v) for v in P.src_rows.values())} *_source rows, {len(P.recompute)} matchups recomputed")
    for t in sorted(P.tables() | ({"competitive_matchup"} if P.recompute else set())):
        print(f"\n[{t}] fact_source -{len(P.fs.get(t, ()))}  rows -{len(P.rows.get(t, ()))}  NULL {len(P.nulls.get(t, ()))}  "
              f"repoint/recount {len(P.repoint.get(t, ()))}  source rows -{len(P.src_rows.get(t, ()))}")
        for k, why in sorted(P.rows.get(t, {}).items())[:40]:
            print(f"    delete {k}  {label(cur, t, k)}  <- {why}")
        for (k, c), why in sorted(P.nulls.get(t, {}).items()):
            print(f"    NULL {c} of {k}  {label(cur, t, k)}  <- {why}")
        for k, (u, how) in sorted(P.repoint.get(t, {}).items())[:12]:
            print(f"    repoint {k} -> {(u or '-')[:60]} ({how}), source_count -> {P.counts.get(k, 'same')}")
        if len(P.repoint.get(t, {})) > 12:
            print(f"    ... {len(P.repoint[t]) - 12} more")
        for k, u in sorted(P.src_rows.get(t, {}).items()):
            print(f"    delete source row {k}  {u[:70]}")
    if P.recompute:
        print("\n[matchups to recompute]")
        for m in sorted(P.recompute):
            old = q(cur, "SELECT edge_score, decision_level, comparable_spec_count, sourced_spec_count FROM staging.competitive_matchup WHERE matchup_id = %s", (m,))
            gone = [k for k in P.rows["competitive_matchup_specification"]
                    if q(cur, "SELECT 1 FROM staging.competitive_matchup_specification WHERE comparison_specification_id::text=%s AND matchup_id=%s", (k, m))]
            # preview: recompute without the specs that will be deleted
            specs = q(cur, "SELECT comparison_specification_id::text AS k, better_side, comparability_state AS st, client_value_numeric AS cn, competitor_value_numeric AS kn, "
                           "client_value_text AS ct, competitor_value_text AS kt FROM staging.competitive_matchup_specification WHERE matchup_id=%s", (m,))
            specs = [s for s in specs if s["k"] not in P.rows["competitive_matchup_specification"]]
            comp = [s for s in specs if (s["st"] or "").lower() == "comparable"]
            sc, lv = derive.score_sides([s["better_side"] for s in comp])
            srcd = [s for s in specs if any(s[c] not in (None, "") for c in ("cn", "kn", "ct", "kt"))]
            print(f"    matchup {m}: deletes {len(gone)} spec(s); {dict(old[0]) if old else None} -> edge_score {sc}, decision_level {lv}, "
                  f"comparable {len(comp)}, sourced {len(srcd)}")
    for r in P.report:
        print("  " + r)


def apply(conn, P: Plan):
    order = sorted(P.tables() | ({"competitive_matchup"} if P.recompute else set()), key=lambda t: (t == "competitive_matchup", t))
    for t in order:
        cur = conn.cursor()
        try:
            cur.execute("SET LOCAL lock_timeout = '5s'")
            if P.fs.get(t):
                cur.execute("DELETE FROM staging.fact_source WHERE fact_source_id = ANY(%s::uuid[])", (list(P.fs[t]),))
                nfs = cur.rowcount
            else:
                nfs = 0
            nrows = nnull = nrep = 0
            gone = list(P.rows.get(t, {})) + list(P.src_rows.get(t, {}))
            if gone:
                cur.execute(sql.SQL("DELETE FROM {} WHERE {}::text = ANY(%s)").format(ident(t), sql.Identifier(pk_of(t))), (gone,))
                nrows = cur.rowcount
                if nrows != len(gone):
                    raise RuntimeError(f"{t}: deleted {nrows} rows, expected {len(gone)} (changed concurrently?)")
            if t == "competitive_matchup_source" and P.src_rows.get(t):
                cur.execute("UPDATE staging.competitive_matchup_advantage SET source_id = NULL WHERE source_id::text = ANY(%s)", (list(P.src_rows[t]),))
            by_col = defaultdict(list)
            for (k, c) in P.nulls.get(t, {}):
                by_col[c].append(k)
            for c, ks in by_col.items():
                cur.execute(sql.SQL("UPDATE {} SET {} = NULL WHERE {}::text = ANY(%s)").format(ident(t), sql.Identifier(c), sql.Identifier(pk_of(t))), (ks,))
                nnull += cur.rowcount
            for k, (u, _how) in P.repoint.get(t, {}).items():
                sets, args = [], []
                if u:
                    sets.append(sql.SQL("source_url = %s"))
                    args.append(u)
                if t == "competitive_product_specification" and k in P.counts:
                    sets.append(sql.SQL("source_count = %s"))
                    args.append(P.counts[k])
                if sets:
                    cur.execute(sql.SQL("UPDATE {} SET {} WHERE {}::text = %s").format(ident(t), sql.SQL(", ").join(sets), sql.Identifier(pk_of(t))), args + [k])
                    nrep += cur.rowcount
            nrec = 0
            if t == "competitive_matchup":
                for m in sorted(P.recompute):
                    cur.execute("SELECT 1 FROM staging.competitive_matchup WHERE matchup_id = %s FOR UPDATE", (m,))
                    if not cur.fetchone():
                        continue
                    v = recompute_matchup(cur, m)
                    cur.execute("UPDATE staging.competitive_matchup SET edge_score = %(edge_score)s, decision_level = %(decision_level)s, "
                                "comparable_spec_count = %(comparable_spec_count)s, sourced_spec_count = %(sourced_spec_count)s WHERE matchup_id = %(m)s", {**v, "m": m})
                    nrec += 1
                    print(f"    matchup {m} recomputed: {v}")
            conn.commit()
            print(f"[{t}] committed: fact_source -{nfs}, rows -{nrows}, NULL {nnull}, repoint/recount {nrep}, matchups recomputed {nrec}")
        except Exception as e:
            conn.rollback()
            print(f"[{t}] ROLLED BACK: {type(e).__name__}: {str(e)[:200]}")
            raise


def scan(cur):
    """{(table, column): rows mentioning a blog} over every text-like column of schema staging / staging_ui, and the blocked-host fact_source count"""
    out = {}
    cols = q(cur, """SELECT c.table_schema, c.table_name, c.column_name FROM information_schema.columns c JOIN information_schema.tables t
                     USING (table_schema, table_name) WHERE t.table_type='BASE TABLE' AND c.table_schema IN ('staging','staging_ui')
                     AND c.data_type IN ('text','character varying','json','jsonb','character')""")
    for c in cols:
        n = q(cur, sql.SQL("SELECT count(*) AS n FROM {} WHERE {}::text ~* %s").format(sql.Identifier(c["table_schema"], c["table_name"]), sql.Identifier(c["column_name"])), (LOOSE,))[0]["n"]
        if n:
            out[(c["table_schema"] + "." + c["table_name"], c["column_name"])] = n
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="run the plan (default: dry run)")
    ap.add_argument("--drop-text-attributed", action="store_true", help="also delete competitor specs whose value text names a blog, e.g. '(idrw)'")
    ap.add_argument("--dsn", default=LOCAL_DSN, help="local kssl_staging only")
    args = ap.parse_args(argv)
    conn = connect(args.dsn)
    if not args.apply:
        conn.set_session(readonly=True)
    cur = conn.cursor()
    before = scan(cur)
    P = build_plan(cur, args.drop_text_attributed)
    print("DRY RUN (nothing written)" if not args.apply else "APPLY")
    show(cur, P)
    if not args.apply:
        conn.rollback()
        print("\nmentions of the blog domains now (table.column: rows):")
        for (t, c), n in sorted(before.items()):
            print(f"    {t}.{c}: {n}")
        return 0
    if P.empty():
        print("nothing to do")
    else:
        apply(conn, P)
    conn.rollback()
    after = scan(conn.cursor())
    print("\nmentions of the blog domains: before -> after (table.column)")
    for key in sorted(set(before) | set(after)):
        print(f"    {key[0]}.{key[1]}: {before.get(key, 0)} -> {after.get(key, 0)}")
    P2 = build_plan(conn.cursor(), args.drop_text_attributed)
    conn.rollback()
    print("second pass plan empty (idempotent):", P2.empty())
    return 0


if __name__ == "__main__":
    sys.exit(main())
