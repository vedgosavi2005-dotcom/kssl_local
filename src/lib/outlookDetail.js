/* MARKET OUTLOOK DETAIL: the analytics behind one row of the Market outlook tables (segment, winner, calibre, buyer,
   driver), drawn by components/marketOutlook/OutlookPanel.jsx.
   Pure functions over the served dataset; every number is counted from records the dataset carries, every date a
   record does not carry is left out of the charts rather than guessed. Values are the stored amounts, shown in rupees
   with stored exchange rates only (lib/tenderValue). No trend word, forecast or recommendation is written here: the
   one stored recommendation per segment is shown by the table. Company scale is SIPRI's Top 100 row (data.sipriArms),
   cited to SIPRI. */
import {
  asDate, tenderDate, segmentOf, cardMeta, winnerKey, isClientName, projectRows, productCalibres, covers,
  calibresIn, calText, fits,
} from "./marketOutlook.js";
import { bucketTenders } from "./overview.js";
import { AWARD_FIELDS, TENDER_FIELDS, amountText, formatTotals, hasAmount, inrSum, rupees, valueTotals } from "./tenderValue.js";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const iso = (d) => (d ? d.toISOString().slice(0, 10) : null);
const client = (d) => (d.client && (d.client.short || d.client.name)) || "the client";
const tVal = (list) => formatTotals(valueTotals(list, TENDER_FIELDS));
const aVal = (list) => formatTotals(valueTotals(list, AWARD_FIELDS));

