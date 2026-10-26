/* Partnership page: tie detail and graph labels (functional test G14, 2026-10-25).
 *
 *     node tests/unit/test_partner_tie_detail.mjs
 *
 *   - "What each side gets" prints the stored tag in plain words, never "market_access:",
 *     and leaves out a value that is only "not stated";
 *   - "Since" is the earliest date the tie or its timeline states;
 *   - every timeline step with a url shows a source chip;
 *   - a partner name is not cut without a mark ("Ministry of Defence and"), and no leaf
 *     label starts under the canvas toolbar.
 */
import { tieValueParts, tieSince } from "../../src/lib/tieValue.js";
import { createPartners } from "../../src/lib/partners.js";

let fails = 0;
const ck = (name, ok, detail) => {
  console.log(`  ${name.padEnd(70)} ${ok ? "ok" : "FAIL"}${!ok && detail ? "  " + detail : ""}`);
  if (!ok) fails++;
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// --- tieValueParts
ck("market_access: tag -> Market access", same(tieValueParts("market_access: a UAV assembly workshop"), { tag: "Market access", text: "a UAV assembly workshop" }));
ck("technology: tag -> Technology", same(tieValueParts("technology: Hermes 900 production"), { tag: "Technology", text: "Hermes 900 production" }));
ck("other: tag is dropped, text kept", same(tieValueParts("other: NORINCO keeps the royalty rights"), { tag: null, text: "NORINCO keeps the royalty rights" }));
ck("untagged text kept as is", same(tieValueParts("A partner for exports."), { tag: null, text: "A partner for exports." }));
ck("unknown tag in plain words", same(tieValueParts("joint_bid: a shared bid"), { tag: "Joint bid", text: "a shared bid" }));
for (const v of ["not stated", "other: not stated", "Not stated.", "", null, "market_access:"]) {
  ck(`${JSON.stringify(v)} is no value`, tieValueParts(v) === null);
}
ck("a sentence that mentions 'not stated' is kept",
  !!tieValueParts("other: Sold its radios business; the sale price is not stated."));

// --- tieSince
ck("first step earlier than date -> the step", tieSince({ date: "2024-03-11", steps: [{ date: "2023-12-22" }, { date: "2024-03-06" }] }) === "2023-12-22");
ck("steps later than date -> the date", tieSince({ date: "2019-02-22", steps: [{ date: "2020-01-01" }] }) === "2019-02-22");
ck("no date, dated steps -> earliest step", tieSince({ date: null, steps: [{ date: null }, { date: "2025-08-11" }] }) === "2025-08-11");
ck("nothing dated -> null", tieSince({ date: null, steps: [{ date: null }] }) === null);

// --- the rendered tie and graph, on a two-company fixture
const longName = "Ministry of Defence and Veteran Affairs";
const co = {
  name: "Rival Co", dir: "rival", partners: [
    { id: "t1", label: "Heavy Industries Taxila", rel: "technology-partner", ptype: "Technology / ToT", date: "2024-03-11",
      valueComp: "other: Rival keeps the royalty rights", valuePartner: "market_access: Pakistan gets local manufacture",
      steps: [
        { date: "2023-12-22", step: "agreement", label: "ToT signed", publisher: "Example News", url: "https://example.test/a" },
        { date: "2024-03-06", step: "first_product", label: "First unit", publisher: "Example Wire", url: "https://example.test/b" },
      ], src: "https://example.test/a" },
    { id: "t2", label: longName, rel: "other", date: "2024-04-19", valueComp: "not stated", valuePartner: "capacity: local UAV assembly", src: "https://example.test/c" },
    ...["Dongfeng Motor Group", "Bank of China", "Changhong Holding Group", "PT Nusatama Berkah", "Sichuan Provincial People's Government",
      "Arab Organization for Industrialization", "Weststar Defence Industries"].map((label, i) => ({
      id: `m${i}`, label, rel: "mou-strategic", date: "2026-01-01", src: "https://example.test/m" })),
  ],
};
const data = { competitors: { rival: co }, compOrder: ["rival"], client: { id: "client", name: "Client", short: "CL" }, KSSL_PARTNERS: [] };
const P = createPartners(data);
const html = P.tieHtml(co, "rival", "t1", "CL");
ck("tie: no raw tag printed", !/market_access:|other:/.test(html), html.match(/[a-z_]+:/g));
ck("tie: tag in plain words", html.includes("Market access:"));
// owner 2026-10-26: no Relationship / Territory / Since / Status table; the timeline is the signal drawer's (folded, rail, chips)
ck("tie: no facts table", !/tie-facts|>Territory<|>Since</.test(html));
ck("tie: timeline drawn like the signal drawer", /<details class="ctx-sec cd-fold"><summary class="eyebrow">Timeline<\/summary><ol class="pj-time">/.test(html)
  && /<span class="pj-d">22 Dec 2023<\/span>/.test(html));
ck("tie: each step shows its source", (html.match(/<li[^>]*><span class="pj-d">/g) || []).length === 2 && html.includes("https://example.test/b"));
const html2 = P.tieHtml(co, "rival", "t2", "CL");
ck("tie: a 'not stated' side is left out", !/not stated/i.test(html2) && html2.includes("Capacity:"));

const other = P.typeGraphSvg(co, { stage: "focus", type: "other", mode: "type" });
const lines = [...other.matchAll(/<text class="lbl-ptr-title pt-leaf-lbl"[^>]*>([^<]*)<\/text>/g)].map((m) => m[1]);
ck("graph: the long name keeps every word", lines.join(" ") === longName, JSON.stringify(lines));
const mou = P.typeGraphSvg(co, { stage: "focus", type: "mou-strategic", mode: "type" });
const ys = [...mou.matchAll(/<text class="lbl-ptr-title pt-leaf-lbl"[^>]*\by="(-?[\d.]+)"/g)].map((m) => +m[1]);
ck("graph: no leaf label under the toolbar (y >= 52)", ys.length > 0 && Math.min(...ys) - 9 >= 52 - 0.5, `min y ${Math.min(...ys)}`);

console.log(fails ? `\nFAIL - ${fails} checks` : "\nok - tie detail and graph labels read cleanly");
process.exit(fails ? 1 : 0);
