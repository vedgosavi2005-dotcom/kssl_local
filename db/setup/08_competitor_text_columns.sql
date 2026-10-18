-- Competitor company details shown as the client's text (qualifiers kept: "More than 7,000 employees", "EUR 2.1 billion - segment revenue").
-- Adds four text columns to competitive_competitor; the number columns (starting_year, employee_count, annual_revenue) stay for filters and are
-- filled only when the text states a plain figure.  Idempotent; applied to the staging DB (schema staging) AND the serving DB (schema serving):
-- the DO block alters whichever of staging.competitive_competitor / serving.competitive_competitor exists in the database it runs in.
-- Local: db/make_databases.sh.  VPS: python -m prompts.batch sql db/setup/08_competitor_text_columns.sql --db vps  (tunnel open), once per database.
-- No existing column needed widening for the current workbook (longest values: origin_country 12/100, headquarters 139/250, industry_sector 176/200).
DO $$
DECLARE s text;
BEGIN
    FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
        IF to_regclass(s || '.competitive_competitor') IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %I.competitive_competitor
                ADD COLUMN IF NOT EXISTS starting_year_text text,
                ADD COLUMN IF NOT EXISTS employee_count_text text,
                ADD COLUMN IF NOT EXISTS revenue_text text,
                ADD COLUMN IF NOT EXISTS financial_year varchar(120)', s);
        END IF;
    END LOOP;
END $$;
