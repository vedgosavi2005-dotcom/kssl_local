/* A tender states one amount in one currency (serving.market_tender.value_amount + value_currency, shipped as
   valueAmount / valueCurrency); a total is a sum per currency. Totals are SHOWN in rupees (formatTotals) using only
   stored exchange rates; no rate exists anywhere in code (ruling R9). */

/* the field names a record keeps its amount and currency under: tenders use the default, awards use AWARD_FIELDS */
export const TENDER_FIELDS = { amount: "valueAmount", currency: "valueCurrency" };
export const AWARD_FIELDS = { amount: "value", currency: "currency" };

/* `f` is ignored unless it names fields, so `list.filter(hasAmount)` (which passes an index) stays a tender test */
export const hasAmount = (t, f) => {
  const k = f && f.amount ? f : TENDER_FIELDS;
  return !!t && Number(t[k.amount]) > 0 && !!String(t[k.currency] || "").trim();
};

/* [{ currency, amount, n }], one per stored currency, in currency-code order */
export function valueTotals(list, f = TENDER_FIELDS) {
  const by = {};
  (list || []).filter((t) => hasAmount(t, f)).forEach((t) => {
    const c = String(t[f.currency]).trim();
    const e = by[c] || (by[c] = { currency: c, amount: 0, n: 0 });
    e.amount += Number(t[f.amount]);
    e.n += 1;
  });
  return Object.values(by).sort((a, b) => a.currency.localeCompare(b.currency));
}

const short = (n) => (n >= 1e6 ? `${(Math.round(n / 1e5) / 10).toLocaleString("en-US")} m` : Math.round(n).toLocaleString("en-US"));

/* RUPEES. Amounts are shown in Indian rupees, Indian style (₹ 12.4 Cr, ₹ 8.5 L). An amount stated in INR is shown as
   it is; another currency is converted only with a STORED rate (data.fxRates: { "USD": <rupees per unit>, ... },
   handed in by wireDataset through setFxRates). No rate is written in code: a currency with no stored rate keeps its
   own code and amount, so nothing is converted at a guessed rate. */
let FX = {};
export function setFxRates(rates) {
  FX = {};
  Object.entries(rates || {}).forEach(([c, r]) => {
    const v = Number(r);
    if (Number.isFinite(v) && v > 0) FX[String(c).trim().toUpperCase()] = v;
  });
}
const inrOf = (t) => {
  const c = String(t.currency).trim().toUpperCase();
  return c === "INR" ? t.amount : FX[c] ? t.amount * FX[c] : null;
};
const one = (n, unit, d) => `${(Math.round((n / unit) * 10 ** d) / 10 ** d).toLocaleString("en-IN")}`;
export const rupees = (n) =>
  n >= 1e7 ? `₹ ${one(n, 1e7, n >= 1e9 ? 0 : 1)} Cr` : n >= 1e5 ? `₹ ${one(n, 1e5, 1)} L` : `₹ ${Math.round(n).toLocaleString("en-IN")}`;

/* one stated amount in rupees ("₹ 12.4 Cr"), or in its own currency when no stored rate exists; null with no amount */
export function amountText(amount, currency) {
  const n = Number(amount), c = String(currency || "").trim();
  return n > 0 && c ? formatTotals([{ currency: c, amount: n, n: 1 }]) : null;
}

/* "₹ 1,240 Cr" when every currency is INR or has a stored rate; otherwise the converted part in rupees and each
   unconverted currency in its own code ("₹ 12 Cr · UAH 34,516 m"); "—" when no record states an amount */
export function formatTotals(totals) {
  if (!totals || !totals.length) return "—";
  const inr = totals.map(inrOf);
  const sum = inr.filter((v) => v != null).reduce((a, b) => a + b, 0);
  const rest = totals.filter((_, i) => inr[i] == null).map((t) => `${t.currency} ${short(t.amount)}`);
  return [...(inr.some((v) => v != null) ? [rupees(sum)] : []), ...rest].join(" · ");
}
