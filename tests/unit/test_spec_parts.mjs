/* A packed spec value shows one figure per line (owner 22 Oct: "tech specs written in a single line").
 *
 *     node tests/unit/test_spec_parts.mjs
 */
import { specParts, specRows } from "../../src/lib/specs.js";

let bad = 0;
const ok = (c, m) => { if (!c) { bad++; console.log("  FAIL " + m); } else console.log("  PASS " + m); };

const otokar = "GVW 19,000 kg; L 6,700 (with winch) x W 2,850 x H 2,650 mm; GC 450 mm; 375-400 hp turbo-diesel; 105 km/h / 700 km; 14.00 R20 run-flat";
ok(specParts(otokar).length === 6 && specParts(otokar)[1] === "L 6,700 (with winch) x W 2,850 x H 2,650 mm", "the Otokar line splits into its six figures");
ok(JSON.stringify(specParts("155 mm")) === '["155 mm"]', "a plain value is one part, unchanged");
ok(specParts("radar (X-band; S-band) and EO; laser").length === 2, "a ';' inside brackets does not split");
ok(specParts("• Weight 12.1 lb; size 10 in")[0] === "Weight 12.1 lb", "a leading bullet is dropped");
ok(specParts("a;b").length === 1, "';' with no space after it is not a separator");
ok(specParts(null).length === 0, "no value, no parts");
const r = specRows({ "Variant-specific weight/performance not published by Otokar; shared platform data (AZ82ED-25)": otokar, Calibre: "7.62x51mm" });
ok(r[0].caption && r[0].caption.startsWith("Variant-specific"), "a long caveat label becomes a caption row");
ok(r[1].label === "GVW" && r[1].value === "19,000 kg", "a figure is labelled by its own leading words");
ok(r[4].label === "" && r[4].value === "375-400 hp turbo-diesel", "a figure with no leading words gets no invented label");
ok(r[r.length - 1].label === "Calibre" && r[r.length - 1].value === "7.62x51mm", "a plain value is one row as stored");
const e = specRows({ Engine: "turbo-charged diesel, 440 hp; automated 12F/2R; permanent 4WD" });
ok(e.length === 3 && e[0].label === "Engine" && e[1].label === "" && e[2].value === "permanent 4WD", "under a real label the parts follow beneath it");
ok(specRows({ Note: "Max speed 110 km/h; range 800 km" })[1].label === "Range", "under Note each figure names itself");
ok(r[2].label === "L × W × H" && r[2].value.startsWith("L 6,700"), "a dimension line is labelled L × W × H and kept whole");
if (bad) { console.log(bad + " failed"); process.exit(1); }
console.log("all pass");
