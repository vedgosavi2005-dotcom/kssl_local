/* Tender judgements are STORED fields; this module only reads them and orders them (ruling R6).

   The fit grade (`clientFit`), the revenue estimate (`revenueEstimate`, `expectedRevenue`, `revenueMid`), the matched
   client product (`matches`) and the matched rival (`competitorFit`) come from the dataset. A field that is absent
   reads as null, never as a computed stand-in: nothing here weights value by fit, assumes a win probability, orders
   a purchase lag or ranks rivals from a product catalogue.

   The Top opportunity tables are built in the browser from those stored fields by deterministic ordering only:
   a tender with a stored fit first, strong before partial before weak, then the nearest closing date, then the
   larger stored value. A tender or project with no stored fit is not listed. Revenue is printed as a stored revenue
   estimate or not at all (the dash is the caller's); the buyer's tender value is never shown as revenue. */
import { formatDate } from "../utils/formatDate.js";
import { COCKPIT_TENDER_ROWS, COCKPIT_PROJECT_ROWS, COCKPIT_MOVE_ROWS } from "./chrome.js";

const has = (v) => v != null && String(v).trim() !== "";
const DAY = 86400000;

/* the stored fit word (strong / partial / weak), as it is, or null */
export const fitOf = (t) => (t && has(t.clientFit) ? String(t.clientFit).trim() : t && has(t.fit) ? String(t.fit).trim() : null);

/* the stored revenue estimate midpoint, or null; a missing estimate is not zero */
export const revenueOf = (t) => {
  if (!t || !has(t.revenueMid)) return null;
  const n = Number(t.revenueMid);
  return Number.isFinite(n) ? n : null;
};

/* The order of the three stored fit words; any other word (or none) is 0 and is not shortlisted. */
const FIT_RANK = { strong: 3, partial: 2, weak: 1 };
export const fitRank = (word) => FIT_RANK[String(word == null ? "" : word).trim().toLowerCase()] || 0;

/* The revenue text as stored: the revenue estimate (revenueEstimate, then expectedRevenue, then the served midpoint
   revenueMid). The buyer's tender value is NOT revenue and is never read here. `estimate` is true whenever a text is
   returned; null text when the record stores no estimate. */
export function revenueText(t) {
  if (!t) return { text: null, estimate: false };
  for (const k of ["revenueEstimate", "expectedRevenue"]) if (has(t[k])) return { text: String(t[k]).trim(), estimate: true };
  const mid = revenueOf(t);
  if (mid !== null) return { text: mid.toLocaleString("en-US"), estimate: true };
  return { text: null, estimate: false };
}

/* the stored matched client product, or null */
export const modelOf = (t) => {
  const m = t && Array.isArray(t.matches) ? t.matches.find((x) => x && has(x.n)) : null;
  return m ? String(m.n).trim() : null;
};

/* the stored matched rival: "Company · product", or null */
export const rivalOf = (t) => {
  const list = t && Array.isArray(t.competitorFit) ? t.competitorFit : [];
  const c = list.find((x) => x && has(x.company || x.name || x.n));
  if (!c) return null;
  const name = String(c.company || c.name || c.n).trim();
  const prod = Array.isArray(c.products) ? c.products.find(has) : null;
  return prod ? `${name} · ${String(prod).trim()}` : name;
};

const stamp = (d) => {
  const n = Date.parse(has(d) ? String(d) : "");
  return Number.isFinite(n) ? n : null;
};
/* ascending, a missing value last */
const nearer = (a, b) => (a === b ? 0 : a === null ? 1 : b === null ? -1 : a - b);
/* descending, a missing value last */
const larger = (a, b) => (a === b ? 0 : a === null ? 1 : b === null ? -1 : b - a);
const amount = (t) => (t && has(t.valueAmount) && Number.isFinite(Number(t.valueAmount)) ? Number(t.valueAmount) : null);

/* TOP TENDERS: the open tenders that carry a stored fit, ordered by fit, then the nearest closing date, then the
   larger stored value, then the id (so the order is total). `open` is the open bucket (overview.bucketTenders). */
export function topTenders(open, limit = COCKPIT_TENDER_ROWS) {
  return (open || [])
    .map((t) => ({ t, fit: fitOf(t) }))
    .filter((r) => fitRank(r.fit) > 0)
    .sort((a, b) =>
      fitRank(b.fit) - fitRank(a.fit) ||
      nearer(stamp(a.t.closingDate), stamp(b.t.closingDate)) ||
      larger(amount(a.t), amount(b.t)) ||
      String(a.t.id).localeCompare(String(b.t.id)))
    .slice(0, limit)
    .map(({ t, fit }) => {
      const rev = revenueText(t);
      return {
        id: t.id, t, _src: t._src, title: t.title,
        where: [t.country, t.issuer].filter(has).join(" · "), issuer: t.issuer,
        decides: has(t.closingDate) ? formatDate(t.closingDate) : "",
        fit, model: modelOf(t), rival: rivalOf(t), revenue: rev.text, estimate: rev.estimate,
      };
    });
}

/* PROJECTS TO WIN BEFORE THEY TENDER: the stored projects (data.projects) that carry a stored fit, by fit, then how
   far along (stageRank), then the latest milestone date, then the name. A project with no stored fit is not listed. The rival is the competitor the project
   belongs to. A column the project does not store prints a dash. */
const dayStamp = (d) => {
  const s = has(d) ? String(d) : "";
  const full = /^\d{4}$/.test(s) ? `${s}-01-01` : /^\d{4}-\d{2}$/.test(s) ? `${s}-01` : s;
  return stamp(full);
};
export function topProjects(projects, limit = COCKPIT_PROJECT_ROWS) {
  return (projects || [])
    .filter((p) => p && has(p.name))
    .map((p) => ({ p, fit: fitOf(p) }))
    .filter((r) => fitRank(r.fit) > 0)
    .sort((a, b) =>
      fitRank(b.fit) - fitRank(a.fit) ||
      (Number(b.p.stageRank) || 0) - (Number(a.p.stageRank) || 0) ||
      larger(dayStamp(a.p.latest && a.p.latest.date), dayStamp(b.p.latest && b.p.latest.date)) ||
      String(a.p.name).localeCompare(String(b.p.name)))
    .slice(0, limit)
    .map(({ p, fit }) => {
      const rev = revenueText(p);
      return {
        id: p.id, p, _src: p._src, title: p.name,
        where: [p.location, p.customer].filter(has).join(" · "), issuer: p.customer,
        stage: has(p.stageNote) ? String(p.stageNote).trim() : has(p.stage) ? String(p.stage).trim() : "",
        fit, model: modelOf(p),
        rival: has(p.company) ? String(p.company).trim() : null,
        revenue: rev.text, estimate: rev.estimate,
      };
    });
}

/* NEXT MOVES: the stored actions ({ do, due }) on the open tenders, those not yet past due, soonest first. The count
   of days is the stored date against today. */
export function nextMoves(open, today = new Date(), limit = COCKPIT_MOVE_ROWS) {
  const midnight = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const rows = [];
  (open || []).forEach((t) =>
    (Array.isArray(t.actions) ? t.actions : []).forEach((a, i) => {
      const due = a && stamp(a.due);
      if (due === null || due < midnight || !has(a.do)) return;
      rows.push({ id: `${t.id}-${i}`, t, _src: t._src, action: String(a.do).trim(), due: a.due, days: Math.round((due - midnight) / DAY) });
    }));
  return rows.sort((a, b) => a.days - b.days || String(a.id).localeCompare(String(b.id))).slice(0, limit);
}
