"""Harvest defence tender notices from official keyless government APIs into staging.tender_raw (local kssl_staging),
then (--stage) turn client-relevant ones into market_tender stubs the `tender` prompt can extract later.

  python -m backend.harvest_tenders --api ted_eu [--from 2026-01-17 --to 2026-10-17] [--open-only] [--max N] [--dry-run]
  python -m backend.harvest_tenders --api all
  python -m backend.harvest_tenders --stage [--dry-run]       # market_tender + market_tender_source stubs, tender_raw 'staged'
  python -m backend.harvest_tenders --report                  # per-API counts from tender_raw
  python -m backend.harvest_tenders --selftest                # assert-based, no network, no database

APIs (source_api): ted_eu gem_india canada uk_fts prozorro_ua decp_fr diavgeia_gr sam_us   (alias: uk = uk_fts)
Window = notices published --from..--to, PLUS every still-open notice (deadline >= today) whatever its publish date.
Resumable: each page is upserted as it arrives (ON CONFLICT (source_api, notice_id)); a cursor per API is kept in
db/harvest_tenders.state.json so an interrupted run continues (--fresh ignores it).

Reuses (read, not run) the mallery scripts, copying only the fetch/parse logic and citing the source file:
  cralwer/scripts/taxonomy.py (imported: 9-category keyword taxonomy, same matcher/veto as tag_tenders.py),
  pull_ted_eu.py, pull_gem_india.py, pull_canada.py, pull_ocds.py (UK Find a Tender), pull_prozorro_ua.py,
  pull_decp_france.py, pull_diavgeia_gr.py, pull_sam_us.py (pull_world_apis.py: Israel/Singapore tried, see report).
Those scripts post to a crawler ingest on :9090; nothing here touches it. Config comes from the environment only:
  KSSL_STAGING_DSN (else .env, else the local docker default) - refused unless it is the local kssl_staging;
  SAM_API_KEY (SAM.gov; without it sam_us is skipped); KSSL_MALLERY_SCRIPTS (folder with taxonomy.py).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "db" / "harvest_tenders.state.json"
LOCAL_DEFAULT = "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl"
MALLERY_SCRIPTS = os.environ.get("KSSL_MALLERY_SCRIPTS") or r"C:\Users\HARICHANDRA\Desktop\mallery\cralwer\scripts"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
WIN_FROM, WIN_TO = (date.today() - timedelta(days=274)).isoformat(), date.today().isoformat()     # rolling 9 months; a routine passes --from

# KSSL portfolio = staging.client_product.category (read it with portfolio_check()); the 'Other' bucket (electronics, AI,
# composites, mine detectors, ...) has no tender category. client_product.category -> taxonomy key:
KSSL_CATEGORIES = {
    "Artillery": "artillery", "Ammunition": "ammunition", "Protected & Armoured Vehicles": "protected_vehicles",
    "Armoured Vehicle MRO": "armoured_vehicle_mro", "Small Arms": "small_arms", "Marine / Naval": "naval",
    "Missiles & Air Defence": "missiles_air_defence", "UAVs & Drones": "uav_drones",
    "Precision Components & Forgings": "precision_forgings"}
KSSL_KEYS = set(KSSL_CATEGORIES.values())
# defence_tags written per notice: taxonomy keys + 'general_defence' (defence buyer/CPV, no hardware match) and, for a
# notice KSSL could bid on, 'kssl_relevant' plus one 'kssl:<key>' per matching portfolio category.


# ---------------------------------------------------------------------------------------------------------------
# taxonomy (imported from the mallery folder, never modified) + multi-label tagging
# ---------------------------------------------------------------------------------------------------------------
_TAX = None
COMPOUND = {"munition", "haubitze", "geschutz", "gewehr", "pistole", "maschinengewehr", "rakete", "flugabwehr", "drohne",
            "panzer", "kriegsschiff", "fregatte", "schusswaffe", "unbemannt", "granatwerfer", "schutzfahrzeug", "schutzweste",
            "unterseeboot", "ubootd", "gepanzert"}
# product names that must match as whole words ("stinger" is not Romanian "stingere" = extinguishing)
FULLWORD = {"stinger", "patriot", "reaper", "predator", "paladin", "bushmaster", "glock", "barrett", "stryker", "tracer",
            "tomahawk", "hellfire", "amraam", "nasams", "thaad", "shahed", "pandur", "bayraktar", "scaneagle"}


def taxonomy():
    global _TAX
    if _TAX is None:
        f = Path(MALLERY_SCRIPTS) / "taxonomy.py"
        if not f.exists():
            raise SystemExit(f"taxonomy.py not found at {f} - set KSSL_MALLERY_SCRIPTS to the mallery cralwer/scripts folder")
        spec = importlib.util.spec_from_file_location("mallery_taxonomy", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Extra multilingual stems (additions, ours): the mallery lists cover en/fr/el/zh; TED and the national portals
        # publish in de/es/it/pl/nl/uk/cs/ro/... so a title like "Munition 155 mm" or "Боєприпаси" would otherwise miss.
        extra = {
            "ammunition": ["munition", "municion", "municiones", "munizioni", "amunicj", "amunici", "boepripas",
                           "боєприпас", "патрон", "снаряд", "munitie", "municoes"],
            "artillery": ["haubitze", "geschutz", "artillerie", "obice", "artilleria", "haubica", "artyleri", "гаубиц",
                          "артилер", "гармат", "міномет", "minomet", "mortero", "mortaio", "granatwerfer"],
            "small_arms": ["gewehr", "pistole", "maschinengewehr", "fucile", "pistola", "fusil", "karabin", "subfusil",
                           "гвинтівк", "стрілецьк", "vuurwapen", "schusswaffe", "arma de fuego",
                           "armi leggere", "bron strzelecka", "bron palna"],
            "uav_drones": ["drohne", "dron ", "drony", "bezzalogow", "bezpilot", "безпілот", "бпла", "дрон",
                           "aeromobile a pilotaggio remoto", "sistema aereo no tripulado", "counter-uas", "c-uas", "counter uas",
                           "anti-drone", "antidrone", "unbemannt"],
            "missiles_air_defence": ["rakete", "flugabwehr", "misil", "missil", "antiaerea", "rakiet", "ракет",
                                     "ппо", "зенітн", "противоповітр", "obrona przeciwlotnicz", "luchtverdediging"],
            "protected_vehicles": ["gepanzert", "panzer", "blindado", "blindato", "opancerzon", "броньован", "бронеавтомоб",
                                   "бтр", "pansarvoertuig", "pantserv", "schutzfahrzeug", "schutzweste", "chaleco antibala",
                                   "giubbotto antiproiettile", "kamizelk", "бронежилет", "balistic"],
            "naval": ["kriegsschiff", "fregatte", "buque de guerra", "nave militare", "okret wojenn", "військов корабл",
                      "ubootd", "unterseeboot", "okrety podwodne", "marynark"],
            "armoured_vehicle_mro": ["panzer instandsetzung", "instandsetzung gepanzert"],
        }
        # KSSL portfolio vocabulary (staging.client_product): STRONG = qualifies alone, WEAK = needs a second signal
        strong = {
            "artillery": ["gun system", "towed gun", "mounted gun", "ultra-light howitzer", "gun platform", "muzzle brake",
                          "mountain artillery", "mortar system", "recoil system"],
            "ammunition": ["fuze", "fuzing", "propellant charge", "empty shell", "ready-to-fill", "shell body", "shell bodies",
                           "rocket motor", "ffar", "high explosive", "energetics", "small calibre ammunition", "medium calibre",
                           "cartridge case", "detonator", "155mm shell", "105mm shell", "small arms ammunition", "tank ammunition"],
            "protected_vehicles": ["armoured vehicle", "armored vehicle", "protected vehicle", "armoured personnel", "troop carrier",
                                   "infantry fighting vehicle", "light strike vehicle", "tactical vehicle", "stanag 4569",
                                   "mine protected", "bullet-proof vehicle", "bulletproof vehicle", "quick reaction fighting vehicle",
                                   "armoured car", "combat vehicle"],
            "armoured_vehicle_mro": ["afv spare", "armoured vehicle spare", "armored vehicle spare", "bmp-2", "bmp 2", "t-72", "t-90",
                                     "tank engine", "tank gearbox", "overhaul of tank", "mro of armoured", "road wheel"],
            "small_arms": ["small arms", "light machine gun", "assault rifle", "sniper rifle", "cqb carbine", "machine pistol",
                           "service pistol", "weapon system sniper"],
            "naval": ["naval gun", "steering gear", "propulsion shaft", "rudder stock", "fin stabili", "homing head",
                      "underwater vehicle", "mine countermeasure", "naval vessel", "expendable underwater", "torpedo"],
            "missiles_air_defence": ["air defence gun", "air defense gun", "anti-tank guided", "atgm", "anti tank missile",
                                     "anti-tank missile", "air defence system", "mrsam", "barak", "manpads", "rocket launcher"],
            "uav_drones": ["unmanned aerial", "unmanned aircraft", "vtol uas", "loitering munition", "isr platform",
                           "unmanned ground vehicle", "unmanned system", "remotely piloted", "counter-uas", "c-uas"],
            "precision_forgings": ["forging", "forged component", "barrel forging", "gun barrel", "howitzer barrel", "barrel blank",
                                   "ring rolling", "precision machining", "die forging", "warhead forging", "forged steel"],
        }
        weak = {
            "artillery": ["155 mm", "155mm", "105 mm", "105mm", "howitzer", "gun barrel", "cannon"],
            "ammunition": ["shell", "shells", "projectile", "propellant", "explosive", "grenade", "cartridge", "rounds", "bomb"],
            "protected_vehicles": ["armoured", "armored", "apc", "mrap", "ifv", "armour plate", "bullet proof", "bulletproof", "ballistic"],
            "armoured_vehicle_mro": ["afv", "tank", "tracked vehicle", "gearbox", "powertrain", "driveline", "sprocket", "running gear", "crankshaft", "turbocharger"],
            "small_arms": ["rifle", "carbine", "pistol", "lmg", "sniper", "firearm", "machine gun"],
            "naval": ["warship", "frigate", "shafting", "stabilizer", "naval", "submarine"],
            "missiles_air_defence": ["missile", "air defence", "air defense", "anti-aircraft", "spike"],
            "uav_drones": ["uas", "uav", "drone", "vtol", "auv"],
            "precision_forgings": ["forged", "forgings", "machined", "heat treatment", "turbine blade", "crankshaft"],
        }
        for key, kws in strong.items():
            extra.setdefault(key, []).extend(kws)
        # our own matcher table (mod._MATCHERS is left untouched). Single-word latin PHRASES from the mallery lists get a
        # left word boundary (stems already have one): "stinger" must not hit "...beleuchtungsstinger", while compounds
        # such as "artilleriemunition" still match our (substring) extras.
        table = []
        for key, is_def, items in mod._MATCHERS:
            new = []
            for kind, m in items:
                if kind == "phrase" and " " not in m and not mod._is_cjk(m) and m.isascii():
                    tail = r"(?![a-z0-9])" if m in FULLWORD else ""
                    new.append(("phrase_re", re.compile(r"(?<![a-z0-9])" + re.escape(m) + tail)))
                else:
                    new.append((kind, m))
            for kw in weak.get(key, []):
                new.append(("stem", re.compile(r"" + re.escape(fold(kw)))))
            for kw in extra.get(key, []):
                f = fold(kw)
                if f in COMPOUND:        # German compounds: the stem is the END of the word ("artilleriemunition")
                    new.append(("phrase", f))
                else:                    # everything else: left word boundary ("communities" is not Dutch "munitie")
                    new.append(("phrase_re", re.compile(r"(?<![a-z0-9])" + re.escape(f))))
            table.append((key, is_def, new))
        mod.TABLE = table
        _TAX = mod
    return _TAX


def fold(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(c))


def tag_text(text: str) -> list[str]:
    """All qualifying DEFENCE hardware categories of the taxonomy, best score first. Same scoring and vetoes as
    taxonomy.categorise_kw (mallery tag_tenders.py first-cut) but multi-label instead of first-best."""
    tx = taxonomy()
    t = fold(text)
    scored = []
    for key, is_def, items in tx.TABLE:
        if not is_def or any(v in t for v in tx._VETO.get(key, [])):
            continue
        score = calibers = signals = 0
        has_phrase = False
        for kind, m in items:
            if kind == "phrase":
                if m in t:
                    score += 2; signals += 1; has_phrase = True
            elif kind == "phrase_re":
                if m.search(t):
                    score += 2; signals += 1; has_phrase = True
            elif kind == "stem":
                if m.search(t):
                    score += 1; signals += 1
            elif m.search(t):
                calibers += 1
        if signals:
            score += calibers
        if has_phrase or score >= 2:
            scored.append((score, key))
    return [k for _, k in sorted(scored, key=lambda x: -x[0])]


# CPV hints (prefix level; the mallery pipeline has none). Only where the 4-digit group is unambiguous.
CPV_TAG = {"3532": "small_arms", "3533": "ammunition", "3534": "ammunition", "3540": "protected_vehicles",
           "3541": "protected_vehicles", "3542": "armoured_vehicle_mro"}
CPV_CORE = ("353", "354", "355", "356", "357")      # weapons/ammo, military vehicles, warships, military aircraft, military electronics

DEFENCE_BUYER = re.compile(
    r"(ministry of defen[cs]e|\bdefen[cs]e\b|\bdefence\b|ministere des armees|\barmee\b|armed forces|"
    r"\barmy\b|\bnavy\b|\bnaval\b|air force|\barmada\b|marine nationale|royal (navy|air force|marines)|british army|bundeswehr|"
    r"ausrustung, informationstechnik|verteidigung|ministerio de defensa|ministero della difesa|\bdifesa\b|defensie|forsvar|"
    r"puolustus|obrony narodowej|agencja uzbrojenia|\bwojsk|\bvojsk|ministerstvo obrany|\bobrana\b|armasuisse|\bnspa\b|\bncia\b|\boccar\b|"
    r"armement|ordnance|armament|\bmilitary\b|\bmilitar\b|krigsmakt|ministarstvo obrane|ministerul apararii|uzbrojen|"
    r"\bdstl\b|\bdes\b|eqthnikhs amynas|εθνικης αμυνας|национальна|міністерство оборони|збройні сили|військов)", re.I)


def defence_buyer(name: str | None) -> bool:
    return bool(name and DEFENCE_BUYER.search(fold(name)))


def make_tags(text: str, cpvs: list[str] | None, buyer: str | None, scoped: bool = False) -> list[str]:
    """defence_tags = taxonomy hardware categories from text + CPV hints. Empty hardware list but a defence cue
    (inherently defence-scoped API, defence buyer, weapons/vehicle/vessel CPV) -> ['general_defence'] (the taxonomy's
    catch-all key, see tag_tenders.py docstring). No cue at all -> [] (not a defence notice: never stored).
    Any KSSL portfolio category hit adds 'kssl_relevant' and 'kssl:<key>'."""
    cpvs = [c for c in (cpvs or []) if c]
    tags = tag_text(text)
    for c in cpvs:
        t = CPV_TAG.get(c[:4])
        if t and t not in tags:
            tags.append(t)
    if not tags and (scoped or defence_buyer(buyer) or any(c.startswith(CPV_CORE) for c in cpvs)):
        tags = ["general_defence"]
    hit = [t for t in tags if t in KSSL_KEYS]
    if hit:
        tags = tags + ["kssl_relevant"] + [f"kssl:{t}" for t in hit]
    return tags


# ---------------------------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------------------------
ISO3 = {  # ISO3 -> English short name (TED buyer-country)
    "AUT": "Austria", "BEL": "Belgium", "BGR": "Bulgaria", "HRV": "Croatia", "CYP": "Cyprus", "CZE": "Czechia",
    "DNK": "Denmark", "EST": "Estonia", "FIN": "Finland", "FRA": "France", "DEU": "Germany", "GRC": "Greece",
    "HUN": "Hungary", "IRL": "Ireland", "ITA": "Italy", "LVA": "Latvia", "LTU": "Lithuania", "LUX": "Luxembourg",
    "MLT": "Malta", "NLD": "Netherlands", "POL": "Poland", "PRT": "Portugal", "ROU": "Romania", "SVK": "Slovakia",
    "SVN": "Slovenia", "ESP": "Spain", "SWE": "Sweden", "ISL": "Iceland", "LIE": "Liechtenstein", "NOR": "Norway",
    "CHE": "Switzerland", "GBR": "United Kingdom", "UKR": "Ukraine", "TUR": "Turkey", "SRB": "Serbia",
    "MKD": "North Macedonia", "ALB": "Albania", "BIH": "Bosnia and Herzegovina", "MNE": "Montenegro", "MDA": "Moldova",
    "GEO": "Georgia", "ARM": "Armenia"}


def fmt_value(amount, cur) -> str | None:
    try:
        a = float(amount)
    except (TypeError, ValueError):
        return None
    s = f"{a:,.2f}"
    s = s[:-3] if s.endswith(".00") else s
    return f"{cur} {s}".strip() if cur else s


def first(v):
    return v[0] if isinstance(v, list) and v else (None if isinstance(v, list) else v)


def i18n(v, prefer=("eng", "ENG", "en")) -> str:
    """TED text fields are {'eng':[...], 'fra':[...]} maps (pull_ted_eu.i18n)."""
    if isinstance(v, dict):
        for lang in prefer:
            if v.get(lang):
                return "; ".join(map(str, v[lang])) if isinstance(v[lang], list) else str(v[lang])
        for val in v.values():
            if val:
                return "; ".join(map(str, val)) if isinstance(val, list) else str(val)
        return ""
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v or "")


def i18n_all(v, limit=2500) -> str:
    if isinstance(v, dict):
        return " ".join(("; ".join(map(str, x)) if isinstance(x, list) else str(x)) for x in v.values() if x)[:limit]
    return i18n(v)[:limit]


def parse_ts(s) -> datetime | None:
    """'2026-02-20+01:00' | '2026-10-17T09:00:00Z' | '2026-11-02T09:00:00' | '17/10/2026 03:00:00' -> aware datetime."""
    if s in (None, ""):
        return None
    s = str(s).strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}):(\d{2}))?$", s)
    if m:
        d, mo, y, hh, mm, ss = m.groups()
        return datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0), tzinfo=timezone.utc)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?$", s)
    if not m:
        return None
    y, mo, d, hh, mm, ss, tz = m.groups()
    if tz in (None, "Z"):
        tzi = timezone.utc
    else:
        sign = 1 if tz[0] == "+" else -1
        t = tz[1:].replace(":", "")
        tzi = timezone(sign * timedelta(hours=int(t[:2]), minutes=int(t[2:])))
    try:
        return datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0), tzinfo=tzi)
    except ValueError:
        return None


def to_date(s) -> date | None:
    t = parse_ts(s)
    return date(t.year, t.month, t.day) if t else None


def raw_id_of(source_api: str, notice_id: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{source_api}|{notice_id}")


def tender_id_of(raw_id: uuid.UUID) -> int:
    """Deterministic bigint from raw_id. Always >= 2**61, so it cannot collide with the small seed ids (9201001..)."""
    return (raw_id.int & (2 ** 61 - 1)) | 2 ** 61


def source_id_of(raw_id: uuid.UUID) -> int:
    return (uuid.uuid5(raw_id, "market_tender_source").int & (2 ** 61 - 1)) | 2 ** 61


def _finite(o):
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None                      # jsonb has no NaN/Infinity
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_finite(v) for v in o]
    return o


def clean_json(obj) -> str:
    """jsonb refuses \\u0000 and NaN/Infinity; drop/null them."""
    return json.dumps(_finite(obj), ensure_ascii=False, default=str, allow_nan=False).replace("\\u0000", "")


class MissingKey(RuntimeError):
    pass


class Ctx:
    def __init__(self, frm, to, open_only, max_n, today, client, state, dry):
        self.frm, self.to, self.open_only, self.max_n, self.today = frm, to, open_only, max_n, today
        self.client, self.state, self.dry = client, state, dry
        self.scan_from = self.scan_to = None      # optional narrower scan range (parallel slices of one long feed scan)

    def wanted(self, published: date | None, deadline: datetime | None) -> bool:
        """In the window, or still open (deadline today or later)."""
        is_open = bool(deadline and deadline.date() >= self.today)
        if self.open_only:
            return is_open
        if is_open:
            return True
        return bool(published and self.frm <= published <= self.to)


def get(ctx: Ctx, method, url, tries=4, **kw):
    """HTTP with retry/backoff; honours 429 Retry-After. Returns httpx.Response (status may be non-200 after retries)."""
    import httpx
    delay = 2.0
    r = None
    for i in range(tries):
        try:
            r = ctx.client.request(method, url, **kw)
        except (httpx.TransportError, httpx.TimeoutException) as e:
            print(f"    http error {type(e).__name__}: {str(e)[:80]} (try {i + 1}/{tries})", flush=True)
            time.sleep(delay); delay *= 2
            continue
        if r.status_code == 429 or r.status_code >= 500:
            ra = str(r.headers.get("Retry-After", ""))
            wait = float(ra) if ra.replace(".", "").isdigit() else delay
            print(f"    http {r.status_code}, waiting {wait:.0f}s (try {i + 1}/{tries})", flush=True)
            time.sleep(min(wait, 60)); delay *= 2
            continue
        return r
    return r


# ---------------------------------------------------------------------------------------------------------------
# per-API mapping. Each map_* turns one API record into a Rec dict:
#   notice_id notice_url title buyer_name country published_at(date) deadline_at(aware dt) value_text cpv_codes raw
#   text (for tagging) scoped (API is inherently defence-scoped)
# ---------------------------------------------------------------------------------------------------------------

# ---- TED (source: mallery pull_ted_eu.py; fields extended with lot titles/descriptions/values) -----------------
TED_URL = "https://api.ted.europa.eu/v3/notices/search"
TED_FIELDS = ["publication-number", "notice-title", "publication-date", "buyer-name", "buyer-country", "classification-cpv",
              "deadline-receipt-tender-date-lot", "links", "notice-type", "estimated-value-lot", "estimated-value-cur-lot",
              "total-value", "total-value-cur", "title-lot", "description-lot", "winner-selection-status",
              "procedure-type", "contract-nature"]


# CPV families of the KSSL portfolio (weapons & ammunition 353/3532/3533/3534, military vehicles 354, warships 355,
# military aircraft/missiles 356): queried FIRST, then the rest of the defence/security division 35.
TED_PRIORITY = "(classification-cpv=353* OR classification-cpv=354* OR classification-cpv=355* OR classification-cpv=356*)"


def ted_query(frm: date, to: date, today: date, open_only: bool, priority: bool = False) -> str:
    d = lambda x: x.strftime("%Y%m%d")
    open_clause = f"deadline-receipt-tender-date-lot>={d(today)}"
    if open_only:
        scope = open_clause
    else:
        scope = f"((publication-date>={d(frm)} AND publication-date<={d(to)}) OR {open_clause})"
    return f"{TED_PRIORITY if priority else 'classification-cpv=35*'} AND {scope} SORT BY publication-number DESC"


def map_ted(n: dict) -> dict:
    pub = str(n.get("publication-number") or "")
    links = n.get("links") or {}
    html = links.get("html") or {}
    pdf = links.get("pdf") or {}
    url = html.get("ENG") or pdf.get("ENG") or next(iter(html.values()), None) or f"https://ted.europa.eu/en/notice/-/detail/{pub}"
    title = i18n(n.get("notice-title")) or i18n(n.get("title-lot")) or "(untitled)"
    buyer = i18n(n.get("buyer-name"))
    iso = first(n.get("buyer-country"))
    cpvs = list(dict.fromkeys(n.get("classification-cpv") or []))
    deadlines = [t for t in (parse_ts(x) for x in (n.get("deadline-receipt-tender-date-lot") or [])) if t]
    if n.get("total-value") not in (None, ""):
        value = fmt_value(n["total-value"], first(n.get("total-value-cur")))
    else:
        vals = list(dict.fromkeys(n.get("estimated-value-lot") or []))
        cur = first(n.get("estimated-value-cur-lot"))
        value = ("estimated lot value " + "; ".join(fmt_value(v, cur) or str(v) for v in vals[:5])) if vals else None
    raw = dict(n)
    # keep the record as returned, minus the 24-language link fan-out (kept: xml + ENG/first html/pdf)
    raw["links"] = {k: ({lg: u for lg, u in v.items() if lg in ("ENG", "MUL")} or dict(list(v.items())[:1]))
                    for k, v in links.items() if isinstance(v, dict)}
    text = " ".join([i18n_all(n.get("notice-title")), i18n_all(n.get("title-lot")), i18n_all(n.get("description-lot"))])
    return dict(notice_id=pub, notice_url=url, title=title[:1000], buyer_name=buyer[:500] or None,
                country=ISO3.get(iso, iso), published_at=to_date(n.get("publication-date")),
                deadline_at=max(deadlines) if deadlines else None, value_text=value, cpv_codes=cpvs, raw=raw,
                text=text, scoped=False)


# ---- GeM India (source: mallery pull_gem_india.py) ------------------------------------------------------------
GEM = "https://bidplus.gem.gov.in"


def map_gem(b: dict) -> dict:
    bid = first(b.get("b_bid_number")) or ""
    item = first(b.get("b_category_name")) or first(b.get("bd_category_name")) or "(item)"
    dept = first(b.get("ba_official_details_deptName")) or ""
    minis = first(b.get("ba_official_details_minName")) or "Ministry of Defence"
    bid_id = first(b.get("b_id")) or b.get("id")
    return dict(notice_id=str(bid or bid_id), notice_url=f"{GEM}/showbidDocument/{bid_id}",
                title=f"{item}"[:1000], buyer_name=(f"{minis} - {dept}" if dept else minis),
                country="India", published_at=to_date(first(b.get("final_start_date_sort"))),
                deadline_at=parse_ts(first(b.get("final_end_date_sort"))), value_text=None, cpv_codes=[], raw=b,
                text=f"{item} {first(b.get('bd_category_name')) or ''}", scoped=True)


# ---- CanadaBuys (source: mallery pull_canada.py) ---------------------------------------------------------------
CB_URL = "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"
CB_ENTITY, CB_ENDUSER = "contractingEntityName-nomEntitContractante-eng", "endUserEntitiesName-nomEntitesUtilisateurFinal-eng"
CB_DEFENCE = re.compile(r"national defence|defence construction|canadian army|royal canadian (navy|air force)|"
                        r"defence research|defense nationale|\bdnd\b|\bcaf\b")


def cb_is_defence(row: dict) -> bool:
    return bool(CB_DEFENCE.search(fold((row.get(CB_ENTITY) or "") + " | " + (row.get(CB_ENDUSER) or ""))))


def map_canada(row: dict) -> dict:
    g = lambda k: (row.get(k) or "").strip()
    ref = g("referenceNumber-numeroReference") or g("solicitationNumber-numeroSollicitation")
    title = g("title-titre-eng") or "(untitled)"
    url = g("noticeURL-URLavis-eng") or f"https://canadabuys.canada.ca/en/tender-opportunities?ref={ref}"
    raw = {k: v for k, v in row.items() if v and not k.startswith("contactInfo") and not k.endswith("-fra")}
    desc = re.sub(r"<[^>]+>", " ", g("tenderDescription-descriptionAppelOffres-eng"))
    return dict(notice_id=ref, notice_url=url, title=title[:1000],
                buyer_name=(g(CB_ENTITY) + (f" (end user: {g(CB_ENDUSER)})" if g(CB_ENDUSER) and g(CB_ENDUSER) != g(CB_ENTITY) else ""))[:500],
                country="Canada", published_at=to_date(g("publicationDate-datePublication")),
                deadline_at=parse_ts(g("tenderClosingDate-appelOffresDateCloture")), value_text=None,
                cpv_codes=[], raw=raw, text=f"{title} {g('gsinDescription-nibsDescription-eng')} {desc[:1500]}", scoped=True)


# ---- UK Find a Tender OCDS (source: mallery pull_ocds.py uk-findatender; to_doc fields) ------------------------
FTS = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"


def release_cpvs(rel: dict) -> list[str]:
    out = []
    t = rel.get("tender") or {}
    for it in (t.get("items") or []):
        for c in [it.get("classification")] + (it.get("additionalClassifications") or []):
            if c and c.get("scheme") == "CPV" and c.get("id"):
                out.append(c["id"])
    for lot in (t.get("lots") or []):
        c = lot.get("classification")
        if c and c.get("scheme") == "CPV" and c.get("id"):
            out.append(c["id"])
    return list(dict.fromkeys(out))


def map_uk(rel: dict) -> dict:
    t = rel.get("tender") or {}
    nid = str(rel.get("id") or "")
    buyer = (rel.get("buyer") or {}).get("name") or next(
        (p.get("name") for p in (rel.get("parties") or []) if "buyer" in (p.get("roles") or [])), None)
    val = t.get("value") or {}
    awards = rel.get("awards") or []
    if not val.get("amount") and awards:
        val = (awards[0].get("value") or {})
    desc = (t.get("description") or "")[:2000]
    raw = json.loads(json.dumps(rel, default=str))
    for lot in ((raw.get("tender") or {}).get("lots") or []):      # drop the bulky award-criteria blocks from the stored copy
        lot.pop("awardCriteria", None)
    return dict(notice_id=nid, notice_url=f"https://www.find-tender.service.gov.uk/Notice/{nid}",
                title=(t.get("title") or t.get("id") or "(untitled)")[:1000], buyer_name=buyer,
                country="United Kingdom", published_at=to_date(rel.get("date")),
                deadline_at=parse_ts((t.get("tenderPeriod") or {}).get("endDate")),
                value_text=fmt_value(val.get("amount"), val.get("currency")), cpv_codes=release_cpvs(rel), raw=raw,
                text=f"{t.get('title') or ''} {desc}", scoped=False)


# ---- Prozorro Ukraine (source: mallery pull_prozorro_ua.py) ---------------------------------------------------
PZ = "https://public-api.prozorro.gov.ua/api/2.5/tenders"


def map_prozorro(t: dict) -> dict:
    tid = t.get("tenderID") or t.get("id")
    val = t.get("value") or {}
    cpvs = [i["classification"]["id"] for i in (t.get("items") or [])
            if (i.get("classification") or {}).get("scheme") == "CPV" and i["classification"].get("id")]
    items_txt = " ".join((i.get("description") or "") for i in (t.get("items") or []))[:1500]
    t = json.loads(json.dumps(t))
    (t.get("procuringEntity") or {}).pop("contactPoint", None)          # personal contact data is not needed
    return dict(notice_id=str(tid), notice_url=f"https://prozorro.gov.ua/tender/{tid}",
                title=(t.get("title") or "(без назви)")[:1000], buyer_name=((t.get("procuringEntity") or {}).get("name") or "")[:500] or None,
                country="Ukraine", published_at=to_date(t.get("datePublished") or (t.get("tenderPeriod") or {}).get("startDate") or t.get("date")),
                deadline_at=parse_ts((t.get("tenderPeriod") or {}).get("endDate")),
                value_text=fmt_value(val.get("amount"), val.get("currency")), cpv_codes=list(dict.fromkeys(cpvs)), raw=t,
                text=f"{t.get('title') or ''} {t.get('description') or ''} {items_txt}", scoped=True)


# ---- France DECP (source: mallery pull_decp_france.py) -------------------------------------------------------
DECP = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/decp-2022-marches-valides/records"


def map_decp(rec: dict) -> dict:
    rid = str(rec.get("id") or rec.get("uid") or hashlib.md5(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()[:16])
    cpv = str(rec.get("codecpv") or "").split("-")[0]
    buyer = rec.get("acheteur_nom") or (f"SIRET {rec['acheteur_id']}" if rec.get("acheteur_id") else None)
    amt = rec.get("montant")
    return dict(notice_id=rid,
                notice_url=f"https://data.economie.gouv.fr/explore/dataset/decp-2022-marches-valides/table/?q=id%3A{rid}",
                title=(rec.get("objet") or "(sans objet)")[:1000], buyer_name=buyer, country="France",
                published_at=to_date(rec.get("datenotification") or rec.get("datepublicationdonnees")), deadline_at=None,
                value_text=fmt_value(amt, "EUR") if amt not in (None, "") else None, cpv_codes=[cpv] if cpv else [],
                raw=rec, text=str(rec.get("objet") or ""), scoped=True)


# ---- Greece Diavgeia (source: mallery pull_diavgeia_gr.py) ---------------------------------------------------
DIAV = "https://opendata.diavgeia.gov.gr/luminapi/api/search"
DIAV_TYPES = ["Δ.2.1", "Δ.2.2", "Δ.1", "Γ.3.4"]      # tender summary, award, assignment, contract


def map_diavgeia(x: dict) -> dict:
    ada = x.get("ada")
    return dict(notice_id=str(ada), notice_url=x.get("documentUrl") or f"https://diavgeia.gov.gr/doc/{ada}",
                title=(x.get("subject") or "(χωρίς θέμα)")[:1000], buyer_name=(x.get("organization") or {}).get("label"),
                country="Greece", published_at=to_date(x.get("issueDate")), deadline_at=None, value_text=None,
                cpv_codes=[], raw=x, text=x.get("subject") or "", scoped=True)


# ---- SAM.gov (source: mallery pull_sam_us.py; needs SAM_API_KEY) ---------------------------------------------
SAM = "https://api.sam.gov/opportunities/v2/search"


def map_sam(o: dict) -> dict:
    nid = o.get("noticeId")
    return dict(notice_id=str(nid), notice_url=o.get("uiLink") or f"https://sam.gov/opp/{nid}/view",
                title=((o.get("title") or "").strip() or "(no title)")[:1000], buyer_name=o.get("fullParentPathName"),
                country="United States", published_at=to_date(o.get("postedDate")),
                deadline_at=parse_ts(o.get("responseDeadLine")), value_text=None,
                cpv_codes=[], raw=o, text=f"{o.get('title') or ''} {o.get('classificationCode') or ''}", scoped=True)


# ---------------------------------------------------------------------------------------------------------------
# fetchers: generators of (page records, cursor, api total); they apply the API-side filters only
# ---------------------------------------------------------------------------------------------------------------
def fetch_ted(ctx: Ctx):
    """Two passes: KSSL-portfolio CPV families first (server-side filter), then all of CPV 35 (upsert dedups)."""
    queries = [ted_query(ctx.frm, ctx.to, ctx.today, ctx.open_only, True), ted_query(ctx.frm, ctx.to, ctx.today, ctx.open_only)]
    cur = ctx.state.get("cursor") or {}
    start = cur.get("qi", 0) if cur.get("queries") == queries else 0
    token = cur.get("token") if start == cur.get("qi") and cur.get("queries") == queries else None
    for qi in range(start, len(queries)):
        q, sent = queries[qi], (cur.get("sent", 0) if token else 0)
        while True:
            body = {"query": q, "fields": TED_FIELDS, "limit": 250, "scope": "ALL", "paginationMode": "ITERATION"}
            if token:
                body["iterationNextToken"] = token
            r = get(ctx, "POST", TED_URL, json=body, timeout=120)
            if r is None or r.status_code != 200:
                if token:      # stale token: restart this query from scratch rather than fail
                    print("    TED token rejected, restarting query", flush=True); token = None; sent = 0; continue
                raise RuntimeError(f"TED {getattr(r, 'status_code', None)} {getattr(r, 'text', '')[:200]}")
            d = r.json()
            notices = d.get("notices") or []
            token = d.get("iterationNextToken")
            sent += len(notices)
            yield notices, {"queries": queries, "qi": qi, "token": token, "sent": sent}, f"pass {qi + 1}/2: {d.get('totalNoticeCount')}"
            if not notices or not token:
                break
            time.sleep(0.6)
        token = None


def fetch_gem(ctx: Ctx):
    def csrf():
        r = get(ctx, "GET", f"{GEM}/all-bids")
        m = re.search(r'name="csrf_bd_gem_nk"[^>]*value="([^"]+)"', r.text) or re.search(r'csrf_bd_gem_nk["\']?\s*[:=]\s*["\']([^"\']+)', r.text)
        return m.group(1) if m else None
    tok = csrf()
    if not tok:
        raise RuntimeError("GeM: no CSRF token (layout changed)")
    page = ctx.state.get("cursor", {}).get("page", 1)
    fails = 0
    while True:
        payload = {"searchType": "ministry-search", "ministry": "Ministry of Defence", "buyerState": "", "organization": "",
                   "department": "", "bidEndFromMin": "", "bidEndToMin": "", "page": page}
        r = get(ctx, "POST", f"{GEM}/search-bids", data={"payload": json.dumps(payload), "csrf_bd_gem_nk": tok},
                headers={"Referer": f"{GEM}/advance-search"}, timeout=60)
        try:
            if r.status_code in (419, 403):
                raise ValueError("csrf")
            resp = r.json()["response"]["response"]
        except Exception:
            fails += 1
            if fails > 4:
                raise RuntimeError(f"GeM: page {page} keeps failing ({getattr(r, 'status_code', None)})")
            tok = csrf() or tok; time.sleep(3); continue
        fails = 0
        docs = resp.get("docs") or []
        total = resp.get("numFound")
        page += 1
        yield docs, {"page": page}, total
        if not docs or (page - 1) * 10 >= (total or 0):
            return
        time.sleep(0.35)


def fetch_canada(ctx: Ctx):
    import csv
    import io
    r = get(ctx, "GET", CB_URL, timeout=240)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"CanadaBuys CSV {getattr(r, 'status_code', None)}")
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    yield [row for row in rows if cb_is_defence(row)], {}, len(rows)


def fetch_uk(ctx: Ctx):
    """Find a Tender OCDS release packages, one day at a time (updatedFrom/updatedTo), cursor = day + next-link.
    The API has no CPV filter, so scope is applied client-side in finalize()."""
    cur = ctx.state.get("cursor") or {}
    day = date.fromisoformat(cur["day"]) if cur.get("day") else ctx.frm
    url = cur.get("next")
    last_sig = None
    while day <= ctx.to:
        if not url:
            url = f"{FTS}?limit=100&updatedFrom={day.isoformat()}T00:00:00&updatedTo={(day + timedelta(days=1)).isoformat()}T00:00:00"
        r = get(ctx, "GET", url, headers={"Accept": "application/json"}, timeout=120)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"FTS {getattr(r, 'status_code', None)} at {day}")
        d = r.json()
        rels = d.get("releases") or []
        nxt_link = (d.get("links") or {}).get("next")
        sig = (rels[0]["id"], rels[-1]["id"]) if rels else None
        if sig and sig == last_sig:       # FTS bug: when >100 releases share one timestamp the next-link serves the same page forever
            print(f"    FTS cursor loops on {day} (identical page twice) - moving to the next day", flush=True)
            nxt_link = None
            rels = []
        last_sig = sig
        if nxt_link and rels:
            url, nday = nxt_link, day
        else:
            url, nday = None, day + timedelta(days=1)
        yield rels, {"day": nday.isoformat(), "next": url}, f"day {day}"
        day = nday
        time.sleep(1.0)


PZ_TRIVIAL = {"reporting", "priceQuotation", "belowThreshold"}      # direct purchases / award reports: ~95% of defence-entity rows


def is_pz_defence(t: dict) -> bool:
    """Feed row of a defence procedure: legacy '*.defense' procedure types (mallery pull_prozorro_ua.py) or - since 2025 the
    war-time types are gone - a procuring entity of kind 'defense' running a real tender (not a trivial direct purchase;
    those would be ~140k detail fetches for the window)."""
    mt = t.get("procurementMethodType") or ""
    if ".defense" in mt:
        return True
    return (t.get("procuringEntity") or {}).get("kind") == "defense" and mt not in PZ_TRIVIAL


def fetch_prozorro(ctx: Ctx):
    """Feed scan from the window start (offset=timestamp), keep '.defense' procedures, hydrate each (mallery
    pull_prozorro_ua.py filtered the same way)."""
    cur = ctx.state.get("cursor") or {}
    start = f"{(ctx.scan_from or ctx.frm).isoformat()}T00:00:00"
    if ctx.open_only:
        start = f"{(ctx.today - timedelta(days=60)).isoformat()}T00:00:00"
    of = "procurementMethodType,dateModified,status,procuringEntity"
    params = {"limit": 1000, "offset": cur.get("offset") or start, "opt_fields": of}
    stop = ((ctx.scan_to or ctx.to) + timedelta(days=1)).isoformat()
    scanned = cur.get("scanned", 0)
    while True:
        r = get(ctx, "GET", PZ, params=params, timeout=90)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"Prozorro feed {getattr(r, 'status_code', None)}")
        d = r.json()
        rows = d.get("data") or []
        scanned += len(rows)
        out = []
        for t in rows:
            if is_pz_defence(t):
                dr = get(ctx, "GET", f"{PZ}/{t['id']}", timeout=60)
                if dr is not None and dr.status_code == 200:
                    out.append(dr.json().get("data", {}))
                time.sleep(0.15)
        nxt = (d.get("next_page") or {}).get("offset")
        last = rows[-1]["dateModified"][:10] if rows else "9999"
        yield out, {"offset": nxt, "scanned": scanned}, f"scanned {scanned}, at {last}"
        if not rows or not nxt or last >= stop:
            return
        params = {"limit": 1000, "offset": nxt, "opt_fields": of}
        time.sleep(0.3)


def fetch_decp(ctx: Ctx):
    """Two passes: CPV 353-356 (KSSL portfolio families) first, then the rest of CPV 35."""
    win = f"datenotification>=date'{ctx.frm.isoformat()}' AND datenotification<=date'{ctx.to.isoformat()}'"
    wheres = [f'(startswith(codecpv,"353") OR startswith(codecpv,"354") OR startswith(codecpv,"355") OR startswith(codecpv,"356")) AND {win}',
              f'startswith(codecpv,"35") AND {win}']
    cur = ctx.state.get("cursor", {})
    for wi in range(cur.get("wi", 0), 2):
        off = cur.get("offset", 0) if wi == cur.get("wi", 0) else 0
        while True:
            r = get(ctx, "GET", DECP, params={"where": wheres[wi], "limit": 100, "offset": off, "order_by": "datenotification desc, id"}, timeout=90)
            if r is None or r.status_code != 200:
                raise RuntimeError(f"DECP {getattr(r, 'status_code', None)} {getattr(r, 'text', '')[:150]}")
            d = r.json()
            total = d.get("total_count")
            rows = d.get("results") or []
            off += len(rows)
            yield rows, {"wi": wi, "offset": off}, f"pass {wi + 1}/2: {total}"
            if not rows or off >= (total or 0):
                break
            time.sleep(0.3)


def fetch_diavgeia(ctx: Ctx):
    page = ctx.state.get("cursor", {}).get("page", 0)
    q = ('organizationUid:"6" AND issueDate:[DT(%sT00:00:00) TO DT(%sT23:59:59)] AND (%s)'
         % (ctx.frm.isoformat(), ctx.to.isoformat(), " OR ".join(f'decisionTypeUid:"{t}"' for t in DIAV_TYPES)))
    total = None
    while True:
        r = get(ctx, "GET", DIAV, params={"q": q, "size": 100, "page": page, "sort": "recent"}, headers={"Accept": "application/json"}, timeout=90)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"Diavgeia {getattr(r, 'status_code', None)}")
        d = r.json()
        if d.get("errors"):
            raise RuntimeError(f"Diavgeia query error {str(d['errors'])[:150]}")
        total = (d.get("info") or {}).get("total", total)
        rows = d.get("decisions") or []
        page += 1
        yield rows, {"page": page}, total
        if not rows or page * 100 >= (total or 0):
            return
        time.sleep(0.4)


def fetch_sam(ctx: Ctx):
    key = os.environ.get("SAM_API_KEY", "").strip()
    if not key:
        raise MissingKey("SAM_API_KEY not set - SAM.gov skipped (pull_sam_us.py reads the same variable)")
    day = date.fromisoformat(ctx.state.get("cursor", {}).get("day", ctx.frm.isoformat()))
    while day <= ctx.to:
        end = min(day + timedelta(days=12), ctx.to)
        qp = {"api_key": key, "postedFrom": day.strftime("%m/%d/%Y"), "postedTo": end.strftime("%m/%d/%Y"),
              "ptype": "o", "limit": 1000, "offset": 0, "deptname": "DEPT OF DEFENSE"}
        r = get(ctx, "GET", SAM, params=qp, timeout=90)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"SAM {getattr(r, 'status_code', None)} (quota?)")
        d = r.json()
        rows = [o for o in d.get("opportunitiesData", []) if (o.get("fullParentPathName") or "").startswith("DEPT OF DEFENSE")]
        day = end + timedelta(days=1)
        yield rows, {"day": day.isoformat()}, d.get("totalRecords")
        time.sleep(0.5)


# api -> (fetcher, mapper, portal name, scope mode)
APIS = {
    "ted_eu": (fetch_ted, map_ted, "TED (Tenders Electronic Daily)", None),
    "gem_india": (fetch_gem, map_gem, "GeM (Government e-Marketplace)", None),
    "canada": (fetch_canada, map_canada, "CanadaBuys", None),
    "uk_fts": (fetch_uk, map_uk, "Find a Tender", None),
    "prozorro_ua": (fetch_prozorro, map_prozorro, "Prozorro", None),
    "decp_fr": (fetch_decp, map_decp, "DECP (data.economie.gouv.fr)", None),
    "diavgeia_gr": (fetch_diavgeia, map_diavgeia, "Diavgeia", None),
    "sam_us": (fetch_sam, map_sam, "SAM.gov", None),
}
ALIASES = {"uk": "uk_fts", "ted": "ted_eu", "gem": "gem_india", "ukraine": "prozorro_ua", "prozorro": "prozorro_ua",
           "france": "decp_fr", "greece": "diavgeia_gr", "sam": "sam_us"}
ORDER = ["ted_eu", "gem_india", "canada", "uk_fts", "prozorro_ua", "decp_fr", "diavgeia_gr", "sam_us"]


def finalize(api: str, rec: dict, ctx: Ctx) -> dict | None:
    """window/open filter + defence tags. None = not stored: outside the window, or not a defence notice (no tag at all)."""
    if not rec.get("notice_id"):
        return None
    if not ctx.wanted(rec["published_at"], rec["deadline_at"]):
        return None
    tags = make_tags(rec["text"], rec["cpv_codes"], rec["buyer_name"], scoped=rec["scoped"])
    if not tags:
        return None            # defence only: CPV-35 civil security / fire-fighting etc. is not harvested
    rec = dict(rec)
    rec["defence_tags"] = tags
    rec["status"] = "new"
    return rec


# ---------------------------------------------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------------------------------------------
def read_env(path: Path = ROOT / ".env") -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                v = v.strip()
                if v[:1] in "'\"" and v.endswith(v[:1]) and len(v) > 1:
                    v = v[1:-1]
                out[k.strip()] = v
    return out


def resolve_dsn() -> str:
    dsn = (os.environ.get("KSSL_STAGING_DSN") or read_env().get("KSSL_STAGING_DSN") or LOCAL_DEFAULT).strip()
    # guard: local kssl_staging only (never the VPS tunnel, never serving)
    if (not re.search(r"dbname=kssl_staging\b|/kssl_staging\b", dsn) or not re.search(r"(127\.0\.0\.1|localhost)", dsn)
            or "55432" not in dsn):
        raise SystemExit("refusing: DSN is not the local kssl_staging on port 55432")
    return dsn


def connect():
    import psycopg2
    return psycopg2.connect(resolve_dsn(), connect_timeout=8)


UPSERT = """
INSERT INTO staging.tender_raw (raw_id, source_api, notice_id, notice_url, title, buyer_name, country, published_at,
                                deadline_at, value_text, cpv_codes, defence_tags, raw, status, fetched_at)
