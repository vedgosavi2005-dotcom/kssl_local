"""Spec harvest for the Product Evaluation flood (plan B, user 2026-10-18): for each chosen like-for-like pair, store credible documents
that state the specs of BOTH products, so prompts/spec_enrich.yml (rival side) and prompts/client_spec_enrich.yml (KSSL side) can read them.

    python -m backend.harvest_specs --select                 resolve PAIRS against the like-for-like gate -> db/flood_logs/spec_pairs_B.json
    python -m backend.harvest_specs --harvest [--dry-run] [--only NAME]
    python -m backend.harvest_specs --routine 30 [--dry-run]   scheduled: gated pairs with nothing comparable, products not tried in 90 days
    python -m backend.harvest_specs --selftest

No web search. Where a document comes from, in order:
  1. documents already in staging.source_document that name the product;
  2. the pages the product's stored specs cite (rival side);
  3. the maker's own site: seed pages, its sitemap(s) (pages whose URL names the product), and the PDF datasheets / brochures linked there;
  4. the DC crawler corpus (pages it already holds whose title / URL names the product) -- also the fallback when a site blocks us.
Every URL must pass backend.sources.classify with the maker's own domains (maker site = primary; official; listed trade press).
Wikipedia, forums, blogs and unlisted sites are never stored for this. A document must name the product (a search term, on word
boundaries) and, off the maker's own site, also name the maker -- so "VIPER" or "M72" on another company's page is not taken.
A stored document gets triage.spec_products[] += product key and triage.spec_offset[key] = where its spec-dense part starts (the prompts
read 12,000 characters from there); a rival document also gets the competitor in competitor_ids, a KSSL one mentions_client = true.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "db" / "flood_logs" / "spec_pairs_B.json"
WINDOW = 12000
STATE = ROOT / "db" / "flood_logs" / "spec_harvest_state.json"     # routine: product key -> date it was last harvested
RETRY_DAYS = 90
MAX_DOCS = 4                      # per product, after ranking (page named after the product, maker site, official, then most mentions)
CLIENT_NAMES = ("Kalyani", "KSSL", "Bharat Forge")

# product (name prefix as stored) -> search terms; KSSL side first. Terms match on word boundaries, case-insensitive.
CLIENT = {
    "Bharat 52 155": ["Bharat 52", "155mm/52 Caliber Gun System"],        # kssl.in names it by calibre only
    "Bharat 45 155": ["Bharat 45"],
    "Bharat ULH": ["Bharat ULH", "ULH"],
    "MAG-ER": ["MAG-ER", "MAG ER"],
    "ATAGS 155": ["ATAGS"],
    "MArG 155 mm/39": ["MArG 155", "MArG"],
    "MArG 155 mm/45": ["MArG 155", "MArG"],
    "Armoured Personnel Carrier, Class-II": ["Armoured Personnel Carrier", "APC"],
    "Kalyani M4": ["Kalyani M4", "M4"],
    "Simha 4x4": ["Mbada", "Simha"],
    "F90 CQB": ["F90"],
    "Protective Carbine (PC)": ["Protective Carbine"],
    "T-5000M Sniper Rifle (.300": ["T-5000M", "T-5000", "T5000"],
    "T-5000M Sniper Rifle (.308": ["T-5000M", "T-5000", "T5000"],
    "T-5000M Sniper Rifle (.338": ["T-5000M", "T-5000", "T5000"],
    "Bharat 150": ["Bharat 150"],
    "FZ275": ["FZ275", "FZ 275"],
    "FZ90": ["FZ90", "FZ 90"],
    "MRO of all armoured": ["MRO", "Maintenance, Repair & Overhaul"],
}
CLIENT_EXTRA_DOMAINS = {"FZ275": ("thalesgroup.com",), "FZ90": ("thalesgroup.com",), "Simha 4x4": ("paramountgroup.com",)}
CLIENT_EXTRA_NAMES = {"FZ275": ("Thales",), "FZ90": ("Thales",), "Simha 4x4": ("Paramount",)}   # the partner maker of a KSSL-listed product
CLIENT_SEEDS = ["https://www.kssl.in/our-business-artillery", "https://www.kssl.in/protected-vehicles", "https://www.kssl.in/small-arms",
                "https://www.kssl.in/ammunition", "https://www.kssl.in/armoured-vehicle-MRO.php"]
# pages found by web search (user, 2026-10-18: "go web search and get the brochures you need"). kssl.in has no brochures and
# bharatforge.com disallows every crawler in robots.txt, so these are exchange filings (Bharat Forge's own releases) and listed trade
# press. Each still has to pass classify() and name KSSL / Kalyani / Bharat Forge.
CLIENT_URLS = {
    "MArG 155 mm/39": ["https://www.bseindia.com/xml-data/corpfiling/AttachHis/72dff088-15ec-44a4-81ca-5c2893003661.pdf",
                       "https://nsearchives.nseindia.com/corporate/ANILSHINDE_05102026113548_SEIntimationPressRelease.pdf",
                       "https://www.asianmilitaryreview.com/2026/06/kalyani-demonstrates-its-export-ambitions-at-eurosatory-2026-foc/",
                       "https://www.armyrecognition.com/archives/archives-land-defense/land-defense-2023/india-confirms-export-contract-of-marg-155mm-wheeled-self-propelled-howitzers-to-armenia",
                       "https://armyrecognition.com/news/army-news/2025/defea-2025-kalyani-strategic-systems-brings-mobile-artillery-and-autonomous-naval-systems-to-the-forefront"],
    "Bharat 52 155": ["https://www.armyrecognition.com/archives/archives-land-defense/land-defense-2018/kalyani-group-bharat-52-caliber-155mm-autonomous-towed-howitzer-at-defexpo-2018",
                      "https://www.shephardmedia.com/news/landwarfareintl/kalyani-in-india-to-export-155mm-towed-howitzers/",
                      "https://www.armyrecognition.com/archives/archives-land-defense/land-defense-2020/saudi-arabia-to-evaluate-indian-kalyani-group-howitzers"],
    "MAG-ER": ["https://www.janes.com/osint-insights/defence-news/defence/kalyani-group-develops-155-mm-artillery"],
    "ATAGS 155": ["https://www.bseindia.com/xml-data/corpfiling/AttachHis/9f3e3200-32b5-4aa5-a56a-81ba6bf1122e.pdf"],
    "Kalyani M4": ["https://www.bseindia.com/xml-data/corpfiling/AttachHis/4dae837e-9cae-44c6-93e5-7e25c4cb75cf.pdf"],
    "Simha 4x4": ["https://www.army-technology.com/news/paramount-kssl-simha-vehicle/"],
    "F90 CQB": ["https://www.army-technology.com/projects/f90-assault-rifle/"],
    "FZ275": ["https://www.army-technology.com/projects/fz275-semi-active-laser-sal-guided-rocket-belgium/",
              "https://www.armyrecognition.com/news/army-news/2026/thales-kssl-fz275-70mm-rocket-manufacturing-india"],
}
for _k in ("MArG 155 mm/45", "Bharat 45 155", "Bharat ULH"):       # the same family pages
    CLIENT_URLS[_k] = CLIENT_URLS["MArG 155 mm/39"] if _k.startswith("MArG") else CLIENT_URLS["MAG-ER"] + CLIENT_URLS["Bharat 52 155"]
CLIENT_LISTING ="https://www.kssl.in/press-releases.php"    # KSSL's own releases + PDFs, and the press coverage it links (credibility-checked)

RIVAL = {
    "ATAGS (Advanced Towed": ["ATAGS"],
    "Dhanush 155mm/52": ["Dhanush"],
    "TRAJAN": ["TRAJAN"],
    "M777": ["M777"],
    "M-71 (155mm/39": ["M-71", "Soltam"],
    "CAESAR 6x6": ["CAESAR"],
    "CAESAR 8x8": ["CAESAR"],
    "RCH 155": ["RCH 155", "RCH155"],
    "WhAP 8x8": ["WhAP", "Kestrel"],
    "Senator APC": ["Senator"],
    "Senator MRAP": ["Senator"],
    "LAV 6.0": ["LAV 6.0", "LAV 6"],
    "Aravis": ["Aravis"],
    "Marauder": ["Marauder"],
    "M72 / M72-I": ["M72-I", "M72 Carbine"],
    "5.56x45mm Close Quarter Battle": ["CQB Carbine", "Close Quarter Battle"],
    "5.56x30mm Joint Venture": ["JVPC", "Joint Venture Protective Carbine"],
    "ABHAY": ["ABHAY"],
    "Galil ACE CQB": ["Galil ACE"],
    "308 VIPER": ["308 VIPER", "VIPER"],
    "SVDM": ["SVDM"],
    "ACHOOK": ["ACHOOK"],
    "338 SABER": ["SABER"],
    "LAKSHYA": ["LAKSHYA"],
    "VAPOR CLE": ["VAPOR"],
    "Hexaglide 600": ["Hexaglide"],
    "X-Intra": ["X-Intra"],
    "Hydra-70 (2.75-inch / 70mm) Rocket System": ["Hydra-70", "Hydra 70"],
    "Total MRO solutions": ["MRO"],
    "Military Vehicle Systems MRO": ["MRO", "through-life"],
    "M1 Abrams Reset": ["Abrams"],
    "M88A2 HERCULES MRO": ["M88A2"],
}
# the makers' own sites (primary for their own products). There is no website column; these are the companies' real domains.
MAKER_DOMAINS = {
    "General Dynamics": ("gd.com", "gdls.com", "gdots.com"), "Hanwha Aerospace": ("hanwhaaerospace.com", "hanwha.com"),
    "Rheinmetall": ("rheinmetall.com",), "BAE Systems": ("baesystems.com",), "Tata Advanced Systems": ("tataadvancedsystems.com",),
    "Elbit Systems": ("elbitsystems.com",), "AWEIL": ("aweil.in",), "Nexter (KNDS France)": ("knds.fr", "knds.com", "nexter-group.fr"),
    "Roshel": ("roshel.com",), "Paramount Group": ("paramountgroup.com",), "SSS Defence": ("sssdefence.com",),
    "Adani Defence & Aerospace": ("adanidefence.com",), "Kalashnikov Concern": ("kalashnikovgroup.ru", "kalashnikov.com"),
    "AeroVironment": ("avinc.com",), "PLR Systems (IWI+Adani JV)": ("iwi.net",), "Otokar": ("otokar.com.tr",),
    "Mahindra Defence": ("mahindradefence.com", "mahindra.com"), "Munitions India Ltd (MIL)": ("munitionsindia.in",),
    "Premier Explosives": ("pelgel.com",),
}

# (KSSL product, rival product): 21 artillery, 9 vehicles, 14 small arms, 3 UAS, 2 rockets, 4 MRO (user plan B + MRO)
PAIRS = [
    ("Bharat 52 155", "ATAGS (Advanced Towed"), ("Bharat 52 155", "Dhanush 155mm/52"), ("Bharat 52 155", "TRAJAN"),
    ("MAG-ER", "M777"), ("MAG-ER", "ATAGS (Advanced Towed"), ("MAG-ER", "Dhanush 155mm/52"),
    ("ATAGS 155", "ATAGS (Advanced Towed"), ("ATAGS 155", "TRAJAN"), ("ATAGS 155", "Dhanush 155mm/52"),
    ("Bharat 45 155", "M-71 (155mm/39"), ("Bharat 45 155", "M777"), ("Bharat 45 155", "ATAGS (Advanced Towed"),
    ("Bharat ULH", "M777"), ("Bharat ULH", "M-71 (155mm/39"), ("Bharat ULH", "ATAGS (Advanced Towed"),
    ("MArG 155 mm/39", "CAESAR 6x6"), ("MArG 155 mm/39", "CAESAR 8x8"), ("MArG 155 mm/39", "RCH 155"),
    ("MArG 155 mm/45", "CAESAR 6x6"), ("MArG 155 mm/45", "CAESAR 8x8"), ("MArG 155 mm/45", "RCH 155"),
    ("Armoured Personnel Carrier, Class-II", "Senator APC"), ("Armoured Personnel Carrier, Class-II", "WhAP 8x8"),
    ("Armoured Personnel Carrier, Class-II", "LAV 6.0"),
    ("Kalyani M4", "Senator MRAP"), ("Kalyani M4", "Aravis"), ("Kalyani M4", "Marauder"),
    ("Simha 4x4", "Senator MRAP"), ("Simha 4x4", "Aravis"), ("Simha 4x4", "Marauder"),
    ("F90 CQB", "M72 / M72-I"), ("F90 CQB", "5.56x45mm Close Quarter Battle"), ("F90 CQB", "Galil ACE CQB"),
    ("Protective Carbine (PC)", "5.56x30mm Joint Venture"), ("Protective Carbine (PC)", "5.56x45mm Close Quarter Battle"),
    ("Protective Carbine (PC)", "ABHAY"),
    ("T-5000M Sniper Rifle (.300", "308 VIPER"), ("T-5000M Sniper Rifle (.300", "SVDM"), ("T-5000M Sniper Rifle (.300", "ACHOOK"),
    ("T-5000M Sniper Rifle (.308", "308 VIPER"), ("T-5000M Sniper Rifle (.308", "SVDM"), ("T-5000M Sniper Rifle (.308", "ACHOOK"),
    ("T-5000M Sniper Rifle (.338", "338 SABER"), ("T-5000M Sniper Rifle (.338", "LAKSHYA"),
    ("Bharat 150", "VAPOR CLE"), ("Bharat 150", "Hexaglide 600"), ("Bharat 150", "X-Intra"),
    ("FZ275", "Hydra-70 (2.75-inch / 70mm) Rocket System"), ("FZ90", "Hydra-70 (2.75-inch / 70mm) Rocket System"),
    ("MRO of all armoured", "Total MRO solutions"), ("MRO of all armoured", "Military Vehicle Systems MRO"),
    ("MRO of all armoured", "M1 Abrams Reset"), ("MRO of all armoured", "M88A2 HERCULES MRO"),
]

_NUM_UNIT = re.compile(r"\d[\d.,]*\s?(?:mm|cm|km/h|kmph|km|kg|tonnes?|t|m/s|m|rounds?|rds|rpm|hp|kw|litres?|l|mils?|°|degrees?|calibres?|cal|"
                       r"minutes?|min|hours?|hrs?|h|kn|mph|psi|bar)\b", re.I)


LISTING = re.compile(r"/(tags?|category|categories|author|search|page/\d+)(/|$)|/(media|news|press|press-releases|blog)/?$", re.I)


NEWSY = re.compile(r"/(news|press|media|blog|stories|article)|/20\d\d/|unveil|sends|signs|order|contract", re.I)


def slug(s) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")


def term_re(terms) -> re.Pattern:
    return re.compile("|".join(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])" for t in terms), re.I)


def spec_offset(body: str, terms) -> int | None:
    """Start of the most spec-dense WINDOW of body that follows a mention of the product; None when the product is not named."""
    hits = [m.start() for m in term_re(terms).finditer(body or "")]
    if not hits:
        return None
    if len(body) <= WINDOW:
        return 0                                  # the whole page fits: read it all
    best = max(hits[:200], key=lambda p: len(_NUM_UNIT.findall(body[max(0, p - 1000): max(0, p - 1000) + WINDOW])))
    return max(0, best - 1000)


def name_variants(name: str) -> list[str]:
    """Names that show a page is about this maker ('Nexter (KNDS France)' -> Nexter, KNDS France, KNDS)."""
    out = {re.sub(r"\s*\(.*?\)", "", name).strip()}
    for inner in re.findall(r"\((.*?)\)", name):
        out.update(p.strip() for p in re.split(r"[/+]", inner))
        out.add(inner.split()[0] if inner.split() else "")
    return [n for n in out if len(n) >= 3]


def pdf_text(data: bytes) -> str:
    import pypdf
    try:
        r = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in r.pages[:60])
    except Exception:
        return ""


# ----------------------------------------------------------------------------------------------------- selection
def select(cur) -> list[dict]:
    """PAIRS resolved to ids; every pair must be a like-for-like pair (matchup_code gate) with a qualifying rival."""
    from prompts.matchup_code import load_pairs
    gated = load_pairs(cur, gated_yaml=True)
    cur.execute("SELECT competitor_id::text AS id FROM staging.competitive_competitor WHERE qualifies IS TRUE")
    ok = {r["id"] for r in cur.fetchall()}
    out, missing = [], []
    for k, r in PAIRS:
        hit = [p for p in gated if p["client_product"].startswith(k) and p["competitor_product"].startswith(r) and str(p["competitor_id"]) in ok]
        hit = [p for p in hit if p["competitor_product"] == r] or hit          # "M777" is BAE's; "M777 Ultra-Lightweight ... (India...)" is Mahindra's
        if len(hit) != 1:
            missing.append((k, r, len(hit)))
            continue
        p = hit[0]
        out.append({"client_key": k, "rival_key": r, "client_product_id": int(p["client_product_id"]), "product_id": str(p["product_id"]),
                    "competitor_id": str(p["competitor_id"]), "client_product": p["client_product"],
                    "competitor_product": p["competitor_product"], "competitor": p["competitor"], "category": p["category"]})
    if missing:
        raise SystemExit(f"pairs not found once among the gated, qualifying pairs: {missing}")
    return out


def routine_pairs(cur, limit: int, state: dict, today: str) -> list[dict]:
    """Routine (scheduled) selection: every like-for-like pair with a qualifying rival whose code comparison has nothing comparable yet,
    where one of the two products was not harvested in the last RETRY_DAYS (state: product key -> last harvest date). At most `limit`."""
    from datetime import date, timedelta
    from prompts.matchup_code import load_pairs
    cur.execute("SELECT competitor_id::text AS id FROM staging.competitive_competitor WHERE qualifies IS TRUE")
    ok = {r["id"] for r in cur.fetchall()}
    cur.execute("SELECT client_product_id, competitor_product_id::text AS pid FROM staging.competitive_matchup WHERE coalesce(comparable_spec_count, 0) > 0")
    compared = {(int(r["client_product_id"]), r["pid"]) for r in cur.fetchall()}
    cutoff = (date.fromisoformat(today) - timedelta(days=RETRY_DAYS)).isoformat()
    out = []
    for p in load_pairs(cur, gated_yaml=True):
        key = (int(p["client_product_id"]), str(p["product_id"]))
        if str(p["competitor_id"]) not in ok or key in compared:
            continue
        if state.get(f"client:{key[0]}", "") >= cutoff and state.get(key[1], "") >= cutoff:
            continue
        out.append({"client_product_id": key[0], "product_id": key[1], "competitor_id": str(p["competitor_id"]), "client_product": p["client_product"],
                    "competitor_product": p["competitor_product"], "competitor": p["competitor"], "category": p["category"]})
    core = ("artillery", "small arms", "ammunition", "protected & armoured vehicles", "uavs & drones", "missiles & air defence")
    out.sort(key=lambda p: core.index(p["category"].lower()) if p["category"].lower() in core else len(core))   # KSSL's core lines first
    return out[:limit]


# ----------------------------------------------------------------------------------------------------- harvest
class Harvest:
    def __init__(self, conn, dry_run=False, log=print):
        from backend.harvest_sites import Ctx
        self.conn, self.dry, self.log = conn, dry_run, log
        self.ctx = Ctx(None, dry_run=True, log=log)          # http + robots only; storing is done here
        self.sitemaps: dict[str, list[str]] = {}
        self.pages: dict[str, tuple] = {}
        self.dc = None
        self.stats: dict = {}

    # --- credibility
    @staticmethod
    def credible(url, domains, client) -> str | None:
        from backend.sources import classify
        return classify(url, tuple(domains), client)

    @staticmethod
    def on_domain(url, domains) -> bool:
        h = urlsplit(url).netloc.lower().split(":")[0]
        return any(h == d or h.endswith("." + d) for d in domains)

    # --- fetching
    def fetch(self, url) -> tuple[str, str, str]:
        """(title, body text, html) of a page or PDF; empty body when not fetched."""
        url = quote(url, safe=":/?&=%~+,;@!$'()*#")             # a space in a site's own link ("pdf/BSE _BFL.pdf")
        if url not in self.pages:
            try:
                self.pages[url] = self._fetch(url)
            except Exception as e:                                 # one bad page never stops the run
                self.log(f"    skip {url[:110]}: {type(e).__name__}: {str(e)[:80]}")
                self.pages[url] = ("", "", "")
        return self.pages[url]

    def _fetch(self, url) -> tuple[str, str, str]:
        from backend.harvest_sites import read_page
        r, why = self.ctx.get(url, max_bytes=25_000_000 if url.lower().split("?")[0].endswith(".pdf") else 3_000_000)
        if r is None:
            self.log(f"    skip {url[:110]}: {why}")
            return "", "", ""
        ct = r.headers.get("content-type", "").lower()
        if "pdf" in ct or r.body[:5] == b"%PDF-":
            return urlsplit(url).path.rsplit("/", 1)[-1], pdf_text(r.body), ""
        html = r.text()
        p = read_page(html, url)
        return p.title, p.body, html

    def sitemap_urls(self, domain) -> list[str]:
        if domain in self.sitemaps:
            return self.sitemaps[domain]
        from backend.harvest_sites import parse_sitemap
        base = f"https://www.{domain}" if domain.count(".") == 1 else f"https://{domain}"
        todo = list(self.ctx.robots_for(base + "/").sitemaps or []) or [base + "/sitemap.xml", base + "/sitemap_index.xml"]
        seen, urls = set(), []
        while todo and len(seen) < 40:
            sm = todo.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            r, _why = self.ctx.get(sm, check_robots=False, max_bytes=20_000_000)
            if r is None:
                continue
            kind, rows = parse_sitemap(r.body)
            if kind == "index":
                todo += [x["loc"] for x in rows if not re.search(r"(post|news|blog|press|tag|author|image|video)[^/]*\.xml", x["loc"], re.I)] + \
                        [x["loc"] for x in rows if re.search(r"(post|news|press)[^/]*\.xml", x["loc"], re.I)]
            else:
                urls += [x["loc"] for x in rows]
        self.sitemaps[domain] = urls
        self.log(f"  sitemap {domain}: {len(urls)} urls")
        return urls

    def dc_page(self, url) -> tuple[str, str]:
        """(title, text) of one page the DC crawler stored under this url (with or without the trailing slash)."""
        if self.dc is None:
            from backend.import_dc_corpus import connect_dc
            self.dc = connect_dc()
        with self.dc.cursor() as c:
            c.execute("SELECT title, main_text FROM public.documents WHERE url = ANY(%s) AND coalesce(main_text, '') <> '' LIMIT 1",
                      ([url, url.rstrip("/"), url.rstrip("/") + "/"],))
            r = c.fetchone()
        return (r[0] or "", r[1]) if r else ("", "")

    def dc_rows(self, terms, limit=40) -> list[tuple]:
        if self.dc is None:
            from backend.import_dc_corpus import connect_dc
            self.dc = connect_dc()
        out = []
        with self.dc.cursor() as c:
            for t in terms:
                if len(t) < 4:
                    continue
                slug = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
                c.execute("SELECT url, title, left(main_text, 400000) FROM public.documents WHERE (title ILIKE %s OR url ILIKE %s) "
                          "AND coalesce(main_text, '') <> '' LIMIT %s", (f"%{t}%", f"%{slug}%", limit))
                out += c.fetchall()
        return out

    # --- storing
    def store(self, url, title, body, *, key, terms, competitor_id, client, source, tier) -> bool:
        off = spec_offset(body, terms)
        if off is None:
            return False
        if self.dry:
            return True
        with self.conn.cursor() as cur:
            cur.execute("""INSERT INTO staging.source_document (doc_id, url, source_kind, source_name, source_tier, title, body_text, triage, status,
                                                               competitor_ids, mentions_client, fetched_at)
                           VALUES (%s, %s, 'spec_page', %s, %s, %s, %s, '{}'::jsonb, 'new', %s::uuid[], %s, now())
                           ON CONFLICT (url) DO UPDATE SET body_text = coalesce(nullif(staging.source_document.body_text, ''), EXCLUDED.body_text)""",
                        (str(uuid.uuid5(uuid.NAMESPACE_URL, url)), url, urlsplit(url).netloc, tier, (title or "")[:500], body,
                         [competitor_id] if competitor_id else [], client))
            cur.execute("""UPDATE staging.source_document SET
                             triage = jsonb_set(jsonb_set(jsonb_set(coalesce(triage, '{}'::jsonb),
                                        '{spec_products}', (SELECT coalesce(jsonb_agg(DISTINCT v), '[]'::jsonb)
                                                            FROM jsonb_array_elements(coalesce(triage->'spec_products', '[]'::jsonb) || to_jsonb(%s::text)) v)),
                                        '{spec_offset}', coalesce(triage->'spec_offset', '{}'::jsonb) || jsonb_build_object(%s::text, %s::int)),
                                        '{spec_harvest}', to_jsonb(%s::text)),
                             competitor_ids = CASE WHEN %s::uuid IS NULL OR %s::uuid = ANY(coalesce(competitor_ids, '{}')) THEN competitor_ids
                                                   ELSE array_append(coalesce(competitor_ids, '{}'), %s::uuid) END,
                             mentions_client = coalesce(mentions_client, false) OR %s
                           WHERE url = %s""",
                        (key, key, off, source, competitor_id, competitor_id, competitor_id, client, url))
        self.conn.commit()
        return True

    # --- one product
    def listing_links(self, url) -> list[str]:
        if not url:
            return []
        _t, _b, html = self.fetch(url)
        links = {urljoin(url, h) for h in re.findall(r'href="([^"#]+)"', html or "")}
        return sorted(u for u in links if u.startswith("http") and not re.search(r"\.(css|js|png|jpe?g|svg|ico)$|instagram|linkedin|x\.com|facebook", u, re.I)
                      and (urlsplit(u).netloc != urlsplit(url).netloc or re.search(r"details|\.pdf$", u, re.I)))

    def product(self, *, key, name, terms, maker_names, domains, competitor_id, client, seeds=(), cited=(), listing="", max_docs=MAX_DOCS):
        tre = term_re(terms)
        maker_re = term_re(maker_names) if maker_names else None
        cand: dict[str, tuple] = {}            # url -> (rank, title, body, source)

        exact = slug(re.sub(r"\s*\(.*?\)", "", name))

        def consider(url, title, body, source, chosen=False):
            url = url.split("#")[0]
            tier = self.credible(url, domains, client)
            if not tier or url in cand or url.rstrip("/") in cand or url + "/" in cand or not body or LISTING.search(urlsplit(url).path):
                return
            hits = len(tre.findall(body))
            named = chosen and hits or tre.search(f"{title} {urlsplit(url).path.replace('-', ' ')}")      # a seed / cited page: one mention is enough
            if not (named or hits >= 2):
                return                          # one passing mention (a menu, a "related" link) is not a page about the product
            own = self.on_domain(url, domains)
            if not own and maker_re and not maker_re.search(body):
                return                          # another company's page that only shares a word with the product name
            rank = (exact not in slug(url + " " + (title or "")), bool(NEWSY.search(url)), not own, tier != "primary", not named, -hits)
            cand[url] = (rank, title, body, source, tier)

        # 1. documents already stored
        with self.conn.cursor() as cur:
            cur.execute("SELECT url, title, body_text FROM staging.source_document WHERE body_text ~* %s",
                        (tre.pattern.replace("(?<![A-Za-z0-9])", r"\m").replace("(?![A-Za-z0-9])", r"\M"),))
            for r in cur.fetchall():
                consider(r["url"], r["title"], r["body_text"], "stored")
        # 2 + 3. cited pages, seeds, the maker's sitemap pages, and the PDFs they link
        pages = list(dict.fromkeys([*cited, *seeds, *self.listing_links(listing)]))
        slugs = [re.sub(r"[^a-z0-9]+", "[-_ ]?", t.lower()) for t in terms if len(t) >= 3]
        for d in domains:
            sm = [u for u in self.sitemap_urls(d) if any(re.search(s, urlsplit(u).path.lower()) for s in slugs)]
            pages += sorted(sm, key=lambda u: (bool(re.search(r"news|press|blog|media|event", u, re.I)), len(u)))[:6]
        for url in pages:
            if not self.credible(url, domains, client):
                continue
            title, body, html = self.fetch(url)
            if not body:                                         # blocked (403 / robots) or gone: the same page from the DC corpus
                title, body = self.dc_page(url)
                if body:
                    consider(url.rstrip("/"), title, body, "dc_corpus", chosen=True)
                continue
            if html and self.on_domain(url, domains):
                from backend.harvest_sites import _plain
                body = max(body, _plain(html), key=len)          # the maker's page: tabs / spec tables the article reader leaves out
            consider(url, title, body, "pdf" if not html and body else "site", chosen=url in cited or url in seeds)
            for href, text in re.findall(r'<a[^>]+href="([^"]+\.pdf[^"]*)"[^>]*>(.*?)</a>', html or "", re.I | re.S)[:40]:
                pdf = urljoin(url, href)
                label = href + " " + re.sub("<[^>]+>", " ", text)
                if tre.search(label) or re.search(r"data\s?sheet|brochure|spec|leaflet|fact\s?sheet|catalog", label, re.I):
                    t, b, _ = self.fetch(pdf)
                    consider(pdf, t or label.strip()[:200], b, "pdf")
        # 4. the DC corpus
        for url, title, body in self.dc_rows(terms):
            consider(url, title, body, "dc_corpus")
        best = sorted(cand.items(), key=lambda kv: kv[1][0])[:max_docs]
        n = sum(self.store(u, t, b, key=key, terms=terms, competitor_id=competitor_id, client=client, source=s, tier=tier)
                for u, (_r, t, b, s, tier) in best)
        by = {}
        for _u, (_r, _t, _b, s, _tier) in best:
            by[s] = by.get(s, 0) + 1
        self.stats[name] = {"stored": n, "candidates": len(cand), "by_source": by, "urls": [u for u, _ in best]}
        self.log(f"  {name[:60]:60} {n} docs {by}")
        return n


def default_terms(name: str) -> list[str]:
    """Search terms for a product not in CLIENT / RIVAL: its name without the bracket, and the bracket's short code."""
    base = re.sub(r"\s*\(.*?\)", "", name).strip()
    out = [base]
    out += [w for w in re.findall(r"\((.*?)\)", name) if re.fullmatch(r"[A-Z0-9][\w.-]{2,12}", w)]
    if " - " in base:                                   # "COBRA II MRAP - 3-door configuration" -> "COBRA II MRAP"
        out.append(base.split(" - ")[0].strip())
    return [t for t in dict.fromkeys(out) if len(t) >= 3]


