-- ops.step_history: what the pipeline did, step by step, in the STAGING DB -- the live log (ops.step, 33_pipeline_log.sql) plus
-- steps RECONSTRUCTED from the timestamps the tables already keep (owner 2026-10-22: "backfill, marked reconstructed").
-- A view, not copied rows: it stays current. Read by /api/review/pipeline/* (backend/pipeline_log.py) and the review site's
-- Pipeline log panel. Reconstructed steps are one row per stage per day (the tables keep times per row, not per run).
-- Safe to re-run; picks up ops.step when 33 is applied (re-run this file after 33).
CREATE SCHEMA IF NOT EXISTS ops;

DO $$
DECLARE live text := '';
BEGIN
  IF to_regclass('ops.step') IS NOT NULL THEN
    live := $q$
      SELECT s.step_id::text AS step_id, s.run_id::text AS run_id, s.name, s.script, s.started_at, s.ended_at, s.status,
             (SELECT sum(coalesce((v->>'insert')::bigint, 0) + coalesce((v->>'update')::bigint, 0) + coalesce((v->>'delete')::bigint, 0))
              FROM jsonb_each(coalesce(s.rows, '{}'::jsonb)) e(k, v)) AS rows_out,
             s.cost_usd, coalesce(s.rows, '{}'::jsonb) AS detail, false AS reconstructed
      FROM ops.step s
      UNION ALL $q$;
  END IF;
  EXECUTE 'DROP VIEW IF EXISTS ops.step_history';
  EXECUTE 'CREATE VIEW ops.step_history AS ' || live || $v$
    -- harvest: documents fetched, per harvester per day
    SELECT 'harvest:' || coalesce(d.triage->>'harvester', d.source_kind) || ':' || d.fetched_at::date AS step_id, NULL::text AS run_id,
           'harvest'::text AS name, coalesce(d.triage->>'harvester', d.source_kind) AS script, min(d.fetched_at) AS started_at,
           max(d.fetched_at) AS ended_at, 'ok'::text AS status, count(*)::numeric AS rows_out, NULL::numeric AS cost_usd,
           jsonb_build_object('staging.source_document', count(*), 'kind', min(d.source_kind),
                              'no_match', count(*) FILTER (WHERE d.status = 'no_match')) AS detail, true AS reconstructed
    FROM staging.source_document d WHERE d.fetched_at IS NOT NULL GROUP BY coalesce(d.triage->>'harvester', d.source_kind), d.fetched_at::date
    UNION ALL
    -- tender notices fetched, per source API per day
    SELECT 'tenders:' || coalesce(t.source_api, '?') || ':' || t.fetched_at::date, NULL, 'harvest_tenders', coalesce(t.source_api, '?'),
           min(t.fetched_at), max(t.fetched_at), 'ok', count(*), NULL, jsonb_build_object('staging.tender_raw', count(*)), true
    FROM staging.tender_raw t WHERE t.fetched_at IS NOT NULL GROUP BY t.source_api, t.fetched_at::date
    UNION ALL
    -- triage: documents routed, per day
    SELECT 'triage:' || (d.triage->>'route_at')::date, NULL, 'triage', max(d.triage->>'route_model'),
           min((d.triage->>'route_at')::timestamptz), max((d.triage->>'route_at')::timestamptz), 'ok', count(*), NULL,
           jsonb_build_object('routed', count(*), 'to_none', count(*) FILTER (WHERE d.triage->'route' = '["none"]'::jsonb)), true
    FROM staging.source_document d WHERE d.triage ? 'route_at' GROUP BY (d.triage->>'route_at')::date
    UNION ALL
    -- news candidates found, per day
    SELECT 'news_candidates:' || n.found_at::date, NULL, 'news_candidates', NULL, min(n.found_at), max(n.found_at), 'ok', count(*), NULL,
           jsonb_build_object('staging.news_candidate', count(*)), true
    FROM staging.news_candidate n WHERE n.found_at IS NOT NULL GROUP BY n.found_at::date
    UNION ALL
    -- model prompts: one row per prompt per day, with outcomes, rows loaded and cost
    SELECT 'prompt:' || r.prompt_id || ':' || r.started_at::date, NULL, r.prompt_id, max(r.model), min(r.started_at),
           max(r.started_at + make_interval(secs => coalesce(r.seconds, 0))),
           CASE WHEN count(*) FILTER (WHERE r.status = 'failed') = count(*) THEN 'failed'
                WHEN count(*) FILTER (WHERE r.status = 'failed') > 0 THEN 'partial' ELSE 'ok' END,
           sum(coalesce(r.rows_loaded, 0)), sum(r.cost_usd),
           jsonb_build_object('runs', count(*), 'loaded', count(*) FILTER (WHERE r.status = 'loaded'),
                              'skipped', count(*) FILTER (WHERE r.status = 'skipped'), 'failed', count(*) FILTER (WHERE r.status = 'failed'),
                              'rejected', count(*) FILTER (WHERE r.status = 'rejected'), 'tokens_in', sum(r.tokens_in), 'tokens_out', sum(r.tokens_out)), true
    FROM staging.prompt_run r GROUP BY r.prompt_id, r.started_at::date
    UNION ALL
    -- article images fetched, per day
    SELECT 'images:' || i.fetched_at::date, NULL, 'images', 'backend.media_images', min(i.fetched_at), max(i.fetched_at), 'ok', count(*), NULL,
           jsonb_build_object('media.image', count(*), 'bytes', sum(i.byte_len)), true
    FROM media.image i WHERE i.fetched_at IS NOT NULL GROUP BY i.fetched_at::date
    UNION ALL
    -- translation of market text, per day
    SELECT 'translate:' || o.translated_at::date, NULL, 'translate', 'backend.translate_market', min(o.translated_at), max(o.translated_at), 'ok',
           count(*), NULL, jsonb_build_object('staging.text_original', count(*)), true
    FROM staging.text_original o WHERE o.translated_at IS NOT NULL GROUP BY o.translated_at::date
    UNION ALL
    -- review decisions (reject / undo kept by the review site), per day
    SELECT 'review:' || rd.decided_at::date, NULL, 'review', 'review site', min(rd.decided_at), max(rd.decided_at), 'ok', count(*), NULL,
           jsonb_build_object('rejected', count(*) FILTER (WHERE rd.status = 'rejected'),
                              'other', count(*) FILTER (WHERE coalesce(rd.status, '') <> 'rejected')), true
    FROM staging.review_decision rd WHERE rd.decided_at IS NOT NULL GROUP BY rd.decided_at::date
  $v$;
END $$;

COMMENT ON VIEW ops.step_history IS 'live steps (ops.step) + steps reconstructed from table timestamps (reconstructed = true), one row per stage per day';
