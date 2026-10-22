-- activity.event for the review site's session-replay player (owner 2026-10-22): who (user_id, once there is a login),
-- the mouse path ('move'), scrolling ('scroll'). Click positions and the full route hash ride in props (src/lib/track.js).
-- Safe to re-run; needs 31_user_activity.sql first.
ALTER TABLE activity.event ADD COLUMN IF NOT EXISTS user_id text;           -- the logged-in user (localStorage kssl_user); NULL before login
CREATE INDEX IF NOT EXISTS event_user_time ON activity.event (user_id, client_ts);

ALTER TABLE activity.event DROP CONSTRAINT IF EXISTS event_event_type_check;
ALTER TABLE activity.event ADD CONSTRAINT event_event_type_check
    CHECK (event_type IN ('page_view', 'leave', 'click', 'search', 'hover', 'move', 'scroll'));
