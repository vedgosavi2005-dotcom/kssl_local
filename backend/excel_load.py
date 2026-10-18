"""Excel -> kssl_staging loader for client-supplied workbooks (competitors + leadership).  Never touches kssl_serving.

    python -m backend.excel_load company --file "<competitor company list.xlsx>" [--db local|vps] [--dry-run] [--reports DIR]
    python -m backend.excel_load leadership --file "<Company Directors Details - Re-verified.xlsx>" [--db local|vps] [--dry-run]
                                            [--compare "<leadership profile.xlsx>"] [--reports DIR]
    python -m backend.excel_load products --file "<Product Specs.xlsx>" [--db local|vps] [--dry-run] [--reports DIR]
    python -m backend.excel_load client-products --file "<KSSL Product Portfolio.xlsx>" [--db local|vps] [--dry-run] [--reports DIR]
    python -m backend.excel_load --selftest                       (no database, no files)

leadership: one competitor per company (inserted if missing, an existing row is never changed), one competitive_leader
per person, one competitive_leader_record per verified bullet, and the matching staging.fact_source rows.  The workbook
is the source of truth for leadership: the leaders / records / fact_source rows of the competitors in the file are
deleted and re-inserted in ONE transaction (idempotent).  Competitors are never deleted.

company: sheet 'COMPANY DIRECTORY', one row per competitor.  Sets (overwrite) origin_country, headquarters, industry_sector, the
text columns starting_year_text / employee_count_text / revenue_text / financial_year (the cell text, verbatim) and, ONLY when the
text states a plain figure with no qualifier, the number columns starting_year / employee_count / annual_revenue + revenue_currency
(else NULL).  One staging.fact_source row per Sources URL per column set (replaced on re-run).  CEO / Chairman / Board are not
stored: they are cross-checked against competitive_leader into <reports>/company_leadership_crosscheck.csv.  Summary:
<reports>/company_details_summary.txt.

Nothing unverified is loaded (leadership).  A role is loaded when the FINAL Position status is Verified / Verified (pass 2).  A
bullet is loaded when its field's FINAL status is Verified / Verified (pass 2), or when the claims that match it
(Claim Evidence 'Supported', or a Pass 2 'Supported' verdict) support it and no matching claim is unsupported.
Everything held back goes to <reports>/leadership_held_back.csv with the reason and, where the workbook has one,
the suggested correction; counts per company go to <reports>/leadership_summary.txt.  The workbook is client data
and the repository is public: the default reports folder db/excel_reports/ is gitignored; never commit it.

products: sheet 'All Products' (the per-company tabs only repeat it, 'Unverified' is not loaded) -> competitive_product (one row
per competitor + product), competitive_product_specification (one row per line of 'Technical Specifications') and the matching
staging.fact_source rows.  Companies map to existing competitors through PRODUCT_COMPANY_MAP (an unmapped company stops the load;
competitors are never created).  Description goes to the description column (also: the 'descriptions' command); Collaboration / Production & Licensing Notes are not loaded.
Idempotent in ONE transaction: for the competitors in the sheet, the products this loader created earlier (product_id =
uuid5 of competitor + name) are deleted with their specs + fact_source and re-inserted; a product that existed before with the same
normalised name keeps its id (its specs are replaced); other products are never touched.

client-products: sheet 'All Products' of the client's own portfolio workbook (same columns as the competitor sheet; 'Unverified' is not loaded)
-> client_product / client_product_specification / client_product_source + staging.fact_source.  The client is the staging.client_account row whose
brand / client / legal name equals the sheet's Company.  Idempotent in ONE transaction.  A product keeps the id of an existing client_product of the
same normalised name (CLIENT_KEEP_ALIASES, else the existing name as a whole-word prefix of the sheet name, e.g. 'MArG 155' -> 'MArG 155 mm/39 cal ...');
new products get a deterministic 63-bit id (prompts.loader.make_id).  The specs, sources and fact_source of the products in the sheet (and of products
this loader created earlier that are no longer in the sheet) are deleted and re-inserted; other client products are never touched.
  - client_product: product_name, category (verbatim), source_id (first source), created_at / updated_at; product_family / subcategory / technology / status stay
    NULL (the sheet has no such columns).  Description goes to the description column (also: the 'descriptions' command); Collaboration / Production & Licensing Notes are not loaded.
  - client_product_source: one row per distinct URL of 'Source(s)'; the matching line of 'Source Type' gives source_type; source_label = publisher (from the host) + type.
  - client_product_specification: one row per line of 'Technical Specifications' ('Label: value', same parser and unit rule as products; no-data lines skipped).
    A trailing '[S2]' / '[S1,S3]' on a line is a footnote to the 1-based line of 'Source(s)' that states the value: it is removed from the value, the FIRST
    footnote becomes the spec's source_id (no footnote = the product's first source) and every footnoted URL gets a fact_source row.
    spec_group rule (first match wins, whole words of the label): Mobility = road, speed, engine, power, weight, mass, gradient, gradeability, drive;
    Performance = range, rate (of fire), velocity, elevation, traverse, time, accuracy, firing, burst; Physical = calibre, barrel, length, width, height, crew,
    dimension(s), diameter; everything else Other.  display_order = line position.
  - a wiki URL stops the load.
  - a source on a blocked blog domain (backend.sources.BLOCKED["blog"]: ajaishukla.com, idrw.org) is never loaded, in any of the four commands: the
    URL is dropped; a spec / line / value whose only source is blocked is skipped with reason 'blocked_source' (reports).

DSN: prompts.batch.resolve_dsn (--db vps needs the tunnel, routines/tunnel.sh).  The target is printed without the password.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS = ROOT / "db" / "excel_reports"

SHEET_DIR, SHEET_SUM, SHEET_CE, SHEET_P2, SHEET_APPLIED = (
    "Company Directory (Corrected)", "Re-verification Summary", "Claim Evidence", "Pass 2 Results", "Applied Changes")
OK_STATUS = {"Verified", "Verified (pass 2)"}
FIELDS = {"experience": ("Professional Experience", "FINAL Experience"), "education": ("Education Background", "FINAL Education")}
# Excel company name -> display_name of the competitor that already exists (news / products are linked to it)
EXISTING_COMPETITORS = {
    "Larsen & Toubro (L&T)": "Larsen & Toubro",
    "Adani Defence": "Adani Defence & Aerospace",
    "Hanwha (Aerospace/Group)": "Hanwha Aerospace",
}
HEADLINE_MAX = 300                      # competitive_leader_record.headline varchar(300)
SUPPORT_MIN, UNSUPPORTED_MIN, UNSUPPORTED_BEST_MIN = 0.6, 0.6, 0.35   # claim -> bullet token containment
MAX_FACT_URLS = 3                       # fact_source rows per role / record
TITLES = {"dr", "mr", "mrs", "ms", "miss", "shri", "smt", "prof", "professor", "gen", "adm", "lt", "col", "maj", "capt", "cdr",
          "brig", "sir", "eng", "ing", "dipl", "vadm", "radm", "cmde", "air", "marshal", "general", "admiral", "lieutenant",
          "colonel", "major", "captain", "commodore", "brigadier", "hon", "rt", "mohd"}


# ---- ids, text helpers ----------------------------------------------------------------------------------------

def competitor_id_for(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "kssl-competitor|" + name)


def leader_id_for(competitor_id, full_name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"kssl-leader|{competitor_id}|{full_name}")


def record_id_for(leader_id, record_type: str, position: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"kssl-leader-record|{leader_id}|{record_type}|{position}")


def split_bullets(cell) -> list[str]:
    """One bullet per line; the bullet glyph (U+2022, or U+FFFD where the encoding was lost), -, * and spaces are stripped."""
    out = []
    for line in str(cell or "").replace("\r", "\n").split("\n"):
        line = re.sub(r"^[\s•�\-\*–—·]+", "", line).strip()
        line = re.sub(r"\s+", " ", line)
        if line:
            out.append(line)
    return out


def initials(name: str) -> str:
    """First + last word of the name, uppercase, titles (Dr, Shri, Gen, Adm, Lt...) skipped: 'Dr Jane Example' -> 'JE'."""
    words = [w for w in re.split(r"[\s]+", name.strip()) if w]
    kept = [w for w in words if re.sub(r"[^a-z]", "", w.casefold()) not in TITLES] or words
    letters = [next((c for c in w if c.isalpha()), "") for w in kept]
    letters = [c for c in letters if c]
    if not letters:
        return ""
    return (letters[0] + (letters[-1] if len(letters) > 1 else "")).upper()


def norm_text(s: str) -> str:
    """casefold, collapse spaces, strip punctuation at both ends."""
    s = re.sub(r"\s+", " ", str(s or "").casefold()).strip()
    return re.sub(r"^[\W_]+|[\W_]+$", "", s)


_STOP = {"the", "of", "a", "an", "and", "at", "in", "as", "for", "to", "by", "with", "from", "is", "was", "its", "his", "her",
         "has", "had", "also", "on", "or", "be", "that", "which", "per"}


def tokens(s: str) -> set[str]:
    s = unicodedata.normalize("NFKD", str(s or "").casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    out = set()
    for t in re.findall(r"[^\W_]+", s):
        if t in _STOP:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


def containment(claim: str, bullet: str) -> float:
    """Share of the claim's content tokens found in the bullet; 1.0 when one normalised text is a prefix of the other."""
    nc, nb = norm_text(claim), norm_text(bullet)
    if nc and nb and (nb.startswith(nc) or nc.startswith(nb)):
        return 1.0
    ct = tokens(claim)
    return len(ct & tokens(bullet)) / len(ct) if ct else 0.0


def urls_of(cell) -> list[str]:
    return [u for u in re.split(r"\s+", str(cell or "").strip()) if u]


def split_blocked(urls) -> tuple[list[str], list[str]]:
    """(kept, blocked): the one source filter of all four commands. Blocked = wiki / blog domains (backend.sources.is_blocked)."""
    from backend.sources import is_blocked
    kept, blocked = [], []
    for u in urls:
        (blocked if is_blocked(u) else kept).append(u)
    return kept, blocked


def to_int(v) -> int:
    return int(float(str(v).strip()))


# ---- workbook -------------------------------------------------------------------------------------------------

