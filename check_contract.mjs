// Contract check: does a /api/dataset snapshot carry every global of docs/ui_port/MAPPING.md section A
// with the container type the frontend indexes into ("presence is not shape", UI_CONTRACT s15)?
//   node check_contract.mjs fixtures/kssl_dataset.json
// Exit 0 when clean; otherwise exit 1 with one line per violation.
import fs from "node:fs";

// MAPPING.md A, global by global. "list" = array, "dict" = plain object (not an array).
// Globals whose A disposition is not-shipped / remove-genset / hidden:chat are not listed (CAT_META, counterRules,
// overviewMetrics, chatSuggest, sourceRegistry, companySources, clientProducts, geoLocations, ...).
const EXPECTED = {
  client: "dict",                // A: client
  competitors: "dict",           // A: competitors (cid -> row, the client row has dir='client')
  compOrder: "list",             // A: compOrder
  competitorNews: "dict",        // A: competitorNews (cid -> news + moment rows)
  overviewConfig: "dict",        // A: overviewConfig (lanes competitive, market, technology)
  competitiveCards: "list",      // A: *Cards
  techCards: "list",             // A: *Cards
  marketCards: "list",           // A: marketCards
  details: "dict",               // A: details (card id -> panel)
  matchups: "dict",              // A: matchups (id -> pair)
  POS_CATS: "list",              // A: POS_CATS
  CAT_KEY: "dict",               // A: CAT_KEY
  tenders: "list",               // A: tenders
  tpAllCountries: "list",        // A: tpAllCountries
  tpAllCats: "list",             // A: tpAllCats
  topOpportunities: "dict",      // A: topOpportunities
  awards: "list",                // A: awards
  globalRequirements: "list",    // A: globalRequirements (KSSL key, feeds marketCards)
  geoComps: "list",              // A: geoComps
  geoData: "dict",               // A: geoData
  geoCountries: "list",          // A: geoCountries
  geoPresence: "list",           // A: geoPresence (a list: profile.js filters it)
  actLabel: "dict",              // A: actLabel
  KSSL_CATS: "list",             // A: KSSL_CATS
  PATENTS: "dict",               // A: PATENTS
  techAreaMeta: "dict",          // A: techAreaMeta
  techCats: "list",              // A: techCats
  innovations: "dict",           // A: innovations (category id -> list)
  KSSL_PARTNERS: "list",         // A: client partners
  REL_LABEL: "dict",             // A: REL_LABEL
  COMPSYN: "dict",               // A: COMPSYN
  TRACEIDS: "dict",              // A: TRACEIDS
  FIELDSYN: "dict",              // A: FIELDSYN
  projects: "list",              // A: projects
  projectsConfig: "dict",        // A: projectsConfig
  sectionVisibility: "dict",     // A: sectionVisibility {key: boolean}
  database: "dict",              // A: KSSL-only (Trace / Review layer)
  databaseSchema: "dict",        // A: KSSL-only
};

// Lists whose items are review cards: each must carry _src.t and _src.id.
const CARD_LISTS = ["competitiveCards", "techCards", "marketCards", "tenders", "awards", "globalRequirements", "projects", "KSSL_PARTNERS"];
// Dicts of cards: every value (or every list item in it) must carry _src.t and _src.id.
const CARD_DICTS = { competitors: "item", matchups: "item", competitorNews: "list" };

const kind = (v) => (Array.isArray(v) ? "list" : v === null ? "null" : typeof v === "object" ? "dict" : typeof v);
const bad = [];
const P = process.argv[2];
if (!P) { console.error("usage: node check_contract.mjs <dataset.json>"); process.exit(2); }
const d = JSON.parse(fs.readFileSync(P, "utf8"));

for (const [g, want] of Object.entries(EXPECTED)) {
  if (!(g in d)) bad.push(`${g}: missing (want ${want})`);
  else if (kind(d[g]) !== want) bad.push(`${g}: is ${kind(d[g])}, want ${want}`);
}

const srcOk = (it) => it && it._src && typeof it._src.t === "string" && it._src.t && typeof it._src.id === "string" && it._src.id;
const checkItems = (name, arr) => {
  arr.forEach((it, i) => { if (!srcOk(it)) bad.push(`${name}[${i}]: missing _src.t / _src.id`); });
};
for (const g of CARD_LISTS) if (kind(d[g]) === "list") checkItems(g, d[g]);
for (const [g, mode] of Object.entries(CARD_DICTS)) {
  if (kind(d[g]) !== "dict") continue;
  for (const [k, v] of Object.entries(d[g])) {
    if (mode === "list") {
      if (!Array.isArray(v)) bad.push(`${g}.${k}: is ${kind(v)}, want list`);
      else checkItems(`${g}.${k}`, v);
    } else if (!(g === "competitors" && v.dir === "client") && !srcOk(v)) bad.push(`${g}.${k}: missing _src.t / _src.id`);
  }
}

