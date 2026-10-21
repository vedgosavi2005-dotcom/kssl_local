-- 90_foundations.sql  Rows for the tables and columns added by db/setup/11_foundations.sql (prompt rebuild, phase 2).
-- FICTIONAL, obviously test data. Reads ids from 10_competitive / 50_geo_project / 60_market / 70_technology:
--   signals a6000000-...-00000000000N, tenders 60001.., requirements 62001.., innovations 71001.., articles 72001.., geo locations 50001..
-- Idempotent: the new-table rows are deleted and re-inserted; the new columns are UPDATEd on rows that already exist.
BEGIN;

-- ---- story + steps (a story is a review card; its steps are its children) -----------------------------------------------------------
DELETE FROM staging.story_step WHERE story_id IN (91001, 91002);
DELETE FROM staging.story WHERE story_id IN (91001, 91002);
INSERT INTO staging.story (story_id, story_key, pillar, kind, competitor_id, buyer_name, country_code, title, current_label, probability, impact, impact_dimension,
                           status, first_step_at, last_step_at, escalated_at, rule_version) VALUES
 (91001, 'competitive:borealis:howitzer:no:order', 'competitive', 'order', 'c0ffee00-0000-4000-8000-000000000001', 'Norland MoD (TEST)', 'NO',
  'Borealis howitzer order, Norland (TEST)', 'threat', 5, 5, 'orders_revenue', 'open', '2026-06-20', '2026-10-08', '2026-10-08', 's1'),
 (91002, 'competitive:halcyon:sph-155:ae:order', 'competitive', 'order', 'c0ffee00-0000-4000-8000-000000000003', 'UAE MoD (TEST)', 'AE',
  'Halcyon SPH-155 export, UAE (TEST)', 'watch', 3, 3, 'orders_revenue', 'open', '2026-09-01', '2026-10-11', NULL, 's1');
INSERT INTO staging.story_step (step_id, story_id, step_no, step_date, step_type, one_line, changed, source_url, source_table, source_row_id, probability, impact, label_after) VALUES
 (91101, 91001, 1, '2026-06-20', 'announced', 'Borealis shortlisted for the Norland howitzer competition (TEST)', NULL, 'https://example.com/test/borealis-shortlist', NULL, NULL, 3, 4, 'watch'),
 (91102, 91001, 2, '2026-10-08', 'order', 'Borealis wins the NOK 2.1 bn order (TEST)', NULL, 'https://example.com/test/borealis-order', 'competitive_signal', 'a6000000-0000-4000-8000-000000000001', 5, 5, 'threat'),
 (91103, 91001, 3, '2026-10-08', 'label_change', 'Label changed from watch to threat (TEST)', 'watch -> threat: probability 3 -> 5 (contract signed)', 'https://example.com/test/borealis-order', 'competitive_signal', 'a6000000-0000-4000-8000-000000000001', 5, 5, 'threat'),
 (91104, 91002, 1, '2026-10-11', 'order', 'Halcyon signs an export deal for 72 SPH-155 (TEST)', NULL, 'https://example.com/test/halcyon-export', 'competitive_signal', 'a6000000-0000-4000-8000-000000000002', 3, 3, 'watch');

-- ---- competitive: signal scores, glance, moment link, product news, partnership, geo, project, patents -------------------------------
UPDATE staging.competitive_signal SET story_id = 91001, direction = 'adverse', probability = 5, impact = 5, impact_dimension = 'orders_revenue',
    impact_dimension_2 = 'market_standing', time_to_effect = '1_3y', subtype_match = 'same', in_client_market = 'yes', rule_version = 's1',
    impact_orders_revenue = 5, impact_market_standing = 4, impact_supply_chain = 1, impact_technology_gap = 2, impact_partnerships = 1, impact_policy_export = 2
 WHERE signal_id = 'a6000000-0000-4000-8000-000000000001';
UPDATE staging.competitive_signal SET story_id = 91002, direction = 'adverse', probability = 3, impact = 3, impact_dimension = 'orders_revenue',
    time_to_effect = 'gt_3y', subtype_match = 'same', in_client_market = 'unknown', rule_version = 's1',
    impact_orders_revenue = 3, impact_market_standing = 2, impact_supply_chain = 1, impact_technology_gap = 1, impact_partnerships = 1, impact_policy_export = 1
 WHERE signal_id = 'a6000000-0000-4000-8000-000000000002';
UPDATE staging.competitive_signal_detail SET glance_who = 'Borealis (TEST)', glance_move = 'Order', glance_where = 'Norland (TEST)',
    glance_impact = 'Orders · high', glance_third_party = 'Norland MoD (TEST)', glance_when = '8 Oct 2026 · deliveries 2028'
 WHERE signal_id = 'a6000000-0000-4000-8000-000000000001';
