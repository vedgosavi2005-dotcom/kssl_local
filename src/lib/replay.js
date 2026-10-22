/* SESSION REPLAY (owner 22 Oct; review site only): the activity log of one person played back on the UI like a video.
   This file is the part with no screen: the playback clock (with long idle gaps shortened), and finding on today's page
   the element a logged click / hover / search was on. The player is components/replay/Replay.jsx.

   A replay re-runs the session on TODAY's data: an item since removed can only be shown as a caption. */
import { labelOf } from "./track.js";

export const IDLE_GAP_MS = 5000;     // a pause longer than this ...
export const IDLE_SHOWN_MS = 1500;   // ... is shown as this long when "skip inactivity" is on
export const HOVER_SHOWN_MAX_MS = 3000;

const t = (e) => new Date(e.ts).getTime();

/* events (sorted, as /api/review/activity/events returns them) -> steps on the playback clock:
   {at: ms on the clock, real: epoch ms when it happened, kind, ev, x?, y?}. A 'move' event becomes one 'cursor' step
   per recorded point. With skipIdle, every gap longer than IDLE_GAP_MS counts as IDLE_SHOWN_MS. */
export function timeline(events, { skipIdle = true } = {}) {
  const raw = [];
  (events || []).forEach((ev) => {
    const at = t(ev);
    if (!Number.isFinite(at)) return;
    if (ev.type === "move" && ev.props && Array.isArray(ev.props.pts)) {
      ev.props.pts.forEach(([dt, x, y]) => raw.push({ real: at + (Number(dt) || 0), kind: "cursor", ev, x, y }));
    } else {
      raw.push({ real: at, kind: ev.type, ev });
    }
  });
  raw.sort((a, b) => a.real - b.real);
  let clock = 0;
  return raw.map((s, i) => {
    if (i > 0) {
      const gap = s.real - raw[i - 1].real;
      clock += skipIdle && gap > IDLE_GAP_MS ? IDLE_SHOWN_MS : gap;
    }
    return { ...s, at: clock };
  });
}

/* the route a page_view asks for: its full hash when logged, else #p=<pillar>&v=<view> */
export function hashOf(ev) {
  const h = ev && ev.props && ev.props.hash;
  if (h && String(h).startsWith("#")) return String(h);
  return ev && (ev.pillar || ev.view) ? `#p=${encodeURIComponent(ev.pillar || "")}&v=${encodeURIComponent(ev.view || "")}` : null;
}

const visible = (el) => !!el && (el.checkVisibility ? el.checkVisibility({ checkVisibilityCSS: true }) : el.offsetParent !== null);
const safeAll = (root, sel) => {
  try {
    return [...root.querySelectorAll(sel)];
  } catch (e) {
    return [];                                  // a logged selector that is not valid CSS today
  }
};
const PICKABLE = "a,button,[role=button],[role=tab],select,input,.alert,.tcard,.pat-li,.cm-title,.proj-row,.pg-partner-roster-card,[data-track],[data-track-hover]";

/* the element a logged event was on, on the page as it is now: its selector + label, else any element with that label,
   else what is under the logged point. null when nothing matches (the player then shows a caption only). */
