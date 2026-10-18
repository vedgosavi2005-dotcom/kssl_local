"""Market pillar roll-ups by code (no model): writes ONLY kssl_staging.

    python -m backend.market_rollups [status] [portals] [awards] [summary] [metrics] [top] [filters] [all]

prune    delete the stub of every notice the tender prompt skipped as not defence hardware (tender_raw.status becomes 'skipped')
status   market_tender.status of open / closing notices from the stored closing_date (open -> closing within 7 days -> closed after it)
portals  market_tender_portal: one row per tender API that has notices in staging.tender_raw (name and url of the API's public site)
awards   market_award: one row per awarded notice (tender status 'awarded' with a stated winner or award value)
summary  market_category_summary: per category x country counts of active tenders, strong fits, disclosed values, portals, opportunities
metrics  market_top_opportunity_metric: totals shown on the Top opportunity page
merge    one procurement = one tender (re-publications / corrigenda merged; backend/harvest_tenders.py)
top      market_top_opportunity_tender / _project / market_next_move: ranking by code from the stored scores (derive.pursue_label)
facts    fact_source rows (the stored document) for global requirement / opportunity columns that lack one
filters  market_filter_option (derive.rebuild_filter_options for the market pillar)

Every number is a count or a stored value; nothing is estimated. KSSL revenue is never computed (no source states it).
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from datetime import date

import psycopg2
import psycopg2.extras

DSN = os.getenv("KSSL_STAGING_DSN") or "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl"
PORTALS = {  # tender API -> (portal name as the harvester stores it, public site, country code of the portal's buyers or None)
    "ted_eu": ("TED (Tenders Electronic Daily)", "https://ted.europa.eu", None),
    "gem_india": ("GeM (Government e-Marketplace)", "https://gem.gov.in", "IN"),
    "canada": ("CanadaBuys", "https://canadabuys.canada.ca", "CA"),
    "uk_fts": ("Find a Tender", "https://www.find-tender.service.gov.uk", "GB"),
    "prozorro_ua": ("Prozorro", "https://prozorro.gov.ua", "UA"),
    "decp_fr": ("DECP (data.economie.gouv.fr)", "https://data.economie.gouv.fr", "FR"),
    "diavgeia_gr": ("Diavgeia", "https://diavgeia.gov.gr", "GR"),
    "sam_us": ("SAM.gov", "https://sam.gov", "US"),
}
TOP_TENDERS, TOP_PROJECTS = 15, 10


def bid(*parts) -> int:
    """Stable positive 63-bit id from text parts."""
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()[:8], "big") >> 1


def connect():
    c = psycopg2.connect(DSN, connect_timeout=5)
    c.cursor_factory = psycopg2.extras.RealDictCursor
    return c


def refresh_status(cur) -> int:
    cur.execute("""UPDATE staging.market_tender SET status = CASE WHEN closing_date < current_date THEN 'closed'
                                                                   WHEN closing_date <= current_date + 7 THEN 'closing' ELSE 'open' END,
                          is_live = (closing_date >= current_date)
                   WHERE status IN ('open', 'closing') AND closing_date IS NOT NULL
                     AND status IS DISTINCT FROM CASE WHEN closing_date < current_date THEN 'closed'
                                                      WHEN closing_date <= current_date + 7 THEN 'closing' ELSE 'open' END""")
    return cur.rowcount


def prune(cur) -> int:
    """A notice the tender prompt skipped (its latest run is 'skipped': not defence hardware or its support) is not a tender for the dashboard:
    its stub market_tender + market_tender_source rows are deleted and the raw notice is marked skipped. Nothing the model extracted is touched."""
    cur.execute("""SELECT s.source_id, s.tender_id FROM staging.market_tender_source s
                   JOIN (SELECT DISTINCT ON (subject_key) subject_key, status FROM staging.prompt_run
                         WHERE prompt_id = 'tender' AND prompt_version = '2' AND status <> 'dry_run' ORDER BY subject_key, started_at DESC) r
                     ON r.subject_key = s.source_id::text AND r.status = 'skipped'
                   JOIN staging.market_tender t ON t.tender_id = s.tender_id AND t.description IS NULL""")
    rows = cur.fetchall()
    for r in rows:
        cur.execute("UPDATE staging.tender_raw SET status = 'skipped' WHERE tender_id = %s", (r["tender_id"],))
        cur.execute("DELETE FROM staging.market_tender_source WHERE tender_id = %s", (r["tender_id"],))
        cur.execute("DELETE FROM staging.market_tender WHERE tender_id = %s", (r["tender_id"],))
    return len(rows)


def portals(cur) -> int:
    cur.execute("SELECT DISTINCT source_api FROM staging.tender_raw")
    n = 0
    for r in cur.fetchall():
        name, url, cc = PORTALS.get(r["source_api"], (r["source_api"], None, None))
        cur.execute("DELETE FROM staging.market_tender_portal WHERE portal_id = %s", (bid("portal", r["source_api"]),))
        # registration_required / submission_method are not in any stored record: left null ("not on record")
        cur.execute("""INSERT INTO staging.market_tender_portal (portal_id, portal_name, portal_url, country_code, access_status)
                       VALUES (%s, %s, %s, %s, %s)""", (bid("portal", r["source_api"]), name, url, cc, "public notices read by API"))
        n += 1
    return n


def awards(cur) -> int:
    from backend.sources import classify
    cur.execute("DELETE FROM staging.market_award WHERE award_id IN (SELECT award_id FROM staging.market_award WHERE source_url IS NOT NULL)")
    # a merged tender has one raw notice per re-publication: read the latest one (one award per tender)
    cur.execute("""SELECT DISTINCT ON (t.tender_id) t.*, r.raw AS raw, r.source_api FROM staging.market_tender t
                   LEFT JOIN staging.tender_raw r ON r.tender_id = t.tender_id
                   WHERE t.status = 'awarded' AND t.description IS NOT NULL
                     AND (coalesce(t.awarded_to, '') <> '' OR coalesce(t.award_value_text, '') <> '')
                   ORDER BY t.tender_id, r.published_at DESC NULLS LAST""")
    n = 0
    for t in cur.fetchall():
        bids = None
        raw = t.get("raw") or {}
        if t.get("source_api") == "decp_fr" and str(raw.get("offresrecues", "")).isdigit():
            bids = int(raw["offresrecues"])
        d = t.get("award_date") or t.get("published_date")   # open decision (red-team 2026-10-18): a notice date stands in for a missing award date
        amount, cur_code = None, None
        m = re.match(r"^\s*([A-Z]{3})\s+([\d,\.]+)", t.get("award_value_text") or "")
        if m:
            cur_code = m.group(1)
            try:
                amount = float(m.group(2).replace(",", ""))
            except ValueError:
                amount = None
        cur.execute("""INSERT INTO staging.market_award (award_id, segment, winner, buyer, country_name, title, title_local, tender_number, award_date,
                           award_year, value_amount, value_currency, value_text, bids, source_url, source_tier)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (bid("award", t["tender_id"]), t.get("category_text"), t.get("awarded_to"), t.get("buyer_name"), t.get("country_name"), t["title"],
                     t.get("title_localized"), t.get("notice_reference"), d, d.year if d else None, amount, cur_code,
                     t.get("award_value_text"), bids, t.get("source_url"), classify(t.get("source_url"), ()) if t.get("source_url") else None))
        n += 1
    return n


