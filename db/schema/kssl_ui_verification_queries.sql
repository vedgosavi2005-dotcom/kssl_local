/* KSSL frontend / PostgreSQL verification queries
 *
 * Read-only checks for DBeaver. The temporary tables used in sections 3 and 4
 * disappear at the end of the transaction/session and do not change ui or serving.
 * Run section by section while the frontend is running on http://127.0.0.1:5178.
 */

/* 1. Connection and schema check */
SELECT current_database() AS database_name,
       current_user AS database_user,
       inet_server_addr() AS server_address,
       inet_server_port() AS server_port;

SELECT schema_name
FROM information_schema.schemata
WHERE schema_name IN ('ui', 'serving')
ORDER BY schema_name;

/* 2. Confirm every expected table and column exists */
SELECT table_schema,
       COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema IN ('ui', 'serving')
  AND table_type = 'BASE TABLE'
GROUP BY table_schema
ORDER BY table_schema;

SELECT table_schema,
       COUNT(*) AS column_count
FROM information_schema.columns
WHERE table_schema IN ('ui', 'serving')
GROUP BY table_schema
ORDER BY table_schema;

SELECT table_schema,
       table_name,
       ordinal_position,
       column_name,
       data_type,
       udt_name,
       is_nullable,
       character_maximum_length,
       numeric_precision,
       numeric_scale
FROM information_schema.columns
WHERE table_schema IN ('ui', 'serving')
ORDER BY table_schema, table_name, ordinal_position;

/* 3. Exact row count for all 151 tables */
CREATE TEMP TABLE _kssl_table_counts (
    table_schema text,
    table_name text,
    row_count bigint
) ON COMMIT DROP;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('ui', 'serving')
          AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
    LOOP
        EXECUTE format(
            'INSERT INTO _kssl_table_counts SELECT %L, %L, COUNT(*) FROM %I.%I',
            r.table_schema, r.table_name, r.table_schema, r.table_name
        );
    END LOOP;
END $$;

SELECT table_schema, table_name, row_count
FROM _kssl_table_counts
ORDER BY table_schema, table_name;

SELECT table_schema,
       COUNT(*) FILTER (WHERE row_count > 0) AS non_empty_tables,
       SUM(row_count) AS total_rows
FROM _kssl_table_counts
GROUP BY table_schema
ORDER BY table_schema;

/* 4. Return every table's current rows as JSON. Empty tables return []. */
CREATE TEMP TABLE _kssl_table_rows (
    table_schema text,
    table_name text,
    rows jsonb
) ON COMMIT DROP;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('ui', 'serving')
          AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
    LOOP
        EXECUTE format(
            'INSERT INTO _kssl_table_rows '
            'SELECT %L, %L, COALESCE(jsonb_agg(to_jsonb(x)), ''[]''::jsonb) '
            'FROM %I.%I AS x',
            r.table_schema, r.table_name, r.table_schema, r.table_name
        );
    END LOOP;
END $$;

SELECT table_schema, table_name, rows
FROM _kssl_table_rows
ORDER BY table_schema, table_name;

/* 5. Client/header value shown in the frontend top-right */
SELECT client_id,
       client_name,
       brand_name,
       legal_name,
       country,
       headquarters,
       industry_sector,
       account_status
FROM serving.client_account
ORDER BY client_id;

/* 6. Competitive overview, navigation, signals, and details */
SELECT * FROM ui.competitive_navigation ORDER BY view_sequence;
SELECT * FROM ui.competitive_metric ORDER BY display_order;
SELECT * FROM ui.competitive_overview_feed;
SELECT signal_id, classification, sequence_no, title, category, company_id, event_date, summary
FROM serving.competitive_signal
ORDER BY sequence_no, event_date DESC NULLS LAST;
SELECT * FROM serving.competitive_signal_detail ORDER BY signal_id;
SELECT * FROM serving.competitive_signal_evidence ORDER BY signal_id, display_order;

/* 7. Competitor Profile */
SELECT * FROM serving.competitive_competitor ORDER BY display_name;
SELECT * FROM serving.competitive_competitor_location ORDER BY competitor_id, location_name;
SELECT * FROM serving.competitive_competitor_swot ORDER BY competitor_id, swot_type;
SELECT * FROM serving.competitive_news_article ORDER BY published_date DESC NULLS LAST;
SELECT * FROM serving.competitive_leader ORDER BY competitor_id, full_name;
SELECT * FROM serving.competitive_leader_record ORDER BY leader_id, start_date;