export function findTarget(ev, root = document) {
  // the item's own id first (a card's data-id): right whatever order or numbering the page shows now
  if (ev.value && !/^(https?:|\/|#)/.test(ev.value)) {
    const esc = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(String(ev.value)) : String(ev.value).replace(/[^\w-]/g, "\\$&");
    const byId = safeAll(root, `[data-id="${esc}"]`).filter(visible);
    if (byId.length) return byId[0];
  }
  const label = ev.target ? sameLabel(ev.target) : null;
  const sel = ev.props && ev.props.sel;
  const byLabel = (list) => list.filter((el) => visible(el) && sameLabel(labelOf(el)) === label);
  if (sel && label) {
    const hit = byLabel(safeAll(root, sel));
    if (hit.length) return pickByValue(hit, ev.value);
  }
  if (label) {
    const hit = byLabel(safeAll(root, PICKABLE));
    if (hit.length) return pickByValue(hit, ev.value);
  }
  const p = ev.props || {};
  if (typeof p.x === "number" && typeof p.y === "number" && root.elementFromPoint) {
    return root.elementFromPoint(p.x * innerWidth, p.y * innerHeight);
  }
  return null;
}

// a card's label starts with its position in the list ("09 Nibe Group ..."), which differs between two pages: compare without it
export const sameLabel = (t) => String(t || "").replace(/^\s*\d{1,3}\s+/, "").trim();

function pickByValue(list, value) {
  if (!value) return list[0];
  return list.find((el) => el.getAttribute("data-id") === value || el.getAttribute("href") === value) || list[0];
}

/* the search box a logged search was typed in: same label / placeholder, else the first visible text box */
export function findInput(ev, root = document) {
  const boxes = safeAll(root, "input[type=text], input[type=search], input:not([type])").filter(visible);
  return boxes.find((el) => labelOf(el) === ev.target || el.placeholder === ev.target) || boxes[0] || null;
}

/* the scrolled element: "doc" = the page, else its logged selector (first visible match) */
export function findScroller(ev, root = document) {
  if (!ev.target || ev.target === "doc") return root.scrollingElement || root.documentElement;
  return safeAll(root, ev.target).find(visible) || null;
}

/* what the player never repeats, only shows: review actions, the player itself, Ask Parallax (it spends model budget),
   and links that leave the site */
export function replayUnsafe(el) {
  if (!el || !el.closest) return true;
  if (el.closest(".rv-bar, .rv-banner, .rv-drawer, .rp-bar, .rp-panel, [class^='pa-'], [class*=' pa-']")) return true;
  const a = el.closest("a[href]");
  return !!(a && (a.target === "_blank" || /^https?:/i.test(a.getAttribute("href") || "")));
}

/* one line for the caption under the player */
export function captionOf(step) {
  const e = step.ev || {};
  const what = e.target ? `“${String(e.target).slice(0, 70)}”` : "";
  switch (step.kind) {
    case "page_view": return `Opened ${[e.pillar, e.view].filter(Boolean).join(" › ") || "a page"}`;
    case "click": return `Clicked ${what || "the page"}`;
    case "search": return `Searched “${String(e.value || "").slice(0, 70)}”`;
    case "hover": return `Looked at ${what} for ${Math.round((e.ms || 0) / 1000)} s`;
    case "scroll": return "Scrolled";
    case "leave": return `Left ${e.view || "the page"} after ${fmtDur(e.ms)}`;
    default: return "";
  }
}

export function fmtDur(ms) {
  const s = Math.round((ms || 0) / 1000);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

/* Self-check: node src/lib/replay.js */
export function replaySelfCheck() {
  const bad = [];
  const ok = (name, c) => { if (!c) bad.push(name); };
  const at = (s) => `2026-10-20T10:00:${String(s).padStart(2, "0")}.000Z`;
  const ev = [
    { ts: at(0), type: "page_view", pillar: "market", view: "tender" },
    { ts: at(2), type: "move", props: { pts: [[0, 0.1, 0.1], [500, 0.2, 0.2]] } },
    { ts: at(4), type: "click", target: "Lockheed Martin" },
    { ts: "2026-10-20T10:05:00.000Z", type: "search", value: "Spike", target: "Search" },
  ];
  const tl = timeline(ev);
  ok("a move becomes one cursor step per point", tl.filter((s) => s.kind === "cursor").length === 2);
  ok("steps keep their real spacing", tl.find((s) => s.kind === "click").at === 4000);
  ok("a 5-minute pause is shortened to 1.5 s", tl[tl.length - 1].at === 4000 + IDLE_SHOWN_MS);
  ok("without skipping, the pause is kept", timeline(ev, { skipIdle: false }).slice(-1)[0].at === 300000);
  ok("a page view replays its route", hashOf(ev[0]) === "#p=market&v=tender");
  ok("a logged full hash wins", hashOf({ props: { hash: "#p=market&v=tender&x=1" } }) === "#p=market&v=tender&x=1");
  ok("a list position is not part of the label", sameLabel("09 Nibe Group PULS") === sameLabel("07 Nibe Group PULS"));
  ok("captions read as words", captionOf({ kind: "search", ev: ev[3] }) === "Searched “Spike”" && fmtDur(125000) === "2 min 5 s");
  return bad;
}

if (typeof process !== "undefined" && process.argv && /replay\.js$/.test(process.argv[1] || "")) {
  const bad = replaySelfCheck();
  console.log(bad.length ? "FAIL: " + bad.join("; ") : "replay self-check ok");
  if (bad.length) process.exit(1);
}
