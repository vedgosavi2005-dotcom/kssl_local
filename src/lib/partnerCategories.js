/* PARTNERSHIP CATEGORIES: every kind of tie a rival can have.

   The legend (groups, category and short labels, definitions, the overlap kind of each, display order) is front-end
   code (chrome.js PARTNER_GROUPS / PARTNER_CATEGORIES), like the rest of the screen's chrome. A row's `rel` is the
   slug of its stored partner_type; it is looked up in the legend by key or alias. A definition may contain {rival}
   and {client}: joins of dataset values, filled in here. Colours are a neutral palette indexed by legend position,
   so a colour means the same thing in the legend, the graph and the cards. */
import { stanceOf, PARTNER_GROUPS, PARTNER_CATEGORIES } from "./chrome.js";


/* line colour and fill, by position in the legend */
const PALETTE = [
  ["#e0a020", "#3a2f15"], ["#f0b95a", "#3b2d14"], ["#d98c3f", "#3b2616"], ["#c9a227", "#352c10"],
  ["#5b9bd5", "#1d3147"], ["#4a86c5", "#1b2f45"], ["#6fb1e0", "#1d3550"], ["#3fa8a0", "#17383a"],
  ["#58b5c9", "#173640"], ["#a58af0", "#2c2447"], ["#3fa86a", "#1d3a2b"], ["#b266c9", "#3a2347"],
  ["#b8b8c0", "#2a2a30"], ["#e0705a", "#40201a"], ["#9aa0aa", "#2a2a30"],
];
const NEUTRAL = ["#9aa0aa", "#2a2a30"];

const fill = (text, rival, client) =>
  String(text == null ? "" : text).replace(/\{rival\}/g, rival || "").replace(/\{client\}/g, client || "");

/* The categories. `rel` on a partner row is the category key (or one of its aliases). The dataset argument is
   accepted for the callers; the legend does not depend on it. */
export function buildCategories() {
  const groupLabel = Object.fromEntries(PARTNER_GROUPS.map((g) => [g.key, g.label]));
  const list = PARTNER_CATEGORIES.map((c, i) => {
    const [color, fillColor] = PALETTE[i % PALETTE.length];
    return {
      key: c.key, group: c.group, groupLabel: groupLabel[c.group] || "", label: c.label, short: c.short || "",
      def: c.def || "", overlapKind: c.overlapKind || "", color, fill: fillColor,
    };
  });
  const byKey = {};
  list.forEach((c, i) => {
    byKey[c.key] = c;
    PARTNER_CATEGORIES[i].aliases.forEach((a) => { if (!byKey[a]) byKey[a] = c; });
  });
  const groups = [];
  list.forEach((c) => { if (c.group && !groups.some((g) => g.key === c.group)) groups.push({ key: c.group, label: c.groupLabel || "" }); });
  /* a tie type the legend does not list gets a neutral entry with no label or definition of its own */
  const categoryOf = (rel) => byKey[rel] || { key: rel || "", group: "", label: "", short: "", def: "", overlapKind: "", color: NEUTRAL[0], fill: NEUTRAL[1] };
  const categoryDef = (rel, rival, client) => fill(categoryOf(rel).def, rival, client);
  /* every category with how many of `rows` fall in it (zero kept, so the whole legend shows) */
  function categoryCounts(items, keyOf = (r) => r) {
    const n = {};
    (items || []).forEach((r) => {
      const c = byKey[r && r.rel];
      if (!c) return;
      (n[c.key] = n[c.key] || new Set()).add(keyOf(r));
    });
    return list.map((c) => ({ ...c, n: n[c.key] ? n[c.key].size : 0 }));
  }
  return { list, groups, categoryOf, categoryDef, categoryCounts, fill };
}

/* The analyst's verdict on a tie for the client: the stored `verdict` of the row, and only when it is a stance
   (threat or watch). Any other stored verdict is not a stance and draws nothing. Returns the
   stance code, or null. */
export function verdictOf(row) {
  return stanceOf(String((row && row.verdict) || "").trim().toLowerCase()) || null;
}

/* the stored `impact` of the row as plain text (no markup, no trailing source link) */
export function impactText(row) {
  return String((row && row.impact) || "")
    .replace(/<span[^>]*>[\s\S]*?<\/span>/gi, "")
    .replace(/<[^>]+>/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
