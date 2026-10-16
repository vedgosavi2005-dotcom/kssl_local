/* WHERE A COUNTRY IS -- read from the served competitive_geo_location rows, never from a table here.

   The coordinates are the location's own latitude / longitude columns. dataset.js registers
   them once per fetch (registerGeoLocations); a country with no coordinates is NOT drawn, it
   is listed beside the map as "unlocated" instead. No fallback is guessed.

   A plain node test can import this module without Leaflet. */
import { hqParts } from "./countryFacet.js";

let COORDS = new Map(); // lower-cased name -> [lat, lng]
let NAMES = []; // every served location name

export function registerGeoLocations(locations) {
  COORDS = new Map();
  NAMES = [];
  (locations || []).forEach((l) => {
    if (!l || !l.name) return;
    NAMES.push(l.name);
    if (Number.isFinite(l.lat) && Number.isFinite(l.lng)) {
      COORDS.set(String(l.name).toLowerCase(), [l.lat, l.lng]);
      if (l.label) COORDS.set(String(l.label).toLowerCase(), [l.lat, l.lng]);
    }
  });
}

export function geoCountryCoords(countryName) {
  if (!countryName) return null;
  return COORDS.get(String(countryName).toLowerCase()) || null;
}

/* Split the served countries into what can be drawn and what cannot. Pure and exported so the
   rule can be tested without a map. */
export function geoPlotPlan(countries) {
  const plotted = [];
  const unlocated = [];
  (countries || []).forEach((ct) => {
    const coords = geoCountryCoords(ct);
    if (coords) plotted.push({ ct, coords });
    else unlocated.push(ct);
  });
  return { plotted, unlocated };
}

/* THE SPELLINGS THAT ARE THE SAME COUNTRY: the served names that share this one's coordinates
   (a location written under two names carries the same latitude and longitude). */
export function countrySpellings(name) {
  const c = geoCountryCoords(name);
  if (!c) return [String(name == null ? "" : name).trim()].filter(Boolean);
  return NAMES.filter((n) => {
    const x = geoCountryCoords(n);
    return x && x[0] === c[0] && x[1] === c[1];
  });
}

/* ARE THESE TWO NAMES THE SAME COUNTRY? Equal text, or two served names at one point. Two
   names with no coordinates are the same only when they are literally the same word. */
export function sameCountry(a, b) {
  const fa = String(a == null ? "" : a).trim().toLowerCase();
  const fb = String(b == null ? "" : b).trim().toLowerCase();
  if (!fa || !fb) return false;
  if (fa === fb) return true;
  const ca = geoCountryCoords(a);
  const cb = geoCountryCoords(b);
  return !!ca && !!cb && ca[0] === cb[0] && ca[1] === cb[1];
}

/* THE COUNTRY AN hq IS IN -- or null, which is a real answer. A component of the hq text
   becomes a country only if it is a served location name, so a city stays null. Broadest
   component last, so the scan runs from the right and stops at the first hit. */
export function hqCountry(hq) {
  const parts = hqParts(hq);
  for (let i = parts.length - 1; i >= 0; i -= 1) {
    if (geoCountryCoords(parts[i])) return parts[i];
  }
  return null;
}

/* Is `country` this company's head office? The stated origin column first, the hq text second.
   No origin and an unreadable hq mean no badge. */
export function isHeadOffice(country, { origin, hq }) {
  if (origin && sameCountry(origin, country)) return true;
  const fromHq = hqCountry(hq);
  return !!fromHq && sameCountry(fromHq, country);
}
