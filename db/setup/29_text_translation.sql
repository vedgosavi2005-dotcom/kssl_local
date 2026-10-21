-- Market text translated in place (2026-10-22, owner: "some parts of the market pillar are still not translated"). backend/translate_market.py
-- --fields writes the English into the displayed column and keeps the original wording here, per cell, for Trace; text_translation is
-- the cache (one model answer per distinct original, so a buyer named in 40 tenders gets one English form everywhere). Staging only:
-- the review Trace reads it; approved rows carry the English. Idempotent.
CREATE TABLE IF NOT EXISTS staging.text_original (
    table_name  text NOT NULL,
    row_id      text NOT NULL,
    column_name text NOT NULL,
    original    text NOT NULL,
    lang        varchar(8),
    translated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (table_name, row_id, column_name)
);
CREATE TABLE IF NOT EXISTS staging.text_translation (
    original   text PRIMARY KEY,
    kind       varchar(8) NOT NULL,          -- name | text
    lang       varchar(8),
    english    text,
    ok         boolean NOT NULL,             -- false = rejected (a number of the original is missing): the cell keeps its original
    model      text,
    created_at timestamptz NOT NULL DEFAULT now()
);
