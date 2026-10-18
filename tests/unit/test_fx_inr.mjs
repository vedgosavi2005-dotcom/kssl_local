/* Market amounts in rupees from STORED rates only (fxRates <- serving.fx_rate).   node --test test_fx_inr.mjs */
import test from "node:test";
import assert from "node:assert/strict";
import { setFxRates, formatTotals, amountText } from "../../src/lib/tenderValue.js";
import { tenderCardCells } from "../../src/lib/tenderRow.js";

test("with stored rates every currency becomes one rupee total", () => {
  setFxRates({ EUR: 100, UAH: 2 });
  assert.equal(formatTotals([{ currency: "EUR", amount: 1e6, n: 1 }, { currency: "UAH", amount: 1e8, n: 1 }]), "₹ 30 Cr");
  assert.equal(amountText(5e6, "EUR"), "₹ 50 Cr");
});

test("a currency with no stored rate keeps its own code: nothing converted at a guessed rate", () => {
  setFxRates({ EUR: 100 });
  assert.equal(formatTotals([{ currency: "XYZ", amount: 2e6, n: 1 }]), "XYZ 2 m");
  assert.equal(amountText(0, "EUR"), null);
});

test("the tender card's Value cell shows rupees when an amount is stored", () => {
  setFxRates({ CZK: 4 });
  const cells = tenderCardCells({ title: "t", valueAmount: 25e6, valueCurrency: "CZK", value: "CZK 25,000,000" });
  const v = cells.find((p) => p.key === "value");
  assert.equal(v.text, "₹ 10 Cr");
});
