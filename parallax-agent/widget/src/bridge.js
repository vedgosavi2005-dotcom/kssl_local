/* THE BRIDGE TO THE PRODUCT -- read its state and drive its navigation without changing
   a line of its code.

   The product keeps its route, the current selection and a description of what the open
   page shows ("headerReport") in a React context (state/AppState.jsx), and opens a page
   on a specific item with that context's jumpTo(pillar, view, payload) -- the same call
   its own global search makes. We find that context's value by walking the React fiber
   tree from #root and call it as the product itself would.

   If the product's internals ever change shape, every function here degrades instead of
   throwing: navigation falls back to the URL hash (#p=..&v=..), which the product's
   router follows on popstate, and page context falls back to what the hash says.

   Every product-specific name (selectors, state fields, routes) comes from
   adapter/product.json via product.js. */
import { APP, DOM, ROUTES, TEXT, fillText, inRoot, pick } from "./product.js";

const PILLAR_LABEL = ROUTES.pillar_labels;
const [PILLAR_KEY, VIEW_KEY] = APP.route_keys;

function rootFiber() {
  const el = document.querySelector(DOM.root);
  if (!el) return null;
  const key = Object.keys(el).find((k) => k.startsWith("__reactContainer$"));
  if (!key) return null;
  const f = el[key];
  // the container holds the HostRoot fiber it was created with; the live tree is
  // FiberRoot.current (React double-buffers fibers between renders)
  return (f && f.stateNode && f.stateNode.current) || f;
}

function findContexts() {
  // the product's optional add-on hook (parallax-agent/adapter/product-hook) is the stable route;
  // without it, the fiber walk below finds the same object
  const hooked = window[APP.hook_global] && window[APP.hook_global].state;
  if (hooked && typeof hooked[APP.navigate_fn] === "function") return { app: hooked, data: null };
  const out = { app: null, data: null };
  const stack = [rootFiber()];
  let n = 0;
  while (stack.length && n < 60000) {
    const f = stack.pop();
    n += 1;
    if (!f) continue;
    const v = f.memoizedProps && f.memoizedProps.value;
    if (v && typeof v === "object" && f.type && f.type._context) {
      if (!out.app && typeof v[APP.navigate_fn] === "function" && APP.route_keys.every((k) => k in v)) out.app = v;
      if (!out.data && APP.data_context_has.every((k) => v[k])) out.data = v;
      if (out.app && out.data) break;
    }
    if (f.sibling) stack.push(f.sibling);
    if (f.child) stack.push(f.child);
  }
  return out;
}

