"""Stories and steps (docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md A.0.5): code proposes, the model picks, code decides.

A story is one thread of events: competitor (or buyer) + product / subject + counterpart country + event family. Its key is
built by code (`story_key`); the prompt is shown the open stories of that competitor as handles (`snippet`) and answers with
`story_ref` = a handle (T + 8 hex) or "new"; the loader links the card to the story (`pick`: an EXACT KEY MATCH WINS over the
model's answer, in both directions). Every card is one step on its story (staging.story_step). After each step the label is
compared with the previous step's; when it changed, a `label_change` step is written ("watch -> threat: probability 3 -> 5
(contract signed)") and, for an upward change, story.escalated_at is set. All label changes are rebuilt from the steps, so
a re-run or a late-arriving older article gives the same result.

    story_key / handle_of / pick / story_change / card_date          pure (self-checked: python -m prompts.story --selftest)
    python -m prompts.story --backfill-dates [--write]               undated signal steps take the card's publication date (dry run without --write)
    python -m prompts.story --prune [--write]                        steps of cards that no longer exist are deleted, their stories rebuilt
    python -m prompts.story --dedupe-events [--write]                one event = one story / one card (G3): signals of one event join one
                                                                     story, repeat technology cards become status 'duplicate', same-day
                                                                     repeat steps are dropped (dry run without --write)
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
    """pillar:party:subject:country:family with blank parts left blank: competitive:hanwha:k9:pl:
    A competitive story with a product and a buyer country is that programme from selection to contract to delivery, so the event
    family is left out of its key (owner 2026-10-20: 'Norway selects Chunmoo' and 'Norway signs the Chunmoo contract' are one story)."""
    iso = str(country or "").strip().lower()
    iso = iso if re.fullmatch(r"[a-z]{2}", iso) else ""
    fam = family if family in FAMILIES and not (pillar == "competitive" and slug(subject) and iso) else ""
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


GAP_DAYS = 365      # a key match more than this far from the story's steps is another event (BrahMos tests 2010 / 2013 / 2017)


def timed_key(key: str, day, by_key: dict) -> str:
    """The story a card joins by key must be near it in time: `key` or `key:YYYY` whose steps span within GAP_DAYS of the card's
    date; else a free key (`key`, then `key:YYYY`) so a new story starts (kssl-02 2026-10-20). No date -> `key`."""
    if not isinstance(day, date):
        return key
    near = [k for k, st in by_key.items() if (k == key or re.fullmatch(re.escape(key) + r":\d{4}", k))
            and (st.get("first_step_at") is None or st["first_step_at"] - timedelta(days=GAP_DAYS) <= day)
            and (st.get("last_step_at") is None or day <= st["last_step_at"] + timedelta(days=GAP_DAYS))]
    if near:
        return min(near, key=lambda k: abs(((by_key[k].get("last_step_at") or day) - day).days))
    return key if key not in by_key else f"{key}:{day.year}"


# ---- one event reported twice (functional test G3, 2026-10-25) ------------------------------------------------------
# A KNDS release filed under KNDS Germany AND Nexter, a Javelin JV award under RTX AND Lockheed: two signals, two stories,
# two overview cards for one event. Two publishers of one award (the Hanwha K9 contract of 19 Aug: Yonhap + Hanwha's newsroom)
# gave one story two "Contract" steps. Technology cards of one reveal (H38 x3, PERCH 2.0 x3) were separate cards.

STOPWORDS = frozenset("a an the of for to in on and with by from at as its it is are be new first us u s".split())
SAME_EVENT_MOVE = 0.5       # title overlap of two same-day signals on one article that report the same kind of move
SAME_EVENT_ANY = 0.8        # title overlap that makes them one event whatever move each was read as
SAME_DAY_PILLARS = ("competitive", "technology")    # market stories hold several needs of one buyer on one day: left alone
TECH_EVENT_DAYS = 10        # two technology cards of one company family naming the same product this close are one reveal
GENERIC_FIRST = frozenset({"general", "united", "the", "american", "us", "u", "national", "advanced", "china", "israel", "israeli"})
_UNIT = re.compile(r"\d+(?:mm|km|kg|cal|m|t|kw|hp|nm)?\Z|\d+x\d+\Z")


def fold(text) -> str:
    """ASCII lower case ("Ragnarök" -> "ragnarok", "NEŞTER" -> "nester")."""
    import unicodedata
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()


def event_url_key(url) -> str:
    """One key per article: backend.news.url_key (scheme, www., port, trailing slash) after a web.archive.org copy prefix."""
    from backend.news import url_key
    u = re.sub(r"^https?://web\.archive\.org/web/[0-9a-z_]+/", "", str(url or "").strip(), flags=re.I)
    return url_key(u) if u else ""


def title_words(text) -> set:
    t = re.sub(r"(\d)\s+(mm|km|kg|billion|million|bn|m)\b", r"\1\2", fold(text))
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", t) if w not in STOPWORDS and len(w) > 1}


def title_overlap(a, b) -> float:
    """Shared words / words of the shorter title (0..1)."""
    x, y = title_words(a), title_words(b)
    return len(x & y) / min(len(x), len(y)) if x and y else 0.0


def same_signal_event(a: dict, b: dict) -> bool:
    """Two competitive signals {url, date, title, move} are one event: the same article, the same day, and titles that say the
    same thing (overlap >= SAME_EVENT_MOVE with the same move, or >= SAME_EVENT_ANY). One article can carry two events (KNDS at
    MSPO: a shell plant AND the CELERIS 8x8; analisidifesa: Croatia's Leopards AND Portugal's Caesars): their titles differ, so
    they stay apart."""
    ka, kb = event_url_key(a.get("url")), event_url_key(b.get("url"))
    if not ka or ka != kb or a.get("date") is None or a.get("date") != b.get("date"):
        return False
    ov = title_overlap(a.get("title"), b.get("title"))
    return ov >= SAME_EVENT_ANY or (ov >= SAME_EVENT_MOVE and bool(a.get("move")) and a.get("move") == b.get("move"))


def same_day_duplicates(steps: list[dict], pillar) -> list:
    """step_ids of steps that repeat an earlier step of their story: same day, same step type, same kind of card (two publishers
    of one award). The first loaded stays (created_at, then step id). Planned and label_change steps never count; market stories
    are left alone."""
    if pillar not in SAME_DAY_PILLARS:
        return []
    seen, drop = set(), []
    for s in sorted(steps, key=lambda s: (str(s.get("created_at") or ""), str(s.get("step_id")))):
        if s.get("step_type") in ("label_change", "planned") or s.get("step_date") is None:
            continue
        k = (s["step_date"], s.get("step_type"), s.get("source_table"))
        if k in seen:
            drop.append(s["step_id"])
        else:
            seen.add(k)
    return drop


def company_family(name) -> str:
    """"Hanwha Defense USA" -> hanwha, "Rheinmetall Nordic" -> rheinmetall, "General Dynamics Land Systems" -> general dynamics."""
    t = re.findall(r"[a-z0-9]+", fold(name))
    return "" if not t else (" ".join(t[:2]) if t[0] in GENERIC_FIRST else t[0])


def tech_tokens(title, subject, company) -> set:
    """The words of a technology card that can name a product: in the title a designator (H38, FV-014, GMF 140, MK2) or an
    all-capitals word (PERCH, MDACS, LORAS); in the model's story thread (story key subject) any word of 4+ letters. Units and
    calibres (155mm, 120) and the company's own name never count."""
    own = set(re.findall(r"[a-z0-9]+", fold(company)))
    t = unicodedata_ascii(title)
    t = re.sub(r"\b([A-Za-z]{1,4})[- ](\d{1,4}[A-Za-z]?)\b", r"\1\2", t)
    out = set()
    for w in re.findall(r"[A-Za-z0-9]+", t):
        lw = w.lower()
        if len(lw) < 3 or _UNIT.match(lw):
            continue
        if (re.search(r"\d", w) and re.search(r"[A-Za-z]", w)) or (w.isupper() and len(w) >= 3):
            out.add(lw)
    sub = re.sub(r"\b([a-z]{1,4})-(\d{1,4}[a-z]?)\b", r"\1\2", str(subject or ""))
    out |= {w for w in sub.split("-") if len(w) >= 4 and not _UNIT.match(w)}
    # slug() splits a name at a non-ASCII letter ("Ragnarök" -> ragnar-k): a title word whose slug is in the thread is that name
    for w in re.findall(r"\w+", str(title or "")):
        if any(ord(ch) > 127 for ch in w) and len(w) >= 4 and slug(w) and f"-{slug(w)}-" in f"-{subject or ''}-":
            out.add(fold(w))
    return {w for w in out if w not in own and w.rstrip("s") not in own}


