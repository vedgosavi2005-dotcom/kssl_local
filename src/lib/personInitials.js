/* AVATAR INITIALS FROM A PERSON'S NAME: first letter of the first name + first letter of
 * the surname.
 *
 * Functional test G11, 2026-10-25: the avatar read "DD" for "Dame Ruth Cairnie DBE" and
 * "S(" for "Commodore Sujay Kapoor (Retd.)" -- the old helper stripped a short list of
 * prefixes only and took the first character of whatever token came last. Stored names
 * carry titles (Dr / Sir / Dame / Air Chief Marshal), bracketed nicknames and remarks
 * ("(Butzi)", "(Retd.)"), post-nominals (DBE, KCB, CBE, Jr.) and initials with dots
 * ("T. V. Chowdary"); all of that goes before the two letters are taken.
 */

// leading titles and ranks, compared lower-case with dots removed
const TITLES = new Set([
  "mr", "mrs", "ms", "miss", "mx", "dr", "prof", "professor", "sir", "dame", "lord", "lady",
  "shri", "sri", "smt", "shrimati", "kumari", "hon", "honourable", "rev", "herr", "frau",
  "ing", "dipl", "mag", "eng",
  "commodore", "cdre", "cmde", "captain", "capt", "col", "colonel", "lt", "lieutenant",
  "gen", "general", "maj", "major", "brig", "brigadier", "adm", "admiral", "vadm", "radm",
  "vice", "rear", "air", "chief", "marshal", "wing", "group", "commander", "cdr", "cmdr",
  "sqn", "ldr", "retd", "ret",
]);
// trailing post-nominals and suffixes, compared lower-case with dots removed
const SUFFIXES = new Set([
  "jr", "sr", "ii", "iii", "iv", "phd", "md", "mba", "retd", "ret", "esq",
  "dbe", "cbe", "obe", "mbe", "kbe", "gbe", "kcb", "cb", "kcmg", "cmg", "freng", "frs",
  "fraes", "dl", "pvsm", "avsm", "vsm", "ysm", "sm", "uysm", "vm",
]);

const bare = (tok) => tok.replace(/[^\p{L}\p{N}]/gu, "");

export function personInitials(name) {
  const text = String(name == null ? "" : name)
    .replace(/\([^)]*\)|\[[^\]]*\]/g, " ") // bracketed nicknames and remarks: "(Butzi)", "(Retd.)"
    .replace(/[()[\]]/g, " ");
  let toks = text.split(/[\s,]+/).map(bare).filter(Boolean);
  while (toks.length > 1 && TITLES.has(toks[0].toLowerCase())) toks.shift();
  while (toks.length > 1) {
    const last = toks[toks.length - 1];
    const lc = last.toLowerCase();
    // a known suffix, or an all-caps post-nominal after a first name and a surname
    if (SUFFIXES.has(lc) || (toks.length > 2 && last.length >= 2 && last === last.toUpperCase() && /^\p{L}+$/u.test(last))) {
      toks.pop();
    } else break;
  }
  if (!toks.length) return "EX";
  if (toks.length === 1) return toks[0].slice(0, 2).toUpperCase();
  return `${toks[0][0]}${toks[toks.length - 1][0]}`.toUpperCase();
}