/* 8. Competitor Moment */
SELECT * FROM ui.competitive_competitor_moment_time_window ORDER BY display_order;
SELECT * FROM ui.competitive_competitor_moment_level ORDER BY display_order;
SELECT * FROM serving.competitive_competitor_moment ORDER BY display_order, movement_date DESC NULLS LAST;
SELECT * FROM serving.competitive_competitor_moment_analysis ORDER BY moment_id, display_order;
SELECT * FROM serving.competitive_competitor_moment_source ORDER BY moment_id, source_id;

/* 9. Products and Product Evaluation, including specifications */
SELECT * FROM ui.competitive_product_view_state;
SELECT * FROM ui.competitive_positioning_tab ORDER BY display_order;
SELECT * FROM ui.competitive_positioning_view_state;
SELECT * FROM serving.client_product ORDER BY client_product_id;
SELECT * FROM serving.client_product_specification ORDER BY client_product_id, spec_name;
SELECT * FROM serving.competitive_product ORDER BY competitor_id, category, product_name;
SELECT * FROM serving.competitive_product_specification ORDER BY product_id, spec_label;
SELECT * FROM serving.competitive_product_program ORDER BY product_id, program_date;
SELECT * FROM serving.competitive_product_news ORDER BY product_id, published_date DESC NULLS LAST;
SELECT * FROM serving.competitive_matchup ORDER BY matchup_id;
SELECT * FROM serving.competitive_matchup_specification ORDER BY matchup_id, display_order;
SELECT * FROM serving.competitive_matchup_advantage ORDER BY matchup_id, side, display_order;
SELECT * FROM serving.competitive_matchup_source ORDER BY matchup_id, source_id;
SELECT * FROM serving.competitive_product_evaluation ORDER BY evaluation_id;
SELECT * FROM serving.competitive_product_evaluation_spec ORDER BY evaluation_id, spec_label;

/* 10. Partnerships */
SELECT * FROM serving.client_partner ORDER BY partner_name;
SELECT * FROM serving.client_partner_product ORDER BY client_partner_id, partner_product_id;
SELECT * FROM serving.client_partner_relationship ORDER BY client_partner_id, category;
SELECT * FROM serving.competitive_partnership ORDER BY competitor_id, partner_name;
SELECT * FROM serving.competitive_partnership_evidence ORDER BY relationship_id, card_number;
SELECT * FROM serving.competitive_partnership_relationship_detail ORDER BY relationship_id;

/* 11. Projects */
SELECT * FROM ui.ui_project_view_state;
SELECT * FROM ui.ui_project_filter ORDER BY filter_id;
SELECT * FROM ui.ui_project_sequence_option ORDER BY sequence_option_id;
SELECT * FROM ui.ui_project_stage_step ORDER BY stage_order;
SELECT * FROM serving.competitive_project ORDER BY display_order, project_id;
SELECT * FROM serving.competitive_project_stage ORDER BY project_id, stage_order;
SELECT * FROM serving.competitive_project_timeline ORDER BY project_id, display_order;
SELECT * FROM serving.competitive_project_specification ORDER BY project_id, display_order;
SELECT * FROM serving.competitive_project_source ORDER BY project_id, source_id;

/* 12. Geo Footprint */
SELECT * FROM ui.ui_geo_footprint_view_state;
SELECT * FROM ui.ui_geo_country_detail_state;
SELECT * FROM ui.ui_geo_products_supplied_state;
SELECT * FROM ui.ui_geo_product_comparison_state;
SELECT * FROM ui.competitive_geo_filter ORDER BY display_order;
SELECT * FROM serving.competitive_geo_location ORDER BY country_name, location_id;
SELECT * FROM serving.competitive_geo_company_presence ORDER BY display_order, presence_id;
SELECT * FROM serving.competitive_geo_product ORDER BY presence_id, display_order;
SELECT * FROM serving.competitive_geo_product_match ORDER BY match_id;
SELECT * FROM serving.competitive_geo_product_specification ORDER BY match_id, display_order;
SELECT * FROM serving.competitive_geo_product_news ORDER BY geo_product_id, published_date DESC NULLS LAST;
SELECT * FROM serving.competitive_geo_source ORDER BY source_id;

