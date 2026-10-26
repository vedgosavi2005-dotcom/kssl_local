/* THE SCREEN'S FURNITURE: words and structure that belong to the front end, not to the database.

   Navigation, pillar names, page headings, tabs, tile labels, time windows, filter controls and their option lists
   are code, defined here exactly as the reference UI defines them (neutral wording, nothing client- or
   product-specific). The database holds the DATA only (the serving tables): every fact, name, number, date and
   judgement on a card comes from the dataset, never from this file. A filter here compares an option CODE against
   the tag value stored on the rows (stance, kind, country, category, ...); the options list is chrome, the values
   it matches are data.

   Stances: threat and watch are the only two. A row stored under any other value has no stance.

   Pure -- no React, no window -- so the tests drive it directly. */

/* ---- stances ------------------------------------------------------------------------------------------------ */
export const STANCES = ["threat", "watch"];
export const STANCE_WORD = { threat: "Threat", watch: "Watch" };
/* THE COMPETITIVE OVERVIEW IS A SHORTLIST (owner 2026-10-23): signals of the last OVERVIEW_DAYS days only (by the card's
   date), at most THREAT_CAP threats and WATCH_CAP watches, the riskiest (probability x impact) first. Every threat and watch,
   of any date, is on Competitor Movement. */
export const OVERVIEW_DAYS = 90;
export const THREAT_CAP = 15;
export const WATCH_CAP = 15;
/* the stance filter options, in menu order: [{code, label}] */
export const STANCE_OPTIONS = STANCES.map((code) => ({ code, label: STANCE_WORD[code] }));
/* A card's stance, or "": only threat or watch count. Anything else has no stance. */
export const stanceOf = (dir) => (STANCES.includes(dir) ? dir : "");
/* the stance words as a fresh object: { threat: "Threat", watch: "Watch" } */
export const stanceWords = () => ({ ...STANCE_WORD });

/* ---- the three overview lanes --------------------------------------------------------------------------------- */
export const COMPETITIVE_TITLE = "Competitive Intelligence";
const ALL_PILL = "All";
const SLOTS = 5; // the metric strip is a grid of five equal columns; unused slots are drawn empty
const STANCE_COLOR = { threat: "var(--threat)", watch: "var(--watch)" };

/* tiles padded with empty slots so the grid keeps its column widths */
const withBlanks = (tiles) => {
  const out = tiles.slice();
  for (let i = 0; out.length < SLOTS; i += 1) out.push({ blank: true, key: `blank-${i}`, l: "", act: "all" });
  return out;
};

/* A tile is bound to its count by KEY (never by its label text); `act` is the filter the tile opens. */
export function competitiveLane() {
  return {
    title: COMPETITIVE_TITLE,
    metrics: withBlanks([
      { key: "threats", l: "Competitive threats", act: "threat" },
      { key: "watch", l: "Watch signals", act: "watch" },
      { key: "companies_tracked", l: "Companies tracked", act: "all" },
    ]),
    filters: [{ f: "all", l: ALL_PILL }, ...STANCES.map((s) => ({ f: s, l: STANCE_WORD[s], c: STANCE_COLOR[s] }))],
    dirWord: stanceWords(),
  };
}

export function technologyLane() {
  return {
    title: "Technology Knowledge",
    metrics: withBlanks([
      { key: "competitor_advances", l: "Competitor advances", act: "rival" },
      { key: "adoptable", l: "Adoptable advances", act: "adopt" },
      { key: "domains_tracked", l: "Domains tracked", act: "all" },
    ]),
    filters: [
      { f: "all", l: ALL_PILL },
      { f: "rival", l: "Competitor Advancements", tag: "rival", c: "var(--threat)" },
      { f: "adopt", l: "Adoptable Advances", tag: "adopt", c: "var(--watch)" },
    ],
    groups: [
      { h: "Competitor Advancements", tags: ["rival"] },
      { h: "Adoptable Advances", tags: ["adopt"] },
    ],
    /* only ADOPTABLE is labelled on a row; a competitor row carries no badge */
    tagWord: { rival: "", adopt: "Adoptable" },
    dirWord: {},
  };
}

