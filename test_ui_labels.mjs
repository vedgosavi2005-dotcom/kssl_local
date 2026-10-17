/* UI CHROME IS FRONT-END CODE; THE DATABASE HOLDS DATA ONLY.
 *
 *     node test_ui_labels.mjs
 *
 * Navigation, pillar names, headings, tabs, tile labels, time windows, filter controls and their option lists are
 * defined in the front end (src/lib/chrome.js, src/lib/route.js), exactly as the reference UI defines them. The
 * dataset's serving tables supply only data (facts, names, numbers, dates and judgements). What this pins, on
 * fixtures/kssl_dataset.json and on a copy of it with EVERY ui table emptied (the shape of the real database):
 *   - the pillar names, the rail items and their order, the headings and the three overview lanes (tiles, pills,
 *     groups, badge words) are the same with or without any ui row;
 *   - the only stances are threat and watch: a row stored with any other stance has no stance, no pill, no colour,
 *     is not counted, and is kept off the competitive overview;
 *   - a stance pill narrows the rows by the stance STORED on them (filtering compares option codes to row fields);
 *   - the word "favourable" is nowhere in src, and no source file reads a chrome ui table.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { wireDataset } from "./src/lib/dataset.js";
import { metricsFor, tilePredicate, filterMatch } from "./src/lib/overview.js";
import { STANCE_OPTIONS, stanceWords, stanceOf, momentStance } from "./src/lib/chrome.js";
import { railFor, navTitle, PILLAR_LABEL, PILLARS, RAIL } from "./src/lib/route.js";
import { setVisibility } from "./src/lib/visibility.js";
import { marketMetrics } from "./src/lib/marketOverview.js";
import { maturityWord, positionWord, maturityLabel } from "./src/lib/innovation.js";

const fx = JSON.parse(readFileSync("fixtures/kssl_dataset.json", "utf-8"));
const clone = () => JSON.parse(JSON.stringify(fx));
/* the real database: every ui table present but empty */
const noUi = () => {
  const r = clone();
  for (const t of Object.keys(r.database.ui)) r.database.ui[t] = [];
  return r;
};
const ok = (m) => console.log("  ok   " + m);

/* ---- the three overview lanes: same with the fixture's ui rows and with none ----------------------------- */
for (const [name, make] of [["fixture", clone], ["empty ui tables", noUi]]) {
  const d = wireDataset(make());

  const comp = d.overviewConfig.competitive;
  const m = metricsFor(comp, "competitive", d);
  const drawn = m.filter((x) => !x.blank);
  assert.deepEqual(drawn.map((x) => x.key), ["threats", "watch", "companies_tracked"]);
  assert.deepEqual(drawn.map((x) => x.l), ["Competitive threats", "Watch signals", "Companies tracked"]);
  assert.equal(m.length, 5, "five slots: the unused ones are empty cells");
  const n = (dir) => comp.cards.filter((c) => c.dir === dir).length;
  assert.equal(m.find((x) => x.key === "threats").v, String(n("threat")));
  assert.equal(m.find((x) => x.key === "watch").v, String(n("watch")));
  assert.deepEqual(comp.filters.map((f) => f.l), ["All", "Threat", "Watch"], "pills: the reset plus threat and watch");
  assert.deepEqual(comp.filters.map((f) => f.f), ["all", "threat", "watch"]);
  assert.deepEqual(comp.dirWord, { threat: "Threat", watch: "Watch" });
  assert.equal(comp.title, "Competitive Intelligence");

  const tech = d.overviewConfig.technology;
  const tm = metricsFor(tech, "technology", d).filter((x) => !x.blank);
  assert.deepEqual(tm.map((x) => x.key), ["competitor_advances", "adoptable", "domains_tracked"]);
  assert.deepEqual(tm.map((x) => x.l), ["Competitor advances", "Adoptable advances", "Domains tracked"]);
  assert.equal(tm[2].v, String(Object.values(d.innovations).filter((r) => r.length).length), "domains tracked counts the domains that hold innovations");
  assert.equal(tech.title, "Technology Knowledge");
  assert.deepEqual(tech.filters.map((f) => f.l), ["All", "Competitor Advancements", "Adoptable Advances"]);
  assert.deepEqual(tech.groups.map((g) => g.h), ["Competitor Advancements", "Adoptable Advances"]);
  assert.deepEqual(tech.tagWord, { rival: "", adopt: "Adoptable" });
  assert.equal(tech.hideFilterButtons, true);

  const mk = d.overviewConfig.market;
  assert.deepEqual(metricsFor(mk, "market", d).filter((x) => !x.blank).map((x) => x.l), ["Latest tenders", "Strong fits", "Tender value", "Perceived opportunities"]);
  assert.equal(mk.title, "Top opportunity");
  assert.deepEqual(mk.filters.map((f) => f.l), ["All", "Latest Tenders", "Perceived Opportunities"]);
  assert.deepEqual(mk.tagWord, { tender: "TENDER", opportunity: "OPPORTUNITY" });
  assert.deepEqual(mk.dirWord, {}, "no stance word on the market lane: the badge follows the card kind");
  assert.deepEqual(marketMetrics(d.tenders).map((x) => x.l), ["Active tenders", "Markets", "Source portals", "Value disclosed"]);
  ok(`${name}: competitive / technology / market lanes carry the front-end tiles, pills, groups and badge words`);
}

