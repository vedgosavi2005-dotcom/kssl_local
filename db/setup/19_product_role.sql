-- Like-for-like gate, second dimension (user rule 2026-10-18): inside a sub-type that mixes roles (towed: ultra-light vs standard;
-- drones: ISR vs cargo vs armed strike; rockets: guided vs unguided ...) two products are compared only when their role is the same.
-- prompts/matchup_class.py ROLES / classify_roles fills it; gate() and matchup_code PAIRS_GATED_SQL read it. Staging only (no UI table).
-- Idempotent.
DO $$
BEGIN
  IF to_regclass('staging.product_class') IS NOT NULL THEN
    ALTER TABLE staging.product_class ADD COLUMN IF NOT EXISTS role varchar(60);
    COMMENT ON COLUMN staging.product_class.role IS
      'role / style inside the sub_type (prompts/matchup_class.py ROLES); NULL where the sub_type has no role split';
  END IF;
END $$;
