"""Copy the owner's SIPRI harvest into the LOCAL staging DB (raw layer, db/setup/46_sipri_raw.sql). No model, no web fetch.

Owner 2026-10-25: "SIPRI data is my data, which I have gathered, so you can use it completely." Every row derived from these
tables cites SIPRI (backend/sipri_geo.py): https://www.sipri.org/databases/armstransfers | armsindustry | milex.

Source (READ-ONLY): the data-centre host, compose stack mallory-sipri.
    Postgres  container mallory-sipri-postgres-1, schema sipri: arms_transfers (one row per trade record) and datasets (metadata +
              the MinIO key of each file). Read through `docker exec -i ... psql` over SSH, stdin only, read-only transaction,
              exported with \\copy (...) TO STDOUT WITH CSV HEADER.
    MinIO     bucket mallory-sipri: the Top 100 / milex / export-value workbooks and the armaments / countries JSON. Read with the
              harvester container's own minio client (`docker exec -i mallory-sipri-sipri-1 python -`, script on stdin), which
              streams the object to stdout. Nothing is written on the host, nothing in that stack is changed or restarted.
    SSH       host / port / user / key from deploy.env (env KSSL_DC_ENV_FILE, default C:\\Users\\HARICHANDRA\\Desktop\\deploy.env):
              DATA_CENTRE_HOST, DATA_CENTRE_SSH_PORT, DATA_CENTRE_SSH_USER, DATA_CENTRE_SSH_KEY (key only, BatchMode, never a password).
              No value of that file is ever printed.
Target: LOCAL kssl_staging (env KSSL_STAGING_DSN), tables staging.sipri_*. Upserts on each table's key: a re-run changes only rows
whose content changed (a row SIPRI dropped stays and is counted as 'not in this copy'); the file sha256 is checked against the
harvester's record.

    python -m backend.sipri_import --selftest                 parsing checks on fictional values (no DB, no SSH)
    python -m backend.sipri_import [--only transfers,top100,top100_total,milex,export_value,armament,country] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

DEFAULT_ENV_FILE = r"C:\Users\HARICHANDRA\Desktop\deploy.env"
PG_CONTAINER = "mallory-sipri-postgres-1"
APP_CONTAINER = "mallory-sipri-sipri-1"
SSH_KEYS = ("DATA_CENTRE_HOST", "DATA_CENTRE_SSH_PORT", "DATA_CENTRE_SSH_USER", "DATA_CENTRE_SSH_KEY")
PARTS = ("transfers", "top100", "top100_total", "milex", "export_value", "armament", "country")
DATASET_OF = {"top100": "armsindustry_top100", "top100_total": "armsindustry_revenues", "milex": "milex",
              "export_value": "financial_value_arms_exports", "armament": "armaments", "country": "countries"}

# the object reader run INSIDE the harvester container (its own env holds the MinIO endpoint and keys; nothing is printed but the bytes)
GET_OBJECT = """import os, sys
from minio import Minio
c = Minio(os.environ["MINIO_ENDPOINT"], access_key=os.environ.get("MINIO_ACCESS_KEY", ""), secret_key=os.environ.get("MINIO_SECRET_KEY", ""),
          secure=os.environ.get("MINIO_SECURE", "0") == "1")
r = c.get_object(os.environ.get("SIPRI_MINIO_BUCKET", "mallory-sipri"), sys.argv[1])
try:
    sys.stdout.buffer.write(r.read())
finally:
    r.close(); r.release_conn()
"""


# =====================================================================================================================================
# reaching the data-centre (read-only)
# =====================================================================================================================================

def read_env_file(path: str, keys=SSH_KEYS) -> dict:
    """KEY=VALUE lines of deploy.env, read raw (a Windows path keeps its backslashes); quotes and CR stripped. Other lines ignored."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if "=" not in line:
                continue
            k, v = line.rstrip("\r\n").split("=", 1)
            if k.strip() in keys:
                out[k.strip()] = v.strip().strip("'\"")
    missing = [k for k in keys if not out.get(k)]
    if missing:
        raise RuntimeError(f"deploy.env lacks {', '.join(missing)}")
    return out


