/* A full-name column is the easiest place on this dashboard to publish something nobody sourced.
   So the expansion table is gone: the full name is competitors[cid].legal (the stored legal name)
   or the served display name, and nothing else. */
import fs from "node:fs";
import * as cn from "../../src/lib/companyNames.js";
import { competitorFullName, companyShort, initialisms, isAbbreviated } from "../../src/lib/companyNames.js";

const d = JSON.parse(fs.readFileSync("../../fixtures/kssl_dataset.json", "utf8"));
let fails = 0;
const ck = (name, ok, detail) => {
  console.log(`  ${String(name).padEnd(66)} ${ok ? "ok" : "FAIL"}${!ok && detail ? "  " + detail : ""}`);
  if (!ok) fails++;
};

ck("COMPANY_NAMES, nameOf, listLine, detailLine are gone",
  !("COMPANY_NAMES" in cn) && !("nameOf" in cn) && !("listLine" in cn) && !("detailLine" in cn));
const src = fs.readFileSync("../../src/lib/companyNames.js", "utf8");
ck("no source tags or expansion entries in the module", !/workbook|expands:|full:/i.test(src));

const [cid, row] = Object.entries(d.competitors).find(([, c]) => c.legal && c.legal !== c.name);
ck("full name = stored legal name", competitorFullName(cid, row.name, d.competitors) === row.legal, row.legal);
ck("no legal name -> the served name", competitorFullName("x", "Some Co", {}) === "Some Co");
ck("unknown id is not echoed", competitorFullName("some-uuid", "", {}) === "");
ck("&amp; is cleaned", competitorFullName("x", "L&amp;T", null) === "L&T");

ck("initialisms found", initialisms("BAE Systems").join() === "BAE" && isAbbreviated("KNDS"));
ck("a long plain name is initialled", companyShort("Advanced Weapons and Equipment India Limited") === "AWEIL");
ck("an already-initialled name is left", companyShort("Saab AB") === "Saab AB");
ck("a short name passes through", companyShort("Nexter") === "Nexter");

console.log(fails ? `${fails} FAILED` : "all passed");
process.exit(fails ? 1 : 0);
