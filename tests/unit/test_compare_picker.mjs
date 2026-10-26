// Compare any two: company -> related company -> product -> rival of the same type only
import assert from "node:assert/strict";
import { catalogue, companiesFacing, productsFacingCompany, rivalsOf } from "../../src/lib/compareProducts.js";

const P = (id, name, vs, extra = {}) => ({ id, name, displayName: name, vs, category: "Aircraft", sheet: { key: [{ l: "Range", v: ["1 km", "2 km"] }] }, ...extra });
const comps = {
  lm: { name: "Lockheed Martin", products: [P(1, "F-35A", "fighter"), P(2, "C-130J", "transport"), P(3, "X-62A", "fighter", { kind: "test_asset" }), P(4, "F-35", "fighter", { umbrella: true })] },
  bo: { name: "Boeing", products: [P(5, "F-15EX", "fighter"), P(6, "Painting", "mro", { kind: "service" })] },
  ab: { name: "Airbus", products: [P(7, "A400M", "transport")] },
  tk: { name: "Tank Co", products: [P(8, "Tank", "mbt"), P(9, "No type", null)] },
  k:  { name: "KSSL full", products: [P(10, "Gun", "mbt")] },
};
const items = catalogue(comps, "k", "KSSL");
assert.deepEqual(items.map((p) => p.name).sort(), ["A400M", "C-130J", "F-15EX", "F-35A", "Gun", "Tank"]);   // no test asset, family, service, untyped
assert.equal(items.find((p) => p.name === "F-35A").specs.Range.v, "1 km; 2 km");
assert.equal(items.find((p) => p.name === "Gun").maker, "KSSL");
assert.deepEqual(companiesFacing(items), ["Airbus", "Boeing", "KSSL", "Lockheed Martin", "Tank Co"]);
assert.deepEqual(companiesFacing(items, "Lockheed Martin"), ["Airbus", "Boeing"]);          // Tank Co makes nothing LM makes
assert.deepEqual(productsFacingCompany(items, "Lockheed Martin", "Boeing").map((p) => p.name), ["F-35A"]);   // C-130J has no Boeing answer
const f35 = items.find((p) => p.name === "F-35A");
assert.deepEqual(rivalsOf(items, f35, "Boeing").map((p) => p.name), ["F-15EX"]);
assert.deepEqual(rivalsOf(items, f35, "Airbus"), []);
assert.deepEqual(rivalsOf(items, undefined, "Boeing"), []);
console.log("compare picker ok");