VALUES %s
ON CONFLICT (source_api, notice_id) DO UPDATE SET
  notice_url = EXCLUDED.notice_url, title = EXCLUDED.title, buyer_name = EXCLUDED.buyer_name, country = EXCLUDED.country,
  published_at = EXCLUDED.published_at, deadline_at = EXCLUDED.deadline_at, value_text = EXCLUDED.value_text,
  cpv_codes = EXCLUDED.cpv_codes, defence_tags = EXCLUDED.defence_tags, raw = EXCLUDED.raw, fetched_at = now(),
  status = CASE WHEN staging.tender_raw.status IN ('staged', 'processed') THEN staging.tender_raw.status ELSE EXCLUDED.status END
"""


def upsert(conn, api: str, recs: list[dict]) -> int:
    from psycopg2.extras import execute_values
    seen = {r["notice_id"]: r for r in recs}          # last wins inside one statement
    now = datetime.now(timezone.utc)
    rows = [(str(raw_id_of(api, nid)), api, nid, r["notice_url"], r["title"], r["buyer_name"], r["country"], r["published_at"],
             r["deadline_at"], r["value_text"], r["cpv_codes"] or [], r["defence_tags"], clean_json(r["raw"]), r["status"], now)
            for nid, r in seen.items()]
    with conn.cursor() as cur:
        execute_values(cur, UPSERT, rows, template="(%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::text[],%s::text[],%s::jsonb,%s,%s)", page_size=200)
    conn.commit()
    return len(rows)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(api: str, entry: dict):
    """Merge-write one API's entry (several harvest processes may run in parallel, one per API)."""
    st = load_state()
    st[api] = entry
    STATE_FILE.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------
