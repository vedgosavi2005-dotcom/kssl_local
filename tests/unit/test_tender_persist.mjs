/* The render-shape contracts the recent rework introduced, pinned on the source so a
 * silent regression is caught: what Tenders persists, what DetailPanel shows and hides,
 * and that the card face still carries its rank number.
 *
 *     node tests/unit/test_tender_persist.mjs
 *
 * These are structural assertions on the JSX (the same technique as test_tender_detail
 * and test_signal_text_intact): the behaviours below are not pure functions, so the
 * contract lives in the component source and is verified there. Line references are the
 * source of record; regexes are tolerant of whitespace, not of the property set.
 */
import { readFileSync } from "node:fs";

let bad = 0;
const ck = (name, cond) => {
  if (cond) console.log("  %s ok", name.padEnd(64));
  else { console.log("  %s FAIL", name.padEnd(64)); bad++; }
};

const tenders = readFileSync("../../src/pages/market/Tenders.jsx", "utf8").replace(/\r/g, "");
const panel = readFileSync("../../src/components/detailPanel/DetailPanel.jsx", "utf8").replace(/\r/g, "");
const card = readFileSync("../../src/components/signalCard/SignalCard.jsx", "utf8").replace(/\r/g, "");

// ---- 1. Tenders: `sel` inits null and is NOT read from localStorage --------------
ck("sel initialises to null (not persisted, collapses on return)",
   /const \[sel, setSel\] = useState\(null\)/.test(tenders));
ck("sel is NOT restored from the saved-tender blob",
   !/useState\(\s*savedTender\.sel/.test(tenders));

// ---- 2. Tenders: only productType/country/cat are persisted ----------------------
const persist = tenders.match(/localStorage\.setItem\("kssl_tender_state",\s*JSON\.stringify\(([^)]*)\)/);
ck("the tender state is persisted with JSON.stringify", !!persist);
const persistedShape = persist ? persist[1].replace(/\s/g, "") : "";
ck("persisted shape is exactly {productType,country,cat}",
   persistedShape === "{productType,country,cat}");
ck("the persisted blob does NOT include sel", !/\bsel\b/.test(persistedShape));

// ---- 3. Tenders: list rows hide not-on-record params -----------------------------
ck("list rows filter out NOT_ON_RECORD values",
   /\.filter\(\(\[,\s*v\]\) => v !== NOT_ON_RECORD\)/.test(tenders));

// ---- 4. DetailPanel: the rank eyebrow was REMOVED --------------------------------
// {detail.rank} must not be rendered anywhere.
ck("the {detail.rank} eyebrow is gone", !/\{detail\.rank\}/.test(panel));
// A comment explicitly records the removal.
ck("signal numbering is documented as kept-in-record-not-shown",
   /numbering kept in the record, not shown/.test(panel));

// ---- 5. DetailPanel: 'In the publisher's words' block REMOVED, 'Key points' added -
ck("no reader-facing 'In the publisher's words' heading",
   !/>[^<]*In the publisher's words/.test(panel));
ck("Key points bullets are rendered from articleBullets",
   /articleBullets\(detail\.lens\)/.test(panel) && /Key points/.test(panel));

// ---- 6. DetailPanel: tender glance hides value === NOT_ON_RECORD ------------------
ck("tender glance filters rows whose value is NOT_ON_RECORD",
   /tenderFactRows\(tenderRec\)\.filter\(\(r\) => r\[1\] !== NOT_ON_RECORD\)/.test(panel));

// ---- 7. SignalCard: the card-face rank number is PRESENT -------------------------
// (test_signal_text_intact pins uiTitle/ksslImpact but not the rank; pin it here.)
ck("the card face still shows the rank number (card.rank)",
   /<span className="rank">\{card\.rank\}<\/span>/.test(card));
ck("title prefers uiTitle then falls back to title",
   /__html: card\.uiTitle \|\| card\.title/.test(card));
ck("descriptor prefers ksslImpact then falls back to sowhat",
   /__html: card\.ksslImpact \|\| card\.sowhat/.test(card));

if (bad) { console.log(`\n${bad} failure(s)`); process.exit(1); }
console.log("\nok - sel not persisted, rank eyebrow gone, key-points bullets in, not-on-record hidden, card rank present");
