"""Geo footprint rows from the owner's SIPRI arms-transfer records (staging.sipri_arms_transfer, backend/sipri_import.py). No model.

Owner 2026-10-25: "SIPRI data is my data, which I have gathered, so you can use it completely." Every row this module writes cites
SIPRI (competitive_geo_source + staging.fact_source, https://www.sipri.org/databases/armstransfers).

    python -m backend.sipri_geo --selftest          pure checks (matching, wording), fictional values
    python -m backend.sipri_geo --report [--json F] the plan only: match rate, samples, review lists; writes nothing
    python -m backend.sipri_geo [--dry-run]         write the rows to the LOCAL staging DB (dry run: roll back)

WHICH RECORDS (the window): orders from 2015 on, plus older deals still delivering (last delivery 2015 or later, or deliveries not
complete for an order from 2005 on). SIPRI's `status` is the weapon's condition (N new, S second-hand, R second-hand refurbished);
`delivery_yr` is the last delivery year on record, 0 = deliveries not complete. Skipped: second-hand transfers (S / R: one state's
used stock, not the maker's sale), buyers that are not states (rebels, "unknown recipient(s)", NATO / UN / AU), generic designations
('vehicle engine 401-600').

MATCHING (by code, strict: precision over recall). A record's designation ("K-9 Thunder 155mm") becomes words ("k9", "thunder"),
a calibre (155) and a wheel layout (6x6). A catalogue product (staging.competitive_product, or staging.client_product for KSSL) fits
when its name holds the FIRST word (hyphens and spaces ignored; a model code anywhere, a plain name as the catalogue name's first
word or its initials; a variant suffix is allowed: K9 -> K9A1, Leopard 2 -> Leopard 2A8, never REMUS 100 -> REMUS 300 or Leopard 2A7
-> 2A8), its calibre and wheel layout do not contradict, its category fits SIPRI's category, and it is not a part of a platform
(display, engine for a non-engine record, fuselage, motor, 'work share'...) or a service / programme / test asset. A plain-name
designation needs all its words ('Puma M-26' is not the Puma IFV). The other words raise the score. Then the seller check:
  * seller side: SIPRI's seller is the company's country (its origin, the product's country, or a country where it has a
    'Local production' presence on record): activity Export in the buyer country;
  * licensee side: SIPRI flags local production in the buyer country (raw locInvolvement 1150405) and the company is from the
    buyer country: activity Local production in its home country.
Several companies fit one record on the same side -> no row, listed for review; one company with a higher score than the rest
wins. The client (KSSL) and a competitor from the client's own country both fitting a record of a client-country sale: the
client takes it (its own exports), the competitor co-claim is listed for review.

WRITING (local staging only; review cards: the presence is NEW or CHANGED on the review site). One geo product per company, buyer
and product (several orders of one product by one buyer are one row: quantity = units with SIPRI's description, summed over the
orders; since = the first order year; customer = the buyer as SIPRI names it; note = each order's year, units, last delivery and
condition), its geo source (SIPRI) and fact_source rows tagged document_id 'sipri_transfer:<record id>', one set per record. The
product name is the catalogue name, or SIPRI's designation when the catalogue entry is named for another customer ('Scorpene
Malaysia (...)' for India's order). The product goes
under the company's presence in that country (extended), or a new presence (Export / Active). A record already covered by a row
on record (same catalogue product, order year within one year or not stated) gets only a SIPRI geo source on that row (tag
'sipri_corroborates:<id>'). Existing rows are never changed; only their roll-ups (product count, product list, overlap, the
country's presence types / KSSL summary) are refreshed. A re-run first removes what this module wrote before and builds it again
(a geo prompt re-run deletes its presence bundles, this step puts the SIPRI rows back). Then derive.geo_match_code (KSSL counter-
products, like-for-like gate) and derive.geo_rollup run for the rows written, as after a geo prompt load.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

SOURCE_URL = "https://www.sipri.org/databases/armstransfers"
SOURCE_LABEL = "SIPRI Arms Transfers Database"
PUBLISHER = "SIPRI"
TAG = "sipri_transfer:"                 # fact_source.document_id of a row this module owns
CORROB = "sipri_corroborates:"          # fact_source.document_id of a SIPRI source added to a row written by someone else
PRES_TAG = "sipri_geo:presence"         # fact_source.document_id of a presence this module created
LICENSED = "1150405"                    # raw locInvolvement: produced under licence / locally in the buyer country
WINDOW_FROM = 2015
OPEN_FROM = 2005                        # an order with deliveries not complete counts from this order year on
SKIP_KINDS = {"service", "programme", "not_product", "test_asset"}
SKIP_CATEGORIES = {"training & simulation", "armoured vehicle mro"}

STOP = {
    "apc", "apv", "ifv", "mrap", "sams", "sam", "ssm", "aam", "asm", "uav", "ucav", "uas", "aev", "arv", "avlb", "afv", "mbt", "lav", "spg", "sph",
    "mlrs", "mrl", "atgm", "cds", "fac", "opv", "lst", "lcac", "lpd", "lhd", "ffg", "ssk", "ssn", "sub", "tel", "gun", "guns", "howitzer",
    "mortar", "launcher", "missile", "missiles", "radar", "engine", "vehicle", "vehicles", "aircraft", "helicopter", "ship", "boat", "truck",
    "system", "systems", "version", "variant", "mk", "mod", "block", "type", "land", "sea", "air", "naval", "light", "heavy", "new", "tank",
    "turret", "tur", "kit", "kits", "and", "the", "for", "with", "of", "rws", "mm", "cal", "lr", "er", "ng", "class", "mi",
}
CATEGORY_FIT = {      # SIPRI category -> catalogue categories it can be ('Other' fits everything, both ways)
    "aircraft": {"aircraft & aerostructures", "uavs & drones"},
    "missiles": {"missiles & air defence", "ammunition", "uavs & drones", "marine / naval"},
    "armoured vehicles": {"protected & armoured vehicles"},
    "ships": {"marine / naval"},
    "sensors": {"sensors & electro-optics", "c4isr, comms & ew", "marine / naval", "missiles & air defence"},
    "artillery": {"artillery", "protected & armoured vehicles"},
    "engines": {"precision components & forgings", "aircraft & aerostructures", "marine / naval", "protected & armoured vehicles"},
    "air-defence systems": {"missiles & air defence", "artillery", "sensors & electro-optics"},
    "naval weapons": {"marine / naval", "missiles & air defence", "artillery", "ammunition"},
}
SENSOR_CATEGORIES = {"sensors & electro-optics", "c4isr, comms & ew"}
# a catalogue row that is a PART of a platform (a display, an engine, a fuselage, a case, a service) is never the transferred system;
# an engine row fits only an engine record, a sensor row only a sensor record
NEVER_WORDS = {"fuselage", "fuselages", "empennage", "aerostructure", "aerostructures", "structures", "doors", "door", "case", "casing", "kit",
               "kits", "upgrade", "upgrades", "modernization", "modernisation", "retrofit", "spares", "spare", "parts", "components",
               "component", "training", "simulator", "simulation", "mro", "overhaul", "maintenance", "services", "service",
               "transmitter", "display", "displays", "avionics", "harness", "motor", "motors", "propellant", "fuze", "fuzes", "seeker", "warhead",
               "resupply", "barrels", "forgings", "shells", "subsystem", "subsystems", "module", "modules", "thruster", "brake", "brakes",
               "wheel", "wheels", "pedestal", "hardware", "booster", "boosters", "airframe", "airframes", "canister", "canisters", "sight",
               "sights", "divert", "blades", "package", "packages", "wings", "propulsion", "canisterised", "canisterized", "test", "tester", "equipment"}
PARTICIPATION = ("work share", "workshare", "industrial participation")      # a share of someone else's programme, anywhere in the name
SHIP_WORDS = {"class", "frigate", "frigates", "corvette", "corvettes", "submarine", "submarines", "destroyer", "destroyers", "lhd", "lpd",
              "opv", "vessel", "vessels", "tanker", "tankers"}
ENGINE_WORDS = {"engine", "engines", "turbofan", "turbojet", "turboshaft", "turboprop", "turbine", "powerpack", "gearbox", "transmission"}
SENSOR_WORDS = {"radar", "radars", "sonar", "sonars", "imager", "pod", "pods", "sensor", "sensors", "camera", "optronic", "optronics", "flir",
                "infrared", "targeting", "rangefinder", "acquisition"}
DROP_PAREN = {"chassis", "hull", "for", "on", "based", "derivative", "platform", "using", "with", "of", "incl", "including", "partner"}
ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8"}
EXTRA_COUNTRY = {"bosnia-herzegovina": "Bosnia and Herzegovina", "cote d'ivoire": "Ivory Coast", "dr congo": "Congo (Democratic Republic)",
                 "viet nam": "Vietnam", "eswatini": "Eswatini", "turkiye": "Turkey", "czech republic": "Czechia"}
CONDITION = {"S": "second-hand", "R": "second-hand, refurbished"}
DEMONYM = {"brazilian": "Brazil", "canadian": "Canada", "australian": "Australia", "indian": "India", "egyptian": "Egypt", "american": "United States",
           "british": "United Kingdom", "french": "France", "german": "Germany", "polish": "Poland", "finnish": "Finland", "norwegian": "Norway",
           "swedish": "Sweden", "italian": "Italy", "spanish": "Spain", "dutch": "Netherlands", "korean": "South Korea", "turkish": "Turkey",
           "israeli": "Israel", "saudi": "Saudi Arabia", "emirati": "United Arab Emirates", "greek": "Greece", "hellenic": "Greece",
           "indonesian": "Indonesia", "malaysian": "Malaysia", "philippine": "Philippines", "chilean": "Chile", "peruvian": "Peru",
           "japanese": "Japan", "u.s.": "United States", "us army": "United States", "us marine": "United States", "royal australian": "Australia"}
CAL = re.compile(r"(\d{1,3}(?:\.\d{1,2})?)\s*-?\s*mm(?![a-z])")
CONFIG = re.compile(r"(?<![0-9a-z])(\d{1,2})x(\d{1,2})(?![0-9a-z])")
PAREN = re.compile(r"\(([^)]*)\)")
CUT = re.compile(r"\s(?:for|on|fitted to|based on|mounted on)\s.*$")


# =====================================================================================================================================
# matching (pure)
# =====================================================================================================================================

@dataclass
class Sig:
    anchor: str
    words: list
    cal: set
    config: set

    @property
    def codes(self) -> list:
        return [w for w in [self.anchor, *self.words] if is_code(w)]


def is_code(w: str) -> bool:
    """a model code: letters and digits ('k9', 'aw139', 'mm403'), or a number of 2+ digits"""
    return bool(re.search(r"\d", w)) and (bool(re.search(r"[a-z]", w)) or len(w) >= 2)


def calibres(s: str) -> set:
    return {float(x) for x in CAL.findall((s or "").lower())}


def configs(s: str) -> set:
    return {f"{a}x{b}" for a, b in CONFIG.findall((s or "").lower())}


def squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def signature(desg: str) -> Sig | None:
    """the designation's words / calibre / layout; None for a generic one ('vehicle engine 401-600', 'ship engine')"""
    s = (desg or "").lower().replace("&", " and ")
    cal, conf = calibres(s), configs(s)
    s = CONFIG.sub(" ", CAL.sub(" ", PAREN.sub(" ", s)))
    words = []
    for w in s.split():
        q = squash(w)
        if len(q) < 2 or q in STOP or q in words:
            continue
        words.append(q)
    anchor = next((w for w in words if not w.isdigit()), None)
    if anchor is None:
        return None
    return Sig(anchor, [w for w in words if w != anchor], cal, conf)


