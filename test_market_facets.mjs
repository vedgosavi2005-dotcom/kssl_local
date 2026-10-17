/* The Market pills must have members, and must count what the tiles count.
 *
 *     node test_market_facets.mjs
 *
 * REPORTED: "filter of market tab opportunity is 0 and live bid also 0".
 *
 * They filtered the 231 demand-signal cards, every one of which carries dir='watch' --
 * the promoter never assigns another value on this lane. The bid state they wanted
 * exists, but on the TENDERS, and not one demand card joins to a tender (measured: 0 of
 * 231 share a url). So the tiles counted tenders while the pills counted cards: two
 * populations under one heading, and the pills read 0 for months.
 *
 * wireDataset now promotes OPEN tenders into the feed. What this pins:
 *
 *   1. the facets are non-empty -- the actual complaint;
 *   2. the split is a PARTITION. Overview filters on `card.dir === f.f`, so a card sits
 *      in exactly one facet. The open tenders are the cards of `kind: "tender"`, no
 *      double counting, none missed; they carry NO `dir` (the data holds no stance for a tender);
 *   3. CONCLUDED tenders are not promoted. Awarded and closed have their own two views,
 *      and adding them here would inflate "Emerging Demand" with unbiddable contracts;
 *   4. every promoted card has a DETAIL. The drawer reads data.details[id]; a card
 *      without one opens an empty panel, which is how this would look "done" and not be;
 *   5. the demand cards are untouched -- still 'watch', still there.
 */
import { wireDataset } from "./src/lib/dataset.js";
import { marketSelfCheck } from "./src/lib/marketOverview.js";
import { filterMatch, tilePredicate, buildFeed } from "./src/lib/overview.js";

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
    market: { cnt: "6 demand signals · sorted by urgency" },
  },
  /* the pills and groups are database rows (lanes.js) */
  database: { ui: { filter_option: [
    { filter_group: "market-feed", option_code: "tenders", option_label: "Latest Tenders", badge_label: "TENDER", display_order: 1 },
    { filter_group: "market-feed", option_code: "opportunities", option_label: "Perceived Opportunities", badge_label: "OPPORTUNITY", display_order: 2 },
  ] } },
  techCats: [], innovations: {}, matchups: {}, details: {}, competitorNews: {},
  patents: {}, competitors: {},
  marketCards: [
    { id: "d1", kind: "opportunity", title: "Kyiv faces sustained attacks", lens: "Market" },
    { id: "d2", kind: "opportunity", title: "Japan MoD allocates funds", lens: "Market" },
  ],
  tenders: [
    tender("t-open-noval"),
    tender("t-open-noval2"),
    tender("t-open-val", { value: "₹1,200 cr" }),
    tender("t-awarded", { status: "awarded" }),
    tender("t-closed", { status: "open", deadline: "Closed 01 Jan 2020" }),
  ],
};

const d = wireDataset(raw);
const cards = d.marketCards || [];
const by = (dir) => cards.filter((c) => c.dir === dir);
const tenders = cards.filter((c) => c.kind === "tender");

// 1. the tender facet has members -- the complaint
if (tenders.length === 0) fail("the tender facet is empty");

// 2. exactly the open tenders, marked by KIND and by nothing else: whether a tender publishes a price is not a
//    stance, so no tender carries a dir (no fav, no threat, no watch)
if (tenders.length !== 3)
  fail(`the 3 open tenders should all be kind "tender", got ${tenders.length}`);
for (const c of tenders) if ("dir" in c && c.dir != null) fail(`${c.id} carries a stance (dir=${c.dir}) the data does not hold`);
if (by("fav").length + by("threat").length !== 0) fail("no card may be sorted into fav or threat on a tender's price");
const ids = cards.map((c) => c.id);
if (new Set(ids).size !== ids.length) fail("a tender was promoted twice");

// 3. concluded tenders are NOT promoted
for (const gone of ["tender-t-awarded", "tender-t-closed"]) {
  if (ids.includes(gone)) fail(`${gone} was promoted -- concluded tenders must not be`);
}

