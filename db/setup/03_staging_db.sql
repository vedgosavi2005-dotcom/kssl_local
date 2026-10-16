-- kssl_staging: everything is written here (Excel loaders, prompt loaders, the news job, hand inserts).
--   staging.*     = the serving tables      staging_ui.* = the ui tables
--   staging.fact_source, staging.review_decision
-- Run by db/make_databases.sh on a fresh schema build (ui + serving). Safe to re-run.
BEGIN;

DO $$
BEGIN
    IF to_regnamespace('ui') IS NOT NULL AND to_regnamespace('staging_ui') IS NULL THEN
        ALTER SCHEMA ui RENAME TO staging_ui;
    END IF;
    IF to_regnamespace('serving') IS NOT NULL AND to_regnamespace('staging') IS NULL THEN
        ALTER SCHEMA serving RENAME TO staging;
    END IF;
END $$;

-- Per-field sources (one row per table / row id / column / source).
CREATE TABLE IF NOT EXISTS staging.fact_source (
    fact_source_id uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    table_name     text        NOT NULL,
    row_id         text        NOT NULL,
    column_name    text        NOT NULL,
    source_url     text        NOT NULL,
    source_tier    varchar(20),
    publisher      text,
    quote          text,
    document_id    text,
    retrieved_at   timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- A rejection holds the signature of the version that was rejected: a different version
-- written later is pending again. Approvals need no row (the serving DB is the record).
CREATE TABLE IF NOT EXISTS staging.review_decision (
    table_name  text        NOT NULL,
    row_key     text        NOT NULL,
    status      text        NOT NULL CHECK (status = 'rejected'),
    signature   text        NOT NULL,
    decided_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (table_name, row_key)
);

COMMIT;
