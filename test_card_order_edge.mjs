/* Edge cases for compareCards (src/lib/overview.js), beyond test_card_order.mjs.
 *
 *     node test_card_order_edge.mjs
 *
 *   - direction (threat > watch) leads everything; a card with no stance, or an unknown dir, sorts last;
 *   - within a direction DATE leads (newest first); an undated card sorts to the bottom;
 *   - the stored sequence number breaks a same-date tie; severity fields are never read.
 */
import { compareCards } from "./src/lib/overview.js";

const data = { details: {} };
const card = (id, over = {}) => ({ id, dir: "threat", ...over });
const order = (list) => list.slice().sort(compareCards(data)).map((c) => c.id).join(",");

let bad = 0;
const ck = (name, want, got) => {
  if (want === got) console.log("  %s ok", name.padEnd(56));
  else { console.log("  %s FAIL\n      want %s\n      got  %s", name.padEnd(56), want, got); bad++; }
};

ck("same-date tie ordered by the stored sequence", "a,b,c",
   order([card("c", { ago: "5 Sep 2026", seq: 3 }), card("a", { ago: "5 Sep 2026", seq: 1 }), card("b", { ago: "5 Sep 2026", seq: 2 })]));

ck("a severity field does not change the order", "n,o",
   order([card("o", { severityRank: 0, ago: "1 Aug 2026", seq: 1 }), card("n", { severityRank: 2, ago: "2 Aug 2026", seq: 2 })]));

ck("newer outranks older whatever the sequence", "new,old",
   order([card("old", { ago: "1 Aug 2026", seq: 1 }), card("new", { ago: "2 Aug 2026", seq: 2 })]));

ck("undated card sorts below a dated card", "dated,undated",
   order([card("undated", { ago: "", seq: 1 }), card("dated", { ago: "1 Jan 2020", seq: 2 })]));

ck("direction leads: threat, then watch", "t,w",
   order([card("w", { dir: "watch", ago: "9 Sep 2026", seq: 1 }),
          card("t", { dir: "threat", ago: "1 Jan 2019", seq: 9 })]));

ck("an unknown dir, or no stance, sorts last of all", "t,w,x,n",
   order([card("x", { dir: "mystery", ago: "9 Sep 2026", seq: 1 }), card("n", { dir: "", ago: "9 Sep 2026", seq: 2 }),
          card("t", { dir: "threat", ago: "1 Jan 2019", seq: 1 }), card("w", { dir: "watch", ago: "1 Jan 2019", seq: 1 })]));

ck("a card with no sequence follows sequenced cards of the same date", "s,u",
   order([card("u", { ago: "5 Sep 2026" }), card("s", { ago: "5 Sep 2026", seq: 7 })]));

ck("the number of sections is not a tie-break", "first,second",
   order([card("first", { ago: "5 Sep 2026", seq: 1, sec: [1] }), card("second", { ago: "5 Sep 2026", seq: 2, sec: [1, 2, 3] })]));

if (bad) { console.log(`\n${bad} failure(s)`); process.exit(1); }
console.log("\nok - direction leads, date leads within a direction, the stored sequence breaks ties");
