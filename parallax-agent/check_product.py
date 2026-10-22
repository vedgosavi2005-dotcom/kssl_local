#!/usr/bin/env python3
"""Does the adapter (adapter/) still fit the product it sits in? A free check: no model
calls, nothing written to the product or its database.

    .local/venv/bin/python check_product.py [--dsn "<product DSN>"] [--api http://127.0.0.1:8600] [--dist <dir>]

Defaults: --dsn $KSSL_DSN, --api $PRODUCT_API, --dist $PRODUCT_DIST or the manifest's
source_checks.dist_dir. Run it after the product changes (new UI or database version);
each FAIL or WARN names the adapter file to change. See PORTING.md.

Checks:
  database   adapter/analytics.sql applies (inside a rolled-back transaction); rows per
             view; the manifest's data facts and companies query run
  dataset    the product API serves the dataset with the globals the adapter expects;
             adapter/ui_index.py builds page blocks from it (count per kind)
  routes     every page in product.json exists in the product's route table, and every
             route view is either mapped or listed as deliberately skipped
  payloads   each page's payload keys are read somewhere in the product's page code
  app state  the navigation function, route keys and context paths exist in the AppState
  dom        every class the bridge relies on appears in the built product
  theme      the product's CSS tokens and palette colours exist
  blocks     each page's focus headings appear in the built product
  widget     the bundled widget is newer than product.json
"""

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADAPTER = Path(os.environ.get("ADAPTER_DIR") or HERE / "adapter")
ROOT = HERE.parent
M = json.loads((ADAPTER / "product.json").read_text(encoding="utf-8"))
SC = M.get("source_checks", {})

rows = []   # (status, area, what, fix)


def note(status, area, what, fix=""):
    rows.append((status, area, what, fix))


