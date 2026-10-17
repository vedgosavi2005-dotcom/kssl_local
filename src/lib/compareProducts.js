/* FREE PRODUCT COMPARISON for the Positioning page: any two products, not only the
   pairs the pipeline matched.

   The catalogue is built from the served matchups -- the only place product specs live.
   Each matchup carries BOTH products' figures (rival: cv/cn, client: kv/kn), so every
   rival and every client product that appears in any matchup becomes one entry, its spec
   rows merged across all the matchups it appears in (first measured value wins).

   A row decides a winner only when both sides carry a number and the field has a
   direction (`hi`: true = higher is better, false = lower is better). Gaps under 3% are a
   tie -- the same deadband the edge index uses. Two numbers more than 50x apart are
   almost always the same quantity in different units (17.7 t against 18000 kg); that row
   is flagged, not scored. */
import { EDGE_DEADBAND } from "./edge.js";

const SKIP = new Set(["Product (sourced)"]);
const UNIT_RATIO = 50;

// "KNDS · CAESAR 6x6" -> { maker: "KNDS", name: "CAESAR 6x6" }
function split(label, fallbackMaker) {
  const s = String(label || "").trim();
  const i = s.indexOf(" · ");
  if (i > 0) return { maker: s.slice(0, i).trim(), name: s.slice(i + 3).trim() };
  return { maker: fallbackMaker || "", name: s };
}

export function buildProductIndex(matchups, clientLabel) {
  const byKey = new Map();
  const add = (side, label, maker, cat, country, spec, v, n) => {
    const { maker: mk, name } = split(label, maker);
    if (!name || /^—?$/.test(name) || /present$/i.test(name)) return;
    const key = `${side}|${(mk || "").toLowerCase()}|${name.toLowerCase()}`;
    let e = byKey.get(key);
    if (!e) {
      e = { key, side, name, maker: side === "client" ? clientLabel : mk || maker || "", cat: cat || "", country: country || "", specs: {} };
      byKey.set(key, e);
    }
    if (!spec || SKIP.has(spec.l)) return;
    const cur = e.specs[spec.l];
    const hasNum = typeof n === "number" && isFinite(n);
    if (!cur || (cur.n == null && hasNum)) {
      e.specs[spec.l] = { v: v == null || v === "" ? null : String(v), n: hasNum ? n : null, hi: spec.hi ?? null, u: spec.u || "" };
    }
  };
  Object.values(matchups || {}).forEach((m) => {
    const specs = m.specs && m.specs.length ? m.specs : [null];
    specs.forEach((s) => {
      add("rival", m.comp, m.compBy, m.cat, m.country, s, s && s.cv, s && s.cn);
      add("client", m.bf || m.anchor, clientLabel, m.cat, "", s, s && s.kv, s && s.kn);
    });
  });
  return [...byKey.values()].sort((a, b) =>
    (a.side === b.side ? 0 : a.side === "client" ? -1 : 1) || a.cat.localeCompare(b.cat) || a.name.localeCompare(b.name));
}

export function compareProducts(a, b) {
  const labels = [...new Set([...Object.keys(a.specs), ...Object.keys(b.specs)])];
  const rows = labels.map((l) => {
    const x = a.specs[l] || {}, y = b.specs[l] || {};
    const hi = x.hi ?? y.hi ?? null;
    const an = x.n, bn = y.n;
    let win = null, note = "";
    if (typeof an === "number" && typeof bn === "number") {
      const big = Math.max(Math.abs(an), Math.abs(bn)), small = Math.min(Math.abs(an), Math.abs(bn));
      if (small > 0 && big / small > UNIT_RATIO) {
        note = "values look like different units — not scored";
      } else if (hi != null) {
        const mean = (an + bn) / 2;
        const gap = mean ? Math.abs(an - bn) / Math.abs(mean) : 0;
        win = gap < EDGE_DEADBAND ? "tie" : (an > bn) === !!hi ? "a" : "b";
      }
    }
    return { l, av: x.v ?? null, bv: y.v ?? null, u: x.u || y.u || "", hi, win, note };
  });
  // rows both sides published first, then one-sided, then empty
  const rank = (r) => (r.av != null && r.bv != null ? 0 : r.av != null || r.bv != null ? 1 : 2);
  rows.sort((p, q) => rank(p) - rank(q));
  const scored = rows.filter((r) => r.win);
  return {
    rows,
    aWins: scored.filter((r) => r.win === "a").length,
    bWins: scored.filter((r) => r.win === "b").length,
    ties: scored.filter((r) => r.win === "tie").length,
    measured: scored.length,
  };
}
