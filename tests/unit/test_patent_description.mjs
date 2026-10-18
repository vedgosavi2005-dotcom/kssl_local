/* Every patent says what it is about -- and says WHICH thing it is telling you.
 *
 * `abstract` is null on all 1,157 served rows: the WIPO harvest stores the bibliographic
 * record and never fetches abstracts, so `.pat-abs` rendered an empty div on every card
 * and the reader had a title and nothing else. The IPC classification IS on every row, so
 * the card prints the field the office placed the filing in.
 *
 * The risk is not coverage, it is CATEGORY: a classification is not an abstract, and a
 * reader must not be able to mistake one for the other. So what is asserted here is the
 * labelling as much as the lookup -- and that a real abstract, when one arrives, wins.
 */
import fs from "node:fs";
import { patRecCard, normCountry } from "../../src/lib/patents.js";

let fail = 0;
const ck = (name, ok, d) => {
  console.log(`  ${name.padEnd(64)} ${ok ? "PASS" : "FAIL"}${d !== undefined && !ok ? "  " + JSON.stringify(d) : ""}`);
  if (!ok) fail++;
};

/* ---- the constant is gone: the words are the stored classification_text ---- */
ck("the IPC subclass table (ipc.js) is deleted", !fs.existsSync("../../src/lib/ipc.js"));
ck("patents.js carries no IPC subclass meaning", !/armour, armoured vehicles|explosive charges|jet-propulsion/i.test(fs.readFileSync("../../src/lib/patents.js", "utf8")));
const fx = JSON.parse(fs.readFileSync("../../fixtures/kssl_dataset.json", "utf8"));
const stored = Object.values(fx.PATENTS.byArea).flat().find((r) => r.ipcText && (r.ipc || []).length);
ck("the fixture stores a classification text with its code", !!stored);

/* ---- the card: is it labelled as what it is? ---- */
const row = (o) => ({ id: "KR1020170079686", title: "유도 무기용 탐색 장치 및 이의 동작 방법",
                      assignee: "Test Assignee", status: "filed", filed: "2017-07-10",
                      jurisdiction: "KR", ipc: ["F42B 15/01"], ipcText: "Explosive charges and projectiles (stored)", abstract: null, ...o });
const meta = { relevDiscriminates: false };

const html = patRecCard(row(), true, meta);
ck("a card with no abstract prints the classification", /Classified under F42B 15\/01/.test(html), html.slice(0, 200));
ck("...with the stored words", /Explosive charges and projectiles \(stored\)/.test(html));
ck("...and NEVER calls it an abstract", !/>Abstract</i.test(html));
ck("...and says in its tooltip that no abstract was captured", /no abstract was captured/.test(html));
ck("...and marks the line as a classification for CSS to set apart", /pat-abs-ipc/.test(html));

const withAbs = patRecCard(row({ abstract: "A seeker for a guided weapon." }), true, meta);
ck("A REAL ABSTRACT WINS -- the classification steps aside", /A seeker for a guided weapon/.test(withAbs));
ck("...and the classification line is not also drawn", !/Classified under/.test(withAbs), withAbs.slice(0, 300));

const noText = patRecCard(row({ ipcText: "" }), true, meta);
ck("a code with no stored words draws no classification line, nothing is looked up", !/Classified under/.test(noText));
const noIpc = patRecCard(row({ ipc: [] }), true, meta);
ck("no abstract and no code draws nothing at all, not an empty label",
   !/Classified under/.test(noIpc) && !/pat-abs/.test(noIpc));

/* ---- the part this does NOT do ---- */
ck("the country normaliser lives with the flag lookups", normCountry("USA") === "US" && normCountry("Zedland") === "Zedland");
ck("the Korean title is still the Korean title: this is not a translation",
   /유도 무기용/.test(html));

console.log(fail ? `\n${fail} FAILED` : "\nall passed");
process.exit(fail ? 1 : 0);
