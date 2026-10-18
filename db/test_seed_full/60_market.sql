-- 60_market.sql  (part B)  Every staging.market_* table. FICTIONAL, obviously test data (names end "(TEST)", URLs on example.com/.org/.net).
-- Pages: Market > Tenders / Market Intelligence (market_tender*), Top opportunity (market_top_opportunity_*, market_opportunity*,
--        market_next_move), Global requirements (market_global_requirement*), filters/charts (market_filter_option, market_category_summary).
-- Reads: client 9001, client products 9101-9106, technology_category 1-6, competitors c0ffee00-...-00000000000N (00_base.sql, 10_competitive.sql).
-- "Today" in this data set is 2026-10-16; days_remaining below are counted from that day.
-- Id ranges: tenders 60001-60011, children 601xx-608xx, opportunities 61001-61006, global requirements 62001-62006.
-- Allowed values (prompts/FORMAT.md): status open/closing/awarded/closed; lean_code go/maybe/pass/won/closed; fit strong/partial/weak;
--   url_kind notice/portal/award.
BEGIN;

-- ---------------------------------------------------------------------------------------------------------------- clean (fact_source first, then children, then parents)
DELETE FROM staging.fact_source WHERE table_name IN ('market_tender', 'market_tender_source', 'market_tender_fit_assessment', 'market_opportunity',
  'market_global_requirement', 'market_top_opportunity_tender', 'market_top_opportunity_project', 'market_next_move')
  AND (row_id IN (SELECT tender_id::text FROM staging.market_tender) OR row_id IN (SELECT source_id::text FROM staging.market_tender_source)
    OR row_id IN (SELECT assessment_id::text FROM staging.market_tender_fit_assessment) OR row_id IN (SELECT opportunity_id::text FROM staging.market_opportunity)
    OR row_id IN (SELECT requirement_id::text FROM staging.market_global_requirement) OR row_id IN (SELECT top_opportunity_tender_id::text FROM staging.market_top_opportunity_tender)
    OR row_id IN (SELECT top_opportunity_project_id::text FROM staging.market_top_opportunity_project) OR row_id IN (SELECT next_move_id::text FROM staging.market_next_move));
DELETE FROM staging.market_tender_product_match_line;
DELETE FROM staging.market_tender_product_match;
DELETE FROM staging.market_tender_competitor_fit;
DELETE FROM staging.market_tender_fit_assessment;
DELETE FROM staging.market_tender_requirement;
DELETE FROM staging.market_tender_source;
DELETE FROM staging.market_tender_closing_window;
DELETE FROM staging.market_tender_portal;
DELETE FROM staging.market_top_opportunity_tender;
DELETE FROM staging.market_top_opportunity_project;
DELETE FROM staging.market_top_opportunity_metric;
DELETE FROM staging.market_next_move;
DELETE FROM staging.market_opportunity_update;
DELETE FROM staging.market_opportunity_source;
DELETE FROM staging.market_opportunity_fit_assessment;
DELETE FROM staging.market_opportunity;
DELETE FROM staging.market_global_requirement_source;
DELETE FROM staging.market_global_requirement_specification;
DELETE FROM staging.market_global_requirement;
DELETE FROM staging.market_category_summary;
DELETE FROM staging.market_filter_option;
DELETE FROM staging.market_tender;

-- ---------------------------------------------------------------------------------------------------------------- market_tender
-- The tender card (Market > Tenders list, Market Intelligence tables, the tender assessment drawer). 11 tenders:
--   open 60001 60003 60004 60009 60010 | closing 60002 60011 | awarded 60005 60006 | closed 60007 60008.
-- kssl_fit / kssl_model / lean_* are the analyst bid read; the fit_assessment child below carries the scored version.
INSERT INTO staging.market_tender
  (tender_id, title, title_localized, tender_number, notice_reference, issuer_display, buyer_name, buyer_organization_id,
   country_code, country_name, category_id, category_text, description, published_date, closing_date, deadline_text,
   days_remaining, is_live, value_text, value_amount, value_currency, expected_revenue_text, quantity, quantity_unit,
   lean_code, lean_text, kssl_fit, kssl_model, rank_position, source_url, url_kind, status,
   submission_method, registration_requirement, local_presence_requirement, frequency, latest_milestone, created_at, updated_at) VALUES
  (60001, '155 mm HE ammunition, 400,000 rounds (TEST)', 'Dostawa amunicji 155 mm HE, 400 000 sztuk (TEST)', 'PL-MND-2026-0155', 'TED-2026-TEST-60001',
   'Armament Agency of Poland (TEST)', 'Ministry of National Defence of Poland (TEST)', 910001,
   'PL', 'Poland', 2, 'Ammunition', 'Framework supply of 155 mm high-explosive artillery rounds with fuzes and propellant charges, four annual call-offs, NATO-standard interfaces.',
   '2026-09-08', '2026-12-09', 'Closes 9 Dec 2026', 54, true, 'USD 185 million', 185000000, 'USD', 'USD 60-95 M (Aurora share)', 400000, 'rounds',
   'go', 'Strong match: Aurora Shell 155 meets the NATO interface and the 30% offset can be met through a Polish line partner.', 'strong', 'Aurora Shell 155 (TEST)', 1,
   'https://tenders.example.com/pl/60001', 'notice', 'open',
   'Electronic bid through the e-Zamowienia Defence portal (TEST)', 'Supplier registration with the Armament Agency required before bidding', 'Local production partner preferred; 30% offset', 'Framework, 4 annual call-offs', 'Pre-bid conference held 2026-10-05',
   '2026-09-08 08:00:00+00', '2026-10-16 08:00:00+00'),
  (60002, 'Towed howitzers 155 mm / 52 cal, 36 guns (TEST)', 'Madafi hawitzer maseuhba 155 mm, 36 madfa (TEST)', 'SA-GAMI-2026-0036', 'NR-SA-60002',
   'General Authority for Military Industries of Saudi Arabia (TEST)', 'Ministry of Defence of Saudi Arabia (TEST)', 910002,
   'SA', 'Saudi Arabia', 1, 'Artillery', 'Thirty-six towed 155 mm / 52 cal howitzers with prime movers, fire control, five years of spares and in-country training.',
   '2026-08-20', '2026-10-27', 'Closes 27 Oct 2026', 11, true, 'USD 240 million', 240000000, 'USD', 'USD 150-210 M', 36, 'guns',
   'maybe', 'Worth qualifying: gun meets range and weight; local presence and offsets are the open gaps.', 'partial', 'Aurora Gun 155 (TEST)', 4,
   'https://portal.example.com/sa/60002', 'portal', 'closing',
   'Sealed bid through the Etimad Defence Portal (TEST)', 'Prequalification with GAMI required', 'Local office or JV with a Saudi company required', 'One-off', 'Deadline extension request pending',
   '2026-08-20 08:00:00+00', '2026-10-16 08:00:00+00'),
  (60003, '8x8 armoured personnel carriers, 120 vehicles (TEST)', 'Aquisicao de blindados 8x8, 120 viaturas (TEST)', 'BR-MD-2026-0120', 'NR-BR-60003',
   'Brazilian Army Procurement Command (TEST)', 'Ministry of Defence of Brazil (TEST)', 910003,
   'BR', 'Brazil', 3, 'Armoured Vehicles', 'One hundred twenty 8x8 amphibious armoured personnel carriers with remote weapon stations, training and a ten-year support contract.',
   '2026-09-29', '2027-01-22', 'Closes 22 Jan 2027', 98, true, 'USD 410 million', 410000000, 'USD', 'USD 220-300 M', 120, 'vehicles',
   'go', 'Aurora APC meets protection and mobility thresholds; transfer-of-technology clause favours a local assembly partner.', 'strong', 'Aurora APC (TEST)', 2,
   'https://tenders.example.com/br/60003', 'notice', 'open',
   'Electronic bid through ComprasNet Defesa (TEST)', 'Brazilian tax registration (CNPJ) or local agent required', 'Local assembly of at least 40% of vehicles', 'One-off, deliveries over 6 years', 'Technical questionnaire published',
   '2026-09-29 08:00:00+00', '2026-10-16 08:00:00+00'),
  (60004, 'Counter-UAS interceptor drone batteries, 24 units (TEST)', NULL, 'FD-MOD-2026-C24', 'NR-FD-60004',
   'Defence Equipment Office of Freedonia (TEST)', 'Ministry of Defence of Freedonia (TEST)', 910004,
   'FD', 'Freedonia (TEST)', 5, 'Unmanned & Counter-UAS', 'Twenty-four short-range counter-UAS batteries using interceptor drones, radar cueing and a command post.',
   '2026-10-01', '2027-02-12', 'Closes 12 Feb 2027', 119, true, 'USD 96 million', 96000000, 'USD', 'USD 30-45 M', 24, 'batteries',
   'maybe', 'Interceptor drone is in field trials only; a teaming partner for radar is needed before bidding.', 'partial', 'Aurora Interceptor Drone (TEST)', 6,
   'https://portal.example.com/fd/60004', 'portal', 'open',
   'Electronic bid through Freedonia eTender (TEST)', 'Security clearance of the bidder required', 'None stated', 'One-off', 'Industry day announced for 2026-11-18',
   '2026-10-01 08:00:00+00', '2026-10-16 08:00:00+00'),
  (60005, 'Assault carbines 5.56 mm, 30,000 units (TEST)', NULL, 'AE-AFC-2026-0301', 'NR-AE-60005',
   'UAE Armed Forces Procurement Council (TEST)', 'UAE Armed Forces (TEST)', 910005,
   'AE', 'United Arab Emirates', 4, 'Small Arms', 'Thirty thousand 5.56 mm carbines with optics, magazines and a three-year armourer training programme.',
   '2026-03-02', '2026-06-30', 'Awarded 14 Aug 2026', NULL, false, 'USD 45 million', 45000000, 'USD', 'USD 45 M (won)', 30000, 'units',
   'won', 'Awarded to Aurora (TEST): carbine met every mandatory requirement and was priced under the incumbent.', 'strong', 'Aurora Carbine (TEST)', 8,
   'https://awards.example.com/ae/60005', 'award', 'awarded',
   'Electronic bid through UAE Armed Forces e-Sourcing (TEST)', 'Vendor registration required', 'None stated', 'One-off', 'Contract signed 2026-08-14',
   '2026-03-02 08:00:00+00', '2026-08-14 08:00:00+00'),
  (60006, 'Wheeled self-propelled guns 155 mm, 18 systems (TEST)', NULL, 'AU-DMO-2026-0018', 'NR-AU-60006',
   'Defence Materiel Office of Australia (TEST)', 'Ministry of Defence of Australia (TEST)', 910006,
   'AU', 'Australia', 1, 'Artillery', 'Eighteen wheeled self-propelled 155 mm guns with ammunition resupply vehicles, awarded to a domestic prime.',
   '2026-02-10', '2026-05-29', 'Awarded 3 Aug 2026', NULL, false, 'USD 280 million', 280000000, 'USD', 'USD 0 M (lost)', 18, 'systems',
   'pass', 'Concluded: awarded to Halcyon Land Systems (TEST); Aurora Mounted Gun did not meet the local-content rule.', 'weak', 'Aurora Mounted Gun (TEST)', 9,
   'https://awards.example.com/au/60006', 'award', 'awarded',
   'Closed tender', 'Not applicable', 'Australian industry content of 60% required', 'One-off', 'Contract signed 2026-08-03',
   '2026-02-10 08:00:00+00', '2026-08-03 08:00:00+00'),
  (60007, '30 mm training ammunition, 2,000,000 rounds (TEST)', NULL, 'NO-FMA-2026-0030', 'NR-NO-60007',
   'Norwegian Defence Materiel Agency (TEST)', 'Ministry of Defence of Norway (TEST)', 910007,
   'NO', 'Norway', 2, 'Ammunition', 'Two million 30 mm cannon training rounds for infantry fighting vehicles; closed without a bid from Aurora.',
   '2026-04-14', '2026-07-15', 'Closed 15 Jul 2026', NULL, false, 'USD 22 million', 22000000, 'USD', 'No bid', 2000000, 'rounds',
   'closed', 'Closed: Aurora has no 30 mm cannon ammunition.', 'weak', 'No matching Aurora product (TEST)', 10,
   'https://tenders.example.com/no/60007', 'notice', 'closed',
   'Electronic bid through Mercell Defence (TEST)', 'Not applicable', 'None stated', 'One-off', 'Deadline passed 2026-07-15',
   '2026-04-14 08:00:00+00', '2026-07-16 08:00:00+00'),
  (60008, 'Short-range air defence missiles, 120 rounds (TEST)', NULL, 'TR-SSB-2026-0120', 'NR-TR-60008',
   'Presidency of Defence Industries of Turkey (TEST)', 'Ministry of National Defence of Turkey (TEST)', 910008,
   'TR', 'Turkey', 6, 'Missiles & Air Defence', 'One hundred twenty short-range surface-to-air missiles with launchers; closed to foreign bidders.',
   '2026-03-20', '2026-06-10', 'Closed 10 Jun 2026', NULL, false, 'USD 130 million', 130000000, 'USD', 'No bid', 120, 'missiles',
   'closed', 'Closed: no Aurora missile product and the tender was restricted to domestic suppliers.', 'weak', 'No matching Aurora product (TEST)', 11,
   'https://portal.example.com/tr/60008', 'portal', 'closed',
   'Restricted tender', 'Turkish defence-industry registration required', 'Domestic suppliers only', 'One-off', 'Awarded to a domestic supplier 2026-07-01',
   '2026-03-20 08:00:00+00', '2026-07-02 08:00:00+00'),
  (60009, 'Self-propelled gun upgrade kits, 24 kits (TEST)', NULL, 'GB-DE&S-2026-0024', 'NR-GB-60009',
   'Defence Equipment and Support Agency of the United Kingdom (TEST)', 'Ministry of Defence of the United Kingdom (TEST)', 910009,
   'GB', 'United Kingdom', 1, 'Artillery', 'Upgrade kits (barrel, autoloader, digital fire control) for twenty-four fielded self-propelled guns.',
   '2026-09-15', '2027-03-18', 'Closes 18 Mar 2027', 153, true, 'USD 150 million', 150000000, 'USD', 'USD 40-70 M', 24, 'kits',
   'maybe', 'Possible fit for Aurora Mounted Gun components; integration with a foreign chassis is unproven.', 'partial', 'Aurora Mounted Gun (TEST)', 5,
   'https://portal.example.com/gb/60009', 'portal', 'open',
   'Electronic bid through Defence Contracts Online (TEST)', 'Supplier registration required', 'UK subsidiary or partner preferred', 'One-off', 'Pre-qualification questionnaire open',
   '2026-09-15 08:00:00+00', '2026-10-16 08:00:00+00'),
  (60010, 'Mine-protected utility vehicles, 300 units (TEST)', 'Khanan-surakshit upyogita vahan, 300 ikai (TEST)', 'IN-MOD-2026-0300', 'NR-IN-60010',
   'Directorate of Procurement of India (TEST)', 'Ministry of Defence of India (TEST)', 910010,
   'IN', 'India', 3, 'Armoured Vehicles', 'Three hundred mine-protected 4x4 utility vehicles for border units, with a five-year warranty.',
   '2026-09-22', '2026-12-30', 'Closes 30 Dec 2026', 75, true, 'USD 120 million', 120000000, 'USD', 'USD 70-100 M', 300, 'vehicles',
   'go', 'Domestic buyer; Aurora APC family can be configured to the utility variant at low risk.', 'strong', 'Aurora APC (TEST)', 3,
   'https://tenders.example.com/in/60010', 'notice', 'open',
   'Electronic bid through the GeM Defence portal (TEST)', 'Seller registration on GeM required', 'Make-in-India: 50% indigenous content', 'One-off', 'Pre-bid meeting on 2026-11-10',
   '2026-09-22 08:00:00+00', '2026-10-16 08:00:00+00'),
  (60011, 'Service carbines 5.56 mm, 5,000 units (TEST)', 'Dienstkarabiner 5,56 mm, 5.000 Stueck (TEST)', 'DE-BAAINBW-2026-0050', 'NR-DE-60011',
   'Federal Office for Equipment of Germany (TEST)', 'Federal Ministry of Defence of Germany (TEST)', 910011,
   'DE', 'Germany', 4, 'Small Arms', 'Five thousand 5.56 mm service carbines for a special-forces unit with suppressors and optics.',
   '2026-08-25', '2026-10-22', 'Closes 22 Oct 2026', 6, true, 'EUR 9 million', 9000000, 'EUR', 'EUR 3-5 M', 5000, 'units',
   'maybe', 'Late call: carbine meets the spec but there is no time to arrange EU certification support.', 'partial', 'Aurora Carbine (TEST)', 7,
   'https://portal.example.com/de/60011', 'portal', 'closing',
   'Electronic bid through DTVP Bund (TEST)', 'DTVP account and EU conformity declaration required', 'EU-based service partner required', 'One-off', 'Final clarification answers issued',
   '2026-08-25 08:00:00+00', '2026-10-16 08:00:00+00');

