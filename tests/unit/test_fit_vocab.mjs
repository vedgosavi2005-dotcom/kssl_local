/* The fit words are the stored ones (strong / partial / weak), compared as served.
 * A "weak" tender is not a fit, and the stored word is what prints.
 *
 *     node --test test_fit_vocab.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { fitOf } from "../../src/lib/tenderIntel.js";
import { segments } from "../../src/lib/marketOutlook.js";

const today = new Date("2026-09-29T00:00:00Z");
const t = (o) => ({ status: "open", cat: "Ammunition", country: "Poland", ...o });
const data = {
  tenders: [
    t({ title: "strong one", clientFit: "strong" }),
    t({ title: "partial one", clientFit: "partial" }),
    t({ title: "weak one", clientFit: "weak" }),
  ],
  awards: [],
  marketCards: [],
};

test("the stored fit word is returned as served, no translation", () => {
  for (const w of ["strong", "partial", "weak"]) assert.equal(fitOf({ clientFit: w }), w);
  assert.equal(fitOf({ clientFit: "poor" }), "poor");
});

test("a weak tender does not count as an open tender that fits", () => {
  const s = segments(data, data.tenders, today, []);
  assert.equal(s.find((r) => r.segment === "Ammunition").open, 2);
});