# harvest driver
# ---------------------------------------------------------------------------------------------------------------
def harvest(api: str, args) -> dict:
    import httpx
    fetch, mapper, _portal, _mode = APIS[api]
    frm, to = date.fromisoformat(args.frm), date.fromisoformat(args.to)
    sig = f"{frm}|{to}|{int(args.open_only)}"
    skey = api + (f":{args.scan_from}..{args.scan_to}" if args.scan_from or args.scan_to else "")
    state = load_state()
    mine = state.get(skey, {})
    if args.fresh or mine.get("sig") != sig or mine.get("done"):
        mine = {"sig": sig, "cursor": {}, "done": False, "stored": 0, "seen": 0}
    ctx = Ctx(frm, to, args.open_only, args.max, date.today(), None, mine, args.dry_run)
    ctx.scan_from = date.fromisoformat(args.scan_from) if args.scan_from else None
    ctx.scan_to = date.fromisoformat(args.scan_to) if args.scan_to else None
    stats = dict(api=api, seen=0, in_scope=0, stored=0, defence_tagged=0, relevant=0, out_of_scope=0, error=None,
                 seconds=0.0, resumed=bool(mine["cursor"]), examples=[])
    t0 = time.time()
    conn = None if args.dry_run else connect()
    with httpx.Client(timeout=90, follow_redirects=True, headers={"User-Agent": UA}) as client:
        ctx.client = client
        try:
            capped = False
            for page, cursor, total in fetch(ctx):
                batch = []
                for raw in page:
                    stats["seen"] += 1
                    try:
                        rec = finalize(api, mapper(raw), ctx)
                    except Exception as e:      # one malformed record must not stop a harvest
                        stats["out_of_scope"] += 1
                        print(f"    map error {type(e).__name__}: {str(e)[:80]}", flush=True)
                        continue
                    if rec is None:
                        stats["out_of_scope"] += 1
                        continue
                    batch.append(rec)
                    if args.max and stats["in_scope"] + len(batch) >= args.max:
                        capped = True
                        break
                stats["in_scope"] += len(batch)
                for r in batch:
                    if r["defence_tags"]:
                        stats["defence_tagged"] += 1
                    if "kssl_relevant" in r["defence_tags"]:
                        stats["relevant"] += 1
                        if len(stats["examples"]) < 4:
                            stats["examples"].append((r["title"][:90], (r["buyer_name"] or "")[:50], r["defence_tags"]))
                if batch and conn:
                    stats["stored"] += upsert(conn, api, batch)
                elif batch:
                    stats["stored"] += len({r["notice_id"] for r in batch})
                if not args.dry_run:
                    mine["cursor"], mine["seen"], mine["stored"] = cursor, stats["seen"], stats["stored"]
                    save_state(skey, mine)
                print(f"  [{api}] seen={stats['seen']} stored={stats['stored']} tagged={stats['defence_tagged']} "
                      f"relevant={stats['relevant']} (api: {total})", flush=True)
                if capped:
                    break
            else:
                if not args.dry_run:
                    mine["done"] = True
                    save_state(skey, mine)
        except MissingKey as e:
            stats["error"] = f"MISSING KEY: {e}"
        except Exception as e:
            stats["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    stats["seconds"] = round(time.time() - t0, 1)
    if conn:
        conn.close()
    return stats


# ---------------------------------------------------------------------------------------------------------------
# staging step: tender_raw -> market_tender stub + market_tender_source + tender_raw.status 'staged'
# ---------------------------------------------------------------------------------------------------------------
def notice_state(api: str, raw: dict, deadline_at: datetime | None, published_at: date | None, today: date):
    """-> (status in open|closing|awarded|closed or None, url_kind). Only what the notice type / API status states."""
    def timed():
        if deadline_at is None:
            return None
        if deadline_at.date() < today:
            return "closed"
        return "closing" if (deadline_at.date() - today).days <= 7 else "open"
    if api == "ted_eu":
        nt = raw.get("notice-type") or ""
        if nt.startswith("can") or nt == "veat":
            return "awarded", "award"
        if nt.startswith("cn"):
            return timed(), "notice"
        return None, "notice"                      # prior-information / buyer-profile / other: not a call for bids
    if api == "gem_india":
        return timed(), "notice"
    if api == "canada":
        return (timed() if (raw.get("tenderStatus-appelOffresStatut-eng") or "Open") == "Open" else "closed"), "notice"
    if api == "uk_fts":
        tags = raw.get("tag") or []
        if "tenderCancellation" in tags:
            return "closed", "notice"
        if "award" in tags or "contract" in tags or "awardUpdate" in tags:
            return "awarded", "award"
        if "tender" in tags or "tenderUpdate" in tags:
            return timed(), "notice"
        return None, "notice"                      # planning
    if api == "prozorro_ua":
        st = raw.get("status")
        if st == "complete":
            return "awarded", "award"
        if st in ("cancelled", "unsuccessful"):
            return "closed", "notice"
        return (timed() or "open"), "notice"
    if api == "decp_fr":
        return "awarded", "award"
    if api == "diavgeia_gr":
        t = (raw.get("decisionType") or {}).get("uid") or ""
        if t in ("Δ.2.2", "Γ.3.4"):
            return "awarded", "award"
        if t == "Δ.2.1" and published_at and (today - published_at).days <= 45:
            return "open", "notice"                # tender summary; deadline is only in the PDF
        return None, "notice"
    if api == "sam_us":
        return timed(), "notice"
    return None, "notice"


def stub_url(api: str, notice_url: str, raw: dict) -> str:
    """URL the tender prompt will fetch (prompts.render.fetch_document: html/text only). TED pages answer a WAF challenge
    (http 202) to plain HTTP and GeM serves a PDF - both are staged anyway and flagged in the report."""
    if api == "canada":      # noticeURL is often an external portal (MERX/Ariba, login); the CanadaBuys page is public
        ref = (raw.get("referenceNumber-numeroReference") or "").strip().lower()
        if ref:
            return f"https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/{ref}"
    if api == "decp_fr" and raw.get("id"):
        return f"{DECP}?where=id%3D%22{raw['id']}%22"
    return notice_url


# ---- one procurement = one tender (user decision 2026-10-18) ---------------------------------------------------------------------
# A re-publication or corrigendum of a notice is the same tender: it becomes a market_tender_source row (with its notice number) on the
# existing tender, never a second tender. The key says which notices are one procurement:
#   uk_fts                       the OCDS ocid (shared by every release of one procurement)
#   prozorro_ua, decp_fr, diavgeia_gr   never merged: each record IS its own procurement / contract / decision
#   every other portal           same title + buyer + deadline date (the deadline is required at harvest time; award notices
#                                without one are merged after extraction by merge_duplicate_tenders, which also checks the winner)
NEVER_MERGE = {"prozorro_ua", "decp_fr", "diavgeia_gr"}
MERGE_CHILDREN = (("market_tender_fit_assessment", "assessment_id"), ("market_tender_product_match", "tender_match_id"),
                  ("market_tender_competitor_fit", "competitor_fit_id"), ("market_tender_eligibility", "eligibility_id"),
                  ("market_tender_requirement", "requirement_id"), ("market_tender_closing_window", "closing_window_id"),
                  ("market_top_opportunity_tender", "top_opportunity_tender_id"), ("market_next_move", "next_move_id"))
LATEST_WINS = ("status", "closing_date", "deadline_text", "days_remaining", "is_live", "latest_milestone")


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def notice_key(api: str, raw: dict | None, title, buyer, deadline, need_deadline: bool) -> tuple | None:
    """The procurement a notice belongs to, or None when it is never merged / cannot be keyed."""
    if api in NEVER_MERGE:
        return None
    if api == "uk_fts":
        ocid = (raw or {}).get("ocid")
        return ("ocid", ocid) if ocid else None
    d = deadline.date() if isinstance(deadline, datetime) else deadline
    if not _norm(title) or not _norm(buyer) or (need_deadline and d is None):
        return None
    return ("text", api, _norm(title), _norm(buyer), d)


def merge_duplicate_tenders(cur, dry_run: bool = False) -> dict:
    """Merge the market_tender rows that are one procurement (see the group rule below). The kept tender: the one
    with the most assessment rows, then the latest notice. It takes the latest notice's status / closing fields, the earliest
    published_date, and any value it lacks from the others. Every notice's source row moves to it with its notice number; children
    move when the kept tender has none of that kind (else the duplicate's copy is dropped with its fact_source rows); raw notices,
    opportunities, story steps and fact_source rows are re-pointed. A group whose notices name different winners is NOT merged
    (separate lots / contracts): it is reported. `cur` = a dict cursor; the caller commits."""
    from prompts.derive_comp import norm_org
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='staging' AND table_name='market_tender'")
    cols = [r["column_name"] for r in cur.fetchall() if r["column_name"] not in ("tender_id", "created_at", "updated_at", "rank_position")]
    cur.execute("""SELECT t.*, r.source_api AS _api, r.raw AS _raw, r.title AS _rt, r.buyer_name AS _rb, r.deadline_at AS _rd
                   FROM staging.market_tender t JOIN staging.tender_raw r ON r.tender_id = t.tender_id""")
    # the group = the user's definition (same title + buyer + closing date on the stored tender); inside it the portal rule decides
    # (never for prozorro / decp / diavgeia, the same ocid for UK, else one group)
    keyed: dict = {}
    ocid_only: dict = {}
    for r in cur.fetchall():
        api = r["_api"]
        if api in NEVER_MERGE:
            continue
        sub = ("ocid", (r["_raw"] or {}).get("ocid")) if api == "uk_fts" else ("text",)
        if sub[-1] is None:
            continue
        keyed.setdefault((_norm(r["title"]), _norm(r["buyer_name"]), r["closing_date"], sub), {})[r["tender_id"]] = r
        if api == "uk_fts":
            ocid_only.setdefault(sub[1], set()).add(r["tender_id"])
    out = {"groups": 0, "merged_tenders": 0, "skipped_winner_conflict": 0, "skipped_examples": [],
           "uk_same_ocid_other_title": sum(1 for v in ocid_only.values() if len(v) > 1)}
    for k, by_id in keyed.items():
        if len(by_id) < 2:
            continue
        rows = list(by_id.values())
        winners = {frozenset(norm_org(w) for w in x["awarded_to"].split(";") if w.strip()) for x in rows if (x.get("awarded_to") or "").strip()}
        if len(winners) > 1:
            out["skipped_winner_conflict"] += 1
            if len(out["skipped_examples"]) < 5:
                out["skipped_examples"].append((rows[0]["title"][:60], [sorted(w) for w in winners][:3]))
            continue
        ids_ = [x["tender_id"] for x in rows]
        cur.execute("SELECT tender_id, count(*) n FROM staging.market_tender_fit_assessment WHERE tender_id = ANY(%s) GROUP BY 1", (ids_,))
        assessed = {r["tender_id"]: r["n"] for r in cur.fetchall()}
        latest = max(rows, key=lambda x: (x["published_date"] or date.min, x["tender_id"]))
        keep = max(rows, key=lambda x: (assessed.get(x["tender_id"], 0), x["published_date"] or date.min, x["tender_id"]))
        drop = [x for x in rows if x["tender_id"] != keep["tender_id"]]
        out["groups"] += 1
        out["merged_tenders"] += len(drop)
        if dry_run:
            continue
        kid = keep["tender_id"]
        # 1. the kept row: latest notice's status / closing fields, earliest publication, gaps filled from the others (latest first)
        upd = {c: latest[c] for c in LATEST_WINS if c in cols and latest.get(c) not in (None, "")}
        pubs = [x["published_date"] for x in rows if x["published_date"]]
        if pubs:
            upd["published_date"] = min(pubs)
        for c in cols:
            if c not in upd and keep.get(c) in (None, ""):
                v = next((x[c] for x in sorted(drop, key=lambda x: x["published_date"] or date.min, reverse=True) if x.get(c) not in (None, "")), None)
                if v is not None:
                    upd[c] = v
        if upd:
            cur.execute(f"UPDATE staging.market_tender SET {', '.join(f'{c} = %s' for c in upd)}, updated_at = now() WHERE tender_id = %s",
                        (*[psycopg2_json(v) for v in upd.values()], kid))
        cur.execute("UPDATE staging.market_tender_source SET notice_reference = %s WHERE tender_id = %s AND notice_reference IS NULL",
                    (keep.get("notice_reference"), kid))
        for d in drop:
            did = d["tender_id"]
            # 2. every notice stays: its source rows move, with its notice number, as secondary sources
            cur.execute("""UPDATE staging.market_tender_source SET tender_id = %s, is_primary = false,
                                  notice_reference = coalesce(notice_reference, %s) WHERE tender_id = %s""", (kid, d.get("notice_reference"), did))
            # 3. children: move when the kept tender has none of that kind, else drop the duplicate's copy (+ its fact_source rows)
            for table, key in MERGE_CHILDREN:
                cur.execute(f"SELECT 1 FROM staging.{table} WHERE tender_id = %s LIMIT 1", (kid,))
                if cur.fetchone() is None:
                    cur.execute(f"UPDATE staging.{table} SET tender_id = %s WHERE tender_id = %s", (kid, did))
                    continue
                cur.execute(f"SELECT {key}::text AS k FROM staging.{table} WHERE tender_id = %s", (did,))
                gone = [r["k"] for r in cur.fetchall()]
                if not gone:
                    continue
                if table == "market_tender_product_match":
                    cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'market_tender_product_match_line' AND row_id IN "
                                "(SELECT match_line_id::text FROM staging.market_tender_product_match_line WHERE tender_match_id::text = ANY(%s))", (gone,))
                    cur.execute("DELETE FROM staging.market_tender_product_match_line WHERE tender_match_id::text = ANY(%s)", (gone,))
                cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = ANY(%s)", (table, gone))
                cur.execute(f"DELETE FROM staging.{table} WHERE tender_id = %s", (did,))
            # 4. everything else that points at the duplicate points at the kept tender
            cur.execute("UPDATE staging.tender_raw SET tender_id = %s WHERE tender_id = %s", (kid, did))
            cur.execute("UPDATE staging.market_opportunity SET tender_id = %s WHERE tender_id = %s", (kid, did))
            cur.execute("UPDATE staging.fact_source SET row_id = %s WHERE table_name = 'market_tender' AND row_id = %s", (str(kid), str(did)))
            cur.execute("UPDATE staging.story_step SET source_row_id = %s WHERE source_table = 'market_tender' AND source_row_id = %s", (str(kid), str(did)))
            cur.execute("DELETE FROM staging.market_tender WHERE tender_id = %s", (did,))
    return out


