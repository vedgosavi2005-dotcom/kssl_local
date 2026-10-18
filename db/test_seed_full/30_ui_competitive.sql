-- 30_ui_competitive.sql
-- (part A) Every staging_ui.competitive_* table (competitive_geo_filter is written by 50_geo_project.sql) and staging_ui.ui_competitor_* table: page chrome, filters and view state of the Competitive pillar.
-- moment levels high / watch / opportunity, time windows 30d / 90d / 1y. Rows reference competitors, signals, moments, matchups of 10_competitive.sql.
-- Note: a few view-state columns are bigint although the thing they point at has a uuid key (selected_competitor_id in ui_competitor_moment_view_state, selected_leader_id in
-- competitive_profile_view_state); those are NULL = nothing selected.
BEGIN;

-- own tables, children first
DELETE FROM staging_ui.ui_competitor_moment_metric;
DELETE FROM staging_ui.ui_competitor_moment_view_state;
DELETE FROM staging_ui.competitive_ui_state;
DELETE FROM staging_ui.competitive_profile_view_state;
DELETE FROM staging_ui.competitive_product_view_state;
DELETE FROM staging_ui.competitive_positioning_view_state;
DELETE FROM staging_ui.competitive_positioning_tab;
DELETE FROM staging_ui.competitive_pillar;
DELETE FROM staging_ui.competitive_patent_view_state;
DELETE FROM staging_ui.competitive_partnership_graph;
DELETE FROM staging_ui.competitive_overview_feed;
DELETE FROM staging_ui.competitive_news_view;
DELETE FROM staging_ui.competitive_navigation;
DELETE FROM staging_ui.competitive_metric;
DELETE FROM staging_ui.competitive_competitor_moment_time_window;
DELETE FROM staging_ui.competitive_competitor_moment_level;

-- Grades a move can have; grade in competitive_competitor_moment must be one of these level_codes (Competitor Moment filter chips and card tags).
INSERT INTO staging_ui.competitive_competitor_moment_level
  (level_code, level_label, tag_class, display_order) VALUES
  ('high', 'High threat', 'threat', 1),
  ('watch', 'Watch', 'watch', 2),
  ('opportunity', 'Opportunity', 'opportunity', 3);

-- Time-window choices of Competitor Moment (30d / 90d / 1y; 90d is the default).
INSERT INTO staging_ui.competitive_competitor_moment_time_window
  (time_window_id, time_window_code, time_window_label, day_count, is_default, display_order) VALUES
  (1, '30d', 'Last 30 days', 30, false, 1),
  (2, '90d', 'Last 90 days', 90, true, 2),
  (3, '1y', 'Last 12 months', 365, false, 3);

-- Metric tiles above the Overview feed (labels, stored counts, as-of date).
INSERT INTO staging_ui.competitive_metric
  (metric_id, metric_label, metric_value, as_of_date, display_order) VALUES
  ('f1000000-0000-4000-8000-000000000001', 'Competitors tracked', 5, '2026-10-16', 1),
  ('f1000000-0000-4000-8000-000000000002', 'Competitive threats', 4, '2026-10-16', 2),
  ('f1000000-0000-4000-8000-000000000003', 'Watch signals', 5, '2026-10-16', 3),
  ('f1000000-0000-4000-8000-000000000004', 'Favourable signals', 1, '2026-10-16', 4),
  ('f1000000-0000-4000-8000-000000000005', 'All signals', 10, '2026-10-16', 5);

-- Left-rail entries of the Competitive pillar with the record count shown beside each.
INSERT INTO staging_ui.competitive_navigation
  (view_key, view_label, view_sequence, is_active, record_count) VALUES
  ('overview', 'Overview', 1, true, 10),
  ('profile', 'Competitor Profile', 2, true, 5),
  ('moment', 'Competitor Moment', 3, true, 13),
  ('products', 'Products', 4, true, 21),
  ('evaluation', 'Product Evaluation', 5, true, 12),
  ('partnerships', 'Partnerships', 6, true, 12),
  ('projects', 'Projects', 7, true, 6),
  ('geo', 'Geo Footprint', 8, true, 8),
  ('patents', 'Patents', 9, true, 14);

-- Saved state of the Profile > News list per competitor (filters, date range, paging).
INSERT INTO staging_ui.competitive_news_view
  (news_view_id, competitor_id, category_filter, date_filter, published_range, custom_start_date, custom_end_date, page_no, page_size, search_query) VALUES
  ('f2000000-0000-4000-8000-000000000001', 'c0ffee00-0000-4000-8000-000000000001', 'All', 'all_time', '12m', '2026-01-01', '2026-10-16', 1, 15, 'howitzer'),
  ('f2000000-0000-4000-8000-000000000002', 'c0ffee00-0000-4000-8000-000000000002', 'Delivery & induction', 'last_30_days', '30d', '2026-09-16', '2026-10-16', 1, 15, 'APC'),
  ('f2000000-0000-4000-8000-000000000003', 'c0ffee00-0000-4000-8000-000000000003', 'Export', 'last_12_months', '12m', '2025-10-16', '2026-10-16', 1, 20, 'SPH'),
  ('f2000000-0000-4000-8000-000000000004', 'c0ffee00-0000-4000-8000-000000000004', 'All', 'custom', 'custom', '2026-05-01', '2026-09-30', 2, 15, 'shell'),
  ('f2000000-0000-4000-8000-000000000005', 'c0ffee00-0000-4000-8000-000000000005', 'Product launch & testing', 'last_6_months', '6m', '2026-04-16', '2026-10-16', 1, 15, 'missile');