def run_harvest(conn, pairs, dry_run=False, only=None, log=print, client_only=False, rivals_only=False) -> dict:
    h = Harvest(conn, dry_run, log)
    with conn.cursor() as cur:
        cur.execute("SELECT product_id::text AS pid, array_agg(DISTINCT source_url) AS urls FROM staging.competitive_product_specification "
                    "WHERE source_url IS NOT NULL GROUP BY 1")
        cited = {r["pid"]: r["urls"] for r in cur.fetchall()}
    from backend.sources import CLIENT_DOMAINS
    done = set()
    for p in pairs:
        if only and only not in p["client_product"] and only not in p["competitor_product"]:
            continue
        ck = f"client:{p['client_product_id']}"
        k = p.get("client_key") or next((c for c in CLIENT if p["client_product"].startswith(c)), None)      # routine pairs carry no key
        r = p.get("rival_key") or next((c for c in RIVAL if p["competitor_product"].startswith(c)), None)
        if ck not in done and not rivals_only:
            done.add(ck)
            h.product(key=str(p["client_product_id"]), name=p["client_product"], terms=CLIENT.get(k) or default_terms(p["client_product"]),
                      maker_names=[*CLIENT_NAMES, *CLIENT_EXTRA_NAMES.get(k, ())],
                      domains=(*CLIENT_DOMAINS, *CLIENT_EXTRA_DOMAINS.get(k, ())), competitor_id=None, client=True,
                      seeds=CLIENT_SEEDS, listing=CLIENT_LISTING, cited=CLIENT_URLS.get(k, ()), max_docs=MAX_DOCS + 2)
        if client_only:
            continue
        if p["product_id"] not in done:
            done.add(p["product_id"])
            h.product(key=p["product_id"], name=p["competitor_product"], terms=RIVAL.get(r) or default_terms(p["competitor_product"]),
                      maker_names=name_variants(p["competitor"]),
                      domains=MAKER_DOMAINS.get(p["competitor"], ()), competitor_id=p["competitor_id"], client=False,
                      cited=cited.get(p["product_id"]) or ())
    return h.stats


