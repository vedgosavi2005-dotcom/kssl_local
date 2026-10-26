/* MARKET OUTLOOK: where demand is heading, who wins, which calibres buyers ask for, who re-tenders, what drives it.

   Every figure is counted from records the dataset serves and each section says which records it used:
     tenders      data.tenders (published_date or closing_date from the row's requirement codes, category `cat`)
     projects     data.topOpportunities.projectsBeforeTender (stored projects to win before they tender); a project's
                  segment is the stored category of its opportunity, read off that opportunity's market card
     awards       data.awards (winner, value + currency, buyer, segment, date or year)
     signals      data.marketCards that are not tenders (meta "Kind · Location · Segment · date")
   Nothing is invented. A date a record does not carry is not guessed: a year-only award counts as an award, not as
   activity in a month. Values are the stored amounts; a share of value is counted in rupees with stored exchange rates
   only (lib/tenderValue inrSum), and an amount with no stored rate is left out of the share. A segment is the stored
   category text, as it is. The "what to do" sentence per segment is a stored judgement
   (serving.market_segment_assessment.recommendation); a segment without one has none. No trend word, forecast or
   next-round date is computed here: the windows are counted and the signed change is plain arithmetic. */

import { AWARD_FIELDS, TENDER_FIELDS, hasAmount, inrSum, valueTotals } from "./tenderValue.js";

const DAY = 86400000;
export const WINDOW_DAYS = 183;      // label only: the windows are whole calendar months, the same 12 months the detail chart draws
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
export const reqVal = (t, code) => ((t.req || []).find((r) => r[0] === code) || [])[1];
export const tenderDate = (t) => asDate(reqVal(t, "published_date")) || asDate(reqVal(t, "closing_date")) || asDate(t.closingDate);

/* the stored segment text, trimmed; "" when the record names none */
export const segmentOf = (s) => (s == null ? "" : String(s).trim());

/* a market card's meta, joined from stored fields: "Kind · Location · Segment · date" (or without a segment) */
export function cardMeta(c) {
  const p = String((c && c.meta) || "").split(" · ").map((x) => x.trim());
  const date = asDate(p[p.length - 1]);
  return { kind: p[0] || "", country: p[1] || "", segment: p.length > 3 ? p[2] : "", date };
}

export const fits = (t) => t.clientFit === "strong" || t.clientFit === "partial";
const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();

/* the last six calendar months (this one and the five before) and the six before those, as [from, to] instants */
export function windows(today) {
  const y = today.getUTCFullYear(), mo = today.getUTCMonth();
  const end = Date.UTC(y, mo + 1, 1) - 1;
  const cut = Date.UTC(y, mo - 5, 1) - 1;
  const cut2 = Date.UTC(y, mo - 11, 1) - 1;
  return { end, cut, cut2 };
}

/* the stored recommendation for a segment, or null */
export function assessmentOf(d, segment) {
  const rows = (d && d.database && d.database.serving && d.database.serving.market_segment_assessment) || [];
  return rows.find((x) => same(x.segment, segment)) || null;
}
export function recommendationOf(d, segment) {
  const r = assessmentOf(d, segment);
  return r && r.recommendation != null && String(r.recommendation).trim() ? String(r.recommendation).trim() : null;
}

/* the client's own names (data.client and its own company row), so its wins are not counted as a rival's */
export function clientNames(d) {
  const c = (d && d.client) || {};
  const own = (d && d.competitors && c.id != null && d.competitors[c.id]) || {};
  return [c.name, c.short, own.name].filter(Boolean).map((x) => String(x).trim().toLowerCase());
}
const wordIn = (hay, needle) => !!needle && new RegExp(`(^|[^a-z0-9])${needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^a-z0-9])`, "i").test(hay);
export const isClientName = (d, s) => clientNames(d).some((n) => wordIn(String(s || ""), n));

/* projects to win before they tender, each with the stored category of its opportunity (null when no card names one) */
export function projectRows(d) {
  const cat = new Map();
  (d.marketCards || []).forEach((c) => {
    const s = c && c._src;
    if (s && s.t === "market_opportunity" && c.tags) cat.set(String(s.id), c.tags);
  });
  return ((d.topOpportunities && d.topOpportunities.projectsBeforeTender) || []).map((p) => ({
    ...p, cat: cat.get(String(p.opportunityId)) || null, clientFit: p.ksslFit || null, pursuit: true,
  }));
}

/* winner names are compared as stored, ignoring case and surrounding space only */
export const winnerKey = (n) => String(n || "").trim().toLowerCase();

