-- competitive_leader_record.headline: varchar(300) -> text (2026-10-22). Five verified experience bullets of the leadership workbook were
-- 301-480 characters (e.g. Gautam Adani's career line) and were held back only for length. Idempotent; staging and serving.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.competitive_leader_record', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_leader_record ALTER COLUMN headline TYPE text', s);
    END IF;
  END LOOP;
END $$;
