/* FREE PRODUCT COMPARISON for the Positioning page: any two products, side by side.

   The catalogue is the product tables as served: every competitor product
   (data.competitors[cid].products, from competitive_product + _specification) and every KSSL
   product (data.clientProducts, from client_product + client_product_specification).

   Nothing is scored. There is no stored direction ("higher is better") for a spec and the free
   pair has no stored better_side, so no winner is invented: the published values are shown next
   to each other, matched by spec label (case-insensitive). The stored winners live on the matchup
   rows (see edge.js). */

const lc = (v) => String(v == null ? "" : v).trim().toLowerCase();

export function buildProductIndex(data, clientShort = "KSSL") {
  const out = [];
  const specMap = (specs) => {
    const m = {};
    (specs || []).forEach((s) => {
      if (!s || !s.label) return;
      const k = lc(s.label);
      if (!m[k]) m[k] = { l: s.label, v: s.value === "" || s.value == null ? null : String(s.value), n: null, hi: null, u: s.unit || "" };
    });
    return m;
  };
  (data.clientProducts || []).forEach((p) => {
    out.push({ key: `client|${p.id}`, side: "client", name: p.name, maker: clientShort, cat: p.category, country: "", specs: specMap(p.specs) });
  });
  Object.values(data.competitors || {}).forEach((co) => {
    (co.products || []).forEach((p) => {
      if (!p || typeof p !== "object") return;
      out.push({ key: `rival|${p.id}`, side: "rival", name: p.name, maker: co.name || "", cat: p.category, country: p.country || "", specs: specMap(p.specs) });
    });
  });
  return out.sort((a, b) =>
    (a.side === b.side ? 0 : a.side === "client" ? -1 : 1) || String(a.cat).localeCompare(String(b.cat)) || String(a.name).localeCompare(String(b.name)));
}

/* Rows for two products' spec maps ({ key: { l, v, n, u } }). No winner is computed: `win` is
   always null and the counters are 0, which is the shape the Geo page already reads. */
export function compareProducts(a, b) {
  const keys = [...new Set([...Object.keys(a.specs), ...Object.keys(b.specs)])];
  const rows = keys.map((k) => {
    const x = a.specs[k] || {}, y = b.specs[k] || {};
    return { l: x.l || y.l || k, av: x.v ?? null, bv: y.v ?? null, u: x.u || y.u || "", hi: null, win: null, note: "" };
  });
  // rows both sides published first, then one-sided
  const rank = (r) => (r.av != null && r.bv != null ? 0 : r.av != null || r.bv != null ? 1 : 2);
  rows.sort((p, q) => rank(p) - rank(q));
  return { rows, aWins: 0, bWins: 0, ties: 0, measured: 0 };
}
