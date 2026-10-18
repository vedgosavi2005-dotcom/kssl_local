"""Plain-English checks (docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md A.0.3) and the small text helpers behind the key-point rules.

Pure functions, no DB. prompts/spec.py calls them for every column that carries a `plain:` rule, and for the table rules
`dedupe` (key points that restate the title / summary) and `count` (3-6 key points).

    lint(text, seen=None)  -> [Issue]        one text; `seen` = acronyms already met in the record (shared across its columns)
    reading_level(texts)   -> [Issue]        record-level proxy: average sentence <= 17 words, average word <= 5.3 letters
    drop_restatements(points, against)       the near-duplicate rule for key points

Severity. A finding is `hard` or soft. `plain: warn` (the default of a column that names the rule) turns every finding into a
warning. `plain: strict` rejects the value for the hard findings and still only warns for the soft ones:
    hard: a sentence over 32 words, a banned phrase (outside quotation marks), "<client> should"
    soft: a sentence over 20 words, an acronym used before it is explained, a statement of absence, the reading-level proxy
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

WARN_WORDS, HARD_WORDS = 20, 32
READING_SENTENCE, READING_WORD = 17.0, 5.3
CLIENT_NAMES = ("KSSL",)

# Fable A.0.3 whitelist, plus the ISO currency codes the sources use (chosen) and the client's own name
ACRONYMS_OK = {
    "ATAGS", "MARG", "DRDO", "MOD", "PIB", "DAC", "AON", "JV", "MOU", "RFI", "RFP", "RFQ", "UAV", "UAS", "UGV", "MRAP", "APC", "IFV",
    "MBT", "SAM", "ATGM", "MRL", "HE", "USD", "INR", "EUR", "GBP", "NATO", "STANAG", "TOT", "MRO",
    "UAE", "USA", "AED", "AUD", "CAD", "CHF", "CNY", "JPY", "KRW", "PLN", "SAR", "SEK", "NOK", "DKK", "TRY", "KSSL",
}

# (pattern, name). Matched outside quotation marks, case-insensitive.
BANNED = [
    (r"\bleverag(?:e|es|ed|ing)\b", "leverage"), (r"\bsynerg(?:y|ies|istic)\b", "synergy"), (r"\becosystems?\b", "ecosystem"),
    (r"\brobust\b", "robust"), (r"\bcutting[- ]edge\b", "cutting-edge"), (r"\bstate[- ]of[- ]the[- ]art\b", "state-of-the-art"),
    (r"\bgame[- ]chang(?:er|ers|ing)\b", "game-changer"), (r"\bgoing forward\b", "going forward"),
    (r"\bstrategic imperative\b", "strategic imperative"), (r"\bcapability enhancements?\b", "capability enhancement"),
    (r"\bend[- ]to[- ]end\b", "end-to-end"), (r"\bstrengthen(?:s|ed|ing)? (?:its|their|the company's) position\b", "strengthens its position"),
    (r"\bextend(?:s|ed|ing)? (?:its|their) footprint\b", "extends its footprint"), (r"\bpos(?:e|es|ed|ing) a threat to\b", "poses a threat to"),
    (r"\bpositions? (?:itself|themselves)\b", "positions itself"), (r"\bunprecedented\b", "unprecedented"),
]
# "no statement of absence as analysis": the shapes Fable quotes. The fixed sentence the rule allows is exempt (ABSENCE_OK).
ABSENCE = [
    r"\bno stated route\b", r"\bno direct overlap\b", r"\bno (?:direct|clear|obvious) (?:link|impact|relevance|competition)\b",
    r"\b(?:is|are) not (?:directly )?relevant to\b",
]
ABSENCE_OK = re.compile(r"\bno [\w ]{1,40}? product lines? (?:is|are) touched\b", re.I)

ABBREV = ("e.g.", "i.e.", "vs.", "approx.", "no.", "mr.", "mrs.", "dr.", "st.", "u.s.", "u.k.", "ltd.", "inc.", "co.", "corp.", "etc.", "cal.", "mm.", "km.")
QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”")
ACRONYM = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3,}(?![A-Za-z0-9])")
STOP = frozenset("a an the of to in on at for from by with and or but is are was were be been it its this that these those as than then "
                 "has have had will would can could may might also not no into over under after before about between per via".split())


@dataclass
class Issue:
    code: str            # sentence_long | sentence_too_long | banned | client_should | acronym | absence | reading_level
    message: str
    hard: bool = False

    def __str__(self) -> str:
        return self.message


# ---- sentences, words -----------------------------------------------------------------------------------------

def sentences(text: str) -> list[str]:
    """Split on . ! ? followed by a capital, digit or quote; and on line breaks. Abbreviations ("e.g.", "No.") and decimals do not split."""
    out: list[str] = []
    for block in re.split(r"\n+", text or ""):
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])", block.strip())
        cur = ""
        for p in parts:
            cur = f"{cur} {p}".strip() if cur else p
            if (cur.split() or [""])[-1].lower() in ABBREV:             # a whole word only: "East." is not "st."
                continue
            if cur:
                out.append(cur)
            cur = ""
        if cur:
            out.append(cur)
    return [s for s in out if re.search(r"\w", s)]


def words(s: str) -> list[str]:
    return [w for w in s.split() if re.search(r"[A-Za-z0-9]", w)]


def _unquoted(text: str) -> str:
    return QUOTED.sub(" ", text)


# ---- the lint -------------------------------------------------------------------------------------------------

def lint(text: str, seen: set | None = None, client_names: tuple = CLIENT_NAMES) -> list[Issue]:
    """Findings for one text. `seen` (a set the caller keeps per record) holds the acronyms already met, so the
    "explain it the first time" rule works across the columns of a record; it is updated here."""
    seen = seen if seen is not None else set()
    out: list[Issue] = []
    if not text or not text.strip():
        return out
    for s in sentences(text):
        n = len(words(s))
        if n > HARD_WORDS:
            out.append(Issue("sentence_too_long", f"sentence of {n} words (hard limit {HARD_WORDS}): \"{s[:70]}...\"", True))
        elif n > WARN_WORDS:
            out.append(Issue("sentence_long", f"sentence of {n} words (aim for {WARN_WORDS} or fewer): \"{s[:70]}...\""))
    free = _unquoted(text)                       # a quoted phrase is somebody else's word
    for rx, name in BANNED:
        if re.search(rx, free, re.I):
            out.append(Issue("banned", f"banned phrase '{name}'", True))
    for name in client_names:
        if re.search(rf"\b{re.escape(name)} should\b", free):
            out.append(Issue("client_should", f"'{name} should': recommendations belong in Next moves, not here", True))
    for rx in ABSENCE:
        m = re.search(rx, free, re.I)
        if m and not ABSENCE_OK.search(free):
            out.append(Issue("absence", f"statement of absence '{m.group(0)}': say what IS touched, or \"No <product> product line is touched; kept because <reason>\""))
            break
    ok = ACRONYMS_OK | {c.upper() for c in client_names}
    for m in ACRONYM.finditer(free):
        a = m.group(0)
        if a in seen:
            continue
        seen.add(a)
        if a in ok:
            continue
        before, after = free[max(0, m.start() - 1):m.start()], free[m.end():m.end() + 2]
        if (before == "(" and after.startswith(")")) or re.match(r"\s*\(", after):        # "(ABC)" after its words, or "ABC (what it is)"
            continue
        out.append(Issue("acronym", f"acronym {a} is used before it is explained (write \"{a} (what it is)\" the first time)"))
    return out


def reading_level(texts: list[str]) -> list[Issue]:
    """Warn-only proxy over a record's prose: average sentence <= 17 words and average word <= 5.3 letters."""
    sents = [s for t in texts for s in sentences(t)]
    ws = [re.sub(r"[^A-Za-z]", "", w) for s in sents for w in words(s)]
    ws = [w for w in ws if w]
    if len(sents) < 2 or len(ws) < 20:
        return []
    avg_s, avg_w = sum(len(words(s)) for s in sents) / len(sents), sum(map(len, ws)) / len(ws)
    out = []
    if avg_s > READING_SENTENCE:
        out.append(Issue("reading_level", f"reading level: sentences average {avg_s:.1f} words (aim for {READING_SENTENCE:g} or fewer)"))
    if avg_w > READING_WORD:
        out.append(Issue("reading_level", f"reading level: words average {avg_w:.1f} letters (aim for {READING_WORD:g} or fewer)"))
    return out