def _joins(toks: list) -> set:
    out = set(toks)
    for n in (2, 3):
        out |= {"".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}
    return out


def product_tokens(name: str, company_words: frozenset = frozenset()) -> dict:
    """what a catalogue name offers to the matcher. The head is the name before ' for ' / ' on ' ('Nammo rocket motor for AMRAAM' ->
    'Nammo rocket motor'); a bracket that describes a host ('(Leopard 2 chassis)', '(with PAC-2 GEM-T)') is dropped. tok = the head's
    tokens, each run of 2-3 joined, also with generic words and roman numerals normalised (Exocet MM40 Block 3 -> mm403, Piranha III ->
    piranha3); lead = the first word of the head (after the company's own name) joined with the next one or two; codes = model codes."""
    s = (name or "").lower().replace("&", " and ")
    kept = []
    for g in PAREN.findall(s):
        if not (set(re.findall(r"[a-z]+", g)) & (DROP_PAREN | NEVER_WORDS)):
            kept.append(g)
    head = CUT.sub("", PAREN.sub(" ", s)).strip()
    hw = set(re.findall(r"[a-z]+", head))
    never = bool(hw & NEVER_WORDS) or any(x in s for x in PARTICIPATION)
    text = " ".join([head, *kept])
    kw = set(re.findall(r"[a-z]+", text))                      # engine / sensor words count in a kept bracket too ('TOW ITAS (... Target Acquisition ...)')
    toks = re.findall(r"[a-z0-9]+", text)
    norm = [ROMAN.get(t, t) for t in toks]
    bare = [re.sub(r"^(?:mk|block|blk|mod)(?=\d)", "", t) for t in norm if t not in STOP]     # 'RBS15 Mk3' -> rbs153
    tok = _joins(toks) | _joins(norm) | _joins([t for t in norm if t not in STOP]) | _joins(bare)
    htoks = [ROMAN.get(t, t) for t in re.findall(r"[a-z0-9]+", head)]
    lead = {"".join(htoks[:n]) for n in (1, 2, 3) if len(htoks) >= n}
    while len(htoks) > 1 and htoks[0] in company_words:        # 'Saab 2000 Erieye' leads with '2000' too; 'BrahMos ...' keeps 'brahmos'
        htoks = htoks[1:]
    lead |= {"".join(htoks[:n]) for n in (1, 2, 3) if len(htoks) >= n}
    words = []
    for w in re.findall(r"[a-z0-9]+|[/,]", head):               # the name's opening words, up to a number or a '/'
        if w in ("/", ",") or re.search(r"\d", w):
            break
        if w not in ("and", "of", "the"):
            words.append(w)
    lead |= {"".join(x[0] for x in words[:n]) for n in range(3, len(words) + 1)}       # 'Naval Strike Missile' -> nsm
    seq = re.findall(r"[a-z0-9]+", text)
    fixed = set(company_words) | {a for a, b in zip(seq, seq[1:]) if a.isalpha() and (len(b) <= 3 or is_code(b))}
    codes = {t for t in tok if is_code(t) and t not in {str(int(c)) for c in calibres(s)} and not re.fullmatch(r"\d{1,2}x\d{1,2}", t)}
    return {"tok": tok, "lead": lead, "fixed": frozenset(fixed), "cal": calibres(s), "conf": configs(s), "codes": codes,
            "never": never, "engine": bool(kw & ENGINE_WORDS), "sensor": bool(kw & SENSOR_WORDS), "ship": bool(hw & SHIP_WORDS),
            "head_n": len(re.findall(r"[a-z0-9]+", head))}


def _kind(c: str) -> str:
    return "d" if c.isdigit() else "a"


def fit_level(w: str, toks: set, fixed: frozenset = frozenset()) -> int:
    """2 = w is a token; 1 = a variant fit: a token is w plus a variant suffix (k9 -> k9a1, remus -> remus300), or w is a token plus a
    lettered suffix after a digit (leopard2 -> leopard2a8), or a family name plus a number (nasams -> nasams2, hawk -> hawk100) when the
    product names no numbered model of that family; 0 = no fit. Never another model number (remus100 vs remus300, aw139 vs aw149,
    leopard2a7 vs 2a8, type26 vs type31)."""
    if w in toks:
        return 2
    for t in toks:
        if len(t) > len(w) and t.startswith(w) and _kind(w[-1]) != _kind(t[len(w)]):
            return 1                                            # the product names a variant of the family SIPRI names
        if len(w) > len(t) >= 3 and w.startswith(t) and t[-1].isdigit() and w[len(t)].isalpha():
            if any(v.startswith(t) and len(v) > len(t) and re.fullmatch(r"[a-z]{1,2}\d{1,2}", v[len(t):]) and not w.startswith(v) for v in toks):
                continue                                        # the product names another lettered variant ('Leopard 2 A4' vs 2A8)
            return 1                                            # SIPRI names a lettered variant of the product's model
        if len(w) > len(t) >= 4 and w.startswith(t) and t[-1].isalpha() and w[len(t)].isdigit() and t not in fixed:
            if any(v.startswith(t) and len(v) > len(t) and v[len(t)].isdigit() for v in toks):
                continue                                        # the product names its own numbered model ('Type 31', 'REMUS 300')
            return 1                                            # SIPRI names a numbered model of the product's family
    return 0


def word_fits(w: str, toks: set) -> bool:
    return fit_level(w, toks) > 0


def category_fits(sipri_cat: str | None, prod_cat: str | None) -> bool:
    a, b = (sipri_cat or "").strip().lower(), (prod_cat or "").strip().lower()
    if not a or not b or a == "other" or b == "other" or a not in CATEGORY_FIT:
        return True
    return b in CATEGORY_FIT[a]


GENERIC_CODE = re.compile(r"(block|blk|mk|mod|batch|tranche|series|lot|increment|inc|phase|version|ver|v)\d")   # a variant label, not a model
GENERIC_NICK = {"advanced", "super", "improved", "enhanced", "extended", "modernised", "modernized", "upgraded", "special", "mobile",
                "tactical", "strategic", "combat", "medium", "airborne", "multirole", "transport", "trainer"}


