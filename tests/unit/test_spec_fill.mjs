/* A matchup product keeps its own specs and gains only the fields it lacks.
 *
 *     node tests/unit/test_spec_fill.mjs
 *
 * Measured on staging 2026-09-18: 25 products that have a matchup (Archer, K9 Thunder,
 * PzH 2000, NSM) showed only the matchup's fields, hiding 149 enriched ones.
 */
import { fillSpecs, specKey } from "../../src/lib/specs.js";

let bad = 0;
const ok = (c, m) => { if (!c) { bad++; console.log("  FAIL " + m); } else console.log("  PASS " + m); };

const r = fillSpecs({ Calibre: "155 mm", "Maximum range": "40 km" },
                    { Range: "54 km", Crew: "4", "Max speed": "65 km/h", Weight: "" });
ok(r.specs.Calibre === "155 mm" && r.specs["Maximum range"] === "40 km", "the matchup's own values are kept");
ok("Range" in r.specs, "a distinct label is a distinct field: no synonym table merges Range into Maximum range");
ok(r.specs.Crew === "4" && r.specs["Max speed"] === "65 km/h", "fields it lacks are added");
ok(specKey("Top speed") !== specKey("Max speed") && specKey("Caliber") !== specKey("Calibre"), "no SPEC_SYNONYMS: labels are compared as stored");
ok(!("Weight" in r.specs), "an empty value adds nothing");
ok(JSON.stringify(r.added) === JSON.stringify(["Range", "Crew", "Max speed"]), "added lists exactly the new fields");
ok(Object.keys(fillSpecs({ A: "1" }, null).specs).length === 1, "no record changes nothing");
ok(fillSpecs(undefined, { B: "2" }).specs.B === "2", "a matchup with no specs takes the record's");
ok(specKey(" Top  Speed ") === "top speed", "labels fold only for case and spacing");

if (bad) { console.log(bad + " failure(s)"); process.exit(1); }
console.log("ok - matchup products keep their specs and gain only the missing fields");