def read_sheets(path: Path, wanted=(SHEET_DIR, SHEET_SUM, SHEET_CE, SHEET_P2, SHEET_APPLIED)) -> dict[str, list[dict]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for name in wb.sheetnames:
        if name not in wanted:
            continue
        it = wb[name].iter_rows(values_only=True)
        head = next(it, None)
        if not head:
            continue
        out[name] = [dict(zip(head, r)) for r in it if any(c is not None and str(c).strip() != "" for c in r)]
    return out


def compare_sheets(a: dict, b: dict) -> list[str]:
    """Differences of the sheets the two workbooks share (SHEET_DIR, SHEET_SUM), cell by cell; Input Row compared as int."""
    diffs = []
    for sh in (SHEET_DIR, SHEET_SUM):
        if sh not in b:
            diffs.append(f"{sh}: missing in the second file")
            continue
        ra, rb = a[sh], b[sh]
        if len(ra) != len(rb):
            diffs.append(f"{sh}: {len(ra)} rows vs {len(rb)} rows")
        for i, (x, y) in enumerate(zip(ra, rb)):
            for k in x:
                vx, vy = x.get(k), y.get(k)
                if k == "Input Row":
                    vx, vy = to_int(vx), to_int(vy)
                if (vx if vx not in ("",) else None) != (vy if vy not in ("",) else None):
                    diffs.append(f"{sh} row {i + 2} col {k!r}: {str(vx)[:60]!r} vs {str(vy)[:60]!r}")
    return diffs


def apply_overrides(sheets: dict, other: dict) -> list[tuple]:
    """The second workbook is a later cut of 'Company Directory (Corrected)': where a cell differs, its value wins.
    Returns [(input row, column, old, new)].  'Cells changed' is bookkeeping, not data, and is left alone."""
    out = []
    for i, (x, y) in enumerate(zip(sheets[SHEET_DIR], other[SHEET_DIR])):
        for k in x:
            if k != "Cells changed" and (x.get(k) or None) != (y.get(k) or None):
                out.append((i + 2, k, x.get(k), y.get(k)))
                x[k] = y.get(k)
    return out


# ---- claims ---------------------------------------------------------------------------------------------------

@dataclass
class Claim:
    text: str
    supported: bool
    result: str                                   # 'Supported' | 'Not established' | 'Contradicted' | 'Still not found'
    evidence: list = field(default_factory=list)  # [(url, quote, quote_check)]
    fix: str = ""                                 # Fix / caveat or Pass 2 'Correct value'
    suggested: str = ""                           # replacement text the workbook proposes (contradicted claims)
    origin: str = "Claim Evidence"


_QC_RANK = {"verbatim in source": 0, "not machine-checked (live fetch / scan / archive)": 1}


def _ev_sort(rows):
    return sorted(rows, key=lambda e: _QC_RANK.get(e[2], 2))


def build_claims(ce_rows: list[dict], p2_rows: list[dict]) -> dict[tuple, list[Claim]]:
    """(input row, 'experience'|'education') -> claims.  A Pass 2 verdict replaces the Claim Evidence claims it re-checked."""
    by_field = {v[0]: k for k, v in FIELDS.items()}
    ev = defaultdict(dict)                                    # key -> norm claim -> Claim
    for r in ce_rows:
        f = by_field.get(r.get("Field"))
        if not f or not r.get("Claim"):
            continue
        key, nc = (to_int(r["Input Row"]), f), norm_text(r["Claim"])
        res = (r.get("Result") or "").strip()
        c = ev[key].setdefault(nc, Claim(str(r["Claim"]).strip(), res == "Supported", res or "none"))
        if r.get("Source URL"):
            c.evidence.append((str(r["Source URL"]).strip(), (r.get("Quote") or "").strip() or None, r.get("Quote check")))
        if r.get("Fix / caveat") and not c.fix:
            c.fix = str(r["Fix / caveat"]).strip()
    p2 = defaultdict(dict)
    for r in p2_rows:
        f = r.get("Field")
        if f not in FIELDS or not r.get("Claim"):
            continue
        key, nc = (to_int(r["Input Row"]), f), norm_text(r["Claim"])
        verdict = (r.get("Accepted verdict") or "").strip()
        c = p2[key].setdefault(nc, Claim(str(r["Claim"]).strip(), False, "Still not found", origin="Pass 2 Results"))
        if verdict == "Supported" or (verdict == "Contradicted" and c.result != "Supported"):
            c.supported, c.result = verdict == "Supported", verdict
        if verdict == "Supported" and r.get("Source URL"):
            c.evidence.append((urls_of(r["Source URL"])[0], (r.get("Quote") or "").strip() or None, r.get("Quote check")))
        if r.get("Correct value (if contradicted)") and not c.fix:
            c.fix = str(r["Correct value (if contradicted)"]).strip()
    claims = defaultdict(list)
    for key in set(ev) | set(p2):
        pool = list(ev[key].values())
        for p in p2[key].values():                           # drop the evidence claims this Pass 2 claim re-checked
            if p.result == "Contradicted":
                p.suggested = p.fix
            pool = [e for e in pool if e.supported or not (containment(p.text, e.text) >= 0.75 or containment(e.text, p.text) >= 0.75)]
        for p in p2[key].values():
            # re-checked evidence claims stay dropped only when the Pass 2 claim is in the pool
            pool.append(p)
        for c in pool:
            if c.result == "Contradicted" and c.origin == "Claim Evidence":
                c.suggested = c.fix
        claims[key] = pool
    return claims


def match_bullets(bullets: list[str], claims: list[Claim]) -> tuple[list[list[Claim]], list[list[Claim]], list[Claim]]:
    """(supporting claims per bullet, unsupported claims per bullet, unmatched unsupported claims).
    A supported claim goes to its best-matching bullet(s) (containment >= SUPPORT_MIN); an unsupported claim to every bullet
    it overlaps (>= UNSUPPORTED_MIN, else the best one if >= UNSUPPORTED_BEST_MIN) so it can only hold a bullet back."""
    sup = [[] for _ in bullets]
    uns = [[] for _ in bullets]
    orphans = []
    for c in claims:
        scores = [containment(c.text, b) for b in bullets]
        if not scores:
            if not c.supported:
                orphans.append(c)
            continue
        best = max(scores)
        if c.supported:
            if best >= SUPPORT_MIN:
                for i, s in enumerate(scores):
                    if s == best:
                        sup[i].append(c)
        else:
            hit = [i for i, s in enumerate(scores) if s >= UNSUPPORTED_MIN] or \
                  ([scores.index(best)] if best >= UNSUPPORTED_BEST_MIN else [])
            for i in hit:
                uns[i].append(c)
            if not hit:
                orphans.append(c)
    return sup, uns, orphans


def uncovered_years(bullet: str, claims: list[Claim]) -> list[str]:
    """4-digit years of the bullet that none of the supporting claims mentions."""
    year = re.compile(r"(?<!\d)(?:19|20)\d\d(?!\d)")
    have = set(year.findall(" ".join(c.text for c in claims)))
    return sorted(set(year.findall(bullet)) - have)


def pick_sources(claims: list[Claim], blocked: bool = False) -> list[tuple[str, str | None]]:
    """distinct (url, quote) of the supporting claims, verbatim-checked first, at most MAX_FACT_URLS.  Sources on blocked domains
    are dropped before the cap (blocked=True returns only those: what the claims cite that must not be loaded)."""
    seen, out = set(), []
    rows = [e for c in claims for e in c.evidence]
    for url, quote, _qc in _ev_sort(rows):
        if bool(split_blocked([url])[1]) != blocked:
            continue
        if url not in seen:
            seen.add(url)
            out.append((url, quote))
    return out[:MAX_FACT_URLS]


# ---- plan -----------------------------------------------------------------------------------------------------

@dataclass
class Plan:
    competitors: list = field(default_factory=list)   # [{name, id, existing, display_name}]
    leaders: list = field(default_factory=list)       # [{leader_id, competitor_id, full_name, role_title, organization, avatar_initials, role_source_url}]
    records: list = field(default_factory=list)       # [{record_id, leader_id, record_type, headline, source_url}]
    facts: list = field(default_factory=list)         # [{table_name, row_id, column_name, source_url, quote, company}]
    held: list = field(default_factory=list)          # csv rows
    stats: dict = field(default_factory=dict)         # company -> counters
    linkedin: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _count(plan: Plan, company: str, key: str, n: int = 1):
    plan.stats.setdefault(company, defaultdict(int))[key] += n


def build_plan(sheets: dict, existing: dict[str, str] | None = None) -> Plan:
    """existing: display_name -> competitor_id already in the database (the three mapped companies must be there)."""
    existing = existing or {}
    cd, rv = sheets[SHEET_DIR], sheets[SHEET_SUM]
    claims = build_claims(sheets.get(SHEET_CE, []), sheets.get(SHEET_P2, []))
    pos_claims = defaultdict(list)
    for r in sheets.get(SHEET_CE, []):
        if r.get("Field") == "Current Position" and r.get("Source URL"):
            pos_claims[to_int(r["Input Row"])].append((str(r["Source URL"]).strip(), (r.get("Quote") or "").strip() or None, r.get("Quote check")))
    applied = defaultdict(list)                         # (row, field) -> [(old bullet, new bullet)]
    for r in sheets.get(SHEET_APPLIED, []):
        applied[(to_int(r["Input Row"]), r["Field"])].append((split_bullets(r["Old bullet (as entered)"]), split_bullets(r["New bullet (applied)"])))
    plan = Plan()
    by_lower = {k.casefold(): v for k, v in existing.items()}
    seen_company = {}
    summary = {to_int(r["Input Row"]): r for r in rv}
    seen_leader = set()

    def held(company, person, fld, value, reason, suggested="", source=""):
        plan.held.append({"company": company, "person": person, "field": fld, "bullet_or_value": value, "reason": reason,
                          "suggested_correction": suggested, "source": source})

    for idx, r in enumerate(cd):
        row = idx + 2
        s = summary.get(row)
        company, person = str(r["Company Name"]).strip(), str(r["People Name"]).strip()
        if not s or s["Company"] != company or not (norm_text(s["Person"]).startswith(norm_text(person)) or norm_text(person).startswith(norm_text(s["Person"]))):
            raise ValueError(f"row {row}: directory ({company} / {person}) does not match Re-verification Summary")
        if company not in seen_company:
            if company in EXISTING_COMPETITORS:
                disp = EXISTING_COMPETITORS[company]
                if disp not in existing:
                    raise ValueError(f"{company!r} must map to the existing competitor {disp!r}, which is not in the database")
                cid, ex = existing[disp], True
            elif company.casefold() in by_lower:
                cid, ex, disp = by_lower[company.casefold()], True, company
            else:
                cid, ex, disp = str(competitor_id_for(company)), False, company
            seen_company[company] = cid
            plan.competitors.append({"name": company, "id": cid, "existing": ex, "display_name": disp})
        cid = seen_company[company]
        lid = str(leader_id_for(cid, person))
        if lid in seen_leader:
            raise ValueError(f"duplicate person {person!r} in {company!r}")
        seen_leader.add(lid)
        urls = urls_of(r.get("Source URL"))
        good_urls = split_blocked(urls)[0]
        first_url = good_urls[0] if good_urls else None
        _count(plan, company, "people")

        # --- role
        position = (r.get("Current Position") or "").strip()
        pstat = s["FINAL Position"]
        role_title = role_url = None
        if pstat in OK_STATUS and position:
            pclaim = [Claim("", True, "Supported", pos_claims.get(row, []))]
            src, cited_blocked = pick_sources(pclaim), pick_sources(pclaim, blocked=True)
            if not src and not cited_blocked and first_url:
                src = [(first_url, None)]
            if not src and (cited_blocked or urls):          # every source of this value is on a blocked domain
                _count(plan, company, "roles_held")
                held(company, person, "Current Position", position, "blocked_source: every source of this value is on a blocked domain",
                     source=(cited_blocked[0][0] if cited_blocked else urls[0]))
            else:
                role_title = position[:200]
                role_url = src[0][0] if src else None
                for url, quote in src:
                    plan.facts.append({"table_name": "competitive_leader", "row_id": lid, "column_name": "role_title", "source_url": url,
                                       "quote": quote, "company": company})
                _count(plan, company, "roles_loaded")
        else:
            _count(plan, company, "roles_held")
            held(company, person, "Current Position", position, f"FINAL Position status: {pstat}" + (f" ({s['Position Note']})" if s.get("Position Note") else ""),
                 source=first_url or "")
        plan.leaders.append({"leader_id": lid, "competitor_id": cid, "full_name": person, "role_title": role_title, "organization": company,
                             "avatar_initials": initials(person), "role_source_url": role_url})
        if s.get("LinkedIn URL"):
            plan.linkedin.append((company, person, s["LinkedIn URL"], s.get("LinkedIn Confidence"), s.get("LinkedIn Note")))

        # --- experience / education bullets
        for rtype, (col, stcol) in FIELDS.items():
            bullets = split_bullets(r.get(col))
            fstat = s[stcol]
            fld_ok = fstat in OK_STATUS
            sup, uns, orphans = match_bullets(bullets, claims.get((row, rtype), []))
            for c in orphans:
                plan.warnings.append(f"row {row} {person} {rtype}: unsupported claim matches no bullet: {c.text[:80]!r} [{c.result}]")
            for pos, b in enumerate(bullets, 1):
                suggested = "; ".join(dict.fromkeys(c.suggested for c in uns[pos - 1] if c.suggested))
                for olds, news in applied.get((row, col), []):
                    if any(norm_text(o) and norm_text(o) in norm_text(b) for o in olds) and not suggested:
                        suggested = "Applied Changes new bullet: " + " | ".join(news)
                if fld_ok:
                    ok, why = True, ""
                    if uns[pos - 1]:
                        plan.warnings.append(f"row {row} {person} {rtype} #{pos}: field is {fstat} but a matching claim is {uns[pos-1][0].result}: {uns[pos-1][0].text[:70]!r} (loaded)")
                elif uns[pos - 1]:
                    ok, why = False, "; ".join(f"claim {c.result}: {c.text}" + (f" ({c.fix})" if c.fix and not c.suggested else "") for c in uns[pos - 1])
                elif sup[pos - 1]:
                    ok, why = True, ""
                    missing = uncovered_years(b, sup[pos - 1])
                    if missing:      # the supporting claims do not mention every year of the bullet: part of it is unchecked
                        ok, why = False, f"supported claims cover only part of the bullet (year {', '.join(missing)} not in any supported claim: " + "; ".join(c.text for c in sup[pos - 1]) + ")"
                else:
                    ok, why = False, f"field {fstat}; no matching supported claim"
                if ok and len(b) > HEADLINE_MAX:
                    ok, why = False, f"longer than {HEADLINE_MAX} characters ({len(b)}): competitive_leader_record.headline is varchar({HEADLINE_MAX})"
                srcs, cited_blocked = pick_sources(sup[pos - 1]), pick_sources(sup[pos - 1], blocked=True)
                if not srcs and not cited_blocked and first_url:
                    srcs = [(first_url, None)]
                if not ok:
                    _count(plan, company, f"{rtype}_held")
                    if not why.startswith("longer"):
                        why = f"field {fstat}: {why}" if not why.startswith("field") else why
                    held(company, person, col, b, why, suggested, srcs[0][0] if srcs else "")
                    continue
                if not srcs and (cited_blocked or urls):          # every source of this line is on a blocked domain
                    plan.warnings.append(f"row {row} {person} {rtype} #{pos}: only blocked sources (skipped)")
                    _count(plan, company, f"{rtype}_held")
                    held(company, person, col, b, "blocked_source: every source of this line is on a blocked domain", "",
                         cited_blocked[0][0] if cited_blocked else urls[0])
                    continue
                if not srcs:
                    plan.warnings.append(f"row {row} {person} {rtype} #{pos}: no source URL at all (skipped)")
                    _count(plan, company, f"{rtype}_held")
                    held(company, person, col, b, "no source URL in the workbook", "", "")
                    continue
                rid = str(record_id_for(lid, rtype, pos))
                plan.records.append({"record_id": rid, "leader_id": lid, "record_type": rtype, "headline": b, "source_url": srcs[0][0]})
                for url, quote in srcs:
                    plan.facts.append({"table_name": "competitive_leader_record", "row_id": rid, "column_name": "headline", "source_url": url,
                                       "quote": quote, "company": company})
                _count(plan, company, f"{rtype}_loaded")
    return plan


# ---- reports --------------------------------------------------------------------------------------------------

def write_reports(plan: Plan, out_dir: Path, dry_run: bool) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    held_path, sum_path = out_dir / "leadership_held_back.csv", out_dir / "leadership_summary.txt"
    cols = ["company", "person", "field", "bullet_or_value", "reason", "suggested_correction", "source"]
    with held_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(plan.held)
    keys = ["people", "roles_loaded", "roles_held", "experience_loaded", "experience_held", "education_loaded", "education_held"]
    lines = [f"Leadership load summary ({'DRY RUN' if dry_run else 'loaded'})", "",
             f"{'company':40} " + " ".join(f"{k[:10]:>10}" for k in keys), "-" * 125]
    tot = defaultdict(int)
    for c in plan.competitors:
        st = plan.stats.get(c["name"], {})
        lines.append(f"{c['name'][:40]:40} " + " ".join(f"{st.get(k, 0):>10}" for k in keys))
        for k in keys:
            tot[k] += st.get(k, 0)
    lines += ["-" * 125, f"{'TOTAL':40} " + " ".join(f"{tot[k]:>10}" for k in keys), ""]
    lines.append(f"competitors: {len(plan.competitors)} ({sum(1 for c in plan.competitors if c['existing'])} existing, "
                 f"{sum(1 for c in plan.competitors if not c['existing'])} new)")
    lines += ["", f"LinkedIn URLs in the workbook (the schema has no LinkedIn column; listed here only): {len(plan.linkedin)}"]
    for company, person, url, conf, note in sorted(plan.linkedin, key=lambda x: (x[0], x[1])):
        lines.append(f"  [{conf}] {company} / {person}: {url}")
    if plan.warnings:
        lines += ["", f"warnings ({len(plan.warnings)}):"] + ["  " + w for w in plan.warnings]
    sum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return held_path, sum_path


# ---- database -------------------------------------------------------------------------------------------------

def company_domains(url: str, names: set[str]) -> tuple:
    """Same rule as prompts.loader: a host whose main label is the company's compact name is the company's own site."""
    from backend.sources import host_of
    host = host_of(url)
    parts = host.split(".")
    label = parts[-3] if len(parts) >= 3 and parts[-2] in ("co", "com", "gov", "org", "ac", "net") else (parts[-2] if len(parts) >= 2 else host)
    label = re.sub(r"[^a-z0-9]", "", label)
    if any(n == label and len(n) >= 3 or (len(label) >= 5 and len(n) >= 5 and (n.startswith(label) or label.startswith(n))) for n in names):
        return (host,)
    return ()


def name_variants(company: str) -> set[str]:
    from prompts.loader import compact_name
    parts = {company, re.sub(r"\(.*?\)", " ", company)}
    for inner in re.findall(r"\((.*?)\)", company):
        parts.update(re.split(r"[/+]", inner))
        parts.add(inner.split()[0] if inner.split() else "")        # 'KNDS France' -> 'KNDS' (only from a parenthetical)
    generic = {"group", "aerospace", "defence", "defense", "systems", "industries", "corporation", "international", "air", "marine"}
    return {n for n in (compact_name(p) for p in parts if p.strip()) if len(n) >= 3 and n not in generic}


def existing_competitors(cur) -> dict[str, str]:
    cur.execute("SELECT display_name, competitor_id::text AS cid FROM staging.competitive_competitor")
    return {r["display_name"]: r["cid"] for r in cur.fetchall()}


def _requalify(conn) -> None:
    """Competitors, products or client data changed: re-test which competitors qualify (same product line AND same market)
    before the load commits (user decision 2026-10-18: the UI shows only qualifying competitors)."""
    import psycopg2.extras
    from prompts.derive_comp import qualify_competitors
    qualify_competitors(conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))


def apply_plan(conn, plan: Plan, dry_run: bool) -> dict:
    from backend.sources import classify
    cur = conn.cursor()
    ids = [c["id"] for c in plan.competitors]
    cur.execute("SELECT leader_id::text AS lid FROM staging.competitive_leader WHERE competitor_id = ANY(%s::uuid[])", (ids,))
    old_leaders = [r["lid"] for r in cur.fetchall()]
    cur.execute("SELECT record_id::text AS rid FROM staging.competitive_leader_record WHERE leader_id = ANY(%s::uuid[])", (old_leaders,))
    old_records = [r["rid"] for r in cur.fetchall()]
    res = {"deleted_leaders": len(old_leaders), "deleted_records": len(old_records)}
    cur.execute("DELETE FROM staging.fact_source WHERE (table_name = 'competitive_leader' AND row_id = ANY(%s)) "
                "OR (table_name = 'competitive_leader_record' AND row_id = ANY(%s))", (old_leaders, old_records))
    res["deleted_facts"] = cur.rowcount
    cur.execute("DELETE FROM staging.competitive_leader_record WHERE leader_id = ANY(%s::uuid[])", (old_leaders,))
    cur.execute("DELETE FROM staging.competitive_leader WHERE competitor_id = ANY(%s::uuid[])", (ids,))
    new = 0
    for c in plan.competitors:
        cur.execute("INSERT INTO staging.competitive_competitor (competitor_id, display_name) SELECT %s, %s "
                    "WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_competitor WHERE competitor_id = %s)", (c["id"], c["display_name"], c["id"]))
        new += cur.rowcount
    res["competitors_inserted"] = new
    for l in plan.leaders:
        cur.execute("INSERT INTO staging.competitive_leader (leader_id, competitor_id, full_name, role_title, organization, avatar_initials, "
                    "role_source_url, detail_route) VALUES (%(leader_id)s, %(competitor_id)s, %(full_name)s, %(role_title)s, %(organization)s, "
                    "%(avatar_initials)s, %(role_source_url)s, NULL)", l)
    for r in plan.records:
        cur.execute("INSERT INTO staging.competitive_leader_record (record_id, leader_id, record_type, headline, role_or_degree, "
                    "institution_or_employer, start_date, end_date, source_url) VALUES (%(record_id)s, %(leader_id)s, %(record_type)s, "
                    "%(headline)s, NULL, NULL, NULL, NULL, %(source_url)s)", r)
    names = {}
    tiers = defaultdict(int)
    for f in plan.facts:
        names.setdefault(f["company"], name_variants(f["company"]))
        tier = classify(f["source_url"], company_domains(f["source_url"], names[f["company"]])) or "unlisted"
        tiers[tier] += 1
        cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at) "
                    "VALUES (%s, %s, %s, %s, %s, NULL, %s, now())", (f["table_name"], f["row_id"], f["column_name"], f["source_url"], tier, f["quote"]))
    res.update(leaders=len(plan.leaders), records=len(plan.records), facts=len(plan.facts), tiers=dict(tiers))
    if dry_run:
        conn.rollback()
    else:
        _requalify(conn)
        conn.commit()
    return res


