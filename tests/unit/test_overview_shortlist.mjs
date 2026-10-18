/* The overview shows every stored card in the stored sequence: no shortlist, no demotion (ruling R5).
 *
 * The browser used to keep only the cards it judged critical (severity and impact grades, a hand-typed
 * client footprint, demonym tables) and fold the rest into rival news. Those grades are not in the
 * database, so the cut is gone, and with it shortlist.js and footprint.js. Nothing is dropped.
 *
 *     node tests/unit/test_overview_shortlist.mjs
 */
import { existsSync, readFileSync } from "node:fs";
import { wireDataset } from "../../src/lib/dataset.js";
import { buildFeed } from "../../src/lib/overview.js";

let fail = 0;
const ck = (name, ok, d) => {
  console.log(`  ${name.padEnd(70)} ${ok ? "PASS" : "FAIL"}${d !== undefined && !ok ? "  " + JSON.stringify(d) : ""}`);
  if (!ok) fail++;
};

ck("shortlist.js is gone", !existsSync(new URL("../../src/lib/shortlist.js", import.meta.url)));
ck("footprint.js is gone", !existsSync(new URL("../../src/lib/footprint.js", import.meta.url)));

const fx = JSON.parse(readFileSync(new URL("../../fixtures/kssl_dataset.json", import.meta.url)));
const wired = wireDataset(JSON.parse(JSON.stringify(fx)));
const cfg = wired.overviewConfig;

ck("no shortlist object is built", wired.overviewShortlist === undefined && !("shortlist" in cfg.competitive) && !("shortlist" in cfg.technology) && !("shortlist" in cfg.market));

const storedIds = fx.competitiveCards.filter((c) => c.dir !== "fav").map((c) => c.id);
ck("the competitive overview lists every stored card (the favourable ones are filtered by direction only), in stored order",
   JSON.stringify(cfg.competitive.cards.map((c) => c.id)) === JSON.stringify(storedIds), cfg.competitive.cards.map((c) => c.id));

ck("a card is never moved into a rival's news feed",
   Object.keys(fx.competitorNews).every((k) => (wired.competitorNews[k] || []).length === fx.competitorNews[k].length));

const feed = buildFeed(cfg.competitive, "priority", wired);
ck("the feed holds all of the overview cards", feed.total === storedIds.length && feed.groups.flatMap((g) => g.cards).length === storedIds.length, feed.total);

const src = ["dataset.js", "overview.js"].map((f) => readFileSync(new URL("../../src/lib/" + f, import.meta.url), "utf8")).join("\n");
ck("no import of the shortlist or footprint modules", !/shortlist\.js|footprint\.js/.test(src));

if (fail) { console.log(`\n${fail} failure(s)`); process.exit(1); }
console.log("\nok - the overview is the stored cards in the stored sequence");
