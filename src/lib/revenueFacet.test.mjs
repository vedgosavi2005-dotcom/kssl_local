import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import { revenueTierOf, revenueOptions } from "./revenueFacet.js";
import * as facet from "./revenueFacet.js";

const d = JSON.parse(fs.readFileSync(new URL("../../fixtures/kssl_dataset.json", import.meta.url), "utf8"));

test("the tier is the stored word, nothing is derived from a revenue figure", () => {
  assert.equal(revenueTierOf({ revenue_filter: "USD 1-5 bn" }), "USD 1-5 bn");
  assert.equal(revenueTierOf({ sales: [{ value: "FY2025 sales USD 67.6 billion" }] }), null);
  assert.equal(revenueTierOf({}), null);
  assert.equal(revenueTierOf(null), null);
});

test("the currency and tier tables are gone", () => {
  const src = fs.readFileSync(new URL("./revenueFacet.js", import.meta.url), "utf8");
  assert.ok(!("revenueCrore" in facet) && !("REVENUE_LABEL" in facet));
  assert.ok(!/CRORE_PER_BN|REVENUE_LABEL|const CUR\b|crore/i.test(src));
});

test("the options are the tiers the fixture's competitors carry, labelled as stored", () => {
  const rows = Object.values(d.competitors).map((c) => ({ revenueTier: revenueTierOf(c) }));
  const opts = revenueOptions(rows);
  const stored = new Set(Object.values(d.competitors).map((c) => c.revenue_filter).filter(Boolean));
  assert.deepEqual(new Set(opts.map((o) => o.v)), stored);
  opts.forEach((o) => assert.equal(o.l, o.v));
  assert.equal(revenueOptions([{ revenueTier: null }, {}]).length, 0);
});
