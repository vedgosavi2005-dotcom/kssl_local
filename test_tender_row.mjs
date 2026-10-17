/* Every tender row exposes the SAME parameters, in the SAME order, and says so when
 * one is not on record.
 *
 *     node test_tender_row.mjs
 *
 * REPORTED: "many have a small basic title, no understanding ... fix per tender row
 * parameters, resolve from each tender and show a consistent flow".
 *
 * Measured on the served corpus (136 tenders, 2026-09-05): the median title is 29
 * characters, 40 titles are 20 characters or fewer and 50 are three words or fewer --
 * "Ammunition", "Firearms", "Eb Tuba". The card under such a title used to print only
 * the fields that happened to be filled, so one row read "buyer · country · category ·
 * value · qty · closes" and the next read "buyer · country · category", and the reader
 * could not tell a field the notice does not publish from one the card forgot.
 *
 * What this pins, on the resolver (src/lib/tenderRow.js) and on the rendered page:
 *
 *   1. FIXED SHAPE: every tender resolves to the same parameter keys in the same order,
 *      whatever the record carries;
 *   2. UNRESOLVED IS EXPLICIT: a parameter the record cannot fill renders the literal
 *      unresolved state with its own class -- never an empty value cell, and never a
 *      guessed value (an empty status is not "Open"; an empty value is not "0");
 *   3. FALLBACK CHAIN: each parameter is drawn from the documented source, in the
 *      documented order, and a computed countdown is never mistaken for a stored date;
 *   4. THE TITLE IS THE STORED TITLE: nothing is composed into it.
 *
 * Hermetic: the resolver is imported directly; the page is bundled with esbuild and
 * server-rendered with the two state hooks stubbed. No network, no dataset dump.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "esbuild";

let bad = 0;
const fail = (m) => { bad++; console.log("  FAIL " + m); };
const ok = (m) => console.log("  ok   " + m);

const { resolveTenderRow, TENDER_PARAMS, NOT_ON_RECORD, tenderGist, tenderSummary } = await import("./src/lib/tenderRow.js");
const { wireTendersWithRealDays } = await import("./src/lib/tenderCalc.js");

/* ---------------------------------------------------------------- fixture ---- */
/* The shape serving.tender emits. Every optional field starts EMPTY so a test names
   exactly what it fills. */
const tender = (id, over) => ({
  id, title: `Tender ${id}`, issuer: "", country: "", cat: "", value: null, qty: null,
  deadline: null, dl: null, reqNote: null, req: [], matches: [], lean: null,
  leanTxt: null, status: "", url: "", urlKind: "tender", srcs: [], stage: null, ...over,
});

const WANT_KEYS = ["buyer", "country", "category", "value", "quantity", "posted", "closing", "status", "source"];

/* ------------------------------------------------------ 1. fixed shape ---- */
{
  const keys = TENDER_PARAMS.map((p) => p.key);
  if (JSON.stringify(keys) !== JSON.stringify(WANT_KEYS))
    fail(`TENDER_PARAMS is ${JSON.stringify(keys)}, want ${JSON.stringify(WANT_KEYS)}`);
  else ok("TENDER_PARAMS is the documented nine, in order");

  const full = tender("full", {
    issuer: "A Ministry", country: "India", cat: "Artillery", value: "EUR 4.0m",
    qty: "20 units", deadline: "22 Jun 2031", status: "open", url: "https://example.test/full",
    srcs: [{ url: "https://example.test/full", label: "Example Portal" }],
  });
  const empty = tender("empty");
  for (const t of [full, empty, { id: "bare" }, null]) {
    const row = resolveTenderRow(t);
    const keys = row.params.map((p) => p.key);
    if (JSON.stringify(keys) !== JSON.stringify(WANT_KEYS))
      fail(`resolveTenderRow(${t && t.id}) exposes ${JSON.stringify(keys)}`);
  }
  ok("a full record, an empty record, a bare {id} and null all resolve to the same nine keys");
}