def category_summary(cur) -> int:
    cur.execute("DELETE FROM staging.market_category_summary")
    cur.execute("""SELECT t.category_id, t.country_code,
                          count(DISTINCT t.tender_id) FILTER (WHERE t.status IN ('open','closing')) AS active,
                          count(DISTINCT t.tender_id) FILTER (WHERE t.status IN ('open','closing') AND a.fit_grade = 'strong') AS strong,
                          count(DISTINCT t.tender_id) FILTER (WHERE t.status IN ('open','closing') AND (t.value_amount IS NOT NULL OR t.value_text IS NOT NULL)) AS disclosed,
                          count(DISTINCT r.source_api) FILTER (WHERE t.status IN ('open','closing')) AS portals
                   FROM staging.market_tender t
                   LEFT JOIN (SELECT DISTINCT ON (tender_id) tender_id, fit_grade FROM staging.market_tender_fit_assessment
                              ORDER BY tender_id, assessed_at DESC) a ON a.tender_id = t.tender_id
                   LEFT JOIN staging.tender_raw r ON r.tender_id = t.tender_id
                   WHERE t.category_id IS NOT NULL AND t.country_code IS NOT NULL
                   GROUP BY 1, 2""")
    rows = cur.fetchall()
    cur.execute("SELECT category_id, country_code, count(*) AS n FROM staging.market_opportunity WHERE category_id IS NOT NULL GROUP BY 1, 2")
    opp = {(r["category_id"], r["country_code"]): r["n"] for r in cur.fetchall()}
    for r in rows:
        cur.execute("""INSERT INTO staging.market_category_summary (summary_id, category_id, country_code, as_of_date, active_tenders_count,
                           strong_fit_count, value_disclosed_count, source_portals_count, perceived_opportunity_count)
                       VALUES (%s,%s,%s,current_date,%s,%s,%s,%s,%s)""",
                    (bid("catsum", r["category_id"], r["country_code"]), r["category_id"], r["country_code"], r["active"], r["strong"],
                     r["disclosed"], r["portals"], opp.get((r["category_id"], r["country_code"]), 0)))
    return len(rows)