def unicodedata_ascii(text) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()


def same_tech_event(a: dict, b: dict, rare) -> str | None:
    """Why two technology cards {url_key, day, family, tokens, story_id} are one event, or None: the same article; or, at most
    TECH_EVENT_DAYS apart, the same story (thread) or the same company family naming the same product word (`rare(word)`: used by
    one company family only)."""
    if a.get("url_key") and a.get("url_key") == b.get("url_key"):
        return "same article"
    if a.get("day") is None or b.get("day") is None or abs((a["day"] - b["day"]).days) > TECH_EVENT_DAYS:
        return None
    if a.get("story_id") is not None and a.get("story_id") == b.get("story_id"):
        return "same story"
    if not a.get("family") or a.get("family") != b.get("family"):
        return None
    common = sorted(w for w in set(a.get("tokens") or ()) & set(b.get("tokens") or ()) if rare(w))
    return f"same product ({', '.join(common)})" if common else None


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
    # the reason is not appended: the step's own one_line already states it, and a reason cut at 50 characters ("full-rate
    # produc…") is what the owner saw (2026-10-25). `why` stays in the signature for the callers.
    return {"direction": direction, "changed": step_line(head)}


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
    """Rewrite the label_change steps, the step numbers and the story's current state from its real steps. A step that repeats
    an earlier one (same_day_duplicates: one event from two publishers) is deleted first."""
    cur.execute("SELECT pillar FROM staging.story WHERE story_id = %s", (story_id,))
    p = cur.fetchone()
    cur.execute("SELECT * FROM staging.story_step WHERE story_id = %s AND step_type <> 'label_change'", (story_id,))
    steps = [dict(r) for r in cur.fetchall()]
    drop = same_day_duplicates(steps, p["pillar"] if p else None)
    if drop:
        cur.execute("DELETE FROM staging.story_step WHERE step_id = ANY(%s)", (drop,))
        steps = [s for s in steps if s["step_id"] not in set(drop)]
    tl = rebuild_timeline(steps)
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
    if source_row_id:
        # one step per card in a story: a re-run that reads the same card as another kind of move ("update" -> "announced")
        # replaces its step instead of adding a second one beside it (owner 22 Oct: the K9 thread listed one article twice)
        cur.execute("""DELETE FROM staging.story_step WHERE story_id = %s AND source_table = %s AND source_row_id = %s
                       AND step_type NOT IN (%s, 'label_change')""", (story_id, source_table, str(source_row_id), step_type))
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


