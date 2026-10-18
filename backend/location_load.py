"""Competitor locations from the research workbook -> staging.competitive_competitor_location (+ fact_source).  kssl_staging only.

    python -m backend.location_load --file "<Defence_Competitor_MASTER_DATASET_50_Companies_AUDITED_FINAL.xlsx>" [--dry-run]
    python -m backend.location_load --selftest

Sheet 'COMPANY DIRECTORY', one row per company.  Columns used: Company, 'Global Locations', 'Facilities & Operating Units', Sources.
  - one row per facility bullet: location_name = the text before ' - ' / ' - ' (the site or unit name as the sheet writes it),
    location_type 'facility'; the capability notes ('Core capabilities ...') are not sites and are skipped;
  - one row for the 'Global Locations' cell, verbatim (location_type 'footprint'), when it fits the 250-character column;
  - country stays NULL: the sheet gives no country per site and none is inferred.
The sheet's Sources URLs of the company (at most 3, blocked ones dropped) become staging.fact_source rows of every location row.
The "Global locations" chips are hidden in the UI (user decision); the rows are held for the day they are shown.
Idempotent: the location rows of the competitors in the sheet are deleted and re-inserted in ONE transaction (ids are uuid5).
The workbook is client-side data and the repository is public: it is never copied into the repo.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path

from backend.excel_load import EXISTING_COMPETITORS, norm_text, split_bullets
from backend.sources import classify, is_blocked

SHEET = "COMPANY DIRECTORY"
MAX_URLS = 3
SPLIT = re.compile(r"\s+[—–-]\s+")          # em dash, en dash or spaced hyphen between a site and its note


def location_id(competitor_id, kind: str, name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"kssl-competitor-location|{competitor_id}|{kind}|{norm_text(name)}")


def facility_name(bullet: str) -> str | None:
    """The site/unit name of a facility bullet; None for a note that is not a site."""
    if re.match(r"(core |key )?capabilit", bullet, re.I):
        return None
    name = SPLIT.split(bullet, maxsplit=1)[0].strip()
    return name[:250] if name else None


def rows_for(company: str, gl, fac, sources) -> list[dict]:
    out, seen = [], set()
    for b in split_bullets(fac):
        n = facility_name(b)
        if n and norm_text(n) not in seen:
            seen.add(norm_text(n))
            out.append({"kind": "facility", "name": n})
    g = re.sub(r"\s+", " ", str(gl or "")).strip()
    if g and len(g) <= 250:
        out.append({"kind": "footprint", "name": g})
    return out


def urls_of(cell) -> list[str]:
    urls = [u.strip() for u in re.split(r"[\s]+", str(cell or "")) if u.strip().startswith(("http://", "https://"))]
    return [u for u in dict.fromkeys(urls) if not is_blocked(u)][:MAX_URLS]


def load(path: str, dry: bool) -> int:
    import openpyxl
    from prompts import batch, run

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(wb[SHEET].iter_rows(values_only=True))
    h = {str(c).strip(): i for i, c in enumerate(rows[0]) if c}
    for need in ("Company", "Global Locations", "Facilities & Operating Units", "Sources"):
        if need not in h:
            print(f"column '{need}' not in the sheet", file=sys.stderr)
            return 2
    conn = batch.connect_db("local")
    cur = conn.cursor()
    cur.execute("SELECT competitor_id, display_name FROM staging.competitive_competitor")
    comps = {norm_text(r["display_name"]): r for r in cur.fetchall()}
    n_rows, n_facts, missing = 0, 0, []
    for r in rows[1:]:
        name = str(r[h["Company"]] or "").strip()
        if not name:
            continue
        c = comps.get(norm_text(EXISTING_COMPETITORS.get(name, name)))
        if c is None:
            missing.append(name)
            continue
        cid = c["competitor_id"]
        locs = rows_for(name, r[h["Global Locations"]], r[h["Facilities & Operating Units"]], r[h["Sources"]])
        urls = urls_of(r[h["Sources"]])
        cur.execute("SELECT location_id FROM staging.competitive_competitor_location WHERE competitor_id = %s", (str(cid),))
        old = [str(x["location_id"]) for x in cur.fetchall()]
        if old:
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_competitor_location' AND row_id = ANY(%s)", (old,))
            cur.execute("DELETE FROM staging.competitive_competitor_location WHERE competitor_id = %s", (str(cid),))
        for L in locs:
            lid = location_id(cid, L["kind"], L["name"])
            cur.execute("INSERT INTO staging.competitive_competitor_location (location_id, competitor_id, location_name, location_type, country, source_url) "
                        "VALUES (%s,%s,%s,%s,NULL,%s)", (str(lid), str(cid), L["name"], L["kind"], urls[0] if urls else None))
            n_rows += cur.rowcount
            for u in urls:
                cur.execute("INSERT INTO staging.fact_source (table_name,row_id,column_name,source_url,source_tier,publisher,quote,retrieved_at) "
                            "VALUES ('competitive_competitor_location',%s,'location_name',%s,%s,%s,%s,now())",
                            (str(lid), u, classify(u, ()) or "unlisted", re.sub(r"^www\.", "", u.split("/")[2]), None))
                n_facts += 1
    print(f"locations written: {n_rows}; fact_source rows: {n_facts}; companies not matched: {missing}")
    if dry:
        conn.rollback()
        print("dry run: rolled back")
    else:
        conn.commit()
    conn.close()
    return 0


def _selftest() -> None:
    assert facility_name("Munich — headquarters / core land-systems activities") == "Munich"
    assert facility_name("Rifle Factory Ishapore (RFI)") == "Rifle Factory Ishapore (RFI)"
    assert facility_name("Core capabilities include gun manufacturing") is None
    assert rows_for("X", "Fictionland; 3 sites", "• Alpha Works — shells\n• Alpha Works — again\n• Key capabilities: forging", None) == [
        {"kind": "facility", "name": "Alpha Works"}, {"kind": "footprint", "name": "Fictionland; 3 sites"}]
    assert urls_of("https://example.com/a\nhttps://example.com/a\nnot a url") == ["https://example.com/a"]
    assert location_id("c1", "facility", "Alpha  Works") == location_id("c1", "facility", "alpha works")
    print("location_load selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    elif a.file:
        sys.exit(load(a.file, a.dry_run))
    else:
        ap.error("give --file or --selftest")
