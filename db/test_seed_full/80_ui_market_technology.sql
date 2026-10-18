-- 80_ui_market_technology.sql  (part B)  Every staging_ui.market_* and staging_ui.technology_* table except the two
-- technology_category mirrors (staging_ui.technology_category, staging_ui.technology_category_ui_label are written by 00_base.sql).
-- These are the page-chrome and view-state tables: labels, tabs, counts, selected rows, display strings. FICTIONAL test data.
-- Reads ids from 60_market.sql (tenders 60001-60011, opportunities 61001-61006, requirements 62001-62006) and
-- 70_technology.sql (innovations 71001-71016, articles 72001-72010, sources 701xx, categories 1-6).
-- Id ranges: market ui 90xxx, technology ui 91xxx. "Today" is 2026-10-16.
BEGIN;

DELETE FROM staging_ui.market_filter;
DELETE FROM staging_ui.market_global_requirement_card;
DELETE FROM staging_ui.market_global_requirement_detail;
DELETE FROM staging_ui.market_global_requirement_filter;
DELETE FROM staging_ui.market_global_requirement_view;
DELETE FROM staging_ui.market_global_requirement_view_state;
DELETE FROM staging_ui.market_intelligence_tab;
DELETE FROM staging_ui.market_metric;
DELETE FROM staging_ui.market_next_move_view;
DELETE FROM staging_ui.market_pillar;
DELETE FROM staging_ui.market_tender_assessment_view;
DELETE FROM staging_ui.market_tender_card;
DELETE FROM staging_ui.market_tender_filter;
DELETE FROM staging_ui.market_tenders_view;
DELETE FROM staging_ui.market_top_opportunity_project_row;
DELETE FROM staging_ui.market_top_opportunity_tender_row;
DELETE FROM staging_ui.market_top_opportunity_view;
DELETE FROM staging_ui.market_ui_navigation;
DELETE FROM staging_ui.market_view;
DELETE FROM staging_ui.technology_innovation_card;
DELETE FROM staging_ui.technology_innovation_category_tab;
DELETE FROM staging_ui.technology_innovation_detail_panel;
DELETE FROM staging_ui.technology_innovation_view;
DELETE FROM staging_ui.technology_metric;
DELETE FROM staging_ui.technology_overview_detail_section;
DELETE FROM staging_ui.technology_overview_detail_panel;
DELETE FROM staging_ui.technology_overview_filter;
DELETE FROM staging_ui.technology_overview_metric_card;
DELETE FROM staging_ui.technology_overview_signal_card;
DELETE FROM staging_ui.technology_overview_view;
DELETE FROM staging_ui.technology_pillar;
DELETE FROM staging_ui.technology_print_report_control;
DELETE FROM staging_ui.technology_ui_navigation;
DELETE FROM staging_ui.technology_ui_view;

-- ================================================================================================================ MARKET

-- market_pillar: the pillar header of the Market section (title, client name, global search box, print button). 1 row.
INSERT INTO staging_ui.market_pillar
  (market_pillar_id, client_name, display_name, global_search_placeholder, print_report_label) VALUES
  ('market', 'Aurora Defence (TEST)', 'Market', 'Search tenders, buyers, countries...', 'Print report');

-- market_ui_navigation: the Market entries of the left navigation rail (one row per view). 5 rows.
INSERT INTO staging_ui.market_ui_navigation
  (navigation_id, pillar_code, view_code, view_label, account_label, global_search_placeholder, print_report_enabled, captured_at) VALUES
  (90001, 'market', 'top-opportunity',     'Top opportunity',     'Aurora Defence (TEST)', 'Search tenders, buyers, countries...', true,  '2026-10-16 08:00:00+00'),
  (90002, 'market', 'market-intelligence', 'Market Intelligence', 'Aurora Defence (TEST)', 'Search tenders, buyers, countries...', true,  '2026-10-16 08:00:00+00'),
  (90003, 'market', 'tenders',             'Tenders',             'Aurora Defence (TEST)', 'Search tenders, buyers, countries...', true,  '2026-10-16 08:00:00+00'),
  (90004, 'market', 'tender-assessment',   'Tender assessment',   'Aurora Defence (TEST)', 'Search tenders, buyers, countries...', false, '2026-10-16 08:00:00+00'),
  (90005, 'market', 'global-requirement',  'Global requirements', 'Aurora Defence (TEST)', 'Search requirements, buyers, countries...', true, '2026-10-16 08:00:00+00');

-- market_view: the Market views as shown on the rail (title, badge count, empty text). 5 rows.
INSERT INTO staging_ui.market_view
  (view_id, view_title, rail_label, rail_order, rail_count, is_selected, empty_state_text) VALUES
  ('top-opportunity',     'Top opportunity',     'Top opportunity',     1, 9,  true,  'No top opportunities or tender pipelines are on record.'),
  ('tenders',             'Tenders',             'Tenders',             2, 11, false, 'No tenders match the filters.'),
  ('global-requirement',  'Global requirements', 'Global requirements', 3, 6,  false, 'No requirements on record'),
  ('market-intelligence', 'Market Intelligence', 'Market Intelligence', 4, 7,  false, 'Nothing on record matches the filters.'),
  ('tender-assessment',   'Tender assessment',   'Tender assessment',   5, 6,  false, 'No tender has been assessed yet.');

-- market_intelligence_tab: the five tabs of Market Intelligence with record counts. 5 rows.
INSERT INTO staging_ui.market_intelligence_tab
  (tab_id, tab_label, tab_order, record_count, is_selected, category_filter, country_filter) VALUES
  ('outlook',     'Market outlook',           1, 6, false, NULL, NULL),
  ('active',      'Number of active tenders', 2, 7, true,  NULL, NULL),
  ('by-category', 'By category',              3, 6, false, NULL, NULL),
  ('awarded',     'Awarded',                  4, 2, false, NULL, NULL),
  ('closed',      'Closed',                   5, 2, false, NULL, NULL);

