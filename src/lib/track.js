/* Usage log: page views (and time on each), clicks, searches, and hovers on cards -> POST /api/track -> activity.event
   (db/setup/31_user_activity.sql; reading it: docs/ui_port/ACTIVITY_LOG.md). First-party and anonymous: a random id per browser
   and per visit, no login, no IP stored. Off when the browser sends Do Not Track, and inert outside a browser (unit tests).
   Imported once for its side effect (src/App.jsx). The server decides live vs review, never this file. */

const FLUSH_MS = 5000;
const IDLE_MS = 30 * 60 * 1000;        // a new visit after 30 minutes without an event
const HOVER_MIN_MS = 800;              // a hover shorter than this is a pass-over, not interest
const SEARCH_WAIT_MS = 1200;           // the search is logged once typing pauses
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

function start() {
  const visitor = stored(localStorage, "kssl_visitor", uuid);
  let session = null;
  let lastAt = 0;
  const sessionId = () => {
    const now = Date.now();
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
  const push = (type, extra) => {
    queue.push({ type, visitor, session: sessionId(), ts: new Date().toISOString(), ...route, ...extra });
    if (queue.length >= 90) flush();
  };
  const flush = (leaving) => {
    if (!queue.length) return;
    const body = JSON.stringify(queue.splice(0, 90));
    fetch("/api/track", { method: "POST", keepalive: !!leaving, headers: { "Content-Type": "application/json", "X-KSSL-Write": "1" }, body })
      .catch(() => {});                  // the log never breaks the page
  };

  const pageView = () => push("page_view", { props: { w: innerWidth, h: innerHeight, ref: document.referrer ? new URL(document.referrer).host : null } });
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
    const el = e.target && e.target.closest && e.target.closest(CLICKABLE);
    if (!el) return;
    push("click", { target: labelOf(el), value: el.getAttribute("data-id") || el.getAttribute("href") || null,
                    props: { kind: el.tagName.toLowerCase() + (el.classList[0] ? "." + el.classList[0] : "") } });
  }, true);

  let typing = null;
  document.addEventListener("input", (e) => {
    const el = e.target;
    if (!el || el.tagName !== "INPUT" || !/^(text|search)$/i.test(el.type || "text")) return;
    clearTimeout(typing);
    typing = setTimeout(() => {
      const v = String(el.value || "").trim();
      if (v.length >= 2) push("search", { target: labelOf(el) || el.placeholder || null, value: v.slice(0, 300) });
    }, SEARCH_WAIT_MS);
  }, true);

  let hovered = null;
  let hoverAt = 0;
  document.addEventListener("mouseover", (e) => {
    const el = e.target && e.target.closest && e.target.closest(HOVERABLE);
    if (el === hovered) return;
    if (hovered && Date.now() - hoverAt >= HOVER_MIN_MS) push("hover", { target: labelOf(hovered), ms: Date.now() - hoverAt });
    hovered = el;
    hoverAt = Date.now();
  }, true);

  setInterval(flush, FLUSH_MS);
  addEventListener("pagehide", () => { if (route.pillar || route.view) leave(); flush(true); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(true); });
  if (route.pillar || route.view) pageView();      // otherwise the first route the app sets logs the first view
}

if (typeof window !== "undefined" && typeof document !== "undefined" && navigator.doNotTrack !== "1" && window.doNotTrack !== "1") {
  try {
    start();
  } catch (e) {
    /* never break the app for analytics */
  }
}