-- ---------------------------------------------------------------------------------------------------------------- market_tender_closing_window
-- The deadline tracker of a tender (the latest as_of_date row is shown: closing date, extension flag, milestone). 14 rows: one per tender + older snapshots.
INSERT INTO staging.market_tender_closing_window
  (closing_window_id, tender_id, as_of_date, closing_date, published_date, days_remaining, status, is_extension_confirmed, extension_checked_at, milestone_text) VALUES
  (60101, 60001, '2026-10-16', '2026-12-09', '2026-09-08', 54, 'open',    false, '2026-10-16 08:00:00+00', 'Pre-bid conference held 2026-10-05'),
  (60102, 60002, '2026-10-16', '2026-10-27', '2026-08-20', 11, 'closing', false, '2026-10-16 08:00:00+00', 'Deadline extension request pending'),
  (60103, 60002, '2026-10-02', '2026-10-13', '2026-08-20', 11, 'closing', true,  '2026-10-02 08:00:00+00', 'Deadline moved from 13 Oct to 27 Oct 2026'),
  (60104, 60003, '2026-10-16', '2027-01-22', '2026-09-29', 98, 'open',    false, '2026-10-16 08:00:00+00', 'Technical questionnaire published'),
  (60105, 60004, '2026-10-16', '2027-02-12', '2026-10-01', 119, 'open',   false, '2026-10-16 08:00:00+00', 'Industry day announced for 2026-11-18'),
  (60106, 60005, '2026-08-14', '2026-06-30', '2026-03-02', NULL, 'awarded', false, '2026-08-14 08:00:00+00', 'Contract signed 2026-08-14'),
  (60107, 60006, '2026-08-03', '2026-05-29', '2026-02-10', NULL, 'awarded', false, '2026-08-03 08:00:00+00', 'Contract signed 2026-08-03'),
  (60108, 60007, '2026-07-16', '2026-07-15', '2026-04-14', NULL, 'closed',  false, '2026-07-16 08:00:00+00', 'Deadline passed 2026-07-15'),
  (60109, 60008, '2026-07-02', '2026-06-10', '2026-03-20', NULL, 'closed',  false, '2026-07-02 08:00:00+00', 'Awarded to a domestic supplier 2026-07-01'),
  (60110, 60009, '2026-10-16', '2027-03-18', '2026-09-15', 153, 'open',    false, '2026-10-16 08:00:00+00', 'Pre-qualification questionnaire open'),
  (60111, 60010, '2026-10-16', '2026-12-30', '2026-09-22', 75, 'open',     false, '2026-10-16 08:00:00+00', 'Pre-bid meeting on 2026-11-10'),
  (60112, 60011, '2026-10-16', '2026-10-22', '2026-08-25', 6, 'closing',   false, '2026-10-16 08:00:00+00', 'Final clarification answers issued'),
  (60113, 60001, '2026-10-01', '2026-12-09', '2026-09-08', 69, 'open',     false, '2026-10-01 08:00:00+00', 'Clarification round 1 answers issued'),
  (60114, 60010, '2026-10-02', '2026-12-30', '2026-09-22', 89, 'open',     false, '2026-10-02 08:00:00+00', 'Tender documents published');

