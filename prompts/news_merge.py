"""Apply the answer of the `news` prompt (prompts/news.yml): staging.news_candidate -> story rows.

    python -m prompts.news_merge --selftest        (no DB, no network)

The model only says which candidates (handles C<8 hex>) report the same EVENT (company news and its products'
news may be in one story), which stored stories (handles S<8 hex>) it already is, and the category. Code does the rest:
  1. validate the answer (unknown / repeated handle dropped, bad category = story dropped, candidates stay 'new').
     relevant = "no" (the story is not about the company) -> category forced to Other and a fact_source judgement
     column 'not_about_company' (the reason) on the row; the row is stored, signal never uses it (it skips Other)
  2. union-find: model groups + the code's pre_group copies + the same article url under two owners = one story
  3. main article of the story = best source (rank_core: not blocked / paywalled, then official or company site >
     wire (Reuters, PTI, ANI, Yonhap, AFP, AP) > national press > others, headline names the company, earliest date,
     has an image, earliest found). A later article of a stored story that ranks better re-picks the main (row id kept)
  4. write the story to the COMPANY news table always, and to the product news table once per product that has an
     article in it (or a stored row of the event): same main article, category and reason; row id = row_id(main url, owner)
     (= the main candidate's id for its own owner). A stored story of the event (same_as) is extended, not replaced;
     a table that has no row of the event yet gets a copy of the stored one.
  5. fact_source rows per row (table_name = that table, row_id = id text; Approve copies them, Trace lists them):
       article_url, image_local_path, also_reported_by (one per other publisher), category (judgement)
  6. candidates -> story_table / story_id of their OWN owner's row; status 'story' (it is that row's main
     article) or 'merged' (an extra source)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date

from backend.sources import hard_to_fetch, outlet_rank

CATEGORIES = ["Contract & order", "Partnership / JV", "Product launch & testing", "Delivery & induction", "Export",
              "Financial results", "Stock & market", "Facility & capacity", "Leadership & corporate",
              "Non-defence business", "Other"]
JUDGEMENT = "judgement"                    # same marker prompts/loader.py writes for a _reason
NOT_ABOUT = "not_about_company"            # fact_source column name of the "this story is not about the company" judgement
WINDOW_DAYS = 21                           # a stored story is shown / matched when it is within this many days of a new article
TABLES = {None: ("competitive_news_article", "article_id"), "product": ("competitive_product_news", "product_news_id")}


@dataclass
class Cand:
    id: str
    product_id: str | None
    headline: str
    url: str
    date: date | None = None
    publisher: str | None = None
    image_url: str | None = None
    image_local_path: str | None = None
    tier: str | None = None
    pre_group: str | None = None
    found_at: object = 0
    match_via: str | None = None             # headline | page | own site (None = unknown)
    page_note: str | None = None             # "http 401" ...: the page could not be read


@dataclass
class Result:
    rows: int = 0
    loaded: list = field(default_factory=list)       # [(table, id, True)]
    warnings: list = field(default_factory=list)
    skip_reason: str | None = None
    note: str = ""
    details: dict = field(default_factory=dict)


# ---- pure logic ---------------------------------------------------------------------------------------------

def handle(prefix: str, id_: str) -> str:
    return prefix + str(id_).replace("-", "")[:8]


def handle_map(items: dict, prefix: str) -> tuple[dict, set]:
    """{handle: item} from {id: item}, and the handles two items share (never resolved: the model cannot tell them apart)."""
    out, bad = {}, set()
    for id_, it in items.items():
        h = handle(prefix, id_)
        if h in out:
            bad.add(h)
        out[h] = it
    return {h: v for h, v in out.items() if h not in bad}, bad


def norm_handle(h) -> str:
    h = str(h or "").strip()
    return h[:1].upper() + h[1:].lower()


def canon_category(c) -> str | None:
    return next((x for x in CATEGORIES if x.lower() == str(c or "").strip().lower()), None)


def rank_core(c: Cand) -> tuple:
    """How good a source is as the story's main article (smaller = better):
    not blocked / paywalled (the signal run fetches the main page), outlet (0 official or company site, 1 wire agency,
    2 national press, 3 others), the headline names the company, earliest date (none last), has an image."""
    blocked = bool(c.page_note) or hard_to_fetch(c.url)
    return (blocked, outlet_rank(c.url, c.tier), c.match_via == "page", c.date is None, c.date or date.max,
            not (c.image_local_path or c.image_url))


def rank_key(c: Cand) -> tuple:
    """Main article first: rank_core, then earliest found."""
    return (*rank_core(c), c.found_at, c.id)


def stored_as_cand(row: dict) -> Cand:
    """A stored story row as a Cand, to compare its main article with a newcomer."""
    return Cand(id=row.get("id") or "", product_id=row.get("product_id"), headline=row.get("headline") or "",
                url=row.get("url") or "", date=row.get("date"), publisher=row.get("publisher"),
                image_url=row.get("image_url"), image_local_path=row.get("image_local_path"), tier=row.get("tier"))


def beats_stored(best: Cand, row: dict) -> bool:
    """Is `best` (the newcomers' best article) a better main article than the stored row's? Ties keep the stored one."""
    return bool(row.get("url")) and best.url != row["url"] and rank_core(best) < rank_core(stored_as_cand(row))


def in_window(day, cand_days, days: int = WINDOW_DAYS) -> bool:
    """A stored story's date is within `days` of any of the batch's candidate dates (mirrors the SQL below / news.yml)."""
    return day is not None and any(d is not None and abs((day - d).days) <= days for d in cand_days)


def relevant(x) -> bool | None:
    """The model's `relevant` field: yes / no (also true / false); anything else (missing) = None = treated as yes."""
    if isinstance(x, bool):
        return x
    t = str(x or "").strip().lower()
    return True if t in ("yes", "true", "y") else False if t in ("no", "false", "n") else None


def validate_records(env: dict, cands: dict, stored: dict, warns: list) -> list[dict]:
    """The model's records -> [{ids, category, reasons, same_as [stored row dicts], not_about (reason or None)}].
    A story with relevant = no is kept, with category forced to Other.
    cands / stored: {handle: Cand} / {handle: stored row dict}."""
    recs = env.get("records")
    if not isinstance(recs, list):
        warns.append("records is not a list")
        return []
    out, seen = [], set()
    for i, r in enumerate(recs):
        v = r.get("values") if isinstance(r, dict) and r.get("table") == "news_story" else None
        if not isinstance(v, dict) or not isinstance(v.get("candidates"), list):
            warns.append(f"records[{i}]: not a news_story with a candidates list, ignored")
            continue
        cat = canon_category(v.get("category"))
        if not cat:
            warns.append(f"records[{i}]: category {v.get('category')!r} is not allowed; story dropped, its articles stay new")
            continue
        ids = []
        for h in v["candidates"]:
            c = cands.get(norm_handle(h))
            if c is None:
                warns.append(f"records[{i}]: unknown or ambiguous handle {h!r} dropped")
            elif c.id in seen:
                warns.append(f"records[{i}]: {h} is already in an earlier story; kept there")
            else:
                seen.add(c.id)
                ids.append(c.id)
        if not ids:
            continue
        same = v.get("same_as")
        same = [] if same in (None, "", "null") else (same if isinstance(same, list) else [same])
        rows = []
        for h in same:
            row = stored.get(norm_handle(h))
            if row is None:
                warns.append(f"records[{i}]: same_as {h!r} is not a stored story; ignored")
            elif row not in rows:
                rows.append(row)
        reasons = {k: x.strip() for k, x in (v.get("_reason") or {}).items() if isinstance(x, str) and x.strip()}
        not_about = None
        if relevant(v.get("relevant")) is False:                      # stored, but marked: category Other + a judgement row
            not_about = reasons.get("relevant") or reasons.get("category") or "the model judged the story not about the company"
            if "relevant" not in reasons:
                warns.append(f"records[{i}]: relevant = no without _reason")
            reasons["category"] = "Not about the company, so Other" + (f" (the model's category: {cat})" if cat != "Other" else "") + ": " + not_about
            cat = "Other"
        elif "category" not in reasons:
            warns.append(f"records[{i}]: category without _reason")
        out.append({"ids": ids, "category": cat, "reasons": reasons, "same_as": rows, "not_about": not_about})
    return out


def plan_stories(stories: list[dict], cands: dict, warns: list) -> tuple[list[dict], list[str]]:
    """cands: {id: Cand} (every 'new' candidate of the competitor). Returns (plans, ids left undecided).
    plan = {members [Cand, main first], category, reasons, stored [row dicts]}. A story may mix owners."""
    parent = {c: c for c in cands}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(b)] = find(a)

    for s in stories:
        for x in s["ids"][1:]:
            union(s["ids"][0], x)
    by_url: dict = {}
    for c in cands.values():
        if c.pre_group in cands:                     # code-known copies are one story whatever the model said
            union(c.pre_group, c.id)
        if c.url in by_url:                          # the same article under two owners is one event
            union(by_url[c.url], c.id)
        by_url.setdefault(c.url, c.id)
    meta: dict = {}
    for s in stories:
        root = find(s["ids"][0])
        m = meta.get(root)
        if m is None:
            meta[root] = {**s, "same_as": list(s["same_as"])}
            continue
        m["same_as"] += [r for r in s["same_as"] if r not in m["same_as"]]
        if m.get("not_about") and not s.get("not_about"):           # joined stories: "not about" only if every part says so
            m.update(category=s["category"], reasons=s["reasons"], not_about=None)
    groups: dict = {}
    for cid in cands:
        groups.setdefault(find(cid), []).append(cands[cid])
    plans, left = [], []
    for root, members in groups.items():
        if root not in meta:
            left += [m.id for m in members]
            continue
        m = meta[root]
        plans.append({"members": sorted(members, key=rank_key), "category": m["category"], "reasons": m["reasons"],
                      "stored": m["same_as"], "not_about": m.get("not_about")})
    return plans, left