UPDATE staging.competitive_competitor_moment SET signal_id = 'a6000000-0000-4000-8000-000000000001', change_note = 'Order follows the June shortlist (TEST)', story_id = 91001
 WHERE moment_id = (SELECT min(moment_id) FROM staging.competitive_competitor_moment WHERE competitor_id = 'c0ffee00-0000-4000-8000-000000000001');
UPDATE staging.competitive_product_news SET news_type = 'programme_order', event_date = published_date, product_variant = 'Mk2 (TEST)',
    kssl_relevance = 'Same class as a KSSL towed howitzer (TEST)', story_id = 91001
 WHERE product_news_id = (SELECT min(product_news_id::text)::uuid FROM staging.competitive_product_news);
UPDATE staging.competitive_partnership SET status = 'active', value_to_competitor = 'market_access: local assembly route (TEST)', value_to_partner = 'technology: gun barrel know-how (TEST)',
    kssl_read = 'Competes with a KSSL supply route; the same partner supplies forgings to KSSL (TEST)', overlap_client_partner_id = 9402, overlap_kind = 'same_partner_other_scope',
    overlap_component = 'forged barrel blanks (TEST)', overlap_effect = 'risk'
 WHERE relationship_id = (SELECT min(relationship_id::text)::uuid FROM staging.competitive_partnership);
UPDATE staging.competitive_partnership_evidence SET step_type = 'agreement'
 WHERE evidence_card_id = (SELECT min(evidence_card_id::text)::uuid FROM staging.competitive_partnership_evidence);
UPDATE staging.competitive_geo_product SET customer_name = 'Norland MoD (TEST)', local_partner = 'Norland Motor Works (TEST)'
 WHERE geo_product_id = (SELECT min(geo_product_id) FROM staging.competitive_geo_product);
UPDATE staging.competitive_project SET kssl_option = 'compete', story_id = 91001
 WHERE project_id = (SELECT min(project_id) FROM staging.competitive_project);
UPDATE staging.competitive_patent_filing SET category_label = 'Propulsion (TEST)'
 WHERE publication_number = (SELECT min(publication_number) FROM staging.competitive_patent_filing);
UPDATE staging.client_product SET product_kind = 'product' WHERE product_kind IS NULL;
UPDATE staging.competitive_product SET subcategory = 'towed_howitzer' WHERE product_id = (SELECT min(product_id::text)::uuid FROM staging.competitive_product);
UPDATE staging.client_partner_product SET component = 'forged barrel blanks (TEST)'
 WHERE partner_product_id = (SELECT min(partner_product_id) FROM staging.client_partner_product);

DELETE FROM staging.competitive_geo_analysis WHERE analysis_id IN (92001, 92002);
INSERT INTO staging.competitive_geo_analysis (analysis_id, location_id, competitor_id, kind, finding, stated_reasons, reason_state, hypothesis, to_find_out, source_url, display_order) VALUES
 (92001, 50001, 'c0ffee00-0000-4000-8000-000000000001', 'anomaly', 'India bought the Borealis gun although the stored matchup puts KSSL ahead on range (TEST)',
  ARRAY['local_partner'], 'stated', NULL, 'Whether price or local assembly decided it (TEST)', 'https://example.com/test/geo-anomaly', 1),
 (92002, 50002, NULL, 'whitespace', 'A comparable rival sells 155 mm towed guns here and KSSL has no row (TEST)', NULL, 'not_stated',
  'Rival has sold here since 2022; KSSL has no presence row (TEST, analyst hypothesis)', 'Ask the local agent who the incumbent supplier is (TEST)', NULL, 2);
DELETE FROM staging.competitive_patent_trend WHERE trend_id IN (93001, 93002, 93003);
INSERT INTO staging.competitive_patent_trend (trend_id, portfolio_id, category_label, year, filing_count) VALUES
 (93001, 'e1000000-0000-4000-8000-000000000001', 'Propulsion (TEST)', 2025, 3),
 (93002, 'e1000000-0000-4000-8000-000000000001', 'Propulsion (TEST)', 2026, 7),
 (93003, 'e1000000-0000-4000-8000-000000000002', 'Guidance (TEST)', 2026, 2);

-- ---- market -------------------------------------------------------------------------------------------------------------------------
UPDATE staging.market_tender SET awarded_to = 'Borealis (TEST)', award_date = '2026-09-30', award_value_text = 'NOK 2.1 bn (TEST)' WHERE tender_id = 60002;
UPDATE staging.market_tender_closing_window SET clarification_deadline = '2026-11-01', opening_date = '2026-12-01'
 WHERE closing_window_id = (SELECT min(closing_window_id) FROM staging.market_tender_closing_window);