-- ---------------------------------------------------------------------------------------------------------------- market_tender_portal
-- Procurement portals (Market Intelligence "Source portals" count; joined to a tender source by portal_name for access status).
INSERT INTO staging.market_tender_portal
  (portal_id, portal_name, portal_url, country_code, access_status, registration_required, submission_method) VALUES
  (60201, 'e-Zamowienia Defence (TEST)',           'https://portal.example.com/pl', 'PL', 'open access',        true,  'e-bid'),
  (60202, 'Etimad Defence Portal (TEST)',          'https://portal.example.com/sa', 'SA', 'login needed',       true,  'sealed bid'),
  (60203, 'ComprasNet Defesa (TEST)',              'https://portal.example.com/br', 'BR', 'registration needed', true, 'e-bid'),
  (60204, 'Freedonia eTender (TEST)',              'https://portal.example.com/fd', 'FD', 'login needed',       true,  'e-bid'),
  (60205, 'UAE Armed Forces e-Sourcing (TEST)',    'https://portal.example.com/ae', 'AE', 'login needed',       true,  'e-bid'),
  (60206, 'Defence Procurement Australia Hub (TEST)', 'https://portal.example.com/au', 'AU', 'open access',     false, 'e-bid'),
  (60207, 'Mercell Defence (TEST)',                'https://portal.example.com/no', 'NO', 'open access',        false, 'e-bid'),
  (60208, 'EKAP Defence (TEST)',                   'https://portal.example.com/tr', 'TR', 'login needed',       true,  'restricted bid'),
  (60209, 'Defence Contracts Online (TEST)',       'https://portal.example.com/gb', 'GB', 'registration needed', true, 'e-bid'),
  (60210, 'GeM Defence (TEST)',                    'https://portal.example.com/in', 'IN', 'registration needed', true, 'e-bid'),
  (60211, 'DTVP Bund (TEST)',                      'https://portal.example.com/de', 'DE', 'open access',        true,  'e-bid');

-- ---------------------------------------------------------------------------------------------------------------- market_tender_source
-- Where a tender was found (Sources section of the tender drawer; the primary row first). 17 rows.
INSERT INTO staging.market_tender_source
  (source_id, tender_id, is_primary, portal_name, publisher, source_type, source_url, access_note, retrieved_at, status_check_url) VALUES
  (60301, 60001, true,  'e-Zamowienia Defence (TEST)', 'Armament Agency of Poland (TEST)', 'tender notice', 'https://tenders.example.com/pl/60001', 'Documents downloadable after supplier registration', '2026-10-16 08:00:00+00', 'https://portal.example.com/pl/status/60001'),
  (60302, 60001, false, NULL, 'Defence Weekly (TEST)', 'news', 'https://news.example.org/pl-155-ammo-framework', 'Public article, no login', '2026-10-16 08:00:00+00', NULL),
  (60303, 60002, true,  'Etimad Defence Portal (TEST)', 'General Authority for Military Industries of Saudi Arabia (TEST)', 'portal listing', 'https://portal.example.com/sa/60002', 'Login needed to read the technical annexes', '2026-10-16 08:00:00+00', 'https://portal.example.com/sa/status/60002'),
  (60304, 60002, false, NULL, 'Gulf Defence Wire (TEST)', 'news', 'https://news.example.org/sa-howitzer-tender', NULL, '2026-10-16 08:00:00+00', NULL),
  (60305, 60003, true,  'ComprasNet Defesa (TEST)', 'Brazilian Army Procurement Command (TEST)', 'tender notice', 'https://tenders.example.com/br/60003', 'Notice in Portuguese; English summary on request', '2026-10-16 08:00:00+00', 'https://portal.example.com/br/status/60003'),
  (60306, 60004, true,  'Freedonia eTender (TEST)', 'Defence Equipment Office of Freedonia (TEST)', 'portal listing', 'https://portal.example.com/fd/60004', 'Login needed', '2026-10-16 08:00:00+00', 'https://portal.example.com/fd/status/60004'),
  (60307, 60004, false, NULL, 'Counter-UAS Journal (TEST)', 'news', 'https://news.example.net/fd-counter-uas-tender', NULL, '2026-10-16 08:00:00+00', NULL),
  (60308, 60005, true,  'UAE Armed Forces e-Sourcing (TEST)', 'UAE Armed Forces Procurement Council (TEST)', 'award notice', 'https://awards.example.com/ae/60005', 'Award notice public', '2026-08-14 08:00:00+00', NULL),
  (60309, 60006, true,  'Defence Procurement Australia Hub (TEST)', 'Defence Materiel Office of Australia (TEST)', 'award notice', 'https://awards.example.com/au/60006', 'Award notice public', '2026-08-03 08:00:00+00', NULL),
  (60310, 60007, true,  'Mercell Defence (TEST)', 'Norwegian Defence Materiel Agency (TEST)', 'tender notice', 'https://tenders.example.com/no/60007', 'Closed notice kept online', '2026-07-16 08:00:00+00', NULL),
  (60311, 60008, true,  'EKAP Defence (TEST)', 'Presidency of Defence Industries of Turkey (TEST)', 'portal listing', 'https://portal.example.com/tr/60008', 'Restricted access', '2026-07-02 08:00:00+00', NULL),
  (60312, 60009, true,  'Defence Contracts Online (TEST)', 'Defence Equipment and Support Agency of the United Kingdom (TEST)', 'portal listing', 'https://portal.example.com/gb/60009', 'Registration needed for the PQQ', '2026-10-16 08:00:00+00', 'https://portal.example.com/gb/status/60009'),
  (60313, 60009, false, NULL, 'Land Forces Review (TEST)', 'news', 'https://news.example.org/gb-sp-gun-upgrade', NULL, '2026-10-16 08:00:00+00', NULL),
  (60314, 60010, true,  'GeM Defence (TEST)', 'Directorate of Procurement of India (TEST)', 'tender notice', 'https://tenders.example.com/in/60010', 'Bid document free to download', '2026-10-16 08:00:00+00', 'https://portal.example.com/in/status/60010'),
  (60315, 60010, false, NULL, 'Indian Defence Digest (TEST)', 'news', 'https://news.example.org/in-mine-protected-vehicles', NULL, '2026-10-16 08:00:00+00', NULL),
  (60316, 60011, true,  'DTVP Bund (TEST)', 'Federal Office for Equipment of Germany (TEST)', 'portal listing', 'https://portal.example.com/de/60011', 'Open access, account for bidding', '2026-10-16 08:00:00+00', 'https://portal.example.com/de/status/60011'),
  (60317, 60003, false, NULL, 'Latin Defence Monitor (TEST)', 'news', 'https://news.example.net/br-8x8-tender', NULL, '2026-10-16 08:00:00+00', NULL);

-- ---------------------------------------------------------------------------------------------------------------- market_tender_requirement
-- What the buyer asks for (Requirements section of the tender drawer; each row is a block of label/value lines). 24 rows.
INSERT INTO staging.market_tender_requirement
  (requirement_id, tender_id, display_order, requirement_type, description, scope_text, requirement_note, equipment_scope, rating_band,
   use_case, quantity, quantity_unit, scope_bullet_label, scope_bullet_value, category_text, source_text) VALUES
  (60401, 60001, 1, 'Platform', 'HE projectile 155 mm, NATO-compatible, 52-calibre barrel range.', 'Four annual call-offs of 100,000 rounds each.', 'Fuze type to be agreed at call-off', 'Projectile body, fuze, charge', '30-40 km range band', 'Counter-battery and area fires', 400000, 'rounds', 'Interface', 'NATO AOP-29', 'Ammunition', 'Section 3.1 of the tender documents'),
  (60402, 60001, 2, 'Support', 'Lot acceptance testing in Poland.', 'Acceptance firing at the buyer range.', 'Buyer witnesses every lot', 'Test equipment and range support', NULL, 'Quality assurance', NULL, NULL, 'Warranty', '10 years shelf life', 'Ammunition', 'Section 4.2'),
  (60403, 60001, 3, 'Industrial', 'Offset and local production.', '30% of contract value as Polish industrial participation.', NULL, NULL, NULL, 'Industrial participation', NULL, NULL, 'Offset', '30% of contract value', 'Ammunition', 'Section 6'),
  (60404, 60002, 1, 'Platform', 'Towed 155 mm / 52 cal howitzer, air-transportable, 90 s into action.', 'Thirty-six guns with prime movers.', NULL, 'Gun, sighting, ammunition handling kit', '35-42 km range band', 'Desert deployment', 36, 'guns', 'Mobility', 'Towed, 90 s into action', 'Artillery', 'Annex A of the RFP'),
  (60405, 60002, 2, 'Support', 'Five years of spares, tools and operator training in country.', 'Training for 12 crews.', 'Training in Arabic and English', NULL, NULL, 'Sustainment', NULL, NULL, 'Warranty', '5 years', 'Artillery', 'Annex C'),
  (60406, 60002, 3, 'Industrial', 'Local content and a Saudi joint venture for support.', 'At least 35% local content.', NULL, NULL, NULL, 'Localisation', NULL, NULL, 'Local content', '35% minimum', 'Artillery', 'Annex D'),
  (60407, 60003, 1, 'Platform', '8x8 amphibious APC, STANAG level 4 ballistic, 30 mm remote weapon station.', 'One hundred twenty vehicles in three variants.', 'APC, command and ambulance variants', 'Hull, powerpack, RWS, communications', 'Gross weight 28-32 t', 'Infantry transport', 120, 'vehicles', 'Protection', 'STANAG 4569 level 4', 'Armoured Vehicles', 'Edital item 2'),
  (60408, 60003, 2, 'Industrial', 'Local assembly and transfer of technology.', 'At least 40% of vehicles assembled in Brazil.', NULL, NULL, NULL, 'Industrial participation', NULL, NULL, 'Local assembly', '40% minimum', 'Armoured Vehicles', 'Edital item 9'),
  (60409, 60004, 1, 'Platform', 'Counter-UAS battery with radar, EO tracker and interceptor drones.', 'Twenty-four batteries.', 'Interceptors must defeat Group 2 UAS', 'Radar, command post, 8 interceptors per battery', '5 km engagement radius', 'Point defence of bases', 24, 'batteries', 'Interceptor', 'Reusable or expendable accepted', 'Unmanned & Counter-UAS', 'Technical specification 2.1'),
  (60410, 60004, 2, 'Support', 'Operator and maintainer training.', 'Twelve-week course in country.', NULL, NULL, NULL, 'Training', NULL, NULL, 'Training', '12 weeks', 'Unmanned & Counter-UAS', 'Technical specification 5'),
  (60411, 60005, 1, 'Platform', '5.56 mm carbine, 14.5 in barrel, accessory rail.', 'Thirty thousand carbines.', NULL, 'Carbine, optic, 3 magazines', 'Weight under 3.2 kg', 'Infantry service weapon', 30000, 'units', 'Reliability', '15,000 rounds mean between stoppages', 'Small Arms', 'Section 2'),
  (60412, 60005, 2, 'Support', 'Armourer training.', 'Three-year programme.', NULL, NULL, NULL, 'Training', NULL, NULL, 'Training', '3 years', 'Small Arms', 'Section 5'),
  (60413, 60006, 1, 'Platform', 'Wheeled self-propelled 155 mm / 52 cal gun with 6x6 or 8x8 chassis.', 'Eighteen systems.', NULL, 'Gun, chassis, ammunition resupply vehicle', '40 km range band', 'Mobile fires', 18, 'systems', 'Local content', '60% Australian industry content', 'Artillery', 'Volume 2'),
  (60414, 60006, 2, 'Support', 'Through-life support in Australia.', 'Fifteen-year support.', NULL, NULL, NULL, 'Sustainment', NULL, NULL, 'Support', '15 years', 'Artillery', 'Volume 3'),
  (60415, 60007, 1, 'Platform', '30 mm cannon training round, TP-T.', 'Two million rounds.', NULL, 'Rounds in links', NULL, 'Training', 2000000, 'rounds', 'Calibre', '30 x 173 mm', 'Ammunition', 'Part B'),
  (60416, 60008, 1, 'Platform', 'Short-range surface-to-air missile, infrared seeker.', 'One hundred twenty missiles with 20 launchers.', 'Domestic suppliers only', 'Missile, launcher, test set', '6 km range', 'Point air defence', 120, 'missiles', 'Seeker', 'Imaging infrared', 'Missiles & Air Defence', 'Specification 1'),
  (60417, 60009, 1, 'Platform', 'Upgrade kit: new barrel, autoloader and digital fire control.', 'Twenty-four kits for fielded guns.', 'Fits the existing turret ring', 'Barrel, loader, fire-control computer', 'Rate of fire 8 rpm', 'Fleet modernisation', 24, 'kits', 'Integration', 'No hull change allowed', 'Artillery', 'PQQ section 3'),
  (60418, 60009, 2, 'Support', 'In-service support for ten years.', 'Spares and technical assistance.', NULL, NULL, NULL, 'Sustainment', NULL, NULL, 'Support', '10 years', 'Artillery', 'PQQ section 6'),
  (60419, 60010, 1, 'Platform', 'Mine-protected 4x4 utility vehicle, V-hull, 1.5 t payload.', 'Three hundred vehicles.', 'Variants: cargo, ambulance, communications', 'Hull, powerpack, mission kit', 'STANAG 4569 mine level 3a', 'Border patrol', 300, 'vehicles', 'Indigenous content', '50% minimum', 'Armoured Vehicles', 'RFP chapter 2'),
  (60420, 60010, 2, 'Support', 'Five-year warranty and spares.', 'Depot-level repair in India.', NULL, NULL, NULL, 'Sustainment', NULL, NULL, 'Warranty', '5 years', 'Armoured Vehicles', 'RFP chapter 7'),
  (60421, 60011, 1, 'Platform', '5.56 mm service carbine with integral suppressor option.', 'Five thousand carbines.', NULL, 'Carbine, suppressor, optic', 'Weight under 3.0 kg', 'Special-forces use', 5000, 'units', 'Certification', 'EU conformity declaration', 'Small Arms', 'Leistungsbeschreibung 3'),
  (60422, 60011, 2, 'Support', 'Armourer training and spares.', 'Two-year spares package.', NULL, NULL, NULL, 'Sustainment', NULL, NULL, 'Spares', '2 years', 'Small Arms', 'Leistungsbeschreibung 7'),
  (60423, 60005, 3, 'Industrial', 'Technology transfer for magazines.', 'Local magazine production line.', NULL, NULL, NULL, 'Localisation', NULL, NULL, 'Local content', '20% of value', 'Small Arms', 'Section 7'),
  (60424, 60008, 2, 'Industrial', 'Domestic production only.', 'Foreign bidders must team with a domestic prime.', NULL, NULL, NULL, 'Localisation', NULL, NULL, 'Eligibility', 'Domestic suppliers only', 'Missiles & Air Defence', 'Specification 8');

