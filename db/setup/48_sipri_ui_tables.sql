-- SIPRI figures on the pages (owner 2026-10-26): a competitor's arms revenue / Top-100 rank / arms share (Company profile) and a
-- country's military expenditure (Geo footprint country panel). Two small SETUP tables (backend/review.py SERVING_TABLES): built in
-- staging by backend/sipri_ui.py from the raw copy (46_sipri_raw.sql), one Approve on the review site copies a whole table to serving.
--
--   sipri_arms_company   one row per competitor and year (latest year + up to 5 earlier ones) of ONE SIPRI Top-100 entity: the
--                        company itself ('own'), its parent group ('parent': KNDS, Hanwha Group, ThyssenKrupp, Oshkosh Corp., Diehl)
--                        or its predecessor ('predecessor': Indian Ordnance Factories for MIL / AWEIL). Never a parent's figure as
--                        the subsidiary's own: the page names the entity.
--   sipri_milex_country  one row per country (as the geo page names it) and year from 2015: military expenditure, current and constant
--                        US$ m., share of GDP, per capita.
--
-- Runs on both databases: the staging tables where schema staging exists, the serving copies (written only by Approve: trigger
-- only_via_approve, like 44_product_class_serving.sql) where schema serving and public.kssl_only_via_approve exist. Same columns on
-- both sides (Approve copies by column name). Additive and idempotent; nothing is deleted.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regnamespace(s) IS NULL THEN
      CONTINUE;
    END IF;
    IF s = 'serving' AND to_regproc('public.kssl_only_via_approve') IS NULL THEN
      RAISE NOTICE '48_sipri_ui_tables.sql: schema serving without public.kssl_only_via_approve, serving tables not created';
      CONTINUE;
    END IF;
    EXECUTE format($t$CREATE TABLE IF NOT EXISTS %I.sipri_arms_company (
        competitor_id        uuid    NOT NULL,
        year                 integer NOT NULL,
        sipri_company        text    NOT NULL,
        relation             text    NOT NULL CHECK (relation IN ('own', 'parent', 'predecessor')),
        rank                 integer,
        arms_revenue_usd_m   numeric,
        total_revenue_usd_m  numeric,
        arms_share           numeric,
        sipri_country        text,
        source_label         text    NOT NULL,
        source_url           text    NOT NULL,
        PRIMARY KEY (competitor_id, year))$t$, s);
    EXECUTE format($t$CREATE TABLE IF NOT EXISTS %I.sipri_milex_country (
        country_name         text    NOT NULL,
        year                 integer NOT NULL,
        sipri_country        text    NOT NULL,
        current_usd_m        numeric,
        constant_2024_usd_m  numeric,
        share_gdp            numeric,
        per_capita_usd       numeric,
        source_label         text    NOT NULL,
        source_url           text    NOT NULL,
        PRIMARY KEY (country_name, year))$t$, s);
    IF s = 'serving' THEN
      EXECUTE 'DROP TRIGGER IF EXISTS only_via_approve ON serving.sipri_arms_company';
      EXECUTE 'CREATE TRIGGER only_via_approve BEFORE INSERT OR UPDATE OR DELETE ON serving.sipri_arms_company
               FOR EACH STATEMENT EXECUTE FUNCTION public.kssl_only_via_approve()';
      EXECUTE 'DROP TRIGGER IF EXISTS only_via_approve ON serving.sipri_milex_country';
      EXECUTE 'CREATE TRIGGER only_via_approve BEFORE INSERT OR UPDATE OR DELETE ON serving.sipri_milex_country
               FOR EACH STATEMENT EXECUTE FUNCTION public.kssl_only_via_approve()';
    END IF;
  END LOOP;
END $$;
