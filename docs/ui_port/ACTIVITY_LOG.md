# Usage log (activity.event)

What people do on the site, first-party, in our own database, Mixpanel / Hotjar style but without a third party.

| Piece | File |
|---|---|
| Table and insight views | `db/setup/31_user_activity.sql` |
| Endpoint `POST /api/track` | `backend/app.py` |
| Browser capture | `src/lib/track.js` (imported once in `src/App.jsx`) |
| Test | `tests/unit/test_track.mjs` |

## What is recorded

| event_type | When | target | value | duration_ms |
|---|---|---|---|---|
| `page_view` | a view opens (the `#p=…&v=…` route changes) | | | |
| `leave` | that view is left (another view, tab closed) | | | time on the view |
| `click` | a click on a button, link, tab, card or list row | its label (aria-label, title or text) | its data-id / href | |
| `search` | typing pauses for 1.2 s in a text or search box | the box's label / placeholder | what was typed | |
| `hover` | the pointer rests on a card or row for 0.8 s or more | the card's label | | the dwell |
| `move` | the mouse moves (for the review site's session replay) | | | |
| `scroll` | a page or panel scrolls (throttled to 300 ms, plus the final position) | the scrolled element ("doc" = the page) | | |

Every event also has `pillar` and `view` (the page it happened on), `visitor_id` (a random id kept in that browser),
`session_id` (one visit; a new one after 30 minutes idle), `client_ts`, `received_at`, the user agent and small `props`
(element kind, window size, referrer host). For the replay player: `page_view` props carry the full route hash, `click` props
the click position (`x`, `y` as fractions of the window) and a short selector `sel`, `move` props a mouse path
`pts = [[ms after client_ts, x, y], ...]` (a point per 100 ms, one event per 2 s), `scroll` props `top` (px) and `frac`.
`user_id` is set once a login stores the user in the browser (`localStorage.kssl_user`); before that it is empty
(`db/setup/32_activity_replay.sql`).

**Privacy.** No IP address. Visits are anonymous until a login sets `user_id`; from then on the session-replay player
on the review site can replay that user's visit (pages, clicks, typed searches, mouse path, scrolling). Tell users so. The ids are random and live in the browser; clearing site data gives a
new visitor. A browser that sends Do Not Track is not logged. Events are batched every 5 seconds; a failed send is
dropped, never retried into the page.

**Where it is stored.** Each API logs into the database it already uses: the live site into `kssl_serving`, the review
site into `kssl_staging`, marked by `site = 'live' | 'review'`. The schema `activity` sits outside `serving` / `ui`, so the
approve guard does not apply, and it is never synced, published or approved. The VPS keeps its own log; that is the
one with client traffic.

## Insight views

Filter on `site = 'live'` for what clients do; `site = 'review'` is the team.

| View | Question it answers |
|---|---|
| `activity.v_daily` | How many visitors, visits, page views, clicks and searches per day? |
| `activity.v_pages` | Which pages are used, by how many people, and how long they stay (median)? |
| `activity.v_searches` | What do people search for, and where? |
| `activity.v_clicks` | What gets clicked on each page? |
| `activity.v_hovers` | What holds attention without a click? |
| `activity.v_sessions` | One row per visit: length, pages, entry and exit page. |
| `activity.v_flows` | Which page do people go to next (from -> to)? |

## Questions worth asking

```sql
-- 1. Is the site used? Visitors and visits, last 30 days
SELECT day, visitors, sessions, page_views FROM activity.v_daily
WHERE site = 'live' AND day > current_date - 30 ORDER BY day;

-- 2. Which pages earn their place, and which nobody opens?
SELECT pillar, view, views, visitors, round(median_time_ms / 1000) AS median_seconds
FROM activity.v_pages WHERE site = 'live' ORDER BY views DESC;

-- 3. Searches that found nothing: a search with no click on the same page in the next 30 seconds
SELECT s.value AS query, count(*) AS times
FROM activity.event s
WHERE s.site = 'live' AND s.event_type = 'search'
  AND NOT EXISTS (SELECT 1 FROM activity.event c WHERE c.session_id = s.session_id AND c.event_type = 'click'
                  AND c.view = s.view AND c.received_at BETWEEN s.received_at AND s.received_at + interval '30 seconds')
GROUP BY 1 ORDER BY 2 DESC LIMIT 30;

-- 4. Drop-off: where visits end
SELECT exit_page, count(*) AS visits_ending_here FROM activity.v_sessions WHERE site = 'live' GROUP BY 1 ORDER BY 2 DESC;

-- 5. A funnel: of the visits that open the overview, how many open a signal, then a tender?
WITH v AS (SELECT session_id,
                  min(received_at) FILTER (WHERE view = 'overview' AND event_type = 'page_view') AS a,
                  min(received_at) FILTER (WHERE view = 'overview' AND event_type = 'click' AND props->>'kind' LIKE 'div.alert%') AS b,
                  min(received_at) FILTER (WHERE view = 'tender' AND event_type = 'page_view') AS c
           FROM activity.event WHERE site = 'live' GROUP BY 1)
SELECT count(a) AS opened_overview, count(b) FILTER (WHERE b > a) AS opened_a_signal, count(c) FILTER (WHERE c > b) AS then_tenders FROM v;

-- 6. Returning visitors: share of visitors seen on more than one day
SELECT round(100.0 * count(*) FILTER (WHERE days > 1) / nullif(count(*), 0), 1) AS pct_returning
FROM (SELECT visitor_id, count(DISTINCT received_at::date) AS days FROM activity.event WHERE site = 'live' GROUP BY 1) t;

-- 7. Interest without action: cards hovered a lot but rarely clicked
SELECT h.view, h.target, h.hovers, coalesce(c.clicks, 0) AS clicks
FROM activity.v_hovers h LEFT JOIN activity.v_clicks c USING (site, pillar, view, target)
WHERE h.site = 'live' ORDER BY h.hovers DESC LIMIT 20;
```

How to use the answers: pages with few views and short time are candidates to merge or drop; searches with no click are
data or labelling gaps (the thing people expect to find); exit pages with long time are fine (the answer was found),
exit pages with short time are friction; hovered-but-not-clicked cards mean the title promises something the card does
not deliver.

## Housekeeping

- Volume: about 50-200 events per visit. A year of light client use is a few million rows; the indexes cover time,
  visit and type. To keep a window: `DELETE FROM activity.event WHERE received_at < now() - interval '13 months';`
- Mouse paths and scrolling are logged for the replay player (about 1 event per 2 s of movement). Screen recordings
  (pixels, DOM snapshots) are not: the player re-drives the real UI from the route, clicks and positions instead.
- While the replay player drives the page (`window.__ksslReplay` set), nothing is logged, and synthetic events never are.
- To tag a control by name, give it `data-track="Approve all"`; to log hovers on a new kind of card, give it
  `data-track-hover`.
