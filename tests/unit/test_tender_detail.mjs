/* A tender card's detail panel must not be blank.
 *
 *     node tests/unit/test_tender_detail.mjs
 *
 * Reported: the Market pillar's Overview tab shows "nothing, not even what we had
 * before". Measured on the live payload: that tab opens on "Live Opportunities", which
 * is 126 tender cards, and
 *
 *   - 0 of 126 carry a `summary`. Correctly so: a tender has no document body, which is
 *     why serving_fill's backfill selects `id LIKE 'pl\_%'` and never sees them;
 *   - 22 of 126 carry `what` as an EMPTY STRING, so `detail.summary || detail.what` is
 *     falsy and the whole prose block is skipped.
 *
 * The panel had a tender branch all along, gated on `detail.kind === "tender"` -- and
 * `kind` is NULL on every served row in every lane, so that branch had never once been
 * true. The writer sets the prefix on the id, not `kind`.
 *
 * So this pins two things: a tender is recognised by what the writer actually sets, and
 * a recognised tender is glanced through resolveTenderRow -- the same nine parameters
 * the Tender Pipeline row prints, from the same function, so the two surfaces cannot
 * drift. Unresolved parameters stay: "Value -- not on record" is a fact about the
 * tender, and dropping the row would present a partial record as a complete one.
 */
import { readFileSync } from "node:fs";
import { TENDER_PARAMS, NOT_ON_RECORD, tenderFactRows } from "../../src/lib/tenderRow.js";

let bad = 0;
const ck = (name, want, got) => {
  if (JSON.stringify(want) === JSON.stringify(got)) console.log("  %s ok", name.padEnd(64));
  else { console.log("  %s FAIL (want %j, got %j)", name.padEnd(64), want, got); bad++; }
};

const src = readFileSync("../../src/components/detailPanel/DetailPanel.jsx", "utf8");

// ---- 1. the panel recognises a tender by its id, not by `kind` -------------------
ck("a tender is detected from the id prefix, not detail.kind alone", true,
   /\/\^tender-\/\.test\(/.test(src));
ck("...and kind is still honoured if it is ever populated", true,
   /detail\.kind === "tender" \|\|/.test(src));
ck("the tender record is looked up on the dataset", true,
   /data\.tenders \|\| \[\]/.test(src));

// ---- 2. a recognised tender is glanced through the shared resolver ---------------
ck("the glance comes from tenderFactRows, not hand-built rows", true,
   /tenderRec[\s\S]{0,160}\?\s*tenderFactRows\(tenderRec\)/.test(src.replace(/\r/g, "")));
ck("...and the panel filters out unresolved (not-on-record) rows", true,
   /tenderFactRows\(tenderRec\)\.filter\(\(r\) => r\[1\] !== NOT_ON_RECORD\)/.test(src));
// A tender takes tenderFactRows; only the final signal-card branch (after the
// per-pillar glance branch) applies DROPPED_FACTS to detail.facts.
ck("...and the DROPPED_FACTS filter is NOT applied to a tender", true,
   /tenderRec[\s\S]{0,120}tenderFactRows[\s\S]{0,500}: \(detail\.facts[\s\S]{0,120}DROPPED_FACTS/.test(src));

// ---- 3. the resolver itself still yields the documented eight, unfiltered --------
const empty = tenderFactRows({});
ck("an empty tender still yields all nine rows", TENDER_PARAMS.length, empty.length);
ck("...labelled in the documented order", TENDER_PARAMS.map((p) => p.label),
   empty.map((r) => r[0]));
/* Eight of the nine, not all nine: RESOLVE.source returns `false` rather than null on
   an empty record, so its row prints "false" and reads as resolved. That is pre-existing
   and out of scope here -- pinned as it is so a change to it is deliberate, not silent. */
ck("...each unresolved one printed, not hidden",
   TENDER_PARAMS.slice(0, 8).map(() => NOT_ON_RECORD), empty.slice(0, 8).map((r) => r[1]));
ck("...and marked unresolved",
   TENDER_PARAMS.slice(0, 8).map(() => false), empty.slice(0, 8).map((r) => r[2]));
ck("Source on an empty record: pre-existing `false`, pinned not endorsed",
   ["Source", "false", true], empty[8]);

// A real record resolves what it carries and still prints what it does not.
const rec = { id: "x", title: "Ammunition", issuer: "PSPC", country: "Canada" };
const rows = tenderFactRows(rec);
ck("a partial record still yields nine rows", 9, rows.length);
ck("...the carried values resolve", ["PSPC", "Canada"],
   [rows.find((r) => r[0] === "Buyer")[1], rows.find((r) => r[0] === "Country")[1]]);
ck("...and the missing ones say so rather than vanishing", NOT_ON_RECORD,
   rows.find((r) => r[0] === "Value")[1]);

// ---- 4. the blank case that was reported ----------------------------------------
// summary null AND what empty -- the prose block is skipped, so the glance is all the
// reader gets. It must not be empty.
const blank = tenderFactRows({ id: "y" });
ck("a tender with no summary and an empty `what` still has a glance to show", true,
   blank.length > 0 && blank.every((r) => typeof r[1] === "string" && r[1].length > 0));

console.log(bad ? `\n${bad} failure(s)` : "\nok - a tender is recognised by its id and glanced through the shared nine");
process.exit(bad ? 1 : 0);