/* months back from today: [{key, label}] oldest first */
export function monthAxis(today, n = 12) {
  const out = [];
  for (let i = n - 1; i >= 0; i -= 1) {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - i, 1));
    out.push({ key: `${d.getUTCFullYear()}-${d.getUTCMonth()}`, label: `${MON[d.getUTCMonth()]}${d.getUTCMonth() === 0 || i === n - 1 ? " " + String(d.getUTCFullYear()).slice(2) : ""}` });
  }
  return out;
}
const mkey = (d) => `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
/* groups: [{ name, dates: [Date|null], total }] -> per-month counts for the panel chart */
export function series(today, groups) {
  const axis = monthAxis(today);
  const rows = axis.map((m) => ({ label: m.label, v: groups.map(() => 0) }));
  const idx = new Map(axis.map((m, i) => [m.key, i]));
  let dated = 0;
  groups.forEach((g, gi) => g.dates.forEach((d) => {
    if (d && idx.has(mkey(d))) { rows[idx.get(mkey(d))].v[gi] += 1; dated += 1; }
  }));
  return { rows, names: groups.map((g) => g.name), dated, undated: groups.reduce((n, g) => n + g.total, 0) - dated };
}
const undatedNote = (ser, w = "record") => (ser.undated ? `${plural(ser.undated, w)} carry no month in the last 12 months and are not charted.` : null);

const fitWord = (f) => (f ? `${f} fit` : null);
/* a tender (or a project to win) as a panel row; a tender opens its page, a project its source */
export const tenderLine = (t) => ({
  title: t.title, sub: [t.country, t.issuer].filter(Boolean).join(" · "),
  right: amountText(t.valueAmount, t.valueCurrency), tag: t.pursuit ? "project" : fitWord(t.clientFit),
  date: t.pursuit ? null : t.closingDate ? `closes ${t.closingDate}` : null,
  id: t.pursuit ? null : t.id, url: t.pursuit ? ((t.sources || [])[0] || {}).url : null,
});
export const awardLine = (a) => ({
  title: a.programme || a.title, sub: [a.winner, a.brand, a.buyer, a.country].filter(Boolean).join(" · "),
  right: amountText(a.value, a.currency) || a.value_text || null, date: a.date || (a.year ? String(a.year) : null), url: a.url,
});

/* the tracked company a name belongs to: its full name (or the name in its brackets) as whole words in the text */
const namesOf = (n) => {
  const s = String(n || "");
  return [s.replace(/\s*\([^)]*\)\s*/g, " ").trim(), (s.match(/\(([^)]+)\)/) || [])[1]].filter((x) => x && x.length >= 3);
};
const hasWords = (hay, w) => new RegExp(`(^|[^a-z0-9])${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^a-z0-9])`, "i").test(hay);
export function companyOf(d, text) {
  const s = String(text || "");
  const hit = Object.entries(d.competitors || {}).find(([cid, c]) => String(cid) !== String((d.client || {}).id) && namesOf(c.name).some((w) => hasWords(s, w)));
  return hit ? { cid: hit[0], name: hit[1].name } : null;
}

/* the companies whose products the stored competitor-fit assessments put against these tenders */
export function activeRows(list, n = 8) {
  const by = new Map();
  list.forEach((t) => (t.competitorFit || []).forEach((f) => {
    if (!f.company) return;
    const r = by.get(f.company) || { company: f.company, tenders: new Set(), products: new Set(), fits: new Map(), why: f.why };
    r.tenders.add(t.id || t.title);
    (f.products || []).forEach((p) => r.products.add(p));
    if (f.fit) r.fits.set(f.fit, (r.fits.get(f.fit) || 0) + 1);
    by.set(f.company, r);
  }));
  return [...by.values()].sort((a, b) => b.tenders.size - a.tenders.size || a.company.localeCompare(b.company)).slice(0, n).map((r) => ({
    title: r.company, right: plural(r.tenders.size, "tender"),
    fields: [["Products", [...r.products].slice(0, 4).join(", ") || "not stated"], ["Fit", [...r.fits.entries()].map(([k, v]) => `${v} ${k}`).join(" · ") || "not stated"], ["Why", r.why || "not stated"]],
  }));
}

/* SIPRI Top 100 rows for the tracked companies among these names: rank and arms revenue, as SIPRI states them */
export function sipriRows(d, names) {
  const seen = new Set();
  return names.map((n) => companyOf(d, n)).filter((c) => c && !seen.has(c.cid) && seen.add(c.cid)).map((c) => {
    const s = (d.sipriArms || {})[c.cid];
    if (!s || !s.armsUsdM) return null;
    return { title: `${c.name} · SIPRI Top 100 #${s.rank} (${s.year})`, sub: `arms revenue US$ ${Number(s.armsUsdM).toLocaleString("en-US")} m${s.share ? ` · ${Math.round(s.share * 100)}% of its total revenue` : ""} · global, not this market`,
      right: `US$ ${(s.armsUsdM / 1000).toFixed(1)} bn`, url: s.source && s.source.url };
  }).filter(Boolean);
}

const tile = (k, v, sub) => ({ k, v, sub });
const sigRows = (d, sigs) => sigs.map((x) => ({ title: x.title, sub: [x.kind ? x.kind.replace(/_/g, " ") : null, x.country, iso(x.date)].filter(Boolean).join(" · "), url: x.url }));
const LAGGED = (d) => `Not established: no ${client(d)} bid, evaluation or rejection record is stored, so no loss or gap can be stated. An award to a rival does not show a ${client(d)} loss.`;

