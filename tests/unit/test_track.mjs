/* The usage log's pure helpers: the route it records and the label it gives an element.
 *     node --test tests/unit/test_track.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { routeOf, labelOf } from "../../src/lib/track.js";
import { routeHash } from "../../src/lib/route.js";

test("routeOf reads the same hash routeHash writes", () => {
  assert.deepEqual(routeOf(routeHash("market", "tender")), { pillar: "market", view: "tender" });
  assert.deepEqual(routeOf(""), { pillar: null, view: null });
});

test("labelOf prefers data-track, then aria-label, title, text; trimmed to 160", () => {
  const el = (attrs, text) => ({ getAttribute: (k) => attrs[k] ?? null, innerText: text });
  assert.equal(labelOf(el({ "data-track": "Approve all" }, "x")), "Approve all");
  assert.equal(labelOf(el({ "aria-label": "Close" }, "✕")), "Close");
  assert.equal(labelOf(el({}, "  Rheinmetall \n 12 ")), "Rheinmetall 12");
  assert.equal(labelOf(el({}, "y".repeat(300))).length, 160);
  assert.equal(labelOf(null), null);
});
