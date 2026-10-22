"""Usage analytics for the review site (owner 2026-10-22): one person's day -- login sessions (login to logout or 2 h idle), time
per page, scroll depth, searches and the words used, top clicks, dead clicks, rage clicks, activity by hour -- and a click heat
map of one page. Reads activity.event (31/32/36) through the cursor the activity routes use (live events: serving DB, review
events: staging DB). Served by /api/review/analytics/* (backend/app.py); drawn by src/components/analytics/Analytics.jsx.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any

STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to was were will with
what which who how why when where do does can i me my we our you your they them their not no yes about into than then""".split())
RAGE_N, RAGE_MS, RAGE_DIST = 3, 1000, 0.03          # 3+ clicks within 1 s, within 3% of the window of each other


def _who(user: str | None, visitor: str | None) -> tuple[str, list]:
    if user:
        return "user_id = %s", [user]
    if visitor:
        return "visitor_id = %s::uuid AND user_id IS NULL", [visitor]
    raise ValueError("user or visitor is required")


def _window(start: str | None, end: str | None) -> tuple[str, list]:
    where, args = "", []
    if start:
        where += " AND coalesce(client_ts, received_at) >= %s::timestamptz"
        args.append(start)
    if end:
        where += " AND coalesce(client_ts, received_at) < %s::timestamptz"
        args.append(end)
    return where, args


def words_of(texts: list[str]) -> list[tuple[str, int]]:
    """the words people typed, most used first (stop words and 1-2 letter words dropped)"""
    c = Counter(w for t in texts for w in re.findall(r"[a-z0-9][a-z0-9\-\.]{2,}", (t or "").lower()) if w not in STOP)
    return c.most_common(40)


def rage_clicks(clicks: list[dict]) -> list[dict]:
    """bursts of RAGE_N+ clicks within RAGE_MS on (nearly) the same spot: something did not respond as expected"""
    out, i = [], 0
    clicks = sorted(clicks, key=lambda c: c["ts"])
    while i < len(clicks):
        j = i + 1
        while (j < len(clicks) and (clicks[j]["ts"] - clicks[j - 1]["ts"]).total_seconds() * 1000 <= RAGE_MS
               and abs((clicks[j]["x"] or 0) - (clicks[i]["x"] or 0)) <= RAGE_DIST and abs((clicks[j]["y"] or 0) - (clicks[i]["y"] or 0)) <= RAGE_DIST):
            j += 1
        if j - i >= RAGE_N:
            c = clicks[i]
            out.append({"at": c["ts"], "view": c["view"], "target": c["target"], "clicks": j - i})
        i = j
    return out


