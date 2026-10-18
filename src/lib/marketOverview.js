/* Market overview: the tender-intelligence read that replaced the signal feed on the
   Market pillar. Pure — it returns data, the React component renders it.

   EVERY function here takes WIRED tenders (the ones `useData()` serves), never the raw
   API rows. `wireDataset` runs each tender through `computeTenderRealDays`, which
   overwrites BOTH `dl` and `deadline`: the served rows carry `dl: null` and a date
   string like "24 Aug 2026", the wired rows carry a day count and a phrase like
   "17 days left". Parsing `t.deadline` for a date here would find one on zero rows.
   And `bucketTenders`' `t.dl <= 0` is TRUE for the served `null`, so raw rows bucket
   as 100% closed. Wired input is a correctness requirement, not a convention. */
import { clientShort } from "./client.js";
import { MARKET_TILE_LABEL } from "./chrome.js";
import { hasAmount, valueTotals, formatTotals } from "./tenderValue.js";
import { facetOptionsByName } from "./countryFacet.js";
import { bucketTenders, marketAttention } from "./overview.js";

/* dl semantics, set by computeTenderRealDays:
     0      awarded, or a closing date that has passed
     1..364 real days left
     365    a published programme STAGE rather than a date
     9999   open, but the record carries no deadline          */
const NO_DATE = 9999;
const STAGE = 365;

export const WINDOWS = [
  { key: "w7", label: "1–7 days", test: (d) => d >= 1 && d <= 7 },
  { key: "w14", label: "8–14 days", test: (d) => d >= 8 && d <= 14 },
  { key: "w30", label: "15–30 days", test: (d) => d >= 15 && d <= 30 },
  { key: "w30p", label: "30+ days", test: (d) => d > 30 && d !== NO_DATE },
  { key: "none", label: "No date published", test: (d) => d === NO_DATE },
];

/* Which closing bucket ONE tender falls in — the same predicate the chart uses, exposed
   so a tooltip can name a row's bucket without re-bucketing the whole corpus. */
export function windowOf(t) {
  const d = t && t.dl === STAGE ? 366 : (t || {}).dl;
  const w = WINDOWS.find((x) => x.test(d));
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

export const catOf = (t) => (t && t.cat) || "—";

/* Every category the corpus carries, most-contracted first — the filter's option list
   and the colour order, from one count so the two can never disagree. */
export function categoryRank(tenders) {
  const n = {};
  (tenders || []).forEach((t) => {
    const k = catOf(t);
    n[k] = (n[k] || 0) + 1;
  });
  return Object.entries(n)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([label, count]) => ({ label, count }));
}

/* Six named slices at most; a seventh hue would have to be GENERATED, and a generated
   hue is the point at which a validated categorical palette stops being validated.
   The tail is one grey "Other" slice on the chart — but it stays fully enumerated in
   the filter, so a small category is still reachable, just not separately coloured. */
/* no category on record ("—") and the stored category "Other" are grey by meaning: they take no hue */
const GREY_CATS = new Set(["—", "Other"]);
export function initCategoryPalette(tenders) {
  const all = categoryRank(tenders).map((r) => r.label);
  const ranked = all.filter((l) => !GREY_CATS.has(l));
  if (ranked.length <= SERIES.length) {
    _otherLabel = "";
    assignCategoryColors(ranked);
    return all;
  }
  const TOP = SERIES.length - 1;
  _otherLabel = `Other (${ranked.length - TOP} categories)`;
  assignCategoryColors(ranked.slice(0, TOP).concat(_otherLabel));
  /* _otherLabel lands in slot TOP (== SERIES.length-1), which is still a real SERIES
     hue, so the aggregate slice would take a category colour instead of the grey its
     folded-in members render as (they fall through CATEGORY_COLOR to OTHER_COLOR). Pin
     the aggregate to OTHER_COLOR explicitly so the "Other" slice and its members match. */
  _catSlot.set(_otherLabel, OTHER_COLOR);
  return all;
}

/* The chart label for one row's category: itself, or the shared "Other" slice. */
export function sliceLabel(cat) {
  return _catSlot.has(cat) ? cat : _otherLabel || cat;
}