def psql_command() -> str:
    """the remote command: psql inside the SIPRI Postgres container, user / db from the container's own env, SQL on stdin"""
    inner = 'psql -X -q -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-sipri}" -d "${POSTGRES_DB:-sipri}"'
    return f"docker exec -i {PG_CONTAINER} sh -c {shlex.quote(inner)}"


def object_command(key: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._/()\-]+", key or ""):
        raise ValueError(f"unexpected MinIO key {key!r}")
    return f"docker exec -i {APP_CONTAINER} python - {shlex.quote(key)}"


class DC:
    def __init__(self, env_file: str | None = None):
        self.v = read_env_file(env_file or os.environ.get("KSSL_DC_ENV_FILE") or DEFAULT_ENV_FILE)
        self.ssh = shutil.which("ssh") or "ssh"

    def run(self, remote: str, stdin: bytes, timeout: int = 600) -> bytes:
        argv = [self.ssh, "-i", self.v["DATA_CENTRE_SSH_KEY"], "-p", self.v["DATA_CENTRE_SSH_PORT"], "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30", f"{self.v['DATA_CENTRE_SSH_USER']}@{self.v['DATA_CENTRE_HOST']}", remote]
        r = subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip().splitlines()
            raise RuntimeError(f"data-centre command failed (exit {r.returncode}): {' | '.join(err[-3:])[:400]}")
        return r.stdout

    def copy_csv(self, select_sql: str) -> list[dict]:
        """one SELECT as CSV rows (dicts), in a read-only transaction with a statement timeout (the host is shared)"""
        sql = ("SET default_transaction_read_only = on;\nSET statement_timeout = '120s';\n"
               f"\\copy ({' '.join(select_sql.split())}) TO STDOUT WITH CSV HEADER\n")
        data = self.run(psql_command(), sql.encode("utf-8"))
        return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))

    def get_object(self, key: str) -> bytes:
        return self.run(object_command(key), GET_OBJECT.encode("utf-8"))


# =====================================================================================================================================
# parsing (pure)
# =====================================================================================================================================

NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def num(v):
    """a cell as a number, or None ('. .', '...', 'xxx', '<1', '' -> None)"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace(",", "").replace("\u2212", "-")
    return float(s) if NUM.fullmatch(s) else None


def cell_text(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def year_of(v) -> int | None:
    s = str(v).strip() if v is not None else ""
    return int(float(s)) if re.fullmatch(r"(19|20)\d\d(\.0)?", s) else None


def as_int(v) -> int | None:
    n = num(v)
    return int(n) if n is not None and float(n).is_integer() else None


def tf(v) -> bool | None:
    return {"t": True, "true": True, "f": False, "false": False}.get(str(v).strip().lower()) if v not in (None, "") else None


def parse_transfers(rows: list[dict]) -> list[tuple]:
    out = []
    for r in rows:
        out.append((int(r["id"]), as_int(r.get("trade_id")), cell_text(r.get("buyer")), cell_text(r.get("seller")), as_int(r.get("order_yr")),
                    tf(r.get("order_yr_est")), as_int(r.get("units")), tf(r.get("units_est")), as_int(r.get("delivery_yr")),
                    cell_text(r.get("status")), tf(r.get("status_est")), cell_text(r.get("desg")), cell_text(r.get("descr")),
                    cell_text(r.get("category")), r.get("raw") or None, r.get("harvested_at") or None))
    return out


def _workbook(data: bytes):
    import openpyxl
    return openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)


def _rows(ws) -> list[list]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _header_index(rows: list[list], first: str, col: int = 0, within: int = 30) -> int | None:
    for i, r in enumerate(rows[:within]):
        if r and len(r) > col and isinstance(r[col], str) and r[col].strip().lower().startswith(first):
            return i
    return None


def parse_top100(data: bytes) -> list[dict]:
    """one row per company and year: every sheet named by a year; columns found by their header words (the layout changes by year)"""
    out = []
    wb = _workbook(data)
    for ws in wb.worksheets:
        year = year_of(ws.title)
        if year is None:
            continue
        rows = _rows(ws)
        h = next((i for i, r in enumerate(rows[:15]) if any(isinstance(c, str) and c.strip().lower().startswith("company") for c in r)), None)
        if h is None:
            continue
        head = [re.sub(r"\s+", " ", str(c)).strip() if c is not None else "" for c in rows[h]]
        col: dict = {}
        ranks, arms, const = [], [], []
        for j, t in enumerate(head):
            tl = t.lower()
            if tl.startswith("rank"):
                ranks.append(j)
            elif tl.startswith("company"):
                col["company"] = j
            elif tl.startswith("country"):
                col["country"] = j
            elif tl.startswith("notes"):
                col["notes"] = j
            elif tl.startswith("total revenues"):
                col["total"] = j
            elif tl.startswith("arms revenues") and "%" in tl:
                col["share"] = j
            elif tl.startswith("arms revenues") and "constant" in tl:
                const.append(j)
            elif tl.startswith("arms revenues"):
                arms.append(j)
        for name, lst in (("rank", ranks), ("arms", arms), ("const", const)):        # this year's column first, the previous year's second
            if lst:
                col[name] = lst[0]
            if len(lst) > 1:
                col[name + "_prev"] = lst[1]
        if "company" not in col:
            continue
        for r in rows[h + 1:]:
            company = cell_text(r[col["company"]]) if col["company"] < len(r) else None
            if not company or company.lower().startswith(("note", "source")):
                continue
            g = lambda k: r[col[k]] if k in col and col[k] < len(r) else None    # noqa: E731
            if num(g("arms")) is None and as_int(g("rank")) is None:             # a footnote line under the table
                continue
            out.append({"year": year, "company": company, "rank": as_int(g("rank")), "rank_text": cell_text(g("rank")),
                        "rank_prev": as_int(g("rank_prev")), "rank_prev_text": cell_text(g("rank_prev")), "country": cell_text(g("country")),
                        "arms_revenue_usd_m": num(g("arms")), "arms_revenue_prev_usd_m": num(g("arms_prev")), "total_revenue_usd_m": num(g("total")),
                        "arms_share": num(g("share")), "arms_revenue_const_usd_m": num(g("const")),
                        "arms_revenue_prev_const_usd_m": num(g("const_prev")),
                        "price_base_note": head[col["const"]] if "const" in col else None, "notes": cell_text(g("notes")),
                        "raw": json.dumps({head[j] or f"col{j}": cell_text(v) for j, v in enumerate(r) if cell_text(v) is not None}, ensure_ascii=False)})
    seen, uniq = set(), []
    for x in out:                                    # (year, company) is the key; a repeated name in one sheet keeps its first row
        if (x["year"], x["company"]) not in seen:
            seen.add((x["year"], x["company"]))
            uniq.append(x)
    return uniq


def parse_top100_total(data: bytes) -> list[dict]:
    wb = _workbook(data)
    rows = _rows(wb.worksheets[0])
    yr_row = next((r for r in rows if sum(year_of(c) is not None for c in r[1:]) >= 3), None)
    if yr_row is None:
        return []
    years = {j: year_of(c) for j, c in enumerate(yr_row) if j > 0 and year_of(c) is not None}
    cur = next((r for r in rows if isinstance(r[0], str) and r[0].strip().lower().startswith("current")), None)
    con = next((r for r in rows if isinstance(r[0], str) and r[0].strip().lower().startswith("constant")), None)
    return [{"year": y, "current_usd_bn": num(cur[j]) if cur and j < len(cur) else None,
             "constant_2024_usd_bn": num(con[j]) if con and j < len(con) else None} for j, y in sorted(years.items())]


MILEX_SHEETS = (("local currency financial", "local_currency_fy"), ("local currency calendar", "local_currency_cy"),
                ("constant", "constant_2024_usd_m"), ("current us", "current_usd_m"), ("share of gdp", "share_gdp"),
                ("per capita", "per_capita_usd"), ("share of govt", "share_govt_spending"))
MILEX_REGIONS = {"africa", "americas", "asia & oceania", "asia and oceania", "europe", "middle east"}
FOOTNOTE_MARK = re.compile(r"[\s\u2020\u2021\u00a7\u00b6*#\u2016]+$")


def parse_milex(data: bytes) -> list[dict]:
    """one row per country and year, the seven country sheets side by side; region / sub-region from the heading rows"""
    wb = _workbook(data)
    rows_out: dict = {}
    for ws in wb.worksheets:
        field = next((f for p, f in MILEX_SHEETS if ws.title.strip().lower().startswith(p)), None)
        if field is None:
            continue
        rows = _rows(ws)
        h = _header_index(rows, "country")
        if h is None:
            continue
        head = rows[h]
        years = {j: year_of(c) for j, c in enumerate(head) if year_of(c) is not None}
        meta = {str(c).strip().lower(): j for j, c in enumerate(head) if isinstance(c, str) and c.strip()}
        region = subregion = None
        for r in rows[h + 1:]:
            name = cell_text(r[0]) if r else None
            if not name:
                continue
            vals = [r[j] if j < len(r) else None for j in years]
            if all(cell_text(v) is None for v in vals):              # a heading row (region / sub-region) or a note under the table
                if name.lower() in MILEX_REGIONS:
                    region, subregion = name, None
                else:
                    subregion = name
                continue
            country = FOOTNOTE_MARK.sub("", name).strip()
            for j, y in years.items():
                v = r[j] if j < len(r) else None
                if cell_text(v) is None:
                    continue
                row = rows_out.setdefault((country, y), {"country": country, "year": y, "raw_text": {}})
                row.setdefault("region", region)
                row.setdefault("subregion", subregion)
                n = num(v)
                if n is None:
                    row["raw_text"][field] = cell_text(v)
                else:
                    row[field] = n
            for label, key in (("currency", "currency"), ("notes", "notes")):
                j = meta.get(label)
                if j is not None and j < len(r) and cell_text(r[j]):
                    for y in years.values():
                        if (country, y) in rows_out:
                            rows_out[(country, y)].setdefault(key, cell_text(r[j]))
            j = next((jj for k, jj in meta.items() if k.startswith("fiscal year")), None)
            if j is not None and j < len(r) and cell_text(r[j]):
                for y in years.values():
                    if (country, y) in rows_out:
                        rows_out[(country, y)].setdefault("fiscal_year", cell_text(r[j]))
            if name != country:
                for y in years.values():
                    if (country, y) in rows_out:
                        rows_out[(country, y)]["raw_text"].setdefault("name_as_printed", name)
    return list(rows_out.values())


EXPORT_SHEETS = (("local", "local_currency"), ("current", "current_usd"), ("constant", "constant_usd"))


def parse_export_values(data: bytes) -> list[dict]:
    """one row per sheet, country, series and year. A country's block: its first row, then rows with an empty first cell (more series),
    an indented label ('   Industry') or a label row with no figures (a sub-heading for the next series)."""
    wb = _workbook(data)
    out = []
    for ws in wb.worksheets:
        basis = next((b for p, b in EXPORT_SHEETS if ws.title.strip().lower().startswith(p)), None)
        if basis is None:
            continue
        rows = _rows(ws)
        h = _header_index(rows, "country")
        if h is None:
            continue
        head = rows[h]
        years = {j: year_of(c) for j, c in enumerate(head) if year_of(c) is not None}
        expl = next((j for j, c in enumerate(head) if isinstance(c, str) and c.strip().lower().startswith("explanation")), None)
        cur_col = next((j for j, c in enumerate(head) if isinstance(c, str) and c.strip().lower() == "currency"), None)
        unit = next((cell_text(r[0]) for r in rows[:h] if r and isinstance(r[0], str) and re.search(r"(million|currency|prices)", r[0], re.I)
                     and not r[0].lower().startswith(("government", "copyright", "updated"))), None)
        country, series_no, pending = None, 0, None
        for r in rows[h + 1:]:
            first = r[0] if r else None
            vals = {y: (r[j] if j < len(r) else None) for j, y in years.items()}
            has_data = any(cell_text(v) is not None for v in vals.values())
            explanation = cell_text(r[expl]) if expl is not None and expl < len(r) else None
            label = cell_text(first)
            if not has_data and not explanation:
                if label and country:
                    pending = label                            # a sub-heading for the next series of this country
                continue
            if label and not str(first).startswith((" ", "\t")):
                country, series_no, pending = label.strip(), 0, None
            elif label:
                pending = label
            if country is None:
                continue
            series_no += 1
            for y, v in vals.items():
                t = cell_text(v)
                if t is None:
                    continue
                n = num(v)
                out.append({"basis": basis, "country": country, "series_no": series_no, "year": y, "series": explanation,
                            "sub_label": pending, "currency": cell_text(r[cur_col]) if cur_col is not None and cur_col < len(r) else None,
                            "unit_note": unit, "value": n, "value_text": None if n is not None else t})
            pending = None
    return out


def parse_armaments(data: bytes) -> list[dict]:
    d = json.loads(data.decode("utf-8"))
    out = [{"kind": "designation", "name": str(n).strip(), "entity_id": None, "code": None, "type_code": None}
           for n in d.get("designations", []) if str(n).strip()]
    out += [{"kind": "category", "name": str(c.get("Name")).strip(), "entity_id": c.get("EntityId"), "code": c.get("Code"), "type_code": c.get("Type")}
            for c in d.get("categories", []) if c.get("Name")]
    seen, uniq = set(), []
    for x in out:
        if (x["kind"], x["name"]) not in seen:
            seen.add((x["kind"], x["name"]))
            uniq.append(x)
    return uniq


def parse_countries(data: bytes) -> list[dict]:
    return [{"entity_id": c.get("EntityId"), "name": c.get("Name"), "country_code": c.get("CountryCode"), "deleted": c.get("deleted")}
            for c in json.loads(data.decode("utf-8")) if c.get("EntityId") is not None]


# =====================================================================================================================================
# writing (local staging)
# =====================================================================================================================================

def upsert(cur, table: str, rows: list[dict], key: list[str], cols: list[str], jsonb: tuple = ()) -> tuple[int, int]:
    """INSERT ... ON CONFLICT (key) DO UPDATE only where a value differs. Returns (inserted, updated)."""
    from psycopg2.extras import execute_values
    if not rows:
        return 0, 0
    allc = key + [c for c in cols if c not in key]
    tmpl = "(" + ", ".join("%s::jsonb" if c in jsonb else "%s" for c in allc) + ")"
    upd = [c for c in allc if c not in key]
    sql = (f"INSERT INTO staging.{table} ({', '.join(allc)}) VALUES %s ON CONFLICT ({', '.join(key)}) DO UPDATE SET "
           + ", ".join(f"{c} = EXCLUDED.{c}" for c in upd) + ", imported_at = now() WHERE ("
           + ", ".join(f"staging.{table}.{c}" for c in upd) + ") IS DISTINCT FROM (" + ", ".join(f"EXCLUDED.{c}" for c in upd)
           + ") RETURNING (xmax = 0)")
    ins = upd_n = 0
    for i in range(0, len(rows), 2000):
        chunk = [tuple((json.dumps(r[c], ensure_ascii=False) if c in jsonb and not isinstance(r.get(c), (str, type(None))) else r.get(c))
                       for c in allc) for r in rows[i:i + 2000]]
        res = execute_values(cur, sql, chunk, template=tmpl, page_size=2000, fetch=True)
        ins += sum(1 for (x,) in res if x)
        upd_n += sum(1 for (x,) in res if not x)
    return ins, upd_n


TRANSFER_COLS = ["id", "trade_id", "buyer", "seller", "order_yr", "order_yr_est", "units", "units_est", "delivery_yr", "status", "status_est",
                 "desg", "descr", "category", "raw", "harvested_at"]
TABLES = {
    "top100": ("sipri_top100", ["year", "company"], ["rank", "rank_text", "rank_prev", "rank_prev_text", "country", "arms_revenue_usd_m",
               "arms_revenue_prev_usd_m", "total_revenue_usd_m", "arms_share", "arms_revenue_const_usd_m", "arms_revenue_prev_const_usd_m",
               "price_base_note", "notes", "raw"], ("raw",), parse_top100),
    "top100_total": ("sipri_top100_total", ["year"], ["current_usd_bn", "constant_2024_usd_bn"], (), parse_top100_total),
    "milex": ("sipri_milex", ["country", "year"], ["region", "subregion", "currency", "fiscal_year", "notes", "local_currency_fy",
              "local_currency_cy", "constant_2024_usd_m", "current_usd_m", "share_gdp", "per_capita_usd", "share_govt_spending", "raw_text"],
              ("raw_text",), parse_milex),
    "export_value": ("sipri_export_value", ["basis", "country", "series_no", "year"], ["series", "sub_label", "currency", "unit_note", "value",
                     "value_text"], (), parse_export_values),
    "armament": ("sipri_armament", ["kind", "name"], ["entity_id", "code", "type_code"], (), parse_armaments),
    "country": ("sipri_country", ["entity_id"], ["name", "country_code", "deleted"], (), parse_countries),
}


def run(parts: list[str], dry_run: bool) -> int:
    import psycopg2
    from backend import ops_log
    from backend.routine import env
    dc = DC()
    meta = {r["key"]: r for r in dc.copy_csv("SELECT key, title, source_url, landing_url, kind, sha256, bytes, minio_key, row_count, harvested_at "
                                             "FROM sipri.datasets ORDER BY key")}
    conn = psycopg2.connect(env()["KSSL_STAGING_DSN"])
    report = []
    try:
        with conn.cursor() as cur:
            if "transfers" in parts:
                rows = parse_transfers(dc.copy_csv(f"SELECT {', '.join(TRANSFER_COLS[:-2])}, raw::text AS raw, harvested_at "
                                                   "FROM sipri.arms_transfers ORDER BY id"))
                dicts = [dict(zip(TRANSFER_COLS, r)) for r in rows]
                ins, upd = upsert(cur, "sipri_arms_transfer", dicts, ["id"], TRANSFER_COLS[1:], jsonb=("raw",))
                cur.execute("SELECT count(*) FROM staging.sipri_arms_transfer")
                held = cur.fetchone()[0]
                gone = held - len({d["id"] for d in dicts})
                report.append(("sipri_arms_transfer", len(dicts), ins, upd, held, gone))
                _dataset_row(cur, {"key": "arms_transfers", "title": "SIPRI Arms Transfers Database (trade records)",
                                   "source_url": "https://www.sipri.org/databases/armstransfers", "kind": "postgres",
                                   "row_count": len(dicts), "harvested_at": max((d["harvested_at"] for d in dicts if d["harvested_at"]), default=None)}, held)
            for part in [p for p in parts if p in TABLES]:
                table, key, cols, jsonb, parser = TABLES[part]
                m = meta.get(DATASET_OF[part])
                if not m or not m.get("minio_key"):
                    report.append((table, 0, 0, 0, None, f"dataset {DATASET_OF[part]} has no file on record"))
                    continue
                blob = dc.get_object(m["minio_key"])
                sha = hashlib.sha256(blob).hexdigest()
                if m.get("sha256") and sha != m["sha256"]:
                    raise RuntimeError(f"{m['minio_key']}: sha256 differs from the harvester's record; nothing written")
                rows = parser(blob)
                ins, upd = upsert(cur, table, rows, key, cols, jsonb=jsonb)
                cur.execute(f"SELECT count(*) FROM staging.{table}")
                held = cur.fetchone()[0]
                report.append((table, len(rows), ins, upd, held, held - len(rows)))
                _dataset_row(cur, m, held)
        print(f"{'table':24} {'parsed':>8} {'new':>7} {'changed':>8} {'held':>7}  not in this copy")
        for t, n, i, u, h, g in report:
            print(f"{t:24} {n:>8} {i:>7} {u:>8} {h if h is not None else '-':>7}  {g}")
        ops_log.note("sipri_import", "copied", "; ".join(f"{t}: {n} parsed, {i} new, {u} changed" for t, n, i, u, _h, _g in report),
                     detail={"rows": [list(map(str, x)) for x in report]})
        if dry_run:
            conn.rollback()
            print("dry run: rolled back")
        else:
            conn.commit()
            print("committed")
    finally:
        conn.close()
    return 0


def _dataset_row(cur, m: dict, held: int) -> None:
    cur.execute("""INSERT INTO staging.sipri_dataset (dataset_key, title, source_url, landing_url, kind, sha256, bytes, minio_key, row_count,
                                                      harvested_at, imported_rows, imported_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                   ON CONFLICT (dataset_key) DO UPDATE SET title = EXCLUDED.title, source_url = EXCLUDED.source_url, landing_url = EXCLUDED.landing_url,
                     kind = EXCLUDED.kind, sha256 = EXCLUDED.sha256, bytes = EXCLUDED.bytes, minio_key = EXCLUDED.minio_key,
                     row_count = EXCLUDED.row_count, harvested_at = EXCLUDED.harvested_at, imported_rows = EXCLUDED.imported_rows, imported_at = now()""",
                (m["key"], m.get("title"), m.get("source_url"), m.get("landing_url") or None, m.get("kind"), m.get("sha256") or None,
                 as_int(m.get("bytes")), m.get("minio_key") or None, as_int(m.get("row_count")), m.get("harvested_at") or None, held))


# =====================================================================================================================================
# self-check (fictional values, no DB, no SSH)
# =====================================================================================================================================

def _book(sheets: dict) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _selftest() -> None:
    assert num("1,234.5") == 1234.5 and num(". .") is None and num("<1") is None and num(42) == 42 and num("xxx") is None
    assert year_of("2019") == 2019 and year_of(2020.0) == 2020 and year_of("Notes") is None and as_int("12") == 12 and as_int("-") is None
    assert tf("t") is True and tf("f") is False and tf("") is None
    t = parse_transfers([{"id": "7", "trade_id": "70", "buyer": "Veland", "seller": "Nordvik", "order_yr": "2022", "order_yr_est": "f", "units": "",
                          "units_est": "", "delivery_yr": "0", "status": "N", "status_est": "", "desg": "NV-155 155mm", "descr": "towed gun",
                          "category": "Artillery", "raw": '{"id": 7}', "harvested_at": "2026-08-20 16:00:00+00"}])
    assert t[0][:9] == (7, 70, "Veland", "Nordvik", 2022, False, None, None, 0) and t[0][11] == "NV-155 155mm"
    top = _book({"2024": [["The Top 100, 2024"], ["Revenue figures ..."], ["Source: ..."],
                          ["Rank (2024) *Note (b)", "Rank (2023)", "Company (c) ", "Notes (2024)", "Country (d)", "Arms revenues (2024)",
                           "Arms revenues (2023)", "Total revenues (2024)", "Arms revenues as a % of total revenues (2024)",
                           "Arms revenues 2023 (constant 2024 prices) note (e)"],
                          [1, 2, "Nordvik Arms", None, "Nordland", 1000, 900, 2000, 0.5, 950],
                          [2, "-", "Veland Works", "new", "Veland", 800, ". .", 800, 1, ". ."],
                          ["(a) A footnote line."]],
                 "Notes": [["not a year"]]})
    p = parse_top100(top)
    assert len(p) == 2 and p[0]["company"] == "Nordvik Arms" and p[0]["rank"] == 1 and p[0]["arms_revenue_usd_m"] == 1000
    assert p[0]["arms_revenue_prev_usd_m"] == 900 and p[0]["arms_share"] == 0.5 and p[0]["arms_revenue_const_usd_m"] == 950
    assert p[1]["rank_prev"] is None and p[1]["rank_prev_text"] == "-" and p[1]["arms_revenue_prev_usd_m"] is None and p[1]["notes"] == "new"
    tot = parse_top100_total(_book({"Sheet1": [["Total"], [None, 2023, 2024, 2025], ["current US$ (billion)", 600, 650, 700],
                                               ["% change", None, 0.1, 0.1], ["constant 2024 US$ (billion)", 610, 650, ". ."]]}))
    assert tot == [{"year": 2023, "current_usd_bn": 600, "constant_2024_usd_bn": 610}, {"year": 2024, "current_usd_bn": 650, "constant_2024_usd_bn": 650},
                   {"year": 2025, "current_usd_bn": 700, "constant_2024_usd_bn": None}]
    mx = parse_milex(_book({"Constant (2024) US$": [["Military expenditure ..."], [""], ["Country", "", "Notes", 2024, 2025], [None],
                                                    ["Europe"], ["Western Europe"], ["Nordland \u2021", None, "\u00a7", 100.5, "..."], ["Veland", None, None, "xxx", 7]],
                            "Share of GDP": [["..."], ["Country", "Notes", 2024, 2025], ["Europe"], ["Nordland", None, 0.02, ". ."]]}))
    byk = {(r["country"], r["year"]): r for r in mx}
    assert byk[("Nordland", 2024)]["constant_2024_usd_m"] == 100.5 and byk[("Nordland", 2024)]["share_gdp"] == 0.02
    assert byk[("Nordland", 2024)]["region"] == "Europe" and byk[("Nordland", 2024)]["subregion"] == "Western Europe"
    assert byk[("Nordland", 2025)]["raw_text"]["constant_2024_usd_m"] == "..." and byk[("Veland", 2024)]["raw_text"]["constant_2024_usd_m"] == "xxx"
    assert byk[("Nordland", 2024)]["notes"] == "\u00a7" and byk[("Nordland", 2024)]["raw_text"]["name_as_printed"] == "Nordland \u2021"
    ev = parse_export_values(_book({"Current US": [["Government and industry data ..."], ["Current million US Dollars"],
                                                   ["Country", 2021, 2022, "Explanation of data"],
                                                   ["Nordland", 10, ". .", "Arms exports"], [None, 20, 30, "Arms export licences"], [None],
                                                   ["Veland", 5, 6, "Arms exports"], ["   Industry", 1, 2, "Arms exports (industry)"],
                                                   ["Arms export agreements"], [None, 9, None, "Arms export agreements (FMS)"]]}))
    k = {(r["country"], r["series_no"], r["year"]): r for r in ev}
    assert k[("Nordland", 1, 2021)]["value"] == 10 and k[("Nordland", 1, 2022)]["value_text"] == ". ." and k[("Nordland", 2, 2022)]["value"] == 30
    assert k[("Veland", 2, 2021)]["sub_label"] == "Industry" and k[("Veland", 1, 2021)]["sub_label"] is None
    assert k[("Veland", 3, 2021)]["sub_label"] == "Arms export agreements" and k[("Veland", 3, 2021)]["value"] == 9
    assert k[("Nordland", 1, 2021)]["unit_note"] == "Current million US Dollars" and k[("Nordland", 1, 2021)]["basis"] == "current_usd"
    ar = parse_armaments(json.dumps({"designations": ["NV-155", "NV-155", " "], "categories": [{"EntityId": 1, "Name": "combat vehicle",
                                                                                                 "Code": "combat vehicle", "Type": 10}]}).encode())
    assert [a["name"] for a in ar] == ["NV-155", "combat vehicle"] and ar[1]["entity_id"] == 1
    assert parse_countries(b'[{"EntityId": 5, "Name": "Veland", "CountryCode": "VEL", "deleted": false}]')[0]["country_code"] == "VEL"
    assert "${POSTGRES_USER:-sipri}" in psql_command() and object_command("datasets/milex/ab-SIPRI-Milex_v1.2.xlsx").endswith("v1.2.xlsx")
    try:
        object_command("x; rm -rf /")
        raise AssertionError("unsafe key accepted")
    except ValueError:
        pass
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as fh:
        fh.write('DATA_CENTRE_HOST=10.0.0.1\nDATA_CENTRE_SSH_PORT=22\nDATA_CENTRE_SSH_USER=u\nDATA_CENTRE_SSH_KEY="C:\\keys\\k"\r\nOTHER=x\n')
    try:
        v = read_env_file(fh.name)
        assert v["DATA_CENTRE_SSH_KEY"] == "C:\\keys\\k" and "OTHER" not in v
    finally:
        os.unlink(fh.name)
    print("sipri_import self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", default=",".join(PARTS), help="comma list of: " + ", ".join(PARTS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    parts = [p.strip() for p in a.only.split(",") if p.strip()]
    bad = [p for p in parts if p not in PARTS]
    if bad:
        ap.error(f"unknown part(s): {', '.join(bad)}")
    return run(parts, a.dry_run)


if __name__ == "__main__":
    from backend import ops_log as _ops
    sys.exit(_ops.logged("backend.sipri_import")(main)())
