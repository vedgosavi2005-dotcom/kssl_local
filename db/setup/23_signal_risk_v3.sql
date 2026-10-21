-- Signal risk v3 (2026-10-21, prompts/derive.py signal_assessment / relabel_signals): the label's inputs are resolved by code before
-- "unknown" (move type -> probability / time to effect, named countries -> KSSL market, product classes -> product match), and each
-- signal stores a graded 0-100 risk score, a confidence and the plain-English basis of its label (the review site's "why" panel).
-- Idempotent; run on the staging DB and the serving DB (Approve copies by column name).
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.competitive_signal', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_signal ADD COLUMN IF NOT EXISTS risk_score smallint', s);
      EXECUTE format('ALTER TABLE %I.competitive_signal ADD COLUMN IF NOT EXISTS risk_confidence varchar(8)', s);
      EXECUTE format('ALTER TABLE %I.competitive_signal ADD COLUMN IF NOT EXISTS label_basis jsonb', s);
      EXECUTE format($c$COMMENT ON COLUMN %I.competitive_signal.risk_score IS
        '0-100: probability x impact x time proximity x market fit x product fit, + breadth (rule s3); the threat sort key'$c$, s);
      EXECUTE format($c$COMMENT ON COLUMN %I.competitive_signal.risk_confidence IS
        'high / medium / low: how many of the four label inputs were stated, worked out by code, or unknown (rule s3)'$c$, s);
      EXECUTE format($c$COMMENT ON COLUMN %I.competitive_signal.label_basis IS
        'why the label: resolved inputs (value, basis stated / derived / unknown, how), six plain-English tests, one-line summary (rule s3)'$c$, s);
    END IF;
  END LOOP;
END $$;
