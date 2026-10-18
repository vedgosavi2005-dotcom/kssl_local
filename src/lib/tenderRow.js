/* THE FIXED PARAMETER SET OF A TENDER ROW.
 *
 * REPORTED: "many have a small basic title, no understanding ... fix per tender row
 * parameters, resolve from each tender and show a consistent flow".
 *
 * Measured on the served corpus (136 tenders, 2026-09-05): the median title is 29
 * characters, 40 titles are 20 characters or fewer, 50 are three words or fewer --
 * "Ammunition", "Firearms", "Eb Tuba", "Vane,Large". The card under such a title used
 * to print whichever of six fields happened to be filled, so one row read six parts and
 * the next three, and a reader could not tell a field the notice does not publish from
 * one the card forgot. The title is not rewritten (a composed title is an invented one);
 * instead the SAME nine parameters are resolved for EVERY tender, in the same order,
 * and each one either carries a stored value or says, in its own visual state, that
 * the record does not hold it.
 *
 * What the served record can fill (origin=pipeline, n=136):
 *   issuer / country / cat / status / url / srcs   136   always
 *   deadline                                         79   "d Mon yyyy" strings
 *   value                                            23
 *   qty                                               7
 *   req / stage / dl / matches                        0   only the 22 reference rows
 *
 * So Value, Quantity and Closing date are unresolved on most rows. That is the fact the
 * row must state, not hide: "not on record" is data; a blank is not.
 *
 * Each parameter names the field it was resolved FROM (`from`), so a reader of the
 * report, a test, or the next engineer can see which link of the chain fired.
 */
import { formatDate } from "../utils/formatDate.js";
import { TENDER_CARD_CELLS, TENDER_EMPTY, TENDER_VALUE_EMPTY } from "./chrome.js";
import { amountText } from "./tenderValue.js";
import { fitOf } from "./tenderIntel.js";

export const NOT_ON_RECORD = "not on record";

/* The fixed set, in display order. `label` is what the row prints. */
export const TENDER_PARAMS = [
  { key: "buyer", label: "Buyer" },
  { key: "country", label: "Country" },
  { key: "category", label: "Category" },
  { key: "value", label: "Value" },
  { key: "quantity", label: "Quantity" },
  { key: "posted", label: "Published" },
  { key: "closing", label: "Closing date" },
  { key: "status", label: "Status" },
  { key: "source", label: "Source" },
];

/* Requirement rows are [code, value]. The code is the source column name; the words below are neutral chrome for
   those columns. A code not listed here is a stored scope_bullet_label and prints as stored. */
const REQ_CODE_LABEL = {
  description: "Description",
  scope_text: "Scope",
  requirement_note: "Note",
  equipment_scope: "Equipment",
  rating_band: "Rating band",
  use_case: "Use case",
  quantity: "Quantity",
  category_text: "Category",
  source_text: "Source",
  published_date: "Published",
  closing_date: "Closing date",
};
export const reqLabel = (code) => (Object.prototype.hasOwnProperty.call(REQ_CODE_LABEL, code) ? REQ_CODE_LABEL[code] : code);

/* "n/d" is the pipeline's placeholder for a figure the notice never published (value
   is stored as "n/d" on every such row) -- it is absence, not a value to print. */
const has = (v) => v != null && String(v).trim() !== "" && !/^n\/?d$/i.test(String(v).trim());
const str = (v) => String(v).trim();

/* A requirement row by its CODE. The dataset ships requirement rows as [code, value]: the code is the source
   column name (description, scope_text, quantity, published_date, closing_date, ...) or a stored
   scope_bullet_label. Only the codes below are read here, by exact match. */
const reqRow = (t, code) => {
  if (!t || !Array.isArray(t.req)) return null;
  const pair = t.req.find((r) => Array.isArray(r) && r[0] === code && has(r[1]));
  return pair ? str(pair[1]) : null;
};

/* wireTendersWithRealDays overwrites `deadline` with a countdown and keeps the served
   string on `closingDate`. Before wiring there is no closingDate key and `deadline` IS
   the served string. Read whichever holds the record, and refuse anything that is a
   computation: a countdown, the "no deadline on record" placeholder, or the milestone text. */
const COMPUTED_DEADLINE = /days?\s+left|closes in|no deadline on record|closed \/ expired|awarded \/ settled/i;
const servedDeadline = (t) => {
  if (Object.prototype.hasOwnProperty.call(t, "closingDate")) return has(t.closingDate) ? str(t.closingDate) : null;
  if (!has(t.deadline)) return null;
  const d = str(t.deadline);
  if (COMPUTED_DEADLINE.test(d)) return null;
  if (has(t.milestone) && d === str(t.milestone)) return null;
  return d;
};