def image_source(members: list[Cand]) -> Cand | None:
    """The main article's image, else the first member (in rank order) that has one."""
    return next((c for c in members if c.image_local_path or c.image_url), None)


def owners_of(plan: dict) -> list:
    """Where a story is written: the company (None) first, then every product that has an article in it or a stored row."""
    prods = {c.product_id for c in plan["members"] if c.product_id} | {r["product_id"] for r in plan["stored"] if r["product_id"]}
    return [None] + sorted(prods)


# ---- database -----------------------------------------------------------------------------------------------

def _fact(cur, table, rid, col, url, tier, publisher, quote=None):
    cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, "
                "retrieved_at) VALUES (%s, %s, %s, %s, %s, %s, %s, now())", (table, rid, col, url, tier, publisher, quote))


def _judgement(cur, table, rid, col, reason):
    cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s AND column_name = %s AND source_url = %s",
                (table, rid, col, JUDGEMENT))
    if reason:
        _fact(cur, table, rid, col, JUDGEMENT, JUDGEMENT, None, reason)


def _also(cur, table, rid, others: list[Cand]):
    cur.execute("SELECT source_url FROM staging.fact_source WHERE table_name = %s AND row_id = %s "
                "AND column_name IN ('article_url', 'also_reported_by')", (table, rid))
    have = {r["source_url"] for r in cur.fetchall()}
    for c in others:
        if c.url not in have:
            have.add(c.url)
            _fact(cur, table, rid, "also_reported_by", c.url, c.tier, c.publisher, c.headline)


