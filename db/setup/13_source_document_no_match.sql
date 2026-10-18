-- Lane A (data flood): attribution marks a raw document that names no tracked competitor as 'no_match'.
-- kssl_staging only. Safe to re-run.
ALTER TABLE staging.source_document DROP CONSTRAINT IF EXISTS source_document_status_check;
ALTER TABLE staging.source_document ADD CONSTRAINT source_document_status_check
    CHECK (status IN ('new', 'attributed', 'no_match', 'processed', 'skipped'));