-- market_metric: the four tiles above Market Intelligence (value as display text). 5 rows.
INSERT INTO staging_ui.market_metric
  (metric_id, metric_label, metric_value, metric_unit, metric_subtext, metric_action) VALUES
  ('active-tenders',  'Active tenders',  '7',          NULL,  'open and closing',               'tab-active'),
  ('markets',         'Markets',         '11',         NULL,  'countries with a tender on record', 'filter-country'),
  ('source-portals',  'Source portals',  '11',         NULL,  'procurement portals read',       NULL),
  ('value-disclosed', 'Value disclosed', 'USD 1.20 bn', NULL, 'sum of stated values, open tenders', NULL),
  ('strong-fits',     'Strong fits',     '3',          NULL,  'open tenders with a strong Aurora fit', 'filter-fit-strong');

-- market_filter: Country and Category filter boxes of Market Intelligence (label, selected value, search text). 4 rows.
INSERT INTO staging_ui.market_filter
  (filter_id, filter_label, filter_value, option_count, option_label, search_query, sort_key) VALUES
  ('country',  'Country',  NULL,       11, 'All countries (11)',  NULL,     'record_count'),
  ('category', 'Category', NULL,       6,  'All categories (6)',  NULL,     'sort_order'),
  ('country-poland', 'Country', 'Poland', 11, 'Poland',           'pol',    'record_count'),
  ('category-artillery', 'Category', 'Artillery', 6, 'Artillery', 'art',    'sort_order');

-- market_tenders_view: the Tenders page header (heading, counts, filter labels, selected tender). 1 row.
INSERT INTO staging_ui.market_tenders_view
  (view_id, view_code, page_heading, active_tenders_count, markets_count, source_portals_count, value_disclosed_display,
   country_filter_label, country_filter_value, category_filter_label, category_filter_value, sort_label, selected_tender_id) VALUES
  (90101, 'tenders', 'Tenders', 7, 11, 11, 'USD 1.20 bn', 'Country', 'All countries (11)', 'Category', 'All categories (6)', 'sorted by deadline', 60001);

-- market_tender_filter: filter controls of the Tenders page (open state, options count, placeholder). 3 rows.
INSERT INTO staging_ui.market_tender_filter
  (filter_id, view_id, filter_type, filter_label, is_open, option_count, search_placeholder, selected_value) VALUES
  (90111, 90101, 'product_type', 'Product Type', false, 6,  NULL,                 'All'),
  (90112, 90101, 'country',      'Country',      true,  11, 'Search country...',  'All countries (11)'),
  (90113, 90101, 'category',     'Category',     false, 6,  'Search category...', 'All categories (6)');

-- market_tender_card: one card per tender on the Tenders page (display strings, selected card). 11 rows.
INSERT INTO staging_ui.market_tender_card
  (card_id, view_id, card_order, tender_id, title_display, buyer_display, country_display, category_display, status_display,
   countdown_display, deadline_display, value_display, fit_grade_display, is_selected) VALUES
  (90121, 90101, 1,  60011, 'Service carbines 5.56 mm, 5,000 units (TEST)',          'Federal Ministry of Defence of Germany (TEST)',   'Germany',              'Small Arms',              'Closing', '6 days left',   'Closes 22 Oct 2026', 'EUR 9 million',   'Partial', false),
  (90122, 90101, 2,  60002, 'Towed howitzers 155 mm / 52 cal, 36 guns (TEST)',       'Ministry of Defence of Saudi Arabia (TEST)',      'Saudi Arabia',         'Artillery',               'Closing', '11 days left',  'Closes 27 Oct 2026', 'USD 240 million', 'Partial', false),
  (90123, 90101, 3,  60001, '155 mm HE ammunition, 400,000 rounds (TEST)',           'Ministry of National Defence of Poland (TEST)',   'Poland',               'Ammunition',              'Open',    '54 days left',  'Closes 9 Dec 2026',  'USD 185 million', 'Strong',  true),
  (90124, 90101, 4,  60010, 'Mine-protected utility vehicles, 300 units (TEST)',     'Ministry of Defence of India (TEST)',             'India',                'Armoured Vehicles',       'Open',    '75 days left',  'Closes 30 Dec 2026', 'USD 120 million', 'Strong',  false),
  (90125, 90101, 5,  60003, '8x8 armoured personnel carriers, 120 vehicles (TEST)',  'Ministry of Defence of Brazil (TEST)',            'Brazil',               'Armoured Vehicles',       'Open',    '98 days left',  'Closes 22 Jan 2027', 'USD 410 million', 'Strong',  false),
  (90126, 90101, 6,  60004, 'Counter-UAS interceptor drone batteries, 24 units (TEST)', 'Ministry of Defence of Freedonia (TEST)',     'Freedonia (TEST)',     'Unmanned & Counter-UAS',  'Open',    '119 days left', 'Closes 12 Feb 2027', 'USD 96 million',  'Partial', false),
  (90127, 90101, 7,  60009, 'Self-propelled gun upgrade kits, 24 kits (TEST)',       'Ministry of Defence of the United Kingdom (TEST)', 'United Kingdom',      'Artillery',               'Open',    '153 days left', 'Closes 18 Mar 2027', 'USD 150 million', 'Partial', false),
  (90128, 90101, 8,  60005, 'Assault carbines 5.56 mm, 30,000 units (TEST)',         'UAE Armed Forces (TEST)',                         'United Arab Emirates', 'Small Arms',              'Awarded', 'Awarded',       'Awarded 14 Aug 2026', 'USD 45 million',  'Strong',  false),
  (90129, 90101, 9,  60006, 'Wheeled self-propelled guns 155 mm, 18 systems (TEST)', 'Ministry of Defence of Australia (TEST)',          'Australia',            'Artillery',               'Awarded', 'Awarded',       'Awarded 3 Aug 2026', 'USD 280 million', 'Weak',    false),
  (90130, 90101, 10, 60007, '30 mm training ammunition, 2,000,000 rounds (TEST)',    'Ministry of Defence of Norway (TEST)',            'Norway',               'Ammunition',              'Closed',  'Closed',        'Closed 15 Jul 2026', 'USD 22 million',  'Weak',    false),
  (90131, 90101, 11, 60008, 'Short-range air defence missiles, 120 rounds (TEST)',   'Ministry of National Defence of Turkey (TEST)',   'Turkey',               'Missiles & Air Defence',  'Closed',  'Closed',        'Closed 10 Jun 2026', 'USD 130 million', 'Weak',    false);