def _exists(cur, table, idcol, rid) -> bool:
    cur.execute(f"SELECT 1 FROM staging.{table} WHERE {idcol} = %s", (rid,))
    return cur.fetchone() is not None


def _new_row(cur, owner, comp_id, rid, head, url, day, pub, img_url, cat):
    if owner:
        cur.execute("INSERT INTO staging.competitive_product_news (product_news_id, product_id, headline, article_url, "
                    "published_date, publisher, category) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (rid, owner, head[:300], url, day, pub, cat))
    else:
        cur.execute("INSERT INTO staging.competitive_news_article (article_id, competitor_id, headline, article_url, "
                    "published_date, publisher, image_url, category) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (rid, comp_id, head[:300], url, day, pub, img_url, cat))


def _repick(cur, table: str, idcol: str, rid: str, row: dict, main: Cand, img: Cand | None) -> None:
    """A later article of the same event is a better main article than the stored one: the row (id kept) now shows
    the new main; the old main becomes an also_reported_by source."""
    if table == "competitive_news_article":
        cur.execute("UPDATE staging.competitive_news_article SET headline = %s, article_url = %s, published_date = %s, "
                    "publisher = %s, image_url = COALESCE(%s, image_url) WHERE article_id = %s",
                    (main.headline[:300], main.url, main.date, (main.publisher or None) and main.publisher[:200],
                     img.image_url if img else None, rid))
    else:
        cur.execute("UPDATE staging.competitive_product_news SET headline = %s, article_url = %s, published_date = %s, "
                    "publisher = %s WHERE product_news_id = %s",
                    (main.headline[:300], main.url, main.date, (main.publisher or None) and main.publisher[:200], rid))
    cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s AND column_name IN "
                "('article_url', 'image_local_path')", (table, rid))
    pub = (main.publisher or None) and main.publisher[:200]
    _fact(cur, table, rid, "article_url", main.url, main.tier, pub)
    if img and img.image_local_path:
        _fact(cur, table, rid, "image_local_path", img.image_local_path, img.tier, (img.publisher or None) and img.publisher[:200])
    _also(cur, table, rid, [stored_as_cand({**row, "id": "stored-main"})])


def _write(cur, plan: dict, comp_id: str) -> dict:
    """One story -> its row in every table it belongs to. Returns {owner: (table, row id, fresh)}; fresh = the row
    was created from this story's main article (so that candidate is its 'story', not a 'merged' extra source)."""
    from backend.news import row_id
    members, cat, reasons = plan["members"], plan["category"], plan["reasons"]
    main, img = members[0], image_source(members)
    pub = (main.publisher or None) and main.publisher[:200]
    stored = {r["product_id"]: r for r in plan["stored"]}
    src = plan["stored"][0] if plan["stored"] else None
    out = {}
    plan["repicked"] = 0
    # owners that already have a row first, so a copy for an owner without one reads the (possibly re-picked) row
    for owner in sorted(owners_of(plan), key=lambda o: o not in stored):
        table, idcol = TABLES["product" if owner else None]
        row = stored.get(owner)
        if row is not None:                                         # the event is stored for this owner: extend it
            rid, fresh = row["id"], False
            if not row.get("category"):
                cur.execute(f"UPDATE staging.{table} SET category = %s WHERE {idcol} = %s", (cat, rid))
                _judgement(cur, table, rid, "category", reasons.get("category"))
            if beats_stored(main, row):                             # a later, better-ranked article becomes the main
                _repick(cur, table, idcol, rid, row, main, img)
                plan["repicked"] += 1
        elif src is not None:                                       # stored for another owner only: copy that row here
            st, sid = src["table"], TABLES["product" if src["product_id"] else None][1]
            cur.execute(f"SELECT headline, article_url, published_date, publisher FROM staging.{st} WHERE {sid} = %s", (src["id"],))
            h = cur.fetchone()
            rid, fresh = row_id(h["article_url"], owner or comp_id), False
            if not _exists(cur, table, idcol, rid):
                _new_row(cur, owner, comp_id, rid, h["headline"], h["article_url"], h["published_date"], h["publisher"],
                         img.image_url if img else None, src["category"] or cat)
                cur.execute("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, "
                            "publisher, quote, retrieved_at) SELECT %s, %s, column_name, source_url, source_tier, publisher, "
                            "quote, now() FROM staging.fact_source WHERE table_name = %s AND row_id = %s",
                            (table, rid, st, src["id"]))
                if not src.get("category"):
                    _judgement(cur, table, rid, "category", reasons.get("category"))
        else:                                                       # a new story: its main article makes the row
            rid, fresh = row_id(main.url, owner or comp_id), True
            if _exists(cur, table, idcol, rid):                     # already a story row (re-run): only the category
                cur.execute(f"UPDATE staging.{table} SET category = %s WHERE {idcol} = %s", (cat, rid))
            else:
                _new_row(cur, owner, comp_id, rid, main.headline, main.url, main.date, pub, img.image_url if img else None, cat)
            cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s AND column_name IN "
                        "('article_url', 'image_local_path')", (table, rid))
            _fact(cur, table, rid, "article_url", main.url, main.tier, pub)
            if img and img.image_local_path:
                _fact(cur, table, rid, "image_local_path", img.image_local_path, img.tier,
                      (img.publisher or None) and img.publisher[:200])
            _judgement(cur, table, rid, "category", reasons.get("category"))
            _judgement(cur, table, rid, NOT_ABOUT, plan.get("not_about"))     # no reason = the row is about the company
        _also(cur, table, rid, members)
        if reasons.get("candidates") and (len(members) > 1 or plan["stored"]):
            _judgement(cur, table, rid, "also_reported_by", reasons["candidates"])
        out[owner] = (table, rid, fresh)
    return out