// inner containers the frontend indexes into without a guard
const want = (path, v, w) => { if (kind(v) !== w) bad.push(`${path}: is ${kind(v)}, want ${w}`); };
if (kind(d.client) === "dict") for (const f of ["id", "name", "short"]) if (!(f in d.client)) bad.push(`client.${f}: missing`);
if (kind(d.overviewConfig) === "dict") {
  for (const lane of ["competitive", "market", "technology"]) {
    const L = d.overviewConfig[lane];
    want(`overviewConfig.${lane}`, L, "dict");
    if (kind(L) !== "dict") continue;
    for (const [f, w] of [["cards", "list"], ["metrics", "list"], ["groups", "list"], ["filters", "list"], ["dirWord", "dict"], ["badgeClass", "dict"]]) want(`overviewConfig.${lane}.${f}`, L[f], w);
  }
}
if (kind(d.competitors) === "dict") {
  for (const [cid, c] of Object.entries(d.competitors)) {
    for (const f of ["products", "partners"]) want(`competitors.${cid}.${f}`, c[f], "list");
    if (!("name" in c)) bad.push(`competitors.${cid}.name: missing`);
  }
  const clients = Object.values(d.competitors).filter((c) => c.dir === "client");
  if (clients.length !== 1) bad.push(`competitors: ${clients.length} rows with dir='client', want 1`);
}
if (kind(d.compOrder) === "list" && kind(d.competitors) === "dict")
  d.compOrder.forEach((cid) => { if (!(cid in d.competitors)) bad.push(`compOrder: ${cid} is not in competitors`); });
if (kind(d.sectionVisibility) === "dict")
  for (const [k, v] of Object.entries(d.sectionVisibility)) if (typeof v !== "boolean") bad.push(`sectionVisibility.${k}: is ${kind(v)}, want boolean`);
if (kind(d.PATENTS) === "dict") {
  for (const [f, w] of [["techAreas", "list"], ["byArea", "dict"], ["byAssignee", "dict"], ["_meta", "dict"]]) want(`PATENTS.${f}`, d.PATENTS[f], w);
  if (kind(d.PATENTS._meta) === "dict") want("PATENTS._meta.providers", d.PATENTS._meta.providers, "list");
}
if (kind(d.innovations) === "dict") for (const [k, v] of Object.entries(d.innovations)) want(`innovations.${k}`, v, "list");
if (kind(d.geoData) === "dict")
  for (const [c, byCountry] of Object.entries(d.geoData)) {
    want(`geoData.${c}`, byCountry, "dict");
    if (kind(byCountry) === "dict") for (const [k, rows] of Object.entries(byCountry)) want(`geoData.${c}.${k}`, rows, "list");
  }
if (kind(d.topOpportunities) === "dict") {
  for (const f of ["topTenders", "projectsBeforeTender", "nextMoves", "metrics"]) want(`topOpportunities.${f}`, d.topOpportunities[f], "list");
  want("topOpportunities.notes", d.topOpportunities.notes, "dict");
}
if (kind(d.details) === "dict") for (const [k, v] of Object.entries(d.details)) {
  want(`details.${k}`, v, "dict");
  if (kind(v) === "dict") { want(`details.${k}.facts`, v.facts, "list"); want(`details.${k}.srcs`, v.srcs, "list"); }
}
if (kind(d.FIELDSYN) === "dict") want("FIELDSYN.patterns", d.FIELDSYN.patterns, "list");
if (kind(d.projectsConfig) === "dict")
  for (const [f, w] of [["stageSteps", "list"]]) want(`projectsConfig.${f}`, d.projectsConfig[f], w);

