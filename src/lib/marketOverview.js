/* Market intelligence: the tender read for the Market pillar. Pure: it returns data, the
   React component renders it. Every function takes the WIRED tenders `useData()` serves
   (src/lib/tenderCalc.js adds `bucket`, `dl`, `isLive`): open / awarded / closed is the
   stored `status`, `dl` is days left to the stored closing date (absent without one). */
import { facetOptionsByName } from "./countryFacet.js";
import { bucketTenders } from "./tenderCalc.js";

const WINDOW_NONE = (d) => d == null;

export const WINDOWS = [
  { key: "w7", label: "Up to 7 days", test: (d) => d != null && d <= 7 },
  { key: "w14", label: "8–14 days", test: (d) => d != null && d >= 8 && d <= 14 },
  { key: "w30", label: "15–30 days", test: (d) => d != null && d >= 15 && d <= 30 },
  { key: "w30p", label: "30+ days", test: (d) => d != null && d > 30 },
  { key: "none", label: "No date published", test: WINDOW_NONE },
];

/* Which closing bucket ONE tender falls in — the same predicate the chart uses, exposed
   so a tooltip can name a row's bucket without re-bucketing the whole corpus. */
export function windowOf(t) {
  const w = WINDOWS.find((x) => x.test(t ? t.dl : undefined));
  return w ? w.label : "";
}

/* Categorical slice colours, in FIXED order by rank — slot N is always the same category
   for a given corpus, so narrowing the market cannot repaint the survivors.

   Validated with the dataviz palette checker against this app's dark surface (#1c1c1f):
   lightness band, chroma floor, CVD separation and contrast all pass. The one CVD warning
   (rose vs sage, ΔE 6.3 deutan) sits in the band that is legal WITH secondary encoding —
   the legend direct-labels every slice with its name, count and share, so hue is never
   doing the work alone. A ninth category folds into "Other" rather than earning a
   generated hue. */
/* NINE slots, because the client's taxonomy has nine categories and every one of them
   is a line KSSL actually sells. With seven, "Other (2 categories)" was Missiles & Air
   Defence and ARTILLERY -- ranked 7th and 8th by tender count and folded into a grey
   slice, which is how the client's flagship line came to be unnamed on its own chart.
   Nothing foreign was ever in that bucket: all eight categories on record are KSSL's.

   Ranking by contract count is the right order for the LEGEND and the wrong rule for
   who gets a name, so the palette now covers the whole taxonomy and "Other" is reserved
   for a category genuinely outside it.

   Re-validated with the dataviz palette checker against BOTH surfaces (dark #1a1a19,
   light #fcfcfb): lightness band, chroma floor, adjacent-pair CVD, normal-vision floor
   and contrast all PASS. The old seven did not -- four sat outside the dark lightness
   band. Hue ORDER is load-bearing: the CVD check runs on adjacent pairs, and the warm
   and green hues are interleaved with the cool ones on purpose (lime beside orange
   collapses to deutan ΔE 1.7). Re-run the checker before reordering or adding one. */
const SERIES = ["#3B82F6", "#D97706", "#0891B2", "#DC2626", "#8B5CF6",
                "#EA580C", "#059669", "#EC4899", "#65A30D"];
const OTHER_COLOR = "#94A3B8";
const _catSlot = new Map();
let _otherLabel = "";

/* Assign ONCE, from the WHOLE corpus, ranked over every tender on record — never from
   the rows currently on screen.

   This used to be called from demandSplit() with whatever set demandSplit had been
   handed, which meant filtering to France re-ranked the categories and repainted the
   survivors: Ammunition blue at "All countries" and teal in France, describing the same
   contracts. Colour identifies the CATEGORY, so it is fixed by the category's standing
   in the corpus and a filter cannot move it. */
export function assignCategoryColors(labels) {
  _catSlot.clear();
  labels.forEach((l, i) => {
    _catSlot.set(l, i < SERIES.length ? SERIES[i] : OTHER_COLOR);
  });
}

export function CATEGORY_COLOR(label) {
  return _catSlot.get(label) || OTHER_COLOR;
}

/* A tender that states no category belongs to none: it is left out of the category
   views, not filed under an invented name. */
export const catOf = (t) => (t && t.cat) || "";

/* Every category the corpus carries, most-contracted first — the filter's option list
   and the colour order, from one count so the two can never disagree. */
export function categoryRank(tenders) {
  const n = {};
  (tenders || []).forEach((t) => {
    const k = catOf(t);
    if (k) n[k] = (n[k] || 0) + 1;
  });
  return Object.entries(n)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([label, count]) => ({ label, count }));
}

/* Six named slices at most; a seventh hue would have to be GENERATED, and a generated
   hue is the point at which a validated categorical palette stops being validated.
   The tail is one grey "Other" slice on the chart — but it stays fully enumerated in
   the filter, so a small category is still reachable, just not separately coloured. */