def score(sig: Sig, prod: dict, sipri_cat: str | None) -> int:
    """0 = no fit. 10 = the designation's first word is a word of the name (9 = a variant of it): a model code anywhere in the name, a
    plain word as the name's first word (or the initials of its words: 'NSM' = 'Naval Strike Missile'), or every word of a 2+ word name;
    9 = another model code of the designation is in the name ('MIM-104 PAC-3 MSE' -> 'PAC-3 MSE ...'); 5 = 'CODE Nickname' fits a
    product named by the nickname ('FGM-148 Javelin' -> 'Javelin ...'). The product's own codes must not contradict in the last two.
    Then +2 per other word, +1 calibre / wheel layout. A plain-word designation needs all its words."""
    p = prod["tok"]
    cat = (sipri_cat or "").strip().lower()
    if p["never"]:
        return 0
    if (cat == "engines") != p["engine"]:
        return 0
    if cat == "sensors":
        if not (p["sensor"] or (prod.get("category") or "").strip().lower() in SENSOR_CATEGORIES):
            return 0
    elif p["sensor"]:
        return 0
    if p.get("ship") and cat and cat != "ships":
        return 0                                                # 'Mistral-class LHD' is not the Mistral missile
    if not category_fits(sipri_cat, prod.get("category")):
        return 0
    if sig.cal and p["cal"] and not (sig.cal & p["cal"]):
        return 0
    if sig.config and p["conf"] and not (sig.config & p["conf"]):
        return 0
    toks, code_anchor = p["tok"], is_code(sig.anchor)

    def codes_agree() -> bool:
        mine = [c for c in p["codes"] if not c.isdigit() or len(c) >= 3]
        return not mine or any(word_fits(c, {x}) or word_fits(x, {c}) for c in mine for x in sig.codes)

    multiword, fx = False, p.get("fixed", frozenset())
    if code_anchor and fit_level(sig.anchor, toks, fx):
        s = 8 + fit_level(sig.anchor, toks, fx)
    elif not code_anchor and fit_level(sig.anchor, p["lead"], fx):
        s = 8 + fit_level(sig.anchor, p["lead"], fx)
    elif not code_anchor and sig.words and all(word_fits(w, toks) for w in [sig.anchor, *sig.words]):
        s, multiword = 10, True
    elif code_anchor and any(is_code(w) and not GENERIC_CODE.match(w) and fit_level(w, toks) == 2 for w in sig.words) and codes_agree():
        s = 9
    elif code_anchor and any(w.isalpha() and len(w) >= 6 and w not in GENERIC_NICK and word_fits(w, p["lead"]) for w in sig.words) and codes_agree():
        s = 5
    else:
        return 0
    extra = 0
    for w in sig.words:
        if word_fits(w, toks) or (len(w) <= 2 and any(t.startswith(w) and len(t) <= 4 for t in toks)):
            extra += 2                                          # 'IRIS-T SL' -> 'IRIS-T SLM'
        elif not code_anchor:
            return 0                                            # 'Puma M-26' is not the 'Puma' IFV; 'Pitbull VX' is not 'Pitbull RWS'
        elif is_code(w) and re.match(r"[a-z]+", w):
            pre = re.match(r"[a-z]+", w).group(0)
            if any(c != w and c.startswith(pre) and c[len(pre):len(pre) + 1].isdigit() for c in p["codes"] if len(c) <= len(pre) + 3):
                return 0                                        # 'Mk-46 Mod-5' (a torpedo) is not the 'Mk 46 Mod 2' gun
    extra += 1 if sig.cal and (sig.cal & p["cal"]) else 0
    extra += 1 if sig.config and (sig.config & p["conf"]) else 0
    if not code_anchor and extra == 0 and (len(sig.anchor) <= 2 or multiword):
        return 0                                                # a two-letter word alone is not enough
    return s + extra


def best_products(cands: list) -> list:
    """the top-scored products of ONE company; ties: an on-offer product before one in development, then the name with the fewest
    words beyond the match (the base model before its variants), then the shortest name"""
    top = max(c["score"] for c in cands)
    best = [c for c in cands if c["score"] == top and not c.get("blocker")] or [c for c in cands if c["score"] == top]
    best.sort(key=lambda c: (c["prod"].get("kind") == "in_development", -c.get("word_hit", 0), not c.get("descr_hit"), c["prod"]["tok"]["head_n"],
                             len(c["prod"]["name"]), c["prod"]["name"]))
    return best


def decide(cands: list, client_key: str | None, client_country: str | None, seller: str | None) -> tuple[list, str | None, list]:
    """candidates of one record on one side -> (winning candidates [one per company], why-not text, co-claims for review).
    A 'blocker' (a service line of another maker, e.g. a Pinaka launcher service row) can make a record ambiguous but never wins it."""
    by_co = defaultdict(list)
    for c in cands:
        by_co[c["company"]].append(c)
    if not by_co:
        return [], None, []
    real = {co for co, lst in by_co.items() if any(not c.get("blocker") for c in lst)}
    if not real:
        return [], "only a service / support line fits: " + "; ".join(f"{lst[0]['company_name']} ({lst[0]['prod']['name']})" for lst in by_co.values()), []
    if len(by_co) == 1:
        (co, lst), = by_co.items()
        return [best_products(lst)[0]], None, []
    if client_key in real and seller and client_country and seller == client_country:
        others = [best_products(by_co[co])[0] for co in by_co if co != client_key]
        return [best_products(by_co[client_key])[0]], None, others
    named = [co for co in real if any(c.get("anchor_in_name") for c in by_co[co])]
    if len(named) == 1:                                         # the family carries one maker's name ('BrahMos' -> BrahMos Aerospace)
        return [best_products(by_co[named[0]])[0]], None, []
    tops = {co: max(c["score"] for c in lst) for co, lst in by_co.items()}
    hi = max(tops.values())
    lead = [co for co, s in tops.items() if s == hi]
    if len(lead) == 1 and lead[0] in real:
        return [best_products(by_co[lead[0]])[0]], None, []
    return [], "ambiguous: " + "; ".join(f"{best_products(by_co[co])[0]['company_name']} ({best_products(by_co[co])[0]['prod']['name']})"
                                         for co in sorted(lead)), []


def descr_hit(descr: str | None, name: str) -> bool:
    """the product's name repeats SIPRI's description: its one long word, or two of its long words ('Patriot Air and Missile Defense
    System' for 'surface-to-air missile system'); a tie-breaker between one maker's products only"""
    words = re.findall(r"[a-z]{5,}", (descr or "").lower())
    have = sum(1 for w in words if w in (name or "").lower())
    return bool(words) and have >= min(2, len(words))


class ProductIndex:
    """token -> products, so a record is scored only against products that can hold its first word (or a nickname word)"""

    def __init__(self, companies: list):
        import bisect
        self._bisect = bisect
        self.exact, self.lead = defaultdict(set), defaultdict(set)
        self.items = []
        for co in companies:
            for p in co["products"] + co.get("blockers", []):
                i = len(self.items)
                self.items.append((co, p))
                for t in p["tok"]["tok"]:
                    self.exact[t].add(i)
                for t in p["tok"]["lead"]:
                    self.lead[t].add(i)
        self.sorted = sorted(self.exact)

    def candidates(self, sig: Sig) -> list:
        hit = set()
        for a in [sig.anchor, *sig.words]:
            hit |= self.exact.get(a, set())
            j = self._bisect.bisect_right(self.sorted, a)
            while j < len(self.sorted) and self.sorted[j].startswith(a):        # tokens that extend the word (k9 -> k9a1)
                hit |= self.exact[self.sorted[j]]
                j += 1
            for k in range(3, len(a)):                                           # tokens the word extends (leopard2 <- leopard2a8)
                hit |= self.exact.get(a[:k], set())
        return [self.items[i] for i in sorted(hit)]


def in_window(t: dict) -> bool:
    oy, dy = t.get("order_yr") or 0, t.get("delivery_yr")
    return oy >= WINDOW_FROM or (dy or 0) >= WINDOW_FROM or (dy == 0 and oy >= OPEN_FROM)


def state_buyer(name: str | None) -> bool:
    n = (name or "").strip()
    return bool(n) and "*" not in n and not n.lower().startswith("unknown") and "(multiple" not in n.lower()


def plural(word: str, n: int | None) -> str:
    if n is None or n == 1 or word.endswith(("s", "craft", "equipment", "materiel", "ammunition")):
        return word
    head, _, tail = word.rpartition(" ")
    return f"{head} {tail}s".strip() if not tail.endswith("y") or tail.endswith(("ay", "ey", "oy")) else f"{head} {tail[:-1]}ies".strip()


def quantity_text(t: dict) -> str | None:
    if not t.get("units"):
        return None
    q = f"{t['units']} {plural((t.get('descr') or 'units').strip(), t['units'])}"
    return f"about {q}" if t.get("units_est") else q


def deal_text(t: dict) -> str:
    oy = t.get("order_yr")
    when = f"Ordered in {oy}{' (estimated year)' if t.get('order_yr_est') else ''}"
    dy = t.get("delivery_yr")
    tail = f"; last delivery recorded in {dy}." if dy else "; deliveries not complete in SIPRI's data."
    return when + tail


