import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import { createPartners, overlapDefs } from "./partners.js";
import { setClient, clientShort } from "./client.js";
import { buildCategories, verdictOf, impactText } from "./partnerCategories.js";
import * as pc from "./partnerCategories.js";
import { PARTNER_CATEGORIES, OVERLAP_KINDS } from "./chrome.js";

const d = JSON.parse(fs.readFileSync(new URL("../../fixtures/kssl_dataset.json", import.meta.url), "utf8"));
const rivals = Object.entries(d.competitors).filter(([, c]) => c.dir !== "client");

test("the category tables are gone from the code", () => {
  const cat = fs.readFileSync(new URL("./partnerCategories.js", import.meta.url), "utf8");
  const par = fs.readFileSync(new URL("./partners.js", import.meta.url), "utf8");
  assert.ok(!("PARTNER_CATEGORIES" in pc) && !("CATEGORY_GROUPS" in pc) && !("closenessOf" in pc));
  assert.ok(!/Exclusive distributor|Rental fleet|Packager|generator sets/i.test(cat));
  assert.ok(!/export const OV_KIND|export const OV_DEF|const REL_SHORT|const CONF_TAG|PG_REGION_ALIAS|DEFENSE_FIRM_COUNTRIES/.test(par));
  assert.ok(!/Brand choice moves to the counter|dealer quotes/i.test(par));
});

test("every relationship type in the dataset is a category of the front-end legend", () => {
  const cats = buildCategories(d);
  assert.deepEqual(cats.list.map((c) => c.label), PARTNER_CATEGORIES.map((c) => c.label));
  rivals.forEach(([, c]) =>
    (c.partners || []).forEach((p) => assert.ok(cats.categoryOf(p.rel).label, `${c.name}: ${p.label} -> ${p.rel}`)),
  );
  // an alias is the same category as its key
  assert.equal(cats.categoryOf("jv").key, "joint-venture");
  assert.equal(cats.categoryOf("distribution").key, "channel-partner");
  assert.ok(cats.groups.length > 1 && cats.groups.every((g) => g.label));
});

test("the legend renders with every ui table empty", () => {
  const empty = JSON.parse(JSON.stringify(d));
  for (const t of Object.keys(empty.database.ui)) empty.database.ui[t] = [];
  const cats = buildCategories(empty);
  assert.equal(cats.list.length, PARTNER_CATEGORIES.length);
  assert.ok(cats.list.every((c) => c.label && c.short && c.def));
  setClient(empty.client);
  const P = createPartners(empty);
  const [cid, c] = rivals.find(([, x]) => (x.partners || []).length > 1);
  const groups = P.pgTypeGroups({ ...c, id: cid });
  assert.ok(groups.length > 0 && groups.every((g) => g.label), "the graph groups carry the legend words");
});

test("a definition names the rival and the client from data; an unknown type has no invented text", () => {
  setClient(d.client);
  const cats = buildCategories(d);
  const k = cats.list.find((c) => /\{rival\}/.test(c.def) && /\{client\}/.test(c.def));
  const txt = cats.categoryDef(k.key, "Zed Co", clientShort());
  assert.ok(txt.includes("Zed Co") && txt.includes(clientShort()) && !/\{rival\}|\{client\}/.test(txt));
  const u = cats.categoryOf("no-such-type");
  assert.equal(u.label, "");
  assert.equal(u.def, "");
});

test("overlap headings and leads are front-end code; the effects are the ui.partner_overlap_effect rows", () => {
  const defs = overlapDefs(d);
  assert.deepEqual(Object.keys(defs).sort(), OVERLAP_KINDS.map((k) => k.kind).sort());
  assert.ok(Object.values(defs).every((x) => x.label && x.lead && /\{client\}/.test(x.label)));
  const n = Object.values(defs).reduce((a, x) => a + x.fx.length, 0);
  assert.equal(n, d.database.ui.partner_overlap_effect.length);
  // no effect rows: the headings stay, no effect prose is drawn
  const none = overlapDefs({});
  assert.deepEqual(Object.keys(none).sort(), OVERLAP_KINDS.map((k) => k.kind).sort());
  assert.ok(Object.values(none).every((x) => x.fx.length === 0));
  // an effect keyed by the alias of a kind lands under that kind
  const aliased = overlapDefs({ database: { ui: { partner_overlap_effect: [{ overlap_kind: "tech", display_order: 1, effect_title: "t", effect_text: "x" }] } } });
  assert.deepEqual(aliased.technology.fx, [["t", "x"]]);
});

