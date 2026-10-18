-- Generated from KSSL_Final_Merged_Database_Schema.docx
-- Creates empty UI and serving tables with documented columns and nullability.
CREATE SCHEMA IF NOT EXISTS "ui";
CREATE SCHEMA IF NOT EXISTS "serving";

CREATE TABLE "ui"."competitive_competitor_moment_level" (
    "display_order" integer NOT NULL,
    "level_code" varchar(40) NOT NULL,
    "level_label" varchar(80) NOT NULL,
    "tag_class" varchar(40) NOT NULL
);

CREATE TABLE "ui"."competitive_competitor_moment_time_window" (
    "day_count" integer,
    "display_order" integer NOT NULL,
    "is_default" boolean NOT NULL,
    "time_window_code" varchar(40) NOT NULL,
    "time_window_id" bigint NOT NULL,
    "time_window_label" varchar(100) NOT NULL
);

CREATE TABLE "ui"."competitive_geo_filter" (
    "display_order" integer NOT NULL,
    "filter_id" bigint NOT NULL,
    "filter_label" varchar(120) NOT NULL,
    "filter_type" varchar(40) NOT NULL,
    "is_active" boolean NOT NULL,
    "option_label" varchar(160),
    "record_count" integer,
    "selected_value" varchar(160)
);

CREATE TABLE "ui"."competitive_metric" (
    "as_of_date" date,
    "display_order" smallint NOT NULL,
    "metric_id" uuid NOT NULL,
    "metric_label" varchar(80) NOT NULL,
    "metric_value" integer
);

CREATE TABLE "ui"."competitive_navigation" (
    "is_active" boolean NOT NULL,
    "record_count" integer,
    "view_key" varchar(50) NOT NULL,
    "view_label" varchar(80) NOT NULL,
    "view_sequence" smallint NOT NULL
);

CREATE TABLE "ui"."competitive_news_view" (
    "category_filter" varchar(80) NOT NULL,
    "competitor_id" uuid NOT NULL,
    "custom_end_date" date,
    "custom_start_date" date,
    "date_filter" varchar(40) NOT NULL,
    "news_view_id" uuid NOT NULL,
    "page_no" integer NOT NULL,
    "page_size" integer NOT NULL,
    "published_range" varchar(40) NOT NULL,
    "search_query" text
);

CREATE TABLE "ui"."competitive_overview_feed" (
    "empty_message" text,
    "feed_id" uuid NOT NULL,
    "local_search_query" text,
    "sequence_mode" varchar(30) NOT NULL,
    "threat_filter" varchar(20) NOT NULL,
    "visible_signal_count" integer
);

CREATE TABLE "ui"."competitive_partnership_graph" (
    "competitor_id" uuid NOT NULL,
    "graph_state_id" uuid NOT NULL,
    "group_by" varchar(30) NOT NULL,
    "legend_type" varchar(60) NOT NULL,
    "partner_card_count" integer,
    "partner_node_click" boolean NOT NULL,
    "relationship_detail_action" boolean NOT NULL,
    "reset_action" boolean NOT NULL,
    "selected_partner_id" uuid,
    "zoom_in_action" boolean NOT NULL,
    "zoom_level" numeric NOT NULL,
    "zoom_out_action" boolean NOT NULL
);