-- market_tender_assessment_view: the tender assessment drawer chrome per tender (section labels, notice ref, closing summary). 6 rows.
INSERT INTO staging_ui.market_tender_assessment_view
  (assessment_view_id, tender_id, panel_title, panel_subtitle, notice_ref_display, closing_summary, fit_grade_display, fit_rank_display,
   open_notice_label, details_section_label, requirements_section_label, matched_products_section_label, competitor_fit_section_label, source_section_label) VALUES
  (90131, 60001, '155 mm HE ammunition, 400,000 rounds (TEST)', 'Ministry of National Defence of Poland (TEST) - Poland', 'TED-2026-TEST-60001', 'Closes 9 Dec 2026, 54 days left', 'Strong',  'Fit rank 1',  'Open the tender notice', 'Tender details', 'Requirements', 'Matched Aurora products', 'Competitor fit', 'Sources'),
  (90132, 60002, 'Towed howitzers 155 mm / 52 cal, 36 guns (TEST)', 'Ministry of Defence of Saudi Arabia (TEST) - Saudi Arabia', 'NR-SA-60002', 'Closes 27 Oct 2026, 11 days left', 'Partial', 'Fit rank 4', 'Open the portal listing', 'Tender details', 'Requirements', 'Matched Aurora products', 'Competitor fit', 'Sources'),
  (90133, 60003, '8x8 armoured personnel carriers, 120 vehicles (TEST)', 'Ministry of Defence of Brazil (TEST) - Brazil', 'NR-BR-60003', 'Closes 22 Jan 2027, 98 days left', 'Strong', 'Fit rank 2', 'Open the tender notice', 'Tender details', 'Requirements', 'Matched Aurora products', 'Competitor fit', 'Sources'),
  (90134, 60004, 'Counter-UAS interceptor drone batteries, 24 units (TEST)', 'Ministry of Defence of Freedonia (TEST) - Freedonia (TEST)', 'NR-FD-60004', 'Closes 12 Feb 2027, 119 days left', 'Partial', 'Fit rank 6', 'Open the portal listing', 'Tender details', 'Requirements', 'Matched Aurora products', 'Competitor fit', 'Sources'),
  (90135, 60009, 'Self-propelled gun upgrade kits, 24 kits (TEST)', 'Ministry of Defence of the United Kingdom (TEST) - United Kingdom', 'NR-GB-60009', 'Closes 18 Mar 2027, 153 days left', 'Partial', 'Fit rank 5', 'Open the portal listing', 'Tender details', 'Requirements', 'Matched Aurora products', 'Competitor fit', 'Sources'),
  (90136, 60005, 'Assault carbines 5.56 mm, 30,000 units (TEST)', 'UAE Armed Forces (TEST) - United Arab Emirates', 'NR-AE-60005', 'Awarded 14 Aug 2026', 'Strong', 'Fit rank 8', 'Open the award notice', 'Tender details', 'Requirements', 'Matched Aurora products', 'Competitor fit', 'Sources');

-- market_top_opportunity_view: headings and labels of the Top opportunity page. 1 row.
INSERT INTO staging_ui.market_top_opportunity_view
  (view_id, view_code, page_heading, top_tenders_section_label, projects_section_label, next_moves_section_label,
   latest_tenders_metric_label, strong_fits_metric_label, tender_value_metric_label, perceived_opportunities_metric_label,
   top_tenders_description, projects_description, next_moves_description, sort_logic_label, tender_value_metric_note) VALUES
  (90201, 'top-opportunity', 'Top opportunity', 'Top tenders', 'Projects to win before they tender', 'Next moves',
   'Latest tenders', 'Strong fits', 'Tender value', 'Perceived opportunities',
   'Tenders in rank order; revenue is the analyst estimate.', 'Programmes with no tender issued yet; revenue is the analyst estimate.', 'Actions in sequence order, soonest first.',
   'ranked by rank_position', 'Sum of stated tender values, open and closing tenders');

-- market_top_opportunity_tender_row: the rows of the Top tenders table (display strings). 5 rows.
INSERT INTO staging_ui.market_top_opportunity_tender_row
  (row_id, view_id, row_order, rank_position, tender_id, tender_title_display, buyer_location_display, decides_display,
   fit_grade_display, client_model_display, rival_display, revenue_display) VALUES
  (90211, 90201, 1, 1, 60001, '155 mm HE ammunition, 400,000 rounds (TEST)',      'Ministry of National Defence of Poland (TEST), Poland', 'Award expected in Q1 2027',        'Strong',  'Aurora Shell 155 (TEST)',    'Halcyon Land Systems (TEST)', 'USD 60-95 M'),
  (90212, 90201, 2, 2, 60003, '8x8 armoured personnel carriers, 120 vehicles (TEST)', 'Ministry of Defence of Brazil (TEST), Brazil',         'Technical evaluation in Q1 2027',  'Strong',  'Aurora APC (TEST)',          'Cobalt Dynamics (TEST)',      'USD 220-300 M'),
  (90213, 90201, 3, 3, 60010, 'Mine-protected utility vehicles, 300 units (TEST)', 'Ministry of Defence of India (TEST), India',            'Pre-bid meeting on 10 Nov 2026',   'Strong',  'Aurora APC (TEST)',          'Cobalt Dynamics (TEST)',      'USD 70-100 M'),
  (90214, 90201, 4, 4, 60002, 'Towed howitzers 155 mm / 52 cal, 36 guns (TEST)',  'Ministry of Defence of Saudi Arabia (TEST), Saudi Arabia', 'Bids due 27 Oct 2026',         'Partial', 'Aurora Gun 155 (TEST)',      'Borealis Arms (TEST)',        'USD 150-210 M'),
  (90215, 90201, 5, 5, 60009, 'Self-propelled gun upgrade kits, 24 kits (TEST)',  'Ministry of Defence of the United Kingdom (TEST), United Kingdom', 'Pre-qualification before 18 Mar 2027', 'Partial', 'Aurora Mounted Gun (TEST)', 'Borealis Arms (TEST)', 'USD 40-70 M');