-- Overview feed state: sequence, threat filter, search box, empty-state text.
INSERT INTO staging_ui.competitive_overview_feed
  (feed_id, sequence_mode, threat_filter, local_search_query, visible_signal_count, empty_message) VALUES
  ('f3000000-0000-4000-8000-000000000001', 'priority', 'all', '', 10, 'No signals match the current filters (TEST DATA).'),
  ('f3000000-0000-4000-8000-000000000002', 'priority', 'threat', '', 4, 'No threat signals match the current filters (TEST DATA).'),
  ('f3000000-0000-4000-8000-000000000003', 'recent', 'watch', 'shell', 2, 'No watch signals match ''shell'' (TEST DATA).'),
  ('f3000000-0000-4000-8000-000000000004', 'recent', 'all', 'Borealis', 2, 'No signals found for this search (TEST DATA).');

-- Partnership graph state per competitor (group-by, zoom, selected partner, card count).
INSERT INTO staging_ui.competitive_partnership_graph
  (graph_state_id, competitor_id, group_by, legend_type, zoom_level, selected_partner_id, partner_card_count, partner_node_click, relationship_detail_action, reset_action, zoom_in_action, zoom_out_action) VALUES
  ('f4000000-0000-4000-8000-000000000001', 'c0ffee00-0000-4000-8000-000000000001', 'partner_type', 'Partner type', 1.25, 'd1000000-0000-4000-8000-000000000001', 3, true, true, false, false, false),
  ('f4000000-0000-4000-8000-000000000002', 'c0ffee00-0000-4000-8000-000000000002', 'region', 'Region', 1.5, 'c0ffee00-0000-4000-8000-000000000005', 3, false, true, false, false, true),
  ('f4000000-0000-4000-8000-000000000003', 'c0ffee00-0000-4000-8000-000000000003', 'partner_type', 'Partner type', 1.0, 'd1000000-0000-4000-8000-000000000005', 3, true, true, false, true, false),
  ('f4000000-0000-4000-8000-000000000004', 'c0ffee00-0000-4000-8000-000000000004', 'region', 'Region', 1.25, 'd1000000-0000-4000-8000-000000000008', 2, false, true, false, false, false),
  ('f4000000-0000-4000-8000-000000000005', 'c0ffee00-0000-4000-8000-000000000005', 'partner_type', 'Partner type', 1.5, 'd1000000-0000-4000-8000-000000000010', 2, true, true, false, false, true);

-- Patents page state: lens (rival / field), selected rival or field, filters.
INSERT INTO staging_ui.competitive_patent_view_state
  (view_state_id, active_lens, selected_competitor_id, selected_technology_area, category_filter, competitor_search_text, technology_search_text, panel_open) VALUES
  (1, 'rival', 'c0ffee00-0000-4000-8000-000000000001', 'Gun barrels and breech mechanisms', 'Guided projectiles', 'Borealis', '', true),
  (2, 'rival', 'c0ffee00-0000-4000-8000-000000000003', 'Ammunition fuzes', 'Ammunition fuzes', '', 'fuze', false),
  (3, 'field', 'c0ffee00-0000-4000-8000-000000000002', 'Counter-UAS interceptors', 'Counter-UAS interceptors', '', 'drone', true),
  (4, 'field', 'c0ffee00-0000-4000-8000-000000000004', 'Armour and vehicle protection', 'Armour and vehicle protection', 'Meridian', 'armour', false);

-- Top bar of the Competitive pillar: brand, account label, global search, print action.
INSERT INTO staging_ui.competitive_pillar
  (pillar_id, active_pillar, brand_name, account_label, global_search_query, print_report_action) VALUES
  ('f5000000-0000-4000-8000-000000000001', 'competitive', 'Parallax Intelligence (TEST)', 'Aurora Defence (TEST)', '', true),
  ('f5000000-0000-4000-8000-000000000002', 'market', 'Parallax Intelligence (TEST)', 'Aurora Defence (TEST)', 'tender', true),
  ('f5000000-0000-4000-8000-000000000003', 'technology', 'Parallax Intelligence (TEST)', 'Aurora Defence (TEST)', 'shell', false);

-- Tabs of Product Evaluation (Analytics, Spec Comparison, ...).
INSERT INTO staging_ui.competitive_positioning_tab
  (tab_id, tab_code, tab_label, display_order, is_enabled) VALUES
  (1, 'analytics', 'Analytics', 1, true),
  (2, 'spec_comparison', 'Spec Comparison', 2, true),
  (3, 'advantages', 'Advantages', 3, true),
  (4, 'sources', 'Sources', 4, true),
  (5, 'gap_analysis', 'Gap Analysis', 5, false);