/* ---------------------------------------------------------------- segment */
export function segmentDetail(d, seg, row, today = new Date()) {
  const { open, closed } = bucketTenders(d.tenders || []);
  const inSeg = (t) => segmentOf(t.cat) === seg;
  // the same rows the table counts (lib/marketOutlook segments)
  const openT = open.filter((t) => inSeg(t) && fits(t));
  const proj = projectRows(d).filter((t) => inSeg(t) && fits(t));
  const closedAll = closed.filter(inSeg);
  const closedT = closedAll.filter((t) => fits(t) && String(t.status || "").toLowerCase() !== "awarded");
  const aw = (d.awards || []).filter((a) => segmentOf(a.segment) === seg);
  const win = aw.filter((a) => a.winner);
  const mine = win.filter((a) => isClientName(d, `${a.winner} ${a.brand || ""}`));
  const rivals = win.filter((a) => !isClientName(d, `${a.winner} ${a.brand || ""}`));
  const byWinner = new Map();
  rivals.forEach((a) => { const k = winnerKey(a.winner); const r = byWinner.get(k) || { name: a.winner, brand: a.brand, list: [] }; r.list.push(a); byWinner.set(k, r); });
  const rivalRows = [...byWinner.values()].map((r) => ({ ...r, inr: inrSum(valueTotals(r.list, AWARD_FIELDS)) || 0 })).sort((a, b) => b.inr - a.inr || b.list.length - a.list.length);
  const totalInr = rivalRows.reduce((n, r) => n + r.inr, 0);
  const published = (d.tenders || []).filter(inSeg).map(tenderDate);
  const sig = (d.marketCards || []).map((c) => ({ ...cardMeta(c), title: c.title, url: c.url })).filter((x) => x.segment && segmentOf(x.segment) === seg)
    .sort((a, b) => ((b.date && b.date.getTime()) || 0) - ((a.date && a.date.getTime()) || 0));
  // the same three record kinds the table counts, so the bars and the table cannot disagree
  const ser = series(today, [{ name: "Tenders published", dates: published, total: published.length }, { name: "Market signals", dates: sig.map((x) => x.date), total: sig.length }, { name: "Awards", dates: aw.map((a) => asDate(a.date)), total: aw.length }]);
  const allHere = (d.tenders || []).filter(inSeg);
  const active = activeRows([...openT, ...allHere.filter((t) => !openT.includes(t))], 8);
  const change = row && row.change != null ? ` (${row.change > 0 ? "+" : ""}${row.change}%)` : "";
  return {
    kind: "segment", title: seg,
    subtitle: row ? `${row.recent} records in the last 6 months, ${row.before} in the 6 months before${change}` : "",
    tiles: [tile("Open tenders that fit", openT.length, openT.length ? `${tVal(openT)} stated value` : "none open"),
      tile("Projects to win", proj.length, proj.length ? "before they tender" : "none on record"),
      tile("Closed, awaiting award", closedT.length, closedAll.length > closedT.length ? `${closedAll.length - closedT.length} other closed, not counted in the table` : ""),
      tile("Rival awards", rivals.length, rivals.length ? aVal(rivals) : "no award on record"),
      tile(`Won by ${client(d)}`, mine.length, mine.length ? aVal(mine) : `no ${client(d)} award on record`),
      tile("Rivals assessed here", active.length, "companies with a stored fit on its tenders")],
    charts: [{ title: "How often tenders are published", sub: `per month, last 12 months · ${row ? `${row.recent} records in the last 6 months, ${row.before} in the 6 before` : ""}`, ...ser, halves: true, note: undatedNote(ser) }],
    sections: [
      { h: "Who is winning here", note: `${plural(rivals.length, "rival award")} with a named winner · ranked by value in rupees, then count`, rows: rivalRows.slice(0, 6).map((r) => ({ title: r.name, sub: [r.brand, plural(r.list.length, "award")].filter(Boolean).join(" · "), right: r.inr ? rupees(r.inr) : null, bar: totalInr && r.inr ? r.inr / totalInr : null })), empty: "No award with a named winner in this segment." },
      { h: "Contracts on record", note: "awards in this segment, newest first", rows: [...aw].sort((a, b) => (asDate(b.date) || 0) - (asDate(a.date) || 0)).slice(0, 12).map(awardLine), empty: "No award on record in this segment." },
      { h: "Competitors active here", note: "the stored competitor-fit assessments on this segment's tenders, open first", rows: active, empty: "No competitor fit is stored for this segment's tenders." },
      { h: "How big the competitors are", note: "SIPRI Top 100 arms revenue; global figures", rows: sipriRows(d, [...active.map((r) => r.title), ...rivalRows.map((r) => r.name)]).slice(0, 6), empty: "" },
      { h: `Where ${client(d)} lagged`, rows: [], empty: LAGGED(d) },
      { h: "Open now", note: "open tenders with a strong or partial fit, as counted in the table", rows: openT.map(tenderLine), empty: proj.length ? `No open tender fits. ${plural(proj.length, "project lead")} are listed below.` : "No open tender with a strong or partial fit in this segment." },
      { h: "Closed, awaiting award", note: "closed for bids; no winner published yet, and none is inferred", rows: closedT.map(tenderLine), empty: "" },
      { h: "Projects to win", note: "stored projects before they tender, with their stored fit", rows: proj.map(tenderLine), empty: "" },
      { h: "Latest signals", rows: sigRows(d, sig.slice(0, 5)), empty: "" },
    ],
  };
}

