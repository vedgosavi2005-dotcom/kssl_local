/* Check for the aggregate "Other" pie slice colour: it must be OTHER_COLOR grey (the
   same colour its folded-in members render as), never a SERIES category hue. Before the
   fix, _otherLabel sat in slot SERIES.length-1 and took SERIES[8]. Run: node this file. */
import assert from "node:assert/strict";
import { initCategoryPalette, CATEGORY_COLOR, sliceLabel } from "./marketOverview.js";

/* Mirror of the module's private constants (marketOverview.js). */
const OTHER_COLOR = "#94A3B8";
const SERIES = ["#3B82F6", "#D97706", "#0891B2", "#DC2626", "#8B5CF6",
                "#EA580C", "#059669", "#EC4899", "#65A30D"];

/* Eleven categories, distinct descending counts, so the rank order is deterministic and
   the tail (ranks 9-11) is forced to fold into one grey "Other" slice. */
const tenders = [];
for (let i = 0; i < 11; i += 1) {
  const cat = `C${String(i + 1).padStart(2, "0")}`;
  for (let j = 0; j < 11 - i; j += 1) tenders.push({ cat }); // C01=11 rows ... C11=1
}

const ranked = initCategoryPalette(tenders);
assert.deepEqual(ranked.slice(0, 3), ["C01", "C02", "C03"], "rank order is by count desc");

// TOP = SERIES.length-1 = 8 named categories; C09/C10/C11 fold into "Other".
const foldedCat = ranked[8]; // "C09"
const otherLabel = sliceLabel(foldedCat);
assert.equal(otherLabel, "Other (3 categories)", "the tail aggregates under one label");

const aggColor = CATEGORY_COLOR(otherLabel);
const foldedColor = CATEGORY_COLOR(foldedCat);
assert.equal(foldedColor, OTHER_COLOR, "a folded-in member renders grey");
assert.equal(aggColor, OTHER_COLOR, "the aggregate Other slice must be grey, not a SERIES hue");
assert.equal(aggColor, foldedColor, "the aggregate must match its folded-in members' colour");
assert.ok(!SERIES.includes(aggColor), "the aggregate Other slice must not take a SERIES category hue");

// sanity: the named top categories DID take their fixed SERIES hues, so folding really happened
ranked.slice(0, 8).forEach((c, i) => {
  assert.equal(CATEGORY_COLOR(c), SERIES[i], `named category ${c} keeps its fixed SERIES hue`);
});

console.log("marketOverview otherColor: all assertions passed");