export function marketLane() {
  return {
    title: "Top opportunity",
    metrics: withBlanks([
      { key: "latest_tenders", l: "Latest tenders", act: "open" },
      /* "Strong-fit TENDERS", not "Strong fits": the stored count (market_rollups.metrics) is open tenders graded strong
         (3 or more checked requirement lines) and its door filters the tender feed, while the "Projects to win" table
         grades pre-tender projects on another basis -- so the tile read 0 beside a STRONG project row. Relabelled rather
         than adding projects to the count: two different grades in one number would explain neither, and the door could
         not open the projects (functional test G17, 2026-10-25). */
      { key: "strong_fits", l: "Strong-fit tenders", act: "fit" },
      { key: "tender_value", l: "Tender value", act: "valued" },
      { key: "perceived_opportunities", l: "Perceived opportunities", act: "opps" },
    ]),
    filters: [
      { f: "all", l: ALL_PILL },
      { f: "tenders", l: "Latest Tenders", kinds: ["tender"], c: "var(--threat)" },
      { f: "opps", l: "Perceived Opportunities", kinds: ["opportunity"], c: "var(--watch)" },
    ],
    groups: [
      { h: "Latest Tenders", kinds: ["tender"] },
      { h: "Perceived Opportunities", kinds: ["opportunity"] },
    ],
    /* a tender is marked by its `kind`, not by a stance; a global requirement reads as an opportunity on its row
       (the reference wording) and its detail panel carries the watch pill (panelStance) */
    tagWord: { tender: "TENDER", opportunity: "OPPORTUNITY", requirement: "OPPORTUNITY" },
    panelStance: { requirement: "watch" },
    dirWord: {},
  };
}

/* ---- the detail panel ---------------------------------------------------------------------------------------- */
/* the badge word of a promoted tender */
export const TENDER_WORD = "Tender";

/* ---- Competitor Movement --------------------------------------------------------------------------------------- */
/* [key, label, days back from the newest move]; null days = every date */
export const MOMENT_PRESETS = [["today", "Today", 0], ["week", "Week", 6], ["month", "Month", 29], ["all", "All", null]];

/* A moment's stored level -> the stance it draws: a level read as a threat ("high", "threat") or a watch gives that
   stance; any other level (or none) gives "" and draws no pill. */
export function momentStance(level) {
  const v = String(level == null ? "" : level).trim().toLowerCase();
  if (v === "high" || v === "threat") return "threat";
  if (v === "watch") return "watch";
  return "";
}

/* ---- Market Intelligence tabs ------------------------------------------------------------------------------------ */
/* the four tabs of the Cummins Market Intelligence page (owner 2026-10-26: "take the Cummins market section"); the
   by-category cut lives on in the open tab's Demand split pie, which filters the list by category */
export const MARKET_SECTIONS = [
  { id: "outlook", label: "Market outlook" },
  { id: "active", label: "Open tenders and projects" },
  { id: "awarded", label: "Awarded" },
  { id: "closed", label: "Closed" },
];

/* ---- Projects: filter, sequence ------------------------------------------------------------------------------------ */
/* the filter options compare against the stored `region` of a project row */
export const PROJECT_FILTERS = [
  { f: "Domestic", l: "Domestic" },
  { f: "Export", l: "Export" },
];
export const PROJECT_SEQ = [
  ["recent", "Most recent milestone"],
  ["stage", "Furthest along"],
];
export const PROJECT_SEQ_DEFAULT = "recent";
/* the stored kssl_option of a project (what the client can do about it), as a phrase */
export const PROJECT_OPTION_WORD = {
  compete: "bid against it with one of its own products",
  partner: "partner with the competitor or its team",
  supply: "supply a component the project needs",
  none: "nothing in the portfolio fits",
};

/* ---- Market tiles (Tenders / Market Intelligence strip) ------------------------------------------------------------------ */
export const MARKET_TILE_LABEL = {
  "active-tenders": "Active tenders",
  markets: "Markets",
  "source-portals": "Source portals",
  "value-disclosed": "Value disclosed",
};

/* ---- the partnership legend ------------------------------------------------------------------------------------------ */
/* Every kind of tie a rival can have, in legend order. `key` is the slug of the stored partner_type (the `rel` of a
   partnership row); `aliases` are other slugs that name the same kind. A definition may carry {rival} and {client},
   filled with names from the data at render. `overlapKind` names the overlap read a SHARED partner of that kind
   gets (OVERLAP_KINDS). Colours are not here: they follow the legend position (partnerCategories.js). */
export const PARTNER_GROUPS = [
  { key: "channel", label: "Channel & distribution" },
  { key: "supply", label: "Supply chain" },
  { key: "tech", label: "Technology & strategy" },
  { key: "buyer", label: "Buyers & customers" },
];

