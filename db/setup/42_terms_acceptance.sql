-- activity.terms_acceptance: who accepted which version of the platform terms, and when (owner 2026-10-25: the login page's
-- Terms & Conditions step, "saved on the server"). Written by POST /api/terms/accept (backend/auth.py) for the signed-in user;
-- read at sign-in to decide whether the terms page is shown. Not reviewed content: outside serving/ui, never approved or synced;
-- each database keeps its own API's rows (live API -> kssl_serving). Safe to re-run.
CREATE SCHEMA IF NOT EXISTS activity;

CREATE TABLE IF NOT EXISTS activity.terms_acceptance (
    user_name      text        NOT NULL,
    terms_version  text        NOT NULL,              -- backend/auth.py TERMS_VERSION; a new version asks every user again
    accepted_at    timestamptz NOT NULL DEFAULT now(),
    user_agent     text,
    PRIMARY KEY (user_name, terms_version)
);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kssl_app') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA activity TO kssl_app';
    EXECUTE 'GRANT SELECT, INSERT ON activity.terms_acceptance TO kssl_app';
  END IF;
END $$;
