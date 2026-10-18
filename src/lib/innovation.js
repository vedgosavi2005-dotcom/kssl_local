/* What the Innovation Pipeline prints for a record's analyst fields, and how its list
 * answers the global search box. Pure, so test_innovation_view.mjs runs it under node.
 *
 * `gap`, `mat`, `horizon`, `whatsNew` and `compNote` are analyst fields the served
 * record leaves null when nobody assessed them -- which is a different thing from a
 * neutral verdict. On the live-shape dump (2026-08-25) `gap` is null on EVERY row, and
 * the detail header's pill read `gap === "behind" ? "GAP" : gap === "parity" ? "WATCH"
 * : "AHEAD"`: every innovation opened under a green AHEAD, a verdict nobody gave,
 * above a Status row that correctly said "not assessed". */

import { clientShort } from "./client.js";

export const NOT_ASSESSED = "not assessed";
export const NOT_STATED = "not stated";

export const has = (v) => v != null && String(v).trim() !== "";

/* maturity labels -- one map, covering every `mat` value in the dataset (lab / dev / prod / fielded). */
export const MAT_LAB = {
  lab: "Lab / research",
  dev: "In development",
  prod: "In production",
  fielded: "Fielded / in service",
};
/* the client's position against a record: the stored code (`gap`) names the colour, this names the words */
export const gapLab = (gap) => {
  const c = clientShort();
  return { behind: `${c} behind`, parity: `${c} at parity`, ahead: `${c} ahead` }[gap] || "";
};

/* The maturity and position WORDS are stored (serving.technology_innovation_status.maturity_label / position_label,
   shipped as `matLabel` / `gapLabel`) and lead; a record with no stored word is named by its stored code through the
   maps above (an unknown maturity code is shown as served, never mapped to something it is not); one with neither
   shows nothing. */
export const maturityWord = (iv) =>
  iv && has(iv.matLabel) ? String(iv.matLabel).trim() : iv && has(iv.mat) ? MAT_LAB[iv.mat] || String(iv.mat) : "";
export const positionWord = (iv) => (iv && has(iv.gapLabel) ? String(iv.gapLabel).trim() : iv && has(iv.gap) ? gapLab(iv.gap) : "");

/* The row's stage pill: the short stage word of the stored maturity code (IN DEVELOPMENT, IN PRODUCTION, ...), as the
   reference prints it; the stored maturity sentence (`matLabel`) is the longer read in the detail. */
export const maturityStage = (iv) => (iv && has(iv.mat) ? MAT_LAB[iv.mat] || String(iv.mat) : "");

/* A missing maturity says so in words. */
export function maturityLabel(iv) {
  return maturityWord(iv) || NOT_STATED;
}

/* The header pill is a VERDICT. No assessed position, no pill -- and a value outside
   the vocabulary is not a verdict either. */
const PILL = { behind: "GAP", parity: "WATCH", ahead: "AHEAD" };
export function positionPill(gap) {
  if (!has(gap)) return null;
  const k = String(gap).trim();
  return PILL[k] ? { text: PILL[k], cls: k } : null;
}

const plain = (v) => (v == null ? "" : String(v)).replace(/<[^>]*>/g, " ");

/* The domain's rows that match the global search box: every token somewhere in the
   row's text (title, driver, horizon, background, impact), markup stripped so a
   reader can neither search for nor match on a <b>. Returns [{ item, index }] with
   the ORIGINAL index kept -- selection on this page is by index into the domain
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
