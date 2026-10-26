"""Product spec sheet presenter (owner 2026-10-25: "fix our own REPRESENTATION first; data clean-up comes later").

Display only: every function here reads stored rows and returns what the client sees; nothing is written to staging or
serving, and the stored label / value / product name stay as they are (the raw name is still the join and search key).

    present(rows, category, ...)   [(label, value, unit)] -> {"key": [...], "other": [...], "armament": [...], "features": [...]}
    clean_description(text)        the description as lines, without pipeline notes and source talk
    display_name(name, companies)  the product NAME only (finding 9 of the 2026-10-25 product audit)
    umbrella_ids(products)         family cards that have variant cards beside them (finding 6), to hide

Owner's decisions (2026-10-25) this follows:
  - one canonical label per parameter, in sentence case, in the category's standard order (the per-category parameter
    standard STD, kept below as SHEET); a standard parameter with no value is not shown
  - units: metric first, imperial in brackets ("31,751 kg (70,000 lb)"), one unit per parameter across a category, never a
    doubled unit, never a label unit that disagrees with the value
  - no blank-label rows (a packed "a; b; c" value is ONE row with a list value), no pipeline/process notes, no
    "not disclosed"/"none" placeholders, no source talk ("(Army Recognition)", "sources differ") anywhere the client reads;
    sources stay in fact_source / Trace
  - specs of a carried weapon on a platform (aircraft, vehicle, vessel, UAV) go into their own Armament section
  - family vs variants: the variant cards only; product names: the name only

staging.spec_dictionary is NOT used: it is not loaded by the API (backend/app.py skips it as a prompt input), serving has
no copy, and the audit found it maps one key per label (9,134 labels -> 6,958 keys) with 376 garbage labels. The STD
regexes plus the synonym lists below do the merging instead, across all 14 categories.

Self-check:  python -m backend.spec_sheet
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

# ---- text cleaning: placeholders, pipeline notes, source talk ----------------------------------------------------------

# a clause saying a figure is not published / not known (b_products._NOTE, plus the bare placeholders the audit found)
_NOTE = re.compile(r"\bnot (?:officially )?(?:given|disclosed|published|stated|released|available|public(?:ly)?|specified|provided|found|read|known)\b"
                   r"|\bundisclosed\b|\bunpublished\b|\bno (?:official |public )?(?:specifications?|specs?|figures?|data|numbers?) (?:published|given|disclosed|available)\b"
                   r"|\b(?:specification|figure|data)s? (?:does|do) not exist\b|^\s*no (?:[\w-]+ ){0,5}(?:is |are )?published\b", re.I)
_PLACEHOLDER = re.compile(r"^\s*(?:n/?a|none|nil|unknown|not applicable|no data|tbd|tba|tbc|[-—–?]+|numeric specs?)\s*(?:\([^()]*\))?\s*\.?\s*$"
                          r"|^\s*(?:tbd|tba|tbc)\b.{0,25}$", re.I)
# the research agent's own process notes (audit finding 7)
_PIPE = re.compile(r"\b(?:excel|xlsx|workbook|spreadsheet|scrap(?:e|ed|ing)|crawl(?:er|ed)|js-rendered|http \d{3}|returned 40[34]|"
                   r"retriev(?:e|able|ed)|could not be (?:read|extracted|fetched|retrieved|accessed|re-read|verified|confirmed)|"
                   r"was not (?:retrievable|accessible|reachable|read)|not (?:extracted|retrievable|obtained|compared)|page text|"
                   r"todo|pipeline|placeholder|article text|truncated at|(?:see|in) (?:the )?(?:separate )?(?:[\w,/.-]+ (?:and )?){0,5}(?:rows?|cards?)\b|"
                   r"(?:this|product|catalogue|workbook|sheet|variant|program(?:me)?/common-systems) row\b|sheet exists|"
                   r"included with a caveat|no reliable source|source reviewed|wikipedia-derived|figures excluded|omitted\b)", re.I)
# a word that makes a bracket a citation: "(Army Recognition)", "(Elbit 2025 datasheet)", "(f35.com)", "(KSSL page)"
_SRC_WORD = (r"sources?|sourced|datasheets?|data sheets?|brochures?|websites?|web ?pages?|homepage|page|pages|deck|sheet|sheets|"
             r"reports?|reported|reporting|press release|news release|fact ?sheets?|fact tables?|fast facts|handbook|wikipedia|army recognition|"
             r"army[- ]technology|air ?force[- ]technology|naval[- ]technology|janes|jane's|csis|globalsecurity|seaforces|defen[cs]e talk|"
             r"defen[cs]e news|breaking defen[cs]e|flightglobal|shephard|aviation week|idrw|livefist|theprint|the print|manufacturer|"
             r"frontier ?india|militarnyi|nrc|"
             r"official|officially|secondary|showroom|news|article|magazine|catalogue|catalog|leaflet|flyer|text|interview|quoted|citing|"
             r"cited|claimed|claim|according|as reproduced|reproduced by|uncited|disputed|typo|as printed|printed|product cards?|"
             r"variant cards?|spec cards?|not stated|not given|not published|not used|(?:19|20)\d\d release|"
             r"(?<!sim )(?<!sd )(?<!memory )(?<!smart )(?<!line )(?<!id )cards?")
_BODY = r"(?:[^()]|\([^()]*\))*"                    # a bracket's text, one nested pair allowed: "(DoO(C&S) product page)"
_SRC_PAREN = re.compile(r"\s*\((?=%s(?:\b(?:%s)\b|\b[\w-]+\.(?:com|org|net|mil|gov|in|io|co\.uk|de|fr)\b))%s\)" % (_BODY, _SRC_WORD, _BODY), re.I)
_SRC_PAREN_CS = re.compile(r"\s*\((?=[^()]*(?:\bper [A-Z]|\b[A-Z][\w&-]+ (?:release|statement|announcement)\b|\b[A-Z][\w-]*\d\w* cards?\b|"
                           r"^[A-Z][\w&.' -]*,\s*(?:\d{1,2} )?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.? \d{4}\s*\)"
                           r"|(?<=\()[A-Z]{2,5} (?:19|20)\d\d\s*\)))[^()]*\)")   # "(AR 2019)": an outlet's initials and a year
_SRC_PHRASE = re.compile(r"\s*[-–—,]?\s*\b(?:sources? (?:differ|conflict|disagree|vary)|disputed|uncited|(?:a )?typo in (?:the )?source)\b[^;]*"
                         r"|\s+in (?:some |other )?secondary (?:sources|reports)\b", re.I)
_SRC_PER = re.compile(r"\s*,?\s*\b(?:(?:per|according to)\s+(?:the\s+)?(?:[\w'’&.-]+\s+){0,3}|"
                      r"(?:as (?:reported|stated|listed) (?:by|in)|citing|in)\s+(?:the\s+)?(?:[A-Z][\w'’&.-]*\s+){0,3})"
                      r"(?:brochure|datasheet|data sheet|website|web page|page|fact sheet|press release|catalogue|leaflet|showroom|card|sheet|table|list)"
                      r"(?:\s+[A-Z0-9][\w-]*\d[\w-]*)?\b|\s*,?\s*\bper (?:the )?(?:army[- ]technology|army recognition|janes|csis|wikipedia|manufacturer)\b"
                      r"|\s*,?\s*\b[Pp]er (?-i:[A-Z][\w&.'’-]*(?: [A-Z][\w&.'’-]*){0,2})\s*$", re.I)   # "25-38 km per Militarnyi" closing an item
_SRC_CLAUSE = re.compile(r"^\s*(?:older|other|some|earlier|secondary) (?:sources?|reports?|press|media)\b|^\s*[A-Z][\w&.'-]*(?: [A-Z][\w&.'-]*)? (?:cites|quotes)\b|\b(?:secondary|other) (?:reports|sources) (?:quote|give|say|list|circulate)"
                         r"|\b(?:appears|given|quoted|cited|reported|circulates?) in (?:some |other )?(?:secondary )?(?:sources|reports|press)\b"
                         r"|\b(?:release|page|sheet|brochure|datasheet|website|article|report|card)s? (?:quotes?|says|states|lists|gives|shows|prints)\b", re.I)
_ITEM_SPLIT = re.compile(r";\s+(?![^()]*\))")       # "; " outside brackets (src/lib/specs.js specParts)
_SENT_SPLIT = re.compile(r"(?<=[.;])\s+(?![^()]*\))")  # a description sentence / clause, outside brackets
_PIPE_PAREN = re.compile(r"\s*\((?=[^()]*%s)[^()]*\)" % _PIPE.pattern, re.I)


def _tidy(s: str) -> str:
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s+([,;:.)])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ,;:/")
    s = re.sub(r"^[-–—]+\s+|\s+[-–—]+$|^[-–—]+$", "", s)          # a dangling dash, not the sign of "-3 to +85 deg"
    return s.strip(" ,;:/").strip()


class Maker:
    """The product's own company as it appears in a citation bracket: "(Elbit)", "(Rafael)", "(Hanwha Defense USA)". A bracket
    naming ANOTHER company is kept: on a platform that is usually the supplier of a part ("AN/APG-81 (Northrop Grumman)")."""

    def __init__(self, names: Iterable[str]):
        stems = set()
        for n in names or ():
            n = str(n or "").strip()
            if len(n) >= 3:
                stems.add(n)
                first = re.split(r"[\s(]", n)[0]
                if len(first) >= 4 and first.lower() not in ("general", "national", "united", "advanced", "defence", "defense", "bharat"):
                    stems.add(first)
        alt = "|".join(re.escape(x) for x in sorted(stems, key=len, reverse=True)) or "(?!)"
        self.paren = re.compile(r"\s*\((?:%s)(?:[\s-]+[A-Z][\w&.-]*){0,3}\)" % alt, re.I)
        self.quote = re.compile(r"(?:%s)\s+(?:(?:states|says|claims|quotes|lists|gives|describes it as)\s+)?(['\"‘“])(.+?)['\"’”]" % alt, re.I)


def strip_sources(s: str, maker: "Maker | None" = None) -> str:
    """Drop citation brackets and source phrases from a client-facing text; the figure itself stays."""
    prev = None
    while prev != s:                                   # innermost brackets first, so "(Elbit UK sheet (2019))" goes whole
        prev = s
        s = _SRC_PAREN.sub("", s)
        s = _SRC_PAREN_CS.sub("", s)
        s = _PIPE_PAREN.sub("", s)                     # "(see the NCM/LCM MK2 row)": the note goes, the figure before it stays
        if maker:
            s = maker.paren.sub("", s)
    s = _SRC_PHRASE.sub("", s)
    s = _SRC_PER.sub("", s)
    s = re.sub(r"^(?:the )?(?:brochure|datasheet|data sheet|website|web page|page|fact sheet|card)\s+(?:headline|figure|claim|value)s?\s*:?\s*", "", s, flags=re.I)
    if maker:                                          # "Hanwha 'more than 40 km'", 'Elbit states "..."': the company quoting itself -> the quote
        m = maker.quote.fullmatch(s.strip())
        if m:
            s = m.group(2)
    return _tidy(s)


def _after_note(s: str) -> str:
    m = _PIPE.search(s)
    if not m:
        return s
    tail = re.match(r"[^:;.]{0,60}:\s+(\S.*)$", s[m.end():])
    return tail.group(1) if tail and not _PIPE.search(tail.group(1)) else s


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s[:1].islower() else s


def clean_text(value: Any, maker: "Maker | None" = None) -> list[str]:
    """A stored value -> its client-facing items: split at "; " (outside brackets), each item without source talk; an item
    that is a placeholder, a "not published" clause, a pipeline note or a source caveat is dropped. [] = nothing to show."""
    out = []
    for part in _ITEM_SPLIT.split(str(value or "")):
        part = re.sub(r"^(?:[\s•·*]+|-\s+)+", "", part).strip()          # a bullet, not the sign of "-3 to +85 deg"
        if not part or _NOTE.search(part) or _SRC_CLAUSE.search(part):
            continue
        part = strip_sources(_after_note(part), maker)
        if not part or _PIPE.search(part) or _PLACEHOLDER.match(part) or part in out:
            continue
        out.append(part)
    return out


def clean_description(text: Any, maker: "Maker | None" = None) -> list[str]:
    """The description as display lines (one stored line each), without pipeline notes, caveats and citations."""
    lines = []
    for line in str(text or "").split("\n"):
        keep = []
        for sent in _SENT_SPLIT.split(line.strip()):
            if not sent or _NOTE.search(sent) or _SRC_CLAUSE.search(sent):
                continue
            end = sent.rstrip()[-1:] if sent.rstrip()[-1:] in ".;" else ""
            sent = strip_sources(_after_note(sent), maker)
            if sent and not _PIPE.search(sent) and not _PLACEHOLDER.match(sent):
                keep.append(sent + (end if not sent.endswith(end) else ""))
        line = " ".join(keep).strip()
        line = _cap(re.sub(r";$", ".", line))
        if line and not re.fullmatch(r"(?:Role|Note)\s*:?\.?", line, re.I):
            lines.append(line)
    return lines


# ---- labels ------------------------------------------------------------------------------------------------------------

GENERIC = {"spec", "specs", "specification", "specifications", "other", "others", "note", "notes", "misc", "miscellaneous", "details",
           "detail", "general", "info", "information", "value", "values", "data", "features", "feature", "item", "parameter",
           "parameters", "remarks", "remark", "comments", "comment", "numeric specs", "numeric specifications", "key specs",
           "technical data", "technical specifications", "summary", "additional", "additional information", "key features",
           "characteristics", "performance", "capabilities", "capability", "highlights", "overview", "general data", "key data",
           "specs note", "measurable technical specs", "claim"}
_CONTAINER = re.compile(r"\b(?:platform (?:data|limits)|shared platform|family data|common (?:data|figures)|shared data)\b", re.I)
_LABEL_UNIT = r"kg|km|kmh|km h|mm|cm|m|t|ft|lb|lbs|hp|kw|nm|h|hrs|s|knots|kn|mph|cal|rpm|deg|m s|g|l|w|min|percent"
_LABEL_UNIT_TAIL = re.compile(r"\s+(%s)$" % _LABEL_UNIT)                      # spec_store template keys: "mtow kg", "maximum speed kmh"
_LABEL_UNIT_PAREN = re.compile(r"\s*\((kg|km|km/h|kmh|mm|cm|m|t|tonnes?|ft|lb|lbs|hp|kw|kW|nm|h|hrs|hours|s|sec|knots|kn|mph|rpm|deg|°|m/s|g|l|W|w|%|min)\)", re.I)
_RELATIVE = re.compile(r"\b(?:increase[ds]?|improve[ds]?|improvement|reduc(?:ed|tion|es)|enhance[ds]?|better|boost(?:ed)?|gain|saving[s]?|decrease[ds]?)\b", re.I)
_COMMON = set(("max maximum min minimum top road speed range weight mass length width height depth combat gross empty kerb curb total overall "
               "operating operational effective rate fire muzzle velocity barrel crew engine power payload capacity fuel tank time type role "
               "class system systems mode modes armour armor protection level ballistic mine ground clearance turning radius circle angle "
               "approach departure side slope gradient trench crossing vertical step obstacle fording wading water land air sea cruise "
               "cruising service ceiling altitude endurance flight take off takeoff landing wing span wingspan rotor diameter main secondary "
               "armament weapon weapons gun guns cannon missile missiles ammunition rounds stowed carried magazine feed temperature storage "
               "shelf life dimensions size volume area thrust torque transmission suspension tyres tires track tracks wheel wheels brakes "
               "steering electrical battery voltage frequency band accuracy detection recognition identification field view coverage "
               "azimuth elevation traverse sensors sensor optics sight sights rail rails stock trigger pull twist rifling grooves unit "
               "output input interface interfaces security encryption standards data link rates waveform waveforms channels presets "
               "platforms platform launch launcher launchers guidance seeker warhead propulsion motor fuze tracer penetration filling "
               "explosive charge charges primer propellant case cartridge projectile shell bullet dispersion packing packaging number "
               "and with without per in on at to for the a of or by from configuration drive drivetrain capacity seating seats passengers "
               "troops dismounts hull turret chassis options variants options standard optional mobility amphibious towing cargo body "
               "crane winch blade control autonomy displacement beam draught draft complement accommodation aviation diving operating "
               "function form factor power consumption interfaces environmental qualification receiver sensitivity jamming bandwidth "
               "standards components material materials process certification customer facility contract period licence trainees "
               "deployment simulator application density strength impulse release ejection hook spacing radar sonar reaction targets "
               "simultaneous profile maximum minimum burst sustained intense into out action auxiliary unit air transport set up wind "
               "time abort attack terminal hardpoints satellite suite").split())


def _norm(label: str) -> str:
    """Label as matched against the synonym lists: lower case, caliber = calibre, punctuation = space."""
    s = label.casefold().replace("caliber", "calibre").replace("&", " and ").replace("take-off", "takeoff").replace("take off", "takeoff")
    s = s.replace("max.", "max ").replace("min.", "min ")
    return " ".join(re.sub(r"[^a-z0-9+]+", " ", s).split())


def sentence_case(label: str) -> str:
    """First letter up, ordinary spec words down ("Max Road Speed" -> "Max road speed"); acronyms and names untouched."""
    words = label.split(" ")
    out = []
    for i, w in enumerate(words):
        if i and re.fullmatch(r"[A-Z][a-z]+", w) and w.lower() in _COMMON:
            w = w.lower()
        out.append(w)
    s = " ".join(out)
    return s[:1].upper() + s[1:]


_LABEL_SRC = re.compile(r"\s+(?:as\s+)?(?:shown|quoted|listed|given|stated|named|exhibited|demonstrated|cited)\s+(?:in|by|at)\s+"
                        r"(?:the\s+)?(?:[\w'’&.-]+\s+){0,3}(?:releases?|datasheets?|brochures?|sheets?|pages?|websites?|catalogues?|reports?|"
                        r"press|media|show|exhibition)\b.*$", re.I)
_LABEL_SOURCE_ONLY = re.compile(r"(?:(?:current|manufacturer|official|company|oem|published|latest|original)\s*)*"
                                r"(?:datasheet|data sheet|brochure|performance|specification|specifications|figures|data)"
                                r"|(?:[a-z0-9&.-]+\s+){0,3}(?:fact table|fact sheet|datasheet|data sheet|brochure|web ?page|website|"
                                r"press release|product card|showroom|catalogue)")


def clean_label(label: Any) -> tuple[str, str | None, bool]:
    """(label for display, unit the label carried, is_container). A container is a label that only holds other figures
    ("Note", "Platform limits (... not published)"): its parts are labelled by their own leading words."""
    s = re.sub(r"^[\s•·*-]+", "", str(label or "")).strip()
    caveat = bool(_NOTE.search(s))
    s = strip_sources(s)
    s = re.sub(r"\s*\((?=[^()]*\b(?:19|20)\d\d\b)[^()]*\)", "", s)        # "(16-17 Jun 2026, Eurosatory)", "(2015, media/1137)"
    s = _LABEL_SRC.sub("", s)                                              # "Seating quoted in Otokar releases for ..." -> "Seating"
    s = "; ".join(c for c in _ITEM_SPLIT.split(s) if c.strip() and not _NOTE.search(c))
    if _LABEL_SOURCE_ONLY.fullmatch(_norm(s)):
        s, caveat = "", True                                               # "MANUFACTURER DATASHEET", "CURRENT PERFORMANCE"
    unit = None
    m = _LABEL_UNIT_PAREN.search(s)
    if m:
        unit, s = m.group(1), _tidy(s[:m.start()] + s[m.end():])
    if s == s.lower():
        m = _LABEL_UNIT_TAIL.search(s)
        if m and len(s) > len(m.group(0)) + 2:
            unit, s = m.group(1), s[:m.start()].strip()
    s = _tidy(s)
    container = caveat or _norm(s) in GENERIC or bool(_CONTAINER.search(s)) or not s
    if _CONTAINER.search(s):
        s = "Platform data"
    return (sentence_case(s) if s else ""), unit, container


# ---- the standard: per category, the parameters in order (owner's STD, 2026-10-24) -------------------------------------
# slot = (STD parameter, STD label regex, [(canonical label, full-match synonyms of the normalised label, target unit)]).
# A label whose normalised form fully matches a synonym list takes that canonical label (and its unit); a label that only
# matches the STD regex ("Max speed (water)") keeps its own wording but sits in Key specifications at that slot's place.

def _S(std: str, rx: str, *subs: tuple[str, str, str | None]) -> tuple:
    subs = subs or ((std, _norm(std), None),)
    return std, re.compile(rx, re.I), [(lab, re.compile(r"(?:%s)" % syn), unit) for lab, syn, unit in subs]


_WEIGHT = ("Weight", r"weight|weights|mass|total weight|system weight|weight total", None)
_LENGTH = ("Length", r"length|overall length|length overall|total length|length total", None)
_WIDTH = ("Width", r"width|overall width|width overall", None)
_HEIGHT = ("Height", r"height|overall height|height overall", None)
_DIMS = ("Dimensions", r"dimensions|dimension|size|l x w x h|length x width x height|length width height|overall dimensions|dimensions l x w x h", None)
_OPTEMP = ("Operating temperature", r"operating temperature|operating temperature range|temperature|temperature range|service temperature|operating temp", None)

SHEET: dict[str, list[tuple]] = {
    "Artillery": [
        _S("Calibre", r"calib", ("Calibre", r"calibre|calibres|calibre mm|calibre cal|calibre barrel|calibre case|bore", None)),
        _S("Barrel length", r"barrel.?length|length.*barrel|tube.?length", ("Barrel length", r"barrel length|barrel|length of barrel|tube length", None)),
        _S("Maximum range", r"max.*range|^range|firing range|min.*range",
           ("Maximum range", r"range|max range|maximum range|max firing range|maximum firing range|firing range|max operational range|range max", "km"),
           ("Minimum range", r"min range|minimum range|min firing range|minimum firing range", None)),
        _S("Rate of fire", r"rate.*fire|salvo|burst",
           ("Rate of fire", r"rate of fire|max rate|maximum rate|max rate of fire|maximum rate of fire|rof|rate of fire rpm|firing rate", None),
           ("Sustained rate of fire", r"sustained rate of fire|sustained rate", None),
           ("Burst rate of fire", r"burst|burst rate|burst rate of fire|intense rate of fire", None)),
        _S("Weight", r"mass|weight", _WEIGHT, ("Combat weight", r"combat weight|combat mass|weight in firing position|firing weight", None),
           ("Travel weight", r"travel weight|travelling weight|transport weight", None)),
        _S("Crew", r"crew", ("Crew", r"crew|crew size|gun crew", None)),
        _S("Elevation and traverse", r"elevation|traverse", ("Elevation", r"elevation|elevation range|gun elevation", None),
           ("Traverse", r"traverse|traverse range", None), ("Elevation and traverse", r"elevation traverse|elevation and traverse", None)),
        _S("Ammunition types", r"ammunition|charges", ("Ammunition types", r"ammunition|ammunition types|ammunition type|ammunition compatibility|compatible ammunition", None)),
        _S("Into / out of action time", r"action", ("Into action time", r"coming into action time|into action time|into action|time into action", None)),
        _S("Auxiliary power unit", r"\bapu\b|auxiliary"),
        _S("Towing vehicle and air transport", r"tow|air.transport", ("Air transport", r"air transport|air transportable|transport", None)),
        _S("Chassis and mobility", r"chassis|configuration", ("Chassis", r"chassis|platform chassis|carrier vehicle", None)),
        _S("Engine power", r"engine", ("Engine", r"engine|engine type", None), ("Engine power", r"engine power|power|engine output", None)),
        _S("Road speed and operating range", r"speed|cruising",
           ("Maximum road speed", r"speed|max speed|maximum speed|road speed|max road speed|maximum road speed|top speed", "km/h"),
           ("Operating range", r"cruising range|operating range|operational range|road range|max road range|vehicle range", "km")),
        _S("Ammunition carried", r"onboard|on board|carried|stowed|stowage", ("Ammunition carried", r"ammunition carried|on board ammunition|onboard ammunition|ammunition stowage|ammunition stowed|rounds carried", None)),
        _S("Crew protection", r"protect|armour", ("Protection", r"protection|armour|armor|crew protection|ballistic protection", None)),
        _S("Automation", r"autoload|fire.control|automat", ("Fire control", r"fire control|fire control system|fcs", None)),
        _S("Bomb mass", r"bomb", ("Bomb mass", r"bomb mass|bomb weight", None)),
        _S("Launch tubes / pods", r"tube|pod|launcher"),
        _S("Rocket types", r"rocket|missile"),
    ],
    "Ammunition": [
        _S("Calibre / designation", r"calib|designation", ("Calibre", r"calibre|calibre cartridge|calibre diameter|calibre designation|designation", None)),
        _S("Type / role", r"ammunition.type|^type|role|case.type", ("Type", r"type|ammunition type|round type|role", None), ("Projectile type", r"projectile type", None)),
        _S("Projectile mass", r"projectile.(?:mass|weight)|bullet.(?:mass|weight)|shell.(?:mass|weight)|bomb.(?:mass|weight)",
           ("Projectile mass", r"projectile mass|projectile weight|bullet mass|bullet weight|shell mass|shell weight|mass of filled shell|mass of filled bomb|bomb mass|bomb weight", None)),
        _S("Complete round mass", r"round.(?:mass|weight)|cartridge.(?:mass|weight)|total.mass|^mass|weight",
           ("Complete round mass", r"complete round mass|complete round weight|round mass|round weight|cartridge mass|cartridge weight|ammunition mass|total mass", None), _WEIGHT),
        _S("Muzzle velocity", r"velocity", ("Muzzle velocity", r"muzzle velocity|velocity|muzzle velocity avg|velocity avg|average muzzle velocity", "m/s")),
        _S("Compatible weapons", r"compatib|guns|weapon|platform",
           ("Compatible weapons", r"compatible weapons|compatible guns|gun compatibility|weapon compatibility|weapons|weapon|compatibility|guns|platforms|carried on", None)),
        _S("Operating temperature", r"temperature", _OPTEMP, ("Storage temperature", r"storage temperature", None), ("Safety temperature", r"safety temperature", None)),
        _S("Cartridge length", r"cartridge.length|overall.length|round.length|shell.length", ("Cartridge length", r"cartridge length", None), ("Length", r"length|overall length|round length|total length", None),
           ("Shell length", r"shell length", None)),
        _S("Accuracy / dispersion", r"dispersion|accura", ("Dispersion", r"dispersion|max dispersion|maximum dispersion", None), ("Accuracy", r"accuracy|accuracy dispersion", None)),
        _S("Penetration", r"penetrat", ("Penetration", r"penetration|penetration capability|armour penetration", None)),
        _S("Maximum range", r"range",
           ("Maximum range", r"range|max range|maximum range|max operational range|maximum operational range", None),
           ("Effective range", r"effective range", None)),
        _S("Explosive filling", r"explosive|filling|payload", ("Explosive filling", r"explosive filling|filling|projectile filling|explosive fill|explosive|high explosive", None)),
        _S("Fuze", r"fuze", ("Fuze", r"fuze|fuze type|fuzes", None), ("Fuze modes", r"fuze modes|fuze functions|functions|modes", None)),
        _S("Tracer", r"tracer", ("Tracer", r"tracer|tracer burn time|tracer burnout", None)),
        _S("Range extension", r"base.bleed|\brap\b|assist"),
        _S("Self-destruct", r"self.destruct", ("Self-destruct", r"self destruction|self destruct|self destruct time", None)),
        _S("Arming distance", r"arming", ("Arming distance", r"arming distance|mechanical safety distance|safety distance", None)),
        _S("Lethal radius", r"lethal|radius|effect"),
    ],
    "Small Arms": [
        _S("Calibre / cartridge", r"calib|cartridge|ammunition", ("Calibre", r"calibre|calibres|calibre cartridge|cartridge|chambering|ammunition", None)),
        _S("Operating principle", r"\baction\b|operat|principle", ("Operating principle", r"action|operation|operating principle|action operation|operating system|principle of operation|operation principle|system of operation", None)),
        _S("Weight", r"mass|weight", _WEIGHT, ("Weight (empty)", r"empty weight|weight empty|weight without magazine|unloaded weight|weight unloaded|weight with empty magazine", "kg")),
        _S("Overall length", r"overall.length|^length|total.length", ("Overall length", r"overall length|length|length overall|total length", "mm"), ("Length (stock folded)", r"length collapsed|length folded|length stock folded|folded length", "mm")),
        _S("Barrel length", r"barrel.?length|length.*barrel", ("Barrel length", r"barrel length|barrel", "mm")),
        _S("Feed and capacity", r"magazine|feed|capacity", ("Magazine capacity", r"magazine capacity|capacity|magazine", None), ("Feed", r"feed|feed system|feeding", None)),
        _S("Effective range", r"range", ("Effective range", r"effective range|range|max effective range|maximum effective range|effective firing range", "m"), ("Sighting range", r"sighting range|sight range", "m")),
        _S("Fire modes", r"fire.mode|firing.mode|mode", ("Fire modes", r"fire modes|firing modes|fire mode|firing mode|mode of fire|modes of fire|modes", None)),
        _S("Sights and rails", r"sight|rail", ("Sights", r"sights|sight|sighting", None), ("Rails", r"rails|rail|rail compatibility", None)),
        _S("Rate of fire", r"rate.*fire|cyclic", ("Rate of fire", r"rate of fire|cyclic rate|cyclic rate of fire|rate of fire rpm|practical rate of fire", None)),
        _S("Muzzle velocity", r"velocity", ("Muzzle velocity", r"muzzle velocity|velocity", "m/s")),
        _S("Stock", r"stock", ("Stock", r"stock|buttstock", None)),
        _S("Barrel change", r"barrel.change|quick"),
        _S("Mounts", r"mount|bipod|tripod"),
        _S("Accuracy", r"accura|\bmoa\b"),
        _S("Twist rate", r"twist|groove|rifling", ("Twist rate", r"twist rate|barrel twist|twist", None), ("Rifling", r"rifling|grooves", None)),
        _S("Trigger pull", r"trigger", ("Trigger pull", r"trigger pull|trigger", None)),
        _S("Height and width", r"height|width", ("Height", r"height|overall height", "mm"), ("Width", r"width|overall width", "mm")),
    ],
    "Protected & Armoured Vehicles": [
        _S("Configuration", r"configuration|drive|tracked", ("Configuration", r"configuration|drive configuration|drive|drivetrain|layout|drive train", None)),
        _S("Weight", r"weight|mass|gvw",
           ("Combat weight", r"combat weight|combat mass|max combat weight|maximum combat weight", "t"),
           ("Gross vehicle weight", r"gvw|gross vehicle weight|gross weight|gvwr|max gvw|maximum gvw", "t"),
           ("Kerb weight", r"kerb weight|curb weight|empty weight|unladen weight|weight empty", "t"),
           ("Weight", r"weight|weights|mass|vehicle weight|total weight", "t")),
        _S("Crew and passengers", r"crew|passenger|seat|troops|dismount",
           ("Crew", r"crew", None), ("Crew and passengers", r"crew passengers|crew and passengers|crew troops|crew capacity|crew and troops|crew dismounts", None),
           ("Seating capacity", r"seating|seating capacity|seats|passengers|capacity seating", None)),
        _S("Engine", r"engine|power|horsepower",
           ("Engine", r"engine|engine type|powerplant|power plant|engine power plant", None),
           ("Engine power", r"engine power|power|horsepower|max power|maximum power|engine output|power output|engine power hp", None)),
        _S("Maximum road speed", r"speed",
           ("Maximum road speed", r"speed|max speed|maximum speed|top speed|road speed|max road speed|maximum road speed|on road speed|speed on road|max speed on road", "km/h")),
        _S("Operating range", r"cruising|range",
           ("Operating range", r"range|operating range|operational range|cruising range|max range|maximum range|road range|max road range|maximum road range|range on road|range road", "km")),
        _S("Protection level", r"protect|armou?r|ballistic|\bmine\b", ("Protection", r"protection|protection level|armour|armor|survivability", None),
           ("Ballistic protection", r"ballistic protection|ballistic", None), ("Mine protection", r"mine protection|mine|mine blast protection", None)),
        _S("Dimensions", r"length|width|height|dimension|size", _LENGTH, _WIDTH, _HEIGHT, _DIMS),
        _S("Payload", r"payload", ("Payload", r"payload|payload capacity|max payload|maximum payload", "t")),
        _S("Amphibious", r"amphib|water", ("Amphibious", r"amphibious|amphibious capability", None)),
        _S("Mobility", r"gradient|slope|ford|trench|obstacle|vertical step|clearance|turning|approach|departure|wading",
           ("Gradient", r"gradient|grade|grade capability|max gradient|maximum gradient", None), ("Side slope", r"side slope|side slope capability", None),
           ("Fording depth", r"fording|fording depth|fording capability|wading depth", None), ("Trench crossing", r"trench crossing|trench", None),
           ("Vertical obstacle", r"vertical obstacle|vertical step|step", None), ("Ground clearance", r"ground clearance|clearance|gc", None),
           ("Turning circle", r"turning circle|turning radius|turning diameter", None)),
        _S("Towing capacity", r"\btow", ("Towing capacity", r"towing capacity|towing|tow capacity", None)),
        _S("Cargo body", r"cargo|body|\bbed\b"),
        _S("Crane / winch / blade", r"crane|winch|blade|boom"),
        _S("Control range and autonomy", r"control range|autonom", ("Autonomy", r"autonomy|autonomy level", None)),
        _S("Endurance", r"endurance|battery"),
    ],
    "Missiles & Air Defence": [
        _S("Role", r"\brole|^type|targets", ("Role", r"role|roles|type|missile type|system type", None), ("Targets", r"targets|target set|target types", None)),
        _S("Maximum range", r"range",
           ("Maximum range", r"range|max range|maximum range|range max|max operational range|operational range", "km"),
           ("Minimum range", r"min range|minimum range|min operating range|minimum operating range", None),
           ("Effective range", r"effective range", None), ("Interception range", r"interception range|intercept range|engagement range", "km")),
        _S("Guidance and seeker", r"guidance|seeker", ("Guidance", r"guidance|guidance system|navigation guidance", None), ("Seeker", r"seeker|seeker type", None),
           ("Guidance and seeker", r"guidance seeker|seeker guidance|guidance and seeker", None)),
        _S("Warhead", r"warhead", ("Warhead", r"warhead|warhead type|warheads|warhead weight|warhead mass", None)),
        _S("Propulsion", r"propulsion|motor|engine", ("Propulsion", r"propulsion|motor|motor type|engine|rocket motor|powerplant", None)),
        _S("Maximum speed", r"speed", ("Maximum speed", r"speed|max speed|maximum speed|top speed", "km/h")),
        _S("Launch mass", r"mass|weight", ("Launch mass", r"weight|mass|launch weight|launch mass|missile weight|missile mass|total weight", "kg")),
        _S("Length and diameter", r"length|diameter|wingspan|span", ("Length", r"length|missile length|overall length|length overall", "m"),
           ("Diameter", r"diameter|missile diameter|body diameter", "mm"), ("Wingspan", r"wingspan|wing span|span|fin span", None)),
        _S("Launch platforms", r"platform|launch", ("Launch platforms", r"platforms|platform|launch platforms|launch platform|launch system|launch|launchers|launcher", None)),
        _S("Altitude coverage", r"altitude|ceiling", ("Altitude coverage", r"altitude|altitude coverage|max altitude|maximum altitude|ceiling|engagement altitude", None)),
        _S("Simultaneous targets", r"simultan"),
        _S("Reaction time", r"reaction"),
        _S("Missiles per launcher", r"launcher.capacity|per.launcher", ("Missiles per launcher", r"missiles per launcher|launcher capacity", None)),
        _S("Armour penetration", r"penetrat", ("Armour penetration", r"penetration|armour penetration|armor penetration", None)),
        _S("Attack mode", r"\btop\b|attack|forget"),
        _S("Accuracy (CEP)", r"accura|\bcep\b", ("Accuracy", r"accuracy|cep|accuracy cep", None)),
        _S("Flight profile", r"profile|apogee"),
        _S("Gun calibre and rate of fire", r"calib|rate.*fire", ("Calibre", r"calibre|calibres", None), ("Rate of fire", r"rate of fire", None)),
        _S("Fire-control radar", r"radar", ("Radar", r"radar|fire control radar", None)),
        _S("Detection range", r"detect", ("Detection range", r"detection range|detection", None)),
        _S("Frequency band", r"\bband|frequency"),
    ],
    "UAVs & Drones": [
        _S("Class / type", r"system.type|type|class", ("Type", r"type|uav type|uas type|system type|class|uas group|configuration", None)),
        _S("Maximum take-off weight", r"takeoff|mtow|mass|weight|\bauw\b",
           ("Maximum take-off weight", r"mtow|max takeoff weight|maximum takeoff weight|takeoff weight|max takeoff mass|maximum takeoff mass|auw|all up weight|max weight|maximum weight|gross weight|max gross weight", "kg"),
           ("Empty weight", r"empty weight|weight empty|dry weight", "kg"), ("Weight", r"weight|mass|total weight|system weight|air vehicle weight", "kg")),
        _S("Endurance", r"endurance|flight time", ("Endurance", r"endurance|max endurance|maximum endurance|flight time|flight endurance|endurance h|time aloft", None)),
        _S("Range", r"range|radius",
           ("Range", r"range|operational range|max range|maximum range|mission range|operating range|flight range", "km"),
           ("Datalink range", r"datalink range|data link range|link range|comm range|comms range|communication range|communications range|control range|range datalink range|range datalink", "km")),
        _S("Maximum speed", r"speed", ("Maximum speed", r"speed|max speed|maximum speed|top speed|dash speed", "km/h"),
           ("Cruise speed", r"cruise speed|cruising speed|operational speed", "km/h"), ("Loiter speed", r"loiter speed", "km/h")),
        _S("Payload", r"payload|sensors", ("Payload", r"payload|payload capacity|max payload|maximum payload|payload weight|useable payload|usable payload|max payload weight|maximum payload capacity|payloads", None)),
        _S("Propulsion", r"propulsion|engine|motor", ("Propulsion", r"propulsion|engine|engine powerplant|powerplant|power plant|motor|engines", None)),
        _S("Launch and recovery", r"launch|recovery", ("Launch and recovery", r"launch|launch method|launch recovery|launch and recovery|launch recovery method|recovery|take off and landing|launcher", None)),
        _S("Service ceiling", r"altitude|ceiling", ("Service ceiling", r"service ceiling|ceiling|max altitude|maximum altitude|max operating altitude", "m"),
           ("Operating altitude", r"operating altitude|operational altitude|altitude|cruise altitude", "m")),
        _S("Size", r"wingspan|wing span|length|dimension|rotor|diameter|width|height",
           ("Wingspan", r"wingspan|wing span|span", "m"), ("Length", r"length|overall length", "m"), _DIMS),
        _S("Warhead", r"warhead", ("Warhead", r"warhead|warhead type|warhead weight|warhead mass|munition", None)),
        _S("Terminal guidance", r"seeker|guidance|targeting", ("Guidance", r"guidance|guidance seeker|seeker|terminal guidance|targeting", None)),
        _S("Abort / re-attack", r"abort|re.?attack"),
        _S("SATCOM", r"satcom|satellite"),
        _S("Sensor suite", r"sensor|\bsar\b", ("Sensors", r"sensors|sensor|sensor suite|optical payload", None)),
        _S("Set-up time and portability", r"setup|set.up|portab|deployment time", ("Set-up time", r"setup|set up|setup time|set up time|deployment time", None)),
        _S("Wind tolerance", r"\bwind"),
        _S("Navigation", r"navigation|gnss|gps"),
        _S("Datalink", r"datalink|data link|comms|communication"),
        _S("Operating temperature", r"temperature", _OPTEMP),
    ],
    "Marine / Naval": [
        _S("Displacement", r"displacement|mass|weight", ("Displacement", r"displacement|full load displacement|displacement full load|standard displacement", "t"), _WEIGHT),
        _S("Length, beam and draught", r"length|beam|draught|draft|dimension|size|width|height",
           ("Length", r"length|length overall|overall length|loa|hull length", "m"), ("Beam", r"beam|width|max beam", "m"),
           ("Draught", r"draught|draft", "m"), ("Height", r"height", "m"), _DIMS),
        _S("Maximum speed", r"speed", ("Maximum speed", r"speed|max speed|maximum speed|top speed", None), ("Cruising speed", r"cruise speed|cruising speed|economical speed", None)),
        _S("Range and endurance", r"range|endurance", ("Range", r"range|max range|maximum range|cruising range|operational range", None), ("Endurance", r"endurance", None)),
        _S("Crew", r"crew|complement|accommodation", ("Crew", r"crew|complement|crew complement|crew size", None), ("Accommodation", r"accommodation|berths", None)),
        _S("Propulsion", r"propulsion|engine|power|thrust", ("Propulsion", r"propulsion|engines|engine|propulsion system|machinery", None), ("Power", r"power|installed power|propulsion power", None)),
        _S("Sensors", r"sensor|radar|sonar|combat", ("Sensors", r"sensors|sensor suite", None), ("Combat system", r"combat system|combat management system|cms", None),
           ("Radar", r"radar|radars", None), ("Sonar", r"sonar|sonars", None)),
        _S("Type", r"\btype|\brole|function|class", ("Type", r"type|role|function|class", None)),
        _S("Calibre / diameter", r"calib|diameter", ("Calibre", r"calibre|calibres", None), ("Diameter", r"diameter", None)),
        _S("Guidance / fire control", r"guidance|fire.control|seeker"),
        _S("Platforms", r"platform|ships", ("Platforms", r"platforms|platform|ships|launch platforms|example launch platforms", None)),
        _S("Frequency band", r"\bband|frequency"),
        _S("Detection range", r"detect"),
        _S("Diving depth", r"depth", ("Diving depth", r"diving depth|depth|operating depth|depth rating|operational depth|max depth|maximum depth|test depth", "m")),
        _S("AIP", r"\baip\b|independent"),
        _S("Autonomy and endurance", r"autonom"),
        _S("Aviation", r"aviation|helicopter|hangar|aircraft", ("Aviation", r"aviation|helicopter|helicopters|hangar|aircraft", None)),
    ],
    "C4ISR, Comms & EW": [
        _S("Function", r"function|\btype|\brole", ("Function", r"function|functions|type|role", None)),
        _S("Frequency range", r"frequen|\bbands?\b", ("Frequency range", r"frequency|frequency range|frequency coverage|frequencies|frequency band|frequency bands|bands|band", None)),
        _S("Form factor and platform", r"platform|form|manpack", ("Platform", r"platform|platforms", None), ("Form factor", r"form factor", None)),
        _S("Weight", r"weight|mass", _WEIGHT),
        _S("Size", r"size|dimension", _DIMS),
        _S("Power", r"power", ("Power", r"power|power supply|power input|input power", None), ("Transmit power", r"transmit power|output power|power output|rf power", None),
           ("Power consumption", r"power consumption|consumption", None)),
        _S("Interfaces", r"interface|ports", ("Interfaces", r"interfaces|interface|ports|i o", None)),
        _S("Security", r"encrypt|security|crypto", ("Security", r"security|encryption|crypto|comsec", None)),
        _S("Environmental qualification", r"environment|temperature|mil.std|ingress",
           ("Environmental qualification", r"environment|environmental|environmental qualification|mil std", None), _OPTEMP),
        _S("Waveforms and data rate", r"waveform|data.rate|throughput", ("Waveforms", r"waveforms|waveform", None), ("Data rate", r"data rate|data rates|throughput", None)),
        _S("Range", r"range", ("Range", r"range|communication range|max range", "km")),
        _S("Jamming power and bandwidth", r"jamm|\berp\b|bandwidth"),
        _S("Receiver sensitivity", r"sensitivity"),
        _S("Standards", r"standard|\blink\b"),
    ],
    "Sensors & Electro-optics": [
        _S("Sensor type", r"\btype|technology|sensor", ("Sensor type", r"type|sensor type|type sensor|technology|sensor|sensors|radar type", None)),
        _S("Detection range", r"detect|range", ("Detection range", r"detection range|detection|range|max range|object detection range|instrumented range|instrumental range", "km")),
        _S("Coverage", r"coverage|azimuth|elevation|field of view|\bfov\b",
           ("Coverage", r"coverage", None), ("Azimuth coverage", r"azimuth coverage|azimuth", None), ("Elevation coverage", r"elevation coverage|elevation", None),
           ("Field of view", r"field of view|fov|hfov", None)),
        _S("Weight", r"weight|mass", _WEIGHT),
        _S("Power consumption", r"power", ("Power consumption", r"power consumption|power|power supply", None)),
        _S("Platform", r"platform|mount", ("Platform", r"platform|platforms|mounting", None)),
        _S("Operating temperature", r"temperature|environment", _OPTEMP, ("Environment", r"environment|environmental", None)),
        _S("Frequency band", r"\bband|frequency", ("Frequency band", r"band|frequency band|frequency|spectral band|spectral range", None)),
        _S("Targets tracked", r"track|targets"),
        _S("Range accuracy", r"accura"),
        _S("Detector and NETD", r"detector|netd|format|pitch", ("Detector", r"detector|format pitch|format|pitch", None), ("NETD", r"netd", None)),
        _S("Recognition / identification range", r"recogni|identif"),
        _S("Laser rangefinder", r"laser|rangefinder"),
        _S("Operating depth", r"depth"),
    ],
    "Aircraft & Aerostructures": [
        _S("Role and crew", r"\brole|crew|function|seats", ("Role", r"role|primary function|function|type", None), ("Crew", r"crew|seats|crew seats", None)),
        _S("Dimensions", r"length|wingspan|wing span|\bspan\b|height|rotor|dimension",
           ("Length", r"length|overall length|length overall", "m"), ("Wingspan", r"wingspan|wing span|span", "m"), ("Height", r"height|overall height", "m"),
           ("Rotor diameter", r"rotor diameter|main rotor diameter", "m"), _DIMS),
        _S("Weights", r"weight|mtow|mass",
           ("Empty weight", r"empty weight|weight empty|operating weight empty|operating empty weight", "kg"),
           ("Maximum take-off weight", r"mtow|max takeoff weight|maximum takeoff weight|takeoff weight|max weight|maximum weight|max gross weight|maximum gross weight|max takeoff mass|maximum takeoff mass|gross weight", "kg"),
           ("Weight", r"weight|mass|weights", "kg")),
        _S("Engines", r"engine|thrust|propulsion|power plant|powerplant",
           ("Engines", r"engines|engine|propulsion|power plant|powerplant", None), ("Thrust", r"thrust|max thrust|maximum thrust|thrust class", "kN")),
        _S("Speed", r"speed", ("Maximum speed", r"speed|max speed|maximum speed|top speed", "km/h"), ("Cruise speed", r"cruise speed|cruising speed", "km/h")),
        _S("Range", r"range|radius", ("Range", r"range|max range|maximum range|operational range", "km"), ("Combat radius", r"combat radius|mission radius|radius", "km"),
           ("Ferry range", r"ferry range", "km")),
        _S("Service ceiling", r"ceiling", ("Service ceiling", r"service ceiling|ceiling|max altitude|maximum altitude", "m")),
        _S("Payload / hardpoints", r"payload|hardpoint|useful load", ("Payload", r"payload|max payload|maximum payload|useful load", "kg"), ("Hardpoints", r"hardpoints|hardpoint|weapon stations", None)),
        _S("Part / assembly", r"\bpart\b|scope|component", ("Scope", r"scope|part|component|components", None)),
        _S("Aircraft programmes", r"aircraft|program|fleet|platforms?", ("Aircraft programmes", r"aircraft|platform|platforms|programme|program|fleet", None)),
        _S("Material and process", r"material|process"),
        _S("Certification", r"certif|\bnds\b|\bnsn\b|approvals?", ("Certification", r"certification|approvals|certifications", None)),
    ],
    "Armoured Vehicle MRO": [
        _S("Service type", r"scope|service|method|build", ("Scope", r"scope|scope of services|services|service", None), ("Build method", r"build method|method", None)),
        _S("Platforms covered", r"platform|vehicles in scope|equipment covered", ("Platforms covered", r"platforms covered|platforms|platform|platforms cited|vehicles in scope|equipment covered", None)),
        _S("Customer", r"customer|client", ("Customer", r"customer|customers|client|clients", None)),
        _S("Facility", r"location|facility", ("Facility", r"facility|location|facilities", None)),
        _S("Capacity", r"capacity"),
        _S("Contract value and period", r"contract|value", ("Contract value and period", r"contract value timing|contract value|contract|value", None)),
        _S("Upgrades delivered", r"fire.control|upgrade|engine"),
        _S("OEM licence / ToT", r"licen|\bmou\b|\btot\b", ("OEM licence", r"licence|license|mou|tot", None)),
    ],
    "Precision Components & Forgings": [
        _S("Component type", r"products|\bpart\b|scope", ("Component type", r"products|part types|parts|scope|component type", None)),
        _S("Material", r"material", ("Material", r"material|materials|metals used across the line", None)),
        _S("Process", r"process|manufactur|forg", ("Process", r"process|processes|manufacturing|forging", None)),
        _S("Applicable platforms", r"platform|applicab"),
        _S("Qualification", r"qualif|certif", ("Qualification", r"qualification|certification|quality certification", None)),
        _S("Capacity", r"capacity|facility", ("Capacity", r"capacity", None), ("Facility", r"facility", None)),
        _S("Barrel data", r"calib|barrel|bore", ("Calibre", r"calibre|calibre range|bore diameter", None), ("Barrel length", r"barrel length", None), ("Barrel life", r"barrel life", None)),
        _S("Tolerance", r"tolerance"),
    ],
    "Training & Simulation": [
        _S("Simulator type", r"\btype|\brole", ("Simulator type", r"type|role|simulator type", None)),
        _S("Weapons / platforms simulated", r"weapon|platform", ("Weapons / platforms simulated", r"weapons trained|weapon simulation|supported platforms|platforms|weapons", None)),
        _S("Trainees at once", r"trainee|lanes|users"),
        _S("Deployment", r"mobile|fixed|deploy", ("Deployment", r"deployment|fleet deployment", None)),
        _S("Standards", r"standard|\bhla\b|\bdis\b", ("Standards", r"standards|standard|compliance", None)),
        _S("After-action review", r"after.action|\baar\b"),
        _S("Motion platform", r"motion|\bdof\b"),
    ],
    "Other": [
        _S("Product type / role", r"\btype|\brole|description|class", ("Type", r"type|role|class|weapon class|product type", None)),
        _S("Weight", r"weight|mass", _WEIGHT),
        _S("Dimensions", r"dimension|length|size", _DIMS, _LENGTH),
        _S("Application / platform", r"platform|applica|aircraft", ("Application", r"application|applications", None), ("Platform", r"platform|platforms|aircraft", None)),
        _S("Operating temperature", r"temperature", _OPTEMP),
        _S("Explosives data", r"velocity of detonation|\bvod\b|density|strength",
           ("Velocity of detonation", r"velocity of detonation|vod|minimum velocity of detonation", None), ("Density", r"density|nominal density", None)),
        _S("Propulsion data", r"thrust|impulse"),
        _S("Release data", r"ejection|hook"),
    ],
}

# the client's catalogue sometimes says "Armoured Vehicles" etc.; anything unknown gets no key slots (rows go to Other / Features)
PLATFORM_CATS = {"Aircraft & Aerostructures", "UAVs & Drones", "Marine / Naval", "Protected & Armoured Vehicles"}
_WEAPON_SUB = {"turret_weapon_station", "naval_weapon", "loitering_munition", "ucav"}
# a product in a platform category whose OWN parameters are a weapon's (a turret, a naval gun, a loitering munition)
_WEAPON_NAME = re.compile(r"\b(?:turrets?|rcws|rws|weapon stations?|remote weapon|gun mounts?|naval guns?|guns?|cannons?|torpedo(?:es)?|launchers?|ciws|"
                          r"decoys?|mines?|missiles?|loitering|munitions?|kamikaze|warheads?|mortars?|howitzers?|rockets?|bombs?)\b", re.I)
_PLATFORM_NAME = re.compile(r"\b(?:vehicles?|carriers?|variant|apc|ifv|truck|tank|vessels?|ships?|boats?|craft|frigates?|corvettes?|submarines?|destroyers?|"
                            r"aircraft|helicopters?|uavs?|uas|drones?|fighter|patrol|platform|4x4|6x6|8x8|10x10|amv|mrap)\b", re.I)
_ARM_LABEL = re.compile(r"\b(?:armament|weapons?|main gun|secondary|cannons?|guns?|machine guns?|coaxial|missiles?|atgms?|torpedo(?:es)?|ciws|rws|rcws|"
                        r"turret|calibre|calibres|caliber|cartridge|muzzle velocity|rate of fire|rof|rounds per minute|cyclic|ammunition|magazine|"
                        r"barrel length|barrel|warheads?|penetration|projectile|vls|bombs?|effectors?|gun pod)\b", re.I)
_ARM_LABEL_VEH = re.compile(r"\b(?:elevation|traverse|stabili[sz]ation|stabili[sz]ed)\b", re.I)   # a turret's arcs on a vehicle / ship


def is_weapon_product(name: Any, category: Any, sub_type: Any = None) -> bool:
    if sub_type in _WEAPON_SUB:
        return True
    n = str(name or "")
    return bool(_WEAPON_NAME.search(n)) and not _PLATFORM_NAME.search(n)


def _armament_label(label: str, category: str) -> bool:
    n = label.casefold()
    if category == "UAVs & Drones" and re.search(r"\bwarhead|penetration\b", n):
        return False                                  # a UAV that has a warhead is the munition itself
    if category == "Aircraft & Aerostructures" and re.search(r"hardpoint", n):
        return False                                  # STD: payload / hardpoints are the aircraft's own figures
    if re.match(r"(?:overall )?(?:length|width|height|ground clearance|weight)(?![a-z])", n) and not re.search(r"barrel|gun|turret weight", n):
        return False                                  # "Length (turret 12 o'clock)", "Height (turret roof)": the vehicle's own size
    return bool(_ARM_LABEL.search(n) or (category in ("Protected & Armoured Vehicles", "Marine / Naval") and _ARM_LABEL_VEH.search(n)))


_FOREIGN = re.compile(r"temperature|frequen|spectral|voltage|price|cost|contract|customer|delivery|deliveries|production|workforce|order", re.I)


def classify(label: str, category: str) -> tuple[int, int, str, str | None] | None:
    """(slot index, place in the slot, display label, target unit) when the label is a standard parameter of the category."""
    slots = SHEET.get(category) or []
    n = _norm(label)
    if not n or n in GENERIC or _RELATIVE.search(n):
        return None
    for i, (_std, _rx, subs) in enumerate(slots):            # 1) a synonym: the canonical label
        for j, (lab, syn, unit) in enumerate(subs):
            if syn.fullmatch(n):
                return i, j, lab, unit
    foreign = _FOREIGN.search(n)
    for i, (_std, rx, _subs) in enumerate(slots):            # 2) the STD regex: its own wording, at the standard place
        if rx.search(n) and not (foreign and not rx.search(foreign.group(0))):
            return i, 99, label, None
    return None


# the Armament section of a platform, in this order; labels outside the list keep their own wording, after these
ARMAMENT = [("Armament", r"armament|armaments|armament options|weapons|weapon|weapon options|weapon fit|armament fitted|weapons fit", None),
            ("Main gun", r"main gun|main armament|main weapon|gun|cannon|main gun calibre", None),
            ("Secondary armament", r"secondary|secondary armament|secondary weapons|secondary weapon|coaxial|coaxial machine gun|machine gun|machine guns", None),
            ("Missiles", r"missiles|missile|atgm|atgms|anti tank missiles", None),
            ("Turret", r"turret|turret type|weapon station|rcws|rws", None),
            ("Calibre", r"calibre|calibres|calibre mm|gun calibre", None),
            ("Barrel length", r"barrel length|barrel|barrel length cal", None),
            ("Rate of fire", r"rate of fire|rof|cyclic rate|cyclic rate of fire|rate of fire rpm|max rate of fire|maximum rate of fire", None),
            ("Muzzle velocity", r"muzzle velocity|velocity", "m/s"),
            ("Ammunition stowed", r"ammunition|ammunition stowed|ammunition stowage|ammunition capacity|ammunition carried|on board ammunition|onboard ammunition|rounds carried|rounds stowed|main gun ammunition", None),
            ("Elevation", r"elevation|gun elevation|elevation range", None),
            ("Traverse", r"traverse|turret traverse", None),
            ("Weapons payload", r"weapons payload|weapon payload|weapons load|weapon load", "kg")]
_ARMAMENT = [(lab, re.compile(syn), unit) for lab, syn, unit in ARMAMENT]


def armament_label(label: str) -> tuple[int, str, str | None]:
    n = _norm(label)
    for i, (lab, syn, unit) in enumerate(_ARMAMENT):
        if syn.fullmatch(n):
            return i, lab, unit
    return len(_ARMAMENT), label, None


# ---- units ---------------------------------------------------------------------------------------------------------------
# (dimension, system, factor to the dimension's base unit, display token). Base: mm, g, m/s, kN, m², L, °C.
_U = {}


def _u(dim: str, system: str, factor: str, show: str, *names: str) -> None:
    for n in names:
        _U[n] = (dim, system, Decimal(factor), show)


_u("length", "metric", "1", "mm", "mm", "millimetre", "millimetres", "millimeter", "millimeters")
_u("length", "metric", "10", "cm", "cm", "centimetre", "centimetres", "centimeter", "centimeters")
_u("length", "metric", "1000", "m", "m", "metre", "metres", "meter", "meters")
_u("length", "metric", "1000000", "km", "km", "kilometre", "kilometres", "kilometer", "kilometers")
_u("length", "imperial", "25.4", "in", "in", "inch", "inches")
_u("length", "imperial", "304.8", "ft", "ft", "feet", "foot")
_u("length", "imperial", "914.4", "yd", "yd", "yard", "yards")
_u("length", "imperial", "1609344", "mi", "mi", "mile", "miles")
_u("length", "nautical", "1852000", "nmi", "nmi", "nautical miles", "nautical mile")
_u("mass", "metric", "1", "g", "g", "gram", "grams")
_u("mass", "metric", "1000", "kg", "kg", "kgs", "kilogram", "kilograms")
_u("mass", "metric", "1000000", "t", "t", "tonne", "tonnes", "metric tons", "metric ton")
_u("mass", "imperial", "453.59237", "lb", "lb", "lbs", "pound", "pounds")
_u("mass", "imperial", "28.349523125", "oz", "oz")
_u("speed", "metric", "1", "m/s", "m/s", "mps")
_u("speed", "metric", "0.2777777777777777777777777778", "km/h", "km/h", "kmh", "kph", "kmph", "km/hr")
_u("speed", "imperial", "0.44704", "mph", "mph")
_u("speed", "imperial", "0.3048", "ft/s", "ft/s", "fps")
_u("speed", "nautical", "0.5144444444444444444444444444", "kn", "kn", "kt", "kts", "knot", "knots")
_u("force", "metric", "1", "kN", "kN")
_u("force", "imperial", "0.0044482216152605", "lbf", "lbf")
_u("area", "metric", "1", "m²", "m2", "m²", "sq m")
_u("area", "imperial", "0.09290304", "ft²", "ft2", "ft²", "sq ft")
_u("volume", "metric", "1", "L", "l", "L", "litre", "litres", "liter", "liters")
_u("volume", "imperial", "3.785411784", "US gal", "gal", "gallon", "gallons")
_UNIT_NAMES = sorted(_U, key=len, reverse=True)
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
# figures sharing one unit: "30 to 41 km", "20 x 13 x 5 in", "12.5 / 13.5 / 14.5 in" (a spaced slash; "1/2 in" is a fraction)
_FIG = re.compile(r"(?<![\w.,/-])(?P<nums>(?:%s)(?:(?:\s*(?:-|–|to|x|×)\s*|\s+/\s+)(?:%s))*)\s?(?P<u>%s)(?![\w²/])"
                  % (_NUM, _NUM, "|".join(re.escape(u) for u in _UNIT_NAMES)))
_CASE_SENSITIVE = {"kN": "force", "kn": "speed"}              # kilonewton vs knot


def _dec(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def fmt_num(x: Decimal) -> str:
    """>= 100: whole number with thousands commas; >= 10: one decimal; >= 1: two; else three significant figures."""
    a = abs(x)
    q = Decimal(1) if a >= 100 else Decimal("0.1") if a >= 10 else Decimal("0.01") if a >= 1 else None
    if q is None:
        if a == 0:
            return "0"
        q = Decimal(1).scaleb(a.adjusted() - 2)
    y = x.quantize(q, rounding=ROUND_HALF_UP)
    s = f"{y:,f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _unit_of(tok: str) -> tuple | None:
    if tok in _CASE_SENSITIVE:
        return _U["kN"] if tok == "kN" else _U["kn"]
    return _U.get(tok) or _U.get(tok.lower())


def _figures(v: str, category: str, label: str) -> list[dict]:
    out = []
    for m in _FIG.finditer(v):
        tok = m.group("u")
        if re.match(r"\s*[x×]\s*\d|\.?[23²³](?!\d)|\^|[-·]\s*[A-Za-z]", v[m.end():m.end() + 4]):
            continue                                    # "10in×8in", "1,641 ft.3", "2,569 ft-lbf": not a plain length -> as written
        if tok.lower() in ("in", "m", "t", "g", "l", "mi", "yd") and not re.match(r"\s*(?:$|[),;/.x×(]|\s*x\s|\s*\(|\s+(?:long|wide|high|deep|span|length|range|altitude|max|min|loaded|empty|combat|class|at|unprepared|prepared|wading|"
                                                                     r"fording|cross-country|on road|off road|without prep\w*|with prep\w*)\b)", v[m.end():m.end() + 16]):
            continue                                    # prose: "1 in 3", "5 m with ...", "3 t of ..." -> not a measured figure here
        if tok in ("nm",):
            continue
        info = _unit_of(tok)
        if not info:
            continue
        dim, system, factor, show = info
        if dim == "mass" and system == "imperial" and re.search(r"thrust", label, re.I):
            dim, system, factor = _U["lbf"][:3]            # "thrust 40,000 lb" is a force (shown as the source wrote it: lb)
        out.append({"m": m, "dim": dim, "sys": system, "factor": factor, "show": show, "tok": tok})
    return out


_TARGET = {"mm": "length", "cm": "length", "m": "length", "km": "length", "g": "mass", "kg": "mass", "t": "mass", "km/h": "speed", "m/s": "speed", "kN": "force"}
_METRIC_FOR = {"length": {"in": "mm", "ft": "m", "yd": "m", "mi": "km", "nmi": "km"}, "mass": {"lb": "kg", "oz": "g"},
               "speed": {"mph": "km/h", "ft/s": "m/s", "kn": "km/h"}, "force": {"lbf": "kN", "lb": "kN"}, "area": {"ft²": "m²"}, "volume": {"US gal": "L"}}


def _convert_nums(nums: str, factor: Decimal, to: str) -> str:
    to_f = _U[to][2] if to in _U else _U[{"m²": "m2", "L": "l"}.get(to, to)][2]
    count = re.fullmatch(r"(\d{1,2})(\s*[x×]\s*)(%s)" % _NUM, nums)
    if count and int(count.group(1)) <= 12:              # "2 x 200 gal": two tanks of 200 gal, not a 2 x 200 shape
        return count.group(1) + count.group(2) + fmt_num(_dec(count.group(3)) * factor / to_f)
    return re.sub(_NUM, lambda m: fmt_num(_dec(m.group(0)) * factor / to_f), nums)


def normalise_units(value: str, category: str, label: str = "", target: str | None = None) -> str:
    """Metric first, imperial in brackets; "kg kg" once; "20mm" -> "20 mm"; a figure in the category's unit for the parameter
    (target) when the value holds exactly one figure of that dimension. Nautical units stay on ships (STD: knots, nm)."""
    v = re.sub(r"(\d)(mm|cm|km/h|kmh|km|kg|kN|kW|hp|lbs?|ft|m/s|mph|nmi|kts?)\b", r"\1 \2", value)
    v = re.sub(r"(?<![\w/])(%|[A-Za-z/²]+)(?:\s+\1)+(?![\w/])", lambda m: m.group(1) if (m.group(1) == "%" or _unit_of(m.group(1)) or m.group(1).lower() in ("hp", "kw", "rpm", "rounds", "hours", "h", "min", "s", "deg", "percent")) else m.group(0), v)
    naval = category == "Marine / Naval"
    if re.search(r"\d\s*(?:ft|')\s*\d+(?:\.\d+)?\s*(?:in\b|\")", v):
        return _metric_tokens(v)                          # "2 ft 4 in (71.12 cm)": feet-and-inches stays as the source wrote it
    figs = _figures(v, category, label)
    metric_seen = [(f["dim"], _dec(re.match(_NUM, f["m"].group("nums")).group(0)) * f["factor"]) for f in figs if f["sys"] == "metric"]
    # 1) a metric/imperial pair: "51.4 ft / 15.7 m", "35 ft (10.7 m)" -> "15.7 m (51.4 ft)"; "1,093 km / 590 nmi" -> "1,093 km (590 nmi)"
    edits, used = [], set()
    for a, b in zip(figs, figs[1:]):
        if a["dim"] != b["dim"] or {a["sys"], b["sys"]} == {a["sys"]} or "metric" not in (a["sys"], b["sys"]):
            continue
        between = v[a["m"].end():b["m"].start()]
        paren = re.fullmatch(r"\s*\(\s*[~≈<>≤≥]?\s*", between)
        if not (paren or re.fullmatch(r"\s*(?:/|or|=|≈)\s*[~≈<>≤≥]?\s*", between)):
            continue
        end = b["m"].end()
        if paren:
            close = re.match(r"\s*\)", v[end:])
            if not close:
                continue
            end += close.end()
        met, imp = (a, b) if a["sys"] == "metric" else (b, a)
        edits.append((a["m"].start(), end, f'{met["m"].group("nums")} {met["show"]} ({imp["m"].group("nums")} {imp["show"]})'))
        used |= {id(a), id(b)}
    # 2) a lone imperial figure -> metric (imperial); inside brackets "metric / imperial" so brackets never nest
    for f in figs:
        if id(f) in used or f["sys"] == "metric" or (naval and f["sys"] == "nautical") or f["dim"] not in _METRIC_FOR:
            continue
        to = _METRIC_FOR[f["dim"]].get(f["show"])
        if not to:
            continue
        base = _dec(re.match(_NUM, f["m"].group("nums")).group(0)) * f["factor"]
        if any(d == f["dim"] and base and abs(x - base) <= abs(base) * Decimal("0.03") for d, x in metric_seen):
            continue                                      # "161 km/h dash (100 mph, 87 kt)": the metric figure is already there
        if f["dim"] == "length" and to == "m" and target == "km":
            to = "km"
        metric = f'{_convert_nums(f["m"].group("nums"), f["factor"], to)} {to}'
        orig = f'{f["m"].group("nums")} {f["show"]}'
        depth = v[:f["m"].start()].count("(") - v[:f["m"].start()].count(")")
        edits.append((f["m"].start(), f["m"].end(), f"{metric} / {orig}" if depth > 0 else f"{metric} ({orig})"))
        used.add(id(f))
    # 3) the parameter's unit for the category (owner: one unit per parameter): a lone metric figure of that dimension is scaled
    if target in _TARGET:
        same = [f for f in figs if f["dim"] == _TARGET[target] and f["sys"] == "metric" and id(f) not in used]
        conv = [f for f in figs if f["dim"] == _TARGET[target] and id(f) in used]
        if len(same) == 1 and not conv and same[0]["show"] != target:
            f = same[0]
            edits.append((f["m"].start(), f["m"].end(), f'{_convert_nums(f["m"].group("nums"), f["factor"], target)} {target}'))
    if not edits:
        return _metric_tokens(v)
    out, last = [], 0
    for s, e, rep in sorted(edits):
        if s < last:
            continue
        out.append(v[last:s])
        out.append(rep)
        last = e
    out.append(v[last:])
    v = "".join(out)
    if target in _TARGET:                                 # a converted pair: scale its metric half to the category unit as well
        figs2 = [f for f in _figures(v, category, label) if f["dim"] == _TARGET[target] and f["sys"] == "metric"]
        if len(figs2) == 1 and figs2[0]["show"] != target:
            f = figs2[0]
            v = v[:f["m"].start()] + f'{_convert_nums(f["m"].group("nums"), f["factor"], target)} {target}' + v[f["m"].end():]
    return _metric_tokens(v)


def _metric_tokens(v: str) -> str:
    """Spelled-out metric units after a figure take their symbol: "15,240 meters" -> "15,240 m", "110 kmh" -> "110 km/h"."""
    def rep(m):
        info = _unit_of(m.group("u"))
        return f'{m.group("nums")} {info[3]}' if info and info[1] == "metric" and m.group("u") != info[3] else m.group(0)
    return _FIG.sub(rep, v)


def _unit_in(value: str, unit: str) -> bool:
    u = str(unit).strip()
    if not u:
        return True
    info = _unit_of(u)
    if info and any(_unit_of(f["tok"]) == info for f in _figures(value, "", "")):
        return True
    if re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(u), value, re.I):
        return True
    if u.lower() in ("percent", "%") and "%" in value:
        return True
    # the value already names some other unit ("Minimum 30 minutes" under hours): the stored unit is not added
    return bool(_figures(value, "", "")) or bool(re.search(r"\d\s*(?:%|°|rounds?|rpm|hours?|hrs?|min(?:utes?)?|sec(?:onds?)?|mach|hp|kw|w|v|db|dbm|mhz|ghz|khz|hz|g\b)", value, re.I))


def with_unit(value: str, unit: Any) -> str:
    """The stored unit, once: added to a value that does not already state a unit ("12,800 kg" + "kg" stays "12,800 kg")."""
    if unit in (None, "") or _unit_in(value, unit):
        return value
    return f"{value} {unit}"


# ---- the sheet -----------------------------------------------------------------------------------------------------------
_QUAL = r"(?:up to|over|under|about|approx\.?|approximately|max\.?|min\.?|more than|less than|at least|in excess of|ca\.?|c\.|nominal)"
_PART_LABEL = re.compile(r"^(?P<l>[A-Za-z][A-Za-z /&'().+-]{1,34}?)\s*(?::\s*|\s+)(?P<v>(?:%s\s+)?[<>~≈+±-]?\s*\d.*)$" % _QUAL, re.I)
_PART_COLON = re.compile(r"^(?P<l>[A-Za-z][A-Za-z0-9 /&'().+-]{1,40}?)\s*:\s+(?P<v>\S.*)$")
_PART_STOP = {"the", "a", "an", "of", "in", "into", "within", "to", "for", "since", "by", "at", "from", "with", "on", "than", "type", "is", "are",
              "was", "were", "be", "and", "or", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "fitted", "up"}
_LWH = re.compile(r"^L\s+\S.*\bx\s*W\s+\S.*\bx\s*H\s+\S")


def _split_part(part: str, colon_only: bool) -> tuple[str | None, str]:
    """"GVW up to 14,500 kg" -> ("GVW", "up to 14,500 kg"); "span: 11 m" -> ("span", "11 m"); "360 hp diesel" -> (None, ...)."""
    if _LWH.match(part):
        return "Dimensions", part
    m = (_PART_COLON if colon_only else _PART_LABEL).match(part) or (None if colon_only else _PART_COLON.match(part))
    if not m:
        return None, part
    lab = m.group("l").strip()
    if lab.count("(") != lab.count(")"):
        return None, part
    words = lab.split()
    if (re.fullmatch(r"%s|[a-z]|and|or|with|incl\.?|including|x" % _QUAL, lab, re.I) or len(re.sub(r"[^A-Za-z]", "", lab)) < 2
            or len(words) > 4 or words[-1].lower() in _PART_STOP or words[0].lower() in _PART_STOP):
        return None, part                                   # "Retains zero within 0.5 mrad", "One 3 V lithium": prose, not a name
    return lab, m.group("v").strip()


def present(rows: Iterable[tuple[Any, Any, Any]], category: Any, product_name: Any = "", sub_type: Any = None,
            maker: Maker | None = None) -> dict[str, list[dict]]:
    """[(label, value, unit)] of one product -> its spec sheet sections. Each row: {"l": label, "v": value | [values]}
    (a list value is one row, shown as a list in one cell); a feature with no label of its own is {"v": ...}.
    maker = the product's own company (Maker), so "(Elbit)" after an Elbit figure is read as a citation and dropped."""
    from backend.areas.b_products import spec_kind          # the existing figure / text split (user 2026-10-18)
    cat = str(category or "")
    armed = cat in PLATFORM_CATS and not is_weapon_product(product_name, cat, sub_type)
    cells: dict[tuple, dict] = {}                           # (section, label) -> {"l", "vs", "order"}
    seq = 0

    def put(section: str, label: str, values: list[str], order: tuple) -> None:
        nonlocal seq
        key = (section, label.casefold())
        cell = cells.get(key)
        if not cell:
            seq += 1
            cell = cells[key] = {"l": label, "vs": [], "order": order + (seq,)}
        for v in values:
            if v and v.casefold() not in {x.casefold() for x in cell["vs"]}:
                cell["vs"].append(v)

    def place(label: str, values: list[str], kind: str, label_unit: str | None, stored_unit: Any) -> None:
        hit = classify(label, cat)
        target = hit[3] if hit else None
        shown = hit[2] if hit else label
        arm = armed and _armament_label(shown, cat)
        if arm:
            ai, shown, target = armament_label(shown if hit and hit[1] != 99 else label)
        if kind == "quant" or hit or arm:
            values = [normalise_units(with_unit(with_unit(v, label_unit) if _bare(v) else v, stored_unit if len(values) == 1 else None),
                                      cat, shown, target) for v in values]
        if arm:
            put("armament", shown, values, (ai, 0))
        elif hit:
            put("key", shown, values, (hit[0], hit[1]))
        elif kind == "quant":
            put("other", shown, values, (0, 0))
        else:
            put("features", shown, values, (0, 0))

    for label, value, unit in rows:
        lab, lunit, container = clean_label(label)
        kind, _v = spec_kind(re.sub(r"^[\s•·*-]+", "", str(label or "")), value, unit)
        if kind == "note":
            continue
        items = clean_text(value, maker)
        if not items:
            continue
        if container:                                   # "Note", "Platform limits (... not published)": each figure names itself
            rest = []
            for it in items:
                pl, pv = _split_part(it, colon_only=False)
                if pl:
                    plab, plunit, pcont = clean_label(pl)
                    if plab and not pcont:
                        pk = spec_kind(plab, pv)[0]
                        place(plab, [pv], "quant" if pk == "quant" else "qual", plunit, None)
                        continue
                rest.append(it)
            if rest:
                rk = "quant" if any(spec_kind("x", r)[0] == "quant" for r in rest) else "qual"
                if rk == "quant":
                    place(lab if lab and _norm(lab) not in GENERIC else "Other figures", rest, "quant", lunit, None)
                else:
                    put("features", "", rest, (0, 0))
            continue
        rest = []
        for it in items:                                 # under a real label only "name: value" parts become rows of their own
            pl, pv = _split_part(it, colon_only=True) if len(items) > 1 else (None, it)
            if pl:
                plab, plunit, pcont = clean_label(pl)
                if plab and not pcont:
                    place(plab, [pv], spec_kind(plab, pv)[0] if spec_kind(plab, pv)[0] != "note" else "qual", plunit, None)
                    continue
            rest.append(it)
        if rest:
            place(lab, rest, kind, lunit, unit)

    out: dict[str, list[dict]] = {"key": [], "other": [], "armament": [], "features": []}
    for (section, _k), cell in sorted(cells.items(), key=lambda kv: kv[1]["order"]):
        if not cell["vs"]:
            continue
        row = {"v": cell["vs"][0] if len(cell["vs"]) == 1 else cell["vs"]}
        if cell["l"]:
            row = {"l": cell["l"], **row}
        out[section].append(row)
    return out


