/* Tender judgements are STORED fields; this module only reads them (ruling R6).

   The fit grade (`clientFit`) comes from the dataset. A field that is absent reads as null, never as a computed
   stand-in. The Top opportunity tables are not built here: they print the stored rank rows (data.topOpportunities). */
import { formatDate } from "../utils/formatDate.js";
import { amountText } from "./tenderValue.js";
const has = (v) => v != null && String(v).trim() !== "";

/* the stored fit word (strong / partial / weak), as it is, or null */
export const fitOf = (t) => (t && has(t.clientFit) ? String(t.clientFit).trim() : t && has(t.fit) ? String(t.fit).trim() : null);

/* ---- Top opportunity table cells (functional test G16, 2026-10-25) ----------------------------------------------- */

/* The words for a stored code, from the ui.code_label rows the dataset ships (data.database.ui.code_label) -- the
   same table the pipeline writes its vocabularies to; no second label map in code. `tables` are tried in order. */
export function codeLabel(data, tables, column, code) {
  const rows = (data && data.database && data.database.ui && data.database.ui.code_label) || [];
  for (const t of tables) {
    const r = rows.find((x) => x && x.table_name === t && x.column_name === column && x.code === code && x.label);
    if (r) return String(r.label);
  }
  return null;
}

/* "Where it stands" is stored as "<stage code> / <short status> / <detail>" ("approved_funded / Possible Foreign
   Military Sale approved / US approved a possible Foreign Military Sale on 2026-10-02"), and the table printed the raw
   code. The code becomes its ui.code_label words ("Approved and funded"; market_opportunity.stage, the table these rows
   come from), the rest is the detail line with its ISO dates in the house format. A text with no leading code is
   returned whole as the detail. */
const isoToDate = (s) => String(s).replace(/\b\d{4}-\d{2}-\d{2}\b/g, (d) => formatDate(d));
export function whereItStands(text, data) {
  const s = text == null ? "" : String(text).trim();
  if (!s) return { label: "", detail: "" };
  const parts = s.split(" / ");
  const code = /^[a-z]+(_[a-z]+)*$/.test(parts[0]) ? parts[0] : null;
  if (!code) return { label: "", detail: isoToDate(s) };
  const label = codeLabel(data, ["market_opportunity", "market_global_requirement"], "stage", code)
    || (code.charAt(0).toUpperCase() + code.slice(1)).replace(/_/g, " ");
  return { label, detail: isoToDate(parts.slice(1).join(" · ")) };
}

/* A stored revenue text in a short form for a narrow cell: "Stated tender value CZK 40,495,867.77" was clipped to
   "Stated". The stated amount goes through amountText (rupees at a stored rate, else "CZK 40.5 m" in its own code), the
   house style of every tender value; the full stored text stays as the cell's tooltip. Only a FULL stated amount is
   rewritten ("CZK 40,495,867.77", "EUR 1250000"); a text already short or a range ("USD 60-95 M") is returned as
   stored. */
const FULL_AMOUNT = /\b([A-Z]{3})\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{5,}(?:\.\d+)?)(?![\d.,\-–])(?!\s*(?:[kKmMbB]|mn|bn|million|billion|crore|lakh|Cr|L)\b)/;
export function revenueShort(text) {
  const s = text == null ? "" : String(text).trim();
  const m = FULL_AMOUNT.exec(s);
  if (!m) return s;
  return amountText(Number(m[2].replace(/,/g, "")), m[1]) || s;
}
