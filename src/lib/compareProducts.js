/* "COMPARE ANY TWO PRODUCTS" on Product Evaluation (owner 2026-10-25): pick a company, then a
   second company that makes the same kind of products, then a product, then a rival product
   that can face it. "Can face it" = the same product type (product.vs: product_class sub_type
   and role, e.g. "fighter_multirole", "apc_wheeled/apc_6x6_8x8"). A product with no type, a
   service, a family card or a hidden kind is not offered: there is nothing to put against it.

   A row decides a winner only when both sides carry a number and the field has a direction
   (`hi`). Catalogue specs are text with no direction, so they are shown, not scored. Two
   numbers more than 50x apart are almost always the same quantity in different units; that
   row is flagged, not scored. */
import { EDGE_DEADBAND } from "./edge.js";

const UNIT_RATIO = 50;
const NOT_OFFERED = new Set(["service", "test_asset", "programme", "not_product"]);
const SHEET_SECTIONS = ["key", "other", "armament"];

/* every product that can be put in a comparison, from the served catalogue */
export function catalogue(competitors, clientCid, clientLabel) {
  const out = [];
  Object.entries(competitors || {}).forEach(([cid, co]) => {
    const maker = String(cid) === String(clientCid) ? clientLabel : co.name;
    (co.products || []).forEach((p) => {
      if (!p || !p.vs || p.umbrella || NOT_OFFERED.has(p.kind)) return;
      const specs = {};
      SHEET_SECTIONS.forEach((s) => ((p.sheet && p.sheet[s]) || []).forEach((r) => {
        if (!r || !r.l || specs[r.l]) return;
        const v = Array.isArray(r.v) ? r.v.join("; ") : r.v;
        if (v != null && v !== "") specs[r.l] = { v: String(v), n: null, hi: null, u: "" };
      }));
      out.push({ key: String(p.id), name: p.displayName || p.name, maker, cat: p.category || "", country: p.country || co.country || "", vs: p.vs, specs });
    });
  });
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

const typesOf = (items, maker) => new Set(items.filter((p) => p.maker === maker).map((p) => p.vs));

/* the companies that make at least one product of a type `maker` also makes (all companies with a
   rival anywhere when `maker` is empty) */
export function companiesFacing(items, maker = "") {
  const byType = new Map();
  items.forEach((p) => byType.set(p.vs, (byType.get(p.vs) || new Set()).add(p.maker)));
  const mine = maker ? typesOf(items, maker) : null;
  const out = new Set();
  byType.forEach((makers, vs) => {
    if (makers.size < 2 || (mine && !mine.has(vs))) return;
    makers.forEach((m) => { if (m !== maker) out.add(m); });
  });
  return [...out].sort((a, b) => a.localeCompare(b));
}

/* makerA's products that makerB has an answer to */
export function productsFacingCompany(items, makerA, makerB) {
  const theirs = typesOf(items, makerB);
  return items.filter((p) => p.maker === makerA && theirs.has(p.vs));
}

/* makerB's products of the same type as product a */
export function rivalsOf(items, a, makerB) {
  return a ? items.filter((p) => p.maker === makerB && p.vs === a.vs && p.key !== a.key) : [];
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
