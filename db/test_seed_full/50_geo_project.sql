-- 50_geo_project.sql  (part B)  Geo footprint and competitor projects: every staging.competitive_geo_* and competitive_project_* table,
-- plus staging_ui.competitive_geo_filter, staging_ui.ui_geo_* and staging_ui.ui_project_*. FICTIONAL, obviously test data
-- (names end "(TEST)", URLs on example.com / example.org / example.net). Latitude / longitude / region are the values of staging.country_reference.
-- Pages: Competitive > Geo Footprint (map, country panel, products supplied, product comparison), Competitive > Projects (feed + drawer).
-- Reads: client 9001, client products 9101-9106, competitors c0ffee00-...-00000000000N (00_base.sql, 10_competitive.sql).
-- Geo ids: locations 50001-50014, presence 501xx, products 502xx, matches 503xx, match specs 504xx, news 505xx, sources 506xx.
-- Project ids: projects 51001-51010, stages 511xx, specs 512xx, timeline 513xx, sources 514xx.
-- Allowed values (prompts/FORMAT.md): overlap_status confirmed/category/none; better_side client/competitor/equal; match_status matched/category_only;
--   decision_level 1 = Aurora behind, 2 = near parity, 3 = Aurora ahead; assessment_stance threat/watch/fav; project stage Concept/Trials/Contract/Production;
--   project region Domestic/Export (the filter codes below). Estimated project values are USD million.
-- competitive_geo_source: product rows set geo_product_id and location_id (as the loader does); match rows also set match_id; 3 location rows set location_id only.
BEGIN;

-- ---------------------------------------------------------------------------------------------------------------- clean (fact_source first, children before parents)
DELETE FROM staging.fact_source WHERE table_name IN ('competitive_geo_location', 'competitive_geo_company_presence', 'competitive_geo_product', 'competitive_geo_product_match', 'competitive_project')
  AND (row_id IN (SELECT location_id::text FROM staging.competitive_geo_location) OR row_id IN (SELECT presence_id::text FROM staging.competitive_geo_company_presence)
    OR row_id IN (SELECT geo_product_id::text FROM staging.competitive_geo_product) OR row_id IN (SELECT match_id::text FROM staging.competitive_geo_product_match)
    OR row_id IN (SELECT project_id::text FROM staging.competitive_project));
DELETE FROM staging_ui.ui_geo_product_comparison_state;
DELETE FROM staging_ui.ui_geo_products_supplied_state;
DELETE FROM staging_ui.ui_geo_country_detail_state;
DELETE FROM staging_ui.ui_geo_footprint_view_state;
DELETE FROM staging_ui.competitive_geo_filter;
DELETE FROM staging_ui.ui_project_metric;
DELETE FROM staging_ui.ui_project_view_state;
DELETE FROM staging_ui.ui_project_sequence_option;
DELETE FROM staging_ui.ui_project_filter;
DELETE FROM staging_ui.ui_project_stage_step;
DELETE FROM staging.competitive_geo_product_specification;
DELETE FROM staging.competitive_geo_product_news;
DELETE FROM staging.competitive_geo_source;
DELETE FROM staging.competitive_geo_product_match;
DELETE FROM staging.competitive_geo_product;
DELETE FROM staging.competitive_geo_company_presence;
DELETE FROM staging.competitive_geo_location;
DELETE FROM staging.competitive_project_timeline;
DELETE FROM staging.competitive_project_stage;
DELETE FROM staging.competitive_project_specification;
DELETE FROM staging.competitive_project_source;
DELETE FROM staging.competitive_project;

-- ---------------------------------------------------------------------------------------------------------------- competitive_geo_location
-- Countries on the Geo Footprint map (pin, region, which kinds of activity occur there, what Aurora does there). 14 rows; presence_types and
-- kssl_presence_summary are the roll-ups of the presence rows below (summary NULL where Aurora has no row).
INSERT INTO staging.competitive_geo_location
  (location_id, country_name, map_label, region_name, latitude, longitude, presence_types, kssl_presence_summary) VALUES
  (50001, 'India', 'India', 'Asia', 20.6, 78.9, 'Export; Local production', 'Aurora produces guns, shells, APCs and carbines at its own plants in Pune.'),
  (50002, 'United Arab Emirates', 'UAE', 'Middle East', 23.4, 53.8, 'Export', 'Aurora exports carbines to the UAE Armed Forces under a 2026 award.'),
  (50003, 'Poland', 'Poland', 'Europe', 51.9, 19.1, 'Export; Licensed production', 'Aurora is preparing a bid for the Polish 155 mm ammunition framework.'),
  (50004, 'France', 'France', 'Europe', 46.2, 2.2, 'Local production', NULL),
  (50005, 'United Kingdom', 'UK', 'Europe', 55.4, -3.4, 'Export', NULL),
  (50006, 'United States', 'USA', 'North America', 37.1, -95.7, 'Local production; Sales and service', NULL),
  (50007, 'Saudi Arabia', 'Saudi Arabia', 'Middle East', 23.9, 45.1, 'Export', 'Aurora is bidding a towed gun in the Saudi 36-gun tender.'),
  (50008, 'Australia', 'Australia', 'Oceania', -25.3, 133.8, 'Local production', NULL),
  (50009, 'Norway', 'Norway', 'Europe', 60.5, 8.5, 'Local production', NULL),
  (50010, 'South Korea', 'South Korea', 'Asia', 35.9, 127.8, 'Local production', NULL),
  (50011, 'Armenia', 'Armenia', 'Asia', 40.1, 45.0, 'Export', NULL),
  (50012, 'Brazil', 'Brazil', 'South America', -14.2, -51.9, 'Export; Sales and service', 'Aurora plans a sales office in Brasilia ahead of the 8x8 tender.'),
  (50013, 'Egypt', 'Egypt', 'Africa', 26.8, 30.8, 'Export; Licensed production; Sales and service', 'Aurora delivered towed guns to the Egyptian Army.'),
  (50014, 'Germany', 'Germany', 'Europe', 51.2, 10.5, 'Export', NULL);

