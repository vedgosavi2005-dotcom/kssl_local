"""Projects with no name or no stage (functional test G15, 2026-10-25): code only, no model.

    python -m scripts.fill_project_gaps --selftest
    python -m scripts.fill_project_gaps [--apply]       dry run (rolled back) without --apply; kssl_staging / kssl_test_* only

Why they are empty: db/purge_blog_sources.py (2026-10-17, blogs are never sources) set a column NULL when its only source was a
blocked blog (idrw.org / ajaishukla.com). The project kept its other, non-blog evidence: the stage note, the stage ladder
(competitive_project_stage.is_current), its story title (the name it was loaded with) and its non-blog source headlines
(competitive_project_source.source_label). A value is filled back only when that non-blog evidence states it:

  * stage: the stage the stage note states (stage_from_note: furthest stage a past-tense clause reports; future, planned and
    negated clauses are ignored) AND the same stage marked current on the project's stage ladder. Both must agree. Its source is a
    judgement fact_source row naming that basis (stage is a JUDGEMENT column, project.yml).
  * project_title: the story title, when its words are stated in a non-blog source headline of the project or in its sourced
    "what the project is" text (title_stated). Its sources are the project sources whose headline states it (quote = the headline).
Anything else stays empty and is listed.
"""

from __future__ import annotations

import re
import sys

LADDER = ("Concept", "Trials", "Contract", "Production", "Deliveries", "In service")
STAGE_WORDS = (   # furthest first: the furthest stage a clause states wins
    ("In service", r"\binduct(?:ed|s)?\b|\bin service\b|\bserv(?:e|es|ing) with\b|\bdeployed\b|\boperational\b|\bcommissioned\b|\bfielded\b"),
    ("Deliveries", r"\bdelivered\b|\bdeliveries (?:began|have begun|are ongoing|have started|started)\b|\bshipped\b|\breceived\b|"
                   r"\bhanded over\b|\barrived\b|\breached\b|\bfinal batch\b|\bfirst batch\b"),
    ("Production", r"\b(?:production|manufacturing) (?:began|started|is under ?way|has started)\b|\bin (?:series )?production\b"),
    ("Contract", r"\bsigned\b|\bawarded\b|\bplaced the order\b|\bwon the order\b|\breported the order\b|\bagreed to (?:acquire|buy)\b|\bholds .*orders?\b"),
    ("Trials", r"\btrials?\b|\btest(?:ed|ing|s)?\b|\bprototypes?\b|\bevaluat"),
    ("Concept", r"\blowest bidder\b|\brequest for proposal\b|\bRFP\b|\btender\b|\bshortlist|\bcleared\b|\bapproved\b"),
)
FUTURE = re.compile(r"\b(?:will|expected|expects|planned|plans?|scheduled|due|to begin|to start|begin in|follow|from 20\d\d|by 20\d\d|"
                    r"no source|not yet|none reports?|no delivery)\b", re.I)


def stage_from_note(note) -> str | None:
    """The furthest LADDER stage a past-tense clause of the stage note states, or None."""
    best = None
    for clause in re.split(r"[;,]|\band\b|\bwhile\b|\bbut\b|\. ", str(note or "")):
        if not clause.strip() or FUTURE.search(clause):
            continue
        for stage, pat in STAGE_WORDS:
            if re.search(pat, clause, re.I):
                if best is None or LADDER.index(stage) > LADDER.index(best):
                    best = stage
                break
    return best


STOP = frozenset("a an the of for to in on and with by from at as its it is are be new local".split())


def words(text) -> set:
    t = re.sub(r"\bmark[- ]?iv\b|\bm4\b", "mk-iv", str(text or "").lower())
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9&]+", t) if w not in STOP and len(w) > 1}


def title_stated(title, texts) -> list[int]:
    """Indexes of the texts that state the title: they hold at least 3/4 of the title's words (and at least 2)."""
    tw = words(title)
    if len(tw) < 2:
        return []
    return [i for i, t in enumerate(texts) if len(tw & words(t)) >= max(2, round(0.75 * len(tw)))]


def title_variants(title) -> list[str]:
    """The title, then (when it spells an acronym out) the acronym form: 'Airborne Early Warning & Control (AEW&C) Mk-II programme'
    -> 'AEW&C Mk-II programme'."""
    t = str(title or "").strip()
    if not t:
        return []
    short = re.sub(r"\b[A-Z][\w-]*(?:\s+(?:&|and|of|[A-Z][\w&-]*)){0,7}\s+\(([A-Z][A-Za-z&]{1,9})\)", r"\1", t)
    return [t] + ([short] if short != t else [])


def plan(cur) -> dict:
    from backend.sources import is_blocked
    cur.execute("""SELECT p.project_id, p.project_title, p.stage, p.stage_note, p.what_the_project_is, s.title AS story_title,
                          (SELECT st.stage_name FROM staging.competitive_project_stage st WHERE st.project_id = p.project_id AND st.is_current LIMIT 1) AS ladder
                   FROM staging.competitive_project p LEFT JOIN staging.story s ON s.story_id = p.story_id
                   WHERE coalesce(trim(p.project_title), '') = '' OR coalesce(trim(p.stage), '') = ''
                   ORDER BY p.project_id""")
    out = {"stage": [], "title": [], "left": []}
    for r in cur.fetchall():
        pid = r["project_id"]
        if not (r["stage"] or "").strip():
            said = stage_from_note(r["stage_note"])
            if said and said == r["ladder"]:
                out["stage"].append((pid, said, r["stage_note"]))
            else:
                out["left"].append((pid, "stage", f"note says {said or 'no stage'}, ladder says {r['ladder'] or 'none'}"))
        if not (r["project_title"] or "").strip():
            cur.execute("SELECT source_url, source_label FROM staging.competitive_project_source WHERE project_id = %s ORDER BY source_id", (pid,))
            srcs = [x for x in cur.fetchall() if x["source_url"] and not is_blocked(x["source_url"])]
            title, hits, in_text = (r["story_title"] or "").strip(), [], False
            for cand in title_variants(title):          # the name as stored, else its acronym form ("AEW&C Mk-II programme")
                hits = title_stated(cand, [x["source_label"] for x in srcs])
                in_text = bool(title_stated(cand, [r["what_the_project_is"]]))
                if hits or in_text:
                    title = cand
                    break
            if title and (hits or in_text):
                out["title"].append((pid, title, [(srcs[i]["source_url"], srcs[i]["source_label"]) for i in hits], in_text))
            else:
                out["left"].append((pid, "project_title", f"story title {title!r} is not stated in a non-blog source headline or the project text"))
    return out


