-- staging.spec_dictionary: maps a spec label (normalised: casefold, punctuation stripped) of one product category to a
-- canonical key shared by the client and competitor catalogues. Written by `python -m prompts.matchup_code` (the model
-- fills it in batches; the pair comparison itself is code). Staging-only: never copied to the serving database.
-- Applied to kssl_staging by db/make_databases.sh. Safe to re-run.
CREATE TABLE IF NOT EXISTS staging.spec_dictionary (
    category        text         NOT NULL,                 -- the category as stored on client_product (e.g. 'Artillery')
    raw_label_norm  text         NOT NULL,                 -- casefolded label, punctuation removed, spaces collapsed
    canonical_key   text         NOT NULL,                 -- snake_case, shared by both sides (max_range_km, combat_weight ...)
    unit_family     text         NOT NULL CHECK (unit_family IN ('length','mass','speed','time','count','rate','angle','power','ratio','other','text')),
    better          text         NOT NULL CHECK (better IN ('higher','lower','none')),
    comparable      boolean      NOT NULL,                 -- false for descriptive labels (Role, Note, Configuration)
    reason          text,                                  -- one sentence: why that side is better (or why none)
    model           text,                                  -- the model that mapped it, or 'code:skipped' for a label not sent
    created_at      timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (category, raw_label_norm)
);
CREATE INDEX IF NOT EXISTS spec_dictionary_key ON staging.spec_dictionary (category, canonical_key);

-- the loader and the matchup engine delete fact_source rows by (table_name, row_id); without an index every delete scans the table
CREATE INDEX IF NOT EXISTS fact_source_table_row ON staging.fact_source (table_name, row_id);

-- staging.product_class: the like-for-like gate of the code matchup engine (python -m prompts.matchup_code --classify-only).
-- One model pass per product gives its sub-type (a controlled vocabulary per category, defined in prompts/matchup_code.py), calibre,
-- weight class and a reason. A client x competitor pair is made only when category and sub-type match, the calibre matches where it
-- applies, and the weight classes are the same or adjacent. Staging-only.
CREATE TABLE IF NOT EXISTS staging.product_class (
    product_side  text         NOT NULL CHECK (product_side IN ('client', 'competitor')),
    product_id    text         NOT NULL,                   -- client_product_id or competitive_product.product_id, as text
    category      text         NOT NULL,
    sub_type      text         NOT NULL,                   -- from the category's vocabulary, or 'unknown'
    calibre_mm    numeric,                                 -- guns, small arms, ammunition; NULL when not stated or not applicable
    barrel_cal    numeric,                                 -- barrel length in calibres (52 for L/52) when stated
    weight_class  text         NOT NULL,                   -- a band of the category's list, 'n/a', or 'unknown'
    reason        text,
    model         text,
    created_at    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (product_side, product_id)
);
CREATE INDEX IF NOT EXISTS product_class_gate ON staging.product_class (category, sub_type);