-- market_top_opportunity_project_row: the rows of "Projects to win before they tender" (display strings). 4 rows.
INSERT INTO staging_ui.market_top_opportunity_project_row
  (row_id, view_id, row_order, rank_position, opportunity_id, project_title_display, buyer_location_display, where_it_stands_display,
   fit_grade_display, client_model_display, rival_display, revenue_display) VALUES
  (90221, 90201, 1, 1, 61001, 'Poland 155 mm ammunition stockpile replenishment (TEST)', 'Ministry of National Defence of Poland (TEST), Poland', 'Budget approved; second tender expected in Q2 2027', 'Strong',  'Aurora Shell 155 (TEST)',        'Halcyon Land Systems (TEST)', 'USD 150-250 M'),
  (90222, 90201, 2, 2, 61003, 'Brazil armoured vehicle family (TEST)',                    'Ministry of Defence of Brazil (TEST), Brazil',         'Market survey; RFI expected',                       'Strong',  'Aurora APC (TEST)',              'Cobalt Dynamics (TEST)',      'USD 400-550 M'),
  (90223, 90201, 3, 3, 61002, 'Saudi towed artillery localisation programme (TEST)',      'Ministry of Defence of Saudi Arabia (TEST), Saudi Arabia', 'Staff requirement being drafted',            'Partial', 'Aurora Gun 155 (TEST)',          'Borealis Arms (TEST)',        'USD 300-450 M'),
  (90224, 90201, 4, 4, 61004, 'Freedonia base air-defence upgrade (TEST)',                'Ministry of Defence of Freedonia (TEST), Freedonia (TEST)', 'RFI issued; responses due 30 Nov 2026',      'Partial', 'Aurora Interceptor Drone (TEST)', 'Tessera Aerospace (TEST)',    'USD 80-120 M');

-- market_next_move_view: the rows of the Next moves list (display strings). 7 rows. tender_id is NULL for moves on pre-tender projects.
INSERT INTO staging_ui.market_next_move_view
  (move_view_id, view_id, row_id, row_order, action_display, due_display, tender_id, tender_display, sort_label) VALUES
  (90231, 90201, 61601, 1, 'Submit the bid or no-bid decision for the Saudi howitzer tender', 'in 7 days',  60002, 'Towed howitzers 155 mm / 52 cal, 36 guns (TEST)',   'soonest first'),
  (90232, 90201, 61602, 2, 'Confirm a Polish line partner for the 30% offset',               'in 21 days', 60001, '155 mm HE ammunition, 400,000 rounds (TEST)',       'soonest first'),
  (90233, 90201, 61603, 3, 'Attend the pre-bid meeting in New Delhi',                         'in 25 days', 60010, 'Mine-protected utility vehicles, 300 units (TEST)', 'soonest first'),
  (90234, 90201, 61604, 4, 'Select a Brazilian assembly partner',                             'in 46 days', 60003, '8x8 armoured personnel carriers, 120 vehicles (TEST)', 'soonest first'),
  (90235, 90201, 61605, 5, 'Answer the Freedonia RFI with a teaming offer',                   'in 45 days', NULL,  'Freedonia base air-defence upgrade (TEST)',        'soonest first'),
  (90236, 90201, 61606, 6, 'Brief the Saudi ministry on localisation options',                'in 60 days', NULL,  'Saudi towed artillery localisation programme (TEST)', 'soonest first'),
  (90237, 90201, 61607, 7, 'Review the closed Norway notice and drop it from the pipeline',   'in 14 days', 60007, '30 mm training ammunition, 2,000,000 rounds (TEST)', 'soonest first');

-- market_global_requirement_view: headings and section labels of the Global requirements page. 1 row.
INSERT INTO staging_ui.market_global_requirement_view
  (view_id, page_heading, panel_title, panel_subtitle, filter_label, country_filter_label, category_filter_label, sort_label,
   assessment_section_label, fit_section_label, scope_section_label, specs_section_label, source_section_label, empty_state_text) VALUES
  (90301, 'Global requirements', 'Requirement detail', 'Requirements published before any tender is issued', 'Filter', 'Country', 'Category', 'sorted by buyer',
   'Strategic assessment', 'Aurora fit', 'Scope', 'Key specifications', 'Sources', 'No requirements on record');

-- market_global_requirement_filter: the filter boxes of the page (country, category, status). 3 rows.
INSERT INTO staging_ui.market_global_requirement_filter
  (filter_id, filter_type, filter_label, display_order, option_count, search_placeholder, selected_value) VALUES
  (90311, 'country',  'Country',  1, 6, 'Search country...',  'All countries'),
  (90312, 'category', 'Category', 2, 6, 'Search category...', 'All categories'),
  (90313, 'status',   'Status',   3, 6, NULL,                 'All statuses');

-- market_global_requirement_card: one list card per requirement (display strings). 6 rows.
INSERT INTO staging_ui.market_global_requirement_card
  (card_id, requirement_id, title_display, buyer_display, country_display, category_display, status_display, deadline_display, value_display, fit_display, is_selected) VALUES
  (90321, 62001, 'Wheeled self-propelled howitzer requirement (TEST)',   'Ministry of National Defence of Poland (TEST)',   'Poland',          'Artillery',              'Requirement stage',   'RFP Q2 2027',      'USD 600 million', 'Partial', true),
  (90322, 62002, 'Insensitive-munition 155 mm shell requirement (TEST)', 'Federal Ministry of Defence of Germany (TEST)',  'Germany',         'Ammunition',             'Draft',               'Draft Q1 2027',    'EUR 300 million', 'Strong',  false),
  (90323, 62003, 'Light protected patrol vehicle requirement (TEST)',    'Ministry of Defence of India (TEST)',             'India',           'Armoured Vehicles',      'Approved in principle', 'Statement of case approved', 'USD 90 million', 'Strong', false),
  (90324, 62004, 'Compact assault carbine requirement (TEST)',           'Ministry of Defence of Brazil (TEST)',            'Brazil',          'Small Arms',             'RFI stage',           'RFI Q4 2026',      'USD 55 million',  'Partial', false),
  (90325, 62005, 'Layered counter-UAS requirement (TEST)',               'Ministry of Defence of Freedonia (TEST)',         'Freedonia (TEST)', 'Unmanned & Counter-UAS', 'Planning',            'Market survey 2027', 'USD 140 million', 'Partial', false),
  (90326, 62006, 'Short-range air-defence replacement (TEST)',           'Ministry of Defence of Saudi Arabia (TEST)',      'Saudi Arabia',    'Missiles & Air Defence', 'Long-term',           'Long-term planning', NULL,            'Weak',    false);