export function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (e) {
    return "";
  }
}

/* The four tiles above the Market pages. Each one is counted from the rows on screen; a measure the corpus
   does not carry prints "—" rather than 0. */
export function marketMetrics(tenders) {
  const list = tenders || [];
  const { open, awarded, closed } = bucketTenders(list);
  const countries = new Set(list.map((t) => t.country).filter(Boolean));
  const portals = new Set(list.map((t) => hostOf(t.url)).filter(Boolean));
  const priced = list.filter(hasAmount);
  const totals = valueTotals(list);
  const tiles = [
    {
      id: "active-tenders",
      act: "active",
      v: String(open.length),
      sub: `open of ${list.length} tracked · ${awarded.length} awarded, ${closed.length} closed`,
    },
    {
      id: "markets",
      act: "markets",
      v: String(countries.size),
      sub: topOf(list, "country"),
    },
    {
      id: "source-portals",
      act: "portals",
      v: String(portals.size),
      sub: `distinct portals feeding this slice`,
    },
    {
      /* An unmeasured total is "—", never 0 — a zero here would read as "these
         contracts are worth nothing". */
      id: "value-disclosed",
      act: "value",
      v: formatTotals(totals),
      unit: "",
      sub: priced.length
        ? `${priced.length} of ${list.length} publish an amount${totals.length > 1 ? ` · ${totals.length} currencies, not converted` : ""}`
        : "no tender on record publishes an amount",
    },
  ];
  return tiles.map(({ id, ...t }) => ({ ...t, key: id, l: MARKET_TILE_LABEL[id] }));
}

function topOf(list, field) {
  const n = {};
  list.forEach((t) => {
    if (t[field]) n[t[field]] = (n[t[field]] || 0) + 1;
  });
  const best = Object.entries(n).sort((a, b) => b[1] - a[1])[0];
  return best ? `${best[0]} leads with ${best[1]}` : "nothing on record";
}

/* Demand split by category. JSW splits Product / Product+MRO / MRO-only; that
   classification is EV-bus specific and has no defence equivalent in this corpus, so
   the honest split here is the one the rows actually carry — `cat`. */
