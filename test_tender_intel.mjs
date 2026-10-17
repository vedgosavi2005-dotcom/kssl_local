/* Tender judgements are stored fields, never browser estimates (lib/tenderIntel.js), and the Top opportunity tables
 * are built in the browser from those stored fields by ordering alone.
 *
 *     node test_tender_intel.mjs
 */
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "esbuild";
import * as TI from "./src/lib/tenderIntel.js";
import { bucketTenders } from "./src/lib/overview.js";
import { wireTendersWithRealDays } from "./src/lib/tenderCalc.js";

const { fitOf, revenueOf, revenueText, modelOf, rivalOf, fitRank, topTenders, topProjects, nextMoves } = TI;

// a tender with no fit field -> null; a stored fit is returned as it is
assert.equal(fitOf({ title: "x" }), null);
assert.equal(fitOf({ clientFit: "" }), null);
assert.equal(fitOf({ clientFit: "good" }), "good");
assert.equal(fitOf({ clientFit: "strong" }), "strong");
assert.equal(fitOf({ fit: "weak" }), "weak");

// revenue estimate absent -> null, never a computed number (0 is not "absent")
assert.equal(revenueOf({ title: "x" }), null);
assert.equal(revenueOf({ revenueMid: null }), null);
assert.equal(revenueOf({ revenueMid: "" }), null);
assert.equal(revenueOf({ revenueMid: "n/a" }), null);
assert.equal(revenueOf({ revenueMid: 2e6 }), 2e6);
assert.equal(revenueOf({ revenueMid: 0 }), 0);
assert.equal(revenueOf({ value: "USD 1 million", valueAmount: 1e6, clientFit: "strong" }), null);

// the old browser engine is gone: no assumption table, no weighting, no tender-intel engine
for (const gone of ["ASSUME", "tenderIntel", "winWeighted", "decisionOf", "kindOf", "isTender", "isProject", "stageOf", "FIT_LABEL", "usdM", "cockpit"])
  assert.equal(gone in TI, false, `${gone} must not be exported`);

// revenue is printed as stored, or not at all: the estimate, then the stored value; never computed from other fields
assert.deepEqual(revenueText({}), { text: null, estimate: false });
assert.deepEqual(revenueText({ valueAmount: 5e6, clientFit: "strong" }), { text: null, estimate: false });
assert.deepEqual(revenueText({ revenueEstimate: "USD 60-95 M", value: "USD 185 million" }), { text: "USD 60-95 M", estimate: true });
assert.deepEqual(revenueText({ expectedRevenue: "EUR 3 M" }), { text: "EUR 3 M", estimate: true });
// the buyer's stored tender value is not the client's revenue: a tender with a value but no revenue estimate has none
assert.deepEqual(revenueText({ value: "USD 185 million", valueAmount: 185e6 }), { text: null, estimate: false });
assert.deepEqual(revenueText({ revenueMid: 77500000 }), { text: "77,500,000", estimate: true });

// fit words: only strong > partial > weak rank; any other word, or none, is not on the shortlist
assert.deepEqual(["strong", "partial", "weak", "poor", "", null, undefined].map(fitRank), [3, 2, 1, 0, 0, 0, 0]);
assert.equal(modelOf({ matches: [{ n: "Aurora APC", fit: "strong" }] }), "Aurora APC");
assert.equal(modelOf({ matches: [] }), null);
assert.equal(rivalOf({ competitorFit: [{ company: "Cobalt", products: ["X1"] }] }), "Cobalt · X1");
assert.equal(rivalOf({ competitorFit: [{ company: "Cobalt", products: [] }] }), "Cobalt");
assert.equal(rivalOf({ competitorFit: [] }), null);

/* ---- the top tenders: stored fit, then nearest deadline, then larger stored value ---- */
const T = (id, o) => ({ id, title: `T${id}`, issuer: "B", country: "C", status: "open", urlKind: "notice", ...o });
const open = [
  T("nofit", { closingDate: "2026-11-01" }),
  T("w1", { clientFit: "weak", closingDate: "2026-11-01" }),
  T("p-late", { clientFit: "partial", closingDate: "2027-02-01", valueAmount: 9e9 }),
  T("p-soon", { clientFit: "partial", closingDate: "2026-12-01", valueAmount: 1 }),
  T("s-big", { clientFit: "strong", closingDate: "2026-12-30", valueAmount: 9e6 }),
  T("s-small", { clientFit: "strong", closingDate: "2026-12-30", valueAmount: 1e6 }),
  T("s-nodate", { clientFit: "strong" }),
  T("s-soonest", { clientFit: "strong", closingDate: "2026-11-15", valueAmount: 5 }),
  T("poor", { clientFit: "poor", closingDate: "2026-11-01" }),
];
const rows = topTenders(open);
assert.deepEqual(rows.map((r) => r.id), ["s-soonest", "s-big", "s-small", "s-nodate", "p-soon", "p-late", "w1"]);
assert.ok(!rows.some((r) => r.id === "nofit" || r.id === "poor"), "a tender with no stored fit is not on the shortlist");
assert.deepEqual(topTenders([T("a", {}), T("b", { clientFit: "" })]), []);
assert.equal(topTenders(open, 3).length, 3);
assert.equal(topTenders(null).length, 0);