def _bare(v: str) -> bool:
    return bool(re.fullmatch(r"\s*[~<>≈≤≥+±]?\s*(?:%s)(?:\s*(?:-|–|to)\s*(?:%s))?\s*\+?\s*" % (_NUM, _NUM), v))


# ---- product names (audit finding 9) --------------------------------------------------------------------------------------
COUNTRIES = ["India", "Indian", "Poland", "Polish", "Australia", "Australian", "Norway", "Norwegian", "Finland", "Finnish", "Belgium", "Belgian",
             "Germany", "German", "France", "French", "UK", "British", "United Kingdom", "USA", "US", "U.S.", "US Army", "US Navy", "USMC", "USAF",
             "United States", "Israel", "Israeli", "Korea", "Korean", "ROK", "RoK", "Turkey", "Turkish", "Türkiye", "Egypt", "Egyptian", "Saudi",
             "UAE", "Romania", "Romanian", "Estonia", "Latvia", "Lithuania", "Sweden", "Swedish", "Brazil", "Canada", "Canadian", "Japan",
             "Japanese", "Spain", "Spanish", "Italy", "Italian", "Netherlands", "Dutch", "Denmark", "Danish", "Czech", "Hungary", "Greece", "Greek",
             "Philippines", "Indonesia", "Malaysia", "Thailand", "Vietnam", "Taiwan", "Ukraine", "Ukrainian", "Bulgaria", "Switzerland", "Swiss",
             "Austria", "Qatar", "Kuwait", "Morocco", "Algeria", "Nigeria", "South Africa", "Chile", "Colombia", "Mexico", "Peru", "Armenia",
             "Singapore", "New Zealand", "Pakistan", "Bangladesh", "Oman", "Bahrain", "NATO", "Army", "Navy", "Air Force", "Marine Corps",
             "Royal Navy", "Coast Guard"]
