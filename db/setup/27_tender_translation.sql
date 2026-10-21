-- Tender translation (2026-10-22, owner: "in market pillar majority data is not translated; use a local LLM"). backend/translate_market.py
-- keeps the original-language text in title_localized / description_localized, writes the English into title / description, and
-- records the source language in text_lang ('en' = already English, no model call). Idempotent; staging and serving.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.market_tender', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.market_tender ADD COLUMN IF NOT EXISTS description_localized text', s);
      EXECUTE format('ALTER TABLE %I.market_tender ADD COLUMN IF NOT EXISTS text_lang varchar(8)', s);
    END IF;
  END LOOP;
END $$;
