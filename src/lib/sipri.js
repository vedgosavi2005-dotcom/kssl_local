/* SIPRI figures as the pages print them (backend/areas/f_sipri.py: data.sipriArms by competitor id, data.sipriMilex by country).
   Pure functions: tests/unit/test_sipri.mjs.

   A parent group's figure is never printed as the subsidiary's own: the entity is always named, with "(parent)" or
   "(predecessor)" when it is not the company itself. */

export const SIPRI_ARMS = { label: "SIPRI Arms Industry Database", url: "https://www.sipri.org/databases/armsindustry" };
export const SIPRI_MILEX = { label: "SIPRI Military Expenditure Database", url: "https://www.sipri.org/databases/milex" };

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

/* US$ millions -> "$64.7bn", "$954bn", "$850m" */
export function fmtUsdM(m) {
  if (!isNum(m)) return null;
  if (Math.abs(m) >= 100000) return `$${Math.round(m / 1000)}bn`;
  if (Math.abs(m) >= 1000) return `$${(m / 1000).toFixed(1)}bn`;
  return `$${Math.round(m)}m`;
}

/* a 0-1 share -> "91%" (digits = 0) or "2.3%" (digits = 1) */
export function fmtShare(x, digits = 0) {
  if (!isNum(x)) return null;
  return `${(x * 100).toFixed(digits)}%`;
}

/* change from the first to the last point that has a value: {pct: "+21%", from, to} or null */
export function trendChange(points, key) {
  const pts = (points || []).filter((p) => p && isNum(p[key]));
  if (pts.length < 2) return null;
  const a = pts[0], b = pts[pts.length - 1];
  if (!a[key]) return null;
  const pct = Math.round(((b[key] - a[key]) / a[key]) * 100);
  return { pct: `${pct > 0 ? "+" : ""}${pct}%`, from: a.year, to: b.year };
}

/* bars of a small trend chart: [{year, x, y, w, h, value}] inside a w x h box */
export function sparkBars(points, key, w = 120, h = 28, gap = 3) {
  const pts = (points || []).filter((p) => p && isNum(p[key]));
  if (!pts.length) return [];
  const max = Math.max(...pts.map((p) => p[key]));
  const bw = (w - gap * (pts.length - 1)) / pts.length;
  return pts.map((p, i) => {
    const bh = max > 0 ? Math.max(2, (p[key] / max) * h) : 2;
    return { year: p.year, value: p[key], x: i * (bw + gap), y: h - bh, w: bw, h: bh };
  });
}

export function entityLabel(a) {
  if (!a || !a.entity) return null;
  if (a.relation === "parent") return `${a.entity} (parent)`;
  if (a.relation === "predecessor") return `${a.entity} (predecessor)`;
  return a.entity;
}

/* what the Company profile prints for one competitor; null when SIPRI does not list it */
export function armsView(a, companyName) {
  if (!a || !isNum(a.armsUsdM) || !a.year) return null;
  const facts = [];
  if (a.rank) facts.push(["Top-100 rank", `#${a.rank} (${a.year})`]);
  const share = fmtShare(a.share);
  if (share) facts.push(["Arms share of revenue", share]);
  const ch = trendChange(a.trend, "armsUsdM");
  if (ch) facts.push([`Change ${ch.from}–${ch.to}`, ch.pct]);
  let note = null;
  if (a.relation === "parent")
    note = `SIPRI lists the parent group, not ${companyName || "the company"} alone: the figures are ${a.entity}'s.`;
  else if (a.relation === "predecessor")
    note = `SIPRI's last listing is the predecessor, ${a.entity} (${a.year}), not ${companyName || "the company"} itself.`;
  return {
    headline: `Arms revenue ${a.year}: ${fmtUsdM(a.armsUsdM)}`,
    entity: entityLabel(a),
    facts,
    note,
    bars: sparkBars(a.trend, "armsUsdM"),
    source: (a.source && a.source.url) ? a.source : SIPRI_ARMS,
  };
}

/* what the Geo country panel prints for one country; null when SIPRI has no figure */
export function milexView(m) {
  if (!m || !m.year) return null;
  const amount = fmtUsdM(isNum(m.currentUsdM) ? m.currentUsdM : m.constantUsdM);
  if (!amount) return null;
  const facts = [];
  const gdp = fmtShare(m.shareGdp, 1);
  if (gdp) facts.push(["Share of GDP", gdp]);
  const ch = trendChange(m.trend, "constantUsdM");
  if (ch) facts.push([`Real change ${ch.from}–${ch.to}`, ch.pct]);
  return {
    headline: `Defence spending ${m.year}: ${amount}`,
    facts,
    bars: sparkBars(m.trend, "constantUsdM", 90, 20, 2),
    source: (m.source && m.source.url) ? m.source : SIPRI_MILEX,
  };
}
