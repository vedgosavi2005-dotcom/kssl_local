"""Raw-layer documents for prompts (docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md C: "source_document.body_text as the document when the
article is in the raw layer, the url fetch as fallback").

staging.source_document holds the cleaned text of every harvested page (db/setup/09_raw_layer.sql), so a prompt does not need to fetch
a page the harvester already read. prompts/render.py (Phase 1) calls `resolve` for a `subject.documents` entry of the kind

    documents:
      - from: source_document          # the stored text of the subject's article ...
        field: article_url             # ... found by this subject column (the url, as the news job stored it)
        min_chars: 400                 # shorter stored text counts as "not read": the caller falls back to the next entry / a url fetch
        cap: 12000                     # characters kept (default render.DOC_CAP)
      - from: source_document          # OR: every recent document about one competitor (a roll-up prompt reads these, nothing is fetched)
        competitor: competitor_id      # subject column holding the competitor uuid (matched against source_document.competitor_ids)
        days: 90                       # published in the last N days
        limit: 20                      # most recent N
        cap_each: 3000                 # characters of body_text per document

    resolve(cur, entry, subject, today=None) -> [Block] | []     # Block = (url, text); render prints "[SOURCE <url>]\\n<text>"
    document_for_url(cur, url)           -> row | None            # one document by url (exact, then the news job's clean_url form)
    recent_for_competitor(cur, competitor_id, days, limit, cap_each) -> [Block]

An empty list means "nothing usable in the raw layer": the caller goes on to the next documents entry (usually `from: url`).
The functions only read; they never write staging.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from typing import NamedTuple

DEFAULT_CAP = 12_000
DEFAULT_MIN_CHARS = 400


class Block(NamedTuple):
    url: str
    text: str


def _clean(url: str) -> str:
    from backend.news import clean_url
    try:
        return clean_url(url)
    except Exception:  # noqa: BLE001
        return url.strip()


def document_for_url(cur, url) -> dict | None:
    """The source_document row for a url: exact match first, then the cleaned form (tracking parameters, /amp, host case removed)."""
    if not url:
        return None
    for candidate in dict.fromkeys([str(url).strip(), _clean(str(url))]):
        cur.execute("SELECT doc_id, url, title, published_at, source_name, body_text FROM staging.source_document WHERE url = %s LIMIT 1", (candidate,))
        r = cur.fetchone()
        if r:
            return dict(r)
    return None


def _text(doc: dict, cap: int) -> str:
    head = " · ".join(str(x) for x in (doc.get("title"), doc.get("source_name"), doc.get("published_at")) if x)
    body = (doc.get("body_text") or "").strip()
    return (head + "\n" + body if head else body)[:cap]


def recent_for_competitor(cur, competitor_id, days: int = 90, limit: int = 20, cap_each: int = 3000, today: date | None = None) -> list:
    since = (today or date.today()) - timedelta(days=int(days))
    cur.execute("""SELECT doc_id, url, title, published_at, source_name, body_text FROM staging.source_document
                   WHERE %s::uuid = ANY(competitor_ids) AND coalesce(published_at, current_date) >= %s AND coalesce(body_text, '') <> ''
                   ORDER BY published_at DESC NULLS LAST, url LIMIT %s""", (str(competitor_id), since, int(limit)))
    return [Block(r["url"], _text(dict(r), cap_each)) for r in cur.fetchall()]


def resolve(cur, entry: dict, subject: dict, today: date | None = None) -> list:
    """The blocks one `from: source_document` entry gives for this subject ([] when the raw layer has nothing usable)."""
    if entry.get("competitor"):
        cid = subject.get(entry["competitor"])
        return recent_for_competitor(cur, cid, entry.get("days", 90), entry.get("limit", 20), entry.get("cap_each", 3000), today) if cid else []
    url = subject.get(entry.get("field", "article_url"))
    doc = document_for_url(cur, url)
    if doc is None or len((doc.get("body_text") or "").strip()) < int(entry.get("min_chars", DEFAULT_MIN_CHARS)):
        return []
    return [Block(str(url), _text(doc, int(entry.get("cap", DEFAULT_CAP))))]


def check_entry(entry: dict) -> None:
    """Spec-time check of a `from: source_document` entry (raises ValueError)."""
    allowed = {"from", "field", "competitor", "days", "limit", "cap", "cap_each", "min_chars"}
    if set(entry) - allowed:
        raise ValueError(f"documents: unknown key(s) {sorted(set(entry) - allowed)} in a source_document entry")
    if not (entry.get("field") or entry.get("competitor")):
        raise ValueError("documents: a source_document entry needs `field` (a subject column holding the url) or `competitor`")


def _selftest() -> None:
    class Cur:
        def __init__(self, rows): self.rows, self.q = rows, []
        def execute(self, sql, args=None): self.q.append(args); self.last = args
        def fetchone(self):
            return next((r for r in self.rows if r["url"] == self.last[0]), None)
        def fetchall(self):
            return list(self.rows)

    doc = {"doc_id": "d1", "url": "https://x.test/a", "title": "T", "published_at": date(2026, 9, 1), "source_name": "News", "body_text": "word " * 200}
    cur = Cur([doc])
    assert document_for_url(cur, "https://x.test/a")["doc_id"] == "d1" and document_for_url(cur, None) is None and document_for_url(cur, "https://x.test/zz") is None
    assert document_for_url(cur, "HTTPS://X.TEST/a?utm_source=abc")["doc_id"] == "d1"            # cleaned form: host case, tracking parameter
    b = resolve(cur, {"from": "source_document", "field": "article_url"}, {"article_url": "https://x.test/a"})
    assert len(b) == 1 and b[0].url == "https://x.test/a" and b[0].text.startswith("T · News · 2026-09-01\nword")
    assert resolve(cur, {"from": "source_document", "field": "article_url", "min_chars": 5000}, {"article_url": "https://x.test/a"}) == []     # too short: fall back
    assert resolve(cur, {"from": "source_document", "field": "article_url"}, {"article_url": None}) == []
    assert len(resolve(cur, {"from": "source_document", "field": "u", "cap": 50}, {"u": "https://x.test/a"})[0].text) == 50
    assert [x.url for x in resolve(cur, {"from": "source_document", "competitor": "cid", "cap_each": 20}, {"cid": "c1"})] == ["https://x.test/a"]
    assert resolve(cur, {"from": "source_document", "competitor": "cid"}, {"cid": None}) == []
    check_entry({"from": "source_document", "field": "article_url", "min_chars": 400})
    for bad in ({"from": "source_document"}, {"from": "source_document", "field": "u", "bogus": 1}):
        try:
            check_entry(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    print("raw_docs self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
