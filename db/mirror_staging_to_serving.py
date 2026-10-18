"""Publish ALL of staging to serving as it is (user 2026-10-18), then verify both sides match. Local databases only.

    python -m db.mirror_staging_to_serving --check      compare only: per table row count + checksum, staging vs serving (no write)
    python -m db.mirror_staging_to_serving --apply      replace every serving.* / ui.* table with its staging.* / staging_ui.* twin, then check

This bypasses the per-card review: every staging row becomes live. Back up the serving DB first
(docker exec kssl-pg pg_dump -U kssl -d kssl_serving -Fc > backup.dump). One serving transaction for every table (all or nothing), with
SET LOCAL kssl.approve = 'on' (the guard of db/setup/04_serving_db.sql). Copied columns = the columns both twins have; a column only one
side has is reported. Staging-only tables (prompt_run, source_document, review_decision ...) are not part of serving and are not copied.
Refuses any host other than 127.0.0.1 / localhost.
"""

from __future__ import annotations

import argparse
import io
import os
import sys

import psycopg2
from psycopg2 import sql

STG = os.environ.get("KSSL_STAGING_DSN", "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl")
SRV = os.environ.get("KSSL_SERVING_DSN", "host=127.0.0.1 port=55432 dbname=kssl_serving user=kssl password=kssl")
TWIN = {"staging": "serving", "staging_ui": "ui"}


def local_only(dsn: str) -> None:
    p = psycopg2.extensions.parse_dsn(dsn)
    if p.get("host") not in ("127.0.0.1", "localhost"):
        raise SystemExit(f"refused: {p.get('host')} is not the local database")


def columns(cur, schema: str, table: str) -> list[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND is_generated = 'NEVER' "
                "ORDER BY ordinal_position", (schema, table))
    return [r[0] for r in cur.fetchall()]


def pairs(st, sv) -> list[tuple[str, str, list[str], list[str], list[str]]]:
    """(staging schema, table, shared columns, staging-only columns, serving-only columns) for every serving table with a staging twin."""
    q = "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE'"
    st.execute(q, (list(TWIN),))
    have = {(s, t) for s, t in st.fetchall()}
    sv.execute(q, (list(TWIN.values()),))
    out = []
    for s_schema, t in sorted((s, t) for s, t in sv.fetchall()):
        stg_schema = next(k for k, v in TWIN.items() if v == s_schema)
        if (stg_schema, t) not in have:
            continue
        a, b = columns(st, stg_schema, t), columns(sv, s_schema, t)
        out.append((stg_schema, t, [c for c in b if c in a], [c for c in a if c not in b], [c for c in b if c not in a]))
    return out


def fingerprint(cur, schema: str, table: str, cols: list[str]) -> tuple[int, str]:
    """(rows, md5 over every row of the shared columns as text, in a fixed order)."""
    row = sql.SQL("ROW({})::text").format(sql.SQL(", ").join(sql.Identifier(c) for c in cols))
    cur.execute(sql.SQL("SELECT count(*), coalesce(md5(string_agg(x, E'\\n' ORDER BY x)), '') FROM (SELECT {} AS x FROM {}.{}) s")
                .format(row, sql.Identifier(schema), sql.Identifier(table)))
    n, h = cur.fetchone()
    return n, h


def check(st, sv, ps) -> int:
    bad = 0
    for stg_schema, t, cols, only_st, only_sv in ps:
        a, b = fingerprint(st, stg_schema, t, cols), fingerprint(sv, TWIN[stg_schema], t, cols)
        if a != b:
            bad += 1
            print(f"  DIFFERENT {TWIN[stg_schema]}.{t}: staging {a[0]} rows, serving {b[0]} rows" + ("" if a[0] != b[0] else " (same count, different values)"))
    st.connection.rollback()
    sv.connection.rollback()
    print(f"check: {len(ps)} tables compared, {len(ps) - bad} identical, {bad} different")
    return bad


def apply(st, sv, ps) -> None:
    sv.execute("SET LOCAL kssl.approve = 'on'")
    total = 0
    for stg_schema, t, cols, _, _ in ps:
        target = sql.SQL("{}.{}").format(sql.Identifier(TWIN[stg_schema]), sql.Identifier(t))
        cl = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
        buf = io.StringIO()
        st.copy_expert(sql.SQL("COPY (SELECT {} FROM {}.{}) TO STDOUT").format(cl, sql.Identifier(stg_schema), sql.Identifier(t)).as_string(st), buf)
        buf.seek(0)
        sv.execute(sql.SQL("DELETE FROM {}").format(target))
        sv.copy_expert(sql.SQL("COPY {} ({}) FROM STDIN").format(target, cl).as_string(sv), buf)
        sv.execute(sql.SQL("SELECT count(*) FROM {}").format(target))
        total += sv.fetchone()[0]
    sv.connection.commit()
    st.connection.rollback()
    print(f"applied: {len(ps)} tables replaced in one transaction, {total} rows now in serving")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    local_only(STG)
    local_only(SRV)
    st, sv = psycopg2.connect(STG).cursor(), psycopg2.connect(SRV).cursor()
    ps = pairs(st, sv)
    diff = [(f"{TWIN[s]}.{t}", o1, o2) for s, t, _, o1, o2 in ps if o1 or o2]
    for name, o1, o2 in diff:
        print(f"  columns differ in {name}: staging only {o1 or '-'}; serving only {o2 or '-'} (not copied / left empty)")
    if a.apply:
        apply(st, sv, ps)
    return 1 if check(st, sv, ps) else 0


if __name__ == "__main__":
    sys.exit(main())
