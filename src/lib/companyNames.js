/* THE FULL NAME BEHIND A COMPETITOR: read from the dataset, never typed here.
 *
 * competitors[cid].legal is serving.competitive_competitor.legal_name. An empty legal name
 * shows the served display name. There is no table of expansions or former names in code:
 * an abbreviation is expanded only when the database says so.
 */

const WORDS = /[A-Za-z&]+/g;
const JOINERS = new Set(["AND", "OF", "THE", "FOR"]);

/** The all-caps tokens in a name -- the ones a reader cannot decode. */
export function initialisms(name) {
  const out = [];
  for (const tok of String(name == null ? "" : name).match(WORDS) || []) {
    if (tok.length < 2 || JOINERS.has(tok.toUpperCase())) continue;
    if (tok === tok.toUpperCase() && /^[A-Za-z]+$/.test(tok)) out.push(tok);
  }
  return out;
}

/** Does this served name contain something a reader would need expanded? */
export const isAbbreviated = (name) => initialisms(name).length > 0;

const clean = (s) => String(s == null ? "" : s).replace(/&amp;/g, "&").trim();

/** The full name of a competitor: its stored legal name, else the served display name.
 *  `competitors` is the dataset's competitors map; nothing is guessed from the id. */
export function competitorFullName(cid, servedName, competitors) {
  const row = competitors && cid ? competitors[cid] : null;
  return clean(row && row.legal) || clean(servedName);
}

/* The SHORT label for a company, for the positioning list where the product is the
   headline and the maker sits under it in small type. Two steps, in order:

     1. A name already anchored by an initialism ("KNDS", "BAE Systems Bofors", "Saab
        AB") is left exactly as stored -- it is already legible, and acronym-ing it would
        invent letters ("BAE Systems Bofors" -> "BSB").
     2. A long spelled-out name with no initialism becomes its own acronym, first letter
        of each significant word: "Advanced Weapons and Equipment India Limited" -> AWEIL.
        Short names (<=2 significant words: "Nexter", "Roshel Inc.") have nothing to
        shorten and pass through.

   Never maps one company onto another -- an abbreviation only ever drops or initialises
   the letters of the same name. */
export function companyShort(name) {
  const s = clean(name);
  if (!s) return "";
  if (isAbbreviated(s)) return s; // already carries an initialism -> leave as stored
  const words = (s.match(WORDS) || []).filter(
    (w) => w !== "&" && !JOINERS.has(w.toUpperCase()),
  );
  if (words.length <= 2) return s; // already short enough to read
  return words.map((w) => w[0].toUpperCase()).join("");
}