_CTRY = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(c) for c in sorted(COUNTRIES, key=len, reverse=True)))
_STATUS_W = re.compile(r"\b(?:concept|prototype|planned|developed|in development|under development|development|demonstrator|proposed|in trials|"
                       r"trials|unveiled|cancelled|canceled|retired|upcoming|announced|not confirmed|pre-production|in testing|future)\b", re.I)
_PROG_W = re.compile(r"\b(?:programme|program|contract|collaboration|partnership|joint venture|JV|licen[cs]ed?|ToT|work share|industrial participation|"
                     r"offset|Make in India|co-production|co-development|teaming|MoU|consortium|partner|built by|made by|-led|led by)\b|\b(?:for|with|by)\s+[A-Z]{2,}", re.I)
_LEAD_W = re.compile(r"^\s*(?:incl\.?|including|with|without|aka|a\.k\.a\.|also|formerly|ex-|e\.g\.|i\.e\.)\b", re.I)
_UNIT_W = {"mm", "cm", "km", "kg", "cal", "inch", "in", "lb", "lbs", "ton", "tons", "tonne", "mk", "hp", "kw", "x", "and", "or", "the", "of", "a"}
_DESC_NOUN = re.compile(r"\b(?:howitzer|gun|guns|vehicle|vehicles|missile|missiles|system|systems|rifle|rifles|round|rounds|launcher|radar|carrier|truck|"
                        r"trucks|tank|drone|drones|uav|uas|ugv|usv|uuv|vessel|boat|ship|ammunition|munition|munitions|rocket|rockets|projectile|"
                        r"cartridge|station|turret|sensor|camera|sight|scope|goggle|goggles|radio|mortar|helicopter|aircraft|fighter|trainer|engine|"
                        r"component|components|forging|forgings|simulator|kit|pod|bomb|torpedo|sonar|jammer|platform|module|fuze|warhead|grenade|"
                        r"machine|pistol|carbine|launcher|licence|license|contract|programme|program|variant|version|upgrade|explosive|explosives|"
                        r"decoy|mast|suite|weapon|weapons|equipment|shelter|bridge|trailer|unit|units)\b", re.I)