def card_date(row):
    """A signal's step date: the event date the article states; else the article's publication date (signal.yml: "else the
    published date"). The model leaves event_date empty on some cards; the timeline must not show those as "date not stated"
    when the harvested record has the publication date. None only when neither exists."""
    return row.get("event_date") or row.get("published_date")


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
                step_type=MOVE_STEP.get(move, "update"), date=card_date(row), line=row.get("title"), url=det.get("source_url"), move=move,
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
    if p["pillar"] == "competitive" and not slug(p["subject"]):
        # no product named: 'competitive:hanwha:::programme' would join every such event of the competitor (Redback, an 8x8 howitzer and
        # a USV in one story, owner 2026-10-20). Such a card is its own story unless the model names an open story's handle.
        key += f":{table}:{row[keycol]}"
    by_handle, by_key = _stories_for_resolution(cur, p["pillar"], p["competitor_id"], p["buyer_name"])
    if p["pillar"] == "competitive":
        key = timed_key(key, p["date"], by_key)
    hit, how, warn = pick(tr.get("story_ref"), key, by_handle, by_key)
    if warn and warnings is not None:
        warnings.append(f"story: {warn}")
    same = same_event_story(cur, table, row, p)
    if same is not None:                          # the same event is already a story (a sister company / JV partner's card)
        story_id = same
    elif hit is not None:
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


def same_event_story(cur, table: str, row: dict, p: dict) -> int | None:
    """The story of another competitive signal (any competitor) that reports this same event (same_signal_event), else None."""
    if table != "competitive_signal" or not p.get("url") or p.get("date") is None:
        return None
    cur.execute("""SELECT s.story_id, s.title, d.source_url, d.glance_move FROM staging.competitive_signal s
                   JOIN staging.competitive_signal_detail d ON d.signal_id = s.signal_id
                   WHERE s.signal_id::text <> %s AND s.story_id IS NOT NULL AND coalesce(s.event_date, s.published_date) = %s
                   ORDER BY s.story_id""", (str(row["signal_id"]), p["date"]))
    me = {"url": p["url"], "date": p["date"], "title": p.get("line"), "move": p.get("move")}
    for r in cur.fetchall():
        if same_signal_event(me, {"url": r["source_url"], "date": p["date"], "title": r["title"], "move": r["glance_move"]}):
            return r["story_id"]
    return None


