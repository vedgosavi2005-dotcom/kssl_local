-- kssl_serving: what the live UI reads. Schemas `ui` and `serving`, plus serving.fact_source.
-- Written only by Approve / Unpublish (backend/review.py): every table here refuses
-- INSERT / UPDATE / DELETE unless the transaction set  kssl.approve = 'on'.
-- TRUNCATE is not blocked (wipe command). Deliberate hand fix of live data:
--   SET kssl.approve = 'on';  ...  RESET kssl.approve;
-- Run by db/make_databases.sh. Safe to re-run (replaces the triggers, never drops data).
BEGIN;

CREATE TABLE IF NOT EXISTS serving.fact_source (
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

CREATE OR REPLACE FUNCTION public.kssl_only_via_approve() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(current_setting('kssl.approve', true), '') <> 'on' THEN
        RAISE EXCEPTION '%.% is the live UI and is written by Approve only. Write it in the staging database (staging.% / staging_ui.%), then approve it in the review copy (http://localhost:5180).',
            TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_TABLE_NAME, TG_TABLE_NAME;
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
