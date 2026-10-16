-- ONE-OFF (not part of make_databases.sh): move the news rows written by the old news job into the
-- holding table staging.news_candidate, so `python -m prompts.run news` can group them into stories.
-- Run once on kssl_staging, then `python -m backend.news --regroup`:
--   docker exec -i kssl-pg psql -U kssl -d kssl_staging -v ON_ERROR_STOP=1 < db/news_to_candidates.sql
-- Source tier and the saved image come from staging.fact_source (article_url / image_local_path).
-- One transaction: the news rows and their fact_source rows are deleted only after the copy.
BEGIN;

INSERT INTO staging.news_candidate (candidate_id, competitor_id, product_id, headline, article_url, published_date,
                                    publisher, image_url, image_local_path, source_tier)
SELECT a.article_id, a.competitor_id, NULL, a.headline, a.article_url, a.published_date, a.publisher, a.image_url,
       (SELECT f.source_url FROM staging.fact_source f WHERE f.table_name = 'competitive_news_article'
           AND f.row_id = a.article_id::text AND f.column_name = 'image_local_path' LIMIT 1),
       (SELECT f.source_tier FROM staging.fact_source f WHERE f.table_name = 'competitive_news_article'
           AND f.row_id = a.article_id::text AND f.column_name = 'article_url' LIMIT 1)
FROM staging.competitive_news_article a
WHERE a.article_url IS NOT NULL AND a.competitor_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO staging.news_candidate (candidate_id, competitor_id, product_id, headline, article_url, published_date,
                                    publisher, image_url, image_local_path, source_tier)
SELECT n.product_news_id, p.competitor_id, n.product_id, n.headline, n.article_url, n.published_date, n.publisher, NULL,
       (SELECT f.source_url FROM staging.fact_source f WHERE f.table_name = 'competitive_product_news'
           AND f.row_id = n.product_news_id::text AND f.column_name = 'image_local_path' LIMIT 1),
       (SELECT f.source_tier FROM staging.fact_source f WHERE f.table_name = 'competitive_product_news'
           AND f.row_id = n.product_news_id::text AND f.column_name = 'article_url' LIMIT 1)
FROM staging.competitive_product_news n
JOIN staging.competitive_product p ON p.product_id = n.product_id
WHERE n.article_url IS NOT NULL
ON CONFLICT DO NOTHING;

DELETE FROM staging.fact_source WHERE table_name = 'competitive_news_article'
    AND row_id IN (SELECT article_id::text FROM staging.competitive_news_article);
DELETE FROM staging.fact_source WHERE table_name = 'competitive_product_news'
    AND row_id IN (SELECT product_news_id::text FROM staging.competitive_product_news);
DELETE FROM staging.competitive_news_article;
DELETE FROM staging.competitive_product_news;

COMMIT;
