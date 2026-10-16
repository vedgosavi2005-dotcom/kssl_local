/* THE FIXED PARAMETER SET OF A TENDER ROW.
 *
 * The same nine parameters are resolved for every tender, in the same order. Each is a
 * stored column or null (the record does not hold it); nothing is guessed from other text.
 *   buyer    issuer_display / buyer_name     country  country_name     category  category_text
 *   value    value_text                      quantity quantity + unit  posted    published_date
 *   closing  closing_date                    status   status           source    primary source's portal / publisher
 */
import { formatDate } from "../utils/formatDate.js";

export const NOT_ON_RECORD = "not on record";

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

const has = (v) => v != null && String(v).trim() !== "";
const str = (v) => String(v).trim();
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const one = (v, fmt = str) => (has(v) ? fmt(v) : null);

const RESOLVE = {
  buyer: (t) => one(t.issuer),
  country: (t) => one(t.country),
  category: (t) => one(t.cat),
  value: (t) => one(t.value),
  quantity: (t) => one(t.qty),
  posted: (t) => one(t.posted, (v) => formatDate(str(v))),
  closing: (t) => one(t.closingDate, (v) => formatDate(str(v))),
  status: (t) => one(t.status, (v) => cap(str(v))),
  source: (t) => {
    const s = Array.isArray(t.srcs) && t.srcs[0];
    return s ? one(s.label) : null;
  },
};

/**
 * Resolve one tender to its fixed row shape.
 *
 * @returns {{ title: string, params: Array<{key, label, value: string|null, text: string}> }}
 *   `value` is the stored string or null; `text` is what to print: the value, or NOT_ON_RECORD.
 */
export function resolveTenderRow(t) {
  const rec = t && typeof t === "object" ? t : {};
  return {
    title: has(rec.title) ? str(rec.title) : "",
    params: TENDER_PARAMS.map(({ key, label }) => {
      const value = RESOLVE[key](rec);
      return { key, label, value, text: value == null ? NOT_ON_RECORD : value };
    }),
  };
}

/* The same nine, as [label, text, resolved] rows. Never filtered: the caller decides. */
export function tenderFactRows(t) {
  return resolveTenderRow(t).params.map((p) => [p.label, p.text, p.value != null]);
}