-- market_global_requirement_detail: drawer chrome per requirement (panel title and section labels). 6 rows.
INSERT INTO staging_ui.market_global_requirement_detail
  (detail_view_id, requirement_id, panel_title, buyer_label, close_label, scope_label, specs_label, fit_label, assessment_label, source_label) VALUES
  (90331, 62001, 'Wheeled self-propelled howitzer requirement (TEST)',   'Buyer', 'Close', 'Scope', 'Key specifications', 'Aurora fit', 'Strategic assessment', 'Sources'),
  (90332, 62002, 'Insensitive-munition 155 mm shell requirement (TEST)', 'Buyer', 'Close', 'Scope', 'Key specifications', 'Aurora fit', 'Strategic assessment', 'Sources'),
  (90333, 62003, 'Light protected patrol vehicle requirement (TEST)',    'Buyer', 'Close', 'Scope', 'Key specifications', 'Aurora fit', 'Strategic assessment', 'Sources'),
  (90334, 62004, 'Compact assault carbine requirement (TEST)',           'Buyer', 'Close', 'Scope', 'Key specifications', 'Aurora fit', 'Strategic assessment', 'Sources'),
  (90335, 62005, 'Layered counter-UAS requirement (TEST)',               'Buyer', 'Close', 'Scope', 'Key specifications', 'Aurora fit', 'Strategic assessment', 'Sources'),
  (90336, 62006, 'Short-range air-defence replacement (TEST)',           'Buyer', 'Close', 'Scope', 'Key specifications', 'Aurora fit', 'Strategic assessment', 'Sources');

-- market_global_requirement_view_state: what the user last selected on the page (panel open, filters, search text). 3 rows.
INSERT INTO staging_ui.market_global_requirement_view_state
  (view_state_id, selected_requirement_id, panel_open, country_filter, category_filter, menu_search_text) VALUES
  (90341, 62001, true,  NULL,     NULL,        NULL),
  (90342, 62002, true,  'Germany', 'Ammunition', 'germ'),
  (90343, NULL,  false, NULL,     NULL,        NULL);

-- ================================================================================================================ TECHNOLOGY

-- technology_pillar: the Technology pillar header (page titles, client name, print button). 1 row (pillar_id is text here).
INSERT INTO staging_ui.technology_pillar
  (pillar_id, pillar_name, client_name, innovation_title, knowledge_title, print_report_label) VALUES
  ('1', 'Technology', 'Aurora Defence (TEST)', 'Technology Innovation', 'Technology Overview', 'Print report');

-- technology_ui_view: the Technology views of the rail (route, heading, search box, sequence options, counts). 2 rows.
INSERT INTO staging_ui.technology_ui_view
  (view_id, pillar_id, view_code, view_key, view_name, view_label, view_number, route_hash, page_heading, search_placeholder,
   sequence_label, sequence_default, sequence_options, record_count, rail_count, display_order, is_active) VALUES
  (91001, '1', 'technology-overview',   'overview',   'Technology Overview',   'Overview',   '1', '#/technology/overview',   'Technology Overview',   'Search signals...',
   'Sequence', 'newest', '[{"code": "newest", "label": "Newest first"}, {"code": "oldest", "label": "Oldest first"}, {"code": "threat", "label": "Threat first"}]'::jsonb, 10, 10, 1, true),
  (91002, '1', 'technology-innovation', 'innovation', 'Technology Innovation', 'Innovations', '2', '#/technology/innovation', 'Technology Innovation', 'Search innovations...',
   'Sequence', 'category', '[{"code": "category", "label": "By category"}, {"code": "position", "label": "Aurora position"}]'::jsonb, 16, 16, 2, true);

-- technology_ui_navigation: the Technology entries of the left navigation (labels, search placeholder, print button). 2 rows.
INSERT INTO staging_ui.technology_ui_navigation
  (navigation_id, pillar_code, view_code, page_heading, account_label, global_search_placeholder, ask_parallax_enabled, print_report_enabled, captured_at) VALUES
  (91011, 'technology', 'technology-overview',   'Technology Overview',   'Aurora Defence (TEST)', 'Search signals, companies, technologies...', true, true, '2026-10-16 08:00:00+00'),
  (91012, 'technology', 'technology-innovation', 'Technology Innovation', 'Aurora Defence (TEST)', 'Search innovations, companies...',           true, true, '2026-10-16 08:00:00+00');

-- technology_print_report_control: the Print report button state per Technology view. 2 rows.
INSERT INTO staging_ui.technology_print_report_control
  (report_control_id, pillar_code, view_code, label, is_enabled) VALUES
  (91021, 'technology', 'technology-overview',   'Print report', true),
  (91022, 'technology', 'technology-innovation', 'Print report', true);

-- technology_metric: the tiles of the Technology pages as display counts (pillar_id text, metric_value int). 8 rows.
INSERT INTO staging_ui.technology_metric
  (metric_id, pillar_id, metric_key, metric_label, metric_value, metric_action, display_order) VALUES
  (91031, '1', 'innovations_tracked', 'Innovations tracked',      16, 'open-innovation-tab',                       1),
  (91032, '1', 'aurora_behind',       'Aurora behind',             8,  'filter-position-behind',                    2),
  (91033, '1', 'aurora_parity',       'Aurora at parity',          6,  'filter-position-parity',                    3),
  (91034, '1', 'aurora_ahead',        'Aurora ahead',              2,  'filter-position-ahead',                     4),
  (91035, '1', 'signals_total',       'Overview signals',          10, 'open-overview',                             5),
  (91036, '1', 'competitor_advances', 'Competitor advances',       6,  'filter-classification-competitor_advance',  6),
  (91037, '1', 'adoptable',           'Adoptable technologies',    4,  'filter-classification-adoptable',          7),
  (91038, '1', 'candidates_pending',  'Candidates pending detail', 2,  NULL,                                        8);