# Stored stories of the batch's competitor that lie near the batch's dates. news.yml's 2nd block selects the same rows.
STORED_SQL = (
    "SELECT a.article_id::text AS id, NULL::text AS product_id, 'competitive_news_article' AS \"table\", a.category, "
    "a.headline, a.article_url AS url, a.published_date AS date, a.publisher, a.image_url, "
    "(SELECT f.source_tier FROM staging.fact_source f WHERE f.table_name = 'competitive_news_article' "
    "AND f.row_id = a.article_id::text AND f.column_name = 'article_url' LIMIT 1) AS tier "
    "FROM staging.competitive_news_article a WHERE a.competitor_id = %(comp)s AND {near_a} "
    "UNION ALL "
    "SELECT s.product_news_id::text, s.product_id::text, 'competitive_product_news', s.category, s.headline, "
    "s.article_url, s.published_date, s.publisher, NULL::text, "
    "(SELECT f.source_tier FROM staging.fact_source f WHERE f.table_name = 'competitive_product_news' "
    "AND f.row_id = s.product_news_id::text AND f.column_name = 'article_url' LIMIT 1) "
    "FROM staging.competitive_product_news s JOIN staging.competitive_product p ON p.product_id = s.product_id "
    "WHERE p.competitor_id = %(comp)s AND {near_s}")