export function demandSplit(tenders) {
  const list = tenders || [];
  const n = {};
  list.forEach((t) => {
    const k = sliceLabel(catOf(t));
    n[k] = (n[k] || 0) + 1;
  });
  /* Ordered by the FIXED palette order, not by count in this slice — so narrowing to
     one country reorders nothing and "Other" stays last where a reader expects it. */
  const order = Array.from(_catSlot.keys());
  return Object.entries(n)
    .map(([label, count]) => ({
      label,
      count,
      pct: list.length ? Math.round((count / list.length) * 100) : 0,
    }))
    .sort((a, b) => {
      const ia = order.indexOf(a.label);
      const ib = order.indexOf(b.label);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
}

/* How much runway is left, over the OPEN set only. Awarded contracts carry dl 0 and no
   deadline; counting them into "no date published" would present concluded programmes
   as still-closing pipeline. */
export function closingWindows(openTenders) {
  const list = openTenders || [];
  return WINDOWS.map((w) => {
    const count = list.filter((t) => w.test(t.dl === STAGE ? 366 : t.dl)).length;
    return {
      key: w.key,
      label: w.label,
      count,
      pct: list.length ? Math.round((count / list.length) * 100) : 0,
    };
  });
}

/* The portals feeding this slice, with what each one contributed. */
export function portalRows(tenders) {
  const n = {};
  (tenders || []).forEach((t) => {
    const h = hostOf(t.url);
    if (!h) return;
    if (!n[h]) n[h] = { host: h, total: 0, open: 0, label: (t.srcs && t.srcs[0] && t.srcs[0].label) || h };
    n[h].total += 1;
    if (t.isLive !== false && t.dl > 0) n[h].open += 1;
  });
  return Object.values(n).sort((a, b) => b.total - a.total);
}

/* The country options for a list of tenders, WITH the row count each one labels.
   Built from the rows the filter narrows -- the open section's rows for the open
   section -- never from every tender: the report offered 22 countries over an
   awarded list that carried 8, and 14 of them returned nothing. */
export function countriesOf(tenders) {
  return facetOptionsByName(tenders, (t) => t.country);
}

/* ── self-check ───────────────────────────────────────────────────────────────
   Runs from DataProvider against the real served set. Asserts the invariants that
   the raw-vs-wired trap breaks, so a regression is loud rather than a wrong chart. */
export function marketSelfCheck(tenders, marketCards) {
  const list = tenders || [];
  if (!list.length) return;

  /* The overview lists a SHORTLIST, not every open tender, and the "Live bids" tile
     counts exactly what is shown -- so the promoted cards must equal marketAttention()
     over the open set. This replaces the older "promoted === all open" invariant: the
     overview is curated now (strong fit or closing soon, falling back to the soonest
     head), and the tile is counted from the same set, so the visible list, the header
     count and the tile cannot drift. Skipped when no cards are passed, so the older
     one-argument call is still valid. */
  if (Array.isArray(marketCards) && marketCards.length) {
    const { open } = bucketTenders(list);
    const promoted = marketCards.filter((c) => c.kind === "tender");
    const attention = marketAttention(open).length;
    if (promoted.length !== attention)
      throw new Error(
        `market: ${promoted.length} promoted tender card(s) but marketAttention() picks ` +
          `${attention} of ${open.length} open -- the shortlist and the "Live bids" tile no longer agree`,
      );
  }
  const { open, awarded, closed } = bucketTenders(list);
  const sum = open.length + awarded.length + closed.length;
  if (sum !== list.length)
    throw new Error(`market: buckets sum to ${sum}, not ${list.length}`);
  if (!open.length && list.length)
    throw new Error(
      "market: zero open tenders - tenders were read RAW (dl null <= 0 is true); " +
        "marketOverview must be given the wired rows from useData()",
    );
  const w = closingWindows(open).reduce((n, b) => n + b.count, 0);
  if (w !== open.length)
    throw new Error(`market: closing windows cover ${w} of ${open.length} open tenders`);
  const s = demandSplit(open).reduce((n, b) => n + b.count, 0);
  if (s !== open.length)
    throw new Error(`market: demand split covers ${s} of ${open.length} open tenders`);

  /* No KSSL category may be folded into the grey "Other" slice. This is the bug the
     nine-slot palette fixes: Artillery and Missiles & Air Defence ranked 7th and 8th
     by contract count and vanished into "Other (2 categories)" -- the client's own
     flagship line, unnamed on the client's own chart. Asserted against the SERVED set
     rather than a fixed list, so it fires the moment the taxonomy outgrows the palette
     again instead of silently folding whichever two rank lowest.

     Counted from the ranking directly, NOT from _catSlot: this runs in DataProvider
     and initCategoryPalette only runs when the Market page renders, so reading the
     slot map here would assert against an empty map on every load. */
  const folded = categoryRank(list)
    .map((r) => r.label)
    .filter((l) => !GREY_CATS.has(l))
    .slice(SERIES.length);
  if (folded.length)
    throw new Error(
      `market: ${folded.length} categor${folded.length === 1 ? "y is" : "ies are"} ` +
        `folded into "Other" (${folded.join(", ")}) -- SERIES has ${SERIES.length} ` +
        "hues for them. Add a validated hue (dataviz palette checker, both surfaces) " +
        `rather than letting a ${clientShort()} line go unnamed.`,
    );
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
    .sort((a, b) => (a.dl || 0) - (b.dl || 0));
}

export function reportFacets(scope, { country, cat } = {}) {
  const rows = scope || [];
  return {
    countries: countriesOf(rows.filter((t) => rowCat(t, cat))),
    cats: categoryRank(rows.filter((t) => rowCountry(t, country))).map((c) => ({ v: c.label, n: c.count })),
  };
}

/* The note under the active table said "no tender on record publishes a value" as a
   hard-coded string, on a corpus where 14 do. Measured from the rows instead. */
export function valueNote(rows) {
  const list = rows || [];
  const priced = list.filter(hasAmount).length;
  return priced
    ? `${priced} of ${list.length} publish${priced === 1 ? "es" : ""} a value`
    : "no tender listed here publishes a value";
}