def company_re(companies: Iterable[str]) -> re.Pattern | None:
    names = sorted({c.strip() for c in companies if c and len(c.strip()) >= 3}, key=len, reverse=True)
    if not names:
        return None
    return re.compile(r"(?<![\w-])(?:%s)(?![\w-])" % "|".join(re.escape(n) for n in names), re.I)


def _paren_groups(s: str) -> list[tuple[int, int]]:
    """Top-level (start, end) of every balanced bracket group."""
    out, depth, start = [], 0, None
    for i, ch in enumerate(s):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                out.append((start, i + 1))
    return out


def _desig(name: str) -> str:
    m = re.match(r"\s*([A-Za-z]{1,6}[- ]?\d{1,4}[A-Za-z]{0,3}|[A-Za-z][A-Za-z0-9-]{2,}|\d+[A-Za-z0-9-]*)", name)
    return m.group(1) if m else ""


def _drop_paren(inner: str, name: str, co_re: re.Pattern | None) -> bool:
    t = inner.strip()
    if not t:
        return True
    if (co_re and co_re.search(t)) or _CTRY.search(t) or _STATUS_W.search(t) or _PROG_W.search(t) or _LEAD_W.match(t):
        return True
    items = [x.strip() for x in re.split(r"\s*/\s*", t)]
    head = _desig(name)
    if len(items) > 1 and head and all(x.upper().startswith(head.upper()) for x in items):
        return True                                       # "F-35 Lightning II (F-35A / F-35B / F-35C)": the family lists its variants
    words = re.findall(r"[A-Za-z]+(?:'[a-z]+)?", t)
    code = re.sub(r"[^A-Z]", "", name.split()[0]) if name.split() else ""
    if len(code) >= 3 and "".join(w[0] for w in words if w[0].isupper()).startswith(code):
        return True                                       # "ATAGS (Advanced Towed Artillery Gun System, 155mm/52 cal)": the acronym spelt out
    if re.search(r"\d\s*mm\b", t, re.I) and re.search(_DESC_NOUN.pattern, t, re.I):
        return True                                       # "M-71 (155mm/39 Towed Howitzer, Soltam)": calibre and role, not the name
    prose =[w for w in words if w.islower() and len(w) >= 3 and w not in _UNIT_W]
    named = [w for w in words if not w.islower()] or re.search(r"\d", t)
    role = any(_DESC_NOUN.fullmatch(w) for w in prose)                  # "(VSHORAD missile)", "(patrol-boat RWS)" is a role
    return len(prose) >= 2 or (len(prose) >= 1 and (not named or role))


