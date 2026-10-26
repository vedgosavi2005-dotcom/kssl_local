-- competitive_product.short_name / client_product.short_name: the product's name only, as every page shows it (owner 2026-10-26:
-- "there are still many products which are named long ... wherever the product name shows, shorten them"). Written by
-- backend/product_short_name.py (local model, checked by code: only words of the stored name, the designation kept); NULL = the
-- rule in backend/spec_sheet.display_name applies. Both schemas (Approve copies a card by column name). Additive, idempotent.
DO $$
DECLARE s text; t text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    FOREACH t IN ARRAY ARRAY['competitive_product', 'client_product'] LOOP
      IF to_regclass(format('%I.%I', s, t)) IS NOT NULL THEN
        EXECUTE format('ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS short_name varchar(60)', s, t);
      END IF;
    END LOOP;
  END LOOP;
END $$;