/* ---- the only stances are threat and watch -------------------------------------------------------- */
{
  const d = wireDataset(noUi());
  const legacy = fx.competitiveCards.filter((c) => c.dir && c.dir !== "threat" && c.dir !== "watch");
  assert.ok(legacy.length > 0, "the fixture holds a card stored with a third stance");
  const filters = d.overviewConfig.competitive.filters;
  for (const c of legacy) {
    const w = d.competitiveCards.find((x) => x.id === c.id);
    assert.equal(w.dir, "", "no stance, never relabelled");
    assert.equal(d.overviewConfig.competitive.cards.some((x) => x.id === c.id), false, "kept off the competitive overview");
    for (const f of filters) if (f.f !== "all") assert.equal(filterMatch(w, f.f, filters), false);
    for (const a of ["threat", "watch"]) assert.equal(tilePredicate(a)(w), false, `not counted in the ${a} tile`);
  }
  assert.deepEqual(stanceWords(), { threat: "Threat", watch: "Watch" });
  assert.deepEqual(STANCE_OPTIONS, [{ code: "threat", label: "Threat" }, { code: "watch", label: "Watch" }], "the stance filter offers threat and watch only");
  assert.equal(stanceOf("other"), "");
  assert.equal(stanceOf("fav"), "");
  assert.equal(momentStance("high"), "threat");
  assert.equal(momentStance("watch"), "watch");
  assert.equal(momentStance("opportunity"), "", "a third level draws no stance");
  assert.equal(momentStance(null), "");
  ok("a stored third stance has no pill, no colour, no count and no place on the competitive overview");
}

/* ---- filters compare option codes against the stance stored on the rows --------------------------------- */
{
  const d = wireDataset(noUi());
  const cfg = d.overviewConfig.competitive;
  const all = cfg.cards.length;
  const threat = cfg.cards.filter((c) => filterMatch(c, "threat", cfg.filters));
  const watch = cfg.cards.filter((c) => filterMatch(c, "watch", cfg.filters));
  assert.ok(threat.length > 0 && watch.length > 0, "the fixture holds both stances");
  assert.ok(threat.every((c) => c.dir === "threat") && watch.every((c) => c.dir === "watch"));
  assert.equal(threat.length + watch.length, all, "every shown row is one of the two");
  assert.equal(cfg.cards.filter((c) => filterMatch(c, "all", cfg.filters)).length, all);
  ok("the Threat / Watch pills narrow the overview by the stored stance of each row");
}

/* ---- rail, pillars and headings ---------------------------------------------------------------------------- */
{
  assert.deepEqual(PILLARS, ["competitive", "market", "technology"]);
  assert.deepEqual(PILLARS.map((p) => PILLAR_LABEL[p]), ["Competitive", "Market", "Technology"]);
  const all = (p) => RAIL[p].map((r) => r.label);
  assert.deepEqual(all("competitive"), ["Overview", "Competitor Profile", "Competitor Moment", "Products", "Product Evaluation", "Partnership", "Projects", "Geo Footprint", "Patent"]);
  assert.deepEqual(all("market"), ["Top opportunity", "Tenders", "Global Requirements", "Market Intelligence"]);
  assert.deepEqual(all("technology"), ["Overview", "Innovations"]);
  assert.equal(navTitle("technology", "innovation"), "Innovation Pipeline");
  assert.equal(navTitle("market", "tender"), "Tenders");
  assert.equal(navTitle("competitive", "partnerships"), "Partnership");
  assert.equal(navTitle("competitive", "nope"), "");
  // the rail a reader sees is the routes whose section the database has not switched off; none of these eight is
  // switchable, so with the real database's empty visibility map every item is listed, in order, with its word
  setVisibility({});
  for (const p of PILLARS) assert.deepEqual(railFor(p).map((r) => r.label), all(p), `${p}: the whole rail is listed`);
  setVisibility(null);
  ok("pillar names are Competitive / Market / Technology; the rail lists each pillar's items in order with the reference words");
}

