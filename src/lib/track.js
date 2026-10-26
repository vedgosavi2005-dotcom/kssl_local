/* Usage log: page views (and time on each), clicks, searches, hovers on cards, and for the review site's session-replay
   player the mouse path and scrolling -> POST /api/track -> activity.event (db/setup/31_user_activity.sql, 32_activity_replay.sql;
   reading it: docs/ui_port/ACTIVITY_LOG.md). A random id per browser and per visit, no IP stored; user_id only once a login
   puts it in localStorage "kssl_user". Logged whether or not the browser sends Do Not Track (owner 23 Oct); inert outside a browser (unit tests).
   Imported once for its side effect (src/App.jsx). The server decides live vs review, never this file. While the replay
   player drives the page (window.__ksslReplay), nothing is logged, and synthetic (untrusted) events never are. */

const FLUSH_MS = 5000;
const IDLE_MS = 30 * 60 * 1000;        // a new visit after 30 minutes without an event
const HOVER_MIN_MS = 800;              // a hover shorter than this is a pass-over, not interest
const SEARCH_WAIT_MS = 1200;           // the search is logged once typing pauses
const MOVE_EVERY_MS = 100;             // mouse path: one point per 100 ms at most
const MOVE_SPAN_MS = 2000;             // ... one 'move' event per ~2 s of movement
const MOVE_MAX_PTS = 40;               // ... or 40 points, whichever first (stays under the server's props cap)
const SCROLL_EVERY_MS = 300;           // scrolling: one 'scroll' per 300 ms, plus the final position
const LOGIN_IDLE_MS = 2 * 60 * 60 * 1000;   // a login session ends after 2 hours without activity (auto logout)
const TOUCH_EVERY_MS = 30 * 1000;      // "last active" is written at most every 30 s
const CLICKABLE = "a,button,[role=button],[role=tab],select,.alert,.tcard,.pat-li,.cm-title,[data-track]";
const HOVERABLE = ".alert,.tcard,.pat-li,.proj-row,.pg-partner-roster-card,[data-track-hover]";

const uuid = () =>
  (crypto && crypto.randomUUID ? crypto.randomUUID() : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)));

function stored(store, key, make) {
  try {
    const v = store.getItem(key) || make();
    store.setItem(key, v);
    return v;
  } catch (e) {
    return make();                       // private mode / blocked storage: an id for this page load only
  }
}

