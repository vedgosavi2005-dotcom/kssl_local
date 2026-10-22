/* A packed spec value shows one figure per line (owner 22 Oct: "tech specs written in a single line").
 *
 *     node tests/unit/test_spec_parts.mjs
 */
import { specParts } from "../../src/lib/specs.js";

let bad = 0;
const ok = (c, m) => { if (!c) { bad++; console.log("  FAIL " + m); } else console.log("  PASS " + m); };

const otokar = "GVW 19,000 kg; L 6,700 (with winch) x W 2,850 x H 2,650 mm; GC 450 mm; 375-400 hp turbo-diesel; 105 km/h / 700 km; 14.00 R20 run-flat";
ok(specParts(otokar).length === 6 && specParts(otokar)[1] === "L 6,700 (with winch) x W 2,850 x H 2,650 mm", "the Otokar line splits into its six figures");
ok(JSON.stringify(specParts("155 mm")) === '["155 mm"]', "a plain value is one part, unchanged");
ok(specParts("radar (X-band; S-band) and EO; laser").length === 2, "a ';' inside brackets does not split");
ok(specParts("• Weight 12.1 lb; size 10 in")[0] === "Weight 12.1 lb", "a leading bullet is dropped");
ok(specParts("a;b").length === 1, "';' with no space after it is not a separator");
ok(specParts(null).length === 0, "no value, no parts");
if (bad) { console.log(bad + " failed"); process.exit(1); }
console.log("all pass");
