/* The client's badge must lose the ECHO without losing the ACTIVITY.
 *
 * The client's footprint rows keep the activity word they were stored with ("Local production"); the loader
 * no longer overwrites it with a client code. The badge reads `<client> Present` and then those words, and a word
 * that only restates the client's name ("KSSL present") is dropped:
 *
 *     wrong (echo)        KSSL Present . KSSL present
 *     right               KSSL Present . Local production
 *
 *     node test_geo_client_activity.mjs
 */
import { ownActivityLabels, presenceBadge } from "./src/lib/geoBadge.js";
import { wireDataset } from "./src/lib/dataset.js";
import { readFileSync } from "node:fs";

let fails = 0;
const ck = (name, ok, detail) => {
  console.log(`  ${name.padEnd(68)} ${ok ? "ok" : "FAIL"}${!ok && detail ? "  " + detail : ""}`);
  if (!ok) fails++;
};

// the activity dictionary: the stored words, plus a label that echoes the client
const ACT = { "Local production": "Local production", Export: "Export", self: "KSSL present" };

const india = [{ c: "Local production", country: "India", src: "https://example.com/x" }];
const labels = ownActivityLabels(india, ACT, "KSSL");
ck("the stored activity survives", labels.length === 1 && labels[0] === "Local production", JSON.stringify(labels));
ck("a label that restates the client name is dropped", ownActivityLabels([{ c: "self" }], ACT, "KSSL").length === 0);
ck("a row with no activity says nothing", ownActivityLabels([{ country: "India" }], ACT, "KSSL").length === 0);

const rival = ownActivityLabels([{ c: "Local production" }, { c: "Export" }], ACT, "KSSL");
ck("a non-client row keeps every one of its activities", rival.length === 2, JSON.stringify(rival));

const badge = presenceBadge({ clientLabel: "KSSL", rows: india, rivalCount: 0, actLabel: ACT });
ck("the rendered badge says the client once and the activity", badge.text === "KSSL Present · Local production", badge.text);

// the loader leaves the stored activity on the client's rows (no client code is stamped over it)
const fx = JSON.parse(readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url)));
const d = wireDataset(JSON.parse(JSON.stringify(fx)));
const own = d.geoData[d.client.id];
let changed = 0;
let n = 0;
Object.entries(own).forEach(([ct, rows]) => rows.forEach((r, i) => {
  n += 1;
  if (r.c !== fx.geoData[d.client.id][ct][i].c || "c0" in r) changed += 1;
}));
ck("the client's footprint rows keep their stored activity and gain no c0", n > 0 && changed === 0, `${changed} of ${n}`);

console.log(fails ? `\n${fails} FAILED` : "\nok - the echo is gone and the stored activity survives");
process.exit(fails ? 1 : 0);
