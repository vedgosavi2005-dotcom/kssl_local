/* Leader avatar initials (functional test G11, 2026-10-25).
 *
 *     node tests/unit/test_person_initials.mjs
 *
 * Titles, bracketed remarks, post-nominals and dots go before the two letters are
 * taken: "Dame Ruth Cairnie DBE" read "DD" and "Commodore Sujay Kapoor (Retd.)" read "S(".
 */
import { personInitials } from "../../src/lib/personInitials.js";

let fails = 0;
const ck = (name, want) => {
  const got = personInitials(name);
  const ok = got === want;
  console.log(`  ${JSON.stringify(name).padEnd(46)} ${got.padEnd(3)} ${ok ? "ok" : `FAIL want ${want}`}`);
  if (!ok) fails++;
};

ck("Dame Ruth Cairnie DBE", "RC");
ck("Commodore Sujay Kapoor (Retd.)", "SK");
ck("Sir Nick Hine KCB", "NH");
ck("Air Chief Marshal NAK Browne (Retd.)", "NB");
ck("Bezhalel (Butzi) Machlis", "BM");
ck("Dr. Jaiteerth R. Joshi", "JJ");
ck("Dr Charles Woodburn CBE", "CW");
ck("T. V. Chowdary", "TC");
ck("Neil G. Mitchill Jr.", "NM");
ck("Dr. Nicolai Künzner", "NK");
ck("Mr. Rajinder Singh Bhatia", "RB");
ck("Shri Shailesh Vagerwal", "SV");
ck("Madonna", "MA");
ck("", "EX");
ck(null, "EX");

// every result is two letters, never a bracket, dot or digit
for (const n of ["Prof. (Dr.) A. Kumar", "Lt Gen (Retd) P. S. Rajeshwar, PVSM, AVSM", "Ms. Jane Doe, PhD"]) {
  const got = personInitials(n);
  const ok = /^\p{Lu}{2}$/u.test(got);
  console.log(`  ${JSON.stringify(n).padEnd(46)} ${got.padEnd(3)} ${ok ? "ok" : "FAIL not two letters"}`);
  if (!ok) fails++;
}

console.log(fails ? `\nFAIL - ${fails} initials wrong` : "\nok - initials come from the first name and the surname");
process.exit(fails ? 1 : 0);