/* -------------------------------------------------- 2. unresolved state ---- */
{
  const row = resolveTenderRow(tender("empty"));
  for (const p of row.params) {
    if (p.value !== null) fail(`empty record: ${p.key} resolved to ${JSON.stringify(p.value)} -- a guess`);
    if (p.text !== NOT_ON_RECORD) fail(`empty record: ${p.key} prints ${JSON.stringify(p.text)}, want the unresolved literal`);
    if (p.from !== null) fail(`empty record: ${p.key} claims source ${JSON.stringify(p.from)}`);
  }
  if (!/not on record/.test(NOT_ON_RECORD)) fail(`NOT_ON_RECORD is ${JSON.stringify(NOT_ON_RECORD)} -- it must SAY the field is absent`);
  ok("an empty record resolves every parameter to the unresolved literal, from no source");

  /* the two guesses the old code made */
  const s = resolveTenderRow(tender("nostatus", { issuer: "X" })).params.find((p) => p.key === "status");
  if (s.value !== null) fail(`empty status was resolved to ${JSON.stringify(s.value)} -- the old default of "Open" is a guess`);
  else ok("an empty status is not defaulted to Open");
  const v = resolveTenderRow(tender("noval", { value: "" })).params.find((p) => p.key === "value");
  if (v.value !== null) fail(`blank value resolved to ${JSON.stringify(v.value)}`);
  else ok("a blank value is unresolved, not zero");
}

/* ---------------------------------------------------- 3. fallback chain ---- */
const pick = (t, key) => resolveTenderRow(t).params.find((p) => p.key === key);
{
  /* buyer, country, value: the stored field only -- requirement rows are [code, value] and no code names them */
  let p = pick(tender("b1", { issuer: "Direct Buyer", req: [["Buyer", "Req Buyer"]] }), "buyer");
  if (p.value !== "Direct Buyer" || p.from !== "issuer") fail(`buyer: issuer should win, got ${JSON.stringify(p)}`);
  p = pick(tender("b2", { req: [["Contracting authority", "Req Buyer"]] }), "buyer");
  if (p.value !== null) fail(`buyer: a requirement row is not a buyer, got ${JSON.stringify(p)}`);
  else ok("buyer: the stored issuer, nothing guessed from a requirement label");

  p = pick(tender("c1", { req: [["Country", "Norway"]] }), "country");
  if (p.value !== null) fail(`country: a requirement row is not a country, got ${JSON.stringify(p)}`);
  p = pick(tender("c2", { cat: "Ammunition" }), "category");
  if (p.value !== "Ammunition" || p.from !== "cat") fail(`category: cat, got ${JSON.stringify(p)}`);
  else ok("country: the stored country; category: cat");

  /* value and quantity */
  p = pick(tender("v1", { value: "EUR 1m", req: [["Estimated value", "EUR 9m"]] }), "value");
  if (p.value !== "EUR 1m" || p.from !== "value") fail(`value: stored value should win, got ${JSON.stringify(p)}`);
  p = pick(tender("v2", { req: [["Estimated value", "EUR 9m"]] }), "value");
  if (p.value !== null) fail(`value: a requirement row is not a value, got ${JSON.stringify(p)}`);
  p = pick(tender("q1", { req: [["quantity", "12 units"]] }), "quantity");
  if (p.value !== "12 units" || p.from !== "req") fail(`quantity: code fallback, got ${JSON.stringify(p)}`);
  p = pick(tender("q2", { qty: "5 sets", req: [["quantity", "12 units"]] }), "quantity");
  if (p.value !== "5 sets" || p.from !== "qty") fail(`quantity: stored qty should win, got ${JSON.stringify(p)}`);
  else ok("value: the stored value; quantity: qty, then the quantity code");

  /* published: the stored posted date, then a req row naming it */
  p = pick(tender("pub1", { posted: "2026-08-15" }), "posted");
  if (p.value !== "15 Aug 2026" || p.from !== "posted") fail(`posted: stored date, got ${JSON.stringify(p)}`);
  p = pick(tender("pub2", { req: [["published_date", "1 Sep 2026"]] }), "posted");
  if (p.value !== "01 Sep 2026" || p.from !== "req") fail(`posted: req fallback, got ${JSON.stringify(p)}`);
  else ok("published: stored posted date, then the published_date code");

  /* closing date: served deadline (as closingDate after wiring), then req, then stage;
     one formatter; a computed countdown is NEVER a source */
  p = pick(tender("d1", { deadline: "2031-06-22" }), "closing");
  if (p.value !== "22 Jun 2031" || p.from !== "deadline") fail(`closing: served ISO deadline, got ${JSON.stringify(p)}`);
  const wired = wireTendersWithRealDays([tender("d2", { deadline: "22 Jun 2031", status: "open" })])[0];
  p = pick(wired, "closing");
  if (p.value !== "22 Jun 2031" || p.from !== "deadline") fail(`closing: after wiring, the served date (not the countdown) -- got ${JSON.stringify(p)}`);
  const wiredNone = wireTendersWithRealDays([tender("d3", { status: "open" })])[0];
  p = pick(wiredNone, "closing");
  if (p.value !== null) fail(`closing: a wired record with no served date resolved to ${JSON.stringify(p.value)} -- that is the computed placeholder, not a record`);
  p = pick(tender("d4", { deadline: "12 days left" }), "closing");
  if (p.value !== null) fail(`closing: a baked countdown was accepted as a date: ${JSON.stringify(p)}`);
  p = pick(tender("d5", { req: [["closing_date", "1 Sep 2031"]] }), "closing");
  // the one formatter zero-pads the day, so "1 Sep" comes back "01 Sep"
  if (p.value !== "01 Sep 2031" || p.from !== "req") fail(`closing: req fallback, got ${JSON.stringify(p)}`);
  p = pick(tender("d6", { milestone: "AoN cleared" }), "closing");
  if (p.value !== "AoN cleared" || p.from !== "milestone") fail(`closing: milestone fallback, got ${JSON.stringify(p)}`);
  p = pick(tender("d7", { deadline: "01 Sept 2031" }), "closing");
  if (p.value !== "01 Sep 2031") fail(`closing: not through the one formatter, got ${JSON.stringify(p.value)}`);
  else ok("closing: served deadline (through formatDate), then the closing_date code, then the milestone; countdowns refused");

  /* status: awarded (status or urlKind), closed (status, or a served date now passed),
     else the stored status word */
  p = pick(tender("s1", { status: "awarded" }), "status");
  if (p.value !== "Awarded" || p.from !== "status") fail(`status: awarded, got ${JSON.stringify(p)}`);
  p = pick(tender("s2", { urlKind: "award" }), "status");
  if (p.value !== "Awarded" || p.from !== "urlKind") fail(`status: urlKind=award, got ${JSON.stringify(p)}`);
  p = pick(tender("s3", { status: "closed" }), "status");
  if (p.value !== "Closed" || p.from !== "status") fail(`status: closed, got ${JSON.stringify(p)}`);
  const passed = wireTendersWithRealDays([tender("s4", { status: "open", deadline: "1 Jan 2020" })])[0];
  p = pick(passed, "status");
  if (p.value !== "Closed" || p.from !== "deadline") fail(`status: open with a passed served date must read Closed from the deadline, got ${JSON.stringify(p)}`);
  p = pick(tender("s5", { status: "open" }), "status");
  if (p.value !== "Open" || p.from !== "status") fail(`status: open, got ${JSON.stringify(p)}`);
  else ok("status: awarded (status/urlKind), closed (status/passed date), else the stored word");

  /* source: the portal label, else the host of the url */
  p = pick(tender("p1", { srcs: [{ label: "TED (EU)", url: "https://ted.europa.eu/x" }], url: "https://other.test/y" }), "source");
  if (p.value !== "TED (EU)" || p.from !== "srcs") fail(`source: srcs label, got ${JSON.stringify(p)}`);
  p = pick(tender("p2", { url: "https://www.find-tender.service.gov.uk/Notice/1" }), "source");
  if (p.value !== "find-tender.service.gov.uk" || p.from !== "url") fail(`source: url host fallback, got ${JSON.stringify(p)}`);
  else ok("source: srcs[0].label, then the url host");

  /* the title is the stored title */
  const r = resolveTenderRow(tender("t1", { title: "Ammunition", issuer: "Bundesamt", country: "Germany" }));
  if (r.title !== "Ammunition") fail(`title was rewritten to ${JSON.stringify(r.title)}`);
  else ok("the title is the stored title, untouched");
}

