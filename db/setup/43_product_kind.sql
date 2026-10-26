-- competitive_product.product_kind: what a catalogue row really is (owner 2026-10-25: "figure out what the actual products are";
-- the X-62A VISTA, a one-of-a-kind test aircraft, was listed as a Lockheed Martin product). Written by backend/product_kind.py
-- (local model, checked by code; the reason and the quote it rests on go to staging.fact_source, column product_kind).
--   product         on offer or in service (NULL is read the same way: a row not yet classified)
--   in_development  concept, prototype, demonstrator, in trials (Products: "In development and testing")
--   service         MRO, upgrade, training, engineering or support offered as a service (Products: "Services")
--   test_asset      a one-off research / test vehicle, not for sale (hidden from the client)
--   programme       a programme, contract, bid or competition, not a product (hidden from the client)
--   not_product     a company capability line, a facility, a material list (hidden from the client)
-- Both databases: Approve copies a card by the serving table's column names. Additive and idempotent.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.competitive_product', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_product ADD COLUMN IF NOT EXISTS product_kind varchar(20)', s);
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'competitive_product_kind_chk'
                       AND conrelid = format('%I.competitive_product', s)::regclass) THEN
        EXECUTE format('ALTER TABLE %I.competitive_product ADD CONSTRAINT competitive_product_kind_chk CHECK (product_kind IS NULL OR '
                       'product_kind IN (''product'', ''in_development'', ''service'', ''test_asset'', ''programme'', ''not_product''))', s);
      END IF;
    END IF;
  END LOOP;
END $$;
