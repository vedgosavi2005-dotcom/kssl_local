-- 35_glance_who_wider.sql -- At a glance "Who" names every firm making the same move (owner 22 Oct: the loitering-munition
-- contracts were signed with Tata Advanced Systems AND NIBE; Who showed Tata only). prompts/signal.yml v5 allows 80 characters.
-- Widening a varchar is safe to re-run; runs on both DBs (staging and serving).
DO $$
BEGIN
    IF to_regclass('staging.competitive_signal_detail') IS NOT NULL THEN
        ALTER TABLE staging.competitive_signal_detail ALTER COLUMN glance_who TYPE varchar(80);
    END IF;
    IF to_regclass('serving.competitive_signal_detail') IS NOT NULL THEN
        ALTER TABLE serving.competitive_signal_detail ALTER COLUMN glance_who TYPE varchar(80);
    END IF;
END $$;
