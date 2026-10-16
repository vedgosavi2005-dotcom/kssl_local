/* Footprint decisions are derived from the serving geo tables. There is no
 * baked-in country or product footprint in the frontend.
 */
export const T0 = "home";
export const T1 = "present";
export const T2 = "contested";
export const T3 = "none";

export function footprintCountries(data) {
  const clientId = (data && data.client && data.client.id) || "KSSL";
  const rows = (data && data.geoData && data.geoData[clientId]) || {};
  return new Set(Object.keys(rows).filter(Boolean));
}

export function tierOf(country, countries) {
  const present = countries instanceof Set ? countries : new Set(countries || []);
  return present.has(country) ? { tier: T1, row: null } : { tier: T3, row: null };
}

export function withinLines() {
  return true;
}

export function tieredCountries(tier, data) {
  if (tier && tier !== T1) return [];
  return Array.from(footprintCountries(data));
}

export default footprintCountries;
