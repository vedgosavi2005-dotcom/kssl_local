-- ops.step_history: what the pipeline did, step by step, in the STAGING DB -- the live log (ops.step, 33_pipeline_log.sql) plus
-- steps RECONSTRUCTED from the timestamps the tables already keep (owner 2026-10-22: "backfill, marked reconstructed").
-- A view, not copied rows: it stays current. Read by /api/review/pipeline/* (backend/pipeline_log.py) and the review site's
-- Pipeline log panel. Reconstructed steps are one row per stage per day (the tables keep times per row, not per run).
-- Each part is added only when its table exists in THIS database: the VPS staging DB has no raw layer (source_document,
-- tender_raw, news_candidate, prompt_run are not synced), so there the view is the live log plus what was synced.
-- Safe to re-run; re-run after 33 (or after a table appears) to pick the new parts up.
CREATE SCHEMA IF NOT EXISTS ops;

DO $$
DECLARE parts text[] := '{}';
BEGIN
  IF to_regclass('ops.step') IS NOT NULL THEN parts := array_append(parts, $q$
    SELECT s.step_id::text, s.run_id::text, s.name, s.script, s.started_at, s.ended_at, s.status,
           (SELECT sum(coalesce((v->>'insert')::bigint, 0) + coalesce((v->>'update')::bigint, 0) + coalesce((v->>'delete')::bigint, 0))
              FROM jsonb_each(coalesce(s.rows, '{}'::jsonb)) e(k, v))::numeric,
           s.cost_usd::numeric, coalesce(s.rows, '{}'::jsonb), false
    FROM ops.step s $q$); END IF;
  IF to_regclass('staging.source_document') IS NOT NULL THEN parts := array_append(parts, $q$
    -- harvest: documents fetched, per harvester per day
    SELECT 'harvest:' || coalesce(d.triage->>'harvester', d.source_kind) || ':' || d.fetched_at::date, NULL::text, 'harvest',
           coalesce(d.triage->>'harvester', d.source_kind), min(d.fetched_at), max(d.fetched_at), 'ok', count(*)::numeric, NULL::numeric,
           jsonb_build_object('staging.source_document', count(*), 'kind', min(d.source_kind),
                              'no_match', count(*) FILTER (WHERE d.status = 'no_match')), true
    FROM staging.source_document d WHERE d.fetched_at IS NOT NULL GROUP BY coalesce(d.triage->>'harvester', d.source_kind), d.fetched_at::date $q$);
    parts := array_append(parts, $q$
    -- triage: documents routed, per day
    SELECT 'triage:' || (d.triage->>'route_at')::date, NULL::text, 'triage', max(d.triage->>'route_model'),
           min((d.triage->>'route_at')::timestamptz), max((d.triage->>'route_at')::timestamptz), 'ok', count(*)::numeric, NULL::numeric,
           jsonb_build_object('routed', count(*), 'to_none', count(*) FILTER (WHERE d.triage->'route' = '["none"]'::jsonb)), true
    FROM staging.source_document d WHERE d.triage ? 'route_at' GROUP BY (d.triage->>'route_at')::date $q$); END IF;
  IF to_regclass('staging.tender_raw') IS NOT NULL THEN parts := array_append(parts, $q$
    -- tender notices fetched, per source API per day
    SELECT 'tenders:' || coalesce(t.source_api, '?') || ':' || t.fetched_at::date, NULL::text, 'harvest_tenders', coalesce(t.source_api, '?'),
           min(t.fetched_at), max(t.fetched_at), 'ok', count(*)::numeric, NULL::numeric, jsonb_build_object('staging.tender_raw', count(*)), true
    FROM staging.tender_raw t WHERE t.fetched_at IS NOT NULL GROUP BY t.source_api, t.fetched_at::date $q$); END IF;
  IF to_regclass('staging.news_candidate') IS NOT NULL THEN parts := array_append(parts, $q$
    -- news candidates found, per day
    SELECT 'news_candidates:' || n.found_at::date, NULL::text, 'news_candidates', NULL::text, min(n.found_at), max(n.found_at), 'ok',
           count(*)::numeric, NULL::numeric, jsonb_build_object('staging.news_candidate', count(*)), true
    FROM staging.news_candidate n WHERE n.found_at IS NOT NULL GROUP BY n.found_at::date $q$); END IF;
  IF to_regclass('staging.prompt_run') IS NOT NULL THEN parts := array_append(parts, $q$
    -- model prompts: one row per prompt per day, with outcomes, rows loaded and cost
    SELECT 'prompt:' || r.prompt_id || ':' || r.started_at::date, NULL::text, r.prompt_id, max(r.model), min(r.started_at),
           max(r.started_at + make_interval(secs => coalesce(r.seconds, 0))),
           CASE WHEN count(*) FILTER (WHERE r.status = 'failed') = count(*) THEN 'failed'
                WHEN count(*) FILTER (WHERE r.status = 'failed') > 0 THEN 'partial' ELSE 'ok' END,
           sum(coalesce(r.rows_loaded, 0))::numeric, sum(r.cost_usd)::numeric,
           jsonb_build_object('runs', count(*), 'loaded', count(*) FILTER (WHERE r.status = 'loaded'),
                              'skipped', count(*) FILTER (WHERE r.status = 'skipped'), 'failed', count(*) FILTER (WHERE r.status = 'failed'),
                              'rejected', count(*) FILTER (WHERE r.status = 'rejected'), 'tokens_in', sum(r.tokens_in), 'tokens_out', sum(r.tokens_out)), true
    FROM staging.prompt_run r GROUP BY r.prompt_id, r.started_at::date $q$); END IF;
  IF to_regclass('media.image') IS NOT NULL THEN parts := array_append(parts, $q$
    -- article images fetched, per day
    SELECT 'images:' || i.fetched_at::date, NULL::text, 'images', 'backend.media_images', min(i.fetched_at), max(i.fetched_at), 'ok',
           count(*)::numeric, NULL::numeric, jsonb_build_object('media.image', count(*), 'bytes', sum(i.byte_len)), true
    FROM media.image i WHERE i.fetched_at IS NOT NULL GROUP BY i.fetched_at::date $q$); END IF;
  IF to_regclass('staging.text_original') IS NOT NULL THEN parts := array_append(parts, $q$
    -- translation of market text, per day
    SELECT 'translate:' || o.translated_at::date, NULL::text, 'translate', 'backend.translate_market', min(o.translated_at), max(o.translated_at),
           'ok', count(*)::numeric, NULL::numeric, jsonb_build_object('staging.text_original', count(*)), true
    FROM staging.text_original o WHERE o.translated_at IS NOT NULL GROUP BY o.translated_at::date $q$); END IF;
  IF to_regclass('staging.review_decision') IS NOT NULL THEN parts := array_append(parts, $q$
    -- review decisions (reject / undo kept by the review site), per day
    SELECT 'review:' || rd.decided_at::date, NULL::text, 'review', 'review site', min(rd.decided_at), max(rd.decided_at), 'ok',
           count(*)::numeric, NULL::numeric,
           jsonb_build_object('rejected', count(*) FILTER (WHERE rd.status = 'rejected'),
                              'other', count(*) FILTER (WHERE coalesce(rd.status, '') <> 'rejected')), true
    FROM staging.review_decision rd WHERE rd.decided_at IS NOT NULL GROUP BY rd.decided_at::date $q$); END IF;
  IF coalesce(array_length(parts, 1), 0) = 0 THEN    -- nothing to show yet: an empty view of the same shape
    parts := ARRAY[$q$ SELECT NULL::text, NULL::text, NULL::text, NULL::text, NULL::timestamptz, NULL::timestamptz, NULL::text,
                              NULL::numeric, NULL::numeric, NULL::jsonb, NULL::boolean WHERE false $q$];
  END IF;
  EXECUTE 'DROP VIEW IF EXISTS ops.step_history';
  EXECUTE 'CREATE VIEW ops.step_history (step_id, run_id, name, script, started_at, ended_at, status, rows_out, cost_usd, detail, reconstructed) AS '
          || array_to_string(parts, ' UNION ALL ');
END $$;

COMMENT ON VIEW ops.step_history IS 'live steps (ops.step) + steps reconstructed from table timestamps (reconstructed = true), one row per stage per day';

-- The view is dropped and re-created here (and by every sync, db/sync_staging_to_vps.sh), which drops its grants: give the
-- app role (the VPS APIs run as kssl_app) read access again each time.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kssl_app') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA ops TO kssl_app';
    EXECUTE 'GRANT SELECT ON ops.step_history TO kssl_app';
  END IF;
END $$;
