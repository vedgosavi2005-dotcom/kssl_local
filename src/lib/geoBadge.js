/* WHAT THE MAP SAYS ABOUT ONE COUNTRY -- as data, so it can be tested without Leaflet.
   GeoMap.jsx turns these objects into the tooltip's HTML and does nothing else with them.

   Everything here exists because of three faults reported on the live footprint map on
   2026-09-06. They are separate bugs with one shape: the badge asserted more than the
   rows behind it.
*/

/* THE CLIENT'S OWN ROWS KEEP THEIR STORED ACTIVITY.

   The client is identified by the company (geoComps.isBf), not by an activity code: its footprint rows carry the
   activity word they were stored with ("Local production", "Export"). The badge is built as `<client> Present`
   followed by those words, and any word that merely restates the client's name is dropped, so a label edit
   cannot bring an echo ("KSSL Present . KSSL present") back. */

const fold = (v) =>
  String(v == null ? "" : v)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

/** True when this label says nothing the "<client> Present" half has not already said. */
export function echoesPresence(label, clientLabel) {
  const f = fold(label);
  if (!f) return true;
  const c = fold(clientLabel);
  if (!c) return false;
  return f === c || f === `${c} present` || f === `${c} presence`;
}

/** The distinct activity labels a set of footprint rows names, in row order. */
export function activityLabels(rows, actLabel) {
  const out = [];
  const seen = new Set();
  (rows || []).forEach((r) => {
    const label = r && (actLabel || {})[r.c];
    if (!label || seen.has(label)) return;
    seen.add(label);
    out.push(label);
  });
  return out;
}

/** The same, for the CLIENT's own rows: any label that only restates the client's name removed. */
export function ownActivityLabels(rows, actLabel, clientLabel) {
  return activityLabels(rows, actLabel).filter((label) => !echoesPresence(label, clientLabel));
}

/* AN ESTIMATE MUST NOT LOOK LIKE A MEASUREMENT.

   serving.geo_presence.src holds the URL a row was read from, or the literal "syn" when
   the row is an analytical estimate rather than a sourced fact (those rows also carry
   val='estimate'). pages/competitive/Geo.jsx has always marked them -- a .syn dot and
   the words "analytical estimate" in the source line. GeoMap.jsx never read src at all,
   so an estimated presence drew the same green pin, with the same wording, as a
   presence three documents state.

   That is the house rule "not measured must not look like zero" in its other direction:
   estimated must not look like measured. The client's own footprint outside India is
   exactly this case -- a client row with src='syn'. */
export const isEstimate = (row) => !!row && row.src === "syn";

/** How many of these rows are sourced and how many are estimates. */
export function evidenceOf(rows) {
  let sourced = 0;
  let estimated = 0;
  (rows || []).forEach((r) => (isEstimate(r) ? (estimated += 1) : (sourced += 1)));
  return {
    sourced,
    estimated,
    total: sourced + estimated,
    /* Nothing here is sourced. The whole claim is an estimate, and the badge has to
       say so in its own text rather than in a footnote nobody hovers. */
    allEstimated: estimated > 0 && sourced === 0,
  };
}

/** The wording that goes beside a presence, or null when nothing needs saying. */
export function evidenceNote(rows) {
  const ev = evidenceOf(rows);
  if (!ev.estimated) return null;
  if (ev.allEstimated)
    return ev.total === 1
      ? "analytical estimate, not a sourced row"
      : `all ${ev.total} rows are analytical estimates, not sourced`;
  return ev.estimated === 1
    ? `1 of ${ev.total} rows is an analytical estimate`
    : `${ev.estimated} of ${ev.total} rows are analytical estimates`;
}

/* THE COUNTRY BADGE.

   Returns { text, cls, estimated, note } -- never HTML, so a test can read the words.
   `cls` keeps the caller's existing "present"/"absent" classes and adds "est" when the
   presence rests only on estimates, so CSS can render it differently from a sourced one
   without the caller re-deriving the rule. */