/* ------------------------------------------------------ 4. rendered page ---- */
const here = fileURLToPath(new URL(".", import.meta.url));
const tmp = mkdtempSync(join(tmpdir(), "kssl-tender-row-"));
const stubs = {
  DataProvider: `export function useData() { return globalThis.__KSSL_TEST__; }`,
  AppState: `export function useAppState() {
    return { searchQuery: "", setScope() {}, takePending() { return null; }, jumpTo() {},
             pillar: "market", view: "tender", setView() {}, setChatCtx() {} };
  }
  export const RAIL = {}; export const PILLARS = []; export const isOverview = () => false;
  export function useHeaderReport() {}
  export const PILLAR_LABEL = { competitive: "Competitive", market: "Market", technology: "Technology" };`,
};
const entry = `
  import React from "react";
  import { renderToStaticMarkup } from "react-dom/server";
  import Tenders from "./src/pages/market/Tenders.jsx";
  import { setClient } from "./src/lib/client.js";
  export function render(data) {
    setClient(data.client); // the page reads the client's name from the loaded dataset
    globalThis.__KSSL_TEST__ = { data, gapModel: [], counts: {}, viewMeta: {} };
    return renderToStaticMarkup(React.createElement(Tenders, { mode: "tender" }));
  }`;
const out = join(tmp, "page.mjs");
await build({
  stdin: { contents: entry, resolveDir: here, loader: "jsx" },
  bundle: true, platform: "node", format: "esm", jsx: "automatic", outfile: out,
  logLevel: "silent", loader: { ".css": "empty" },
  define: { "import.meta.env.VITE_REVIEW": "undefined" }, // Review.jsx reads it; the live build has none
  banner: { js: 'import { createRequire as __cr } from "node:module"; const require = __cr(import.meta.url);' },
  plugins: [{
    name: "stub-state",
    setup(b) {
      b.onResolve({ filter: /state\/(DataProvider|AppState)$/ }, (a) => ({
        path: a.path.replace(/.*\//, ""), namespace: "stub",
      }));
      b.onLoad({ filter: /.*/, namespace: "stub" }, (a) => ({ contents: stubs[a.path], loader: "js" }));
    },
  }],
});
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
globalThis.window = { location: { hash: "" }, addEventListener() {}, removeEventListener() {} };
globalThis.document = { addEventListener() {}, removeEventListener() {} };

const { render } = await import(pathToFileURL(out).href);
const rows = wireTendersWithRealDays([
  /* the shape the corpus mostly has: a one-word title, no value, no qty, no date */
  tender("bare", { title: "Ammunition", issuer: "Bundesamt", country: "Germany", cat: "Ammunition", status: "open",
                   url: "https://ted.europa.eu/1", srcs: [{ label: "TED (EU)", url: "https://ted.europa.eu/1" }] }),
  /* everything filled */
  tender("full", { title: "155mm HE shells", issuer: "A Ministry", country: "India", cat: "Ammunition",
                   value: "EUR 4.0m", qty: "20 units", posted: "15 Aug 2026", deadline: "22 Jun 2031", status: "open",
                   url: "https://example.test/full", srcs: [{ label: "Example Portal", url: "https://example.test/full" }] }),
  /* nothing but a title and an open status -- must still show all eight, all unresolved but status */
  tender("thin", { title: "Firearms", status: "open" }),
]);
const html = render({ tenders: rows, tpAllCountries: [], tpAllCats: [], client: { short: "CC" } });
rmSync(tmp, { recursive: true, force: true });

const cards = [...html.matchAll(/<div class="tcard[^"]*"[\s\S]*?(?=<div class="tcard|<div class="tp-asmt")/g)].map((m) => m[0]);
if (cards.length !== 3) fail(`rendered ${cards.length} cards, want 3`);
const labelsOf = (card) => [...card.matchAll(/class="tpk"[^>]*>([^<]*)</g)].map((m) => m[1].trim().toLowerCase());
const valuesOf = (card) => [...card.matchAll(/<span class="tpv"[^>]*>([\s\S]*?)<\/span>/g)].map((m) => m[1].replace(/<[^>]+>/g, "").trim());
/* THE CARD IS THE SAME ON EVERY ROW: Buyer, Country, Category, Value, Status, then the client's fit row. A cell the
   record leaves empty prints "not disclosed" (value) or a dash, it is not dropped. */