_PART_NOUN = re.compile(r"\b(?:radars?|sights?|engines?|turrets?|fuzes?|fuses?|seekers?|launchers?|sensors?|cameras?|antennas?|"
                        r"gearbox(?:es)?|transmissions?|propulsion|motors?|warheads?|modules?|suites?|kits?|pods?|mounts?|"
                        r"stations?|consoles?|simulators?|trainers?|gun barrels?|barrels?|chassis|hulls?|track systems?)\b", re.I)


def display_name(name: Any, companies: Iterable[str] = ()) -> str:
    """The product's name without the extra text the workbook put in it: the company in brackets, a role / descriptor phrase, a
    country or customer, a status word, a programme or partner note (audit finding 9). Deterministic; the stored name stays
    the join and search key. Several products in one name (pattern f) are left for owner review."""
    raw = str(name or "").strip()
    co_re = companies if isinstance(companies, re.Pattern) else company_re(companies or ())
    s = raw
    # trailing " - DEVELOPMENT" / " - ANNOUNCED / PLANNED (...)", " - <company>", " - Italian Army", " - lower-case descriptor"
    while True:
        m = re.search(r"\s+[-–—]\s+([^-–—]+)$", s)
        if not m:
            break
        seg = m.group(1).strip()
        bare = re.sub(r"\([^()]*\)", "", seg).strip()
        if (_STATUS_W.match(bare) or (co_re and co_re.fullmatch(bare)) or not _CTRY.sub("", bare).strip(" ,/&")
                or (bare[:1].islower() and not re.match(r"\d", bare))):
            s = s[:m.start()].strip()
            continue
        break
    # brackets: drop the ones that are not part of the name ("(CTOL)", "(TACS)", "(PJ-10)", "(.50 CAL)" stay)
    for a, b in reversed(_paren_groups(s)):
        if _drop_paren(s[a + 1:b - 1], raw, co_re):
            s = s[:a] + s[b:]
    s = re.sub(r"\s{2,}", " ", s).strip(" -,;:/")
    # a designation, then its calibre and role: "K9 Vajra-T 155 mm/52 cal Tracked Self-Propelled Howitzer" -> "K9 Vajra-T"
    first = re.split(r"\s+[-–—]\s+", s)[0]
    m = re.match(r"^(?P<head>[A-Za-z].*?)\s+\d+(?:\.\d+)?(?:x\d+)?\s*mm\b(?P<tail>.*)$", first)
    if (m and re.search(r"[A-Z0-9]", m.group("head")) and _DESC_NOUN.search(m.group("tail"))
            and m.group("head").count("(") == m.group("head").count(")") and not (co_re and co_re.fullmatch(m.group("head")))):
        s = m.group("head") + s[len(first):]
    # a designation, then a lower-case role: "M88A2 HERCULES MRO licence" -> "M88A2 HERCULES MRO"; a code of 4 characters or fewer
    # keeps its role ("NOVA night vision goggle", "K2 tank sights")
    m = re.match(r"^(?P<head>.*?[A-Z0-9][^\s]*)(?P<tail>(?:\s+(?!(?:mm|cm|m|km|kg|g|t|cal|in|x|class)\b)[a-z][a-z/-]*)+)(?P<rest>\s*(?:\(.*)?)$", s)
    if (m and _DESC_NOUN.search(m.group("tail")) and re.search(r"\d|[A-Z]{2}", m.group("head"))     # the head is a designation;
            and len(m.group("head").strip()) > 4                                                     # but a bare short code misleads
            and not _PART_NOUN.search(m.group("tail"))      # a PART named after its platform keeps its type: "KF-21 AESA radar"
                                                            # is the radar, "KF-21 AESA" would read as the fighter (owner 2026-10-25)
            # ("K2 tank sights" -> "K2" reads as the K2 tank, "APS radar" -> "APS"): owner review 2026-10-25
            and not (co_re and co_re.fullmatch(m.group("head").strip()))):                           # "NORINCO naval RWS" stays
        s = (m.group("head") + m.group("rest")).strip()
    # "... for SM-3" / "... for HAL": the platform or customer it is made for
    s = re.sub(r"\s+for\s+(?:the\s+)?(?:[A-Z][\w/-]*\d[\w/-]*|[A-Z]{2,}[\w/-]*)(?:\s+[A-Z][\w/-]*)*$", "", s)
    s = re.sub(r",\s*(?:concept|prototype|planned|developed|in development)\b.*$", "", s, flags=re.I)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -–—,;:/")
    return s if len(s) >= 2 else raw


