-- Hand test rows for the KSSL schema. Everything goes to the STAGING side:
--   staging_ui.*  for ui tables     staging.*  for serving tables
-- They show in the review copy (http://localhost:5180) as "new"; Approve puts them live
-- (http://localhost:5178). Direct writes to ui.* / serving.* are refused by design.

-- 1. Setup (ui): the competitive pillar header
INSERT INTO staging_ui.competitive_pillar
  (pillar_id, brand_name, active_pillar, account_label, print_report_action)
VALUES ('00000000-0000-0000-0000-0000000000a1', '137 Parallax', 'competitive', 'KSSL', true);

-- 2. The client (KSSL) account
INSERT INTO staging.client_account
  (client_id, client_name, brand_name, legal_name, headquarters, industry_sector, country, created_at, updated_at)
VALUES (1, 'KSSL', 'KSSL', 'KSSL Ltd', 'Pune, India', 'Defence', 'India', now(), now());

-- 3. A competitor
INSERT INTO staging.competitive_competitor
  (competitor_id, display_name, legal_name, headquarters, industry_sector, origin_country, threat_level)
VALUES ('11111111-1111-1111-1111-111111111111', 'Acme Defense', 'Acme Defense Ltd', 'Pune, India',
        'Defense', 'India', 'High');

-- 4. Its product
INSERT INTO staging.competitive_product
  (product_id, competitor_id, product_name, category, country, category_filter, is_collapsed)
VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111',
        'Thunderbolt Engine', 'Propulsion', 'India', 'Propulsion', false);

-- 5. A competitive signal + its drawer
INSERT INTO staging.competitive_signal
  (signal_id, sequence_no, title, summary, classification, event_date, company_id, category)
VALUES ('33333333-3333-3333-3333-333333333333', 1, 'Acme wins naval contract',
        'Acme secured a large propulsion order.', 'threat', '2026-09-01',
        '11111111-1111-1111-1111-111111111111', 'Contracts');

INSERT INTO staging.competitive_signal_detail
  (signal_id, drawer_title, why_it_matters, what_article_says, source_url, source_name)
VALUES ('33333333-3333-3333-3333-333333333333', 'Acme wins naval contract',
        'Erodes KSSL share in naval propulsion.', 'The order covers 12 vessels over 3 years.',
        'https://example.com/acme-naval', 'Example News');

-- 6. A tender (tender_id is a number now)
INSERT INTO staging.market_tender
  (tender_id, title, buyer_name, country_name, category_text, value_amount, value_currency, value_text,
   status, closing_date, deadline_text, days_remaining, is_live, created_at, updated_at)
VALUES (1001, 'Supply of marine engines', 'Indian Navy', 'India', 'Propulsion',
        5000000, 'INR', '₹50 lakh', 'open', '2026-12-31', 'Closes 31 Dec 2026', 76, true, now(), now());

-- 7. A market opportunity (opportunity_id is a number; opportunity_kind is required)
INSERT INTO staging.market_opportunity
  (opportunity_id, opportunity_kind, title, description, buyer_name, country_code, stage,
   as_of_date, created_at, updated_at)
VALUES (2001, 'project', 'Export demand rising', 'Southeast Asia naval refits accelerating.',
        'Royal Example Navy', 'TH', 'planning', '2026-09-15', now(), now());

-- 8. Technology pillar + a technology overview article
INSERT INTO staging.technology_pillar
  (pillar_id, pillar_code, pillar_name, client_name, is_active, created_at, updated_at)
VALUES (1, 'technology', 'Technology', 'KSSL', true, now(), now());

INSERT INTO staging.technology_overview_article
  (overview_article_id, article_id, external_id, pillar_id, sequence_no, title, lens, status,
   published_label, card_summary, direction, category_id, created_at, updated_at)
VALUES (3001, 3001, 'tech-001', 1, 1, 'Hybrid-electric propulsion breakthrough', 'Technology', 'published',
        'Sep 2026', 'New hybrid drive cuts fuel use 20%.', 'watch', NULL, now(), now());  -- category_id is a technology_category id (number)

-- Wipe ALL data, staged and live (ui, serving, staging, staging_ui). Keeps the tables.
-- DO $$
-- DECLARE r record;
-- BEGIN
--   FOR r IN SELECT schemaname, tablename FROM pg_tables
--            WHERE schemaname IN ('ui', 'serving', 'staging', 'staging_ui')
--   LOOP
--     EXECUTE format('TRUNCATE TABLE %I.%I', r.schemaname, r.tablename);
--   END LOOP;
-- END $$;

-- Wipe only what is waiting for review (keeps everything already live):
-- DO $$
-- DECLARE r record;
-- BEGIN
--   FOR r IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('staging', 'staging_ui')
--   LOOP
--     EXECUTE format('TRUNCATE TABLE %I.%I', r.schemaname, r.tablename);
--   END LOOP;
-- END $$;
