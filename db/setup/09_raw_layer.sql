-- Raw layer (kssl_staging only, never reviewed, never shown): every harvester writes here first, prompts read from
-- here and write the real tables. Safe to re-run.
--   staging.source_document : one fetched document - news/RSS item, company newsroom post, government page, DC corpus doc
--   staging.tender_raw      : one tender notice from an official API / portal puller (TED, SAM, GeM, OCDS, ...)

CREATE TABLE IF NOT EXISTS staging.source_document (
    doc_id        uuid         PRIMARY KEY,                  -- uuid5(NAMESPACE_URL, canonical url)
    url           text         NOT NULL UNIQUE,              -- canonical article / document URL
    source_kind   text         NOT NULL,                     -- rss | newsroom | gov | trade_press | dc_corpus
    source_name   text,                                      -- publisher / site name
    source_tier   text,                                      -- backend/sources.py tier (primary | independent | ...)
    feed_url      text,                                      -- the feed / listing page / corpus it came from
    origin_ref    text,                                      -- id in the origin system (e.g. DC document id)
    title         text,
    published_at  date,
    language      text,
    body_text     text,                                      -- cleaned main text (capped by the harvester)
    triage        jsonb,                                     -- DC document_triage scores / hints, or harvester notes
    competitor_ids uuid[]      NOT NULL DEFAULT '{}',        -- attribution step: competitors the document is about
    mentions_client boolean,                                 -- attribution step: names the client
    status        text         NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new', 'attributed', 'no_match', 'processed', 'skipped')),
    processed_by  jsonb        NOT NULL DEFAULT '{}'::jsonb, -- {prompt_id: run time} of prompts that used it
    fetched_at    timestamptz  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS source_document_published ON staging.source_document (published_at DESC);
CREATE INDEX IF NOT EXISTS source_document_status ON staging.source_document (status);
CREATE INDEX IF NOT EXISTS source_document_kind ON staging.source_document (source_kind);
CREATE INDEX IF NOT EXISTS source_document_competitors ON staging.source_document USING gin (competitor_ids);

CREATE TABLE IF NOT EXISTS staging.tender_raw (
    raw_id        uuid         PRIMARY KEY,                  -- uuid5(NAMESPACE_URL, source_api || '|' || notice_id)
    source_api    text         NOT NULL,                     -- ted_eu | sam_us | gem_india | ocds_<portal> | canada | ...
    notice_id     text         NOT NULL,
    notice_url    text,
    title         text,
    buyer_name    text,
    country       text,
    published_at  date,
    deadline_at   timestamptz,
    value_text    text,
    cpv_codes     text[],
    defence_tags  text[],                                    -- tag_tenders.py / tenderdefense.py taxonomy
    raw           jsonb,                                     -- the notice as the API returned it
    tender_id     bigint,                                    -- set when a market_tender stub was made from it
    status        text         NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new', 'staged', 'processed', 'skipped')),
    fetched_at    timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (source_api, notice_id)
);
CREATE INDEX IF NOT EXISTS tender_raw_status ON staging.tender_raw (status);
CREATE INDEX IF NOT EXISTS tender_raw_published ON staging.tender_raw (published_at DESC);
