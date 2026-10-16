/* Helpers for the Innovation Pipeline. Pure. Everything the page prints about a record
 * (maturity, position, badge, horizon, drivers) is a stored value; this file only
 * decides whether one is present and how the list answers the global search box. */

export const has = (v) => v != null && String(v).trim() !== "";

/* A stored free-text word as a CSS class token ("In production" -> "in-production"). */
export const cls = (v) => (has(v) ? String(v).trim().toLowerCase().replace(/[^a-z0-9]+/g, "-") : "");

const plain = (v) => (v == null ? "" : String(v)).replace(/<[^>]*>/g, " ");

/* The domain's rows that match the global search box: every token somewhere in the
   row's text (title, drivers, horizon, background, impact). Returns [{ item, index }]
   with the ORIGINAL index kept -- selection on this page is by index into the domain
   list, and a filtered view must still select the row the reader clicked. */
export function filterInnovations(list, query) {
  const rows = (list || []).map((item, index) => ({ item, index }));
  const tokens = String(query == null ? "" : query).toLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!tokens.length) return rows;
  return rows.filter(({ item }) => {
    if (!item) return false;
    const hay = [item.t, item.driver, item.horizon, item.body, item.impact].map(plain).join(" ").toLowerCase();
    return tokens.every((t) => hay.includes(t));
  });
}
