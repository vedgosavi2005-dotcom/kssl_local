/* "Direct Partner" was the else branch of a two-state badge, and the only branch that
 * could run.
 *
 * The badge answers one question -- is this rival's partner also KSSL's? -- and had
 * two answers for it: red "Overlapping Partner" if shared, green "Direct Partner"
 * otherwise. The overlap join (mark_shared.py) was wired into no pass and its roster
 * query filtered on origin='pipeline', which returns none of KSSL's 11 reference-only
 * roster rows. So `shared` was never set, and every partner of every competitor on the
 * tab wore the green badge -- including Rafael, which is KSSL's own KRAS JV partner
 * AND Mahindra Defence's, and is the single most valuable line on the page.
 *
 *   node frontend/test_overlap_badge.mjs        (no build, no browser, no data)
 */
import { overlapState, overlapBadge, tieKind, tieKindShort } from "./src/lib/partners.js";
import { buildCategories } from "./src/lib/partnerCategories.js";

let fail = 0;
const check = (name, got, want) => {
  const ok = typeof want === "function" ? want(got) : got === want || String(got).includes(want);
  console.log(`  ${ok ? "ok  " : "FAIL"} ${name}${ok ? "" : `\n    got ${JSON.stringify(got)}`}`);
  if (!ok) fail++;
};

// --- the three states are actually three -------------------------------------
check("a tie the client also holds is shared", overlapState({ koel: { rel: "jv" } }), "shared");
check("  `shared` alone is enough (a rival partnering the client direct)",
      overlapState({ shared: true, clientTie: true }), "shared");
check("  and an overlap on any underlying row counts",
      overlapState({ rows: [{ cid: "x" }, { koel: {} }] }), "shared");
check("a keyed tie with no overlap is direct", overlapState({ cid: "anduril" }), "direct");
check("  keyed on an underlying row counts too", overlapState({ rows: [{ cid: "anduril" }] }), "direct");

// THE CASE THIS FILE EXISTS FOR. No cid means mark_shared never reached this tie.
// Absence of evidence is not evidence of absence, and the badge must not say it is.
check("an unkeyed tie is UNCHECKED, not direct", overlapState({ label: "Anduril Industries" }), "unchecked");
check("  a bare object is unchecked", overlapState({}), "unchecked");
check("  and nothing at all does not throw", overlapState(null), "unchecked");
check("  an empty rows array is not a check having run",
      overlapState({ label: "Ultra Electronics", rows: [] }), "unchecked");

// --- what each state renders --------------------------------------------------
check("shared renders the red badge", overlapBadge({ label: "Rafael", koel: {} }, "KSSL"), "Overlapping Partner");
check("  and names the client in the tooltip",
      overlapBadge({ label: "Rafael", koel: {} }, "KSSL"), "also on KSSL's own partner roster");
// A BADGE ON EVERY CARD IS NOT A BADGE. Eight of 42 staging ties overlap; the other
// 34 wore a green "Direct Partner" in the card's most prominent slot, which is how the
// relationship type ended up with nowhere to print. The norm is now the absence of one.
check("the normal case prints no badge at all",
      overlapBadge({ label: "Anduril", cid: "anduril" }, "KSSL"), (h) => h === "");
check("unchecked does not claim a direct tie",
      overlapBadge({ label: "Anduril" }, "KSSL"), (h) => !h.includes("Direct Partner"));
check("  it prints no badge -- unchecked is the norm now (cid join dead), not an exception to flag",
      overlapBadge({ label: "Anduril" }, "KSSL"), (h) => h === "");
check("  and is neutral, not green -- green is a claim",
      overlapBadge({ label: "Anduril" }, "KSSL"), (h) => !h.includes("#16a34a"));

// only a real overlap renders a badge now; the unchecked norm renders nothing
check("the unchecked norm carries no badge at all", overlapBadge({ label: "A" }, "KSSL"), (h) => h === "");
check("  shared carries its own class", overlapBadge({ label: "A", shared: true }, "KSSL"), "ov-badge ov-shared");

// a quote in a model-written label must not break out of title="..."
check("a quoted label is attribute-escaped",
      overlapBadge({ label: 'Rheinmetall "Skyranger" GmbH', koel: {} }, "KSSL"),
      (h) => h.includes("&quot;Skyranger&quot;") && h.split('title="')[1].split('"')[0].length > 20);

// a missing client name must not print "undefined's roster" at the user (checked on the
// shared badge, the one that now renders a tooltip; unchecked no longer prints anything)
check("no client name degrades to prose, not undefined",
      overlapBadge({ label: "A", koel: {} }, ""), (h) => h.includes("the partner roster") && !h.includes("undefined"));

// THE REGRESSION: the exact staging shape. 0 of 42 ties carried cid, so under the old
// two-state badge all 42 -- Rafael included -- rendered as confirmed direct partners.
const staging = [
  { label: "Rafael Advanced Defense Systems" }, { label: "Anduril Industries" },
  { label: "BAE Systems" }, { label: "Bharat Electronics Ltd. (BEL)" },
  { label: "Telephonics Corporation" }, { label: "Ultra Electronics" },
  { label: "Airbus Helicopters" },
];
check("Mahindra's 7 unmarked ties claim nothing",
      staging.every((p) => overlapState(p) === "unchecked"), true);
check("  and not one of them renders as Direct Partner",
      staging.some((p) => overlapBadge(p, "KSSL").includes("Direct Partner")), false);

// --- what the tie IS, not what kind of company the partner is -----------------
// Every card and every node read p.kind first, and kind is "Foreign OEM" / "Domestic"
// -- printed beside the country that already says it. A 51/49 JV, an MoU and a supply
// agreement all rendered identically, and the tab's whole subject appeared nowhere.
const tele = { label: "Telephonics Corporation", kind: "Foreign OEM", rel: "jv",
               ptype: "Joint Venture (51% Mahindra, 49% Telephonics)", country: "United States" };
const cats = buildCategories({ database: { ui: { partner_category: [
  { category_key: "joint-venture", group_key: "g", group_label: "G", category_label: "Joint venture", short_label: "JV", definition: "", overlap_kind: "", display_order: 1 },
  { category_key: "mou-strategic", group_key: "g", group_label: "G", category_label: "MoU / strategic", short_label: "MoU", definition: "", overlap_kind: "", display_order: 2 },
] } } });
check("the card shows the relationship, not the company category",
      tieKind(tele, cats), "Joint Venture (51% Mahindra, 49% Telephonics)");
check("  and never falls back to kind while ptype exists",
      tieKind(tele, cats).includes("Foreign OEM"), false);
check("a graph node gets the legend's short label, not truncated free text",
      tieKindShort({ ...tele, rel: "joint-venture" }, 22, cats), "JV");
check("  a long ptype with no category is trimmed, not overflowed",
      tieKindShort({ ptype: "Licensed Component Manufacturing & Technical Data Exchange" }, 22, cats),
      (t) => t.length <= 22 && t.endsWith("…"));
check("a category's short label comes from the legend", tieKindShort({ rel: "mou-strategic" }, 22, cats), "MoU");
check("an unknown rel with no ptype shows the dash, not an invented word", tieKind({ rel: "zzz" }, cats), "—");
check("kind is the last resort, not the first", tieKind({ kind: "Foreign OEM" }, cats), "Foreign OEM");
check("nothing at all does not throw", tieKind(null, cats), "—");
check("without a legend the tie's own words still show", tieKind({ ptype: "Supplier" }), "Supplier");

console.log(fail ? `\n${fail} failed` : "\nok - the badge marks the exception, the chip names the tie");
process.exit(fail ? 1 : 0);
