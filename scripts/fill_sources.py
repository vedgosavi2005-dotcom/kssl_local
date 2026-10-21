"""Give every shown row a source from what the pipeline already holds -- never an invented one (owner 2026-10-22).

    python -m scripts.fill_sources            (dry run: counts what it would fill)
    python -m scripts.fill_sources --write

Fills, each idempotent and only from a stored source:
  1. market_tender_eligibility: the tender notice the assessment read (the tender's own source_url, its tier);
     the row's quote goes along as the proof.
  2. story_step of a signal with no source_url: the url behind the signal's title (else event_date, else the
     signal detail's source_url).
  3. technology_innovation_milestone: a fact_source row for the url the milestone already stores.
  4. competitive_news_article with an empty article_url (its own site was blocked as a source): re-pointed to its
     best "also_reported_by" article -- url, publisher host, that article's headline, the date in its url;
     the blocked site's description and image are dropped.
Then it lists what is still unsourced. Connection: KSSL_STAGING_DSN (else KSSL_DSN).
"""
from __future__ import annotations

import os
import sys

import psycopg2

FILLS = {
    "eligibility": """
        INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
        SELECT 'market_tender_eligibility', e.eligibility_id::text, 'item', t.source_url,
               coalesce((SELECT f.source_tier FROM staging.fact_source f WHERE f.table_name = 'market_tender' AND f.row_id = t.tender_id::text
                         AND f.source_url = t.source_url ORDER BY (f.source_tier = 'primary') DESC LIMIT 1), 'primary'),
               NULL, e.quote, now()
        FROM staging.market_tender_eligibility e JOIN staging.market_tender t USING (tender_id)
        WHERE t.source_url LIKE 'http%%' AND NOT EXISTS (SELECT 1 FROM staging.fact_source f WHERE f.table_name = 'market_tender_eligibility'
              AND f.row_id = e.eligibility_id::text AND f.source_url LIKE 'http%%')""",
    "signal_steps": """
        UPDATE staging.story_step s SET source_url = x.url FROM (
          SELECT s2.step_id, coalesce(
            (SELECT f.source_url FROM staging.fact_source f WHERE f.table_name = 'competitive_signal' AND f.row_id = s2.source_row_id AND f.column_name = 'title' AND f.source_url LIKE 'http%%' LIMIT 1),
            (SELECT f.source_url FROM staging.fact_source f WHERE f.table_name = 'competitive_signal' AND f.row_id = s2.source_row_id AND f.column_name = 'event_date' AND f.source_url LIKE 'http%%' LIMIT 1),
            (SELECT d.source_url FROM staging.competitive_signal_detail d WHERE d.signal_id::text = s2.source_row_id AND d.source_url LIKE 'http%%' LIMIT 1)) url
          FROM staging.story_step s2 WHERE s2.source_table = 'competitive_signal' AND coalesce(s2.source_url, '') = '') x
        WHERE x.step_id = s.step_id AND x.url IS NOT NULL""",
    "milestones": """
        INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
        SELECT 'technology_innovation_milestone', m.milestone_id::text, 'note', m.source_url,
               coalesce((SELECT f.source_tier FROM staging.fact_source f WHERE f.source_url = m.source_url AND f.source_tier NOT IN ('judgement', 'stored') LIMIT 1), 'primary'),
               NULL, m.note, now()
        FROM staging.technology_innovation_milestone m
        WHERE m.source_url LIKE 'http%%' AND NOT EXISTS (SELECT 1 FROM staging.fact_source f WHERE f.table_name = 'technology_innovation_milestone' AND f.row_id = m.milestone_id::text)""",
    "news": """
        WITH pick AS (
          SELECT DISTINCT ON (a.article_id) a.article_id, f.source_url url, f.quote headline,
                 CASE WHEN f.source_url ~ '/20\\d\\d/\\d\\d/\\d\\d/' THEN to_date(substring(f.source_url from '/(20\\d\\d/\\d\\d/\\d\\d)/'), 'YYYY/MM/DD') END url_date
          FROM staging.competitive_news_article a
          JOIN staging.fact_source f ON f.table_name = 'competitive_news_article' AND f.row_id = a.article_id::text
               AND f.column_name = 'also_reported_by' AND f.source_url LIKE 'http%%' AND coalesce(f.quote, '') <> ''
          WHERE coalesce(a.article_url, '') = ''
          ORDER BY a.article_id, CASE f.source_tier WHEN 'primary' THEN 0 WHEN 'independent' THEN 0 WHEN 'listed' THEN 1 ELSE 2 END, length(f.source_url))
        UPDATE staging.competitive_news_article a SET article_url = p.url, headline = left(p.headline, 300),
               publisher = regexp_replace(regexp_replace(p.url, '^https?://(www\\.)?', ''), '/.*$', ''),
               published_date = coalesce(p.url_date, a.published_date), description = NULL, image_url = NULL
        FROM pick p WHERE p.article_id = a.article_id""",
}

LEFT = """
    SELECT 'eligibility', count(*) FROM staging.market_tender_eligibility e WHERE NOT EXISTS (SELECT 1 FROM staging.fact_source f
           WHERE f.table_name = 'market_tender_eligibility' AND f.row_id = e.eligibility_id::text AND f.source_url LIKE 'http%%')
    UNION ALL SELECT 'signal steps', count(*) FROM staging.story_step WHERE source_table = 'competitive_signal' AND coalesce(source_url, '') = ''
    UNION ALL SELECT 'news', count(*) FROM staging.competitive_news_article WHERE coalesce(article_url, '') = ''"""


def main(argv: list[str]) -> int:
    write = "--write" in argv
    dsn = os.environ.get("KSSL_STAGING_DSN") or os.environ.get("KSSL_DSN")
    if not dsn:
        print("set KSSL_STAGING_DSN")
        return 1
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        for name, sql in FILLS.items():
            cur.execute(sql)
            print(f"{name}: {cur.rowcount} row(s) {'filled' if write else 'would be filled'}")
        cur.execute(LEFT)
        for name, n in cur.fetchall():
            print(f"still without a source -- {name}: {n}")
        if not write:
            conn.rollback()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