# ---- family / variant (audit finding 6) -----------------------------------------------------------------------------------
_FAM_WORD = re.compile(r"\b(?:family|series|common[- ]systems|platform family)\b", re.I)
_FAM_MARK_DESC = re.compile(r"\bfamily\b|common[- ]systems|program(?:me)?/common", re.I)
_VARIANT_WORD = re.compile(r"^(?:(?i:Block|Blk|Mk\.?|MK\w*|Mark|Increment|Inc|Batch|Gen)\b|\d{1,2}[A-Z]{0,2}\b)")
_DESIG_SUFFIX = re.compile(r"[A-Z]{1,2}\d?|\d[A-Z]?|-[A-Z0-9]{1,3}|[A-Z]\d|-\d{1,2}|\s+(?i:Block|Blk|Mk\.?|MK|Mark|Increment|Inc)\s*[\w.+]+")
# a service, an upgrade or a launcher is not a variant card of a product, and not a family card either
_NOT_FAMILY = re.compile(r"\b(?:upgrade|retrofit|program|programme|conversion|reset|recapitali[sz]ation|mro|support|training|simulator|"
                         r"launcher|launch and recovery|launch system|recovery system|canister|kit|legacy|target[- ]practice|tp|trainer|"
                         r"inert|dummy|blank)\b", re.I)