def _selftest() -> None:
    assert spec_offset("x" * 50 + " The M777 weighs 4,200 kg and fires to 30 km.", ["M777"]) == 0
    assert spec_offset("Nothing here", ["M777"]) is None
    assert spec_offset("M777 " + "x" * 5000 + " 30 km 4 kg 5 mm" * 20, ["M777"]) == 0
    assert term_re(["MArG"]).search("the MArG 155") and not term_re(["MArG"]).search("a margin call")
    assert not term_re(["M72-I"]).search("M72-IX") and term_re(["T-5000"]).search("T-5000M rifle") is None
    assert term_re(["T-5000"]).search("the T-5000 rifle")
    assert sorted(name_variants("Nexter (KNDS France)")) == ["KNDS", "KNDS France", "Nexter"]
    assert Harvest.on_domain("https://defense.otokar.com.tr/x", ("otokar.com.tr",)) and not Harvest.on_domain("https://notroshel.com", ("roshel.com",))
    assert LISTING.search("/tag/simha") and LISTING.search("/media") and not LISTING.search("/media/news/paramount-unveils-mbada")
    assert slug("Senator MRAP") in slug("https://roshel.com/products/defense/senator-mrap")
    assert default_terms("COBRA II MRAP - 3-door configuration") == ["COBRA II MRAP - 3-door configuration", "COBRA II MRAP"]
    assert default_terms("Survivor R (4x4 Protected Special Operations Vehicle)") == ["Survivor R"]
    assert default_terms("AK-102 (5.56x45mm carbine)") == ["AK-102"] and "JVPC" in default_terms("5.56x30mm Joint Venture Protective Carbine (JVPC)")
    assert len(PAIRS) == len(set(PAIRS)) == 53 and all(k in CLIENT and r in RIVAL for k, r in PAIRS)
    print("harvest_specs self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--harvest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--client-only", action="store_true", help="only the KSSL side of each pair")
    ap.add_argument("--rivals-only", action="store_true", help="only the rival side of each pair")
    ap.add_argument("--routine", type=int, metavar="N", help="scheduled run: up to N gated pairs with nothing comparable yet (no static list)")
    ap.add_argument("--pairs", help="another pair list (json, same fields as --select writes)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    from prompts.run import connect
    conn = connect()
    if a.select:
        with conn.cursor() as cur:
            pairs = select(cur)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(pairs, indent=1), encoding="utf-8")
        print(f"{len(pairs)} pairs, {len({p['client_product_id'] for p in pairs})} KSSL products, {len({p['product_id'] for p in pairs})} rival products -> {OUT}")
        return 0
    if a.routine:
        from datetime import date
        today = date.today().isoformat()
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        with conn.cursor() as cur:
            pairs = routine_pairs(cur, a.routine, state, today)
        conn.rollback()
        stats = run_harvest(conn, pairs, a.dry_run)
        if not a.dry_run:
            for p in pairs:
                state[f"client:{p['client_product_id']}"] = state[p["product_id"]] = today
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(state, indent=0, sort_keys=True), encoding="utf-8")
        print(f"routine: {len(pairs)} pairs, products {len(stats)}, with docs {sum(1 for s in stats.values() if s['stored'])}, docs {sum(s['stored'] for s in stats.values())}")
        return 0
    if a.harvest:
        pairs = json.loads((Path(a.pairs) if a.pairs else OUT).read_text(encoding="utf-8"))
        stats = run_harvest(conn, pairs, a.dry_run, a.only, client_only=a.client_only, rivals_only=a.rivals_only)
        (OUT.parent / "spec_harvest_B.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
        print(f"products {len(stats)}, with docs {sum(1 for s in stats.values() if s['stored'])}, docs {sum(s['stored'] for s in stats.values())}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