def judge(text: str, mode: str, seen: set | None = None, client_names: tuple = CLIENT_NAMES) -> tuple[list[str], str | None]:
    """(warnings, rejection reason or None) for one text under a `plain:` mode: off | warn | strict."""
    if mode in (None, False, "off"):
        return [], None
    issues = lint(text, seen, client_names)
    if mode == "strict":
        hard = [i for i in issues if i.hard]
        if hard:
            return [str(i) for i in issues if not i.hard], "plain English (strict): " + "; ".join(str(i) for i in hard)
    return [str(i) for i in issues], None


# ---- near-duplicate key points --------------------------------------------------------------------------------

def content_words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", (s or "").lower()) if w not in STOP and (len(w) > 2 or w.isdigit())}


def containment(point: str, reference: str) -> float:
    """Share of the point's content words that the reference already contains (0 for an empty point)."""
    p = content_words(point)
    return len(p & content_words(reference)) / len(p) if p else 0.0


def drop_restatements(points: list[str], against: list[str], threshold: float = 0.6) -> tuple[list[int], list[str]]:
    """Indexes of the points to keep, and a note for each dropped one. A point is dropped when more than `threshold` of its
    content words are found in the title or summary (`against`), or in a point kept before it (both ways, threshold 0.7)."""
    keep, notes = [], []
    for i, p in enumerate(points):
        hit = next((r for r in against if r and containment(p, r) > threshold), None)
        if hit is not None:
            notes.append(f"key point {i + 1} restates the title / summary and was dropped: \"{(p or '')[:60]}\"")
            continue
        twin = next((points[j] for j in keep if containment(p, points[j]) > 0.7 and containment(points[j], p) > 0.7), None)
        if twin is not None:
            notes.append(f"key point {i + 1} repeats an earlier key point and was dropped: \"{(p or '')[:60]}\"")
            continue
        keep.append(i)
    return keep, notes