def _compact(amount: float) -> str:
    for div, suf in ((1e9, " bn"), (1e6, " m")):
        if abs(amount) >= div:
            v = amount / div
            return (f"{v:,.2f}" if v < 10 else f"{v:,.1f}") + suf
    return f"{amount:,.0f}"


def _indian(n: float, decimals: int = 0) -> str:
    """Indian digit grouping: 193981 -> '1,93,981' (the browser's toLocaleString('en-IN'))."""
    s = f"{abs(n):.{decimals}f}"
    whole, _, frac = s.partition(".")
    head, tail = whole[:-3], whole[-3:]
    while len(head) > 2:
        tail, head = head[-2:] + "," + tail, head[:-2]
    whole = (head + "," + tail) if head else tail
    return ("-" if n < 0 else "") + whole + (("." + frac.rstrip("0")).rstrip(".") if frac else "")


def rupees(n: float) -> str:
    """House style of src/lib/tenderValue.js rupees(): '₹ 1,93,981 Cr' (no decimal from ₹ 100 Cr), '₹ 12.4 Cr', '₹ 8.5 L'."""
    if n >= 1e7:
        return f"₹ {_indian(round(n / 1e7, 0 if n >= 1e9 else 1), 0 if n >= 1e9 else 1)} Cr"
    if n >= 1e5:
        return f"₹ {_indian(round(n / 1e5, 1), 1)} L"
    return f"₹ {_indian(round(n))}"


