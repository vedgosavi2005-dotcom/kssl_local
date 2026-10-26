/* Display helpers behind the functional-test fixes G15-G19 (2026-10-25): the Projects rows and panel, the Top
   opportunity cells, the matched-product badge and the multi-lot requirement rows. Pure functions, run under node. */
import assert from "node:assert/strict";
import { projectTitle, projectStage, sentenceCase, plainDates } from "../../src/lib/projects.js";
import { whereItStands, revenueShort } from "../../src/lib/tenderIntel.js";
import { matchFitWord, matchAssessed, matchLine, reqBlocks, tenderFactRows, tenderFitBar, NO_DATE_PUBLISHED, NOT_ASSESSED } from "../../src/lib/tenderRow.js";

const STEPS = ["Concept", "Trials", "Contract", "Production", "Deliveries", "In service"];

// G15: a project with no name gets its best available headline, never an empty title
assert.equal(projectTitle({ name: "Project Zorawar" }), "Project Zorawar");
assert.equal(projectTitle({ name: null, overview: ["Vietnam signed a contract with India for BrahMos missiles. More text."] }),
  "Vietnam signed a contract with India for BrahMos missiles");
assert.equal(projectTitle({ name: "", overview: [], kind: "production contract", customer: "Indian Army" }), "Production contract for Indian Army");
assert.equal(projectTitle({ company: "SAAB" }), "SAAB project");
// G15: no stage -> the step the stored rank points at; neither -> "" (the row prints no label and no colon)
assert.equal(projectStage({ stage: "Contract" }, STEPS), "Contract");
assert.equal(projectStage({ stage: null, stageRank: 6 }, STEPS), "In service");
assert.equal(projectStage({ stage: null, stageRank: null }, STEPS), "");
// G15: Kind sentence-cased, ISO dates in prose in the house format
assert.equal(sentenceCase("initial supply contract, 21 vehicles"), "Initial supply contract, 21 vehicles");
assert.equal(sentenceCase("Buy (Indian-IDDM) contract"), "Buy (Indian-IDDM) contract");
assert.equal(plainDates("L3Harris started delivering on 2026-10-13."), "L3Harris started delivering on 13 Oct 2026.");

// G16: a stage code reads as its ui.code_label words; the rest is the detail, with house dates
const data = { database: { ui: { code_label: [{ table_name: "market_opportunity", column_name: "stage", code: "approved_funded", label: "Approved and funded" }] } } };
assert.deepEqual(whereItStands("approved_funded / FMS approved / US approved on 2026-10-02", data),
  { label: "Approved and funded", detail: "FMS approved · US approved on 02 Oct 2026" });
assert.equal(whereItStands("need_stated / Forthcoming program", data).label, "Need stated");   // no label row: the code in words
assert.deepEqual(whereItStands("Market survey; RFI expected", data), { label: "", detail: "Market survey; RFI expected" });
// G16: a full stated amount in short form; a short or ranged text as stored
assert.equal(revenueShort("Stated tender value CZK 40,495,867.77"), "CZK 40.5 m");
assert.equal(revenueShort("USD 60-95 M"), "USD 60-95 M");

// G18: 0% or only "no spec on file" lines -> Not assessed, never a percentage
const noSpec = { n: "Spares", fit: "partial", pct: null, lines: [["Item", "no spec on file | required: TORSION BAR"]] };
assert.equal(matchFitWord({ ...noSpec, pct: "0%" }).word, NOT_ASSESSED);
assert.equal(matchFitWord(noSpec).word, NOT_ASSESSED);
assert.equal(matchFitWord({ n: "X", fit: "partial", pct: "72%", lines: [] }).word, "72% fit");
assert.equal(matchFitWord({ n: "X", fit: "partial", pct: null, lines: [["Calibre", "matches 155 mm"]] }).word, "partial fit");
assert.equal(matchAssessed({ n: "X", pct: null, lines: [] }), true);
assert.deepEqual(matchLine("no spec on file | required: LV1 R72 COVER"), { required: "LV1 R72 COVER", noSpec: true });
assert.deepEqual(matchLine("meets the range"), { text: "meets the range" });
// the card's fit bar does not draw a 0% bar for an unassessed match: the tender's stored grade stands
assert.equal(tenderFitBar({ fit: "partial", matches: [{ ...noSpec, pct: "0%" }] }).word, "partial");

// G19: lots share what is the same once, keep what differs per lot; a single-lot notice is unchanged
const req = [
  ["description", "Minimum order of 32400 rounds"], ["use_case", "Sea target shooting"], ["quantity", "32400 rounds"], ["source_text", "Mindest"],
  ["description", "Maximum order of 150480 rounds"], ["use_case", "Sea target shooting"], ["quantity", "150480 rounds"], ["source_text", "Maximal"],
  ["description", "Option to extend once by 12 months"],
  ["published_date", "2026-09-28"], ["closing_date", "2026-10-29"],
];
const rb = reqBlocks(req);
assert.deepEqual(rb.shared, [["use_case", "Sea target shooting"]]);
assert.deepEqual(rb.blocks.map((b) => [b.description, b.rows]), [
  ["Minimum order of 32400 rounds", [["quantity", "32400 rounds"]]],
  ["Maximum order of 150480 rounds", [["quantity", "150480 rounds"]]],
  ["Option to extend once by 12 months", []],
]);
assert.equal(rb.blocks[0].source, "Mindest");
assert.deepEqual(rb.tail.map((r) => r[0]), ["published_date", "closing_date"]);
const one = reqBlocks([["description", "Body armour"], ["quantity", "40"], ["closing_date", "2026-11-01"]]);
assert.deepEqual([one.blocks.length, one.head.length, one.tail.length], [0, 2, 1]);
// G19: a missing published date says so instead of vanishing from the drawer
assert.equal(tenderFactRows({ title: "VR7", closingDate: "2030-10-14" }).find((r) => r[0] === "Published")[1], NO_DATE_PUBLISHED);

console.log("ok - project, top-opportunity, match and lot display helpers (functional test G15-G19)");