/* ----------------------------------------------------------------- winner */
export function winnerDetail(d, name, row, today = new Date()) {
  const k = winnerKey(name);
  const aw = (d.awards || []).filter((a) => winnerKey(a.winner) === k);
  const buyers = [...new Set(aw.map((a) => String(a.buyer || "").trim()).filter(Boolean))];
  const countries = [...new Set(aw.map((a) => a.country).filter(Boolean))];
  const segs = new Map();
  aw.forEach((a) => { const s = segmentOf(a.segment) || "Segment not stated"; const r = segs.get(s) || { s, list: [] }; r.list.push(a); segs.set(s, r); });
  const segRows = [...segs.values()].map((r) => ({ ...r, inr: inrSum(valueTotals(r.list, AWARD_FIELDS)) || 0 })).sort((a, b) => b.inr - a.inr || b.list.length - a.list.length);
  const priced = aw.filter((a) => hasAmount(a, AWARD_FIELDS));
  const total = inrSum(valueTotals(priced, AWARD_FIELDS));
  const inrOne = (a) => inrSum(valueTotals([a], AWARD_FIELDS));
  const big = [...priced].sort((a, b) => (inrOne(b) || 0) - (inrOne(a) || 0))[0];
  const last = aw.map((a) => asDate(a.date)).filter(Boolean).sort((a, b) => b - a)[0];
  const ser = series(today, [{ name: "Awards", dates: aw.map((a) => asDate(a.date)), total: aw.length }]);
  const lines = [
    `${name} ${row && row.share != null ? `holds ${Math.round(row.share * 100)}% of the rival award value counted in rupees` : "has no award value that can be counted in rupees"}, with ${plural(aw.length, "award")}${total ? ` worth ${rupees(total)}` : ""}.`,
    priced.length && total ? `Average stated award ${rupees(total / priced.length)}; largest ${amountText(big.value, big.currency)} (${big.programme || big.title}).` : "None of its awards states a value.",
    `${segRows[0] ? `Most awards in ${segRows[0].s} (${plural(segRows[0].list.length, "award")})` : "No segment recorded"}; ${countries.length ? `in ${countries.join(", ")}` : "no country recorded"}${last ? `; latest award ${iso(last)}` : ""}.`,
    `No ${client(d)} bid against this winner is stored, so no head-to-head result can be stated.`,
  ];
  return {
    kind: "winner", title: name, subtitle: [row && row.brand, countries.join(", ")].filter(Boolean).join(" · "),
    tiles: [tile("Awards won", aw.length, `${priced.length} with a stated value`), tile("Value won", total ? rupees(total) : "—", row && row.share != null ? `${Math.round(row.share * 100)}% of priced rival awards` : ""),
      tile("Buyers served", buyers.length, buyers.slice(0, 2).join(", ")), tile("Countries", countries.length, countries.slice(0, 3).join(", ")),
      tile("Segments", segs.size, segRows.map((x) => x.s).slice(0, 3).join(", ")), ...((row && row.brand) ? [tile("Brand", row.brand, "")] : [])],
    charts: [{ title: "When they won", sub: "awards per month, last 12 months", ...ser, note: undatedNote(ser, "award") }],
    sections: [
      { h: "In figures", note: "counted from the awards on record; values in rupees at stored rates", lines },
      { h: "How big they are", note: "SIPRI Top 100 arms revenue; global figures", rows: sipriRows(d, [name, ...aw.map((a) => a.brand || "")]), empty: "" },
      { h: "Contracts won", rows: [...aw].sort((a, b) => (asDate(b.date) || 0) - (asDate(a.date) || 0)).map(awardLine), empty: "" },
      { h: "Where they win", note: "by segment", rows: segRows.map((r) => ({ title: r.s, sub: plural(r.list.length, "award"), right: r.inr ? rupees(r.inr) : null, bar: total && r.inr ? r.inr / total : null })), empty: "" },
      { h: "Buyers", rows: buyers.map((b) => ({ title: b })), empty: "" },
    ],
  };
}