def metrics(cur) -> int:
    """The four tiles of the Top opportunity page. Every number is counted or summed from stored rows; tender values are summed per currency
    and converted to rupees only with a stored rate (staging.fx_rate, kssl-40 2026-10-18); a currency without one keeps its own code."""
    from prompts.derive import client_name
    client = client_name(cur)
    cur.execute("DELETE FROM staging.market_top_opportunity_metric")
    live = "t.status IN ('open','closing') AND (t.closing_date IS NULL OR t.closing_date >= current_date)"

    def q(sql):
        cur.execute(sql)
        return cur.fetchone()["n"]

    active = q(f"SELECT count(*) n FROM staging.market_tender t WHERE {live}")
    assessed = q(f"SELECT count(DISTINCT t.tender_id) n FROM staging.market_tender t JOIN staging.market_tender_fit_assessment a USING (tender_id) WHERE {live}")
    strong = q(f"SELECT count(DISTINCT t.tender_id) n FROM staging.market_tender t JOIN staging.market_tender_fit_assessment a USING (tender_id) WHERE {live} AND a.fit_grade = 'strong'")
    partial = q(f"SELECT count(DISTINCT t.tender_id) n FROM staging.market_tender t JOIN staging.market_tender_fit_assessment a USING (tender_id) WHERE {live} AND a.fit_grade = 'partial'")
    cur.execute(f"""SELECT t.value_currency AS cur, sum(t.value_amount) AS total, count(*) AS n FROM staging.market_tender t
                    WHERE {live} AND t.value_amount IS NOT NULL AND t.value_currency IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""")
    vals = cur.fetchall()
    opps = q("SELECT count(*) n FROM staging.market_opportunity")
    cur.execute("SELECT upper(trim(currency_code)) AS c, inr_per_unit AS r, as_of_date FROM staging.fx_rate")
    fx = {r["c"]: r for r in cur.fetchall()}                 # stored rates only (scripts/load_fx_rates.py); no rate -> the currency's own code
    inr = sum(float(v["total"]) * (1.0 if v["cur"].strip().upper() == "INR" else float(fx[v["cur"].strip().upper()]["r"]))
              for v in vals if v["cur"].strip().upper() == "INR" or v["cur"].strip().upper() in fx)
    rest = [v for v in vals if v["cur"].strip().upper() != "INR" and v["cur"].strip().upper() not in fx]
    conv = [v for v in vals if v not in rest]
    shown = " · ".join(([rupees(inr)] if conv else []) + [f"{v['cur'].strip()} {_compact(float(v['total']))}" for v in rest]) if vals else "—"
    asof = max((fx[v["cur"].strip().upper()]["as_of_date"] for v in conv if v["cur"].strip().upper() in fx), default=None)
    n_val = sum(v["n"] for v in vals)
    items = [
        ("latest_tenders", "Latest tenders", f"{active:,}", active, f"{assessed:,} of them assessed for {client} fit; open or closing, deadline not passed", None, None),
        ("strong_fits", "Strong fits", f"{strong:,}", strong, f"{partial:,} more fit in part. A strong fit needs 3 or more checked requirement lines", None, None),
        ("tender_value", "Tender value", shown, round(inr, 2) if conv else None,
         (f"Sum of the values the notices state ({n_val:,} tenders) in rupees" + (f", converted at stored rates as of {asof:%d %b %Y}" if asof else "")
          + (f"; no stored rate for {', '.join(v['cur'].strip() for v in rest)}" if rest else "") if vals else "No active tender states a value"),
         round(inr, 2) if conv else None, "INR" if conv else None),
        ("perceived_opportunities", "Perceived opportunities", f"{opps:,}", opps, "Demand reported before any tender: opportunity cards on record", None, None),
    ]
    for key, label, text, num, note, amount, cc in items:
        cur.execute("""INSERT INTO staging.market_top_opportunity_metric (metric_id, metric_key, metric_label, formatted_value, numeric_value, amount_value, currency_code, as_of_date, note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,current_date,%s)""", (bid("metric", key), key, label, text, num, amount, cc, note))
    return len(items)


MOVE_WORDS = [("register", re.compile(r"regist|enrol|portal|vendor", re.I)), ("find_partner", re.compile(r"local (content|partner|agent|assembly|presence)|partner|domestic", re.I)),
              ("request_documents", re.compile(r"document|annex|drawing|specification", re.I)), ("clarify", re.compile(r"clarif|question", re.I))]


def next_move_for(t: dict, elig: list, portal: str | None, client: str) -> tuple:
    """(kind, text, due) from the tender's own stored fields: the first not_met / unknown eligibility item decides the kind."""
    due = t["closing_date"]
    when = f" before {due:%d %b %Y}" if due else ""
    for e in elig:
        if e["state"] in ("not_met", "unknown"):
            for kind, rx in MOVE_WORDS:
                if rx.search(e["item"] or ""):
                    verb = {"register": f"Register on {portal or 'the tender portal'}", "find_partner": f"Line up a local partner or agent for: {e['item']}",
                            "request_documents": f"Request the documents for: {e['item']}", "clarify": f"Ask the buyer to clarify: {e['item']}"}[kind]
                    return kind, f"{verb}{when}.", due
            return "confirm_eligibility", f"Confirm {client} can meet: {e['item']}{when}.", due
    if due:
        return "prepare_bid", f"Prepare the bid for {tidy_title(t['title'])}{when}.", due
    return "monitor", f"Watch {tidy_title(t['title'])} for a closing date.", None


