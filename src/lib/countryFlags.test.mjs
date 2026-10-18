import assert from "node:assert/strict";
import { normCountryKey, renderFlagContent, countryFlagDisc } from "./countryFlags.js";
import { createPartners } from "./partners.js";

// Test 1: Country normalisation
assert.equal(normCountryKey("USA"), "usa");
assert.equal(normCountryKey("United States"), "usa");
assert.equal(normCountryKey("U.S."), "usa");
assert.equal(normCountryKey("UK"), "uk");
assert.equal(normCountryKey("United Kingdom"), "uk");
assert.equal(normCountryKey("Israel"), "israel");
assert.equal(normCountryKey("India"), "india");
assert.equal(normCountryKey("South Africa"), "south_africa");
assert.equal(normCountryKey("France"), "france");
assert.equal(normCountryKey("Germany"), "germany");
assert.equal(normCountryKey("Unknown"), "unknown");
assert.equal(normCountryKey(""), "unknown");
assert.equal(normCountryKey(null), "unknown");

// Test 2: Flag disc SVG structure
const discSvg = countryFlagDisc("Israel", 100, 150, 28, "#7fa8c9", 'filter="url(#pgxGlow)"', "clip_test_1");
assert.ok(discSvg.includes('<defs><clipPath id="clip_test_1"><circle cx="100" cy="150" r="28" />'), "has clipPath in defs");
assert.ok(discSvg.includes('<g class="pg-flag" clip-path="url(#clip_test_1)">'), "has clipped flag group");
assert.ok(discSvg.includes('class="halo"'), "has halo ring");
assert.ok(discSvg.includes('class="net-circle"'), "has outer net-circle ring");
assert.ok(discSvg.includes('filter="url(#pgxGlow)"'), "passes extra attributes like filter");

// Test 3: Flag vector generation across countries
const sampleCountries = [
  "India", "Israel", "USA", "United Kingdom", "France", "Germany",
  "South Africa", "Sweden", "Norway", "Denmark", "Japan", "South Korea",
  "Australia", "Brazil", "Canada", "Netherlands", "Poland", "Ukraine",
  "Russia", "Spain", "Turkey", "UAE", "Switzerland", "Unknown"
];
sampleCountries.forEach((c) => {
  const content = renderFlagContent(normCountryKey(c), 100, 100, 28);
  assert.ok(content.length > 20, `Flag content for ${c} should be non-empty`);
});

// Test 4: Integration with partners.typeGraphSvg in region mode
const mockData = {
  competitors: {},
  KSSL_PARTNERS: [
    { id: "p1", label: "AM General", country: "USA" },
    { id: "p2", label: "Paramount Group", country: "South Africa" },
    { id: "p3", label: "Rafael Advanced Defense Systems", country: "Israel" },
  ],
  REL_LABEL: {},
  FIELDSYN: {},
  COMPSYN: {},
  TRACEIDS: {},
  sourceRegistry: {},
};
const partners = createPartners(mockData);
const ksslCo = {
  id: "KSSL",
  name: "KSSL",
  dir: "client",
  partners: mockData.KSSL_PARTNERS,
};
const svg = partners.typeGraphSvg(ksslCo, { stage: "spread", mode: "region" });
assert.ok(svg.includes('class="pg-flag"'), "Region graph includes flag groups");
assert.ok(svg.includes('clipPath id="pgx-flag-'), "Region graph defines clip paths for flags");
assert.ok(svg.includes("Israel"), "Region graph includes Israel");
assert.ok(svg.includes("USA"), "Region graph includes USA");
assert.ok(svg.includes("South Africa"), "Region graph includes South Africa");

console.log("countryFlags: all assertions passed");