-- Product Evaluation state: tab, category, rival, matchup, compare product.
INSERT INTO staging_ui.competitive_positioning_view_state
  (view_state_id, active_tab, selected_category, selected_competitor_id, selected_matchup_id, compare_product_id, search_text, panel_open) VALUES
  (1, 'analytics', 'Artillery', 'c0ffee00-0000-4000-8000-000000000001', 9301, 9101, '', true),
  (2, 'spec_comparison', 'Ammunition', 'c0ffee00-0000-4000-8000-000000000003', 9305, 9103, 'range', true),
  (3, 'analytics', 'Unmanned & Counter-UAS', 'c0ffee00-0000-4000-8000-000000000005', 9311, 9106, '', false);

-- Products page state: filters and the selected product (client products use their bigint id).
INSERT INTO staging_ui.competitive_product_view_state
  (view_state_id, category_filter, country_filter, revenue_filter, company_search_text, product_search_text, selected_company_id, selected_product_id, selected_news_category, panel_open) VALUES
  (1, 'Artillery', 'Norway', 'USD 1-5 bn', '', 'howitzer', 'c0ffee00-0000-4000-8000-000000000001', 9101, 'Contract & order', true),
  (2, 'Ammunition', 'South Korea', 'USD 1-5 bn', 'Halcyon', 'shell', 'c0ffee00-0000-4000-8000-000000000003', 9103, 'Product launch & testing', true),
  (3, 'Armoured Vehicles', 'France', 'EUR 1-5 bn', '', 'APC', 'c0ffee00-0000-4000-8000-000000000004', 9104, 'Delivery & induction', false);

-- Competitor Profile state: selected competitor, section, news filters (selected_leader_id is bigint; leaders have uuid keys, so NULL).
INSERT INTO staging_ui.competitive_profile_view_state
  (view_state_id, selected_competitor_id, active_section, search_text, news_category, news_range, news_search_text, selected_leader_id, panel_open) VALUES
  (1, 'c0ffee00-0000-4000-8000-000000000001', 'overview', '', 'All', '12m', '', NULL, false),
  (2, 'c0ffee00-0000-4000-8000-000000000003', 'leaders', '', 'Export', '6m', 'SPH', NULL, true),
  (3, 'c0ffee00-0000-4000-8000-000000000005', 'news', 'Tessera', 'Product launch & testing', '30d', 'missile', NULL, false);

-- Generic page state per Competitive view: drawer, loading, empty and error flags (the last row is an error example).
INSERT INTO staging_ui.competitive_ui_state
  (state_id, active_view, drawer_open, selected_record_id, is_loading, empty_state_code, render_error_code, render_error_message, retry_action, last_refreshed_at) VALUES
  ('f6000000-0000-4000-8000-000000000001', 'overview', true, 'a6000000-0000-4000-8000-000000000001', false, NULL, NULL, NULL, NULL, '2026-10-16 07:30:00'),
  ('f6000000-0000-4000-8000-000000000002', 'profile', false, 'c0ffee00-0000-4000-8000-000000000001', false, NULL, NULL, NULL, NULL, '2026-10-16 07:30:00'),
  ('f6000000-0000-4000-8000-000000000003', 'patents', false, NULL, false, 'no_filings', NULL, NULL, NULL, '2026-10-16 07:30:00'),
  ('f6000000-0000-4000-8000-000000000004', 'partnerships', false, NULL, true, NULL, NULL, NULL, NULL, '2026-10-16 07:29:00'),
  ('f6000000-0000-4000-8000-000000000005', 'geo', false, NULL, false, NULL, 'LOAD_FAILED', 'Could not load the geo footprint (TEST DATA error example).', true, '2026-10-16 07:25:00');

-- Competitor Moment state: time window, sequence, selected move, search, date range (selected_competitor_id is bigint, competitors have uuid keys, so NULL).
INSERT INTO staging_ui.ui_competitor_moment_view_state
  (view_state_id, time_window, sequence, selected_competitor_id, selected_moment_id, search_text, from_date, to_date, panel_open) VALUES
  (1, '90d', 'priority', NULL, 9401, '', '2026-07-18', '2026-10-16', true),
  (2, '30d', 'newest', NULL, 9402, '', '2026-09-16', '2026-10-16', true),
  (3, '1y', 'newest', NULL, 9413, 'shell', '2025-10-16', '2026-10-16', false),
  (4, '90d', 'priority', NULL, 9405, 'Poland', '2026-07-18', '2026-10-16', false);

-- Metric tiles of Competitor Moment for the default 90-day view (view_state_id 1).
INSERT INTO staging_ui.ui_competitor_moment_metric
  (metric_id, view_state_id, display_order, metric_label, metric_unit, metric_value) VALUES
  (9501, 1, 1, 'Moves in window', 'moves', 11),
  (9502, 1, 2, 'High threat', 'moves', 4),
  (9503, 1, 3, 'Watch', 'moves', 5),
  (9504, 1, 4, 'Opportunity', 'moves', 2),
  (9505, 1, 5, 'Competitors active', 'companies', 5),
  (9506, 1, 6, 'Countries involved', 'countries', 8);

COMMIT;
