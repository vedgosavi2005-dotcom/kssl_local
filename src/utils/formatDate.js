/* The ONE date formatter: "05 Aug 2026" -- ZERO-PADDED day, three-letter month, year.

   It used to call toLocaleDateString("en-GB", { month: "short" }), which is not one
   format: the ICU data in Node 20+ and current Chrome spells September "Sept", so a
   report dated in September read "1 Sept 2026" beside pipeline dates that read
   "1 Sep 2026". The month table below is the one the served signal dates use, so
   every date in the app comes out of one spelling.

   Accepts a Date, an ISO string ("2026-09-05" or a full timestamp), a printed date in
   the house style ("1 Sep 2026", "01 Sept 2026"), or anything Date can parse. A string
   that is not a date at all ("Q4 2026 expected", "AoN cleared") is returned as it came:
   a served descriptive deadline is information, and a dash in its place would be a
   silent deletion. Only a non-string that fails to parse prints the dash. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/* Zero-pad the DAY to two digits, so single-digit days read "04 Aug 2026", not
   "4 Aug 2026" -- the operator asked for one consistent width across every surface.
   Only the day needs it here: the month is always a name, never a number. */
const pad2 = (n) => String(n).padStart(2, "0");

/* No value -> "" (never today, never 1970): a record with no stored date shows no date. Callers that mean
   "now" (a report's print date) pass new Date() themselves. */
export function formatDate(value) {
  if (value == null || value === "") return "";
  if (value instanceof Date) return fromDate(value);
  if (typeof value === "string") {
    const s = value.trim();
    if (!s) return "";
    let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (m) return `${pad2(Number(m[3]))} ${MONTHS[Number(m[2]) - 1] || m[2]} ${m[1]}`;
    m = /^(\d{1,2})\s+([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{4})$/.exec(s);
    if (m) {
      const mi = MONTHS.findIndex((x) => x.toLowerCase() === m[2].toLowerCase());
      if (mi >= 0) return `${pad2(Number(m[1]))} ${MONTHS[mi]} ${m[3]}`;
    }
    /* MONTH-ONLY IN, MONTH-ONLY OUT -- never a fabricated day. "2026-09" and
       "Sep 2026"/"September 2026" carry no day, but `new Date("Sep 2026")` silently
       resolves them to the 1st -- which is how a 9 Sep article read as "01 Sep 2026".
       They carry a real month, so they return as month + year rather than a dash. */
    // YEAR-ONLY IN, YEAR-ONLY OUT ("2019": a source that states only the year), never "01 Jan 2019"
    if (/^(19|20)\d{2}$/.test(s)) return s;
    m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(s);
    if (m) return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
    m = /^([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{4})$/.exec(s);
    if (m) {
      const mi = MONTHS.findIndex((x) => x.toLowerCase() === m[1].toLowerCase());
      if (mi >= 0) return `${MONTHS[mi]} ${m[2]}`;
    }
    const parsed = new Date(s);
    return Number.isNaN(parsed.getTime()) ? s : fromDate(parsed);
  }
  return fromDate(new Date(value));
}

function fromDate(date) {
  if (Number.isNaN(date.getTime())) return "—";
  return `${pad2(date.getDate())} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}