def _rebuild_or_drop(cur, story_id) -> str:
    """A story a card left: rebuilt while it has a step or a card (or project) still points at it, else deleted."""
    cur.execute("SELECT count(*) AS n FROM staging.story_step WHERE story_id = %s AND step_type <> 'label_change'", (story_id,))
    if cur.fetchone()["n"]:
        rebuild_story(cur, story_id)
        return "rebuilt"
    cur.execute(" UNION ALL ".join(f"(SELECT 1 FROM staging.{tb} WHERE story_id = %(s)s LIMIT 1)" for tb in (*CARDS, "competitive_project")),
                {"s": story_id})
    if cur.fetchone() is not None:
        rebuild_story(cur, story_id)
        return "kept"
    cur.execute("DELETE FROM staging.story_step WHERE story_id = %s", (story_id,))
    cur.execute("DELETE FROM staging.story WHERE story_id = %s", (story_id,))
    return "deleted"


def move_card(cur, table: str, row_id, target) -> dict:
    """Put a stored card into story `target`: its steps move there (step ids re-keyed, created_at kept so the first-loaded rule
    still holds), the card's story_id is set, the target is rebuilt (same-day repeats dropped) and each story it left is rebuilt
    or, left empty, deleted. Returns {left_story_id: rebuilt | kept | deleted}."""
    keycol, _ = CARDS[table]
    cur.execute(f"SELECT story_id FROM staging.{table} WHERE {keycol}::text = %s", (str(row_id),))
    r = cur.fetchone()
    left = {r["story_id"]} if r and r["story_id"] is not None and r["story_id"] != target else set()
    cur.execute("""SELECT * FROM staging.story_step WHERE source_table = %s AND source_row_id = %s AND step_type <> 'label_change'
                   AND story_id <> %s""", (table, str(row_id), target))
    for s in cur.fetchall():
        left.add(s["story_id"])
        cur.execute("DELETE FROM staging.story_step WHERE step_id = %s", (s["step_id"],))
        cur.execute("""INSERT INTO staging.story_step (step_id, story_id, step_no, step_date, step_type, one_line, changed, source_url, source_table,
                                                       source_row_id, probability, impact, label_after, run_id, created_at, date_precision)
                       VALUES (%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (step_id) DO NOTHING""",
                    (_step_id(target, table, str(row_id), s["step_type"]), target, s["step_date"], s["step_type"], s["one_line"], s["changed"],
                     s["source_url"], table, str(row_id), s["probability"], s["impact"], s["label_after"], s["run_id"], s["created_at"],
                     s.get("date_precision")))
    cur.execute(f"UPDATE staging.{table} SET story_id = %s WHERE {keycol}::text = %s", (target, str(row_id)))
    rebuild_story(cur, target)
    return {sid: _rebuild_or_drop(cur, sid) for sid in sorted(left)}


# ---- technology: one card per reveal --------------------------------------------------------------------------------

DUPLICATE = "duplicate"      # technology_overview_article.status of a card that repeats another (the live site leaves it out)


def tech_cards(cur) -> list[dict]:
    """Every active / duplicate technology card with what same_tech_event reads."""
    cur.execute("""SELECT a.overview_article_id AS id, a.title, a.status, a.story_id, a.image_url, a.created_at,
                          coalesce(a.article_date, a.published_on) AS day, s.story_key,
                          (SELECT c.display_name FROM staging.technology_company c WHERE c.company_id = a.primary_company_id
                            ORDER BY c.display_name LIMIT 1) AS company,
                          (SELECT ts.source_url FROM staging.technology_overview_source o JOIN staging.technology_source ts ON ts.source_id = o.source_id
                            WHERE o.overview_article_id = a.overview_article_id ORDER BY o.is_primary DESC NULLS LAST, o.display_order LIMIT 1) AS url
                   FROM staging.technology_overview_article a LEFT JOIN staging.story s ON s.story_id = a.story_id
                   WHERE coalesce(a.status, 'active') IN ('active', %s)""", (DUPLICATE,))
    out = []
    for r in cur.fetchall():
        key = r["story_key"] or ""
        subject = key.split(":")[2] if key.count(":") >= 2 else ""
        out.append({**dict(r), "url_key": event_url_key(r["url"]), "family": company_family(r["company"]),
                    "tokens": tech_tokens(r["title"], subject, r["company"])})
    return out


def tech_clusters(cards: list[dict]) -> list[list[dict]]:
    """Groups (2+) of cards that are one event (same_tech_event, joined transitively), each sorted keeper first: the earliest
    date, then a card with an image, then the first loaded, then the id. A product word is rare when one company family uses it."""
    fams: dict = {}
    for c in cards:
        for w in c["tokens"]:
            fams.setdefault(w, set()).add(c["family"])

    def rare(w):
        return len(fams.get(w, ())) <= 1 and not w.isdigit()
    parent = {c["id"]: c["id"] for c in cards}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, a in enumerate(cards):
        for b in cards[i + 1:]:
            if find(a["id"]) != find(b["id"]) and same_tech_event(a, b, rare):
                parent[find(b["id"])] = find(a["id"])
    groups: dict = {}
    for c in cards:
        groups.setdefault(find(c["id"]), []).append(c)

    def order(c):
        return (c["day"] or date.max, 0 if c.get("image_url") else 1, str(c.get("created_at") or ""), str(c["id"]))
    return [sorted(g, key=order) for g in groups.values() if len(g) > 1]