/* the route as the hash states it: #p=market&v=tender -> {pillar, view} */
export function routeOf(hash) {
  const q = new URLSearchParams(String(hash || "").replace(/^#/, ""));
  return { pillar: q.get("p") || null, view: q.get("v") || null };
}

/* a short, human label for an element: its own data-track, aria-label, title, or first line of text */
export function labelOf(el) {
  if (!el) return null;
  const t = el.getAttribute("data-track") || el.getAttribute("aria-label") || el.getAttribute("title") || el.innerText || el.value || "";
  return String(t).replace(/\s+/g, " ").trim().slice(0, 160) || null;
}

/* a short selector for an element, ancestor to element, up to 3 levels: "div.cp-body ul li.pat-li"; "doc" for the page itself.
   tag#id ends the walk (an id is enough to find it again). */
export function selOf(el) {
  if (!el || !el.tagName || /^(html|body)$/i.test(el.tagName)) return "doc";
  const parts = [];
  for (let n = el; n && n.tagName && parts.length < 3 && !/^(html|body)$/i.test(n.tagName); n = n.parentElement) {
    const tag = n.tagName.toLowerCase();
    if (n.id) {
      parts.unshift(`${tag}#${n.id}`);
      break;
    }
    const cls = n.classList && n.classList[0];
    parts.unshift(cls ? `${tag}.${cls}` : tag);
  }
  return parts.join(" ") || "doc";
}

const r3 = (v) => Math.round(v * 1000) / 1000;

/* localStorage get / set / remove that never throws (private mode, blocked storage) */
function ls(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch (e) {
    /* storage blocked */
  }
  return null;
}

function start() {
  const visitor = stored(localStorage, "kssl_visitor", uuid);
  const user = () => {
    try {
      return localStorage.getItem("kssl_user") || null;
    } catch (e) {
      return null;
    }
  };
  let session = null;
  let lastAt = 0;
  // a LOGIN SESSION (owner 2026-10-22): from login to logout or to 2 hours idle, shared by the browser's tabs
  let loginSession = ls("kssl_login_session");
  const sessionId = () => {
    const now = Date.now();
    if (loginSession && user()) return loginSession;
    try {
      const s = JSON.parse(sessionStorage.getItem("kssl_visit") || "null");
      session = s && now - s.at < IDLE_MS ? s.id : uuid();
      sessionStorage.setItem("kssl_visit", JSON.stringify({ id: session, at: now }));
    } catch (e) {
      if (!session || now - lastAt > IDLE_MS) session = uuid();
    }
    lastAt = now;
    return session;
  };

  let queue = [];
  let route = routeOf(location.hash);
  let viewSince = Date.now();
  const replaying = () => !!window.__ksslReplay;
  let touched = 0;
  const touch = () => {                          // the user did something: keep the login session alive
    const now = Date.now();
    if (now - touched >= TOUCH_EVERY_MS) {
      touched = now;
      ls("kssl_last_active", String(now));
    }
  };
  const push = (type, extra) => {
    if (replaying()) return;                     // the player is driving the page: not activity
    if (type !== "logout" && type !== "leave") touch();
    const session = sessionId();
    window.__ksslSession = session;              // the page recording (record.js) files its chunks under the same visit
    queue.push({ type, visitor, session, user: user(), ts: new Date().toISOString(), ...route, ...extra });
    if (queue.length >= 90) flush();
  };
  const flush = (leaving) => {
    if (!queue.length) return;
    const body = JSON.stringify(queue.splice(0, 90));
    fetch("/api/track", { method: "POST", keepalive: !!leaving, headers: { "Content-Type": "application/json", "X-KSSL-Write": "1" }, body })
      .catch(() => {});                  // the log never breaks the page
  };

  const pageView = () => push("page_view", { props: { hash: location.hash, w: innerWidth, h: innerHeight,
                                                       ref: document.referrer ? new URL(document.referrer).host : null } });
  const leave = () => push("leave", { ms: Date.now() - viewSince });
  const onRoute = () => {
    const next = routeOf(location.hash);
    if (next.pillar === route.pillar && next.view === route.view) return;
    if (route.pillar || route.view) leave();      // the app sets its first route after load: no empty "page" before it
    route = next;
    viewSince = Date.now();
    pageView();
  };
  // the app moves with history.pushState / replaceState, which fire no event: wrap them
  for (const fn of ["pushState", "replaceState"]) {
    const orig = history[fn];
    history[fn] = function (...a) {
      const r = orig.apply(this, a);
      setTimeout(onRoute, 0);
      return r;
    };
  }
  addEventListener("popstate", onRoute);
  addEventListener("hashchange", onRoute);

  document.addEventListener("click", (e) => {
    if (!e.isTrusted) return;
    const el = e.target && e.target.closest && e.target.closest(CLICKABLE);
    if (!el) {                                   // a "dead" click: on something that does nothing (a sign of confusion)
      const t = e.target && e.target.nodeType === 1 ? e.target : null;
      const lab = t ? labelOf(t) : null;         // a big container's text is not a label: keep short ones only, sel says where
      push("click", { target: lab && lab.length <= 60 ? lab : null, props: { dead: true, sel: selOf(t), x: r3(e.clientX / innerWidth), y: r3(e.clientY / innerHeight) } });
      return;
    }
    push("click", { target: labelOf(el), value: el.getAttribute("data-id") || el.getAttribute("href") || null,
                    props: { kind: el.tagName.toLowerCase() + (el.classList[0] ? "." + el.classList[0] : ""),
                             sel: selOf(el), x: r3(e.clientX / innerWidth), y: r3(e.clientY / innerHeight) } });
  }, true);

  let typing = null;
  document.addEventListener("input", (e) => {
    if (!e.isTrusted) return;
    const el = e.target;
    const textBox = el && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && /^(text|search)$/i.test(el.type || "text")));
    if (!textBox || /password/i.test(el.type || "") || el.autocomplete === "current-password") return;
    clearTimeout(typing);
    typing = setTimeout(() => {
      const v = String(el.value || "").trim();
      if (v.length >= 2) push("search", { target: labelOf(el) || el.placeholder || null, value: v.slice(0, 300), props: { sel: selOf(el) } });
    }, SEARCH_WAIT_MS);
  }, true);

  let hovered = null;
  let hoverAt = 0;
  document.addEventListener("mouseover", (e) => {
    if (!e.isTrusted) return;
    const el = e.target && e.target.closest && e.target.closest(HOVERABLE);
    if (el === hovered) return;
    if (hovered && Date.now() - hoverAt >= HOVER_MIN_MS) push("hover", { target: labelOf(hovered), ms: Date.now() - hoverAt });
    hovered = el;
    hoverAt = Date.now();
  }, true);

  // mouse path: points every 100 ms, sent as one 'move' per ~2 s or 40 points; ts = the first point
  let path = null;
  let pathTimer = null;
  const endPath = () => {
    clearTimeout(pathTimer);
    if (path && path.pts.length) push("move", { ts: new Date(path.t0).toISOString(), props: { pts: path.pts } });
    path = null;
  };
  document.addEventListener("mousemove", (e) => {
    if (!e.isTrusted || replaying()) return;
    const now = Date.now();
    if (path && now - path.last < MOVE_EVERY_MS) return;
    if (!path) path = { t0: now, last: 0, pts: [] };
    path.pts.push([now - path.t0, r3(e.clientX / innerWidth), r3(e.clientY / innerHeight)]);
    path.last = now;
    if (path.pts.length >= MOVE_MAX_PTS || now - path.t0 >= MOVE_SPAN_MS) endPath();
    else {
      clearTimeout(pathTimer);
      pathTimer = setTimeout(endPath, MOVE_SPAN_MS);   // the mouse stopped: send what there is
    }
  }, { capture: true, passive: true });

  // scrolling: the scrolled element (or "doc") and its position, throttled, plus the final position
  const scrollAt = new Map();
  const scrollEnd = new Map();
  const scrollTop = new Map();                    // the last logged position per element: the final one is not repeated
  const logScroll = (t) => {
    const isDoc = t === document || t === document.documentElement || t === document.body || t === window;
    const el = isDoc ? document.scrollingElement || document.documentElement : t;
    const top = Math.round(el.scrollTop);
    if (scrollTop.get(t) === top) return;
    scrollTop.set(t, top);
    const room = el.scrollHeight - el.clientHeight;
    push("scroll", { target: isDoc ? "doc" : selOf(el), props: { top, frac: room > 0 ? r3(el.scrollTop / room) : 0 } });
  };
  document.addEventListener("scroll", (e) => {
    if (!e.isTrusted || replaying()) return;
    const t = e.target;
    const now = Date.now();
    clearTimeout(scrollEnd.get(t));
    scrollEnd.set(t, setTimeout(() => logScroll(t), SCROLL_EVERY_MS));   // the final position
    if (now - (scrollAt.get(t) || 0) >= SCROLL_EVERY_MS) {
      scrollAt.set(t, now);
      logScroll(t);
    }
  }, { capture: true, passive: true });

  setInterval(flush, FLUSH_MS);
  addEventListener("pagehide", () => { endPath(); if (route.pillar || route.view) leave(); flush(true); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") { endPath(); flush(true); } });
  // login sessions: start on a fresh login, close on logout (the app reloads without a user) or after 2 hours idle
  const endSession = (reason, at) => {
    if (!loginSession || ls("kssl_login_session") !== loginSession) return false;   // another tab closed it already
    ls("kssl_login_session", null);
    push("logout", { session: loginSession, user: ls("kssl_login_user") || user(), ts: new Date(at || Date.now()).toISOString(),
                     props: { reason, ...(reason === "idle" ? { idle_ms: Date.now() - (at || Date.now()) } : {}) } });
    loginSession = null;
    return true;
  };
  const idleCheck = () => {
    if (!loginSession || !user()) return;
    const last = Number(ls("kssl_last_active") || 0);
    if (last && Date.now() - last > LOGIN_IDLE_MS && endSession("idle", last)) {
      ls("kssl_user", null);                     // auto logout (lib/login.js logout() does the same: drop the session, reload)
      flush(true);
      fetch("/api/logout", { method: "POST", headers: { "X-KSSL-Write": "1" } }).catch(() => {})
        .finally(() => setTimeout(() => location.reload(), 300));
    }
  };
  if (loginSession && !user()) endSession("logout");                     // the user logged out: the app reloaded without one
  else if (loginSession) idleCheck();                                     // back after a long break (or a closed browser)
  if (user() && !loginSession) {                                          // a fresh login
    loginSession = uuid();
    ls("kssl_login_session", loginSession);
    ls("kssl_login_user", user());               // the logout event names the user even after the login cleared it
    touched = 0;
    push("login", { props: { w: innerWidth, h: innerHeight } });
  }
  setInterval(idleCheck, 60 * 1000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") idleCheck(); });
  document.addEventListener("keydown", (e) => { if (e.isTrusted) touch(); }, true);

  if (route.pillar || route.view) pageView();      // otherwise the first route the app sets logs the first view
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  try {
    start();
  } catch (e) {
    /* never break the app for analytics */
  }
}