// 4. every promoted card has a detail, with the tender's real fields
for (const c of cards.filter((x) => x.id.startsWith("tender-"))) {
  const det = (d.details || {})[c.id];
  if (!det) { fail(`${c.id} has no detail -- its drawer would open empty`); continue; }
  if (det.dir != null) fail(`${c.id} detail carries a stance (dir=${det.dir})`);
  if (det.kind !== "tender") fail(`${c.id} detail is not marked kind "tender"`);
  if (!det.url) fail(`${c.id} detail has no source url`);
  if (!det.facts.some((f) => f[0] === "Issuer")) fail(`${c.id} detail lost its issuer`);
  // no fabricated value on a tender that publishes none
  const v = det.facts.find((f) => f[0] === "Value");
  if (!!v !== (c.id === "tender-t-open-val")) fail(`${c.id}: the Value fact must appear exactly when the tender publishes one`);
}

// 5. the demand cards survive in d.marketCards -- search, news and the top-bar count
//    still read them; only the OVERVIEW FEED is curated to tenders.
if (d.marketCards.filter((c) => c.kind === "opportunity").length !== 2) fail("the 2 demand cards should be intact");

// the OVERVIEW FEED serves TWO streams: the Latest Tenders shortlist (promoted tenders)
// and the curated Perceived Opportunities (the demand/geopolitical watch lane, no tender
// required). d.marketCards still carries the whole news lane for search.
const served = ((d.overviewConfig || {}).market || {}).cards || [];
const promotedCards = cards.filter((c) => c.id.startsWith("tender-"));
const mk = (d.overviewConfig || {}).market || {};
for (const f of mk.filters || []) if (f.dirs && f.dirs.some((x) => x === "fav" || x === "threat")) fail(`filter ${f.f} still selects tenders by a stance`);
for (const g of mk.groups || []) if (g.dirs && g.dirs.some((x) => x === "fav" || x === "threat")) fail(`group ${g.h} still selects tenders by a stance`);
if (!(mk.filters || []).some((f) => f.kinds && f.kinds.includes("tender"))) fail("the Latest Tenders filter must select kind tender");
const tenderServed = served.filter((c) => c.id.startsWith("tender-"));
if (tenderServed.length !== promotedCards.length)
  fail(`the Latest Tenders stream has ${tenderServed.length}, expected the ${promotedCards.length} promoted tenders`);
const oppServed = served.filter((c) => c.kind === "opportunity");
if (oppServed.length === 0)
  fail("the overview feed must carry the Perceived Opportunities stream (opportunity cards)");
if (served.length !== tenderServed.length + oppServed.length)
  fail("the feed is the two streams and nothing else -- tenders + opportunities");
if (/\bfit|act on|defence-tech|can adopt/.test(((d.overviewConfig || {}).market || {}).cnt || ""))
  fail("the subhead claims a fit or an action the data does not hold");
if (/demand signals/.test(((d.overviewConfig || {}).market || {}).cnt || ""))
  fail("the subhead still calls the feed 'demand signals'");

// the pills, the "Latest tenders" tile and the feed groups select tenders by kind
for (const c of tenders) {
  if (!filterMatch(c, "tenders", mk.filters)) fail(`${c.id} is missed by the Latest Tenders pill`);
  if (filterMatch(c, "opps", mk.filters)) fail(`${c.id} is wrongly in Perceived Opportunities`);
  if (!tilePredicate("open")(c)) fail(`${c.id} is missed by the Latest tenders tile`);
}
for (const c of oppServed) {
  if (filterMatch(c, "tenders", mk.filters) || tilePredicate("open")(c)) fail(`${c.id} (an opportunity) is counted as a tender`);
}
const feedGroups = buildFeed(mk, "priority", d).groups;
if (!feedGroups.length || feedGroups[0].cards.some((c) => c.kind !== "tender")) fail("the first feed group must hold only tenders");
// the technology count line names what is counted and claims nothing
if (/adopt|defence-tech/i.test(((d.overviewConfig || {}).technology || {}).cnt || "")) fail("the technology subhead still claims what can be adopted");

// and the invariant that keeps the pills and the tiles honest
try {
  marketSelfCheck(d.tenders, d.marketCards);
} catch (e) {
  fail("marketSelfCheck rejected a correct dataset: " + e.message);
}
// ...which must actually fire when they disagree
try {
  marketSelfCheck(d.tenders, cards.filter((c) => c.id !== "tender-t-open-val"));
  fail("marketSelfCheck passed when a tender card went missing");
} catch (e) { /* expected */ }

if (bad) { console.log(`\n${bad} failure(s)`); process.exit(1); }
console.log("ok - market facets: open tenders promoted as kind tender with no stance, "
  + "concluded excluded, every card has a detail");
