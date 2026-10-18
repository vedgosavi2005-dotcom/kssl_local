-- Product drawer (user 2026-10-18): "when I click on a product, first show the product description, then the tech specs, and a special
-- case such as in development written in brackets". description = the Description column of the product spec workbook (backend/excel_load.py,
-- plain text, one bullet per line). status = a non-standard lifecycle state (in development / prototype / concept / trials / retired /
-- cancelled), written only by prompts/product_status.yml with a quote; NULL = nothing special stated. client_product.status already exists.
-- Staging and serving (Approve copies by column name). Idempotent.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.competitive_product', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_product ADD COLUMN IF NOT EXISTS description text', s);
      EXECUTE format('ALTER TABLE %I.competitive_product ADD COLUMN IF NOT EXISTS status varchar(40)', s);
    END IF;
    IF to_regclass(format('%I.client_product', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.client_product ADD COLUMN IF NOT EXISTS description text', s);
    END IF;
  END LOOP;
END $$;
