import { useEffect, useRef, useState } from "react";
import "../../styles/analytics.css";

/* Usage analytics (review site only, owner 2026-10-22): pick a site, a person and a day -> that day's login sessions (each
   one plays back in the Session replay player: onPlay), time per page, scroll depth, the words searched or typed, top / dead /
   rage clicks, hovers, activity by hour; and a click heat map painted over the real page. Reads /api/review/activity/people,
   /api/review/activity/events (Session replay's routes) and /api/review/analytics/* (backend/activity_analytics.py). */

const api = async (path, params) => {
  const r = await fetch(`/api/review/${path}?${new URLSearchParams(Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v != null && v !== "")))}`);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status}`);
  return body;
};
const today = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const dayWindow = (day) => { const s = new Date(`${day}T00:00:00`); const e = new Date(s); e.setDate(e.getDate() + 1); return { start: s.toISOString(), end: e.toISOString() }; };
const hm = (t) => (t ? new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—");
const dur = (ms) => { if ((ms || 0) < 60000) return `${Math.round((ms || 0) / 1000)} s`; const m = Math.round(ms / 60000); return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`; };
const ENDED = { logout: "logged out", idle: "auto logout (2 h idle)", open: "still open" };

export default function Analytics({ onClose, onPlay }) {
  const [site, setSite] = useState("live");
  const [people, setPeople] = useState(null);
  const [who, setWho] = useState(null);                 // {user} or {visitor}, plus label
  const [day, setDay] = useState(today());
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [heat, setHeat] = useState(null);                // {view, hash}
  const fail = (e) => setErr(e.message || String(e));

  useEffect(() => { setPeople(null); setWho(null); setData(null);
    api("activity/people", { site }).then(setPeople, fail); }, [site]);
  useEffect(() => { if (!who) return; setData(null); setErr("");
    api("analytics/day", { site, user: who.user, visitor: who.visitor, ...dayWindow(day) }).then(setData, fail); }, [site, who, day]);

  const play = (s) => api("activity/events", { site, session: s.id })
    .then((d) => onPlay && onPlay(d.events, `${who.label} · ${hm(s.started)}–${hm(s.ended)}`, site), fail);

  if (heat) return <HeatOverlay site={site} who={who} day={day} page={heat} onClose={() => setHeat(null)} />;
  const t = data && data.totals;
  const maxHour = data ? Math.max(1, ...data.hourly.map((h) => h.events)) : 1;
  return (
    <div className="an-panel" role="dialog" aria-label="Usage analytics">
      <div className="an-h">
        <b>Usage analytics</b>
        <select value={site} onChange={(e) => setSite(e.target.value)} aria-label="Site">
          <option value="live">Live site</option><option value="review">Review site</option>
        </select>
        <select value={who ? JSON.stringify(who) : ""} onChange={(e) => setWho(e.target.value ? JSON.parse(e.target.value) : null)} aria-label="Person">
          <option value="">Pick a person…</option>
          {(people?.users || []).map((u) => <option key={u.id} value={JSON.stringify({ user: u.id, label: u.label })}>{u.label}{u.events ? ` (${u.events})` : ""}</option>)}
          {(people?.visitors || []).slice(0, 50).map((v) => <option key={v.id} value={JSON.stringify({ visitor: v.id, label: `Browser ${v.id.slice(0, 8)}` })}>Browser {v.id.slice(0, 8)} · no login</option>)}
        </select>
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" />
        <button type="button" className="an-x" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {err && <p className="an-err">{err}</p>}
      {!who && <p className="an-dim">Pick a person and a day.</p>}
      {who && !data && !err && <p className="an-dim">Loading…</p>}
      {data && (
        <div className="an-body">
          <div className="an-kpis">
            <span><b>{t.sessions}</b> sessions</span><span><b>{dur(t.active_ms)}</b> active</span><span><b>{t.pages}</b> page views</span>
            <span><b>{t.searches}</b> searches</span><span><b>{t.clicks}</b> clicks</span>
            <span className={t.dead_clicks ? "warn" : ""}><b>{t.dead_clicks}</b> dead clicks</span>
            <span className={t.rage_clicks ? "warn" : ""}><b>{t.rage_clicks}</b> rage clicks</span>
          </div>
          <div className="an-grid">
            <section>
              <div className="an-sec">Sessions</div>
              {!data.sessions.length && <p className="an-dim">No activity that day.</p>}
              {data.sessions.map((s) => (
                <div className="an-row" key={s.id}>
                  <span className="an-t">{hm(s.started)}–{hm(s.ended)}</span>
                  <span className="an-dim">{dur(new Date(s.ended) - new Date(s.started))} · {s.pages} pages · {s.clicks} clicks · {s.searches} searches</span>
                  <span className={`an-end ${s.end_reason}`}>{s.logged_in ? ENDED[s.end_reason] || s.end_reason : "no login"}</span>
                  <button type="button" onClick={() => play(s)}>▶ Play</button>
                </div>
              ))}
              <div className="an-sec">Activity by hour</div>
              <div className="an-hours">
                {Array.from({ length: 24 }, (_, h) => { const e = (data.hourly.find((x) => x.hour === h) || {}).events || 0;
                  return <span key={h} title={`${h}:00 · ${e} events`} style={{ height: `${Math.round((e / maxHour) * 100)}%` }} className={e ? "on" : ""} />; })}
              </div>
              <div className="an-hlabels"><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div>
            </section>
            <section>
              <div className="an-sec">Pages · time spent</div>
              <table className="an-tbl"><thead><tr><th>Page</th><th>Time</th><th>Views</th><th>Scrolled</th><th>Clicks</th><th /></tr></thead>
                <tbody>{data.pages.map((p) => (
                  <tr key={`${p.pillar}/${p.view}`}>
                    <td>{p.pillar}/{p.view}</td><td>{dur(p.time_ms)}</td><td>{p.views}</td>
                    <td>{p.scroll_depth != null ? `${Math.round(p.scroll_depth * 100)}%` : "—"}</td><td>{p.clicks}</td>
                    <td><button type="button" onClick={() => setHeat({ view: p.view, hash: p.hash })} disabled={!p.hash}>Heat map</button></td>
                  </tr>))}</tbody></table>
            </section>
            <section>
              <div className="an-sec">Words used</div>
              <div className="an-words">{data.words.length ? data.words.map(([w, n]) => <span key={w} style={{ fontSize: `${Math.min(20, 11 + n * 2)}px` }} title={`${n}×`}>{w}</span>) : <span className="an-dim">none</span>}</div>
              <div className="an-sec">Searches and typed text</div>
              {data.searches.map((s, i) => <div className="an-row" key={i}><span className="an-dim">{hm(s.first_at)}</span><span className="an-t">“{s.value}”</span><span className="an-dim">{s.target} · {s.view}{s.times > 1 ? ` · ${s.times}×` : ""}</span></div>)}
              {!data.searches.length && <p className="an-dim">none</p>}
            </section>
            <section>
              <div className="an-sec">Most clicked</div>
              {data.top_clicks.map((c, i) => <div className="an-row" key={i}><span className="an-t">{String(c.target).slice(0, 70)}</span><span className="an-dim">{c.view} · {c.clicks}×</span></div>)}
              <div className="an-sec">Dead clicks <span className="an-dim">(clicked, nothing happened)</span></div>
              {data.dead_clicks.map((c, i) => <div className="an-row" key={i}><span className="an-t">{String(c.target || c.sel).slice(0, 70)}</span><span className="an-dim">{c.view} · {c.clicks}×</span></div>)}
              {!data.dead_clicks.length && <p className="an-dim">none</p>}
              <div className="an-sec">Rage clicks <span className="an-dim">(3+ fast clicks on one spot)</span></div>
              {data.rage_clicks.map((c, i) => <div className="an-row" key={i}><span className="an-dim">{hm(c.at)}</span><span className="an-t">{String(c.target || "?").slice(0, 60)}</span><span className="an-dim">{c.view} · {c.clicks} clicks</span></div>)}
              {!data.rage_clicks.length && <p className="an-dim">none</p>}
              <div className="an-sec">Hovered longest</div>
              {data.hovers.map((h, i) => <div className="an-row" key={i}><span className="an-t">{String(h.target).slice(0, 70)}</span><span className="an-dim">{h.view} · {h.hovers}× · {Math.round(h.avg_ms / 100) / 10} s</span></div>)}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

/* The heat map over the real page: open the page the clicks were made on, then paint them (red = clicks, blue = dead
   clicks) at their place in the window. The tracker is muted while it shows (window.__ksslReplay). */
function HeatOverlay({ site, who, day, page, onClose }) {
  const canvas = useRef(null);
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState("");
  const [everyone, setEveryone] = useState(false);
  useEffect(() => {
    window.__ksslReplay = true;
    if (page.hash) location.hash = page.hash;
    return () => { window.__ksslReplay = false; };
  }, [page.hash]);
  useEffect(() => {
    api("analytics/heatmap", { site, view: page.view, ...(everyone ? {} : { user: who.user, visitor: who.visitor }), ...dayWindow(day) })
      .then(setInfo, (e) => setErr(e.message || String(e)));
  }, [site, who, day, page.view, everyone]);
  useEffect(() => {
    const c = canvas.current;
    if (!c || !info) return;
    const draw = () => {
      c.width = innerWidth; c.height = innerHeight;
      const g = c.getContext("2d");
      g.clearRect(0, 0, c.width, c.height);
      for (const [x, y, dead] of info.points) {
        const px = x * c.width, py = y * c.height;
        const r = g.createRadialGradient(px, py, 0, px, py, 26);
        r.addColorStop(0, dead ? "rgba(60,140,255,.55)" : "rgba(255,60,40,.55)");
        r.addColorStop(1, "rgba(255,60,40,0)");
        g.fillStyle = r; g.fillRect(px - 26, py - 26, 52, 52);
      }
    };
    draw();
    addEventListener("resize", draw);
    return () => removeEventListener("resize", draw);
  }, [info]);
  return (
    <>
      <canvas ref={canvas} className="an-heat" aria-hidden="true" />
      <div className="an-heatbar" role="dialog" aria-label="Heat map">
        <b>Heat map · {page.view}</b>
        <span>{err || (info ? `${info.points.length} clicks${info.max_scroll != null ? ` · scrolled up to ${Math.round(info.max_scroll * 100)}% (median ${Math.round((info.median_scroll || 0) * 100)}%)` : ""}` : "loading…")}</span>
        <label><input type="checkbox" checked={everyone} onChange={(e) => setEveryone(e.target.checked)} /> everyone that day</label>
        <span className="an-key"><i className="r" /> click <i className="b" /> dead click</span>
        <button type="button" onClick={onClose}>Back to analytics</button>
      </div>
    </>
  );
}
