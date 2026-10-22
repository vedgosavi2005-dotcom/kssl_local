-- 33_pipeline_log.sql -- the PIPELINE LOG (owner 22 Oct: "log every inch of the flow, harvest to UI, each step, with timestamps").
-- STAGING DB only (the pipeline writes staging; serving changes only by Approve, which review.py logs here too).
--
--   ops.run           one run of the routine (or one manual script run, as a run of one step)
--   ops.step          one script run: start / end, status, cost, rows inserted / updated / deleted per table, error
--   ops.record_event  every row written: which table + row, insert / update (changed columns) / delete, by which step, when
--                     -- a trigger on every staging / staging_ui / media table; the step comes from the connection setting
--                     kssl.ops_step, which backend/ops_log.py puts in PGOPTIONS for each step's process (no script changes)
--   ops.note          the scripts' own decisions in plain words ("no og:image; used the article's <img>", "image too small 180x90",
--                     "date taken from <meta article:published_time>"), each tied to its step and the record it is about
--
-- Idempotent and DBeaver-safe: IF NOT EXISTS / CREATE OR REPLACE throughout; installing the triggers is a function
-- (ops.install_triggers()) that ops_log calls at every run start, so tables added later are covered too.
-- Writes are never blocked by the log: the trigger only inserts into ops.record_event.

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.run (
    run_id     uuid PRIMARY KEY,
    kind       text NOT NULL CHECK (kind IN ('routine', 'manual', 'api')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    ended_at   timestamptz,
    status     text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'failed', 'partial')),
    args       jsonb,
    host       text,
    git_sha    text,
    cost_usd   numeric,
    notes      text
);

CREATE TABLE IF NOT EXISTS ops.step (
    step_id    uuid PRIMARY KEY,
    run_id     uuid REFERENCES ops.run (run_id) ON DELETE CASCADE,
    name       text NOT NULL,                 -- the routine step name, or the module for a script run on its own
    script     text,                          -- the command, e.g. "backend.harvest_sites --from 2026-10-08"
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    ended_at   timestamptz,
    status     text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'failed', 'skipped', 'usage_limit')),
    exit_code  integer,
    seconds    numeric,
    cost_usd   numeric,                       -- model spend inside the step (staging.prompt_run)
    rows       jsonb,                         -- {"staging.source_document": {"ins": 123, "upd": 4, "del": 0}, ...}
    error      text,                          -- the end of the step's log when it failed
    log_path   text
);
CREATE INDEX IF NOT EXISTS step_run ON ops.step (run_id, started_at);
CREATE INDEX IF NOT EXISTS step_started ON ops.step (started_at);

CREATE TABLE IF NOT EXISTS ops.record_event (
    event_id   bigserial PRIMARY KEY,
    at         timestamptz NOT NULL DEFAULT clock_timestamp(),
    step_id    uuid,                          -- NULL: written outside a logged step (DBeaver, an ad-hoc script)
    tbl        text NOT NULL,                 -- schema.table
    rec_id     text,                          -- the row's key (its primary key, else its *_id column); NULL for truncate
    action     text NOT NULL CHECK (action IN ('insert', 'update', 'delete', 'truncate', 'approve', 'reject', 'unpublish', 'undo')),
    detail     jsonb                          -- update: {"cols": [changed columns]}; review actions: what review.py adds
);
CREATE INDEX IF NOT EXISTS record_event_rec ON ops.record_event (tbl, rec_id, at);
CREATE INDEX IF NOT EXISTS record_event_step ON ops.record_event (step_id);
CREATE INDEX IF NOT EXISTS record_event_at ON ops.record_event (at);

CREATE TABLE IF NOT EXISTS ops.note (
    note_id    bigserial PRIMARY KEY,
    at         timestamptz NOT NULL DEFAULT clock_timestamp(),
    step_id    uuid,
    script     text,                          -- the module that wrote it
    kind       text NOT NULL,                 -- the area: image, date, fetch, harvest, attribution, triage, prompt, translate, ...
    outcome    text NOT NULL,                 -- a short code: og_image, article_img_fallback, too_small, no_image, date_meta, ...
    subject    text,                          -- what it is about, as a person would search it: the page url, a notice id, a name
    tbl        text,                          -- the row it is about, when there is one (schema.table + key)
    rec_id     text,
    message    text NOT NULL,                 -- one plain-English sentence
    detail     jsonb
);
CREATE INDEX IF NOT EXISTS note_step ON ops.note (step_id);
CREATE INDEX IF NOT EXISTS note_subject ON ops.note (subject);
CREATE INDEX IF NOT EXISTS note_rec ON ops.note (tbl, rec_id);
CREATE INDEX IF NOT EXISTS note_at ON ops.note (at);