MONTH_SQL = " AND date_trunc('month', coalesce({a}published_date, {a}found_at::date)) = %(month)s::date"
NEAR_SQL = ("EXISTS (SELECT 1 FROM staging.news_candidate c WHERE c.competitor_id = %(comp)s AND c.status = 'new'{month} "
            "AND abs({d} - c.published_date) <= %(win)s)")


def stored_sql(month=None) -> str:
    """The stored-stories query for a batch (a competitor's 'new' candidates, of one month when `month` is given)."""
    near = NEAR_SQL.format(month=MONTH_SQL.format(a="c.") if month else "", d="{d}")
    return STORED_SQL.format(near_a=near.format(d="a.published_date"), near_s=near.format(d="s.published_date"))


def _load(cur, comp_id: str, month=None):
    """(new candidates {id: Cand}, stored stories {id: row}) of one batch. A batch is a competitor's 'new' candidates,
    of one calendar month when `month` is given (news.yml subject). Stored stories are those within WINDOW_DAYS of
    any candidate date of the batch -- the candidates' own dates, not today's date (a backfill batch must see the
    stories already stored for its own period)."""
    args = {"comp": comp_id, "month": month, "win": WINDOW_DAYS}
    cur.execute("SELECT candidate_id::text AS id, product_id::text AS product_id, headline, article_url AS url, "
                "published_date AS date, publisher, image_url, image_local_path, source_tier AS tier, "
                "pre_group::text AS pre_group, found_at, match_via, page_note FROM staging.news_candidate "
                "WHERE competitor_id = %(comp)s AND status = 'new'" + (MONTH_SQL.format(a="") if month else "")
                + " ORDER BY found_at, candidate_id", args)
    cands = {r["id"]: Cand(**r) for r in cur.fetchall()}
    cur.execute(stored_sql(month), args)
    stored = {r["id"]: dict(r) for r in cur.fetchall()}
    return cands, stored


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    """Write the stories the model described. The caller commits (or rolls back for a dry run)."""
    res, comp_id = Result(), str(subject["competitor_id"])
    cands, stored = _load(cur, comp_id, subject.get("month"))
    by_h, bad_c = handle_map(cands, "C")
    st_h, bad_s = handle_map(stored, "S")
    for h in sorted(bad_c | bad_s):
        res.warnings.append(f"handle {h} is shared by two rows; not resolvable")
    stories = validate_records(env, by_h, st_h, res.warnings)
    if not stories:
        skip = env.get("skip_reason")
        res.skip_reason = skip.strip() if isinstance(skip, str) and skip.strip() and not env.get("records") else None
        return res
    plans, left = plan_stories(stories, cands, res.warnings)
    if left:
        res.warnings.append(f"{len(left)} article(s) left out by the model stay new: " + "; ".join(cands[i].headline[:50] for i in left[:5]))
    done = extended = 0
    for p in plans:
        cur.execute("SAVEPOINT news_story")
        try:
            rows = _write(cur, p, comp_id)
            for c in p["members"]:
                table, rid, fresh = rows[c.product_id]
                cur.execute("UPDATE staging.news_candidate SET status = %s, story_table = %s, story_id = %s, decided_at = now() "
                            "WHERE candidate_id = %s", ("story" if fresh and c.id == rid else "merged", table, rid, c.id))
            cur.execute("RELEASE SAVEPOINT news_story")
        except Exception as e:  # noqa: BLE001  (one bad story must not sink the batch)
            cur.execute("ROLLBACK TO SAVEPOINT news_story")
            res.warnings.append(f"story {p['members'][0].url[:80]}: {type(e).__name__}: {str(e).splitlines()[0][:100]}")
            continue
        done += len(p["members"])
        extended += bool(p["stored"])
        for table, rid, _ in rows.values():
            if (table, rid, True) not in res.loaded:
                res.loaded.append((table, rid, True))
    res.rows = len(res.loaded)
    res.note = f"{len(plans)} stories ({res.rows} rows) from {done} articles" + (f", {extended} extend stored stories" if extended else "")
    res.details = {"candidates": len(cands), "stored_in_view": len(stored), "stories": len(plans), "left_new": len(left),
                   "repicked_main": sum(p.get("repicked", 0) for p in plans),
                   "not_about": sum(bool(p.get("not_about")) for p in plans)}
    return res