def record_note(t: dict, side: str) -> str:
    bits = [deal_text(t)]
    cond = CONDITION.get((t.get("status") or "").strip().upper())
    if cond:
        bits.append(f"SIPRI lists the equipment as {cond}.")
    if side == "licensee":
        bits.append(f"Produced under licence in {t['buyer']} (SIPRI).")
    elif str((t.get("raw") or {}).get("locInvolvement") or "") == LICENSED:
        bits.append(f"SIPRI notes local production in {t['buyer']}.")
    bits.append(f"SIPRI designation: {t['desg'].rstrip(' -').strip()}.")
    return " ".join(bits)


def merged_text(ts: list, side: str) -> tuple[str | None, str]:
    """(quantity, note) of one product row that stands for one or more SIPRI records of the same product and buyer"""
    ts = sorted(ts, key=lambda t: (t.get("order_yr") or 9999, t["id"]))
    if len(ts) == 1:
        return quantity_text(ts[0]), record_note(ts[0], side)
    known = [t for t in ts if t.get("units")]
    descr = (ts[0].get("descr") or "units").strip()
    qty = None
    if known:
        n = sum(t["units"] for t in known)
        est = any(t.get("units_est") for t in known)
        qty = f"{'about ' if est else ''}{n} {plural(descr, n)} in {len(ts)} orders" + ("" if len(known) == len(ts) else " (some without a number)")
    parts = []
    for t in ts:
        u = f"{t['units']}{' (estimate)' if t.get('units_est') else ''}" if t.get("units") else "number not stated"
        d = f"last delivery {t['delivery_yr']}" if t.get("delivery_yr") else "deliveries not complete"
        cond = CONDITION.get((t.get("status") or "").strip().upper())
        parts.append(f"{t.get('order_yr')}: {u}, {d}{', ' + cond if cond else ''}")
    note = f"{len(ts)} orders in SIPRI's data. " + "; ".join(parts) + "."
    if side == "licensee":
        note += f" Produced under licence in {ts[0]['buyer']} (SIPRI)."
    elif any(str((t.get("raw") or {}).get("locInvolvement") or "") == LICENSED for t in ts):
        note += f" SIPRI notes local production in {ts[0]['buyer']}."
    names = list(dict.fromkeys(clean_desg(t["desg"]) for t in ts))
    note += f" SIPRI designation{'s' if len(names) > 1 else ''}: {', '.join(names)}."
    return qty, note


def quote_text(t: dict) -> str:
    units = f"{t['units']}{' (estimate)' if t.get('units_est') else ''}" if t.get("units") else "not stated"
    dy = t.get("delivery_yr") or "not complete"
    return (f"SIPRI arms transfer record {t['id']}: {t['seller']} to {t['buyer']}, {t['desg'].rstrip(' -').strip()} ({t.get('descr')}), "
            f"ordered {t.get('order_yr')}, units {units}, last delivery {dy}, condition {t.get('status')}.")


def relationship_text(company: str, country: str, products: list, side: str) -> str:
    names = list(dict.fromkeys(products))
    shown = ", ".join(names[:2]) + (f" and {len(names) - 2} more" if len(names) > 2 else "")
    if side == "licensee":
        return f"{company} produces {shown} in {country} under licence, per SIPRI."
    return f"SIPRI records arms orders from {country} for {company}'s {shown}."


# =====================================================================================================================================
# the plan (reads the DB, writes nothing)
# =====================================================================================================================================

@dataclass
class Plan:
    window: int = 0
    skipped: Counter = field(default_factory=Counter)
    matches: list = field(default_factory=list)             # one per record and company
    review: list = field(default_factory=list)              # ambiguous / co-claims
    unmatched: list = field(default_factory=list)
    near_miss: list = field(default_factory=list)           # a product name fits but the seller / category / calibre does not