test("one company is one node and the type groups follow the legend", () => {
  setClient(d.client);
  const P = createPartners(d);
  const [cid, c] = rivals.find(([, x]) => (x.partners || []).length > 1);
  const nodes = P.pgNodes({ ...c, id: cid });
  assert.ok(nodes.length >= 1 && nodes.length <= c.partners.length);
  const groups = P.pgTypeGroups({ ...c, id: cid }).map((g) => g.key);
  assert.ok(groups.every((g) => c.partners.some((p) => p.rel === g)));
});

test("the relationship brief names both parties and the client read; no raw tags", () => {
  setClient(d.client);
  const P = createPartners(d);
  const [cid, c] = rivals.find(([, x]) => (x.partners || []).some((p) => p.impact));
  const p = c.partners.find((x) => x.impact);
  const html = P.tieHtml({ ...c, id: cid }, cid, p.id);
  assert.ok(html.includes(p.label.split(" ")[0]));
  assert.ok(html.includes(`What it means for ${clientShort()}`));
  assert.ok(!/&lt;b&gt;|&lt;span/.test(html));
});

test("verdict and read parsing", () => {
  assert.equal(verdictOf({ verdict: "watch" }), "watch");
  assert.equal(verdictOf({ verdict: "Threat" }), "threat");
  assert.equal(impactText({ impact: "a  b <span style='o'>· <a href='u'>s</a></span>" }), "a b");
});

test("only threat and watch verdicts render: an 'opportunity' (or unset) verdict is no stance, no pill, no green", () => {
  setClient(d.client);
  const P = createPartners(d);
  const words = Object.fromEntries(d.database.ui.filter_option.filter((o) => o.filter_group === "stance").map((o) => [o.option_code, o.badge_label || o.option_label]));
  const all = rivals.flatMap(([cid, c]) => (c.partners || []).map((p) => ({ cid, c, p })));
  const by = (v) => all.filter(({ p }) => p.verdict === v);
  assert.ok(by("opportunity").length > 0 && by("threat").length > 0 && by("watch").length > 0, "the fixture holds all three stored verdicts");
  // a tie is opened by its partner's whole company key, so check the tie that carries only the verdict under test
  const html = ({ cid, c, p }) => P.tieHtml({ ...c, id: cid }, cid, p.id);
  for (const t of by("opportunity")) {
    const h = html(t);
    assert.ok(!/#e6f5ec|#1f7a46|#a9d9bc/.test(h), "no green verdict colour");
    const tied = (t.c.partners || []).filter((x) => x.label === t.p.label);
    if (tied.every((x) => x.verdict === "opportunity" || !x.verdict)) assert.ok(!/Read for/.test(h), "an opportunity-only tie has no 'Read for' verdict");
  }
  for (const t of by("threat")) {
    const h = html(t);
    assert.ok(h.includes(words.threat) && h.includes("#b5341f"), "a threat verdict draws the stored threat word in the threat colour");
  }
  for (const t of all.filter(({ p }) => !p.verdict)) {
    const tied = (t.c.partners || []).filter((x) => x.label === t.p.label);
    if (tied.every((x) => !x.verdict)) assert.ok(!/Read for/.test(html(t)), "no stored verdict, no verdict");
  }
  assert.equal(verdictOf({ verdict: "opportunity" }), null);
  assert.equal(verdictOf({ verdict: "fav" }), null);
  assert.equal(verdictOf({}), null);
  const src = ["partners.js", "partnerCategories.js"].map((f) => fs.readFileSync(new URL(`./${f}`, import.meta.url), "utf8")).join("\n");
  assert.ok(!/opportunity/i.test(src), "no 'opportunity' stance path in the partnership code");
  assert.ok(!/#1f7a46|#e6f5ec/.test(src), "no green verdict style in the partnership code");
});
