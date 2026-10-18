-- Foundations for the prompt rebuild (docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md sections B and G): the schema gaps of
-- Fable B.1 to B.4, the story tables, and the three ui tables that hold every code list and filter option (G.1).
-- ADDITIVE ONLY and idempotent (ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS / INSERT ... WHERE NOT EXISTS).
-- Applied to BOTH databases by db/make_databases.sh, because Approve copies a card by the column names of the serving table:
--   kssl_staging  -> schema staging  + staging_ui     (DDL, and the ui.code_label seed rows)
--   kssl_serving  -> schema serving  + ui             (DDL only; the rows arrive by Approve)
-- A database that holds all four schemas (a single-DB test setup) gets both blocks.
-- Local: bash db/make_databases.sh.  VPS: python -m prompts.batch sql db/setup/11_foundations.sql --db vps (tunnel open), once per database.
--
-- Names and types are Fable's. Where Fable is vague the choice made here is marked "(chosen)". Nothing is dropped or retyped.
-- Rule versions: every derived label stores the version of the rule that produced it (prompts/derive.py RULE_VERSIONS), so a rule
-- change can be re-derived without a model call.

CREATE OR REPLACE FUNCTION pg_temp.add_cols(s text, t text, cols text[]) RETURNS void LANGUAGE plpgsql AS $f$
DECLARE c text;
BEGIN
    IF to_regclass(format('%I.%I', s, t)) IS NULL THEN
        RAISE NOTICE 'foundations: %.% does not exist - skipped', s, t;
        RETURN;
    END IF;
    FOREACH c IN ARRAY cols LOOP
        EXECUTE format('ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS %s', s, t, c);
    END LOOP;
END $f$;

CREATE OR REPLACE FUNCTION pg_temp.run_sql(s text, u text, q text) RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
    EXECUTE replace(replace(q, '{S}', s), '{U}', u);
END $f$;