def _canon_factory(cur):
    cur.execute("SELECT country_name, iso2, aliases FROM staging.country_reference")
    canon = {}
    for r in cur.fetchall():
        for a in (r["country_name"], r["iso2"], *(r["aliases"] or [])):
            if a:
                canon[squash(a)] = r["country_name"]
    for k, v in EXTRA_COUNTRY.items():
        canon.setdefault(squash(k), v)

    def c(name):
        if not name:
            return None
        return canon.get(squash(name), str(name).strip())
    cur.execute("SELECT country_name, aliases FROM staging.country_reference")
    words = {}
    for r in cur.fetchall():
        for a in (r["country_name"], *(r["aliases"] or [])):
            if a and (len(a) >= 4 or a.lower() in ("uae", "usa", "usmc")):
                words[a.lower()] = r["country_name"]
    for k, v in DEMONYM.items():
        words.setdefault(k, c(v))
    c.mentions = [(re.compile(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])"), v) for k, v in sorted(words.items(), key=lambda kv: -len(kv[0]))]
    return c


def other_country(name: str, buyer: str | None, seller: str | None, canon) -> str | None:
    """a country the catalogue name is about that is neither the buyer nor the maker's ('Scorpene Malaysia (...)' for India's order)"""
    low = re.sub(r"\([^)]*?(?:incl|including|family|overview|e\.g)[^)]*\)", " ", (name or "").lower())    # '(incl. Homar-K for Poland)'
    for rx, country in getattr(canon, "mentions", []):
        if rx.search(low) and country not in (buyer, seller):
            return country
    return None


def clean_desg(desg: str) -> str:
    return re.sub(r"[\s-]+$", "", desg or "").strip()


def load_companies(cur, canon) -> tuple[list, dict]:
    cur.execute("SELECT client_id, client_name, country FROM staging.client_account ORDER BY client_id LIMIT 1")
    cl = cur.fetchone()
    cur.execute("""SELECT p.competitor_id::text AS cid, p.client_id, p.company_role, l.country_name FROM staging.competitive_geo_company_presence p
                   JOIN staging.competitive_geo_location l USING (location_id) WHERE p.activity_type = 'Local production'""")
    made = defaultdict(set)
    for r in cur.fetchall():
        made[f"client:{r['client_id']}" if r["company_role"] == "client" else f"competitor:{r['cid']}"].add(canon(r["country_name"]))
    companies = []
    if cl:
        key = f"client:{cl['client_id']}"
        cur.execute("SELECT client_product_id::text AS id, product_name AS name, category FROM staging.client_product")
        prods = [dict(r, kind="product", country=None) for r in cur.fetchall()]
        cur.execute("SELECT coalesce(legal_name, '') || ' ' || coalesce(brand_name, '') AS n FROM staging.client_account WHERE client_id = %s", (cl["client_id"],))
        extra = (cur.fetchone() or {}).get("n") or ""
        companies.append({"key": key, "role": "client", "client_id": cl["client_id"], "competitor_id": None, "name": cl["client_name"],
                          "origin": canon(cl["country"]), "sellers": {canon(cl["country"])} | made[key], "products": prods,
                          "words": f"{cl['client_name']} {extra}"})
    cur.execute("SELECT competitor_id::text AS cid, display_name, origin_country FROM staging.competitive_competitor ORDER BY display_name")
    for c in cur.fetchall():
        key = f"competitor:{c['cid']}"
        cur.execute("""SELECT product_id::text AS id, product_name AS name, category, product_kind AS kind, country FROM staging.competitive_product
                       WHERE competitor_id::text = %s""", (c["cid"],))
        prods = [dict(r) for r in cur.fetchall()]
        own = {canon(p["country"]) for p in prods if p.get("country") and p["country"].strip().lower() not in ("europe", "global")}
        companies.append({"key": key, "role": "competitor", "client_id": None, "competitor_id": c["cid"], "name": c["display_name"],
                          "origin": canon(c["origin_country"]), "sellers": ({canon(c["origin_country"])} | own | made[key]) - {None},
                          "products": prods, "words": c["display_name"]})
    for co in companies:
        cw = frozenset(w for w in re.findall(r"[a-z]+", co.pop("words").lower()) if len(w) >= 4)
        co["name_words"] = cw
        allp = co["products"]
        ok = lambda p: (p.get("category") or "").strip().lower() not in SKIP_CATEGORIES      # noqa: E731
        co["products"] = [dict(p, tok=product_tokens(p["name"], cw)) for p in allp if (p.get("kind") or "product") not in SKIP_KINDS and ok(p)]
        co["blockers"] = [dict(p, tok=product_tokens(p["name"], cw), blocker=True) for p in allp if p.get("kind") == "service" and ok(p)]
    client = companies[0] if companies and companies[0]["role"] == "client" else None
    return companies, {"client_key": client["key"] if client else None, "client_country": client["origin"] if client else None}


def load_transfers(cur) -> list:
    cur.execute("""SELECT id, trade_id, buyer, seller, order_yr, order_yr_est, units, units_est, delivery_yr, status, desg, descr, category, raw,
                          harvested_at FROM staging.sipri_arms_transfer ORDER BY id""")
    return [dict(r) for r in cur.fetchall()]


def build_plan(companies: list, info: dict, transfers: list, canon) -> Plan:
    plan = Plan()
    index = ProductIndex(companies)
    for t in transfers:
        if not in_window(t):
            continue
        plan.window += 1
        if not state_buyer(t["buyer"]):
            plan.skipped["buyer is not a state"] += 1
            continue
        if (t.get("status") or "").strip().upper() in CONDITION:
            plan.skipped["second-hand (not the maker's sale)"] += 1
            continue
        sig = signature(t["desg"])
        if sig is None:
            plan.skipped["generic designation"] += 1
            continue
        seller, buyer = canon(t["seller"]), canon(t["buyer"])
        licensed = str((t.get("raw") or {}).get("locInvolvement") or "") == LICENSED
        sides = {"seller": [], "licensee": []}
        missed = set()
        for co, p in index.candidates(sig):
            side = "seller" if seller in co["sellers"] else ("licensee" if licensed and buyer == co["origin"] else None)
            s = score(sig, p, t.get("category"))
            if s and side:
                sides[side].append({"company": co["key"], "company_name": co["name"], "co": co, "prod": p, "score": s, "side": side,
                                    "blocker": bool(p.get("blocker")), "anchor_in_name": sig.anchor in co["name_words"],
                                    "descr_hit": descr_hit(t.get("descr"), p["name"]),
                                    "word_hit": sum(1 for w in re.findall(r"[a-z]{3,}", t["desg"].lower()) if w in p["name"].lower())})
            elif s and side is None and co["role"] == "competitor" and len(sig.anchor) >= 4 and not p.get("blocker"):
                missed.add((co["name"], p["name"]))
        if missed and not (sides["seller"] or sides["licensee"]):
            for name, pname in sorted(missed):
                plan.near_miss.append((name, t["desg"].rstrip(" -").strip(), t["seller"], pname))
        got = False
        for side, cands in sides.items():
            if not cands:
                continue
            win, why, co_claims = decide(cands, info["client_key"], info["client_country"], seller if side == "seller" else None)
            if why:
                plan.review.append({"record": t["id"], "desg": t["desg"], "seller": t["seller"], "buyer": t["buyer"], "order_yr": t["order_yr"],
                                    "side": side, "why": why})
            for c in co_claims:
                plan.review.append({"record": t["id"], "desg": t["desg"], "seller": t["seller"], "buyer": t["buyer"], "order_yr": t["order_yr"],
                                    "side": side, "why": f"co-claim, given to the client: {c['company_name']} ({c['prod']['name']})"})
            for c in win:
                got = True
                same = best_products([x for x in cands if x["company"] == c["company"] and x["score"] == c["score"]])
                fit = next((x for x in same if not other_country(x["prod"]["name"], buyer, seller, canon)), None)
                pick = fit or c                                  # a catalogue entry named for another customer is not this deal's name
                plan.matches.append({"t": t, "co": c["co"], "prod": pick["prod"], "score": c["score"], "side": side,
                                     "label": pick["prod"]["name"] if fit else clean_desg(t["desg"]),
                                     "country": t["buyer"] if side == "seller" else c["co"]["origin"], "country_canon": buyer if side == "seller" else c["co"]["origin"]})
        if not got:
            plan.unmatched.append(t)
    return plan


# =====================================================================================================================================
# writing (local staging)
# =====================================================================================================================================

def _ids():
    from prompts.loader import make_id, norm_name
    return make_id, norm_name


def remove_own(cur) -> dict:
    """everything this module wrote before (it rebuilds it): its geo products and their children, its presences, its SIPRI sources on
    others' rows, and their fact_source rows"""
    n = Counter()
    cur.execute("SELECT DISTINCT row_id FROM staging.fact_source WHERE table_name = 'competitive_geo_product' AND document_id LIKE %s", (TAG + "%",))
    gids = [r["row_id"] for r in cur.fetchall()]
    if gids:
        cur.execute("SELECT match_id::text AS m FROM staging.competitive_geo_product_match WHERE geo_product_id::text = ANY(%s)", (gids,))
        mids = [r["m"] for r in cur.fetchall()]
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_geo_product_match' AND row_id = ANY(%s)", (mids,))
        cur.execute("DELETE FROM staging.competitive_geo_product_specification WHERE match_id::text = ANY(%s)", (mids,))
        cur.execute("DELETE FROM staging.competitive_geo_product_match WHERE geo_product_id::text = ANY(%s)", (gids,))
        n["matches"] += cur.rowcount
        cur.execute("DELETE FROM staging.competitive_geo_product_news WHERE geo_product_id::text = ANY(%s)", (gids,))
        cur.execute("DELETE FROM staging.competitive_geo_source WHERE geo_product_id::text = ANY(%s)", (gids,))
        cur.execute("DELETE FROM staging.competitive_geo_product WHERE geo_product_id::text = ANY(%s)", (gids,))
        n["products"] += cur.rowcount
    cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_geo_product' AND document_id LIKE %s", (TAG + "%",))
    cur.execute("""DELETE FROM staging.competitive_geo_source s WHERE s.source_url = %s AND s.source_label = %s""", (SOURCE_URL, SOURCE_LABEL))
    n["corroborations"] += cur.rowcount
    cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_geo_product' AND document_id LIKE %s", (CORROB + "%",))
    cur.execute("SELECT DISTINCT row_id FROM staging.fact_source WHERE table_name = 'competitive_geo_company_presence' AND document_id = %s", (PRES_TAG,))
    pids = [r["row_id"] for r in cur.fetchall()]
    if pids:
        cur.execute("""SELECT presence_id::text AS p FROM staging.competitive_geo_company_presence p WHERE presence_id::text = ANY(%s)
                       AND EXISTS (SELECT 1 FROM staging.competitive_geo_product g WHERE g.presence_id = p.presence_id)""", (pids,))
        kept = {r["p"] for r in cur.fetchall()}             # someone else's products now sit under it: it stays (theirs too)
        gone = [p for p in pids if p not in kept]
        cur.execute("DELETE FROM staging.competitive_geo_company_presence WHERE presence_id::text = ANY(%s)", (gone,))
        n["presences"] += cur.rowcount
        cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_geo_company_presence' AND document_id = %s AND row_id = ANY(%s)",
                    (PRES_TAG, gone))
    return n