-- technology_innovation_view: header and state of the Innovation page (selected category and innovation). 1 row.
INSERT INTO staging_ui.technology_innovation_view
  (view_id, view_state_id, page_heading, list_heading, empty_state_text, total_innovations, selected_category_id, selected_innovation_id) VALUES
  (91101, 1, 'Technology Innovation', 'Innovations in this category', 'No innovations on record for this category.', 16, 1, 71001);

-- technology_innovation_category_tab: the six category tabs of the Innovation page with counts. 6 rows.
INSERT INTO staging_ui.technology_innovation_category_tab
  (tab_id, view_state_id, category_id, tab_number, tab_label, tab_order, innovation_count, is_selected) VALUES
  (91111, 1, 1, '1', 'Artillery',              1, 3, true),
  (91112, 1, 2, '2', 'Ammunition',             2, 3, false),
  (91113, 1, 3, '3', 'Armoured Vehicles',      3, 3, false),
  (91114, 1, 4, '4', 'Small Arms',             4, 2, false),
  (91115, 1, 5, '5', 'Unmanned & Counter-UAS', 5, 3, false),
  (91116, 1, 6, '6', 'Missiles & Air Defence', 6, 2, false);

-- technology_innovation_card: the list cards of the Innovation page (one per active innovation, display strings). 16 rows.
INSERT INTO staging_ui.technology_innovation_card
  (card_id, view_state_id, card_order, innovation_id, title_display, summary_display, company_display, maturity_display,
   client_position_display, horizon_display, is_selected) VALUES
  (91121, 1, 1,  71001, 'Automatic loader for towed howitzers (TEST)',           'A powered loader that raises the sustained rate of fire of a towed gun.',        'Borealis Arms (TEST)',               'In development', 'Aurora behind',    '2028 first fielding', true),
  (91122, 1, 2,  71002, 'Barrel wear sensing and life prediction (TEST)',         'Embedded sensors track bore erosion and predict remaining barrel life.',         'Fjord Institute of Technology (TEST)', 'Fielded',      'Aurora ahead',     'Fielded today',       false),
  (91123, 1, 3,  71003, 'Extended-range 58-calibre barrel (TEST)',                'A longer barrel that adds range on standard charges.',                           'Halcyon Land Systems (TEST)',        'Lab / research', 'Aurora at parity', 'by 2029',             false),
  (91124, 1, 4,  71004, 'Low-erosion modular propellant charge (TEST)',           'A propellant that cuts barrel erosion at high charge zones.',                    'Nova Propellants GmbH (TEST)',       'Lab / research', 'Aurora at parity', 'by 2030',             false),
  (91125, 1, 5,  71005, 'Insensitive-munition 155 mm fill (TEST)',                'Explosive fills that survive fire and impact without detonating.',               'Meridian Ordnance (TEST)',           'In production',  'Aurora behind',    'orders from 2027',    false),
  (91126, 1, 6,  71006, 'Guided 155 mm precision kit (TEST)',                     'A fuze-replacement kit that adds GPS guidance to unguided shells.',              'Borealis Arms (TEST)',               'In development', 'Aurora behind',    '2028',                false),
  (91127, 1, 7,  71007, 'Compact active protection system (TEST)',                'Hard-kill protection sized for light and medium armoured vehicles.',             'Cobalt Dynamics (TEST)',             'In production',  'Aurora behind',    'orders from 2027',    false),
  (91128, 1, 8,  71008, 'Composite hull armour (TEST)',                           'Lightweight ceramic-composite panels for vehicle hulls.',                        'Redstone University Labs (TEST)',    'Fielded',        'Aurora at parity', 'Fielded today',       false),
  (91129, 1, 9,  71009, 'Hybrid-electric silent drive (TEST)',                    'A diesel-electric drive enabling silent watch and lower fuel use.',              'Fjord Institute of Technology (TEST)', 'Lab / research', 'Aurora behind',  'after 2031',          false),
  (91130, 1, 10, 71010, 'Smart sight with ballistic computer (TEST)',             'A sight that computes the aim point from range and wind.',                       'Pinewood Optics Ltd (TEST)',         'Fielded',        'Aurora at parity', 'Fielded today',       false),
  (91131, 1, 11, 71011, 'Polymer-cased 5.56 mm ammunition (TEST)',                'Cartridges with a polymer case that cut ammunition weight by a third.',          'Nova Propellants GmbH (TEST)',       'In development', 'Aurora ahead',     '2028',                false),
  (91132, 1, 12, 71012, 'Interceptor drones for counter-UAS (TEST)',              'Small drones that hunt and ram or explode near enemy drones.',                   'Tessera Aerospace (TEST)',           'In development', 'Aurora at parity', '2027 trials',         false),
  (91133, 1, 13, 71013, 'Fibre-optic controlled FPV strike drones (TEST)',        'Drones controlled over a fibre cable, immune to jamming.',                       'Cobalt Dynamics (TEST)',             'Fielded',        'Aurora behind',    'Fielded today',       false),
  (91134, 1, 14, 71014, 'Swarm-resistant jammer array (TEST)',                    'A phased jammer array that defeats swarms with directional nulls.',              'Cobalt Dynamics (TEST)',             'In production',  'Aurora behind',    'orders from 2027',    false),
  (91135, 1, 15, 71015, 'Imaging infrared seeker for short-range missiles (TEST)', 'A seeker that recognises targets by shape, hard to decoy.',                     'Tessera Aerospace (TEST)',           'In development', 'Aurora behind',    'by 2029',             false),
  (91136, 1, 16, 71016, 'Programmable airburst for air-defence guns (TEST)',      'A fuze that bursts a shell at a computed point near the target.',                'Pinewood Optics Ltd (TEST)',         'In production',  'Aurora at parity', 'licence in 2027',     false);

