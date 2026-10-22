-- Page recordings for session replay (owner 2026-10-23): the live site records the page itself (rrweb: a snapshot of the
-- page, then every change to it), so a replay shows exactly what the person saw then -- that day's data and that day's UI --
-- not today's. Written by POST /api/track/rec from src/lib/record.js; read by the review site's player. One row per upload
-- (a few seconds of the visit), gzip-compressed JSON (an array of rrweb events). Same session_id as activity.event.
-- Not reviewed content, never approved or synced (like activity.event). Safe to re-run; needs 31.
CREATE TABLE IF NOT EXISTS activity.recording (
    rec_id       bigserial   PRIMARY KEY,
    received_at  timestamptz NOT NULL DEFAULT now(),
    site         text        NOT NULL CHECK (site IN ('live', 'review')),
    visitor_id   uuid        NOT NULL,
    session_id   uuid        NOT NULL,
    user_id      text,
    first_ts     timestamptz,                               -- browser clock: the chunk's first and last event
    last_ts      timestamptz,
    n_events     integer     NOT NULL,
    bytes        integer     NOT NULL,                      -- uncompressed JSON size
    data         bytea       NOT NULL                       -- gzip(JSON array of rrweb events)
);
CREATE INDEX IF NOT EXISTS recording_session ON activity.recording (session_id, rec_id);
CREATE INDEX IF NOT EXISTS recording_received ON activity.recording (received_at);