-- ---------------------------------------------------------------------------------------------------------------- market_tender_fit_assessment
-- The scored Aurora fit of a tender (Fit section / fit chip in the drawer; the newest assessed_at row is shown). 13 rows, 60001 has an older partial read.
INSERT INTO staging.market_tender_fit_assessment
  (assessment_id, tender_id, assessed_at, client_product_id, fit_grade, fit_rank, fit_score, kssl_fit, kssl_fit_rank, kssl_fit_rationale,
   assessment_rationale, kssl_model, kssl_revenue_estimate, match_status, match_summary, revenue_currency, revenue_estimate_min,
   revenue_estimate_max, revenue_estimate_text, revenue_tier) VALUES
  (60501, 60001, '2026-10-16 08:00:00+00', 9103, 'strong',  1, 91.0, 'strong',  1, 'NATO interface, 30-40 km range band and lot testing are all met; offsets need a Polish line partner.',
   'Newest read after the pre-bid conference confirmed fuze flexibility.', 'Aurora Shell 155 (TEST)', 'USD 60-95 M', 'matched', 'Aurora Shell 155 matches the HE round in full.', 'USD', 60000000, 95000000, 'USD 60-95 M over 4 years', 'high'),
  (60502, 60001, '2026-09-20 08:00:00+00', 9103, 'partial', 2, 74.0, 'partial', 2, 'Fuze type unclear before the pre-bid conference.',
   'Older read superseded by 60501.', 'Aurora Shell 155 (TEST)', 'USD 40-70 M', 'partial', 'Fuze interface was not confirmed.', 'USD', 40000000, 70000000, 'USD 40-70 M', 'medium'),
  (60503, 60002, '2026-10-16 08:00:00+00', 9101, 'partial', 4, 66.0, 'partial', 4, 'Range and weight meet the band; no local presence in Saudi Arabia and the JV clause is open.',
   'Needs a Saudi partner before the 27 Oct deadline.', 'Aurora Gun 155 (TEST)', 'USD 150-210 M', 'partial', 'Gun matches; support set-up does not.', 'USD', 150000000, 210000000, 'USD 150-210 M', 'high'),
  (60504, 60003, '2026-10-16 08:00:00+00', 9104, 'strong',  2, 87.0, 'strong',  2, 'Protection, amphibious capability and 8x8 layout match; local assembly can be set up with a partner.',
   'Brazil local-assembly clause is an opportunity for a partner.', 'Aurora APC (TEST)', 'USD 220-300 M', 'matched', 'APC variant matches the request.', 'USD', 220000000, 300000000, 'USD 220-300 M', 'high'),
  (60505, 60004, '2026-10-16 08:00:00+00', 9106, 'partial', 6, 58.0, 'partial', 6, 'Interceptor drone is in trials; radar and command post must come from a partner.',
   'Bid only as a team.', 'Aurora Interceptor Drone (TEST)', 'USD 30-45 M', 'partial', 'Interceptor matches, battery does not.', 'USD', 30000000, 45000000, 'USD 30-45 M', 'medium'),
  (60506, 60005, '2026-08-14 08:00:00+00', 9105, 'strong',  8, 93.0, 'strong',  8, 'Carbine met every mandatory requirement; won.',
   'Outcome read after award.', 'Aurora Carbine (TEST)', 'USD 45 M', 'matched', 'Full match; contract signed.', 'USD', 45000000, 45000000, 'USD 45 M (won)', 'medium'),
  (60507, 60006, '2026-08-03 08:00:00+00', 9102, 'weak',    9, 28.0, 'weak',    9, 'Local-content rule of 60% could not be met.',
   'Outcome read after award to Halcyon Land Systems (TEST).', 'Aurora Mounted Gun (TEST)', 'USD 0', 'no_match', 'Mounted gun did not qualify.', 'USD', 0, 0, 'USD 0 (lost)', 'low'),
  (60508, 60007, '2026-07-16 08:00:00+00', NULL, 'weak',   10, 5.0, 'weak',   10, 'No 30 mm cannon ammunition in the Aurora range.',
   'Closed without a bid.', 'No matching Aurora product (TEST)', 'USD 0', 'no_match', 'No product matches.', 'USD', 0, 0, 'No bid', 'low'),
  (60509, 60008, '2026-07-02 08:00:00+00', NULL, 'weak',   11, 3.0, 'weak',   11, 'No missile product and domestic-only rule.',
   'Closed without a bid.', 'No matching Aurora product (TEST)', 'USD 0', 'no_match', 'No product matches.', 'USD', 0, 0, 'No bid', 'low'),
  (60510, 60009, '2026-10-16 08:00:00+00', 9102, 'partial', 5, 62.0, 'partial', 5, 'Barrel and autoloader modules fit; integrating a foreign chassis is unproven.',
   'Pre-qualification first, then decide.', 'Aurora Mounted Gun (TEST)', 'USD 40-70 M', 'partial', 'Gun modules match, chassis integration does not.', 'USD', 40000000, 70000000, 'USD 40-70 M', 'medium'),
  (60511, 60010, '2026-10-16 08:00:00+00', 9104, 'strong',  3, 84.0, 'strong',  3, 'Utility variant of the Aurora APC meets the mine-protection level; indigenous content is met.',
   'Domestic buyer, low-risk bid.', 'Aurora APC (TEST)', 'USD 70-100 M', 'matched', 'APC family covers the utility variant.', 'USD', 70000000, 100000000, 'USD 70-100 M', 'high'),
  (60512, 60011, '2026-10-16 08:00:00+00', 9105, 'partial', 7, 55.0, 'partial', 7, 'Carbine meets the spec; EU certification and service partner are missing.',
   'Deadline in 6 days, unlikely to bid.', 'Aurora Carbine (TEST)', 'EUR 3-5 M', 'partial', 'Carbine matches, paperwork does not.', 'EUR', 3000000, 5000000, 'EUR 3-5 M', 'low'),
  (60513, 60003, '2026-10-02 08:00:00+00', 9104, 'partial', 3, 70.0, 'partial', 3, 'Earlier read before the technical questionnaire.',
   'Older read superseded by 60504.', 'Aurora APC (TEST)', 'USD 150-250 M', 'partial', 'Variants not yet confirmed.', 'USD', 150000000, 250000000, 'USD 150-250 M', 'medium');