CREATE OR REPLACE FUNCTION pg_temp.kssl_foundations(s text, u text) RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE r record;
BEGIN
    -- ======================================================================================================= B.1 shared
    -- story = one thread (competitor + product + counterpart country + event family); story_step = one dated step on it.
    -- Code assigns the key, the model picks a handle or "new", the loader writes both tables (prompts/story.py).
    PERFORM pg_temp.run_sql(s, u, $q$
    CREATE TABLE IF NOT EXISTS {S}.story (
        story_id        bigint       NOT NULL PRIMARY KEY,
        story_key       text         NOT NULL UNIQUE,      -- pillar:party:subject:country:family, e.g. competitive:hanwha:k9:pl:order
        pillar          text         NOT NULL,             -- competitive | market | technology
        kind            text,                              -- event family: programme order delivery trial partnership capacity policy demand technology
        competitor_id   uuid,
        product_id      uuid,
        buyer_name      text,
        country_code    char(2),
        title           text,
        current_label   text,                              -- threat | watch | fav (competitive), pursue ... (market), state after the latest step
        probability     smallint,
        impact          smallint,
        impact_dimension text,
        status          text         NOT NULL DEFAULT 'open',   -- open | closed (chosen)
        first_step_at   date,
        last_step_at    date,
        escalated_at    date,                              -- date of the latest upward label change
        rule_version    text,
        created_at      timestamptz  NOT NULL DEFAULT now(),
        updated_at      timestamptz  NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS story_competitor ON {S}.story (competitor_id, status);
    CREATE TABLE IF NOT EXISTS {S}.story_step (
        step_id         bigint       NOT NULL PRIMARY KEY,
        story_id        bigint       NOT NULL,
        step_no         integer      NOT NULL,             -- 1.. in date order
        step_date       date,
        step_type       text         NOT NULL,             -- announced order contract delivery trial ... label_change
        one_line        varchar(120),
        changed         varchar(120),                      -- what differs from the previous step
        source_url      text,
        source_table    text,                              -- the card this step came from
        source_row_id   text,
        probability     smallint,
        impact          smallint,
        label_after     text,
        run_id          uuid,
        created_at      timestamptz  NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS story_step_story ON {S}.story_step (story_id, step_no);
    CREATE UNIQUE INDEX IF NOT EXISTS story_step_source ON {S}.story_step (story_id, source_table, source_row_id, step_type)
        WHERE source_row_id IS NOT NULL;
    $q$);

    -- cards that belong to a story
    PERFORM pg_temp.add_cols(s, 'competitive_signal',            ARRAY['story_id bigint']);
    PERFORM pg_temp.add_cols(s, 'competitive_product_news',      ARRAY['story_id bigint']);
    PERFORM pg_temp.add_cols(s, 'competitive_competitor_moment', ARRAY['story_id bigint']);
    PERFORM pg_temp.add_cols(s, 'competitive_project',           ARRAY['story_id bigint']);
    PERFORM pg_temp.add_cols(s, 'market_opportunity',            ARRAY['story_id bigint']);
    PERFORM pg_temp.add_cols(s, 'market_global_requirement',     ARRAY['story_id bigint']);
    PERFORM pg_temp.add_cols(s, 'technology_overview_article',   ARRAY['story_id bigint']);

    -- KSSL lens: product kind (product | variant | capability | venture), competitor sub-type, what a partner supplies
    PERFORM pg_temp.add_cols(s, 'client_product',         ARRAY['product_kind varchar(20)']);
    PERFORM pg_temp.add_cols(s, 'competitive_product',    ARRAY['subcategory varchar(128)']);      -- G.3: sub-type copied from product_class (chosen: same type as client_product.subcategory)
    PERFORM pg_temp.add_cols(s, 'client_partner_product', ARRAY['component text']);

    -- ======================================================================================================= B.2 competitive
    PERFORM pg_temp.add_cols(s, 'competitive_signal', ARRAY[
        'direction varchar(12)',                 -- adverse | favourable
        'probability smallint',                  -- 1-5, anchored on the procurement state
        'impact smallint',                       -- = max of the six dimensions (derive.signal_label)
        'impact_dimension varchar(20)',          -- the dimension of the maximum
        'impact_dimension_2 varchar(20)',        -- a second dimension scoring >= 4, else null
        'time_to_effect varchar(10)',            -- lt_1y | 1_3y | gt_3y | unknown
        'subtype_match varchar(10)',             -- same | adjacent | none | unknown
        'in_client_market varchar(10)',          -- yes | no | unknown
        'rule_version varchar(10)',              -- version of the label rule that wrote classification
        'impact_orders_revenue smallint',        -- the six model-scored dimensions (Fable F.1 names)
        'impact_market_standing smallint',
        'impact_supply_chain smallint',
        'impact_technology_gap smallint',
        'impact_partnerships smallint',
        'impact_policy_export smallint']);
    PERFORM pg_temp.add_cols(s, 'competitive_signal_detail', ARRAY[
        'glance_who varchar(40)', 'glance_move varchar(20)', 'glance_where varchar(40)',
        'glance_impact varchar(40)', 'glance_third_party varchar(60)', 'glance_when varchar(60)']);
    PERFORM pg_temp.add_cols(s, 'competitive_competitor_moment', ARRAY['signal_id uuid', 'change_note varchar(160)']);
    PERFORM pg_temp.add_cols(s, 'competitive_product_news', ARRAY[
        'news_type varchar(40)', 'event_date date', 'product_variant varchar(60)', 'kssl_relevance varchar(200)']);
    PERFORM pg_temp.add_cols(s, 'competitive_partnership', ARRAY[
        'status varchar(12)',                    -- announced | active | ended | unknown
        'value_to_competitor varchar(200)', 'value_to_partner varchar(200)', 'kssl_read varchar(300)',
        'overlap_client_partner_id bigint',      -- resolved by code (name match against client_partner)
        'overlap_kind varchar(30)', 'overlap_component varchar(160)', 'overlap_effect varchar(12)']);
    PERFORM pg_temp.add_cols(s, 'competitive_partnership_evidence', ARRAY['step_type varchar(20)']);
    PERFORM pg_temp.add_cols(s, 'competitive_geo_product', ARRAY['customer_name varchar(120)', 'local_partner varchar(120)']);
    PERFORM pg_temp.add_cols(s, 'competitive_project', ARRAY['kssl_option varchar(12)']);   -- compete | partner | supply | none | unknown; the reason is a fact_source row
    PERFORM pg_temp.add_cols(s, 'competitive_patent_filing', ARRAY['category_label varchar(80)']);

    PERFORM pg_temp.run_sql(s, u, $q$
    -- geo layer 2: overlap / anomaly / whitespace findings, one row each (child of the country card)
    CREATE TABLE IF NOT EXISTS {S}.competitive_geo_analysis (
        analysis_id     bigint       NOT NULL PRIMARY KEY,
        location_id     bigint       NOT NULL,
        competitor_id   uuid,
        geo_product_id  bigint,
        kssl_product_id bigint,
        matchup_id      bigint,
        kind            varchar(12)  NOT NULL,              -- overlap | anomaly | whitespace
        finding         varchar(300),
        stated_reasons  text[],                             -- incumbency offsets_local_content financing_g2g delivery_time local_partner after_sales politics price performance other
        reason_state    varchar(12),                        -- stated | not_stated
        hypothesis      varchar(200),                       -- analyst hypothesis, no source (shown greyed)
        to_find_out     varchar(160),
        source_url      text,
        display_order   integer,
        created_at      timestamptz  NOT NULL DEFAULT now()
    );
    -- patent filings per portfolio, category and year: a code roll-up (derive: patent_trend), never a prompt
    CREATE TABLE IF NOT EXISTS {S}.competitive_patent_trend (
        trend_id        bigint       NOT NULL PRIMARY KEY,
        portfolio_id    uuid         NOT NULL,
        category_label  varchar(80)  NOT NULL,
        year            smallint     NOT NULL,
        filing_count    integer      NOT NULL
    );
    $q$);

    -- ======================================================================================================= B.3 market
    PERFORM pg_temp.add_cols(s, 'market_tender_fit_assessment', ARRAY[
        'value_score smallint', 'strategic_score smallint', 'attractiveness smallint', 'ability smallint',
        'pursue_label varchar(10)', 'time_to_award varchar(10)', 'rule_version varchar(10)']);
    PERFORM pg_temp.add_cols(s, 'market_opportunity_fit_assessment', ARRAY[
        'value_score smallint', 'strategic_score smallint', 'attractiveness smallint', 'ability smallint',
        'pursue_label varchar(10)', 'time_to_award varchar(10)', 'rule_version varchar(10)']);
    PERFORM pg_temp.add_cols(s, 'market_tender_competitor_fit', ARRAY['basis varchar(20)']);     -- selected | shortlisted | offered | presence
    PERFORM pg_temp.add_cols(s, 'market_next_move', ARRAY['move_kind varchar(20)']);
    PERFORM pg_temp.add_cols(s, 'market_tender', ARRAY['awarded_to varchar(200)', 'award_date date', 'award_value_text varchar(120)']);
    PERFORM pg_temp.add_cols(s, 'market_tender_closing_window', ARRAY['clarification_deadline date', 'opening_date date']);
    PERFORM pg_temp.add_cols(s, 'market_global_requirement', ARRAY[
        'stage varchar(24)', 'stage_date date', 'last_confirmed date', 'status_state varchar(12)']);
    PERFORM pg_temp.add_cols(s, 'market_opportunity', ARRAY['requirement_id bigint', 'tender_id bigint']);
    PERFORM pg_temp.run_sql(s, u, $q$
    CREATE TABLE IF NOT EXISTS {S}.market_tender_eligibility (
        eligibility_id  bigint       NOT NULL PRIMARY KEY,
        tender_id       bigint       NOT NULL,
        item            varchar(120) NOT NULL,
        state           varchar(10),                        -- met | not_met | unknown
        fixable         varchar(10),                        -- yes | no | unknown
        note            varchar(200),
        requirement_id  bigint,
        quote           text,                               -- (chosen) the verbatim line, as in Fable F.2
        display_order   integer
    );
    CREATE TABLE IF NOT EXISTS {S}.market_global_requirement_rival (
        rival_id        bigint       NOT NULL PRIMARY KEY,
        requirement_id  bigint       NOT NULL,
        competitor_id   uuid,
        product_id      uuid,
        basis           varchar(20),                        -- selected | shortlisted | offered | presence
        note            text,
        display_order   integer
    );
    $q$);

    -- ======================================================================================================= B.4 technology
    PERFORM pg_temp.add_cols(s, 'technology_overview_article', ARRAY[
        'maturity smallint', 'relevance smallint',
        'horizon varchar(10)',                   -- lt_2y | 2_5y | gt_5y | unknown
        'horizon_source varchar(6)',             -- stated | rule
        'touches_client_product_id bigint', 'spec_touched varchar(60)',
        'client_position varchar(10)',           -- behind | parity | ahead | unknown
        'rule_version varchar(10)']);
    PERFORM pg_temp.add_cols(s, 'technology_innovation', ARRAY[
        'maturity_level smallint', 'technology_kind varchar(30)', 'stance varchar(10)']);
    PERFORM pg_temp.run_sql(s, u, $q$
    CREATE TABLE IF NOT EXISTS {S}.technology_innovation_milestone (
        milestone_id    bigint       NOT NULL PRIMARY KEY,
        innovation_id   bigint       NOT NULL,
        step_date       date,
        step_type       varchar(20),                        -- announced | prototype | trials | contract | production | fielded
        note            varchar(160),
        source_url      text
    );
    $q$);

    -- ======================================================================================================= G.1 code lists and filter options (ui schema)
    PERFORM pg_temp.run_sql(s, u, $q$
    -- one row per allowed value of every enum column of every pillar; prompts' enum lists and the pages read it
    CREATE TABLE IF NOT EXISTS {U}.code_label (
        table_name      text         NOT NULL,
        column_name     text         NOT NULL,
        code            text         NOT NULL,
        label           text         NOT NULL,
        tag_class       varchar(40),
        tooltip         text,
        display_order   integer      NOT NULL DEFAULT 0,
        is_active       boolean      NOT NULL DEFAULT true,
        value_from      numeric,                            -- (chosen) day windows: day_from / day_to
        value_to        numeric,
        is_default      boolean      NOT NULL DEFAULT false,
        PRIMARY KEY (table_name, column_name, code)
    );
    -- the exact shape of market_filter_option, rebuilt from the stored values by derive.filter_options
    CREATE TABLE IF NOT EXISTS {U}.competitive_filter_option (
        option_id       bigint       NOT NULL PRIMARY KEY,
        filter_type     varchar(40)  NOT NULL,
        option_code     varchar(80)  NOT NULL,
        option_label    varchar(240),
        record_count    integer,
        sort_order      integer,
        is_active       boolean      NOT NULL DEFAULT true
    );
    CREATE TABLE IF NOT EXISTS {U}.technology_filter_option (
        option_id       bigint       NOT NULL PRIMARY KEY,
        filter_type     varchar(40)  NOT NULL,
        option_code     varchar(80)  NOT NULL,
        option_label    varchar(240),
        record_count    integer,
        sort_order      integer,
        is_active       boolean      NOT NULL DEFAULT true
    );
    $q$);
    -- closing windows (G.2 row 7) read from market_tender_filter rows instead of marketOverview.js WINDOWS
    PERFORM pg_temp.add_cols(u, 'market_tender_filter', ARRAY['day_from integer', 'day_to integer', 'tag_class varchar(40)']);

    -- the live database refuses writes unless Approve set kssl.approve (db/setup/04_serving_db.sql): protect the new tables too
    IF s = 'serving' AND to_regproc('public.kssl_only_via_approve') IS NOT NULL THEN
        FOR r IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('serving', 'ui') LOOP
            EXECUTE format('DROP TRIGGER IF EXISTS only_via_approve ON %I.%I', r.schemaname, r.tablename);
            EXECUTE format('CREATE TRIGGER only_via_approve BEFORE INSERT OR UPDATE OR DELETE ON %I.%I
                            FOR EACH STATEMENT EXECUTE FUNCTION public.kssl_only_via_approve()', r.schemaname, r.tablename);
        END LOOP;
    END IF;
END $fn$;

DO $$
BEGIN
    IF to_regnamespace('staging') IS NOT NULL AND to_regnamespace('staging_ui') IS NOT NULL THEN
        PERFORM pg_temp.kssl_foundations('staging', 'staging_ui');
    END IF;
    IF to_regnamespace('serving') IS NOT NULL AND to_regnamespace('ui') IS NOT NULL THEN
        PERFORM pg_temp.kssl_foundations('serving', 'ui');
    END IF;
END $$;

-- ============================================================================================================================
-- ui.code_label seed (kssl_staging only, DATA): the option / tag lists that were typed into the frontend (Fable G.2), plus the
-- vocabularies of every new column (G.3). A row is inserted only if missing, so a hand edit is never overwritten.
-- File:line -> table_name.column_name that the UI must read instead (frontend change comes later):
--   1  src/lib/dataset.js:113-117,131-135, src/lib/overview.js:344-364   competitive_metric.metric_key, technology_overview_metric_card.metric_key
--   2  src/lib/overview.js:29 DIR_WORD; Profile.jsx:18 DOT; ThreatAnalysis.jsx:13-15; Projects.jsx:11 STANCE_LABEL; Products.jsx:379
--                                                                        competitive_signal.classification, competitive_competitor.threat_level, competitive_project.assessment_stance
--   3  src/lib/overview.js:6-25 SEQ_LABEL / SEQ_SUB / SEQ_OPTIONS         competitive_overview_feed.sequence_mode
--   4  src/lib/overview.js:317 TECH_KIND, dataset.js:128 tagWord          technology_overview_article.classification (tag_class = stream)
--   5  src/lib/overview.js:391-407 TILE_LABELS                            overview_tile.metric_key (tooltip = the phrase)
--   6  src/lib/news.js:112-120, src/pages/competitive/Profile.jsx:721-728  competitive_news_view.published_range (value_from / value_to = days, is_default)
--   7  src/lib/marketOverview.js:10-16, MarketOverview.jsx:139-145,29-34   market_tender_filter.closing_window (value_from / value_to = days), market_view.section
--   8  src/lib/tenderCalc.js:10, src/pages/market/Tenders.jsx:145         market_tender.status (tag_class = tab), market_tender.lean_code
--   9  src/lib/tenderRow.js:13-24, Tenders.jsx:85                         market_tender_card.param (low priority)
--  10  src/components/matchupDossier/MatchupDossier.jsx:6                  competitive_positioning_tab.tab_code
--  11  src/lib/partners.js:27-45,20-26, Partnerships.jsx:587,672-700      competitive_partnership.partner_type (tag_class = symbol key), competitive_partnership_graph.group_by
--  12  src/lib/partners.js:66-70 CONF_TAG                                 competitive_partnership.relationship_confidence (tooltip)
--  13  src/pages/competitive/Geo.jsx:21-25,33-35, src/lib/geoBadge.js:41-44  competitive_geo_company_presence.overlap_status / .activity_type, competitive_matchup.decision_level, better_side
--  14  src/lib/chat.js:14-19 MAT_LAB, backend/areas/d_market_tech.py:13, Innovation.jsx:213   technology_innovation.maturity_level, technology_overview_article.maturity
--  15  src/lib/edge.js:28-31, src/lib/specs.js:142-143                    competitive_matchup.decision_level, competitive_geo_product_match.decision_level
--  16  Projects.jsx:11, Profile.jsx:18, ThreatAnalysis.jsx:13-15, Products.jsx:379   same rows as 2
--  17  src/lib/route.js:13-52 (navigation) and 18 src/lib/search.js, Review.jsx:15 (chrome): left in the frontend on purpose.
-- ============================================================================================================================
DO $seed$
BEGIN
    IF to_regclass('staging_ui.code_label') IS NOT NULL THEN
        INSERT INTO staging_ui.code_label (table_name, column_name, code, label, tag_class, tooltip, display_order, is_active, value_from, value_to, is_default)
        SELECT v.* FROM (VALUES
    ('competitive_signal', 'classification', 'threat', 'Threat', 'threat', NULL, 1, true, NULL, NULL, false),
    ('competitive_signal', 'classification', 'watch', 'Watch', 'watch', NULL, 2, true, NULL, NULL, false),
    ('competitive_signal', 'classification', 'fav', 'Favourable', 'fav', NULL, 3, true, NULL, NULL, false),
    ('competitive_competitor', 'threat_level', 'threat', 'Threat', 'threat', NULL, 1, true, NULL, NULL, false),
    ('competitive_competitor', 'threat_level', 'watch', 'Watch', 'watch', NULL, 2, true, NULL, NULL, false),
    ('competitive_competitor', 'threat_level', 'fav', 'Favourable', 'fav', NULL, 3, true, NULL, NULL, false),
    ('competitive_project', 'assessment_stance', 'threat', 'Threat', 'threat', NULL, 1, true, NULL, NULL, false),
    ('competitive_project', 'assessment_stance', 'watch', 'Watch', 'watch', NULL, 2, true, NULL, NULL, false),
    ('competitive_project', 'assessment_stance', 'fav', 'Favourable', 'fav', NULL, 3, true, NULL, NULL, false),
    ('technology_overview_article', 'direction', 'threat', 'Threat', 'threat', NULL, 1, true, NULL, NULL, false),
    ('technology_overview_article', 'direction', 'watch', 'Watch', 'watch', NULL, 2, true, NULL, NULL, false),
    ('technology_overview_article', 'direction', 'fav', 'Favourable', 'fav', NULL, 3, true, NULL, NULL, false),
    ('competitive_metric', 'metric_key', 'threat', 'Competitive threats', 'threat', 'threats to active bids', 1, true, NULL, NULL, false),
    ('competitive_metric', 'metric_key', 'watch', 'Watch signals', 'watch', 'watch signals', 2, true, NULL, NULL, false),
    ('competitive_metric', 'metric_key', 'all', 'Companies tracked', NULL, 'sorted by relevance', 3, true, NULL, NULL, false),
    ('technology_overview_metric_card', 'metric_key', 'rival', 'Competitor advances', 'rival', 'competitor advancements', 1, true, NULL, NULL, false),
    ('technology_overview_metric_card', 'metric_key', 'adopt', 'Adoptable advances', 'adopt', 'advances KSSL can adopt', 2, true, NULL, NULL, false),
    ('technology_overview_metric_card', 'metric_key', 'all', 'Domains tracked', NULL, 'sorted by relevance', 3, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'atstake', 'At stake', NULL, 'contested bids, by value', 1, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'threat', 'Threats', NULL, 'threats to active bids', 2, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'fav', 'Favourable', NULL, 'openings to press', 3, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'watch', 'Watch', NULL, 'watch signals', 4, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'deadline', 'Deadlines', NULL, 'by submission deadline', 5, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'rival', 'Competitor advances', NULL, 'competitor advancements', 6, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'adopt', 'Adoptable advances', NULL, 'advances KSSL can adopt', 7, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'geo', 'Geo', NULL, 'markets in play', 8, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'positioning', 'Positioning', NULL, 'rating-matched rivals', 9, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'gap', 'Gaps', NULL, 'capability gaps', 10, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'patents', 'Patents', NULL, 'patent activity', 11, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'emission', 'Emission', NULL, 'emission compliance', 12, true, NULL, NULL, false),
    ('overview_tile', 'metric_key', 'all', 'All', NULL, 'sorted by relevance', 13, true, NULL, NULL, false),
    ('competitive_overview_feed', 'sequence_mode', 'priority', 'Priority order', NULL, 'highest threat and impact first', 1, true, NULL, NULL, true),
    ('competitive_overview_feed', 'sequence_mode', 'recency', 'Most recent', NULL, 'newest signals at top', 2, true, NULL, NULL, false),
    ('competitive_overview_feed', 'sequence_mode', 'depth', 'Richest analysis first', NULL, 'most analytical lenses first', 3, false, NULL, NULL, false),
    ('competitive_overview_feed', 'sequence_mode', 'category', 'Grouped by domain', NULL, 'ordered by category', 4, false, NULL, NULL, false),
    ('technology_overview_article', 'classification', 'competitor_advance', 'Competitor advance', 'rival', 'a rival gains a capability', 1, true, NULL, NULL, false),
    ('technology_overview_article', 'classification', 'adoptable', 'Adoptable', 'adopt', 'something KSSL could adopt, license or partner on', 2, true, NULL, NULL, false),
    ('technology_overview_article', 'classification', 'threat_to_position', 'Threat to KSSL''s position', 'trend', 'a development that weakens KSSL''s technology position', 3, true, NULL, NULL, false),
    ('technology_overview_article', 'classification', 'industry_trend', 'Industry trend', 'trend', 'an enabling or general development', 4, true, NULL, NULL, false),
    ('competitive_news_view', 'published_range', 'all', 'All dates', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_news_view', 'published_range', '7d', 'Last 7 days', NULL, NULL, 2, true, 0, 7, false),
    ('competitive_news_view', 'published_range', '30d', 'Last 30 days', NULL, NULL, 3, true, 0, 30, false),
    ('competitive_news_view', 'published_range', '3m', 'Last 3 months', NULL, NULL, 4, true, 0, 90, false),
    ('competitive_news_view', 'published_range', '6m', 'Last 6 months', NULL, NULL, 5, true, 0, 180, false),
    ('competitive_news_view', 'published_range', '12m', 'Last 12 months', NULL, NULL, 6, true, 0, 365, true),
    ('competitive_news_view', 'published_range', 'custom', 'Custom range', NULL, NULL, 7, true, NULL, NULL, false),
    ('market_tender_filter', 'closing_window', 'w7', 'Up to 7 days', 'w7', NULL, 1, true, 0, 7, false),
    ('market_tender_filter', 'closing_window', 'w14', '8-14 days', 'w14', NULL, 2, true, 8, 14, false),
    ('market_tender_filter', 'closing_window', 'w30', '15-30 days', 'w30', NULL, 3, true, 15, 30, false),
    ('market_tender_filter', 'closing_window', 'w30p', '30+ days', 'w30p', NULL, 4, true, 31, NULL, false),
    ('market_tender_filter', 'closing_window', 'none', 'No date published', 'none', NULL, 5, true, NULL, NULL, false),
    ('market_view', 'section', 'active', 'Number of active tenders', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_view', 'section', 'category', 'By category', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_view', 'section', 'awarded', 'Awarded', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_view', 'section', 'closed', 'Closed', NULL, NULL, 4, true, NULL, NULL, false),
    ('market_tender', 'status', 'open', 'Open', 'open', NULL, 1, true, NULL, NULL, false),
    ('market_tender', 'status', 'closing', 'Closing', 'open', NULL, 2, true, NULL, NULL, false),
    ('market_tender', 'status', 'awarded', 'Awarded', 'awarded', NULL, 3, true, NULL, NULL, false),
    ('market_tender', 'status', 'closed', 'Closed', 'closed', NULL, 4, true, NULL, NULL, false),
    ('market_tender', 'lean_code', 'go', 'Pursue', 'go', NULL, 1, true, NULL, NULL, false),
    ('market_tender', 'lean_code', 'maybe', 'Position', 'maybe', NULL, 2, true, NULL, NULL, false),
    ('market_tender', 'lean_code', 'watch', 'Monitor', 'watch', NULL, 3, true, NULL, NULL, false),
    ('market_tender', 'lean_code', 'pass', 'Pass', 'pass', NULL, 4, true, NULL, NULL, false),
    ('market_tender', 'lean_code', 'won', 'Won', 'won', NULL, 5, true, NULL, NULL, false),
    ('market_tender', 'lean_code', 'closed', 'Closed', 'closed', NULL, 6, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'buyer', 'Buyer', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'country', 'Country', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'category', 'Category', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'value', 'Value', NULL, NULL, 4, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'quantity', 'Quantity', NULL, NULL, 5, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'posted', 'Published', NULL, NULL, 6, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'closing', 'Closing date', NULL, NULL, 7, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'status', 'Status', NULL, NULL, 8, true, NULL, NULL, false),
    ('market_tender_card', 'param', 'source', 'Source', NULL, NULL, 9, true, NULL, NULL, false),
    ('competitive_positioning_tab', 'tab_code', 'adv', 'Analytics', NULL, NULL, 1, true, NULL, NULL, true),
    ('competitive_positioning_tab', 'tab_code', 'specs', 'Spec Comparison', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_partnership', 'partner_type', 'JV', 'JV', 'jv', NULL, 1, true, NULL, NULL, false),
    ('competitive_partnership', 'partner_type', 'MoU / teaming', 'MoU / teaming', 'mou', NULL, 2, true, NULL, NULL, false),
    ('competitive_partnership', 'partner_type', 'Contract (customer-supplier)', 'Contract (customer-supplier)', 'supply', NULL, 3, true, NULL, NULL, false),
    ('competitive_partnership', 'partner_type', 'Supplier / sub-supplier', 'Supplier / sub-supplier', 'supply', NULL, 4, true, NULL, NULL, false),
    ('competitive_partnership', 'partner_type', 'Licence / ToT', 'Licence / ToT', 'tech', NULL, 5, true, NULL, NULL, false),
    ('competitive_partnership', 'partner_type', 'Co-development', 'Co-development', 'tech', NULL, 6, true, NULL, NULL, false),
    ('competitive_partnership', 'partner_type', 'Investment / acquisition', 'Investment / acquisition', 'acq', NULL, 7, true, NULL, NULL, false),
    ('competitive_partnership_graph', 'group_by', 'type', 'Categories', NULL, NULL, 1, true, NULL, NULL, true),
    ('competitive_partnership_graph', 'group_by', 'region', 'Regions', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_partnership', 'relationship_confidence', 'official', 'official', 'official', 'the maker or a government publisher states it', 1, true, NULL, NULL, false),
    ('competitive_partnership', 'relationship_confidence', 'corroborated', 'corroborated', 'corroborated', 'two or more independent sources', 2, true, NULL, NULL, false),
    ('competitive_partnership', 'relationship_confidence', 'single_source', 'single source', 'single_source', 'one source, uncorroborated', 3, true, NULL, NULL, false),
    ('competitive_partnership', 'status', 'announced', 'Announced', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_partnership', 'status', 'active', 'Active', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_partnership', 'status', 'ended', 'Ended', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_partnership', 'status', 'unknown', 'Unknown', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_partnership_evidence', 'step_type', 'mou', 'MoU', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_partnership_evidence', 'step_type', 'agreement', 'Agreement', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_partnership_evidence', 'step_type', 'jv_formed', 'JV formed', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_partnership_evidence', 'step_type', 'first_product', 'First product', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_partnership_evidence', 'step_type', 'order', 'Order', NULL, NULL, 5, true, NULL, NULL, false),
    ('competitive_partnership_evidence', 'step_type', 'delivery', 'Delivery', NULL, NULL, 6, true, NULL, NULL, false),
    ('competitive_partnership_evidence', 'step_type', 'ended', 'Ended', NULL, NULL, 7, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_kind', 'same_component', 'Same component', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_kind', 'same_partner_other_scope', 'Same partner, other scope', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_kind', 'kssl_market', 'KSSL market', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_kind', 'none', 'None', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_kind', 'unknown', 'Unknown', NULL, NULL, 5, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_effect', 'risk', 'Risk', 'threat', NULL, 1, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_effect', 'advantage', 'Advantage', 'fav', NULL, 2, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_effect', 'both', 'Both', 'watch', NULL, 3, true, NULL, NULL, false),
    ('competitive_partnership', 'overlap_effect', 'unknown', 'Unknown', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_geo_company_presence', 'overlap_status', 'confirmed', 'Confirmed overlap', 'spec', NULL, 1, true, NULL, NULL, false),
    ('competitive_geo_company_presence', 'overlap_status', 'category', 'Category overlap', 'cat', NULL, 2, true, NULL, NULL, false),
    ('competitive_geo_company_presence', 'overlap_status', 'none', 'No indexed overlap', 'none', NULL, 3, true, NULL, NULL, false),
    ('competitive_geo_company_presence', 'activity_type', 'Sells', 'Sells', 'ex', NULL, 1, true, NULL, NULL, false),
    ('competitive_geo_company_presence', 'activity_type', 'Manufactures', 'Manufactures', 'lp', NULL, 2, true, NULL, NULL, false),
    ('competitive_geo_company_presence', 'activity_type', 'Licensed production', 'Licensed production', 'pt', NULL, 3, true, NULL, NULL, false),
    ('competitive_geo_company_presence', 'activity_type', 'Sources', 'Sources', 'bf', NULL, 4, true, NULL, NULL, false),
    ('competitive_geo_company_presence', 'activity_type', 'Sales and service', 'Sales and service', 'sv', NULL, 5, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'kind', 'overlap', 'Overlap', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'kind', 'anomaly', 'Anomaly', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'kind', 'whitespace', 'Whitespace', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'reason_state', 'stated', 'Stated in a source', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'reason_state', 'not_stated', 'Not stated', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'incumbency', 'Incumbency', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'offsets_local_content', 'Offsets / local content', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'financing_g2g', 'Financing / government-to-government', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'delivery_time', 'Delivery time', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'local_partner', 'Local partner', NULL, NULL, 5, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'after_sales', 'After-sales network', NULL, NULL, 6, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'politics', 'Politics', NULL, NULL, 7, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'price', 'Price', NULL, NULL, 8, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'performance', 'Performance', NULL, NULL, 9, true, NULL, NULL, false),
    ('competitive_geo_analysis', 'stated_reasons', 'other', 'Other', NULL, NULL, 10, true, NULL, NULL, false),
    ('competitive_matchup', 'decision_level', '1', 'Behind', 'behind', 'competitor holds the edge', 1, true, NULL, NULL, false),
    ('competitive_matchup', 'decision_level', '2', 'Near parity', 'parity', 'near parity', 2, true, NULL, NULL, false),
    ('competitive_matchup', 'decision_level', '3', 'Ahead', 'ahead', 'KSSL holds the edge', 3, true, NULL, NULL, false),
    ('competitive_geo_product_match', 'decision_level', '1', 'Behind', 'behind', 'competitor holds the edge', 1, true, NULL, NULL, false),
    ('competitive_geo_product_match', 'decision_level', '2', 'Near parity', 'parity', 'near parity', 2, true, NULL, NULL, false),
    ('competitive_geo_product_match', 'decision_level', '3', 'Ahead', 'ahead', 'KSSL holds the edge', 3, true, NULL, NULL, false),
    ('competitive_matchup_specification', 'better_side', 'client', 'KSSL', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_matchup_specification', 'better_side', 'competitor', 'Competitor', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_matchup_specification', 'better_side', 'equal', 'Equal', NULL, NULL, 3, true, NULL, NULL, false),
    ('technology_innovation', 'maturity_level', '1', 'Concept / research', 'lab', NULL, 1, true, NULL, NULL, false),
    ('technology_innovation', 'maturity_level', '2', 'Prototype', 'dev', NULL, 2, true, NULL, NULL, false),
    ('technology_innovation', 'maturity_level', '3', 'Trials', 'dev', NULL, 3, true, NULL, NULL, false),
    ('technology_innovation', 'maturity_level', '4', 'Production', 'prod', NULL, 4, true, NULL, NULL, false),
    ('technology_innovation', 'maturity_level', '5', 'Fielded', 'fielded', NULL, 5, true, NULL, NULL, false),
    ('technology_overview_article', 'maturity', '1', 'Concept / research', 'lab', NULL, 1, true, NULL, NULL, false),
    ('technology_overview_article', 'maturity', '2', 'Prototype', 'dev', NULL, 2, true, NULL, NULL, false),
    ('technology_overview_article', 'maturity', '3', 'Trials', 'dev', NULL, 3, true, NULL, NULL, false),
    ('technology_overview_article', 'maturity', '4', 'Production', 'prod', NULL, 4, true, NULL, NULL, false),
    ('technology_overview_article', 'maturity', '5', 'Fielded', 'fielded', NULL, 5, true, NULL, NULL, false),
    ('technology_innovation', 'client_position', 'behind', 'Behind', 'behind', NULL, 1, true, NULL, NULL, false),
    ('technology_innovation', 'client_position', 'parity', 'Parity', 'parity', NULL, 2, true, NULL, NULL, false),
    ('technology_innovation', 'client_position', 'ahead', 'Ahead', 'ahead', NULL, 3, true, NULL, NULL, false),
    ('technology_innovation', 'client_position', 'unknown', 'Unknown', NULL, NULL, 4, true, NULL, NULL, false),
    ('technology_overview_article', 'client_position', 'behind', 'Behind', 'behind', NULL, 1, true, NULL, NULL, false),
    ('technology_overview_article', 'client_position', 'parity', 'Parity', 'parity', NULL, 2, true, NULL, NULL, false),
    ('technology_overview_article', 'client_position', 'ahead', 'Ahead', 'ahead', NULL, 3, true, NULL, NULL, false),
    ('technology_overview_article', 'client_position', 'unknown', 'Unknown', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_project', 'kssl_option', 'compete', 'Compete', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_project', 'kssl_option', 'partner', 'Partner', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_project', 'kssl_option', 'supply', 'Supply', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_project', 'kssl_option', 'none', 'None', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_project', 'kssl_option', 'unknown', 'Unknown', NULL, NULL, 5, true, NULL, NULL, false),
    ('competitive_signal', 'direction', 'adverse', 'Adverse to KSSL', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_signal', 'direction', 'favourable', 'Favourable to KSSL', 'fav', NULL, 2, true, NULL, NULL, false),
    ('competitive_signal', 'probability', '5', 'Done', NULL, 'contract signed, delivery made, JV registered, plant opened, induction completed', 1, true, NULL, NULL, false),
    ('competitive_signal', 'probability', '4', 'Decided', NULL, 'selected, L1 or approved with funding; award or signature expected within 12 months', 2, true, NULL, NULL, false),
    ('competitive_signal', 'probability', '3', 'In competition', NULL, 'shortlisted, in trials, RFP response submitted, MoU tied to a named programme', 3, true, NULL, NULL, false),
    ('competitive_signal', 'probability', '2', 'Intent', NULL, 'MoU without a programme, plans to, in talks, capacity announced without a customer', 4, true, NULL, NULL, false),
    ('competitive_signal', 'probability', '1', 'Rumour', NULL, 'report of interest, unnamed sources, analyst speculation', 5, true, NULL, NULL, false),
    ('competitive_signal', 'impact', '5', 'Decisive', NULL, 'changes a tender, customer, supplier or partner KSSL is tied to', 1, true, NULL, NULL, false),
    ('competitive_signal', 'impact', '4', 'High', NULL, 'hits a KSSL customer, supplier or product line directly', 2, true, NULL, NULL, false),
    ('competitive_signal', 'impact', '3', 'Medium', NULL, 'same kind of product, market or supplier, but not KSSL''s own', 3, true, NULL, NULL, false),
    ('competitive_signal', 'impact', '2', 'Low', NULL, 'indirect, or outside KSSL''s markets', 4, true, NULL, NULL, false),
    ('competitive_signal', 'impact', '1', 'None', NULL, 'no link to a KSSL line', 5, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension', 'orders_revenue', 'Orders and revenue', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension', 'market_standing', 'Market standing', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension', 'supply_chain', 'Supply chain', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension', 'technology_gap', 'Technology gap', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension', 'partnerships', 'Partnerships', NULL, NULL, 5, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension', 'policy_export', 'Policy and export', NULL, NULL, 6, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension_2', 'orders_revenue', 'Orders and revenue', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension_2', 'market_standing', 'Market standing', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension_2', 'supply_chain', 'Supply chain', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension_2', 'technology_gap', 'Technology gap', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension_2', 'partnerships', 'Partnerships', NULL, NULL, 5, true, NULL, NULL, false),
    ('competitive_signal', 'impact_dimension_2', 'policy_export', 'Policy and export', NULL, NULL, 6, true, NULL, NULL, false),
    ('competitive_signal', 'time_to_effect', 'lt_1y', 'Under 1 year', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_signal', 'time_to_effect', '1_3y', '1 to 3 years', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_signal', 'time_to_effect', 'gt_3y', 'Over 3 years', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_signal', 'time_to_effect', 'unknown', 'Unknown', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_signal', 'subtype_match', 'same', 'Same sub-type', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_signal', 'subtype_match', 'adjacent', 'Adjacent sub-type', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_signal', 'subtype_match', 'none', 'No match', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_signal', 'subtype_match', 'unknown', 'Unknown', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_signal', 'in_client_market', 'yes', 'Yes', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_signal', 'in_client_market', 'no', 'No', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_signal', 'in_client_market', 'unknown', 'Unknown', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Order', 'Order', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Contract', 'Contract', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Selection', 'Selection', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Delivery', 'Delivery', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Induction', 'Induction', NULL, NULL, 5, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Trial', 'Trial', NULL, NULL, 6, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Launch', 'Launch', NULL, NULL, 7, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'JV', 'JV', NULL, NULL, 8, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'MoU', 'MoU', NULL, NULL, 9, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Acquisition', 'Acquisition', NULL, NULL, 10, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Capacity', 'Capacity', NULL, NULL, 11, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Export approval', 'Export approval', NULL, NULL, 12, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Policy', 'Policy', NULL, NULL, 13, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Supply deal', 'Supply deal', NULL, NULL, 14, true, NULL, NULL, false),
    ('competitive_signal_detail', 'glance_move', 'Cancellation', 'Cancellation', NULL, NULL, 15, true, NULL, NULL, false),
    ('story', 'kind', 'programme', 'Programme', NULL, NULL, 1, true, NULL, NULL, false),
    ('story', 'kind', 'order', 'Order', NULL, NULL, 2, true, NULL, NULL, false),
    ('story', 'kind', 'delivery', 'Delivery', NULL, NULL, 3, true, NULL, NULL, false),
    ('story', 'kind', 'trial', 'Trial', NULL, NULL, 4, true, NULL, NULL, false),
    ('story', 'kind', 'partnership', 'Partnership', NULL, NULL, 5, true, NULL, NULL, false),
    ('story', 'kind', 'capacity', 'Capacity', NULL, NULL, 6, true, NULL, NULL, false),
    ('story', 'kind', 'policy', 'Policy', NULL, NULL, 7, true, NULL, NULL, false),
    ('story', 'kind', 'demand', 'Demand', NULL, NULL, 8, true, NULL, NULL, false),
    ('story', 'kind', 'technology', 'Technology', NULL, NULL, 9, true, NULL, NULL, false),
    ('story_step', 'step_type', 'announced', 'Announced', NULL, NULL, 1, true, NULL, NULL, false),
    ('story_step', 'step_type', 'order', 'Order', NULL, NULL, 2, true, NULL, NULL, false),
    ('story_step', 'step_type', 'contract', 'Contract', NULL, NULL, 3, true, NULL, NULL, false),
    ('story_step', 'step_type', 'delivery', 'Delivery', NULL, NULL, 4, true, NULL, NULL, false),
    ('story_step', 'step_type', 'trial', 'Trial', NULL, NULL, 5, true, NULL, NULL, false),
    ('story_step', 'step_type', 'partnership', 'Partnership', NULL, NULL, 6, true, NULL, NULL, false),
    ('story_step', 'step_type', 'capacity', 'Capacity', NULL, NULL, 7, true, NULL, NULL, false),
    ('story_step', 'step_type', 'policy', 'Policy', NULL, NULL, 8, true, NULL, NULL, false),
    ('story_step', 'step_type', 'update', 'Update', NULL, NULL, 9, true, NULL, NULL, false),
    ('story_step', 'step_type', 'label_change', 'Label change', NULL, NULL, 10, true, NULL, NULL, false),
    ('story_step', 'label_after', 'threat', 'Threat', 'threat', NULL, 1, true, NULL, NULL, false),
    ('story_step', 'label_after', 'watch', 'Watch', 'watch', NULL, 2, true, NULL, NULL, false),
    ('story_step', 'label_after', 'fav', 'Favourable', 'fav', NULL, 3, true, NULL, NULL, false),
    ('story_step', 'label_after', 'pursue', 'Pursue', 'go', NULL, 4, true, NULL, NULL, false),
    ('story_step', 'label_after', 'position', 'Position', 'maybe', NULL, 5, true, NULL, NULL, false),
    ('story_step', 'label_after', 'monitor', 'Monitor', 'watch', NULL, 6, true, NULL, NULL, false),
    ('story_step', 'label_after', 'pass', 'Pass', 'pass', NULL, 7, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'programme_order', 'Programme / order', NULL, NULL, 1, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'delivery_induction', 'Delivery / induction', NULL, NULL, 2, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'deployment_combat_use', 'Deployment / combat use', NULL, NULL, 3, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'trial_test_demo', 'Trial / test / demonstration', NULL, NULL, 4, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'export_new_customer', 'Export / new customer', NULL, NULL, 5, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'upgrade_variant_component', 'Upgrade / variant / component', NULL, NULL, 6, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'production_localisation_licence', 'Production / localisation / licence', NULL, NULL, 7, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'certification_qualification', 'Certification / qualification', NULL, NULL, 8, true, NULL, NULL, false),
    ('competitive_product_news', 'news_type', 'incident_failure', 'Incident / failure', NULL, NULL, 9, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'pursue_label', 'pursue', 'Pursue', 'go', 'attractive and KSSL is able to win', 1, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'pursue_label', 'position', 'Position', 'maybe', 'attractive; close the gaps before bidding', 2, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'pursue_label', 'monitor', 'Monitor', 'watch', 'not attractive enough, or too hard to win, for now', 3, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'pursue_label', 'pass', 'Pass', 'pass', 'weak fit or a bar KSSL cannot clear', 4, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'time_to_award', 'le_6m', 'Within 6 months', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'time_to_award', '6_18m', '6 to 18 months', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'time_to_award', 'gt_18m', 'Over 18 months', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'time_to_award', 'unknown', 'Unknown', NULL, NULL, 4, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'fit_grade', 'strong', 'Strong', 'strong', NULL, 1, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'fit_grade', 'partial', 'Partial', 'partial', NULL, 2, true, NULL, NULL, false),
    ('market_tender_fit_assessment', 'fit_grade', 'weak', 'Weak', 'weak', NULL, 3, true, NULL, NULL, false),
    ('market_tender_eligibility', 'state', 'met', 'Met', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_tender_eligibility', 'state', 'not_met', 'Not met', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_tender_eligibility', 'state', 'unknown', 'Unknown', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_tender_eligibility', 'fixable', 'yes', 'Yes', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_tender_eligibility', 'fixable', 'no', 'No', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_tender_eligibility', 'fixable', 'unknown', 'Unknown', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_tender_competitor_fit', 'basis', 'selected', 'Selected', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_tender_competitor_fit', 'basis', 'shortlisted', 'Shortlisted', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_tender_competitor_fit', 'basis', 'offered', 'Offered', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_tender_competitor_fit', 'basis', 'presence', 'Presence', NULL, NULL, 4, true, NULL, NULL, false),
    ('market_next_move', 'move_kind', 'register', 'Register', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_next_move', 'move_kind', 'request_documents', 'Request documents', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_next_move', 'move_kind', 'clarify', 'Clarify', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_next_move', 'move_kind', 'find_partner', 'Find partner', NULL, NULL, 4, true, NULL, NULL, false),
    ('market_next_move', 'move_kind', 'confirm_eligibility', 'Confirm eligibility', NULL, NULL, 5, true, NULL, NULL, false),
    ('market_next_move', 'move_kind', 'prepare_bid', 'Prepare bid', NULL, NULL, 6, true, NULL, NULL, false),
    ('market_next_move', 'move_kind', 'monitor', 'Monitor', NULL, NULL, 7, true, NULL, NULL, false),
    ('market_global_requirement', 'stage', 'need_stated', 'Need stated', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_global_requirement', 'stage', 'approved_funded', 'Approved and funded', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_global_requirement', 'stage', 'rfi', 'RFI', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_global_requirement', 'stage', 'rfp_tender', 'RFP / tender', NULL, NULL, 4, true, NULL, NULL, false),
    ('market_global_requirement', 'stage', 'downselect_prototype', 'Down-select / prototype', NULL, NULL, 5, true, NULL, NULL, false),
    ('market_global_requirement', 'stage', 'production_award', 'Production award', NULL, NULL, 6, true, NULL, NULL, false),
    ('market_global_requirement', 'stage', 'delivered', 'Delivered', NULL, NULL, 7, true, NULL, NULL, false),
    ('market_global_requirement', 'stage', 'cancelled', 'Cancelled', NULL, NULL, 8, true, NULL, NULL, false),
    ('market_opportunity', 'stage', 'need_stated', 'Need stated', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_opportunity', 'stage', 'approved_funded', 'Approved and funded', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_opportunity', 'stage', 'rfi', 'RFI', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_opportunity', 'stage', 'rfp_tender', 'RFP / tender', NULL, NULL, 4, true, NULL, NULL, false),
    ('market_opportunity', 'stage', 'downselect_prototype', 'Down-select / prototype', NULL, NULL, 5, true, NULL, NULL, false),
    ('market_opportunity', 'stage', 'production_award', 'Production award', NULL, NULL, 6, true, NULL, NULL, false),
    ('market_opportunity', 'stage', 'delivered', 'Delivered', NULL, NULL, 7, true, NULL, NULL, false),
    ('market_opportunity', 'stage', 'cancelled', 'Cancelled', NULL, NULL, 8, true, NULL, NULL, false),
    ('market_global_requirement', 'status_state', 'current', 'Current', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_global_requirement', 'status_state', 'unconfirmed', 'Unconfirmed', 'watch', NULL, 2, true, NULL, NULL, false),
    ('market_global_requirement_rival', 'basis', 'selected', 'Selected', NULL, NULL, 1, true, NULL, NULL, false),
    ('market_global_requirement_rival', 'basis', 'shortlisted', 'Shortlisted', NULL, NULL, 2, true, NULL, NULL, false),
    ('market_global_requirement_rival', 'basis', 'offered', 'Offered', NULL, NULL, 3, true, NULL, NULL, false),
    ('market_global_requirement_rival', 'basis', 'presence', 'Presence', NULL, NULL, 4, true, NULL, NULL, false),
    ('technology_overview_article', 'horizon', 'lt_2y', 'Under 2 years', NULL, NULL, 1, true, NULL, NULL, false),
    ('technology_overview_article', 'horizon', '2_5y', '2 to 5 years', NULL, NULL, 2, true, NULL, NULL, false),
    ('technology_overview_article', 'horizon', 'gt_5y', 'Over 5 years', NULL, NULL, 3, true, NULL, NULL, false),
    ('technology_overview_article', 'horizon', 'unknown', 'Unknown', NULL, NULL, 4, true, NULL, NULL, false),
    ('technology_overview_article', 'horizon_source', 'stated', 'Stated in the source', NULL, NULL, 1, true, NULL, NULL, false),
    ('technology_overview_article', 'horizon_source', 'rule', 'Derived from maturity', NULL, NULL, 2, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'material', 'Material', NULL, NULL, 1, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'energetics', 'Energetics', NULL, NULL, 2, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'propulsion', 'Propulsion', NULL, NULL, 3, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'guidance_fuze', 'Guidance fuze', NULL, NULL, 4, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'autonomy_ai', 'Autonomy ai', NULL, NULL, 5, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'sensor', 'Sensor', NULL, NULL, 6, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'protection', 'Protection', NULL, NULL, 7, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'manufacturing_process', 'Manufacturing process', NULL, NULL, 8, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'platform_architecture', 'Platform architecture', NULL, NULL, 9, true, NULL, NULL, false),
    ('technology_innovation', 'technology_kind', 'c2_software', 'C2 software', NULL, NULL, 10, true, NULL, NULL, false),
    ('technology_innovation', 'stance', 'watch', 'Watch', NULL, NULL, 1, true, NULL, NULL, false),
    ('technology_innovation', 'stance', 'partner', 'Partner', NULL, NULL, 2, true, NULL, NULL, false),
    ('technology_innovation', 'stance', 'license', 'License', NULL, NULL, 3, true, NULL, NULL, false),
    ('technology_innovation', 'stance', 'develop', 'Develop', NULL, NULL, 4, true, NULL, NULL, false),
    ('technology_innovation', 'stance', 'ignore', 'Ignore', NULL, NULL, 5, true, NULL, NULL, false),
    ('technology_innovation_milestone', 'step_type', 'announced', 'Announced', NULL, NULL, 1, true, NULL, NULL, false),
    ('technology_innovation_milestone', 'step_type', 'prototype', 'Prototype', NULL, NULL, 2, true, NULL, NULL, false),
    ('technology_innovation_milestone', 'step_type', 'trials', 'Trials', NULL, NULL, 3, true, NULL, NULL, false),
    ('technology_innovation_milestone', 'step_type', 'contract', 'Contract', NULL, NULL, 4, true, NULL, NULL, false),
    ('technology_innovation_milestone', 'step_type', 'production', 'Production', NULL, NULL, 5, true, NULL, NULL, false),
    ('technology_innovation_milestone', 'step_type', 'fielded', 'Fielded', NULL, NULL, 6, true, NULL, NULL, false)
        ) AS v(table_name, column_name, code, label, tag_class, tooltip, display_order, is_active, value_from, value_to, is_default)
        ON CONFLICT (table_name, column_name, code) DO NOTHING;
    END IF;
    -- project stage steps beyond Concept / Trials / Contract / Production (A.1.8): the `project` prompt reads this table
    IF to_regclass('staging_ui.ui_project_stage_step') IS NOT NULL THEN
        INSERT INTO staging_ui.ui_project_stage_step (stage_step_id, stage_name, stage_order)
        SELECT v.id, v.name, v.ord FROM (VALUES (5, 'Deliveries', 5), (6, 'In service', 6)) AS v(id, name, ord)
        WHERE NOT EXISTS (SELECT 1 FROM staging_ui.ui_project_stage_step s WHERE s.stage_name = v.name);
    END IF;
END $seed$;
