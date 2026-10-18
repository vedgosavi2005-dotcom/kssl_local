-- One category vocabulary = the client Excel's 10 categories (decision 2026-10-17, docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md A.0.1).
--   Artillery, Ammunition, Protected & Armoured Vehicles, Armoured Vehicle MRO, Small Arms, Marine / Naval,
--   Missiles & Air Defence, UAVs & Drones, Precision Components & Forgings, Other
-- client_product.category, competitive_product.category, spec_dictionary.category and product_class.category already use
-- these strings. This file brings staging.technology_category (+ the staging_ui mirror tables) and every stored text that
-- still holds an old category name in line:
--     ids 1-6 are KEPT (market_tender.category_id, technology_innovation.category_id ... point at them) and renamed in place
--     1 Artillery  2 Ammunition  3 Armoured Vehicles -> Protected & Armoured Vehicles  4 Small Arms
--     5 Unmanned & Counter-UAS -> UAVs & Drones  6 Missiles & Air Defence
--     7 Armoured Vehicle MRO  8 Marine / Naval  9 Precision Components & Forgings  10 Other (inactive: a catch-all, not a technology tab)
-- Applied to kssl_staging only by db/make_databases.sh (serving gets the new vocabulary through Approve). Idempotent: a re-run
-- changes nothing. Run history text (prompt_run.prompt_text / raw_output / skip_reason) is a log and is left as written.

-- 1. technology_category (staging): rename ids 1-6 in place, add 7-10 --------------------------------------------------------------
BEGIN;
CREATE TEMP TABLE _vocab (category_id bigint, category_code text, category_name text, is_active boolean) ON COMMIT DROP;
INSERT INTO _vocab VALUES
    (1,  'artillery',                     'Artillery',                       true),
    (2,  'ammunition',                    'Ammunition',                      true),
    (3,  'protected-armoured-vehicles',   'Protected & Armoured Vehicles',   true),
    (4,  'small-arms',                    'Small Arms',                      true),
    (5,  'uavs-drones',                   'UAVs & Drones',                   true),
    (6,  'missiles-air-defence',          'Missiles & Air Defence',          true),
    (7,  'armoured-vehicle-mro',          'Armoured Vehicle MRO',            true),
    (8,  'marine-naval',                  'Marine / Naval',                  true),
    (9,  'precision-components-forgings', 'Precision Components & Forgings', true),
    (10, 'other',                         'Other',                           false);

UPDATE staging.technology_category t
   SET category_code = v.category_code, category_name = v.category_name, canonical_name = v.category_name
  FROM _vocab v
 WHERE t.category_id = v.category_id
   AND (t.category_code, t.category_name, t.canonical_name) IS DISTINCT FROM (v.category_code, v.category_name, v.category_name);

INSERT INTO staging.technology_category (category_id, category_code, category_name, canonical_name, category_number, display_order, is_active, tab_number)
SELECT v.category_id, v.category_code, v.category_name, v.category_name, v.category_id, v.category_id, v.is_active, v.category_id
  FROM _vocab v
 WHERE NOT EXISTS (SELECT 1 FROM staging.technology_category t WHERE t.category_id = v.category_id);

-- 2. the staging_ui mirror and the two ui_label tables. They are empty until a roll-up fills them; when they hold rows the
--    same ids are renamed in place and 7-10 added, so the three copies never disagree.
UPDATE staging_ui.technology_category t SET category_name = v.category_name
  FROM _vocab v WHERE t.category_id = v.category_id::text AND t.category_name IS DISTINCT FROM v.category_name;
INSERT INTO staging_ui.technology_category (category_id, category_name, display_order, tab_number)
SELECT v.category_id::text, v.category_name, v.category_id, v.category_id
  FROM _vocab v
 WHERE EXISTS (SELECT 1 FROM staging_ui.technology_category)
   AND NOT EXISTS (SELECT 1 FROM staging_ui.technology_category t WHERE t.category_id = v.category_id::text);

