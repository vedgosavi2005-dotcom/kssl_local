-- serving.product_class: the product types "Compare any two" on Product Evaluation pairs on (owner 2026-10-25: the versus list offers
-- only products that can face the chosen one). Same columns as staging.product_class (10_spec_dictionary.sql + 19_product_role.sql);
-- a setup table (backend/review.py SERVING_TABLES): one Approve copies the whole staging table. Serving DB only. Additive, idempotent.
CREATE TABLE IF NOT EXISTS serving.product_class (
    product_side  text         NOT NULL CHECK (product_side IN ('client', 'competitor')),
    product_id    text         NOT NULL,
    category      text         NOT NULL,
    sub_type      text         NOT NULL,
    calibre_mm    numeric,
    barrel_cal    numeric,
    weight_class  text         NOT NULL,
    reason        text,
    model         text,
    created_at    timestamptz  NOT NULL DEFAULT now(),
    role          varchar(60),
    PRIMARY KEY (product_side, product_id)
);
DROP TRIGGER IF EXISTS only_via_approve ON serving.product_class;
CREATE TRIGGER only_via_approve BEFORE INSERT OR UPDATE OR DELETE ON serving.product_class
    FOR EACH STATEMENT EXECUTE FUNCTION public.kssl_only_via_approve();