/* ---------------------------------------------------------------- calibre */
export function calibreDetail(d, row, cal, today = new Date()) {
  if (!row) return null;
  const items = row.items || [];
  const open = items.filter((t) => !t.pursuit);
  const proj = items.filter((t) => t.pursuit);
  const segOk = (s) => !row.cat || same(segmentOf(s), row.cat);
  const aw = (d.awards || []).filter((a) => !isClientName(d, `${a.winner || ""} ${a.brand || ""}`) && segOk(a.segment) && calibresIn(`${a.title || ""} ${a.programme || ""}`).some((v) => Math.abs(v - row.cal) < 0.01));
  const ser = series(today, [{ name: "Tenders", dates: open.map(tenderDate), total: open.length }, { name: "Awards", dates: aw.map((a) => asDate(a.date)), total: aw.length }]);
  const cat = ((cal && cal.catalogue) || productCalibres(d)).filter((p) => (!row.cat || same(p.cat, row.cat)) && covers(p, row.cal));
  const mine = cat.filter((p) => p.own);
  const rivals = cat.filter((p) => !p.own);
  const byWinner = new Map();
  aw.filter((a) => a.winner).forEach((a) => { const k = winnerKey(a.winner); const r = byWinner.get(k) || { name: a.winner, list: [] }; r.list.push(a); byWinner.set(k, r); });
  const countries = [...new Set(items.map((t) => t.country).filter(Boolean))];
  const buyers = [...new Set(items.map((t) => String(t.issuer || "").trim()).filter(Boolean))];
  const next = open.map((t) => asDate(t.closingDate)).filter((x) => x && x >= today).sort((a, b) => a - b)[0];
  const lines = [
    `${plural(open.length, "open tender")} and ${plural(proj.length, "project lead")} name ${row.key}${countries.length ? `, in ${countries.join(", ")}` : ""}.`,
    open.length ? `Stated value of the open tenders: ${tVal(open)}.${next ? ` The next one closes ${iso(next)}.` : ""}` : "No open tender at this calibre.",
    mine.length ? `${client(d)} lists ${plural(mine.length, "model")} at this calibre: ${mine.slice(0, 4).map((p) => p.name).join(", ")}.` : `${client(d)} lists no model at this calibre in this category: a gap in the catalogue as stored.`,
    `${plural(rivals.length, "rival model")} at this calibre in the catalogue; ${plural(aw.length, "award")} on record name it.`,
  ];
  return {
    kind: "calibre", title: row.key, subtitle: row.covered ? `${client(d)} covers it with ${plural(mine.length, "model")}` : `A gap: ${client(d)} lists no model at this calibre`,
    tiles: [tile("Open tenders", open.length, open.length ? `${tVal(open)} stated value` : ""), tile("Project leads", proj.length, ""),
      tile("Awards at this calibre", aw.length, `${aw.filter((a) => hasAmount(a, AWARD_FIELDS)).length} with a value`), tile("Countries", countries.length, countries.slice(0, 3).join(", ")),
      tile("Buyers", buyers.length, buyers.slice(0, 2).join(", ")), tile("Models at this calibre", mine.length + rivals.length, `${mine.length} ${client(d)} · ${rivals.length} rival`)],
    charts: [{ title: "Demand at this calibre", sub: "tenders and awards per month, last 12 months", ...ser, note: undatedNote(ser) }],
    sections: [
      { h: "In figures", note: "the calibre as the tender title or equipment scope states it", lines },
      { h: "Open tenders at this calibre", rows: open.map(tenderLine), empty: "No open tender at this calibre." },
      { h: "Project leads at this calibre", rows: proj.map(tenderLine), empty: "" },
      { h: "Who wins at this calibre", note: "rival awards whose title names this calibre", rows: [...byWinner.values()].sort((a, b) => b.list.length - a.list.length).map((r) => ({ title: r.name, sub: plural(r.list.length, "award"), right: aVal(r.list) === "—" ? null : aVal(r.list) })), empty: "No award on record names this calibre." },
      { h: "Awards at this calibre", rows: aw.map(awardLine), empty: "" },
      { h: `${client(d)} models that cover it`, note: "stored Calibre spec, same category", rows: mine.map((p) => ({ title: p.name, sub: [p.cat, p.cals.map(calText).join(", ")].filter(Boolean).join(" · ") })), empty: "No model at this calibre in this category: this is a gap." },
      { h: "Rival models at this calibre", rows: rivals.sort((a, b) => a.company.localeCompare(b.company)).slice(0, 12).map((p) => ({ title: p.name, sub: [p.company, p.cals.map(calText).join(", ")].filter(Boolean).join(" · ") })), empty: "No rival model in the catalogue at this calibre." },
    ],
  };
}

