"""Stories and steps (docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md A.0.5): code proposes, the model picks, code decides.

A story is one thread of events: competitor (or buyer) + product / subject + counterpart country + event family. Its key is
built by code (`story_key`); the prompt is shown the open stories of that competitor as handles (`snippet`) and answers with
`story_ref` = a handle (T + 8 hex) or "new"; the loader links the card to the story (`pick`: an EXACT KEY MATCH WINS over the
model's answer, in both directions). Every card is one step on its story (staging.story_step). After each step the label is
compared with the previous step's; when it changed, a `label_change` step is written ("watch -> threat: probability 3 -> 5
(contract signed)") and, for an upward change, story.escalated_at is set. All label changes are rebuilt from the steps, so
a re-run or a late-arriving older article gives the same result.

    story_key / handle_of / pick / story_change                      pure (self-checked: python -m prompts.story --selftest)
    open_stories / snippet / stories_block                           candidates for a prompt (DB, read-only)
    link_card(cur, table, row, transient, run_id)                    called by the derive hook `story_link` (prompts/derive.py)

Tables: staging.story, staging.story_step (db/setup/11_foundations.sql); both are in backend/review.py GRAPH (story is a card,
its steps are its children).
"""

from __future__ import annotations

import hashlib
import re
import sys
from datetime import date, datetime, timedelta

NONE_ON_RECORD = "none on record"
FAMILIES = ("programme", "order", "delivery", "trial", "partnership", "capacity", "policy", "demand", "technology")
NEW = "new"
HANDLE = re.compile(r"T[0-9a-f]{8}\Z", re.I)
MAX_LINE = 120
STAGES = ("need_stated", "approved_funded", "rfi", "rfp_tender", "downselect_prototype", "production_award", "delivered", "cancelled")
# how much "worse for KSSL / further along" a label is, so a change can be called up or down
LABEL_RANK = {"fav": 0, "watch": 1, "threat": 2, "pass": 0, "monitor": 1, "position": 2, "pursue": 3,
              **{s: i for i, s in enumerate(STAGES[:6], 1)}, "delivered": 7, "cancelled": 0}
# glance_move (competitive_signal_detail) -> story step type / event family
MOVE_STEP = {"Order": "order", "Contract": "contract", "Selection": "order", "Delivery": "delivery", "Induction": "delivery", "Trial": "trial",
             "Launch": "announced", "JV": "partnership", "MoU": "partnership", "Acquisition": "partnership", "Capacity": "capacity",
             "Export approval": "policy", "Policy": "policy", "Supply deal": "contract", "Cancellation": "update"}
MOVE_FAMILY = {"Order": "order", "Contract": "order", "Selection": "order", "Supply deal": "order", "Delivery": "delivery", "Induction": "delivery",
               "Trial": "trial", "Launch": "trial", "JV": "partnership", "MoU": "partnership", "Acquisition": "partnership",
               "Capacity": "capacity", "Export approval": "policy", "Policy": "policy", "Cancellation": "programme"}
NEWS_FAMILY = {"programme_order": "order", "delivery_induction": "delivery", "deployment_combat_use": "delivery", "trial_test_demo": "trial",
               "export_new_customer": "order", "upgrade_variant_component": "technology", "production_localisation_licence": "capacity",
               "certification_qualification": "programme", "incident_failure": "programme"}


# ---- pure rules -----------------------------------------------------------------------------------------------

def slug(s) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")


def story_key(pillar: str, party, subject, country, family) -> str:
    """pillar:party:subject:country:family with blank parts left blank: competitive:hanwha:k9:pl:order"""
    iso = str(country or "").strip().lower()
    iso = iso if re.fullmatch(r"[a-z]{2}", iso) else ""
    fam = family if family in FAMILIES else ""
    return ":".join([slug(pillar), slug(party), slug(subject), iso, fam])


