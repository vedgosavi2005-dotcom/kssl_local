-- Review flow for the KSSL schema (kssl_schema_from_docx.sql): one database, staged writes.
--
--   staging.*     mirror of serving.*   written by loaders, the news job and hand inserts
--   staging_ui.*  mirror of ui.*        written by hand inserts (page config, metrics)
--   serving.* / ui.*                    what the live UI shows; written only by Approve /
--                                       Unpublish in the review copy (backend/review.py)
--
-- serving.* and ui.* refuse INSERT / UPDATE / DELETE unless the transaction set
-- kssl.approve = 'on' (the review backend does). TRUNCATE is not blocked (wipe command).
-- Deliberate hand fix of live data:  SET kssl.approve = 'on';  ...  RESET kssl.approve;
-- Run after kssl_schema_from_docx.sql. Safe to re-run (creates only what is missing).
BEGIN;

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS staging_ui;

DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('serving', 'ui') LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS %I.%I (LIKE %I.%I INCLUDING ALL)',
                       CASE r.schemaname WHEN 'serving' THEN 'staging' ELSE 'staging_ui' END,
                       r.tablename, r.schemaname, r.tablename);
    END LOOP;
END $$;

-- Per-field sources and review decisions live with the staged data.
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
CREATE TABLE IF NOT EXISTS serving.fact_source (LIKE staging.fact_source INCLUDING ALL);

-- A rejection holds the signature of the version that was rejected: a different version
-- written later is pending again. Approvals need no row (serving / ui are the record).
CREATE TABLE IF NOT EXISTS staging.review_decision (
    table_name  text        NOT NULL,
    row_key     text        NOT NULL,
    status      text        NOT NULL CHECK (status = 'rejected'),
    signature   text        NOT NULL,
    decided_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (table_name, row_key)
);

CREATE OR REPLACE FUNCTION public.kssl_only_via_approve() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(current_setting('kssl.approve', true), '') <> 'on' THEN
        RAISE EXCEPTION '%.% is the live UI and is written by Approve only. Write to %.% instead, then approve it in the review copy (http://localhost:5180).',
            TG_TABLE_SCHEMA, TG_TABLE_NAME,
            CASE TG_TABLE_SCHEMA WHEN 'serving' THEN 'staging' ELSE 'staging_ui' END, TG_TABLE_NAME;
    END IF;
    RETURN NULL;
END $$;

DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('serving', 'ui') LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS only_via_approve ON %I.%I', r.schemaname, r.tablename);
        EXECUTE format('CREATE TRIGGER only_via_approve BEFORE INSERT OR UPDATE OR DELETE ON %I.%I
                        FOR EACH STATEMENT EXECUTE FUNCTION public.kssl_only_via_approve()',
                       r.schemaname, r.tablename);
    END LOOP;
END $$;

COMMIT;
