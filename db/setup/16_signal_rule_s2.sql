-- Competitive pillar aligned with the user's spec (2026-10-18), rule s2 (prompts/derive.py signal_label):
--   * threat and watch only: a done event (probability 5) with impact 1-2, or a done favourable move, gets the label 'none'
--     (stored, not shown on the overview); 'fav' is no longer written for competitive signals.
--   * a seventh impact dimension, funding (the spec's "increase in funding" indicator; signal.yml v4 scores it for new signals).
--   * competitor qualification (spec: same product line AND same market), computed by code (prompts/derive_comp.py qualify_competitors).
-- Idempotent; run on the staging DB (staging + staging_ui) and the serving DB (serving): Approve copies by column name.
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['staging', 'serving'] LOOP
    IF to_regclass(format('%I.competitive_signal', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_signal ADD COLUMN IF NOT EXISTS impact_funding smallint', s);
      EXECUTE format($c$COMMENT ON COLUMN %I.competitive_signal.impact_funding IS
        'impact 1-5 of a capital raise or state funding for the rival (signal.yml v4); NULL on signals scored before v4'$c$, s);
    END IF;
    IF to_regclass(format('%I.competitive_competitor', s)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I.competitive_competitor ADD COLUMN IF NOT EXISTS qualifies boolean', s);
      EXECUTE format('ALTER TABLE %I.competitive_competitor ADD COLUMN IF NOT EXISTS qualification_reason text', s);
      EXECUTE format($c$COMMENT ON COLUMN %I.competitive_competitor.qualifies IS
        'spec test, by code: makes a product of the same line (sub-type) as a client product AND is present in a client market; NULL = not testable yet'$c$, s);
    END IF;
  END LOOP;
END $$;

DO $seed$
BEGIN
  IF to_regclass('staging_ui.code_label') IS NOT NULL THEN
    INSERT INTO staging_ui.code_label (table_name, column_name, code, label, tag_class, tooltip, display_order, is_active, value_from, value_to, is_default)
    SELECT v.* FROM (VALUES
      ('competitive_signal', 'classification', 'none', 'Not shown', NULL, 'happened already with low impact: kept, not on the overview', 4, true, NULL::numeric, NULL::numeric, false),
      ('competitive_signal', 'impact_dimension', 'funding', 'Funding', NULL, NULL, 7, true, NULL, NULL, false),
      ('competitive_signal', 'impact_dimension_2', 'funding', 'Funding', NULL, NULL, 7, true, NULL, NULL, false)
    ) AS v(table_name, column_name, code, label, tag_class, tooltip, display_order, is_active, value_from, value_to, is_default)
    WHERE NOT EXISTS (SELECT 1 FROM staging_ui.code_label c
                      WHERE c.table_name = v.table_name AND c.column_name = v.column_name AND c.code = v.code);
    UPDATE staging_ui.code_label SET is_active = false
     WHERE table_name = 'competitive_signal' AND column_name = 'classification' AND code = 'fav';
  END IF;
END $seed$;