def story_id_of(key: str) -> int:
    return int.from_bytes(hashlib.sha256(("story|" + key).encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def handle_of(story_id) -> str:
    """T + 8 hex: what the model is shown and answers with."""
    return "T" + hashlib.sha256(f"handle|{story_id}".encode()).hexdigest()[:8]


def parse_ref(text) -> str | None:
    """The model's story_ref -> a normalised handle, NEW, or None (empty / not a handle)."""
    t = str(text or "").strip()
    if t.lower() == NEW:
        return NEW
    return "T" + t[1:].lower() if HANDLE.match(t) else None


def pick(ref, key: str, by_handle: dict, by_key: dict) -> tuple[dict | None, str, str | None]:
    """(story row or None for a new story, how, warning). Exact key wins over the model's answer."""
    if key in by_key:
        hit = by_key[key]
        asked = parse_ref(ref)
        warn = None
        if asked not in (None, NEW) and by_handle.get(asked) is not None and by_handle[asked] is not hit:
            warn = f"story_ref {asked} ignored: the key {key} already exists"
        return hit, "key", warn
    h = parse_ref(ref)
    if h in (None, NEW):
        return None, "new", (f"story_ref '{ref}' is not a handle or 'new'" if h is None and str(ref or "").strip() else None)
    if h in by_handle:
        return by_handle[h], "handle", None
    return None, "new", f"story_ref {h} is not an open story of this competitor: a new story is made"


def step_line(text, limit: int = MAX_LINE) -> str | None:
    t = " ".join(str(text or "").split())
    return None if not t else (t if len(t) <= limit else t[:limit - 1].rstrip() + "…")


def story_change(prev_label, new_label, prev_prob=None, new_prob=None, prev_impact=None, new_impact=None, why=None) -> dict | None:
    """The label_change step between two states, or None when the label is the same (or either is unknown).
    {"direction": up | down | changed, "changed": "watch -> threat: probability 3 -> 5 (contract signed)"} (<= 120 chars)."""
    if not prev_label or not new_label or str(prev_label) == str(new_label):
        return None
    a, b = LABEL_RANK.get(str(prev_label)), LABEL_RANK.get(str(new_label))
    direction = "changed" if a is None or b is None or a == b else ("up" if b > a else "down")
    bits = [f"{n} {x} -> {y}" for n, x, y in (("probability", prev_prob, new_prob), ("impact", prev_impact, new_impact))
            if x is not None and y is not None and x != y]
    head = f"{prev_label} -> {new_label}" + (": " + ", ".join(bits) if bits else "")
    tail = f" ({step_line(why, 50)})" if why else ""
    return {"direction": direction, "changed": step_line(head + tail)}


def rebuild_timeline(steps: list[dict]) -> dict:
    """Pure core of the escalation logic. `steps` = the real (non label_change) steps of one story, each
    {step_id, step_date, one_line, label_after, probability, impact, ...}. Returns
    {"ordered": steps in date order, "changes": [{"after": step, direction, changed}], "state": last step, "escalated_at": date|None}."""
    # same-day steps keep the order they were loaded in (created_at), then the id, so a re-run gives the same timeline
    ordered = sorted(steps, key=lambda s: (s.get("step_date") or date.max, str(s.get("created_at") or ""), str(s.get("step_id"))))
    # a planned or future-dated step is an expectation, not an event: it never sets the story's state, label changes or
    # escalation (a 2038 delivery plan made stories look like the newest news). A story with only planned steps keeps its last one.
    today = date.today()
    real = [s for s in ordered if s.get("step_type") != "planned" and not (isinstance(s.get("step_date"), date) and s["step_date"] > today)]
    changes, escalated = [], None
    for prev, cur in zip(real, real[1:]):
        ch = story_change(prev.get("label_after"), cur.get("label_after"), prev.get("probability"), cur.get("probability"),
                          prev.get("impact"), cur.get("impact"), cur.get("one_line"))
        if ch:
            changes.append({"after": cur, **ch})
            if ch["direction"] == "up":
                escalated = cur.get("step_date") or escalated
    return {"ordered": ordered, "changes": changes, "state": (real or ordered)[-1] if ordered else None, "escalated_at": escalated}


def snippet(cands: list[dict]) -> str:
    """The STORIES context block: `T3f9a12c0: competitive:borealis:howitzer:no:order - Borealis wins the order (2026-10-08)`."""
    if not cands:
        return NONE_ON_RECORD
    return "\n".join(f"{c['handle']}: {c['story_key']} - {c.get('last_line') or c.get('title') or 'no step yet'}"
                     + (f" ({c['last_step_at']})" if c.get("last_step_at") else "") for c in cands)


# ---- database: candidates -----------------------------------------------------------------------------------

def open_stories(cur, competitor_id=None, product_id=None, buyer_name=None, pillar: str | None = None, days: int = 365,
                 limit: int = 15, today: date | None = None) -> list[dict]:
    """Open stories of a competitor (and of the named product / buyer) active in the last `days`, newest first, with a handle each."""
    since = (today or date.today()) - timedelta(days=days)
    where, args = ["s.status = 'open'", "(s.last_step_at IS NULL OR s.last_step_at >= %s)"], [since]
    who = []
    if competitor_id is not None:
        who.append("s.competitor_id = %s")
        args.append(str(competitor_id))
    if product_id is not None:
        who.append("s.product_id = %s")
        args.append(str(product_id))
    if buyer_name:
        who.append("lower(s.buyer_name) = lower(%s)")
        args.append(buyer_name)
    if who:
        where.append("(" + " OR ".join(who) + ")")
    if pillar:
        where.append("s.pillar = %s")
        args.append(pillar)
    cur.execute(f"""SELECT s.story_id, s.story_key, s.title, s.current_label, s.last_step_at,
                           (SELECT t.one_line FROM staging.story_step t WHERE t.story_id = s.story_id AND t.step_type <> 'label_change'
                             ORDER BY t.step_no DESC LIMIT 1) AS last_line
                    FROM staging.story s WHERE {' AND '.join(where)}
                    ORDER BY s.last_step_at DESC NULLS LAST, s.story_key LIMIT %s""", [*args, limit])
    return [{**dict(r), "handle": handle_of(r["story_id"])} for r in cur.fetchall()]


def stories_block(cur, **kw) -> str:
    """Ready-made context snippet for a prompt: stories_block(cur, competitor_id=..., pillar='competitive')."""
    return snippet(open_stories(cur, **kw))


def _stories_for_resolution(cur, pillar: str, competitor_id=None, buyer_name=None) -> tuple[dict, dict]:
    where, args = ["pillar = %s"], [pillar]
    if competitor_id is not None:
        where.append("competitor_id = %s")
        args.append(str(competitor_id))
    elif buyer_name:
        where.append("lower(buyer_name) = lower(%s)")
        args.append(buyer_name)
    cur.execute(f"SELECT * FROM staging.story WHERE {' AND '.join(where)}", args)
    rows = [dict(r) for r in cur.fetchall()]
    return {handle_of(r["story_id"]): r for r in rows}, {r["story_key"]: r for r in rows}


# ---- database: writing ------------------------------------------------------------------------------------------

def _step_id(story_id, table, row_id, step_type, extra="") -> int:
    return int.from_bytes(hashlib.sha256(f"step|{story_id}|{table}|{row_id}|{step_type}|{extra}".encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


_LABEL_WORDS: dict = {}


def label_word(cur, code) -> str:
    """The display word of a stored label code (story_step.label_after first, then any column holding that code, e.g. a
    stage); a code with no label reads with spaces, never as snake_case."""
    if not _LABEL_WORDS:
        cur.execute("""SELECT code, label FROM staging_ui.code_label WHERE label IS NOT NULL
                       ORDER BY (table_name = 'story_step' AND column_name = 'label_after') DESC""")
        for r in cur.fetchall():
            _LABEL_WORDS.setdefault(r["code"], r["label"])
    c = str(code or "")
    return _LABEL_WORDS.get(c) or c.replace("_", " ")


def rebuild_story(cur, story_id, rule_version: str | None = None) -> dict:
    """Rewrite the label_change steps, the step numbers and the story's current state from its real steps."""
    cur.execute("SELECT * FROM staging.story_step WHERE story_id = %s AND step_type <> 'label_change'", (story_id,))
    tl = rebuild_timeline([dict(r) for r in cur.fetchall()])
    cur.execute("DELETE FROM staging.story_step WHERE story_id = %s AND step_type = 'label_change'", (story_id,))
    entries = []
    for st in tl["ordered"]:
        entries.append((st, False, None))
        for ch in tl["changes"]:
            if ch["after"] is st:
                entries.append((st, True, ch))
    for n, (st, is_change, ch) in enumerate(entries, 1):
        if is_change:
            cur.execute("""INSERT INTO staging.story_step (step_id, story_id, step_no, step_date, step_type, one_line, changed, source_url, source_table,
                                                           source_row_id, probability, impact, label_after, run_id)
                           VALUES (%s,%s,%s,%s,'label_change',%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (_step_id(story_id, st.get("source_table"), st.get("source_row_id"), "label_change", st["step_id"]), story_id, n, st.get("step_date"),
                         step_line(f"Label changed to {label_word(cur, st.get('label_after'))}"), ch["changed"], st.get("source_url"), st.get("source_table"),
                         st.get("source_row_id"), st.get("probability"), st.get("impact"), st.get("label_after"), st.get("run_id")))
        else:
            cur.execute("UPDATE staging.story_step SET step_no = %s WHERE step_id = %s", (n, st["step_id"]))
    last, first = tl["state"], (tl["ordered"][0] if tl["ordered"] else None)
    if last:
        cur.execute("""UPDATE staging.story SET current_label = %s, probability = %s, impact = %s, first_step_at = %s, last_step_at = %s,
                              escalated_at = %s, rule_version = coalesce(%s, rule_version), updated_at = now() WHERE story_id = %s""",
                    (last.get("label_after"), last.get("probability"), last.get("impact"), first.get("step_date"), last.get("step_date"),
                     tl["escalated_at"], rule_version, story_id))
    return tl


def add_step(cur, story_id, *, step_date, step_type: str, one_line, source_url=None, source_table=None, source_row_id=None,
             probability=None, impact=None, label=None, run_id=None, rule_version=None) -> dict:
    """One real step (replaced, not duplicated, when the same card is loaded again), then the timeline is rebuilt."""
    sid = _step_id(story_id, source_table, source_row_id, step_type) if source_row_id else _step_id(story_id, None, None, step_type, f"{step_date}|{one_line}")
    cur.execute("""INSERT INTO staging.story_step (step_id, story_id, step_no, step_date, step_type, one_line, source_url, source_table, source_row_id,
                                                   probability, impact, label_after, run_id)
                   VALUES (%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (step_id) DO UPDATE SET step_date = EXCLUDED.step_date, one_line = EXCLUDED.one_line, source_url = EXCLUDED.source_url,
                       probability = EXCLUDED.probability, impact = EXCLUDED.impact, label_after = EXCLUDED.label_after, run_id = EXCLUDED.run_id""",
                (sid, story_id, step_date, step_type, step_line(one_line), source_url, source_table, source_row_id, probability, impact, label, run_id))
    return rebuild_story(cur, story_id, rule_version)


def upsert_story(cur, key: str, *, pillar: str, kind=None, competitor_id=None, product_id=None, buyer_name=None, country_code=None,
                 title=None, impact_dimension=None) -> int:
    sid = story_id_of(key)
    iso = str(country_code or "").upper()[:2] or None
    cur.execute("""INSERT INTO staging.story (story_id, story_key, pillar, kind, competitor_id, product_id, buyer_name, country_code, title, impact_dimension)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (story_key) DO UPDATE SET impact_dimension = coalesce(EXCLUDED.impact_dimension, staging.story.impact_dimension),
                       title = coalesce(staging.story.title, EXCLUDED.title), updated_at = now()
                   RETURNING story_id""",
                (sid, key, pillar, kind, None if competitor_id is None else str(competitor_id), None if product_id is None else str(product_id),
                 buyer_name, iso, step_line(title, 200), impact_dimension))
    return cur.fetchone()["story_id"]


# per card table: how its story key, step and label are read. `parts(row, transient, cur)` -> dict
def _country_iso(cur, name_or_code) -> str:
    if not name_or_code:
        return ""
    cur.execute("""SELECT iso2 FROM staging.country_reference WHERE lower(iso2) = lower(%(v)s) OR lower(country_name) = lower(%(v)s)
                   OR lower(%(v)s) = ANY(SELECT lower(a) FROM unnest(coalesce(aliases, '{}')) a) LIMIT 1""", {"v": str(name_or_code).strip()})
    r = cur.fetchone()
    return (r["iso2"] or "").lower() if r else ""


def _signal_parts(cur, row, tr):
    cur.execute("SELECT * FROM staging.competitive_signal_detail WHERE signal_id = %s", (row["signal_id"],))
    det = cur.fetchone() or {}
    move = det.get("glance_move")
    cur.execute("SELECT display_name, short_name FROM staging.competitive_competitor WHERE competitor_id = %s", (row["company_id"],))
    comp = cur.fetchone() or {}
    name = tr.get("story_product")
    pid = None
    if name:
        cur.execute("SELECT product_id, product_name FROM staging.competitive_product WHERE competitor_id = %s AND lower(product_name) = lower(%s)",
                    (row["company_id"], str(name).strip()))
        r = cur.fetchone()
        if r:
            pid, name = r["product_id"], r["product_name"]
    return dict(pillar="competitive", party=comp.get("short_name") or comp.get("display_name"), subject=name, product_id=pid,
                competitor_id=row["company_id"], buyer_name=None,
                country=_country_iso(cur, tr.get("story_country") or det.get("glance_where")),
                family=tr.get("story_kind") if tr.get("story_kind") in FAMILIES else MOVE_FAMILY.get(move, "programme"),
                step_type=MOVE_STEP.get(move, "update"), date=row.get("event_date"), line=row.get("title"), url=det.get("source_url"),
                probability=row.get("probability"), impact=row.get("impact"), label=row.get("classification"),
                impact_dimension=row.get("impact_dimension"), rule_version=row.get("rule_version"), title=row.get("title"))


def _product_news_parts(cur, row, tr):
    cur.execute("""SELECT p.product_name, p.competitor_id, c.display_name, c.short_name FROM staging.competitive_product p
                   JOIN staging.competitive_competitor c ON c.competitor_id = p.competitor_id WHERE p.product_id = %s""", (row["product_id"],))
    p = cur.fetchone() or {}
    return dict(pillar="competitive", party=p.get("short_name") or p.get("display_name"), subject=p.get("product_name"), product_id=row["product_id"],
                competitor_id=p.get("competitor_id"), buyer_name=None, country=_country_iso(cur, tr.get("story_country")),
                family=tr.get("story_kind") if tr.get("story_kind") in FAMILIES else NEWS_FAMILY.get(row.get("news_type"), "programme"),
                step_type={"programme_order": "order", "delivery_induction": "delivery", "trial_test_demo": "trial"}.get(row.get("news_type"), "update"),
                date=row.get("event_date") or row.get("published_date"), line=row.get("headline"), url=row.get("article_url"),
                probability=None, impact=None, label=None, impact_dimension=None, rule_version=None, title=row.get("headline"))


def _requirement_parts(cur, row, tr):
    return dict(pillar="market", party=row.get("buyer_name") or row.get("country_name"), subject=row.get("category"), product_id=None,
                competitor_id=None, buyer_name=row.get("buyer_name") or row.get("country_name"), country=_country_iso(cur, row.get("country_name")),
                family="demand", step_type="update", date=row.get("last_confirmed") or row.get("stage_date"), line=row.get("title"), url=None,
                probability=None, impact=None, label=row.get("stage"), impact_dimension=None, rule_version=None, title=row.get("title"))


def _opportunity_parts(cur, row, tr):
    return dict(pillar="market", party=row.get("buyer_name"), subject=tr.get("story_product"), product_id=None, competitor_id=None,
                buyer_name=row.get("buyer_name"), country=_country_iso(cur, row.get("country_code")), family="demand", step_type="update",
                date=row.get("as_of_date"), line=row.get("title"), url=None, probability=None, impact=None,
                label=row.get("stage") if row.get("stage") in STAGES else None, impact_dimension=None, rule_version=None, title=row.get("title"))


def _tech_parts(cur, row, tr):
    cur.execute("SELECT display_name FROM staging.technology_company WHERE company_id = %s", (row.get("primary_company_id"),))
    c = cur.fetchone() or {}
    return dict(pillar="technology", party=c.get("display_name"), subject=tr.get("story_thread") or row.get("category_text"), product_id=None, competitor_id=None,
                buyer_name=None, country=_country_iso(cur, row.get("country_code")), family="technology", step_type="update",
                date=row.get("article_date") or row.get("published_on"), line=row.get("title"), url=None, probability=None, impact=row.get("relevance"),
                label=row.get("direction"), impact_dimension=None, rule_version=row.get("rule_version"), title=row.get("title"))


CARDS = {   # table -> (key column, parts function)
    "competitive_signal": ("signal_id", _signal_parts),
    "competitive_product_news": ("product_news_id", _product_news_parts),
    "market_global_requirement": ("requirement_id", _requirement_parts),
    "market_opportunity": ("opportunity_id", _opportunity_parts),
    "technology_overview_article": ("overview_article_id", _tech_parts),
}


def link_card(cur, table: str, row: dict, tr: dict | None = None, run_id=None, warnings: list | None = None) -> int | None:
    """Link one stored card to its story (found by handle or key, or created) and write its step. Returns story_id."""
    tr = tr or {}
    keycol, parts_fn = CARDS[table]
    p = parts_fn(cur, row, tr)
    key = story_key(p["pillar"], p["party"], p["subject"], p["country"], p["family"])
    by_handle, by_key = _stories_for_resolution(cur, p["pillar"], p["competitor_id"], p["buyer_name"])
    hit, how, warn = pick(tr.get("story_ref"), key, by_handle, by_key)
    if warn and warnings is not None:
        warnings.append(f"story: {warn}")
    if hit is not None:
        story_id = hit["story_id"]
    else:
        story_id = upsert_story(cur, key, pillar=p["pillar"], kind=p["family"], competitor_id=p["competitor_id"], product_id=p["product_id"],
                                buyer_name=p["buyer_name"], country_code=p["country"], title=p["title"], impact_dimension=p["impact_dimension"])
    cur.execute("SELECT DISTINCT story_id FROM staging.story_step WHERE source_table = %s AND source_row_id = %s AND story_id <> %s",
                (table, str(row[keycol]), story_id))
    for r in cur.fetchall():                      # the card moved to another story (its key changed on a re-run): take its old steps away
        cur.execute("DELETE FROM staging.story_step WHERE story_id = %s AND source_table = %s AND source_row_id = %s", (r["story_id"], table, str(row[keycol])))
        cur.execute("SELECT count(*) AS n FROM staging.story_step WHERE story_id = %s AND step_type <> 'label_change'", (r["story_id"],))
        if cur.fetchone()["n"]:
            rebuild_story(cur, r["story_id"])
        else:
            cur.execute("DELETE FROM staging.story_step WHERE story_id = %s", (r["story_id"],))
            cur.execute("DELETE FROM staging.story WHERE story_id = %s", (r["story_id"],))
    add_step(cur, story_id, step_date=p["date"], step_type=p["step_type"], one_line=p["line"], source_url=p["url"], source_table=table,
             source_row_id=str(row[keycol]), probability=p["probability"], impact=p["impact"], label=p["label"], run_id=run_id,
             rule_version=p["rule_version"])
    cur.execute(f"UPDATE staging.{table} SET story_id = %s WHERE {keycol}::text = %s", (story_id, str(row[keycol])))
    return story_id


# ---- self-check ---------------------------------------------------------------------------------------------------

def _selftest() -> None:
    # keys: blank parts stay blank; the country must be an ISO code; an unknown family is blank
    assert story_key("competitive", "Hanwha", "K9", "PL", "order") == "competitive:hanwha:k9:pl:order"
    assert story_key("competitive", "Hanwha Aerospace", "", "", "order") == "competitive:hanwha-aerospace:::order"
    assert story_key("competitive", "Nordvik", "NV-155", "Veland", "weird") == "competitive:nordvik:nv-155::"
    assert story_key("market", None, None, "in", "demand") == "market:::in:demand"
    # ids and handles are stable and differ per key
    k1, k2 = "competitive:a:b:pl:order", "competitive:a:b:pl:delivery"
    assert story_id_of(k1) == story_id_of(k1) != story_id_of(k2) and 0 <= story_id_of(k1) < 2 ** 63
    h = handle_of(story_id_of(k1))
    assert HANDLE.match(h) and h == handle_of(story_id_of(k1)) != handle_of(story_id_of(k2))
    assert parse_ref(h.upper().replace("T", "t", 1)) == h and parse_ref("NEW") == NEW and parse_ref("") is None and parse_ref("T123") is None
    # pick: exact key wins; a handle is used when the key is new; an unknown handle makes a new story with a warning
    s1, s2 = {"story_id": 1, "story_key": k1}, {"story_id": 2, "story_key": k2}
    by_h, by_k = {handle_of(1): s1, handle_of(2): s2}, {k1: s1, k2: s2}
    assert pick(NEW, k1, by_h, by_k) == (s1, "key", None)                                   # the model said new; the key exists
    hit, how, w = pick(handle_of(2), k1, by_h, by_k)
    assert hit is s1 and how == "key" and "ignored" in w                                     # the model picked another story; the key wins
    assert pick(handle_of(2), "competitive:x:::order", by_h, by_k) == (s2, "handle", None)
    assert pick(NEW, "competitive:x:::order", by_h, by_k) == (None, "new", None)
    assert pick(None, "competitive:x:::order", by_h, by_k) == (None, "new", None)
    hit, how, w = pick("T00000000", "competitive:x:::order", by_h, by_k)
    assert hit is None and how == "new" and "not an open story" in w
    assert "not a handle" in pick("banana", "competitive:x:::order", by_h, by_k)[2]
    # step_line
    assert step_line("  a   b ") == "a b" and step_line(None) is None and len(step_line("x" * 300)) == MAX_LINE and step_line("x" * 300).endswith("…")
    # story_change: up, down, same, unknown, text
    c = story_change("watch", "threat", 3, 5, 3, 5, "contract signed")
    assert c == {"direction": "up", "changed": "watch -> threat: probability 3 -> 5, impact 3 -> 5 (contract signed)"}, c
    assert story_change("threat", "watch", 5, 3)["direction"] == "down" and story_change("threat", "watch", 5, 3)["changed"] == "threat -> watch: probability 5 -> 3"
    assert story_change("watch", "watch", 3, 5) is None and story_change(None, "watch") is None and story_change("watch", None) is None
    assert story_change("a", "b")["direction"] == "changed" and story_change("pass", "pursue")["direction"] == "up"
    assert story_change("need_stated", "rfp_tender")["direction"] == "up" and story_change("rfp_tender", "cancelled")["direction"] == "down"
    assert len(story_change("watch", "threat", why="x " * 100)["changed"]) <= MAX_LINE
    # timeline: watch -> watch -> threat -> watch; escalated_at = the date of the upward change
    d = lambda m, dd: date(2025, m, dd)            # past dates: a future step is a plan, not the state
    steps = [dict(step_id=3, step_date=d(10, 8), one_line="Contract signed", label_after="threat", probability=5, impact=5),
             dict(step_id=1, step_date=d(6, 20), one_line="Shortlisted", label_after="watch", probability=3, impact=4),
             dict(step_id=2, step_date=d(8, 1), one_line="Trials", label_after="watch", probability=3, impact=4),
             dict(step_id=4, step_date=d(11, 2), one_line="Order cancelled", label_after="watch", probability=2, impact=4)]
    tl = rebuild_timeline(steps)
    assert [s["step_id"] for s in tl["ordered"]] == [1, 2, 3, 4] and tl["state"]["step_id"] == 4
    assert [(c["after"]["step_id"], c["direction"]) for c in tl["changes"]] == [(3, "up"), (4, "down")]
    assert tl["changes"][0]["changed"] == "watch -> threat: probability 3 -> 5, impact 4 -> 5 (Contract signed)" and tl["escalated_at"] == d(10, 8)
    # an older article arriving late is placed by date and does not change the current state
    late = rebuild_timeline(steps[:1] + [dict(step_id=9, step_date=d(5, 1), one_line="Rumour", label_after="watch", probability=1, impact=2)])
    assert late["state"]["step_id"] == 3 and late["escalated_at"] == d(10, 8) and [c["direction"] for c in late["changes"]] == ["up"]
    assert rebuild_timeline([]) == {"ordered": [], "changes": [], "state": None, "escalated_at": None}
    # a planned / future step never becomes the state and makes no label change
    fut = rebuild_timeline(steps[:1] + [dict(step_id=8, step_date=date(2038, 7, 1), one_line="Deliveries end", step_type="planned", label_after="threat",
                                             probability=5, impact=5)])
    assert fut["state"]["step_id"] == steps[0]["step_id"] and fut["changes"] == [], fut
    only_plan = rebuild_timeline([dict(step_id=7, step_date=date(2038, 7, 1), one_line="Plan", step_type="planned", label_after="watch")])
    assert only_plan["state"]["step_id"] == 7
    assert rebuild_timeline(steps[:1])["changes"] == []
    # context snippet
    assert snippet([]) == NONE_ON_RECORD
    assert snippet([{"handle": "T3f9a12c0", "story_key": k1, "last_line": "Contract signed", "last_step_at": d(10, 8)}]) == f"T3f9a12c0: {k1} - Contract signed (2025-10-08)"
    assert set(MOVE_STEP) == set(MOVE_FAMILY) and set(MOVE_FAMILY.values()) <= set(FAMILIES) and set(NEWS_FAMILY.values()) <= set(FAMILIES)
    print("story self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