def same_procurement(cur, api: str, raw_id: str, raw: dict, title, buyer, deadline):
    """tender_id of an already staged notice of the same procurement (notice_key with the deadline required), else None."""
    k = notice_key(api, raw, title, buyer, deadline, need_deadline=True)
    if k is None:
        return None
    norm = "lower(btrim(regexp_replace({c}, '\\s+', ' ', 'g')))"
    if k[0] == "ocid":
        cur.execute("""SELECT r.tender_id FROM staging.tender_raw r JOIN staging.market_tender t ON t.tender_id = r.tender_id
                       WHERE r.source_api = 'uk_fts' AND r.raw->>'ocid' = %s AND r.raw_id <> %s::uuid LIMIT 1""", (k[1], raw_id))
    else:
        cur.execute(f"""SELECT r.tender_id FROM staging.tender_raw r JOIN staging.market_tender t ON t.tender_id = r.tender_id
                        WHERE r.source_api = %s AND {norm.format(c='r.title')} = %s AND {norm.format(c='r.buyer_name')} = %s
                          AND r.deadline_at::date = %s AND r.raw_id <> %s::uuid LIMIT 1""", (k[1], k[2], k[3], k[4], raw_id))
    r = cur.fetchone()
    return r[0] if r else None


def psycopg2_json(v):
    """dict / list values (jsonb columns) go back as JSON."""
    if isinstance(v, (dict, list)):
        import psycopg2.extras
        return psycopg2.extras.Json(v)
    return v


