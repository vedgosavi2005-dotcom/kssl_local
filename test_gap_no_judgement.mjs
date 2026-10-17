/* The gap surfaces print counts, stored scores and links; they invent no grade word, band, exposure or
 * explanatory sentence (gated sections must not invent either).
 *
 *     node test_gap_no_judgement.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { wireDataset } from "./src/lib/dataset.js";
import { buildGapModel } from "./src/lib/gapModel.js";
import { gapRivals, gapCategoryBody } from "./src/lib/gapAnalysis.js";
import { matchupGapHtml } from "./src/lib/specs.js";
import { setClient } from "./src/lib/client.js";

const fx = JSON.parse(readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url)));
const d = wireDataset(JSON.parse(JSON.stringify(fx)));
setClient(d.client);
const model = buildGapModel(d);
const WORDS = /\b(critical|moderate|severity|exposed|exposure|why this gap matters|recorded as an advantage)\b/i;

// the model carries no severity, urgency, rank score or exposure
assert.ok(model.length > 0);
for (const g of model) {
  for (const k of ["severity", "severity_pct", "urgency", "rank_score", "exposure_value", "exposure_horizon"])
    assert.equal(k in g, false, `${k} must not be on a gap`);
  for (const c of g.correlates) assert.equal("sev" in c, false);
}

// the matchup strip states the stored edge and links; no grade word or sentence
let any = 0;
for (const m of Object.values(d.matchups)) {
  const h = matchupGapHtml(m, model);
  if (m.edge == null) { assert.equal(h, ""); continue; }
  any++;
  assert.ok(h.includes(`Edge ${m.edge}/100`));
  assert.ok(!WORDS.test(h), h);
  assert.ok(!/class="mug (crit|high|med|lead|par)/.test(h));
}
assert.ok(any > 0);

// the category body prints counts and stored words only
const cats = [...new Set(Object.values(d.matchups).map((m) => m.cat))];
for (const cat of cats) {
  const rivals = gapRivals(d.matchups, cat);
  const h = gapCategoryBody(rivals, d.client.short || "", 0);
  assert.ok(!WORDS.test(h.replace(/<[^>]*>/g, " ")), `${cat}: ${(h.match(WORDS) || [])[0]}`);
  assert.ok(!/ga-acc-val (crit|high|med|low)/.test(h));
  assert.ok(!/class="gk-hero (crit|high)/.test(h));
  for (const r of rivals) assert.deepEqual(Object.keys(r.verdict), ["k"]);
}

assert.ok(cats.some((c) => gapRivals(d.matchups, c).length > 0), "at least one category has rivals");
const src = readFileSync(new URL("./src/lib/gapAnalysis.js", import.meta.url), "utf8");
assert.ok(!/GAP_BINS|gbin|Critical|Moderate|Calibre|MTOW|naval length/.test(src));
console.log("ok - gap surfaces carry counts, stored scores and links only");