def tidy_title(title, limit: int = 70) -> str:
    """A tender title fit to sit inside a sentence: spaces collapsed, leading / trailing punctuation dropped, cut at a word."""
    s = re.sub(r"\s+", " ", str(title or "")).strip()
    s = re.sub(r"^\.\s+(?=\d)", ".", s)                  # ". 22 RIM FIRE" -> ".22 RIM FIRE" (a calibre, keep its dot)
    s = re.sub(r"^[\s,;:/-]+|^\.(?!\d)\s*", "", s).rstrip(" .,;:-/")
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(" .,;:-/")
        while re.search(r"\s(of|for|to|and|or|the|with|in|on|at|by|a|an|de|du|des|la|le|et)$", s, re.I):   # never end on a function word
            s = s.rsplit(" ", 1)[0].rstrip(" .,;:-/")
    return s


LIVE = "t.status IN ('open','closing') AND (t.closing_date IS NULL OR t.closing_date >= current_date)"
TOP_ORDER = """CASE a.fit_grade WHEN 'strong' THEN 0 ELSE 1 END, CASE a.pursue_label WHEN 'pursue' THEN 0 WHEN 'position' THEN 1 WHEN 'monitor' THEN 2 ELSE 3 END,
               a.attractiveness DESC NULLS LAST, a.ability DESC NULLS LAST, a.fit_score DESC NULLS LAST, t.closing_date NULLS LAST, t.tender_id"""


def top_candidates(cur) -> list:
    """The ranking, by code: strong before partial, then pursue label, attractiveness, ability, fit score, soonest closing."""
    cur.execute(f"""SELECT t.*, a.pursue_label, a.attractiveness, a.ability, a.fit_grade, a.fit_score, a.time_to_award FROM staging.market_tender t
                    JOIN (SELECT DISTINCT ON (tender_id) * FROM staging.market_tender_fit_assessment ORDER BY tender_id, assessed_at DESC) a ON a.tender_id = t.tender_id
                    WHERE {LIVE} AND a.fit_grade IN ('strong','partial') ORDER BY {TOP_ORDER} LIMIT %s""", (TOP_TENDERS,))
    return cur.fetchall()


def project_candidates(cur) -> list:
    cur.execute("""SELECT o.*, f.fit_grade, f.client_model_display, f.rival_name, f.rival_product_display FROM staging.market_opportunity o
                   JOIN (SELECT DISTINCT ON (opportunity_id) * FROM staging.market_opportunity_fit_assessment ORDER BY opportunity_id, assessed_at DESC) f
                     ON f.opportunity_id = o.opportunity_id
                   WHERE f.fit_grade IN ('strong','partial') AND coalesce(o.stage, '') NOT IN ('cancelled', 'delivered')
                   ORDER BY CASE f.fit_grade WHEN 'strong' THEN 0 ELSE 1 END, o.as_of_date DESC NULLS LAST, o.opportunity_id LIMIT %s""", (TOP_PROJECTS,))
    return cur.fetchall()


def decides_default(t: dict, elig: list):
    """Closing date, then the one condition that decides eligibility (first not_met item, else first unknown), from stored rows only."""
    bits = []
    if t.get("closing_date"):
        bits.append(f"Closes {t['closing_date']:%d %b %Y}")
    bad = next((e for e in elig if e["state"] == "not_met"), None) or next((e for e in elig if e["state"] == "unknown"), None)
    if bad:
        bits.append(f"{bad['item']} decides eligibility" if bad["state"] == "not_met" else f"{bad['item']} is not confirmed")
    return ("; ".join(bits) + ".")[:160] if bits else None


def revenue_text_for(t: dict):
    """Only a value the notice states (copied as written); KSSL revenue is on no source."""
    return f"Stated tender value {t['value_text']}" if t.get("value_text") else None