export function initCategoryPalette(tenders) {
  const ranked = categoryRank(tenders).map((r) => r.label);
  if (ranked.length <= SERIES.length) {
    _otherLabel = "";
    assignCategoryColors(ranked);
    return ranked;
  }
  const TOP = SERIES.length - 1;
  _otherLabel = `Other (${ranked.length - TOP} categories)`;
  assignCategoryColors(ranked.slice(0, TOP).concat(_otherLabel));
  /* _otherLabel lands in slot TOP (== SERIES.length-1), which is still a real SERIES
     hue, so the aggregate slice would take a category colour instead of the grey its
     folded-in members render as (they fall through CATEGORY_COLOR to OTHER_COLOR). Pin
     the aggregate to OTHER_COLOR explicitly so the "Other" slice and its members match. */
  _catSlot.set(_otherLabel, OTHER_COLOR);
  return ranked;
}

/* The chart label for one row's category: itself, or the shared "Other" slice. */
export function sliceLabel(cat) {
  return _catSlot.has(cat) ? cat : _otherLabel || cat;
}

/* The metric strip: four tiles, each counted from the stored rows on screen. */
export function marketMetrics(tenders) {
  const list = tenders || [];
  const { open } = bucketTenders(list);
  const countries = new Set(list.map((t) => t.country).filter(Boolean));
  const portals = new Set(
    list.flatMap((t) => (t.srcs || []).map((s) => s.portal || s.publisher)).filter(Boolean),
  );
  const valued = list.filter((t) => t.value && String(t.value).trim() !== "");
  /* A COUNT, never a total: tender values are stated in several currencies and there is
     no stored rate to add them up. */
  return [
    { l: "Active tenders", act: "active", v: String(open.length) },
    { l: "Markets", act: "markets", v: String(countries.size) },
    { l: "Source portals", act: "portals", v: String(portals.size) },
    { l: "Tenders with a stated value", act: "value", v: String(valued.length) },
  ];
}

/* The Top opportunity page's tiles are the stored market_top_opportunity_metric rows. */
export function topOpportunityMetrics(data) {
  const rows = (data && data.topOpportunities && data.topOpportunities.metrics) || [];
  return rows.map((m) => ({
    l: m.label,
    act: m.key,
    v: m.value || (m.amount != null ? String(m.amount) : "—"),
    sub: m.note,
  }));
}

/* Demand split by category: the stored `cat` of each tender that states one. */
export function demandSplit(tenders) {
  const list = tenders || [];
  const n = {};
  let total = 0;
  list.forEach((t) => {
    if (!catOf(t)) return;
    const k = sliceLabel(catOf(t));
    n[k] = (n[k] || 0) + 1;
    total += 1;
  });
  /* Ordered by the FIXED palette order, not by count in this slice — so narrowing to
     one country reorders nothing and "Other" stays last where a reader expects it. */
  const order = Array.from(_catSlot.keys());
  return Object.entries(n)
    .map(([label, count]) => ({
      label,
      count,
      pct: total ? Math.round((count / total) * 100) : 0,
    }))
    .sort((a, b) => {
      const ia = order.indexOf(a.label);
      const ib = order.indexOf(b.label);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
}

/* How much runway is left, over the OPEN set only: concluded tenders counted into "no
   date published" would present them as still-closing pipeline. */
export function closingWindows(openTenders) {
  const list = openTenders || [];
  return WINDOWS.map((w) => {
    const count = list.filter((t) => w.test(t.dl)).length;
    return {
      key: w.key,
      label: w.label,
      count,
      pct: list.length ? Math.round((count / list.length) * 100) : 0,
    };
  });
}

/* The country options for a list of tenders, WITH the row count each one labels.
   Built from the rows the filter narrows -- the open section's rows for the open
   section -- never from every tender: the report offered 22 countries over an
   awarded list that carried 8, and 14 of them returned nothing. */
export function countriesOf(tenders) {
  return facetOptionsByName(tenders, (t) => t.country);
}

/* The report's two filters, each counted over the section's rows with the OTHER
   facet applied -- so an option lists exactly the number it advertises, and an option
   with no row behind it in this section does not exist. The category options were
   ranked over all 136 tenders whatever the tab: "Ammunition (48)" over an awarded
   list of 11. Same shape as the Tender Pipeline's facets. */
const rowCat = (t, cat) => !cat || catOf(t) === cat || sliceLabel(catOf(t)) === cat;
const rowCountry = (t, country) => !country || country === "all" || t.country === country;

export function reportRows(scope, { country, cat } = {}) {
  return (scope || [])
    .filter((t) => rowCountry(t, country) && rowCat(t, cat))
    .slice()
    .sort((a, b) => (a.dl == null) - (b.dl == null) || (a.dl || 0) - (b.dl || 0));
}

export function reportFacets(scope, { country, cat } = {}) {
  const rows = scope || [];
  return {
    countries: countriesOf(rows.filter((t) => rowCat(t, cat))),
    cats: categoryRank(rows.filter((t) => rowCountry(t, country))).map((c) => ({ v: c.label, n: c.count })),
  };
}
