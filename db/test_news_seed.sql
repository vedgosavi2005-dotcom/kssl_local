-- Test competitors and products for the news job (backend/news.py). STAGING only; idempotent
-- (no keys on these tables, so WHERE NOT EXISTS). Minimal real rows: names + origin country.
-- competitive_product.category / category_filter are NOT NULL, so a neutral label is used.
-- Run: docker exec -i kssl-pg psql -U kssl -d kssl_frontend < db/test_news_seed.sql
BEGIN;

INSERT INTO staging.competitive_competitor (competitor_id, display_name, legal_name, origin_country)
SELECT '77ffa9e5-e00b-5653-84ae-5f3f83042575', 'Bharat Forge', 'Bharat Forge Limited', 'India'
WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_competitor WHERE competitor_id = '77ffa9e5-e00b-5653-84ae-5f3f83042575');

INSERT INTO staging.competitive_competitor (competitor_id, display_name, legal_name, origin_country)
SELECT 'd970c905-6616-5e60-888a-c0a7120b3fe2', 'Larsen & Toubro', 'Larsen & Toubro Limited', 'India'
WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_competitor WHERE competitor_id = 'd970c905-6616-5e60-888a-c0a7120b3fe2');

INSERT INTO staging.competitive_competitor (competitor_id, display_name, legal_name, origin_country)
SELECT '82f7e394-418f-5e95-8168-a784e0bb485d', 'Adani Defence & Aerospace', NULL, 'India'
WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_competitor WHERE competitor_id = '82f7e394-418f-5e95-8168-a784e0bb485d');

INSERT INTO staging.competitive_competitor (competitor_id, display_name, legal_name, origin_country)
SELECT 'eb5fad0b-c2fb-5197-849a-e71b9e515a5c', 'Hanwha Aerospace', 'Hanwha Aerospace Co., Ltd.', 'South Korea'
WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_competitor WHERE competitor_id = 'eb5fad0b-c2fb-5197-849a-e71b9e515a5c');

INSERT INTO staging.competitive_product (product_id, competitor_id, product_name, category, category_filter, is_collapsed)
SELECT 'ec48e70f-e68f-5a38-b635-c33f4cf68ec0', 'd970c905-6616-5e60-888a-c0a7120b3fe2', 'K9 Vajra-T', 'Test', 'Test', false
WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_product WHERE product_id = 'ec48e70f-e68f-5a38-b635-c33f4cf68ec0');

INSERT INTO staging.competitive_product (product_id, competitor_id, product_name, category, category_filter, is_collapsed)
SELECT 'c65995e1-5aed-570f-86cd-085a3b598d67', '77ffa9e5-e00b-5653-84ae-5f3f83042575', 'ATAGS', 'Test', 'Test', false
WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_product WHERE product_id = 'c65995e1-5aed-570f-86cd-085a3b598d67');

INSERT INTO staging.competitive_product (product_id, competitor_id, product_name, category, category_filter, is_collapsed)
SELECT '2ed43eed-6474-5507-a01c-9720db1e264e', '77ffa9e5-e00b-5653-84ae-5f3f83042575', 'Kalyani M4', 'Test', 'Test', false
WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_product WHERE product_id = '2ed43eed-6474-5507-a01c-9720db1e264e');

INSERT INTO staging.competitive_product (product_id, competitor_id, product_name, category, category_filter, is_collapsed)
SELECT '796708c1-e374-512b-b9b4-67c3a68f1c2a', 'eb5fad0b-c2fb-5197-849a-e71b9e515a5c', 'K9 Thunder', 'Test', 'Test', false
WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_product WHERE product_id = '796708c1-e374-512b-b9b4-67c3a68f1c2a');

COMMIT;
