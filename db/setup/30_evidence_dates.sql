-- Evidence / timeline dates (2026-10-22, owner: "staging should get them"). VPS serving already had these four columns (empty, added
-- there by an ALTER with no migration file); staging and the local serving DB lacked them. Same types as on the VPS. Nothing writes them
-- yet: they are empty until a prompt or code step fills them. Idempotent; staging and serving.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.story_step', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.story_step ADD COLUMN IF NOT EXISTS date_precision text', s);
    END IF;
    IF to_regclass(format('%I.competitive_signal_evidence', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_signal_evidence ADD COLUMN IF NOT EXISTS event_date date', s);
      EXECUTE format('ALTER TABLE %I.competitive_signal_evidence ADD COLUMN IF NOT EXISTS date_precision text', s);
      EXECUTE format('ALTER TABLE %I.competitive_signal_evidence ADD COLUMN IF NOT EXISTS is_expected boolean', s);
    END IF;
  END LOOP;
END $$;
