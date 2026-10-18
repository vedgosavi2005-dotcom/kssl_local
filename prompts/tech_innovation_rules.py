"""Innovation rules of the technology pillar (derive hooks `innovation_gate`, `innovation_stance`; pure functions self-checked below).

    product_gate   a candidate whose title carries a KSSL or competitor product name is "a product, not a technology" and is deleted (A.3.2)
    stance_for     the model proposes watch / partner / license / develop / ignore; the rule allows only what the facts support

    python -m prompts.tech_innovation_rules --selftest
"""

from __future__ import annotations

import re
import sys

from prompts.derive import _row, hook, ids

CALIBRE = re.compile(r"\d+(mm|cal|km|kg|kw|mw|t|m|in)?\Z", re.I)
GENERIC_UPPER = {"heat", "hesh", "apfsds", "nato", "ammo", "atgm", "manpads", "c4isr", "unmanned", "radar", "lidar", "lasers"}
STANCES = ("watch", "partner", "license", "develop", "ignore")


def designations(product_name: str) -> set:
    """The tokens of a product name that identify it (not describe it): letters mixed with digits (XM1776, K9MH, M4A1; kept lower-case,
    matched in any case) or a word of 4+ letters with two or more capitals (ATAGS, MArG; kept as written and matched only in that exact
    case, so 'Linked' in a title never matches 'LINKED' in a catalogue name). Calibre and unit tokens (155mm, 52cal) never count."""
    out = set()
    letters = [c for c in (product_name or "") if c.isalpha()]
    shouting = bool(letters) and sum(c.isupper() for c in letters) / len(letters) >= 0.9     # an all-capitals catalogue name has no designation words
    for tok in re.findall(r"[A-Za-z0-9]+", product_name or ""):
        if len(tok) < 4 or CALIBRE.match(tok) or tok.casefold() in GENERIC_UPPER:
            continue
        has_d = any(c.isdigit() for c in tok)
        caps = sum(c.isupper() for c in tok)
        if has_d and any(c.isalpha() for c in tok):
            if not re.fullmatch(r"\d+[a-z]{1,3}", tok, re.I):
                out.add(tok.casefold())
        elif not shouting and caps >= 2 and (not tok.isupper() or len(tok) <= 6):
            out.add(tok)
    return out


def product_gate(title: str, product_names: list, desig: dict | None = None):
    """The product name a candidate title carries (a whole name of 8+ characters, or one designation token), else None.
    `desig` = {designation token: product name}, built once by `designation_index`."""
    t = (title or "").casefold()
    for name in product_names:
        n = (name or "").casefold().strip()
        if len(n) >= 8 and n in t:
            return name
    if desig is None:
        desig = designation_index(product_names)
    for tok in re.findall(r"[A-Za-z0-9]+", title or ""):
        if tok in desig:
            return desig[tok]
        if tok.casefold() in desig and any(c.isdigit() for c in tok):
            return desig[tok.casefold()]
    return None


MAX_DF = 3        # a token found in more than this many product names is a word of the trade (DRDO, FUZE, SHELL), not a designation


def designation_index(product_names: list) -> dict:
    """{designation token: first product name carrying it}, leaving out tokens that occur in more than MAX_DF product names."""
    df, first = {}, {}
    uniq = list(dict.fromkeys(n for n in product_names if n))
    for name in uniq:
        for t in set(re.findall(r"[A-Za-z0-9]+", name)):                  # document frequency over every word of every name (as written and lower-case)
            df[t] = df.get(t, 0) + 1
            df[t.casefold()] = df.get(t.casefold(), 0) + 1
        for d in designations(name):
            first.setdefault(d, name)
    return {d: n for d, n in first.items() if df.get(d, 0) <= MAX_DF}


def score_or_none(v):
    try:
        i = int(float(v))
    except (TypeError, ValueError):
        return None
    return i if 1 <= i <= 5 else None


def stance_for(stance, client_position, relevance, developer_is_competitor) -> tuple:
    """(stance, note). develop only when KSSL is behind and relevance >= 4; partner / license only when the developer is not a competitor;
    ignore only when relevance <= 2; anything else is watch (also a missing or unknown stance)."""
    s = str(stance or "").strip().lower()
    pos, rel = str(client_position or "").strip().lower(), score_or_none(relevance)
    if s not in STANCES:
        return "watch", "no valid stance given: watch"
    if s == "develop" and not (pos == "behind" and rel is not None and rel >= 4):
        return "watch", "develop needs KSSL behind and relevance 4 or more: watch"
    if s in ("partner", "license") and developer_is_competitor:
        return "watch", f"{s} is not allowed when the developer is a competitor: watch"
    if s == "ignore" and not (rel is not None and rel <= 2):
        return "watch", "ignore needs relevance 2 or less: watch"
    return s, ""


def delete_innovation(cur, iid) -> None:
    cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'technology_innovation' AND row_id = %s", (str(iid),))
    for t in ("technology_innovation_source", "technology_innovation_company", "technology_innovation_status",
              "technology_innovation_analysis", "technology_innovation_milestone"):
        cur.execute(f"DELETE FROM staging.{t} WHERE innovation_id = %s", (iid,))
    cur.execute("DELETE FROM staging.technology_innovation WHERE innovation_id = %s", (iid,))