def write_plan(cur, plan: Plan, canon) -> dict:
    make_id, norm_name = _ids()
    stats = Counter()
    stats.update({f"removed {k}": v for k, v in remove_own(cur).items()})
    cur.execute("""SELECT l.location_id, l.country_name, (SELECT count(*) FROM staging.competitive_geo_company_presence p
                                                          WHERE p.location_id = l.location_id) AS n
                   FROM staging.competitive_geo_location l ORDER BY n DESC, l.location_id""")
    loc_by, key_of_loc = {}, {}                                  # one country can have two location rows ('Czechia', 'Czech Republic'):
    for r in cur.fetchall():                                     # new rows go to the one most presences use, presences are found on any
        k = squash(canon(r["country_name"]) or "")
        loc_by.setdefault(k, r["location_id"])
        key_of_loc[r["location_id"]] = k
    cur.execute("SELECT country_name, region_name, latitude, longitude FROM staging.country_reference")
    ref = {r["country_name"]: dict(r) for r in cur.fetchall()}
    cur.execute("""SELECT presence_id, company_role, competitor_id::text AS cid, client_id, location_id, display_order
                   FROM staging.competitive_geo_company_presence ORDER BY display_order NULLS LAST, presence_id""")
    pres_by, pres_loc, max_order = {}, {}, Counter()
    for r in cur.fetchall():
        key = f"client:{r['client_id']}" if r["company_role"] == "client" else f"competitor:{r['cid']}"
        if (key, key_of_loc.get(r["location_id"])) not in pres_by:
            pres_by[(key, key_of_loc.get(r["location_id"]))] = r["presence_id"]
            pres_loc[r["presence_id"]] = r["location_id"]
        max_order[key] = max(max_order[key], r["display_order"] or 0)
    cur.execute("SELECT geo_product_id, presence_id, product_name, since_date, display_order FROM staging.competitive_geo_product")
    gp_by = defaultdict(list)
    for r in cur.fetchall():
        gp_by[r["presence_id"]].append(dict(r))

    def location(name: str, canon_name: str) -> int:
        k = squash(canon_name or name)
        if k in loc_by:
            return loc_by[k]
        cname = canon_name or name.strip()
        lid = make_id("bigint", f"created|competitive_geo_location|{norm_name(cname)}")
        rr = ref.get(cname, {})
        cur.execute("""INSERT INTO staging.competitive_geo_location (location_id, country_name, map_label, region_name, latitude, longitude)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (lid, cname[:128], cname[:128], rr.get("region_name"), rr.get("latitude"), rr.get("longitude")))
        loc_by[k] = lid
        key_of_loc[lid] = k
        stats["locations created"] += 1
        return lid

    groups = defaultdict(list)                                   # (company, country) -> matches
    for m in plan.matches:
        groups[(m["co"]["key"], key_of_loc[location(m["country"], m["country_canon"])])].append(m)
    new_presences = sorted([g for g in groups if g not in pres_by], key=lambda g: (g[0], str(groups[g][0]["country_canon"]).lower()))
    for key, ck in new_presences:
        ms = groups[(key, ck)]
        lid = loc_by[ck]
        co, country = ms[0]["co"], ms[0]["country_canon"] or ms[0]["country"]
        side = "licensee" if all(m["side"] == "licensee" for m in ms) else "seller"
        pid = make_id("bigint", f"sipri|presence|{key}|{ck}")
        max_order[key] += 1
        rel = relationship_text(co["name"], country, [m.get("label", m["prod"]["name"]) for m in ms], side)
        cur.execute("""INSERT INTO staging.competitive_geo_company_presence (presence_id, company_role, competitor_id, client_id, company_name,
                              location_id, activity_type, presence_status, relationship_text, display_order)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'Active',%s,%s)""",
                    (pid, co["role"], co["competitor_id"], co["client_id"], co["name"][:255], lid, "Local production" if side == "licensee" else "Export",
                     rel, max_order[key]))
        first = min(ms, key=lambda m: (m["t"]["order_yr"] or 0, m["t"]["id"]))["t"]
        _fact(cur, "competitive_geo_company_presence", pid, "relationship_text", SOURCE_URL, "independent", PUBLISHER, quote_text(first), PRES_TAG, first)
        _fact(cur, "competitive_geo_company_presence", pid, "activity_type", "judgement", "judgement", None,
              (f"SIPRI records an order by {country} from {first['seller']}: an export to that country."
               if side == "seller" else f"SIPRI records production under licence in {country}."), PRES_TAG, None)
        pres_by[(key, ck)], pres_loc[pid] = pid, lid
        stats["presences created"] += 1
    touched_presences, own_products = set(), []
    for (key, ck), ms in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        pid = pres_by[(key, ck)]
        lid = pres_loc[pid]
        touched_presences.add(pid)
        mine_new = (key, ck) in new_presences
        order = max([g["display_order"] or 0 for g in gp_by.get(pid, [])], default=0)
        rest: dict = {}
        for m in sorted(ms, key=lambda m: (m["t"]["order_yr"] or 0, m["t"]["id"])):
            t, p, co = m["t"], m["prod"], m["co"]
            same = None if mine_new else _covered(gp_by.get(pid, []), p, t)
            if same is not None:
                sid = make_id("bigint", f"sipri|corroborate|{same['geo_product_id']}|{t['id']}")
                cur.execute("""INSERT INTO staging.competitive_geo_source (source_id, geo_product_id, location_id, source_label, source_type, source_url)
                               VALUES (%s,%s,%s,%s,'official',%s)""", (sid, same["geo_product_id"], lid, SOURCE_LABEL, SOURCE_URL))
                _fact(cur, "competitive_geo_product", same["geo_product_id"], "product_name", SOURCE_URL, "independent", PUBLISHER, quote_text(t),
                      f"{CORROB}{t['id']}", t)
                stats["corroborated rows on record"] += 1
                m["written"] = "corroborated"
                continue
            rest.setdefault((m.get("label", p["name"]), m["side"]), []).append(m)
        for (label, side), lst in rest.items():               # one row per product and buyer: repeated orders are one row
            p, ts = lst[0]["prod"], [m["t"] for m in lst]
            gid = make_id("bigint", f"sipri|geo_product|{key}|{lid}|{side}|{norm_name(label)}")
            order += 1
            qty, note = merged_text(ts, side)
            note += "" if label == p["name"] else f" Catalogue entry: {p['name']}."
            first = min(ts, key=lambda t: (t.get("order_yr") or 9999, t["id"]))
            cur.execute("""INSERT INTO staging.competitive_geo_product (geo_product_id, presence_id, product_name, product_range, activity_type,
                                  since_date, quantity, customer_name, record_note, display_order)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (gid, pid, label[:255], (p.get("category") or "")[:128] or None, "Local production" if side == "licensee" else "Export",
                         date(first["order_yr"], 1, 1) if first.get("order_yr") else None, qty, (first["buyer"] or "")[:120] or None, note, order))
            sid = make_id("bigint", f"sipri|geo_source|{gid}")
            cur.execute("""INSERT INTO staging.competitive_geo_source (source_id, geo_product_id, location_id, source_label, source_type, source_url)
                           VALUES (%s,%s,%s,%s,'official',%s)""", (sid, gid, lid, SOURCE_LABEL, SOURCE_URL))
            for t in ts:                                      # every record backs the row; the first order also backs the date
                cols = ("product_name", "customer_name", "record_note") + (("quantity",) if t.get("units") else ()) + (("since_date",) if t is first else ())
                for col in cols:
                    _fact(cur, "competitive_geo_product", gid, col, SOURCE_URL, "independent", PUBLISHER, quote_text(t), f"{TAG}{t['id']}", t)
            own_products.append(gid)
            stats["products added"] += 1
            stats["records in added rows"] += len(lst)
            for m in lst:
                m["written"] = "added"
    _rollups(cur, touched_presences, own_products)
    stats["presences extended"] = len(touched_presences) - stats["presences created"]
    return dict(stats)


def _covered(rows: list, prod: dict, t: dict) -> dict | None:
    """a product row on record under the presence that is the same product and deal (catalogue name fits, order year within 1 or none)"""
    sig = signature(t["desg"])
    for r in rows:
        if r.get("own"):                                         # a row this run wrote for another SIPRI record: each record keeps its row
            continue
        toks = product_tokens(r["product_name"] or "")
        same_name = (r["product_name"] or "").strip().lower() == prod["name"].strip().lower()
        if not same_name and not (sig and score(sig, {"tok": toks, "category": None}, t.get("category"))):
            continue
        y = r["since_date"].year if r.get("since_date") else None
        if y is None or t.get("order_yr") is None or abs(y - t["order_yr"]) <= 1:
            return r
    return None


def _fact(cur, table, row_id, col, url, tier, publisher, quote, doc, t) -> None:
    cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, document_id, retrieved_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (table, str(row_id), col, url, tier, publisher, quote, doc, (t or {}).get("harvested_at")))


def _rollups(cur, presences: set, products: list) -> None:
    """product count / list of every presence touched (existing values kept, new names appended), then the geo prompt's own code
    steps for these rows: KSSL counter-products (derive.geo_match_code) and overlap / country roll-ups (derive.geo_rollup)"""
    from prompts import derive, derive_comp
    for pid in presences:
        cur.execute("SELECT product_count, products_summary FROM staging.competitive_geo_company_presence WHERE presence_id = %s", (pid,))
        r = cur.fetchone()
        cur.execute("SELECT product_name FROM staging.competitive_geo_product WHERE presence_id = %s AND product_name IS NOT NULL ORDER BY display_order, geo_product_id", (pid,))
        names = list(dict.fromkeys(x["product_name"] for x in cur.fetchall()))
        summary = r["products_summary"] or ""
        have = {s.strip().lower() for s in re.split(r"[;,]\s*", summary) if s.strip()}
        add = [n for n in names if n.strip().lower() not in have and n.strip().lower() not in summary.lower()]
        new_summary = "; ".join([summary] + add) if summary and add else (summary or "; ".join(names) or None)
        cur.execute("UPDATE staging.competitive_geo_company_presence SET product_count = (SELECT count(*) FROM staging.competitive_geo_product WHERE presence_id = %s), "
                    "products_summary = %s WHERE presence_id = %s", (pid, new_summary, pid))
    ctx = {"rows": [("competitive_geo_product", str(g), False) for g in products]
           + [("competitive_geo_company_presence", str(p), False) for p in presences], "notes": []}
    derive_comp.geo_match_code(cur, ctx)
    derive.geo_rollup(cur, ctx)


# =====================================================================================================================================
# reporting
# =====================================================================================================================================

def counts(cur) -> dict:
    cur.execute("""SELECT coalesce(c.display_name, a.client_name) AS name, count(DISTINCT p.presence_id) AS presences, count(DISTINCT p.location_id) AS countries,
                          count(g.geo_product_id) AS products
                   FROM staging.competitive_geo_company_presence p
                   LEFT JOIN staging.competitive_competitor c ON c.competitor_id = p.competitor_id
                   LEFT JOIN staging.client_account a ON a.client_id = p.client_id
                   LEFT JOIN staging.competitive_geo_product g ON g.presence_id = p.presence_id
                   GROUP BY 1""")
    return {r["name"]: (r["presences"], r["countries"], r["products"]) for r in cur.fetchall()}


