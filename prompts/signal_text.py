"""Signal text tidy (functional test G1, 2026-10-25): code only, no model.

    python -m prompts.signal_text --selftest            pure rules
    python -m prompts.signal_text [--apply]             one-off repair of the stored signals (dry run without --apply;
                                                        kssl_staging / kssl_test_* only, one transaction)

Two rules, also applied to every new signal by the derive hook `signal_text_tidy` (prompts/derive.py, signal.yml):
  * a drawer headline must be finished: one that ends on a dangling word ("... in the programme KSSL and AM General bid for")
    is replaced by the card's own stored title (the source headline), and drawer_title gets the title's sources.
  * number and unit are written apart: "155mm" -> "155 mm", "2,000km" -> "2,000 km", "70kg" -> "70 kg" (the house style the
    other 211 values already follow). Never inside a product name (the maker's spelling: "105mm K274 APFSDS-T"), a quoted
    passage ("..." / “...”) or a link; the evidence `quote` column (the article's own words) is never touched.
"""

from __future__ import annotations

import re
import sys

DANGLING = re.compile(r"(?:^|\s)(?:for|to|of|with|in|on|by|and|or|the|a|an|at|from|as|into|over|under|against|than|that)\s*[.,:;]?\s*\Z", re.I)
UNIT_GLUED = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)*(?:x\d+(?:[.,]\d+)*)?)(mm|km|kg)\b")
SKIP = re.compile(r"https?://\S+|“[^”]*”|\"[^\"]*\"")

# the stored text columns a signal shows (card + drawer); evidence `quote` is the article's own words and is left alone
COLUMNS = {
    "competitive_signal": ("signal_id", ("title", "summary")),
    "competitive_signal_detail": ("signal_id", ("drawer_title", "what_article_says", "why_it_matters", "glance_who", "glance_move",
                                                "glance_where", "glance_impact", "glance_third_party", "glance_when", "impact_eyebrow")),
    "competitive_signal_evidence": ("evidence_id", ("label", "value")),
}


def finished(drawer, title):
    """The drawer headline, or the card's title when the drawer headline stops on a dangling word (or is empty)."""
    d = " ".join(str(drawer or "").split())
    if d and not DANGLING.search(d):
        return drawer
    return title if str(title or "").strip() else drawer


def product_guard(names) -> re.Pattern | None:
    """A pattern matching any product name that writes a number and unit together (longest first, case-insensitive)."""
    names = sorted({n.strip() for n in names if n and UNIT_GLUED.search(n)}, key=len, reverse=True)
    return re.compile("|".join(re.escape(n) for n in names), re.I) if names else None


def unit_space(text, guard: re.Pattern | None = None):
    """'155mm' -> '155 mm' outside product names, quoted passages and links. None stays None."""
    if not text:
        return text
    s = str(text)
    keep = [m.span() for m in SKIP.finditer(s)] + ([m.span() for m in guard.finditer(s)] if guard else [])

    def fix(m):
        return m.group(0) if any(a <= m.start() < b for a, b in keep) else f"{m.group(1)} {m.group(2)}"
    return UNIT_GLUED.sub(fix, s)


def load_guard(cur) -> re.Pattern | None:
    cur.execute("SELECT product_name AS n FROM staging.competitive_product UNION SELECT product_name FROM staging.client_product")
    return product_guard([r["n"] if isinstance(r, dict) else r[0] for r in cur.fetchall()])