/* ------------------------------------------------------------------ buyer */
export function buyerDetail(d, name, row, today = new Date()) {
  const sameB = (s) => same(s, name);
  const all = (d.tenders || []).filter((t) => sameB(t.issuer));
  const aw = (d.awards || []).filter((a) => sameB(a.buyer));
  const openSet = new Set(bucketTenders(d.tenders || []).open);
  const openT = all.filter((t) => openSet.has(t));
  const ser = series(today, [{ name: "Tenders", dates: all.map(tenderDate), total: all.length }, { name: "Awards", dates: aw.map((a) => asDate(a.date)), total: aw.length }]);
  const winners = new Map();
  aw.filter((a) => a.winner).forEach((a) => { const k = winnerKey(a.winner); const r = winners.get(k) || { name: a.winner, brand: a.brand, list: [] }; r.list.push(a); winners.set(k, r); });
  all.filter((t) => t.awardedTo).forEach((t) => { const k = winnerKey(t.awardedTo); const r = winners.get(k) || { name: t.awardedTo, brand: null, list: [] }; r.list.push({}); winners.set(k, r); });
  return {
    kind: "buyer", title: name, subtitle: row ? row.segments.join(" · ") : "",
    tiles: [tile("Tenders", all.length, `${openT.length} open now`), tile("Awards", aw.length, `${aw.filter((a) => a.winner).length} with a named winner`),
      tile("Value in play", openT.length ? tVal(openT) : "—", "open tenders, stated value"), tile("Awards value", aw.length ? aVal(aw) : "—", `${aw.filter((a) => hasAmount(a, AWARD_FIELDS)).length} priced`),
      tile("Last dated record", row && row.last ? iso(row.last) : "—", ""), tile("Next known deadline", row && row.nextDeadline ? iso(row.nextDeadline) : "—", row && row.nextDeadline ? "an open tender's stored closing date" : "no open tender with a future deadline")],
    charts: [{ title: "How often this buyer tenders", sub: "tenders and awards per month, last 12 months", ...ser, note: undatedNote(ser) }],
    sections: [
      { h: "Open now", rows: openT.map(tenderLine), empty: "Nothing open from this buyer." },
      { h: "Who won its contracts", rows: [...winners.values()].sort((a, b) => b.list.length - a.list.length).map((r) => ({ title: r.name, sub: r.brand || "", right: aVal(r.list) === "—" ? plural(r.list.length, "award") : aVal(r.list) })), empty: "No winner is published for its tenders." },
      { h: "Every record", rows: [...all.map((t) => ({ ...tenderLine(t), tag: String(t.status || "").toLowerCase() || null })), ...aw.map((a) => ({ ...awardLine(a), tag: "award" }))].slice(0, 30), empty: "" },
    ],
  };
}