def summary(plan: Plan, companies: list, canon) -> dict:
    per = Counter(m["co"]["name"] for m in plan.matches)
    per_side = Counter((m["co"]["name"], m["side"]) for m in plan.matches)
    rec_matched = {m["t"]["id"] for m in plan.matches}
    eligible = plan.window - sum(plan.skipped.values())
    un_by_home = defaultdict(Counter)                    # records from a tracked competitor's home country that fit no catalogue product
    homes = defaultdict(list)
    for co in companies:
        if co["role"] == "competitor" and co["origin"]:
            homes[co["origin"]].append(co["name"])
    for t in plan.unmatched:
        for name in homes.get(canon(t["seller"]), []):
            un_by_home[canon(t["seller"])][t["desg"].rstrip(" -").strip()] += 1
            break
    samples = [{"company": m["co"]["name"], "desg": m["t"]["desg"], "seller": m["t"]["seller"], "buyer": m["t"]["buyer"], "order_yr": m["t"]["order_yr"],
                "units": m["t"]["units"], "delivery_yr": m["t"]["delivery_yr"], "product": m["prod"]["name"], "label": m.get("label"), "score": m["score"],
                "side": m["side"], "record": m["t"]["id"]} for m in plan.matches]
    return {"window": plan.window, "skipped": dict(plan.skipped), "eligible": eligible, "records_matched": len(rec_matched),
            "match_rate": round(len(rec_matched) / eligible, 4) if eligible else 0, "matches": len(plan.matches), "per_company": dict(per.most_common()),
            "per_company_side": {f"{k[0]} [{k[1]}]": v for k, v in per_side.items()}, "review": plan.review, "samples": samples,
            "unmatched_by_home_country": {f"{k} ({', '.join(homes[k])})": v.most_common(15) for k, v in un_by_home.items()},
            "near_miss": Counter(plan.near_miss).most_common(60)}


# =====================================================================================================================================
# self-check (fictional values)
# =====================================================================================================================================