def cmd_leadership(args) -> int:
    from prompts import batch
    sheets = read_sheets(Path(args.file))
    overrides = []
    if args.compare:
        other = read_sheets(Path(args.compare))
        diffs = compare_sheets(sheets, other)
        print(f"compare with {Path(args.compare).name}: " + ("identical (Company Directory (Corrected) + Re-verification Summary)" if not diffs else f"{len(diffs)} differing cells"))
        for d in diffs[:80]:
            print("   ", d[:200])
        overrides = apply_overrides(sheets, other)
        if overrides:
            print(f"  -> {len(overrides)} cells taken from the second file (it differs from the first)")
    conn = batch.connect_db(args.db)
    try:
        plan = build_plan(sheets, existing_competitors(conn.cursor()))
        plan.warnings += [f"row {r} {c!r} taken from the second file: {str(o)[:70]!r} -> {str(n)[:70]!r}" for r, c, o, n in overrides]
        held_path, sum_path = write_reports(plan, Path(args.reports), args.dry_run)
        res = apply_plan(conn, plan, args.dry_run)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    tot = defaultdict(int)
    for st in plan.stats.values():
        for k, v in st.items():
            tot[k] += v
    print(("DRY RUN (rolled back)" if args.dry_run else "LOADED") + f": competitors {len(plan.competitors)} "
          f"({sum(1 for c in plan.competitors if c['existing'])} existing, {res['competitors_inserted']} inserted)")
    print(f"  leaders {res['leaders']}  (replaced {res['deleted_leaders']} leaders / {res['deleted_records']} records / {res['deleted_facts']} fact_source)")
    print(f"  roles loaded {tot['roles_loaded']}, held {tot['roles_held']}")
    for t in ("experience", "education"):
        print(f"  {t}: loaded {tot[t + '_loaded']}, held {tot[t + '_held']}")
    print(f"  records {res['records']}  fact_source {res['facts']}  tiers {res['tiers']}  warnings {len(plan.warnings)}")
    print(f"  reports: {held_path}\n           {sum_path}")
    return 0


# ---- company details (sheet 'COMPANY DIRECTORY') ---------------------------------------------------------------

SHEET_COMPANY = "COMPANY DIRECTORY"
COMPANY_COLS = {"Company": "company", "Country / Region": "country", "Source Entity Label": "label",
                "Starting Year / Corporate Origin": "start", "Headquarters": "hq", "Company Size": "size",
                "Annual Revenue / Sales": "revenue", "Financial Year": "fy", "Industry / Sector": "sector",
                "CEO / Managing Director": "ceo", "Chairman": "chairman", "Board / Leadership": "board", "Sources": "sources"}
# competitive_competitor columns this command writes (fact_source rows of exactly these columns are replaced on a re-run)
COMPANY_FACT_COLS = ["origin_country", "headquarters", "industry_sector", "starting_year_text", "starting_year", "employee_count_text",
                     "employee_count", "revenue_text", "annual_revenue", "revenue_currency", "financial_year"]
VARCHAR_LIMITS = {"origin_country": 100, "headquarters": 250, "industry_sector": 200, "financial_year": 120}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
YEAR_RE = re.compile(r"(?<![\d.,])(?:1[5-9]|20)\d\d(?![\d])")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
SIZE_QUALIFIER = re.compile(r"more than|\bover\b|approx|\babout\b|~|\+|\baround\b|\bnearly\b|\balmost\b|\broughly\b|\bcirca\b|\bestimate|"
                            r"up to|at least|less than|\bunder\b|\bparent\b|\bgroup\b|\bincluding\b|linkedin|\bnot\b|\bn/a\b|[–—]|\d\s*-\s*\d|\brange\b|\bband\b|\bto\b", re.I)
REV_QUALIFIER = re.compile(r"approx|\babout\b|~|\baround\b|\broughly\b|\bnearly\b|\bestimate|\bsegment|\bparent\b|group[- ]level|\bgroup\b|\blegacy\b|"
                           r"\brange\b|up to|at least|less than|\bbetween\b|\bnot\b|\bn/a\b|\bhistorical\b|\bclassified\b", re.I)
SCALES = {"crore": Decimal(10) ** 7, "cr": Decimal(10) ** 7, "lakh": Decimal(10) ** 5, "lakhs": Decimal(10) ** 5, "million": Decimal(10) ** 6,
          "mn": Decimal(10) ** 6, "billion": Decimal(10) ** 9, "bn": Decimal(10) ** 9, "trillion": Decimal(10) ** 12}
CURRENCIES = {"₹": "INR", "RS": "INR", "RS.": "INR", "INR": "INR", "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP", "US$": "USD",
              "$": "USD", "USD": "USD", "KRW": "KRW", "₩": "KRW", "NOK": "NOK", "SEK": "SEK", "PLN": "PLN", "TL": "TRY", "TRY": "TRY",
              "NIS": "ILS", "ILS": "ILS"}
AMOUNT_RE = re.compile(r"(?<![A-Za-z])(US\$|USD|\$|₹|Rs\.?|INR|€|EUR|£|GBP|KRW|₩|NOK|SEK|PLN|TRY|TL|NIS|ILS)\s*(\d[\d,]*(?:\.\d+)?)"
                       r"(?:\s*(crore|cr|lakhs?|million|mn|billion|bn|trillion)\b)?", re.I)


def clean_cell(v) -> str | None:
    """The cell text as the workbook shows it (stripped); a date cell becomes 'D Mon YYYY'; empty -> None."""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return f"{v.day} {MONTHS[v.month - 1]} {v.year}"
    t = str(v).strip()
    return t or None


def parse_year(text: str | None) -> tuple[int | None, str]:
    """(year, reason): the year only when the text holds exactly one distinct 4-digit year."""
    years = sorted(set(YEAR_RE.findall(text or "")))
    if len(years) == 1:
        return int(years[0]), "one year"
    return None, "no year" if not years else "several years " + ", ".join(years)


def parse_employees(text: str | None) -> tuple[int | None, str]:
    """(count, reason): a plain count only - one number, no qualifier.  Dates, years after at/in/as of, and parenthetical notes
    ('8,765 employees (31 Mar 2030)') do not count as numbers; a qualifier anywhere (also inside the brackets) blocks it."""
    t = text or ""
    if not t:
        return None, "empty"
    m = SIZE_QUALIFIER.search(t)
    if m:
        return None, f"qualifier {m.group(0).strip()!r}"
    body = re.sub(r"\([^)]*\)", " ", t)
    body = re.sub(r"\b\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}\b|\b[A-Za-z]{3,9}\.?\s+\d{4}\b", " ", body)
    body = re.sub(r"\b(?:at|in|as of|as on|by|end-?|end of|mid-)\s*(?:19|20)\d\d\b", " ", body, flags=re.I)
    nums = NUM_RE.findall(body)
    if len(nums) != 1:
        return None, "no number" if not nums else f"{len(nums)} numbers"
    n = nums[0].replace(",", "")
    if "." in n:
        return None, "decimal"
    return int(n), "plain count"


def _amounts(text: str):
    out = []
    for m in AMOUNT_RE.finditer(text):
        sym = m.group(1)
        cur = CURRENCIES.get(sym.upper()) or CURRENCIES[sym]
        num = m.group(2).replace(",", "")
        scale = SCALES[m.group(3).lower()] if m.group(3) else Decimal(1)
        dec = len(num.split(".")[1]) if "." in num else 0
        out.append((cur, Decimal(num) * scale, Decimal(1).scaleb(-dec) * scale))     # (currency, value, step = unit of the last digit)
    return out


def parse_revenue(text: str | None) -> tuple[Decimal | None, str | None, str]:
    """(amount in full currency units, ISO currency, reason): only when the text states ONE amount with no qualifier.
    The same figure stated twice ('7.2 billion (7.215 billion)') counts once, the more precise one wins."""
    t = text or ""
    if not t:
        return None, None, "empty"
    m = REV_QUALIFIER.search(t)
    if m:
        return None, None, f"qualifier {m.group(0).strip()!r}"
    am = _amounts(t)
    if not am:
        return None, None, "no amount"
    if len({a[0] for a in am}) > 1:
        return None, None, "two currencies"
    best = min(am, key=lambda a: a[2])                      # smallest step = most precise
    for cur, val, step in am:
        if (best[1] / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step != val:
            return None, None, f"{len({a[1] for a in am})} different amounts"
    return best[1], best[0], "one amount" if len(am) == 1 else "same figure stated twice"


def company_rows(sheet_rows: list[dict]) -> list[dict]:
    """Workbook rows -> one dict per company (short keys, cleaned text); the 13 expected headers must be there."""
    out = []
    for r in sheet_rows:
        missing = [h for h in COMPANY_COLS if h not in r]
        if missing:
            raise ValueError(f"company sheet is missing columns: {missing}")
        d = {k: clean_cell(r[h]) for h, k in COMPANY_COLS.items()}
        if d["company"]:
            out.append(d)
    names = [d["company"] for d in out]
    if len(set(names)) != len(names):
        raise ValueError("duplicate company names in the sheet")
    return out


def resolve_competitor(company: str, existing: dict[str, str]) -> dict:
    """Same mapping as the leadership loader: the 3 mapped companies keep their ids, a case-insensitive display_name match is
    reused, anything else gets the deterministic uuid5 (inserted if missing)."""
    by_lower = {k.casefold(): v for k, v in existing.items()}
    if company in EXISTING_COMPETITORS:
        disp = EXISTING_COMPETITORS[company]
        if disp not in existing:
            raise ValueError(f"{company!r} must map to the existing competitor {disp!r}, which is not in the database")
        return {"name": company, "id": existing[disp], "existing": True, "display_name": disp}
    if company.casefold() in by_lower:
        return {"name": company, "id": by_lower[company.casefold()], "existing": True, "display_name": company}
    return {"name": company, "id": str(competitor_id_for(company)), "existing": False, "display_name": company}


def build_company_plan(rows: list[dict], existing: dict[str, str]) -> dict:
    """{'items': [...], 'widen': {...}}: per company the competitor, the column values to write, the fact_source rows and why
    numbers were left NULL."""
    items, widen = [], {}
    for d in rows:
        comp = resolve_competitor(d["company"], existing)
        year, ywhy = parse_year(d["start"])
        emp, ewhy = parse_employees(d["size"])
        rev, cur, rwhy = parse_revenue(d["revenue"])
        vals = {"origin_country": d["country"], "headquarters": d["hq"], "industry_sector": d["sector"],
                "starting_year_text": d["start"], "starting_year": year, "employee_count_text": d["size"], "employee_count": emp,
                "revenue_text": d["revenue"], "annual_revenue": rev, "revenue_currency": cur, "financial_year": d["fy"]}
        for col, lim in VARCHAR_LIMITS.items():
            if vals[col] and len(vals[col]) > lim:
                widen[col] = max(widen.get(col, 0), len(vals[col]))
        rev_quote = None
        if d["revenue"]:
            rev_quote = f"{d['revenue']} [entity: {d['label'] or d['company']}; {d['fy'] or 'financial year not stated'}]"
        quotes = {"origin_country": d["country"], "headquarters": d["hq"], "industry_sector": d["sector"],
                  "starting_year_text": d["start"], "starting_year": d["start"], "employee_count_text": d["size"],
                  "employee_count": d["size"], "revenue_text": rev_quote, "annual_revenue": rev_quote, "revenue_currency": rev_quote,
                  "financial_year": d["fy"]}
        raw_urls = list(dict.fromkeys(urls_of(d["sources"])))
        urls = split_blocked(raw_urls)[0]
        blocked_only = bool(raw_urls) and not urls
        if blocked_only:       # every source is on a blocked domain: the values rest on nothing loadable, so none is written (NULL)
            vals.update({col: None for col in COMPANY_FACT_COLS})
        facts = [{"column_name": col, "source_url": u, "quote": quotes[col]}
                 for col in COMPANY_FACT_COLS if vals[col] is not None and quotes[col] for u in urls]
        items.append({"company": d["company"], "comp": comp, "vals": vals, "facts": facts, "urls": urls, "src": d, "blocked_source": blocked_only,
                      "why": {"starting_year": ywhy, "employee_count": ewhy, "annual_revenue": rwhy}})
    return {"items": items, "widen": widen}


# -- cross-check of CEO / Chairman / Board against competitive_leader (nothing from these cells is stored) --

HONOURS = {"cbe", "obe", "dbe", "kbe", "mbe", "dso", "phd", "ret", "dame", "sir", "jr", "sr", "ing"}


def name_tokens(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", str(name or "").casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [t for t in re.findall(r"[^\W_]+", s) if t not in TITLES and t not in HONOURS]


def same_person(a: str, b: str) -> bool:
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    sa, sb = set(ta), set(tb)
    shared = sa & sb
    return bool(shared) and (sa <= sb or sb <= sa or (len(shared) >= 2 and ta[-1] == tb[-1]))


def excel_people(d: dict) -> list[tuple[str, str, str]]:
    """[(name, title, cell)] from CEO / Chairman / Board; a line without 'Name - Title' is ignored."""
    out = []
    for cell, key in (("CEO / Managing Director", "ceo"), ("Chairman", "chairman"), ("Board / Leadership", "board")):
        for line in split_bullets(d.get(key)):
            parts = re.split(r"\s*[—–]\s*|\s+-\s*", line, maxsplit=1)
            if len(parts) == 2 and 1 <= len(name_tokens(parts[0])) <= 7 and len(parts[0]) < 60:
                out.append((parts[0].strip(), parts[1].strip(), cell))
    return out


def title_close(a: str, b: str) -> bool:
    ta, tb = tokens(a), tokens(b)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.5


def crosscheck(item: dict, leaders: list[dict]) -> list[dict]:
    """Rows for the CSV: names in the Excel cells but not in competitive_leader, the reverse, and title differences."""
    rows = []
    ex = excel_people(item["src"])
    company = item["company"]
    seen = set()
    for name, title, cell in ex:
        hit = next((l for l in leaders if same_person(name, l["full_name"])), None)
        if hit is None:
            if name not in seen:
                seen.add(name)
                rows.append({"company": company, "difference": "in Excel, not in leaders", "name": name, "excel_title": title, "excel_cell": cell, "leader_title": ""})
        else:
            lt = hit["role_title"] or ""
            if lt and not title_close(title, lt):
                rows.append({"company": company, "difference": "title differs", "name": name, "excel_title": title, "excel_cell": cell, "leader_title": lt})
    for l in leaders:
        if not any(same_person(l["full_name"], n) for n, _, _ in ex):
            rows.append({"company": company, "difference": "in leaders, not in Excel", "name": l["full_name"], "excel_title": "", "excel_cell": "", "leader_title": l["role_title"] or ""})
    return rows


def apply_company_plan(conn, plan: dict, dry_run: bool) -> dict:
    from backend.sources import classify
    cur = conn.cursor()
    ids = [it["comp"]["id"] for it in plan["items"]]
    inserted = 0
    for it in plan["items"]:
        c = it["comp"]
        cur.execute("INSERT INTO staging.competitive_competitor (competitor_id, display_name) SELECT %s, %s "
                    "WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_competitor WHERE competitor_id = %s)", (c["id"], c["display_name"], c["id"]))
        inserted += cur.rowcount
    cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_competitor' AND row_id = ANY(%s) AND column_name = ANY(%s)",
                (ids, COMPANY_FACT_COLS))
    deleted_facts = cur.rowcount
    updated, nfacts, tiers = 0, 0, defaultdict(int)
    sets = ", ".join(f"{c} = %({c})s" for c in COMPANY_FACT_COLS)
    for it in plan["items"]:
        cur.execute(f"UPDATE staging.competitive_competitor SET {sets} WHERE competitor_id = %(cid)s", {**it["vals"], "cid": it["comp"]["id"]})
        updated += cur.rowcount
        names = name_variants(it["company"])
        for f in it["facts"]:
            tier = classify(f["source_url"], company_domains(f["source_url"], names)) or "unlisted"
            tiers[tier] += 1
            nfacts += 1
            cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at) "
                        "VALUES ('competitive_competitor', %s, %s, %s, %s, NULL, %s, now())",
                        (it["comp"]["id"], f["column_name"], f["source_url"], tier, f["quote"]))
    leaders = {}
    cur.execute("SELECT competitor_id::text AS cid, full_name, role_title FROM staging.competitive_leader WHERE competitor_id = ANY(%s::uuid[])", (ids,))
    for r in cur.fetchall():
        leaders.setdefault(r["cid"], []).append(dict(r))
    cross = []
    for it in plan["items"]:
        cross += crosscheck(it, leaders.get(it["comp"]["id"], []))
    if updated != len(plan["items"]):
        conn.rollback()
        raise RuntimeError(f"updated {updated} rows, expected {len(plan['items'])}: rolled back")
    if dry_run:
        conn.rollback()
    else:
        _requalify(conn)
        conn.commit()
    return {"inserted": inserted, "updated": updated, "deleted_facts": deleted_facts, "facts": nfacts, "tiers": dict(tiers), "cross": cross}


