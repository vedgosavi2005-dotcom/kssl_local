import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import { hasAmount, valueTotals, formatTotals } from "./tenderValue.js";

const d = JSON.parse(fs.readFileSync(new URL("../../fixtures/kssl_dataset.json", import.meta.url), "utf8"));

test("totals are per stored currency, never converted", () => {
  const t = valueTotals(d.tenders);
  assert.ok(t.length >= 2, "the fixture states more than one currency");
  d.tenders.filter(hasAmount).forEach((x) => assert.ok(t.some((e) => e.currency === x.valueCurrency)));
  const usd = d.tenders.filter((x) => x.valueCurrency === "USD").reduce((n, x) => n + x.valueAmount, 0);
  assert.equal(t.find((e) => e.currency === "USD").amount, usd);
  assert.match(formatTotals(t), /EUR .* · USD /);
});

test("no amount means a dash, not zero; text alone is not an amount", () => {
  assert.equal(formatTotals(valueTotals([])), "—");
  assert.equal(hasAmount({ value: "USD 5 million" }), false);
  assert.equal(hasAmount({ valueAmount: 5, valueCurrency: "" }), false);
});

test("no exchange rate lives in code", () => {
  for (const f of ["tenderValue.js", "gapModel.js", "marketOverview.js", "overview.js"]) {
    const src = fs.readFileSync(new URL(`./${f}`, import.meta.url), "utf8");
    assert.ok(!/CR_PER_MILLION|parseCr|CRORE_PER_BN/.test(src), f);
  }
});

test("awards: one total per stored currency, a missing value is not summed, nothing reads value_usd", async () => {
  const { winners } = await import("./marketOutlook.js");
  const { AWARD_FIELDS } = await import("./tenderValue.js");
  const t = valueTotals(d.awards, AWARD_FIELDS);
  assert.deepEqual(t.map((e) => e.currency), ["EUR", "INR", "USD"]);
  assert.equal(t.find((e) => e.currency === "EUR").amount, 410000000 + 18500000);
  assert.equal(t.reduce((n, e) => n + e.n, 0), d.awards.filter((a) => a.value && a.currency).length);
  const w = winners(d);
  assert.equal(w.priced, d.awards.filter((a) => a.winner && a.value && a.currency).length);
  assert.deepEqual(w.totals, valueTotals(d.awards.filter((a) => a.winner), AWARD_FIELDS));
  w.rows.forEach((r) => assert.ok(Array.isArray(r.totals) && !("usd" in r) && !("share" in r)));
  assert.ok(!/value_usd/.test(fs.readFileSync(new URL("./marketOutlook.js", import.meta.url), "utf8")));
});
