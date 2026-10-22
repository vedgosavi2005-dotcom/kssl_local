import { useEffect, useRef, useState } from "react";
import { timeline, hashOf, findTarget, findInput, findScroller, replayUnsafe, captionOf, fmtDur, HOVER_SHOWN_MAX_MS } from "../../lib/replay";
import "../../styles/replay.css";

/* SESSION REPLAY, review site only (owner 22 Oct): pick a person (User 1-5 once the login exists, or a browser seen
   without a login), a time window and a visit, press Play: the UI re-runs what they did -- the pages they opened, a
   cursor along their mouse path, the cards they clicked and looked at, the searches they typed, the scrolling.
   Engine (clock, element matching): lib/replay.js. Data: /api/review/activity/* (backend/app.py).

   Never repeated, only shown: review actions, Ask Parallax questions and links that leave the site
   (lib/replay replayUnsafe). The tracker is muted while it plays (window.__ksslReplay), so a replay logs nothing. */

const IST = { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false };
const fmtTime = (v) => (v ? new Date(v).toLocaleString("en-GB", IST) : "—");
const SPEEDS = [1, 2, 4, 8];
const localInput = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

async function get(path, params) {
  const r = await fetch(`${path}?${new URLSearchParams(Object.entries(params).filter(([, v]) => v))}`);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status}`);
  return body;
}

/* the chooser: site, person, time window, visits */
export function ReplayPanel({ onClose, onPlay }) {
  const [site, setSite] = useState("live");
  const [people, setPeople] = useState(null);
  const [who, setWho] = useState(null);                   // {user} | {visitor}
  const [from, setFrom] = useState(localInput(new Date(Date.now() - 7 * 864e5)));
  const [to, setTo] = useState("");
  const [sessions, setSessions] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setPeople(null); setWho(null); setSessions(null);
    get("/api/review/activity/people", { site }).then(setPeople, (e) => setErr(e.message));
  }, [site]);
  useEffect(() => {
    if (!who) return;
    setSessions(null);
    get("/api/review/activity/sessions", { site, ...who, start: from && new Date(from).toISOString(), end: to && new Date(to).toISOString() })
      .then((b) => setSessions(b.sessions), (e) => setErr(e.message));
  }, [site, who, from, to]);

  const play = async (list) => {
    try {
      const all = [];
      for (const s of [...list].sort((a, b) => new Date(a.start) - new Date(b.start))) {
        all.push(...(await get("/api/review/activity/events", { site, session: s.id })).events);
      }
      if (!all.length) return setErr("No events in this visit.");
      onPlay(all, who.user ? people.users.find((u) => u.id === who.user)?.label || who.user : `Browser ${who.visitor.slice(0, 8)}`);
    } catch (e) {
      setErr(e.message);
    }
  };

  return (
    <div className="rp-panel" role="dialog" aria-label="Session replay">
      <div className="rp-h">
        <b>Session replay</b>
        <button type="button" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {err && <p className="rp-err">{err}</p>}
      <div className="rp-row">
        {["live", "review"].map((s) => (
          <button key={s} type="button" className={site === s ? "on" : ""} onClick={() => setSite(s)}>{s === "live" ? "Live site" : "Review site"}</button>
        ))}
      </div>
      <div className="rp-sec">Users</div>
      <div className="rp-users">
        {(people?.users || []).map((u) => (
          <button key={u.id} type="button" className={who?.user === u.id ? "on" : ""} onClick={() => setWho({ user: u.id })}
            title={u.events ? `last seen ${fmtTime(u.last)}` : "no activity yet (the login is not in place yet)"}>
            {u.label}<span>{u.events || 0}</span>
          </button>
        ))}
      </div>
      <div className="rp-sec">Browsers without a login <span className="rp-dim">({people?.visitors.length ?? "…"})</span></div>
      <div className="rp-list rp-visitors">
        {(people?.visitors || []).map((v) => (
          <button key={v.id} type="button" className={who?.visitor === v.id ? "on" : ""} onClick={() => setWho({ visitor: v.id })}>
            <span><b>{v.id.slice(0, 8)}</b> · {v.sessions} visit{v.sessions === 1 ? "" : "s"} · {v.events} events</span>
            <span className="rp-dim">last {fmtTime(v.last)} · {/Edg\//.test(v.user_agent || "") ? "Edge" : /Chrome\//.test(v.user_agent || "") ? "Chrome" : /Firefox\//.test(v.user_agent || "") ? "Firefox" : /Safari\//.test(v.user_agent || "") ? "Safari" : "browser"}</span>
          </button>
        ))}
        {people && !people.visitors.length && <p className="rp-dim">No visits logged on this site yet.</p>}
      </div>
      {who && (
        <>
          <div className="rp-sec">Time window (your local time)</div>
          <div className="rp-row rp-when">
            <label>From <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
            <label>To <input type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} /></label>
          </div>
          <div className="rp-sec">
            Visits {sessions ? `(${sessions.length})` : "…"}
            {sessions && sessions.length > 1 && (
              <button type="button" className="rp-playall" onClick={() => play(sessions)}>▶ Play all, in order</button>
            )}
          </div>
          <div className="rp-list">
            {(sessions || []).map((s) => (
              <div key={s.id} className="rp-visit">
                <div>
                  <b>{fmtTime(s.start)}</b> → {fmtTime(s.end).split(", ").pop()} · {fmtDur(new Date(s.end) - new Date(s.start))}
                  <span className="rp-dim">{s.pages} pages · {s.clicks} clicks · {s.searches} searches · {s.events} events</span>
                </div>
                <button type="button" onClick={() => play([s])}>▶ Play</button>
              </div>
            ))}
            {sessions && !sessions.length && <p className="rp-dim">No visits in this window.</p>}
          </div>
        </>
      )}
    </div>
  );
}

/* the player: the control bar, the ghost cursor, the highlight. Plays `events` on this page. */
export function ReplayPlayer({ events, who, onClose }) {
  const [skipIdle, setSkipIdle] = useState(true);
  const steps = useRef([]);
  const [total, setTotal] = useState(0);
  const [clock, setClock] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(2);
  const [caption, setCaption] = useState("");
  const [now, setNow] = useState(null);
  const cursor = useRef(null), box = useRef(null), ripple = useRef(null);
  const state = useRef({ clock: 0, next: 0, last: 0 });

  // build the clock; keep the position on a skip-idle change by real time
  useEffect(() => {
    steps.current = timeline(events, { skipIdle });
    setTotal(steps.current.length ? steps.current[steps.current.length - 1].at : 0);
    seek(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events, skipIdle]);

  // mute the tracker and hide the review chrome (the person did not see it) while the player is open
  useEffect(() => {
    window.__ksslReplay = true;
    document.body.classList.add("rp-on");
    return () => {
      window.__ksslReplay = false;
      document.body.classList.remove("rp-on");
    };
  }, []);

  const moveCursor = (x, y) => {
    if (cursor.current) cursor.current.style.transform = `translate(${x}px, ${y}px)`;
  };
  const mark = (el, ms) => {
    if (!el || !box.current || !el.getBoundingClientRect) return null;
    el.scrollIntoView && el.scrollIntoView({ block: "nearest", inline: "nearest" });
    const r = el.getBoundingClientRect();
    Object.assign(box.current.style, { left: `${r.left - 4}px`, top: `${r.top - 4}px`, width: `${r.width + 8}px`, height: `${r.height + 8}px`, opacity: 1 });
    clearTimeout(box.current._t);
    box.current._t = setTimeout(() => box.current && (box.current.style.opacity = 0), ms);
    const cx = r.left + Math.min(r.width / 2, 60), cy = r.top + r.height / 2;
    moveCursor(cx, cy);
    return [cx, cy];
  };
  const click = (xy) => {
    if (!ripple.current || !xy) return;
    const el = ripple.current;
    el.style.left = `${xy[0]}px`; el.style.top = `${xy[1]}px`;
    el.classList.remove("go"); void el.offsetWidth; el.classList.add("go");
  };

  // run one step on the page; `quiet` = while seeking (restore the place, repeat nothing)
  const run = (s, quiet) => {
    const e = s.ev;
    if (s.kind === "cursor") return moveCursor(s.x * innerWidth, s.y * innerHeight);
    if (s.kind === "page_view") {
      const h = hashOf(e);
      if (h && location.hash !== h) location.hash = h;
    } else if (s.kind === "scroll") {
      const sc = findScroller(e);
      const p = e.props || {};
      if (sc) sc.scrollTo({ top: typeof p.frac === "number" ? p.frac * (sc.scrollHeight - sc.clientHeight) : p.top || 0, behavior: quiet ? "auto" : "smooth" });
    } else if (!quiet && s.kind === "click") {
      const el = findTarget(e);
      const xy = el ? mark(el, 900 / speed) : null;
      click(xy);
      if (el && !replayUnsafe(el)) el.click();
      else if (el) s.note = " (shown, not repeated)";
      else s.note = " (not on the page any more)";
    } else if (!quiet && s.kind === "hover") {
      const el = findTarget(e);
      if (el) mark(el, Math.min(e.ms || 1000, HOVER_SHOWN_MAX_MS) / speed);
      else s.note = " (not on the page any more)";
    } else if (!quiet && s.kind === "search") {
      const input = findInput(e);
      if (input) {
        mark(input, 1200 / speed);
        const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
        set.call(input, e.value || "");
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    if (!quiet && s.kind !== "scroll") setCaption(captionOf(s) + (s.note || ""));
  };

  // jump: replay pages and scrolling up to `to` without repeating clicks, then continue from there
  const seek = (to) => {
    const st = state.current;
    st.clock = to; st.next = 0;
    let lastPage = null, lastScroll = null, lastCursor = null;
    while (st.next < steps.current.length && steps.current[st.next].at <= to) {
      const s = steps.current[st.next++];
      if (s.kind === "page_view") lastPage = s;
      else if (s.kind === "scroll") lastScroll = s;
      else if (s.kind === "cursor") lastCursor = s;
    }
    if (lastPage) run(lastPage, true);
    if (lastScroll) setTimeout(() => run(lastScroll, true), 400);
    if (lastCursor) run(lastCursor, true);
    setClock(to);
    const cur = steps.current[Math.max(0, st.next - 1)];
    setNow(cur ? cur.real : null);
    if (to > 0) setCaption("Jumped here: pages and scrolling restored; clicks before this point are not repeated.");
  };

  // the playback loop
  useEffect(() => {
    if (!playing) return undefined;
    let raf;
    let prev = performance.now();
    const tick = (t) => {
      const st = state.current;
      st.clock = Math.min(total, st.clock + (t - prev) * speed);
      prev = t;
      while (st.next < steps.current.length && steps.current[st.next].at <= st.clock) {
        const s = steps.current[st.next++];
        run(s, false);
        setNow(s.real);
      }
      setClock(st.clock);
      if (st.clock >= total) { setPlaying(false); setCaption((c) => c + " · end of replay"); return; }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, speed, total]);

  const fmtClock = (ms) => { const s = Math.floor(ms / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  return (
    <>
      <div ref={cursor} className="rp-cursor" aria-hidden="true">
        <svg width="20" height="22" viewBox="0 0 20 22"><path d="M2 1l15 11-7 1.2-3.6 6.8z" fill="#fff" stroke="#111" strokeWidth="1.4" /></svg>
      </div>
      <div ref={box} className="rp-box" aria-hidden="true" />
      <div ref={ripple} className="rp-ripple" aria-hidden="true" />
      <div className="rp-bar" role="region" aria-label="Replay controls">
        <button type="button" className="rp-pp" onClick={() => { if (clock >= total) seek(0); setPlaying((p) => !p); }} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="rp-mid">
          <div className="rp-top">
            <b>{who}</b>
            <span>{now ? fmtTime(now) : ""}</span>
            <span className="rp-cap">{caption}</span>
          </div>
          <input type="range" min="0" max={Math.max(1, total)} step="100" value={clock}
            onChange={(e) => { seek(Number(e.target.value)); }} aria-label="Position in the replay" />
        </div>
        <span className="rp-time">{fmtClock(clock)} / {fmtClock(total)}</span>
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} aria-label="Speed">
          {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
        </select>
        <label className="rp-skip" title="Shorten pauses longer than 5 s"><input type="checkbox" checked={skipIdle} onChange={(e) => setSkipIdle(e.target.checked)} /> skip idle</label>
        <button type="button" onClick={onClose} aria-label="Stop the replay">✕</button>
      </div>
    </>
  );
}