CREATE TABLE "ui"."competitive_patent_view_state" (
    "active_lens" varchar(40) NOT NULL,
    "category_filter" varchar(180),
    "competitor_search_text" text,
    "panel_open" boolean NOT NULL,
    "selected_competitor_id" uuid,
    "selected_technology_area" varchar(180),
    "technology_search_text" text,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."competitive_pillar" (
    "account_label" varchar(100),
    "active_pillar" varchar(30) NOT NULL,
    "brand_name" varchar(100) NOT NULL,
    "global_search_query" text,
    "pillar_id" uuid NOT NULL,
    "print_report_action" boolean NOT NULL
);

CREATE TABLE "ui"."competitive_positioning_tab" (
    "display_order" integer NOT NULL,
    "is_enabled" boolean NOT NULL,
    "tab_code" varchar(40) NOT NULL,
    "tab_id" bigint NOT NULL,
    "tab_label" varchar(120) NOT NULL
);

CREATE TABLE "ui"."competitive_positioning_view_state" (
    "active_tab" varchar(40),
    "compare_product_id" bigint,
    "panel_open" boolean NOT NULL,
    "search_text" text,
    "selected_category" varchar(160),
    "selected_competitor_id" uuid,
    "selected_matchup_id" bigint,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."competitive_product_view_state" (
    "category_filter" varchar(160),
    "company_search_text" text,
    "country_filter" varchar(120),
    "panel_open" boolean NOT NULL,
    "product_search_text" text,
    "revenue_filter" varchar(80),
    "selected_company_id" uuid,
    "selected_news_category" varchar(120),
    "selected_product_id" bigint,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."competitive_profile_view_state" (
    "active_section" varchar(80),
    "news_category" varchar(120),
    "news_range" varchar(30),
    "news_search_text" text,
    "panel_open" boolean NOT NULL,
    "search_text" text,
    "selected_competitor_id" uuid,
    "selected_leader_id" bigint,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."competitive_ui_state" (
    "active_view" varchar(50) NOT NULL,
    "drawer_open" boolean NOT NULL,
    "empty_state_code" varchar(80),
    "is_loading" boolean NOT NULL,
    "last_refreshed_at" timestamp without time zone,
    "render_error_code" varchar(80),
    "render_error_message" text,
    "retry_action" boolean,
    "selected_record_id" uuid,
    "state_id" uuid NOT NULL
);

CREATE TABLE "ui"."market_filter" (
    "filter_id" text NOT NULL,
    "filter_label" text NOT NULL,
    "filter_value" text,
    "option_count" integer,
    "option_label" text,
    "search_query" text,
    "sort_key" text
);

CREATE TABLE "ui"."market_global_requirement_card" (
    "buyer_display" varchar(240),
    "card_id" bigint NOT NULL,
    "category_display" varchar(180),
    "country_display" varchar(160),
    "deadline_display" varchar(120),
    "fit_display" varchar(80),
    "is_selected" boolean NOT NULL,
    "requirement_id" bigint NOT NULL,
    "status_display" varchar(80),
    "title_display" varchar(240) NOT NULL,
    "value_display" varchar(120)
);

CREATE TABLE "ui"."market_global_requirement_detail" (
    "assessment_label" varchar(120) NOT NULL,
    "buyer_label" varchar(100) NOT NULL,
    "close_label" varchar(80) NOT NULL,
    "detail_view_id" bigint NOT NULL,
    "fit_label" varchar(120) NOT NULL,
    "panel_title" varchar(180) NOT NULL,
    "requirement_id" bigint NOT NULL,
    "scope_label" varchar(120) NOT NULL,
    "source_label" varchar(120) NOT NULL,
    "specs_label" varchar(120) NOT NULL
);

CREATE TABLE "ui"."market_global_requirement_filter" (
    "display_order" integer NOT NULL,
    "filter_id" bigint NOT NULL,
    "filter_label" varchar(100) NOT NULL,
    "filter_type" varchar(40) NOT NULL,
    "option_count" integer,
    "search_placeholder" varchar(160),
    "selected_value" varchar(180)
);

CREATE TABLE "ui"."market_global_requirement_view" (
    "assessment_section_label" varchar(120) NOT NULL,
    "category_filter_label" varchar(100) NOT NULL,
    "country_filter_label" varchar(100) NOT NULL,
    "empty_state_text" text,
    "filter_label" varchar(100) NOT NULL,
    "fit_section_label" varchar(120) NOT NULL,
    "page_heading" varchar(180) NOT NULL,
    "panel_subtitle" text,
    "panel_title" varchar(180) NOT NULL,
    "scope_section_label" varchar(120) NOT NULL,
    "sort_label" varchar(160) NOT NULL,
    "source_section_label" varchar(120) NOT NULL,
    "specs_section_label" varchar(120) NOT NULL,
    "view_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_global_requirement_view_state" (
    "category_filter" varchar(180),
    "country_filter" varchar(160),
    "menu_search_text" text,
    "panel_open" boolean NOT NULL,
    "selected_requirement_id" bigint,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_intelligence_tab" (
    "category_filter" text,
    "country_filter" text,
    "is_selected" boolean NOT NULL,
    "record_count" integer NOT NULL,
    "tab_id" text NOT NULL,
    "tab_label" text NOT NULL,
    "tab_order" integer NOT NULL
);

CREATE TABLE "ui"."market_metric" (
    "metric_action" text,
    "metric_id" text NOT NULL,
    "metric_label" text NOT NULL,
    "metric_subtext" text,
    "metric_unit" text,
    "metric_value" text NOT NULL
);

CREATE TABLE "ui"."market_next_move_view" (
    "action_display" text NOT NULL,
    "due_display" varchar(160),
    "move_view_id" bigint NOT NULL,
    "row_id" bigint NOT NULL,
    "row_order" integer NOT NULL,
    "sort_label" varchar(160),
    "tender_display" text,
    "tender_id" bigint,
    "view_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_pillar" (
    "client_name" text NOT NULL,
    "display_name" text NOT NULL,
    "global_search_placeholder" text NOT NULL,
    "market_pillar_id" text NOT NULL,
    "print_report_label" text NOT NULL
);

CREATE TABLE "ui"."market_tender_assessment_view" (
    "assessment_view_id" bigint NOT NULL,
    "closing_summary" varchar(160),
    "competitor_fit_section_label" varchar(160) NOT NULL,
    "details_section_label" varchar(160) NOT NULL,
    "fit_grade_display" varchar(40),
    "fit_rank_display" varchar(80),
    "matched_products_section_label" varchar(160) NOT NULL,
    "notice_ref_display" varchar(160),
    "open_notice_label" varchar(160),
    "panel_subtitle" text,
    "panel_title" text NOT NULL,
    "requirements_section_label" varchar(160) NOT NULL,
    "source_section_label" varchar(160) NOT NULL,
    "tender_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_tender_card" (
    "buyer_display" text,
    "card_id" bigint NOT NULL,
    "card_order" integer NOT NULL,
    "category_display" varchar(160),
    "countdown_display" varchar(160),
    "country_display" varchar(160),
    "deadline_display" varchar(160),
    "fit_grade_display" varchar(40),
    "is_selected" boolean NOT NULL,
    "status_display" varchar(80),
    "tender_id" bigint NOT NULL,
    "title_display" text NOT NULL,
    "value_display" varchar(200),
    "view_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_tender_filter" (
    "filter_id" bigint NOT NULL,
    "filter_label" varchar(80) NOT NULL,
    "filter_type" varchar(40) NOT NULL,
    "is_open" boolean NOT NULL,
    "option_count" integer,
    "search_placeholder" varchar(160),
    "selected_value" varchar(160),
    "view_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_tenders_view" (
    "active_tenders_count" integer,
    "category_filter_label" varchar(80) NOT NULL,
    "category_filter_value" varchar(160),
    "country_filter_label" varchar(80) NOT NULL,
    "country_filter_value" varchar(160),
    "markets_count" integer,
    "page_heading" varchar(160) NOT NULL,
    "selected_tender_id" bigint,
    "sort_label" varchar(160),
    "source_portals_count" integer,
    "value_disclosed_display" varchar(160),
    "view_code" varchar(80) NOT NULL,
    "view_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_top_opportunity_project_row" (
    "buyer_location_display" text,
    "client_model_display" text,
    "fit_grade_display" varchar(40),
    "opportunity_id" bigint,
    "project_title_display" text NOT NULL,
    "rank_position" integer NOT NULL,
    "revenue_display" varchar(160),
    "rival_display" text,
    "row_id" bigint NOT NULL,
    "row_order" integer NOT NULL,
    "view_id" bigint NOT NULL,
    "where_it_stands_display" text
);

CREATE TABLE "ui"."market_top_opportunity_tender_row" (
    "buyer_location_display" text,
    "client_model_display" text,
    "decides_display" varchar(160),
    "fit_grade_display" varchar(40),
    "rank_position" integer NOT NULL,
    "revenue_display" varchar(160),
    "rival_display" text,
    "row_id" bigint NOT NULL,
    "row_order" integer NOT NULL,
    "tender_id" bigint,
    "tender_title_display" text NOT NULL,
    "view_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_top_opportunity_view" (
    "latest_tenders_metric_label" varchar(160) NOT NULL,
    "next_moves_description" text,
    "next_moves_section_label" varchar(160) NOT NULL,
    "page_heading" varchar(160) NOT NULL,
    "perceived_opportunities_metric_label" varchar(160) NOT NULL,
    "projects_description" text,
    "projects_section_label" varchar(160) NOT NULL,
    "sort_logic_label" varchar(160),
    "strong_fits_metric_label" varchar(160) NOT NULL,
    "tender_value_metric_label" varchar(160) NOT NULL,
    "tender_value_metric_note" text,
    "top_tenders_description" text,
    "top_tenders_section_label" varchar(160) NOT NULL,
    "view_code" varchar(80) NOT NULL,
    "view_id" bigint NOT NULL
);

CREATE TABLE "ui"."market_ui_navigation" (
    "account_label" varchar(160),
    "captured_at" timestamp with time zone NOT NULL,
    "global_search_placeholder" varchar(160),
    "navigation_id" bigint NOT NULL,
    "pillar_code" varchar(40) NOT NULL,
    "print_report_enabled" boolean NOT NULL,
    "view_code" varchar(80) NOT NULL,
    "view_label" varchar(160) NOT NULL
);

CREATE TABLE "ui"."market_view" (
    "empty_state_text" text,
    "is_selected" boolean NOT NULL,
    "rail_count" integer,
    "rail_label" text NOT NULL,
    "rail_order" integer NOT NULL,
    "view_id" text NOT NULL,
    "view_title" text NOT NULL
);

CREATE TABLE "ui"."technology_category" (
    "category_description" text,
    "category_id" text NOT NULL PRIMARY KEY,
    "category_name" text NOT NULL,
    "display_order" smallint NOT NULL,
    "innovation_count" integer,
    "tab_number" smallint NOT NULL
);

CREATE TABLE "ui"."technology_category_ui_label" (
    "database_category_id" varchar(80) NOT NULL,
    "tab_number" smallint NOT NULL,
    "ui_name" varchar(120) NOT NULL
);

CREATE TABLE "ui"."technology_innovation_card" (
    "card_id" bigint NOT NULL,
    "card_order" integer NOT NULL,
    "client_position_display" varchar(120),
    "company_display" varchar(240),
    "horizon_display" varchar(80),
    "innovation_id" bigint NOT NULL,
    "is_selected" boolean NOT NULL,
    "maturity_display" varchar(100),
    "summary_display" text,
    "title_display" text NOT NULL,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."technology_innovation_category_tab" (
    "category_id" bigint NOT NULL,
    "innovation_count" integer,
    "is_selected" boolean NOT NULL,
    "tab_id" bigint NOT NULL,
    "tab_label" varchar(200) NOT NULL,
    "tab_number" varchar(20) NOT NULL,
    "tab_order" integer NOT NULL,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."technology_innovation_detail_panel" (
    "assessment_badge" varchar(80),
    "background_text" text,
    "client_position_display" varchar(120),
    "close_label" varchar(40) NOT NULL,
    "horizon_display" varchar(80),
    "innovation_id" bigint NOT NULL,
    "maturity_display" varchar(100),
    "panel_id" bigint NOT NULL,
    "panel_title" text NOT NULL,
    "source_section_label" varchar(160) NOT NULL,
    "whats_new_text" text,
    "why_matters_text" text,
    "why_position_text" text
);

CREATE TABLE "ui"."technology_innovation_view" (
    "empty_state_text" text,
    "list_heading" varchar(200),
    "page_heading" varchar(160) NOT NULL,
    "selected_category_id" bigint,
    "selected_innovation_id" bigint,
    "total_innovations" integer,
    "view_id" bigint NOT NULL,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."technology_metric" (
    "display_order" smallint NOT NULL,
    "metric_action" text,
    "metric_id" bigint NOT NULL PRIMARY KEY,
    "metric_key" text NOT NULL,
    "metric_label" text NOT NULL,
    "metric_value" integer NOT NULL,
    "pillar_id" text NOT NULL
);

CREATE TABLE "ui"."technology_overview_detail_panel" (
    "article_id" bigint NOT NULL,
    "at_a_glance_label" varchar(160) NOT NULL,
    "close_label" varchar(40) NOT NULL,
    "key_points_label" varchar(160),
    "panel_id" bigint NOT NULL,
    "panel_title" text NOT NULL,
    "provenance_label" varchar(160),
    "source_label" varchar(160) NOT NULL,
    "what_article_says_label" varchar(160) NOT NULL
);

CREATE TABLE "ui"."technology_overview_detail_section" (
    "panel_id" bigint NOT NULL,
    "section_code" varchar(80) NOT NULL,
    "section_id" bigint NOT NULL,
    "section_label" varchar(160) NOT NULL,
    "section_order" integer NOT NULL,
    "source_id" bigint,
    "value_text" text
);

CREATE TABLE "ui"."technology_overview_filter" (
    "filter_label" varchar(160),
    "filter_state_id" bigint NOT NULL,
    "filter_type" varchar(40) NOT NULL,
    "is_active" boolean NOT NULL,
    "option_values" jsonb,
    "selected_value" text,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."technology_overview_metric_card" (
    "is_clickable" boolean NOT NULL,
    "metric_card_id" bigint NOT NULL,
    "metric_key" varchar(80) NOT NULL,
    "metric_label" varchar(160) NOT NULL,
    "metric_order" integer NOT NULL,
    "metric_unit" varchar(80),
    "metric_value" numeric,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."technology_overview_signal_card" (
    "article_id" bigint NOT NULL,
    "card_id" bigint NOT NULL,
    "classification_display" varchar(80),
    "is_selected" boolean NOT NULL,
    "narrative_display" text,
    "published_date_display" varchar(80),
    "rank_position" integer NOT NULL,
    "title_display" text NOT NULL,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."technology_overview_view" (
    "page_heading" varchar(160) NOT NULL,
    "search_placeholder" varchar(160),
    "selected_article_id" bigint,
    "sequence_label" varchar(80),
    "sequence_options" jsonb,
    "sequence_value" varchar(80),
    "showing_from" integer,
    "showing_to" integer,
    "total_signals" integer,
    "view_id" bigint NOT NULL,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."technology_pillar" (
    "client_name" text NOT NULL,
    "innovation_title" text NOT NULL,
    "knowledge_title" text NOT NULL,
    "pillar_id" text NOT NULL,
    "pillar_name" text NOT NULL,
    "print_report_label" text NOT NULL
);

CREATE TABLE "ui"."technology_print_report_control" (
    "is_enabled" boolean NOT NULL,
    "label" varchar(80) NOT NULL,
    "pillar_code" varchar(40) NOT NULL,
    "report_control_id" bigint NOT NULL,
    "view_code" varchar(80) NOT NULL
);

CREATE TABLE "ui"."technology_ui_navigation" (
    "account_label" varchar(160),
    "ask_parallax_enabled" boolean NOT NULL,
    "captured_at" timestamp with time zone NOT NULL,
    "global_search_placeholder" varchar(160),
    "navigation_id" bigint NOT NULL,
    "page_heading" varchar(160) NOT NULL,
    "pillar_code" varchar(40) NOT NULL,
    "print_report_enabled" boolean NOT NULL,
    "view_code" varchar(80) NOT NULL
);

CREATE TABLE "ui"."technology_ui_view" (
    "display_order" smallint NOT NULL,
    "is_active" boolean NOT NULL,
    "page_heading" text NOT NULL,
    "pillar_id" text NOT NULL,
    "rail_count" integer,
    "record_count" integer,
    "route_hash" varchar(160) NOT NULL,
    "search_placeholder" text,
    "sequence_default" text,
    "sequence_label" text,
    "sequence_options" jsonb,
    "view_code" varchar(80) NOT NULL,
    "view_id" bigint NOT NULL,
    "view_key" text NOT NULL,
    "view_label" varchar(160) NOT NULL,
    "view_name" text NOT NULL,
    "view_number" varchar(20)
);

CREATE TABLE "ui"."ui_competitor_moment_metric" (
    "display_order" integer,
    "metric_id" bigint NOT NULL,
    "metric_label" varchar(128),
    "metric_unit" varchar(32),
    "metric_value" numeric,
    "view_state_id" bigint
);

CREATE TABLE "ui"."ui_competitor_moment_view_state" (
    "from_date" date,
    "panel_open" boolean,
    "search_text" text,
    "selected_competitor_id" bigint,
    "selected_moment_id" bigint,
    "sequence" varchar(64),
    "time_window" varchar(16),
    "to_date" date,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."ui_geo_country_detail_state" (
    "active_competitor_count" integer,
    "category_only_competitor_count" integer,
    "kssl_present" boolean,
    "location_id" bigint,
    "rating_matched_competitor_count" integer,
    "selected_presence_id" bigint,
    "state_id" bigint NOT NULL
);

CREATE TABLE "ui"."ui_geo_footprint_view_state" (
    "map_center_latitude" numeric,
    "map_center_longitude" numeric,
    "map_zoom" integer,
    "panel_open" boolean,
    "popup_location_id" bigint,
    "selected_competitor_id" bigint,
    "selected_location_id" bigint,
    "selected_presence_id" bigint,
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "ui"."ui_geo_product_comparison_state" (
    "comparison_state_id" bigint NOT NULL,
    "comparison_title" varchar(256),
    "competitor_score" numeric,
    "decision_level" integer,
    "evaluation_label" varchar(128),
    "kssl_score" numeric,
    "match_basis" text,
    "match_id" bigint,
    "rating_delta" numeric
);

CREATE TABLE "ui"."ui_geo_products_supplied_state" (
    "competitor_id" bigint,
    "export_supply_count" integer,
    "location_id" bigint,
    "matched_model_count" integer,
    "product_count" integer,
    "sales_service_site_count" integer,
    "selected_geo_product_id" bigint,
    "state_id" bigint NOT NULL
);

CREATE TABLE "ui"."ui_project_filter" (
    "display_order" integer NOT NULL,
    "filter_code" varchar(50) NOT NULL,
    "filter_id" bigint NOT NULL,
    "filter_label" varchar(120) NOT NULL,
    "is_default" boolean NOT NULL
);

CREATE TABLE "ui"."ui_project_metric" (
    "display_order" integer,
    "metric_id" bigint NOT NULL,
    "metric_label" varchar(128),
    "metric_unit" varchar(32),
    "metric_value" numeric,
    "view_state_id" bigint
);

CREATE TABLE "ui"."ui_project_sequence_option" (
    "display_order" integer NOT NULL,
    "is_default" boolean NOT NULL,
    "sequence_code" varchar(40) NOT NULL,
    "sequence_label" varchar(120) NOT NULL,
    "sequence_option_id" bigint NOT NULL
);

CREATE TABLE "ui"."ui_project_stage_step" (
    "stage_name" varchar(120) NOT NULL,
    "stage_order" integer NOT NULL,
    "stage_step_id" bigint NOT NULL
);

CREATE TABLE "ui"."ui_project_view_state" (
    "active_filter" varchar(50),
    "competitor_search_text" text,
    "geography_scope" varchar(32),
    "panel_open" boolean,
    "project_search_text" text,
    "search_text" text,
    "selected_competitor_id" bigint,
    "selected_project_id" bigint,
    "selected_sequence" varchar(40),
    "sequence" varchar(64),
    "view_state_id" bigint NOT NULL
);

CREATE TABLE "serving"."client_account" (
    "account_status" varchar(32),
    "brand_name" varchar(255),
    "client_id" bigint NOT NULL,
    "client_name" varchar(255) NOT NULL,
    "country" varchar(128),
    "created_at" timestamp with time zone NOT NULL,
    "headquarters" varchar(255),
    "industry_sector" varchar(128),
    "legal_name" varchar(255),
    "strategic_positioning" text,
    "updated_at" timestamp with time zone NOT NULL
);

CREATE TABLE "serving"."client_partner" (
    "client_id" bigint NOT NULL,
    "client_partner_id" bigint NOT NULL,
    "country" varchar(128),
    "created_at" timestamp with time zone NOT NULL,
    "legal_name" varchar(255),
    "partner_name" varchar(255) NOT NULL,
    "partner_type" varchar(128),
    "region" varchar(128),
    "relationship_confidence" varchar(32),
    "relationship_scope" text,
    "relationship_start_date" date,
    "relationship_status" varchar(64),
    "source_id" bigint,
    "strategic_role" text,
    "updated_at" timestamp with time zone NOT NULL
);

CREATE TABLE "serving"."client_partner_product" (
    "activity_type" varchar(128),
    "client_partner_id" bigint NOT NULL,
    "client_product_id" bigint,
    "market" varchar(128),
    "partner_product_id" bigint NOT NULL,
    "scope" text,
    "source_id" bigint,
    "status" varchar(64)
);

CREATE TABLE "serving"."client_partner_relationship" (
    "category" varchar(128),
    "client_partner_id" bigint NOT NULL,
    "competitor_overlap" boolean,
    "description" text,
    "end_date" date,
    "kssl_read" text,
    "relationship_id" bigint NOT NULL,
    "relationship_type" varchar(128) NOT NULL,
    "source_id" bigint,
    "start_date" date,
    "status" varchar(64),
    "territory" varchar(255)
);

CREATE TABLE "serving"."client_partner_source" (
    "as_of_date" date,
    "client_partner_id" bigint NOT NULL,
    "confidence" varchar(32),
    "relationship_id" bigint,
    "source_id" bigint NOT NULL,
    "source_label" varchar(255) NOT NULL,
    "source_note" text,
    "source_type" varchar(64),
    "source_url" text NOT NULL
);

CREATE TABLE "serving"."client_product" (
    "category" varchar(128),
    "client_id" bigint NOT NULL,
    "client_product_id" bigint NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "frequency_hz" numeric,
    "fuel_type" varchar(64),
    "image_url" text,
    "market_availability" text,
    "model_code" varchar(128),
    "prime_rating" text,
    "product_family" varchar(128),
    "product_name" varchar(255) NOT NULL,
    "rated_power_unit" varchar(16),
    "rated_power_value" numeric,
    "source_id" bigint,
    "standby_rating" text,
    "status" varchar(64),
    "subcategory" varchar(128),
    "technology" varchar(128),
    "updated_at" timestamp with time zone NOT NULL
);

CREATE TABLE "serving"."client_product_program" (
    "client_product_id" bigint NOT NULL,
    "description" text,
    "end_date" date,
    "owner" varchar(255),
    "program_id" bigint NOT NULL,
    "program_name" varchar(255) NOT NULL,
    "program_type" varchar(64),
    "start_date" date,
    "status" varchar(64)
);

CREATE TABLE "serving"."client_product_source" (
    "client_product_id" bigint NOT NULL,
    "published_date" date,
    "source_id" bigint NOT NULL,
    "source_label" varchar(255) NOT NULL,
    "source_type" varchar(64),
    "source_url" text NOT NULL
);

CREATE TABLE "serving"."client_product_specification" (
    "client_product_id" bigint NOT NULL,
    "display_order" integer NOT NULL,
    "source_id" bigint,
    "spec_group" varchar(128),
    "spec_name" varchar(255) NOT NULL,
    "specification_id" bigint NOT NULL,
    "unit" varchar(32),
    "value_numeric" numeric,
    "value_text" text
);

CREATE TABLE "serving"."competitive_competitor" (
    "annual_revenue" numeric,
    "competitor_id" uuid NOT NULL,
    "display_name" varchar(200) NOT NULL,
    "employee_count" integer,
    "global_locations" text,
    "headquarters" varchar(250),
    "industry_sector" varchar(200),
    "legal_name" varchar(250),
    "origin_country" varchar(100),
    "parallax_read" text,
    "revenue_currency" char(3),
    "revenue_tier" varchar(50),
    "short_name" varchar(120),
    "starting_year" smallint,
    "strategic_positioning" text,
    "threat_level" varchar(20)
);

CREATE TABLE "serving"."competitive_competitor_location" (
    "competitor_id" uuid NOT NULL,
    "country" varchar(100),
    "location_id" uuid NOT NULL,
    "location_name" varchar(250) NOT NULL,
    "location_type" varchar(40) NOT NULL,
    "source_url" text
);

CREATE TABLE "serving"."competitive_competitor_moment" (
    "card_summary" text,
    "category" varchar(64),
    "company_display" varchar(240),
    "competitor_id" bigint,
    "countries" text,
    "country_name" varchar(160),
    "description" text,
    "display_order" integer,
    "grade" varchar(32),
    "image_url" text,
    "kssl_analysis" text,
    "moment_id" bigint NOT NULL,
    "movement_date" date,
    "program_name" varchar(240),
    "region" varchar(128),
    "source_domain" varchar(255),
    "source_label" varchar(240),
    "source_url" text,
    "title" text,
    "what_happened" text
);

CREATE TABLE "serving"."competitive_competitor_moment_analysis" (
    "analysis_id" bigint NOT NULL,
    "analysis_text" text,
    "display_order" integer,
    "moment_id" bigint,
    "view_name" varchar(128)
);

CREATE TABLE "serving"."competitive_competitor_moment_source" (
    "moment_id" bigint,
    "publisher" varchar(255),
    "source_domain" varchar(255),
    "source_id" bigint NOT NULL,
    "source_type" varchar(64),
    "source_url" text
);

CREATE TABLE "serving"."competitive_competitor_swot" (
    "competitor_id" uuid NOT NULL,
    "empty_message" text,
    "record_count" integer NOT NULL,
    "statement" text,
    "swot_id" uuid NOT NULL,
    "swot_type" varchar(20) NOT NULL
);

CREATE TABLE "serving"."competitive_geo_company_presence" (
    "activity_type" text,
    "client_id" bigint,
    "company_name" varchar(255),
    "company_role" varchar(30) NOT NULL,
    "competitor_id" bigint,
    "display_order" integer,
    "location_id" bigint,
    "matched_ranges" text,
    "overlap_status" varchar(32),
    "presence_id" bigint NOT NULL,
    "presence_status" varchar(64),
    "product_count" integer,
    "products_summary" text,
    "relationship_text" text
);

CREATE TABLE "serving"."competitive_geo_location" (
    "country_name" varchar(128),
    "kssl_presence_summary" text,
    "latitude" numeric,
    "location_id" bigint NOT NULL,
    "longitude" numeric,
    "map_label" varchar(128),
    "presence_types" text,
    "region_name" varchar(128)
);

CREATE TABLE "serving"."competitive_geo_product" (
    "activity_type" text,
    "display_order" integer,
    "frequency_hz" numeric,
    "fuel_type" varchar(64),
    "geo_product_id" bigint NOT NULL,
    "presence_id" bigint,
    "product_name" varchar(255),
    "product_range" varchar(128),
    "quantity" text,
    "rated_power_unit" varchar(16),
    "rated_power_value" numeric,
    "record_note" text,
    "reported_value" text,
    "since_date" date
);

CREATE TABLE "serving"."competitive_geo_product_match" (
    "comparison_title" varchar(255),
    "competitor_score" numeric,
    "decision_level" integer,
    "evaluation_label" varchar(128),
    "geo_product_id" bigint,
    "kssl_counter_label" varchar(255),
    "kssl_product_id" bigint,
    "kssl_score" numeric,
    "match_basis" text,
    "match_id" bigint NOT NULL,
    "match_status" varchar(64),
    "qualitative_summary" text,
    "rating_delta" numeric
);

CREATE TABLE "serving"."competitive_geo_product_news" (
    "article_url" text,
    "display_order" integer NOT NULL,
    "geo_product_id" bigint NOT NULL,
    "headline" text NOT NULL,
    "news_id" bigint NOT NULL,
    "published_date" date,
    "publisher" varchar(240),
    "source_id" bigint
);

CREATE TABLE "serving"."competitive_geo_product_specification" (
    "better_side" varchar(32),
    "comparison_spec_id" bigint NOT NULL,
    "competitor_value" text,
    "display_order" integer,
    "gap_value" text,
    "kssl_value" text,
    "match_id" bigint,
    "spec_group" varchar(128),
    "spec_name" varchar(255),
    "unit" varchar(32)
);

CREATE TABLE "serving"."competitive_geo_source" (
    "geo_product_id" bigint,
    "location_id" bigint,
    "match_id" bigint,
    "source_id" bigint NOT NULL,
    "source_label" varchar(255),
    "source_type" varchar(64),
    "source_url" text
);

CREATE TABLE "serving"."competitive_leader" (
    "avatar_initials" varchar(10),
    "competitor_id" uuid NOT NULL,
    "detail_route" varchar(120),
    "full_name" varchar(200) NOT NULL,
    "leader_id" uuid NOT NULL,
    "organization" varchar(200),
    "role_source_url" text,
    "role_title" varchar(200)
);

CREATE TABLE "serving"."competitive_leader_record" (
    "empty_message" text,
    "end_date" date,
    "headline" varchar(300),
    "institution_or_employer" varchar(250),
    "leader_id" uuid NOT NULL,
    "record_id" uuid NOT NULL,
    "record_type" varchar(30) NOT NULL,
    "role_or_degree" varchar(250),
    "source_url" text,
    "start_date" date
);

CREATE TABLE "serving"."competitive_matchup" (
    "category_code" varchar(160) NOT NULL,
    "client_product_id" bigint,
    "client_product_name" varchar(240) NOT NULL,
    "comparable_spec_count" integer,
    "competitor_country" varchar(120),
    "competitor_id" uuid,
    "competitor_name" varchar(240) NOT NULL,
    "competitor_product_id" bigint,
    "competitor_product_name" varchar(240) NOT NULL,
    "created_at" timestamptz NOT NULL,
    "decision_level" integer,
    "edge_score" numeric,
    "match_basis" text,
    "matchup_id" bigint NOT NULL,
    "sourced_spec_count" integer,
    "updated_at" timestamptz NOT NULL,
    "verdict" text,
    "verdict_headline" varchar(240)
);

CREATE TABLE "serving"."competitive_matchup_advantage" (
    "advantage_id" bigint NOT NULL,
    "advantage_text" text NOT NULL,
    "display_order" integer NOT NULL,
    "matchup_id" bigint NOT NULL,
    "side" varchar(30) NOT NULL,
    "source_id" bigint
);

CREATE TABLE "serving"."competitive_matchup_source" (
    "matchup_id" bigint NOT NULL,
    "published_date" date,
    "source_id" bigint NOT NULL,
    "source_label" varchar(240) NOT NULL,
    "source_note" text,
    "source_type" varchar(80),
    "source_url" text NOT NULL
);

CREATE TABLE "serving"."competitive_matchup_specification" (
    "better_side" varchar(30),
    "client_value_numeric" numeric,
    "client_value_text" text,
    "comparability_state" varchar(40),
    "comparison_specification_id" bigint NOT NULL,
    "competitor_value_numeric" numeric,
    "competitor_value_text" text,
    "display_order" integer NOT NULL,
    "gap_value" numeric,
    "matchup_id" bigint NOT NULL,
    "spec_group" varchar(120),
    "spec_label" varchar(180) NOT NULL,
    "unit" varchar(60)
);

CREATE TABLE "serving"."competitive_news_article" (
    "article_id" uuid NOT NULL,
    "article_url" text,
    "category" varchar(80),
    "competitor_id" uuid,
    "headline" varchar(300) NOT NULL,
    "image_url" text,
    "published_date" date,
    "publisher" varchar(200)
);

CREATE TABLE "serving"."competitive_partnership" (
    "as_of_date" date,
    "competitor_id" uuid NOT NULL,
    "description" text,
    "mapped_partner_count" integer,
    "partner_id" uuid NOT NULL,
    "partner_name" varchar(250) NOT NULL,
    "partner_type" varchar(60),
    "region" varchar(100),
    "relationship_confidence" varchar(40),
    "relationship_id" uuid NOT NULL,
    "relationship_scope" text,
    "source_count" integer,
    "source_note" text,
    "view_relationship_action" boolean NOT NULL
);

CREATE TABLE "serving"."competitive_partnership_evidence" (
    "as_of_date" date,
    "basis_for_type" text,
    "card_number" smallint NOT NULL,
    "confidence" varchar(40),
    "evidence_card_id" uuid NOT NULL,
    "evidence_text" text,
    "evidence_type" varchar(80),
    "relationship_id" uuid NOT NULL,
    "relationship_label" varchar(150),
    "scope" text,
    "source_article_title" varchar(300),
    "source_article_url" text,
    "source_note" text,
    "source_publisher" varchar(200),
    "source_type" varchar(80),
    "source_url" text
);

CREATE TABLE "serving"."competitive_partnership_relationship_detail" (
    "back_action" boolean NOT NULL,
    "basis_for_type" text,
    "confidence" varchar(40),
    "detail_id" uuid NOT NULL,
    "detail_label" varchar(150),
    "image_state" varchar(60),
    "relationship_id" uuid NOT NULL,
    "relationship_title" varchar(300) NOT NULL,
    "scope" text,
    "selected_card_id" uuid NOT NULL,
    "source_article_url" text,
    "source_note" text,
    "source_publisher_label" varchar(200),
    "stated_as_of" date,
    "type" varchar(100)
);

CREATE TABLE "serving"."competitive_patent_classification" (
    "category_label" varchar(150) NOT NULL,
    "classification_id" uuid NOT NULL,
    "filing_count" integer,
    "lens" varchar(30) NOT NULL,
    "portfolio_id" uuid NOT NULL
);

CREATE TABLE "serving"."competitive_patent_filing" (
    "classification_code" varchar(80),
    "classification_text" text,
    "filed_date" date,
    "filing_id" uuid NOT NULL,
    "jurisdiction" varchar(20),
    "patent_url" text,
    "portfolio_id" uuid NOT NULL,
    "publication_number" varchar(80),
    "status" varchar(50),
    "title" varchar(400) NOT NULL
);

CREATE TABLE "serving"."competitive_patent_portfolio" (
    "competitor_id" uuid NOT NULL,
    "competitor_search_query" text,
    "data_source_note" text,
    "empty_message" text,
    "filing_count" integer NOT NULL,
    "grant_status_state" varchar(30) NOT NULL,
    "granted_count" integer,
    "lens" varchar(30) NOT NULL,
    "pending_count" integer,
    "portfolio_id" uuid NOT NULL,
    "status_note" text
);

CREATE TABLE "serving"."competitive_product" (
    "category" varchar(100) NOT NULL,
    "category_count" integer,
    "category_filter" varchar(100) NOT NULL,
    "competitor_id" uuid NOT NULL,
    "country" varchar(100),
    "image_source_url" text,
    "image_url" text,
    "is_collapsed" boolean NOT NULL,
    "product_id" uuid NOT NULL,
    "product_name" varchar(250) NOT NULL,
    "product_search_query" text
);

CREATE TABLE "serving"."competitive_product_evaluation" (
    "analytics_tab" varchar(30) NOT NULL,
    "category" varchar(100) NOT NULL,
    "comparable_value_count" integer,
    "compare_action_enabled" boolean NOT NULL,
    "competitor_analytics" json,
    "competitor_country" varchar(100),
    "competitor_name" varchar(200),
    "competitor_product_id" uuid NOT NULL,
    "competitor_product_name" varchar(250) NOT NULL,
    "evaluation_id" uuid NOT NULL,
    "kssl_analytics" json,
    "kssl_product_id" uuid NOT NULL,
    "kssl_product_name" varchar(250) NOT NULL,
    "sourced_value_count" integer,
    "verdict" text
);

CREATE TABLE "serving"."competitive_product_evaluation_spec" (
    "comparability_state" varchar(30) NOT NULL,
    "comparison_spec_id" uuid NOT NULL,
    "competitor_value" text,
    "evaluation_id" uuid NOT NULL,
    "kssl_value" text,
    "source_urls" json,
    "spec_label" varchar(150) NOT NULL,
    "unit" varchar(40)
);

CREATE TABLE "serving"."competitive_product_news" (
    "article_url" text,
    "category" varchar(80),
    "comparison_reason" text,
    "headline" varchar(300) NOT NULL,
    "matchup_id" uuid,
    "product_id" uuid NOT NULL,
    "product_news_id" uuid NOT NULL,
    "published_date" date,
    "publisher" varchar(200),
    "side_a_product_id" uuid,
    "side_b_product_id" uuid
);

CREATE TABLE "serving"."competitive_product_program" (
    "authority" varchar(200),
    "description" text,
    "product_id" uuid NOT NULL,
    "program_date" date,
    "program_id" uuid NOT NULL,
    "program_title" varchar(250) NOT NULL,
    "status" varchar(80),
    "status_color" varchar(30)
);

CREATE TABLE "serving"."competitive_product_specification" (
    "product_id" uuid NOT NULL,
    "source_count" integer,
    "source_url" text,
    "spec_id" uuid NOT NULL,
    "spec_label" varchar(150) NOT NULL,
    "spec_value" text,
    "unit" varchar(40)
);

CREATE TABLE "serving"."competitive_project" (
    "assessment_read" text,
    "assessment_stance" varchar(40),
    "card_summary" text,
    "company_display" varchar(240),
    "competitor_id" bigint,
    "customer" text,
    "display_order" integer,
    "estimated_value" numeric,
    "grade" varchar(32),
    "kind" varchar(64),
    "kssl_advantage" text,
    "kssl_platform" varchar(240),
    "latest_milestone" text,
    "latest_milestone_date" date,
    "location" text,
    "project_id" bigint NOT NULL,
    "project_title" text,
    "region" varchar(128),
    "researched_as_of" date,
    "stage" varchar(32),
    "stage_note" text,
    "strategic_assessment" text,
    "what_the_project_is" text
);

CREATE TABLE "serving"."competitive_project_source" (
    "project_id" bigint,
    "source_domain" varchar(255),
    "source_id" bigint NOT NULL,
    "source_label" varchar(240),
    "source_type" varchar(64),
    "source_url" text
);

CREATE TABLE "serving"."competitive_project_specification" (
    "display_order" integer,
    "project_id" bigint,
    "project_spec_id" bigint NOT NULL,
    "spec_label" varchar(128),
    "spec_value" text,
    "unit" varchar(32)
);

CREATE TABLE "serving"."competitive_project_stage" (
    "is_current" boolean,
    "project_id" bigint,
    "project_stage_id" bigint NOT NULL,
    "stage_name" varchar(32),
    "stage_order" integer
);

CREATE TABLE "serving"."competitive_project_timeline" (
    "display_order" integer,
    "event_date" date,
    "event_description" text,
    "event_title" text,
    "is_expected" boolean,
    "project_id" bigint,
    "timeline_id" bigint NOT NULL
);

CREATE TABLE "serving"."competitive_signal" (
    "category" varchar(100),
    "classification" varchar(20) NOT NULL,
    "company_id" uuid,
    "event_date" date,
    "sequence_no" integer NOT NULL,
    "signal_id" uuid NOT NULL,
    "summary" text,
    "thumbnail_url" text,
    "title" varchar(300) NOT NULL
);

CREATE TABLE "serving"."competitive_signal_detail" (
    "ask_box_query" text,
    "drawer_title" varchar(300) NOT NULL,
    "impact_eyebrow" varchar(120),
    "provenance" text,
    "signal_id" uuid NOT NULL,
    "source_name" varchar(200),
    "source_url" text,
    "what_article_says" text,
    "why_it_matters" text
);

CREATE TABLE "serving"."competitive_signal_evidence" (
    "display_order" smallint NOT NULL,
    "evidence_group" varchar(30) NOT NULL,
    "evidence_id" uuid NOT NULL,
    "label" varchar(120) NOT NULL,
    "quote" text,
    "signal_id" uuid NOT NULL,
    "source_url" text,
    "value" text
);

CREATE TABLE "serving"."competitive_stock_quote" (
    "availability_state" varchar(30) NOT NULL,
    "competitor_id" uuid NOT NULL,
    "currency" char(3),
    "empty_message" text,
    "exchange" varchar(80),
    "latest_price" numeric,
    "quote_timestamp" timestamp without time zone,
    "stock_id" uuid NOT NULL,
    "ticker" varchar(40)
);

CREATE TABLE "serving"."competitive_stock_series" (
    "close_price" numeric,
    "move_direction" varchar(10),
    "move_news_article_id" uuid,
    "move_percent" numeric,
    "period_end" date,
    "period_start" date,
    "range_key" varchar(20) NOT NULL,
    "range_label" varchar(80),
    "range_value" varchar(120),
    "series_id" uuid NOT NULL,
    "stock_id" uuid NOT NULL,
    "volume" bigint
);

CREATE TABLE "serving"."market_category_summary" (
    "active_tenders_count" integer,
    "as_of_date" date,
    "category_id" bigint,
    "country_code" char(2),
    "perceived_opportunity_count" integer,
    "source_portals_count" integer,
    "strong_fit_count" integer,
    "summary_id" bigint NOT NULL,
    "value_disclosed_count" integer
);

CREATE TABLE "serving"."market_filter_option" (
    "filter_type" varchar(40) NOT NULL,
    "is_active" boolean NOT NULL,
    "option_code" varchar(80),
    "option_id" bigint NOT NULL,
    "option_label" varchar(240) NOT NULL,
    "record_count" integer,
    "sort_order" integer
);

CREATE TABLE "serving"."market_global_requirement" (
    "buyer_name" varchar(240),
    "category" text,
    "country_name" varchar(160),
    "days_remaining" integer,
    "deadline" varchar(120),
    "description" text,
    "empty_state_message" text NOT NULL,
    "kssl_fit" varchar(40),
    "kssl_model" varchar(240),
    "region" text,
    "requirement_id" text NOT NULL,
    "status" text,
    "strategic_assessment" text,
    "title" text,
    "value_text" varchar(120)
);

CREATE TABLE "serving"."market_global_requirement_source" (
    "display_order" integer NOT NULL,
    "requirement_id" bigint NOT NULL,
    "requirement_source_id" bigint NOT NULL,
    "source_label" varchar(240) NOT NULL,
    "source_type" varchar(80),
    "source_url" text
);

CREATE TABLE "serving"."market_global_requirement_specification" (
    "display_order" integer NOT NULL,
    "requirement_id" bigint NOT NULL,
    "requirement_spec_id" bigint NOT NULL,
    "spec_label" varchar(180) NOT NULL,
    "spec_value" text
);

CREATE TABLE "serving"."market_next_move" (
    "action_text" text NOT NULL,
    "days_remaining" integer,
    "due_date" date,
    "due_text" varchar(160),
    "next_move_id" bigint NOT NULL,
    "opportunity_id" bigint,
    "priority" varchar(40),
    "sequence" integer,
    "status" varchar(40),
    "tender_id" bigint,
    "tender_title" varchar(240)
);

CREATE TABLE "serving"."market_opportunity" (
    "as_of_date" date,
    "buyer_name" text,
    "category_id" bigint,
    "contractor_name" text,
    "country_code" char(2),
    "created_at" timestamp with time zone NOT NULL,
    "current_status" varchar(80),
    "description" text,
    "latest_milestone" text,
    "location_text" text,
    "opportunity_id" bigint NOT NULL,
    "opportunity_kind" varchar(40) NOT NULL,
    "scope_text" text,
    "stage" varchar(80),
    "title" text NOT NULL,
    "updated_at" timestamp with time zone NOT NULL
);

CREATE TABLE "serving"."market_opportunity_fit_assessment" (
    "assessed_at" timestamp with time zone,
    "assessment_id" bigint NOT NULL,
    "client_model_display" text,
    "client_product_id" bigint,
    "fit_grade" varchar(40),
    "fit_score" numeric,
    "opportunity_id" bigint NOT NULL,
    "rationale" text,
    "revenue_currency" char(3),
    "revenue_display" varchar(160),
    "revenue_estimate_amount" numeric,
    "rival_name" varchar(240),
    "rival_product_display" text
);

CREATE TABLE "serving"."market_opportunity_source" (
    "confidence" varchar(40),
    "opportunity_id" bigint NOT NULL,
    "publisher" varchar(240),
    "source_date" date,
    "source_id" bigint NOT NULL,
    "source_title" text,
    "source_type" varchar(80),
    "source_url" text
);

CREATE TABLE "serving"."market_opportunity_update" (
    "confidence" varchar(40),
    "headline" varchar(240),
    "narrative" text,
    "opportunity_id" bigint NOT NULL,
    "source_id" bigint,
    "update_date" date,
    "update_id" bigint NOT NULL,
    "update_type" varchar(80) NOT NULL
);

CREATE TABLE "serving"."market_tender" (
    "buyer_name" text,
    "buyer_organization_id" bigint,
    "category_id" bigint,
    "category_text" varchar(180),
    "closing_date" date,
    "country_code" char(2),
    "country_name" varchar(160),
    "created_at" timestamp with time zone NOT NULL,
    "days_remaining" integer,
    "deadline_text" varchar(120),
    "description" text,
    "expected_revenue_text" varchar(120),
    "frequency" varchar(80),
    "is_live" boolean,
    "issuer_display" varchar(240),
    "kssl_fit" varchar(40),
    "kssl_model" varchar(240),
    "latest_milestone" text,
    "lean_code" varchar(40),
    "lean_text" text,
    "local_presence_requirement" text,
    "notice_reference" varchar(160),
    "published_date" date,
    "quantity" numeric,
    "quantity_unit" varchar(80),
    "rank_position" integer,
    "registration_requirement" text,
    "source_url" text,
    "status" varchar(40) NOT NULL,
    "submission_method" text,
    "tender_id" bigint NOT NULL,
    "tender_number" varchar(160),
    "title" text NOT NULL,
    "title_localized" text,
    "updated_at" timestamp with time zone NOT NULL,
    "url_kind" varchar(40),
    "value_amount" numeric,
    "value_currency" char(3),
    "value_text" text
);

CREATE TABLE "serving"."market_tender_closing_window" (
    "as_of_date" date NOT NULL,
    "closing_date" date,
    "closing_window_id" bigint NOT NULL,
    "days_remaining" integer,
    "extension_checked_at" timestamp with time zone,
    "is_extension_confirmed" boolean,
    "milestone_text" text,
    "published_date" date,
    "status" varchar(40) NOT NULL,
    "tender_id" bigint NOT NULL
);

CREATE TABLE "serving"."market_tender_competitor_fit" (
    "competitor_fit_id" bigint NOT NULL,
    "competitor_name" varchar(240) NOT NULL,
    "competitor_product_display" text,
    "competitor_product_id" bigint,
    "competitor_products_text" text,
    "fit_label" varchar(80),
    "fit_rationale" text,
    "rank_position" integer,
    "source_id" bigint,
    "tender_id" bigint NOT NULL
);

CREATE TABLE "serving"."market_tender_fit_assessment" (
    "assessed_at" timestamp with time zone,
    "assessment_id" bigint NOT NULL,
    "assessment_rationale" text,
    "client_product_id" bigint,
    "fit_grade" varchar(40),
    "fit_rank" integer,
    "fit_score" numeric,
    "kssl_fit" varchar(40),
    "kssl_fit_rank" integer,
    "kssl_fit_rationale" text,
    "kssl_model" varchar(240),
    "kssl_revenue_estimate" varchar(120),
    "match_status" varchar(80),
    "match_summary" text,
    "revenue_currency" char(3),
    "revenue_estimate_max" numeric,
    "revenue_estimate_min" numeric,
    "revenue_estimate_text" text,
    "revenue_tier" varchar(40),
    "tender_id" bigint NOT NULL
);

CREATE TABLE "serving"."market_tender_portal" (
    "access_status" varchar(80),
    "country_code" char(2),
    "portal_id" bigint NOT NULL,
    "portal_name" varchar(240) NOT NULL,
    "portal_url" text,
    "registration_required" boolean,
    "submission_method" varchar(160)
);

CREATE TABLE "serving"."market_tender_product_match" (
    "display_order" integer NOT NULL,
    "fit_grade" varchar(40),
    "fit_percent" numeric,
    "match_label" varchar(240) NOT NULL,
    "tender_id" bigint NOT NULL,
    "tender_match_id" bigint NOT NULL
);

CREATE TABLE "serving"."market_tender_product_match_line" (
    "display_order" integer NOT NULL,
    "line_label" varchar(180) NOT NULL,
    "line_value" text,
    "match_line_id" bigint NOT NULL,
    "tender_match_id" bigint NOT NULL
);

CREATE TABLE "serving"."market_tender_requirement" (
    "category_text" varchar(160),
    "description" text,
    "display_order" integer,
    "equipment_scope" text,
    "quantity" numeric,
    "quantity_unit" varchar(80),
    "rating_band" varchar(160),
    "requirement_id" bigint NOT NULL,
    "requirement_note" text,
    "requirement_type" varchar(80) NOT NULL,
    "scope_bullet_label" varchar(180),
    "scope_bullet_value" text,
    "scope_text" text,
    "source_text" text,
    "tender_id" bigint NOT NULL,
    "use_case" text
);

CREATE TABLE "serving"."market_tender_source" (
    "access_note" text,
    "is_primary" boolean NOT NULL,
    "portal_name" varchar(240),
    "publisher" varchar(240),
    "retrieved_at" timestamp with time zone,
    "source_id" bigint NOT NULL,
    "source_type" varchar(80),
    "source_url" text,
    "status_check_url" text,
    "tender_id" bigint NOT NULL
);

CREATE TABLE "serving"."market_top_opportunity_metric" (
    "amount_value" numeric,
    "as_of_date" date,
    "currency_code" char(3),
    "formatted_value" varchar(160),
    "metric_id" bigint NOT NULL,
    "metric_key" varchar(80) NOT NULL,
    "metric_label" varchar(160) NOT NULL,
    "note" text,
    "numeric_value" numeric
);

CREATE TABLE "serving"."market_top_opportunity_project" (
    "buyer_name" varchar(240),
    "country_name" varchar(160),
    "kssl_fit" varchar(40),
    "kssl_model" varchar(240),
    "opportunity_id" bigint NOT NULL,
    "rank_position" integer NOT NULL,
    "revenue_text" varchar(120),
    "rival_to_beat" varchar(240),
    "top_opportunity_project_id" bigint NOT NULL,
    "where_it_stands" text
);

CREATE TABLE "serving"."market_top_opportunity_tender" (
    "decides" text,
    "kssl_fit" varchar(40),
    "kssl_model" varchar(240),
    "rank_position" integer NOT NULL,
    "revenue_text" varchar(120),
    "rival_to_beat" varchar(240),
    "status" varchar(60),
    "tender_id" bigint NOT NULL,
    "top_opportunity_tender_id" bigint NOT NULL
);

CREATE TABLE "serving"."technology_category" (
    "canonical_name" varchar(240) NOT NULL,
    "category_code" varchar(80) NOT NULL,
    "category_description" text,
    "category_id" bigint NOT NULL,
    "category_name" text NOT NULL,
    "category_number" integer NOT NULL,
    "display_order" smallint NOT NULL,
    "innovation_count" integer,
    "is_active" boolean NOT NULL,
    "tab_number" smallint NOT NULL
);

CREATE TABLE "serving"."technology_category_ui_label" (
    "category_id" bigint NOT NULL,
    "category_label_id" bigint NOT NULL,
    "database_category_id" varchar(80) NOT NULL,
    "label_text" varchar(240) NOT NULL,
    "locale" varchar(20) NOT NULL,
    "short_label" varchar(160),
    "sort_order" integer NOT NULL,
    "tab_number" smallint NOT NULL,
    "ui_name" varchar(120) NOT NULL
);

CREATE TABLE "serving"."technology_company" (
    "company_id" bigint NOT NULL,
    "company_type" varchar(80),
    "country_code" char(2),
    "display_name" varchar(240) NOT NULL,
    "is_client" boolean NOT NULL
);

CREATE TABLE "serving"."technology_innovation" (
    "action_note" text,
    "assessment_outcome" varchar(40),
    "background_what_it_is" text,
    "category_id" bigint NOT NULL,
    "client_position" varchar(120),
    "competitive_note" text,
    "created_at" timestamp with time zone NOT NULL,
    "external_id" text,
    "horizon_year" integer,
    "innovation_id" bigint NOT NULL,
    "list_description" text,
    "list_secondary_value" text,
    "list_status_label" text,
    "maturity" varchar(100),
    "pillar_id" bigint NOT NULL,
    "sequence_no" integer,
    "status" varchar(40) NOT NULL,
    "summary" text,
    "title" text NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "whats_new" text,
    "why_matters_to_kssl" text
);

CREATE TABLE "serving"."technology_innovation_analysis" (
    "analysis_id" bigint NOT NULL,
    "display_order" integer NOT NULL,
    "innovation_id" bigint NOT NULL,
    "is_client_assessment" boolean NOT NULL,
    "narrative" text NOT NULL,
    "section_code" varchar(80) NOT NULL,
    "section_label" varchar(200) NOT NULL
);

CREATE TABLE "serving"."technology_innovation_company" (
    "company_id" bigint NOT NULL,
    "display_name" text,
    "display_order" integer NOT NULL,
    "innovation_company_id" bigint NOT NULL,
    "innovation_id" bigint NOT NULL,
    "relationship" text NOT NULL,
    "relationship_type" varchar(80) NOT NULL
);

CREATE TABLE "serving"."technology_innovation_source" (
    "innovation_id" bigint NOT NULL,
    "innovation_source_id" bigint NOT NULL,
    "is_primary" boolean NOT NULL,
    "provenance_status" varchar(80),
    "source_id" bigint NOT NULL
);

CREATE TABLE "serving"."technology_innovation_status" (
    "assessment_badge" varchar(40),
    "effective_date" date,
    "horizon_text" varchar(80),
    "innovation_id" bigint NOT NULL,
    "maturity_label" varchar(100),
    "position_label" varchar(120),
    "status_id" bigint NOT NULL
);

CREATE TABLE "serving"."technology_metric" (
    "as_of_date" date,
    "display_order" smallint NOT NULL,
    "metric_action" text,
    "metric_id" bigint NOT NULL,
    "metric_key" varchar(80) NOT NULL,
    "metric_label" varchar(160) NOT NULL,
    "metric_unit" varchar(80),
    "metric_value" numeric NOT NULL,
    "pillar_id" bigint NOT NULL
);

CREATE TABLE "serving"."technology_overview_article" (
    "article_date" date,
    "article_id" bigint NOT NULL,
    "article_says" text,
    "card_summary" text,
    "category_id" text,
    "category_text" varchar(160),
    "classification" varchar(80),
    "client_narrative" text,
    "country_code" char(2),
    "created_at" timestamp with time zone NOT NULL,
    "direction" text,
    "external_id" text,
    "image_url" text,
    "lens" text NOT NULL,
    "overview_article_id" bigint NOT NULL,
    "pillar_id" bigint NOT NULL,
    "primary_company_id" bigint,
    "published_label" text,
    "published_on" date,
    "sequence_no" integer NOT NULL,
    "status" varchar(40) NOT NULL,
    "summary" text,
    "title" text NOT NULL,
    "updated_at" timestamp with time zone NOT NULL
);

CREATE TABLE "serving"."technology_overview_company" (
    "article_id" bigint NOT NULL,
    "company_id" bigint NOT NULL,
    "display_label" text,
    "display_order" integer NOT NULL,
    "overview_article_id" bigint NOT NULL,
    "overview_company_id" bigint NOT NULL,
    "relationship" text NOT NULL,
    "relationship_type" varchar(80)
);

CREATE TABLE "serving"."technology_overview_fact" (
    "article_id" bigint NOT NULL,
    "display_order" integer NOT NULL,
    "fact_id" bigint NOT NULL,
    "fact_key" varchar(80) NOT NULL,
    "fact_label" varchar(160) NOT NULL,
    "fact_value" text NOT NULL,
    "overview_article_id" bigint NOT NULL,
    "overview_fact_id" bigint NOT NULL,
    "proof_text" text,
    "ui_label" text NOT NULL
);

CREATE TABLE "serving"."technology_overview_key_point" (
    "article_id" bigint NOT NULL,
    "display_order" integer NOT NULL,
    "evidence_text" text,
    "key_point_id" bigint NOT NULL,
    "overview_article_id" bigint NOT NULL,
    "point_no" smallint NOT NULL,
    "point_text" text NOT NULL,
    "point_type" varchar(80)
);

CREATE TABLE "serving"."technology_overview_source" (
    "article_id" bigint NOT NULL,
    "display_order" smallint NOT NULL,
    "is_primary" boolean NOT NULL,
    "overview_article_id" bigint NOT NULL,
    "overview_source_id" bigint NOT NULL,
    "provenance_status" varchar(80),
    "source_id" bigint NOT NULL,
    "source_role" text NOT NULL
);

CREATE TABLE "serving"."technology_pillar" (
    "client_name" varchar(240),
    "created_at" timestamp with time zone NOT NULL,
    "is_active" boolean NOT NULL,
    "pillar_code" varchar(40) NOT NULL,
    "pillar_id" bigint NOT NULL,
    "pillar_name" varchar(160) NOT NULL,
    "updated_at" timestamp with time zone NOT NULL
);

CREATE TABLE "serving"."technology_source" (
    "access_status" varchar(80),
    "label" text NOT NULL,
    "publisher" varchar(240),
    "retrieved_at" timestamp with time zone,
    "source_id" bigint NOT NULL,
    "source_kind" text,
    "source_type" varchar(80),
    "source_url" text NOT NULL,
    "url" text NOT NULL
);
