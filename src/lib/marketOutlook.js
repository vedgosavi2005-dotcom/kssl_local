/* MARKET OUTLOOK: where demand is heading, who wins, who re-tenders, what drives it.

   Every figure is counted from records the dataset serves and each section says which records it used:
     tenders      data.tenders (published_date or closing_date from the row's requirement codes, category `cat`)
     awards       data.awards (winner, value + currency, buyer, segment, date or year)
     signals      data.marketCards that are not tenders (meta "Kind · Location · Segment · date")
   Nothing is invented. A date a record does not carry is not guessed: a year-only award counts as an award, not as
   activity in a quarter. Values are the stored amounts in their own currency (ruling R9), never converted. A segment
   is the stored category text, as it is. The "what to do" sentence per segment is a stored judgement
   (serving.market_segment_assessment.recommendation); a segment without one has none. */

import { AWARD_FIELDS, TENDER_FIELDS, hasAmount, valueTotals } from "./tenderValue.js";

const DAY = 86400000;
export const WINDOW_DAYS = 183;      // "last 6 months" is this many days back from today, and the same again before it
const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };

/* "15 Oct 2026", "2026-10-15" or "2026-10-15 09:59" -> Date (UTC), else null */
export function asDate(s) {
  const t = String(s || "").trim();
  let m = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  m = t.match(/^(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})/);
  if (m && MONTHS[m[2].toLowerCase()] != null) return new Date(Date.UTC(+m[3], MONTHS[m[2].toLowerCase()], +m[1]));
  return null;
}

/* requirement rows are [code, value] */
const reqVal = (t, code) => ((t.req || []).find((r) => r[0] === code) || [])[1];
const tenderDate = (t) => asDate(reqVal(t, "published_date")) || asDate(reqVal(t, "closing_date")) || asDate(t.closingDate);

/* the stored segment text, trimmed; "" when the record names none */
export const segmentOf = (s) => (s == null ? "" : String(s).trim());

/* a market card's meta, joined from stored fields: "Kind · Location · Segment · date" (or without a segment) */
export function cardMeta(c) {
  const p = String((c && c.meta) || "").split(" · ").map((x) => x.trim());
  const date = asDate(p[p.length - 1]);
  return { kind: p[0] || "", country: p[1] || "", segment: p.length > 3 ? p[2] : "", date };
}

const fits = (t) => t.clientFit === "strong" || t.clientFit === "partial";
const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();

/* the stored recommendation for a segment, or null */
export function assessmentOf(d, segment) {
  const rows = (d && d.database && d.database.serving && d.database.serving.market_segment_assessment) || [];
  return rows.find((x) => same(x.segment, segment)) || null;
}
export function recommendationOf(d, segment) {
  const r = assessmentOf(d, segment);
  return r && r.recommendation != null && String(r.recommendation).trim() ? String(r.recommendation).trim() : null;
}

/* ---- 1. where demand is heading, by segment ---- */
export function segments(d, openTenders, today = new Date(), closedTenders = []) {
  const t0 = today.getTime();
  const cut = t0 - WINDOW_DAYS * DAY;
  const cut2 = cut - WINDOW_DAYS * DAY;
  const known = new Set();
  (d.tenders || []).forEach((t) => known.add(segmentOf(t.cat)));
  (d.awards || []).forEach((a) => known.add(segmentOf(a.segment)));
  known.delete("");
  const by = new Map();
  const bump = (seg, date, kind) => {
    if (!known.has(seg)) return;
    const r = by.get(seg) || { segment: seg, recent: 0, before: 0, tenders: 0, signals: 0, awards: 0 };
    r[kind] += 1;
    if (date) {
      const t = date.getTime();
      if (t <= t0 && t > cut) r.recent += 1;
      else if (t <= cut && t > cut2) r.before += 1;
    }
    by.set(seg, r);
  };
  (d.tenders || []).forEach((t) => bump(segmentOf(t.cat), tenderDate(t), "tenders"));
  (d.marketCards || []).map(cardMeta).filter((m) => m.segment).forEach((m) => bump(segmentOf(m.segment), m.date, "signals"));
  (d.awards || []).forEach((a) => bump(segmentOf(a.segment), asDate(a.date), "awards"));

  const fit = (openTenders || []).filter(fits);
  // closed for bids, award not yet made or published
  const waiting = (closedTenders || []).filter((t) => fits(t) && String(t.status || "").toLowerCase() !== "awarded");
  const won = (d.awards || []).filter((a) => a.winner);
  const latestSignal = new Map();
  (d.marketCards || []).forEach((c) => {
    const m = cardMeta(c);
    if (!m.segment) return;
    const seg = segmentOf(m.segment);
    const cur = latestSignal.get(seg);
    if (!cur || (m.date && (!cur.date || m.date > cur.date))) latestSignal.set(seg, { title: c.title, kind: m.kind, country: m.country, date: m.date });
  });
  return [...by.values()].map((r) => {
    const mine = fit.filter((t) => segmentOf(t.cat) === r.segment);
    const aw = won.filter((a) => segmentOf(a.segment) === r.segment);
    /* the segment's leading winner is the one with the most awards; award values are in their own
       currencies and are never added across currencies, so no share of value is computed */
    const wins = new Map();
    aw.forEach((a) => {
      const k = winnerKey(a.winner);
      const cur = wins.get(k) || { name: a.winner, n: 0 };
      cur.n += 1;
      wins.set(k, cur);
    });
    const top = [...wins.values()].sort((a, b) => b.n - a.n || String(a.name).localeCompare(String(b.name)))[0];
    const pend = waiting.filter((t) => segmentOf(t.cat) === r.segment);
    return {
      segment: r.segment, recent: r.recent, before: r.before,
      /* the signed percentage change between the two counted windows; no change is called when the earlier one is empty */
      change: r.before > 0 ? Math.round(((r.recent - r.before) / r.before) * 100) : null,
      records: { tenders: r.tenders, signals: r.signals, awards: r.awards },
      open: mine.length, totals: valueTotals(mine, TENDER_FIELDS),
      winner: top ? top.name : null,
      winnerWins: top ? top.n : 0, named: aw.length,
      recommendation: recommendationOf(d, r.segment),
      /* the assessment row's card key, so the review copy can approve the recommendation */
      assessmentSrc: (assessmentOf(d, r.segment) || {})._src || null,
      pending: { n: pend.length, totals: valueTotals(pend, TENDER_FIELDS), titles: pend.map((t) => t.title) },
      latest: latestSignal.get(r.segment) || null,
    };
  }).filter((r) => r.recent || r.before || r.open).sort((a, b) => b.open - a.open || b.recent - a.recent || a.segment.localeCompare(b.segment));
}

