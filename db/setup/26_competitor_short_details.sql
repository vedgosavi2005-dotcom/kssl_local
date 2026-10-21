-- Short company details for the Competitor Profile (2026-10-22, owner: "the company details are written as sentences, make them a single
-- word or short"; the revenue filter was empty because revenue_tier was never filled). The full workbook sentence stays in the *_text
-- columns (shown in Trace); backend/company_short.py writes the short form (local LLM, every figure checked against the sentence) and
-- revenue_usd + revenue_tier (code, staging.fx_rate). Idempotent; staging and serving.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.competitive_competitor', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_competitor ADD COLUMN IF NOT EXISTS starting_year_short varchar(40)', s);
      EXECUTE format('ALTER TABLE %I.competitive_competitor ADD COLUMN IF NOT EXISTS employee_count_short varchar(40)', s);
      EXECUTE format('ALTER TABLE %I.competitive_competitor ADD COLUMN IF NOT EXISTS revenue_short varchar(60)', s);
      EXECUTE format('ALTER TABLE %I.competitive_competitor ADD COLUMN IF NOT EXISTS industry_short varchar(80)', s);
      EXECUTE format('ALTER TABLE %I.competitive_competitor ADD COLUMN IF NOT EXISTS revenue_usd numeric', s);
    END IF;
  END LOOP;
END $$;