UPDATE staging_ui.technology_category_ui_label l SET ui_name = v.category_name, database_category_id = v.category_code
  FROM _vocab v WHERE l.tab_number = v.category_id AND (l.ui_name, l.database_category_id) IS DISTINCT FROM (v.category_name, v.category_code);
INSERT INTO staging_ui.technology_category_ui_label (database_category_id, tab_number, ui_name)
SELECT v.category_code, v.category_id, v.category_name
  FROM _vocab v
 WHERE EXISTS (SELECT 1 FROM staging_ui.technology_category_ui_label)
   AND NOT EXISTS (SELECT 1 FROM staging_ui.technology_category_ui_label l WHERE l.tab_number = v.category_id);

UPDATE staging.technology_category_ui_label l
   SET label_text = v.category_name, ui_name = v.category_name, database_category_id = v.category_code,
       short_label = CASE WHEN l.short_label = l.label_text OR l.short_label IS NULL THEN v.category_name ELSE l.short_label END
  FROM _vocab v WHERE l.category_id = v.category_id
   AND (l.label_text, l.ui_name, l.database_category_id) IS DISTINCT FROM (v.category_name, v.category_name, v.category_code);
INSERT INTO staging.technology_category_ui_label (category_id, category_label_id, database_category_id, label_text, locale, short_label, sort_order, tab_number, ui_name)
SELECT v.category_id, v.category_id, v.category_code, v.category_name, 'en', v.category_name, v.category_id, v.category_id, v.category_name
  FROM _vocab v
 WHERE EXISTS (SELECT 1 FROM staging.technology_category_ui_label)
   AND NOT EXISTS (SELECT 1 FROM staging.technology_category_ui_label l WHERE l.category_id = v.category_id);

-- 3. every stored text that holds an old category name (exact value) --------------------------------
--    Found by scanning every text column of staging / staging_ui; these are the ones that hold a category name:
DO $$
DECLARE
    n bigint;
    cols text[] := ARRAY[
        'staging.competitive_competitor_moment.category',
        'staging.competitive_signal.category',
        'staging.competitive_geo_product.product_range',
        'staging.competitive_geo_company_presence.matched_ranges',
        'staging.competitive_product.category',
        'staging.competitive_product.category_filter',
        'staging.competitive_product_evaluation.category',
        'staging.client_product.category',
        'staging.client_partner_relationship.category',
        'staging.market_global_requirement.category',
        'staging.market_tender.category_text',
        'staging.market_tender_requirement.category_text',
        'staging.technology_overview_article.category_text',
        'staging.competitive_patent_classification.category_label',
        'staging.technology_overview_fact.fact_value'];            -- only rows with fact_key = 'category' (see below)
    olds text[] := ARRAY['Armoured Vehicles', 'Unmanned & Counter-UAS'];
    news text[] := ARRAY['Protected & Armoured Vehicles', 'UAVs & Drones'];
    c text; i int; sch text; tbl text; col text; extra text;
BEGIN
    FOREACH c IN ARRAY cols LOOP
        sch := split_part(c, '.', 1); tbl := split_part(c, '.', 2); col := split_part(c, '.', 3);
        extra := CASE WHEN c = 'staging.technology_overview_fact.fact_value' THEN ' AND fact_key = ''category''' ELSE '' END;
        FOR i IN 1 .. array_length(olds, 1) LOOP
            EXECUTE format('UPDATE %I.%I SET %I = %L WHERE %I = %L%s', sch, tbl, col, news[i], col, olds[i], extra);
            GET DIAGNOSTICS n = ROW_COUNT;
            IF n > 0 THEN RAISE NOTICE '12_vocabulary: %.%.%  "%" -> "%" : % row(s)', sch, tbl, col, olds[i], news[i], n; END IF;
        END LOOP;
    END LOOP;
END $$;

COMMIT;
