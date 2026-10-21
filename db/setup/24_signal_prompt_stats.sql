-- Per-signal prompt analytics (2026-10-21, the review drawer's "what this card cost"): every staging.prompt_run that touched a signal,
-- by prompt. A run touches a signal when it ran on the signal's article (signal prompt), loaded the signal, loaded its news article
-- (news prompt) or loaded a moment that points at it (moment prompt). A batch run (news, moment) is shared: its tokens, cost and seconds
-- are divided by the number of card rows it loaded, so one news run over 30 articles is not charged 30 times.
-- Staging only (review site); the live site never shows it. Idempotent.
CREATE OR REPLACE VIEW staging.signal_prompt_stats AS
WITH sig AS (
    SELECT s.signal_id, a.article_id
    FROM staging.competitive_signal s
    LEFT JOIN staging.competitive_signal_detail d USING (signal_id)
    LEFT JOIN LATERAL (SELECT n.article_id FROM staging.competitive_news_article n WHERE n.article_url = d.source_url LIMIT 1) a ON true
), loaded AS (
    SELECT r.run_id, e->>'table' AS tbl, e->>'id' AS id, coalesce((e->>'card')::boolean, false) AS card
    FROM staging.prompt_run r
    CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(r.loaded::jsonb) = 'array' THEN r.loaded::jsonb ELSE '[]'::jsonb END) e
), cards AS (
    SELECT run_id, greatest(count(*) FILTER (WHERE card), 1) AS n FROM loaded GROUP BY run_id
), touch AS (
    SELECT sig.signal_id, r.run_id FROM sig JOIN staging.prompt_run r ON r.prompt_id = 'signal' AND r.subject_key = sig.article_id::text
    UNION SELECT sig.signal_id, l.run_id FROM sig JOIN loaded l ON l.tbl = 'competitive_signal' AND l.id = sig.signal_id::text
    UNION SELECT sig.signal_id, l.run_id FROM sig JOIN loaded l ON l.tbl = 'competitive_news_article' AND l.id = sig.article_id::text
    UNION SELECT m.signal_id, l.run_id FROM staging.competitive_competitor_moment m
          JOIN loaded l ON l.tbl = 'competitive_competitor_moment' AND l.id = m.moment_id::text WHERE m.signal_id IS NOT NULL
)
SELECT t.signal_id, r.prompt_id,
       count(*)                                                                    AS runs,
       count(*) FILTER (WHERE r.status = 'failed')                                 AS failures,
       count(*) - count(DISTINCT r.subject_key)                                     AS reruns,
       round(sum(coalesce(r.tokens_in, 0)::numeric / CASE WHEN r.prompt_id = 'signal' THEN 1 ELSE coalesce(c.n, 1) END))  AS tokens_in,
       round(sum(coalesce(r.tokens_out, 0)::numeric / CASE WHEN r.prompt_id = 'signal' THEN 1 ELSE coalesce(c.n, 1) END)) AS tokens_out,
       round(sum(coalesce(r.cost_usd, 0)::numeric / CASE WHEN r.prompt_id = 'signal' THEN 1 ELSE coalesce(c.n, 1) END), 4) AS cost_usd,
       round(sum(coalesce(r.seconds, 0)::numeric / CASE WHEN r.prompt_id = 'signal' THEN 1 ELSE coalesce(c.n, 1) END), 1)  AS seconds,
       string_agg(DISTINCT r.model, ', ')                                           AS models,
       max(r.started_at)                                                            AS last_run_at
FROM touch t
JOIN staging.prompt_run r USING (run_id)
LEFT JOIN cards c USING (run_id)
GROUP BY t.signal_id, r.prompt_id;

COMMENT ON VIEW staging.signal_prompt_stats IS
  'per signal and prompt: runs, failures, reruns, tokens, cost and seconds of every prompt run that touched the signal (batch runs shared per card)';
