"""Spec value parsing and comparison, pure functions (no DB, no model). Used by prompts/matchup_code.py.

A spec value is parsed into a number (or a min..max range) and a unit only when that is unambiguous:
    '17.6 km'  '48'+unit 'km'  '6 rounds/min'  '16 t (army-technology)'  '1,000 hp'  '52 cal'  'L/52'
    '155 mm / 52 cal' (calibre, read as 155 mm)   '6 rounds in 30 s' (read as a rate)   '18-42 km' (range)
Anything else is NOT parsed and so never compared (its text is kept as stored):
    qualifiers ('over 40 km', '~38 km', 'up to 18 km/h', '<60 s', '40+ km'), several values in one string
    ('18 t (A); 16 t (B)', '2.5 min by day; 3 min at night'), unknown units, text.

Ranges: a range is kept as (lo, hi). For a 'higher is better' key the range is compared on its MAX (hi),
for a 'lower is better' key on its MIN (lo); for a neutral key (better none) on hi. The number stored in
the matchup row is the number compared, converted into the client's unit.

Units convert only inside one dimension by fixed factors (mm/cm/m/km/in/ft, g/kg/t/lb, m/s, km/h, mph,
knots, s/min/h, deg/mil, W/kW/hp, rounds per minute variants). 'gr' (grain or gram?), 'ton' (short/long/
metric?) and 'nm' (nanometre or nautical mile?) are deliberately not understood.

Self-check:  python -m prompts.spec_values
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal as D

# ---- unit tables: token -> (dimension, factor to the dimension's base unit) ----------------------------------

BASE = {"length": "mm", "mass": "g", "speed": "m/s", "time": "s", "angle": "deg", "power": "W", "rate": "rounds/min",
        "count": "", "ratio_pct": "%", "ratio_cal": "cal"}


def _table() -> dict:
    t: dict = {}

    def add(dim, factor, *names):
        for n in names:
            t[n] = (dim, D(factor) if not isinstance(factor, D) else factor)

    add("length", 1, "mm", "millimetre", "millimetres", "millimeter", "millimeters")
    add("length", 10, "cm", "centimetre", "centimetres", "centimeter", "centimeters")
    add("length", 1000, "m", "metre", "metres", "meter", "meters")
    add("length", 1000000, "km", "kilometre", "kilometres", "kilometer", "kilometers")
    add("length", D("25.4"), "in", "inch", "inches", '"')
    add("length", D("304.8"), "ft", "foot", "feet")
    add("length", D("914.4"), "yd", "yard", "yards")
    add("length", D("1609344"), "mi", "mile", "miles")
    add("length", D("1852000"), "nmi")
    add("mass", 1, "g", "gram", "grams")
    add("mass", 1000, "kg", "kgs", "kilogram", "kilograms", "kilogramme", "kilogrammes")
    add("mass", 1000000, "t", "tonne", "tonnes", "metric ton", "metric tons", "mt")
    add("mass", D("453.59237"), "lb", "lbs", "pound", "pounds")
    add("speed", 1, "m/s", "mps", "metres per second", "meters per second")
    kmh = D(1000) / D(3600)
    add("speed", kmh, "km/h", "kph", "kmph", "km/hr", "kmh", "kilometres per hour", "kilometers per hour")
    add("speed", D("0.44704"), "mph", "miles per hour")
    add("speed", D(1852) / D(3600), "kn", "kt", "kts", "knot", "knots")
    add("speed", D("0.3048"), "ft/s", "fps")
    add("time", 1, "s", "sec", "secs", "second", "seconds")
    add("time", D("0.001"), "ms")
    add("time", 60, "min", "mins", "minute", "minutes")
    add("time", 3600, "h", "hr", "hrs", "hour", "hours")
    add("time", 86400, "day", "days")
    add("time", 31557600, "yr", "yrs", "year", "years")
    add("angle", 1, "deg", "degree", "degrees", "°")
    add("angle", D("0.05625"), "mil", "mils")                      # NATO mil: 6400 per circle
    add("power", 1, "w", "watt", "watts")
    add("power", 1000, "kw", "kilowatt", "kilowatts")
    add("power", 1000000, "mw", "megawatt", "megawatts")
    add("power", D("745.69987158227022"), "hp", "bhp", "shp", "horsepower")
    add("power", D("735.49875"), "ps")
    add("rate", 1, "rounds/min", "rds/min", "rd/min", "rpm", "rounds per minute", "rounds per min", "rounds/minute",
        "rds/minute", "shots/min", "shots per minute", "rd/m", "r/min", "rounds min")
    add("rate", 60, "rounds/s", "rds/s", "rounds/sec", "rounds per second")
    add("rate", D(1) / D(60), "rounds/h", "rounds/hour", "rounds per hour", "rds/h")
    add("count", 1, "", "round", "rounds", "rd", "rds", "pcs", "pc", "nos", "no", "unit", "units", "person", "persons",
        "men", "crew", "pax", "piece", "pieces", "shots", "shot")
    add("ratio_pct", 1, "%", "percent", "per cent")
    add("ratio_cal", 1, "cal", "calibre", "calibres", "caliber", "calibers")
    return t


UNITS = _table()

NUM = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_QUALIFIER = re.compile(
    r"^\s*(?:over|more than|greater than|up to|upto|about|approx\.?|approximately|around|circa|c\.|nearly|almost|roughly|"
    r"min\.?|max\.?|minimum|maximum|at least|at most|under|below|above|less than|up|~|≈|>=?|<=?|≥|≤|±|from|typically|"
    r"nominal|est\.?|estimated)(?![a-z])", re.I)
_QUAL_ANYWHERE = re.compile(r"(?:^|\s)(?:or more|or less|and above|and below|max|min|approx|approximately|plus)\b|\d\s*\+(?:\s|$)|~|≈", re.I)
NOTE_BLOCK = {"max", "maximum", "min", "minimum", "and", "or", "to", "from", "up", "over", "per", "at", "approx", "typical",
              "loaded", "empty", "dry", "laden", "unladen", "combat", "gross", "net", "cruise", "cruising", "standard", "burst",
              "sustained", "initial", "effective", "extended", "range", "with", "without", "plus", "each", "per-"}
_APPROX = re.compile(r"^(?:~|≈|about|approx\.?|approximately|around|circa|c\.|nearly|almost|roughly|est\.?|estimated|typically)\s*", re.I)
_MIN = re.compile(r"^(?:over|more than|greater than|above|at least|exceeding|in excess of|>=|>|≥)\s*", re.I)
_MAX = re.compile(r"^(?:up to|upto|under|below|less than|at most|no more than|within|<=|<|≤)\s*", re.I)
_SUFFIX_MIN = re.compile(r"(?<=\d)\s*\+(?=\s|$)|\s+(?:or more|and above|and over)\b", re.I)
_SUFFIX_MAX = re.compile(r"\s+(?:or less|and below|and under)\b", re.I)
_QUAL_WORDS = re.compile(r"(?:^|\s)(?:max|min|maximum|minimum|approx|approximately|plus|typical|from|to\s*$)\b|~|≈|[<>≥≤]|\+/-|±", re.I)


def _split_qualifier(s: str):
    """(qual, rest): one leading or trailing qualifier is read off ('over 40 km' -> 'min', '40 km'); two of them, or a
    qualifier that is not followed by a plain value, give (None, None)."""
    qual = None
    for rx, q in ((_APPROX, "approx"), (_MIN, "min"), (_MAX, "max")):
        m = rx.match(s)
        if m:
            qual, s = q, s[m.end():].strip()
            break
    for rx, q in ((_SUFFIX_MIN, "min"), (_SUFFIX_MAX, "max")):
        if rx.search(s):
            if qual:
                return None, None
            qual, s = q, rx.sub("", s).strip()
    if qual and (_APPROX.match(s) or _MIN.match(s) or _MAX.match(s)):
        return None, None
    return qual, s


_DIGIT_UNIT = re.compile(r"\d\s*[a-zA-Z%°/]")
_PAREN = re.compile(r"\s*\([^()]*\)")


@dataclass(frozen=True)
class Parsed:
    lo: D                  # in `unit`
    hi: D
    unit: str              # normalised unit token ('' for a bare count)
    dim: str               # length | mass | speed | time | angle | power | rate | count | ratio_pct | ratio_cal | other:<unit>
    factor: D              # unit -> base unit of the dimension
    qual: str | None = None    # None (exact) | 'approx' (~X, about X) | 'min' (over X, X+, >= X: a lower bound) | 'max' (up to X, <= X: an upper bound)

    @property
    def is_range(self) -> bool:
        return self.lo != self.hi

    def pick(self, better: str) -> D:
        """The number compared: max of a range for 'higher' (and neutral), min for 'lower'."""
        return self.lo if better == "lower" else self.hi

    def to_unit(self, x: D, factor: D) -> D:
        """x (in this value's unit) expressed in a unit with the given factor."""
        return x * self.factor / factor


def _unit(token: str):
    t = " ".join(token.lower().replace(".", "").replace("µ", "u").split())
    t = re.sub(r"\s*/\s*", "/", t)
    return UNITS.get(t), t


def _num(s: str) -> D:
    return D(s.replace(",", ""))


def parse_value(text, unit_hint=None):
    """Parsed or None. `unit_hint` is the stored unit column; it applies only when the text names no unit."""
    if text is None:
        return None
    s = str(text).replace(" ", " ").replace("–", "-").replace("—", "-").replace("−", "-")
    s = re.sub(r"\s+at\s+[\d.]+\s*(?:deg|°|degrees?)\s*/\s*s(?:ec)?\b\.?", "", s, flags=re.I)    # '... at 5 deg/s': the slew rate, another quantity
    s = re.sub(r"(\d)\s*(?:deg|degrees?|°)\s*(to|-)\s*(?=[-+]?\d)", r"\1 \2 ", s, flags=re.I)    # '-2 deg to +73 deg' -> '-2 to +73 deg'
    s = re.sub(r"\b(\d+)\s*['′]\s*(\d{1,2})\s*[\"″]", lambda m: f"{int(m[1]) * 60 + int(m[2])} s", s)  # 1'30" -> 90 s
    s = s.replace("�", "").strip().strip("'` ").strip()
    if s.startswith('"'):
        s = s.lstrip('"').rstrip('"').strip()               # a trailing " after a figure is the inch sign: kept
    if not s or len(s) > 80:
        return None
    # parentheticals: a note ('(army-technology)', '(CN98)') is dropped; one that holds another figure is ambiguous
    outer = _PAREN.sub("", s).strip()
    for m in _PAREN.finditer(s):
        if _DIGIT_UNIT.search(m.group(0)):
            # '(215 lb)' after '97.5 kg' restates the same quantity in another unit: fine; any other figure is ambiguous
            a = parse_value(outer, unit_hint) if "(" not in outer else None
            b = parse_value(m.group(0).strip(" ()"), None)
            if not (a and b and a.dim == b.dim and not a.is_range and not b.is_range and b.unit
                    and abs(a.lo * a.factor - b.lo * b.factor) <= D("0.03") * max(abs(a.lo * a.factor), abs(b.lo * b.factor), D("1e-9"))):
                return None
    s = outer
    bare = re.sub(r"\s(?:or more|or less|and above|and over|and below|and under)\b", "", s.lower())     # qualifiers read below
    if not s or ";" in s or " or " in bare or " and " in bare or "," in re.sub(r"\d,\d{3}", "", s):
        return None
    qual, s = _split_qualifier(s)
    if s is None or _QUAL_WORDS.search(s):
        return None
    low = re.sub(r"(\d)\s*-\s*(cal)", r"\1 \2", s.lower())        # 52-cal -> 52 cal
    # 'L/52' and '52 cal' / '52-cal' / '52 calibres'
    m = re.fullmatch(r"l\s*/\s*(\d+(?:\.\d+)?)", low)
    if m:
        v = D(m.group(1))
        return Parsed(v, v, "cal", "ratio_cal", D(1), qual)
    # '155 mm / 52 cal' (calibre and barrel length in one string): the calibre
    m = re.fullmatch(rf"({NUM})\s*mm\s*/\s*\d+(?:\.\d+)?\s*-?\s*cal(?:ibres?|ibers?)?", low)
    if m:
        v = _num(m.group(1))
        return Parsed(v, v, "mm", "length", D(1), qual)
    # '6 rounds in 30 s' / '3 rounds in 15 seconds' -> a rate
    m = re.fullmatch(rf"({NUM})\s*(?:rounds?|rds?|shots?)\s+in\s+({NUM})\s*([a-z]+)", low)
    if m:
        u, _ = _unit(m.group(3))
        if u is None or u[0] != "time" or _num(m.group(2)) == 0:
            return None
        per_min = _num(m.group(1)) / (_num(m.group(2)) * u[1] / D(60))
        return Parsed(per_min, per_min, "rounds/min", "rate", D(1), qual)
    # number or range, then an optional unit
    m = re.fullmatch(rf"({NUM})(?:\s*(?:-|to)\s*({NUM}))?\s*(.*)", low)
    if not m:
        return None
    a = _num(m.group(1))
    b = _num(m.group(2)) if m.group(2) is not None else a
    if b < a:
        return None
    if qual in ("min", "max") and a != b:                     # 'up to 18-20 km' is not a bound
        return None
    tail = m.group(3).strip()
    if tail:
        words = tail.split()
        for k in range(min(len(words), 3), 0, -1):                 # unit, then at most 3 plain words ('t depending on configuration')
            u, tok = _unit(" ".join(words[:k]))
            rest = words[k:]
            if u is not None and len(rest) <= 3 and all(re.fullmatch(r"[a-z-]+", w) and w not in NOTE_BLOCK for w in rest):
                return Parsed(a, b, tok, u[0], u[1], qual)
        return None
    if unit_hint:
        u, tok = _unit(str(unit_hint))
        if u is not None:
            return Parsed(a, b, tok, u[0], u[1], qual)
        return None                                     # a stored unit this module does not understand
    return Parsed(a, b, "", "count", D(1), qual)


FAMILY_DIMS = {"length": {"length"}, "mass": {"mass"}, "speed": {"speed"}, "time": {"time"}, "count": {"count"},
               "rate": {"rate"}, "angle": {"angle"}, "power": {"power"}, "ratio": {"ratio_pct", "ratio_cal"}}


def family_ok(family: str, p: Parsed) -> bool:
    return p.dim in FAMILY_DIMS.get(family, ())


@dataclass(frozen=True)
class Verdict:
    client_num: D          # compared numbers, both in the client's unit (for a bound: the bound itself)
    competitor_num: D
    unit: str              # the client's unit
    side: str | None       # client | competitor | equal | None (neutral key, or a bound that does not decide)
    gap: D | None
    note: str | None = None    # 'approximate value' / 'bound: ...': shown in the fact_source quote of the row
    decided: bool = True       # False: a bound is involved and does not decide the comparison -> not comparable


def _interval(p: Parsed, x: D):
    return (x, None) if p.qual == "min" else ((None, x) if p.qual == "max" else (x, x))


def compare_values(client: Parsed, competitor: Parsed, family: str, better: str, band: float = 3.0):
    """None when the two cannot be compared (family mismatch, different dimension). Otherwise a Verdict; side is None for a neutral
    key (better 'none'). Qualified values: '~X' / 'about X' compare as X (note 'approximate value'); 'over X' / 'X+' (lower bound) and
    'up to X' (upper bound) compare only when the bound decides it ('over 40 km' beats 30 km, says nothing against 45 km)."""
    from prompts import derive
    if not (family_ok(family, client) and family_ok(family, competitor)) or client.dim != competitor.dim:
        return None
    if family == "angle" and (client.is_range or competitor.is_range):
        # an arc ('-3 to +72 deg') is compared by its total span; an arc against a single angle is not like for like
        if not (client.is_range and competitor.is_range):
            return None
        span = lambda p: Parsed(p.hi - p.lo, p.hi - p.lo, p.unit, p.dim, p.factor, p.qual)
        v = compare_values(span(client), span(competitor), family, better, band)
        return v and Verdict(v.client_num, v.competitor_num, v.unit, v.side, v.gap, "; ".join(x for x in (v.note, "compared as the total arc") if x), v.decided)
    cn = client.pick(better)
    kn = competitor.to_unit(competitor.pick(better), client.factor)
    gap = derive.gap_value(cn, kn)
    small = gap is not None and gap < D(str(band))
    notes = ["approximate value"] if "approx" in (client.qual, competitor.qual) else []
    bounded = [(w, p) for w, p in (("client", client), ("competitor", competitor)) if p.qual in ("min", "max")]
    if not bounded:
        side = None
        if better in ("higher", "lower"):
            if cn == kn or small:
                side = "equal"
            elif better == "higher":
                side = "client" if cn > kn else "competitor"
            else:
                side = "client" if cn < kn else "competitor"
        return Verdict(cn, kn, client.unit, side, gap, "; ".join(notes) or None)
    desc = "; ".join(f"{w} value is a {'lower' if p.qual == 'min' else 'upper'} bound" for w, p in bounded)
    if better not in ("higher", "lower"):
        return Verdict(cn, kn, client.unit, None, None, "; ".join(notes + [desc]))
    (clo, chi), (klo, khi) = _interval(client, cn), _interval(competitor, kn)
    if better == "higher":
        c_wins = clo is not None and khi is not None and clo > khi
        k_wins = klo is not None and chi is not None and klo > chi
    else:
        c_wins = chi is not None and klo is not None and chi < klo
        k_wins = khi is not None and clo is not None and khi < clo
    if (c_wins or k_wins) and not small:
        return Verdict(cn, kn, client.unit, "client" if c_wins else "competitor", gap, "; ".join(notes + [desc + " and it decides the comparison"]))
    return Verdict(cn, kn, client.unit, None, None, "; ".join(notes + [desc + "; the bound does not decide the comparison"]), decided=False)


_SPLIT = re.compile(r";\s*|,\s+(?=(?:~|about |approx\.? |over |up to )?[-+]?\d)")
_COND_PAREN = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")
_COND_WORD = re.compile(r"^(.*?\d[^a-zA-Z]*[a-zA-Z/%\u00b0\"]*)\s+(?:with|using|for|by|on|at)\s+(.+)$", re.I)


def parse_multi(text, unit_hint=None):
    """Several values in one cell, each possibly followed by its condition: '30 km (HE), 40 km (ERFB-BB)' or
    '80 km/h (KSSL page); 60 km/h (Janes)'. Returns [(condition or '', Parsed, segment text)] when there are at least two segments
    and every one is a plain or approximate value of the same dimension; otherwise None."""
    if text is None or len(str(text)) > 400:
        return None
    parts = [x.strip(" .") for x in _SPLIT.split(str(text).replace("\u2013", "-")) if x and x.strip(" .")]
    if len(parts) < 2 or len(parts) > 8:
        return None
    out = []
    for part in parts:
        cond = ""
        m = _COND_PAREN.match(part)
        if m and m.group(1).strip():
            val, cond = m.group(1), m.group(2)
        else:
            m = _COND_WORD.match(part)
            val, cond = (m.group(1), m.group(2)) if m else (part, "")
        p = parse_value(val, unit_hint)
        if p is None or p.qual in ("min", "max"):
            return None
        out.append((cond.strip(), p, part))
    if len({p.dim for _, p, _ in out}) != 1:
        return None
    return out


# ---- self-check ---------------------------------------------------------------------------------------------

def _selftest() -> None:
    assert parse_value("-2 deg to +73 deg").lo == -2 and parse_value("-3 to +72 deg at 5 deg/s").hi == 72
    assert parse_value("less than 1'30\"").lo == 90 and parse_value("less than 1'30\"").qual == "max"
    arc = compare_values(parse_value("-3 to +72 deg"), parse_value("-2 to +73 deg"), "angle", "higher")
    assert arc.side == "equal" and "total arc" in arc.note and compare_values(parse_value("-3 to 72 deg"), parse_value("34 deg"), "angle", "higher") is None
    def p(t, u=None):
        r = parse_value(t, u)
        return None if r is None else (r.lo, r.hi, r.unit, r.dim)

    # plain figures and units
    assert p("17.6 km") == (D("17.6"), D("17.6"), "km", "length")
    assert p("48", "km") == (D(48), D(48), "km", "length")
    assert p("6 rounds/min") == (D(6), D(6), "rounds/min", "rate")
    assert p("16 t") == (D(16), D(16), "t", "mass")
    assert p("1,000 hp") == (D(1000), D(1000), "hp", "power")
    assert p("52 cal") == (D(52), D(52), "cal", "ratio_cal")
    assert p("L/52") == (D(52), D(52), "cal", "ratio_cal")
    assert p("52-cal") == (D(52), D(52), "cal", "ratio_cal")
    assert p("46.3 t (army-technology)") == (D("46.3"), D("46.3"), "t", "mass")
    assert p("155 mm / 52-cal (CN98)") == (D(155), D(155), "mm", "length")
    assert p("155 mm / 52 cal") == (D(155), D(155), "mm", "length")
    assert p("3 rounds in 15 s") == (D(12), D(12), "rounds/min", "rate")
    assert p("6 rounds in 30 seconds")[:2] == (D(12), D(12))
    assert p("32-34 t depending on configuration") == (D(32), D(34), "t", "mass")
    assert p("40 mm smoothbore") == (D(40), D(40), "mm", "length")
    assert p("97.5 kg (215 lb)") == (D("97.5"), D("97.5"), "kg", "mass")
    assert p("52.5 in (133.4 cm)") == (D("52.5"), D("52.5"), "in", "length")
    assert p('0.22"') == (D("0.22"), D("0.22"), '"', "length")
    assert p("12", None) == (D(12), D(12), "", "count")
    assert p("6 to 8") == (D(6), D(8), "", "count")
    assert p("18-42 km") == (D(18), D(42), "km", "length")
    assert p("18–42 km") == (D(18), D(42), "km", "length")
    assert p("5 m", "km") == (D(5), D(5), "m", "length")                  # the text's unit wins over the hint
    # refused: qualifiers, several values, unknown units, text
    for bad in ("over 40 km 3", "up to 18-20 km", "~ ~38 km", "max 40 km", "from 5 km", "over", "up to Zone 7", "40 + 5 km",
                "18 t (Army 2024); 16 t (Other 2016)", "2.5 min by day; 3 min at night", "12 m L / 3.4 m W / 3.5 m H",
                "diesel", "", None, "200 m max", "30 t loaded", "5 km at 3 km", "10 gr", "5 ton", "97.5 kg (300 lb)", "5 km (8 km)", "7 widgets", "46 t (40000 kg)", "8 - 4 km", "1 or 2"):
        assert p(bad) is None, bad
    assert p("5", "widgets") is None
    # qualifiers
    q = lambda t, u=None: (lambda r: None if r is None else (r.hi, r.unit, r.qual))(parse_value(t, u))
    assert q("over 40 km") == (D(40), "km", "min") and q("more than 40") == (D(40), "", "min") and q("more than 40", "km") == (D(40), "km", "min")
    assert q("40+ km") == (D(40), "km", "min") and q("40 km or more") == (D(40), "km", "min") and q(">= 5 kg") == (D(5), "kg", "min")
    assert q("up to 18 km/h") == (D(18), "km/h", "max") and q("<60 s") == (D(60), "s", "max") and q("within 60 s") == (D(60), "s", "max")
    assert q("~38 km") == (D(38), "km", "approx") and q("approx. 12 t") == (D(12), "t", "approx") and q("about 3.5 t") == (D("3.5"), "t", "approx")
    assert q("~30-40 km") == (D(40), "km", "approx")
    # several values in one cell
    pm = parse_multi("30 km (HE), 40 km (ERFB-BB)")
    assert [(c, x.hi) for c, x, _ in pm] == [("HE", D(30)), ("ERFB-BB", D(40))], pm
    pm = parse_multi("80 km/h (KSSL page); 60 km/h (Janes, citing TASL)")
    assert [x.hi for _, x, _ in pm] == [D(80), D(60)] and pm[1][0].startswith("Janes")
    pm = parse_multi("18 km with M107 HE, 30 km with RAP")
    assert [(c, x.hi) for c, x, _ in pm] == [("M107 HE", D(18)), ("RAP", D(30))]
    assert parse_multi("30 km") is None and parse_multi("30 km; diesel") is None and parse_multi("30 km; 5 kg") is None
    assert parse_multi("over 40 km; 30 km") is None
    assert parse_multi("1,000 hp") is None
    # comparison
    a, b = parse_value("16 t"), parse_value("46300", "kg")
    r = compare_values(a, b, "mass", "lower")
    assert r.side == "client" and r.unit == "t" and r.competitor_num == D("46.3") and r.client_num == D(16)
    assert r.gap == D("97.27"), r.gap
    r = compare_values(parse_value("48", "km"), parse_value("40000 m"), "length", "higher")
    assert r.side == "client" and r.competitor_num == D(40) and r.gap == D("18.18")
    r = compare_values(parse_value("30-40 km"), parse_value("35 km"), "length", "higher")      # range -> max 40 vs 35
    assert r.client_num == D(40) and r.side == "client"
    r = compare_values(parse_value("30-40 km"), parse_value("35 km"), "length", "lower")       # range -> min 30 vs 35
    assert r.client_num == D(30) and r.side == "client"
    r = compare_values(parse_value("100 km/h"), parse_value("62 mph"), "speed", "higher")      # 62 mph = 99.78 km/h -> equal (<3 %)
    assert r.side == "equal", r
    r = compare_values(parse_value("155 mm"), parse_value("155 mm"), "length", "none")
    assert r.side is None and r.gap == D("0.00")
    assert compare_values(parse_value("10 km"), parse_value("10 kg"), "length", "higher") is None   # other side not a length
    assert compare_values(parse_value("10 km"), parse_value("10 m"), "mass", "higher") is None      # family says mass
    assert compare_values(parse_value("52 cal"), parse_value("155 mm"), "ratio", "none") is None
    assert compare_values(parse_value("4"), parse_value("6 to 8"), "count", "none").side is None
    # bounds: 'over 40 km' beats 30 km, says nothing against 45 km; 'up to X' only decides against a better exact value
    r = compare_values(parse_value("over 40 km"), parse_value("30 km"), "length", "higher")
    assert r.side == "client" and r.decided and "lower bound" in r.note and r.client_num == D(40)
    r = compare_values(parse_value("over 40 km"), parse_value("45 km"), "length", "higher")
    assert r.side is None and not r.decided and r.gap is None
    r = compare_values(parse_value("30 km"), parse_value("over 40 km"), "length", "higher")
    assert r.side == "competitor" and r.decided
    r = compare_values(parse_value("up to 25 km"), parse_value("30 km"), "length", "higher")
    assert r.side == "competitor" and "upper bound" in r.note
    r = compare_values(parse_value("up to 35 km"), parse_value("30 km"), "length", "higher")
    assert not r.decided
    r = compare_values(parse_value("up to 25 s"), parse_value("30 s"), "time", "lower")          # lower is better: <= 25 beats 30
    assert r.side == "client" and r.decided
    r = compare_values(parse_value("over 40 s"), parse_value("30 s"), "time", "lower")           # >= 40 is worse than 30
    assert r.side == "competitor"
    r = compare_values(parse_value("over 40 km"), parse_value("up to 35 km"), "length", "higher")  # the two bounds do not overlap
    assert r.side == "client"
    r = compare_values(parse_value("over 40 km"), parse_value("over 30 km"), "length", "higher")
    assert not r.decided
    r = compare_values(parse_value("over 40 km"), parse_value("30 km"), "length", "none")
    assert r.side is None and r.decided
    r = compare_values(parse_value("over 40 km"), parse_value("39 km"), "length", "higher")        # the bound decides, but the gap is < 3 %
    assert not r.decided
    r = compare_values(parse_value("~38 km"), parse_value("30 km"), "length", "higher")
    assert r.side == "client" and r.note == "approximate value" and r.gap == D("23.53")
    print("spec_values selftest ok")


if __name__ == "__main__":
    _selftest()
