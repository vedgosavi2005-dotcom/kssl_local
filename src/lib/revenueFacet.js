/* The revenue facet, built from the roster like its neighbours (lib/countryFacet.js).

   The tier is the stored competitive_competitor.revenue_tier text, shown as stored. No
   band definition, FX rate or cut-off lives here: which tier a company is in is decided
   when the row is written. A company with no stored tier is simply not offered under any
   option; the caller may add a neutral "not on record" bucket for it. */
import { facetOptions } from "./countryFacet.js";

export function revenueTierOf(co) {
  const t = co && co.revenue_tier != null ? String(co.revenue_tier).trim() : "";
  return t || null;
}

/* rows -> [{ v, n, l }] : every stored tier the rows carry, by name; the label is the tier. */
export function revenueOptions(rows) {
  return facetOptions(rows, (r) => (r && r.revenueTier) || null)
    .map((o) => ({ ...o, l: o.v }))
    .sort((a, b) => a.v.localeCompare(b.v));
}