# ---- self-check -----------------------------------------------------------------------------------------------

def _selftest() -> None:
    codes = lambda t, **k: sorted(i.code for i in lint(t, **k))
    # sentences: abbreviations and decimals do not split; line breaks do
    assert sentences("Range is 2.5 km, e.g. with base bleed. Next one.") == ["Range is 2.5 km, e.g. with base bleed.", "Next one."]
    assert sentences("No. 5 battery fired.\nSecond line") == ["No. 5 battery fired.", "Second line"]
    assert sentences("It sells in the Middle East. The K9 is the same class.") == ["It sells in the Middle East.", "The K9 is the same class."]     # "East." ends in "st."
    assert lint("") == [] and lint(None) == []
    # sentence length: 20 ok, 21 warn, 33 hard
    w = lambda n: " ".join(["Word"] * n) + "."
    assert codes(w(20)) == [] and codes(w(21)) == ["sentence_long"] and codes(w(32)) == ["sentence_long"] and codes(w(33)) == ["sentence_too_long"]
    assert codes(w(20) + " " + w(20)) == []                      # two short sentences are fine
    # banned phrases are hard, and exempt inside quotation marks
    assert codes("The deal gives a robust base.") == ["banned"] and lint("A robust base.")[0].hard
    assert codes('The minister called it "a game-changer" in the speech.') == []
    assert codes("It will leverage local assembly going forward.") == ["banned", "banned"]
    assert codes("The firm extends its footprint and poses a threat to rivals.") == ["banned", "banned"]
    # the client's own recommendation
    assert codes("KSSL should bid for this order.") == ["client_should"] and lint("KSSL should bid.")[0].hard
    assert codes("The order shows KSSL could bid.") == []
    # statements of absence (soft), with the fixed allowed sentence
    assert codes("KSSL has no stated route to adopt it.") == ["absence"] and not lint("There is no direct overlap exists here.")[0].hard
    assert codes("No artillery product line is touched; kept because of supply chain.") == []
    assert codes("The article gives no reason for the choice.") == []
    # acronyms: whitelist, first use, explained forms, once per record (shared `seen`)
    assert codes("The RFP names NATO and the MoD.") == []
    assert codes("The FOO order was placed.") == ["acronym"]
    seen: set = set()
    assert codes("The FOO order was placed.", seen=seen) == ["acronym"] and codes("The FOO order was repeated.", seen=seen) == []
    assert codes("The Forward Operating Office (FOO) placed it.") == [] and codes("The FOO (forward office) placed it.") == []
    assert codes("The firm is KSSL.", client_names=("KSSL",)) == [] and codes("Zorya is in the ZZZ plan.") == ["acronym"]
    # judge: modes
    assert judge("A robust deal.", "off") == ([], None)
    ws, rej = judge("A robust deal. " + w(25), "warn")
    assert rej is None and len(ws) == 2
    ws, rej = judge("A robust deal. " + w(25), "strict")
    assert rej and "robust" in rej and len(ws) == 1 and "25 words" in ws[0]
    assert judge(w(25), "strict")[1] is None                     # only soft findings: warn, never reject
    assert judge(w(40), "strict")[1] is not None
    # reading level (warn-only)
    short = "The firm won an order. It will build guns. Work starts in May. The buyer is the army. It paid cash for them."
    assert reading_level([short]) == []
    long_words = ("Notwithstanding considerable organisational uncertainty, procurement authorities announced comprehensive "
                  "modernisation programmes. Subsequently, manufacturers demonstrated extraordinary technological capabilities. ")
    assert {i.code for i in reading_level([long_words * 2])} == {"reading_level"} and reading_level(["Short."]) == []
    # near-duplicate key points
    title, summary = "Veland orders 24 NV-155 wheeled guns from Nordvik", "Veland's army signed for 24 NV-155 truck-mounted 155 mm guns, with deliveries from 2028."
    points = ["Veland orders 24 NV-155 guns from Nordvik.",                                # restates the title
              "The army signed for 24 truck-mounted guns with deliveries from 2028.",     # restates the summary
              "An option for 12 more guns can be taken until the end of 2029.",           # new facts
              "Final assembly takes place at Veland Motor Works, a ministry condition.",  # new facts
              "Final assembly is at Veland Motor Works, a condition of the ministry."]    # repeats the previous kept point
    keep, notes = drop_restatements(points, [title, summary])
    assert keep == [2, 3] and len(notes) == 3 and "title" in notes[0] and "earlier" in notes[2], (keep, notes)
    assert containment("", "x") == 0.0 and drop_restatements([], [title]) == ([], [])
    print("plain_english self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
