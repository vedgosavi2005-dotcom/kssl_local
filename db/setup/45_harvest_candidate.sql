-- 45_harvest_candidate.sql -- FREE CANDIDATE FINDER (owner 2026-10-25: "base system -> partners -> source article", done by code).
-- STAGING DB, additive. backend/candidate_finder.py scans the raw layer (staging.source_document: title + the opening ~2,000
-- characters) and writes one row per candidate:
--   kind 'pair' : a tracked competitor and another company (a tracked competitor, a known partner from competitive_partnership,
--                 or the client) named in the same headline / opening paragraph -> a possible partnership;
--   kind 'geo'  : a tracked competitor + a country + a deal word (contract, order, plant, subsidiary, JV, delivery ...) in one
--                 sentence -> a possible geo-footprint / project row.
-- has_existing_row: the pair already has a competitive_partnership row (or the country already shows for the competitor).
-- search_*: the targeted free search for a pair without a row ("A" "B" in DC corpus titles + Google News); what it found is stored
-- as raw source_document rows (source_kind 'pair_search'), never as records. Nothing here is shown on any site.
-- Idempotent and DBeaver-safe (no DELETE / TRUNCATE / approval switch).

CREATE TABLE IF NOT EXISTS staging.harvest_candidate (
    candidate_key       text PRIMARY KEY,           -- kind | competitor_id | normalised other name or country
    kind                text NOT NULL CHECK (kind IN ('pair', 'geo')),
    competitor_id       uuid NOT NULL,
    other_name          text,                       -- pair: the other company as written; geo: NULL
    other_kind          text,                       -- pair: competitor | partner | client
    other_competitor_id uuid,                       -- pair with another tracked competitor
    country             text,                       -- geo: country_reference.country_name
    deal_words          text[] NOT NULL DEFAULT '{}',
    doc_count           integer NOT NULL DEFAULT 0,
    doc_ids             uuid[] NOT NULL DEFAULT '{}',   -- up to 20, newest first
    first_seen          date,
    last_seen           date,
    sample_title        text,
    sample_url          text,
    snippet             text,                       -- the headline / sentence that names both (evidence for a reviewer or a prompt)
    has_existing_row    boolean NOT NULL DEFAULT false,
    search_status       text NOT NULL DEFAULT 'pending' CHECK (search_status IN ('pending', 'searched', 'not_needed')),
    search_found        integer,                    -- new raw documents the targeted search stored
    search_note         text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS harvest_candidate_comp ON staging.harvest_candidate (competitor_id, kind);
CREATE INDEX IF NOT EXISTS harvest_candidate_search ON staging.harvest_candidate (kind, search_status, doc_count DESC);
COMMENT ON TABLE staging.harvest_candidate IS 'code-found partnership / geo candidates from the raw layer (backend/candidate_finder.py); raw leads, not records';
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kssl_app') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON staging.harvest_candidate TO kssl_app';
  END IF;
END $$;

-- Where a news candidate came from (owner 2026-10-26: count per source and per query type). backend/news_sources.py writes one row
-- per (candidate, source, query type) for the candidates IT saved: source google | bing | gdelt | dc_title; query_type company |
-- partner | pair | geo | product. Google News company / product runs of backend/news.py write no row here (they are the rest).
CREATE TABLE IF NOT EXISTS staging.news_candidate_origin (
    candidate_id  uuid NOT NULL,
    source        text NOT NULL,
    query_type    text NOT NULL,
    query         text,
    competitor_id uuid,
    found_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (candidate_id, source, query_type)
);
CREATE INDEX IF NOT EXISTS news_candidate_origin_comp ON staging.news_candidate_origin (competitor_id, query_type);
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kssl_app') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON staging.news_candidate_origin TO kssl_app';
  END IF;
END $$;