/* ---- Innovation words: the stored word leads, the code's own word is the fallback ------------------------- */
{
  const ivs = Object.values(fx.innovations).flat();
  assert.ok(ivs.length > 0);
  for (const iv of ivs) {
    assert.equal(maturityWord(iv), iv.matLabel || "", "the maturity word is the stored maturity_label");
    assert.equal(positionWord(iv), iv.gapLabel || "", "the position word is the stored position_label");
  }
  assert.equal(maturityWord({ mat: "prod" }), "In production");
  assert.equal(maturityLabel({ mat: null }), "not stated");
  assert.equal(positionWord({ gap: null }), "");
  ok("Innovation maturity and position words");
}

/* ---- no chrome is read from a ui table, and no third stance is anywhere in src ------------------------------- */
{
  const walk = (dir, out = []) => {
    for (const e of readdirSync(dir)) {
      const p = join(dir, e);
      if (statSync(p).isDirectory()) walk(p, out);
      else if (/\.(jsx?|css)$/.test(p) && !/\.test\./.test(p)) out.push(p);
    }
    return out;
  };
  const files = walk("src");
  const strip = (f) => readFileSync(f, "utf-8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const hit = files.filter((f) => /favou?rable/i.test(readFileSync(f, "utf-8")));
  assert.deepEqual(hit, [], `the word favourable appears in ${hit.join(", ")}`);
  const fav = files.filter((f) => /["'`.-]fav\b|\bfav["':]/.test(readFileSync(f, "utf-8")));
  assert.deepEqual(fav, [], `a fav stance is referenced in ${fav.join(", ")}`);
  const CHROME_TABLE = /ui\.(competitive_navigation|competitive_metric|competitive_positioning_tab|competitive_competitor_moment_(level|time_window)|competitive_geo_filter|market_(view|pillar|metric|top_opportunity_view|tenders_view|intelligence_tab|global_requirement_view)|technology_(ui_view|pillar|innovation_view)|filter_option|ui_project_|partner_category|partner_overlap_kind)/;
  const reads = files.filter((f) => CHROME_TABLE.test(strip(f)));
  assert.deepEqual(reads, [], `chrome is read from a ui table in ${reads.join(", ")}`);
  assert.ok(!files.some((f) => /lib[\\/](uiText|lanes)\.js$/.test(f)), "uiText.js and lanes.js are gone");
  assert.ok(!files.some((f) => /from "[^"]*(uiText|lanes)(\.js)?"/.test(readFileSync(f, "utf-8"))), "nothing imports them");
  ok("no favourable stance anywhere in src; no chrome ui table is read by any source file");
}

/* ---- the Perceived opportunities tile counts the opportunity cards (kind), never a stance ------------------- */
{
  const d = wireDataset(noUi());
  const mk = d.overviewConfig.market;
  const opps = d.marketCards.filter((c) => c.kind === "opportunity");
  assert.ok(opps.length > 0, "the fixture carries pipeline opportunity cards");
  assert.ok(opps.every((c) => !c.dir), "market cards carry no stance, so the tile cannot depend on one");
  const tile = metricsFor(mk, "market", d).find((x) => x.key === "perceived_opportunities");
  assert.ok(tile, "the tile is drawn");
  const served = mk.cards.filter((c) => c.kind === "opportunity");
  assert.ok(served.length > 0, "the opportunity lane is not empty on the fixture");
  assert.equal(tile.v, String(served.length), "the tile counts the opportunity cards it names");
  assert.equal(mk.cards.filter(tilePredicate("opps")).length, served.length, "its door opens exactly those cards");
  assert.equal(mk.cards.filter((c) => filterMatch(c, "opps", mk.filters)).length, served.length, "and so does the pill");
  ok("Perceived opportunities tile counts the opportunity cards (" + served.length + " > 0 on the fixture)");
}

console.log("\nok - chrome is front-end code; the lanes, rail and stances hold with and without ui rows");