const wantCells = ["buyer", "country", "category", "value", "status"];
for (const card of cards) {
  const title = (card.match(/class="ttl"[^>]*>([^<]*)</) || [])[1];
  const labels = labelsOf(card);
  if (JSON.stringify(labels) !== JSON.stringify(wantCells))
    fail(`card "${title}": cells ${JSON.stringify(labels)}, want ${JSON.stringify(wantCells)}`);
  const vals = valuesOf(card);
  if (vals.length !== wantCells.length) fail(`card "${title}": ${vals.length} value cells for ${wantCells.length} labels`);
  for (const v of vals) {
    if (!v) fail(`card "${title}": an empty value cell`);
    if (v === NOT_ON_RECORD) fail(`card "${title}": the old unresolved literal appears in the list`);
  }
  if (!/<div class="fitbar"><span class="fitlab">CC(?:<!-- -->)? fit<\/span><span class="fittrack"><i [^>]*><\/i><\/span><span class="fitpct grade">/.test(card))
    fail(`card "${title}": no fit row with the client's label`);
}
ok("rendered: every card has the five cells in order and the fit row");
{
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("./src/pages/market/Tenders.jsx", import.meta.url), "utf8");
  if (!/<Review src=\{row\._src\} \/>/.test(src)) fail("the tender card carries no Review control");
  else ok("the tender card carries the Review control");
}

const thin = cards.find((c) => /class="ttl"[^>]*>Firearms</.test(c)) || "";
const thinVals = valuesOf(thin);
if (JSON.stringify(thinVals) !== JSON.stringify(["—", "—", "—", "not disclosed", "Open"]))
  fail(`title-only card: cells ${JSON.stringify(thinVals)}, want dashes, "not disclosed" for the value, and the stored status`);
