/* Competitive spec (owner 2026-10-23: 15 threats, 15 watches, last 90 days): at most THREAT_CAP threats, the riskiest (probability x impact) first; on a tie the one that lands sooner,
 * then the one in a client market. Watch cards are untouched by the cap.
 *
 *     node --test test_threat_cap.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { capThreats, compareRisk, recentCards } from "../../src/lib/overview.js";
import { THREAT_CAP, WATCH_CAP, OVERVIEW_DAYS } from "../../src/lib/chrome.js";

const T = (id, risk, timeToEffect, inClientMarket, dir = "threat") => ({ id, dir, risk, timeToEffect, inClientMarket });

test("risk order: probability x impact, then sooner effect, then in a client market", () => {
  const cards = [T("low", 16, "lt_1y", "yes"), T("late", 25, "gt_3y", "yes"), T("soon-out", 25, "lt_1y", "no"), T("soon-in", 25, "lt_1y", "yes")];
  assert.deepEqual(cards.sort(compareRisk).map((c) => c.id), ["soon-in", "soon-out", "late", "low"]);
});

test("at most THREAT_CAP threats are kept, the riskiest; watch cards all pass", () => {
  assert.equal(THREAT_CAP, 15);
  const threats = Array.from({ length: 17 }, (_, i) => T(`t${i}`, i + 1, "1_3y", "yes"));
  const watch = [T("w1", 25, "lt_1y", "yes", "watch"), T("w2", null, null, null, "watch")];
  const kept = capThreats([...watch, ...threats], THREAT_CAP);
  assert.equal(kept.filter((c) => c.dir === "threat").length, 15);
  assert.ok(!kept.some((c) => c.id === "t0" || c.id === "t1"), "the two least risky threats are the ones left out");
  assert.ok(kept.some((c) => c.id === "w1") && kept.some((c) => c.id === "w2"));
  assert.deepEqual(capThreats(threats.slice(0, 3), THREAT_CAP).length, 3, "fewer than the cap: all kept");
});

test("watches are capped the same way, and threats are untouched by the watch cap", () => {
  assert.equal(WATCH_CAP, 15);
  const watch = Array.from({ length: 20 }, (_, i) => T(`w${i}`, i + 1, "1_3y", "yes", "watch"));
  const threats = Array.from({ length: 3 }, (_, i) => T(`t${i}`, 1, "1_3y", "yes"));
  const kept = capThreats([...threats, ...watch], WATCH_CAP, "watch");
  assert.equal(kept.filter((c) => c.dir === "watch").length, 15);
  assert.ok(!kept.some((c) => ["w0", "w1", "w2", "w3", "w4"].includes(c.id)), "the five least risky watches are left out");
  assert.equal(kept.filter((c) => c.dir === "threat").length, 3);
});

test("the overview keeps the last OVERVIEW_DAYS days by the card's date; undated and older cards stay off it", () => {
  assert.equal(OVERVIEW_DAYS, 90);
  const today = new Date(2026, 9, 23);
  const cards = [{ id: "new", ago: "20 Oct 2026" }, { id: "edge", ago: "25 Jul 2026" }, { id: "old", ago: "24 Jul 2026" },
                 { id: "month", ago: "Aug 2026" }, { id: "oldmonth", ago: "Jul 2026" }, { id: "nodate", ago: "" }];
  const data = { details: { new: { facts: [["Date", "2026-10-21"]] } } };
  assert.deepEqual(recentCards(cards, data, OVERVIEW_DAYS, today).map((c) => c.id), ["new", "edge", "month"]);
});
