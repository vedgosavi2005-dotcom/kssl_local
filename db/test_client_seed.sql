-- TEST-ONLY client setup in kssl_staging, so the prompts have a client to work for until the
-- client's Excel files are loaded (they replace these rows). Names and categories only; no
-- figures. Run: docker exec -i kssl-pg psql -U kssl -d kssl_staging < db/test_client_seed.sql
BEGIN;

-- The news test seeded Bharat Forge as a competitor with ATAGS and Kalyani M4 as its products,
-- but KSSL is Bharat Forge's defence arm and those are KSSL products: take them out of the
-- competitor side (with their news and per-field sources).
DELETE FROM staging.fact_source WHERE row_id IN (
    SELECT product_news_id::text FROM staging.competitive_product_news WHERE product_id IN (
        SELECT product_id FROM staging.competitive_product WHERE competitor_id IN (
            SELECT competitor_id FROM staging.competitive_competitor WHERE display_name = 'Bharat Forge'))
    UNION ALL
    SELECT article_id::text FROM staging.competitive_news_article WHERE competitor_id IN (
        SELECT competitor_id FROM staging.competitive_competitor WHERE display_name = 'Bharat Forge'));
DELETE FROM staging.competitive_product_news WHERE product_id IN (
    SELECT product_id FROM staging.competitive_product WHERE competitor_id IN (
        SELECT competitor_id FROM staging.competitive_competitor WHERE display_name = 'Bharat Forge'));
DELETE FROM staging.competitive_product WHERE competitor_id IN (
    SELECT competitor_id FROM staging.competitive_competitor WHERE display_name = 'Bharat Forge');
DELETE FROM staging.competitive_news_article WHERE competitor_id IN (
    SELECT competitor_id FROM staging.competitive_competitor WHERE display_name = 'Bharat Forge');
DELETE FROM staging.competitive_competitor WHERE display_name = 'Bharat Forge';

INSERT INTO staging.client_account (client_id, client_name, brand_name, legal_name, headquarters, industry_sector, country, created_at, updated_at)
SELECT 1, 'KSSL', 'KSSL', 'Kalyani Strategic Systems Limited', 'Pune, India', 'Defence', 'India', now(), now()
WHERE NOT EXISTS (SELECT 1 FROM staging.client_account WHERE client_id = 1);

INSERT INTO staging.technology_category (category_id, category_code, category_name, canonical_name, category_number, display_order, is_active, tab_number)
SELECT v.* FROM (VALUES
    (1::bigint, 'artillery', 'Artillery', 'Artillery', 1, 1, true, 1),
    (2, 'ammunition', 'Ammunition', 'Ammunition', 2, 2, true, 2),
    (3, 'armoured-vehicles', 'Armoured Vehicles', 'Armoured Vehicles', 3, 3, true, 3),
    (4, 'small-arms', 'Small Arms', 'Small Arms', 4, 4, true, 4),
    (5, 'unmanned-counter-uas', 'Unmanned & Counter-UAS', 'Unmanned & Counter-UAS', 5, 5, true, 5),
    (6, 'missiles-air-defence', 'Missiles & Air Defence', 'Missiles & Air Defence', 6, 6, true, 6)
) AS v(category_id, category_code, category_name, canonical_name, category_number, display_order, is_active, tab_number)
WHERE NOT EXISTS (SELECT 1 FROM staging.technology_category);

INSERT INTO staging.client_product (client_product_id, client_id, product_name, category, created_at, updated_at)
SELECT v.id, 1, v.name, v.cat, now(), now() FROM (VALUES
    (101::bigint, 'ATAGS', 'Artillery'),
    (102, 'MArG 155', 'Artillery'),
    (103, 'Garuda 105', 'Artillery'),
    (104, 'Kalyani M4', 'Armoured Vehicles')
) AS v(id, name, cat)
WHERE NOT EXISTS (SELECT 1 FROM staging.client_product);

-- Page setup (ui side): Competitor Moment grades and time windows.
INSERT INTO staging_ui.competitive_competitor_moment_level (display_order, level_code, level_label, tag_class)
SELECT v.* FROM (VALUES (1, 'high', 'High impact', 'threat'), (2, 'watch', 'Watch', 'watch'),
                        (3, 'opportunity', 'Opening for the client', 'opportunity')) AS v(o, c, l, t)
WHERE NOT EXISTS (SELECT 1 FROM staging_ui.competitive_competitor_moment_level);
INSERT INTO staging_ui.competitive_competitor_moment_time_window (time_window_id, time_window_code, time_window_label, day_count, display_order, is_default)
SELECT v.* FROM (VALUES (1::bigint, '30d', 'Last 30 days', 30, 1, false), (2, '90d', 'Last 90 days', 90, 2, true),
                        (3, '1y', 'Last 12 months', 365, 3, false)) AS v(i, c, l, d, o, df)
WHERE NOT EXISTS (SELECT 1 FROM staging_ui.competitive_competitor_moment_time_window);

COMMIT;
