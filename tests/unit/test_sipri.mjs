/* SIPRI figures on the Company profile and the Geo country panel (src/lib/sipri.js).
 *
 *     node tests/unit/test_sipri.mjs
 *
 * Owner 2026-10-26: arms revenue / Top-100 rank / arms share per competitor, and a country's defence budget, each cited to
 * its SIPRI database. A parent group's figure must never read as the subsidiary's own. */
import test from "node:test";
import assert from "node:assert/strict";
import { fmtUsdM, fmtShare, trendChange, sparkBars, entityLabel, armsView, milexView, SIPRI_ARMS, SIPRI_MILEX } from "../../src/lib/sipri.js";

test("money and shares", () => {
  assert.equal(fmtUsdM(64650), "$64.7bn");
  assert.equal(fmtUsdM(954387), "$954bn");
  assert.equal(fmtUsdM(850.4), "$850m");
  assert.equal(fmtUsdM(null), null);
  assert.equal(fmtShare(0.9100506), "91%");
  assert.equal(fmtShare(0.022951, 1), "2.3%");
  assert.equal(fmtShare(undefined), null);
});

test("trend change uses the first and last points with a value", () => {
  const pts = [{ year: 2019, v: 100 }, { year: 2020, v: null }, { year: 2024, v: 121 }];
  assert.deepEqual(trendChange(pts, "v"), { pct: "+21%", from: 2019, to: 2024 });
  assert.equal(trendChange([{ year: 2024, v: 5 }], "v"), null);
  assert.deepEqual(trendChange([{ year: 2020, v: 200 }, { year: 2021, v: 150 }], "v"), { pct: "-25%", from: 2020, to: 2021 });
});

test("spark bars fit the box and the largest bar is full height", () => {
  const bars = sparkBars([{ year: 1, v: 50 }, { year: 2, v: 100 }], "v", 100, 20, 4);
  assert.equal(bars.length, 2);
  assert.equal(bars[1].h, 20);
  assert.equal(bars[0].h, 10);
  assert.equal(bars[1].x + bars[1].w, 100);
  assert.deepEqual(sparkBars([], "v"), []);
});

test("own figures: headline, rank, share, change and source", () => {
  const v = armsView({ entity: "Lockheed Martin Corp.", relation: "own", year: 2024, rank: 1, armsUsdM: 64650, share: 0.91,
    trend: [{ year: 2019, armsUsdM: 53230 }, { year: 2024, armsUsdM: 64650 }], source: { label: "SIPRI Arms Industry Database", url: SIPRI_ARMS.url } },
  "Lockheed Martin");
  assert.equal(v.headline, "Arms revenue 2024: $64.7bn");
  assert.equal(v.entity, "Lockheed Martin Corp.");
  assert.deepEqual(v.facts, [["Top-100 rank", "#1 (2024)"], ["Arms share of revenue", "91%"], ["Change 2019–2024", "+21%"]]);
  assert.equal(v.note, null);
  assert.equal(v.source.url, "https://www.sipri.org/databases/armsindustry");
});

test("a parent group is named as the parent, never as the company", () => {
  const a = { entity: "Hanwha Group", relation: "parent", year: 2024, rank: 21, armsUsdM: 7970, share: 0.12, trend: [] };
  const v = armsView(a, "Hanwha Aerospace");
  assert.equal(entityLabel(a), "Hanwha Group (parent)");
  assert.equal(v.entity, "Hanwha Group (parent)");
  assert.match(v.note, /parent group, not Hanwha Aerospace alone/);
  assert.equal(entityLabel({ entity: "Indian Ordnance Factories", relation: "predecessor" }), "Indian Ordnance Factories (predecessor)");
  assert.match(armsView({ ...a, entity: "Indian Ordnance Factories", relation: "predecessor", year: 2020 }, "AWEIL").note, /predecessor/);
});

test("nothing on record prints nothing", () => {
  assert.equal(armsView(null, "X"), null);
  assert.equal(armsView({ year: 2024, armsUsdM: null }, "X"), null);
  assert.equal(milexView(undefined), null);
  assert.equal(milexView({ year: 2025, currentUsdM: null, constantUsdM: null }), null);
});

test("defence spending: current US$ for the year, real change from constant US$, share of GDP", () => {
  const v = milexView({ year: 2025, currentUsdM: 92057, constantUsdM: 93254, shareGdp: 0.02295,
    trend: [{ year: 2020, constantUsdM: 80209 }, { year: 2025, constantUsdM: 93254 }] });
  assert.equal(v.headline, "Defence spending 2025: $92.1bn");
  assert.deepEqual(v.facts, [["Share of GDP", "2.3%"], ["Real change 2020–2025", "+16%"]]);
  assert.equal(v.source.label, SIPRI_MILEX.label);
  assert.equal(v.bars.length, 2);
});
