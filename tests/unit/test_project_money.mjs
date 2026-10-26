/* Project spec money in plain form (owner 2026-10-25): rupees in crore with separators plus a rough dollar figure from the
   STORED rate; dollar values as "US$70 bn"; other values untouched.   node --test tests/unit/test_project_money.mjs */
import test from "node:test";
import assert from "node:assert/strict";
import { specValue, specLabel, usdRough, projectValue } from "../../src/lib/projects.js";

const fx = { USD: 86 };   // rupees per dollar

test("an INR crore value reads as rupees in crore with a rough dollar figure", () => {
  assert.equal(specValue("Programme outlay approved by Cabinet Committee on Security", "19000 crore INR", fx), "₹19,000 crore (~US$2.2 bn)");
  assert.equal(specValue("Contract value", "7628.70 INR crore", fx), "₹7,628.7 crore (~US$890 m)");
  assert.equal(specValue("Contract value", "nearly 5000 crore INR", fx), "nearly ₹5,000 crore (~US$580 m)");
  assert.equal(specValue("Contract value", "2960 crore (approximately) INR", fx), "approximately ₹2,960 crore (~US$340 m)");
  assert.equal(specValue("Cost per gun", "nearly 14 crore each INR", fx), "nearly ₹14 crore each (~US$1.6 m)");
});

test("the crore unit may sit in the label; lakh and million convert too", () => {
  assert.equal(specValue("Contract value (crore)", "33.69 INR", fx), "₹33.69 crore (~US$3.9 m)");
  assert.equal(specValue("Order", "12 lakh INR", fx), "₹12 lakh (~US$14,000)");
  assert.equal(specValue("Estimated tender value", "50 million INR", fx), "₹5 crore (~US$580,000)");
});

test("no stored rate: rupees only, nothing converted at a guessed rate", () => {
  assert.equal(specValue("Contract value", "1543 crore INR", {}), "₹1,543 crore");
  assert.equal(specValue("Contract value", "1543 crore INR", null), "₹1,543 crore");
});

test("dollar values read as US$ bn / m with their stated digits", () => {
  assert.equal(specValue("Combined contract value", "about 70 billion USD", fx), "about US$70 bn");
  assert.equal(specValue("Value", "253 USD million", fx), "US$253 m");
  assert.equal(specValue("Value", "$500m USD", fx), "US$500 m");
  assert.equal(specValue("Value", "7 billion USD (at least)", fx), "at least US$7 bn");
});

test("anything else is left as stored (a doubled unit word printed once)", () => {
  assert.equal(specValue("Total carbines", "4.25 lakh carbines", fx), "4.25 lakh carbines");
  assert.equal(specValue("Value", "approximately $750 million (€650 million) USD", fx), "approximately $750 million (€650 million) USD");
  assert.equal(specValue("Value", "182 million EUR", fx), "182 million EUR");
  assert.equal(specValue("Delivery period", "seven years years", fx), "seven years");
  assert.equal(specValue("Anything", "", fx), "");
});

test("long labels shorten by a fixed rule; a unit in brackets goes", () => {
  assert.equal(specLabel("Programme outlay approved by Cabinet Committee on Security"), "Approved budget");
  assert.equal(specLabel("Contract value (crore)"), "Contract value");
  assert.equal(specLabel("Contract value (crore, including GST)"), "Contract value (including GST)");
  assert.equal(specLabel("Contract value (Korea Times)"), "Contract value (Korea Times)");
});

test("usdRough keeps two significant figures", () => {
  assert.equal(usdRough(2.004e9), "2.0 bn");
  assert.equal(usdRough(3.56e6), "3.6 m");
  assert.equal(usdRough(527000), "530,000");
});

test("the headline value is the deal's own value, never a part of it", () => {
  const p = { specs: [{ k: "Cost per gun", v: "14 crore INR" }, { k: "Programme outlay approved by Cabinet Committee on Security", v: "19000 crore INR" }] };
  assert.equal(projectValue(p, fx), "₹19,000 crore (~US$2.2 bn)");
  assert.equal(projectValue({ specs: [{ k: "Phase 2 contract value", v: "30 million USD" }] }, fx), "");
});