const urlHost = (u) => {
  if (!has(u)) return null;
  const h = str(u).replace(/^https?:\/\/(www\.)?/i, "").split("/")[0];
  return h || null;
};

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/* ------------------------------------------------------------- resolvers ----
   Each returns { value, from } -- value null when nothing on the record fills it. A
   resolver reads STORED fields only; the one computation allowed is "the served closing
   date has passed", which tenderCalc already makes and the Closed tab already relies on.
   The chain order is the documentation. */
const RESOLVE = {
  buyer: (t) => (has(t.issuer) ? { value: str(t.issuer), from: "issuer" } : none()),
  country: (t) => (has(t.country) ? { value: str(t.country), from: "country" } : none()),
  category: (t) => (has(t.cat) ? { value: str(t.cat), from: "cat" } : none()),
  // the stated amount in rupees (stored fx_rate), else the stored value text as written
  value: (t) => (amountText(t.valueAmount, t.valueCurrency) ? { value: amountText(t.valueAmount, t.valueCurrency), from: "valueAmount" }
    : has(t.value) ? { value: str(t.value), from: "value" } : none()),
  quantity: (t) =>
    has(t.qty) ? { value: str(t.qty), from: "qty" }
    : first(reqRow(t, "quantity"), "req"),
  posted: (t) => {
    if (has(t.posted)) return { value: formatDate(str(t.posted)), from: "posted" };
    const r = reqRow(t, "published_date");
    return r ? { value: formatDate(r), from: "req" } : none();
  },
  closing: (t) => {
    const d = servedDeadline(t);
    if (d) return { value: formatDate(d), from: "deadline" };
    const r = reqRow(t, "closing_date");
    if (r) return { value: formatDate(r), from: "req" };
    if (has(t.milestone)) return { value: str(t.milestone), from: "milestone" };
    return none();
  },
  status: (t) => {
    const s = has(t.status) ? str(t.status).toLowerCase() : "";
    if (s === "awarded") return { value: "Awarded", from: "status" };
    if (t.urlKind === "award") return { value: "Awarded", from: "urlKind" };
    if (s === "closed") return { value: "Closed", from: "status" };
    /* the served date has passed: tenderCalc set isLive=false from closingDate */
    if (t.isLive === false && servedDeadline(t)) return { value: "Closed", from: "deadline" };
    if (s) return { value: cap(s), from: "status" };
    return none();
  },
  source: (t) => {
    const lbl = Array.isArray(t.srcs) && t.srcs[0] && has(t.srcs[0].label) ? str(t.srcs[0].label) : null;
    if (lbl) return { value: lbl, from: "srcs" };
    const h = urlHost(t.url) || urlHost(Array.isArray(t.srcs) && t.srcs[0] && t.srcs[0].url);
    return h ? { value: h, from: "url" } : none();
  },
};
const none = () => ({ value: null, from: null });
const first = (v, from) => (v ? { value: v, from } : none());

/**
 * Resolve one tender to its fixed row shape.
 *
 * @returns {{ title: string, params: Array<{key, label, value: string|null, from: string|null, text: string}> }}
 *   `value` is the resolved string or null; `text` is what to print -- the value, or
 *   NOT_ON_RECORD. `title` is the stored title, untouched.
 */
export function resolveTenderRow(t) {
  const rec = t && typeof t === "object" ? t : {};
  return {
    title: has(rec.title) ? str(rec.title) : "",
    params: TENDER_PARAMS.map(({ key, label }) => {
      const { value, from } = RESOLVE[key](rec);
      return { key, label, value, from, text: value == null ? NOT_ON_RECORD : value };
    }),
  };
}

/* The same nine, as [label, text, resolved] rows -- for report tables and any surface
   that prints facts as pairs. Never filtered: the unresolved ones are the point. */
export function tenderFactRows(t) {
  return resolveTenderRow(t).params.map((p) => [p.label, p.text, p.value != null]);
}

/* A READABLE GIST, not an invented title.
 *
 * REPORTED: "the tender title are very short not understandable ... decide a format of
 * keep a title which will act as a gist and quickly understand". SAM/GePNIC titles are
 * procurement nomenclature -- "Vane Large", "Bristle Disc", "Eb Tuba" -- that names a
 * part without saying what class of thing it is or who wants it. The gist adds exactly
 * two facts the record already holds, in a fixed order, so it reads as a class and a
 * place at a glance:  <item> — <category> · <country>.
 *
 * Nothing here is composed from outside the record: category is the graded t.cat, country
 * is t.country, item is the stored title verbatim. A field the notice omits is dropped, so
 * a bare "Ammunition" tender with no country simply stays "Ammunition". The redundancy
 * guard keeps a title that already NAMES its category ("...Armoured Vehicles..." in the
 * "Protected & Armoured Vehicles" class) from repeating it. */
const _tok = (s) => str(s).toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length >= 4);

