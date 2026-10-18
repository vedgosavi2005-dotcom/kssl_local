/* Signal cards are sequenced by ONE comparator, everywhere: direction, then date (newest first),
 * then the stored sequence number. No severity, no impact, no shortlist (ruling R5).
 *
 *     node tests/unit/test_card_order.mjs
 *
 * A severity grade is a judgement and the database holds none for these cards, so the browser
 * neither derives one nor orders by one. A card that happens to carry a severity field is
 * ordered exactly as a card without one.
 */
import { buildFeed, compareCards } from "../../src/lib/overview.js";
import * as OV from "../../src/lib/overview.js";
import { buildProfile } from "../../src/lib/profile.js";

let bad = 0;
const fail = (m) => { bad++; console.log("  FAIL " + m); };
const ids = (list) => list.map((c) => c.id).join(",");

const card = (id, over = {}) => ({ id, dir: "threat", company: "Rheinmetall", ...over });
const data = { details: {} };

/* ---- 1. date leads within a direction, the stored sequence breaks a same-date tie ---- */
const cards = [
  card("old", { ago: "1 Aug 2026", seq: 1 }),
  card("new-b", { ago: "5 Sep 2026", seq: 3 }),
  card("new-a", { ago: "5 Sep 2026", seq: 2 }),
  card("mid", { ago: "4 Sep 2026", seq: 4 }),
];
const cfg = { cards, groups: [{ n: 99, h: "All", s: "" }] };
const feed = buildFeed(cfg, "priority", data).groups.flatMap((g) => g.cards);
const want = "new-a,new-b,mid,old";
if (ids(feed) !== want) fail(`priority order\n    got  ${ids(feed)}\n    want ${want}`);
if (feed.length !== cards.length) fail("no card may be dropped by the ordering");

/* ---- 2. severity fields are not read: a graded card is not placed by its grade ---- */
const graded = [
  card("low-new", { severity: "low", severityRank: 2, ago: "5 Sep 2026", seq: 2 }),
  card("high-old", { severity: "high", severityRank: 0, ago: "1 Aug 2026", seq: 1 }),
  card("none-newest", { severity: null, severityRank: 3, ago: "6 Sep 2026", seq: 3 }),
].sort(compareCards(data));
if (ids(graded) !== "none-newest,low-new,high-old") fail(`severity must not order cards, got ${ids(graded)}`);
for (const gone of ["severityRankOf", "SEVERITY_UNASSESSED_RANK", "SEVERITY_UNASSESSED_LABEL"])
  if (gone in OV) fail(`${gone} must not be exported`);

/* ---- 3. direction still leads ---- */
const mixed = [
  card("watch-new", { dir: "watch", ago: "6 Sep 2026", seq: 1 }),
  card("threat-old", { ago: "1 Aug 2026", seq: 2 }),
].sort(compareCards(data));
if (mixed[0].id !== "threat-old") fail("a threat still outranks a watch");

/* ---- 4. an undated card sorts last of its band, and says so ---- */
const undated = [
  card("no-date", { ago: "", seq: 1 }),
  card("dated", { ago: "1 Jan 2020", seq: 2 }),
].sort(compareCards(data));
if (undated[0].id !== "dated") fail("a card with no date must sort below a dated one, not as though it were today");
if (OV.NO_DATE_LABEL !== "date not known") fail("the undated card needs a word for it");

/* ---- 5. a card with no stored sequence keeps its place (stable), after sequenced ones ---- */
const noSeq = [card("x", { ago: "1 Sep 2026" }), card("y", { ago: "1 Sep 2026", seq: 1 }), card("z", { ago: "1 Sep 2026" })]
  .sort(compareCards(data));
if (ids(noSeq) !== "y,x,z") fail(`unsequenced cards follow sequenced ones in stored order, got ${ids(noSeq)}`);

/* ---- 6. EVERYWHERE: the profile list uses the same comparator ---- */
const dataset = {
  details: {},
  competitors: { rheinmetall: { name: "Rheinmetall", products: [], partners: [] } },
  competitiveCards: cards,
  marketCards: [],
  techCards: [],
  matchups: {},
  innovations: {},
  geoPresence: [],
  companySources: {},
};
const profile = buildProfile(dataset, "rheinmetall");
if (ids(profile.cards) !== want) fail(`the profile card list must use the same order as the feed\n    got  ${ids(profile.cards)}\n    want ${want}`);

/* ---- 7. the other sequence modes end in the same comparator ---- */
const sameDay = [card("sd-2", { ago: "5 Sep 2026", seq: 2 }), card("sd-1", { ago: "5 Sep 2026", seq: 1 })];
const rec = buildFeed({ cards: sameDay, groups: [{ n: 99, h: "All", s: "" }] }, "recency", data).groups.flatMap((g) => g.cards);
if (rec[0].id !== "sd-1") fail("the stored sequence must still break a tie inside 'most recent'");

if (bad) {
  console.log(`\n${bad} failure(s)`);
  process.exit(1);
}
console.log("ok - one comparator: direction, date, stored sequence; severity is not read");
