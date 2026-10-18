/* Competitive spec: at most 10 threats, the riskiest (probability x impact) first; on a tie the one that lands sooner,
 * then the one in a client market. Watch cards are untouched by the cap.
 *
 *     node --test test_threat_cap.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { capThreats, compareRisk } from "../../src/lib/overview.js";
import { THREAT_CAP } from "../../src/lib/chrome.js";

const T = (id, risk, timeToEffect, inClientMarket, dir = "threat") => ({ id, dir, risk, timeToEffect, inClientMarket });

test("risk order: probability x impact, then sooner effect, then in a client market", () => {
  const cards = [T("low", 16, "lt_1y", "yes"), T("late", 25, "gt_3y", "yes"), T("soon-out", 25, "lt_1y", "no"), T("soon-in", 25, "lt_1y", "yes")];
  assert.deepEqual(cards.sort(compareRisk).map((c) => c.id), ["soon-in", "soon-out", "late", "low"]);
});

test("at most THREAT_CAP threats are kept, the riskiest; watch cards all pass", () => {
  assert.equal(THREAT_CAP, 10);
  const threats = Array.from({ length: 12 }, (_, i) => T(`t${i}`, i + 1, "1_3y", "yes"));
  const watch = [T("w1", 25, "lt_1y", "yes", "watch"), T("w2", null, null, null, "watch")];
  const kept = capThreats([...watch, ...threats], THREAT_CAP);
  assert.equal(kept.filter((c) => c.dir === "threat").length, 10);
  assert.ok(!kept.some((c) => c.id === "t0" || c.id === "t1"), "the two least risky threats are the ones left out");
  assert.ok(kept.some((c) => c.id === "w1") && kept.some((c) => c.id === "w2"));
  assert.deepEqual(capThreats(threats.slice(0, 3), THREAT_CAP).length, 3, "fewer than the cap: all kept");
});