# ---- self-check -----------------------------------------------------------------------------------------------

def _selftest() -> None:
    d = lambda n: date(2026, 10, n)
    mk = lambda i, prod=None, tier="independent", day=1, img=None, found=0, pg=None, url=None: Cand(
        i * 8 + "-0000", prod, f"h{i}", url or f"https://x.test/{i}", d(day) if day else None, f"pub{i}",
        f"https://img/{i}" if img else None, f"news/{i}.jpg" if img else None, tier, pg, found)
    a, b, c, e, f = (mk(x) for x in "abcef")
    ids = {x.id: x for x in (a, b, c, e, f)}
    # handles
    assert handle("C", "1a2b3c4d-1111-2222-3333-444455556666") == "C1a2b3c4d"
    hm, bad = handle_map(ids, "C")
    assert set(hm) == {"Caaaaaaaa", "Cbbbbbbbb", "Ccccccccc", "Ceeeeeeee", "Cffffffff"} and not bad
    hm2, bad2 = handle_map({"aaaaaaaa-1": 1, "aaaaaaaa-2": 2, "bbbbbbbb-1": 3}, "C")
    assert bad2 == {"Caaaaaaaa"} and set(hm2) == {"Cbbbbbbbb"}
    assert norm_handle(" CAAAAAAAA ") == "Caaaaaaaa" and canon_category(" contract & ORDER ") == "Contract & order"
    assert canon_category("Orders") is None and canon_category(None) is None
    assert canon_category("stock & market") == "Stock & market" and canon_category("NON-defence business") == "Non-defence business"
    assert len(CATEGORIES) == 11 and CATEGORIES[-1] == "Other"
    # main article ranking: primary > earlier date > saved image > earlier found
    assert sorted([mk("p", day=5), mk("q", tier="primary", day=9), mk("r", day=2)], key=rank_key)[0].id.startswith("q")
    assert sorted([mk("p", day=5), mk("r", day=2), mk("s", day=None)], key=rank_key)[0].id.startswith("r")
    assert sorted([mk("p", day=2), mk("r", day=2, img=True)], key=rank_key)[0].id.startswith("r")
    assert sorted([mk("p", day=2, found=5), mk("r", day=2, found=3)], key=rank_key)[0].id.startswith("r")
    assert sorted([mk("p", day=None), mk("r", day=None, found=-1)], key=rank_key)[0].id.startswith("r")
    # validation: unknown handle, repeated handle, bad category, same_as as one handle or a list
    srow = lambda ch, prod=None: {"id": ch * 8 + "-0000", "table": "competitive_product_news" if prod else "competitive_news_article",
                                  "product_id": prod, "category": None}
    stored = {"Sdddddddd": srow("d"), "Sgggggggg": srow("g", "P")}
    w: list = []
    env = {"records": [
        {"table": "news_story", "values": {"candidates": ["Caaaaaaaa", "CBBBBBBBB", "Cnope"], "category": "contract & order",
                                           "same_as": ["Sdddddddd", "SGGGGGGGG", "Sdddddddd", "Sxxxx"], "_reason": {"category": "r"}}},
        {"table": "news_story", "values": {"candidates": ["Cbbbbbbbb", "Ccccccccc"], "category": "Stock & market", "same_as": "Sgggggggg"}},
        {"table": "news_story", "values": {"candidates": ["Ceeeeeeee"], "category": "Bogus"}},
        {"table": "other", "values": {}}, "junk"]}
    st = validate_records(env, hm, stored, w)
    assert [s["ids"] for s in st] == [[a.id, b.id], [c.id]] and st[0]["category"] == "Contract & order"
    assert st[0]["same_as"] == [stored["Sdddddddd"], stored["Sgggggggg"]] and st[1]["same_as"] == [stored["Sgggggggg"]]
    assert st[1]["category"] == "Stock & market"
    assert any("unknown" in x for x in w) and any("earlier story" in x for x in w) and any("Bogus" in x for x in w)
    assert any("not a stored story" in x for x in w) and any("without _reason" in x for x in w)
    assert validate_records({"records": None}, hm, stored, []) == []
    # a story may mix owners; pre_group copies and the same url under two owners join it; undecided stay
    p1, p2, p3 = mk("1", prod="P", day=3), mk("2", prod="P", day=2), mk("3", prod="Q", day=4, url=a.url)
    g1, g2, g3 = mk("7"), mk("8", pg="7" * 8 + "-0000"), mk("9")
    cs = {x.id: x for x in (a, b, c, e, f, p1, p2, p3, g1, g2, g3)}
    stories = [{"ids": [a.id, b.id, p1.id], "category": "Export", "reasons": {"category": "x"}, "same_as": [stored["Sdddddddd"]]},
               {"ids": [c.id], "category": "Other", "reasons": {}, "same_as": []},
               {"ids": [g1.id], "category": "Financial results", "reasons": {}, "same_as": []}]
    plans, left = plan_stories(stories, cs, [])
    by = {tuple(sorted(m.id[0] for m in p["members"])): p for p in plans}
    assert set(by) == {("1", "3", "a", "b"), ("c",), ("7", "8")}, set(by)      # p3 joins a (same url); g2 joins g1 (pre_group)
    big = by[("1", "3", "a", "b")]
    assert big["stored"] == [stored["Sdddddddd"]] and big["category"] == "Export"
    assert owners_of(big) == [None, "P", "Q"] and owners_of(by[("c",)]) == [None]
    assert owners_of({"members": [c], "stored": [stored["Sgggggggg"]]}) == [None, "P"]     # stored product row is a target too
    assert sorted(left) == sorted([e.id, f.id, p2.id, g3.id])
    # two model stories joined by a pre_group copy: first story's category wins, same_as lists merge
    h1, h2 = mk("h"), mk("i", pg="h" * 8 + "-0000")
    pl, lf = plan_stories([{"ids": [h1.id], "category": "Export", "reasons": {}, "same_as": []},
                           {"ids": [h2.id], "category": "Other", "reasons": {}, "same_as": [stored["Sdddddddd"]]}],
                          {h1.id: h1, h2.id: h2}, [])
    assert len(pl) == 1 and pl[0]["category"] == "Export" and pl[0]["stored"] == [stored["Sdddddddd"]] and not lf
    # a product-only story: main is ranked over all members, the company table is still a target
    pp = plan_stories([{"ids": [p1.id, p2.id], "category": "Other", "reasons": {}, "same_as": []}],
                      {p1.id: p1, p2.id: p2}, [])[0][0]
    assert pp["members"][0] is p2 and owners_of(pp) == [None, "P"]
    # image: main's, else the first member that has one
    i1, i2 = mk("j", tier="primary"), mk("k", img=True)
    assert image_source([i1, i2]) is i2 and image_source([i2, i1]) is i2 and image_source([i1]) is None
    # --- main article: not blocked > outlet (official/company > wire > national press > others) > headline names the company
    #     > earlier date > image  (fictional urls)
    rk = lambda *cs: [c.url for c in sorted(cs, key=rank_key)]
    mkc = lambda host, i, **kw: mk(i, url=f"https://{host}/{i}", **kw)
    official, company = mkc("army.mil", "o1", tier="primary"), mkc("veland.test", "o2", tier="primary")
    wire, wire2 = mkc("www.ptinews.com", "w1", day=4), mkc("en.yna.co.kr", "w2", day=2)
    nat, nat2 = mkc("www.thehindu.com", "n1", day=1), mkc("www.koreatimes.co.kr", "n2", day=3)
    trade, blog = mkc("www.breakingdefense.com", "t1", day=1), mkc("www.armyrecognition.com", "t2", day=1)
    assert rk(trade, nat, wire, official)[:1] == [official.url] and rk(trade, nat, wire)[:3] == [wire.url, nat.url, trade.url]
    assert rk(nat2, wire, nat, wire2)[:2] == [wire2.url, wire.url]               # same rank: earlier date first
    assert rk(trade, nat2)[0] == nat2.url                                         # national press beats a trade outlet even when later
    rt = mkc("www.reuters.com", "r1", day=1)                                       # Reuters answers 401 to scripts: last among readable ones
    assert rk(rt, trade)[0] == trade.url and rk(rt, mkc("www.bloomberg.com", "b1", day=2))[0] == rt.url   # both blocked: back to outlet rank
    pn = mkc("www.ptinews.com", "p1", day=1, tier="independent")
    pn.page_note = "http 403"
    assert rk(pn, trade)[0] == trade.url                                           # a page that could not be read goes last
    named, page_only = mkc("www.thehindu.com", "h1", day=5), mkc("www.thehindu.com", "h2", day=1)
    named.match_via, page_only.match_via = "headline", "page"
    assert rk(page_only, named)[0] == named.url                                    # a headline that names the company wins over an earlier page-only match
    assert rk(mkc("x.test", "i1", day=2), mkc("x.test", "i2", day=2, img=True))[0].endswith("/i2")
    # a later article of a stored story re-picks the main only when it ranks strictly better
    srow2 = lambda **kw: {"id": "s" * 8 + "-0000", "table": "competitive_news_article", "product_id": None, "category": "Export",
                          "headline": "h", "url": "https://www.breakingdefense.com/old", "date": d(3), "publisher": "BD",
                          "image_url": None, "tier": "independent", **kw}
    assert beats_stored(wire, srow2()) and beats_stored(nat, srow2()) and not beats_stored(mkc("www.breakingdefense.com", "t9", day=9), srow2())
    assert not beats_stored(wire, srow2(url=wire.url)) and not beats_stored(nat, srow2(url="https://www.ptinews.com/x"))
    assert not beats_stored(nat, srow2(url="https://www.thehindu.com/old", date=d(1)))             # tie on rank, stored is earlier: stays
    assert beats_stored(mkc("www.thehindu.com", "e1", day=1), srow2(url="https://www.thehindu.com/old", date=d(3)))      # same rank, earlier date
    assert beats_stored(official, srow2(url="https://www.ptinews.com/x"))
    # --- not about the company: stored, category forced to Other, reason kept; missing field = about the company
    assert relevant("No") is False and relevant(False) is False and relevant("yes") is True and relevant(None) is None and relevant("maybe") is None
    wn: list = []
    stn = validate_records({"records": [
        {"table": "news_story", "values": {"candidates": ["Caaaaaaaa"], "category": "Export", "same_as": [], "relevant": "no",
                                           "_reason": {"category": "x", "relevant": "Veland is one of five bidders named in a list."}}},
        {"table": "news_story", "values": {"candidates": ["Cbbbbbbbb"], "category": "Export", "relevant": "yes", "_reason": {"category": "r"}}},
        {"table": "news_story", "values": {"candidates": ["Ccccccccc"], "category": "Contract & order", "_reason": {"category": "r"}}},
        {"table": "news_story", "values": {"candidates": ["Ceeeeeeee"], "category": "Contract & order", "relevant": "no", "_reason": {"category": "r"}}}]},
        hm, {}, wn)
    assert [s["category"] for s in stn] == ["Other", "Export", "Contract & order", "Other"]
    assert stn[0]["not_about"] == "Veland is one of five bidders named in a list." and stn[0]["reasons"]["category"].startswith("Not about the company")
    assert "model's category: Export" in stn[0]["reasons"]["category"]
    assert stn[1]["not_about"] is None and stn[2]["not_about"] is None and stn[3]["not_about"]
    assert any("relevant = no without _reason" in x for x in wn) and len(wn) == 1
    # two model stories joined by a pre_group copy: "not about" only when both parts say so; the "about" part's category wins
    n1, n2 = mk("n"), mk("m", pg="n" * 8 + "-0000")
    pj = plan_stories([{"ids": [n1.id], "category": "Other", "reasons": {"category": "a"}, "same_as": [], "not_about": "r1"},
                       {"ids": [n2.id], "category": "Export", "reasons": {"category": "b"}, "same_as": [], "not_about": None}],
                      {n1.id: n1, n2.id: n2}, [])[0][0]
    assert pj["not_about"] is None and pj["category"] == "Export"
    pj2 = plan_stories([{"ids": [n1.id], "category": "Other", "reasons": {}, "same_as": [], "not_about": "r1"},
                        {"ids": [n2.id], "category": "Other", "reasons": {}, "same_as": [], "not_about": "r2"}], {n1.id: n1, n2.id: n2}, [])[0][0]
    assert pj2["not_about"] == "r1"
    assert plan_stories([{"ids": [c.id], "category": "Other", "reasons": {}, "same_as": []}], {c.id: c}, [])[0][0]["not_about"] is None
    # --- stored-story window: the batch's own dates +- 21 days, never current_date
    assert WINDOW_DAYS == 21 and in_window(d(1), [d(22)]) and not in_window(d(1), [d(23)]) and in_window(d(30), [d(9), d(28)])
    assert not in_window(None, [d(1)]) and not in_window(d(1), [None]) and not in_window(date(2026, 6, 5), [date(2026, 10, 1)])
    q_all, q_month = stored_sql(), stored_sql(date(2026, 6, 1))
    assert "current_date" not in q_all and "current_date" not in q_month and "<= %(win)s" in q_all and "date_trunc" not in q_all
    assert "date_trunc('month'" in q_month and q_month.count("%(month)s") == 2 and q_all.count("%(comp)s") == 4
    print("news_merge self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
