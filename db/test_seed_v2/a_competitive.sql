-- Area A test rows (fictional). Requires db/test_seed_v2/a_base.sql (client 1, three competitors, technology_pillar 1,
-- technology_category 1-3). Loaded into staging.* / staging_ui.*; make_test_db.sh copies them to the live schemas.
-- Vocabularies: see the docstring of backend/areas/a_competitive.py.

-- ---- competitive_competitor_location (Global Locations chips) --------------------------------------------
INSERT INTO staging.competitive_competitor_location (location_id, competitor_id, location_name, location_type, country, source_url) VALUES
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Rivertown plant', 'plant', 'Exampleland', 'https://example.test/eds/locations'),
  ('a1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Pune office', 'office', 'India', NULL),
  ('a1000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Abu Dhabi sales office', 'office', 'UAE', NULL),
  ('a1000000-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'Nordhafen works', 'plant', 'Northland', NULL),
  ('a1000000-0000-0000-0000-000000000005', '22222222-2222-2222-2222-222222222222', 'Gdansk assembly', 'plant', 'Poland', 'https://example.test/northwind/gdansk');

-- ---- leaders + records -----------------------------------------------------------------------------------
INSERT INTO staging.competitive_leader (leader_id, competitor_id, full_name, role_title, organization, avatar_initials, role_source_url, detail_route) VALUES
  ('b1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Alma Fictional', 'Chief Executive Officer', 'Example Defence Systems Limited', 'AF', 'https://example.test/eds/leadership', NULL),
  ('b1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Bruno Testcase', 'Chief Technology Officer', 'Example Defence Systems Limited', NULL, 'https://example.test/eds/leadership', NULL),
  ('b1000000-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222', 'Carla Northwind-Sample', 'Managing Director', 'Northwind Arms GmbH', 'CN', NULL, NULL);

INSERT INTO staging.competitive_leader_record (record_id, leader_id, record_type, role_or_degree, institution_or_employer, start_date, end_date, headline, source_url, empty_message) VALUES
  ('c1000000-0000-0000-0000-000000000001', 'b1000000-0000-0000-0000-000000000001', 'experience', 'Chief Executive Officer', 'Example Defence Systems Limited', '2019-04-01', NULL, NULL, 'https://example.test/eds/alma', NULL),
  ('c1000000-0000-0000-0000-000000000002', 'b1000000-0000-0000-0000-000000000001', 'experience', 'Vice President, Land Systems', 'Example Defence Systems Limited', '2012-02-01', '2019-03-31', NULL, 'https://example.test/eds/alma', NULL),
  ('c1000000-0000-0000-0000-000000000003', 'b1000000-0000-0000-0000-000000000001', 'experience', 'Programme Engineer', 'Fictional Ordnance Works', '2004-07-01', '2012-01-31', NULL, NULL, NULL),
  ('c1000000-0000-0000-0000-000000000004', 'b1000000-0000-0000-0000-000000000001', 'education', 'MSc Mechanical Engineering', 'University of Exampleland', '2000-09-01', '2002-06-30', NULL, 'https://example.test/eds/alma', NULL),
  ('c1000000-0000-0000-0000-000000000005', 'b1000000-0000-0000-0000-000000000002', 'experience', 'Chief Technology Officer', 'Example Defence Systems Limited', '2021-01-01', NULL, NULL, NULL, NULL),
  ('c1000000-0000-0000-0000-000000000006', 'b1000000-0000-0000-0000-000000000002', 'education', 'PhD Materials Science', 'Rivertown Institute', '2009-09-01', '2013-06-30', NULL, NULL, NULL);

-- ---- news (competitive_news_article): category is NULL on rows written by backend/news.py -------------------
INSERT INTO staging.competitive_news_article (article_id, competitor_id, headline, article_url, published_date, publisher, category, image_url) VALUES
  ('d1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Example Defence opens second plant in Rivertown', 'https://example.test/news/eds-second-plant', '2026-10-02', 'Example Wire', NULL, NULL),
  ('d1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Example Defence wins export order for towed guns', 'https://example.test/news/eds-export-order', '2026-09-18', 'Defence Sample Daily', 'Orders', NULL),
  ('d1000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Alma Fictional named to national industry council', 'https://example.test/news/alma-council', '2026-08-21', 'Example Wire', 'People', NULL),
  ('d1000000-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'Northwind Arms reports quarterly results', 'https://example.test/news/northwind-results', '2026-09-30', 'Nord Business Test', 'Financial', NULL);

-- ---- competitive signals (+ detail + evidence) -----------------------------------------------------------
INSERT INTO staging.competitive_signal (signal_id, company_id, classification, sequence_no, title, summary, category, event_date, thumbnail_url) VALUES
  ('e1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'threat', 1, 'Example Defence wins 155mm towed gun order from Sampleland', 'A first export order for the EDS-155 in a market KSSL also bids in.', 'Artillery', '2026-10-05', NULL),
  ('e1000000-0000-0000-0000-000000000002', '22222222-2222-2222-2222-222222222222', 'watch', 2, 'Northwind Arms qualifies new fuze line at Gdansk', 'Qualification trials finished; volume production is not yet announced.', 'Ammunition', '2026-09-28', NULL),
  ('e1000000-0000-0000-0000-000000000003', '33333333-3333-3333-3333-333333333333', 'watch', 3, 'Tarvo Systems demonstrates modular fire-control kit', 'Demonstrator shown to two European buyers.', 'Armoured Vehicles', '2026-09-12', NULL),
  ('e1000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'fav', 4, 'Example Defence delays self-propelled gun programme', 'A schedule slip of two quarters is reported by the buyer.', 'Artillery', '2026-08-30', NULL),
  ('e1000000-0000-0000-0000-000000000005', NULL, 'Exploratory', 5, 'Sector note: ammunition lead times lengthen', 'No single company is named in this note.', 'Ammunition', NULL, NULL);

INSERT INTO staging.competitive_signal_detail (signal_id, drawer_title, why_it_matters, what_article_says, impact_eyebrow, provenance, source_name, source_url, ask_box_query) VALUES
  ('e1000000-0000-0000-0000-000000000001', 'Example Defence wins 155mm towed gun order from Sampleland',
   'Sampleland is a market KSSL has bid in twice; an EDS foothold raises the price floor for the next tender.',
   'Sampleland''s ministry signed for 24 EDS-155 towed guns with deliveries from 2027, according to the contract notice.',
   'Threat to KSSL', 'Contract notice, read on 2026-10-06', 'Sampleland MoD notice', 'https://example.test/notices/sampleland-155', NULL),
  ('e1000000-0000-0000-0000-000000000002', 'Northwind Arms qualifies new fuze line at Gdansk',
   'Fuze supply is a shared constraint; a new line eases Northwind''s own lead times.',
   'The company said trials of the new fuze line ended in September.',
   NULL, NULL, 'Northwind press release', 'https://example.test/northwind/fuze-line', NULL),
  ('e1000000-0000-0000-0000-000000000003', 'Tarvo Systems demonstrates modular fire-control kit',
   'The kit targets the same upgrade programmes as KSSL''s retrofit offer.',
   'Tarvo showed the kit to buyers from two countries.',
   'Competitor advance', NULL, 'Tarvo newsroom', 'https://example.test/tarvo/fire-control', NULL),
  ('e1000000-0000-0000-0000-000000000004', 'Example Defence delays self-propelled gun programme',
   'A slip opens a window for KSSL''s alternative.',
   'The buyer reported a two-quarter slip.',
   NULL, NULL, NULL, 'https://example.test/news/eds-delay', NULL),
  ('e1000000-0000-0000-0000-000000000005', 'Sector note: ammunition lead times lengthen',
   'Longer lead times affect every bidder.',
   'An industry body reported lead times above 14 months.',
   NULL, NULL, 'Sample Industry Body', 'https://example.test/industry/lead-times', NULL);

INSERT INTO staging.competitive_signal_evidence (evidence_id, signal_id, evidence_group, label, value, quote, source_url, display_order) VALUES
  ('f1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001', 'fact', 'Competitor', 'Example Defence', NULL, NULL, 1),
  ('f1000000-0000-0000-0000-000000000002', 'e1000000-0000-0000-0000-000000000001', 'fact', 'Deal size', '24 guns', 'the ministry signed for 24 EDS-155 towed guns', 'https://example.test/notices/sampleland-155', 2),
  ('f1000000-0000-0000-0000-000000000003', 'e1000000-0000-0000-0000-000000000001', 'fact', 'Delivery', 'from 2027', NULL, NULL, 3),
  ('f1000000-0000-0000-0000-000000000004', 'e1000000-0000-0000-0000-000000000001', 'key_point', 'Point 1', 'First EDS-155 export order', NULL, NULL, 4),
  ('f1000000-0000-0000-0000-000000000005', 'e1000000-0000-0000-0000-000000000001', 'key_point', 'Point 2', 'Deliveries start in 2027', 'with deliveries from 2027', NULL, 5),
  ('f1000000-0000-0000-0000-000000000006', 'e1000000-0000-0000-0000-000000000001', 'source', 'Example Wire report', NULL, NULL, 'https://example.test/news/eds-sampleland', 6),
  ('f1000000-0000-0000-0000-000000000007', 'e1000000-0000-0000-0000-000000000002', 'fact', 'Competitor', 'Northwind Arms', NULL, NULL, 1),
  ('f1000000-0000-0000-0000-000000000008', 'e1000000-0000-0000-0000-000000000002', 'key_point', 'Point 1', 'Trials ended in September', NULL, NULL, 2),
  ('f1000000-0000-0000-0000-000000000009', 'e1000000-0000-0000-0000-000000000003', 'fact', 'Competitor', 'Tarvo Systems', NULL, NULL, 1);

-- ---- Competitor Moment ------------------------------------------------------------------------------------
INSERT INTO staging_ui.competitive_competitor_moment_level (level_code, level_label, tag_class, display_order) VALUES
  ('THREAT', 'Threat', 'threat', 1),
  ('WATCH', 'Watch', 'watch', 2),
  ('OPPORTUNITY', 'Opportunity', 'opportunity', 3);

INSERT INTO staging_ui.competitive_competitor_moment_time_window (time_window_id, time_window_code, time_window_label, day_count, is_default, display_order) VALUES
  (1, '30d', 'Last 30 days', 30, false, 1),
  (2, '90d', 'Last 90 days', 90, true, 2),
  (3, 'all', 'All time', NULL, false, 3);

INSERT INTO staging.competitive_competitor_moment
  (moment_id, competitor_id, company_display, movement_date, category, country_name, countries, region, program_name, title, card_summary, description,
   what_happened, kssl_analysis, grade, source_label, source_domain, source_url, image_url, display_order) VALUES
  (1, '11111111-1111-1111-1111-111111111111', 'Example Defence', '2026-10-05', 'Contract win', 'Sampleland', NULL, 'Asia', 'EDS-155 towed gun',
   'Example Defence signs Sampleland towed gun contract', 'Example Defence is awarded 24 towed guns by Sampleland.', 'Longer description column (not shown).',
   'Sampleland signed for 24 EDS-155 guns with deliveries from 2027.', 'KSSL loses a reference customer; the next Sampleland tender will price against EDS.', 'THREAT',
   'Sampleland MoD notice', 'example.test', 'https://example.test/notices/sampleland-155', NULL, 1),
  (2, '22222222-2222-2222-2222-222222222222', 'Northwind Arms', '2026-07-14', 'Capacity', 'Poland', NULL, 'Europe', 'Gdansk fuze line',
   'Northwind adds fuze capacity in Poland', 'A new fuze line at Gdansk reaches qualification.', NULL,
   'Northwind finished qualification of a new fuze line at its Gdansk site.', 'Eases a shared supply constraint; watch for pricing effects.', 'WATCH',
   NULL, 'example.test', 'https://example.test/northwind/fuze-line', NULL, 2);

INSERT INTO staging.competitive_competitor_moment_analysis (analysis_id, moment_id, view_name, analysis_text, display_order) VALUES
  (1, 1, 'Market', 'Sampleland has been a repeat KSSL target; an EDS win lowers KSSL odds in the next round.', 1),
  (2, 1, 'Product', 'The EDS-155 competes with the KSSL towed gun in range and weight.', 2),
  (3, 2, 'Supply', 'More fuze supply in Europe may shorten ammunition lead times.', 1);

INSERT INTO staging.competitive_competitor_moment_source (source_id, moment_id, publisher, source_domain, source_type, source_url) VALUES
  (1, 1, 'Sampleland MoD', 'example.test', 'official', 'https://example.test/notices/sampleland-155'),
  (2, 1, 'Example Wire', 'example.test', 'press', 'https://example.test/news/eds-sampleland'),
  (3, 2, 'Northwind press office', 'example.test', 'company', 'https://example.test/northwind/fuze-line');

-- ---- Technology overview feed + drawer ---------------------------------------------------------------------
INSERT INTO staging.technology_company (company_id, display_name, company_type, country_code, is_client) VALUES
  (1, 'Example Defence', 'competitor', 'XX', false),
  (2, 'Orbital Fictional Labs', 'research', 'YY', false);

INSERT INTO staging.technology_source (source_id, label, publisher, source_type, source_kind, source_url, url, access_status, retrieved_at) VALUES
  (1, 'Example Wire report', 'Example Wire', 'press', 'news', 'https://example.test/tech/smart-fuze', 'https://example.test/tech/smart-fuze', 'open', now()),
  (2, 'Orbital Fictional Labs paper', 'Orbital Fictional Labs', 'paper', 'research', 'https://example.test/tech/lab-paper', 'https://example.test/tech/lab-paper', 'open', now());

INSERT INTO staging.technology_overview_article
  (article_id, overview_article_id, pillar_id, category_id, category_text, classification, direction, sequence_no, title, card_summary, summary, article_says,
   client_narrative, published_on, article_date, published_label, primary_company_id, image_url, lens, status, created_at, updated_at) VALUES
  (1, 1, 1, '1', 'Artillery', 'competitor_advance', 'threat', 1, 'Example Defence tests a programmable smart fuze',
   'A programmable fuze that sets burst height from a radar reading.', 'Not shown.',
   'Example Defence reported a successful live-fire test of a programmable fuze with radar-set burst height.',
   'If fielded, the fuze would raise the effect per round of competing ammunition; KSSL has no equivalent in its range.',
   '2026-10-03', NULL, NULL, 1, NULL, 'technology', 'published', now(), now()),
  (2, 2, 1, '2', 'Ammunition', 'adoptable', 'watch', 2, 'Orbital Fictional Labs publishes low-cost propellant additive',
   'A propellant additive that lowers barrel wear in lab tests.', NULL,
   'The lab reports a measurable drop in barrel erosion over 500 rounds.',
   'KSSL could trial the additive in its own propellant lines.',
   '2026-09-20', NULL, NULL, 2, NULL, 'technology', 'published', now(), now()),
  (3, 3, 1, '3', 'Armoured Vehicles', 'market_note', NULL, 3, 'Sample Industry Body maps armour trends',
   'A review of passive armour trends.', NULL, NULL, NULL, '2026-08-15', NULL, NULL, NULL, NULL, 'technology', 'published', now(), now());

INSERT INTO staging.technology_overview_company (overview_company_id, article_id, overview_article_id, company_id, display_label, relationship, relationship_type, display_order) VALUES
  (1, 1, 1, 1, NULL, 'actor', 'competitor', 1),
  (2, 2, 2, 2, 'Orbital Fictional Labs (research lab)', 'actor', 'research', 1);

INSERT INTO staging.technology_overview_fact (fact_id, overview_fact_id, article_id, overview_article_id, fact_key, fact_label, ui_label, fact_value, proof_text, display_order) VALUES
  (1, 1, 1, 1, 'maturity', 'Maturity', 'Maturity', 'Live-fire test', 'a successful live-fire test', 1),
  (2, 2, 1, 1, 'sensor', 'Sensor', 'Sensor', 'Radar', NULL, 2),
  (3, 3, 1, 1, 'first_seen', 'First reported', 'First reported', '3 Oct 2026', NULL, 3);

INSERT INTO staging.technology_overview_key_point (key_point_id, article_id, overview_article_id, point_no, point_text, point_type, evidence_text, display_order) VALUES
  (1, 1, 1, 1, 'Burst height is set from a radar reading', 'capability', 'sets burst height from a radar reading', 1),
  (2, 2, 1, 1, 'Live-fire test completed', 'status', NULL, 2),
  (3, 3, 1, 1, 'No fielding date announced', 'status', NULL, 3);

INSERT INTO staging.technology_overview_source (overview_source_id, article_id, overview_article_id, source_id, source_role, is_primary, provenance_status, display_order) VALUES
  (1, 1, 1, 1, 'primary', true, 'single-source', 1),
  (2, 2, 2, 2, 'primary', true, 'peer-reviewed', 1);
