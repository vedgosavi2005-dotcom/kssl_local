/* The Competitor Profile NEWS list's category dropdown (owner 2026-10-26).
 *
 * Options are the categories present in the company's news, each with its count; an article carrying several
 * ("Partnership / JV · Contract & order", or a stored "Facility & capacity · Investments") counts under each and
 * shows under each. "all" keeps everything; an unknown category keeps nothing; "—" (no category) is not an option.
 */
import { newsCategoryOptions, hasNewsCategory } from "../../src/lib/news.js";

let fail = 0;
const ck = (name, ok, d) => {
  console.log(`  ${name.padEnd(60)} ${ok ? "PASS" : "FAIL"}${d !== undefined && !ok ? "  " + JSON.stringify(d) : ""}`);
  if (!ok) fail++;
};

const arts = [
  { id: 1, category: "Partnership / JV · Contract & order" },
  { id: 2, category: "Contract & order" },
  { id: 3, category: "Facility & capacity · Investments" },
  { id: 4, category: "Investments" },
  { id: 5, category: "—" },
  { id: 6, category: "Export" },
  { id: 7, category: "Contract & order·Export" },          // no spaces around the dot: still two
];

const opts = newsCategoryOptions(arts);
ck("options: present categories, most articles first, ties by name",
  JSON.stringify(opts.map((o) => o.value)) ===
    JSON.stringify(["Contract & order", "Export", "Investments", "Facility & capacity", "Partnership / JV"]), opts);
ck("each option carries its count in the label", opts[0].count === 3 && opts[0].label === "Contract & order (3)", opts[0]);
ck("'—' (no category) is not an option", !opts.some((o) => o.value === "—"));
ck("no articles -> no options", newsCategoryOptions([]).length === 0 && newsCategoryOptions(null).length === 0);

const pick = (cat) => arts.filter((a) => hasNewsCategory(a, cat)).map((a) => a.id);
ck("all keeps every article", pick("all").length === arts.length && pick("").length === arts.length);
ck("a split category matches each of its parts",
  JSON.stringify(pick("Contract & order")) === "[1,2,7]" && JSON.stringify(pick("Partnership / JV")) === "[1]", pick("Contract & order"));
ck("Investments: the added and the lone one", JSON.stringify(pick("Investments")) === "[3,4]", pick("Investments"));
ck("a category is matched whole, not as a substring", pick("Contract").length === 0 && pick("Export").length === 2);
ck("each option's count equals what the filter shows", opts.every((o) => pick(o.value).length === o.count));

console.log(fail ? `\n${fail} FAILED` : "\nall pass");
process.exit(fail ? 1 : 0);
