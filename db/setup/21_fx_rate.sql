-- fx_rate: official reference rates, rupees per one unit of each currency, so the Market pillar shows every stated
-- amount in INR (src/lib/tenderValue.js converts only with these; no rate is written in code). Filled by
-- scripts/load_fx_rates.py into staging (ECB euro reference rates crossed through INR; UAH from the National Bank
-- of Ukraine, which the ECB does not quote). A setup table: Approve copies it to serving as a whole table.
-- Idempotent: run on the staging DB (staging schema) and the serving DB (serving schema). Never drops data.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regnamespace(s) IS NULL THEN CONTINUE; END IF;
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I.fx_rate (
        currency_code char(3) PRIMARY KEY,
        inr_per_unit  numeric NOT NULL CHECK (inr_per_unit > 0),
        as_of_date    date NOT NULL,
        source_label  text NOT NULL,
        source_url    text NOT NULL)', s);
    EXECUTE format($c$COMMENT ON TABLE %I.fx_rate IS
      'official reference rate per currency: rupees for one unit (scripts/load_fx_rates.py)'$c$, s);
  END LOOP;
END $$;

-- the live copy is written only by Approve (same guard as db/setup/04_serving_db.sql)
DO $$
BEGIN
  IF to_regprocedure('public.kssl_only_via_approve()') IS NULL OR to_regclass('serving.fx_rate') IS NULL THEN RETURN; END IF;
  DROP TRIGGER IF EXISTS only_via_approve ON serving.fx_rate;
  CREATE TRIGGER only_via_approve BEFORE INSERT OR UPDATE OR DELETE ON serving.fx_rate
    FOR EACH STATEMENT EXECUTE FUNCTION public.kssl_only_via_approve();
END $$;