function routeFromHash() {
  try {
    const p = new URLSearchParams(String(window.location.hash || "").replace(/^#/, ""));
    return { pillar: p.get(ROUTES.pillar_param) || ROUTES.default.pillar, view: p.get(ROUTES.view_param) || ROUTES.default.view };
  } catch (e) {
    return { ...ROUTES.default };
  }
}

const plain = (v) =>
  String(v == null ? "" : v)
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();

/* What the user is looking at, as plain data for the agent. The page's own report is
   trimmed: section headings and label/value rows, no raw payload. */
export function getPageContext() {
  let app = null;
  let data = null;
  try {
    ({ app, data } = findContexts());
  } catch (e) {
    /* fall through to the hash */
  }
  if (!app) {
    const r = routeFromHash();
    return { pillar: r.pillar, view: r.view, viewTitle: "", selection: null, report: null };
  }
  const view = app[VIEW_KEY];
  const viewMeta = data && pick(data, APP.view_meta);
  const meta = (viewMeta && (viewMeta[view] || null)) || {};
  const rep = pick(app, APP.report);
  let report = null;
  if (rep && typeof rep === "object") {
    let budget = 5000;
    const sections = [];
    for (const s of rep.sections || []) {
      if (budget <= 0) break;
      const rows = [];
      // sections come as {h, rows} on most pages, {heading, facts} or {heading, body} on some
      for (const row of s.rows || s.facts || (s.body ? [s.body] : [])) {
        if (budget <= 0) break;
        const r = Array.isArray(row) ? [plain(row[0]).slice(0, 80), plain(row[1]).slice(0, 280)] : plain(row).slice(0, 280);
        budget -= JSON.stringify(r).length;
        rows.push(r);
      }
      sections.push({ h: plain(s.h || s.heading).slice(0, 120), rows });
    }
    report = { title: plain(rep.title), subtitle: plain(rep.subtitle), sections };
  }
  return {
    blocks: pageBlocks(),
    pillar: app[PILLAR_KEY],
    view,
    viewTitle: plain(meta.title || pick(app, APP.view_title) || ""),
    selection: pick(app, APP.selection) ? plain(pick(app, APP.selection)) : null,
    report,
  };
}

/* A short label for the dock's context line: "Competitive · Competitor · Caterpillar". */
export function pageLabel(ctx) {
  if (!ctx) return "";
  return [PILLAR_LABEL[ctx.pillar] || ctx.pillar, ctx.viewTitle || ctx.view, ctx.selection]
    .filter(Boolean)
    .join(" · ");
}

/* Open a page, on an item when payload says which -- exactly as the product's own
   search does. Returns true when the product's navigation handled it. */
export function navigate(pillar, view, payload) {
  try {
    const { app } = findContexts();
    if (app) {
      app[APP.navigate_fn](pillar, view, payload && Object.keys(payload).length ? payload : undefined);
      return true;
    }
  } catch (e) {
    /* fall back below */
  }
  window.location.hash = `#${ROUTES.pillar_param}=${encodeURIComponent(pillar)}&${ROUTES.view_param}=${encodeURIComponent(view)}`;
  return false;
}

/* Where the canvas goes: over the page BODY only -- right of the rail, below the page
   header and metric strip. Nothing of the product is hidden or restyled; the canvas sits
   on top of the body and lifts off when closed. */
export function productFrame() {
  const shell = document.querySelector(DOM.body);
  const rail = document.querySelector(DOM.rail);
  const top = document.querySelector(DOM.topbar);
  return {
    top: shell ? Math.round(shell.getBoundingClientRect().top) : top ? Math.round(top.getBoundingClientRect().bottom) : 0,
    left: rail ? Math.round(rail.getBoundingClientRect().right) : 0,
  };
}

/* ---------------------------------------------------------------- page blocks */

const norm = (t) => String(t || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

function ownText(e) {
  let t = "";
  for (const n of e.childNodes) if (n.nodeType === 3) t += n.textContent;
  return t.replace(/\s+/g, " ").trim();
}

/* a section heading: an h1-h6, or text styled the way the product styles its headings
   (adapter/product.json frontend.dom.heading) */
const HEAD = DOM.heading;
const HEAD_FONT = new RegExp(HEAD.font_family_match || ".", "i");
function isHeading(e) {
  if (/^H[1-6]$/.test(e.tagName)) return true;
  if ((HEAD.never || []).includes(e.tagName)) return false;
  const s = getComputedStyle(e);
  return (!HEAD.uppercase || s.textTransform === "uppercase") && HEAD_FONT.test(s.fontFamily) &&
    parseFloat(s.letterSpacing) > (HEAD.min_letter_spacing_px || 0);
}

function bodyScope() {
  return document.querySelector(DOM.body) || document.querySelector(DOM.root);
}

/* Section headings on the page in view -- the agent's focus targets for "show me where". */
export function pageBlocks(limit = 40) {
  const scope = bodyScope();
  if (!scope) return [];
  const out = [];
  const seen = new Set();
  for (const e of scope.querySelectorAll("*")) {
    if (e.closest(DOM.rail)) continue;
    const t = ownText(e);
    if (t.length < 3 || t.length > 70 || !isHeading(e)) continue;
    const k = norm(t);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(t);
    if (out.length >= limit) break;
  }
  return out;
}

function findBlock(needle) {
  const scope = bodyScope();
  if (!scope || !needle) return null;
  let best = null;
  let bestScore = 0;
  for (const e of scope.querySelectorAll("*")) {
    if (e.closest(DOM.rail) || !e.getClientRects().length) continue;
    const own = ownText(e);
    if (own.length < 2) continue;
    const t = norm(own);
    let score;
    if (t === needle) score = 100;
    else if (t.startsWith(needle) || (needle.startsWith(t) && t.length > 8)) score = 75;
    else if (t.includes(needle)) score = 55;
    else continue;
    if (isHeading(e)) score += 20;
    score -= Math.min(25, own.length / 12);
    if (score > bestScore) {
      bestScore = score;
      best = e;
    }
  }
  return best;
}

/* the block a label belongs to: climb until the box is a real section, not a word */
function blockOf(el) {
  let b = el;
  for (let i = 0; i < 5 && b.parentElement && b.parentElement !== bodyScope(); i += 1) {
    const r = b.getBoundingClientRect();
    if (r.height >= 70 && r.width >= 220) break;
    b = b.parentElement;
  }
  const r = b.getBoundingClientRect();
  return r.height > window.innerHeight * 0.85 ? el : b;
}

let ring = null;
function highlight(el) {
  if (ring) ring.remove();
  ring = document.createElement("div");
  ring.className = "pa-focus-ring";
  document.body.appendChild(ring);
  const own = ring;
  const t0 = performance.now();
  const place = (t) => {
    const r = el.getBoundingClientRect();
    own.style.cssText = `top:${r.top - 4}px;left:${r.left - 4}px;width:${r.width + 8}px;height:${r.height + 8}px;` +
      `opacity:${t - t0 > 2600 ? Math.max(0, 1 - (t - t0 - 2600) / 900) : 1}`;
  };
  place(t0); // drawn at once; frames then keep it on the block while the page settles
  const step = (t) => {
    if (own !== ring) return;
    place(t);
    if (t - t0 < 3500) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  setTimeout(() => {
    own.remove();
    if (ring === own) ring = null;
  }, 3600);
}

/* Scroll the page to the block that holds `text` and ring it for a few seconds. The page
   may still be rendering after a navigation, so it retries briefly. Only an overlay is
   drawn: the product's elements are scrolled, never restyled. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const inView = (el) => {
  const r = el.getBoundingClientRect();
  return r.bottom > 60 && r.top < window.innerHeight - 40;
};

export async function focusBlock(text, timeout = 6000) {
  const needle = norm(text);
  if (!needle) return false;
  // a page opened on a new item re-renders (and resets its own scroll) as the selection
  // lands, so let it settle before looking; then scroll, confirm, and retry if the page
  // moved it back
  await sleep(700);
  const until = Date.now() + timeout;
  let attempt = 0;
  while (Date.now() < until) {
    const hit = findBlock(needle);
    if (hit) {
      const block = blockOf(hit);
      const where = block.getBoundingClientRect().height > 300 ? "start" : "center";
      block.scrollIntoView({ behavior: attempt === 0 ? "smooth" : "auto", block: where });
      await sleep(attempt === 0 ? 650 : 200);
      if (inView(block) || attempt >= 3) {
        highlight(block);
        return inView(block);
      }
      attempt += 1;
      continue;
    }
    await sleep(250);
  }
  return false;
}

/* The product's own "Ask Parallax" button opens this dock instead of the offline
   assistant -- the button stays exactly where and how the product draws it. */
export function routeProductAssistant(open) {
  if (!DOM.assistant_button) return () => {};
  const onClick = (e) => {
    if (e.target.closest && e.target.closest(DOM.assistant_button)) {
      e.preventDefault();
      e.stopPropagation();
      open();
    }
  };
  document.addEventListener("click", onClick, true);
  return () => document.removeEventListener("click", onClick, true);
}


/* ---------------------------------------------------------------- the product's own ask boxes

   Several product panels carry an "Ask" box (a tender's assessment, a matchup dossier, a
   signal, a profile...). Their answers came from an offline keyword engine. While this
   widget runs, a question typed there goes to the agent instead -- with the page and the
   panel's selection as context -- and the answer appears in the dock. */
const PANEL_INPUT = DOM.panel_input;
const PANEL_SEND = DOM.panel_send;
const PANEL_CHIP = DOM.panel_chip;

function clearInput(input) {
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  set.call(input, "");
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

export function routeProductAsks(ask) {
  if (!PANEL_INPUT.length) return () => {};
  const take = (input) => {
    const q = (input && input.value || "").trim();
    if (!q) return false;
    clearInput(input);
    ask(q);
    return true;
  };
  const onKey = (e) => {
    if (e.key !== "Enter" || !e.target.matches || !e.target.matches(inRoot(PANEL_INPUT))) return;
    if (take(e.target)) {
      e.preventDefault();
      e.stopPropagation();
    }
  };
  const onClick = (e) => {
    const t = e.target.closest && e.target.closest(inRoot([...PANEL_SEND, ...PANEL_CHIP]));
    if (!t) return;
    if (t.matches(PANEL_CHIP.join(", "))) {
      e.preventDefault();
      e.stopPropagation();
      ask(t.textContent.trim());
      return;
    }
    const box = t.closest(DOM.panel_box.join(", "));
    const input = box && box.querySelector("input");
    if (take(input)) {
      e.preventDefault();
      e.stopPropagation();
    }
  };
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("click", onClick, true);
  return () => {
    document.removeEventListener("keydown", onKey, true);
    document.removeEventListener("click", onClick, true);
  };
}

/* ---------------------------------------------------------------- page-aware suggestions */

/* adapter/product.json frontend.page_suggestions: per view, `with_selection` (when an item is
   open; {name} is its name) and `default` */
export function pageSuggestions(ctx) {
  const v = ctx && ctx.view;
  const sel = ctx && ctx.selection;
  const name = sel && sel.length < 50 ? sel : null;
  const S = TEXT.pages[v] || TEXT.pages[ROUTES.default.view] || { default: [] };
  const list = (name && S.with_selection) || S.default || [];
  return list.map((q) => fillText(q.replaceAll("{name}", name || ""))).slice(0, 4);
}