/* ---- 1. where demand is heading, by segment ---- */
export function segments(d, openTenders, today = new Date(), closedTenders = []) {
  const { end, cut, cut2 } = windows(today);
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
      if (t <= end && t > cut) r.recent += 1;
      else if (t <= cut && t > cut2) r.before += 1;
    }
    by.set(seg, r);
  };
  (d.tenders || []).forEach((t) => bump(segmentOf(t.cat), tenderDate(t), "tenders"));
  (d.marketCards || []).map(cardMeta).filter((m) => m.segment).forEach((m) => bump(segmentOf(m.segment), m.date, "signals"));
  (d.awards || []).forEach((a) => bump(segmentOf(a.segment), asDate(a.date), "awards"));

  const fit = (openTenders || []).filter(fits);
  const projects = projectRows(d).filter(fits);
  // closed for bids, award not yet made or published
  const waiting = (closedTenders || []).filter((t) => fits(t) && String(t.status || "").toLowerCase() !== "awarded");
  // "who wins here" is the rivals: the client's own wins are not counted
  const won = (d.awards || []).filter((a) => a.winner && !isClientName(d, `${a.winner} ${a.brand || ""}`));
  const latestSignal = new Map();
  (d.marketCards || []).forEach((c) => {
    const m = cardMeta(c);
    if (!m.segment) return;
    const seg = segmentOf(m.segment);
    const cur = latestSignal.get(seg);
    if (!cur || (m.date && (!cur.date || m.date > cur.date))) latestSignal.set(seg, { title: c.title, kind: m.kind, country: m.country, date: m.date, url: c.url });
  });
  return [...by.values()].map((r) => {
    const mine = fit.filter((t) => segmentOf(t.cat) === r.segment);
    const projectRowsHere = projects.filter((t) => segmentOf(t.cat) === r.segment);
    const aw = won.filter((a) => segmentOf(a.segment) === r.segment);
    /* the leading winner: the most award value in rupees (stored rates), then the most awards */
    const wins = new Map();
    aw.forEach((a) => {
      const k = winnerKey(a.winner);
      const cur = wins.get(k) || { name: a.winner, n: 0, awards: [] };
      cur.n += 1;
      cur.awards.push(a);
      wins.set(k, cur);
    });
    const ranked = [...wins.values()].map((w) => ({ ...w, inr: inrSum(valueTotals(w.awards, AWARD_FIELDS)) || 0 }))
      .sort((a, b) => b.inr - a.inr || b.n - a.n || String(a.name).localeCompare(String(b.name)));
    const top = ranked[0];
    const totalInr = ranked.reduce((n, w) => n + w.inr, 0);
    const pend = waiting.filter((t) => segmentOf(t.cat) === r.segment);
    return {
      segment: r.segment, recent: r.recent, before: r.before,
      /* the signed percentage change between the two counted windows; no change is called when the earlier one is empty */
      change: r.before > 0 ? Math.round(((r.recent - r.before) / r.before) * 100) : null,
      records: { tenders: r.tenders, signals: r.signals, awards: r.awards },
      open: mine.length, totals: valueTotals(mine, TENDER_FIELDS),
      projects: projectRowsHere.length,
      winner: top ? top.name : null,
      winnerShare: top && totalInr && top.inr ? top.inr / totalInr : null,
      winnerWins: top ? top.n : 0, named: aw.length,
      recommendation: recommendationOf(d, r.segment),
      /* the assessment row's card key, so the review copy can approve the recommendation */
      assessmentSrc: (assessmentOf(d, r.segment) || {})._src || null,
      pending: { n: pend.length, totals: valueTotals(pend, TENDER_FIELDS), titles: pend.map((t) => t.title) },
      latest: latestSignal.get(r.segment) || null,
    };
  }).filter((r) => r.recent || r.before || r.open || r.projects).sort((a, b) => b.open - a.open || b.recent - a.recent || a.segment.localeCompare(b.segment));
}

/* ---- 2. who wins ---- */
export function winners(d) {
  const all = (d.awards || []).filter((a) => !isClientName(d, `${a.winner || ""} ${a.brand || ""}`));
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
  const totals = valueTotals(priced, AWARD_FIELDS);
  const totalInr = inrSum(totals);
  /* ranked by award value in rupees (stored rates), then by number of wins */
  const rows = [...by.values()].map(({ awards, ...r }) => {
    const t = valueTotals(awards, AWARD_FIELDS);
    const inr = inrSum(t);
    return { ...r, buyers: [...r.buyers], totals: t, inr, share: totalInr && inr ? inr / totalInr : null };
  }).sort((a, b) => (b.inr || 0) - (a.inr || 0) || b.wins - a.wins || String(a.winner).localeCompare(String(b.winner)));
  return { records: all.length, named: won.length, priced: priced.length, totals, totalInr, rows };
}