def _selftest() -> None:
    s = signature("K-9 Thunder 155mm")
    assert s.anchor == "k9" and s.words == ["thunder"] and s.cal == {155.0}
    assert signature("vehicle engine 401-600") is None and signature("ship engine 8001-11000") is None
    assert signature("Arma 6x6 -").anchor == "arma" and signature("Arma 6x6 -").config == {"6x6"}
    assert signature("LM-2500 (30001-35000)").words == [] and signature("Spike-MR").anchor == "spikemr"
    P = lambda name, cat="Artillery", kind="product": {"name": name, "category": cat, "kind": kind, "tok": product_tokens(name)}   # noqa: E731
    assert score(s, P("K9 / K9A1 Thunder"), "Artillery") == 12
    assert score(s, P("K9 Vajra-T 155 mm/52 cal Tracked Self-Propelled Howitzer"), "Artillery") == 11
    assert score(s, P("K9 Vajra-T 105 mm"), "Artillery") == 0                                   # calibre contradicts
    assert score(s, P("K9 / K9A1 Thunder", cat="Aircraft & Aerostructures"), "Artillery") == 0              # category does not fit
    assert score(signature("REMUS-100"), P("REMUS 300", "Marine / Naval"), "Ships") == 0
    assert score(signature("AW-139"), P("AW149", "Aircraft & Aerostructures"), "Aircraft") == 0
    assert score(signature("Leopard-2A8"), P("Leopard 2A7+", "Protected & Armoured Vehicles"), "Armoured vehicles") == 0
    assert score(signature("Leopard-2A8"), P("Leopard 2 main battle tank", "Protected & Armoured Vehicles"), "Armoured vehicles") == 9
    assert score(signature("Spike-MR"), P("SPIKE MR/LR", "Missiles & Air Defence"), "Missiles") == 10
    assert score(signature("Spike-SR"), P("SPIKE LR2", "Missiles & Air Defence"), "Missiles") == 0
    assert score(signature("FGM-148 Javelin"), P("Javelin Weapon System", "Missiles & Air Defence"), "Missiles") == 7
    assert score(signature("CAESAR 155mm"), P("CAESAR 6x6 (155mm/52-cal self-propelled howitzer)"), "Artillery") == 11
    assert score(signature("CAESAR 155mm"), P("CAESAR 6x6", cat="Aircraft & Aerostructures"), "Artillery") == 0      # category
    assert score(signature("Arma 6x6 -"), P("ARMA 8x8", "Protected & Armoured Vehicles"), "Armoured vehicles") == 0
    assert score(signature("Arma 6x6 -"), P("ARMA 6x6", "Protected & Armoured Vehicles"), "Armoured vehicles") == 11
    assert score(signature("RAM"), P("RAM 2000 LTV", "Protected & Armoured Vehicles"), "Missiles") == 0
    assert score(signature("AH-64E Apache"), P('6.25" x 6.25" Multi-Purpose Display (MPD) (AH-64 Apache)', "Aircraft & Aerostructures"), "Aircraft") == 0
    assert score(signature("King Air"), P("HC-130J Combat King II", "Aircraft & Aerostructures"), "Aircraft") == 0
    assert score(signature("Puma M-26"), P("Puma Infantry Fighting Vehicle", "Protected & Armoured Vehicles"), "Armoured vehicles") == 0
    assert score(signature("AH-1Z Viper"), P("VIPER 300", "UAVs & Drones"), "Aircraft") == 0
    assert score(signature("MM-40-3 Exocet"), P("Exocet MM40 Block 3 (ship-launched)", "Missiles & Air Defence"), "Missiles") == 12
    assert score(signature("MM-40-3 Exocet"), P("Exocet AM39 (air-launched)", "Missiles & Air Defence"), "Missiles") == 0
    assert score(signature("Leopard-2A4"), P("Buffalo / Buffel armoured recovery vehicle 3 (Leopard 2 chassis)", "Protected & Armoured Vehicles"),
                 "Armoured vehicles") == 0
    assert score(signature("Piranha-3"), P("Piranha III (and LAV III derivative)", "Protected & Armoured Vehicles"), "Armoured vehicles") == 10
    assert score(signature("F-404 (8000)"), P("F404 turbofan engine (T-50 / FA-50)", "Aircraft & Aerostructures"), "Engines") == 10
    assert score(signature("FA-50"), P("F404 turbofan engine (T-50 / FA-50)", "Aircraft & Aerostructures"), "Aircraft") == 0
    assert score(signature("MT-30 (50000)"), P("MT30 manned turret", "Protected & Armoured Vehicles"), "Engines") == 0
    assert score(signature("Global Combat Ship"), P("Type 26 / Global Combat Ship (City class)", "Marine / Naval"), "Ships") == 12
    assert score(signature("Erieye SRSS"), P("Saab 2000 Erieye AEW&C", "Sensors & Electro-optics", ), "Sensors") == 0     # 'srss' not in the name
    assert score(signature("Erieye"), {"tok": product_tokens("Saab 2000 Erieye AEW&C", frozenset({"saab"})), "category": "Sensors & Electro-optics"},
                 "Sensors") == 0                                                                         # the lead word is the model '2000'
    assert score(signature("Patriot SAMS"), P("Patriot AN/MPQ-65 / MPQ-65A Radar Set", "Sensors & Electro-optics"), "Air-defence systems") == 0
    assert score(signature("Patriot SAMS"), P("Patriot Air and Missile Defense System (with PAC-2 GEM-T)", "Missiles & Air Defence"),
                 "Air-defence systems") == 10
    assert score(signature("Leopard-2A8"), P("LEOPARD 2 A4", "Protected & Armoured Vehicles"), "Armoured vehicles") == 0
    assert score(signature("Leopard-2A8"), P("LEOPARD 2 A8", "Protected & Armoured Vehicles"), "Armoured vehicles") == 10
    assert score(signature("Mistral SAM"), P("Mistral-class LHD (French Navy)", "Marine / Naval"), "Missiles") == 0
    assert score(signature("Mk-46 Mod-5 NEARTIP"), P("Mk 46 Mod 2 (30 mm Gun Weapon System)", "Marine / Naval"), "Naval weapons") == 0
    assert score(signature("F-35A Lightning-2"), P("F-35 Lightning II (BAE work share)", "Aircraft & Aerostructures"), "Aircraft") == 0
    assert score(signature("Phalanx"), P("Phalanx tracking pedestal (L3Harris)", "Marine / Naval"), "Naval weapons") == 0
    assert descr_hit("surface-to-air missile system", "Patriot Air and Missile Defense System") and not descr_hit("infantry fighting vehicle", "ARMA CBRN Vehicle")
    assert "brahmos" in product_tokens("BrahMos (PJ-10) - baseline cruise missile", frozenset({"brahmos", "aerospace"}))["lead"]
    assert score(signature("NASAMS-2"), P("NASAMS (National/Norwegian Advanced Surface-to-Air Missile System)", "Missiles & Air Defence"),
                 "Air-defence systems") == 9
    assert score(signature("Type-26"), P("Type 31 (Inspiration class) frigate", "Marine / Naval"), "Ships") == 0
    assert score(signature("NSM"), P("Naval Strike Missile (NSM) / RGM-184A", "Missiles & Air Defence"), "Missiles") == 10
    assert score(signature("RBS-15-3"), P("RBS15 Mk3 anti-ship missile", "Missiles & Air Defence"), "Missiles") == 10
    assert score(signature("IRIS-T SL"), P("IRIS-T SLM (Surface Launched Medium range)", "Missiles & Air Defence"), "Air-defence systems") == 12
    assert score(signature("MIM-104 PAC-3 MSE"), P("PAC-3 MSE (Patriot Advanced Capability-3)", "Missiles & Air Defence"), "Missiles") == 13
    assert score(signature("Heron-2"), P("Heron MK II", "UAVs & Drones"), "Aircraft") > score(signature("Heron-2"), P("Heron TP", "UAVs & Drones"), "Aircraft")
    assert score(signature("AAQ-33 Sniper ATP"), P("Sniper Advanced Targeting Pod (ATP)", "Sensors & Electro-optics"), "Sensors") == 9
    assert score(signature("F-15 Advanced Eagle"), P("Advanced Hawk", "Aircraft & Aerostructures"), "Aircraft") == 0
    assert score(signature("SM-6 Block-1"), P("ATACMS MGM-140 Block 1", "Missiles & Air Defence"), "Missiles") == 0
    assert score(signature("Barak-1"), P("BARAK ER", "Missiles & Air Defence"), "Missiles") == 0
    assert score(signature("Python-4"), P("SPYDER (Surface-to-air PYthon and DERby)", "Missiles & Air Defence"), "Missiles") == 0
    assert score(signature("Saab-2000 AEW"), {"tok": product_tokens("Saab electromechanical actuators (EMA)", frozenset({"saab"})),
                                             "category": "Aircraft & Aerostructures"}, "Aircraft") == 0
    assert score(signature("Hawk-100"), P("Hawk Advanced Jet Trainer", "Aircraft & Aerostructures"), "Aircraft") == 9
    assert score(signature("TOW"), P("TOW ITAS (Improved Target Acquisition System)", "Missiles & Air Defence"), "Missiles") == 0
    def fake_canon(x):
        return x
    fake_canon.mentions = [(re.compile(r"(?<![a-z])malaysia(?![a-z])"), "Malaysia"), (re.compile(r"(?<![a-z])norwegian(?![a-z])"), "Norway")]
    assert other_country("Scorpene Malaysia (KD Tunku Abdul Rahman)", "India", "France", fake_canon) == "Malaysia"
    assert other_country("NASAMS (National/Norwegian Advanced ...)", "Lithuania", "Norway", fake_canon) is None
    assert other_country("Chunmoo MRLS (incl. Homar-K for Malaysia)", "Norway", "South Korea", fake_canon) is None
    assert clean_desg("CAESAR 155mm -") == "CAESAR 155mm" and clean_desg("MEKO-A200 --") == "MEKO-A200"
    assert word_fits("k9a1", {"k9"}) is False and word_fits("leopard2a8", {"leopard2"}) is True and word_fits("remus100", {"remus", "remus300"}) is False
    co_a = {"key": "a", "name": "A"}
    c = lambda co, name, sc: {"company": co, "company_name": co.upper(), "co": {"key": co},     # noqa: E731
                              "prod": {"name": name, "kind": "product", "tok": product_tokens(name)}, "score": sc}
    win, why, cl = decide([c("a", "X 1", 10), c("a", "X", 10), c("b", "X", 10)], None, None, "Nordland")
    assert not win and why.startswith("ambiguous")
    win, why, cl = decide([c("a", "X long name", 12), c("a", "X", 10), c("b", "X", 10)], None, None, "Nordland")
    assert win[0]["prod"]["name"] == "X long name" and why is None
    win, why, cl = decide([c("client:1", "ATAGS", 11), c("t", "ATAGS", 11)], "client:1", "India", "India")
    assert win[0]["company"] == "client:1" and cl[0]["company"] == "t"
    assert decide([c("a", "X", 10)], None, None, None)[0][0]["company"] == co_a["key"]
    blk = dict(c("t", "X launcher service", 10), blocker=True)
    win, why, cl = decide([c("a", "X", 10), blk], None, None, "Nordland")
    assert not win and why.startswith("ambiguous")
    nm = dict(c("n", "NV launcher", 10), anchor_in_name=True)
    assert decide([c("a", "NV booster", 10), nm], None, None, "Nordland")[0][0]["company"] == "n"
    win, why, cl = decide([blk], None, None, "Nordland")
    assert not win and why.startswith("only a service")
    t = {"id": 9, "buyer": "Veland", "seller": "Nordland", "order_yr": 2022, "order_yr_est": False, "units": 30, "units_est": False, "delivery_yr": 0,
         "status": "S", "desg": "NV-155 155mm -", "descr": "self-propelled gun", "raw": {"locInvolvement": 1150405}}
    assert quantity_text(t) == "30 self-propelled guns" and quantity_text({**t, "units": 1}) == "1 self-propelled gun"
    assert quantity_text({**t, "descr": "multiple rocket launcher", "units_est": True}) == "about 30 multiple rocket launchers"
    assert quantity_text({**t, "descr": "light transport aircraft", "units": 2}) == "2 light transport aircraft"
    assert quantity_text({**t, "descr": "armoured personnel carrier", "units": None}) is None
    n = record_note(t, "seller")
    assert n == ("Ordered in 2022; deliveries not complete in SIPRI's data. SIPRI lists the equipment as second-hand. "
                 "SIPRI notes local production in Veland. SIPRI designation: NV-155 155mm."), n
    assert record_note({**t, "delivery_yr": 2024, "status": "N", "raw": {}}, "seller").startswith("Ordered in 2022; last delivery recorded in 2024.")
    assert in_window({"order_yr": 2015, "delivery_yr": 2016}) and in_window({"order_yr": 2010, "delivery_yr": 2016})
    assert in_window({"order_yr": 2008, "delivery_yr": 0}) and not in_window({"order_yr": 1993, "delivery_yr": 0}) and not in_window({"order_yr": 2010, "delivery_yr": 2013})
    assert state_buyer("Armenia") and not state_buyer("RSF (Sudan)*") and not state_buyer("NATO**") and not state_buyer("unknown recipient(s)")
    assert relationship_text("Nordvik", "Veland", ["NV-155", "NV-155", "NV-30", "NV-9"], "seller") == \
        "SIPRI records arms orders from Veland for Nordvik's NV-155, NV-30 and 1 more."
    assert "ordered 2022, units 30, last delivery not complete" in quote_text(t)
    q, n2 = merged_text([{**t, "id": 1, "order_yr": 2019, "units": 10, "delivery_yr": 2021, "status": "N", "raw": {}},
                         {**t, "id": 2, "units": None, "status": "N", "raw": {}}], "seller")
    assert q == "10 self-propelled guns in 2 orders (some without a number)", q
    assert n2 == ("2 orders in SIPRI's data. 2019: 10, last delivery 2021; 2022: number not stated, deliveries not complete. "
                  "SIPRI designation: NV-155 155mm."), n2
    assert merged_text([t], "seller") == (quantity_text(t), record_note(t, "seller"))
    print("sipri_geo self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--report", action="store_true", help="the plan only: nothing is written")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", help="write the plan summary (all samples, review list, unmatched) to this file")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    import psycopg2
    import psycopg2.extras
    from backend import ops_log
    from backend.routine import env
    conn = psycopg2.connect(env()["KSSL_STAGING_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            canon = _canon_factory(cur)
            companies, info = load_companies(cur, canon)
            transfers = load_transfers(cur)
            plan = build_plan(companies, info, transfers, canon)
            sm = summary(plan, companies, canon)
            before = counts(cur)
            print(f"window {sm['window']} records; skipped {sm['skipped']}; eligible {sm['eligible']}; matched {sm['records_matched']} "
                  f"({sm['match_rate']:.1%}); {sm['matches']} company rows; {len(plan.review)} for review")
            for k, v in sm["per_company"].items():
                print(f"  {k:36} {v}")
            out = {"summary": sm}
            if not a.report:
                stats = write_plan(cur, plan, canon)
                after = counts(cur)
                out["write"] = stats
                out["before_after"] = {k: {"before": before.get(k, (0, 0, 0)), "after": after.get(k, (0, 0, 0))} for k in sorted(set(before) | set(after))}
                out["written"] = Counter(m.get("written", "not written") for m in plan.matches)
                print("written:", stats)
                ops_log.note("sipri_geo", "written" if not a.dry_run else "dry_run",
                             f"SIPRI geo rows: {stats.get('products added', 0)} products added, {stats.get('presences created', 0)} presences created, "
                             f"{stats.get('corroborated rows on record', 0)} rows on record given a SIPRI source; {len(plan.review)} records for review",
                             detail={k: v for k, v in stats.items()})
            if a.json:
                with open(a.json, "w", encoding="utf-8") as fh:
                    json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
        if a.report or a.dry_run:
            conn.rollback()
            print("nothing written" if a.report else "dry run: rolled back")
        else:
            conn.commit()
            print("committed")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    if "--report" in sys.argv:                  # read-only: no pipeline-log run (its trigger install takes table locks)
        sys.exit(main())
    from backend import ops_log as _ops
    sys.exit(_ops.logged("backend.sipri_geo")(main)())
