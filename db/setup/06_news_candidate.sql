-- staging.news_candidate: holding table of the news job (python -m backend.news). Never reviewed, never shown.
-- python -m prompts.run news groups candidates into stories (same event, many publishers) and writes ONE row
-- per story to staging.competitive_news_article / competitive_product_news (prompts/news_merge.py).
-- Applied to kssl_staging by db/make_databases.sh. Safe to re-run.
CREATE TABLE IF NOT EXISTS staging.news_candidate (
    candidate_id     uuid          PRIMARY KEY,   -- backend.news.row_id(url, owner): a story's id = its main candidate's id
    competitor_id    uuid          NOT NULL,
    product_id       uuid,                        -- NULL = company news
    headline         text          NOT NULL,
    article_url      text          NOT NULL,
    published_date   date,
    publisher        text,
    image_url        text,
    image_local_path text,
    source_tier      text,                        -- primary | independent
    pre_group        uuid,                        -- candidate_id of the first near-copy (code pre-grouping), NULL if none
    found_at         timestamptz   NOT NULL DEFAULT now(),
    status           text          NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'story', 'merged')),   -- story = main article, merged = extra source
    story_table      text,
    story_id         uuid,
    decided_at       timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS news_candidate_owner_url
    ON staging.news_candidate (coalesce(product_id, competitor_id), article_url);
CREATE INDEX IF NOT EXISTS news_candidate_competitor_status ON staging.news_candidate (competitor_id, status);