/* ---- 3. calibres buyers ask for, against the client's catalogue ----
   A tender's calibre is the millimetre figure its title (or stored equipment scope) states: "155 mm", "7.62 x 51 mm"
   reads 7.62. A client product covers it when its stored Calibre spec names the same figure, or a range holding it
   ("70 to 155 mm"), in the same category. Calibres stated only in inches are not read. */
const CAL = /(\d{1,3}(?:\.\d{1,2})?)\s*(?:x\s*\d{1,3}(?:\.\d{1,2})?\s*)?mm\b/gi;
const RANGE = /(\d{1,3}(?:\.\d{1,2})?)\s*(?:mm)?\s*(?:to|-|–)\s*(\d{1,3}(?:\.\d{1,2})?)\s*mm\b/i;
export function calibresIn(text) {
  const out = new Set();
  String(text || "").replace(CAL, (_, n) => { const v = Number(n); if (v >= 4 && v <= 400) out.add(v); return _; });
  return [...out];
}
export const calText = (v) => `${Number.isInteger(v) ? v : String(v)} mm`;
const specVals = (p, label) => {
  const sh = (p && p.sheet) || {};
  const rows = ["key", "other", "armament"].flatMap((s) => (Array.isArray(sh[s]) ? sh[s] : []));
  return rows.filter((r) => same(r.l, label)).flatMap((r) => (Array.isArray(r.v) ? r.v : [r.v])).map(String);
};
/* every catalogue product with a stored calibre: [{ own, company, name, cat, cals: [v], ranges: [[lo, hi]] }];
   `own` marks the client's own products */
export function productCalibres(d) {
  const cid = d && d.client && d.client.id != null ? String(d.client.id) : null;
  return Object.entries((d && d.competitors) || {}).flatMap(([id, co]) => (co.products || []).map((p) => {
    const vals = specVals(p, "Calibre");
    const ranges = vals.map((v) => RANGE.exec(v)).filter(Boolean).map((m) => [Number(m[1]), Number(m[2])]);
    return { own: id === cid, company: co.name || id, name: p.displayName || p.name, cat: p.category || null, cals: [...new Set(vals.flatMap(calibresIn))], ranges };
  })).filter((p) => p.cals.length || p.ranges.length);
}
export const clientCalibres = (d) => productCalibres(d).filter((p) => p.own);
export const covers = (p, v) => p.cals.some((x) => Math.abs(x - v) < 0.01) || p.ranges.some(([lo, hi]) => v >= lo && v <= hi);
export function calibres(d, openTenders) {
  const all0 = productCalibres(d);
  const cat = all0.filter((p) => p.own);
  /* a millimetre figure counts as a calibre only when some catalogue product (any company) states it as its calibre:
     "210 mm" in a forging or pipe tender is a dimension, not a calibre */
  const known = all0.flatMap((p) => p.cals);
  const isCal = (v) => known.some((x) => Math.abs(x - v) < 0.01);
  const rows = new Map();
  let read = 0;
  const all = [...(openTenders || []), ...projectRows(d)];
  all.forEach((t) => {
    const vs = calibresIn(`${t.title || ""} ${reqVal(t, "equipment_scope") || ""}`).filter(isCal);
    if (!vs.length) return;
    read += 1;
    vs.forEach((v) => {
      const seg = segmentOf(t.cat) || null;
      const key = `${calText(v)}${seg ? ` · ${seg}` : ""}`;
      const r = rows.get(key) || { key, cal: v, cat: seg, tenders: 0, projects: 0, items: [] };
      if (t.pursuit) r.projects += 1; else r.tenders += 1;
      r.items.push(t);
      rows.set(key, r);
    });
  });
  const out = [...rows.values()].map((r) => {
    const models = cat.filter((p) => (!r.cat || same(p.cat, r.cat)) && covers(p, r.cal)).map((p) => p.name);
    return { ...r, totals: valueTotals(r.items.filter((t) => !t.pursuit), TENDER_FIELDS), models, covered: models.length > 0 };
  }).sort((a, b) => b.tenders + b.projects - (a.tenders + a.projects) || a.cal - b.cal);
  return { read, ranked: all.length, rows: out, catalogue: all0 };
}

