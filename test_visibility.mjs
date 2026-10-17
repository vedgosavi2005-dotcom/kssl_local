/* ui.section_visibility gates the 8 hideable sections; a missing key is hidden.
 *
 *     node --test test_visibility.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { setVisibility, isVisible, firstVisibleView, viewVisible, HIDEABLE } from "./src/lib/visibility.js";
import { parseRoute, railFor, RAIL } from "./src/lib/route.js";
import { navCounts, viewMetaFor } from "./src/lib/overview.js";
import { wireDataset } from "./src/lib/dataset.js";
import { setClient } from "./src/lib/client.js";
import { buildGapModel } from "./src/lib/gapModel.js";
import { searchDataset } from "./src/lib/search.js";

const fx = JSON.parse(readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url), "utf8"));

test("isVisible is true only for an explicit true", () => {
  for (const m of [{}, null, undefined, { stock: false }, { stock: "true" }, { stock: 1 }]) {
    setVisibility(m);
    assert.equal(isVisible("stock"), false, JSON.stringify(m));
  }
  setVisibility({ stock: true });
  assert.equal(isVisible("stock"), true);
  assert.equal(isVisible("swot"), false);
});

test("the 8 hideable keys are the contract", () => {
  assert.deepEqual([...HIDEABLE].sort(), ["chat", "finances", "gap-analysis", "parallax-read", "product-images", "stock", "strategic-positioning", "swot"]);
});

test("a hidden gap-analysis view routes to the first visible view of its pillar", () => {
  setVisibility({ "gap-analysis": false });
  for (const v of ["gap-analysis", "gap-competitive"]) {
    const r = parseRoute(`#p=competitive&v=${v}`);
    assert.equal(r.view, firstVisibleView("competitive"));
    assert.notEqual(r.view, "gap-analysis");
    assert.notEqual(r.view, "gap-competitive");
    assert.equal(r.repaired, true);
  }
  setVisibility(null);
  const f = parseRoute("#p=competitive&v=finances");
  assert.equal(f.view, firstVisibleView("competitive"));
  assert.equal(f.repaired, true);
});

test("a visible gap view still routes", () => {
  setVisibility({ "gap-analysis": true });
  assert.deepEqual(parseRoute("#p=competitive&v=gap-competitive"), { pillar: "competitive", view: "gap-competitive", repaired: false });
  setVisibility({ finances: true });
  assert.equal(parseRoute("#p=competitive&v=finances").repaired, false);
});

test("firstVisibleView skips a hidden rail item and the rail filters it", () => {
  setVisibility({});
  assert.equal(firstVisibleView("competitive"), RAIL.competitive[0].view);
  for (const p of Object.keys(RAIL)) {
    assert.ok(railFor(p).every((r) => viewVisible(r.view)));
    assert.equal(railFor(p).some((r) => r.view === "gap-competitive" || r.view === "finances"), false);
  }
});

test("navCounts carries no badge for a hidden view", () => {
  setVisibility({});
  setClient(fx.client);
  const d = wireDataset(JSON.parse(JSON.stringify(fx)));
  setClient(d.client);
  const counts = navCounts(d, buildGapModel(d));
  for (const k of ["gap-analysis", "gap-competitive", "finances"]) assert.equal(k in counts, false, k);
  setVisibility({ "gap-analysis": true, finances: true });
  const on = navCounts(d, buildGapModel(d));
  assert.equal("gap-competitive" in on, true);
  assert.equal("finances" in on, true);
});

test("viewMeta drops hidden views and search never indexes a hidden section", () => {
  setVisibility({});
  setClient(fx.client);
  const d = wireDataset(JSON.parse(JSON.stringify(fx)));
  const meta = viewMetaFor(d);
  assert.equal("gap-competitive" in meta, false);
  assert.equal("finances" in meta, false);
  const res = searchDataset(d, "SWOT");
  assert.equal(res.total, 0);
});

test("every hideable key has a host that reads it", async () => {
  const { readdirSync, statSync } = await import("node:fs");
  const files = [];
  const walk = (dir) => readdirSync(dir).forEach((f) => {
    const p = `${dir}/${f}`;
    statSync(p).isDirectory() ? walk(p) : /\.jsx?$/.test(f) && !p.endsWith("visibility.js") && files.push(p);
  });
  walk("./src");
  const text = files.map((f) => readFileSync(f, "utf8")).join("\n");
  for (const k of HIDEABLE) {
    // stock has no host: its Vite lanes and UI were removed in Task 10 (no data source); the key stays in the contract
    if (k === "stock") continue;
    // finances and gap-analysis also gate their rail views through VIEW_KEY
    assert.ok(text.includes(`isVisible("${k}")`) || text.includes(`viewVisible(`), `${k} is read nowhere`);
    if (!["finances"].includes(k)) assert.ok(text.includes(`isVisible("${k}")`), `${k} has no isVisible host`);
  }
});
