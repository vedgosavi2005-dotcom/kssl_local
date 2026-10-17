/* Global requirements are the stored requirement rows, linked by their prefixed card id.
 *
 *     node test_global_requirements.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { globalRequirements, globalCardFilter, requirementCardId } from "./src/lib/globalRequirements.js";

const fx = JSON.parse(readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url)));
const rows = globalRequirements(fx);

// one row per stored requirement, in stored order, none dropped
assert.equal(rows.length, fx.globalRequirements.length);
assert.ok(rows.length > 0);
assert.deepEqual(rows.map((r) => r.id), fx.globalRequirements.map((r) => `req-${r.id}`));

// every cross-link id is the market card's own id (the req- prefixed one), never the raw stored id
const cardIds = new Set(fx.marketCards.map((c) => c.id));
for (const r of rows) assert.ok(cardIds.has(r.id), `${r.id} is a market card id`);
for (const r of fx.globalRequirements) assert.equal(requirementCardId(r), `req-${r.id}`);

// the feed filter keeps exactly the requirement cards
const keep = fx.marketCards.filter(globalCardFilter(fx));
assert.deepEqual(keep.map((c) => c.id).sort(), rows.map((r) => r.id).sort());
assert.equal(fx.marketCards.some((c) => /^upd-/.test(c.id) && globalCardFilter(fx)(c)), false);

// text comes from stored fields
assert.equal(rows[0].why, fx.details["req-" + fx.globalRequirements[0].id]?.why || fx.globalRequirements[0].strategicAssessment);
assert.equal(globalRequirements({}).length, 0);

console.log("ok - global requirements follow the stored rows and their req- card ids");
