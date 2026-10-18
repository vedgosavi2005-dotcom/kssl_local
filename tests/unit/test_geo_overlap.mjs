/* Overlap with the client is a stored judgement of a company's presence in a country
 * (competitive_geo_company_presence.overlap_status + matched_ranges); the browser reads it,
 * and keeps no product bands, keyword classifier or counter-product rules.
 *
 *     node tests/unit/test_geo_overlap.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { wireDataset } from "../../src/lib/dataset.js";
import { createGeo } from "../../src/lib/geo.js";
import { setClient } from "../../src/lib/client.js";

const fx = JSON.parse(readFileSync(new URL("../../fixtures/kssl_dataset.json", import.meta.url)));
const d = wireDataset(JSON.parse(JSON.stringify(fx)));
setClient(d.client);
const geo = createGeo(d);

assert.equal(geo.clientFootprintKnown, true);

// every stored presence row with a confirmed or category word is an overlap, and no other row is
let confirmed = 0, category = 0;
for (const p of fx.geoPresence) {
  const c = fx.geoComps.find((x) => x.id === p.cid);
  const ov = geo.geoOverlap(p.cid, p.country);
  if (c.isBf) { assert.equal(ov, null, "the client cannot overlap itself"); continue; }
  if (p.overlap === "confirmed" || p.overlap === "category") {
    assert.ok(ov, `${p.comp} in ${p.country}: stored ${p.overlap}`);
    assert.equal(ov.status, p.overlap);
    assert.equal(ov.tier, p.overlap === "confirmed" ? "spec" : "cat");
    assert.deepEqual(ov.ranges, p.ranges ? p.ranges.split(",").map((x) => x.trim()) : []);
    p.overlap === "confirmed" ? confirmed++ : category++;
  } else {
    assert.equal(ov, null, `${p.comp} in ${p.country}: stored ${p.overlap} is no overlap`);
  }
}
assert.ok(confirmed > 0 && category > 0);

// a country lists the rivals whose stored word is an overlap, nothing computed from text
const poland = geo.geoRivalsIn("Poland");
assert.deepEqual(poland.map((o) => o.comp.id).sort(),
  fx.geoPresence.filter((p) => p.country === "Poland" && p.overlap === "confirmed" && p.cid !== d.client.id).map((p) => p.cid).sort());

// the dropdown dot agrees with the stored overlaps; the self-check passes on the fixture
assert.deepEqual(geo.selfCheck(), []);
const rival = fx.geoComps.find((c) => !c.isBf && fx.geoPresence.some((p) => p.cid === c.id && p.overlap === "confirmed"));
assert.equal(geo.geoPickOverlap(rival, null).cls, "ovl");

// the panel and badges are built from the stored words
const own = geo.geoOwnPanel("Poland");
assert.match(own, /Overlapping categories/);
assert.match(own, /Datasheet outcome/);
assert.match(geo.geoOvBadge(poland[0]), /geo-ovb spec/);

// no band engine is left
for (const gone of ["koelCounter", "geoCatsOf", "geoKvaSpan", "geoBandsOf", "geoBandShort", "geoBandLabel", "geoOffer", "geoSpanText"])
  assert.equal(gone in geo, false, `${gone} must be gone`);
const src = readFileSync(new URL("../../src/lib/geo.js", import.meta.url), "utf8");
assert.ok(!/CAT_META|counterRules|kva|genset|BAND|GEO_NOTGEN/i.test(src));

// the rival's products carry their STORED comparison: the counterpart is the stored matchup on that product, the
// verdict is the stored decision_level, and the comparison prints the stored spec rows; nothing is paired here
{
  const x = Object.values(fx.matchups).find((m) => m.compProductId && m.edge != null);
  const list = geo.geoProductListHtml(x.compId, null);
  assert.match(list, /Products .* sells/);
  assert.ok(list.includes(`data-cmp-prod="${x.compProductId}"`), "the matched product is listed");
  assert.ok(list.includes(x.bf.replace(/&/g, "&amp;")), "its stored counterpart is named");
  const want = ({ 1: "Competitor’s product is better", 2: "Level: neither leads", 3: "has the superior product" })[x.decision];
  assert.ok(list.includes(want), `the stored decision level ${x.decision} reads "${want}"`);
  const cmp = geo.geoProductCompare(x.compId, x.compProductId);
  assert.ok(cmp && cmp.title.includes(x.bf));
  for (const sp of x.specs.slice(0, 3)) assert.ok(cmp.html.includes(String(sp.l).replace(/&/g, "&amp;")), `spec row ${sp.l} is printed`);
  assert.equal(geo.geoProductListHtml(fx.client.id, null), "", "the client has no counterpart list of its own");
  assert.equal(geo.geoProductCompare(x.compId, "no-such-product"), null);
}

console.log("ok - geo overlap is the stored overlap_status and matched_ranges; product counterparts are the stored matchups");
