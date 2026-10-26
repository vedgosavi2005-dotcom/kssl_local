"""Handler of prompts/signal_rewrite.yml: the two prose fields of one signal's drawer (competitive_signal_detail).

    python -m prompts.signal_rewrite --selftest         pure checks, fictional values

Writes ONLY what_article_says and why_it_matters of the subject signal. A text is refused when it is empty, too long, fails the
strict plain-English check (prompts/plain_english.judge) or still uses an internal term the rewrite exists to remove; a refused text
leaves the stored one in place. The rows' fact_source entries (the article sentence, the reason) are kept: the facts did not change.
Same Result shape as prompts/spec_enrich.
"""

from __future__ import annotations

import re
import sys

from prompts.plain_english import judge
from prompts.spec_enrich import Result

FIELDS = ("what_article_says", "why_it_matters")
MAX = 900
JARGON = re.compile(r"country line|client line|sub-?type|like-for-like|\banchor\b|the article (?:does not )?says?\b|is touched|kept because"
                    r"|\b(?:threat|watch)\b", re.I)


def check(field: str, text: str) -> str | None:
    """None when the text may be stored, else why not."""
    t = " ".join(str(text or "").split())
    if not t:
        return "empty"
    if len(t) > MAX:
        return f"{len(t)} characters (max {MAX})"
    bad = JARGON.findall(t) if field == "why_it_matters" else [m for m in JARGON.findall(t) if m.lower() not in ("threat", "watch")]
    if bad:
        return f"internal term: {bad[0]!r}"
    return judge(t, "strict")[1]


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    res = Result()
    recs = [r.get("values") or {} for r in env.get("records") or [] if isinstance(r, dict)]
    if not recs:
        res.skip_reason = (env.get("skip_reason") or "no rewrite returned")[:300]
        return res
    vals = {}
    for f in FIELDS:
        why = check(f, recs[0].get(f))
        if why:
            res.warnings.append(f"{f} kept as stored: {why}")
        else:
            vals[f] = " ".join(str(recs[0][f]).split())
    if not vals:
        return res                                   # nothing usable: rejected, the stored text stays
    sid = str(subject["signal_id"])
    if not dry_run:
        cur.execute("UPDATE staging.competitive_signal_detail SET " + ", ".join(f"{f} = %s" for f in vals) + " WHERE signal_id = %s::uuid",
                    [*vals.values(), sid])
    res.loaded.append(("competitive_signal", sid, True))
    res.rows = 1
    res.details = {"written": sorted(vals)}
    res.note = "rewrote " + " + ".join(sorted(vals)) + (f" ({'; '.join(res.warnings)})" if res.warnings else "")
    return res


def _selftest() -> None:
    good = "Hanwha met about 70 U.S. parts makers in Washington this week to build a supply chain for its XM1776 howitzer."
    assert check("what_article_says", good) is None
    assert check("why_it_matters", "No gun product line is touched; kept because of reputation.").startswith("internal term")
    assert check("why_it_matters", "This is a threat to KSSL's gun sales in the United States.").startswith("internal term")
    assert check("what_article_says", "The Army called it a threat to its schedule.") is None    # a quoted word in the report is fine
    assert check("why_it_matters", "") == "empty" and check("why_it_matters", "x " * 600).startswith("1199")
    assert check("why_it_matters", "The deal gives Hanwha a robust base in the United States.").startswith("plain English")
    r = apply(None, {"signal_id": "x"}, {"records": [{"values": {"what_article_says": good, "why_it_matters": "kept because x"}}]}, dry_run=True)
    assert r.rows == 1 and r.details["written"] == ["what_article_says"] and r.warnings
    assert apply(None, {"signal_id": "x"}, {"records": [], "skip_reason": "paywall"}, dry_run=True).skip_reason == "paywall"
    print("signal_rewrite self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
