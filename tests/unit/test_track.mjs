/* The usage log's pure helpers: the route it records and the label it gives an element.
 *     node --test tests/unit/test_track.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { routeOf, labelOf, selOf } from "../../src/lib/track.js";
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

test("selOf: ancestor-to-element, up to 3 levels, an id ends the walk, the page itself is 'doc'", () => {
  const node = (tag, cls, id, parent) => ({ tagName: tag.toUpperCase(), id: id || "", classList: cls ? [cls] : [], parentElement: parent || null });
  const body = node("body");
  const main = node("main", null, "app", body);
  const ul = node("ul", "pat-list", null, node("div", "cp-body", null, main));
  assert.equal(selOf(node("li", "pat-li", null, ul)), "div.cp-body ul.pat-list li.pat-li");
  assert.equal(selOf(node("span", null, null, main)), "main#app span");
  assert.equal(selOf(body), "doc");
  assert.equal(selOf(null), "doc");
});