def apply_plan(cur, p: dict) -> None:
    for pid, stage, note in p["stage"]:
        cur.execute("UPDATE staging.competitive_project SET stage = %s WHERE project_id = %s AND coalesce(trim(stage), '') = ''", (stage, pid))
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at)
                       SELECT 'competitive_project', %s, 'stage', 'judgement', 'judgement', %s, now()
                       WHERE NOT EXISTS (SELECT 1 FROM staging.fact_source WHERE table_name = 'competitive_project' AND row_id = %s AND column_name = 'stage')""",
                    (str(pid), f"{stage}: the stage note states it (\"{note}\") and the project's stage ladder marks it current "
                               f"(code rule, scripts/fill_project_gaps.py, G15 2026-10-25).", str(pid)))
    for pid, title, srcs, in_text in p["title"]:
        cur.execute("UPDATE staging.competitive_project SET project_title = %s WHERE project_id = %s AND coalesce(trim(project_title), '') = ''",
                    (title, pid))
        cur.execute("SELECT 1 FROM staging.fact_source WHERE table_name = 'competitive_project' AND row_id = %s AND column_name = 'project_title'", (str(pid),))
        if cur.fetchone() is None:
            for url, label in srcs:
                cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, quote, retrieved_at)
                               VALUES ('competitive_project', %s, 'project_title', %s, %s, now())""", (str(pid), url, label))
            if not srcs:     # stated only in the project's own sourced text: that text's sources carry the name
                cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, document_id, retrieved_at)
                               SELECT table_name, row_id, 'project_title', source_url, source_tier, publisher, quote, document_id, now()
                               FROM staging.fact_source WHERE table_name = 'competitive_project' AND row_id = %s AND column_name = 'what_the_project_is'""",
                            (str(pid),))


def main(apply: bool) -> dict:
    from prompts.run import connect
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS d")
        db = cur.fetchone()["d"]
        if db != "kssl_staging" and not db.startswith("kssl_test"):
            raise SystemExit(f"refused: database {db} (kssl_staging or kssl_test_* only)")
        p = plan(cur)
        for pid, stage, note in p["stage"]:
            print(f"stage  {pid}: {stage}   <- note: {note}")
        for pid, title, srcs, in_text in p["title"]:
            print(f"title  {pid}: {title}   <- " + ("; ".join(lbl for _u, lbl in srcs) if srcs else "") + (" [project text]" if in_text else ""))
        for pid, col, why in p["left"]:
            print(f"LEFT   {pid} {col}: {why}")
        apply_plan(cur, p)
        print("applied" if apply else "dry run, rolled back (--apply to write)")
        conn.commit() if apply else conn.rollback()
    conn.close()
    return p


def _selftest() -> None:
    assert stage_from_note("Kalyani shipped the first large batch of rifles under its 2026 state contract.") == "Deliveries"
    assert stage_from_note("The Army has inducted the gun; the 114-gun order is nearly complete and a follow-on contract is expected by March 2027.") == "In service"
    assert stage_from_note("Nordvik is the lowest bidder; no source reports a signed contract.") == "Concept"
    assert stage_from_note("The Indian Army signed contracts worth Rs 1,577 crore with two firms.") == "Contract"
    assert stage_from_note("Finland and Sweden have started procurement; deliveries begin in 2027 and national field trials follow.") is None
    assert stage_from_note("Veland has deployed 250 howitzers along its border.") == "In service"
    assert stage_from_note(None) is None and stage_from_note("") is None
    assert title_stated("Loiter Munition Systems for Indian Army", ["MoD inks Rs 1,577 crore contracts for Loiter Munition Systems for Indian Army", "x"]) == [0]
    assert title_stated("Carl-Gustaf MK-IV rocket launchers for the Indian Army", ["Carl Gustaf M4 Rocket Launchers for Indian Army"]) == [0]
    assert title_stated("BrahMos missile deal with Vietnam", ["BrahMos deal with Vietnam signed, Indonesia close"]) == [0]
    assert title_stated("Nordvik NV-155 for Veland", ["Veland buys trucks"]) == [] and title_stated("X", ["X"]) == []
    assert title_variants("Airborne Early Warning & Control (AEW&C) Mk-II programme") == [
        "Airborne Early Warning & Control (AEW&C) Mk-II programme", "AEW&C Mk-II programme"]
    assert title_variants("Loiter Munition Systems") == ["Loiter Munition Systems"] and title_variants(None) == []
    assert title_stated("AEW&C Mk-II programme", ["DRDO inks two contracts as part of AEW&C MK-II programme"]) == [0]
    print("fill_project_gaps self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main(apply="--apply" in sys.argv)
