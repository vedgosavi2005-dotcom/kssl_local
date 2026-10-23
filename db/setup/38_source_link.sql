-- Dead source links (owner 2026-10-23: a signal's source gave 404 -- Army Recognition took the article down after we read it).
-- scripts/check_source_links.py checks every source URL the sites show; a URL the publisher no longer serves (404 / 410) gets
-- the Internet Archive copy of the same page, taken before it went. Both APIs swap the dead URL for archive_url in what they
-- send (backend/app.py), so the source stays the article we read, and the stored source_url is never rewritten.
-- STAGING DB only (both APIs read it, as they do media.image); synced to the VPS with the staging schema. Safe to re-run.
CREATE TABLE IF NOT EXISTS staging.source_link (
    url          text PRIMARY KEY,
    status       int,                 -- HTTP status after redirects; 0 = no answer
    archive_url  text,                -- web.archive.org snapshot of url, when it is dead and one exists
    archived_at  timestamptz,         -- when that snapshot was taken
    checked_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE staging.source_link IS 'source URL health; dead URLs (404/410) are served as their archive_url';
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kssl_app') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON staging.source_link TO kssl_app';
  END IF;
END $$;
