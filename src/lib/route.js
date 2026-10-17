/* The route: which pillar, which view, and how that reads to and from the URL hash.
 *
 * Pure -- no window, no React -- so test_route.mjs can pin it under node. AppState
 * owns the history calls; this file owns what a hash MEANS.
 *
 * Before this the router wrote every navigation with history.replaceState, listened to
 * nothing, and validated the pillar but never the view. Three things followed, all
 * found by driving the built app (2026-09-05): Back left the site because the session
 * had one history entry; a hash edited in the address bar of an open tab changed
 * nothing; and #v=does-not-exist rendered the rail beside an empty pane -- then saved
 * that route to localStorage, so it came back on every reload. */

import { viewVisible, firstVisibleView } from "./visibility.js";

export const PILLARS = ["competitive", "market", "technology"];
/* The pillar names, as the top bar prints them. */
export const PILLAR_LABEL = {
  competitive: "Competitive",
  market: "Market",
  technology: "Technology",
};

/* Which rail item each pillar opens on, and the pillar each rail belongs to. `label` is the rail word; `title` (only
   where the page heading reads differently) is the page heading. */
export const RAIL = {
  /* `gap-competitive` is ARCHIVED, not deleted: it is off the rail but Layout still
     routes it, so a saved route or a pasted #v=gap-competitive link still resolves.
     Same for `awarded-tenders` / `closed-tenders`, which the Market overview now
     carries as tabs. */
  competitive: [
    { view: "overview", label: "Overview", ix: "grid", overview: true },
    { view: "profile", label: "Competitor Profile", ix: "01" },
    { view: "threat-analysis", label: "Competitor Moment", ix: "02" },
    { view: "products", label: "Products", ix: "03" },
    { view: "positioning", label: "Product Evaluation", ix: "04" },
    { view: "partnerships", label: "Partnership", ix: "05" },
    { view: "projects", label: "Projects", ix: "06" },
    { view: "geo", label: "Geo Footprint", ix: "07" },
    { view: "patents-comp", label: "Patent", ix: "08" },
  ],
  market: [
    { view: "m-overview", label: "Top opportunity", ix: "grid", overview: true },
    { view: "tender", label: "Tenders", ix: "01" },
    { view: "global-requirement", label: "Global Requirements", ix: "02" },
    { view: "m-report", label: "Market Intelligence", ix: "03" },
  ],
  technology: [
    { view: "t-overview", label: "Overview", ix: "grid", overview: true },
    // "Innovations", not "Innovation Pipeline": the rail is 244px at its widest and the longer label does not fit;
    // the page's own header still reads Innovation Pipeline -- a nav label is not the page title.
    { view: "innovation", label: "Innovations", title: "Innovation Pipeline", ix: "01" },
  ],
};

/* a view's page heading; "" when the view is on no rail */
export function navTitle(pillar, view) {
  const item = (RAIL[pillar] || []).find((r) => r.view === view);
  return item ? item.title || item.label : "";
}

/* Views Layout still renders that are on no rail. */
export const ARCHIVED_VIEWS = {
  competitive: ["gap-competitive", "threat_analysis", "project", "finance", "finances"],
  market: ["awarded-tenders", "closed-tenders"],
  technology: [],
};

/* The signal-feed view of each pillar. The global search routes a signal here, and
   the feed takes its pending payload under this name -- ONE table, so the two cannot
   disagree (they did: the feed asked for "overview" on all three pillars). */
export const OVERVIEW_VIEW = {
  competitive: "overview",
  market: "m-overview",
  technology: "t-overview",
};

export const DEFAULT_ROUTE = { pillar: "competitive", view: "overview" };

const VIEWS_OF = {};
PILLARS.forEach((p) => {
  VIEWS_OF[p] = new Set(RAIL[p].map((r) => r.view).concat(ARCHIVED_VIEWS[p] || []));
});

/* The rail a reader sees: the routes whose section the database has not switched off. */
export function railFor(pillar) {
  return (RAIL[pillar] || []).filter((r) => viewVisible(r.view));
}

export function isKnownView(view, pillar) {
  if (pillar) return !!(VIEWS_OF[pillar] && VIEWS_OF[pillar].has(view));
  return PILLARS.some((p) => VIEWS_OF[p].has(view));
}

export function routeHash(pillar, view) {
  return `#p=${encodeURIComponent(pillar)}&v=${encodeURIComponent(view)}`;
}

/* A hash -> { pillar, view, repaired } or null.

   null means the hash carries no route (empty, foreign, or an unknown pillar): the
   caller falls back to its saved route or the default. An unknown or HIDDEN view on a
   known pillar is repaired to that pillar's first visible view and flagged, so the shell never boots
   into a pane its switch cannot render. */
export function parseRoute(hash) {
  const raw = String(hash == null ? "" : hash).replace(/^#/, "");
  if (!raw || !raw.includes("p=")) return null;
  let params;
  try {
    params = new URLSearchParams(raw);
  } catch (e) {
    return null;
  }
  const p = params.get("p");
  const v = params.get("v");
  if (!p || !v || !PILLARS.includes(p)) return null;
  if (isKnownView(v, p) && viewVisible(v)) return { pillar: p, view: v, repaired: false };
  return { pillar: p, view: firstVisibleView(p), repaired: true };
}
