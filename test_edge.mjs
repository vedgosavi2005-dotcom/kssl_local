/* The edge index is a stored score; the browser keeps only the generic dead-band comparison
 * over the stored spec rows (lib/edge.js, ruling R6).
 *
 *     node test_edge.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as E from "./src/lib/edge.js";
import { wireDataset } from "./src/lib/dataset.js";

const S = (l, cn, kn, hi) => ({ l, cn, kn, hi });

// the score is the stored one, not computed
assert.equal(E.computeSpecEdge({ edge: 38, specs: [S("a", 10, 10, true)] }).edge, 38);
assert.equal(E.computeSpecEdge({ edge: 0, specs: [] }).edge, 0);
assert.equal(E.computeSpecEdge({ specs: [S("a", 10, 20, true)] }).edge, null, "no stored score -> null, never a computed stand-in");
assert.equal(E.computeSpecEdge({ edge: null, specs: [S("a", 10, 20, true)] }).edge, null);

// direction: client larger on a higher-is-better row is an advantage; the same on lower-is-better is not
const up = E.computeSpecEdge({ edge: 50, specs: [S("Range", 40, 48, true)] }).dims[0];
assert.ok(up.a > 0);
const down = E.computeSpecEdge({ edge: 50, specs: [S("Weight", 30, 36, false)] }).dims[0];
assert.ok(down.a < 0);
// symmetry
assert.equal(E.computeSpecEdge({ specs: [S("x", 40, 48, true)] }).dims[0].a, -E.computeSpecEdge({ specs: [S("x", 48, 40, true)] }).dims[0].a);
// dead-band: a gap below 3% is level
assert.equal(E.computeSpecEdge({ edge: 50, specs: [S("x", 100, 102, true)] }).dims[0].a, 0);
assert.equal(E.computeSpecEdge({ edge: 50, specs: [S("x", 100, 102, true)] }).decided, 0);
// the cap clamps `a` but `raw` keeps the true gap
const big = E.computeSpecEdge({ specs: [S("x", 10, 90, true)] }).dims[0];
assert.equal(big.a, E.EDGE_CAP);
assert.ok(big.raw > E.EDGE_CAP);
// a row with no direction or a missing side is not compared
assert.equal(E.computeSpecEdge({ specs: [S("x", 10, 20, null), S("y", null, 5, true), S("z", 5, null, true)] }).n, 0);
// no label is special: a row named like a pairing axis or a plausibility-limited row is compared like any other
assert.equal(E.computeSpecEdge({ specs: [S("Calibre", 155, 105, true), S("Crew", 45, 5, false)] }).n, 2);
// related specs are not merged
assert.equal(E.computeSpecEdge({ specs: [S("Fuel use", 100, 80, false), S("Fuel use at half load", 60, 40, false)] }).n, 2);

// the words
assert.equal(E.edgeVerdict(null, "Acme").cls, "parity");
assert.equal(E.edgeVerdict(60, "Acme").word, "ACME AHEAD");
assert.equal(E.edgeVerdict(50, "Acme").word, "NEAR PARITY");
assert.equal(E.edgeVerdict(30, "Acme").word, "ACME BEHIND");

// basis lists the fields that lead, only when there is a stored score
assert.equal(E.edgeBasis(E.computeSpecEdge({ specs: [S("Range", 40, 48, true)] })), "");
assert.match(E.edgeBasis(E.computeSpecEdge({ edge: 70, specs: [S("Range", 40, 48, true)] })), /Range/);

// on the fixture the loader leaves the stored score and the stored comparable counts alone
const fx = JSON.parse(readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url)));
const wired = wireDataset(JSON.parse(JSON.stringify(fx)));
for (const [id, m] of Object.entries(fx.matchups)) {
  assert.equal(wired.matchups[id].edge, m.edge, `${id}: edge is the stored score`);
  assert.equal(wired.matchups[id].specDims, m.specDims);
  assert.equal(wired.matchups[id].specDecided, m.specDecided);
}

// no assumption about one product family is left in the module
const src = readFileSync(new URL("./src/lib/edge.js", import.meta.url), "utf8");
assert.ok(!/EDGE_AXIS|EDGE_GROUPS|EDGE_RANGE|EDGE_DEADBAND_BY|perKva|classAxis|Calibre|MTOW|kva|fuel/i.test(src));
assert.equal("edgeSelfCheck" in E, false);

console.log("ok - edge is the stored score; only the dead-band comparison is computed");