else ok('rendered: a title-only card prints "—" for buyer, country and category and "not disclosed" for the value');
if (!/<span class="fitpct grade">—<\/span>/.test(thin) || !/<i class="" style="width:0%"><\/i>/.test(thin))
  fail("title-only card: with no stored fit the bar is not empty and the word is not a dash");
else ok("rendered: no stored fit gives an empty bar and a dash");
const bareCard = cards.find((c) => /class="ttl"[^>]*>Ammunition</.test(c)) || "";
if (!/class="tpv"[^>]*>Bundesamt</.test(bareCard) || !/class="tpv"[^>]*>Germany</.test(bareCard))
  fail("one-word title card: buyer and country were not composed around the title");
else ok("rendered: a one-word title is surrounded by the buyer, country and category the record carries");

/* a stored fit word (on the tender, or on the first matched product) fills the bar and prints the word */
{
  const html2 = render({
    tenders: wireTendersWithRealDays([
      tender("fit1", { title: "Graded", status: "open", clientFit: "partial" }),
      tender("fit2", { title: "Scored", status: "open", matches: [{ n: "P", fit: "strong", pct: "92%" }] }),
    ]),
    tpAllCountries: [], tpAllCats: [], client: { short: "CC" },
  });
  if (!/<i class="mid" style="width:55%"><\/i><\/span><span class="fitpct grade">partial</.test(html2)) fail("a stored tender fit (partial) did not fill the bar and print the word");
  else if (!/<i class="high" style="width:92%"><\/i><\/span><span class="fitpct">92%</.test(html2)) fail("a stored match percentage did not set the bar's own length");
  else ok("rendered: a stored grade or percentage fills the fit bar");
}

/* --------------------------------- posted regex must not eat the title row ---- */
{
  // The real SAM reference rows carry ["Title, as published", "Vane,Large"]; an
  // unanchored /published/ matched it and printed the raw title in the Published slot.
  const t = tender("vane", {
    issuer: "Dept Of Defense", country: "United States", cat: "Ammunition",
    req: [["Category", "Ammunition"], ["Title, as published", "Vane,Large"]],
  });
  const posted = resolveTenderRow(t).params.find((p) => p.key === "posted");
  if (posted.text !== NOT_ON_RECORD)
    fail(`posted grabbed the "Title, as published" row: got ${JSON.stringify(posted.text)}`);
  else ok('posted ignores the "Title, as published" requirement row');
  // A genuine publication-date row still resolves.
  const t2 = tender("pd", { req: [["published_date", "1 Sep 2026"]] });
  const p2 = resolveTenderRow(t2).params.find((p) => p.key === "posted");
  if (p2.text !== "01 Sep 2026") fail(`publication date row lost: ${JSON.stringify(p2.text)}`);
  else ok("a published_date code row still resolves");
}

/* --------------------------------- gist + summary are grounded readable ---- */
{
  const t = tender("g1", {
    title: "Vane Large", issuer: "Dept Of Defense", country: "United States",
    cat: "Ammunition", lean: "go", leanTxt: "Strong match for the portfolio.", deadline: "28 Sep 2026",
  });
  const g = tenderGist(t);
  if (g !== "Vane Large — Ammunition · United States")
    fail(`gist: got ${JSON.stringify(g)}`);
  else ok("gist adds category and country around a terse item name");

  // Redundancy guard: a title that already names its category does not repeat it.
  const t2 = tender("g2", {
    title: "Commercial Pattern Armoured Vehicles Phase II B", country: "Canada",
    cat: "Protected & Armoured Vehicles",
  });
  if (/Armoured Vehicles.*Armoured Vehicles/.test(tenderGist(t2)))
    fail(`gist repeated the category: ${tenderGist(t2)}`);
  else ok("gist does not repeat a category the title already names");

  const s = tenderSummary(t);
  if (!/Dept Of Defense is procuring Vane Large/.test(s) ||
      !/Ammunition category/.test(s) ||
      !/Strong match for the portfolio\./.test(s) ||
      !/not disclosed/.test(s))
    fail(`summary missing a grounded clause: ${JSON.stringify(s)}`);
  else ok("summary states buyer, item, category, the stored lean sentence, and the value/qty record");

  // No invention: a value that is not on record never appears as a number.
  if (/\bvalue\s+[€$₹]?\d/i.test(s)) fail("summary invented a value");
  else ok("summary invents no value when the notice publishes none");
}

console.log(bad ? `\n${bad} FAILED` : "\nall passed");
process.exit(bad ? 1 : 0);
