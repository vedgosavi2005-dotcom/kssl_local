/* Overlap with the client is a stored judgement of a company's presence in a country
 * (competitive_geo_company_presence.overlap_status + matched_ranges); the browser reads it,
 * and keeps no product bands, keyword classifier or counter-product rules.
 *
 *     node test_geo_overlap.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { wireDataset } from "./src/lib/dataset.js";
import { createGeo } from "./src/lib/geo.js";
import { setClient } from "./src/lib/client.js";

const fx = JSON.parse(readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url)));
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
assert.match(geo.geoOwnPanel("Poland"), /Matched ranges/);
assert.match(geo.geoOvBadge(poland[0]), /geo-ovb spec/);

// no band engine is left
for (const gone of ["koelCounter", "geoCatsOf", "geoKvaSpan", "geoBandsOf", "geoBandShort", "geoBandLabel", "geoOffer", "geoProductListHtml", "geoProductCompare", "geoSpanText"])
  assert.equal(gone in geo, false, `${gone} must be gone`);
const src = readFileSync(new URL("./src/lib/geo.js", import.meta.url), "utf8");
assert.ok(!/CAT_META|counterRules|kva|genset|BAND|GEO_NOTGEN/i.test(src));

console.log("ok - geo overlap is the stored overlap_status and matched_ranges");