def day(cur, user: str | None, visitor: str | None, start: str | None, end: str | None) -> dict[str, Any]:
    who, args = _who(user, visitor)
    win, wargs = _window(start, end)
    base = f"FROM activity.event WHERE {who}{win}"
    a = [*args, *wargs]

    cur.execute(f"""SELECT session_id::text AS id,
                           coalesce(min(client_ts) FILTER (WHERE event_type = 'login'), min(coalesce(client_ts, received_at))) AS started,
                           greatest(coalesce(max(client_ts) FILTER (WHERE event_type = 'logout'), max(coalesce(client_ts, received_at))),
                                    coalesce(min(client_ts) FILTER (WHERE event_type = 'login'), min(coalesce(client_ts, received_at)))) AS ended,
                           coalesce(max(props->>'reason') FILTER (WHERE event_type = 'logout'), 'open') AS end_reason,
                           bool_or(event_type = 'login') AS logged_in,
                           count(*) FILTER (WHERE event_type = 'page_view') AS pages, count(*) FILTER (WHERE event_type = 'click') AS clicks,
                           count(*) FILTER (WHERE event_type = 'search') AS searches, count(*) AS events
                    {base} GROUP BY session_id ORDER BY 2""", a)
    sessions = cur.fetchall()
    if any(s["logged_in"] for s in sessions):        # a person who logs in: their login sessions (the anonymous visit before a
        sessions = [s for s in sessions if s["logged_in"]]   # login is not one); before logins existed, every visit

    cur.execute(f"""SELECT pillar, view, max(props->>'hash') FILTER (WHERE event_type = 'page_view') AS hash,
                           count(*) FILTER (WHERE event_type = 'page_view') AS views,
                           coalesce(sum(duration_ms) FILTER (WHERE event_type = 'leave'), 0) AS time_ms,
                           max((props->>'frac')::numeric) FILTER (WHERE event_type = 'scroll') AS scroll_depth,
                           count(*) FILTER (WHERE event_type = 'click') AS clicks
                    {base} AND (pillar IS NOT NULL OR view IS NOT NULL) GROUP BY pillar, view ORDER BY time_ms DESC, views DESC""", a)
    pages = cur.fetchall()

    cur.execute(f"""SELECT value, target, view, count(*) AS times, min(coalesce(client_ts, received_at)) AS first_at
                    {base} AND event_type = 'search' AND coalesce(value, '') <> '' GROUP BY value, target, view ORDER BY first_at""", a)
    searches = cur.fetchall()

    cur.execute(f"""SELECT coalesce(client_ts, received_at) AS ts, view, target, (props->>'x')::float AS x, (props->>'y')::float AS y,
                           coalesce((props->>'dead')::boolean, false) AS dead, props->>'sel' AS sel
                    {base} AND event_type = 'click'""", a)
    clicks = cur.fetchall()
    top = Counter((c["view"], c["target"]) for c in clicks if not c["dead"] and c["target"])
    dead = Counter((c["view"], c["sel"], c["target"]) for c in clicks if c["dead"])

    cur.execute(f"""SELECT target, view, count(*) AS hovers, round(avg(duration_ms)) AS avg_ms
                    {base} AND event_type = 'hover' AND target IS NOT NULL GROUP BY target, view ORDER BY hovers DESC LIMIT 15""", a)
    hovers = cur.fetchall()

    cur.execute(f"""SELECT extract(hour FROM coalesce(client_ts, received_at) AT TIME ZONE %s)::int AS hour, count(*) AS events
                    {base} GROUP BY 1 ORDER BY 1""", ["Asia/Kolkata", *a])
    hourly = cur.fetchall()

    active_ms = sum(int(p["time_ms"] or 0) for p in pages)
    rage = rage_clicks([c for c in clicks if c["x"] is not None])
    return {
        "totals": {"sessions": len(sessions), "active_ms": active_ms, "pages": sum(int(p["views"] or 0) for p in pages),
                   "searches": len(searches), "clicks": sum(1 for c in clicks if not c["dead"]),
                   "dead_clicks": sum(1 for c in clicks if c["dead"]), "rage_clicks": len(rage)},
        "sessions": sessions, "pages": pages, "searches": searches, "words": words_of([s["value"] for s in searches]),
        "top_clicks": [{"view": v, "target": t, "clicks": n} for (v, t), n in top.most_common(20)],
        "dead_clicks": [{"view": v, "sel": s, "target": t, "clicks": n} for (v, s, t), n in dead.most_common(15)],
        "rage_clicks": rage, "hovers": hovers, "hourly": hourly,
    }


def heatmap(cur, view: str, user: str | None, visitor: str | None, start: str | None, end: str | None) -> dict[str, Any]:
    """click points on one view (window fractions), and how far down people scrolled it"""
    who, args = ("TRUE", []) if not (user or visitor) else _who(user, visitor)
    win, wargs = _window(start, end)
    cur.execute(f"""SELECT (props->>'x')::float AS x, (props->>'y')::float AS y, coalesce((props->>'dead')::boolean, false) AS dead
                    FROM activity.event WHERE {who}{win} AND event_type = 'click' AND view = %s AND props ? 'x' LIMIT 20000""",
                [*args, *wargs, view])
    points = [[r["x"], r["y"], r["dead"]] for r in cur.fetchall()]
    cur.execute(f"""SELECT max(props->>'hash') FILTER (WHERE event_type = 'page_view') AS hash,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY (props->>'frac')::numeric) FILTER (WHERE event_type = 'scroll') AS median_scroll,
                           max((props->>'frac')::numeric) FILTER (WHERE event_type = 'scroll') AS max_scroll
                    FROM activity.event WHERE {who}{win} AND view = %s""", [*args, *wargs, view])
    meta = cur.fetchone() or {}
    return {"view": view, "points": points, "hash": meta.get("hash"), "median_scroll": meta.get("median_scroll"),
            "max_scroll": meta.get("max_scroll"), "generated": datetime.now().isoformat(timespec="seconds")}


def _selftest() -> None:
    from datetime import timedelta
    t0 = datetime(2026, 10, 22, 9)
    burst = [{"ts": t0 + timedelta(milliseconds=200 * i), "x": 0.5, "y": 0.5, "view": "tender", "target": "Save"} for i in range(4)]
    assert len(rage_clicks(burst)) == 1 and rage_clicks(burst)[0]["clicks"] == 4
    assert rage_clicks(burst[:2]) == []                                                   # two clicks are not rage
    spread = [{**c, "x": 0.1 * i} for i, c in enumerate(burst)]
    assert rage_clicks(spread) == []                                                      # fast but in different places
    assert words_of(["Hanwha K9 tender", "hanwha in India"])[0] == ("hanwha", 2)
    print("activity_analytics self-check ok")


if __name__ == "__main__":
    _selftest()