-- ---------------------------------------------------------------------------------------------------------------- market_tender_product_match
-- Which Aurora products match a tender (Matched products section; a fit percentage per product). 12 rows.
INSERT INTO staging.market_tender_product_match
  (tender_match_id, tender_id, display_order, match_label, fit_grade, fit_percent) VALUES
  (60601, 60001, 1, 'Aurora Shell 155 (TEST)', 'strong', 92),
  (60602, 60001, 2, 'Aurora Shell 155 base-bleed variant (TEST)', 'partial', 71),
  (60603, 60002, 1, 'Aurora Gun 155 (TEST)', 'partial', 68),
  (60604, 60002, 2, 'Aurora Mounted Gun (TEST)', 'weak', 35),
  (60605, 60003, 1, 'Aurora APC (TEST)', 'strong', 88),
  (60606, 60004, 1, 'Aurora Interceptor Drone (TEST)', 'partial', 61),
  (60607, 60005, 1, 'Aurora Carbine (TEST)', 'strong', 94),
  (60608, 60009, 1, 'Aurora Mounted Gun (TEST)', 'partial', 63),
  (60609, 60009, 2, 'Aurora Gun 155 (TEST)', 'weak', 30),
  (60610, 60010, 1, 'Aurora APC (TEST)', 'strong', 85),
  (60611, 60011, 1, 'Aurora Carbine (TEST)', 'partial', 56),
  (60612, 60006, 1, 'Aurora Mounted Gun (TEST)', 'weak', 28);

-- ---------------------------------------------------------------------------------------------------------------- market_tender_product_match_line
-- The line items under each product match (spec vs requirement lines in the Matched products section). 26 rows.
INSERT INTO staging.market_tender_product_match_line
  (match_line_id, tender_match_id, display_order, line_label, line_value) VALUES
  (60701, 60601, 1, 'Calibre and interface', '155 mm, NATO AOP-29 compliant'),
  (60702, 60601, 2, 'Range', '39 km with base bleed vs 30-40 km required'),
  (60703, 60601, 3, 'Shelf life', '12 years vs 10 required'),
  (60704, 60602, 1, 'Range', '42 km, above the band'),
  (60705, 60602, 2, 'Cost per round', 'Higher than the HE baseline'),
  (60706, 60603, 1, 'Range', '38 km vs 35-42 km required'),
  (60707, 60603, 2, 'Weight', '6.9 t, inside the ceiling'),
  (60708, 60603, 3, 'Local support', 'No Saudi service base yet'),
  (60709, 60604, 1, 'Mobility', 'Truck-mounted, not towed as required'),
  (60710, 60605, 1, 'Protection', 'STANAG level 4 met'),
  (60711, 60605, 2, 'Amphibious', 'Swims at 8 km/h'),
  (60712, 60605, 3, 'Weapon station', '30 mm RWS integrated'),
  (60713, 60606, 1, 'Interceptor', 'Meets Group 2 engagement envelope in trials'),
  (60714, 60606, 2, 'Radar and command post', 'Not in Aurora scope'),
  (60715, 60607, 1, 'Weight', '2.9 kg vs 3.2 kg ceiling'),
  (60716, 60607, 2, 'Reliability', '18,000 rounds between stoppages'),
  (60717, 60608, 1, 'Barrel', '52 cal barrel fits the ring'),
  (60718, 60608, 2, 'Integration', 'Foreign chassis unproven'),
  (60719, 60609, 1, 'Fit', 'Towed gun is not an upgrade kit'),
  (60720, 60610, 1, 'Mine protection', 'Level 3a met'),
  (60721, 60610, 2, 'Payload', '1.6 t vs 1.5 t required'),
  (60722, 60610, 3, 'Indigenous content', '62% vs 50% required'),
  (60723, 60611, 1, 'Weight', '2.9 kg vs 3.0 kg ceiling'),
  (60724, 60611, 2, 'Certification', 'EU declaration not yet issued'),
  (60725, 60612, 1, 'Local content', '22% vs 60% required'),
  (60726, 60612, 2, 'Range', '38 km, adequate');

-- ---------------------------------------------------------------------------------------------------------------- market_tender_competitor_fit
-- Rival bidders likely to compete (Competitor fit section; ranked). Rival products come from 10_competitive.sql. 20 rows.
INSERT INTO staging.market_tender_competitor_fit
  (competitor_fit_id, tender_id, competitor_name, fit_label, competitor_product_display, competitor_products_text, fit_rationale, rank_position, source_id, competitor_product_id) VALUES
  (60801, 60001, 'Halcyon Land Systems (TEST)', 'strong',  'Halcyon K-Shell 155 (TEST)', 'Halcyon K-Shell 155 (TEST)', 'Fast delivery and a Polish line make Halcyon the lead rival.', 1, 60302, 'b0000000-0000-4000-8000-000000000032'),
  (60802, 60001, 'Meridian Ordnance (TEST)',    'partial', 'Meridian LR-155 Long-Range Shell (TEST)', 'Meridian LR-155 Long-Range Shell (TEST)', 'Competitive on price, slower delivery.', 2, 60302, 'b0000000-0000-4000-8000-000000000041'),
  (60803, 60001, 'Borealis Arms (TEST)',        'partial', 'Borealis Smart Shell 155 (TEST)', 'Borealis Smart Shell 155 (TEST)', 'Premium price point, strong NATO references.', 3, 60301, 'b0000000-0000-4000-8000-000000000013'),
  (60804, 60002, 'Borealis Arms (TEST)',        'strong',  'Borealis BH-155 Towed Howitzer (TEST)', 'Borealis BH-155 Towed Howitzer (TEST)', 'Fielded in the region with local support.', 1, 60304, 'b0000000-0000-4000-8000-000000000011'),
  (60805, 60002, 'Halcyon Land Systems (TEST)', 'strong',  'Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Self-propelled alternative with a Gulf reference.', 2, 60303, 'b0000000-0000-4000-8000-000000000031'),
  (60806, 60003, 'Cobalt Dynamics (TEST)',      'strong',  'Cobalt Guardian APC (TEST)', 'Cobalt Guardian APC (TEST)', 'Incumbent 8x8 supplier in Latin America.', 1, 60317, 'b0000000-0000-4000-8000-000000000021'),
  (60807, 60003, 'Meridian Ordnance (TEST)',    'partial', 'Meridian W8 Wheeled APC (TEST)', 'Meridian W8 Wheeled APC (TEST)', 'Wheeled vehicle with francophone ties but no amphibious variant.', 2, 60305, 'b0000000-0000-4000-8000-000000000042'),
  (60808, 60004, 'Tessera Aerospace (TEST)',    'strong',  'Tessera Drone Killer (TEST)', 'Tessera Drone Killer (TEST)', 'Radar-cued interceptor already in service in India.', 1, 60307, 'b0000000-0000-4000-8000-000000000051'),
  (60809, 60004, 'Cobalt Dynamics (TEST)',      'partial', 'Cobalt Swarm Interceptor (TEST)', 'Cobalt Swarm Interceptor (TEST)', 'Swarm-based counter-UAS; a different concept from battery interceptors.', 2, 60306, 'b0000000-0000-4000-8000-000000000023'),
  (60810, 60005, 'Tessera Aerospace (TEST)',    'partial', 'Tessera TC-9 Carbine (TEST)', 'Tessera TC-9 Carbine (TEST)', 'Domestic incumbent; lost on price.', 1, 60308, 'b0000000-0000-4000-8000-000000000053'),
  (60811, 60006, 'Halcyon Land Systems (TEST)', 'strong',  'Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Winner with a local assembly line.', 1, 60309, 'b0000000-0000-4000-8000-000000000031'),
  (60812, 60006, 'Borealis Arms (TEST)',        'partial', 'Borealis BMG-52 Mounted Gun (TEST)', 'Borealis BMG-52 Mounted Gun (TEST)', 'Runner-up, lower local content.', 2, 60309, 'b0000000-0000-4000-8000-000000000012'),
  (60813, 60007, 'Meridian Ordnance (TEST)',    'strong',  'Meridian LR-155 Long-Range Shell (TEST)', 'Meridian LR-155 Long-Range Shell (TEST)', 'Supplies ammunition to the buyer already.', 1, 60310, 'b0000000-0000-4000-8000-000000000041'),
  (60814, 60008, 'Tessera Aerospace (TEST)',    'strong',  'Tessera Vayu Missile (TEST)', 'Tessera Vayu Missile (TEST)', 'Domestic short-range missile.', 1, 60311, 'b0000000-0000-4000-8000-000000000052'),
  (60815, 60009, 'Borealis Arms (TEST)',        'strong',  'Borealis BMG-52 Mounted Gun (TEST)', 'Borealis BMG-52 Mounted Gun (TEST)', 'Offers its own mounted-gun upgrade with UK references.', 1, 60313, 'b0000000-0000-4000-8000-000000000012'),
  (60816, 60009, 'Halcyon Land Systems (TEST)', 'partial', 'Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Halcyon SPH-155 Self-Propelled Gun (TEST)', 'Upgrade path exists but no UK presence.', 2, 60312, 'b0000000-0000-4000-8000-000000000031'),
  (60817, 60010, 'Cobalt Dynamics (TEST)',      'partial', 'Cobalt Guardian APC (TEST)', 'Cobalt Guardian APC (TEST)', 'Strong vehicle but not built in India.', 1, 60315, 'b0000000-0000-4000-8000-000000000021'),
  (60818, 60010, 'Meridian Ordnance (TEST)',    'weak',    'Meridian W8 Wheeled APC (TEST)', 'Meridian W8 Wheeled APC (TEST)', 'No Indian assembly and no mine-protected variant.', 2, 60314, 'b0000000-0000-4000-8000-000000000042'),
  (60819, 60011, 'Halcyon Land Systems (TEST)', 'partial', 'Halcyon HR-7 Rifle (TEST)', 'Halcyon HR-7 Rifle (TEST)', 'Has EU certification; bid likely.', 1, 60316, 'b0000000-0000-4000-8000-000000000033'),
  (60820, 60011, 'Tessera Aerospace (TEST)',    'weak',    'Tessera TC-9 Carbine (TEST)', 'Tessera TC-9 Carbine (TEST)', 'No EU certification; unlikely to bid.', 2, 60316, 'b0000000-0000-4000-8000-000000000053');

