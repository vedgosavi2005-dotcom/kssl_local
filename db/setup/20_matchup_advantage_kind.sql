-- Matchup dossier ANALYTICS panel (user 2026-10-18: "this should be given by prompt only"): the matchup prompt (v4) writes two kinds of
-- lines per side -- 'compared' (a lead on a compared spec, both figures: the ▲ list) and 'stated' (a capability that side's own sources
-- state, never a claim about the other side: the ◆ list). Both come from prompts/matchup_verdict.py only. Staging and serving
-- (Approve copies by column name). Idempotent.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.competitive_matchup_advantage', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_matchup_advantage ADD COLUMN IF NOT EXISTS kind varchar(20)', s);
      EXECUTE format($c$COMMENT ON COLUMN %I.competitive_matchup_advantage.kind IS
        'compared = a lead on a compared spec (both figures); stated = a capability this side''s own sources state. NULL = compared (before v4)'$c$, s);
    END IF;
  END LOOP;
END $$;