def _base(name: str, keep_tokens: bool) -> str:
    """The name without brackets; keep_tokens keeps a one-token code bracket ("(NISHANK)", "(PJ-10)"), which names the model."""
    s = name
    while True:
        t = re.sub(r"\(([^()]*)\)", lambda m: m.group(0) if keep_tokens and re.fullmatch(r"[A-Z0-9][A-Z0-9./+-]*", m.group(1).strip()) else "", s)
        if t == s:
            break
        s = t
    return re.sub(r"\s{2,}", " ", s).strip(" -")


def _slash_list(name: str, desig: str) -> set[str]:
    """Designations a family name lists: "K9 / K9A1 Thunder" -> {K9, K9A1}; "F-35 Lightning II (F-35A / F-35B / F-35C)" -> {F-35A, ...};
    "AIM-9X Sidewinder (family: Block I / II / II+)" counts too. Empty when the "/" joins something else ("HEI/SD", "SAMP/T")."""
    out = set()
    for chunk in [name] + re.findall(r"\(([^()]*)\)", name):
        items = [x.strip() for x in re.split(r"\s+/\s+|(?<=\w)/(?=[A-Z])", re.sub(r"^\s*(?:incl\.?|including|family:)\s*", "", chunk, flags=re.I))]
        hits = {_desig(x) for x in items if desig and x.upper().startswith(desig.upper())}
        if len(items) > 1 and len(hits) >= 2 or (len(hits) >= 1 and re.match(r"\s*(?:incl\.?|including)\b", chunk, re.I)):
            out |= hits
    return out


def umbrella_ids(products: list[dict], companies: Iterable[str] = ()) -> dict[str, dict]:
    """{umbrella product id: {"variants": [ids], "rule": why}} for one company's products ({"id", "name", "description", "category"}).
    An umbrella is a family card with variant cards of the same kind beside it (owner 2026-10-25: show the variants, not the
    family). Rules, all on the stored names:
      R1 configuration  "COBRA II" beside "COBRA II - Mobile Satcom Vehicle" (the variant names a configuration after " - ")
      R2 designation    "AIM-120 AMRAAM" beside "AIM-120C AMRAAM" (the family's name with a suffix after its designation)
      R3 version word   "Aster 30" beside "Aster 30 Block 1", "Brimstone" beside "Brimstone 2"; on a card marked as a family,
                        any card that extends its name ("FMTV A2 (Family of ...)" beside "FMTV A2 6x6 Cargo")
      R4 listed         "K9 / K9A1 Thunder", "F-35 Lightning II (F-35A / F-35B / F-35C)": the card lists the variants that have
                        cards of their own
    R2 and R3 need two variants, or one plus a family marker (family / series / common-systems in the name or description,
    "(incl. C-130J-30 ...)"), so a single derivative ("Altius-600M" beside "Altius-600") hides nothing. A name that starts
    with a calibre (ammunition: "155 mm LU211 HE") is never a family by designation; a service, upgrade or launcher card is
    neither a family nor a variant."""
    co_re = companies if isinstance(companies, re.Pattern) else company_re(companies or ())
    info = []
    for p in products:
        nm = str(p.get("name") or "")
        dn = display_name(nm, co_re)
        keep = _base(dn, True)
        desig = _desig(keep)
        info.append({"id": p.get("id"), "raw": nm, "cat": p.get("category"), "keep": keep, "strip": _base(nm, False),
                     "dash": bool(re.search(r"\s+[-–—]\s+", _base(nm, False))), "desig": desig if re.match(r"[A-Za-z]", desig) else "",
                     "service": bool(_NOT_FAMILY.search(nm)), "list": _slash_list(nm, desig),
                     "marker": bool(_FAM_WORD.search(nm) or _FAM_MARK_DESC.search(str(p.get("description") or "")))})
    out = {}
    for p in info:
        if p["dash"] or p["service"] or not p["keep"]:
            continue
        r1, r2, r3, r4 = [], [], [], []
        pk, pd = p["keep"], p["desig"]
        marker = p["marker"] or bool(p["list"])
        for q in info:
            if q is p or q["service"] or q["keep"].casefold() == pk.casefold() or (p["cat"] and q["cat"] and p["cat"] != q["cat"]):
                continue                                  # a variant is the same kind of product (F-35 TR-3 hardware is not an F-35)
            if q["dash"] and re.split(r"\s+[-–—]\s+", q["strip"])[0].casefold() == p["strip"].casefold():
                r1.append(q["id"])
            elif pd and q["desig"] and p["list"] and q["desig"] != pd and (q["desig"] in p["list"] or
                                                                           (q["desig"].startswith(pd) and _DESIG_SUFFIX.fullmatch(q["desig"][len(pd):]))):
                r4.append(q["id"])
            elif pd and q["keep"].startswith(pd):
                rest = pk[len(pd):]
                suf = q["keep"][len(pd):len(q["keep"]) - len(rest)] if q["keep"].endswith(rest) else ""
                if suf and _DESIG_SUFFIX.fullmatch(suf) and not (pd[-1].isdigit() and suf[0].isdigit()):   # VN2 -> VN22 is another vehicle
                    r2.append(q["id"])
                elif q["keep"].casefold().startswith(pk.casefold() + " ") and (marker or _VARIANT_WORD.match(q["keep"][len(pk) + 1:])):
                    r3.append(q["id"])                    # "Aster 30 Block 1"; under a family marker any "FMTV A2 <...>" card
        listed = [i for i in r4 if next(x for x in info if x["id"] == i)["desig"] in p["list"]]
        if r1:
            out[p["id"]] = {"variants": r1 + r2 + r3 + r4, "rule": "R1 configuration"}
        elif listed:
            out[p["id"]] = {"variants": r4 + r2 + r3, "rule": "R4 listed variants"}
        elif r2 + r3 and (marker or len(r2 + r3) >= 2):
            out[p["id"]] = {"variants": r2 + r3, "rule": ("R2 designation" if r2 else "R3 version word") + (" + marker" if marker else " (2+ variants)")}
    return out


