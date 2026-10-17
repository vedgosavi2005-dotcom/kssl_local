/* The Market overview's metric strip must be counted from the wired data, and every
 * tile that reads as a door must open the rows it counts.
 *
 *     node test_market_tiles.mjs
 *
 * FOUND 2026-09-05 (interaction sweep, live dataset): the strip read
 * "Open opportunities 7 · Already concluded 15 · Markets tracked 14 · All signals 6"
 * above a feed of 323 signals promoted from 89 open tenders. Those are the numbers
 * baked into the served config for the Sep-2 sample. metricsFor computes the real
 * ones -- but wireDataset stamps `sec: t.cat` (a STRING) on every promoted tender
 * card, every other card carries `sec` as an array of lens sections, the lens loop
 * called .forEach on the string, threw, and the catch left the baked values on
 * screen. A number on the dashboard the data did not hold -- the exact thing the
 * strip exists to prevent -- and invisible on the sample dump, where the baked
 * values happened to be right.
 *
 * The doors were wrong independently: "Open opportunities" (act fav) opened
 * fav+watch = every demand card plus the unpriced tenders, "Already concluded" (act
 * deadline) opened everything, "Markets tracked" (act all) reset a filter that was
 * already clear. What this pins:
 *
 *   1. a promoted tender card's `sec` is an array, like every other card's;
 *   2. metricsFor(market) counts All signals / Open opportunities / Already concluded /
 *      Markets tracked from the wired data, never from the served `v`;
 *   3. a non-array `sec` on any card cannot take the whole strip down;
 *   4. the "Open opportunities" tile's door (act "open") selects exactly the promoted
 *      open tenders, and the two tiles that have no feed behind them carry acts
 *      Layout routes to the Market Report rather than a feed predicate.
 */
import assert from "node:assert/strict";
import { wireDataset } from "./src/lib/dataset.js";
import { metricsFor, tilePredicate } from "./src/lib/overview.js";

let bad = 0;
const fail = (m) => { bad++; console.log("  FAIL " + m); };

const tender = (id, over) => ({
  id, title: `tender ${id}`, issuer: "Some Ministry", country: "India",
  cat: "Artillery", value: null, qty: null, deadline: "22 Jun 2027",
  status: "open", url: `https://example.test/${id}`, srcs: [], req: [], matches: [],
  ...over,
});

const raw = {
  overviewConfig: {
    competitive: {}, technology: {},
    market: {
      cnt: "6 demand signals · sorted by urgency",
      /* the baked sample numbers -- none of them true for this fixture */
      metrics: [
        { l: "Live bid value", v: "73,895", act: "atstake" },
        { l: "Open opportunities", v: "7", act: "fav" },
        { l: "Already concluded", v: "15", act: "deadline" },
        { l: "Markets tracked", v: "14", act: "all" },
        { l: "All signals", v: "6", act: "all" },
      ],
    },
  },
  techCats: [], innovations: {}, matchups: {}, details: {}, competitorNews: {},
  patents: {}, competitors: {},
  marketCards: [
    { id: "d1", kind: "opportunity", title: "Kyiv faces sustained attacks", lens: "Market", sec: [{ lens: "Market" }] },
    { id: "d2", kind: "opportunity", title: "Japan MoD allocates funds", lens: "Market", sec: [] },
  ],
  tenders: [
    tender("t-open-1"),
    tender("t-open-2", { country: "France" }),
    tender("t-open-val", { value: "USD 145 million", valueAmount: 145000000, valueCurrency: "USD", country: "Egypt" }),
    tender("t-awarded", { status: "awarded" }),
    tender("t-closed", { status: "open", deadline: "Closed 01 Jan 2020" }),
  ],
};

const d = wireDataset(raw);
const cfg = d.overviewConfig.market;
const promoted = cfg.cards.filter((c) => c.id.startsWith("tender-"));
if (promoted.length !== 3) fail(`expected 3 promoted open tenders, got ${promoted.length}`);

// 1. shape
promoted.forEach((c) => {
  if (!Array.isArray(c.sec)) fail(`promoted card ${c.id} carries sec as ${typeof c.sec}, not an array`);
});