@hook("innovation_gate")
def innovation_gate_hook(cur, ctx: dict) -> None:
    """Delete this run's candidates that are products (title carries a KSSL or competitor product name) or have no source row."""
    cur.execute("SELECT product_name FROM staging.client_product WHERE product_name IS NOT NULL UNION SELECT product_name FROM staging.competitive_product WHERE product_name IS NOT NULL")
    names = [r["product_name"] for r in cur.fetchall()]
    idx = designation_index(names)
    for iid in ids(ctx, "technology_innovation"):
        r = _row(cur, "technology_innovation", "innovation_id", iid)
        if r is None or r.get("status") != "candidate":
            continue
        hit = product_gate(r.get("title"), names, idx)
        cur.execute("SELECT count(*) AS n FROM staging.technology_innovation_source WHERE innovation_id = %s", (r["innovation_id"],))
        if hit or not cur.fetchone()["n"]:
            delete_innovation(cur, r["innovation_id"])
            ctx["notes"].append(f"innovation_gate: dropped '{r.get('title')}': " + (f"a product, not a technology (carries '{hit}')" if hit else "no source"))
            ctx["cards"] = [(t, i) for t, i in ctx.get("cards", []) if not (t == "technology_innovation" and str(i) == str(iid))]
            ctx["rows"] = [x for x in ctx.get("rows", []) if not (x[0] == "technology_innovation" and str(x[1]) == str(iid))]


@hook("innovation_stance")
def innovation_stance_hook(cur, ctx: dict) -> None:
    """technology_innovation.stance = stance_for(model stance, client_position, transient relevance, developer type). A change made by the
    rule is added to fact_source as a judgement-tier note beside the model's own reason."""
    tr = ctx.get("transient", {})
    for iid in ids(ctx, "technology_innovation"):
        r = _row(cur, "technology_innovation", "innovation_id", iid)
        if r is None:
            continue
        cur.execute("""SELECT bool_or(c.relationship_type = 'competitor' OR EXISTS (SELECT 1 FROM staging.competitive_competitor k
                          WHERE lower(k.display_name) = lower(c.display_name) OR lower(k.short_name) = lower(c.display_name))) AS comp
                       FROM staging.technology_innovation_company c WHERE c.innovation_id = %s AND c.relationship_type IN ('driver', 'competitor')""",
                    (r["innovation_id"],))
        comp = bool((cur.fetchone() or {}).get("comp"))
        rel = (tr.get(("technology_innovation", str(iid))) or {}).get("relevance")
        pos = r.get("client_position") or "unknown"
        st, note = stance_for(r.get("stance"), pos, rel, comp)
        cur.execute("UPDATE staging.technology_innovation SET stance = %s, client_position = %s WHERE innovation_id = %s", (st, pos, r["innovation_id"]))
        if note:
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
                           VALUES ('technology_innovation', %s, 'stance', 'judgement', 'judgement', NULL, %s, now())""", (str(r["innovation_id"]), "Rule: " + note))
            ctx["notes"].append(f"innovation_stance: {iid}: {r.get('stance')} -> {st} ({note})")


def selftest() -> None:
    names = ["ATAGS 155 mm/52 cal Advanced Towed Artillery Gun System", "MArG 155 mm/52 cal Mounted Gun System", "XM1776 Mobile Tactical Cannon", "Zeta-155 Gun"]
    assert designations("XM1776 Mobile Tactical Cannon") == {"xm1776"} and designations("MArG 155 mm/52 cal Mounted Gun System") == {"MArG"}
    assert designations("SA 7.62 x 51 MM LINKED AMMUNITION") == set() and product_gate("Drone linked to a fire direction system", ["SA 7.62 x 51 MM LINKED AMMUNITION"]) is None
    assert designations("SHELL 105 MM SMOKE") == set() and designations("CHARGE M4A2 (155 MM HOWITZER)") == {"m4a2"}
    assert "ATAGS" in designations(names[0]) and "155mm" not in designations("155mm Gun")
    assert product_gate("Hanwha XM1776 wheeled howitzer for the US Army", names) == "XM1776 Mobile Tactical Cannon"
    assert product_gate("ATAGS towed howitzer order", names) == names[0] and product_gate("Zeta-155 Gun upgrade", names) == "Zeta-155 Gun"
    assert product_gate("Ramjet-assisted 155 mm artillery shell (Nammo)", names) is None and product_gate("Additive-manufactured gun barrel liner", names) is None
    assert stance_for("develop", "behind", 4, False) == ("develop", "") and stance_for("develop", "unknown", 5, False)[0] == "watch"
    assert stance_for("partner", "behind", 4, True)[0] == "watch" and stance_for("license", "ahead", 3, False) == ("license", "")
    assert stance_for("ignore", "ahead", 2, False) == ("ignore", "") and stance_for("ignore", "ahead", 4, False)[0] == "watch"
    assert stance_for(None, "behind", 5, False)[0] == "watch" and stance_for("develop", "behind", None, False)[0] == "watch"
    assert stance_for("Partner", "unknown", "3", False) == ("partner", "")
    print("tech_innovation_rules self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        print(__doc__)
