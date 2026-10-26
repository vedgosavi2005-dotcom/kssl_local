/* The Competitor Movement page lists moments only: the competitorNews rows that carry a stored `level` (ruling R4).
 * Plain news rows (no level) stay in the competitor's news, but are not moments and are not counted as moments.
 *
 *     node tests/unit/test_moments.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { wireDataset } from "../../src/lib/dataset.js";
import { isMoment, momentsOf } from "../../src/lib/moments.js";
import { navCounts } from "../../src/lib/overview.js";

const fx = JSON.parse(readFileSync("fixtures/kssl_dataset.json", "utf-8"));

assert.equal(isMoment({ level: "high" }), true);
assert.equal(isMoment({ level: "" }), false);
assert.equal(isMoment({ level: null }), false);
assert.equal(isMoment({}), false);
assert.equal(isMoment(null), false);
assert.deepEqual(momentsOf(null), []);
assert.deepEqual(momentsOf([{ id: 1 }, { id: 2, level: "watch" }]).map((m) => m.id), [2]);

const d = wireDataset(JSON.parse(JSON.stringify(fx)));
const rivals = Object.entries(d.competitorNews).filter(([k]) => k !== d.client.id);
const news = rivals.reduce((n, [, v]) => n + v.length, 0);
const moments = rivals.reduce((n, [, v]) => n + momentsOf(v).length, 0);
assert.equal(news, 30, "the fixture holds 30 rival news + moment rows");
assert.equal(moments, 13, "of which 13 are moments");
// owner 2026-10-23: Competitor Movement opens on every threat and watch card (one per story); the moves are its second tab
assert.equal(navCounts(d)["threat-analysis"], d.movementCards.length, "the rail counts the threat and watch cards Movement opens on");
assert.ok(d.movementCards.every((c) => !c.noStance), "Movement holds threats and watches only");

/* the page (owner 2026-10-25: competitor -> events -> episodes) is built from threat / watch signals only, not every news row */
const page = readFileSync("src/pages/competitive/ThreatAnalysis.jsx", "utf-8");
assert.ok(/competitiveCards[\s\S]{0,40}\.filter\(\(c\) => stanceOf\(/.test(page), "ThreatAnalysis builds its episodes from threat / watch signals");
assert.ok(!/competitorNews/.test(page), "ThreatAnalysis no longer maps every news row");

console.log("ok - moment page and rail list only rows that carry a level (13 of 30 on the fixture)");