export const PARTNER_CATEGORIES = [
  { key: "channel-partner", group: "channel", label: "Channel partner", short: "Channel", overlapKind: "channel",
    aliases: ["distribution", "distributor", "dealer", "reseller", "integration"],
    def: "Sells, stocks or services {rival}'s products in an assigned market: {rival}'s route to market there." },
  { key: "supplier", group: "supply", label: "Supplier", short: "Supplier", overlapKind: "supplier",
    aliases: ["component-supplier", "manufacturing", "oem", "framework-supplier", "supply-customer", "supply"],
    // either direction since "Supply / customer" was folded in (prompts/partnership.yml, 2026-10-25)
    def: "{rival} buys parts, products or services from this company, or sells them to it, under a contract or order; a shared supplier can tighten {client}'s own supply." },
  { key: "localization-partner", group: "supply", label: "Localization partner", short: "Local", overlapKind: "supplier",
    aliases: ["localization", "local"],
    def: "Licensed or equipped to make, assemble or source {rival}'s products inside the country, which counts toward local-content rules." },
  { key: "service-partner", group: "supply", label: "Service partner", short: "Service", overlapKind: "service",
    aliases: ["service", "service-and-retrofit-partner"],
    def: "Maintains, repairs and supplies parts for {rival}'s installed products in its territory." },
  { key: "technology-partner", group: "tech", label: "Technology / licence", short: "Tech", overlapKind: "technology",
    aliases: ["technology", "tech", "technology-tot", "licensing", "rnd"],
    def: "A technology, licence or product-development tie that gives {rival} (or the partner) a capability the other supplies." },
  { key: "joint-venture", group: "tech", label: "Joint venture", short: "JV", overlapKind: "technology",
    aliases: ["jv"],
    def: "A jointly owned company with shared investment and control." },
  { key: "teaming", group: "tech", label: "Teaming", short: "Teaming", overlapKind: "technology",
    aliases: ["teaming-agreement", "consortium"],
    // its own kind since 2026-10-25 (owner): it had shown the MoU definition
    def: "{rival} and this company bid for, or deliver, one contract or programme together, each bringing its own part." },
  { key: "acquisition-stake", group: "tech", label: "Acquisition / stake", short: "Acquisition", overlapKind: "technology",
    aliases: ["acquisition", "acq"],
    def: "{rival} owns, or has bought into, the other party (or the reverse)." },
  { key: "mou-strategic", group: "tech", label: "MoU / strategic", short: "MoU", overlapKind: "technology",
    aliases: ["mou", "strategic"],
    def: "A memorandum or strategic agreement: stated intent to cooperate, not yet a supply, licence or ownership contract." },
  { key: "key-account", group: "buyer", label: "Key account", short: "Account", overlapKind: "",
    aliases: ["account", "customer"],
    def: "A named end customer that buys {rival}'s products: the buyer in the relationship." },
  { key: "other", group: "tech", label: "Other", short: "Other", overlapKind: "",
    aliases: ["partner"],
    def: "A tie the source records without classifying its type." },
];

/* The heading and one-line lead of the overlap read in the partnership drawer: what a SHARED partner of that kind
   means for the client. {client} and {rival} are filled from the data. The effects under each heading (what the
   overlap costs the client, point by point) are analysis, so they are DATA (ui.partner_overlap_effect rows keyed by
   overlap kind) and are drawn only when stored. */
export const OVERLAP_KINDS = [
  { kind: "channel", aliases: [], label: "What an overlapping channel costs {client}",
    lead: "the same channel partner represents {client} and {rival}, so the buying decision moves from the customer to the partner" },
  { kind: "supplier", aliases: [], label: "What an overlapping supplier costs {client}",
    lead: "{client} and {rival} buy the same part from the same vendor, so that component stops separating the two offers" },
  { kind: "service", aliases: [], label: "What an overlapping service network costs {client}",
    lead: "the aftermarket is delivered by someone who also earns on {rival}'s installed base" },
  { kind: "technology", aliases: ["tech"], label: "What an overlapping technology partner costs {client}",
    lead: "the partner behind a {client} capability is also inside {rival}, so the capability is a lead-time rather than a moat" },
];

/* ---- Tender card and the Top opportunity tables ------------------------------------------------------------------- */
/* What a tender card prints in a cell the record leaves empty: the value cell says the figure is not disclosed, every
   other cell a dash. These are screen words, never a stored value. */
export const TENDER_EMPTY = "—";
export const TENDER_VALUE_EMPTY = "not disclosed";

/* The tender card's cells, in order: [key of the stored parameter (tenderRow.TENDER_PARAMS), label]. */
export const TENDER_CARD_CELLS = [
  ["buyer", "Buyer"],
  ["country", "Country"],
  ["category", "Category"],
  ["value", "Value"],
  ["status", "Status"],
];

/* How many rows each Top opportunity table lists, and the headings, column titles and one-line notes above them.
   {client} is the client's short name from the data (the empty string when the dataset names none). */
export function cockpitWords(client) {
  const c = client || "";
  return {
    tendersHead: "Top tenders",
    tendersCols: ["Rank", "Tender", "Decides", c ? `${c} fit` : "Fit", c ? `${c} model` : "Model", "Rival to beat", "Revenue"],
    tendersNote: "in the stored rank order",
    tendersEmpty: "No top tender is on record yet.",
    projectsHead: "Projects to win before they tender",
    projectsCols: ["Rank", "Project", "Where it stands", c ? `${c} fit` : "Fit", c ? `${c} model` : "Model", "Rival to beat", "Revenue"],
    projectsNote: "projects with no tender yet, in the stored rank order",
    projectsEmpty: "No project to win before it tenders is on record yet.",
    movesHead: "Next moves",
    movesCols: ["Due", "Action", "Tender"],
    movesNote: "in the stored order",
    movesEmpty: "No next move is on record yet.",
  };
}