-- the row trigger: one ops.record_event per row written. TG_ARGV[0] = the key column(s), comma-separated;
-- TG_ARGV[1] = 'heavy' for tables whose rows are large payloads (raw notices): the key is read without turning the row into
-- JSON, and an update records that the row changed, not which columns.
CREATE OR REPLACE FUNCTION ops.log_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    sid   text := nullif(current_setting('kssl.ops_step', true), '');
    keys  text[] := string_to_array(TG_ARGV[0], ',');
    heavy boolean := coalesce(TG_ARGV[1], '') = 'heavy';
    cols  jsonb;
    k     text;
    v     text;
    id    text := NULL;
BEGIN
    IF current_setting('kssl.ops_off', true) = 'on' THEN
        RETURN NULL;
    END IF;
    IF TG_OP = 'TRUNCATE' THEN
        INSERT INTO ops.record_event (step_id, tbl, rec_id, action) VALUES (sid::uuid, TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, NULL, 'truncate');
        RETURN NULL;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF NEW IS NOT DISTINCT FROM OLD THEN
            RETURN NULL;                                   -- an UPDATE that changed nothing is not an event
        END IF;
        IF NOT heavy THEN
            SELECT jsonb_agg(e.key ORDER BY e.key) INTO cols
            FROM jsonb_each(to_jsonb(NEW)) e WHERE e.value IS DISTINCT FROM to_jsonb(OLD) -> e.key;
        END IF;
    END IF;
    FOREACH k IN ARRAY keys LOOP
        IF TG_OP = 'DELETE' THEN
            EXECUTE format('SELECT ($1).%I::text', k) USING OLD INTO v;
        ELSE
            EXECUTE format('SELECT ($1).%I::text', k) USING NEW INTO v;
        END IF;
        id := concat_ws('|', id, v);
    END LOOP;
    INSERT INTO ops.record_event (step_id, tbl, rec_id, action, detail)
    VALUES (sid::uuid, TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, id, lower(TG_OP),
            CASE WHEN cols IS NOT NULL THEN jsonb_build_object('cols', cols) END);
    RETURN NULL;
END $$;

-- (re)install the trigger on every table of staging / staging_ui / media; returns how many tables it covers. Left out:
-- media.image (picture bytes; media.page_image logs every picture taken or refused), staging.prompt_run (itself the log of
-- every model call), staging.review_decision (review.py writes approve / reject events with their reason instead).
CREATE OR REPLACE FUNCTION ops.install_triggers() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    t   record;
    key text;
    n   integer := 0;
BEGIN
    SET LOCAL client_min_messages = warning;
    FOR t IN SELECT c.oid, n.nspname AS s, c.relname AS r
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'r' AND n.nspname IN ('staging', 'staging_ui', 'media')
               AND (n.nspname || '.' || c.relname) NOT IN ('media.image', 'staging.prompt_run', 'staging.review_decision')
    LOOP
        SELECT string_agg(a.attname, ',' ORDER BY array_position(i.indkey::int[], a.attnum::int)) INTO key
        FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
        WHERE i.indrelid = t.oid AND i.indisprimary;
        IF key IS NULL THEN                                -- no primary key (most tables): the first *_id / id column, else the first
            SELECT a.attname INTO key FROM pg_attribute a
            WHERE a.attrelid = t.oid AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY (a.attname = 'id' OR a.attname LIKE '%\_id') DESC, a.attnum LIMIT 1;
        END IF;
        EXECUTE format('DROP TRIGGER IF EXISTS ops_log ON %I.%I', t.s, t.r);
        EXECUTE format('CREATE TRIGGER ops_log AFTER INSERT OR UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION ops.log_change(%L, %L)',
                       t.s, t.r, key, CASE WHEN t.s || '.' || t.r IN ('staging.tender_raw', 'staging.source_document') THEN 'heavy' ELSE '' END);
        EXECUTE format('DROP TRIGGER IF EXISTS ops_log_truncate ON %I.%I', t.s, t.r);
        EXECUTE format('CREATE TRIGGER ops_log_truncate AFTER TRUNCATE ON %I.%I FOR EACH STATEMENT EXECUTE FUNCTION ops.log_change(%L)', t.s, t.r, key);
        n := n + 1;
    END LOOP;
    -- the tables left out lose a trigger an earlier version gave them
    DROP TRIGGER IF EXISTS ops_log ON staging.prompt_run;
    DROP TRIGGER IF EXISTS ops_log_truncate ON staging.prompt_run;
    DROP TRIGGER IF EXISTS ops_log ON staging.review_decision;
    DROP TRIGGER IF EXISTS ops_log_truncate ON staging.review_decision;
    RETURN n;
END $$;

SELECT ops.install_triggers();