def tidy_signals(cur, signal_ids=None, guard=None) -> dict:
    """Apply both rules to the given signals (None = all). Returns {column: rows changed} and the drawer titles replaced."""
    guard = guard if guard is not None else load_guard(cur)
    only = [str(s) for s in signal_ids] if signal_ids is not None else None
    n: dict = {}
    replaced = []
    # 1 finished drawer headlines
    cur.execute("SELECT d.signal_id::text AS sid, d.drawer_title, s.title FROM staging.competitive_signal_detail d "
                "JOIN staging.competitive_signal s ON s.signal_id = d.signal_id" + (" WHERE d.signal_id::text = ANY(%s)" if only is not None else ""),
                (only,) if only is not None else None)
    for r in cur.fetchall():
        new = finished(r["drawer_title"], r["title"])
        if new != r["drawer_title"]:
            cur.execute("UPDATE staging.competitive_signal_detail SET drawer_title = %s WHERE signal_id::text = %s", (new, r["sid"]))
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_signal_detail' AND row_id = %s AND column_name = 'drawer_title'",
                        (r["sid"],))
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, document_id, retrieved_at)
                           SELECT 'competitive_signal_detail', row_id, 'drawer_title', source_url, source_tier, publisher, quote, document_id, now()
                           FROM staging.fact_source WHERE table_name = 'competitive_signal' AND row_id = %s AND column_name = 'title'""", (r["sid"],))
            replaced.append((r["sid"], r["drawer_title"], new))
    # 2 number + unit spacing
    for table, (key, cols) in COLUMNS.items():
        where = ""
        args = None
        if only is not None:
            where = " WHERE signal_id::text = ANY(%s)"
            args = (only,)
        cur.execute(f"SELECT {key}::text AS k, {', '.join(cols)} FROM staging.{table}{where}", args)
        for r in cur.fetchall():
            sets = {c: unit_space(r[c], guard) for c in cols if r[c] and unit_space(r[c], guard) != r[c]}
            if sets:
                cur.execute(f"UPDATE staging.{table} SET {', '.join(c + ' = %s' for c in sets)} WHERE {key}::text = %s", [*sets.values(), r["k"]])
                for c in sets:
                    n[f"{table}.{c}"] = n.get(f"{table}.{c}", 0) + 1
    # the story timeline shows the signal titles: its lines and story titles follow
    cur.execute("""SELECT st.step_id, st.one_line FROM staging.story_step st JOIN staging.story s ON s.story_id = st.story_id
                   WHERE s.pillar = 'competitive' AND st.one_line ~ '[0-9](mm|km|kg)'""")
    for r in cur.fetchall():
        new = unit_space(r["one_line"], guard)
        if new != r["one_line"]:
            cur.execute("UPDATE staging.story_step SET one_line = %s WHERE step_id = %s", (new, r["step_id"]))
            n["story_step.one_line"] = n.get("story_step.one_line", 0) + 1
    cur.execute("SELECT story_id, title FROM staging.story WHERE pillar = 'competitive' AND title ~ '[0-9](mm|km|kg)'")
    for r in cur.fetchall():
        new = unit_space(r["title"], guard)
        if new != r["title"]:
            cur.execute("UPDATE staging.story SET title = %s WHERE story_id = %s", (new, r["story_id"]))
            n["story.title"] = n.get("story.title", 0) + 1
    return {"columns": n, "drawer_titles": replaced}


COUNT_SQL = """SELECT count(*) FILTER (WHERE x ~ '[0-9](mm|km|kg)([^a-z0-9]|$)') AS glued, count(*) FILTER (WHERE x ~ '[0-9] (mm|km|kg)([^a-z0-9]|$)') AS spaced
               FROM (SELECT concat_ws(' ', s.title, s.summary, d.drawer_title, d.what_article_says, d.why_it_matters) AS x
                     FROM staging.competitive_signal s LEFT JOIN staging.competitive_signal_detail d ON d.signal_id = s.signal_id
                     UNION ALL SELECT concat_ws(' ', label, value) FROM staging.competitive_signal_evidence) t"""


def repair(apply: bool = False) -> dict:
    from prompts.run import connect
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS d")
        db = cur.fetchone()["d"]
        if db != "kssl_staging" and not db.startswith("kssl_test"):
            raise SystemExit(f"refused: database {db} (kssl_staging or kssl_test_* only)")
        cur.execute(COUNT_SQL)
        before = dict(cur.fetchone())
        out = tidy_signals(cur)
        cur.execute(COUNT_SQL)
        after = dict(cur.fetchone())
        print(f"signal text rows with a glued / spaced number+unit: {before} -> {after}")
        for k, v in sorted(out["columns"].items()):
            print(f"  {k}: {v} rows")
        for sid, old, new in out["drawer_titles"]:
            print(f"  drawer title {sid}: '{old}' -> '{new}'")
        print("applied" if apply else "dry run, rolled back (--apply to write)")
        conn.commit() if apply else conn.rollback()
    conn.close()
    return {"before": before, "after": after, **out}


def _selftest() -> None:
    assert finished("U.S. Army receives first prototype in the programme KSSL and AM General bid for", "U.S. Army Receives First Prototype") \
        == "U.S. Army Receives First Prototype"
    assert finished("Nordvik wins the Veland order", "x") == "Nordvik wins the Veland order"
    assert finished("", "Card title") == "Card title" and finished(None, None) is None and finished("Order to", "") == "Order to"
    assert finished("Veland signs up for.", "T") == "T"
    hand = "Nordvik demonstrates a loitering munition with 80 km hand-over"
    assert finished(hand, "T") == hand                                                     # "-over" is not a dangling word
    g = product_guard(["105mm K274 APFSDS-T", "NV-155", "TriCa (Trichy Carbine) 7.62x39mm", None])
    assert unit_space("Nordvik fires 155mm shells 40km with a 70kg round", g) == "Nordvik fires 155 mm shells 40 km with a 70 kg round"
    assert unit_space("2,000km range; 5.56mm and 7.62x51mm rifles", g) == "2,000 km range; 5.56 mm and 7.62x51 mm rifles"
    assert unit_space("Orders 105mm K274 APFSDS-T rounds and 120mm shells", g) == "Orders 105mm K274 APFSDS-T rounds and 120 mm shells"   # product kept
    assert unit_space('He said "a 155mm gun" and “40km” today, 155mm', g) == 'He said "a 155mm gun" and “40km” today, 155 mm'   # quotes kept
    assert unit_space("see https://x.com/155mm-gun for the 155mm gun", g) == "see https://x.com/155mm-gun for the 155 mm gun"
    assert unit_space("155 mm, 3mmx, mm155, K9A1mm, 155mmL52", g) == "155 mm, 3mmx, mm155, K9A1mm, 155mmL52"                 # left alone
    assert unit_space(None) is None and unit_space("") == "" and unit_space("no units") == "no units"
    assert product_guard([]) is None and product_guard(["NV-155"]) is None
    print("signal_text self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        repair(apply="--apply" in sys.argv)