-- ---------------------------------------------------------------------------------------------------------------- competitive_geo_company_presence
-- One company active in one country (country panel list, map filters; overlap_status is the roll-up of that company's matches there). 27 rows:
-- 6 Aurora rows (company_role client, client_id 9001) and 21 competitor rows.
INSERT INTO staging.competitive_geo_company_presence
  (presence_id, location_id, company_role, client_id, competitor_id, company_name, activity_type, presence_status, overlap_status, matched_ranges, product_count, products_summary, relationship_text, display_order) VALUES
  (50101, 50001, 'client', 9001, NULL, 'Aurora Defence (TEST)', 'Local production', 'Active', NULL, NULL, 5, 'Aurora Gun 155 (TEST); Aurora Mounted Gun (TEST); Aurora Shell 155 (TEST); Aurora APC (TEST); Aurora Carbine (TEST)', 'Aurora produces guns, shells, APCs and carbines at its own plants in Pune.', 1),
  (50102, 50002, 'client', 9001, NULL, 'Aurora Defence (TEST)', 'Export', 'Active', NULL, NULL, 1, 'Aurora Carbine (TEST)', 'Aurora exports carbines to the UAE Armed Forces under a 2026 award.', 2),
  (50103, 50007, 'client', 9001, NULL, 'Aurora Defence (TEST)', 'Export', 'Planned', NULL, NULL, 1, 'Aurora Gun 155 (TEST)', 'Aurora is bidding a towed gun in the Saudi 36-gun tender.', 3),
  (50104, 50003, 'client', 9001, NULL, 'Aurora Defence (TEST)', 'Export', 'Planned', NULL, NULL, 1, 'Aurora Shell 155 (TEST)', 'Aurora is preparing a bid for the Polish 155 mm ammunition framework.', 4),
  (50105, 50012, 'client', 9001, NULL, 'Aurora Defence (TEST)', 'Sales and service', 'Planned', NULL, NULL, 1, 'Aurora APC (TEST)', 'Aurora plans a sales office in Brasilia ahead of the 8x8 tender.', 5),
  (50106, 50013, 'client', 9001, NULL, 'Aurora Defence (TEST)', 'Export', 'Active', NULL, NULL, 1, 'Aurora Gun 155 (TEST)', 'Aurora delivered towed guns to the Egyptian Army.', 6),
  (50111, 50009, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST)', 'Local production', 'Active', 'confirmed', 'Ammunition, Artillery', 3, 'Borealis BH-155 Towed Howitzer (TEST); Borealis BMG-52 Mounted Gun (TEST); Borealis Smart Shell 155 (TEST)', 'Borealis builds its guns and shells at the Fjordvik plant.', 7),
  (50112, 50003, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST)', 'Licensed production', 'Planned', 'confirmed', 'Ammunition', 1, 'Borealis Smart Shell 155 (TEST)', 'Borealis plans licensed shell production in Poland.', 8),
  (50113, 50001, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST)', 'Export', 'Active', 'category', NULL, 1, 'Borealis BMG-52 Mounted Gun (TEST)', 'Borealis sells mounted guns to Indian trials units.', 9),
  (50114, 50005, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST)', 'Export', 'Active', 'none', NULL, 1, 'Borealis BH-155 Towed Howitzer (TEST)', 'Borealis exports howitzers to the UK.', 10),
  (50115, 50006, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST)', 'Sales and service', 'Active', 'none', NULL, 1, 'Borealis BH-155 Towed Howitzer (TEST)', 'Borealis runs a spares and service office in Virginia.', 11),
  (50121, 50006, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST)', 'Local production', 'Active', 'confirmed', 'Armoured Vehicles, Unmanned & Counter-UAS', 3, 'Cobalt Guardian APC (TEST); Cobalt Scout IFV (TEST); Cobalt Swarm Interceptor (TEST)', 'Cobalt builds its armoured vehicles and interceptors in Redstone Bay.', 12),
  (50122, 50005, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST)', 'Export', 'Active', 'category', NULL, 1, 'Cobalt Scout IFV (TEST)', 'Cobalt sold IFVs to the UK Army.', 13),
  (50123, 50007, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST)', 'Export', 'Active', 'confirmed', 'Armoured Vehicles', 1, 'Cobalt Guardian APC (TEST)', 'Cobalt supplies APCs to the Saudi National Guard.', 14),
  (50124, 50008, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST)', 'Local production', 'Active', 'none', NULL, 1, 'Cobalt Scout IFV (TEST)', 'Cobalt assembles IFVs in Australia.', 15),
  (50125, 50012, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST)', 'Export', 'Active', 'confirmed', 'Armoured Vehicles', 1, 'Cobalt Guardian APC (TEST)', 'Cobalt is the incumbent 8x8 supplier to the Brazilian Army.', 16),
  (50131, 50010, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000003', 'Halcyon Land Systems (TEST)', 'Local production', 'Active', 'confirmed', 'Ammunition, Artillery, Small Arms', 3, 'Halcyon SPH-155 Self-Propelled Gun (TEST); Halcyon K-Shell 155 (TEST); Halcyon HR-7 Rifle (TEST)', 'Halcyon builds guns, shells and rifles in Changwon.', 17),
  (50132, 50003, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000003', 'Halcyon Land Systems (TEST)', 'Export', 'Active', 'confirmed', 'Ammunition, Artillery', 2, 'Halcyon SPH-155 Self-Propelled Gun (TEST); Halcyon K-Shell 155 (TEST)', 'Halcyon exports self-propelled guns and shells to Poland.', 18),
  (50133, 50013, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000003', 'Halcyon Land Systems (TEST)', 'Licensed production', 'Active', 'confirmed', 'Ammunition', 1, 'Halcyon K-Shell 155 (TEST)', 'Halcyon licensed shell production to an Egyptian plant.', 19),
  (50134, 50001, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000003', 'Halcyon Land Systems (TEST)', 'Export', 'Planned', 'category', NULL, 1, 'Halcyon HR-7 Rifle (TEST)', 'Halcyon offered rifles to the Indian reserve forces.', 20),
  (50141, 50004, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000004', 'Meridian Ordnance (TEST)', 'Local production', 'Active', 'confirmed', 'Ammunition, Armoured Vehicles', 2, 'Meridian LR-155 Long-Range Shell (TEST); Meridian W8 Wheeled APC (TEST)', 'Meridian builds shells and wheeled APCs at Valmont.', 21),
  (50142, 50002, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000004', 'Meridian Ordnance (TEST)', 'Export', 'Active', 'confirmed', 'Ammunition', 1, 'Meridian LR-155 Long-Range Shell (TEST)', 'Meridian supplies long-range shells to the UAE.', 22),
  (50143, 50013, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000004', 'Meridian Ordnance (TEST)', 'Sales and service', 'Active', 'none', NULL, 1, 'Meridian W8 Wheeled APC (TEST)', 'Meridian runs an after-sales site in Cairo.', 23),
  (50144, 50014, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000004', 'Meridian Ordnance (TEST)', 'Export', 'Active', 'none', NULL, 1, 'Meridian Skyguard SAM (TEST)', 'Meridian exports air-defence missiles to Germany for trials.', 24),
  (50151, 50001, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000005', 'Tessera Aerospace (TEST)', 'Local production', 'Active', 'confirmed', 'Small Arms, Unmanned & Counter-UAS', 2, 'Tessera Drone Killer (TEST); Tessera TC-9 Carbine (TEST)', 'Tessera builds interceptors and carbines in Bengaluru.', 25),
  (50152, 50002, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000005', 'Tessera Aerospace (TEST)', 'Export', 'Active', 'confirmed', 'Unmanned & Counter-UAS', 1, 'Tessera Drone Killer (TEST)', 'Tessera exports interceptors to the UAE.', 26),
  (50153, 50011, 'competitor', NULL, 'c0ffee00-0000-4000-8000-000000000005', 'Tessera Aerospace (TEST)', 'Export', 'Active', 'category', NULL, 1, 'Tessera Drone Killer (TEST)', 'Tessera sells interceptors to Armenia.', 27);

-- ---------------------------------------------------------------------------------------------------------------- competitive_geo_product
-- Products a company supplies in a country (Products supplied list; quantity, value, rated power for vehicles, link frequency for drones). 40 rows.
INSERT INTO staging.competitive_geo_product
  (geo_product_id, presence_id, product_name, activity_type, since_date, record_note, reported_value, quantity, product_range, rated_power_value, rated_power_unit, fuel_type, frequency_hz, display_order) VALUES
  (50201, 50101, 'Aurora Gun 155 (TEST)', 'Local production', '2015-04-01', 'Built at the Pune gun plant; 120 guns delivered to the Indian Army.', NULL, '120 guns', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50202, 50101, 'Aurora Mounted Gun (TEST)', 'Local production', '2019-09-01', 'Truck-mounted variant assembled in Pune.', NULL, '36 guns', 'Artillery', NULL, NULL, NULL, NULL, 2),
  (50203, 50101, 'Aurora Shell 155 (TEST)', 'Local production', '2016-06-01', 'Shell filling line at Pune with 1.5 million rounds per year.', NULL, '1.5 million rounds per year', 'Ammunition', NULL, NULL, NULL, NULL, 3),
  (50204, 50101, 'Aurora APC (TEST)', 'Local production', '2021-02-01', '8x8 APC assembled for border units.', NULL, '64 vehicles', 'Armoured Vehicles', 420, 'kW', 'Diesel', NULL, 4),
  (50205, 50101, 'Aurora Carbine (TEST)', 'Local production', '2018-03-01', 'Service carbine in use with infantry battalions.', NULL, '40,000 carbines', 'Small Arms', NULL, NULL, NULL, NULL, 5),
  (50206, 50102, 'Aurora Carbine (TEST)', 'Export', '2026-08-14', 'Contract signed after tender 60005.', 'USD 45 million', '30,000 carbines', 'Small Arms', NULL, NULL, NULL, NULL, 1),
  (50207, 50103, 'Aurora Gun 155 (TEST)', 'Export', NULL, 'Bid planned for the 27 Oct 2026 deadline.', 'USD 240 million (tender value)', '36 guns (tendered)', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50208, 50104, 'Aurora Shell 155 (TEST)', 'Export', NULL, 'Bid planned for the 9 Dec 2026 deadline.', 'USD 185 million (tender value)', '400,000 rounds (tendered)', 'Ammunition', NULL, NULL, NULL, NULL, 1),
  (50209, 50105, 'Aurora APC (TEST)', 'Sales and service', NULL, 'Office opening planned for early 2027.', NULL, 'No units yet', 'Armoured Vehicles', 420, 'kW', 'Diesel', NULL, 1),
  (50210, 50106, 'Aurora Gun 155 (TEST)', 'Export', '2022-11-01', 'First batch delivered 2023.', 'USD 60 million', '18 guns', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50211, 50111, 'Borealis BH-155 Towed Howitzer (TEST)', 'Local production', '2012-05-01', 'Main export howitzer built at Fjordvik.', NULL, '300 guns built', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50212, 50111, 'Borealis BMG-52 Mounted Gun (TEST)', 'Local production', '2018-10-01', 'Truck-mounted gun assembled at Fjordvik.', NULL, '90 guns built', 'Artillery', NULL, NULL, NULL, NULL, 2),
  (50213, 50111, 'Borealis Smart Shell 155 (TEST)', 'Local production', '2020-03-01', 'Guided shell in series production.', NULL, '200,000 rounds built', 'Ammunition', NULL, NULL, NULL, NULL, 3),
  (50214, 50112, 'Borealis Smart Shell 155 (TEST)', 'Licensed production', NULL, 'Licence agreement under negotiation with a Polish plant.', NULL, 'Planned 100,000 rounds per year', 'Ammunition', NULL, NULL, NULL, NULL, 1),
  (50215, 50113, 'Borealis BMG-52 Mounted Gun (TEST)', 'Export', '2025-04-01', 'Trial quantity delivered to the Indian Army.', 'USD 25 million', '4 guns', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50216, 50114, 'Borealis BH-155 Towed Howitzer (TEST)', 'Export', '2024-06-01', 'Sold to the UK Army as an interim gun.', 'USD 90 million', '20 guns', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50217, 50115, 'Borealis BH-155 Towed Howitzer (TEST)', 'Sales and service', '2023-01-01', 'Spares and technical support for US test units.', NULL, 'Service office', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50221, 50121, 'Cobalt Guardian APC (TEST)', 'Local production', '2010-07-01', '8x8 APC in series production.', NULL, '1,200 vehicles built', 'Armoured Vehicles', 450, 'kW', 'Diesel', NULL, 1),
  (50222, 50121, 'Cobalt Scout IFV (TEST)', 'Local production', '2014-09-01', 'Tracked IFV in service with several armies.', NULL, '600 vehicles built', 'Armoured Vehicles', 560, 'kW', 'Diesel', NULL, 2),
  (50223, 50121, 'Cobalt Swarm Interceptor (TEST)', 'Local production', '2024-02-01', 'Counter-UAS interceptor in low-rate production.', NULL, '300 interceptors', 'Unmanned & Counter-UAS', NULL, NULL, NULL, 2400000000, 3),
  (50224, 50122, 'Cobalt Scout IFV (TEST)', 'Export', '2023-05-01', 'IFV selected for a UK fleet top-up.', 'USD 300 million', '100 vehicles', 'Armoured Vehicles', 560, 'kW', 'Diesel', NULL, 1),
  (50225, 50123, 'Cobalt Guardian APC (TEST)', 'Export', '2019-11-01', 'APCs delivered in three batches.', 'USD 520 million', '300 vehicles', 'Armoured Vehicles', 450, 'kW', 'Diesel', NULL, 1),
  (50226, 50124, 'Cobalt Scout IFV (TEST)', 'Local production', '2022-03-01', 'Assembly line with 60% local content.', 'USD 410 million', '90 vehicles', 'Armoured Vehicles', 560, 'kW', 'Diesel', NULL, 1),
  (50227, 50125, 'Cobalt Guardian APC (TEST)', 'Export', '2018-08-01', 'First 8x8 batch delivered; follow-on expected.', 'USD 280 million', '150 vehicles', 'Armoured Vehicles', 450, 'kW', 'Diesel', NULL, 1),
  (50231, 50131, 'Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Local production', '2016-04-01', 'Self-propelled gun in service with the home army.', NULL, '250 guns built', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50232, 50131, 'Halcyon K-Shell 155 (TEST)', 'Local production', '2015-01-01', 'Base-bleed shell produced at 2 million rounds per year.', NULL, '2 million rounds per year', 'Ammunition', NULL, NULL, NULL, NULL, 2),
  (50233, 50131, 'Halcyon HR-7 Rifle (TEST)', 'Local production', '2019-06-01', 'Standard infantry rifle.', NULL, '150,000 rifles', 'Small Arms', NULL, NULL, NULL, NULL, 3),
  (50234, 50132, 'Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Export', '2022-09-01', 'Large framework contract for guns.', 'USD 3.2 billion', '212 guns', 'Artillery', NULL, NULL, NULL, NULL, 1),
  (50235, 50132, 'Halcyon K-Shell 155 (TEST)', 'Export', '2023-03-01', 'Shell supply under the same framework.', 'USD 800 million', '600,000 rounds', 'Ammunition', NULL, NULL, NULL, NULL, 2),
  (50236, 50133, 'Halcyon K-Shell 155 (TEST)', 'Licensed production', '2024-01-01', 'Egyptian plant fills Halcyon shells under licence.', NULL, '300,000 rounds per year', 'Ammunition', NULL, NULL, NULL, NULL, 1),
  (50237, 50134, 'Halcyon HR-7 Rifle (TEST)', 'Export', NULL, 'Offer submitted; no contract.', NULL, 'Offer for 20,000 rifles', 'Small Arms', NULL, NULL, NULL, NULL, 1),
  (50241, 50141, 'Meridian LR-155 Long-Range Shell (TEST)', 'Local production', '2017-05-01', 'Long-range shell produced at 1 million rounds per year.', NULL, '1 million rounds per year', 'Ammunition', NULL, NULL, NULL, NULL, 1),
  (50242, 50141, 'Meridian W8 Wheeled APC (TEST)', 'Local production', '2020-10-01', 'Wheeled APC for the French export market.', NULL, '150 vehicles built', 'Armoured Vehicles', 400, 'kW', 'Diesel', NULL, 2),
  (50243, 50142, 'Meridian LR-155 Long-Range Shell (TEST)', 'Export', '2021-04-01', 'Multi-year ammunition supply contract.', 'USD 350 million', '400,000 rounds', 'Ammunition', NULL, NULL, NULL, NULL, 1),
  (50244, 50143, 'Meridian W8 Wheeled APC (TEST)', 'Sales and service', '2023-09-01', 'Spares and training for earlier APC sales.', NULL, 'Service site', 'Armoured Vehicles', 400, 'kW', 'Diesel', NULL, 1),
  (50245, 50144, 'Meridian Skyguard SAM (TEST)', 'Export', '2025-06-01', 'Evaluation quantity for the Bundeswehr trial.', 'EUR 12 million', '6 missiles', 'Missiles & Air Defence', NULL, NULL, NULL, NULL, 1),
  (50251, 50151, 'Tessera Drone Killer (TEST)', 'Local production', '2024-08-01', 'Interceptor in service with the Indian Army test units.', NULL, '120 interceptors', 'Unmanned & Counter-UAS', NULL, NULL, NULL, 2400000000, 1),
  (50252, 50151, 'Tessera TC-9 Carbine (TEST)', 'Local production', '2023-01-01', 'Carbine produced for domestic buyers.', NULL, '25,000 carbines', 'Small Arms', NULL, NULL, NULL, NULL, 2),
  (50253, 50152, 'Tessera Drone Killer (TEST)', 'Export', '2025-10-01', 'Counter-UAS interceptors for base defence.', 'USD 55 million', '80 interceptors', 'Unmanned & Counter-UAS', NULL, NULL, NULL, 2400000000, 1),
  (50254, 50153, 'Tessera Drone Killer (TEST)', 'Export', '2025-03-01', 'Small export order; spec sheet not published.', 'USD 18 million', '30 interceptors', 'Unmanned & Counter-UAS', NULL, NULL, NULL, 2400000000, 1);

-- ---------------------------------------------------------------------------------------------------------------- competitive_geo_product_match
-- The Aurora product that counters a rival's geo product (Product comparison: scores, level, summary). 24 rows;
-- match_status category_only rows have no scores and no specification rows.
INSERT INTO staging.competitive_geo_product_match
  (match_id, geo_product_id, kssl_product_id, kssl_counter_label, comparison_title, evaluation_label, decision_level, kssl_score, competitor_score, rating_delta, match_basis, qualitative_summary, match_status) VALUES
  (50301, 50211, 9101, 'Aurora Gun 155 (TEST)', 'Aurora Gun 155 (TEST) vs Borealis BH-155 Towed Howitzer (TEST)', 'Rival ahead on rate of fire', 1, 46, 62, -16, 'Same role: 155 mm towed howitzer for export tenders.', 'The BH-155 fires 8 rounds per minute against 6 and deploys 30 seconds faster; range is level.', 'matched'),
  (50302, 50212, 9102, 'Aurora Mounted Gun (TEST)', 'Aurora Mounted Gun (TEST) vs Borealis BMG-52 Mounted Gun (TEST)', 'Near parity', 2, 58, 57, 1, 'Same role: truck-mounted 155 mm gun on an 8x8 chassis.', 'The two guns are level on range and crew; Aurora is lighter and faster on the road, Borealis fires faster.', 'matched'),
  (50303, 50213, 9103, 'Aurora Shell 155 (TEST)', 'Aurora Shell 155 (TEST) vs Borealis Smart Shell 155 (TEST)', 'Rival ahead on range and accuracy', 1, 41, 64, -23, 'Same role: 155 mm extended-range artillery shell.', 'The guided Smart Shell reaches 60 km with 8 m CEP against 36 km and 38 m, but Aurora has the longer shelf life.', 'matched'),
  (50304, 50214, 9103, 'Aurora Shell 155 (TEST)', 'Aurora Shell 155 (TEST) vs Borealis Smart Shell 155 (TEST)', 'Rival ahead on range and accuracy', 1, 41, 64, -23, 'Same role: 155 mm extended-range artillery shell.', 'Licensed production would give Borealis a Polish source for the guided shell.', 'matched'),
  (50305, 50215, 9101, 'Aurora Gun 155 (TEST)', 'Aurora Gun 155 (TEST) vs Borealis BMG-52 Mounted Gun (TEST)', 'Different configuration', NULL, NULL, NULL, NULL, 'Same category: 155 mm gun, but mounted versus towed, so specifications are not comparable.', 'Both address 155 mm gun orders; the BMG-52 is truck-mounted and the Aurora Gun 155 is towed.', 'category_only'),
  (50306, 50221, 9104, 'Aurora APC (TEST)', 'Aurora APC (TEST) vs Cobalt Guardian APC (TEST)', 'Near parity', 2, 52, 56, -4, 'Same role: 8x8 wheeled armoured personnel carrier.', 'The Guardian carries one more person and is faster; Aurora has the longer operational range.', 'matched'),
  (50307, 50223, 9106, 'Aurora Interceptor Drone (TEST)', 'Aurora Interceptor Drone (TEST) vs Cobalt Swarm Interceptor (TEST)', 'Rival ahead on reach', 1, 44, 56, -12, 'Same role: counter-UAS interceptor drone.', 'The Swarm Interceptor reaches 10 km against 8 km and flies 5 minutes longer.', 'matched'),
  (50308, 50224, 9104, 'Aurora APC (TEST)', 'Aurora APC (TEST) vs Cobalt Scout IFV (TEST)', 'Different class', NULL, NULL, NULL, NULL, 'Same category: armoured vehicle, but tracked IFV versus wheeled APC.', 'The Scout IFV is tracked and heavier; specifications are not comparable to a wheeled APC.', 'category_only'),
  (50309, 50225, 9104, 'Aurora APC (TEST)', 'Aurora APC (TEST) vs Cobalt Guardian APC (TEST)', 'Near parity', 2, 52, 56, -4, 'Same role: 8x8 wheeled armoured personnel carrier.', 'The Guardian carries one more person and is faster; Aurora has the longer operational range.', 'matched'),
  (50310, 50227, 9104, 'Aurora APC (TEST)', 'Aurora APC (TEST) vs Cobalt Guardian APC (TEST)', 'Near parity', 2, 52, 56, -4, 'Same role: 8x8 wheeled armoured personnel carrier.', 'The Guardian carries one more person and is faster; Aurora has the longer operational range.', 'matched'),
  (50311, 50231, 9101, 'Aurora Gun 155 (TEST)', 'Aurora Gun 155 (TEST) vs Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Rival ahead on fire rate and reaction', 1, 44, 60, -16, 'Same role: 155 mm gun for export artillery tenders; self-propelled versus towed.', 'The SPH-155 deploys in 15 seconds and fires 8 rounds per minute; Aurora is far lighter at 13.5 t against 47 t.', 'matched'),
  (50312, 50232, 9103, 'Aurora Shell 155 (TEST)', 'Aurora Shell 155 (TEST) vs Halcyon K-Shell 155 (TEST)', 'Aurora ahead on range and accuracy', 3, 62, 48, 14, 'Same role: unguided 155 mm HE base-bleed shell.', 'Aurora reaches 36 km against 32 km and is slightly more accurate; shelf life is equal.', 'matched'),
  (50313, 50233, 9105, 'Aurora Carbine (TEST)', 'Aurora Carbine (TEST) vs Halcyon HR-7 Rifle (TEST)', 'Near parity', 2, 55, 57, -2, 'Same role: 5.56 mm rifle for infantry.', 'HR-7 reaches 50 m further; the Aurora Carbine is 200 g lighter.', 'matched'),
  (50314, 50234, 9101, 'Aurora Gun 155 (TEST)', 'Aurora Gun 155 (TEST) vs Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Rival ahead on fire rate and reaction', 1, 44, 60, -16, 'Same role: 155 mm gun for export artillery tenders; self-propelled versus towed.', 'The SPH-155 deploys in 15 seconds and fires 8 rounds per minute; Aurora is far lighter at 13.5 t against 47 t.', 'matched'),
  (50315, 50235, 9103, 'Aurora Shell 155 (TEST)', 'Aurora Shell 155 (TEST) vs Halcyon K-Shell 155 (TEST)', 'Aurora ahead on range and accuracy', 3, 62, 48, 14, 'Same role: unguided 155 mm HE base-bleed shell.', 'Aurora reaches 36 km against 32 km and is slightly more accurate; shelf life is equal.', 'matched'),
  (50316, 50236, 9103, 'Aurora Shell 155 (TEST)', 'Aurora Shell 155 (TEST) vs Halcyon K-Shell 155 (TEST)', 'Aurora ahead on range and accuracy', 3, 62, 48, 14, 'Same role: unguided 155 mm HE base-bleed shell.', 'Aurora reaches 36 km against 32 km and is slightly more accurate; shelf life is equal.', 'matched'),
  (50317, 50237, 9105, 'Aurora Carbine (TEST)', 'Aurora Carbine (TEST) vs Halcyon HR-7 Rifle (TEST)', 'Specs not on file', NULL, NULL, NULL, NULL, 'Same category: 5.56 mm rifle; the export variant''s specifications are not on file.', 'Both are 5.56 mm infantry weapons; no export spec sheet is available to compare.', 'category_only'),
  (50318, 50241, 9103, 'Aurora Shell 155 (TEST)', 'Aurora Shell 155 (TEST) vs Meridian LR-155 Long-Range Shell (TEST)', 'Rival ahead on range', 1, 41, 58, -17, 'Same role: 155 mm extended-range artillery shell.', 'The LR-155 reaches 55 km against 36 km and has the longer shelf life of 25 years.', 'matched'),
  (50319, 50242, 9104, 'Aurora APC (TEST)', 'Aurora APC (TEST) vs Meridian W8 Wheeled APC (TEST)', 'Near parity', 2, 51, 53, -2, 'Same role: 8x8 wheeled armoured personnel carrier.', 'The W8 carries 10 and goes farther; Aurora has more engine power.', 'matched'),
  (50320, 50243, 9103, 'Aurora Shell 155 (TEST)', 'Aurora Shell 155 (TEST) vs Meridian LR-155 Long-Range Shell (TEST)', 'Rival ahead on range', 1, 41, 58, -17, 'Same role: 155 mm extended-range artillery shell.', 'The LR-155 reaches 55 km against 36 km and has the longer shelf life of 25 years.', 'matched'),
  (50321, 50251, 9106, 'Aurora Interceptor Drone (TEST)', 'Aurora Interceptor Drone (TEST) vs Tessera Drone Killer (TEST)', 'Aurora ahead on reach and endurance', 3, 60, 48, 12, 'Same role: radar-cued electric interceptor drone.', 'Aurora reaches 8 km against 6 km and flies 5 minutes longer.', 'matched'),
  (50322, 50252, 9105, 'Aurora Carbine (TEST)', 'Aurora Carbine (TEST) vs Tessera TC-9 Carbine (TEST)', 'Near parity', 2, 56, 54, 2, 'Same role: 5.56 mm carbine for the domestic market.', 'Aurora reaches 50 m further; the TC-9 is 200 g lighter.', 'matched'),
  (50323, 50253, 9106, 'Aurora Interceptor Drone (TEST)', 'Aurora Interceptor Drone (TEST) vs Tessera Drone Killer (TEST)', 'Aurora ahead on reach and endurance', 3, 60, 48, 12, 'Same role: radar-cued electric interceptor drone.', 'Aurora reaches 8 km against 6 km and flies 5 minutes longer.', 'matched'),
  (50324, 50254, 9106, 'Aurora Interceptor Drone (TEST)', 'Aurora Interceptor Drone (TEST) vs Tessera Drone Killer (TEST)', 'Export variant not on file', NULL, NULL, NULL, NULL, 'Same category: counter-UAS interceptor; the export variant''s specifications are not on file.', 'Both are point-defence interceptors; the Armenian configuration is unpublished.', 'category_only');

-- ---------------------------------------------------------------------------------------------------------------- competitive_geo_product_specification
-- Per-spec rows of a matched comparison (Product comparison table). gap_value = |a - b| / mean * 100. 70 rows.
INSERT INTO staging.competitive_geo_product_specification
  (comparison_spec_id, match_id, spec_name, spec_group, kssl_value, competitor_value, unit, gap_value, better_side, display_order) VALUES
  (50401, 50301, 'Maximum range', 'Performance', '40', '41', 'km', '2.5%', 'equal', 1),
  (50402, 50301, 'Burst rate of fire', 'Performance', '6', '8', 'rds/min', '28.6%', 'competitor', 2),
  (50403, 50301, 'Weight in action', 'Mobility', '13.5', '12.8', 't', '5.3%', 'competitor', 3),
  (50404, 50301, 'Into-action time', 'Mobility', '90', '60', 's', '40.0%', 'competitor', 4),
  (50405, 50302, 'Maximum range', 'Performance', '40', '41', 'km', '2.5%', 'equal', 1),
  (50406, 50302, 'Burst rate of fire', 'Performance', '6', '8', 'rds/min', '28.6%', 'competitor', 2),
  (50407, 50302, 'Weight in action', 'Mobility', '28', '30', 't', '6.9%', 'client', 3),
  (50408, 50302, 'Road speed', 'Mobility', '95', '90', 'km/h', '5.4%', 'client', 4),
  (50409, 50303, 'Maximum range', 'Performance', '36', '60', 'km', '50.0%', 'competitor', 1),
  (50410, 50303, 'Circular error probable', 'Performance', '38', '8', 'm', '130.4%', 'competitor', 2),
  (50411, 50303, 'Shelf life', 'Logistics', '20', '15', 'years', '28.6%', 'client', 3),
  (50412, 50304, 'Maximum range', 'Performance', '36', '60', 'km', '50.0%', 'competitor', 1),
  (50413, 50304, 'Circular error probable', 'Performance', '38', '8', 'm', '130.4%', 'competitor', 2),
  (50414, 50304, 'Shelf life', 'Logistics', '20', '15', 'years', '28.6%', 'client', 3),
  (50415, 50306, 'Troops carried', 'Capacity', '8', '9', 'persons', '11.8%', 'competitor', 1),
  (50416, 50306, 'Top speed', 'Mobility', '100', '105', 'km/h', '4.9%', 'competitor', 2),
  (50417, 50306, 'Operational range', 'Mobility', '600', '550', 'km', '8.7%', 'client', 3),
  (50418, 50306, 'Engine power', 'Mobility', '420', '450', 'kW', '6.9%', 'competitor', 4),
  (50419, 50307, 'Interception range', 'Performance', '8', '10', 'km', '22.2%', 'competitor', 1),
  (50420, 50307, 'Maximum speed', 'Performance', '160', '180', 'km/h', '11.8%', 'competitor', 2),
  (50421, 50307, 'Endurance', 'Performance', '25', '30', 'min', '18.2%', 'competitor', 3),
  (50422, 50309, 'Troops carried', 'Capacity', '8', '9', 'persons', '11.8%', 'competitor', 1),
  (50423, 50309, 'Top speed', 'Mobility', '100', '105', 'km/h', '4.9%', 'competitor', 2),
  (50424, 50309, 'Operational range', 'Mobility', '600', '550', 'km', '8.7%', 'client', 3),
  (50425, 50309, 'Engine power', 'Mobility', '420', '450', 'kW', '6.9%', 'competitor', 4),
  (50426, 50310, 'Troops carried', 'Capacity', '8', '9', 'persons', '11.8%', 'competitor', 1),
  (50427, 50310, 'Top speed', 'Mobility', '100', '105', 'km/h', '4.9%', 'competitor', 2),
  (50428, 50310, 'Operational range', 'Mobility', '600', '550', 'km', '8.7%', 'client', 3),
  (50429, 50310, 'Engine power', 'Mobility', '420', '450', 'kW', '6.9%', 'competitor', 4),
  (50430, 50311, 'Maximum range', 'Performance', '40', '40', 'km', '0.0%', 'equal', 1),
  (50431, 50311, 'Burst rate of fire', 'Performance', '6', '8', 'rds/min', '28.6%', 'competitor', 2),
  (50432, 50311, 'Weight in action', 'Mobility', '13.5', '47', 't', '110.7%', 'client', 3),
  (50433, 50311, 'Into-action time', 'Mobility', '90', '15', 's', '142.9%', 'competitor', 4),
  (50434, 50312, 'Maximum range', 'Performance', '36', '32', 'km', '11.8%', 'client', 1),
  (50435, 50312, 'Circular error probable', 'Performance', '38', '40', 'm', '5.1%', 'client', 2),
  (50436, 50312, 'Shelf life', 'Logistics', '20', '20', 'years', '0.0%', 'equal', 3),
  (50437, 50313, 'Weight (unloaded)', 'Handling', '3.2', '3.4', 'kg', '6.1%', 'client', 1),
  (50438, 50313, 'Effective range', 'Performance', '450', '500', 'm', '10.5%', 'competitor', 2),
  (50439, 50313, 'Magazine capacity', 'Capacity', '30', '30', 'rounds', '0.0%', 'equal', 3),
  (50440, 50314, 'Maximum range', 'Performance', '40', '40', 'km', '0.0%', 'equal', 1),
  (50441, 50314, 'Burst rate of fire', 'Performance', '6', '8', 'rds/min', '28.6%', 'competitor', 2),
  (50442, 50314, 'Weight in action', 'Mobility', '13.5', '47', 't', '110.7%', 'client', 3),
  (50443, 50314, 'Into-action time', 'Mobility', '90', '15', 's', '142.9%', 'competitor', 4),
  (50444, 50315, 'Maximum range', 'Performance', '36', '32', 'km', '11.8%', 'client', 1),
  (50445, 50315, 'Circular error probable', 'Performance', '38', '40', 'm', '5.1%', 'client', 2),
  (50446, 50315, 'Shelf life', 'Logistics', '20', '20', 'years', '0.0%', 'equal', 3),
  (50447, 50316, 'Maximum range', 'Performance', '36', '32', 'km', '11.8%', 'client', 1),
  (50448, 50316, 'Circular error probable', 'Performance', '38', '40', 'm', '5.1%', 'client', 2),
  (50449, 50316, 'Shelf life', 'Logistics', '20', '20', 'years', '0.0%', 'equal', 3),
  (50450, 50318, 'Maximum range', 'Performance', '36', '55', 'km', '41.8%', 'competitor', 1),
  (50451, 50318, 'Circular error probable', 'Performance', '38', '30', 'm', '23.5%', 'competitor', 2),
  (50452, 50318, 'Shelf life', 'Logistics', '20', '25', 'years', '22.2%', 'competitor', 3),
  (50453, 50319, 'Troops carried', 'Capacity', '8', '10', 'persons', '22.2%', 'competitor', 1),
  (50454, 50319, 'Top speed', 'Mobility', '100', '100', 'km/h', '0.0%', 'equal', 2),
  (50455, 50319, 'Operational range', 'Mobility', '600', '700', 'km', '15.4%', 'competitor', 3),
  (50456, 50319, 'Engine power', 'Mobility', '420', '400', 'kW', '4.9%', 'client', 4),
  (50457, 50320, 'Maximum range', 'Performance', '36', '55', 'km', '41.8%', 'competitor', 1),
  (50458, 50320, 'Circular error probable', 'Performance', '38', '30', 'm', '23.5%', 'competitor', 2),
  (50459, 50320, 'Shelf life', 'Logistics', '20', '25', 'years', '22.2%', 'competitor', 3),
  (50460, 50321, 'Interception range', 'Performance', '8', '6', 'km', '28.6%', 'client', 1),
  (50461, 50321, 'Maximum speed', 'Performance', '160', '150', 'km/h', '6.5%', 'client', 2),
  (50462, 50321, 'Endurance', 'Performance', '25', '20', 'min', '22.2%', 'client', 3),
  (50463, 50321, 'Radar detection cue range', 'Sensors', '15', '12', 'km', '22.2%', 'client', 4),
  (50464, 50322, 'Weight (unloaded)', 'Handling', '3.2', '3', 'kg', '6.5%', 'competitor', 1),
  (50465, 50322, 'Effective range', 'Performance', '450', '400', 'm', '11.8%', 'client', 2),
  (50466, 50322, 'Magazine capacity', 'Capacity', '30', '30', 'rounds', '0.0%', 'equal', 3),
  (50467, 50323, 'Interception range', 'Performance', '8', '6', 'km', '28.6%', 'client', 1),
  (50468, 50323, 'Maximum speed', 'Performance', '160', '150', 'km/h', '6.5%', 'client', 2),
  (50469, 50323, 'Endurance', 'Performance', '25', '20', 'min', '22.2%', 'client', 3),
  (50470, 50323, 'Radar detection cue range', 'Sensors', '15', '12', 'km', '22.2%', 'client', 4);

-- ---------------------------------------------------------------------------------------------------------------- competitive_geo_product_news
-- News about a product in a country (News list under the product). 12 rows; source_id points at the product's competitive_geo_source row.
INSERT INTO staging.competitive_geo_product_news
  (news_id, geo_product_id, headline, publisher, published_date, article_url, display_order, source_id) VALUES
  (50501, 50211, 'Borealis delivers 300th BH-155 howitzer', 'Gun Journal (TEST)', '2026-09-12', 'https://news.example.com/borealis-300th-bh155', 1, 50611),
  (50502, 50213, 'Borealis Smart Shell passes qualification', 'Munitions Quarterly (TEST)', '2026-08-03', 'https://news.example.net/smart-shell-qualified', 2, 50613),
  (50503, 50221, 'Cobalt wins follow-on Guardian order', 'Armour Today (TEST)', '2026-09-30', 'https://news.example.com/guardian-follow-on', 3, 50618),
  (50504, 50225, 'Saudi Guard orders more Guardian APCs', 'Gulf Defence Wire (TEST)', '2026-07-21', 'https://news.example.org/saudi-guardian-order', 4, 50622),
  (50505, 50231, 'Halcyon SPH-155 enters Polish service', 'Defence Weekly (TEST)', '2026-06-15', 'https://news.example.com/sph155-polish-service', 5, 50625),
  (50506, 50232, 'Halcyon doubles K-Shell output', 'Munitions Quarterly (TEST)', '2026-05-27', 'https://news.example.net/kshell-double', 6, 50626),
  (50507, 50234, 'Poland signs SPH-155 second executive contract', 'Defence Weekly (TEST)', '2026-04-09', 'https://news.example.com/poland-sph155-second', 7, 50628),
  (50508, 50241, 'Meridian LR-155 reaches 55 km in trials', 'Munitions Quarterly (TEST)', '2026-03-18', 'https://news.example.net/lr155-trials', 8, 50632),
  (50509, 50243, 'UAE extends Meridian shell supply', 'Gulf Defence Wire (TEST)', '2026-02-02', 'https://news.example.org/uae-meridian-extension', 9, 50634),
  (50510, 50251, 'Tessera Drone Killer joins army exercise', 'Counter-UAS Journal (TEST)', '2026-09-05', 'https://news.example.net/drone-killer-exercise', 10, 50637),
  (50511, 50253, 'Tessera wins UAE interceptor deal', 'Gulf Defence Wire (TEST)', '2025-10-14', 'https://news.example.org/tessera-uae-deal', 11, 50639),
  (50512, 50206, 'Aurora wins UAE carbine award', 'Small Arms Review (TEST)', '2026-08-15', 'https://news.example.net/aurora-uae-carbine', 12, 50606);

-- ---------------------------------------------------------------------------------------------------------------- competitive_geo_source
-- Sources of a location, product or comparison (Sources lists of the country panel and product rows). 47 rows.
INSERT INTO staging.competitive_geo_source
  (source_id, location_id, geo_product_id, match_id, source_label, source_type, source_url) VALUES
  (50601, 50001, 50201, NULL, 'Aurora newsroom - Aurora Gun 155 (India)', 'company', 'https://kssl-aurora.example.com/geo/india/50201'),
  (50602, 50001, 50202, NULL, 'Aurora newsroom - Aurora Mounted Gun (India)', 'company', 'https://kssl-aurora.example.com/geo/india/50202'),
  (50603, 50001, 50203, NULL, 'Aurora newsroom - Aurora Shell 155 (India)', 'company', 'https://kssl-aurora.example.com/geo/india/50203'),
  (50604, 50001, 50204, NULL, 'Aurora newsroom - Aurora APC (India)', 'company', 'https://kssl-aurora.example.com/geo/india/50204'),
  (50605, 50001, 50205, NULL, 'Aurora newsroom - Aurora Carbine (India)', 'company', 'https://kssl-aurora.example.com/geo/india/50205'),
  (50606, 50002, 50206, NULL, 'Aurora newsroom - Aurora Carbine (United Arab Emirates)', 'company', 'https://kssl-aurora.example.com/geo/united-arab-emirates/50206'),
  (50607, 50007, 50207, NULL, 'Aurora newsroom - Aurora Gun 155 (Saudi Arabia)', 'company', 'https://kssl-aurora.example.com/geo/saudi-arabia/50207'),
  (50608, 50003, 50208, NULL, 'Aurora newsroom - Aurora Shell 155 (Poland)', 'company', 'https://kssl-aurora.example.com/geo/poland/50208'),
  (50609, 50012, 50209, NULL, 'Aurora newsroom - Aurora APC (Brazil)', 'company', 'https://kssl-aurora.example.com/geo/brazil/50209'),
  (50610, 50013, 50210, NULL, 'Aurora newsroom - Aurora Gun 155 (Egypt)', 'company', 'https://kssl-aurora.example.com/geo/egypt/50210'),
  (50611, 50009, 50211, NULL, 'Borealis Arms newsroom - Borealis BH-155 Towed Howitzer (Norway)', 'company', 'https://borealis-arms.example.com/geo/norway/50211'),
  (50612, 50009, 50212, NULL, 'Borealis Arms newsroom - Borealis BMG-52 Mounted Gun (Norway)', 'company', 'https://borealis-arms.example.com/geo/norway/50212'),
  (50613, 50009, 50213, NULL, 'Borealis Arms newsroom - Borealis Smart Shell 155 (Norway)', 'company', 'https://borealis-arms.example.com/geo/norway/50213'),
  (50614, 50003, 50214, NULL, 'Borealis Arms newsroom - Borealis Smart Shell 155 (Poland)', 'company', 'https://borealis-arms.example.com/geo/poland/50214'),
  (50615, 50001, 50215, NULL, 'Borealis Arms newsroom - Borealis BMG-52 Mounted Gun (India)', 'company', 'https://borealis-arms.example.com/geo/india/50215'),
  (50616, 50005, 50216, NULL, 'Borealis Arms newsroom - Borealis BH-155 Towed Howitzer (United Kingdom)', 'company', 'https://borealis-arms.example.com/geo/united-kingdom/50216'),
  (50617, 50006, 50217, NULL, 'Borealis Arms newsroom - Borealis BH-155 Towed Howitzer (United States)', 'company', 'https://borealis-arms.example.com/geo/united-states/50217'),
  (50618, 50006, 50221, NULL, 'Cobalt Dynamics newsroom - Cobalt Guardian APC (United States)', 'company', 'https://cobalt-dynamics.example.com/geo/united-states/50221'),
  (50619, 50006, 50222, NULL, 'Cobalt Dynamics newsroom - Cobalt Scout IFV (United States)', 'company', 'https://cobalt-dynamics.example.com/geo/united-states/50222'),
  (50620, 50006, 50223, NULL, 'Cobalt Dynamics newsroom - Cobalt Swarm Interceptor (United States)', 'company', 'https://cobalt-dynamics.example.com/geo/united-states/50223'),
  (50621, 50005, 50224, NULL, 'Cobalt Dynamics newsroom - Cobalt Scout IFV (United Kingdom)', 'company', 'https://cobalt-dynamics.example.com/geo/united-kingdom/50224'),
  (50622, 50007, 50225, NULL, 'Cobalt Dynamics newsroom - Cobalt Guardian APC (Saudi Arabia)', 'company', 'https://cobalt-dynamics.example.com/geo/saudi-arabia/50225'),
  (50623, 50008, 50226, NULL, 'Cobalt Dynamics newsroom - Cobalt Scout IFV (Australia)', 'company', 'https://cobalt-dynamics.example.com/geo/australia/50226'),
  (50624, 50012, 50227, NULL, 'Cobalt Dynamics newsroom - Cobalt Guardian APC (Brazil)', 'company', 'https://cobalt-dynamics.example.com/geo/brazil/50227'),
  (50625, 50010, 50231, NULL, 'Halcyon Land Systems newsroom - Halcyon SPH-155 Self-Propelled Gun (South Korea)', 'company', 'https://halcyon-land.example.com/geo/south-korea/50231'),
  (50626, 50010, 50232, NULL, 'Halcyon Land Systems newsroom - Halcyon K-Shell 155 (South Korea)', 'company', 'https://halcyon-land.example.com/geo/south-korea/50232'),
  (50627, 50010, 50233, NULL, 'Halcyon Land Systems newsroom - Halcyon HR-7 Rifle (South Korea)', 'company', 'https://halcyon-land.example.com/geo/south-korea/50233'),
  (50628, 50003, 50234, NULL, 'Halcyon Land Systems newsroom - Halcyon SPH-155 Self-Propelled Gun (Poland)', 'company', 'https://halcyon-land.example.com/geo/poland/50234'),
  (50629, 50003, 50235, NULL, 'Halcyon Land Systems newsroom - Halcyon K-Shell 155 (Poland)', 'company', 'https://halcyon-land.example.com/geo/poland/50235'),
  (50630, 50013, 50236, NULL, 'Halcyon Land Systems newsroom - Halcyon K-Shell 155 (Egypt)', 'company', 'https://halcyon-land.example.com/geo/egypt/50236'),
  (50631, 50001, 50237, NULL, 'Halcyon Land Systems newsroom - Halcyon HR-7 Rifle (India)', 'company', 'https://halcyon-land.example.com/geo/india/50237'),
  (50632, 50004, 50241, NULL, 'Meridian Ordnance newsroom - Meridian LR-155 Long-Range Shell (France)', 'company', 'https://meridian-ordnance.example.com/geo/france/50241'),
  (50633, 50004, 50242, NULL, 'Meridian Ordnance newsroom - Meridian W8 Wheeled APC (France)', 'company', 'https://meridian-ordnance.example.com/geo/france/50242'),
  (50634, 50002, 50243, NULL, 'Meridian Ordnance newsroom - Meridian LR-155 Long-Range Shell (United Arab Emirates)', 'company', 'https://meridian-ordnance.example.com/geo/united-arab-emirates/50243'),
  (50635, 50013, 50244, NULL, 'Meridian Ordnance newsroom - Meridian W8 Wheeled APC (Egypt)', 'company', 'https://meridian-ordnance.example.com/geo/egypt/50244'),
  (50636, 50014, 50245, NULL, 'Meridian Ordnance newsroom - Meridian Skyguard SAM (Germany)', 'company', 'https://meridian-ordnance.example.com/geo/germany/50245'),
  (50637, 50001, 50251, NULL, 'Tessera Aerospace newsroom - Tessera Drone Killer (India)', 'company', 'https://tessera-aero.example.com/geo/india/50251'),
  (50638, 50001, 50252, NULL, 'Tessera Aerospace newsroom - Tessera TC-9 Carbine (India)', 'company', 'https://tessera-aero.example.com/geo/india/50252'),
  (50639, 50002, 50253, NULL, 'Tessera Aerospace newsroom - Tessera Drone Killer (United Arab Emirates)', 'company', 'https://tessera-aero.example.com/geo/united-arab-emirates/50253'),
  (50640, 50011, 50254, NULL, 'Tessera Aerospace newsroom - Tessera Drone Killer (Armenia)', 'company', 'https://tessera-aero.example.com/geo/armenia/50254'),
  (50641, 50009, 50211, 50301, 'Aurora comparison sheet for match 50301', 'company', 'https://kssl-aurora.example.com/compare/50301'),
  (50642, 50010, 50231, 50311, 'Aurora comparison sheet for match 50311', 'company', 'https://kssl-aurora.example.com/compare/50311'),
  (50643, 50001, 50251, 50321, 'Aurora comparison sheet for match 50321', 'company', 'https://kssl-aurora.example.com/compare/50321'),
  (50644, 50004, 50241, 50318, 'Aurora comparison sheet for match 50318', 'company', 'https://kssl-aurora.example.com/compare/50318'),
  (50645, 50001, NULL, NULL, 'India trade statistics (TEST)', 'official', 'https://trade.example.org/india'),
  (50646, 50002, NULL, NULL, 'UAE defence exhibition catalogue (TEST)', 'news', 'https://expo.example.net/uae'),
  (50647, 50003, NULL, NULL, 'Poland armaments review (TEST)', 'official', 'https://mod.example.com/pl/review');

-- ---------------------------------------------------------------------------------------------------------------- competitive_project
-- A competitor defence project (Competitive > Projects feed card and drawer). 10 rows, 2 per competitor; region is the Domestic / Export filter code,
-- stage one of the four stage steps, estimated_value in USD million.
INSERT INTO staging.competitive_project
  (project_id, competitor_id, company_display, project_title, customer, location, kind, region, stage, stage_note, card_summary, estimated_value, grade, latest_milestone, latest_milestone_date, assessment_stance, assessment_read, strategic_assessment, kssl_platform, kssl_advantage, what_the_project_is, researched_as_of, display_order) VALUES
  (51001, 'c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST)', 'BH-155 Polish Howitzer Contract (TEST)', 'Armament Agency of Poland (TEST)', 'Gdansk, Poland', 'production contract', 'Export', 'Contract', 'Contract signed; first deliveries due mid-2027.', 'Borealis supplies 120 BH-155 howitzers to Poland.', 420, 'A', 'Contract signed', '2026-05-12', 'threat', 'The contract gives Borealis a reference in the same NATO market as the Aurora Gun 155 and strengthens its position in the 36-gun Saudi tender.', 'Strengthens Borealis as a NATO supplier of towed artillery; Aurora should stress price and weight.', 'Aurora Gun 155 (TEST)', 'Aurora Gun 155 matches the BH-155 range within 1 km (40 km against 41 km) at a lower unit cost.', 'A programme to deliver 120 towed 155 mm howitzers with digital fire control to the Polish army over four years.', '2026-10-10', 1),
  (51002, 'c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST)', 'Smart Shell Precision Line (TEST)', 'Norwegian Defence Materiel Agency (TEST)', 'Fjordvik, Norway', 'production line', 'Domestic', 'Production', 'Line running at 200,000 rounds per year.', 'A domestic line making guided 155 mm shells.', 150, 'B', 'Line reached full rate', '2026-08-20', 'watch', 'Guided shells in series production give Borealis a precision offer Aurora cannot match with unguided Shell 155 yet.', 'Raises the bar for 155 mm shell tenders asking for precision.', 'Aurora Shell 155 (TEST)', NULL, 'A domestic production line that fills and fuzes guided 155 mm shells for the Norwegian armed forces.', '2026-10-10', 2),
  (51003, 'c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST)', 'Guardian APC Brazil Programme (TEST)', 'Brazilian Army Procurement Command (TEST)', 'Sao Paulo, Brazil', 'supply and assembly', 'Export', 'Trials', 'Acceptance trials under way with local assembly.', 'Cobalt competes to supply 8x8 APCs to Brazil with local assembly.', 410, 'A', 'Acceptance trials began', '2026-09-14', 'threat', 'Cobalt is the incumbent 8x8 supplier and its local assembly offer competes directly with the Aurora APC bid in tender 60003.', 'A win would lock Brazil''s 8x8 fleet to Cobalt for a decade.', 'Aurora APC (TEST)', 'Aurora APC has the longer operational range of 600 km against 550 km.', 'A programme to supply 120 8x8 armoured personnel carriers to Brazil with at least 40% local assembly.', '2026-10-10', 3),
  (51004, 'c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST)', 'Swarm Interceptor Base Defence (TEST)', 'US Army Futures Command (TEST)', 'Redstone Bay, United States', 'development', 'Domestic', 'Concept', 'Concept study with two prototypes.', 'A counter-UAS shield for forward bases using swarm interceptors.', 85, 'C', 'Concept study awarded', '2026-07-02', 'watch', 'A concept-stage programme; it signals Cobalt direction in counter-UAS but is not yet a contract.', 'Watch for a move from concept to trials.', 'Aurora Interceptor Drone (TEST)', NULL, 'A study to defend forward bases against drone swarms with cooperative interceptor drones.', '2026-10-10', 4),
  (51005, 'c0ffee00-0000-4000-8000-000000000003', 'Halcyon Land Systems (TEST)', 'SPH-155 Saudi Localisation (TEST)', 'Ministry of Defence of Saudi Arabia (TEST)', 'Riyadh, Saudi Arabia', 'localisation', 'Export', 'Trials', 'Hot-weather trials completed; localisation talks under way.', 'Halcyon proposes local production of the SPH-155 in Saudi Arabia.', 600, 'A', 'Hot-weather trials completed', '2026-09-22', 'threat', 'Halcyon''s localisation offer targets the same Saudi artillery buyer as Aurora, and a JV would meet the tender''s local-presence clause.', 'Halcyon may secure the Saudi localisation programme before Aurora forms a JV.', 'Aurora Gun 155 (TEST)', 'Aurora Gun 155 is far lighter at 13.5 t against 47 t, easier to transport.', 'A proposal to build the SPH-155 self-propelled gun in Saudi Arabia through a joint venture.', '2026-10-10', 5),
  (51006, 'c0ffee00-0000-4000-8000-000000000003', 'Halcyon Land Systems (TEST)', 'K-Shell Capacity Expansion (TEST)', 'Defense Acquisition Programme Administration (TEST)', 'Changwon, South Korea', 'capacity expansion', 'Domestic', 'Production', 'New line commissioned, ramping up.', 'Halcyon doubles its 155 mm shell output.', 220, 'B', 'New line commissioned', '2026-07-30', 'watch', 'More K-Shell output lets Halcyon undercut export ammunition tenders on price and delivery.', 'Pressure on Aurora in framework shell tenders.', 'Aurora Shell 155 (TEST)', 'Aurora Shell 155 out-ranges the K-Shell by 36 km to 32 km.', 'A line extension that raises K-Shell 155 production to 4 million rounds per year.', '2026-10-10', 6),
  (51007, 'c0ffee00-0000-4000-8000-000000000004', 'Meridian Ordnance (TEST)', 'LR-155 Gulf Supply Contract (TEST)', 'UAE Armed Forces (TEST)', 'Abu Dhabi, United Arab Emirates', 'supply contract', 'Export', 'Contract', 'Contract extension signed; deliveries ongoing.', 'Meridian extends long-range shell supply to the UAE.', 130, 'B', 'Extension signed', '2026-02-02', 'threat', 'The extension keeps Meridian ahead of Aurora in Gulf ammunition thanks to the 55 km LR-155.', 'Makes UAE ammunition tenders hard for Aurora to win on range.', 'Aurora Shell 155 (TEST)', NULL, 'A multi-year contract for 400,000 long-range 155 mm shells for the UAE armed forces.', '2026-10-10', 7),
  (51008, 'c0ffee00-0000-4000-8000-000000000004', 'Meridian Ordnance (TEST)', 'W8 APC Francophone Africa (TEST)', 'Ministry of Armed Forces of Morocco (TEST)', 'Rabat, Morocco', 'supply and training', 'Export', 'Concept', 'Evaluation unit shipped; no contract yet.', 'Meridian offers the W8 APC to Morocco.', 90, 'C', 'Evaluation unit shipped', '2026-09-01', 'fav', 'A small, uncertain export campaign in a market where Aurora is not active; it ties up Meridian rather than threatening Aurora.', 'Opens ground for Aurora in India and Brazil while Meridian focuses on Africa.', 'Aurora APC (TEST)', NULL, 'A proposal to supply and support wheeled APCs to Morocco, with an evaluation unit already shipped.', '2026-10-10', 8),
  (51009, 'c0ffee00-0000-4000-8000-000000000005', 'Tessera Aerospace (TEST)', 'Drone Killer Indian Army Fast-Track (TEST)', 'Ministry of Defence of India (TEST)', 'Bengaluru, India', 'fast-track procurement', 'Domestic', 'Trials', 'User trials under way.', 'Fast-track purchase of interceptor drones for the Indian Army.', 60, 'A', 'User trials began', '2026-09-05', 'threat', 'A domestic fast-track pushes Tessera ahead of the Aurora Interceptor Drone in the home market.', 'Domestic preference rules favour Tessera if it passes trials first.', 'Aurora Interceptor Drone (TEST)', 'Aurora Interceptor Drone reaches 8 km against 6 km.', 'A fast-track procurement of radar-cued interceptor drones for Indian Army air-defence units.', '2026-10-10', 9),
  (51010, 'c0ffee00-0000-4000-8000-000000000005', 'Tessera Aerospace (TEST)', 'TC-9 Carbine Reserve Units (TEST)', 'Ministry of Defence of India (TEST)', 'Bengaluru, India', 'supply contract', 'Domestic', 'Contract', 'Order placed for reserve units.', 'Tessera supplies carbines to reserve units.', 115, 'B', 'Order placed', '2026-06-18', 'watch', 'A domestic carbine order for reserve units; Aurora competes in the phase 2 replacement programme.', 'Shows Tessera can win domestic small-arms orders.', 'Aurora Carbine (TEST)', 'Aurora Carbine reaches 450 m against 400 m.', 'An order for 25,000 TC-9 carbines for Indian reserve units.', '2026-10-10', 10);

-- ---------------------------------------------------------------------------------------------------------------- competitive_project_stage
-- The four-step stage stepper of a project (is_current marks the project's stage). 40 rows = 10 projects x Concept / Trials / Contract / Production.
INSERT INTO staging.competitive_project_stage
  (project_stage_id, project_id, stage_name, stage_order, is_current) VALUES
  (51101, 51001, 'Concept', 1, false),
  (51102, 51001, 'Trials', 2, false),
  (51103, 51001, 'Contract', 3, true),
  (51104, 51001, 'Production', 4, false),
  (51105, 51002, 'Concept', 1, false),
  (51106, 51002, 'Trials', 2, false),
  (51107, 51002, 'Contract', 3, false),
  (51108, 51002, 'Production', 4, true),
  (51109, 51003, 'Concept', 1, false),
  (51110, 51003, 'Trials', 2, true),
  (51111, 51003, 'Contract', 3, false),
  (51112, 51003, 'Production', 4, false),
  (51113, 51004, 'Concept', 1, true),
  (51114, 51004, 'Trials', 2, false),
  (51115, 51004, 'Contract', 3, false),
  (51116, 51004, 'Production', 4, false),
  (51117, 51005, 'Concept', 1, false),
  (51118, 51005, 'Trials', 2, true),
  (51119, 51005, 'Contract', 3, false),
  (51120, 51005, 'Production', 4, false),
  (51121, 51006, 'Concept', 1, false),
  (51122, 51006, 'Trials', 2, false),
  (51123, 51006, 'Contract', 3, false),
  (51124, 51006, 'Production', 4, true),
  (51125, 51007, 'Concept', 1, false),
  (51126, 51007, 'Trials', 2, false),
  (51127, 51007, 'Contract', 3, true),
  (51128, 51007, 'Production', 4, false),
  (51129, 51008, 'Concept', 1, true),
  (51130, 51008, 'Trials', 2, false),
  (51131, 51008, 'Contract', 3, false),
  (51132, 51008, 'Production', 4, false),
  (51133, 51009, 'Concept', 1, false),
  (51134, 51009, 'Trials', 2, true),
  (51135, 51009, 'Contract', 3, false),
  (51136, 51009, 'Production', 4, false),
  (51137, 51010, 'Concept', 1, false),
  (51138, 51010, 'Trials', 2, false),
  (51139, 51010, 'Contract', 3, true),
  (51140, 51010, 'Production', 4, false);

-- ---------------------------------------------------------------------------------------------------------------- competitive_project_specification
-- Stated parameters of a project (Facts list of the drawer; contract values are rows here). 26 rows.
INSERT INTO staging.competitive_project_specification
  (project_spec_id, project_id, spec_label, spec_value, unit, display_order) VALUES
  (51201, 51001, 'Calibre', '155', 'mm', 1),
  (51202, 51001, 'Guns in scope', '120', 'guns', 2),
  (51203, 51001, 'Contract value', '420', 'USD million', 3),
  (51204, 51002, 'Calibre', '155', 'mm', 1),
  (51205, 51002, 'Annual capacity', '200000', 'rounds', 2),
  (51206, 51002, 'Contract value', '150', 'USD million', 3),
  (51207, 51003, 'Vehicles in scope', '120', 'vehicles', 1),
  (51208, 51003, 'Local assembly', '40', 'percent minimum', 2),
  (51209, 51003, 'Contract value', '410', 'USD million', 3),
  (51210, 51004, 'Interceptors per base', '24', 'drones', 1),
  (51211, 51004, 'Study value', '85', 'USD million', 2),
  (51212, 51005, 'Calibre', '155', 'mm', 1),
  (51213, 51005, 'Local content target', '35', 'percent', 2),
  (51214, 51005, 'Programme value', '600', 'USD million', 3),
  (51215, 51006, 'Annual capacity', '4000000', 'rounds', 1),
  (51216, 51006, 'Project value', '220', 'USD million', 2),
  (51217, 51007, 'Shells', '400000', 'rounds', 1),
  (51218, 51007, 'Contract value', '130', 'USD million', 2),
  (51219, 51007, 'Maximum range', '55', 'km', 3),
  (51220, 51008, 'Vehicles', '40', 'APCs', 1),
  (51221, 51008, 'Programme value', '90', 'USD million', 2),
  (51222, 51009, 'Interceptor range', '6', 'km', 1),
  (51223, 51009, 'Batteries', '12', 'units', 2),
  (51224, 51009, 'Programme value', '60', 'USD million', 3),
  (51225, 51010, 'Carbines', '25000', 'units', 1),
  (51226, 51010, 'Contract value', '115', 'USD million', 2);

-- ---------------------------------------------------------------------------------------------------------------- competitive_project_timeline
-- Dated events of a project, oldest first (Timeline of the drawer; is_expected = future event). 30 rows.
INSERT INTO staging.competitive_project_timeline
  (timeline_id, project_id, event_date, event_title, event_description, is_expected, display_order) VALUES
  (51301, 51001, '2025-11-04', 'Tender issued', 'The Polish agency issued the howitzer tender.', false, 1),
  (51302, 51001, '2026-05-12', 'Contract signed', 'Borealis signed the 120-gun contract.', false, 2),
  (51303, 51001, '2026-09-01', 'Design review completed', 'Critical design review passed.', false, 3),
  (51304, 51001, '2027-06-30', 'First deliveries', 'First guns due to the army.', true, 4),
  (51305, 51002, '2024-03-15', 'Line investment approved', 'Board approved the precision line.', false, 1),
  (51306, 51002, '2026-08-20', 'Line reached full rate', 'Output reached 200,000 rounds per year.', false, 2),
  (51307, 51002, '2027-03-31', 'Second shift added', 'A second shift is planned.', true, 3),
  (51308, 51003, '2025-12-02', 'Tender shortlist', 'Cobalt shortlisted with two other bidders.', false, 1),
  (51309, 51003, '2026-09-14', 'Acceptance trials began', 'Trials of the Brazilian-assembled prototype began.', false, 2),
  (51310, 51003, '2027-02-28', 'Trials end', 'Trials expected to end.', true, 3),
  (51311, 51004, '2026-07-02', 'Concept study awarded', 'Two prototype teams selected.', false, 1),
  (51312, 51004, '2027-01-15', 'Prototype demonstration', 'First field demonstration planned.', true, 2),
  (51313, 51005, '2026-03-10', 'Proposal submitted', 'Halcyon submitted the localisation proposal.', false, 1),
  (51314, 51005, '2026-09-22', 'Hot-weather trials completed', 'Trials in Saudi summer completed.', false, 2),
  (51315, 51005, '2027-04-01', 'JV decision', 'Saudi decision on a JV expected.', true, 3),
  (51316, 51006, '2025-06-01', 'Line construction began', 'Construction of the new line started.', false, 1),
  (51317, 51006, '2026-07-30', 'New line commissioned', 'First shells off the new line.', false, 2),
  (51318, 51006, '2027-01-31', 'Full rate', 'Full rate expected.', true, 3),
  (51319, 51007, '2021-04-01', 'First contract signed', 'Initial supply contract signed.', false, 1),
  (51320, 51007, '2026-02-02', 'Extension signed', 'Contract extended by three years.', false, 2),
  (51321, 51007, '2028-12-31', 'Contract end', 'Extended contract ends.', true, 3),
  (51322, 51008, '2026-06-10', 'Demonstration in Rabat', 'W8 demonstrated to the army.', false, 1),
  (51323, 51008, '2026-09-01', 'Evaluation unit shipped', 'Evaluation unit shipped for trials.', false, 2),
  (51324, 51008, '2027-05-31', 'Decision expected', 'Moroccan decision expected.', true, 3),
  (51325, 51009, '2026-04-22', 'Request for proposals', 'Fast-track RFP issued.', false, 1),
  (51326, 51009, '2026-09-05', 'User trials began', 'User trials started with two vendors.', false, 2),
  (51327, 51009, '2027-01-31', 'Trials end', 'Trials expected to end.', true, 3),
  (51328, 51010, '2026-02-18', 'Requirement approved', 'Reserve unit requirement approved.', false, 1),
  (51329, 51010, '2026-06-18', 'Order placed', '25,000 carbines ordered.', false, 2),
  (51330, 51010, '2027-09-30', 'Deliveries end', 'Deliveries expected to complete.', true, 3);

-- ---------------------------------------------------------------------------------------------------------------- competitive_project_source
-- Sources of a project (Sources list of the drawer; source_type official / company / news). 23 rows.
INSERT INTO staging.competitive_project_source
  (source_id, project_id, source_label, source_url, source_domain, source_type) VALUES
  (51401, 51001, 'Polish agency contract notice', 'https://mod.example.com/pl/bh155-contract', 'mod.example.com', 'official'),
  (51402, 51001, 'Borealis press release', 'https://borealis-arms.example.com/news/bh155-poland', 'borealis-arms.example.com', 'company'),
  (51403, 51001, 'Gun Journal report', 'https://news.example.com/borealis-poland-howitzers', 'news.example.com', 'news'),
  (51404, 51002, 'Borealis annual report', 'https://borealis-arms.example.com/ir/annual-2025', 'borealis-arms.example.com', 'company'),
  (51405, 51002, 'Munitions Quarterly report', 'https://news.example.net/smart-shell-line', 'news.example.net', 'news'),
  (51406, 51003, 'Brazilian Army tender page', 'https://tenders.example.com/br/60003', 'tenders.example.com', 'official'),
  (51407, 51003, 'Armour Today report', 'https://news.example.com/cobalt-brazil-trials', 'news.example.com', 'news'),
  (51408, 51004, 'US Army award notice', 'https://mod.example.com/us/swarm-concept', 'mod.example.com', 'official'),
  (51409, 51004, 'Counter-UAS Journal', 'https://news.example.net/cobalt-swarm-concept', 'news.example.net', 'news'),
  (51410, 51005, 'Halcyon investor note', 'https://halcyon-land.example.com/ir/saudi-localisation', 'halcyon-land.example.com', 'company'),
  (51411, 51005, 'Gulf Defence Wire', 'https://news.example.org/halcyon-saudi', 'news.example.org', 'news'),
  (51412, 51005, 'Saudi MoD statement', 'https://mod.example.com/sa/localisation', 'mod.example.com', 'official'),
  (51413, 51006, 'Halcyon press release', 'https://halcyon-land.example.com/news/kshell-line', 'halcyon-land.example.com', 'company'),
  (51414, 51006, 'Munitions Quarterly', 'https://news.example.net/kshell-line', 'news.example.net', 'news'),
  (51415, 51007, 'UAE Armed Forces notice', 'https://mod.example.com/ae/lr155-extension', 'mod.example.com', 'official'),
  (51416, 51007, 'Gulf Defence Wire', 'https://news.example.org/uae-lr155-extension', 'news.example.org', 'news'),
  (51417, 51008, 'Meridian press release', 'https://meridian-ordnance.example.com/news/w8-morocco', 'meridian-ordnance.example.com', 'company'),
  (51418, 51008, 'Africa Defence Digest', 'https://news.example.net/w8-morocco', 'news.example.net', 'news'),
  (51419, 51009, 'Indian MoD RFP', 'https://mod.example.com/in/drone-killer-rfp', 'mod.example.com', 'official'),
  (51420, 51009, 'Counter-UAS Journal', 'https://news.example.net/drone-killer-trials', 'news.example.net', 'news'),
  (51421, 51009, 'Tessera press release', 'https://tessera-aero.example.com/news/drone-killer-trials', 'tessera-aero.example.com', 'company'),
  (51422, 51010, 'Indian MoD order notice', 'https://mod.example.com/in/tc9-reserve-order', 'mod.example.com', 'official'),
  (51423, 51010, 'Small Arms Review', 'https://news.example.net/tc9-reserve', 'news.example.net', 'news');

-- ================================================================================================================ UI TABLES

-- ui_project_stage_step: the four steps of the project stepper (the prompt reads these names). 4 rows.
INSERT INTO staging_ui.ui_project_stage_step
  (stage_step_id, stage_name, stage_order) VALUES
  (1, 'Concept', 1),
  (2, 'Trials', 2),
  (3, 'Contract', 3),
  (4, 'Production', 4);

-- ui_project_filter: the Domestic / Export filter chips of the Projects page (filter_code is what competitive_project.region holds). 2 rows.
INSERT INTO staging_ui.ui_project_filter
  (filter_id, filter_code, filter_label, display_order, is_default) VALUES
  (1, 'Domestic', 'Domestic', 1, false),
  (2, 'Export', 'Export', 2, false);

-- ui_project_sequence_option: the 'Sequence' drop-down of the Projects page (sort choices). 3 rows.
INSERT INTO staging_ui.ui_project_sequence_option
  (sequence_option_id, sequence_code, sequence_label, display_order, is_default) VALUES
  (1, 'recent', 'Most recent milestone', 1, true),
  (2, 'stage', 'Furthest along', 2, false),
  (3, 'value', 'Largest value', 3, false);

-- ui_project_view_state: what is selected on the Projects page (filter, sequence, selected project, search texts, drawer). 3 rows.
INSERT INTO staging_ui.ui_project_view_state
  (view_state_id, active_filter, selected_sequence, sequence, geography_scope, selected_competitor_id, selected_project_id, search_text, project_search_text, competitor_search_text, panel_open) VALUES
  (51501, 'all', 'recent', 'recent', 'all', NULL, 51001, NULL, NULL, NULL, true),
  (51502, 'Export', 'stage', 'stage', 'Export', NULL, 51003, 'carrier', 'carrier', NULL, true),
  (51503, 'Domestic', 'value', 'value', 'Domestic', NULL, NULL, NULL, NULL, 'Tessera', false);

-- ui_project_metric: the counters above the Projects feed (per view state). 6 rows.
INSERT INTO staging_ui.ui_project_metric
  (metric_id, view_state_id, metric_label, metric_value, metric_unit, display_order) VALUES
  (51511, 51501, 'Projects tracked', 10, 'projects', 1),
  (51512, 51501, 'In production', 2, 'projects', 2),
  (51513, 51501, 'Under contract', 3, 'projects', 3),
  (51514, 51501, 'Threats', 5, 'projects', 4),
  (51515, 51501, 'Export projects', 5, 'projects', 5),
  (51516, 51501, 'Total estimated value', 2280, 'USD million', 6);

-- competitive_geo_filter: the filters of the Geo Footprint page (company, country, activity, overlap) with option counts. 6 rows.
INSERT INTO staging_ui.competitive_geo_filter
  (filter_id, filter_type, filter_label, option_label, selected_value, record_count, display_order, is_active) VALUES
  (50701, 'company', 'Company', 'All companies', 'all', 6, 1, true),
  (50702, 'company', 'Company', 'Aurora Defence (TEST)', '9001', 6, 2, true),
  (50703, 'country', 'Country', 'All countries', 'all', 14, 3, true),
  (50704, 'activity', 'Activity', 'Local production', 'Local production', 8, 4, true),
  (50705, 'overlap', 'Overlap', 'Confirmed overlap', 'confirmed', 15, 5, true),
  (50706, 'overlap', 'Overlap', 'Category only', 'category', 4, 6, false);

-- ui_geo_footprint_view_state: what is selected on the map (centre, zoom, selected country / company, popup, side panel). 3 rows.
-- selected_competitor_id is bigint but competitors have uuid keys, so only the client id 9001 (or NULL) fits.
INSERT INTO staging_ui.ui_geo_footprint_view_state
  (view_state_id, map_center_latitude, map_center_longitude, map_zoom, selected_location_id, popup_location_id, selected_presence_id, selected_competitor_id, panel_open) VALUES
  (50711, 25.0, 40.0, 2, NULL, NULL, NULL, NULL, false),
  (50712, 20.6, 78.9, 4, 50001, 50001, 50101, 9001, true),
  (50713, 23.4, 53.8, 5, 50002, NULL, 50142, NULL, true);

-- ui_geo_country_detail_state: the country panel's counters (active / category-only / rating-matched rivals, Aurora present?). 5 rows.
INSERT INTO staging_ui.ui_geo_country_detail_state
  (state_id, location_id, selected_presence_id, active_competitor_count, category_only_competitor_count, rating_matched_competitor_count, kssl_present) VALUES
  (50721, 50001, 50101, 2, 2, 1, true),
  (50722, 50002, 50102, 2, 0, 2, true),
  (50723, 50003, 50132, 1, 0, 2, true),
  (50724, 50007, 50123, 1, 0, 1, true),
  (50725, 50013, 50133, 2, 0, 1, true);

-- ui_geo_products_supplied_state: counters of the Products supplied panel (products, matched models, export / service sites). 4 rows.
-- competitor_id is bigint but competitors have uuid keys, so only the client id 9001 (or NULL) fits.
INSERT INTO staging_ui.ui_geo_products_supplied_state
  (state_id, competitor_id, location_id, product_count, matched_model_count, export_supply_count, sales_service_site_count, selected_geo_product_id) VALUES
  (50731, 9001, 50001, 5, 0, 0, 0, 50201),
  (50732, NULL, 50003, 2, 2, 1, 0, 50234),
  (50733, NULL, 50002, 1, 1, 1, 0, 50243),
  (50734, NULL, 50001, 2, 2, 0, 0, 50251);

-- ui_geo_product_comparison_state: the headline of the open comparison panel (title, label, level, scores, delta). 5 rows, one per matched comparison shown.
INSERT INTO staging_ui.ui_geo_product_comparison_state
  (comparison_state_id, match_id, comparison_title, evaluation_label, decision_level, kssl_score, competitor_score, rating_delta, match_basis) VALUES
  (50741, 50301, 'Aurora Gun 155 (TEST) vs Borealis BH-155 Towed Howitzer (TEST)', 'Rival ahead on rate of fire', 1, 46, 62, -16, 'Same role: 155 mm towed howitzer for export tenders.'),
  (50742, 50311, 'Aurora Gun 155 (TEST) vs Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Rival ahead on fire rate and reaction', 1, 44, 60, -16, 'Same role: 155 mm gun for export artillery tenders; self-propelled versus towed.'),
  (50743, 50312, 'Aurora Shell 155 (TEST) vs Halcyon K-Shell 155 (TEST)', 'Aurora ahead on range and accuracy', 3, 62, 48, 14, 'Same role: unguided 155 mm HE base-bleed shell.'),
  (50744, 50318, 'Aurora Shell 155 (TEST) vs Meridian LR-155 Long-Range Shell (TEST)', 'Rival ahead on range', 1, 41, 58, -17, 'Same role: 155 mm extended-range artillery shell.'),
  (50745, 50321, 'Aurora Interceptor Drone (TEST) vs Tessera Drone Killer (TEST)', 'Aurora ahead on reach and endurance', 3, 60, 48, 12, 'Same role: radar-cued electric interceptor drone.');

-- ---------------------------------------------------------------------------------------------------------------- staging.fact_source (Trace panel)
-- Product rows: their source link; project cards: their sources; judgement rows for overlap, match status, project stage and stance.
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
SELECT 'competitive_geo_product', s.geo_product_id::text, 'record_note', s.source_url, 'primary', s.source_label, p.record_note, '2026-10-16 08:00:00+00'
FROM staging.competitive_geo_source s
JOIN staging.competitive_geo_product p ON p.geo_product_id = s.geo_product_id
WHERE s.match_id IS NULL;
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
SELECT 'competitive_geo_location', s.location_id::text, 'presence_types', s.source_url,
       CASE s.source_type WHEN 'official' THEN 'primary' ELSE 'independent' END, s.source_label,
       'Country-level source for: ' || l.country_name, '2026-10-16 08:00:00+00'
FROM staging.competitive_geo_source s
JOIN staging.competitive_geo_location l ON l.location_id = s.location_id
WHERE s.geo_product_id IS NULL;
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
SELECT 'competitive_project', s.project_id::text, 'stage', s.source_url,
       CASE s.source_type WHEN 'official' THEN 'primary' WHEN 'company' THEN 'primary' ELSE 'independent' END,
       s.source_label, 'Source for the stage of: ' || p.project_title, '2026-10-16 08:00:00+00'
FROM staging.competitive_project_source s
JOIN staging.competitive_project p ON p.project_id = s.project_id;
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at) VALUES
  ('competitive_geo_company_presence', '50111', 'overlap_status', 'judgement', 'judgement', NULL, 'Confirmed: at least one Borealis product in Norway has a matched Aurora counterpart (BH-155 against Aurora Gun 155).', '2026-10-16 08:00:00+00'),
  ('competitive_geo_company_presence', '50113', 'overlap_status', 'judgement', 'judgement', NULL, 'Category: the only product in India is a mounted gun, a different configuration from the Aurora towed gun, so the overlap is by category.', '2026-10-16 08:00:00+00'),
  ('competitive_geo_company_presence', '50114', 'overlap_status', 'judgement', 'judgement', NULL, 'None: no product in the UK has a counterpart in the Aurora catalogue on file.', '2026-10-16 08:00:00+00'),
  ('competitive_geo_company_presence', '50132', 'overlap_status', 'judgement', 'judgement', NULL, 'Confirmed: SPH-155 and K-Shell 155 both have matched Aurora counterparts.', '2026-10-16 08:00:00+00'),
  ('competitive_geo_company_presence', '50153', 'overlap_status', 'judgement', 'judgement', NULL, 'Category: the Armenian interceptor''s specifications are not on file.', '2026-10-16 08:00:00+00'),
  ('competitive_geo_product_match', '50301', 'match_status', 'judgement', 'judgement', NULL, 'Matched: both products are 155 mm towed howitzers in the same category with comparable specification rows.', '2026-10-16 08:00:00+00'),
  ('competitive_geo_product_match', '50305', 'match_status', 'judgement', 'judgement', NULL, 'Category only: same category, but mounted versus towed, so the specification rows are not comparable.', '2026-10-16 08:00:00+00'),
  ('competitive_geo_product_match', '50311', 'evaluation_label', 'judgement', 'judgement', NULL, 'SPH-155 deploys in 15 seconds and fires 8 rounds per minute against 90 seconds and 6, but weighs 47 t against 13.5 t.', '2026-10-16 08:00:00+00'),
  ('competitive_geo_product_match', '50321', 'qualitative_summary', 'judgement', 'judgement', NULL, 'Aurora reaches 8 km against 6 km and flies 25 minutes against 20, so Aurora leads.', '2026-10-16 08:00:00+00'),
  ('competitive_project', '51001', 'assessment_stance', 'judgement', 'judgement', NULL, 'Threat: the contract strengthens Borealis with a NATO customer in a category where Aurora has the Gun 155.', '2026-10-16 08:00:00+00'),
  ('competitive_project', '51001', 'stage', 'judgement', 'judgement', NULL, 'Contract: the Polish agency notice states the contract was signed on 12 May 2026.', '2026-10-16 08:00:00+00'),
  ('competitive_project', '51003', 'region', 'judgement', 'judgement', NULL, 'Export: the customer is the Brazilian Army and the supplier is American.', '2026-10-16 08:00:00+00'),
  ('competitive_project', '51004', 'stage', 'judgement', 'judgement', NULL, 'Concept: only a study award is reported; no prototype has been tested.', '2026-10-16 08:00:00+00'),
  ('competitive_project', '51008', 'assessment_stance', 'judgement', 'judgement', NULL, 'Favourable: the campaign is in a market where Aurora is not active and ties up Meridian.', '2026-10-16 08:00:00+00'),
  ('competitive_project', '51009', 'assessment_stance', 'judgement', 'judgement', NULL, 'Threat: domestic fast-track favours Tessera against the Aurora Interceptor Drone.', '2026-10-16 08:00:00+00');

COMMIT;