def stage(args) -> dict:
    today = date.today()
    frm, to = date.fromisoformat(args.frm), date.fromisoformat(args.to)
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT raw_id::text, source_api, notice_id, notice_url, title, buyer_name, country, published_at, deadline_at,
                          value_text, defence_tags, raw FROM staging.tender_raw
                   WHERE status = 'new' AND 'kssl_relevant' = ANY(defence_tags)
                   ORDER BY source_api, published_at DESC NULLS LAST""")
    rows = cur.fetchall()
    portfolio_check(cur)
    # tenders that were put in by hand / the test seed (ids below 2**61): never stub the same notice URL a second time
    cur.execute("SELECT source_url, min(tender_id) FROM staging.market_tender_source WHERE tender_id < %s AND source_url IS NOT NULL GROUP BY 1",
                (2 ** 61,))
    foreign = dict(cur.fetchall())
    out = dict(candidates=len(rows), staged=0, not_staged={}, by_api={}, examples=[], linked_existing=0)
    for rid, api, nid, url, title, buyer, country, pub, dl, value, tags, raw in rows:
        st, kind = notice_state(api, raw or {}, dl, pub, today)
        reason = None
        if st is None:
            reason = "not a bidding/award notice"
        elif st == "closed" and not (getattr(args, "closed_months", 0) and (dl.date() if dl else pub) and (dl.date() if dl else pub) >= today - timedelta(days=30 * args.closed_months)):
            reason = "closed (deadline passed or cancelled)"
        elif st == "awarded" and not (pub and frm <= pub <= to):
            reason = "award outside window"
        if reason:
            out["not_staged"][reason] = out["not_staged"].get(reason, 0) + 1
            continue
        raw_uuid = uuid.UUID(rid)
        tid, sid = tender_id_of(raw_uuid), source_id_of(raw_uuid)
        su = stub_url(api, url, raw or {})
        if su in foreign:                                  # already a market_tender: link, do not duplicate
            out["linked_existing"] += 1
            if not args.dry_run:
                cur.execute("UPDATE staging.tender_raw SET tender_id = %s, status = 'staged' WHERE raw_id = %s::uuid", (foreign[su], rid))
            continue
        same = same_procurement(cur, api, rid, raw or {}, title, buyer, dl)
        if same is not None:                               # a re-publication / corrigendum: a source row on the existing tender
            out["merged_republication"] = out.get("merged_republication", 0) + 1
            if not args.dry_run:
                cur.execute("DELETE FROM staging.market_tender_source WHERE source_id = %s", (sid,))
                cur.execute("""INSERT INTO staging.market_tender_source (source_id, tender_id, source_url, is_primary, portal_name, publisher, source_type,
                                                                         notice_reference)
                               VALUES (%s,%s,%s,false,%s,%s,%s,%s)""",
                            (sid, same, su, APIS[api][2][:240], (buyer or "")[:240] or None, kind, (nid or "")[:160] or None))
                cur.execute("UPDATE staging.tender_raw SET tender_id = %s, status = 'staged' WHERE raw_id = %s::uuid", (same, rid))
            continue
        out["staged"] += 1
        out["by_api"][api] = out["by_api"].get(api, 0) + 1
        if len(out["examples"]) < 5:
            out["examples"].append((api, tid, st, kind, (title or "")[:70], su))
        if args.dry_run:
            continue
        cur.execute("DELETE FROM staging.market_tender_source WHERE tender_id = %s", (tid,))
        cur.execute("DELETE FROM staging.market_tender WHERE tender_id = %s", (tid,))
        cur.execute("""INSERT INTO staging.market_tender (tender_id, title, status, url_kind, source_url, buyer_name, country_name,
                         published_date, closing_date, notice_reference, value_text, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now())""",
                    (tid, title or "(untitled)", st, kind, su, buyer, (country or "")[:160] or None, pub,
                     dl.date() if dl else None, (nid or "")[:160], value))
        cur.execute("""INSERT INTO staging.market_tender_source (source_id, tender_id, source_url, is_primary, portal_name, publisher, source_type)
                       VALUES (%s,%s,%s,true,%s,%s,%s)""",
                    (sid, tid, su, APIS[api][2][:240], (buyer or "")[:240] or None, kind))
        cur.execute("UPDATE staging.tender_raw SET tender_id = %s, status = 'staged' WHERE raw_id = %s::uuid", (tid, rid))
        if out["staged"] % 200 == 0:
            conn.commit()
    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    conn.close()
    return out


def portfolio_check(cur):
    """The KSSL scope comes from staging.client_product; warn when its categories drift from KSSL_CATEGORIES."""
    cur.execute("SELECT DISTINCT category FROM staging.client_product WHERE category IS NOT NULL")
    cats = {r[0] for r in cur.fetchall()}
    missing = sorted(cats - set(KSSL_CATEGORIES) - {"Other"})
    if missing:
        print(f"  WARNING client_product categories without a tender mapping: {missing}")
    return cats


def report():
    conn = connect()
    cur = conn.cursor()
    cats = portfolio_check(cur)
    print("KSSL portfolio categories in client_product:", ", ".join(sorted(cats)))
    cur.execute("""SELECT source_api, count(*), count(*) FILTER (WHERE 'kssl_relevant' = ANY(defence_tags)),
                          count(*) FILTER (WHERE status = 'staged'), count(*) FILTER (WHERE deadline_at >= now()),
                          min(published_at), max(published_at)
                   FROM staging.tender_raw GROUP BY 1 ORDER BY 1""")
    print(f"{'source_api':13s} {'defence':>8s} {'kssl_rel':>8s} {'staged':>7s} {'open':>6s}  published")
    for r in cur.fetchall():
        print(f"{r[0]:13s} {r[1]:8d} {r[2]:8d} {r[3]:7d} {r[4]:6d}  {r[5]}..{r[6]}")
    cur.execute("""SELECT source_api, t, count(*) FROM staging.tender_raw, unnest(defence_tags) t
                   WHERE t LIKE 'kssl:%' GROUP BY 1,2 ORDER BY 1, 3 DESC""")
    by = {}
    for api, t, n in cur.fetchall():
        by.setdefault(api, []).append(f"{t[5:]}:{n}")
    print("KSSL-relevant per category (a notice can match several):")
    for api, v in by.items():
        print(f"  {api}: " + ", ".join(v))
    conn.close()


def retag(args):
    """Recompute defence_tags for every stored row from its stored raw record (no network); delete rows that are not
    defence at all; un-stage our own stubs whose notice is no longer kssl_relevant."""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT raw_id::text, source_api, raw, defence_tags, status, tender_id FROM staging.tender_raw ORDER BY source_api")
    rows = cur.fetchall()
    upd = dele = unstaged = 0
    for rid, api, raw, old_tags, status, tid in rows:
        if api not in APIS:
            continue
        try:
            rec = APIS[api][1](raw)
            tags = make_tags(rec["text"], rec["cpv_codes"], rec["buyer_name"], scoped=rec["scoped"])
        except Exception as e:
            print(f"  retag error {api} {rid}: {str(e)[:80]}")
            continue
        if not tags:
            if tid and tid >= 2 ** 61:
                cur.execute("DELETE FROM staging.market_tender_source WHERE tender_id = %s", (tid,))
                cur.execute("DELETE FROM staging.market_tender WHERE tender_id = %s", (tid,))
            cur.execute("DELETE FROM staging.tender_raw WHERE raw_id = %s::uuid", (rid,))
            dele += 1
            continue
        if status == "staged" and "kssl_relevant" not in tags and tid and tid >= 2 ** 61:
            cur.execute("DELETE FROM staging.market_tender_source WHERE tender_id = %s", (tid,))
            cur.execute("DELETE FROM staging.market_tender WHERE tender_id = %s", (tid,))
            cur.execute("UPDATE staging.tender_raw SET tender_id = NULL, status = 'new' WHERE raw_id = %s::uuid", (rid,))
            unstaged += 1
        if sorted(tags) != sorted(old_tags or []):
            cur.execute("UPDATE staging.tender_raw SET defence_tags = %s::text[] WHERE raw_id = %s::uuid", (tags, rid))
            upd += 1
    conn.commit()
    conn.close()
    print(f"retag: rows={len(rows)} tags_changed={upd} deleted_non_defence={dele} unstaged={unstaged}")


# ---------------------------------------------------------------------------------------------------------------
# selftest: fictional records, no network, no database
# ---------------------------------------------------------------------------------------------------------------
def selftest():
    assert raw_id_of("ted_eu", "1-2026") == uuid.uuid5(uuid.NAMESPACE_URL, "ted_eu|1-2026")
    tid = tender_id_of(raw_id_of("ted_eu", "1-2026"))
    assert 2 ** 61 <= tid < 2 ** 62 and tid == tender_id_of(raw_id_of("ted_eu", "1-2026")) and tid > 9202003
    assert source_id_of(raw_id_of("ted_eu", "1-2026")) != tid
    assert fmt_value(12157584.33, "CHF") == "CHF 12,157,584.33" and fmt_value(120000.0, "GBP") == "GBP 120,000"
    assert to_date("2026-01-19+01:00") == date(2026, 1, 19) and to_date("16/10/2026 03:00:00") == date(2026, 10, 16)
    assert parse_ts("2026-10-17T09:00:00Z").hour == 9 and parse_ts("garbage") is None

    # tagging
    assert "ammunition" in tag_text("Supply of 155mm artillery shell ammunition") and "artillery" in tag_text("Self-propelled howitzer 155 mm")
    assert "uav_drones" in tag_text("Counter-UAS drone detection and neutralisation system")
    assert "uav_drones" in tag_text("Beschaffung von Drohnen und Aufklärungsdrohnen")           # de (our extras)
    assert "small_arms" in tag_text("Pistole und Sturmgewehr") and "ammunition" in tag_text("Боєприпаси 155 мм")
    assert "protected_vehicles" in tag_text("Procurement of MRAP armoured personnel carriers")
    assert tag_text("Supply of toner cartridges and office furniture") == []
    assert "missiles_air_defence" not in tag_text("Lieferung Beleuchtungsstinger Löschfahrzeug") and "missiles_air_defence" in tag_text("Stinger missile launchers")
    assert "ammunition" in tag_text("Lieferung von Artilleriemunition")
    assert "missiles_air_defence" not in tag_text("vehicule de stingere a incendiilor")
    assert make_tags("Printer toner", [], "City Council") == []
    # KSSL portfolio vocabulary (staging.client_product)
    assert "kssl:ammunition" in make_tags("Supply of fuzes for 155mm projectiles", [], None)
    assert "kssl:armoured_vehicle_mro" in make_tags("Overhaul of armoured vehicle road wheels and sprockets", [], None)
    assert "kssl:precision_forgings" in make_tags("Gun barrel forging 120 mm", [], None)
    assert "kssl:naval" in make_tags("Steering gear and rudder stock for patrol vessel", [], None)
    assert make_tags("Water tank cleaning service", [], None) == [] and make_tags("Shell plc fuel cards", [], None) == []
    assert make_tags("Catering", [], "Ministry of Defence") == ["general_defence"]                  # defence, but no KSSL flag
    assert set(KSSL_CATEGORIES.values()) == KSSL_KEYS and len(KSSL_KEYS) == 9
    assert make_tags("Catering services", [], "Ministry of Defence of Fictionland") == ["general_defence"]
    assert make_tags("Rifles", ["35321000"], None)[0] == "small_arms"
    assert make_tags("x", ["35321000"], None) == ["small_arms", "kssl_relevant", "kssl:small_arms"]
    assert make_tags("Training services", ["35700000"], None) == ["general_defence"]
    assert make_tags("Tunnel maintenance", ["35100000"], "Wegschap Tunnel") == []
    assert defence_buyer("Ministerio de Defensa") and defence_buyer("Defence Equipment & Support")
    assert not defence_buyer("Sevenoaks District Council") and not defence_buyer("Defensor del Pueblo")

    # TED mapping (fictional record, shaped like the v3 API)
    ted = {"publication-number": "999999-2026", "notice-type": "cn-standard", "publication-date": "2026-05-04+02:00",
           "notice-title": {"eng": ["Supply of 155 mm artillery ammunition"], "deu": ["Lieferung von Artilleriemunition"]},
           "buyer-name": {"deu": ["Bundesministerium der Verteidigung (fiktiv)"]}, "buyer-country": ["DEU"],
           "classification-cpv": ["35330000", "35330000", "35341000"],
           "deadline-receipt-tender-date-lot": ["2026-11-30+01:00", "2026-12-15+01:00"],
           "estimated-value-lot": [1000000, 2500000], "estimated-value-cur-lot": ["EUR", "EUR"],
           "links": {"html": {"ENG": "https://ted.example/en/notice/-/detail/999999-2026", "DEU": "https://ted.example/de/x"},
                     "pdf": {"ENG": "https://ted.example/en/notice/999999-2026/pdf", "FRA": "https://ted.example/fr/x"}}}
    m = map_ted(ted)
    assert m["notice_id"] == "999999-2026" and m["country"] == "Germany" and m["published_at"] == date(2026, 5, 4)
    assert m["deadline_at"].date() == date(2026, 12, 15) and m["cpv_codes"] == ["35330000", "35341000"]
    assert m["notice_url"].endswith("detail/999999-2026") and "DEU" not in m["raw"]["links"]["html"]
    assert m["value_text"].startswith("estimated lot value EUR 1,000,000")
    ctx = Ctx(date(2026, 1, 17), date(2026, 10, 17), False, 0, date(2026, 10, 17), None, {}, True)
    f = finalize("ted_eu", m, ctx)
    assert f and f["status"] == "new" and "ammunition" in f["defence_tags"] and "kssl_relevant" in f["defence_tags"] and "kssl:ammunition" in f["defence_tags"]
    assert notice_state("ted_eu", ted, f["deadline_at"], f["published_at"], date(2026, 10, 17)) == ("open", "notice")
    assert notice_state("ted_eu", {"notice-type": "can-standard"}, None, None, date(2026, 10, 17)) == ("awarded", "award")
    assert notice_state("ted_eu", {"notice-type": "pin-only"}, None, None, date(2026, 10, 17))[0] is None
    assert stub_url("ted_eu", m["notice_url"], m["raw"]) == m["notice_url"]
    assert stub_url("canada", "https://merx.example/x", {"referenceNumber-numeroReference": "CB-445-1"}).endswith("/tender-notice/cb-445-1")
    civil = map_ted({"publication-number": "1-2026", "publication-date": "2026-02-01+01:00", "notice-type": "can-standard",
                     "notice-title": {"nld": ["Onderhoud tunnel"]}, "buyer-name": {"nld": ["Wegschap"]}, "buyer-country": ["NLD"],
                     "classification-cpv": ["35100000"]})
    fc = finalize("ted_eu", civil, ctx)
    assert fc is None                                                           # civil CPV-35 notice: not harvested
    old = map_ted({"publication-number": "2-2025", "publication-date": "2025-02-01+01:00", "notice-title": {"eng": ["Rifles"]},
                   "classification-cpv": ["35321000"]})
    assert finalize("ted_eu", old, ctx) is None                                 # out of window and not open
    old["deadline_at"] = datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert finalize("ted_eu", old, ctx) is not None                             # ... but open -> in
    q = ted_query(date(2026, 1, 17), date(2026, 10, 17), date(2026, 10, 17), False)
    assert "classification-cpv=35*" in q and "20260117" in q and "deadline-receipt-tender-date-lot>=20261017" in q
    assert ted_query(date(2026, 1, 17), date(2026, 10, 17), date(2026, 10, 17), False, True).startswith("(classification-cpv=353*")
    assert "publication-date" not in ted_query(date(2026, 1, 17), date(2026, 10, 17), date(2026, 10, 17), True)

    # GeM
    g = {"id": "9479676", "b_id": [9479676], "b_bid_number": ["GEM/2026/B/0000001"], "b_category_name": ["Fictional 5.56 mm ball ammunition"],
         "final_start_date_sort": ["2026-06-17T11:47:26Z"], "final_end_date_sort": ["2026-11-02T09:00:00Z"],
         "ba_official_details_minName": ["Ministry of Defence"], "ba_official_details_deptName": ["Department of Military Affairs"]}
    gm = map_gem(g)
    assert gm["notice_id"] == "GEM/2026/B/0000001" and gm["notice_url"].endswith("/showbidDocument/9479676")
    assert gm["buyer_name"] == "Ministry of Defence - Department of Military Affairs" and gm["country"] == "India"
    fg = finalize("gem_india", gm, ctx)
    assert fg["defence_tags"] and "ammunition" in fg["defence_tags"]
    assert notice_state("gem_india", g, fg["deadline_at"], fg["published_at"], date(2026, 10, 17)) == ("open", "notice")
    assert notice_state("gem_india", g, fg["deadline_at"], fg["published_at"], date(2026, 10, 28)) == ("closing", "notice")

    # Canada
    row = {"referenceNumber-numeroReference": "PW-26-0001", "title-titre-eng": "Fictional Light Utility Armoured Vehicle",
           CB_ENTITY: "Department of National Defence", "publicationDate-datePublication": "2026-09-01",
           "tenderClosingDate-appelOffresDateCloture": "2026-12-01T14:00:00", "noticeURL-URLavis-eng": "https://canadabuys.example/n/1",
           "contactInfoEmail-informationsContactCourriel": "x@example.invalid", "tenderStatus-appelOffresStatut-eng": "Open"}
    assert cb_is_defence(row) and not cb_is_defence({CB_ENTITY: "Parks Canada"})
    cm = map_canada(row)
    assert "contactInfoEmail-informationsContactCourriel" not in cm["raw"] and cm["country"] == "Canada"

    # UK
    rel = {"id": "123456-2026", "tag": ["tender"], "date": "2026-09-10T10:00:00+01:00", "buyer": {"name": "Defence Equipment & Support"},
           "tender": {"title": "Fictional Mortar Systems 81mm", "description": "Supply of mortar and bombs",
                      "value": {"amount": 250000.0, "currency": "GBP"}, "tenderPeriod": {"endDate": "2026-11-20T12:00:00+00:00"},
                      "items": [{"id": "1", "additionalClassifications": [{"scheme": "CPV", "id": "35300000"}]}],
                      "lots": [{"id": "1", "awardCriteria": {"criteria": ["bulky"]}}]}}
    um = map_uk(rel)
    assert um["cpv_codes"] == ["35300000"] and um["value_text"] == "GBP 250,000" and "awardCriteria" not in um["raw"]["tender"]["lots"][0]
    fu = finalize("uk_fts", um, ctx)
    assert fu and fu["defence_tags"] and um["notice_url"].endswith("/Notice/123456-2026")
    assert finalize("uk_fts", map_uk({"id": "9-2026", "date": "2026-09-10T10:00:00+01:00", "tender": {"title": "Roof works"},
                                      "buyer": {"name": "A Council"}}), ctx) is None

    # Prozorro / DECP / Diavgeia / SAM
    pz = {"id": "abc", "tenderID": "UA-2026-09-01-000001-a", "title": "Закупівля боєприпасів", "status": "active.tendering",
          "procurementMethodType": "aboveThresholdUA.defense", "procuringEntity": {"name": "Військова частина А0000"},
          "value": {"amount": 5000000, "currency": "UAH"}, "tenderPeriod": {"startDate": "2026-09-01T10:00:00+03:00", "endDate": "2026-11-02T10:00:00+02:00"},
          "datePublished": "2026-09-01T10:00:00+03:00", "items": [{"classification": {"scheme": "CPV", "id": "35330000-5"}}]}
    pm = map_prozorro(pz)
    assert pm["notice_url"].endswith("UA-2026-09-01-000001-a") and pm["value_text"] == "UAH 5,000,000"
    assert "ammunition" in finalize("prozorro_ua", pm, ctx)["defence_tags"]
    assert is_pz_defence({"procurementMethodType": "simple.defense"})
    assert not is_pz_defence({"procuringEntity": {"kind": "general"}, "procurementMethodType": "aboveThreshold"})
    assert not is_pz_defence({"procuringEntity": {"kind": "defense"}, "procurementMethodType": "reporting"})
    assert is_pz_defence({"procuringEntity": {"kind": "defense"}, "procurementMethodType": "aboveThreshold"})
    assert notice_state("prozorro_ua", pz, pm["deadline_at"], pm["published_at"], date(2026, 10, 17))[0] == "open"
    dm = map_decp({"id": "2026X1", "objet": "Acquisition de munitions 9mm", "codecpv": "35300000-7", "acheteur_id": "123", "montant": 160000.0,
                   "datenotification": "2026-10-07"})
    assert dm["cpv_codes"] == ["35300000"] and dm["value_text"] == "EUR 160,000" and notice_state("decp_fr", {}, None, None, date.today())[1] == "award"
    assert "ammunition" in finalize("decp_fr", dm, ctx)["defence_tags"]
    dg = {"ada": "ΨΨΨ1-ΑΒΓ", "subject": "Προμήθεια πυρομαχικών", "issueDate": "16/10/2026 03:00:00", "documentUrl": "https://diavgeia.gov.gr/doc/ΨΨΨ1-ΑΒΓ",
          "decisionType": {"uid": "Δ.2.1", "label": "ΠΕΡΙΛΗΨΗ ΔΙΑΚΗΡΥΞΗΣ"}, "organization": {"uid": "6", "label": "ΥΠΟΥΡΓΕΙΟ ΕΘΝΙΚΗΣ ΑΜΥΝΑΣ"}}
    gdm = map_diavgeia(dg)
    assert gdm["published_at"] == date(2026, 10, 16) and "ammunition" in finalize("diavgeia_gr", gdm, ctx)["defence_tags"]
    assert notice_state("diavgeia_gr", dg, None, date(2026, 10, 16), date(2026, 10, 17)) == ("open", "notice")
    sm = map_sam({"noticeId": "n1", "title": "Fictional 120mm mortar ammunition", "fullParentPathName": "DEPT OF DEFENSE.ARMY", "postedDate": "2026-09-30",
                  "responseDeadLine": "2026-11-15T17:00:00-05:00"})
    assert sm["notice_url"].endswith("/n1/view") and sm["deadline_at"].date() == date(2026, 11, 15)
    saved = os.environ.pop("SAM_API_KEY", None)
    try:
        next(fetch_sam(ctx))
        raise AssertionError("expected MissingKey")
    except MissingKey:
        pass
    finally:
        if saved is not None:
            os.environ["SAM_API_KEY"] = saved
    # DSN guard
    old = os.environ.get("KSSL_STAGING_DSN")
    os.environ["KSSL_STAGING_DSN"] = "host=62.0.0.1 port=5460 dbname=kssl_staging user=a password=b"
    try:
        resolve_dsn()
        raise AssertionError("guard should refuse non-local DSN")
    except SystemExit:
        pass
    finally:
        if old is None:
            os.environ.pop("KSSL_STAGING_DSN", None)
        else:
            os.environ["KSSL_STAGING_DSN"] = old
    assert clean_json({"a": "x\u0000y"}) == '{"a": "xy"}'
    assert clean_json({"v": [float("inf"), float("nan"), 1.5]}) == '{"v": [null, null, 1.5]}'
    assert tag_text("Safe Water Projects and community engagement, communities") == []
    # one procurement = one tender: the merge key per portal
    dl = datetime(2026, 11, 3, 12, 0)
    assert notice_key("prozorro_ua", {}, "T", "B", dl, True) is None and notice_key("decp_fr", {}, "T", "B", dl, True) is None
    assert notice_key("uk_fts", {"ocid": "ocds-1"}, "T", "B", None, True) == ("ocid", "ocds-1") and notice_key("uk_fts", {}, "T", "B", dl, True) is None
    assert notice_key("ted_eu", None, " Parts  for warships ", "Marinha", dl, True) == ("text", "ted_eu", "parts for warships", "marinha", date(2026, 11, 3))
    assert notice_key("ted_eu", None, "T", "B", None, True) is None and notice_key("ted_eu", None, "T", "B", None, False) == ("text", "ted_eu", "t", "b", None)
    print("selftest ok")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Harvest defence tender notices into staging.tender_raw")
    ap.add_argument("--api", default="all", help="|".join(ORDER) + "|all  (comma list; alias uk=uk_fts, ...)")
    ap.add_argument("--from", dest="frm", default=WIN_FROM)
    ap.add_argument("--to", default=WIN_TO)
    ap.add_argument("--open-only", action="store_true", help="only notices whose deadline is today or later")
    ap.add_argument("--scan-from", help="prozorro_ua: scan the feed only from this date (parallel slices; window filter still applies)")
    ap.add_argument("--scan-to", help="prozorro_ua: ... to this date")
    ap.add_argument("--max", type=int, default=0, help="stop after N in-scope notices per API")
    ap.add_argument("--dry-run", action="store_true", help="fetch + map + tag, write nothing")
    ap.add_argument("--fresh", action="store_true", help="ignore the saved resume cursor")
    ap.add_argument("--stage", action="store_true", help="create market_tender stubs for client-relevant open/awarded notices")
    ap.add_argument("--closed-months", dest="closed_months", type=int, default=0, help="--stage: also stage notices that closed within the last N months (status closed)")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--merge", action="store_true", help="merge market_tender rows that are one procurement (re-publications / corrigenda); with --dry-run: count only")
    ap.add_argument("--retag", action="store_true", help="recompute defence_tags/kssl flags of stored rows from stored raw (no network)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.selftest:
        return selftest()
    if args.report:
        return report()
    if args.retag:
        return retag(args)
    if args.merge:
        import psycopg2.extras
        conn = connect()
        try:
            o = merge_duplicate_tenders(conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), dry_run=args.dry_run)
            conn.rollback() if args.dry_run else conn.commit()
        finally:
            conn.close()
        print(f"merge{' (dry-run)' if args.dry_run else ''}: {o['groups']} groups, {o['merged_tenders']} duplicate tenders merged into them; "
              f"{o['skipped_winner_conflict']} groups not merged (different winners: separate lots / contracts); "
              f"UK procurements whose notices share an ocid (any title / date): {o['uk_same_ocid_other_title']}")
        for e in o["skipped_examples"]:
            print("  not merged:", e)
        return
    if args.stage:
        o = stage(args)
        print(f"stage{' (dry-run)' if args.dry_run else ''}: candidates={o['candidates']} staged={o['staged']} linked_to_existing={o['linked_existing']} "
              f"merged_republications={o.get('merged_republication', 0)} by_api={o['by_api']}")
        print(f"  not staged: {o['not_staged']}")
        for e in o["examples"]:
            print("  e.g.", e)
        return
    names = ORDER if args.api == "all" else [ALIASES.get(a, a) for a in args.api.split(",")]
    for n in names:
        if n not in APIS:
            raise SystemExit(f"unknown api {n}; known: {', '.join(ORDER)}")
    for n in names:
        print(f"== {n} window {args.frm}..{args.to}{' open-only' if args.open_only else ''}{' DRY-RUN' if args.dry_run else ''}", flush=True)
        s = harvest(n, args)
        print(f"== {n}: seen={s['seen']} in_scope={s['in_scope']} stored={s['stored']} defence_tagged={s['defence_tagged']} "
              f"client_relevant={s['relevant']} out_of_scope={s['out_of_scope']} {s['seconds']}s"
              + (f" ERROR {s['error']}" if s["error"] else ""), flush=True)
        for e in s["examples"]:
            print("   e.g.", e, flush=True)


if __name__ == "__main__":
    main()