// 2. counted, not baked -- and over the SHOWN shortlist (marketAttention), so the tiles
//    agree with the visible list. The 3 open tenders here are far-future and ungraded,
//    so marketAttention falls back to the soonest head and shows all 3.
const m = metricsFor(cfg, "market", d);
// a tile is found by its KEY (the column it came from), never by its label text
const KEY = { "Latest tenders": "latest_tenders", "Strong fits": "strong_fits", "Tender value": "tender_value", "Perceived opportunities": "perceived_opportunities" };
const tile = (l) => m.find((x) => x.key === KEY[l]) || {};
const v = (l) => tile(l).v;
const act = (l) => tile(l).act;
if (m.length !== 5 || m.filter((x) => x.blank).length !== 1) fail(`the strip is four stored tiles and one empty slot, got ${m.length} tiles`);
// the tile words are the front end's own (chrome.js), the same with or without any ui table in the dataset
if (JSON.stringify(m.filter((x) => !x.blank).map((x) => x.l)) !== JSON.stringify(["Latest tenders", "Strong fits", "Tender value", "Perceived opportunities"]))
  fail("the four tile labels are the front-end words");
if (JSON.stringify((cfg.filters || []).map((f) => f.l)) !== JSON.stringify(["All", "Latest Tenders", "Perceived Opportunities"])) fail("the pills are the front-end words");
if (v("Latest tenders") !== "3") fail(`Latest tenders reads ${v("Latest tenders")}, 3 are on the shortlist`);
if (v("Strong fits") !== "—") fail(`Strong fits reads ${v("Strong fits")}, no tender is graded so it must read "—"`);
// the tile shows the stored amount in its own currency; nothing is converted
if (v("Tender value") !== "USD 145 m") fail(`Tender value reads ${v("Tender value")}, one shown tender states USD 145 million`);
// the two demand cards (no KSSL taxonomy served in this fixture, so the lane is kept) are
// the Perceived Opportunities stream on the same feed
if (v("Perceived opportunities") !== "2") fail(`Perceived opportunities reads ${v("Perceived opportunities")}, expected the 2 watch cards`);

// 3. a hostile shape on one card degrades that card, not the strip
const hostile = { ...cfg, cards: cfg.cards.concat([{ id: "x", kind: "opportunity", sec: "Artillery" }]) };
const m2 = metricsFor(hostile, "market", d);
if ((m2.find((x) => x.key === "latest_tenders") || {}).v !== "3")
  fail("a string `sec` on one card still takes the whole strip back to the baked values");

// 4. doors -- each tile filters the feed to the rows it counts
if (act("Latest tenders") !== "open") fail(`Latest tenders tile act is ${act("Latest tenders")}, expected "open"`);
if (act("Strong fits") !== "fit") fail(`Strong fits tile act is ${act("Strong fits")}, expected "fit"`);
if (act("Tender value") !== "valued") fail(`Tender value tile act is ${act("Tender value")}, expected "valued"`);
if (act("Perceived opportunities") !== "opps") fail(`Perceived opportunities tile act is ${act("Perceived opportunities")}, expected "opps"`);
const opened = cfg.cards.filter(tilePredicate("open"));
const openedIds = opened.map((c) => c.id).sort().join(",");
const promotedIds = promoted.map((c) => c.id).sort().join(",");
if (openedIds !== promotedIds) fail(`the Latest tenders door opens [${openedIds}], the tile counts [${promotedIds}]`);
if (opened.length !== Number(v("Latest tenders"))) fail(`door opens ${opened.length}, tile says ${v("Latest tenders")}`);
// the Perceived opportunities door opens exactly the watch stream
const oppsOpened = cfg.cards.filter(tilePredicate("opps"));
if (oppsOpened.length !== Number(v("Perceived opportunities"))) fail(`opps door opens ${oppsOpened.length}, tile says ${v("Perceived opportunities")}`);
// the "valued" door opens exactly the one priced tender
const valued = cfg.cards.filter(tilePredicate("valued"));
if (valued.length !== 1 || !valued[0].id.includes("t-open-val"))
  fail(`the Live bid value door opens ${valued.map((c) => c.id).join(",")}, expected the one priced tender`);

if (bad) { console.log(`test_market_tiles: ${bad} failure(s)`); process.exit(1); }
console.log("test_market_tiles: ok -- market tiles are counted from the wired data and their doors open what they count");