export function tenderGist(t) {
  const rec = t && typeof t === "object" ? t : {};
  const item = has(rec.title) ? str(rec.title) : "";
  if (!item) return "";
  const titleToks = new Set(_tok(item));
  const catToks = _tok(rec.cat);
  const catInTitle = catToks.length > 0 && catToks.some((w) => titleToks.has(w));
  const cat = has(rec.cat) && !catInTitle ? str(rec.cat) : null;
  const country =
    has(rec.country) && !titleToks.has(str(rec.country).toLowerCase()) ? str(rec.country) : null;
  const tail = [cat, country].filter(Boolean).join(" · ");
  return tail ? `${item} — ${tail}` : item;
}

/* A grounded one-line answer to "what is this tender about", for the At a glance panel,
 * where tenders showed no summary at all. Every clause is a stored field or is omitted --
 * buyer, item, category, country, the pipeline's own fit grade, closing date -- and the
 * value/quantity clause states the RECORD, never a number the notice does not publish. */
export function tenderSummary(t) {
  const rec = t && typeof t === "object" ? t : {};
  const item = has(rec.title) ? str(rec.title) : "this requirement";
  const buyer = has(rec.issuer) ? str(rec.issuer) : null;
  const cat = has(rec.cat) ? str(rec.cat) : null;
  const country = has(rec.country) ? str(rec.country) : null;
  const where = country ? ` in ${country}` : "";
  const catClause = cat ? ` (${cat} category)` : "";
  const lead = buyer
    ? `${buyer} is procuring ${item}${catClause}${where}.`
    : `Procurement of ${item}${catClause}${where}.`;

  // the stored lean sentence (serving.market_tender.lean_text), as it is
  const fit = has(rec.leanTxt) ? ` ${str(rec.leanTxt)}` : "";

  const closes = servedDeadline(rec);
  const closeClause = closes ? ` Closes ${formatDate(closes)}.` : "";

  const bits = [];
  if (has(rec.value)) bits.push(`published value ${str(rec.value)}`);
  if (has(rec.qty)) bits.push(`quantity ${str(rec.qty)}`);
  const recordClause = bits.length
    ? ` The notice states ${bits.join(" and ")}.`
    : " Value and quantity are not disclosed in the notice.";

  return `${lead}${fit}${closeClause}${recordClause}`;
}

/* THE TENDER CARD: the same five cells in the same order on every card (Buyer, Country, Category, Value, Status), then the
   client's fit row. A cell the record leaves empty prints the screen's own empty word (chrome.js: "not disclosed" for the
   value, a dash for every other cell) -- never a dropped cell, never a guessed value. */
export function tenderCardCells(t) {
  const byKey = {};
  resolveTenderRow(t).params.forEach((p) => { byKey[p.key] = p; });
  return TENDER_CARD_CELLS.map(([key, label]) => {
    const p = byKey[key];
    const empty = !p || p.value == null;
    return { key, label, text: empty ? (key === "value" ? TENDER_VALUE_EMPTY : TENDER_EMPTY) : p.value, empty };
  });
}

/* The fit row's bar and word. A stored percentage on the first matched product draws its own length; a stored grade
   (strong / partial / weak, on the match or on the tender) draws the grade's fixed length and prints the word; no stored
   fit draws an empty bar and a dash. */
const GRADE_CLASS = { strong: "high", partial: "mid", weak: "low" };
const GRADE_WIDTH = { high: 85, mid: 55, low: 25 };
const pctClass = (n) => (n >= 75 ? "high" : n >= 50 ? "mid" : "low");
/* list order: tenders with a stored client fit first (the stored %, else the grade's bar width), then by deadline */
export function fitRank(t) {
  const f = tenderFitBar(t);
  return f.cls ? parseFloat(f.width) : -1;
}
export const compareTenders = (a, b) => fitRank(b) - fitRank(a) || (Number(a.dl) || 999) - (Number(b.dl) || 999);
export function tenderFitBar(t) {
  const m0 = t && Array.isArray(t.matches) ? t.matches[0] : null;
  const pct = m0 && /%/.test(m0.pct || "") ? parseFloat(String(m0.pct).replace(/[^\d.]/g, "")) : NaN;
  if (!Number.isNaN(pct)) return { cls: pctClass(pct), width: `${Math.max(0, Math.min(100, pct))}%`, word: String(m0.pct), scored: true };
  const grade = String((m0 && m0.fit) || fitOf(t) || "").trim().toLowerCase();
  const cls = GRADE_CLASS[grade] || (GRADE_WIDTH[grade] ? grade : "");
  if (!cls) return { cls: "", width: "0%", word: TENDER_EMPTY, scored: false };
  const word = Object.keys(GRADE_CLASS).find((k) => GRADE_CLASS[k] === cls);
  return { cls, width: `${GRADE_WIDTH[cls]}%`, word, scored: false };
}
