/* The Products / Profile sidebars' revenue facet, built from the roster like its two
   neighbours (lib/countryFacet.js).

   The tier word is the one the database stores (serving.competitive_competitor.revenue_tier,
   shipped as competitors[cid].revenue_filter) and is shown as it is. There are no tier
   labels, thresholds or currency rates in code: a company with no stored tier carries no
   tier, and with no tier on file there are no options -- the page draws no control rather
   than a dead one. */
import { facetOptions } from "./countryFacet.js";

/* A company's revenue tier: the stored word, or null. */
export function revenueTierOf(co) {
  const t = co && co.revenue_filter;
  return t && String(t).trim() ? String(t).trim() : null;
}

/* rows -> [{ v, n, l }] : every tier the rows carry, with its count; the label is the stored word. */
export function revenueOptions(rows) {
  return facetOptions(rows, (r) => (r && r.revenueTier) || null)
    .map((o) => ({ ...o, l: o.v }));
}