def write_company_reports(plan: dict, res: dict, out_dir: Path, dry_run: bool) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath, spath = out_dir / "company_leadership_crosscheck.csv", out_dir / "company_details_summary.txt"
    cols = ["company", "difference", "name", "excel_title", "excel_cell", "leader_title"]
    with cpath.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(res["cross"])
    items = plan["items"]
    lines = [f"Company details load summary ({'DRY RUN' if dry_run else 'loaded'})", "",
             f"{'company':34} {'year':>6} {'employees':>10} {'revenue':>26}  left NULL because", "-" * 150]
    cnt = defaultdict(int)
    for it in items:
        v, why = it["vals"], it["why"]
        notes = []
        for col, label in (("starting_year", "year"), ("employee_count", "employees"), ("annual_revenue", "revenue")):
            if v[col] is None:
                notes.append(f"{label}: {why[col]}")
            else:
                cnt[col] += 1
        rev = f"{v['annual_revenue']:,.0f} {v['revenue_currency']}" if v["annual_revenue"] is not None else "NULL"
        emp = v["employee_count"] if v["employee_count"] is not None else "NULL"
        lines.append(f"{it['company'][:34]:34} {v['starting_year'] or 'NULL':>6} {emp:>10} {rev:>26}  " + "; ".join(notes))
    n = len(items)
    lines += ["-" * 150, f"companies {n}: starting_year filled {cnt['starting_year']}, employee_count filled {cnt['employee_count']}, annual_revenue+currency filled {cnt['annual_revenue']}",
              f"  (text columns are filled wherever the cell is not empty: starting_year_text {sum(1 for i in items if i['vals']['starting_year_text'])}, "
              f"employee_count_text {sum(1 for i in items if i['vals']['employee_count_text'])}, revenue_text {sum(1 for i in items if i['vals']['revenue_text'])}, "
              f"financial_year {sum(1 for i in items if i['vals']['financial_year'])})", ""]
    lines.append("columns widened to text: " + (", ".join(f"{c} (longest {n_} > {VARCHAR_LIMITS[c]})" for c, n_ in plan["widen"].items()) or "none needed"))
    lens = {c: max(len(i["vals"][c] or "") for i in items) for c in VARCHAR_LIMITS}
    lines.append("longest values vs limits: " + ", ".join(f"{c} {lens[c]}/{VARCHAR_LIMITS[c]}" for c in lens))
    new = [i["company"] for i in items if not i["comp"]["existing"]]
    lines += ["", f"competitors: {n} ({n - len(new)} existing in competitive_competitor, {res['inserted']} inserted)",
              "companies not found in competitive_competitor (inserted): " + (", ".join(new) if new else "none"),
              f"fact_source: {res['facts']} rows written ({res['deleted_facts']} earlier rows of these columns replaced); tiers {res['tiers']}",
              "blocked_source (every source on a blocked blog domain; all fact columns left NULL): "
              + (", ".join(i["company"] for i in items if i.get("blocked_source")) or "none"),
              f"leadership cross-check: {len(res['cross'])} differences -> {cpath.name}"]
    spath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cpath, spath


def cmd_company(args) -> int:
    from prompts import batch
    sheets = read_sheets(Path(args.file), wanted=(SHEET_COMPANY,))
    if SHEET_COMPANY not in sheets:
        raise SystemExit(f"sheet {SHEET_COMPANY!r} not found")
    rows = company_rows(sheets[SHEET_COMPANY])
    conn = batch.connect_db(args.db)
    try:
        plan = build_company_plan(rows, existing_competitors(conn.cursor()))
        if plan["widen"]:
            raise SystemExit(f"values longer than the column limit {plan['widen']}: widen those columns to text in db/setup/08_competitor_text_columns.sql first")
        res = apply_company_plan(conn, plan, args.dry_run)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    cpath, spath = write_company_reports(plan, res, Path(args.reports), args.dry_run)
    items = plan["items"]
    filled = {c: sum(1 for i in items if i["vals"][c] is not None) for c in ("starting_year", "employee_count", "annual_revenue")}
    print(("DRY RUN (rolled back)" if args.dry_run else "LOADED") + f": {res['updated']} competitors updated, {res['inserted']} inserted")
    print(f"  numbers filled: starting_year {filled['starting_year']}, employee_count {filled['employee_count']}, annual_revenue {filled['annual_revenue']} (of {len(items)}); the rest are NULL with the text shown")
    print(f"  fact_source {res['facts']} (replaced {res['deleted_facts']})  tiers {res['tiers']}  cross-check differences {len(res['cross'])}")
    print(f"  reports: {spath}\n           {cpath}")
    return 0


# ---- product specifications (sheet 'All Products') -------------------------------------------------------------

SHEET_PRODUCTS = "All Products"
PRODUCT_COLS = ["Company", "Category", "Product", "Description", "Technical Specifications", "Collaboration / Partners",
                "Production & Licensing Notes", "Source(s)", "Source Type", "Confidence", "Notes", "Verification", "Verification detail"]
# spec-sheet company name -> display_name of the competitor (every other name must equal a display_name, case-insensitively)
PRODUCT_COMPANY_MAP = {
    "Larsen & Toubro": "Larsen & Toubro",
    "Hanwha Aerospace": "Hanwha Aerospace",
    "Adani Defence": "Adani Defence & Aerospace",
    "Saab": "SAAB",
    "SIG SAUER": "SIG Sauer",
    "Kalashnikov": "Kalashnikov Concern",
    "Israel Aerospace Inds (IAI)": "Israel Aerospace Industries (IAI)",
    "Bharat Dynamics": "Bharat Dynamics Ltd (BDL)",
    "Huta Stalowa Wola": "Huta Stalowa Wola (HSW)",
    "Munitions India (MIL)": "Munitions India Ltd (MIL)",
    "PLR Systems": "PLR Systems (IWI+Adani)",
    "Rafael": "Rafael Advanced Defense Systems",
    "Nexter (KNDS France)": "Nexter (KNDS France)",
    "KNDS (KMW+Nexter)": "KNDS Germany",          # the KMW+Nexter group tab goes to KNDS Germany; the same product may also sit under Nexter
}
PRODUCT_LIMITS = {"product_name": 250, "category": 100, "spec_label": 150}      # varchar limits of competitive_product(_specification)
NOT_DISCLOSED = {"not disclosed", "not stated in sources"}      # a spec whose value is one of these (or empty) is not loaded
NEAR_UNDISCLOSED = ("not disclosed", "not published", "not stated", "not specified", "not available", "n/a", "unknown", "none published")
NO_DATA_NOTE = re.compile(r"^(technical\s+)?(specifications?|specs?|details?|data|parameters?)\s+(are\s+|is\s+)?(not|un)\s*(published|disclosed|available|stated|released)\b", re.I)
UNIT_RE = re.compile(r"^(-?\d[\d,]*(?:\.\d+)?)\s+([A-Za-zµμ°%][A-Za-z0-9µμ°%/.²³^*·-]{0,19})$")      # '<number> <one-token unit>', unit <= 20 chars
UNIT_NOT = {"x", "to", "and", "or", "per", "of", "with", "at", "by", "from", "on"}
QUOTE_DETAIL_MAX = 300
# {(competitor display_name, name of an existing product row): spec-sheet product name} - to keep a hand-made product (its id, matchups) when the
# sheet names the same product differently; empty = only the same normalised name keeps an id
PRODUCT_KEEP_ALIASES: dict[tuple[str, str], str] = {
    ("Larsen & Toubro", "K9 Vajra-T"): "K9 Vajra-T 155 mm/52 cal Tracked Self-Propelled Howitzer",
    ("Hanwha Aerospace", "K9 Thunder"): "K9 / K9A1 Thunder",
}


def product_id_for(competitor_id, name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "kssl-product|" + str(competitor_id) + "|" + name)


def spec_id_for(product_id, label: str, position: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"kssl-product-spec|{product_id}|{label}|{position}")


def norm_product(name: str) -> str:
    """casefold, every dash variant becomes a space, spaces collapsed: 'K9 Vajra-T' == 'k9  vajra t'."""
    s = re.sub(r"[-‐-―−]", " ", str(name or "").casefold())
    return re.sub(r"\s+", " ", s).strip()


def split_unit(value: str) -> tuple[str, str | None]:
    """(value, unit): the unit only when the value is exactly '<number> <unit>' ('17.6 km' -> ('17.6', 'km')); else the whole value, no unit."""
    m = UNIT_RE.match(value)
    if m and m.group(2).casefold() not in UNIT_NOT:
        return m.group(1), m.group(2)
    return value, None


def parse_spec_lines(cell) -> list[dict]:
    """Technical Specifications -> [{pos, label, value, unit, skip}] (pos = 1-based number of the non-blank line).
    'Label: value' splits at the FIRST colon; a line without a colon is label 'Note' with the line as value.  skip is None, 'empty',
    'not_disclosed' or 'label_too_long'."""
    out = []
    pos = 0
    for line in str(cell or "").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        pos += 1
        if ":" in line:
            label, value = (x.strip() for x in line.split(":", 1))
        else:
            label, value = "Note", line
        skip = None
        if not value or not label:
            skip = "empty"
        elif value.rstrip(". ").casefold() in NOT_DISCLOSED:
            skip = "not_disclosed"
        elif value.casefold().startswith(NEAR_UNDISCLOSED) or (label == "Note" and NO_DATA_NOTE.match(value)):
            skip = "not_disclosed"          # 'Not published', 'n/a', 'Specifications not published.': no value to show
        elif len(label) > PRODUCT_LIMITS["spec_label"]:
            skip = "label_too_long"
        unit = None
        if skip is None:
            value, unit = split_unit(value)
        out.append({"pos": pos, "label": label, "value": value, "unit": unit, "skip": skip})
    return out


def resolve_product_company(name: str, by_display: dict[str, dict]) -> dict | None:
    """The competitor ({id, display_name, country}) a spec-sheet company maps to, None when it maps to nothing."""
    disp = PRODUCT_COMPANY_MAP.get(name)
    if disp is not None:
        return by_display.get(disp)
    return {k.casefold(): v for k, v in by_display.items()}.get(name.casefold())


def product_rows(sheet_rows: list[dict]) -> list[dict]:
    missing = [h for h in PRODUCT_COLS if sheet_rows and h not in sheet_rows[0]]
    if missing:
        raise ValueError(f"sheet {SHEET_PRODUCTS!r} is missing columns: {missing}")
    out = []
    for r in sheet_rows:
        d = {h: clean_cell(r.get(h)) for h in PRODUCT_COLS}
        if d["Company"] and d["Product"]:
            out.append(d)
    return out


def build_products_plan(rows: list[dict], competitors: dict[str, dict], existing: list[dict]) -> dict:
    """competitors: display_name -> {id, display_name, country}.  existing: rows of competitive_product
    ({product_id, competitor_id, product_name}).  A product that already exists for the competitor under the same normalised name keeps
    its id (mode 'kept' = not created by this loader, 'reloaded' = created by it earlier); else the id is uuid5 (mode 'new')."""
    unmapped = sorted({r["Company"] for r in rows if resolve_product_company(r["Company"], competitors) is None})
    if unmapped:
        raise ValueError(f"spec-sheet companies that map to no competitor (nothing loaded): {unmapped}")
    by_comp = defaultdict(list)
    for e in existing:
        by_comp[str(e["competitor_id"])].append(e)
    groups: dict[tuple, dict] = {}
    order, warnings, merged, blocked_products = [], [], [], []
    for r in rows:
        comp = resolve_product_company(r["Company"], competitors)
        cid = str(comp["id"])
        key = (cid, norm_product(r["Product"]))
        raw_urls = list(dict.fromkeys(u.strip() for u in re.split(r"[\r\n]+", str(r["Source(s)"] or "")) if u.strip()))      # one URL per line (a URL may hold spaces)
        urls = split_blocked(raw_urls)[0]
        blocked_only = bool(raw_urls) and not urls          # every source of this row is on a blocked domain
        bad = [u for u in urls if not u.lower().startswith(("http://", "https://"))]
        if bad:
            warnings.append(f"{r['Company']} / {r['Product']}: non-http source token(s) {bad[:2]}")
        quote = f"Verification: {r['Verification']}; Confidence: {r['Confidence']}"
        if r["Verification detail"]:
            quote += " — " + r["Verification detail"][:QUOTE_DETAIL_MAX]
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"company": r["Company"], "comp": comp, "cid": cid, "name": r["Product"], "category": r["Category"],
                               "rows": [], "specs": [], "urls": [], "raw_urls": [], "quote": quote}
            order.append(key)
        else:
            merged.append((r["Company"], g["name"], r["Product"]))
            if r["Category"] != g["category"]:
                warnings.append(f"{r['Company']} / {g['name']}: merged duplicate has category {r['Category']!r}, kept {g['category']!r}")
        g["rows"].append(r)
        for u in urls:
            if u not in g["urls"]:
                g["urls"].append(u)
        g["raw_urls"] += raw_urls
        g["specs"].append({"urls": urls, "quote": quote, "blocked_only": blocked_only, "lines": parse_spec_lines(r["Technical Specifications"])})
    products = []
    for key in order:
        g = groups[key]
        if g["raw_urls"] and not g["urls"]:          # the product rests only on blocked sources: not loaded
            blocked_products.append((g["company"], g["name"]))
            continue
        cid = g["cid"]
        dn = g["comp"]["display_name"]
        match = sorted((e for e in by_comp.get(cid, []) if norm_product(PRODUCT_KEEP_ALIASES.get((dn, e["product_name"]), e["product_name"])) == key[1]),
                       key=lambda e: str(e["product_id"]))
        if match:
            e = match[0]
            pid = str(e["product_id"])
            mode = "reloaded" if pid == str(product_id_for(cid, e["product_name"])) else "kept"
        else:
            pid, mode = str(product_id_for(cid, g["name"])), "new"
        g["product_id"], g["mode"] = pid, mode
        specs, skipped, seen, n = [], [], set(), 0
        for blk in g["specs"]:
            for ln in blk["lines"]:
                n += 1
                reason = ln["skip"]
                if reason is None and blk["blocked_only"]:
                    reason = "blocked_source"
                if reason is None and len(g["rows"]) > 1:        # merged rows: an identical label + value is loaded once
                    if (ln["label"], ln["value"], ln["unit"]) in seen:
                        reason = "duplicate_after_merge"
                    seen.add((ln["label"], ln["value"], ln["unit"]))
                if reason:
                    skipped.append({"pos": n, "label": ln["label"], "value": ln["value"], "reason": reason})
                    continue
                specs.append({"spec_id": str(spec_id_for(pid, ln["label"], n)), "product_id": pid, "spec_label": ln["label"],
                              "spec_value": ln["value"], "unit": ln["unit"], "source_url": blk["urls"][0] if blk["urls"] else None,
                              "source_count": len(blk["urls"]), "urls": blk["urls"], "quote": blk["quote"], "pos": n})
        g["spec_rows"], g["skipped"] = specs, skipped
        products.append(g)
    counts = defaultdict(int)
    for g in products:
        counts[(g["cid"], g["category"])] += 1
    for g in products:
        g["category_count"] = counts[(g["cid"], g["category"])]
        for col, val in (("product_name", g["name"]), ("category", g["category"])):
            if len(val) > PRODUCT_LIMITS[col]:
                raise ValueError(f"{g['company']} / {g['name']}: {col} longer than {PRODUCT_LIMITS[col]}")
    return {"products": products, "merged": merged, "warnings": warnings, "blocked_products": blocked_products}


