/* Stored text enters the app as text: tag-shaped input from a portal title or headline is dropped before any
 * render site injects it as HTML.   node --test test_no_markup.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { noMarkup, wireDataset } from "../../src/lib/dataset.js";

test("tags are dropped, comparisons and plain text survive", () => {
  assert.equal(noMarkup('Drone tender <img src=x onerror="alert(1)">x'), "Drone tender x");
  assert.equal(noMarkup("Mortar <script>alert(1)</script>bid"), "Mortar alert(1)bid");
  assert.equal(noMarkup("unclosed <svg onload=alert(1)"), "unclosed ");
  assert.equal(noMarkup("range < 40 km and 3<5"), "range < 40 km and 3<5");
  assert.equal(noMarkup("Bharat Forge & Elbit"), "Bharat Forge & Elbit");
});

test("wireDataset strips markup from served strings", () => {
  const d = wireDataset({ competitiveCards: [{ id: "a", title: "<img src=x onerror=alert(1)>Hostile title", dir: "watch" }] });
  assert.ok(!/<img|onerror/.test(JSON.stringify(d.competitiveCards)));
});
