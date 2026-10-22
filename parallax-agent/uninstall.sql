-- Removes everything Parallax Analyst added to the product database: the analytics views,
-- the saved conversations and views (schema parallax_agent) and the read-only agent role.
-- The product's own schemas are not touched.
--   psql "<product DSN>" -f parallax-agent/uninstall.sql
-- If you applied the optional product hook, also run parallax-agent/adapter/product-hook/revert.sh.
DROP SCHEMA IF EXISTS analytics CASCADE;
DROP SCHEMA IF EXISTS parallax_agent CASCADE;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parallax_agent') THEN
    EXECUTE 'DROP OWNED BY parallax_agent';
    EXECUTE 'DROP ROLE parallax_agent';
  END IF;
END $$;