def dedupe_tech(cur, only_ids=None, show: bool = False) -> dict:
    """One technology card per event: in each tech_clusters group the keeper is 'active' and the others 'duplicate' and in the
    keeper's story. `only_ids`: touch only groups holding one of these cards (a prompt run). A card no longer in any group goes
    back to 'active'. Returns counts."""
    cards = tech_cards(cur)
    only = {str(i) for i in only_ids} if only_ids is not None else None
    n = {"groups": 0, "duplicate": 0, "restored": 0, "moved": 0}
    grouped = set()
    for g in tech_clusters(cards):
        ids = {str(c["id"]) for c in g}
        grouped |= ids
        if only is not None and not ids & only:
            continue
        n["groups"] += 1
        keep = g[0]
        if show:
            print(f"  keep {keep['id']} {keep['day']} {str(keep['title'])[:90]}")
            for c in g[1:]:
                print(f"    dup {c['id']} {c['day']} {str(c['title'])[:90]}")
        if keep["status"] == DUPLICATE:
            cur.execute("UPDATE staging.technology_overview_article SET status = 'active' WHERE overview_article_id = %s", (keep["id"],))
        for c in g[1:]:
            if c["status"] != DUPLICATE:
                cur.execute("UPDATE staging.technology_overview_article SET status = %s WHERE overview_article_id = %s", (DUPLICATE, c["id"]))
                n["duplicate"] += 1
            if keep["story_id"] is not None and c["story_id"] != keep["story_id"]:
                move_card(cur, "technology_overview_article", c["id"], keep["story_id"])
                n["moved"] += 1
    for c in cards:
        if c["status"] == DUPLICATE and str(c["id"]) not in grouped and (only is None or str(c["id"]) in only):
            cur.execute("UPDATE staging.technology_overview_article SET status = 'active' WHERE overview_article_id = %s", (c["id"],))
            n["restored"] += 1
    return n


def merge_signal_events(cur) -> list[tuple]:
    """Competitive signals of one event in different stories (same_signal_event): each later story's signal moves into the story
    created first. Returns [(signal_id, from_story, to_story)]."""
    cur.execute("""SELECT s.signal_id::text AS id, s.story_id, s.title, coalesce(s.event_date, s.published_date) AS day, d.source_url, d.glance_move,
                          st.created_at AS story_created
                   FROM staging.competitive_signal s JOIN staging.competitive_signal_detail d ON d.signal_id = s.signal_id
                   JOIN staging.story st ON st.story_id = s.story_id
                   WHERE d.source_url IS NOT NULL AND coalesce(s.event_date, s.published_date) IS NOT NULL""")
    by: dict = {}
    for r in cur.fetchall():
        by.setdefault((event_url_key(r["source_url"]), r["day"]), []).append(dict(r))

    def ev(r):
        return {"url": r["source_url"], "date": r["day"], "title": r["title"], "move": r["glance_move"]}
    moves = []
    for grp in by.values():
        if len({r["story_id"] for r in grp}) < 2:
            continue
        grp.sort(key=lambda r: (str(r["story_created"]), r["story_id"]))
        for i, b in enumerate(grp):
            for a in grp[:i]:
                if a["story_id"] != b["story_id"] and same_signal_event(ev(a), ev(b)):
                    moves.append((b["id"], b["story_id"], a["story_id"], b["title"]))
                    b["story_id"] = a["story_id"]
                    break
    for sid, _from, to, _t in moves:
        move_card(cur, "competitive_signal", sid, to)
    return moves


