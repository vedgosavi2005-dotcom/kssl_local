"""Apply the answer of the `news` prompt (prompts/news.yml): staging.news_candidate -> story rows.

    python -m prompts.news_merge --selftest        (no DB, no network)

The model only says which candidates (handles C<8 hex>) report the same EVENT (company news and its products'
news may be in one story), which stored stories (handles S<8 hex>) it already is, and the category. Code does the rest:
  1. validate the answer (unknown / repeated handle dropped, bad category = story dropped, candidates stay 'new')
  2. union-find: model groups + the code's pre_group copies + the same article url under two owners = one story
  3. main article of the story = primary tier, earliest date, has an image, earliest found
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

CATEGORIES = ["Contract & order", "Partnership / JV", "Product launch & testing", "Delivery & induction", "Export",
              "Financial results", "Stock & market", "Facility & capacity", "Leadership & corporate",
              "Non-defence business", "Other"]
JUDGEMENT = "judgement"                    # same marker prompts/loader.py writes for a _reason
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


def rank_key(c: Cand) -> tuple:
    """Main article first: primary tier, earliest date (none last), has a saved image, earliest found."""
    return (c.tier != "primary", c.date is None, c.date or date.max, not c.image_local_path, c.found_at, c.id)


def validate_records(env: dict, cands: dict, stored: dict, warns: list) -> list[dict]:
    """The model's records -> [{ids, category, reasons, same_as [stored row dicts]}].
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
        if "category" not in reasons:
            warns.append(f"records[{i}]: category without _reason")
        out.append({"ids": ids, "category": cat, "reasons": reasons, "same_as": rows})
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
        m = meta.setdefault(find(s["ids"][0]), {**s, "same_as": []})
        m["same_as"] += [r for r in s["same_as"] if r not in m["same_as"]]
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
                      "stored": m["same_as"]})
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
    for owner in owners_of(plan):
        table, idcol = TABLES["product" if owner else None]
        row = stored.get(owner)
        if row is not None:                                         # the event is stored for this owner: extend it
            rid, fresh = row["id"], False
            if not row.get("category"):
                cur.execute(f"UPDATE staging.{table} SET category = %s WHERE {idcol} = %s", (cat, rid))
                _judgement(cur, table, rid, "category", reasons.get("category"))
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
        _also(cur, table, rid, members)
        if reasons.get("candidates") and (len(members) > 1 or plan["stored"]):
            _judgement(cur, table, rid, "also_reported_by", reasons["candidates"])
        out[owner] = (table, rid, fresh)
    return out


def _load(cur, comp_id: str):
    cur.execute("SELECT candidate_id::text AS id, product_id::text AS product_id, headline, article_url AS url, "
                "published_date AS date, publisher, image_url, image_local_path, source_tier AS tier, "
                "pre_group::text AS pre_group, found_at FROM staging.news_candidate "
                "WHERE competitor_id = %s AND status = 'new' ORDER BY found_at, candidate_id", (comp_id,))
    cands = {r["id"]: Cand(**r) for r in cur.fetchall()}
    cur.execute("SELECT article_id::text AS id, NULL::text AS product_id, 'competitive_news_article' AS \"table\", "
                "category FROM staging.competitive_news_article WHERE competitor_id = %s AND published_date >= current_date - 45 "
                "UNION ALL SELECT s.product_news_id::text, s.product_id::text, 'competitive_product_news', s.category "
                "FROM staging.competitive_product_news s JOIN staging.competitive_product p ON p.product_id = s.product_id "
                "WHERE p.competitor_id = %s AND s.published_date >= current_date - 45", (comp_id, comp_id))
    stored = {r["id"]: dict(r) for r in cur.fetchall()}
    return cands, stored


def apply(cur, subject: dict, env: dict, dry_run: bool = False) -> Result:
    """Write the stories the model described. The caller commits (or rolls back for a dry run)."""
    res, comp_id = Result(), str(subject["competitor_id"])
    cands, stored = _load(cur, comp_id)
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
    res.details = {"candidates": len(cands), "stored_in_view": len(stored), "stories": len(plans), "left_new": len(left)}
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
    print("news_merge self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