/* ----------------------------------------------------------------- driver */
export function driverDetail(d, country, seg, row, today = new Date()) {
  const { open, closed } = bucketTenders(d.tenders || []);
  const parts = String(country).split(/[,;]/).map((x) => x.trim());
  const here = (t) => segmentOf(t.cat) === seg && parts.some((p) => same(p, t.country));
  const openT = open.filter(here);
  const proj = projectRows(d).filter(here);
  const closedT = closed.filter(here);
  const aw = (d.awards || []).filter((a) => segmentOf(a.segment) === seg && parts.some((p) => same(p, a.country)));
  const sigs = row ? row.signals : [];
  const ser = series(today, [{ name: "Market signals", dates: sigs.map((s) => s.date), total: sigs.length }, { name: "Tenders", dates: [...openT, ...closedT].map(tenderDate), total: openT.length + closedT.length }]);
  const n = openT.length + proj.length;
  return {
    kind: "driver", title: `${country} · ${seg}`, subtitle: "",
    tiles: [tile("Signals", sigs.length, "news and pipeline items"), tile("Open tenders", openT.length, openT.length ? `${tVal(openT)} stated value` : ""),
      tile("Projects to win", proj.length, ""), tile("Closed tenders", closedT.length, ""),
      tile("Awards", aw.length, aw.length ? aVal(aw) : "no value stated"), tile("Signals per open tender", n ? (sigs.length / n).toFixed(1) : "—", "signals ÷ open tenders and projects")],
    charts: [{ title: "Signals against tenders", sub: "per month, last 12 months", ...ser, note: undatedNote(ser) }],
    sections: [
      { h: "What is driving it", rows: sigRows(d, sigs), empty: "" },
      { h: "Open tenders", rows: openT.map(tenderLine), empty: "No open tender in this place and segment." },
      { h: "Projects to win", rows: proj.map(tenderLine), empty: "" },
      { h: "Competitors active here", note: "the stored competitor-fit assessments on these tenders", rows: activeRows([...openT, ...closedT], 6), empty: "No competitor fit is stored for tenders here." },
      { h: "Who has won here", note: `rivals; ${client(d)} is the client and is not listed`, rows: aw.filter((a) => a.winner && !isClientName(d, `${a.winner} ${a.brand || ""}`)).map(awardLine), empty: "No award on record in this place and segment." },
    ],
  };
}

/* awards and awarded tenders per tracked competitor, one per source URL: the Awarded tab's "Awarded per top competitor" */
export function awardedByCompetitor(d, limit = 8) {
  const seen = new Set();
  const by = new Map();
  const add = (who, title, url) => {
    const u = /^https?:\/\//i.test(String(url || "")) ? String(url) : null;
    const c = companyOf(d, who);
    if (!c || !u || seen.has(u) || isClientName(d, who)) return;
    seen.add(u);
    const r = by.get(c.cid) || { competitor: c.name, awards: 0, sources: [] };
    r.awards += 1;
    r.sources.push({ url: u, title: String(title || "").slice(0, 110), winner: who });
    by.set(c.cid, r);
  };
  (d.awards || []).filter((a) => a.winner).forEach((a) => add(`${a.winner} ${a.brand || ""}`, a.programme || a.title, a.url));
  (d.tenders || []).filter((t) => t.awardedTo).forEach((t) => add(t.awardedTo, t.title, t.url));
  return [...by.values()].sort((a, b) => b.awards - a.awards || a.competitor.localeCompare(b.competitor)).slice(0, limit);
}