def apply_products_plan(conn, plan: dict, dry_run: bool) -> dict:
    """Replace the products of the competitors in the plan (see the module docstring); returns the counters."""
    from psycopg2.extras import execute_values
    from backend.sources import classify
    cur = conn.cursor()
    prods = plan["products"]
    cids = sorted({g["cid"] for g in prods})
    cur.execute("SELECT product_id::text AS pid, competitor_id::text AS cid, product_name FROM staging.competitive_product WHERE competitor_id = ANY(%s::uuid[])", (cids,))
    old = cur.fetchall()
    new_ids = {g["product_id"] for g in prods}
    managed = [o["pid"] for o in old if o["pid"] == str(product_id_for(o["cid"], o["product_name"]))]    # created by this loader
    stale = [p for p in managed if p not in new_ids]
    touched = sorted(set(managed) | {g["product_id"] for g in prods if g["mode"] == "kept"})
    res = {"stale_products": len(stale), "replaced_products": len(managed) - len(stale)}
    cur.execute("SELECT count(*) AS n FROM staging.competitive_matchup WHERE competitor_product_id = ANY(%s::uuid[])", (stale,))
    res["stale_matchups"] = cur.fetchone()["n"]
    cur.execute("SELECT spec_id::text AS sid FROM staging.competitive_product_specification WHERE product_id = ANY(%s::uuid[])", (touched,))
    old_specs = [r["sid"] for r in cur.fetchall()]
    cur.execute("DELETE FROM staging.fact_source WHERE (table_name = 'competitive_product' AND column_name = 'product_name' AND row_id = ANY(%s)) "
                "OR (table_name = 'competitive_product_specification' AND column_name = 'spec_value' AND row_id = ANY(%s))", (touched, old_specs))
    res["deleted_facts"] = cur.rowcount
    cur.execute("DELETE FROM staging.competitive_product_specification WHERE product_id = ANY(%s::uuid[])", (touched,))
    res["deleted_specs"] = cur.rowcount
    cur.execute("DELETE FROM staging.competitive_product WHERE product_id = ANY(%s::uuid[])", (managed,))
    rows = []
    for g in prods:
        country = g["comp"].get("country")
        if g["mode"] == "kept":
            cur.execute("UPDATE staging.competitive_product SET product_name = %s, category = %s, category_filter = %s, category_count = %s, "
                        "country = %s, is_collapsed = false WHERE product_id = %s", (g["name"], g["category"], g["category"], g["category_count"], country, g["product_id"]))
            if cur.rowcount != 1:
                raise RuntimeError(f"kept product {g['name']!r} not found exactly once: rolled back")
        else:
            rows.append((g["product_id"], g["cid"], g["name"], g["category"], g["category"], g["category_count"], country))
    execute_values(cur, "INSERT INTO staging.competitive_product (product_id, competitor_id, product_name, category, category_filter, "
                        "category_count, country, is_collapsed) VALUES %s", rows, template="(%s, %s, %s, %s, %s, %s, %s, false)")
    spec_rows = [(s["spec_id"], s["product_id"], s["spec_label"], s["spec_value"], s["unit"], s["source_url"], s["source_count"])
                 for g in prods for s in g["spec_rows"]]
    execute_values(cur, "INSERT INTO staging.competitive_product_specification (spec_id, product_id, spec_label, spec_value, unit, source_url, source_count) VALUES %s",
                   spec_rows, page_size=2000)
    tier_cache, tiers, facts = {}, defaultdict(int), []

    def tier_of(url, company):
        k = (url, company)
        if k not in tier_cache:
            tier_cache[k] = classify(url, company_domains(url, name_variants(company))) or "unlisted"
        return tier_cache[k]

    for g in prods:
        for u in g["urls"]:
            t = tier_of(u, g["company"])
            tiers[t] += 1
            facts.append(("competitive_product", g["product_id"], "product_name", u, t, g["quote"]))
        for s in g["spec_rows"]:
            for u in s["urls"]:
                t = tier_of(u, g["company"])
                tiers[t] += 1
                facts.append(("competitive_product_specification", s["spec_id"], "spec_value", u, t, s["quote"]))
    execute_values(cur, "INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at) VALUES %s",
                   facts, template="(%s, %s, %s, %s, %s, NULL, %s, now())", page_size=5000)
    res["descriptions"] = write_descriptions(cur, prods)
    res.update(products=len(prods), specs=len(spec_rows), facts=len(facts), tiers=dict(tiers), facts_product=sum(len(g["urls"]) for g in prods))
    if dry_run:
        conn.rollback()
    else:
        _requalify(conn)
        conn.commit()
    return res


def write_product_reports(plan: dict, res: dict, sheet_comp: dict, out_dir: Path, dry_run: bool, extra: dict) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prods = plan["products"]
    by = defaultdict(list)
    for g in prods:
        by[g["comp"]["display_name"]].append(g)
    reasons = ["empty", "not_disclosed", "label_too_long", "duplicate_after_merge", "blocked_source"]
    lines = [f"Products load summary ({'DRY RUN' if dry_run else 'loaded'})", "",
             f"{'competitor':38} {'products':>8} {'new':>5} {'kept':>5} {'reload':>6} {'specs':>7} " + " ".join(f"{r[:12]:>12}" for r in reasons) + "  categories", "-" * 190]
    tot = defaultdict(int)
    for disp in sorted(by):
        gs = by[disp]
        sk, modes, cats = defaultdict(int), defaultdict(int), defaultdict(int)
        for g in gs:
            modes[g["mode"]] += 1
            cats[g["category"]] += 1
            for s in g["skipped"]:
                sk[s["reason"]] += 1
        nspec = sum(len(g["spec_rows"]) for g in gs)
        lines.append(f"{disp[:38]:38} {len(gs):>8} {modes['new']:>5} {modes['kept']:>5} {modes['reloaded']:>6} {nspec:>7} "
                     + " ".join(f"{sk[r]:>12}" for r in reasons) + "  " + "; ".join(f"{c} {n}" for c, n in sorted(cats.items())))
        for k, v in (("products", len(gs)), ("new", modes["new"]), ("kept", modes["kept"]), ("reloaded", modes["reloaded"]), ("specs", nspec)):
            tot[k] += v
        for r in reasons:
            tot[r] += sk[r]
    lines += ["-" * 190, f"{'TOTAL':38} {tot['products']:>8} {tot['new']:>5} {tot['kept']:>5} {tot['reloaded']:>6} {tot['specs']:>7} " + " ".join(f"{tot[r]:>12}" for r in reasons), ""]
    lines += [f"competitors with products: {len(by)}; without products: " + (", ".join(extra["without_products"]) or "none"),
              f"units split off (value exactly '<number> <unit>'): {sum(1 for g in prods for s in g['spec_rows'] if s['unit'])} of {tot['specs']} loaded specs",
              f"loaded specs whose value starts with a near-'not disclosed' wording ('not published', 'not stated', 'n/a'...; NOT skipped): {extra['near_undisclosed']}",
              f"merged duplicate product rows (same company + normalised name): {len(plan['merged'])}",
              f"products not loaded because every source is on a blocked blog domain (blocked_source): {len(plan['blocked_products'])}"]
    lines += [f"  {c}: {n!r}" for c, n in plan["blocked_products"][:50]]
    lines += [f"  {c}: {a!r} + {b!r}" for c, a, b in plan["merged"][:50]]
    lines += ["", "columns NOT loaded (no column in the schema), non-empty cells: " + ", ".join(f"{k} {v}" for k, v in extra["unloaded"].items()),
              f"fact_source: {res['facts']} rows ({res['facts_product']} product_name, {res['facts'] - res['facts_product']} spec_value); tiers {res['tiers']}",
              f"replaced earlier loader rows: {res['replaced_products']} products, {res['deleted_specs']} specs, {res['deleted_facts']} fact_source; "
              f"stale products deleted {res['stale_products']} (matchups pointing at them: {res['stale_matchups']})"]
    if plan["warnings"]:
        lines += ["", f"warnings ({len(plan['warnings'])}):"] + ["  " + w for w in plan["warnings"][:100]]
    spath = out_dir / "products_summary.txt"
    spath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cpath = out_dir / "products_skipped.csv"
    with cpath.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["company", "product", "line_no", "spec_label", "spec_value", "reason"])
        for g in prods:
            for s in g["skipped"]:
                w.writerow([g["company"], g["name"], s["pos"], s["label"], s["value"], s["reason"]])
    npath = out_dir / "products_name_map.txt"
    nl = ["spec-sheet company -> competitor display_name (competitor_id)", ""]
    for name in sorted(sheet_comp):
        c = sheet_comp[name]
        nl.append(f"{name}  ->  {c['display_name']}  ({c['id']})" + ("   [explicit]" if name in PRODUCT_COMPANY_MAP else ""))
    nl += ["", "competitors with no products in the sheet: " + (", ".join(extra["without_products"]) or "none"), "",
           f"KNDS (KMW+Nexter) -> KNDS Germany: {extra['knds_total']} products, of which {extra['knds_overlap']} have a product of the same normalised name under Nexter (KNDS France) (both kept)"]
    npath.write_text("\n".join(nl) + "\n", encoding="utf-8")
    return [spath, cpath, npath]


