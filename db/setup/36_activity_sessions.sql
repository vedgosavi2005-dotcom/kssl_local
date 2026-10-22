-- Login sessions for the usage log (owner 2026-10-22): a session runs from login to logout, or to 2 hours without activity
-- (auto logout). The tracker (src/lib/track.js) writes 'login' and 'logout' events (props.reason: logout | idle) and uses the
-- login session id as session_id for everything in between, across the browser's tabs. Safe to re-run; needs 31, 32.
ALTER TABLE activity.event DROP CONSTRAINT IF EXISTS event_event_type_check;
ALTER TABLE activity.event ADD CONSTRAINT event_event_type_check
    CHECK (event_type IN ('page_view', 'leave', 'click', 'search', 'hover', 'move', 'scroll', 'login', 'logout'));

-- One row per login session: who, start, end, how it ended, and what happened in it.
CREATE OR REPLACE VIEW activity.v_login_sessions AS
SELECT e.session_id, min(e.site) AS site, min(e.user_id) AS user_id,
       coalesce(min(e.client_ts) FILTER (WHERE e.event_type = 'login'), min(coalesce(e.client_ts, e.received_at))) AS started,
       greatest(coalesce(max(e.client_ts) FILTER (WHERE e.event_type = 'logout'), max(coalesce(e.client_ts, e.received_at))),
                coalesce(min(e.client_ts) FILTER (WHERE e.event_type = 'login'), min(coalesce(e.client_ts, e.received_at)))) AS ended,
       coalesce(max(e.props->>'reason') FILTER (WHERE e.event_type = 'logout'), 'open') AS end_reason,
       count(*) FILTER (WHERE e.event_type = 'page_view') AS pages,
       count(*) FILTER (WHERE e.event_type = 'click') AS clicks,
       count(*) FILTER (WHERE e.event_type = 'click' AND (e.props->>'dead')::boolean) AS dead_clicks,
       count(*) FILTER (WHERE e.event_type = 'search') AS searches,
       count(*) AS events
FROM activity.event e
WHERE e.user_id IS NOT NULL
GROUP BY e.session_id
HAVING bool_or(e.event_type = 'login');           -- a login session has a login; the anonymous visit before it is not one
