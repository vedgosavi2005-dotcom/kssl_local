/* Tender judgements are stored fields (lib/tenderIntel.js), and the Top opportunity tables print the STORED rank rows
 * (data.topOpportunities: market_top_opportunity_tender / _project / market_next_move) in their stored order, with their
 * stored text. Nothing is ranked or derived in the browser.
 *
 *     node tests/unit/test_tender_intel.mjs
 */
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "esbuild";
import * as TI from "../../src/lib/tenderIntel.js";
import { wireTendersWithRealDays } from "../../src/lib/tenderCalc.js";

const { fitOf } = TI;

// a tender with no fit field -> null; a stored fit is returned as it is
assert.equal(fitOf({ title: "x" }), null);
assert.equal(fitOf({ clientFit: "" }), null);
assert.equal(fitOf({ clientFit: "strong" }), "strong");
assert.equal(fitOf({ fit: "weak" }), "weak");

// the browser ranking is gone: no shortlist, ordering, revenue or rival builder
for (const gone of ["topTenders", "topProjects", "nextMoves", "fitRank", "revenueText", "revenueOf", "modelOf", "rivalOf",
  "ASSUME", "tenderIntel", "winWeighted", "cockpit"])
  assert.equal(gone in TI, false, `${gone} must not be exported`);

const fx = JSON.parse(readFileSync(new URL("../../fixtures/kssl_dataset.json", import.meta.url)));
const TO = fx.topOpportunities;
assert.ok(TO.topTenders.length && TO.projectsBeforeTender.length && TO.nextMoves.length, "the fixture stores all three tables");

/* ---- the rendered tables (server-side render, state stubbed) ---- */
const here = fileURLToPath(new URL(".", import.meta.url));
const tmp = mkdtempSync(join(tmpdir(), "kssl-cockpit-"));
const stubs = {
  DataProvider: `export function useData() { return globalThis.__KSSL_TEST__; }`,
  AppState: `export function useAppState() { return { jumpTo() {} }; }`,
};
async function bundle(name, review) {
  const out = join(tmp, name);
  await build({
    stdin: {
      contents: `import React from "react";
      import { renderToStaticMarkup } from "react-dom/server";
      import TenderCockpit from "../../src/components/tenderCockpit/TenderCockpit.jsx";
      import { ReviewProvider } from "../../src/components/review/Review.jsx";
      import { setClient } from "../../src/lib/client.js";
      export function render(data) {
        globalThis.__KSSL_TEST__ = { data }; setClient(data.client);
        return renderToStaticMarkup(React.createElement(ReviewProvider, { initial: {} }, React.createElement(TenderCockpit, {})));
      }`,
      resolveDir: here, loader: "jsx",
    },
    bundle: true, platform: "node", format: "esm", jsx: "automatic", outfile: out, logLevel: "silent", loader: { ".css": "empty" },
    define: { "import.meta.env.VITE_REVIEW": review ? '"1"' : "undefined" },
    banner: { js: 'import { createRequire as __cr } from "node:module"; const require = __cr(import.meta.url);' },
    plugins: [{
      name: "stub-state",
      setup(b) {
        b.onResolve({ filter: /state\/(DataProvider|AppState)$/ }, (a) => ({ path: a.path.replace(/.*\//, ""), namespace: "stub" }));
        b.onLoad({ filter: /.*/, namespace: "stub" }, (a) => ({ contents: stubs[a.path], loader: "js" }));
      },
    }],
  });
  return (await import(pathToFileURL(out).href)).render;
}
const render = await bundle("cockpit.mjs", false);
const renderReview = await bundle("cockpit-review.mjs", true);
rmSync(tmp, { recursive: true, force: true });
const text = (h) => h.replace(/<[^>]+>/g, "|").replace(/\|+/g, "|");
const base = { client: { short: "Aurora" }, tenders: wireTendersWithRealDays(fx.tenders), projects: fx.projects };

// the fixture: the three stored tables, in stored order, with the stored text and the client's name in the headings
const html = render({ ...base, topOpportunities: TO });
const flat = text(html);
assert.match(html, /Top tenders/);
assert.match(html, /Projects to win before they tender/);
assert.match(html, /Next moves/);
assert.match(html, /Aurora<!-- --> fit|Aurora fit/);
assert.match(html, /Rival to beat/);
const at = (s) => { const i = flat.indexOf(s); assert.ok(i >= 0, `"${s}" is printed`); return i; };
const tPos = TO.topTenders.map((r) => at(r.title));
assert.deepEqual([...tPos].sort((a, b) => a - b), tPos, "top tenders print in the stored rank order");
for (const r of TO.topTenders) for (const k of ["decides", "ksslModel", "rivalToBeat", "revenue"]) if (r[k]) at(r[k]);
for (const r of TO.projectsBeforeTender) for (const k of ["title", "stage", "revenue"]) if (r[k]) at(r[k]);
const mPos = TO.nextMoves.map((m) => at(m.action));
assert.deepEqual([...mPos].sort((a, b) => a - b), mPos, "next moves print in the stored order");
for (const m of TO.nextMoves) if (m.due) at(m.due);

// the review copy: every row carries its Review controls, keyed on the stored row's own _src
{
  const rv = renderReview({ ...base, topOpportunities: TO });
  const nRows = (rv.match(/class="ti-row-link"/g) || []).length;
  const nBars = (rv.match(/class="rv-bar"/g) || []).length;
  assert.equal(nRows, TO.topTenders.length + TO.projectsBeforeTender.length + TO.nextMoves.length);
  assert.equal(nBars, nRows, `${nBars} Review bars for ${nRows} rows`);
  assert.ok(!/rv-bar/.test(html), "the live build renders no Review controls");
}

// nothing stored -> three honest empty states, even when tenders carry a stored fit: no row is derived
const none = render({ ...base, tenders: wireTendersWithRealDays([{ id: "x", title: "Tx", clientFit: "strong", status: "open", closingDate: "2027-01-01" }]), topOpportunities: undefined });
assert.match(none, /No top tender is on record yet\./);
assert.match(none, /No project to win before it tenders is on record yet\./);
assert.match(none, /No next move is on record yet\./);
assert.ok(!/<tbody>/.test(none) && !/Tx/.test(none), "no row is derived from the tenders");

// an empty stored cell is a dash
const dash = render({ ...base, topOpportunities: { topTenders: [{ id: "1", rank: 1, title: "Only title" }], projectsBeforeTender: [], nextMoves: [] } });
assert.match(text(dash), /\|1\|Only title\|\|?—\|—\|—\|—\|—\|/);

console.log("ok - the cockpit prints the stored Top opportunity rows in stored order; nothing is ranked or derived");