/* revenue is the stored text only: a row with no stored figure has none, and nothing is computed from value or fit */
const priced = topTenders([
  T("r1", { clientFit: "strong", revenueEstimate: "USD 60-95 M (share)", valueAmount: 185e6, value: "USD 185 million" }),
  T("r2", { clientFit: "strong", valueAmount: 4e6, value: "USD 4 M" }),
]);
assert.equal(priced.find((r) => r.id === "r1").revenue, "USD 60-95 M (share)");
assert.equal(priced.find((r) => r.id === "r2").revenue, null, "no stored revenue text -> none, never computed from value or fit");
assert.equal(priced.find((r) => r.id === "r2").estimate, false);

const valued = topTenders([T("v1", { clientFit: "strong", value: "USD 185 million", valueAmount: 185e6 })])[0];
assert.equal(valued.revenue, null, "a tender with a value but no revenue estimate shows no revenue");
assert.equal(valued.estimate, false);

/* decides is the stored closing date in the house format; none when there is none */
assert.equal(rows[0].decides, "15 Nov 2026");
assert.equal(rows.find((r) => r.id === "s-nodate").decides, "");

/* ---- the projects: the stored projects, by stored fit, then how far along, then the latest milestone ---- */
const P = (id, o) => ({ id, name: `P${id}`, company: `Co${id}`, customer: "Cust", location: "Loc", stage: "Trials", stageRank: 1, ...o });
const prows = topProjects([
  P("a", { stageRank: 1, latest: { date: "2026-09-01" }, clientFit: "weak" }),
  P("b", { stageRank: 3, latest: { date: "2026-01-01" }, clientFit: "partial" }),
  P("c", { stageRank: 3, latest: { date: "2026-08-01" }, clientFit: "partial" }),
  P("unfitted", { stageRank: 9, latest: { date: "2026-10-01" } }),
  P("d", { stageRank: 0, clientFit: "partial" }),
  P("e", { stageRank: 0, clientFit: "strong", revenueEstimate: "USD 1 M" }),
  { id: "nameless", stageRank: 9 },
]);
assert.deepEqual(prows.map((r) => r.id), ["e", "c", "b", "d", "a"]);
assert.equal(prows[0].revenue, "USD 1 M");
assert.equal(prows[2].revenue, null);
assert.equal(prows[2].fit, "partial");
assert.equal(prows[2].model, null);
assert.ok(!prows.some((r) => r.id === "unfitted"), "a project with no stored fit is not listed");
assert.deepEqual(topProjects([P("x", {}), P("y", { clientFit: "" })]), []);
assert.equal(prows[2].rival, "Cob", "the rival is the competitor the project belongs to");
assert.equal(prows[2].stage, "Trials");
assert.equal(prows[2].where, "Loc · Cust");
assert.equal(topProjects(null).length, 0);

/* ---- the next moves: the stored actions that are not past due, soonest first ---- */
const today = new Date(2026, 9, 20); // 20 Oct 2026, local
const mv = nextMoves([
  T("m1", { actions: [{ do: "later", due: "2026-12-01" }, { do: "past", due: "2026-10-01" }, { do: "now", due: "2026-10-20" }] }),
  T("m2", { actions: [{ do: "soon", due: "2026-10-23" }] }),
  T("m3", { actions: [] }),
], today);
assert.deepEqual(mv.map((m) => [m.action, m.days]), [["now", 0], ["soon", 3], ["later", 42]]);