UPDATE staging.market_tender_fit_assessment SET value_score = 4, strategic_score = 4, attractiveness = 4, ability = 3, pursue_label = 'position', time_to_award = '6_18m', rule_version = 'p1'
 WHERE assessment_id = (SELECT min(assessment_id) FROM staging.market_tender_fit_assessment);
UPDATE staging.market_opportunity_fit_assessment SET value_score = 3, strategic_score = 3, attractiveness = 3, ability = 4, pursue_label = 'pursue', time_to_award = 'unknown', rule_version = 'p1'
 WHERE assessment_id = (SELECT min(assessment_id) FROM staging.market_opportunity_fit_assessment);
UPDATE staging.market_tender_competitor_fit SET basis = 'presence' WHERE competitor_fit_id = (SELECT min(competitor_fit_id) FROM staging.market_tender_competitor_fit);
UPDATE staging.market_next_move SET move_kind = 'find_partner' WHERE next_move_id = (SELECT min(next_move_id) FROM staging.market_next_move);
UPDATE staging.market_global_requirement SET stage = 'downselect_prototype', stage_date = '2026-06-01', last_confirmed = '2026-08-15', status_state = 'current', story_id = NULL
 WHERE requirement_id = 62001;
UPDATE staging.market_opportunity SET requirement_id = 62001, tender_id = 60002, story_id = NULL
 WHERE opportunity_id = (SELECT min(opportunity_id) FROM staging.market_opportunity);

DELETE FROM staging.market_tender_eligibility WHERE eligibility_id IN (94001, 94002);
INSERT INTO staging.market_tender_eligibility (eligibility_id, tender_id, item, state, fixable, note, quote, display_order) VALUES
 (94001, 60002, 'Local content 30 percent (TEST)', 'not_met', 'yes', 'A local assembly partner is accepted (TEST)', 'A minimum of 30 percent local content, which may be achieved through a local partner. (TEST)', 1),
 (94002, 60002, 'Bid security 2 percent (TEST)', 'unknown', 'yes', 'Standard bank guarantee (TEST)', 'Bid security of 2 percent of the bid value. (TEST)', 2);
DELETE FROM staging.market_global_requirement_rival WHERE rival_id IN (95001, 95002);
INSERT INTO staging.market_global_requirement_rival (rival_id, requirement_id, competitor_id, basis, note, display_order) VALUES
 (95001, 62001, 'c0ffee00-0000-4000-8000-000000000001', 'selected', 'Selected for the prototype phase (TEST)', 1),
 (95002, 62001, 'c0ffee00-0000-4000-8000-000000000003', 'shortlisted', 'Shortlisted (TEST)', 2);

-- ---- technology ---------------------------------------------------------------------------------------------------------------------
UPDATE staging.technology_overview_article SET maturity = 3, relevance = 5, horizon = '2_5y', horizon_source = 'stated', touches_client_product_id = 9101,
    spec_touched = 'Maximum range (TEST)', client_position = 'behind', rule_version = 't1', story_id = NULL
 WHERE overview_article_id = 72001;
UPDATE staging.technology_innovation SET maturity_level = 3, technology_kind = 'propulsion', stance = 'watch' WHERE innovation_id = 71001;
DELETE FROM staging.technology_innovation_milestone WHERE milestone_id IN (96001, 96002);
INSERT INTO staging.technology_innovation_milestone (milestone_id, innovation_id, step_date, step_type, note, source_url) VALUES
 (96001, 71001, '2026-03-01', 'announced', 'Announced at a trade show (TEST)', 'https://example.com/test/loader-announced'),
 (96002, 71001, '2026-09-10', 'trials', 'First trials with a towed howitzer (TEST)', 'https://example.com/test/loader-trials');

-- ---- ui: option lists --------------------------------------------------------------------------------------------------------------
UPDATE staging_ui.market_tender_filter SET day_from = 0, day_to = 7, tag_class = 'w7' WHERE filter_id = (SELECT min(filter_id) FROM staging_ui.market_tender_filter);
DELETE FROM staging_ui.competitive_filter_option WHERE option_id IN (97001, 97002);
INSERT INTO staging_ui.competitive_filter_option (option_id, filter_type, option_code, option_label, record_count, sort_order, is_active) VALUES
 (97001, 'classification', 'threat', 'Threat', 1, 1, true), (97002, 'classification', 'watch', 'Watch', 6, 2, true);
DELETE FROM staging_ui.technology_filter_option WHERE option_id IN (98001, 98002);
INSERT INTO staging_ui.technology_filter_option (option_id, filter_type, option_code, option_label, record_count, sort_order, is_active) VALUES
 (98001, 'classification', 'competitor_advance', 'Competitor advance', 3, 1, true), (98002, 'classification', 'adoptable', 'Adoptable', 2, 2, true);

COMMIT;
