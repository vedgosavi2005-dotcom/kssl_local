"""Stock-exchange filings of the listed Indian rivals (BSE) -> staging.source_document (raw layer), free, no model.

    python -m backend.harvest_filings --selftest
    python -m backend.harvest_filings --announcements [--from 2023-01-01] [--to 2026-10-26] [--filer 526247] [--dry-run]
    python -m backend.harvest_filings --annual [--filer 541143] [--dry-run]          (latest annual report per filer)

Owner 2026-10-25: annual reports / investor pages / exchange filings list orders, JVs, subsidiaries, plants and country offices --
exactly what the Movement, Partnerships, Geo footprint and Projects sections of the thin Indian rivals lack. BSE publishes them
through the JSON endpoints its own pages call (api.bseindia.com, the same Referer / Origin a browser sends; no login, no bot wall):
  * announcements (AnnSubCategoryGetData; at most 12 months per query, so the window is walked a year at a time). Only the
    business sub-categories are kept (orders, press releases, JV / MoU / acquisition, investor presentations, earnings-call
    transcripts, management changes, results, open offers, clarifications ...); compliance paperwork (trading window, Reg. 74(5)
    certificates, newspaper copies, record dates ...) is left out. The attached PDF is read once (PyMuPDF, in memory, never
    saved or executed) and its text is the body (capped);
  * the latest annual report (AnnualReport_New): the overview pages plus every page that speaks of subsidiaries, joint ventures,
    associates, collaborations, exports, order book, plants and countries (capped) -- a 300-page report is mostly accounts.
For a parent company that is not itself the defence rival (Mahindra & Mahindra -> Mahindra Defence, Adani Enterprises -> Adani
Defence, and Larsen & Toubro whose filings are mostly infrastructure) a filing is kept only when its text speaks of defence.
Rows: source_kind 'filing' / 'annual_report', tier 'primary', competitor_ids = the rival, status 'attributed' with
triage.attrib {competitor: 'own site'} (a company's own disclosure). INSERT .. ON CONFLICT (url) DO NOTHING, so a re-run resumes.
Local kssl_staging only. Stdlib + psycopg2 + PyMuPDF (fitz, already installed; pypdf as a fallback).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import date, timedelta

from backend import news

HARVESTER = "harvest_filings v1"
API = "https://api.bseindia.com/BseIndiaAPI/api"
HEADERS = {"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com", "Accept": "application/json, text/plain, */*"}
ATTACH = ("https://www.bseindia.com/xml-data/corpfiling/AttachLive/{}", "https://www.bseindia.com/xml-data/corpfiling/AttachHis/{}")
BODY_CAP = 60_000
ANNUAL_CAP = 150_000
PDF_MAX = 80_000_000

# scrip code -> (competitor display name, filer name, parent: keep only defence filings)
FILERS = {
    "541143": ("Bharat Dynamics Ltd (BDL)", "Bharat Dynamics Limited", False),
    "532725": ("Solar Industries", "Solar Industries India Limited", False),
    "526247": ("Premier Explosives", "Premier Explosives Limited", False),
    "500510": ("Larsen & Toubro", "Larsen & Toubro Limited", True),
    "500520": ("Mahindra Defence", "Mahindra & Mahindra Limited (parent of Mahindra Defence Systems)", True),
    "512599": ("Adani Defence & Aerospace", "Adani Enterprises Limited (parent of Adani Defence & Aerospace)", True),
}
KEEP_SUBCAT = re.compile(r"order|press release|media release|joint venture|\bjv\b|agreement|mou|acquisition|amalgamation|merger|"
                         r"investor presentation|earnings call transcript|change in management|appointment|resignation of (md|ceo|managing)|"
                         r"financial results|open offer|clarification|general|allotment|incorporation|subsidiary|scheme of arrangement|"
                         r"collaboration|cessation|diversification|capacity|plant|new project|business expansion", re.I)
DROP_SUBCAT = re.compile(r"trading window|reg\. 74|newspaper|record date|book closure|board meeting intimation|agm|egm|postal ballot|"
                         r"scrutinizer|loss of share|duplicate share|certificate|compliance|investor complaint|analyst / investor meet - intimation|"
                         r"audio|credit rating|dividend|sast|insider|esop|shareholding|cessation of independent", re.I)
DEFENCE = re.compile(r"\b(defen[cs]e|military|army|navy|naval|air force|missile|ammunition|munition|explosive|artillery|armou?red|"
                     r"weapon|drdo|ministry of defence|mod\b|warship|submarine|radar|uav|drone|aerospace|precision engineering)\b", re.I)
ANNUAL_PAGE = re.compile(r"subsidiar|joint venture|associate compan|collaborat|memorandum of understanding|\bmou\b|technology transfer|"
                         r"licen[cs]e agreement|export|order book|order inflow|orders? (worth|valued|received)|plant|facility|"
                         r"manufacturing (unit|site)|overseas|countries|international business|step-down", re.I)


# ----------------------------------------------------------------------------------------------- pure helpers
def year_windows(start: date, end: date) -> list[tuple[date, date]]:
    """[start, end] in windows of at most 12 months (the BSE limit), newest first."""
    out, e = [], end
    while e >= start:
        s = max(start, date(e.year - 1, e.month, e.day) + timedelta(days=1) if not (e.month == 2 and e.day == 29) else date(e.year - 1, 3, 1))
        out.append((s, e))
        e = s - timedelta(days=1)
    return out


def keep_announcement(a: dict) -> bool:
    sub = f"{a.get('SUBCATNAME') or ''} | {a.get('CATEGORYNAME') or ''}"
    if DROP_SUBCAT.search(sub):
        return False
    return bool(KEEP_SUBCAT.search(sub) or a.get("CATEGORYNAME", "").strip() in ("Result",))


def is_defence(text: str) -> bool:
    return bool(DEFENCE.search(text or ""))


def annual_digest(pages: list[str], cap: int = ANNUAL_CAP, parent: bool = False) -> tuple[str, int]:
    """The overview (first 4 pages) + the pages ANNUAL_PAGE picks (and, for a parent, that also speak of defence)."""
    keep, n = [], 0
    for i, t in enumerate(pages):
        t = (t or "").strip()
        if not t:
            continue
        if i < 4 or (ANNUAL_PAGE.search(t) and (not parent or is_defence(t))):
            keep.append(f"[page {i + 1}]\n{t}")
            n += 1
    out = "\n\n".join(keep)
    return out[:cap], n


def pdf_text_pages(data: bytes) -> list[str]:
    """Text per page, parsed in memory (the PDF is never written to disk or executed)."""
    try:
        import fitz
        with fitz.open(stream=data, filetype="pdf") as doc:
            return [p.get_text("text") for p in doc]
    except ImportError:
        import io
        from pypdf import PdfReader
        return [(p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages]


def clean_text(s: str) -> str:
    s = (s or "").replace("\x00", "")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def doc_id(url: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))


# ----------------------------------------------------------------------------------------------- network
def get_json(url: str):
    with news.GATE("api.bseindia.com"):
        r = news.http(url, headers=HEADERS, timeout=40)
    time.sleep(0.8)
    if r.status != 200:
        raise RuntimeError(f"http {r.status} for {url}")
    return json.loads(r.body)


def get_pdf(name_or_url: str) -> tuple[bytes | None, str, str]:
    urls = [name_or_url] if name_or_url.startswith("http") else [u.format(name_or_url) for u in ATTACH]
    note = ""
    for u in urls:
        with news.GATE("www.bseindia.com"):
            r = news.http(u, headers={"Referer": "https://www.bseindia.com/"}, timeout=90, max_bytes=PDF_MAX)
        time.sleep(0.8)
        if r.status == 200 and r.body[:5] == b"%PDF-":
            return r.body, u, ""
        note = f"http {r.status}" + ("" if r.status != 200 else " (not a PDF)")
    return None, urls[0], note


def announcements(scrip: str, start: date, end: date) -> list[dict]:
    out = []
    for a, b in year_windows(start, end):
        for page in range(1, 60):
            d = get_json(f"{API}/AnnSubCategoryGetData/w?pageno={page}&strCat=-1&strPrevDate={a:%Y%m%d}&strScrip={scrip}"
                         f"&strSearch=P&strToDate={b:%Y%m%d}&strType=C&subcategory=-1")
            t = d.get("Table") or []
            out += t
            if len(t) < 50:
                break
    return out


# ----------------------------------------------------------------------------------------------- DB
def connect():
    import psycopg2
    return psycopg2.connect(os.environ.get("KSSL_STAGING_DSN") or "postgresql://kssl:kssl@127.0.0.1:55432/kssl_staging")


def competitor_ids(cur) -> dict[str, str]:
    cur.execute("SELECT display_name, competitor_id::text FROM staging.competitive_competitor")
    return dict(cur.fetchall())


def insert(cur, url, kind, source_name, title, published, body, cid, triage) -> bool:
    cur.execute("INSERT INTO staging.source_document (doc_id, url, source_kind, source_name, source_tier, feed_url, title, published_at,"
                " language, body_text, triage, competitor_ids, status) VALUES (%s,%s,%s,%s,'primary',%s,%s,%s,'en',%s,%s::jsonb,%s::uuid[],"
                "'attributed') ON CONFLICT (url) DO NOTHING",
                (doc_id(url), url, kind, source_name, "bse:" + kind, (title or "")[:1000], published, body or None,
                 json.dumps({**triage, "harvester": HARVESTER, "attrib": {cid: "own site"}}), [cid]))
    return bool(cur.rowcount)


def run_announcements(filers, start, end, dry_run=False, log=print) -> dict:
    conn = connect()
    cur = conn.cursor()
    cids = competitor_ids(cur)
    cur.execute("SELECT url FROM staging.source_document WHERE source_kind = 'filing'")
    known = {r[0] for r in cur.fetchall()}
    stats = {}
    for scrip in filers:
        comp, filer, parent = FILERS[scrip]
        st = {"listed": 0, "kept_subcat": 0, "not_defence": 0, "stored": 0, "known": 0, "no_pdf": 0}
        rows = announcements(scrip, start, end)
        st["listed"] = len(rows)
        for a in rows:
            if not keep_announcement(a):
                continue
            st["kept_subcat"] += 1
            name = (a.get("ATTACHMENTNAME") or "").strip()
            head = clean_text(f"{a.get('NEWSSUB') or ''}\n{a.get('HEADLINE') or ''}\n{a.get('MORE') or ''}")
            if not name:
                continue
            if any(u.format(name) in known for u in ATTACH):
                st["known"] += 1
                continue
            data, url, note = get_pdf(name)
            text = ""
            if data:
                try:
                    text = clean_text("\n".join(pdf_text_pages(data)))
                except Exception as e:                    # a broken PDF: the headline is still a lead
                    note = f"pdf parse: {type(e).__name__}"
            else:
                st["no_pdf"] += 1
            body = (head + "\n\n" + text)[:BODY_CAP]
            if parent and not is_defence(body):
                st["not_defence"] += 1
                continue
            day = (a.get("NEWS_DT") or "")[:10] or None
            title = f"{filer.split(' (')[0]}: {a.get('NEWSSUB') or a.get('HEADLINE') or 'BSE filing'}"
            tri = {"bse": {"scrip": scrip, "newsid": a.get("NEWSID"), "category": a.get("CATEGORYNAME"), "subcategory": a.get("SUBCATNAME"),
                           "pdf_note": note or None, "pdf_chars": len(text)}}
            if not dry_run:
                st["stored"] += insert(cur, url, "filing", f"BSE: {filer.split(' (')[0]}", title, day, body, cids[comp], tri)
                conn.commit()
            else:
                st["stored"] += 1
            known.add(url)
        stats[comp] = st
        log(f"  {comp:28} {st}", flush=True)
    conn.close()
    return stats


def run_annual(filers, dry_run=False, log=print) -> dict:
    conn = connect()
    cur = conn.cursor()
    cids = competitor_ids(cur)
    stats = {}
    for scrip in filers:
        comp, filer, parent = FILERS[scrip]
        rows = (get_json(f"{API}/AnnualReport_New/w?scripcode={scrip}") or {}).get("Table") or []
        rows.sort(key=lambda r: (str(r.get("Year")), str(r.get("Fld_AuthoriseDate"))), reverse=True)
        if not rows:
            stats[comp] = "no annual report listed"
            continue
        r = rows[0]
        cur.execute("SELECT 1 FROM staging.source_document WHERE url = %s", (r["PDFDownload"],))
        if cur.fetchone():
            stats[comp] = {"year": r.get("Year"), "stored": 0, "note": "latest report already stored"}
            log(f"  {comp:28} {stats[comp]}")
            continue
        data, url, note = get_pdf(r["PDFDownload"])
        if not data:
            stats[comp] = f"pdf not fetched ({note})"
            log(f"  {comp:28} {stats[comp]}")
            continue
        pages = pdf_text_pages(data)
        body, n = annual_digest([clean_text(p) for p in pages], parent=parent)
        title = f"{filer.split(' (')[0]}: Annual Report {r.get('Year')} (BSE filing)"
        day = (r.get("Fld_AuthoriseDate") or "")[:10] or None
        tri = {"bse": {"scrip": scrip, "year": r.get("Year"), "pages": len(pages), "pages_kept": n, "pdf_bytes": len(data)}}
        stored = 1 if dry_run else insert(cur, url, "annual_report", f"BSE: {filer.split(' (')[0]}", title, day, body, cids[comp], tri)
        conn.commit()
        stats[comp] = {"year": r.get("Year"), "pages": len(pages), "pages_kept": n, "chars": len(body), "stored": int(stored)}
        log(f"  {comp:28} {stats[comp]}", flush=True)
    conn.close()
    return stats


# ----------------------------------------------------------------------------------------------- selftest
def _selftest() -> None:
    w = year_windows(date(2023, 1, 1), date(2026, 10, 26))
    assert w[0] == (date(2025, 10, 27), date(2026, 10, 26)) and w[-1][0] == date(2023, 1, 1) and len(w) == 4
    assert all((b - a).days <= 365 for a, b in w) and all(w[i][0] - timedelta(days=1) == w[i + 1][1] for i in range(len(w) - 1))
    assert keep_announcement({"SUBCATNAME": "Award of Order / Receipt of Order", "CATEGORYNAME": "Company Update"})
    assert keep_announcement({"SUBCATNAME": "Earnings Call Transcript", "CATEGORYNAME": "Company Update"})
    assert not keep_announcement({"SUBCATNAME": "Closure of Trading Window", "CATEGORYNAME": "Insider Trading / SAST"})
    assert not keep_announcement({"SUBCATNAME": "Newspaper Publication", "CATEGORYNAME": "Company Update"})
    assert not keep_announcement({"SUBCATNAME": "Certificate under Reg. 74 (5) of SEBI (DP) Regulations, 2018", "CATEGORYNAME": "Company Update"})
    assert keep_announcement({"SUBCATNAME": "Financial Results", "CATEGORYNAME": "Result"})
    assert is_defence("order from the Ministry of Defence for 155 mm shells") and not is_defence("tractor sales rose 9%")
    pages = ["Cover", "Chairman", "Highlights", "Board", "Profit and loss", "Our subsidiaries: Acme Defence Pvt Ltd (Joint Venture)",
             "Notes", "Export orders from 12 countries"]
    body, n = annual_digest(pages)
    assert n == 6 and "[page 6]" in body and "[page 8]" in body and "[page 5]" not in body
    body, n = annual_digest(pages + ["New tractor plant in Pune"], parent=True)
    assert "[page 9]" not in body                                        # a parent's non-defence page is left out
    assert clean_text("a\x00b  \t c\n\n\n\nd") == "ab c\n\nd"
    assert set(FILERS) == {"541143", "532725", "526247", "500510", "500520", "512599"}
    print("harvest_filings self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.harvest_filings", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true")
    g.add_argument("--announcements", action="store_true")
    g.add_argument("--annual", action="store_true")
    ap.add_argument("--filer", action="append", help="BSE scrip code (repeatable); default: all in FILERS")
    ap.add_argument("--from", dest="frm", default="2023-01-01")
    ap.add_argument("--to", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
        return 0
    filers = a.filer or list(FILERS)
    if a.announcements:
        print(run_announcements(filers, date.fromisoformat(a.frm), date.fromisoformat(a.to), a.dry_run))
    else:
        print(run_annual(filers, a.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