export function presenceBadge({ clientLabel, rows, rivalCount, actLabel }) {
  const own = rows || [];
  if (!own.length) {
    return {
      text:
        rivalCount > 0
          ? `${clientLabel} not on record here · Contested market`   // no row is not proof of absence
          : "No activity on file",
      cls: "absent",
      estimated: false,
      note: null,
    };
  }
  const ev = evidenceOf(own);
  const acts = ownActivityLabels(own, actLabel, clientLabel);
  const parts = [`${clientLabel} Present`];
  if (ev.allEstimated) parts.push("estimated, not sourced");
  if (acts.length) parts.push(acts.join(" / "));
  return {
    text: parts.join(" · "),
    cls: ev.allEstimated ? "present est" : "present",
    estimated: ev.estimated > 0,
    note: evidenceNote(own),
  };
}

/* "IS THE CLIENT IN ONE PLACE ONLY?" -- asked of this map, and the map could not answer it.

   A client can hold rows for a country, for a region, and for an estimate. Only a country is
   plottable: a region is a region and is deliberately not pinned, and an estimate must not look
   like a measurement. So a reader saw one green dot and read it as the whole footprint -- an answer
   the data does not support, produced by honest rules with nothing tying them together for the
   client's own row.

   This states the client's footprint in words beside the map: every country it holds a
   row in, which of those are estimates, and the regional rows that exist and cannot be
   drawn. No new geography is invented -- a region stays a region. `plan` is
   lib/geoCountries.geoPlotPlan over the client's own countries. */
/* A LEGEND, NOT A PARAGRAPH OF CAVEATS.
 *
 * This used to return one sentence, and the sentence read as working notes on a screen
 * that goes to a client: "KSSL footprint: India . recorded but not a country, so not
 * pinned: Europe . 1 without map coordinates: Georgia . regional rows, not pinned:
 * Africa, Europe". Reported as exactly that, with "it look professional and clean" as
 * the standard to meet.
 *
 * The FACTS in it are not optional -- the map draws one green dot over India, and a
 * reader who is not told about the Europe row concludes KSSL is India-only. What was
 * wrong was the form: prose explaining the map's own limitations, in the map's own
 * vocabulary, at the reader.
 *
 * So it returns structure now and the component renders chips: the countries, then the
 * ones that could not be pinned, each under a short label. Same facts, no sentence. A
 * footprint that is entirely plottable returns no second group at all, so the caveat
 * disappears the moment there is nothing to caveat -- which is what fixing the underlying
 * geo data will do to it.
 *
 * Returns null when there is nothing whatever to say. */
export function clientFootprintNote({ clientLabel, ownByCountry, plan }) {
  const own = ownByCountry || {};
  const estimated = (ct) => evidenceOf(own[ct] || []).allEstimated;
  const chip = (ct) => ({ label: ct, estimated: estimated(ct) });
  const drawn = (plan && plan.plotted ? plan.plotted : []).map((p) => p.ct);
  const regions = (plan && plan.regions ? plan.regions : []).slice();
  const unlocated = (plan && plan.unlocated ? plan.unlocated : []).slice();
  if (!drawn.length && !regions.length && !unlocated.length) return null;
  return {
    label: clientLabel,
    /* on the map */
    plotted: drawn.map(chip),
    /* on the record, not on the map: a continent has no honest point, and a country the
       coordinate table does not carry is not going to be invented one */
    offMap: regions.concat(unlocated).map(chip),
    empty: drawn.length === 0,
  };
}

/* WHAT ONE COMPANY DOES IN ONE COUNTRY, for the tooltip's company list.

   `isHq` is decided by lib/geoCountries.isHeadOffice, which reads the stated origin
   column and the tidied hq -- not by a string comparison here. */
export function companyRole({ comp, rows, actLabel, clientLabel, isHq }) {
  const c = comp || {};
  const acts = c.isBf
    ? ownActivityLabels(rows, actLabel, clientLabel)
    : activityLabels(rows, actLabel);
  const parts = isHq ? ["Head office", ...acts] : acts;
  if (parts.length) return parts.join(" · ");
  return c.isBf ? `${clientLabel} presence` : "Competitor";
}
