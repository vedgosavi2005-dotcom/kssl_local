-- SIPRI raw layer (owner 2026-10-25: "SIPRI data is my data, which I have gathered, so you can use it completely").
-- A raw copy of the owner's SIPRI harvest (data-centre stack mallory-sipri: Postgres schema sipri + MinIO bucket mallory-sipri),
-- written by backend/sipri_import.py and read by backend/sipri_geo.py (Geo footprint rows, cited to SIPRI). Nothing here is shown
-- on a page by itself and none of these tables is a review card (not in backend/review.py GRAPH), so Approve never copies them.
--
--   sipri_dataset          one row per SIPRI dataset copied: its key, file sha256, MinIO key, harvest time, rows imported
--   sipri_arms_transfer    Arms Transfers Database, one row per trade record (all columns + the API's raw jsonb).
--                          status is SIPRI's weapon condition (N new, S second-hand, R second-hand refurbished), NOT the deal stage;
--                          delivery_yr is the last delivery year on record, 0 = deliveries not complete (ordered / in progress).
--   sipri_top100           Arms Industry Database, Top 100: one row per company and year, as in the yearly sheet (US$ m.)
--   sipri_top100_total     the Top 100's total arms revenues per year (US$ b., current and constant 2024)
--   sipri_milex            Military Expenditure Database: one row per country and year (every sheet of the workbook side by side)
--   sipri_export_value     Financial value of national arms exports: one row per sheet (price basis), country, series and year
--   sipri_armament         the armaments catalogue behind the transfers' designations (designations + sub-categories)
--   sipri_country          SIPRI's country list (names as the transfers use them, ISO3 codes)
--
-- STAGING DB ONLY. Every statement runs inside one DO block that does nothing unless the database is kssl_staging or a kssl_test*
-- copy, so a run on the serving DB (or a DBeaver run that goes on past an error) writes nothing. Additive and idempotent.
DO $$
BEGIN
  IF current_database() <> 'kssl_staging' AND current_database() NOT LIKE 'kssl\_test%' THEN
    RAISE NOTICE '46_sipri_raw.sql: % is not the staging DB, nothing done', current_database();
    RETURN;
  END IF;

  CREATE TABLE IF NOT EXISTS staging.sipri_dataset (
    dataset_key   text PRIMARY KEY,
    title         text,
    source_url    text,
    landing_url   text,
    kind          text,
    sha256        text,
    bytes         bigint,
    minio_key     text,
    row_count     integer,                 -- as the harvester recorded it
    harvested_at  timestamptz,
    imported_rows integer,                 -- rows this copy holds after the last import
    imported_at   timestamptz NOT NULL DEFAULT now()
  );

  CREATE TABLE IF NOT EXISTS staging.sipri_arms_transfer (
    id            bigint PRIMARY KEY,
    trade_id      integer,
    buyer         text,
    seller        text,
    order_yr      integer,
    order_yr_est  boolean,
    units         integer,
    units_est     boolean,
    delivery_yr   integer,
    status        text,
    status_est    boolean,
    desg          text,
    descr         text,
    category      text,
    raw           jsonb,
    harvested_at  timestamptz,
    imported_at   timestamptz NOT NULL DEFAULT now()
  );
  CREATE INDEX IF NOT EXISTS sipri_arms_transfer_seller ON staging.sipri_arms_transfer (seller);
  CREATE INDEX IF NOT EXISTS sipri_arms_transfer_buyer ON staging.sipri_arms_transfer (buyer);

  CREATE TABLE IF NOT EXISTS staging.sipri_top100 (
    year                     integer NOT NULL,
    company                  text    NOT NULL,
    rank                     integer,
    rank_text                text,       -- as printed (a tie or '-' kept)
    rank_prev                integer,
    rank_prev_text           text,
    country                  text,
    arms_revenue_usd_m       numeric,    -- current US$ m. of that year
    arms_revenue_prev_usd_m  numeric,    -- the previous year, as printed in this year's sheet
    total_revenue_usd_m      numeric,
    arms_share               numeric,    -- arms revenues as a share of total revenues (0-1)
    arms_revenue_const_usd_m numeric,    -- constant prices (base year in price_base_note)
    arms_revenue_prev_const_usd_m numeric,
    price_base_note          text,
    notes                    text,
    raw                      jsonb,      -- the sheet row, header -> cell text
    imported_at              timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, company)
  );

  CREATE TABLE IF NOT EXISTS staging.sipri_top100_total (
    year                 integer PRIMARY KEY,
    current_usd_bn       numeric,
    constant_2024_usd_bn numeric,
    imported_at          timestamptz NOT NULL DEFAULT now()
  );

  CREATE TABLE IF NOT EXISTS staging.sipri_milex (
    country              text    NOT NULL,
    year                 integer NOT NULL,
    region               text,
    subregion            text,
    currency             text,
    fiscal_year          text,
    notes                text,
    local_currency_fy    numeric,     -- local currency, current prices, financial years
    local_currency_cy    numeric,     -- local currency, current prices, calendar years
    constant_2024_usd_m  numeric,     -- US$ m., constant 2024 prices and exchange rates
    current_usd_m        numeric,     -- US$ m., current prices and exchange rates
    share_gdp            numeric,     -- share of GDP (0-1)
    per_capita_usd       numeric,     -- current US$
    share_govt_spending  numeric,     -- share of general government spending (0-1)
    raw_text             jsonb,       -- cells that are not numbers ('...', 'xxx'), per sheet
    imported_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (country, year)
  );

  CREATE TABLE IF NOT EXISTS staging.sipri_export_value (
    basis        text    NOT NULL,    -- local_currency | current_usd | constant_usd (the workbook's three sheets)
    country      text    NOT NULL,
    series_no    integer NOT NULL,    -- 1.. the order of the country's series in the sheet
    year         integer NOT NULL,
    series       text,                -- SIPRI's 'Explanation of data' (arms exports, licences, agreements ...)
    sub_label    text,                -- an indented label or a sub-heading above the series, when there is one
    currency     text,
    unit_note    text,                -- the sheet's unit line (e.g. 'Current million US Dollars')
    value        numeric,
    value_text   text,                -- the cell as printed when it is not a plain number ('. .', '<1')
    imported_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (basis, country, series_no, year)
  );

  CREATE TABLE IF NOT EXISTS staging.sipri_armament (
    kind        text NOT NULL,        -- designation | category
    name        text NOT NULL,
    entity_id   bigint,
    code        text,
    type_code   integer,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, name)
  );

  CREATE TABLE IF NOT EXISTS staging.sipri_country (
    entity_id    bigint PRIMARY KEY,
    name         text,
    country_code text,
    deleted      boolean,
    imported_at  timestamptz NOT NULL DEFAULT now()
  );
END $$;
