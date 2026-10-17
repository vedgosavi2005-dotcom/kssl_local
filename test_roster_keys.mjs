/* The client roster and a rival's partner rows do not share a key space.
 *
 *     node test_roster_keys.mjs
 *
 * KSSL_PARTNERS is reference data: `plp_01`..`plp_03`, cid null. The partner rows on a
 * rival carry a name slug (`paramount-group`) and no cid at all. Both name the same
 * company, and every lookup that compared one to the other missed every time.
 *
 * Two things broke on that, on the committed snapshot:
 *
 *   1. dataset.js required `p.cid` before attaching `koel`, so the CLIENT relation --
 *      the whole point of the red line, "what does KSSL use this partner for" -- never
 *      attached to a single flagged row;
 *   2. partners.js selfCheck() looked the roster up the same way and reported every
 *      genuinely-shared partner as "flagged shared but is absent from roster". That is
 *      what took CI's layout gate down and, being on staging, took every PR opened
 *      against it down too.
 *
 * The overlap itself was never wrong. Paramount Group really is both KSSL's partner and
 * a rival's; only the key used to confirm it was.
 *
 * So this pins the index, and pins that the join and its guard use the SAME one -- a
 * guard that asks a different question from the code it guards is how this stayed
 * invisible.
 */
import { readFileSync } from "node:fs";
import { rosterIndex, rosterLookup, rosterKey } from "./src/lib/partners.js";

let bad = 0;
const ck = (name, want, got) => {
  if (JSON.stringify(want) === JSON.stringify(got)) console.log("  %s ok", name.padEnd(62));
  else { console.log("  %s FAIL (want %j, got %j)", name.padEnd(62), want, got); bad++; }
};

// ---- the index knows a company by every key it is written under ------------------
const roster = [
  { id: "plp_01", cid: null, label: "AM General" },
  { id: "plp_02", cid: null, label: "Paramount Group" },
  { id: "plp_03", cid: null, label: "Rafael Advanced Defense Systems" },
];
const ix = rosterIndex(roster);

ck("found by its reference id", "Paramount Group", (ix["plp_02"] || {}).label);
ck("found by the name slug a rival row uses", "Paramount Group",
   (ix["paramount-group"] || {}).label);
ck("...and the long one too", "Rafael Advanced Defense Systems",
   (ix["rafael-advanced-defense-systems"] || {}).label);

// ---- a rival's row resolves, with no cid and a slug id ---------------------------
const row = { id: "paramount-group", label: "Paramount Group", shared: true };
ck("a flagged row with no cid resolves to the roster entry", "plp_02",
   (rosterLookup(ix, row) || {}).id);
ck("an unrelated company does not", null,
   rosterLookup(ix, { id: "acme-corp", label: "Acme Corp" }));

// A cid still wins when one exists -- this must not become slug-only matching.
const ixc = rosterIndex([{ id: "plp_09", cid: "c-123", label: "Someone" }]);
ck("cid is still a key", "plp_09", (ixc["c-123"] || {}).id);

// ---- the normaliser is the boring one, and stable --------------------------------
ck("slug: punctuation and case collapse", "rafael-advanced-defense-systems",
   rosterKey("Rafael  Advanced/Defense Systems"));
ck("slug: no leading or trailing separators", "bae-systems", rosterKey(" BAE Systems. "));
ck("slug: empty in, empty out", "", rosterKey(null));

// ---- the join and the guard must ask the SAME question ---------------------------
// Asserted on the source, because the failure mode is precisely the two drifting apart.
const dsrc = readFileSync("./src/lib/dataset.js", "utf8");
const psrc = readFileSync("./src/lib/partners.js", "utf8");
ck("dataset.js attaches koel through the shared index", true,
   /rosterIndex\(d\.KSSL_PARTNERS\)/.test(dsrc) && /rosterLookup\(roster, p\)/.test(dsrc));
ck("...and no longer requires p.cid to attach it", false, /p\.shared && p\.cid && roster\[p\.cid\]/.test(dsrc));
ck("selfCheck uses the same index, not its own", true,
   /const roster = rosterIndex\(KSSL_PARTNERS\)/.test(psrc));
ck("...and the same lookup", true, /rosterLookup\(roster, p\)/.test(psrc));

// ---- the fixture snapshot: every flagged partner now resolves -----------------------
const d = JSON.parse(readFileSync("./fixtures/kssl_dataset.json", "utf8"));
(await import("./src/lib/client.js")).setClient(d.client);
const wired = (await import("./src/lib/dataset.js")).wireDataset(d);
const live = rosterIndex(wired.KSSL_PARTNERS);
const missing = [];
let flagged = 0;
for (const c of Object.values(wired.competitors || {})) {
  if (c.isBf) continue;
  for (const p of c.partners || []) {
    if (!(p.koel || p.shared)) continue;
    flagged += 1;
    if (!rosterLookup(live, p)) missing.push(p.label);
  }
}
ck("on the fixture, every flagged partner resolves", [], missing);
ck("...and there were flagged partners to resolve (the check can still fail)", true, flagged > 0);

console.log(bad ? `\n${bad} failure(s)` : "\nok - one roster index, used by the join and by the guard that checks it");
process.exit(bad ? 1 : 0);
