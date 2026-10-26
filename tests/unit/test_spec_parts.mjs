/* A packed spec value shows one figure per line (owner 22 Oct: "tech specs written in a single line").
 *
 *     node tests/unit/test_spec_parts.mjs
 */
import { specParts, specRows, productSheet, rowText } from "../../src/lib/specs.js";

let bad = 0;
const ok = (c, m) => { if (!c) { bad++; console.log("  FAIL " + m); } else console.log("  PASS " + m); };

const otokar = "GVW 19,000 kg; L 6,700 (with winch) x W 2,850 x H 2,650 mm; GC 450 mm; 375-400 hp turbo-diesel; 105 km/h / 700 km; 14.00 R20 run-flat";
ok(specParts(otokar).length === 6 && specParts(otokar)[1] === "L 6,700 (with winch) x W 2,850 x H 2,650 mm", "the Otokar line splits into its six figures");
ok(JSON.stringify(specParts("155 mm")) === '["155 mm"]', "a plain value is one part, unchanged");
ok(specParts("radar (X-band; S-band) and EO; laser").length === 2, "a ';' inside brackets does not split");
ok(specParts("• Weight 12.1 lb; size 10 in")[0] === "Weight 12.1 lb", "a leading bullet is dropped");
ok(specParts("a;b").length === 1, "';' with no space after it is not a separator");
ok(specParts(null).length === 0, "no value, no parts");
/* owner 2026-10-25: no blank-label rows, no caveat caption, a packed value under a real label is ONE row with a list */
const r = specRows({ "Variant-specific weight/performance not published by Otokar; shared platform data (AZ82ED-25)": otokar, Calibre: "7.62x51mm" });
ok(!r.some((x) => x.caption), "a caveat label is not shown as a caption");
ok(r.every((x) => x.label), "every row has a label");
ok(r[0].label === "GVW" && r[0].value === "19,000 kg", "a figure is labelled by its own leading words");
ok(r[1].label === "L × W × H" && r[1].value.startsWith("L 6,700"), "a dimension line is labelled L × W × H and kept whole");
const other = r.find((x) => x.label === "Other figures");
ok(other && other.values.includes("375-400 hp turbo-diesel"), "figures with no leading words share one labelled row, not blank labels");
ok(r[r.length - 1].label === "Calibre" && r[r.length - 1].value === "7.62x51mm", "a plain value is one row as stored");
const e = specRows({ Engine: "turbo-charged diesel, 440 hp; automated 12F/2R; permanent 4WD" });
ok(e.length === 1 && e[0].label === "Engine" && e[0].values.length === 3 && e[0].values[2] === "permanent 4WD", "under a real label the parts are one row with a list value");
ok(specRows({ Note: "Max speed 110 km/h; range 800 km" })[1].label === "Range", "under Note each figure names itself");

/* the API's presented sheet (backend/spec_sheet.py) is what the drawer shows when it is there */
const sheetP = { name: "F-35A Lightning II (conventional takeoff and landing, CTOL)", specs: { Calibre: "20mm" }, sheet: {
  description: ["Single-engine stealth fighter."],
  key: [{ l: "Length", v: "15.7 m (51.4 ft)" }, { l: "Maximum take-off weight", v: "31,751 kg (70,000 lb)" }],
  armament: [{ l: "Calibre", v: "20 mm" }, { l: "Standard internal weapons load", v: ["25 mm GAU-22/A cannon", "2x AIM-120C/D"] }],
  features: [{ l: "IOC", v: "USAF August 2016" }, { v: "Over 2,500 systems in service" }] } };
const ps = productSheet(sheetP);
ok(ps.sections.map((x) => x.title).join("|") === "Key specifications|Armament", "sections in order; an empty one (Other) is hidden");
ok(ps.sections[1].rows[1].values.length === 2 && rowText(ps.sections[1].rows[1]) === "25 mm GAU-22/A cannon; 2x AIM-120C/D", "a list value stays one row");
ok(ps.features[1].label === "" && ps.features[1].value.startsWith("Over"), "a feature without a label of its own is a plain line");
ok(ps.description[0] === "Single-engine stealth fighter.", "the description comes from the sheet");
const legacy = productSheet({ specs: { Engine: "a; b" }, features: { Hull: "steel" }, description: ["x", "y"].join(String.fromCharCode(10)) });
ok(legacy.sections[0].title === "Technical specifications" && legacy.sections[0].rows[0].values.length === 2, "a payload without a sheet falls back to the stored specs");
ok(legacy.features[0].label === "Hull" && legacy.description.length === 2, "...and to the stored features and description");
if (bad) { console.log(bad + " failed"); process.exit(1); }
console.log("all pass");