def cmd_products(args) -> int:
    from prompts import batch
    sheets = read_sheets(Path(args.file), wanted=(SHEET_PRODUCTS,))
    if SHEET_PRODUCTS not in sheets:
        raise SystemExit(f"sheet {SHEET_PRODUCTS!r} not found")
    rows = product_rows(sheets[SHEET_PRODUCTS])
    conn = batch.connect_db(args.db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT competitor_id::text AS id, display_name, origin_country AS country FROM staging.competitive_competitor")
        comps = {r["display_name"]: {"id": r["id"], "display_name": r["display_name"], "country": r["country"]} for r in cur.fetchall()}
        cur.execute("SELECT product_id::text AS product_id, competitor_id::text AS competitor_id, product_name FROM staging.competitive_product")
        plan = build_products_plan(rows, comps, cur.fetchall())
        names = sorted({r["Company"] for r in rows})
        sheet_comp = {n: resolve_product_company(n, comps) for n in names}
        print("name map (spec sheet -> competitor):")
        for n in names:
            print(f"  {n}  ->  {sheet_comp[n]['display_name']}")
        used = {c["id"] for c in sheet_comp.values()}
        without = sorted(d for d, c in comps.items() if c["id"] not in used)
        by_comp = defaultdict(set)
        for g in plan["products"]:
            by_comp[g["comp"]["display_name"]].add(norm_product(g["name"]))
        knds = by_comp.get("KNDS Germany", set())
        unloaded = {h: sum(1 for r in rows if r[h]) for h in ("Description", "Collaboration / Partners", "Production & Licensing Notes")}
        near = sum(1 for g in plan["products"] for s in g["spec_rows"] if s["spec_value"].casefold().startswith(NEAR_UNDISCLOSED))
        extra = {"without_products": without, "knds_total": len(knds), "knds_overlap": len(knds & by_comp.get("Nexter (KNDS France)", set())),
                 "unloaded": unloaded, "near_undisclosed": near}
        res = apply_products_plan(conn, plan, args.dry_run)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    paths = write_product_reports(plan, res, sheet_comp, Path(args.reports), args.dry_run, extra)
    skipped, modes = defaultdict(int), defaultdict(int)
    for g in plan["products"]:
        modes[g["mode"]] += 1
        for s in g["skipped"]:
            skipped[s["reason"]] += 1
    print(("DRY RUN (rolled back)" if args.dry_run else "LOADED") + f": {res['products']} products {dict(modes)}, {res['specs']} specs, skipped {dict(skipped)}")
    print(f"  fact_source {res['facts']}  tiers {res['tiers']}  replaced {res['replaced_products']} products / {res['deleted_specs']} specs, stale deleted {res['stale_products']}")
    print(f"  competitors without products: {without}")
    print(f"  KNDS Germany products {len(knds)}, also under Nexter (KNDS France): {extra['knds_overlap']}")
    print(f"  not loaded (no column): {unloaded}; merged duplicate rows {len(plan['merged'])}; warnings {len(plan['warnings'])}; "
          f"products with only blocked sources (not loaded) {len(plan['blocked_products'])}")
    print("  reports: " + "\n           ".join(str(p) for p in paths))
    return 0


# ---- client products (sheet 'All Products' of the client's own portfolio workbook) ------------------------------------

# existing client_product name (normalised) -> sheet product name that keeps its id; empty = same name or whole-word prefix of the sheet name
CLIENT_KEEP_ALIASES: dict[str, str] = {}
CLIENT_LIMITS = {"product_name": 255, "category": 128, "spec_name": 150, "unit": 32, "source_label": 255}
CLIENT_PRIMARY_DOMAINS = ("kssl.in", "bharatforge.com", "kalyanigroup.com")
SRC_MARK = re.compile(r"\s*\[S(\d+(?:\s*[,;]\s*S?\d+)*)\]")


def description_text(cell) -> str | None:
    """A Description cell as plain text: one bullet per line (inline bullets split too), [S#] source marks dropped, repeats once."""
    lines = (SRC_MARK.sub("", b).strip() for part in str(cell or "").split("•") for b in split_bullets(part))
    return "\n".join(dict.fromkeys(l for l in lines if l)) or None


def write_descriptions(cur, prods: list[dict], client: bool = False) -> int:
    """description of every planned product from its sheet row(s) (merged rows: their lines in sheet order); returns how many got one."""
    from psycopg2.extras import execute_batch
    rows = [(description_text("\n".join(str(r["Description"] or "") for r in g.get("rows") or [g["row"]])), g["product_id"]) for g in prods]
    sql = ("UPDATE staging.client_product SET description = %s WHERE client_product_id = %s" if client
           else "UPDATE staging.competitive_product SET description = %s WHERE product_id = %s")
    execute_batch(cur, sql, rows, page_size=1000)
    return sum(1 for d, _ in rows if d)


def cmd_descriptions(args) -> int:
    """Descriptions only (no spec, source or product row is replaced, so specs added by prompts stay): the competitor workbook, or with
    --client the client's own portfolio workbook. Same sheet and product matching as 'products' / 'client-products'."""
    from prompts import batch
    rows = product_rows(read_sheets(Path(args.file), wanted=(SHEET_PRODUCTS,))[SHEET_PRODUCTS])
    conn = batch.connect_db(args.db)
    try:
        cur = conn.cursor()
        if args.client:
            names = sorted({r["Company"] for r in rows})
            cur.execute("SELECT client_id, client_name, brand_name, legal_name FROM staging.client_account")
            hit = [r for r in cur.fetchall() if len(names) == 1 and names[0].casefold() in {str(r[k] or "").casefold() for k in ("client_name", "brand_name", "legal_name")}]
            if len(hit) != 1:
                raise SystemExit(f"the sheet must hold ONE company that matches one staging.client_account row, found {names}")
            client = {"client_id": hit[0]["client_id"], "name": hit[0]["client_name"]}
            cur.execute("SELECT client_product_id, product_name FROM staging.client_product WHERE client_id = %s", (client["client_id"],))
            plan = build_client_plan(rows, client, cur.fetchall())
            prods = [g for g in plan["products"] if g["mode"] == "kept"]              # a product not loaded yet gets its text with client-products
        else:
            cur.execute("SELECT competitor_id::text AS id, display_name, origin_country AS country FROM staging.competitive_competitor")
            comps = {r["display_name"]: {"id": r["id"], "display_name": r["display_name"], "country": r["country"]} for r in cur.fetchall()}
            cur.execute("SELECT product_id::text AS product_id, competitor_id::text AS competitor_id, product_name FROM staging.competitive_product")
            have = cur.fetchall()
            plan = build_products_plan(rows, comps, have)
            ids = {str(e["product_id"]) for e in have}
            prods = [g for g in plan["products"] if g["product_id"] in ids]
        n = write_descriptions(cur, prods, client=args.client)
        (conn.rollback if args.dry_run else conn.commit)()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(("DRY RUN (rolled back)" if args.dry_run else "LOADED") + f": {n} of {len(prods)} existing products got a description "
          f"({len(rows)} sheet rows; products not in the database are left to the full loader)")
    return 0
BULLET_START = re.compile("^[\\s•�·*]+|^-\\s+")
GROUP_RULES = (
    ("Mobility", re.compile(r"\b(road|speed|engine|power|weight|mass|gradient|gradeability|drive)\b", re.I)),
    ("Performance", re.compile(r"\b(range|rate|velocity|elevation|traverse|time|accuracy|firing|burst)\b", re.I)),
    ("Physical", re.compile(r"\b(calibre|caliber|barrel|length|width|height|crew|dimensions?|diameter)\b", re.I)),
)
PUBLISHERS = {"kssl.in": "KSSL", "bharatforge.com": "Bharat Forge", "kalyanigroup.com": "Kalyani Group", "pib.gov.in": "PIB",
              "drdo.gov.in": "DRDO", "mod.gov.in": "Ministry of Defence", "armyrecognition.com": "Army Recognition", "janes.com": "Janes",
              "army-technology.com": "Army Technology", "ajaishukla.com": "Ajai Shukla (Broadsword)", "frontierindia.com": "Frontier India",
              "thehindu.com": "The Hindu", "defensenews.com": "Defense News", "livemint.com": "Mint", "business-standard.com": "Business Standard",
              "idrw.org": "IDRW", "spslandforces.com": "SP's Land Forces", "forceindia.net": "Force India", "defence-industry.eu": "Defence-Industry.eu",
              "breakingdefense.com": "Breaking Defense", "economictimes.indiatimes.com": "Economic Times", "rafael.co.il": "Rafael", "fnherstal.com": "FN Herstal"}


def client_id_for(kind: str, *parts) -> int:
    """Deterministic 63-bit id (same hash as prompts.loader.make_id for a bigint column)."""
    from prompts.loader import make_id
    return make_id("bigint", "kssl-client-" + kind + "|" + "|".join(str(p) for p in parts))


def spec_group(label: str) -> str:
    for name, rx in GROUP_RULES:
        if rx.search(label):
            return name
    return "Other"


def source_type_of(text: str | None) -> str | None:
    t = (text or "").casefold()
    if not t.strip():
        return None
    if "manufactur" in t or "company" in t or "kssl" in t:
        return "manufacturer"
    if "partner" in t or "jv" in t or "joint" in t:
        return "partner"
    if "gov" in t or "mod" in t or "drdo" in t or "pib" in t:
        return "government"
    return "defence_press"


def publisher_of(url: str) -> str:
    from backend.sources import host_of
    host = host_of(url)
    for dom, name in PUBLISHERS.items():
        if host == dom or host.endswith("." + dom):
            return name
    return host or url[:60]


def numeric_of(value: str | None, unit: str | None) -> Decimal | None:
    """value_numeric only for an exact '<number> <unit>' value (split_unit gave a unit)."""
    if unit is None or value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except Exception:
        return None


def parse_client_specs(cell) -> list[dict]:
    """parse_spec_lines + the '[S#]' footnotes: [{pos, label, value, unit, skip, src, group}] (src = 1-based indexes into Source(s), in order of appearance)."""
    lines, srcs = [], []
    for line in str(cell or "").replace("\r", "\n").split("\n"):
        line = BULLET_START.sub("", line.strip()).strip()
        if not line:
            continue
        nums = [int(n) for m in SRC_MARK.finditer(line) for n in re.findall(r"\d+", m.group(1))]
        line = SRC_MARK.sub("", line).strip()
        if line:
            lines.append(line)
            srcs.append(list(dict.fromkeys(nums)))
    out = parse_spec_lines("\n".join(lines))
    for ln, src in zip(out, srcs):
        ln["src"] = src
        if ln["skip"] is None:
            ln["group"] = spec_group(ln["label"])
    return out


def build_client_plan(rows: list[dict], client: dict, existing: list[dict]) -> dict:
    """rows: product_rows() of the sheet (all one company).  client: {client_id, name}.  existing: client_product rows of that client
    ({client_product_id, product_name}).  Returns {'products': [...], 'warnings': [...], 'stale': [existing rows no longer in the sheet that this loader created]}."""
    from backend.sources import is_wiki
    cid = client["client_id"]
    groups: dict[str, dict] = {}
    order, warnings = [], []
    for r in rows:
        key = norm_product(r["Product"])
        urls = list(dict.fromkeys(u.strip() for u in re.split(r"[\r\n]+", str(r["Source(s)"] or "")) if u.strip()))
        wiki = [u for u in urls if is_wiki(u)]
        if wiki:
            raise ValueError(f"{r['Product']}: wiki source {wiki[0]!r}: nothing loaded")
        bad = [u for u in urls if not u.lower().startswith(("http://", "https://"))]
        if bad:
            raise ValueError(f"{r['Product']}: non-http source token(s) {bad[:2]}")
        types = [t.strip() for t in re.split(r"[\r\n]+", str(r["Source Type"] or "")) if t.strip()]
        types_all = [types[i] if i < len(types) else (types[0] if len(types) == 1 else None) for i in range(len(urls))]
        n_raw = len(urls)                                    # [S#] footnotes count the lines of the original Source(s) cell
        kept = set(split_blocked(urls)[0])
        kept_idx = [i for i, u in enumerate(urls, 1) if u in kept]
        urls, types = [urls[i - 1] for i in kept_idx], [types_all[i - 1] for i in kept_idx]
        if key in groups:
            raise ValueError(f"duplicate product name in the sheet: {r['Product']!r}")
        quote = f"Verification: {r['Verification']}; Confidence: {r['Confidence']}"
        if r["Verification detail"]:
            quote += " — " + r["Verification detail"][:QUOTE_DETAIL_MAX]
        groups[key] = {"name": r["Product"], "category": r["Category"], "row": r, "urls": urls, "quote": quote, "types": types,
                       "n_raw": n_raw, "kept_idx": kept_idx}
        order.append(key)
        if n_raw and not urls:
            warnings.append(f"{r['Product']}: every source is on a blocked domain (specs skipped as blocked_source, product loaded without sources)")
        elif not urls:
            warnings.append(f"{r['Product']}: no source URL (specs get no source)")
    # keep ids of existing products: exact normalised name (or alias) first, then whole-word prefix; each existing id once
    taken, assign = set(), {}
    ex = sorted(existing, key=lambda e: int(e["client_product_id"]))
    for e in ex:
        en = norm_product(e["product_name"])
        want = norm_product(CLIENT_KEEP_ALIASES[en]) if en in CLIENT_KEEP_ALIASES else en
        if want in groups and want not in assign:
            assign[want] = e
            taken.add(int(e["client_product_id"]))
    for e in ex:
        if int(e["client_product_id"]) in taken:
            continue
        en = norm_product(e["product_name"])
        for key in order:
            if key not in assign and key.startswith(en + " "):
                assign[key] = e
                taken.add(int(e["client_product_id"]))
                break
    products = []
    for key in order:
        g = groups[key]
        e = assign.get(key)
        if e:
            g["product_id"], g["mode"] = int(e["client_product_id"]), "kept"
        else:
            g["product_id"], g["mode"] = client_id_for("product", cid, key), "new"
        pid = g["product_id"]
        g["sources"] = [{"source_id": client_id_for("source", pid, u), "url": u, "source_type": source_type_of(t), "label": None}
                        for u, t in zip(g["urls"], g["types"])]
        by_idx = dict(zip(g["kept_idx"], g["sources"]))          # 1-based line of the original Source(s) cell -> kept source
        for s in g["sources"]:
            s["label"] = (publisher_of(s["url"]) + (" - " + s["source_type"].replace("_", " ") if s["source_type"] else ""))[:CLIENT_LIMITS["source_label"]]
        specs, skipped = [], []
        for ln in parse_client_specs(g["row"]["Technical Specifications"]):
            reason = ln["skip"]
            bad_src = [i for i in ln["src"] if not 1 <= i <= g["n_raw"]]
            if bad_src:
                raise ValueError(f"{g['name']}: line {ln['pos']} cites [S{bad_src[0]}] but Source(s) has {g['n_raw']} URLs")
            used = [by_idx[i] for i in ln["src"] if i in by_idx] or ([] if ln["src"] else g["sources"][:1])
            if reason is None and not used and g["n_raw"]:       # every source of this line is on a blocked domain
                reason = "blocked_source"
            if reason:
                skipped.append({"pos": ln["pos"], "label": ln["label"], "value": ln["value"], "reason": reason})
                continue
            specs.append({"specification_id": client_id_for("spec", pid, ln["label"], ln["pos"]), "client_product_id": pid,
                          "spec_name": ln["label"], "value_text": ln["value"], "value_numeric": numeric_of(ln["value"], ln["unit"]),
                          "unit": ln["unit"], "spec_group": ln["group"], "display_order": ln["pos"],
                          "source_id": used[0]["source_id"] if used else None, "source_urls": [u["url"] for u in used], "quote": g["quote"]})
        g["spec_rows"], g["skipped"] = specs, skipped
        for col, val in (("product_name", g["name"]), ("category", g["category"])):
            if len(val) > CLIENT_LIMITS[col]:
                raise ValueError(f"{g['name']}: {col} longer than {CLIENT_LIMITS[col]}")
        products.append(g)
    new_ids = {g["product_id"] for g in products}
    stale = [e for e in existing if int(e["client_product_id"]) not in new_ids
             and int(e["client_product_id"]) == client_id_for("product", cid, norm_product(e["product_name"]))]      # created by this loader
    return {"products": products, "warnings": warnings, "stale": stale}


def apply_client_plan(conn, plan: dict, client: dict, dry_run: bool) -> dict:
    from psycopg2.extras import execute_values
    from backend.sources import classify
    cur = conn.cursor()
    prods = plan["products"]
    touched = sorted({g["product_id"] for g in prods} | {int(e["client_product_id"]) for e in plan["stale"]})
    cur.execute("SELECT specification_id::text AS sid FROM staging.client_product_specification WHERE client_product_id = ANY(%s)", (touched,))
    old_specs = [r["sid"] for r in cur.fetchall()]
    cur.execute("DELETE FROM staging.fact_source WHERE (table_name = 'client_product' AND column_name = 'product_name' AND row_id = ANY(%s)) "
                "OR (table_name = 'client_product_specification' AND column_name = 'value_text' AND row_id = ANY(%s))",
                ([str(i) for i in touched], old_specs))
    res = {"deleted_facts": cur.rowcount}
    cur.execute("DELETE FROM staging.client_product_specification WHERE client_product_id = ANY(%s)", (touched,))
    res["deleted_specs"] = cur.rowcount
    cur.execute("DELETE FROM staging.client_product_source WHERE client_product_id = ANY(%s)", (touched,))
    res["deleted_sources"] = cur.rowcount
    stale_ids = [int(e["client_product_id"]) for e in plan["stale"]]
    cur.execute("SELECT count(*) AS n FROM staging.competitive_matchup WHERE client_product_id = ANY(%s)", (stale_ids,))
    res["stale_matchups"] = cur.fetchone()["n"]
    cur.execute("DELETE FROM staging.client_product WHERE client_product_id = ANY(%s)", (stale_ids,))
    res["stale_products"] = cur.rowcount
    for g in prods:
        first = g["sources"][0]["source_id"] if g["sources"] else None
        if g["mode"] == "kept":
            cur.execute("UPDATE staging.client_product SET product_name = %s, category = %s, source_id = %s, updated_at = now() "
                        "WHERE client_product_id = %s AND client_id = %s", (g["name"], g["category"], first, g["product_id"], client["client_id"]))
            if cur.rowcount != 1:
                raise RuntimeError(f"kept product {g['name']!r} not found exactly once: rolled back")
        else:
            cur.execute("INSERT INTO staging.client_product (client_product_id, client_id, product_name, category, source_id, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, now(), now()) ON CONFLICT DO NOTHING", (g["product_id"], client["client_id"], g["name"], g["category"], first))
            if cur.rowcount != 1:
                raise RuntimeError(f"id collision for new product {g['name']!r}: rolled back")
    execute_values(cur, "INSERT INTO staging.client_product_source (client_product_id, source_id, source_label, source_type, source_url, published_date) VALUES %s",
                   [(g["product_id"], s["source_id"], s["label"], s["source_type"], s["url"], None) for g in prods for s in g["sources"]])
    spec_rows = [(s["specification_id"], s["client_product_id"], s["spec_name"], s["value_text"], s["value_numeric"], s["unit"], s["spec_group"],
                  s["display_order"], s["source_id"]) for g in prods for s in g["spec_rows"]]
    execute_values(cur, "INSERT INTO staging.client_product_specification (specification_id, client_product_id, spec_name, value_text, value_numeric, unit, "
                        "spec_group, display_order, source_id) VALUES %s", spec_rows, page_size=2000)
    tier_cache, tiers, facts = {}, defaultdict(int), []

    def tier_of(url):
        if url not in tier_cache:
            tier_cache[url] = classify(url, CLIENT_PRIMARY_DOMAINS) or "unlisted"
        return tier_cache[url]

    for g in prods:
        for u in g["urls"]:
            tiers[tier_of(u)] += 1
            facts.append(("client_product", str(g["product_id"]), "product_name", u, tier_of(u), g["quote"]))
        for s in g["spec_rows"]:
            for u in s["source_urls"]:
                tiers[tier_of(u)] += 1
                facts.append(("client_product_specification", str(s["specification_id"]), "value_text", u, tier_of(u), s["quote"]))
    execute_values(cur, "INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at) VALUES %s",
                   facts, template="(%s, %s, %s, %s, %s, NULL, %s, now())", page_size=5000)
    res["descriptions"] = write_descriptions(cur, prods, client=True)
    res.update(products=len(prods), specs=len(spec_rows), sources=sum(len(g["sources"]) for g in prods), facts=len(facts), tiers=dict(tiers))
    if dry_run:
        conn.rollback()
    else:
        _requalify(conn)
        conn.commit()
    return res


def write_client_reports(plan: dict, res: dict, client: dict, out_dir: Path, dry_run: bool) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prods = plan["products"]
    cats = defaultdict(lambda: [0, 0])
    for g in prods:
        cats[g["category"]][0] += 1
        cats[g["category"]][1] += 1 if g["spec_rows"] else 0
    lines = [f"Client products load summary ({'DRY RUN' if dry_run else 'loaded'}) - client {client['name']} (client_id {client['client_id']})", "",
             f"products {res['products']} ({sum(1 for g in prods if g['mode'] == 'kept')} kept id, {sum(1 for g in prods if g['mode'] == 'new')} new); "
             f"specs {res['specs']}; sources {res['sources']}; fact_source {res['facts']} tiers {res['tiers']}",
             f"replaced: {res['deleted_specs']} specs, {res['deleted_sources']} sources, {res['deleted_facts']} fact_source; stale products deleted {res['stale_products']} "
             f"(matchups pointing at them: {res['stale_matchups']})", "", f"{'category':36} {'products':>8} {'with specs':>10}", "-" * 58]
    lines += [f"{c[:36]:36} {n:>8} {w:>10}" for c, (n, w) in sorted(cats.items())]
    lines += ["", f"units split off: {sum(1 for g in prods for s in g['spec_rows'] if s['unit'])} of {res['specs']} specs; "
                  f"spec groups: {dict(sorted(Counter(s['spec_group'] for g in prods for s in g['spec_rows']).items()))}",
              "", "per product (id, mode, specs, skipped lines, sources):"]
    lines += [f"  {g['product_id']} {g['mode']:5} {len(g['spec_rows']):>3} {len(g['skipped']):>3} {len(g['sources']):>2}  [{g['category']}] {g['name']}" for g in prods]
    if plan["warnings"]:
        lines += ["", f"warnings ({len(plan['warnings'])}):"] + ["  " + w for w in plan["warnings"]]
    spath = out_dir / "client_products_summary.txt"
    spath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cpath = out_dir / "client_products_skipped.csv"
    with cpath.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["product", "line_no", "spec_label", "spec_value", "reason"])
        for g in prods:
            for s in g["skipped"]:
                w.writerow([g["name"], s["pos"], s["label"], s["value"], s["reason"]])
    return [spath, cpath]


