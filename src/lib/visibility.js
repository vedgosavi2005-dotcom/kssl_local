/* Which sections the dataset says to show: ui.section_visibility, shipped as
 * `sectionVisibility: {key: bool}`.
 *
 * A key is visible ONLY when the map holds exactly `true` for it. No map, an empty map,
 * a missing key, `false`, "true" and 1 all read as hidden -- a section the database has
 * not switched on does not appear. The code behind a hidden section stays; it is gated,
 * not deleted.
 *
 * Pure module state, set once by DataProvider before anything renders. Exported pure
 * helpers keep route.js, search.js and overview.js free of React. */
import { RAIL } from "./route.js";

/* the eight keys the UI can gate */
export const HIDEABLE = Object.freeze([
  "gap-analysis",
  "finances",
  "stock",
  "parallax-read",
  "swot",
  "strategic-positioning",
  "product-images",
  "chat",
]);

/* views that exist only while a key is on (the routed ids, current and archived) */
export const VIEW_KEY = Object.freeze({
  "gap-analysis": "gap-analysis",
  "gap-competitive": "gap-analysis",
  finances: "finances",
  finance: "finances",
});

let map = null;

export function setVisibility(m) {
  map = m && typeof m === "object" && !Array.isArray(m) ? m : null;
}

export function isVisible(key) {
  return !!map && map[key] === true;
}

/* a view with no gating key is always visible */
export function viewVisible(view) {
  const key = VIEW_KEY[view];
  return key === undefined || isVisible(key);
}

/* the rail item a pillar opens on: its first visible view */
export function firstVisibleView(pillar) {
  const items = RAIL[pillar] || [];
  const hit = items.find((r) => viewVisible(r.view));
  return hit ? hit.view : "";
}