def repair_events(write: bool = False) -> dict:
    """One-off repair (G3): signals of one event join one story, one card per technology event, same-day repeat steps dropped.
    Dry run (rolled back) unless write=True. Refuses any database but kssl_staging / kssl_test_*."""
    from prompts.run import connect
    conn = connect()
    dup_q = """SELECT count(*) AS n FROM (SELECT 1 FROM staging.story_step st JOIN staging.story s USING (story_id)
               WHERE s.pillar IN ('competitive', 'technology') AND st.step_type NOT IN ('label_change', 'planned') AND st.step_date IS NOT NULL
               GROUP BY st.story_id, st.step_date, st.step_type, st.source_table HAVING count(*) > 1) x"""
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS d")
        db = cur.fetchone()["d"]
        if db != "kssl_staging" and not db.startswith("kssl_test"):
            raise SystemExit(f"refused: database {db} (kssl_staging or kssl_test_* only)")
        cur.execute(dup_q)
        before = cur.fetchone()["n"]
        moves = merge_signal_events(cur)
        print(f"signals moved into the story of the same event: {len(moves)}")
        for m in moves:
            print(f"  {m[0]}  story {m[1]} -> {m[2]}  {str(m[3])[:80]}")
        print("technology groups:")
        tech = dedupe_tech(cur, show=True)
        cur.execute("""SELECT DISTINCT st.story_id FROM staging.story_step st JOIN staging.story s USING (story_id)
                       WHERE s.pillar IN ('competitive', 'technology') AND st.step_type NOT IN ('label_change', 'planned') AND st.step_date IS NOT NULL
                       GROUP BY st.story_id, st.step_date, st.step_type, st.source_table HAVING count(*) > 1""")
        for r in cur.fetchall():
            rebuild_story(cur, r["story_id"])
        cur.execute(dup_q)
        after = cur.fetchone()["n"]
        print(f"technology: {tech}")
        print(f"same-day repeat step groups: {before} -> {after}" + ("" if write else "  (dry run, rolled back: --write to apply)"))
        if write:
            conn.commit()
        else:
            conn.rollback()
    conn.close()
    return {"signal_moves": moves, "tech": tech, "same_day_step_groups": (before, after)}


# ---- self-check ---------------------------------------------------------------------------------------------------

