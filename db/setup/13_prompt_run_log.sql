-- Full per-run logging for the prompt runner (prompts/run.py log_run / run_totals).
-- tokens_in / tokens_out / cost_usd / seconds already exist; these split them further.
-- details.calls keeps one entry per model call (usage, api_ms, turns, stop_reason, session_id).
ALTER TABLE staging.prompt_run
  ADD COLUMN IF NOT EXISTS finished_at        timestamptz,
  ADD COLUMN IF NOT EXISTS tokens_fresh_in    integer,
  ADD COLUMN IF NOT EXISTS tokens_cache_read  integer,
  ADD COLUMN IF NOT EXISTS tokens_cache_write integer,
  ADD COLUMN IF NOT EXISTS web_searches       integer,
  ADD COLUMN IF NOT EXISTS num_turns          integer,
  ADD COLUMN IF NOT EXISTS attempts           integer,
  ADD COLUMN IF NOT EXISTS api_seconds        numeric(8,1),
  ADD COLUMN IF NOT EXISTS render_seconds     numeric(8,1),
  ADD COLUMN IF NOT EXISTS model_seconds      numeric(8,1),
  ADD COLUMN IF NOT EXISTS load_seconds       numeric(8,1),
  ADD COLUMN IF NOT EXISTS rows_by_table      jsonb;

-- one row per prompt: how many runs, outcome mix, time, tokens, cost
CREATE OR REPLACE VIEW staging.prompt_run_stats AS
SELECT prompt_id, model,
       count(*)                                         AS runs,
       count(*) FILTER (WHERE status = 'loaded')        AS loaded,
       count(*) FILTER (WHERE status = 'skipped')       AS skipped,
       count(*) FILTER (WHERE status IN ('failed','rejected')) AS failed,
       sum(rows_loaded)                                 AS rows_loaded,
       round(avg(seconds), 1)                           AS avg_seconds,
       round(sum(seconds) / 3600, 2)                    AS total_hours,
       round(avg(tokens_in))                            AS avg_tokens_in,
       round(avg(tokens_out))                           AS avg_tokens_out,
       sum(tokens_in)                                   AS total_tokens_in,
       sum(tokens_out)                                  AS total_tokens_out,
       sum(tokens_cache_read)                           AS total_cache_read,
       sum(web_searches)                                AS total_web_searches,
       round(avg(cost_usd), 4)                          AS avg_cost_usd,
       round(sum(cost_usd), 2)                          AS total_cost_usd,
       min(started_at)                                  AS first_run,
       max(started_at)                                  AS last_run
FROM staging.prompt_run
GROUP BY prompt_id, model;