-- technology_innovation_detail_panel: the detail panel of an innovation (panel title, texts, badge, labels). 6 rows.
INSERT INTO staging_ui.technology_innovation_detail_panel
  (panel_id, innovation_id, panel_title, close_label, source_section_label, assessment_badge, maturity_display, client_position_display,
   horizon_display, background_text, whats_new_text, why_matters_text, why_position_text) VALUES
  (91141, 71001, 'Automatic loader for towed howitzers (TEST)', 'Close', 'Sources', 'GAP',   'In development', 'Aurora behind',    '2028 first fielding',
   'An electric rammer and a magazine arm lift and ram the shell so the crew does not.', 'First live-fire trial completed this quarter at 8 rounds per minute.',
   'Aurora towed guns load by hand; a loader would close the sustained rate-of-fire gap in export tenders.', 'Aurora is behind: its guns have no powered loader.'),
  (91142, 71002, 'Barrel wear sensing and life prediction (TEST)', 'Close', 'Sources', 'AHEAD', 'Fielded', 'Aurora ahead', 'Fielded today',
   'Fibre-optic and acoustic sensors measure bore erosion round by round.', 'Fielded on two export customers; reduces unplanned barrel changes.',
   'Aurora already ships a barrel-life monitor, a selling point against rivals in life-cycle cost.', 'Aurora is ahead: no rival fields this.'),
  (91143, 71005, 'Insensitive-munition 155 mm fill (TEST)', 'Close', 'Sources', 'GAP',   'In production',  'Aurora behind',    'orders from 2027',
   'A polymer-bonded explosive resists fast and slow cook-off and bullet impact.', 'Qualification completed; first orders from two European buyers.',
   'IM compliance is becoming a tender requirement in Europe; Aurora Shell 155 is not yet qualified.', 'Aurora is behind: no IM qualification on record.'),
  (91144, 71007, 'Compact active protection system (TEST)', 'Close', 'Sources', 'GAP',   'In production',  'Aurora behind',    'orders from 2027',
   'Radar-cued countermeasures defeat incoming rockets within milliseconds.', 'First export order announced for an 8x8 fleet.',
   'Light vehicles are a growth line for Aurora; protection is a buying criterion in Brazil and India.', 'Aurora is behind: no active protection partner yet.'),
  (91145, 71011, 'Polymer-cased 5.56 mm ammunition (TEST)', 'Close', 'Sources', 'AHEAD', 'In development', 'Aurora ahead',     '2028',
   'A polymer case replaces brass, cutting a third of the ammunition weight.', 'Production line qualified by a supplier.',
   'Aurora Carbine can fire polymer-cased ammunition with a barrel change.', 'Aurora is ahead: no rival names this capability.'),
  (91146, 71012, 'Interceptor drones for counter-UAS (TEST)', 'Close', 'Sources', 'WATCH', 'In development', 'Aurora at parity', '2027 trials',
   'A radar-cued drone with electro-optical seeker closes on the target.', 'Demonstration against Group 2 drones succeeded.',
   'Counter-UAS is a priority line; the Aurora Interceptor Drone is in trials.', 'Aurora is at parity with Tessera.');

-- technology_overview_view: header and state of the Overview feed (heading, search box, sequence, showing range). 1 row.
INSERT INTO staging_ui.technology_overview_view
  (view_id, view_state_id, page_heading, search_placeholder, sequence_label, sequence_value, sequence_options, total_signals,
   showing_from, showing_to, selected_article_id) VALUES
  (91201, 2, 'Technology Overview', 'Search signals...', 'Sequence', 'newest',
   '[{"code": "newest", "label": "Newest first"}, {"code": "oldest", "label": "Oldest first"}, {"code": "threat", "label": "Threat first"}]'::jsonb, 10, 1, 10, 72001);

-- technology_overview_filter: the filter chips of the Overview feed (classification, direction, category). 4 rows.
INSERT INTO staging_ui.technology_overview_filter
  (filter_state_id, view_state_id, filter_type, filter_label, is_active, selected_value, option_values) VALUES
  (91211, 2, 'classification', 'Type',      true,  'all', '["all", "competitor_advance", "adoptable"]'::jsonb),
  (91212, 2, 'direction',      'Direction', true,  'all', '["all", "threat", "watch", "fav"]'::jsonb),
  (91213, 2, 'category',       'Category',  false, 'all', '["all", "Artillery", "Ammunition", "Armoured Vehicles", "Small Arms", "Unmanned & Counter-UAS", "Missiles & Air Defence"]'::jsonb),
  (91214, 2, 'country',        'Country',   false, 'all', '["all", "KR", "FR", "US", "DE", "IN", "NO", "GB"]'::jsonb);

-- technology_overview_metric_card: the metric cards above the Overview feed (clickable ones filter the feed). 4 rows.
INSERT INTO staging_ui.technology_overview_metric_card
  (metric_card_id, view_state_id, metric_order, metric_key, metric_label, metric_value, metric_unit, is_clickable) VALUES
  (91221, 2, 1, 'signals_total',       'Signals',             10, 'signals', false),
  (91222, 2, 2, 'competitor_advances', 'Competitor advances', 6,  'signals', true),
  (91223, 2, 3, 'adoptable',           'Adoptable',           4,  'signals', true),
  (91224, 2, 4, 'threats',             'Threats',             3,  'signals', true);

-- technology_overview_signal_card: one feed card per overview article (display strings, selected card). 10 rows.
INSERT INTO staging_ui.technology_overview_signal_card
  (card_id, view_state_id, rank_position, article_id, title_display, narrative_display, classification_display, published_date_display, is_selected) VALUES
  (91231, 2, 1,  72001, 'Halcyon fields 58-calibre barrel on self-propelled howitzer (TEST)', 'Halcyon fields a 58-calibre barrel with 25% more range than Aurora 52-calibre guns.',     'Competitor advance', '10 Oct 2026', true),
  (91232, 2, 2,  72002, 'Meridian qualifies insensitive-munition 155 mm shell (TEST)',        'Meridian completed IM qualification of a 155 mm shell, the first in its class.',            'Competitor advance', '9 Oct 2026',  false),
  (91233, 2, 3,  72003, 'Open radar-cueing software released for counter-UAS (TEST)',         'Redstone University Labs released open software that cues interceptors from commodity radars.', 'Adoptable',       '8 Oct 2026',  false),
  (91234, 2, 4,  72004, 'Cobalt unveils compact active protection for 8x8 vehicles (TEST)',   'Cobalt Dynamics launched an active protection system sized for 8x8 vehicles with a first export order.', 'Competitor advance', '7 Oct 2026', false),
  (91235, 2, 5,  72005, 'Polymer-cased 5.56 mm ammunition reaches production readiness (TEST)', 'A supplier qualified a production line for polymer-cased 5.56 mm ammunition.',            'Adoptable',          '6 Oct 2026',  false),
  (91236, 2, 6,  72006, 'Tessera tests interceptor drone with 5 km reach (TEST)',             'Tessera Aerospace demonstrated an interceptor drone with a 5 km engagement radius.',        'Competitor advance', '5 Oct 2026',  false),
  (91237, 2, 7,  72007, 'Borealis integrates automatic loader on towed gun (TEST)',           'Borealis Arms fitted an automatic loader to its towed 155 mm gun.',                         'Competitor advance', '4 Oct 2026',  false),
  (91238, 2, 8,  72008, 'Programmable airburst fuze licence offered to Aurora (TEST)',        'Pinewood Optics offers a licence for a programmable airburst fuze.',                        'Adoptable',          '3 Oct 2026',  false),
  (91239, 2, 9,  72009, 'Tessera trials imaging infrared seeker (TEST)',                      'Tessera Aerospace trialled an imaging infrared seeker against decoys.',                     'Competitor advance', '2 Oct 2026',  false),
  (91240, 2, 10, 72010, 'Nova offers low-erosion propellant licence (TEST)',                  'Nova Propellants offers a licence for a low-erosion modular propellant charge.',            'Adoptable',          '1 Oct 2026',  false);

