/* The Technology overview is KNOWLEDGE, not a threat board.
 *
 *     node tests/unit/test_tech_tiles.mjs
 *
 * Competitive owns the threat comparison; anything that directly impacts KSSL is a
 * competitive threat there. So the Technology pillar drops the gap/watch framing and
 * reads as two knowledge streams: COMPETITOR ADVANCEMENTS (a tech move by a tracked
 * competitor -- card.competitor is set) and ADOPTABLE ADVANCES (defence-tech from anyone
 * else KSSL could learn from or adopt). What this pins:
 *
 *   1. the classifier is grounded on card.competitor (no name-matching);
 *   2. technologyAttention tags each card rival/adopt, neutralises dir to 'watch'
 *      (knowledge, so no red gap band), caps a head, and represents BOTH streams;
 *   3. the wired config carries NO gap/watch/edge label, and metricsFor(technology)
 *      counts its tiles from the tags;
 *   4. d.techCards -- the full lane behind global search -- is left whole.
 */
import { wireDataset } from "../../src/lib/dataset.js";
import { metricsFor, technologyAttention, isRivalCard, TECH_ATTENTION_HEAD } from "../../src/lib/overview.js";

let bad = 0;
const fail = (m) => { bad++; console.log("  FAIL " + m); };
const tags = (c) => String(c.tags || "").split(/\s+/);

const card = (id, over) => ({
  id, dir: "watch", title: `tech ${id}`, lens: "Technology", company: "Someone",
  ago: "1 Jan 2026", sec: [{ lens: "EVIDENCE" }], ...over,
});
const rival = (id, over) => card(id, { competitor: "BAE Systems", ...over });
const adopt = (id, over) => card(id, { competitor: "", ...over });

const baseRaw = (techCards) => ({
  overviewConfig: { competitive: {}, market: {}, technology: { cnt: "tech", metrics: [] } },
  techCats: [], techAreaMeta: {}, innovations: { artillery: [{ id: 1 }, { id: 2 }], ammunition: [{ id: 3 }] }, matchups: {}, details: {}, competitorNews: {},
  patents: {}, competitors: {}, tenders: [], marketCards: [], competitiveCards: [],
  techCards,
});

/* ---- 1: classification is grounded on card.competitor -------------------------------- */
if (isRivalCard(rival("r")) !== true) fail("a card with a competitor set must classify as rival");
if (isRivalCard(adopt("a")) !== false) fail("a card with no competitor must classify as adoptable");

/* ---- 2: technologyAttention tags, neutralises dir, represents both streams ------------ */
{
  const lane = [];
  for (let i = 0; i < 40; i++) lane.push(rival(`r${i}`, { ago: `${(i % 28) + 1} Jan 2026` }));
  for (let i = 0; i < 40; i++) lane.push(adopt(`a${i}`, { ago: `${(i % 28) + 1} Feb 2026` }));
  const shown = technologyAttention(lane, isRivalCard);
  if (shown.length !== TECH_ATTENTION_HEAD) fail(`shortlist should cap at ${TECH_ATTENTION_HEAD}, got ${shown.length}`);
  if (shown.some((c) => c.dir !== "watch")) fail("every knowledge card is neutralised to dir=watch (no gap/red band)");
  if (!shown.some((c) => tags(c).includes("rival"))) fail("no competitor advancement in the shortlist");
  if (!shown.some((c) => tags(c).includes("adopt"))) fail("no adoptable advance in the shortlist");
  if (shown.some((c) => tags(c).includes("rival") && tags(c).includes("adopt"))) fail("a card is tagged both rival and adopt");
}

/* ---- 3 + 4: wired config, tiles from tags, no gap/watch words, full lane kept --------- */
{
  const lane = [];
  for (let i = 0; i < 30; i++) lane.push(rival(`r${i}`, { ago: `${(i % 28) + 1} Jan 2026` }));
  for (let i = 0; i < 20; i++) lane.push(adopt(`a${i}`, { ago: `${(i % 28) + 1} Feb 2026` }));
  const d = wireDataset(baseRaw(lane));
  const cfg = d.overviewConfig.technology;
  if (d.techCards.length !== 50) fail(`d.techCards (full lane) must stay whole (50), got ${d.techCards.length}`);
  if (cfg.cards.length !== TECH_ATTENTION_HEAD) fail(`overview capped at ${TECH_ATTENTION_HEAD}, got ${cfg.cards.length}`);

  // only the visible LABELS -- not the CSS colour tokens (var(--watch) is a hue, not a word)
  const labels = [
    ...Object.values(cfg.dirWord || {}),
    ...(cfg.filters || []).map((f) => f.l),
    ...(cfg.metrics || []).map((m) => m.l),
  ].join(" | ");
  if (/\bGap\b|\bWatch\b|Capability threat/i.test(labels)) fail(`a gap/watch label survives in the tech config: ${labels}`);

  const m = metricsFor(cfg, "technology", d);
  // tiles are found by KEY; three tiles draw, the rest of the five slots are empty
  const v = (k) => (m.find((x) => x.key === k) || {}).v;
  if (m.filter((x) => !x.blank).length !== 3) fail("the strip draws the three bound tiles");
  const rivalN = cfg.cards.filter((c) => tags(c).includes("rival")).length;
  const adoptN = cfg.cards.filter((c) => tags(c).includes("adopt")).length;
  if (v("competitor_advances") !== String(rivalN)) fail(`Competitor advances reads ${v("competitor_advances")}, tags hold ${rivalN}`);
  if (v("adoptable") !== String(adoptN)) fail(`Adoptable advances reads ${v("adoptable")}, tags hold ${adoptN}`);
  // Domains tracked counts the domains that hold innovations (artillery and ammunition here)
  if (v("domains_tracked") !== "2") fail(`Domains tracked reads ${v("domains_tracked")}, 2 domains hold innovations`);
  // the tile words are the front end's own
  if (m.filter((x) => !x.blank).map((x) => x.l).join("|") !== "Competitor advances|Adoptable advances|Domains tracked") fail("the tile words are the front-end words");
  if (cfg.title !== "Technology Knowledge") fail(`the lane heading is ${cfg.title}`);
}

if (bad) { console.log(`test_tech_tiles: ${bad} failure(s)`); process.exit(1); }
console.log("test_tech_tiles: ok -- technology is knowledge: rival/adopt streams, no gap/watch, tiles match the tags");