// Field names (MAPPING.md A, the "field" column): a key must be PRESENT on every item; its value may be null
// when the column is empty. This guards the restructure of each global, not the data inside it.
const KEYS = {
  rival: ["name", "legal", "sector", "hq", "country", "threat", "assess", "strategic_positioning", "strengths", "weaknesses",
    "starting_year", "company_size", "sales", "revenue_filter", "global_locations", "leadership", "partners", "products"],
  clientRow: ["name", "dir", "sector", "hq", "country", "strategic_positioning", "leadership", "global_locations", "partners", "products"],
  leader: ["value", "detail", "url", "full_name", "experience", "education"],
  news: ["id", "title", "description", "source", "date", "category", "url", "image"],
  moment: ["level", "analysis", "country", "card", "lenses"],
  card: ["id", "dir", "title", "meta", "sowhat", "ago", "url"],
  feedCard: ["tags", "company", "image", "ksslImpact", "ksslImpactKind", "seq"],
  detail: ["title", "facts", "what", "why", "lens", "url", "srcs", "provenance"],
  matchup: ["cat", "catKey", "comp", "compBy", "bf", "anchor", "country", "reason", "verdict", "verdictH", "edge",
    "specDims", "specDecided", "specs", "advBf", "advComp"],
  spec: ["l", "cv", "cn", "kv", "kn", "u", "hi"],
  tender: ["id", "title", "issuer", "country", "cat", "value", "qty", "deadline", "closingDate", "posted", "status", "urlKind",
    "url", "srcs", "desc", "req", "matches", "rank", "fit", "clientFit", "revenueEstimate", "expectedRevenue", "revenueMid",
    "lean", "leanTxt", "competitorFit", "actions"],
  product: ["id", "name", "category", "country", "specs", "source", "source_url", "sources", "tier", "programs", "news", "matchupId"],
  partner: ["id", "cid", "label", "ptype", "rel", "note", "date", "as_of", "country", "confidence", "srcnote", "verdict", "impact", "src"],
  clientPartner: ["id", "label", "cid", "ptype", "rel", "country", "note", "role", "status", "date", "as_of", "mean", "insight"],
  award: ["segment", "winner", "brand", "buyer", "site", "title", "title_ar", "programme", "tender_no", "date", "year",
    "value", "currency", "bids", "country", "url", "source"],
  project: ["id", "cid", "company", "name", "kind", "region", "customer", "location", "stage", "stageRank", "stageNote",
    "specs", "timeline", "latest", "overview", "assessment", "sources"],
  geoComp: ["id", "name", "isBf", "dir", "hq"],
  geoRow: ["name", "c", "val", "since", "qty", "stage", "note", "srcnote", "srcs"],
  patent: ["no", "title", "assignee", "comp_id", "status", "filed", "country", "ipc", "area", "threat", "relev", "url"],
  innovation: ["t", "mat", "gap", "driver", "horizon", "body", "impact", "whatsNew", "compNote", "sources", "url", "srcs"],
  topTender: ["tenderId", "title", "issuer", "country", "rank", "decides", "ksslFit", "ksslModel", "rivalToBeat", "revenue"],
  topProject: ["id", "title", "issuer", "country", "stage", "ksslFit", "ksslModel", "rivalToBeat", "revenue"],
  nextMove: ["action", "due", "tenderTitle"],
};
const need = (path, o, keys) => {
  if (kind(o) !== "dict") { bad.push(`${path}: is ${kind(o)}, want dict`); return; }
  keys.forEach((k) => { if (!(k in o)) bad.push(`${path}.${k}: missing`); });
};
const needAll = (name, arr, keys) => { if (kind(arr) === "list") arr.forEach((it, i) => need(`${name}[${i}]`, it, keys)); };
if (kind(d.competitors) === "dict") for (const [cid, c] of Object.entries(d.competitors)) {
  need(`competitors.${cid}`, c, c.dir === "client" ? KEYS.clientRow : KEYS.rival);
  needAll(`competitors.${cid}.leadership`, c.leadership, KEYS.leader);
  needAll(`competitors.${cid}.products`, c.products, KEYS.product);
  needAll(`competitors.${cid}.partners`, c.partners, KEYS.partner);
}
if (kind(d.competitorNews) === "dict") for (const [cid, rows] of Object.entries(d.competitorNews)) {
  needAll(`competitorNews.${cid}`, rows, KEYS.news);
  if (kind(rows) === "list") rows.forEach((r, i) => { if ("level" in r || "card" in r) need(`competitorNews.${cid}[${i}]`, r, KEYS.moment); });
}
needAll("competitiveCards", d.competitiveCards, [...KEYS.card, ...KEYS.feedCard]);
needAll("techCards", d.techCards, [...KEYS.card, ...KEYS.feedCard, "competitor", "lens"]);
needAll("marketCards", d.marketCards, ["id", "title", "meta", "sowhat", "ago"]);
if (kind(d.details) === "dict") for (const [k, v] of Object.entries(d.details)) need(`details.${k}`, v, KEYS.detail);
if (kind(d.matchups) === "dict") for (const [k, m] of Object.entries(d.matchups)) {
  need(`matchups.${k}`, m, KEYS.matchup);
  needAll(`matchups.${k}.specs`, m.specs, KEYS.spec);
}
needAll("tenders", d.tenders, KEYS.tender);
needAll("KSSL_PARTNERS", d.KSSL_PARTNERS, KEYS.clientPartner);
needAll("awards", d.awards, KEYS.award);
needAll("projects", d.projects, KEYS.project);
needAll("geoComps", d.geoComps, KEYS.geoComp);
needAll("geoPresence", d.geoPresence, ["comp", "cid", "country"]);
if (kind(d.geoData) === "dict") for (const [c, byCountry] of Object.entries(d.geoData))
  if (kind(byCountry) === "dict") for (const [k, rows] of Object.entries(byCountry)) needAll(`geoData.${c}.${k}`, rows, KEYS.geoRow);
