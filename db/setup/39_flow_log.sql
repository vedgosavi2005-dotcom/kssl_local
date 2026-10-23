-- 39_flow_log.sql -- the Flow dashboard's log (owner 2026-10-24: "a proper dashboard of our Flow ... each and every log").
-- STAGING DB, schema ops (33_pipeline_log.sql). Idempotent and DBeaver-safe.
--   ops.step.output  the step's WHOLE console output (33 kept only the last 4,000 characters of a failed step in error);
--                    written by backend/ops_log.finish_step for routine steps and for scripts run on their own
--   ops.note.level   info / warn / error, so the dashboard can list every warning and error a script reported

ALTER TABLE ops.step ADD COLUMN IF NOT EXISTS output text;
ALTER TABLE ops.note ADD COLUMN IF NOT EXISTS level text NOT NULL DEFAULT 'info';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'note_level_check') THEN
    ALTER TABLE ops.note ADD CONSTRAINT note_level_check CHECK (level IN ('info', 'warn', 'error'));
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS note_level ON ops.note (level, at) WHERE level <> 'info';