-- ---------------------------------------------------------------------------------------------------------------- market_opportunity
-- Pre-tender projects ("Projects to win before they tender", Top opportunity page). 6 rows.
INSERT INTO staging.market_opportunity
  (opportunity_id, opportunity_kind, title, description, scope_text, buyer_name, contractor_name, location_text, country_code,
   category_id, stage, current_status, latest_milestone, as_of_date, created_at, updated_at) VALUES
  (61001, 'programme', 'Poland 155 mm ammunition stockpile replenishment (TEST)', 'Multi-year programme to rebuild 155 mm stocks after donations; the 60001 framework is its first tender.',
   'About 1.2 million rounds over six years.', 'Ministry of National Defence of Poland (TEST)', NULL, 'Poland, national', 'PL',
   2, 'budget approved', 'Budget line approved by parliament', 'Second tender expected in Q2 2027', '2026-10-10', '2026-08-01 08:00:00+00', '2026-10-10 08:00:00+00'),
  (61002, 'programme', 'Saudi towed artillery localisation programme (TEST)', 'Localisation programme tied to the 36-gun tender; a JV with a Saudi company is the preferred route.',
   'Local production of 100+ guns over ten years.', 'Ministry of Defence of Saudi Arabia (TEST)', 'Halcyon Land Systems (TEST)', 'Riyadh, Saudi Arabia', 'SA',
   1, 'requirements drafting', 'Armed forces are drafting the staff requirement', 'Industry briefing held 2026-09-30', '2026-10-08', '2026-07-12 08:00:00+00', '2026-10-08 08:00:00+00'),
  (61003, 'framework', 'Brazil armoured vehicle family (TEST)', 'Follow-on framework for 8x8 variants (mortar carrier, ambulance) after the first APC tender.',
   'About 250 vehicles.', 'Ministry of Defence of Brazil (TEST)', 'Cobalt Dynamics (TEST)', 'Brasilia, Brazil', 'BR',
   3, 'market survey', 'Request for information expected', 'Defence white paper names the programme', '2026-10-05', '2026-06-20 08:00:00+00', '2026-10-05 08:00:00+00'),
  (61004, 'programme', 'Freedonia base air-defence upgrade (TEST)', 'Base air-defence upgrade with counter-UAS at the core; precursor of the 60004 tender.',
   'Twelve airbases.', 'Ministry of Defence of Freedonia (TEST)', NULL, 'Freedonia (TEST)', 'FD',
   5, 'RFI issued', 'Request for information issued to industry', 'Responses due 2026-11-30', '2026-10-12', '2026-09-01 08:00:00+00', '2026-10-12 08:00:00+00'),
  (61005, 'modernisation', 'India small-arms replacement phase 2 (TEST)', 'Replacement of legacy rifles in reserve units with domestic carbines.',
   'About 150,000 carbines.', 'Ministry of Defence of India (TEST)', 'Tessera Aerospace (TEST)', 'New Delhi, India', 'IN',
   4, 'trials', 'User trials under way', 'Trial phase 1 completed 2026-09-18', '2026-09-25', '2026-05-15 08:00:00+00', '2026-09-25 08:00:00+00'),
  (61006, 'programme', 'UAE artillery fleet renewal (TEST)', 'Replacement of 155 mm towed guns with mounted guns over eight years.',
   'About 60 guns.', 'UAE Armed Forces (TEST)', NULL, 'Abu Dhabi, United Arab Emirates', 'AE',
   1, 'requirements drafting', 'Staff requirement being circulated', 'Draft requirement circulated 2026-10-02', '2026-10-09', '2026-08-20 08:00:00+00', '2026-10-09 08:00:00+00');

-- ---------------------------------------------------------------------------------------------------------------- market_opportunity_fit_assessment
-- Aurora fit and revenue read for a pre-tender project (Top opportunity project rows and drawer). 6 rows.
INSERT INTO staging.market_opportunity_fit_assessment
  (assessment_id, opportunity_id, assessed_at, client_product_id, fit_grade, fit_score, rationale, revenue_currency, revenue_display,
   revenue_estimate_amount, rival_name, client_model_display, rival_product_display) VALUES
  (61101, 61001, '2026-10-10 08:00:00+00', 9103, 'strong',  86, 'Aurora Shell 155 is already on the Polish qualified-products list.', 'USD', 'USD 150-250 M', 200000000, 'Halcyon Land Systems (TEST)', 'Aurora Shell 155 (TEST)', 'Halcyon K-Shell 155 (TEST)'),
  (61102, 61002, '2026-10-08 08:00:00+00', 9101, 'partial', 64, 'Gun fits; a Saudi JV partner is required.', 'USD', 'USD 300-450 M', 375000000, 'Borealis Arms (TEST)', 'Aurora Gun 155 (TEST)', 'Borealis BH-155 Towed Howitzer (TEST)'),
  (61103, 61003, '2026-10-05 08:00:00+00', 9104, 'strong',  80, 'APC family covers the variants.', 'USD', 'USD 400-550 M', 475000000, 'Cobalt Dynamics (TEST)', 'Aurora APC (TEST)', 'Cobalt Guardian APC (TEST)'),
  (61104, 61004, '2026-10-12 08:00:00+00', 9106, 'partial', 57, 'Interceptor drone fits; needs radar partner.', 'USD', 'USD 80-120 M', 100000000, 'Tessera Aerospace (TEST)', 'Aurora Interceptor Drone (TEST)', 'Tessera Drone Killer (TEST)'),
  (61105, 61005, '2026-09-25 08:00:00+00', 9105, 'strong',  78, 'Carbine in the user-trial pool.', 'USD', 'USD 90-140 M', 115000000, 'Tessera Aerospace (TEST)', 'Aurora Carbine (TEST)', 'Tessera TC-9 Carbine (TEST)'),
  (61106, 61006, '2026-10-09 08:00:00+00', 9102, 'weak',    38, 'Mounted gun lacks the Gulf reference.', 'USD', 'USD 40-80 M', 60000000, 'Borealis Arms (TEST)', 'Aurora Mounted Gun (TEST)', 'Borealis BMG-52 Mounted Gun (TEST)');

-- ---------------------------------------------------------------------------------------------------------------- market_opportunity_source
-- Where a pre-tender project was found (Sources list of the project drawer). 9 rows.
INSERT INTO staging.market_opportunity_source
  (source_id, opportunity_id, source_title, publisher, source_type, source_url, source_date, confidence) VALUES
  (61201, 61001, 'Parliament approves ammunition stockpile line', 'Defence Weekly (TEST)', 'news', 'https://news.example.org/pl-stockpile-budget', '2026-10-02', 'high'),
  (61202, 61001, 'Ministry procurement plan 2027', 'Ministry of National Defence of Poland (TEST)', 'official notice', 'https://mod.example.com/pl/plan-2027', '2026-09-25', 'high'),
  (61203, 61002, 'Industry briefing on localisation', 'Gulf Defence Wire (TEST)', 'news', 'https://news.example.org/sa-localisation-briefing', '2026-09-30', 'medium'),
  (61204, 61003, 'Defence white paper names 8x8 family', 'Ministry of Defence of Brazil (TEST)', 'official document', 'https://mod.example.com/br/white-paper', '2026-09-12', 'high'),
  (61205, 61004, 'RFI for base air-defence upgrade', 'Defence Equipment Office of Freedonia (TEST)', 'official notice', 'https://portal.example.com/fd/rfi-air-defence', '2026-10-12', 'high'),
  (61206, 61004, 'Freedonia seeks counter-drone shield', 'Counter-UAS Journal (TEST)', 'news', 'https://news.example.net/fd-drone-shield', '2026-10-06', 'medium'),
  (61207, 61005, 'User trials for new carbines begin', 'Indian Defence Digest (TEST)', 'news', 'https://news.example.org/in-carbine-trials', '2026-09-18', 'medium'),
  (61208, 61006, 'UAE reviews artillery fleet', 'Gulf Defence Wire (TEST)', 'news', 'https://news.example.org/ae-artillery-review', '2026-10-02', 'low'),
  (61209, 61003, 'Brazil army plans 8x8 follow-on', 'Latin Defence Monitor (TEST)', 'news', 'https://news.example.net/br-8x8-follow-on', '2026-09-20', 'medium');

-- ---------------------------------------------------------------------------------------------------------------- market_opportunity_update
-- Dated developments of a pre-tender project (Updates timeline in the project drawer, newest first). 11 rows.
INSERT INTO staging.market_opportunity_update
  (update_id, opportunity_id, update_date, update_type, headline, narrative, confidence, source_id) VALUES
  (61301, 61001, '2026-10-02', 'budget',    'Stockpile budget line approved', 'Parliament approved the 2027 line for 155 mm ammunition; the first framework is already out for tender.', 'high', 61201),
  (61302, 61001, '2026-09-25', 'milestone', 'Procurement plan published', 'The 2027 plan lists a second 155 mm framework for Q2 2027.', 'high', 61202),
  (61303, 61002, '2026-09-30', 'milestone', 'Industry briefing held', 'Buyer briefed industry on a localisation programme; JV with a Saudi company preferred.', 'medium', 61203),
  (61304, 61002, '2026-08-28', 'news',      'Staff requirement drafting begins', 'Armed forces started drafting the requirement for towed guns.', 'medium', NULL),
  (61305, 61003, '2026-09-12', 'milestone', 'White paper names 8x8 family', 'The defence white paper lists the 8x8 family as a priority programme.', 'high', 61204),
  (61306, 61003, '2026-09-20', 'news',      'Army plans follow-on', 'Army sources say variants will follow the first 120 vehicles.', 'medium', 61209),
  (61307, 61004, '2026-10-12', 'milestone', 'RFI issued', 'The buyer issued an RFI for base air defence with counter-UAS.', 'high', 61205),
  (61308, 61004, '2026-10-06', 'news',      'Counter-drone shield reported', 'Local press reports the shield covers twelve airbases.', 'medium', 61206),
  (61309, 61005, '2026-09-18', 'milestone', 'Trial phase 1 completed', 'Four domestic carbines completed phase 1 user trials.', 'medium', 61207),
  (61310, 61006, '2026-10-02', 'news',      'UAE reviews its artillery fleet', 'Report says a mounted gun is favoured; no tender date given.', 'low', 61208),
  (61311, 61006, '2026-10-09', 'milestone', 'Draft requirement circulated', 'A staff requirement draft is being circulated to industry.', 'medium', NULL);