/* 13. Patents */
SELECT * FROM ui.competitive_patent_view_state;
SELECT * FROM serving.competitive_patent_portfolio ORDER BY competitor_id, lens;
SELECT * FROM serving.competitive_patent_filing ORDER BY portfolio_id, filed_date DESC NULLS LAST;
SELECT * FROM serving.competitive_patent_classification ORDER BY portfolio_id, classification_id;

/* 14. Market: tenders, global requirements, and opportunities */
SELECT * FROM ui.market_tenders_view;
SELECT * FROM ui.market_tender_filter ORDER BY filter_id;
SELECT * FROM ui.market_tender_card ORDER BY card_order;
SELECT * FROM serving.market_tender ORDER BY rank_position, closing_date;
SELECT * FROM serving.market_tender_closing_window ORDER BY tender_id;
SELECT * FROM serving.market_tender_requirement ORDER BY tender_id, requirement_id;
SELECT * FROM serving.market_tender_product_match ORDER BY tender_id, tender_match_id;
SELECT * FROM serving.market_tender_product_match_line ORDER BY tender_match_id, match_line_id;
SELECT * FROM serving.market_tender_competitor_fit ORDER BY tender_id, competitor_fit_id;
SELECT * FROM serving.market_tender_fit_assessment ORDER BY tender_id;
SELECT * FROM serving.market_tender_source ORDER BY tender_id, source_id;
SELECT * FROM serving.market_tender_portal ORDER BY portal_id;
SELECT * FROM serving.market_global_requirement ORDER BY requirement_id;
SELECT * FROM serving.market_global_requirement_specification ORDER BY requirement_id, display_order;
SELECT * FROM serving.market_global_requirement_source ORDER BY requirement_id, display_order;
SELECT * FROM serving.market_opportunity ORDER BY opportunity_id;
SELECT * FROM serving.market_opportunity_fit_assessment ORDER BY opportunity_id;
SELECT * FROM serving.market_opportunity_update ORDER BY opportunity_id, update_date DESC NULLS LAST;
SELECT * FROM serving.market_opportunity_source ORDER BY opportunity_id, source_id;

/* 15. Technology */
SELECT * FROM ui.technology_ui_navigation ORDER BY navigation_id;
SELECT * FROM ui.technology_category ORDER BY display_order;
SELECT * FROM ui.technology_category_ui_label ORDER BY tab_number;
SELECT * FROM ui.technology_innovation_card ORDER BY card_order;
SELECT * FROM ui.technology_innovation_category_tab ORDER BY tab_id;
SELECT * FROM serving.technology_category ORDER BY display_order, category_id;
SELECT * FROM serving.technology_category_ui_label ORDER BY category_id, sort_order;
SELECT * FROM serving.technology_innovation ORDER BY sequence_no, innovation_id;
SELECT * FROM serving.technology_innovation_analysis ORDER BY innovation_id, display_order;
SELECT * FROM serving.technology_innovation_company ORDER BY innovation_id, display_order;
SELECT * FROM serving.technology_innovation_source ORDER BY innovation_id, source_id;
SELECT * FROM serving.technology_innovation_status ORDER BY innovation_id, effective_date;
SELECT * FROM serving.technology_metric ORDER BY display_order, metric_id;
SELECT * FROM serving.technology_overview_article ORDER BY article_id;
SELECT * FROM serving.technology_overview_company ORDER BY article_id, display_order;
SELECT * FROM serving.technology_overview_fact ORDER BY article_id, display_order;
SELECT * FROM serving.technology_overview_key_point ORDER BY article_id, display_order;
SELECT * FROM serving.technology_overview_source ORDER BY article_id, source_id;
SELECT * FROM serving.technology_pillar ORDER BY pillar_id;

/* 16. Optional API-side check from DBeaver: verify that backend reads all schemas */
/* GET http://127.0.0.1:8600/api/health
 * GET http://127.0.0.1:8600/api/manifest
 * GET http://127.0.0.1:8600/api/dataset
 *
 * /api/manifest should report 62 ui tables and 89 serving tables.
 * /api/dataset.database should contain the same 151 tables.
 */
