/* ALPHABETICAL COMPANY ORDER.
 *
 * The roster is every competitor row the dataset carries (serving.competitive_competitor);
 * nothing here chooses who is shown. Every competitive view lists companies in compOrder
 * (Competitor, Products, Partnerships, Patents) or geoComps order (Geo Footprint), so
 * sorting those two here orders every one of them at once. The client row stays first in
 * both; the rest sort by display name, case- and accent-insensitive.
 */
const byName = (a, b) => String(a || "").localeCompare(String(b || ""), "en", { sensitivity: "base" });

export function sortCompaniesByName(d) {
  const comps = (d && d.competitors) || null;
  if (!comps) return d;
  const isClient = (cid) => (comps[cid] || {}).dir === "client";
  const nameOf = (cid) => (comps[cid] || {}).name || cid;
  const order = d.compOrder || [];
  const compOrder = order.filter(isClient)
    .concat(order.filter((cid) => !isClient(cid)).sort((a, b) => byName(nameOf(a), nameOf(b))));
  const geo = d.geoComps || [];
  const geoComps = geo.filter((g) => g && g.isBf)
    .concat(geo.filter((g) => !(g && g.isBf)).sort((a, b) => byName(a && a.name, b && b.name)));
  return { ...d, compOrder, geoComps };
}