/* ---- on the fixture and on the real shape (1403 tenders, one weak fit, no revenue) ---- */
const fx = JSON.parse(readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url)));
const fxTop = topTenders(bucketTenders(wireTendersWithRealDays(fx.tenders)).open);
assert.ok(fxTop.length > 0 && fxTop.every((r) => fitRank(r.fit) > 0));
for (const r of fxTop) assert.equal(r.revenue, revenueText(r.t).text);
for (const t of fx.tenders) {
  assert.equal(fitOf(t), t.clientFit ?? null);
  assert.equal(revenueOf(t), t.revenueMid == null ? null : Number(t.revenueMid));
}
const bare = Array.from({ length: 1403 }, (_, i) => T(String(i), { closingDate: "2027-01-01" }));
assert.deepEqual(topTenders(bare), [], "1403 tenders and no stored fit give an honest empty table");
assert.equal(topTenders([...bare, T("one", { clientFit: "weak" })]).length, 1);

// the module source carries no assumption of any kind
const src = readFileSync(new URL("./src/lib/tenderIntel.js", import.meta.url), "utf8");
assert.ok(!/genset|kva|generator|pWin|fitWeight|orderLag/i.test(src));

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
      import TenderCockpit from "./src/components/tenderCockpit/TenderCockpit.jsx";
      import { ReviewProvider } from "./src/components/review/Review.jsx";
      import { setClient } from "./src/lib/client.js";
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

// the fixture: both tables, from the stored fields, with the client's name in the headings
const html = render({ client: { short: "Aurora" }, tenders: wireTendersWithRealDays(fx.tenders), projects: fx.projects });
assert.match(html, /Top tenders/);
assert.match(html, /Projects to win before they tender/);
assert.match(html, /Aurora<!-- --> fit|Aurora fit/);
assert.match(html, /Aurora<!-- --> model|Aurora model/);
assert.match(html, /Rival to beat/);
assert.match(html, /USD 60-95 M \(Aurora share\)/, "the stored revenue estimate is printed as stored");
assert.match(html, /revenue is a stored estimate/);
assert.ok(!/revenue is an estimate/.test(html), "the unqualified estimate claim is gone");

// the review copy: every row of every table carries its Review controls, keyed on the tender's / project's own _src
{
  const data = { client: { short: "Aurora" }, tenders: wireTendersWithRealDays(fx.tenders), projects: fx.projects };
  const rv = renderReview(data);
  const nRows = (rv.match(/class="ti-row-link"/g) || []).length;
  const nBars = (rv.match(/class="rv-bar"/g) || []).length;
  assert.ok(nRows > 10 && nBars === nRows, `${nBars} Review bars for ${nRows} rows`);
  assert.ok(!/rv-bar/.test(html), "the live build renders no Review controls");
}

// the real shape: no stored fit -> the table frame and an honest empty state, no blank page
const real = render({ client: { short: "KSSL" }, tenders: wireTendersWithRealDays(bare.map((t) => ({ ...t, closingDate: undefined }))), projects: [] });
assert.match(real, /Top tenders/);
assert.match(real, /No open tender on record carries a stored fit yet\./);
assert.ok(!/<tbody>/.test(real), "no row is invented when no tender carries a stored fit");
assert.match(real, /Projects to win before they tender/);
assert.match(real, /No project on record carries a stored fit yet\./);
assert.ok(!/revenue is a stored estimate/.test(real), "no estimate is claimed when none is shown");
// an unfitted project is not listed (honest empty state); a fitted one lists, with dashes for what it does not store
const pNone = render({ client: { short: "KSSL" }, tenders: [], projects: [P("z", { stageNote: "Contract signed." })] });
assert.match(pNone, /No project on record carries a stored fit yet\./);
assert.ok(!/Pz/.test(pNone));
const pOnly = render({ client: { short: "KSSL" }, tenders: [], projects: [P("z", { stageNote: "Contract signed.", clientFit: "weak" })] });
assert.match(text(pOnly), /Pz\|.*Contract signed\.\|weak\|—\|Coz\|—/);
// a tender with a value but no revenue estimate: the revenue cell is a dash, and no estimate is claimed
const vOnly = render({ client: { short: "KSSL" }, projects: [], tenders: wireTendersWithRealDays([T("v", { clientFit: "strong", value: "USD 5 million", valueAmount: 5e6, closingDate: "2027-01-01" })]) });
assert.ok(!/USD 5 million/.test(vOnly), "the buyer's value is not shown as revenue");
assert.match(text(vOnly), /Tv\|.*\|strong\|—\|—\|—\|/);
assert.ok(!/revenue is a stored estimate/.test(vOnly));

console.log("ok - fit and revenue are stored fields; the cockpit orders stored rows, invents no revenue, and lists no tender without a stored fit");
