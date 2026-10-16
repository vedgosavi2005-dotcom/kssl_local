-- The docx schema gives the same reference two types in a few places, so joins can never match
-- (e.g. competitive_project.competitor_id bigint vs competitive_competitor.competitor_id uuid).
-- Rule: the referencing column takes the type of the record it points to. Applied to the live
-- schema and its staged copy alike (Approve copies rows between them, so they must match).
-- The tables were empty when this was written; a non-empty table makes it fail rather than
-- guess values (USING NULL would erase data).
BEGIN;

DO $$
DECLARE
    s text;
    c record;
    n bigint;
BEGIN
    FOR s IN SELECT unnest(ARRAY['serving', 'staging']) LOOP
        FOR c IN SELECT * FROM (VALUES
            -- table                              column                   new type  points to
            ('competitive_competitor_moment',     'competitor_id',         'uuid'),   -- competitive_competitor
            ('competitive_geo_company_presence',  'competitor_id',         'uuid'),   -- competitive_competitor
            ('competitive_project',               'competitor_id',         'uuid'),   -- competitive_competitor
            ('competitive_matchup',               'competitor_product_id', 'uuid'),   -- competitive_product
            ('market_tender_competitor_fit',      'competitor_product_id', 'uuid'),   -- competitive_product
            ('competitive_product_news',          'matchup_id',            'bigint'), -- competitive_matchup
            ('technology_overview_article',       'category_id',           'bigint'), -- technology_category
            ('market_global_requirement',         'requirement_id',        'bigint')  -- its _source / _specification rows
        ) AS v(tbl, col, typ) LOOP
            EXECUTE format('SELECT count(*) FROM %I.%I WHERE %I IS NOT NULL', s, c.tbl, c.col) INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION '%.%.% has % value(s); convert them by hand first', s, c.tbl, c.col, n;
            END IF;
            EXECUTE format('ALTER TABLE %I.%I ALTER COLUMN %I TYPE %s USING NULL', s, c.tbl, c.col, c.typ);
        END LOOP;
    END LOOP;
END $$;

COMMIT;