-- technology_overview_detail_panel: the drawer chrome of an article (panel title and section labels). 6 rows.
INSERT INTO staging_ui.technology_overview_detail_panel
  (panel_id, article_id, panel_title, close_label, at_a_glance_label, what_article_says_label, key_points_label, source_label, provenance_label) VALUES
  (91241, 72001, 'Halcyon fields 58-calibre barrel on self-propelled howitzer (TEST)', 'Close', 'At a glance', 'What the article says', 'Key points', 'Sources', 'Provenance'),
  (91242, 72002, 'Meridian qualifies insensitive-munition 155 mm shell (TEST)',        'Close', 'At a glance', 'What the article says', 'Key points', 'Sources', 'Provenance'),
  (91243, 72003, 'Open radar-cueing software released for counter-UAS (TEST)',         'Close', 'At a glance', 'What the article says', 'Key points', 'Sources', 'Provenance'),
  (91244, 72004, 'Cobalt unveils compact active protection for 8x8 vehicles (TEST)',   'Close', 'At a glance', 'What the article says', 'Key points', 'Sources', 'Provenance'),
  (91245, 72007, 'Borealis integrates automatic loader on towed gun (TEST)',           'Close', 'At a glance', 'What the article says', 'Key points', 'Sources', 'Provenance'),
  (91246, 72008, 'Programmable airburst fuze licence offered to Aurora (TEST)',        'Close', 'At a glance', 'What the article says', 'Key points', 'Sources', 'Provenance');

-- technology_overview_detail_section: the labelled sections inside an article drawer (text value, linked source). 24 rows.
INSERT INTO staging_ui.technology_overview_detail_section
  (section_id, panel_id, section_order, section_code, section_label, value_text, source_id) VALUES
  (91251, 91241, 1, 'at_a_glance',       'At a glance',           'Halcyon Land Systems (TEST) - Artillery - South Korea',                                           70119),
  (91252, 91241, 2, 'what_article_says', 'What the article says', 'Halcyon delivered the first self-propelled howitzers with a 58-calibre barrel to its home army.', 70119),
  (91253, 91241, 3, 'key_points',        'Key points',            'First delivery; 70 km in trials; Aurora 52-calibre guns would lose range in tenders.',            70119),
  (91254, 91241, 4, 'provenance',        'Provenance',            'verified',                                                                                         70129),
  (91255, 91242, 1, 'at_a_glance',       'At a glance',           'Meridian Ordnance (TEST) - Ammunition - France',                                                  70120),
  (91256, 91242, 2, 'what_article_says', 'What the article says', 'Meridian completed qualification of an insensitive-munition 155 mm shell and booked first orders.', 70120),
  (91257, 91242, 3, 'key_points',        'Key points',            'Qualification complete; two European buyers.',                                                    70120),
  (91258, 91242, 4, 'provenance',        'Provenance',            'verified',                                                                                         70130),
  (91259, 91243, 1, 'at_a_glance',       'At a glance',           'Redstone University Labs (TEST) - Unmanned & Counter-UAS - United States',                       70121),
  (91260, 91243, 2, 'what_article_says', 'What the article says', 'Open-source software links commodity radars to interceptor drones.',                             70121),
  (91261, 91243, 3, 'key_points',        'Key points',            'Open source; works with commodity radars.',                                                       70121),
  (91262, 91243, 4, 'provenance',        'Provenance',            'verified',                                                                                         70121),
  (91263, 91244, 1, 'at_a_glance',       'At a glance',           'Cobalt Dynamics (TEST) - Armoured Vehicles - United States',                                      70122),
  (91264, 91244, 2, 'what_article_says', 'What the article says', 'Cobalt unveiled a compact active protection system and announced the first export order.',      70122),
  (91265, 91244, 3, 'key_points',        'Key points',            'Sized for 8x8 vehicles; first export order; radar-cued.',                                         70122),
  (91266, 91244, 4, 'provenance',        'Provenance',            'verified; single_source',                                                                          70131),
  (91267, 91245, 1, 'at_a_glance',       'At a glance',           'Borealis Arms (TEST) - Artillery - Norway',                                                       70125),
  (91268, 91245, 2, 'what_article_says', 'What the article says', 'Borealis integrated a powered loader on its towed gun and reached 8 rounds per minute.',         70125),
  (91269, 91245, 3, 'key_points',        'Key points',            '8 rounds per minute; fits the existing towed gun.',                                               70125),
  (91270, 91245, 4, 'provenance',        'Provenance',            'verified',                                                                                         70133),
  (91271, 91246, 1, 'at_a_glance',       'At a glance',           'Pinewood Optics Ltd (TEST) - Missiles & Air Defence - United Kingdom',                            70126),
  (91272, 91246, 2, 'what_article_says', 'What the article says', 'Pinewood offered Aurora and other makers a licence for a programmable airburst fuze.',          70126),
  (91273, 91246, 3, 'key_points',        'Key points',            'Licence offered; inductively set fuze.',                                                          70126),
  (91274, 91246, 4, 'provenance',        'Provenance',            'verified',                                                                                         70126);

COMMIT;
