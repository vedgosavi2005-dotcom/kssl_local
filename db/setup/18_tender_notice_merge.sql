-- Duplicate tenders merged (user decision 2026-10-18): re-publications and corrigenda of one procurement are ONE market_tender;
-- each notice stays as a market_tender_source row carrying its own notice number (backend/harvest_tenders.py merge_duplicate_tenders).
-- Idempotent; staging and serving (Approve copies by column name).
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.market_tender_source', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.market_tender_source ADD COLUMN IF NOT EXISTS notice_reference varchar(160)', s);
      EXECUTE format($c$COMMENT ON COLUMN %I.market_tender_source.notice_reference IS
        'the notice number of this source (a tender merged from re-publications / corrigenda keeps one source row per notice)'$c$, s);
    END IF;
  END LOOP;
END $$;