-- ---------------------------------------------------------------------------------------------------------------- market_top_opportunity_tender
-- The "Top tenders" list of the Top opportunity page (ranked; revenue is the analyst estimate). 5 rows. Parent card: market_tender.
INSERT INTO staging.market_top_opportunity_tender
  (top_opportunity_tender_id, tender_id, rank_position, decides, kssl_fit, kssl_model, rival_to_beat, revenue_text, status) VALUES
  (61401, 60001, 1, 'Award expected in Q1 2027', 'strong', 'Aurora Shell 155 (TEST)', 'Halcyon Land Systems (TEST)', 'USD 60-95 M', 'open'),
  (61402, 60003, 2, 'Technical evaluation in Q1 2027', 'strong', 'Aurora APC (TEST)', 'Cobalt Dynamics (TEST)', 'USD 220-300 M', 'open'),
  (61403, 60010, 3, 'Pre-bid meeting on 10 Nov 2026', 'strong', 'Aurora APC (TEST)', 'Cobalt Dynamics (TEST)', 'USD 70-100 M', 'open'),
  (61404, 60002, 4, 'Bids due 27 Oct 2026', 'partial', 'Aurora Gun 155 (TEST)', 'Borealis Arms (TEST)', 'USD 150-210 M', 'evaluation'),
  (61405, 60009, 5, 'Pre-qualification before 18 Mar 2027', 'partial', 'Aurora Mounted Gun (TEST)', 'Borealis Arms (TEST)', 'USD 40-70 M', 'open');

-- ---------------------------------------------------------------------------------------------------------------- market_top_opportunity_project
-- The "Projects to win before they tender" list (ranked). 4 rows. Parent card: market_opportunity.
INSERT INTO staging.market_top_opportunity_project
  (top_opportunity_project_id, opportunity_id, rank_position, buyer_name, country_name, where_it_stands, kssl_fit, kssl_model, rival_to_beat, revenue_text) VALUES
  (61501, 61001, 1, 'Ministry of National Defence of Poland (TEST)', 'Poland', 'Budget approved; second tender expected in Q2 2027', 'strong', 'Aurora Shell 155 (TEST)', 'Halcyon Land Systems (TEST)', 'USD 150-250 M'),
  (61502, 61003, 2, 'Ministry of Defence of Brazil (TEST)', 'Brazil', 'Market survey; RFI expected', 'strong', 'Aurora APC (TEST)', 'Cobalt Dynamics (TEST)', 'USD 400-550 M'),
  (61503, 61002, 3, 'Ministry of Defence of Saudi Arabia (TEST)', 'Saudi Arabia', 'Staff requirement being drafted', 'partial', 'Aurora Gun 155 (TEST)', 'Borealis Arms (TEST)', 'USD 300-450 M'),
  (61504, 61004, 4, 'Ministry of Defence of Freedonia (TEST)', 'Freedonia (TEST)', 'RFI issued; responses due 30 Nov 2026', 'partial', 'Aurora Interceptor Drone (TEST)', 'Tessera Aerospace (TEST)', 'USD 80-120 M');

-- ---------------------------------------------------------------------------------------------------------------- market_next_move
-- "Next moves" actions list of the Top opportunity page (by sequence). 7 rows.
INSERT INTO staging.market_next_move
  (next_move_id, sequence, action_text, tender_id, tender_title, opportunity_id, due_date, due_text, days_remaining, priority, status) VALUES
  (61601, 1, 'Submit the bid or no-bid decision for the Saudi howitzer tender', 60002, 'Towed howitzers 155 mm / 52 cal, 36 guns (TEST)', NULL, '2026-10-23', 'in 7 days', 7, 'high', 'open'),
  (61602, 2, 'Confirm a Polish line partner for the 30% offset', 60001, '155 mm HE ammunition, 400,000 rounds (TEST)', NULL, '2026-11-06', 'in 21 days', 21, 'high', 'open'),
  (61603, 3, 'Attend the pre-bid meeting in New Delhi', 60010, 'Mine-protected utility vehicles, 300 units (TEST)', NULL, '2026-11-10', 'in 25 days', 25, 'medium', 'open'),
  (61604, 4, 'Select a Brazilian assembly partner', 60003, '8x8 armoured personnel carriers, 120 vehicles (TEST)', NULL, '2026-12-01', 'in 46 days', 46, 'medium', 'open'),
  (61605, 5, 'Answer the Freedonia RFI with a teaming offer', NULL, NULL, 61004, '2026-11-30', 'in 45 days', 45, 'medium', 'open'),
  (61606, 6, 'Brief the Saudi ministry on localisation options', NULL, NULL, 61002, '2026-12-15', 'in 60 days', 60, 'low', 'open'),
  (61607, 7, 'Review the closed Norway notice and drop it from the pipeline', 60007, '30 mm training ammunition, 2,000,000 rounds (TEST)', NULL, '2026-10-30', 'in 14 days', 14, 'low', 'done');

-- ---------------------------------------------------------------------------------------------------------------- market_top_opportunity_metric
-- The four tiles above the Top opportunity page (and the metric strip). 5 rows.
INSERT INTO staging.market_top_opportunity_metric
  (metric_id, metric_key, metric_label, formatted_value, numeric_value, amount_value, currency_code, note, as_of_date) VALUES
  (61701, 'latest_tenders',          'Latest tenders',          '7',          7,           NULL,       NULL, 'Open and closing tenders on record', '2026-10-16'),
  (61702, 'strong_fits',             'Strong fits',             '3',          3,           NULL,       NULL, 'Open tenders with a stored strong fit', '2026-10-16'),
  (61703, 'tender_value',            'Tender value',            'USD 1.20 bn', 1201000000, 1201000000, 'USD', 'Sum of disclosed value of open and closing tenders', '2026-10-16'),
  (61704, 'perceived_opportunities', 'Perceived opportunities', '6',          6,           NULL,       NULL, 'Pre-tender projects on record', '2026-10-16'),
  (61705, 'next_moves',              'Next moves',              '6',          6,           NULL,       NULL, 'Open actions', '2026-10-16');

-- ---------------------------------------------------------------------------------------------------------------- market_global_requirement
-- Requirements published before any tender (Market > Global requirements list and drawer). 6 rows.
INSERT INTO staging.market_global_requirement
  (requirement_id, title, buyer_name, country_name, region, category, value_text, deadline, days_remaining, status, description,
   kssl_fit, kssl_model, strategic_assessment, empty_state_message) VALUES
  (62001, 'Wheeled self-propelled howitzer requirement (TEST)', 'Ministry of National Defence of Poland (TEST)', 'Poland', 'Europe', 'Artillery', 'USD 600 million', 'Request for proposals Q2 2027', 227, 'Requirement stage',
   'Poland seeks a wheeled 155 mm self-propelled howitzer to complement its tracked guns.', 'partial', 'Aurora Mounted Gun (TEST)',
   'Aurora has a truck-mounted gun but no Polish service base; a teaming route with a local chassis maker is needed.', 'No requirements on record'),
  (62002, 'Insensitive-munition 155 mm shell requirement (TEST)', 'Federal Ministry of Defence of Germany (TEST)', 'Germany', 'Europe', 'Ammunition', 'EUR 300 million', 'Draft expected Q1 2027', 150, 'Draft',
   'Germany plans to move its 155 mm stock to insensitive-munition fills.', 'strong', 'Aurora Shell 155 (TEST)',
   'Aurora Shell 155 IM variant is in qualification; early engagement can secure a place on the supplier list.', 'No requirements on record'),
  (62003, 'Light protected patrol vehicle requirement (TEST)', 'Ministry of Defence of India (TEST)', 'India', 'Asia', 'Armoured Vehicles', 'USD 90 million', 'Statement of case approved', NULL, 'Approved in principle',
   'Border force wants two hundred light protected patrol vehicles.', 'strong', 'Aurora APC (TEST)',
   'Aurora APC derivative already meets the draft threat level; domestic buyer.', 'No requirements on record'),
  (62004, 'Compact assault carbine requirement (TEST)', 'Ministry of Defence of Brazil (TEST)', 'Brazil', 'South America', 'Small Arms', 'USD 55 million', 'Request for information Q4 2026', 60, 'RFI stage',
   'Brazil intends to replace service rifles in two brigades with compact carbines.', 'partial', 'Aurora Carbine (TEST)',
   'Carbine fits; the buyer prefers local licensed production.', 'No requirements on record'),
  (62005, 'Layered counter-UAS requirement (TEST)', 'Ministry of Defence of Freedonia (TEST)', 'Freedonia (TEST)', 'Europe', 'Unmanned & Counter-UAS', 'USD 140 million', 'Market survey 2027', 400, 'Planning',
   'Freedonia plans a layered counter-UAS shield: sensors, jammers and interceptor drones.', 'partial', 'Aurora Interceptor Drone (TEST)',
   'Interceptor drone covers one layer; the buyer will likely split lots.', 'No requirements on record'),
  (62006, 'Short-range air-defence replacement (TEST)', 'Ministry of Defence of Saudi Arabia (TEST)', 'Saudi Arabia', 'Middle East', 'Missiles & Air Defence', NULL, 'Long-term planning', NULL, 'Long-term',
   'Saudi Arabia is considering a replacement for ageing short-range air-defence missiles after 2030.', 'weak', 'No matching Aurora product (TEST)',
   'No Aurora missile product; monitor only.', 'No requirements on record');

-- ---------------------------------------------------------------------------------------------------------------- market_global_requirement_specification
-- Headline specs of a requirement (Scope / specs list in the requirement drawer). 16 rows.
INSERT INTO staging.market_global_requirement_specification
  (requirement_spec_id, requirement_id, display_order, spec_label, spec_value) VALUES
  (62101, 62001, 1, 'Calibre', '155 mm / 52 cal'),
  (62102, 62001, 2, 'Mobility', 'Wheeled 8x8'),
  (62103, 62001, 3, 'Quantity', '48 systems'),
  (62104, 62002, 1, 'Shell type', 'Insensitive munition, IM-compliant fill'),
  (62105, 62002, 2, 'Quantity', '250,000 rounds per year'),
  (62106, 62003, 1, 'Protection', 'STANAG 4569 level 2'),
  (62107, 62003, 2, 'Seats', '6'),
  (62108, 62003, 3, 'Quantity', '200 vehicles'),
  (62109, 62004, 1, 'Calibre', '5.56 mm'),
  (62110, 62004, 2, 'Barrel length', '10 to 12 in'),
  (62111, 62005, 1, 'Layers', 'Sensor, jammer, interceptor'),
  (62112, 62005, 2, 'Engagement radius', '5 km'),
  (62113, 62005, 3, 'Sites', '12 airbases'),
  (62114, 62006, 1, 'Seeker', 'Imaging infrared'),
  (62115, 62006, 2, 'Range', '8 km'),
  (62116, 62004, 3, 'Quantity', '18,000 carbines');