# ---- self-check --------------------------------------------------------------------------------------------------------------
def _selftest() -> None:
    def sheet(rows, cat, name=""):
        return present(rows, cat, name)

    def row(sec, label):
        hit = [r for r in sec if r.get("l") == label]
        assert len(hit) == 1, (label, sec)
        return hit[0]["v"]

    # unit dedupe: the value already names the unit the record stores
    s = sheet([("Fording capability", "150cm", "cm"), ("Side slope", "60%", "%"), ("Cruising Range", "1,000 km", "km")], "Protected & Armoured Vehicles")
    assert row(s["key"], "Fording depth") == "150 cm" and row(s["key"], "Side slope") == "60%" and row(s["key"], "Operating range") == "1,000 km", s
    assert normalise_units("12,800 kg kg", "Other") == "12,800 kg" and with_unit("4 to 9 hours", "hours") == "4 to 9 hours"
    assert with_unit("eight", "hours") == "eight hours" and with_unit("Minimum 30 minutes", "hours") == "Minimum 30 minutes"
    # label unit vs value unit (spec_store template keys): the value's unit wins, metric first
    s = sheet([("mtow kg", "70,000 lb", "lb"), ("length overall m", "51.4 ft", "ft"), ("maximum speed kmh", "Mach 1.6", "Mach"),
               ("operational range km", "1,380 miles", "miles")], "Aircraft & Aerostructures", "F-35 Lightning II")
    assert row(s["key"], "Maximum take-off weight") == "31,751 kg (70,000 lb)", s
    assert row(s["key"], "Length") == "15.7 m (51.4 ft)" and row(s["key"], "Maximum speed") == "Mach 1.6", s
    assert row(s["key"], "Range") == "2,221 km (1,380 mi)", s
    assert [r["l"] for r in s["key"]] == ["Length", "Maximum take-off weight", "Maximum speed", "Range"], s     # the standard order
    s = sheet([("max speed knots", "8 km/h", "knots")], "Protected & Armoured Vehicles")
    assert row(s["key"], "Maximum road speed") == "8 km/h", s
    # imperial -> metric (imperial); a stated pair is put metric first
    assert normalise_units("132.6 ft", "Aircraft & Aerostructures", "Span") == "40.4 m (132.6 ft)"
    assert normalise_units("14.4 ft / 4.38 m", "Aircraft & Aerostructures", "Height") == "4.38 m (14.4 ft)"
    assert normalise_units("over 50,000 feet (15,240 meters)", "Aircraft & Aerostructures", "Service ceiling", "m") == "over 15,240 m (50,000 ft)"
    assert normalise_units("Mach 1.6 (~1,200 mph)", "Aircraft & Aerostructures", "Speed") == "Mach 1.6 (~1,931 km/h / 1,200 mph)"
    assert normalise_units("43,000 pounds", "Aircraft & Aerostructures", "Afterburner thrust") == "191 kN (43,000 lb)"
    assert normalise_units("32,000 kg", "Protected & Armoured Vehicles", "Combat weight", "t") == "32 t"
    assert normalise_units("20 x 13 x 5 in", "Other", "Dimensions") == "508 x 330 x 127 mm (20 x 13 x 5 in)"
    assert normalise_units("28 knots", "Marine / Naval", "Maximum speed") == "28 knots"                        # ships keep knots (STD)
    # a packed value under a real label is ONE row with a list value; never a blank label
    s = sheet([("Engine", "MTU MT 881 Ka-500, 1,000 hp; Allison X1100-5A3 transmission", None)], "Artillery")
    assert row(s["key"], "Engine") == ["MTU MT 881 Ka-500, 1,000 hp", "Allison X1100-5A3 transmission"], s
    # under a container label each figure is labelled by its own leading words; the rest stay one list row
    s = sheet([("Variant-specific weight/performance not published by Otokar; shared platform data (AZ77EG-25)",
                "GVW up to 14,500 kg; crew up to 11 incl. driver and commander; L 6,400 x W 2,500 x H 2,300 mm; 360 hp diesel; 110 km/h / 700 km", None)],
              "Protected & Armoured Vehicles", "COBRA II - Mobile Satcom Vehicle")
    assert row(s["key"], "Gross vehicle weight") == "up to 14.5 t" and row(s["key"], "Crew") == "up to 11 incl. driver and commander", s
    assert row(s["key"], "Dimensions") == "L 6,400 x W 2,500 x H 2,300 mm" and row(s["other"], "Platform data") == ["360 hp diesel", "110 km/h / 700 km"], s
    assert all(r.get("l") for sec in ("key", "other", "armament") for r in s[sec])
    # source talk: a trailing source bracket goes, the figure stays
    s = sheet([("Weight empty", "29,300 lb (Lockheed 2021 fast facts)", None), ("Crew (NAVAIR MH-60R page)", "3", None)], "Aircraft & Aerostructures")
    assert row(s["key"], "Empty weight") == "13,290 kg (29,300 lb)" and row(s["key"], "Crew") == "3", s
    assert strip_sources("<10 m (GPS); SAL <5 m (Elbit 2025 datasheet) - sources differ") == "<10 m (GPS); SAL <5 m"
    elbit = Maker(["Elbit Systems"])
    assert clean_text('28.5 km (Elbit); 21 km NATO-standard', elbit) == ["28.5 km", "21 km NATO-standard"]
    assert clean_text('Elbit states "wide angle of traverse"', elbit) == ["wide angle of traverse"]
    assert clean_text("25 to 40 km; 25-38 km per Militarnyi; GP6 guided shell 6-25 km (AR 2019)") == ["25 to 40 km", "25-38 km", "GP6 guided shell 6-25 km"]
    assert clean_text("4569 Class II per Bharat Forge") == ["4569 Class II"]
    assert clean_text("6.8 t; titanium version 4.8 t (Frontier India)") == ["6.8 t", "titanium version 4.8 t"]
    assert clean_text("800 m; 1000 m (DoO(C&S) product page, archived)") == ["800 m", "1000 m"]
    assert clean_text("39 degrees both sides (NRC Canada)") == ["39 degrees both sides"]
    assert clean_text("maximum about 5 rounds per minute; the 2016 article text is truncated at '4 to... rounds'") == ["maximum about 5 rounds per minute"]
    assert clean_text("12.5 t (total)") == ["12.5 t (total)"] and clean_text("> 40 km/h (metalled roads)") == ["> 40 km/h (metalled roads)"]
    assert clean_text("Rotax 916 (Army Recognition); older sources Rotax 914 - disputed") == ["Rotax 916"]
    assert clean_text("24/7 support; Lockheed F-35 sustainment page text could not be extracted (JS-rendered)") == ["24/7 support"]
    # placeholders and "not disclosed" rows are not shown
    s = sheet([("Altitude", "Not officially disclosed (earlier open-source ~36 km figure was uncited and removed)", None), ("Armament", "None", None),
               ("Numeric specs", "none", None), ("Hardware specifications", "not applicable", None)], "Missiles & Air Defence")
    assert not any(s.values()), s
    # armament on a platform: the carried gun's figures leave the aircraft's own sheet; calibre / caliber merge into one row
    s = sheet([("Calibre", "20mm", "mm"), ("caliber", "20mm", "mm"), ("rate of fire", "up to 6,000 rounds per minute", "rounds"),
               ("Wingspan", "35 ft / 10.7 m", None), ("Standard internal weapons load", "25 mm GAU-22/A cannon; 2x AIM-120C/D", None)],
              "Aircraft & Aerostructures", "F-35A Lightning II (conventional takeoff and landing, CTOL)")
    assert row(s["armament"], "Calibre") == "20 mm" and row(s["armament"], "Rate of fire") == "up to 6,000 rounds per minute", s
    assert row(s["key"], "Wingspan") == "10.7 m (35 ft)" and "Calibre" not in [r.get("l") for r in s["key"]], s
    s = sheet([("Calibre", "30 mm", None), ("Weight", "1,900 kg", None)], "Protected & Armoured Vehicles", "UT30MK2 unmanned turret")
    assert row(s["key"], "Weight") == "1.9 t" and not s["armament"], s                                      # a turret's calibre is its own
    # display names (real names from the audit)
    co = ["L3Harris", "L3Harris Technologies", "Hanwha Systems", "Hanwha Aerospace", "Rheinmetall", "Rheinmetall Aviation Services", "KSSL",
          "Thales Belgium", "Aerojet Rocketdyne", "MBDA", "Lockheed Martin", "Otokar"]
    names = {
        "Compact Laser Weapon (Hanwha Systems)": "Compact Laser Weapon",
        "NOVA night vision goggle (L3Harris)": "NOVA night vision goggle",
        "K2 tank sights (gunner/commander sight and thermal camera)": "K2 tank sights",
        "APS radar (Hanwha Systems)": "APS radar",
        "KF-21 AESA radar (Hanwha Systems)": "KF-21 AESA radar",
        "FFX Batch-III multi-function radar (FFX B-3 MFR, Hanwha Systems)": "FFX Batch-III multi-function radar",
        "EO/IR-linked drone surveillance radar (Hanwha Systems)": "EO/IR-linked drone surveillance radar",
        "Gnat HD (L3Harris UK)": "Gnat HD",
        "ARX 20 (20mm land remote-controlled weapon station)": "ARX 20",
        "Vingmate FCS 4500 (day-night sight and fire control system)": "Vingmate FCS 4500",
        "LANIUS-X (X200 indoor/outdoor seek-and-strike drone)": "LANIUS-X",
        "K9A3 (next-generation K9, concept)": "K9A3",
        "DEFENDAIR (counter-UAS missile) - DEVELOPMENT": "DEFENDAIR",
        "F-21 (proposed fighter for India)": "F-21",
        "AbramsX (next-generation Abrams technology demonstrator, 2022)": "AbramsX",
        "FZ275 70 mm semi-active laser-guided rocket (Thales Belgium; Indian manufacture planned with KSSL)": "FZ275",
        "Hunter class frigate (Australia)": "Hunter class frigate",
        "K9 VAJRA-T (India)": "K9 VAJRA-T",
        "K9 Vajra-T 155 mm/52 cal Tracked Self-Propelled Howitzer": "K9 Vajra-T",
        "Vlissingen (2nd rMCM vessel, first for the Royal Netherlands Navy)": "Vlissingen",
        "Prachand LCH fuselage structures (for HAL)": "Prachand LCH fuselage structures",
        "Modular Imaging Mast Attack (submarine optronic mast) (L3Harris)": "Modular Imaging Mast Attack",
        "Sharang 155mm/45 Calibre Gun (130mm M-46 upgrade)": "Sharang",
        "F-35A Lightning II (conventional takeoff and landing, CTOL)": "F-35A Lightning II",
        "F-35 Lightning II (F-35A / F-35B / F-35C)": "F-35 Lightning II",
        "Arad (5.56x45 mm / .300 BLK M4-type assault rifle) - ANNOUNCED / PLANNED (not confirmed in production)": "Arad",
        "M88A2 HERCULES MRO licence (Poland, WZM / HCP)": "M88A2 HERCULES MRO",
        "DTCS Mission Module (AssuredReach SATCOM channel expansion for AN/PRC-163)": "DTCS Mission Module",
        "F-35 centre fuselage sections (Weeze) - Rheinmetall Aviation Services": "F-35 centre fuselage sections (Weeze)",
        "COBRA II - Mobile Satcom Vehicle": "COBRA II - Mobile Satcom Vehicle",                              # a variant keeps its variant name
        "Tandem Assault Crossing System (TACS)": "Tandem Assault Crossing System (TACS)",
        "DM42 IM (40 mm x 53 HE-DP-T)": "DM42 IM (40 mm x 53 HE-DP-T)",
        "155 mm Modular Charge System": "155 mm Modular Charge System",
        "ATAGS (Advanced Towed Artillery Gun System, 155mm/52 cal)": "ATAGS",                   # the acronym spelt out
        "M-71 (155mm/39 Towed Howitzer, Soltam)": "M-71",
    }
    for raw, want in names.items():
        got = display_name(raw, co)
        assert got == want, (raw, got, want)
    # family: the F-35 programme card is the umbrella of F-35A / B / C; a single derivative hides nothing
    prods = [{"id": "fam", "name": "F-35 Lightning II (F-35A / F-35B / F-35C)", "description": "Program/common-systems row for the F-35 family"},
             {"id": "a", "name": "F-35A Lightning II (conventional takeoff and landing, CTOL)"},
             {"id": "b", "name": "F-35B Lightning II (short takeoff / vertical landing, STOVL)"},
             {"id": "c", "name": "F-35C Lightning II (carrier variant, CV)"}, {"id": "x", "name": "F-35 TR-3 open-systems hardware", "category": "Other"}]
    for q in prods[:4]:
        q["category"] = "Aircraft & Aerostructures"
    u = umbrella_ids(prods, ["Lockheed Martin"])
    assert set(u) == {"fam"} and sorted(u["fam"]["variants"]) == ["a", "b", "c"], u
    u = umbrella_ids([{"id": "1", "name": "COBRA II"}, {"id": "2", "name": "COBRA II - Mobile Satcom Vehicle"}, {"id": "3", "name": "COBRA"},
                      {"id": "4", "name": "Altius-600"}, {"id": "5", "name": "Altius-600M"}])
    assert set(u) == {"1"}, u
    # descriptions: pipeline notes and citations go
    assert clean_description("Program/common-systems row for the F-35 family. Single-engine stealth fighter (Lockheed page).") == ["Single-engine stealth fighter."]
    print("spec_sheet self-check ok")


if __name__ == "__main__":
    _selftest()
