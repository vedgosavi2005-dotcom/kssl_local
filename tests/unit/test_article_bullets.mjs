/* articleBullets: signal_detail.lens propositions -> 3-4 clean "Key points" bullets.
 *
 *     node tests/unit/test_article_bullets.mjs
 *
 * Each lens row is `<English lead-in phrase> - <i>"the article's own sentence"</i>`
 * (em-dash separator). articleBullets keeps the lead-in only: it splits on the FIRST
 * em-dash, strips HTML, capitalizes the first letter, and drops the quoted (often
 * foreign) half. It must survive the non-uniform lens shapes that once blanked the app:
 * a bare string in place of the array, and bare-string rows inside it.
 *
 * The em-dash is written as an escape so this file stays ASCII.
 */
import { articleBullets } from "../../src/lib/detail.js";

const DASH = String.fromCharCode(0x2014); // em-dash U+2014, the lens phrase/quote separator

let bad = 0;
const ck = (name, want, got) => {
  const w = JSON.stringify(want), g = JSON.stringify(got);
  if (w === g) console.log("  %s ok", name.padEnd(52));
  else { console.log("  %s FAIL (want %s, got %s)", name.padEnd(52), w, g); bad++; }
};

const row = (phrase, quote) => ["STATEMENT", `${phrase} ${DASH} <i>&ldquo;${quote}&rdquo;</i>`];

// ---- 1. cap at 4: six propositions in, at most four bullets out -------------------
const six = [
  row("Leonardo signed with Brazil", "firmou contrato"),
  row("Rheinmetall opened a plant", "eroeffnete ein Werk"),
  row("Saab delivered radars", "levererade radar"),
  row("BAE won a frigate order", "won the order"),
  row("Thales upgraded avionics", "a mis a niveau"),
  row("KNDS merged two lines", "a fusionne"),
];
ck("caps the list at 4 bullets", 4, articleBullets(six).length);
ck("cap honours a custom cap arg", 2, articleBullets(six, 2).length);

// ---- 2. capitalization of the first letter ---------------------------------------
ck("lead-in first letter is capitalized",
   ["Leonardo signed with Brazil"], articleBullets([row("leonardo signed with Brazil", "x")]));

// ---- 3. HTML tags are stripped from the lead-in ----------------------------------
ck("HTML tags stripped from the lead-in",
   ["Leonardo signed a deal"],
   articleBullets([["STATEMENT", `<b>Leonardo</b> signed a <i>deal</i> ${DASH} <i>"quote"</i>`]]));

// ---- 4. the quoted (foreign) half is dropped -------------------------------------
const b = articleBullets([row("Leonardo signed with Esercito Brasiliano", "sette veicoli 8x8 Centauro II")]);
ck("bullet keeps only the English lead-in", ["Leonardo signed with Esercito Brasiliano"], b);
ck("...and drops the foreign quoted sentence", false, /Centauro|veicoli/.test(b[0] || ""));

// ---- 5. bare-string reference rows do not crash and are handled ------------------
// lens ITSELF a bare string (the shape that once blanked the app) -> no bullets.
ck("a bare-string lens yields no bullets (not a crash)", [], articleBullets("SPEC RANK"));
// a bare string as a ROW inside the array is treated as the html cell.
ck("a bare-string row is capitalized and kept",
   ["Spec rank"], articleBullets(["spec rank"]));
// a row with no em-dash: the whole (stripped) string becomes the phrase.
ck("a row with no em-dash uses the whole string",
   ["Leonardo signed a deal"], articleBullets([["STATEMENT", "leonardo signed a deal"]]));

// ---- 6. empty / malformed lens ---------------------------------------------------
ck("empty array -> no bullets", [], articleBullets([]));
ck("null lens -> no bullets", [], articleBullets(null));
ck("undefined lens -> no bullets", [], articleBullets(undefined));
// a row whose phrase is empty (leads with the dash) contributes nothing.
ck("an empty lead-in is skipped", [], articleBullets([["STATEMENT", `${DASH} <i>"only a quote"</i>`]]));
// a row with an empty second cell is skipped by statementRows.
ck("a row with an empty value cell is skipped", [], articleBullets([["STATEMENT", ""]]));

if (bad) { console.log(`\n${bad} failure(s)`); process.exit(1); }
console.log("\nok - articleBullets caps at 4, capitalizes, strips HTML, drops the quote, survives bare-string shapes");