-- ---------------------------------------------------------------------------------------------------------------- market_global_requirement_source
-- Where a requirement was published (Sources list of the requirement drawer). 10 rows.
INSERT INTO staging.market_global_requirement_source
  (requirement_source_id, requirement_id, display_order, source_label, source_type, source_url) VALUES
  (62201, 62001, 1, 'Polish MoD modernisation plan', 'official', 'https://mod.example.com/pl/modernisation-plan'),
  (62202, 62001, 2, 'Defence Weekly article', 'news', 'https://news.example.org/pl-wheeled-howitzer'),
  (62203, 62002, 1, 'German MoD procurement outlook', 'official', 'https://mod.example.com/de/outlook'),
  (62204, 62003, 1, 'Indian MoD statement of case', 'official', 'https://mod.example.com/in/statement-of-case'),
  (62205, 62003, 2, 'Indian Defence Digest', 'news', 'https://news.example.org/in-patrol-vehicle'),
  (62206, 62004, 1, 'Brazil army RFI notice', 'official', 'https://mod.example.com/br/rfi-carbine'),
  (62207, 62005, 1, 'Freedonia defence strategy', 'official', 'https://mod.example.com/fd/strategy'),
  (62208, 62005, 2, 'Counter-UAS Journal', 'news', 'https://news.example.net/fd-layered-counter-uas'),
  (62209, 62006, 1, 'Saudi MoD long-term plan', 'official', 'https://mod.example.com/sa/long-term-plan'),
  (62210, 62002, 2, 'Munitions Quarterly', 'news', 'https://news.example.org/de-im-shell');

-- ---------------------------------------------------------------------------------------------------------------- market_category_summary
-- Stored counts behind the "By category" pie and table of Market Intelligence (per category and country). 12 rows.
INSERT INTO staging.market_category_summary
  (summary_id, category_id, country_code, as_of_date, active_tenders_count, perceived_opportunity_count, source_portals_count, strong_fit_count, value_disclosed_count) VALUES
  (61801, 1, 'SA', '2026-10-16', 1, 1, 1, 0, 1),
  (61802, 1, 'GB', '2026-10-16', 1, 0, 1, 0, 1),
  (61803, 1, 'AE', '2026-10-16', 0, 1, 1, 0, 0),
  (61804, 2, 'PL', '2026-10-16', 1, 1, 1, 1, 1),
  (61805, 2, 'NO', '2026-10-16', 0, 0, 1, 0, 1),
  (61806, 3, 'BR', '2026-10-16', 1, 1, 1, 1, 1),
  (61807, 3, 'IN', '2026-10-16', 1, 0, 1, 1, 1),
  (61808, 4, 'DE', '2026-10-16', 1, 0, 1, 0, 1),
  (61809, 4, 'IN', '2026-10-16', 0, 1, 1, 0, 0),
  (61810, 5, 'FD', '2026-10-16', 1, 1, 1, 0, 1),
  (61811, 6, 'TR', '2026-10-16', 0, 0, 1, 0, 1),
  (61812, 6, 'SA', '2026-10-16', 0, 0, 1, 0, 0);

-- ---------------------------------------------------------------------------------------------------------------- market_filter_option
-- Options of the Country and Category filters of Market pages (labels and counts). 18 rows.
INSERT INTO staging.market_filter_option
  (option_id, filter_type, option_code, option_label, record_count, sort_order, is_active) VALUES
  (61901, 'country',  'PL', 'Poland',               1, 1,  true),
  (61902, 'country',  'SA', 'Saudi Arabia',         1, 2,  true),
  (61903, 'country',  'BR', 'Brazil',               1, 3,  true),
  (61904, 'country',  'FD', 'Freedonia (TEST)',     1, 4,  true),
  (61905, 'country',  'AE', 'United Arab Emirates', 1, 5,  true),
  (61906, 'country',  'AU', 'Australia',            1, 6,  true),
  (61907, 'country',  'NO', 'Norway',               1, 7,  true),
  (61908, 'country',  'TR', 'Turkey',               1, 8,  true),
  (61909, 'country',  'GB', 'United Kingdom',       1, 9,  true),
  (61910, 'country',  'IN', 'India',                1, 10, true),
  (61911, 'country',  'DE', 'Germany',              1, 11, true),
  (61912, 'category', '1',  'Artillery',            3, 1,  true),
  (61913, 'category', '2',  'Ammunition',           2, 2,  true),
  (61914, 'category', '3',  'Armoured Vehicles',    2, 3,  true),
  (61915, 'category', '4',  'Small Arms',           2, 4,  true),
  (61916, 'category', '5',  'Unmanned & Counter-UAS', 1, 5, true),
  (61917, 'category', '6',  'Missiles & Air Defence', 1, 6, true),
  (61918, 'country',  'XX', 'Retired country (TEST)', 0, 12, false);

-- ---------------------------------------------------------------------------------------------------------------- staging.fact_source (Trace panel)
-- One source row per tender (the notice url) ...
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
SELECT 'market_tender', tender_id::text, 'source_url', source_url,
       CASE WHEN url_kind = 'portal' THEN 'unlisted' ELSE 'primary' END, issuer_display,
       'Tender notice for: ' || title, '2026-10-16 08:00:00+00'
FROM staging.market_tender;
-- ... one per tender source row ...
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
SELECT 'market_tender_source', source_id::text, 'source_url', source_url,
       CASE WHEN source_type = 'news' THEN 'independent' ELSE 'primary' END, publisher,
       'Listing of tender ' || tender_id::text, '2026-10-16 08:00:00+00'
FROM staging.market_tender_source;
-- ... and the judgement reasons behind the bid read of the main tenders, the scored fits and the ranked top opportunities.
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at) VALUES
  ('market_tender', '60001', 'lean_code',  'judgement', 'judgement', NULL, 'Go: the NATO interface, range band and lot-testing terms all match Aurora Shell 155, and a Polish line partner can meet the offset.', '2026-10-16 08:00:00+00'),
  ('market_tender', '60001', 'kssl_fit',   'judgement', 'judgement', NULL, 'Strong: every mandatory line in section 3.1 is met by the stored Aurora Shell 155 specifications.', '2026-10-16 08:00:00+00'),
  ('market_tender', '60002', 'lean_code',  'judgement', 'judgement', NULL, 'Maybe: gun meets range and weight, but the Saudi local-presence and JV clause is not met today.', '2026-10-16 08:00:00+00'),
  ('market_tender', '60002', 'kssl_fit',   'judgement', 'judgement', NULL, 'Partial: technical match on the gun; support and local content missing.', '2026-10-16 08:00:00+00'),
  ('market_tender', '60003', 'kssl_fit',   'judgement', 'judgement', NULL, 'Strong: protection level 4, amphibious capability and 8x8 layout are in the Aurora APC specification.', '2026-10-16 08:00:00+00'),
  ('market_tender', '60004', 'lean_code',  'judgement', 'judgement', NULL, 'Maybe: the interceptor is still in trials and radar must come from a partner.', '2026-10-16 08:00:00+00'),
  ('market_tender', '60005', 'lean_code',  'judgement', 'judgement', NULL, 'Won: the award notice names Aurora Defence (TEST) as the supplier.', '2026-10-16 08:00:00+00'),
  ('market_tender', '60006', 'lean_code',  'judgement', 'judgement', NULL, 'Pass: awarded to another bidder; Aurora Mounted Gun did not meet the local-content rule.', '2026-10-16 08:00:00+00'),
  ('market_tender', '60010', 'kssl_fit',   'judgement', 'judgement', NULL, 'Strong: utility variant of the Aurora APC meets mine level 3a and the 50% indigenous-content rule.', '2026-10-16 08:00:00+00'),
  ('market_tender_fit_assessment', '60501', 'fit_score', 'judgement', 'judgement', NULL, 'Score 91: all mandatory lines matched, fuze flexibility confirmed at the pre-bid conference.', '2026-10-16 08:00:00+00'),
  ('market_tender_fit_assessment', '60503', 'fit_score', 'judgement', 'judgement', NULL, 'Score 66: technical match of the gun, deducted for missing local support.', '2026-10-16 08:00:00+00'),
  ('market_opportunity', '61001', 'fit_grade', 'judgement', 'judgement', NULL, 'Strong: Aurora Shell 155 is already on the Polish qualified-products list.', '2026-10-16 08:00:00+00'),
  ('market_opportunity', '61001', 'source_url', 'https://news.example.org/pl-stockpile-budget', 'independent', 'Defence Weekly (TEST)', 'Parliament approved the 2027 line for 155 mm ammunition.', '2026-10-16 08:00:00+00'),
  ('market_opportunity', '61004', 'source_url', 'https://portal.example.com/fd/rfi-air-defence', 'primary', 'Defence Equipment Office of Freedonia (TEST)', 'RFI for base air-defence upgrade.', '2026-10-16 08:00:00+00'),
  ('market_top_opportunity_tender', '61401', 'rank_position', 'judgement', 'judgement', NULL, 'Rank 1: largest estimated Aurora revenue among strong fits and the earliest decision date.', '2026-10-16 08:00:00+00'),
  ('market_top_opportunity_project', '61501', 'rank_position', 'judgement', 'judgement', NULL, 'Rank 1: approved budget and an existing qualified product make this the nearest pre-tender win.', '2026-10-16 08:00:00+00'),
  ('market_next_move', '61601', 'action_text', 'judgement', 'judgement', NULL, 'Decision needed before the 27 Oct deadline; later than that the bid cannot be prepared.', '2026-10-16 08:00:00+00'),
  ('market_global_requirement', '62001', 'kssl_fit', 'judgement', 'judgement', NULL, 'Partial: Aurora Mounted Gun is truck-mounted, not wheeled 8x8 as the requirement states.', '2026-10-16 08:00:00+00'),
  ('market_global_requirement', '62001', 'source_url', 'https://mod.example.com/pl/modernisation-plan', 'primary', 'Ministry of National Defence of Poland (TEST)', 'Modernisation plan lists a wheeled self-propelled howitzer.', '2026-10-16 08:00:00+00'),
  ('market_global_requirement', '62002', 'kssl_fit', 'judgement', 'judgement', NULL, 'Strong: the IM variant of Aurora Shell 155 is in qualification.', '2026-10-16 08:00:00+00'),
  ('market_global_requirement', '62003', 'source_url', 'https://mod.example.com/in/statement-of-case', 'primary', 'Ministry of Defence of India (TEST)', 'Statement of case approved for patrol vehicles.', '2026-10-16 08:00:00+00');

COMMIT;