def write_top(cur, keep_text: bool = False) -> dict:
    """Write market_top_opportunity_tender, _project and market_next_move from the ranking. keep_text=True keeps the model's `decides`,
    `rival_to_beat` and `where_it_stands` on rows the prompt wrote; everything else (rank, fit, model, status, revenue text) comes from stored rows."""
    from prompts.derive import client_name
    client = client_name(cur)
    old_t, old_p = {}, {}
    if keep_text:
        cur.execute("SELECT * FROM staging.market_top_opportunity_tender")
        old_t = {r["tender_id"]: r for r in cur.fetchall()}
        cur.execute("SELECT * FROM staging.market_top_opportunity_project")
        old_p = {r["opportunity_id"]: r for r in cur.fetchall()}
    for tb in ("market_top_opportunity_tender", "market_top_opportunity_project", "market_next_move"):
        cur.execute(f"DELETE FROM staging.{tb}")
    tops = top_candidates(cur)
    for i, t in enumerate(tops, 1):
        cur.execute("SELECT competitor_name, competitor_product_display FROM staging.market_tender_competitor_fit WHERE tender_id = %s "
                    "ORDER BY rank_position NULLS LAST LIMIT 1", (t["tender_id"],))
        rv = cur.fetchone()
        cur.execute("SELECT item, state, fixable, note, quote FROM staging.market_tender_eligibility WHERE tender_id = %s ORDER BY display_order", (t["tender_id"],))
        elig = cur.fetchall()
        prev = old_t.get(t["tender_id"]) or {}
        rival = f"{rv['competitor_name']} {rv['competitor_product_display'] or ''}".strip() if rv else None
        cur.execute("""INSERT INTO staging.market_top_opportunity_tender (top_opportunity_tender_id, tender_id, rank_position, kssl_fit, kssl_model,
                           rival_to_beat, decides, revenue_text, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (prev.get("top_opportunity_tender_id") or bid("toptender", t["tender_id"]), t["tender_id"], i, t["fit_grade"], t["kssl_model"], rival or prev.get("rival_to_beat"),
                     (prev.get("decides") or decides_default(t, elig) or "")[:160] or None, revenue_text_for(t), t["status"]))
        cur.execute("SELECT portal_name FROM staging.market_tender_source WHERE tender_id = %s AND is_primary LIMIT 1", (t["tender_id"],))
        p = cur.fetchone()
        kind, text, due = next_move_for(t, elig, p["portal_name"] if p else None, client)
        days = (due - date.today()).days if due else None
        cur.execute("""INSERT INTO staging.market_next_move (next_move_id, tender_id, sequence, action_text, due_date, due_text, priority, status, tender_title, move_kind)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'open',%s,%s)""",
                    (bid("move", t["tender_id"]), t["tender_id"], i, text, due, f"{due:%d %b %Y}" if due else "No closing date stated",
                     None if days is None else ("high" if days <= 14 else "medium" if days <= 45 else "low"), t["title"][:240], kind))
    projs = project_candidates(cur)
    for i, o in enumerate(projs, 1):
        prev = old_p.get(o["opportunity_id"]) or {}
        cur.execute("SELECT country_name FROM staging.country_reference WHERE iso2 = %s", (o["country_code"],))
        c = cur.fetchone()
        cur.execute("""INSERT INTO staging.market_top_opportunity_project (top_opportunity_project_id, opportunity_id, rank_position, buyer_name, country_name, kssl_fit,
                           kssl_model, rival_to_beat, where_it_stands) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (prev.get("top_opportunity_project_id") or bid("topproj", o["opportunity_id"]), o["opportunity_id"], i, o["buyer_name"], c["country_name"] if c else None, o["fit_grade"], o["client_model_display"],
                     " ".join(x for x in (o["rival_name"], o["rival_product_display"]) if x) or prev.get("rival_to_beat"),
                     prev.get("where_it_stands") or " / ".join(x for x in (o["stage"], o["current_status"], o["latest_milestone"]) if x) or None))
    return {"tenders": len(tops), "projects": len(projs)}


def top_lists(cur) -> dict:
    r = write_top(cur, keep_text=False)
    metrics(cur)
    return r