def _selftest() -> None:
    # keys: blank parts stay blank; the country must be an ISO code; an unknown family is blank
    assert story_key("competitive", "Hanwha", "K9", "PL", "order") == "competitive:hanwha:k9:pl:"           # a programme: no family
    assert story_key("competitive", "Hanwha", "K9", "", "order") == "competitive:hanwha:k9::order"
    assert story_key("competitive", "Hanwha Aerospace", "", "", "order") == "competitive:hanwha-aerospace:::order"
    assert story_key("competitive", "Nordvik", "NV-155", "Veland", "weird") == "competitive:nordvik:nv-155::"
    assert story_key("market", None, None, "in", "demand") == "market:::in:demand"
    # ids and handles are stable and differ per key
    k1, k2 = "competitive:a:b::order", "competitive:a:b::delivery"
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
    # a key match is bounded in time: near steps join, a year-plus gap starts key:YYYY, which later cards of that time then join
    bk = {"competitive:b:x:in:": {"first_step_at": date(2010, 3, 1), "last_step_at": date(2010, 12, 1)},
          "competitive:b:x:in::2017": {"first_step_at": date(2017, 5, 1), "last_step_at": date(2017, 5, 1)}}
    assert timed_key("competitive:b:x:in:", date(2011, 6, 1), bk) == "competitive:b:x:in:"
    assert timed_key("competitive:b:x:in:", date(2013, 11, 1), bk) == "competitive:b:x:in::2013"
    assert timed_key("competitive:b:x:in:", date(2017, 9, 1), bk) == "competitive:b:x:in::2017"
    assert timed_key("competitive:b:x:in:", None, bk) == "competitive:b:x:in:" and timed_key("competitive:c::in:", date(2020, 1, 1), bk) == "competitive:c::in:"
    # step_line
    assert step_line("  a   b ") == "a b" and step_line(None) is None and len(step_line("x" * 300)) == MAX_LINE and step_line("x" * 300).endswith("…")
    # story_change: up, down, same, unknown, text
    c = story_change("watch", "threat", 3, 5, 3, 5, "contract signed")
    assert c == {"direction": "up", "changed": "watch -> threat: probability 3 -> 5, impact 3 -> 5"}, c          # no cut-off reason
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
    assert tl["changes"][0]["changed"] == "watch -> threat: probability 3 -> 5, impact 4 -> 5" and tl["escalated_at"] == d(10, 8)
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
    # a signal step date: the event date wins; the publication date fills an empty one; neither -> None
    assert card_date({"event_date": date(2026, 4, 1), "published_date": date(2026, 4, 2)}) == date(2026, 4, 1)
    assert card_date({"event_date": None, "published_date": date(2026, 4, 2)}) == date(2026, 4, 2)
    assert card_date({}) is None and card_date({"event_date": None, "published_date": None}) is None
    # one event reported twice (G3): same article + same day + same words; an archive copy is the same article
    day = date(2026, 9, 17)
    u = "https://knds.com/en/press-releases/thl-20-turrets-selected/"
    assert event_url_key("https://web.archive.org/web/20261015003304/https://www.knds.com/en/press-releases/thl-20-turrets-selected") == event_url_key(u)
    s1 = {"url": u, "date": day, "title": "Veland THL20 turrets selected for the new helicopter", "move": "Selection"}
    assert same_signal_event(s1, dict(s1, url="http://www.knds.com/en/press-releases/thl-20-turrets-selected"))
    assert same_signal_event({"url": u, "date": day, "title": "Army awards the Javelin Joint Venture $1.3B contract", "move": "Contract"},
                             {"url": u, "date": day, "title": "Army awards Javelin Joint Venture $1.3 billion contract for missiles", "move": "Contract"})
    assert not same_signal_event(s1, dict(s1, date=date(2026, 9, 18)))                                   # another day
    assert not same_signal_event(s1, dict(s1, url="https://knds.com/en/press-releases/other"))           # another article
    assert not same_signal_event({"url": u, "date": day, "title": "Nordvik sets up local shell production in Veland", "move": "Capacity"},
                                 {"url": u, "date": day, "title": "Nordvik unveils 8x8 platform for wheeled combat vehicles", "move": "Launch"})
    mid = {"url": u, "date": day, "title": "Veland Army fields first Bradley IFV with Iron Fist to counter drones and missiles", "move": "Delivery"}
    other = "Veland Army fields first Bradley infantry fighting vehicles with Iron Fist active protection"
    assert 0.5 <= title_overlap(mid["title"], other) < 0.8 and same_signal_event(mid, dict(mid, title=other))     # same move
    assert not same_signal_event(mid, dict(mid, title=other, move="Capacity"))
    assert title_overlap("", "x") == 0.0 and title_overlap("155 mm gun", "155mm gun") == 1.0
    # same-day repeat steps: the first loaded stays; another type, another day, a planned step or a market story stay
    st = [dict(step_id=1, step_date=day, step_type="contract", source_table="competitive_signal", created_at="2026-10-01"),
          dict(step_id=2, step_date=day, step_type="contract", source_table="competitive_signal", created_at="2026-10-02"),
          dict(step_id=3, step_date=day, step_type="trial", source_table="competitive_signal", created_at="2026-10-03"),
          dict(step_id=4, step_date=day, step_type="contract", source_table="competitive_project_timeline", created_at="2026-10-04"),
          dict(step_id=5, step_date=None, step_type="contract", source_table="competitive_signal", created_at="2026-10-05"),
          dict(step_id=6, step_date=None, step_type="contract", source_table="competitive_signal", created_at="2026-10-06"),
          dict(step_id=7, step_date=day, step_type="planned", source_table="competitive_signal", created_at="2026-10-07"),
          dict(step_id=8, step_date=day, step_type="planned", source_table="competitive_signal", created_at="2026-10-08")]
    assert same_day_duplicates(st, "competitive") == [2] and same_day_duplicates(list(reversed(st)), "technology") == [2]
    assert same_day_duplicates(st, "market") == [] and same_day_duplicates([], "competitive") == []
    # technology: one reveal from three publishers is one event; the company's own name, units and other families never match
    assert company_family("Hanwha Defense USA") == "hanwha" == company_family("Hanwha") and company_family("General Dynamics Land Systems") == "general dynamics"
    assert company_family("Rheinmetall Nordic") == "rheinmetall" and company_family(None) == ""
    tk = tech_tokens("Nordvik shows H38 medium vessel with PERCH 2.0 and 155mm gun", "h38-unmanned-vessel", "Nordvik Defence")
    assert {"h38", "perch", "unmanned", "vessel"} <= tk and not tk & {"155mm", "nordvik", "defence", "medium", "shows"}, tk
    assert "ragnarok" in tech_tokens("Rheinmetall demonstrates its 120 mm Ragnarök mortar", "ragnar-k-120-mm-mortar", "Rheinmetall")
    assert "refuels" not in tech_tokens("Robot Refuels a Drone Boat at Sea in US Navy Test", "", "Sealartec")
    assert {"fv014", "gmf140"} <= tech_tokens("Veland FV-014 and GMF 140 shown", "", "Veland")
    a = {"url_key": "a.com/x", "day": date(2026, 10, 12), "family": "nordvik", "tokens": {"h38", "vessel"}}
    b = {"url_key": "b.com/y", "day": date(2026, 10, 15), "family": "nordvik", "tokens": {"h38", "vessel"}}
    rare = lambda w: w == "h38"   # noqa: E731
    assert same_tech_event(a, b, rare) == "same product (h38)"
    assert same_tech_event(a, dict(b, url_key="a.com/x", family="other"), rare) == "same article"
    assert same_tech_event(a, dict(b, day=date(2026, 11, 1)), rare) is None                               # 20 days apart
    assert same_tech_event(a, dict(b, family="veland"), rare) is None and same_tech_event(a, dict(b, tokens={"vessel"}), rare) is None
    assert same_tech_event(dict(a, story_id=7), dict(b, story_id=7, family="veland", tokens=set()), rare) == "same story"
    assert same_tech_event(dict(a, story_id=7), dict(b, story_id=7, day=date(2026, 12, 1)), rare) is None              # a thread, months apart
    cl = tech_clusters([dict(id=1, title="t", day=date(2026, 10, 15), family="n", tokens={"h38"}, url_key="u1", image_url=None, created_at="1"),
                        dict(id=2, title="t", day=date(2026, 10, 12), family="n", tokens={"h38"}, url_key="u2", image_url=None, created_at="2"),
                        dict(id=3, title="t", day=date(2026, 10, 12), family="n", tokens={"h38"}, url_key="u3", image_url="x", created_at="3"),
                        dict(id=4, title="t", day=date(2026, 10, 12), family="m", tokens={"zz9"}, url_key="u4", image_url=None, created_at="4")])
    assert [[c["id"] for c in g] for g in cl] == [[3, 2, 1]], cl                    # earliest day, then the one with a picture
    print("story self-check ok")


