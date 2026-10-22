/* Colour, by the job it does -- in the PRODUCT's own palette, so a generated chart looks
   like one the platform drew itself.

   CATEGORICAL is the product's validated series palette (source/frontend/src/lib/
   marketOverview.js SERIES), re-checked here with the dataviz palette checker on the
   canvas surface #161618: lightness band, chroma floor, normal-vision floor and contrast
   PASS; worst adjacent CVD pair is 7.6 (pink/green), the band that is legal with secondary
   encoding -- every multi-series chart carries a legend and tooltips.

   Slots are assigned in fixed order, never cycled. Companies are entities, so each has ONE
   colour in every view (colour follows the entity, never its rank): the client takes
   slot 1 and each rival its own (adapter/product.json companies[].color_slot). Past the palette, series fold to "Other" grey. */

import { COMPANIES, RUNTIME, THEME } from "../product.js";

/* all from adapter/product.json frontend.theme (the product's palette and ink tokens) */
export const SURFACE = THEME.surface;
export const PANEL = THEME.panel;
export const CATEGORICAL = THEME.palette;
export const OTHER = THEME.other;            // the product's OTHER_COLOR
export const MUTED_MARK = THEME.muted_mark;  // de-emphasised bars beside a highlight
export const SEQUENTIAL = THEME.sequential;
export const INK = THEME.ink;                // primary, secondary, muted, faint, grid, axis, line
export const FONT = THEME.font_sans;
export const MONO = THEME.font_mono;

/* company -> fixed palette slot (companies[].color_match, a case-insensitive regex): from
   product.json, or from the data when the service sends the company list */
const slotsOf = (list) => (Array.isArray(list) ? list : [])
  .filter((c) => c && c.color_match != null && c.color_slot != null)
  .map((c) => {
    try {
      return [new RegExp(c.color_match, "i"), c.color_slot];
    } catch (e) {
      return null;
    }
  })
  .filter(Boolean);
const LISTED = slotsOf(COMPANIES);
let fromData = null;

export function companySlot(name) {
  if (RUNTIME.companies && !fromData) fromData = slotsOf(RUNTIME.companies);
  const s = String(name || "");
  for (const [re, slot] of fromData || LISTED) if (re.test(s)) return slot;
  return null;
}

/* name -> colour for a series domain. Known companies keep their fixed colour; anything
   else takes the next free slot in domain order; past the palette, "Other" grey. */
export function colorMap(names) {
  const map = {};
  const used = new Set();
  names.forEach((n) => {
    const slot = companySlot(n);
    if (slot !== null) {
      map[n] = CATEGORICAL[slot];
      used.add(slot);
    }
  });
  let next = 0;
  names.forEach((n) => {
    if (map[n]) return;
    while (used.has(next)) next += 1;
    map[n] = next < CATEGORICAL.length ? CATEGORICAL[next] : OTHER;
    used.add(next);
  });
  return map;
}

export function sequentialColor(t) {
  const i = Math.max(0, Math.min(SEQUENTIAL.length - 1, Math.round(t * (SEQUENTIAL.length - 1))));
  return SEQUENTIAL[i];
}

/* white or ink for a label sitting inside a fill */
export function inkOn(hex) {
  const n = parseInt(hex.slice(1), 16);
  const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return lum > 0.6 ? "#0b0b0b" : "#f5f5f4";
}