if (kind(d.PATENTS) === "dict") {
  for (const [a, rows] of Object.entries(d.PATENTS.byArea || {})) needAll(`PATENTS.byArea.${a}`, rows, KEYS.patent);
  for (const [a, rows] of Object.entries(d.PATENTS.byAssignee || {})) needAll(`PATENTS.byAssignee.${a}`, rows, KEYS.patent);
}
if (kind(d.innovations) === "dict") for (const [k, rows] of Object.entries(d.innovations)) needAll(`innovations.${k}`, rows, KEYS.innovation);
needAll("techCats", d.techCats, ["id", "name"]);
if (kind(d.topOpportunities) === "dict") {
  needAll("topOpportunities.topTenders", d.topOpportunities.topTenders, KEYS.topTender);
  needAll("topOpportunities.projectsBeforeTender", d.topOpportunities.projectsBeforeTender, KEYS.topProject);
  needAll("topOpportunities.nextMoves", d.topOpportunities.nextMoves, KEYS.nextMove);
}
if (kind(d.COMPSYN) === "dict") for (const [cid, c] of Object.entries(d.COMPSYN)) {
  need(`COMPSYN.${cid}`, c, ["thesis", "vulns", "strat"]);
  if (kind(c.strat) === "dict") need(`COMPSYN.${cid}.strat`, c.strat, ["thesis", "pattern", "sowhat"]);
  needAll(`COMPSYN.${cid}.vulns`, c.vulns, ["title", "from", "intel"]);
}
if (kind(d.TRACEIDS) === "dict") for (const [cid, v] of Object.entries(d.TRACEIDS)) want(`TRACEIDS.${cid}`, v, "list");
if (kind(d.FIELDSYN) === "dict") { need("FIELDSYN", d.FIELDSYN, ["patterns", "bottom"]); needAll("FIELDSYN.patterns", d.FIELDSYN.patterns, ["field", "pattern", "implication", "n", "total"]); }

// Card ids are one id space (feed, details, browser-built tender cards): no id may repeat across the three card lists,
// and every details key must be a card id of one of them or a tender / signal id.
{
  const seen = new Map();
  for (const g of ["competitiveCards", "techCards", "marketCards"])
    if (kind(d[g]) === "list") d[g].forEach((c) => {
      if (seen.has(c.id)) bad.push(`${g}: card id ${c.id} repeats ${seen.get(c.id)}`);
      else seen.set(c.id, g);
    });
  if (kind(d.details) === "dict") for (const [k, v] of Object.entries(d.details)) if (v.id !== k) bad.push(`details.${k}: id ${v.id} differs from its key`);
  // a card's detail panel is keyed by the card id
  for (const [g, list] of [["marketCards", d.marketCards], ["techCards", d.techCards]])
    if (kind(list) === "list") list.forEach((c) => { if (kind(d.details) === "dict" && !(c.id in d.details)) bad.push(`${g}: card ${c.id} has no details row`); });
}
// awards may have a null date; the list must still be present and ordered by date, nulls last
if (kind(d.awards) === "list") {
  const dated = d.awards.map((a) => a.date);
  const firstNull = dated.indexOf(null);
  if (firstNull >= 0 && dated.slice(firstNull).some((x) => x !== null)) bad.push("awards: a dated award follows an undated one (nulls must sort last)");
}

if (bad.length) {
  bad.forEach((b) => console.log("CONTRACT: " + b));
  console.log(`${bad.length} violation(s)`);
  process.exit(1);
}
console.log(`contract ok: ${Object.keys(EXPECTED).length} globals checked`);