def cmd_client_products(args) -> int:
    from prompts import batch
    sheets = read_sheets(Path(args.file), wanted=(SHEET_PRODUCTS,))
    if SHEET_PRODUCTS not in sheets:
        raise SystemExit(f"sheet {SHEET_PRODUCTS!r} not found")
    rows = product_rows(sheets[SHEET_PRODUCTS])
    names = sorted({r["Company"] for r in rows})
    if len(names) != 1:
        raise SystemExit(f"the sheet must hold ONE client company, found {names}")
    conn = batch.connect_db(args.db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT client_id, client_name, brand_name, legal_name FROM staging.client_account")
        hit = [r for r in cur.fetchall() if names[0].casefold() in {str(r[k] or "").casefold() for k in ("client_name", "brand_name", "legal_name")}]
        if len(hit) != 1:
            raise SystemExit(f"company {names[0]!r} matches {len(hit)} staging.client_account rows (need exactly 1)")
        client = {"client_id": hit[0]["client_id"], "name": hit[0]["client_name"]}
        cur.execute("SELECT client_product_id, product_name FROM staging.client_product WHERE client_id = %s", (client["client_id"],))
        plan = build_client_plan(rows, client, cur.fetchall())
        res = apply_client_plan(conn, plan, client, args.dry_run)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    paths = write_client_reports(plan, res, client, Path(args.reports), args.dry_run)
    modes = Counter(g["mode"] for g in plan["products"])
    print(("DRY RUN (rolled back)" if args.dry_run else "LOADED") + f": {res['products']} products {dict(modes)}, {res['specs']} specs, {res['sources']} sources, "
          f"skipped lines {sum(len(g['skipped']) for g in plan['products'])}")
    print(f"  fact_source {res['facts']}  tiers {res['tiers']}  replaced {res['deleted_specs']} specs / {res['deleted_sources']} sources, stale deleted {res['stale_products']}")
    print(f"  warnings {len(plan['warnings'])}")
    print("  reports: " + "\n           ".join(str(p) for p in paths))
    return 0


# ---- selftest -------------------------------------------------------------------------------------------------

def _selftest() -> None:
    # bullet splitting
    assert split_bullets("• One.\n• • Two  words\n� Three\n- Four\n* Five\n\n  ") == ["One.", "Two words", "Three", "Four", "Five"]
    assert split_bullets(None) == [] and split_bullets("") == []
    # initials
    assert initials("Asha Rao") == "AR" and initials("Dr Jane Example") == "JE" and initials("Gen. Mark A. Milley") == "MM"
    assert initials("Shri Rajesh Kumar Singh") == "RS" and initials("Adm John Smith") == "JS" and initials("Madonna") == "M"
    assert initials("Lt Gen Anil Chauhan") == "AC" and initials("Prof. Dr. Ali Veli") == "AV" and initials("Éric Trappier") == "ÉT"
    # claim matching
    assert norm_text("  Hello,   World. ") == "hello, world"
    assert containment("Became KNDS France CEO on 5 January 2026", "Became KNDS France CEO on 5 January 2026 and also serves as EVP.") == 1.0
    assert containment("CEO of Pandrol 2023-2025", "Previously served as CEO of Pandrol (2023–2025).") == 1.0
    assert containment("Saïd Business School Oxford 2015", "Strategic Leadership programme, Said Business School, University of Oxford (2015–2016).") == 1.0
    assert containment("Plant Manager 2007-2010", "General Manager (2010–2013) and Plant Manager (2007–2010)") == 1.0
    assert containment("Faurecia Quality Manager 2004-2007", "Earlier served at Johnson Controls (2010–2013)") < 0.35
    bullets = ["Joined Wegmann in 1995 as Head of Systems Technology.", "Became Head of System Development in January 2004.", "Lecturing at Kassel."]
    cl = [Claim("Joined Wegmann in 1995", True, "Supported"), Claim("Joined as Head of Systems Technology", False, "Not established"),
          Claim("Head of System Development from January 2004", False, "Not established"), Claim("Lecturing experience at Kassel", True, "Supported"),
          Claim("Became chairman of the moon", False, "Not established")]
    sup, uns, orph = match_bullets(bullets, cl)
    assert [len(x) for x in sup] == [1, 0, 1] and [len(x) for x in uns] == [1, 1, 0], (sup, uns)
    assert orph == [cl[4]]
    assert uncovered_years("CEO of BMA (2018–2023), began in 1998.", [Claim("Began in 1998", True, "Supported")]) == ["2018", "2023"]
    assert uncovered_years("Joined in 1995.", [Claim("Joined 1995", True, "Supported")]) == []
    # Pass 2 verdicts: a Supported verdict replaces the Not established evidence claim it re-checked; others stay out
    ce = [{"Input Row": 5, "Field": "Professional Experience", "Claim": "Director of Roanne site 2006-2009", "Result": "Not established",
           "Source URL": "http://a.example/x", "Quote": "q", "Quote check": "no quote"},
          {"Input Row": 5, "Field": "Professional Experience", "Claim": "Joined in 1995", "Result": "Supported", "Source URL": "http://b.example/y",
           "Quote": "joined 1995", "Quote check": "verbatim in source"}]
    p2 = [{"Input Row": 5, "Field": "experience", "Claim": "Director of Roanne site (claimed 2006-2009)", "Accepted verdict": "Supported",
           "Source URL": "http://c.example/z\nhttp://d.example", "Quote": "roanne", "Quote check": None, "Correct value (if contradicted)": "dates not stated"}]
    cs = build_claims(ce, p2)[(5, "experience")]
    assert sorted((c.text, c.supported) for c in cs) == [("Director of Roanne site (claimed 2006-2009)", True), ("Joined in 1995", True)], cs
    assert [c for c in cs if c.origin == "Pass 2 Results"][0].evidence == [("http://c.example/z", "roanne", None)]
    # ids are deterministic and distinct
    c1 = competitor_id_for("Acme Corp")
    assert c1 == competitor_id_for("Acme Corp") != competitor_id_for("Acme Corp.")
    l1 = leader_id_for(c1, "A B")
    assert l1 == leader_id_for(str(c1), "A B") != leader_id_for(c1, "A C")
    assert record_id_for(l1, "experience", 1) == record_id_for(str(l1), "experience", 1)
    assert len({record_id_for(l1, "experience", 1), record_id_for(l1, "education", 1), record_id_for(l1, "experience", 2)}) == 3
    # a tiny end-to-end plan
    sheets = {SHEET_DIR: [{"Company Name": "Larsen & Toubro (L&T)", "People Name": "Dr Jane Example", "Current Position": "CTO",
                           "Professional Experience": "• Joined Wegmann in 1995 as Head.\n• Became head of R&D in 2009.", "Education Background": "• Diplom, Kassel.",
                           "Source URL": "http://s.example/1\nhttp://s.example/2"}],
              SHEET_SUM: [{"Input Row": "2.0", "Company": "Larsen & Toubro (L&T)", "Person": "Dr Jane Example", "FINAL Position": "Verified (pass 2)",
                           "FINAL Experience": "Not Found", "FINAL Education": "Mismatch", "Position Note": "n", "LinkedIn URL": None}],
              SHEET_CE: [{"Input Row": 2, "Field": "Current Position", "Claim": "CTO", "Result": None, "Source URL": "http://p.example", "Quote": "cto", "Quote check": "verbatim in source"},
                         {"Input Row": 2, "Field": "Professional Experience", "Claim": "Joined Wegmann in 1995", "Result": "Supported", "Source URL": "http://e.example", "Quote": "1995", "Quote check": "verbatim in source"},
                         {"Input Row": 2, "Field": "Education Background", "Claim": "Diplom Kassel", "Result": "Contradicted", "Source URL": "http://f.example", "Quote": "x", "Quote check": None, "Fix / caveat": "it was Hannover"}],
              SHEET_P2: [], SHEET_APPLIED: []}
    p = build_plan(sheets, {"Larsen & Toubro": "11111111-1111-1111-1111-111111111111"})
    assert p.competitors[0]["id"] == "11111111-1111-1111-1111-111111111111" and p.competitors[0]["existing"]
    assert p.leaders[0]["role_title"] == "CTO" and p.leaders[0]["avatar_initials"] == "JE" and p.leaders[0]["role_source_url"] == "http://p.example"
    assert [r["headline"] for r in p.records] == ["Joined Wegmann in 1995 as Head."] and p.records[0]["source_url"] == "http://e.example"
    assert [h["field"] for h in p.held] == ["Professional Experience", "Education Background"] and p.held[1]["reason"].count("Contradicted") == 1
    assert p.held[1]["suggested_correction"] == "it was Hannover"
    assert [r["record_id"] for r in p.records] == [r["record_id"] for r in build_plan(sheets, {"Larsen & Toubro": "11111111-1111-1111-1111-111111111111"}).records]
    # company details: year / count / revenue parsers (fictional values)
    assert parse_year("1889")[0] == 1889 and parse_year("3 Mar 2019 incorporation; operations began 1 Jun 2019")[0] == 2019
    assert parse_year("2015 formed; renamed in 2016")[0] is None and parse_year("Founded long ago")[0] is None
    assert parse_year("1937 roots / current Foo business")[0] == 1937 and parse_year("2015-2017 build-out")[0] is None
    assert clean_cell(datetime(1980, 2, 5)) == "5 Feb 1980" and clean_cell("  x \n") == "x" and clean_cell("  ") is None
    for ok, n in (("8,765 employees (31 Mar 2030)", 8765), ("2,300 employees", 2300), ("6,543 employees (2030)", 6543), ("5,432 personnel at end-2030", 5432),
                  ("1,234 employees as on 31 Mar 2030", 1234), ("9,999 employees (Fortune Global 500, 2025)", 9999), ("321 average employees", 321),
                  ("7,659 employees at 31 Dec 2024 (latest count located in reporting)", 7659), ("5406", 5406)):
        assert parse_employees(ok)[0] == n, ok
    for bad in ("More than 7,000 employees", "Over 12,000 employees (2030 disclosure; ~11,000 in 2029)", "Approximately 54,000 employees", "6000+ employees",
                "11–50 employees", "2,001–4,000 employees; LinkedIn shows ~1,111 profiles", "1,100 – 1,300+ Employees", "~700+ Employees",
                "Not publicly disclosed", "11,400 employees (31 Dec 2025, including share of investments)", "100 total: 12 regular + 88 deputation",
                "Parent Corp: 12,300 employees", "22,111 employees at 31 Dec 2030; 23,000 in mid-2031", "up to 300 staff", "1,200 employees, group-wide"):
        assert parse_employees(bad)[0] is None, bad
    D = Decimal
    assert parse_revenue("₹1,23,456 Crore")[:2] == (D(123456) * 10 ** 7, "INR")
    assert parse_revenue("₹1,234.50 crore turnover")[:2] == (D("12345000000"), "INR")
    assert parse_revenue("Rs 12 lakh sales")[:2] == (D(1200000), "INR") and parse_revenue("INR 5 Cr")[:2] == (D(50000000), "INR")
    assert parse_revenue("€2,345.6 million net sales")[:2] == (D("2345600000"), "EUR")
    assert parse_revenue("£3.141 billion revenue")[:2] == (D("3141000000"), "GBP")
    assert parse_revenue("US$12.3456 billion revenue (Fortune Global 500)")[:2] == (D("12345600000"), "USD")
    assert parse_revenue(" $123.4 million")[:2] == (D("123400000"), "USD") and parse_revenue("USD 2 billion")[1] == "USD"
    assert parse_revenue("KRW 2.25 Trillion revenue")[:2] == (D("2250000000000"), "KRW") and parse_revenue("₩3 trillion")[1] == "KRW"
    assert parse_revenue("NOK 9.87 billion revenue")[1] == "NOK" and parse_revenue("SEK 7 billion")[1] == "SEK" and parse_revenue("PLN 6.0 billion revenue")[1] == "PLN"
    assert parse_revenue("TL 12.34 billion revenue")[1] == "TRY" and parse_revenue("NIS 3 billion sales")[1] == "ILS" and parse_revenue("TRY 9 million")[1] == "TRY"
    assert parse_revenue("€7.2 billion revenue (€7.215 billion)")[:2] == (D("7215000000"), "EUR")      # same figure twice -> the precise one
    assert parse_revenue("€7.215 billion revenue (€7.2 billion)")[0] == D("7215000000")
    for bad in ("£9.9 billion sales (IFRS revenue £8.765 billion)", "€1.3 billion — Foo segment revenue", "Approx. NIS 11.1 billion / US$3.21 billion sales",
                "₹10 - ₹50 Cr as on Mar 31", "Not publicly disclosed — privately held", "Corp segment sales: US$2.0967 billion", "about €2 billion",
                "NOK 44.4 billion total legacy-group revenue; segment NOK 12.34 billion", "Revenue grew 70% yoy", "€1 billion parent revenue"):
        assert parse_revenue(bad)[0] is None, bad
    # company plan: mapping, text kept verbatim, facts, qualifier -> NULL
    rows = company_rows([{**{h: None for h in COMPANY_COLS}, "Company": "Larsen & Toubro (L&T)", "Country / Region": "India", "Source Entity Label": "Foo Ltd",
                          "Starting Year / Corporate Origin": datetime(1938, 1, 2), "Headquarters": "Nowhere", "Company Size": "Over 100 employees",
                          "Annual Revenue / Sales": "₹5 crore revenue", "Financial Year": "FY2025", "Sources": "http://a.example/x\nhttp://a.example/x http://b.example"},
                         {**{h: None for h in COMPANY_COLS}, "Company": "Acme Corp", "Company Size": "250 employees"}])
    cp = build_company_plan(rows, {"Larsen & Toubro": "11111111-1111-1111-1111-111111111111"})
    a, b = cp["items"]
    assert a["comp"]["id"] == "11111111-1111-1111-1111-111111111111" and a["comp"]["display_name"] == "Larsen & Toubro"
    assert b["comp"]["id"] == str(competitor_id_for("Acme Corp")) and not b["comp"]["existing"]
    assert a["vals"]["starting_year_text"] == "2 Jan 1938" and a["vals"]["starting_year"] == 1938 and a["vals"]["employee_count"] is None
    assert a["vals"]["employee_count_text"] == "Over 100 employees" and a["vals"]["annual_revenue"] == D(50000000) and a["vals"]["revenue_currency"] == "INR"
    assert b["vals"]["employee_count"] == 250 and b["vals"]["annual_revenue"] is None and b["facts"] == []
    rq = [f["quote"] for f in a["facts"] if f["column_name"] == "annual_revenue"]
    assert rq == ["₹5 crore revenue [entity: Foo Ltd; FY2025]"] * 2, rq
    assert sorted({f["column_name"] for f in a["facts"]}) == sorted(c for c in COMPANY_FACT_COLS if c not in ("employee_count", "industry_sector"))
    # leadership cross-check
    assert same_person("Dr John Example CBE", "John Example") and not same_person("Jane Roe", "John Roe")
    xi = {"company": "Acme", "src": {"ceo": "Dr Ann Example — Group CEO", "chairman": "Bob Builder -Chairman of Acme", "board": "• Cy Dee — CFO\n• Public-private ownership note"}}
    xr = crosscheck(xi, [{"full_name": "Ann Example", "role_title": "Chair"}, {"full_name": "Eve Fake", "role_title": "CTO"}])
    assert sorted((r["difference"], r["name"]) for r in xr) == [("in Excel, not in leaders", "Bob Builder"), ("in Excel, not in leaders", "Cy Dee"),
                                                                ("in leaders, not in Excel", "Eve Fake"), ("title differs", "Dr Ann Example")], xr
    # products: spec lines, unit rule, not-disclosed skip, name normalisation, company map (fictional values)
    assert split_unit("17.6 km") == ("17.6", "km") and split_unit("1,200 rounds/min") == ("1,200", "rounds/min") and split_unit("-40 °C") == ("-40", "°C")
    assert split_unit("5 %") == ("5", "%") and split_unit("2.5 g/cc") == ("2.5", "g/cc")
    for whole in ("~2,500 m", "over 360", "2 x 255 mm", "12 km; Range: 500 km", "9x19mm", "40 km (normal charge)", "12", "-54°C to +71°C", "3 to 5"):
        assert split_unit(whole) == (whole, None), whole
    pl = parse_spec_lines("Range: 17.6 km\nMuzzle velocity (normal charge): 800 m/s\n\nFuel: diesel: type 2\nNot disclosed\n"
                          "Crew: Not disclosed\nMass: not stated in sources.\nEmpty:\nA free text line\n" + "L" * 151 + ": 1 kg")
    assert [(x["label"], x["value"], x["unit"], x["skip"]) for x in pl] == [
        ("Range", "17.6", "km", None), ("Muzzle velocity (normal charge)", "800", "m/s", None), ("Fuel", "diesel: type 2", None, None),
        ("Note", "Not disclosed", None, "not_disclosed"), ("Crew", "Not disclosed", None, "not_disclosed"), ("Mass", "not stated in sources.", None, "not_disclosed"),
        ("Empty", "", None, "empty"), ("Note", "A free text line", None, None), ("L" * 151, "1 kg", None, "label_too_long")], pl
    assert [x["pos"] for x in pl] == list(range(1, 10))
    assert norm_product("K9  Vajra-T") == norm_product("k9 vajra t") == norm_product("K9 Vajra–T") and norm_product("A-1") != norm_product("A1")
    cpx = uuid.uuid4()
    assert product_id_for(cpx, "X") == product_id_for(str(cpx), "X") != product_id_for(cpx, "Y")
    assert spec_id_for("p", "L", 1) != spec_id_for("p", "L", 2) and spec_id_for("p", "L", 1) == spec_id_for("p", "L", 1)
    comps = {"Acme Corp": {"id": "aaaaaaaa-0000-0000-0000-000000000000", "display_name": "Acme Corp", "country": "Exampleland"},
             "SAAB": {"id": "bbbbbbbb-0000-0000-0000-000000000000", "display_name": "SAAB", "country": "Sweden"},
             "KNDS Germany": {"id": "cccccccc-0000-0000-0000-000000000000", "display_name": "KNDS Germany", "country": "Germany"}}
    assert resolve_product_company("Saab", comps)["display_name"] == "SAAB" and resolve_product_company("acme corp", comps)["id"] == comps["Acme Corp"]["id"]
    assert resolve_product_company("KNDS (KMW+Nexter)", comps)["display_name"] == "KNDS Germany" and resolve_product_company("Nobody Ltd", comps) is None

    def prow(company, product, specs, cat="Artillery", src="http://a.example/1\nhttp://a.example/2"):
        return {**{h: None for h in PRODUCT_COLS}, "Company": company, "Category": cat, "Product": product, "Technical Specifications": specs,
                "Source(s)": src, "Confidence": "high", "Verification": "Verified", "Verification detail": "d" * 400}
    exist = [{"product_id": "11111111-1111-1111-1111-111111111111", "competitor_id": comps["Acme Corp"]["id"], "product_name": "Zed-1 Gun"}]
    pr = build_products_plan([prow("Acme Corp", "Zed 1 gun", "Range: 10 km\nCrew: 4"), prow("Acme Corp", "Other", "Not disclosed"),
                              prow("Acme Corp", "Zed-1  Gun", "Range: 10 km\nWeight: 5 t", cat="Mortars"),
                              prow("Saab", "Zed-1 Gun", "Mass: 5 kg", src="http://b.example/9")], comps, exist)
    a, o, s_ = pr["products"]
    assert [p["name"] for p in pr["products"]] == ["Zed 1 gun", "Other", "Zed-1 Gun"]
    assert a["product_id"] == "11111111-1111-1111-1111-111111111111" and a["mode"] == "kept"
    assert o["mode"] == "new" and o["product_id"] == str(product_id_for(comps["Acme Corp"]["id"], "Other")) and o["spec_rows"] == [] and o["skipped"][0]["reason"] == "not_disclosed"
    assert s_["comp"]["display_name"] == "SAAB" and s_["product_id"] != a["product_id"] and s_["mode"] == "new"          # same name, other competitor
    assert [(x["spec_label"], x["spec_value"], x["unit"]) for x in a["spec_rows"]] == [("Range", "10", "km"), ("Crew", "4", None), ("Weight", "5", "t")]
    assert [x["reason"] for x in a["skipped"]] == ["duplicate_after_merge"] and len(pr["merged"]) == 1 and len(pr["warnings"]) == 1       # category differs
    assert a["spec_rows"][0]["source_count"] == 2 and a["spec_rows"][0]["source_url"] == "http://a.example/1" and a["urls"] == ["http://a.example/1", "http://a.example/2"]
    assert a["category"] == "Artillery" and a["category_count"] == 2 and a["spec_rows"][0]["quote"] == "Verification: Verified; Confidence: high — " + "d" * 300
    assert len({x["spec_id"] for x in a["spec_rows"]}) == 3
    assert build_products_plan([prow("Saab", "P", "A: 1", src="http://c.example/a b.pdf\n http://c.example/a b.pdf \nhttp://c.example/z")], comps, [])["products"][0]["urls"] == \
        ["http://c.example/a b.pdf", "http://c.example/z"]
    try:
        build_products_plan([prow("Nobody Ltd", "P", "A: 1")], comps, [])
        raise AssertionError("an unmapped company must stop the load")
    except ValueError as e:
        assert "Nobody Ltd" in str(e)
    assert build_products_plan([prow("Saab", "P", "A: 1")], comps, [])["products"][0]["spec_rows"][0]["spec_id"] == \
        build_products_plan([prow("Saab", "P", "A: 1")], comps, [])["products"][0]["spec_rows"][0]["spec_id"]
    # client products: footnotes, groups, unit rule, id keeping (fictional values)
    cl = parse_client_specs("• Calibre: 99 mm [S1]\n- Range: 12.5 km [S2,S1]\nWeight: 7 t (A); 8 t (B) [S1,S2]\n\nEngine power: 300 hp\nColour: not disclosed [S1]\nSomething free")
    assert [(x["label"], x["value"], x["unit"], x["skip"], x["src"], x.get("group")) for x in cl] == [
        ("Calibre", "99", "mm", None, [1], "Physical"), ("Range", "12.5", "km", None, [2, 1], "Performance"), ("Weight", "7 t (A); 8 t (B)", None, None, [1, 2], "Mobility"),
        ("Engine power", "300", "hp", None, [], "Mobility"), ("Colour", "not disclosed", None, "not_disclosed", [1], None), ("Note", "Something free", None, None, [], "Other")], cl
    assert [spec_group(x) for x in ("Barrel length", "Muzzle velocity", "Max speed (road)", "Maximum range", "Crew", "Coming into action time", "Magazine capacity", "Combat weight")] == \
        ["Physical", "Performance", "Mobility", "Performance", "Physical", "Performance", "Other", "Mobility"]
    assert numeric_of("1,200", "rounds/min") == Decimal(1200) and numeric_of("7 t (A)", None) is None and numeric_of("-5", "deg") == Decimal(-5)
    assert source_type_of("manufacturer (Zed page)") == "manufacturer" and source_type_of("defence-press") == "defence_press" and source_type_of("government / MoD") == "government"
    assert publisher_of("https://www.kssl.in/x") == "KSSL" and publisher_of("https://unknown.example/x") == "unknown.example"
    assert client_id_for("product", 9, "a") == client_id_for("product", 9, "a") != client_id_for("product", 9, "b") and 0 <= client_id_for("spec", 1, "L", 1) < 2 ** 63

    def krow(product, specs, cat="Artillery", src="http://a.example/1\nhttp://b.example/2", types="manufacturer\ndefence-press"):
        return {**{h: None for h in PRODUCT_COLS}, "Company": "Acme Defence", "Category": cat, "Product": product, "Technical Specifications": specs,
                "Source(s)": src, "Source Type": types, "Confidence": "high", "Verification": "Verified", "Verification detail": "d" * 400}
    kex = [{"client_product_id": 101, "product_name": "Zed Gun"}, {"client_product_id": 102, "product_name": "Zed"}, {"client_product_id": 103, "product_name": "Old Thing"},
           {"client_product_id": client_id_for("product", 7, "gone"), "product_name": "Gone"}, {"client_product_id": 105, "product_name": "Unrelated"}]
    kp = build_client_plan([krow("Zed Gun", "Calibre: 99 mm [S1]\nRange: 12 km [S2]"), krow("Zed 2 mk1 (variant)", "Weight: 7 t"), krow("Fresh Product", "Note only", cat="Small Arms", src="", types="")],
                           {"client_id": 7, "name": "Acme"}, kex)
    z, z2, f = kp["products"]
    assert (z["product_id"], z["mode"]) == (101, "kept") and (z2["product_id"], z2["mode"]) == (102, "kept") and f["mode"] == "new" and f["product_id"] == client_id_for("product", 7, "fresh product")
    assert [e["client_product_id"] for e in kp["stale"]] == [client_id_for("product", 7, "gone")]            # hand-made 103 / 105 are never stale
    assert [(s["spec_name"], s["unit"], s["value_numeric"], s["spec_group"], s["display_order"]) for s in z["spec_rows"]] == \
        [("Calibre", "mm", Decimal(99), "Physical", 1), ("Range", "km", Decimal(12), "Performance", 2)]
    assert z["spec_rows"][0]["source_id"] == z["sources"][0]["source_id"] and z["spec_rows"][1]["source_id"] == z["sources"][1]["source_id"] == client_id_for("source", 101, "http://b.example/2")
    assert z2["spec_rows"][0]["source_urls"] == ["http://a.example/1"] and z["sources"][1]["source_type"] == "defence_press" and z["sources"][0]["label"] == "a.example - manufacturer"
    assert f["spec_rows"][0]["spec_name"] == "Note" and f["sources"] == [] and len(kp["warnings"]) == 1 and z["quote"].endswith("d" * 300)
    for bad in ([krow("P", "A: 1 [S3]")], [krow("P", "A: 1", src="https://en.wikipedia.org/wiki/X")], [krow("P", "A: 1"), krow("p", "B: 2")]):
        try:
            build_client_plan(bad, {"client_id": 7, "name": "Acme"}, [])
            raise AssertionError("must stop")
        except ValueError:
            pass
    # blocked blog domains (backend.sources.BLOCKED["blog"]): URLs dropped; a value / line / spec whose only source is blocked is skipped as blocked_source
    assert split_blocked(["http://idrw.org/a", "https://www.ajaishukla.com/b", "https://m.idrw.org/c", "http://ok.example/d", "http://notidrw.org/e"]) == \
        (["http://ok.example/d", "http://notidrw.org/e"], ["http://idrw.org/a", "https://www.ajaishukla.com/b", "https://m.idrw.org/c"])
    import copy
    from backend.sources import is_blocked
    bs = copy.deepcopy(sheets)
    bs[SHEET_SUM][0]["FINAL Experience"] = "Verified"
    bs[SHEET_DIR][0]["Source URL"] = "http://idrw.org/1"
    bs[SHEET_CE] = [dict(x, **{"Source URL": "http://ajaishukla.com/p" if x["Field"] == "Current Position" else "http://idrw.org/e"}) for x in bs[SHEET_CE][:2]]
    bp = build_plan(bs, {"Larsen & Toubro": "11111111-1111-1111-1111-111111111111"})
    assert bp.leaders[0]["role_title"] is None and bp.leaders[0]["role_source_url"] is None and bp.records == [] and bp.facts == [], (bp.records, bp.facts)
    assert sorted(h["reason"].split(":")[0] for h in bp.held if h["field"] != "Education Background") == ["blocked_source"] * 3 and bp.stats["Larsen & Toubro (L&T)"]["roles_held"] == 1
    bs[SHEET_DIR][0]["Source URL"] = "http://idrw.org/1\nhttp://s.example/2"
    bs[SHEET_CE][1]["Source URL"] = "http://s.example/e"
    bp = build_plan(bs, {"Larsen & Toubro": "11111111-1111-1111-1111-111111111111"})
    assert bp.leaders[0]["role_title"] is None                                # its only cited source is blocked: no fallback to the row's other URL
    assert [r["source_url"] for r in bp.records] == ["http://s.example/e", "http://s.example/2"] and [f["source_url"] for f in bp.facts] == ["http://s.example/e", "http://s.example/2"]
    bs[SHEET_CE][0]["Source URL"] = None
    bp = build_plan(bs, {"Larsen & Toubro": "11111111-1111-1111-1111-111111111111"})
    assert bp.leaders[0]["role_source_url"] == "http://s.example/2"          # no cited source at all: the row's first non-blocked URL
    assert not any(is_blocked(f["source_url"]) for f in bp.facts)
    cb = build_company_plan(company_rows([{**{h: None for h in COMPANY_COLS}, "Company": "Acme Corp", "Company Size": "250 employees", "Headquarters": "Nowhere",
                                           "Sources": "http://idrw.org/x https://www.ajaishukla.com/y"},
                                          {**{h: None for h in COMPANY_COLS}, "Company": "Zed Ltd", "Company Size": "250 employees",
                                           "Sources": "http://idrw.org/x http://b.example/z"}]), {})
    assert cb["items"][0]["vals"]["employee_count"] is None and cb["items"][0]["vals"]["headquarters"] is None and cb["items"][0]["facts"] == [] and cb["items"][0]["blocked_source"]
    assert cb["items"][1]["vals"]["employee_count"] == 250 and {f["source_url"] for f in cb["items"][1]["facts"]} == {"http://b.example/z"} and not cb["items"][1]["blocked_source"]
    pb = build_products_plan([prow("Acme Corp", "Only Blog", "A: 1", src="http://idrw.org/1"), prow("Acme Corp", "Mixed", "A: 1", src="http://idrw.org/1\nhttp://a.example/2"),
                              prow("Acme Corp", "Mixed 2", "A: 1", src="http://ajaishukla.com/1"), prow("Acme Corp", "Mixed 2", "B: 2", src="http://a.example/3")], comps, [])
    assert pb["blocked_products"] == [("Acme Corp", "Only Blog")] and [g["name"] for g in pb["products"]] == ["Mixed", "Mixed 2"]
    m1, m2 = pb["products"]
    assert m1["urls"] == ["http://a.example/2"] and m1["spec_rows"][0]["source_url"] == "http://a.example/2" and m1["spec_rows"][0]["source_count"] == 1
    assert [(x["spec_label"], x["source_url"]) for x in m2["spec_rows"]] == [("B", "http://a.example/3")] and [x["reason"] for x in m2["skipped"]] == ["blocked_source"]
    kb = build_client_plan([krow("Zed Gun", "Calibre: 99 mm [S1]\nRange: 12 km [S2]\nWeight: 7 t", src="http://idrw.org/1\nhttp://b.example/2"),
                            krow("Blog Only", "Calibre: 9 mm\nRange: 1 km [S1]", src="https://www.ajaishukla.com/2016/x.html", types="defence-press")],
                           {"client_id": 7, "name": "Acme"}, [])
    zb, bo = kb["products"]
    assert [x["spec_name"] for x in zb["spec_rows"]] == ["Range", "Weight"] and [x["reason"] for x in zb["skipped"]] == ["blocked_source"]
    assert [s["url"] for s in zb["sources"]] == ["http://b.example/2"] and zb["spec_rows"][0]["source_id"] == client_id_for("source", zb["product_id"], "http://b.example/2")
    assert zb["spec_rows"][1]["source_urls"] == ["http://b.example/2"] and zb["urls"] == ["http://b.example/2"]       # no footnote: the first kept source
    assert bo["spec_rows"] == [] and bo["sources"] == [] and [x["reason"] for x in bo["skipped"]] == ["blocked_source"] * 2 and len(kb["warnings"]) == 1
    try:
        build_client_plan([krow("P", "A: 1 [S3]", src="http://idrw.org/1\nhttp://b.example/2")], {"client_id": 7, "name": "Acme"}, [])
        raise AssertionError("a footnote beyond the original Source(s) lines must still stop the load")
    except ValueError:
        pass
    assert description_text("• Role: rocket • Two [S1].\n• Two.\n- Three") == "Role: rocket\nTwo.\nThree" and description_text(None) is None
    print("excel_load selftest ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    lp = sub.add_parser("leadership", help="competitors + leaders + experience/education records")
    lp.add_argument("--file", required=True)
    lp.add_argument("--compare", help="a second workbook (a subset); differences are printed")
    lp.add_argument("--db", choices=["local", "vps"], default="local")
    lp.add_argument("--dry-run", action="store_true")
    lp.add_argument("--reports", default=str(DEFAULT_REPORTS), help="reports folder (default db/excel_reports/, gitignored)")
    cp_ = sub.add_parser("company", help="company details (sheet COMPANY DIRECTORY) -> competitive_competitor + fact_source")
    cp_.add_argument("--file", required=True)
    cp_.add_argument("--db", choices=["local", "vps"], default="local")
    cp_.add_argument("--dry-run", action="store_true")
    cp_.add_argument("--reports", default=str(DEFAULT_REPORTS), help="reports folder (default db/excel_reports/, gitignored)")
    pp = sub.add_parser("products", help="competitor products + specifications (sheet All Products) -> competitive_product / _specification + fact_source")
    pp.add_argument("--file", required=True)
    pp.add_argument("--db", choices=["local", "vps"], default="local")
    pp.add_argument("--dry-run", action="store_true")
    pp.add_argument("--reports", default=str(DEFAULT_REPORTS), help="reports folder (default db/excel_reports/, gitignored)")
    kp = sub.add_parser("client-products", help="the client's own products + specifications (sheet All Products) -> client_product / _specification / _source + fact_source")
    kp.add_argument("--file", required=True)
    kp.add_argument("--db", choices=["local", "vps"], default="local")
    kp.add_argument("--dry-run", action="store_true")
    kp.add_argument("--reports", default=str(DEFAULT_REPORTS), help="reports folder (default db/excel_reports/, gitignored)")
    dp = sub.add_parser("descriptions", help="only the Description column -> competitive_product.description (or client_product with --client)")
    dp.add_argument("--file", required=True)
    dp.add_argument("--client", action="store_true", help="the client's own portfolio workbook")
    dp.add_argument("--db", choices=["local", "vps"], default="local")
    dp.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        _selftest()
        return 0
    if args.cmd == "leadership":
        return cmd_leadership(args)
    if args.cmd == "company":
        return cmd_company(args)
    if args.cmd == "products":
        return cmd_products(args)
    if args.cmd == "client-products":
        return cmd_client_products(args)
    if args.cmd == "descriptions":
        return cmd_descriptions(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