/* winner names are compared as stored, ignoring case and surrounding space only */
const winnerKey = (n) => String(n || "").trim().toLowerCase();

/* ---- 2. who wins ---- */
export function winners(d) {
  const all = d.awards || [];
  const won = all.filter((a) => a.winner);
  const priced = won.filter((a) => hasAmount(a, AWARD_FIELDS));
  const by = new Map();
  won.forEach((a) => {
    const k = winnerKey(a.winner);
    const r = by.get(k) || { winner: a.winner, wins: 0, awards: [], brand: null, buyers: new Set() };
    r.wins += 1;
    r.awards.push(a);
    if (a.buyer) r.buyers.add(a.buyer);
    if (!r.brand && a.brand) r.brand = a.brand;
    by.set(k, r);
  });
  /* one total per stored currency for each winner and overall; no conversion, so no share of value either */
  const rows = [...by.values()].map(({ awards, ...r }) => ({ ...r, buyers: [...r.buyers], totals: valueTotals(awards, AWARD_FIELDS) }))
    .sort((a, b) => b.wins - a.wins || String(a.winner).localeCompare(String(b.winner)));
  return { records: all.length, named: won.length, priced: priced.length, totals: valueTotals(priced, AWARD_FIELDS), rows };
}

/* ---- 3. repeat buyers: a buyer with two or more tenders or awards ---- */
const buyerName = (s) => String(s == null ? "" : s).trim();
export function buyers(d) {
  const by = new Map();
  const get = (name) => by.get(name) || { buyer: name, tenders: [], awards: 0, segments: new Set(), dates: [] };
  (d.tenders || []).forEach((t) => {
    const name = buyerName(t.issuer);
    if (!name) return;
    const r = get(name);
    r.tenders.push(t);
    if (segmentOf(t.cat)) r.segments.add(segmentOf(t.cat));
    const dt = tenderDate(t);
    if (dt) r.dates.push(dt.getTime());
    by.set(name, r);
  });
  (d.awards || []).forEach((a) => {
    const name = buyerName(a.buyer);
    if (!name) return;
    const r = get(name);
    r.awards += 1;
    if (segmentOf(a.segment)) r.segments.add(segmentOf(a.segment));
    const dt = asDate(a.date);
    if (dt) r.dates.push(dt.getTime());
    by.set(name, r);
  });
  return [...by.values()].filter((r) => r.tenders.length + r.awards >= 2).map((r) => {
    const last = r.dates.length ? new Date(Math.max(...r.dates)) : null;
    return { buyer: r.buyer, tenders: r.tenders.length, awards: r.awards, count: r.tenders.length + r.awards,
      totals: valueTotals(r.tenders, TENDER_FIELDS), segments: [...r.segments], last };
  }).sort((a, b) => b.count - a.count || a.buyer.localeCompare(b.buyer));
}

/* ---- 4. what is driving it: market news by location and segment, beside the tenders in the same place ---- */
export function drivers(d) {
  const by = new Map();
  (d.marketCards || []).forEach((c) => {
    const m = cardMeta(c);
    if (!m.country || !m.segment) return;
    const seg = segmentOf(m.segment);
    const key = `${m.country}||${seg}`;
    const r = by.get(key) || { country: m.country, segment: seg, signals: [], tenders: [] };
    r.signals.push({ kind: m.kind, title: c.title, date: m.date });
    by.set(key, r);
  });
  /* a tender is in the same place when its country is one of the comma-separated parts of the signal's location */
  by.forEach((r) => {
    const parts = r.country.split(",").map((x) => x.trim());
    r.tenders = (d.tenders || []).filter((t) => segmentOf(t.cat) === r.segment && parts.some((p) => same(p, t.country)));
  });
  by.forEach((r) => r.signals.sort((a, b) => ((b.date && b.date.getTime()) || 0) - ((a.date && a.date.getTime()) || 0)));
  return [...by.values()].map((r) => ({ country: r.country, segment: r.segment, signals: r.signals, tenders: r.tenders.length, totals: valueTotals(r.tenders, TENDER_FIELDS) }))
    .sort((a, b) => b.signals.length - a.signals.length || b.tenders - a.tenders || a.country.localeCompare(b.country));
}

export function outlook(d, openTenders, today = new Date(), closedTenders = []) {
  return { segments: segments(d, openTenders, today, closedTenders), winners: winners(d), buyers: buyers(d), drivers: drivers(d) };
}