def load_module(name):
    spec = importlib.util.spec_from_file_location(f"adapter_{name}", ADAPTER / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(rel):
    p = (ROOT / rel) if rel else None
    return p.read_text(encoding="utf-8", errors="replace") if p and p.is_file() else None


# ---------------------------------------------------------------- database

def check_database(dsn):
    try:
        import psycopg2
    except ImportError:
        note("SKIP", "database", "psycopg2 not installed (use .local/venv/bin/python)")
        return
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except Exception as exc:
        note("FAIL", "database", f"cannot connect: {exc}", "start the product database; pass --dsn")
        return
    try:
        with conn.cursor() as cur:
            try:
                cur.execute((ADAPTER / "analytics.sql").read_text(encoding="utf-8"))
            except Exception as exc:
                note("FAIL", "database", f"adapter/analytics.sql does not apply: {str(exc).strip().splitlines()[0]}",
                     "adapter/analytics.sql: point the view at the renamed table/column")
                return
            cur.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'analytics' AND c.relkind IN ('v', 'r', 'm') ORDER BY 1")
            views = [r[0] for r in cur.fetchall()]
            empty = []
            counts = []
            for v in views:
                cur.execute(f'SELECT count(*) FROM analytics."{v}"')
                n = cur.fetchone()[0]
                counts.append(f"{v} {n}")
                if n == 0:
                    empty.append(v)
            note("OK", "database", f"analytics.sql applies: {len(views)} views ({', '.join(counts)})")
            for v in empty:
                note("WARN", "database", f"analytics.{v} is empty", "adapter/analytics.sql: the source moved, or the data has none")
            order = M["database"].get("catalog_order") or []
            missing = [v for v in order if v not in views]
            if missing:
                note("FAIL", "database", f"catalog_order names views that do not exist: {', '.join(missing)}", "adapter/product.json database.catalog_order")
            cur.execute("SET search_path = analytics")
            bad = []
            for name, sql in (M["database"].get("facts") or {}).items():
                try:
                    cur.execute("SAVEPOINT f")
                    cur.execute(sql)
                    cur.fetchone()
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT f")
                    bad.append(f"{name} ({str(exc).strip().splitlines()[0]})")
            if bad:
                note("FAIL", "database", "data facts fail: " + "; ".join(bad), "adapter/product.json database.facts")
            else:
                note("OK", "database", f"{len(M['database'].get('facts') or {})} data facts run")
            try:
                cur.execute(M["database"]["companies_sql"])
                ids = {str(r[0]) for r in cur.fetchall()}
                if M["companies"] == "from_data":
                    note("OK" if ids else "FAIL", "database", f"companies come from the data ({len(ids)})",
                         "" if ids else "adapter/analytics.sql company view")
                    raise StopIteration
                known = {c["id"] for c in M["companies"]}
                if ids - known:
                    note("WARN", "database", f"companies in the data but not in product.json: {', '.join(sorted(ids - known))}",
                         "adapter/product.json companies (aliases, colour slot)")
                if known - ids:
                    note("WARN", "database", f"companies in product.json but not in the data: {', '.join(sorted(known - ids))}",
                         "adapter/product.json companies")
                if ids == known:
                    note("OK", "database", f"companies match product.json ({len(ids)})")
            except StopIteration:
                pass
            except Exception as exc:
                note("FAIL", "database", f"companies_sql fails: {exc}", "adapter/product.json database.companies_sql")
    finally:
        conn.rollback()
        conn.close()


# ---------------------------------------------------------------- dataset and page index

def check_dataset(api):
    try:
        import httpx
    except ImportError:
        note("SKIP", "dataset", "httpx not installed (use .local/venv/bin/python)")
        return
    url = api.rstrip("/") + M["product_api"]["dataset"]
    try:
        r = httpx.get(url, timeout=60)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:
        note("FAIL", "dataset", f"{url}: {exc}", "start the product backend; pass --api")
        return
    want = M["product_api"].get("required_globals") or {}
    wrong = [f"{k} ({'missing' if k not in d else type(d[k]).__name__})" for k, t in want.items()
             if k not in d or (t == "object" and not isinstance(d[k], dict)) or (t == "array" and not isinstance(d[k], list))]
    if wrong:
        note("FAIL", "dataset", "globals missing or retyped: " + ", ".join(wrong), "adapter/ui_index.py and product_api.required_globals")
    else:
        note("OK", "dataset", f"{len(want)} expected globals present ({len(d)} in all)")
    new = sorted(set(d) - set(want))
    if new:
        note("INFO", "dataset", "globals the adapter does not read: " + ", ".join(new), "adapter/ui_index.py if a page shows them")
    try:
        idx = load_module("ui_index")
        docs = idx.build(d, M)
    except Exception as exc:
        note("FAIL", "dataset", f"adapter/ui_index.py build() fails: {type(exc).__name__}: {exc}", "adapter/ui_index.py")
        return
    by = {}
    for doc in docs.values():
        by[doc["kind"]] = by.get(doc["kind"], 0) + 1
    note("OK", "dataset", f"page index: {len(docs)} blocks ({', '.join(f'{k} {v}' for k, v in sorted(by.items()))})")
    for k in getattr(idx, "KINDS", []):
        if not by.get(k):
            note("WARN", "dataset", f"no page blocks of kind '{k}'", "adapter/ui_index.py")
    pages = {(p["pillar"], p["view"]) for p in M["pages"]}
    stray = {(doc["page"]["pillar"], doc["page"]["view"]) for doc in docs.values() if doc.get("page")} - pages
    if stray:
        note("FAIL", "dataset", f"blocks point at pages product.json does not list: {sorted(stray)}", "adapter/ui_index.py or product.json pages")


# ---------------------------------------------------------------- product source

def check_routes():
    src = read(SC.get("route_file"))
    if src is None:
        note("WARN", "routes", f"route file not found: {SC.get('route_file')}", "product.json source_checks.route_file")
        return
    found = set(re.findall(SC.get("route_view_regex") or r"""["']([a-z][a-z0-9-]+)["']""", src))
    mapped = {p["view"] for p in M["pages"]}
    skipped = set(SC.get("views_not_mapped") or [])
    gone = sorted(v for v in mapped if v not in found)
    if gone:
        note("FAIL", "routes", f"pages in product.json that the route table no longer has: {', '.join(gone)}", "adapter/product.json pages")
    new = sorted(found - mapped - skipped)
    if new and SC.get("route_view_regex"):
        note("WARN", "routes", f"route views with no page in product.json: {', '.join(new)}",
             "adapter/product.json pages (or source_checks.views_not_mapped)")
    if not gone:
        note("OK", "routes", f"all {len(mapped)} pages exist in {SC.get('route_file')}")


def _page_sources():
    base = ROOT / (SC.get("pages_dir") or "")
    if not base.is_dir():
        return ""
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in base.rglob("*.js*")
                     if p.is_file() and "node_modules" not in p.parts and "test" not in p.name)


def check_payloads(src):
    if not src:
        note("WARN", "payloads", f"page sources not found under {SC.get('pages_dir')}", "product.json source_checks.pages_dir")
        return
    missing = []
    for p in M["pages"]:
        for k in p.get("payload") or {}:
            if not re.search(rf"\b{re.escape(k)}\b", src):
                missing.append(f"{p['pillar']}/{p['view']}.{k}")
    if missing:
        note("FAIL", "payloads", "payload keys no page reads any more: " + ", ".join(missing), "adapter/product.json pages[].payload and adapter/navigation.py")
    else:
        note("OK", "payloads", "every page payload key is read in the page code")


def check_app_state():
    src = read(SC.get("app_state_file"))
    a = M["frontend"]["app_state"]
    if src is None:
        note("WARN", "app state", f"not found: {SC.get('app_state_file')}", "product.json source_checks.app_state_file")
        return
    names = [a["navigate_fn"], *a["route_keys"], *(x.split(".")[-1] for x in (a["selection"], a["view_title"], a["report"]))]
    missing = [n for n in names if not re.search(rf"\b{re.escape(n)}\b", src)]
    if missing:
        note("FAIL", "app state", "AppState no longer has: " + ", ".join(missing), "adapter/product.json frontend.app_state")
    else:
        note("OK", "app state", f"{a['navigate_fn']}, route keys and context paths present")
    note("INFO", "app state", "product hook applied" if a["hook_global"] in src else
         "product hook not applied (optional; the bridge reads React internals instead)", "adapter/product-hook/apply.sh")


