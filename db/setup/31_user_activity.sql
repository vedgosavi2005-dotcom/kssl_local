-- activity.event: what people do on the site -- page views, clicks, searches, hovers, time on page. First-party and anonymous
-- (a random browser id, no login, no IP stored). It is NOT reviewed content: it sits outside serving/ui (no only_via_approve
-- guard), is never approved, published or synced; each database keeps the events of the API that connects to it
-- (live API -> kssl_serving, review API -> kssl_staging). Written by POST /api/track (backend/app.py) from src/lib/track.js.
-- How to read it: docs/ui_port/ACTIVITY_LOG.md.  Safe to re-run.
CREATE SCHEMA IF NOT EXISTS activity;

CREATE TABLE IF NOT EXISTS activity.event (
    event_id     bigserial   PRIMARY KEY,
    received_at  timestamptz NOT NULL DEFAULT now(),       -- server clock (use this one for time series)
    client_ts    timestamptz,                               -- browser clock, when the event happened (a batch arrives later)
    site         text        NOT NULL CHECK (site IN ('live', 'review')),
    visitor_id   uuid        NOT NULL,                      -- random id kept in that browser (localStorage); not a person
    session_id   uuid        NOT NULL,                      -- random per visit; a new one after 30 minutes idle
    event_type   text        NOT NULL CHECK (event_type IN ('page_view', 'leave', 'click', 'search', 'hover')),
    pillar       text,                                      -- route at the time: competitive / market / technology
    view         text,                                      -- route view: overview, profile, tender, ...
    target       text,                                      -- what was clicked / hovered / searched in (a label, <= 160)
    value        text,                                      -- search text, or the card / item id (<= 300)
    duration_ms  integer,                                   -- hover dwell, or time spent on the view ('leave')
    props        jsonb,                                     -- small extras: element kind, viewport, referrer
    user_agent   text
);
CREATE INDEX IF NOT EXISTS event_received ON activity.event (received_at);
CREATE INDEX IF NOT EXISTS event_session ON activity.event (session_id, received_at);
CREATE INDEX IF NOT EXISTS event_type_time ON activity.event (event_type, received_at);

-- ---- insight views (each answers one question; filter on site = 'live' for clients) -------------------------------------

-- Who comes, how often: one row per site and day.
CREATE OR REPLACE VIEW activity.v_daily AS
SELECT site, received_at::date AS day,
       count(DISTINCT visitor_id) AS visitors, count(DISTINCT session_id) AS sessions,
       count(*) FILTER (WHERE event_type = 'page_view') AS page_views,
       count(*) FILTER (WHERE event_type = 'click') AS clicks,
       count(*) FILTER (WHERE event_type = 'search') AS searches
FROM activity.event GROUP BY 1, 2;

-- Which pages matter: views, distinct visitors and median time on page.
CREATE OR REPLACE VIEW activity.v_pages AS
SELECT site, pillar, view,
       count(*) FILTER (WHERE event_type = 'page_view') AS views,
       count(DISTINCT visitor_id) FILTER (WHERE event_type = 'page_view') AS visitors,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) FILTER (WHERE event_type = 'leave') AS median_time_ms
FROM activity.event GROUP BY 1, 2, 3;

-- What people look for (and, with zero clicks after it, do not find).
CREATE OR REPLACE VIEW activity.v_searches AS
SELECT site, pillar, view, lower(value) AS query, count(*) AS searches, count(DISTINCT visitor_id) AS visitors,
       max(received_at) AS last_seen
FROM activity.event WHERE event_type = 'search' AND coalesce(value, '') <> '' GROUP BY 1, 2, 3, 4;

-- What gets clicked on each page.
CREATE OR REPLACE VIEW activity.v_clicks AS
SELECT site, pillar, view, target, props->>'kind' AS kind, count(*) AS clicks, count(DISTINCT visitor_id) AS visitors
FROM activity.event WHERE event_type = 'click' GROUP BY 1, 2, 3, 4, 5;

-- What holds attention without a click (cards hovered for a while).
CREATE OR REPLACE VIEW activity.v_hovers AS
SELECT site, pillar, view, target, count(*) AS hovers, round(avg(duration_ms)) AS avg_dwell_ms
FROM activity.event WHERE event_type = 'hover' GROUP BY 1, 2, 3, 4;

-- One row per visit: length, pages, the path in and out.
CREATE OR REPLACE VIEW activity.v_sessions AS
SELECT session_id, min(site) AS site, min(visitor_id::text) AS visitor_id,
       min(received_at) AS started, max(received_at) AS ended, max(received_at) - min(received_at) AS length,
       count(*) FILTER (WHERE event_type = 'page_view') AS pages, count(*) AS events,
       (array_agg(coalesce(pillar, '') || '/' || coalesce(view, '') ORDER BY received_at) FILTER (WHERE event_type = 'page_view'))[1] AS entry_page,
       (array_agg(coalesce(pillar, '') || '/' || coalesce(view, '') ORDER BY received_at DESC) FILTER (WHERE event_type = 'page_view'))[1] AS exit_page
FROM activity.event GROUP BY session_id;

-- Paths: which page people go to next (from -> to, count).
CREATE OR REPLACE VIEW activity.v_flows AS
SELECT site, from_page, to_page, count(*) AS moves FROM (
    SELECT site, coalesce(pillar, '') || '/' || coalesce(view, '') AS to_page,
           lag(coalesce(pillar, '') || '/' || coalesce(view, '')) OVER (PARTITION BY session_id ORDER BY received_at) AS from_page
    FROM activity.event WHERE event_type = 'page_view') t
WHERE from_page IS NOT NULL AND from_page <> to_page GROUP BY 1, 2, 3;