/* ---- 4. repeat buyers: a buyer with two or more tenders or awards ---- */
const buyerName = (s) => String(s == null ? "" : s).trim();
/* `openTenders`: the page's own open set (bucketTenders), so "open" means the same rows everywhere; without it the
   stored status open / closing is read */
const openTest = (openTenders) => {
  if (openTenders) { const set = new Set(openTenders); return (t) => set.has(t); }
  return (t) => ["open", "closing"].includes(String(t.status || "").toLowerCase());
};
export function buyers(d, today = new Date(), openTenders = null) {
  const by = new Map();
  const get = (name) => by.get(name) || { buyer: name, tenders: [], awards: [], segments: new Set(), dates: [] };
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
    r.awards.push(a);
    if (segmentOf(a.segment)) r.segments.add(segmentOf(a.segment));
    const dt = asDate(a.date);
    if (dt) r.dates.push(dt.getTime());
    by.set(name, r);
  });
  const isOpen = openTest(openTenders);
  return [...by.values()].filter((r) => r.tenders.length + r.awards.length >= 2).map((r) => {
    const last = r.dates.length ? new Date(Math.max(...r.dates.filter((x) => x <= today.getTime()).concat([-Infinity]))) : null;
    const openT = r.tenders.filter(isOpen);
    /* the next stored bid deadline of an open tender, a fact on the record; nothing is forecast */
    const deadlines = openT.map((t) => asDate(t.closingDate || reqVal(t, "closing_date"))).filter((x) => x && x >= today).map((x) => x.getTime());
    const pricedAw = r.awards.filter((a) => hasAmount(a, AWARD_FIELDS));
    return { buyer: r.buyer, tenders: r.tenders.length, awards: r.awards.length, count: r.tenders.length + r.awards.length,
      openN: openT.length, withWinner: r.awards.filter((a) => a.winner).length,
      totals: valueTotals(r.tenders, TENDER_FIELDS), openTotals: valueTotals(openT, TENDER_FIELDS),
      awardTotals: valueTotals(pricedAw, AWARD_FIELDS), pricedAwards: pricedAw.length,
      segments: [...r.segments], last: last && Number.isFinite(last.getTime()) ? last : null,
      nextDeadline: deadlines.length ? new Date(Math.min(...deadlines)) : null };
  }).sort((a, b) => b.count - a.count || a.buyer.localeCompare(b.buyer));
}

/* ---- 5. what is driving it: market news by location and segment, beside the tenders in the same place ---- */
export function drivers(d, openTenders = null) {
  const by = new Map();
  (d.marketCards || []).forEach((c) => {
    const m = cardMeta(c);
    if (!m.country || !m.segment) return;
    const seg = segmentOf(m.segment);
    const key = `${m.country}||${seg}`;
    const r = by.get(key) || { country: m.country, segment: seg, signals: [], tenders: [] };
    r.signals.push({ kind: m.kind, title: c.title, date: m.date, url: c.url });
    by.set(key, r);
  });
  /* a tender is in the same place when its country is one of the comma-separated parts of the signal's location */
  const projects = projectRows(d);
  const isOpen = openTest(openTenders);
  by.forEach((r) => {
    const parts = r.country.split(/[,;]/).map((x) => x.trim());
    const here = (t) => segmentOf(t.cat) === r.segment && parts.some((p) => same(p, t.country));
    r.tenders = (d.tenders || []).filter(here);
    r.projects = projects.filter(here);
  });
  by.forEach((r) => r.signals.sort((a, b) => ((b.date && b.date.getTime()) || 0) - ((a.date && a.date.getTime()) || 0)));
  return [...by.values()].map((r) => ({ country: r.country, segment: r.segment, signals: r.signals, tenders: r.tenders.length,
    openN: r.tenders.filter(isOpen).length, projects: r.projects.length, totals: valueTotals(r.tenders.filter(isOpen), TENDER_FIELDS) }))
    .sort((a, b) => b.signals.length - a.signals.length || b.tenders - a.tenders || a.country.localeCompare(b.country));
}

export function outlook(d, openTenders, today = new Date(), closedTenders = []) {
  return { segments: segments(d, openTenders, today, closedTenders), winners: winners(d), calibres: calibres(d, openTenders),
    buyers: buyers(d, today, openTenders), drivers: drivers(d, openTenders) };
}

export { DAY };
