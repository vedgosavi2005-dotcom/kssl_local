/* The roster is every competitor row the dataset carries; this module only sorts. */
import fs from "node:fs";
import * as roster from "./src/lib/roster.js";
import { sortCompaniesByName } from "./src/lib/roster.js";

let fail = 0;
const ck = (name, ok, d) => {
  console.log(`  ${name.padEnd(62)} ${ok ? "PASS" : "FAIL"}${d !== undefined && !ok ? "  " + JSON.stringify(d) : ""}`);
  if (!ok) fail++;
};

ck("the hardcoded ROSTER and applyRoster are gone", !("ROSTER" in roster) && !("applyRoster" in roster));
ck("roster.js carries no company id list", !/rheinmetall|kalashnikov/i.test(fs.readFileSync("./src/lib/roster.js", "utf8")));
ck("the duplicate-merge module is gone", !fs.existsSync("./src/lib/dedupeCompanies.js"));

const s = sortCompaniesByName({
  competitors: {
    kssl: { name: "KSSL", dir: "client" },
    saab: { name: "Saab" }, "bae-systems": { name: "BAE Systems" }, anduril: { name: "anduril" },
  },
  compOrder: ["saab", "kssl", "bae-systems", "anduril"],
  geoComps: [{ id: "saab", name: "Saab" }, { id: "kssl", name: "KSSL", isBf: true }, { id: "anduril", name: "Anduril" }],
});
ck("alphabetical by name, client first", JSON.stringify(s.compOrder) === JSON.stringify(["kssl", "anduril", "bae-systems", "saab"]), s.compOrder);
ck("geo picker alphabetical, client first", s.geoComps.map((g) => g.id).join() === "kssl,anduril,saab", s.geoComps);
ck("sort: no competitors -> unchanged", sortCompaniesByName({ x: 1 }).x === 1);

console.log(fail ? `${fail} FAILED` : "all passed");
process.exit(fail ? 1 : 0);