def facts(cur) -> int:
    """Backfill: every fact column of a global requirement / opportunity (and its spec, rival and update rows) without a fact_source row gets one
    naming the document that row cites as its source (derive.doc_source_facts does the same at load time). Not a quotation."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.sources import classify
    from prompts.derive import DOC_FACT_COLS
    parents = {"market_global_requirement": ("market_global_requirement", "requirement_id", "market_global_requirement_source", "requirement_id", "source_url"),
               "market_global_requirement_specification": ("market_global_requirement", "requirement_id", "market_global_requirement_source", "requirement_id", "source_url"),
               "market_global_requirement_rival": ("market_global_requirement", "requirement_id", "market_global_requirement_source", "requirement_id", "source_url"),
               "market_opportunity": ("market_opportunity", "opportunity_id", "market_opportunity_source", "opportunity_id", "source_url"),
               "market_opportunity_update": ("market_opportunity", "opportunity_id", "market_opportunity_source", "opportunity_id", "source_url")}
    n = 0
    for table, (keycol, cols) in DOC_FACT_COLS.items():
        _, fk, srctable, srcfk, urlcol = parents[table]
        cur.execute(f"SELECT t.*, (SELECT s.{urlcol} FROM staging.{srctable} s WHERE s.{srcfk} = t.{fk} LIMIT 1) AS _url FROM staging.{table} t")
        for r in cur.fetchall():
            if not r["_url"]:
                continue
            cur.execute("SELECT column_name FROM staging.fact_source WHERE table_name = %s AND row_id = %s", (table, str(r[keycol])))
            have = {x["column_name"] for x in cur.fetchall()}
            for col in cols:
                if r.get(col) not in (None, "") and col not in have:
                    cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at) VALUES (%s,%s,%s,%s,%s,%s,now())",
                                (table, str(r[keycol]), col, r["_url"], classify(r["_url"], ()) or "unlisted", "stated in the stored text of this document"))
                    n += 1
    return n


def filters(cur) -> dict:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from prompts import derive
    return derive.rebuild_filter_options(cur, pillars=("market",))


def merge(cur) -> dict:
    """One procurement = one tender: re-publications / corrigenda the harvester could not key at stub time (award notices with no
    deadline) are merged once extracted (backend/harvest_tenders.merge_duplicate_tenders; different winners are never merged)."""
    from backend.harvest_tenders import merge_duplicate_tenders
    o = merge_duplicate_tenders(cur)
    return {k: o[k] for k in ("groups", "merged_tenders", "skipped_winner_conflict")}


STEPS = {"merge": merge, "prune": prune, "status": refresh_status, "portals": portals, "awards": awards, "summary": category_summary, "metrics": metrics, "top": top_lists, "facts": facts, "filters": filters}


def _selftest() -> None:
    assert tidy_title(". 22 RIM FIRE  AMMO ") == ".22 RIM FIRE AMMO" and tidy_title("- Supply of trucks;") == "Supply of trucks"
    assert tidy_title("UPGRADATION OF 5.56MM TAVOR ASSAULT RIFLE FOR PARA SF BATTALIONS OF NORTHERN COMMAND") == "UPGRADATION OF 5.56MM TAVOR ASSAULT RIFLE FOR PARA SF BATTALIONS"
    assert tidy_title(".Supply") == "Supply" and len(tidy_title("word " * 30)) <= 70 and not tidy_title("word " * 30).endswith(" ")
    assert _indian(193981) == "1,93,981" and _indian(1234567.5, 1) == "12,34,567.5" and _indian(999) == "999"
    assert rupees(1.93981e12) == "₹ 1,93,981 Cr" and rupees(1.24e8) == "₹ 12.4 Cr" and rupees(8.5e5) == "₹ 8.5 L"
    print("market_rollups self-check ok")


def main(argv=None) -> int:
    if "--selftest" in (argv or sys.argv[1:]):
        _selftest()
        return 0
    names = [a for a in (argv or sys.argv[1:]) if not a.startswith("-")] or ["all"]
    if "all" in names:
        names = list(STEPS)
    conn = connect()
    try:
        with conn.cursor() as cur:
            for n in names:
                r = STEPS[n](cur)
                print(f"{n}: {r}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
