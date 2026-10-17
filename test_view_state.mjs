/* A selection is remembered while you stay in the pillar, and forgotten when you leave.
 *
 * The operator's own description: on Competitive, open Competitor, pick BAE, step across
 * to Partnerships -- come back and BAE should still be selected. But go to Market and
 * back to Competitive, and everything should be default again.
 *
 * The first half already worked. The second could not: seven pages persisted their
 * selection to localStorage, which survives the pillar, the tab, the browser and the next
 * reboot -- so a company opened once in September was still the landing selection weeks
 * later, on a dashboard whose entire subject is what changed. The durability was the bug.
 *
 * What is asserted here is the LIFETIME, since that is the only thing that changed:
 * survives a view change, dies on a pillar change, and is not written to any browser
 * store that would outlive the tab.
 */
import { readFileSync, readdirSync } from "node:fs";
import { getItem, setItem, removeItem, clearViewState, viewStateKeys } from "./src/lib/viewState.js";

let fail = 0;
const ck = (name, ok, d) => {
  console.log(`  ${name.padEnd(66)} ${ok ? "PASS" : "FAIL"}${d !== undefined && !ok ? "  " + JSON.stringify(d) : ""}`);
  if (!ok) fail++;
};

/* ---- the store behaves like the Storage the call sites were written against ---- */
clearViewState();
ck("a key nobody set reads null, as getItem does", getItem("kssl_profile_cid") === null);
setItem("kssl_profile_cid", "bae-systems");
ck("what was set comes back", getItem("kssl_profile_cid") === "bae-systems");
ck("values are strings, as Storage returns", (setItem("n", 5), getItem("n") === "5"));
removeItem("kssl_profile_cid");
ck("removeItem clears one key", getItem("kssl_profile_cid") === null);

/* ---- the lifetime: this is the whole point ---- */
clearViewState();   // the coercion probe above left a key behind
setItem("kssl_profile_cid", "bae-systems");
setItem("kssl_part_state", JSON.stringify({ cid: "bae-systems", tie: "t1" }));
setItem("kssl_geo_state", JSON.stringify({ comp: "bae-systems" }));
ck("three pages can hold a selection at once", viewStateKeys().length === 3, viewStateKeys());

/* a view change touches nothing: the store is not keyed on the view and nothing in the
   app clears it on a view change -- that is what makes BAE survive the detour */
ck("stepping to another VIEW keeps every selection",
   getItem("kssl_profile_cid") === "bae-systems" && !!getItem("kssl_part_state"));

clearViewState();
ck("a PILLAR change clears all of them", viewStateKeys().length === 0, viewStateKeys());
ck("...so the next page lands on its default, not on BAE", getItem("kssl_profile_cid") === null);
ck("clearing an already-empty store is not an error", (clearViewState(), viewStateKeys().length === 0));

/* ---- and no page may quietly go back to a durable store ---- */
const PAGES = "./src/pages/competitive";
const offenders = readdirSync(PAGES)
  .filter((f) => f.endsWith(".jsx"))
  .filter((f) => /(^|[^.\w])localStorage\s*\./.test(readFileSync(`${PAGES}/${f}`, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "")));
ck("no competitive page writes a selection to localStorage any more",
   offenders.length === 0, offenders);

/* AppState is the ONE place that empties it. If a second caller appears, the rule stops
   being "a pillar change clears" and becomes "something, somewhere, sometimes clears". */
const appState = readFileSync("./src/state/AppState.jsx", "utf8");
ck("AppState imports the clear", /import \{ clearViewState \}/.test(appState));
ck("...and calls it from setPillar", /if \(prev !== next\) clearViewState\(\);/.test(appState));
ck("...guarded on a real change, so re-clicking the open pillar keeps the selection",
   /prev !== next/.test(appState));

const callers = readdirSync("./src", { recursive: true })
  .filter((f) => typeof f === "string" && /\.(jsx?|mjs)$/.test(f))
  .filter((f) => !f.endsWith("viewState.js"))
  .filter((f) => /clearViewState\s*\(/.test(readFileSync(`./src/${f}`, "utf8")));
ck("exactly one caller clears the store", callers.length === 1, callers);

console.log(fail ? `\n${fail} FAILED` : "\nall passed");
process.exit(fail ? 1 : 0);
