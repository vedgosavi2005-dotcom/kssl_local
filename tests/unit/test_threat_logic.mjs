/* Threat is a stored field of the competitor and of the signal; the browser re-grades nothing
 * (lib/threat.js, ruling R5/R7).
 *
 *     node tests/unit/test_threat_logic.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as TH from "../../src/lib/threat.js";
import { wireDataset } from "../../src/lib/dataset.js";

const { threatOf } = TH;

// a competitor's threat is its own field, as stored; absent -> null
assert.equal(threatOf({ name: "x" }), null);
assert.equal(threatOf({ threat: "" }), null);
assert.equal(threatOf({ threat: null }), null);
assert.equal(threatOf({ threat: "threat" }), "threat");
assert.equal(threatOf({ threat: "watch" }), "watch");
// a stance is threat or watch: a legacy third value is no stance, never relabelled
assert.equal(threatOf({ threat: "fav" }), null);
assert.equal(threatOf({ threat: "high" }), null);
assert.equal(threatOf(null), null);

// no keyword engine: the regex re-grader and its severity grades are gone
for (const gone of ["refineThreat", "refineThreats", "SEV", "NON_KSSL", "PLATFORM", "INDIA", "EXPORT"])
  assert.equal(gone in TH, false, `${gone} must not be exported`);
const src = readFileSync(new URL("../../src/lib/threat.js", import.meta.url), "utf8");
assert.ok(!/RegExp|\/\b\(|saudi|spanish|qatari|ISR|electro|howitzer|india/i.test(src), "no keyword regexes in threat.js");

// the loader does not move a stored dir (threat or watch) on any competitor signal
const fx = JSON.parse(readFileSync(new URL("../../fixtures/kssl_dataset.json", import.meta.url)));
const wired = wireDataset(JSON.parse(JSON.stringify(fx)));
const stored = new Map(fx.competitiveCards.map((c) => [c.id, c.dir]));
assert.ok(stored.size > 0);
const isStance = (w) => w === "threat" || w === "watch";
for (const c of wired.competitiveCards) {
  // a stored threat or watch is kept word for word; any other stored value is no stance (never relabelled)
  assert.equal(c.dir, isStance(stored.get(c.id)) ? stored.get(c.id) : "", `${c.id}: dir is the stored stance or none`);
  assert.equal("threatWhy" in c, false, "no browser-written threat reason");
}
const legacy = fx.competitiveCards.filter((c) => c.dir && !isStance(c.dir));
assert.ok(legacy.length > 0, "the fixture carries a card stored with a third stance");
const lane = wired.overviewConfig.competitive.cards.map((c) => c.id);
for (const c of legacy) assert.equal(lane.includes(c.id), false, `${c.id}: a card with no threat/watch stance is not on the competitive overview`);
for (const c of legacy) assert.ok(wired.competitiveCards.some((w) => w.id === c.id && w.noStance), "it is still served, marked as having no stance");
assert.equal(lane.length, fx.competitiveCards.filter((c) => isStance(c.dir) || !c.dir).length, "every other card is on the overview");

// the competitor rows carry their threat word to the profile unchanged
for (const [id, c] of Object.entries(fx.competitors)) {
  if (c.dir === "client") continue;
  assert.equal(threatOf(wired.competitors[id]), threatOf(c));
}

console.log("ok - threat is the stored field; nothing is re-graded in the browser");