def _dist_text(dist):
    if not dist or not dist.is_dir():
        return None
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in list(dist.rglob("*.js")) + list(dist.rglob("*.css"))
                     + list(dist.glob("*.html")) if p.is_file())


def check_dom(built):
    dom = M["frontend"]["dom"]
    sels = [v for k, v in dom.items() if isinstance(v, str)] + [s for v in dom.values() if isinstance(v, list) for s in v]
    classes = sorted({c for s in sels for c in re.findall(r"\.([A-Za-z_][\w-]*)", s)})
    missing = [c for c in classes if not re.search(rf"""(["'\s.]){re.escape(c)}(["'\s,{{:>.)])""", built)]
    if missing:
        note("FAIL", "dom", "classes the bridge uses that the product no longer has: " + ", ".join(missing), "adapter/product.json frontend.dom")
    else:
        note("OK", "dom", f"{len(classes)} classes found in the built product")


def check_theme(built):
    th = M["frontend"]["theme"]
    vars_ = sorted({v for t in th["tokens"].values() for v in re.findall(r"var\((--[\w-]+)", t)})
    missing = [v for v in vars_ if v not in built]
    if missing:
        note("WARN", "theme", "product CSS tokens not found (the widget falls back to the stated colours): " + ", ".join(missing),
             "adapter/product.json frontend.theme.tokens")
    else:
        note("OK", "theme", f"{len(vars_)} product tokens present")
    pal = read(SC.get("palette_file"))
    if pal is not None:
        miss = [c for c in th["palette"] if c.lower() not in pal.lower()]
        note("WARN" if miss else "OK", "theme", (f"palette colours not in {SC.get('palette_file')}: {', '.join(miss)}" if miss
             else f"palette matches {SC.get('palette_file')}"), "adapter/product.json frontend.theme.palette")


def check_blocks(built):
    low = built.lower()
    miss = []
    total = 0
    for p in M["pages"]:
        for b in p.get("blocks") or []:
            if b.startswith("<"):
                continue
            total += 1
            if b.lower() not in low and b.lower().replace("&", "&amp;") not in low:
                miss.append(f"{p['view']}: {b}")
    if miss:
        note("WARN", "blocks", f"{len(miss)} of {total} focus headings not found in the built product: " + "; ".join(miss),
             "adapter/product.json pages[].blocks (a heading text built at run time can be fine)")
    else:
        note("OK", "blocks", f"all {total} focus headings found")


def check_widget():
    w = HERE / "service" / "static" / "widget.js"
    if not w.is_file():
        note("FAIL", "widget", "widget not built", "cd widget && npx vite build")
    elif (ADAPTER / "product.json").stat().st_mtime > w.stat().st_mtime:
        note("WARN", "widget", "product.json is newer than the built widget", "cd widget && npx vite build (run-local.sh does it)")
    else:
        note("OK", "widget", f"built {time.strftime('%Y-%m-%d %H:%M', time.localtime(w.stat().st_mtime))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("KSSL_DSN", "host=127.0.0.1 port=5499 dbname=kssl user=postgres"))
    ap.add_argument("--api", default=os.environ.get("PRODUCT_API", "http://127.0.0.1:8600"))
    ap.add_argument("--dist", default=os.environ.get("PRODUCT_DIST") or str(ROOT / SC.get("dist_dir", "dist")))
    a = ap.parse_args()

    check_database(a.dsn)
    check_dataset(a.api)
    check_routes()
    check_payloads(_page_sources())
    check_app_state()
    built = _dist_text(Path(a.dist))
    if built is None:
        note("WARN", "dom", f"built product not found at {a.dist}: dom, theme and block checks skipped", "pass --dist")
    else:
        check_dom(built)
        check_theme(built)
        check_blocks(built)
    check_widget()

    order = {"FAIL": 0, "WARN": 1, "INFO": 2, "SKIP": 3, "OK": 4}
    lines = [f"# Adapter check: {M['product']['name']} ({M['product'].get('version', '')})", "",
             "| | Area | Finding | Where to fix |", "|---|---|---|---|"]
    for s, area, what, fix in sorted(rows, key=lambda r: order[r[0]]):
        lines.append(f"| {s} | {area} | {what.replace('|', '/')} | {fix if s != 'OK' else ''} |")
    fails = sum(r[0] == "FAIL" for r in rows)
    warns = sum(r[0] == "WARN" for r in rows)
    lines += ["", f"{fails} fail, {warns} warn, {sum(r[0] == 'OK' for r in rows)} ok."]
    out = "\n".join(lines)
    print(out)
    (HERE / ".local").mkdir(exist_ok=True)
    (HERE / ".local" / "check_product.md").write_text(out + "\n")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