def backfill_step_dates(write: bool = False) -> int:
    """Undated signal steps whose card has a publication date: set step_date from it, then rebuild each touched story (order,
    step numbers, label changes, current state). Dry run unless write=True. KSSL_STAGING_DSN picks the database."""
    from prompts.run import connect
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("""SELECT st.step_id, st.story_id, s.published_date FROM staging.story_step st
                       JOIN staging.competitive_signal s ON s.signal_id::text = st.source_row_id
                       WHERE st.source_table = 'competitive_signal' AND st.step_type <> 'label_change'
                         AND st.step_date IS NULL AND s.published_date IS NOT NULL""")
        rows = cur.fetchall()
        stories = sorted({r["story_id"] for r in rows})
        print(f"{len(rows)} undated signal steps get their publication date; {len(stories)} stories are rebuilt" + ("" if write else "  (dry run: --write to apply)"))
        if write:
            for r in rows:
                cur.execute("UPDATE staging.story_step SET step_date = %s WHERE step_id = %s", (r["published_date"], r["step_id"]))
            for sid in stories:
                rebuild_story(cur, sid)
            conn.commit()
    conn.close()
    return len(rows)


def prune_orphans(write: bool = False) -> int:
    """Steps whose card no longer exists (a re-run gave the card a new id, a purge deleted it): deleted, each touched story
    rebuilt, and a story left with no step and no card deleted. Without this a timeline shows the gone card as a ghost step
    (an undated duplicate of a live step). Dry run unless write=True."""
    from prompts.run import connect
    gone = " OR ".join(f"(t.source_table = '{tb}' AND NOT EXISTS (SELECT 1 FROM staging.{tb} c WHERE c.{col}::text = t.source_row_id))"
                       for tb, (col, _fn) in CARDS.items())
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(f"SELECT t.step_id, t.story_id FROM staging.story_step t WHERE t.step_type <> 'label_change' AND ({gone})")
        rows = cur.fetchall()
        stories = sorted({r["story_id"] for r in rows})
        print(f"{len(rows)} steps of gone cards; {len(stories)} stories touched" + ("" if write else "  (dry run: --write to apply)"))
        if write:
            cur.execute("DELETE FROM staging.story_step WHERE step_id = ANY(%s)", ([r["step_id"] for r in rows],))
            empty = 0
            for sid in stories:
                cur.execute("SELECT count(*) AS n FROM staging.story_step WHERE story_id = %s AND step_type <> 'label_change'", (sid,))
                if cur.fetchone()["n"]:
                    rebuild_story(cur, sid)
                    continue
                cur.execute(" UNION ALL ".join(f"(SELECT 1 FROM staging.{tb} WHERE story_id = %(s)s LIMIT 1)" for tb in CARDS), {"s": sid})
                if cur.fetchone() is None:              # no step and no card left: the story itself is gone
                    cur.execute("DELETE FROM staging.story_step WHERE story_id = %s", (sid,))
                    cur.execute("DELETE FROM staging.story WHERE story_id = %s", (sid,))
                    empty += 1
            print(f"  deleted {len(rows)} steps, {empty} empty stories")
            conn.commit()
    conn.close()
    return len(rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--backfill-dates" in sys.argv:
        backfill_step_dates(write="--write" in sys.argv)
    elif "--prune" in sys.argv:
        prune_orphans(write="--write" in sys.argv)
    elif "--dedupe-events" in sys.argv:
        repair_events(write="--write" in sys.argv)
    else:
        print(__doc__)
