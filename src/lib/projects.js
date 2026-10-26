/* Projects feed: what each competitor is working on or pursuing. Pure -- the page renders what this returns.
   The rows are data.projects (serving.competitive_project and its child tables); the region filters and the
   sequence menu are front-end chrome (chrome.js); the stage steps are data.projectsConfig.stageSteps (the stages the
   projects carry). Nothing here is a record. */
import { formatDate } from "../utils/formatDate.js";
import { countryVocabulary, countriesNamedIn, companyOrigin } from "./countryFacet.js";
import { geoCountryNames, REGIONS } from "./geoCountries.js";

/* The stance of a project is its stored `assessment.stance`: threat or watch, nothing else (chrome.stanceOf). */

export const day = (d) => (d && /^\d{4}/.test(d) ? (/^\d{4}$/.test(d) ? `${d}-01-01` : /^\d{4}-\d{2}$/.test(d) ? `${d}-01` : d) : "");

export const latestWhen = (p) => (p.latest && p.latest.date ? formatDate(p.latest.date) : "");

/* The sorts the browser can do on stored values. A menu entry whose code is not here (a size or value
   sort: no numeric column holds it) is not offered -- see sortableSeq. */
const SEQ = {
  recent: (a, b) => day(b.latest && b.latest.date).localeCompare(day(a.latest && a.latest.date)),
  stage: (a, b) => (b.stageRank || 0) - (a.stageRank || 0) || SEQ.recent(a, b),
};
export const sortableSeq = (options) => (options || []).filter((o) => o && SEQ[o[0]]);

const haystack = (p) =>
  [p.name, p.company, p.customer, p.location, p.kind, p.stage, p.stageNote, (p.overview || []).join(" "), (p.specs || []).map((s) => s.v).join(" ")].join(" ").toLowerCase();

/* `cid` null = every competitor. `filters` is the chrome filter list (chrome.js; their codes are matched against the stored `region`). `counts` is what each button would show
   under the current competitor and search, so no button promises rows it lacks; `perCompetitor` is each
   rival's count under the current region filter and search. */
/* `country` (owner 2026-10-25): keep only projects whose derived `countries` (projectCountries) include it; null = all. */
export function projectFeed({ projects, filters = [], cid = null, filter = "all", query = "", seq = "recent", country = null } = {}) {
  projects = projects || [];
  const tokens = String(query || "").toLowerCase().split(/\s+/).filter(Boolean);
  const searched = projects.filter((p) => tokens.every((t) => haystack(p).includes(t)) && (!country || (p.countries || []).includes(country)));
  const mine = cid ? searched.filter((p) => p.cid === cid) : searched;
  const counts = { all: mine.length };
  filters.forEach(({ f }) => { counts[f] = mine.filter((p) => p.region === f).length; });
  const inRegion = (p) => filter === "all" || p.region === filter;
  const perCompetitor = {};
  searched.filter(inRegion).forEach((p) => { perCompetitor[p.cid] = (perCompetitor[p.cid] || 0) + 1; });
  const rows = mine.filter(inRegion).slice().sort(SEQ[seq] || SEQ.recent);
  return { rows, counts, perCompetitor, total: projects.length };
}

/* the tiles above the list, counted from the rows */
export function projectMetrics(projects) {
  projects = projects || [];
  const rivals = new Set(projects.map((p) => p.cid)).size;
  return [
    { act: "all", l: "Projects tracked", v: String(projects.length), unit: " projects" },
    { act: "rivals", l: "Competitors covered", v: String(rivals), unit: " companies" },
    { act: "threat", l: "Read as a threat", v: String(projects.filter((p) => p.assessment && p.assessment.stance === "threat").length), unit: " projects" },
  ];
}

/* ---- display helpers (functional test G15, 2026-10-25) ----------------------------------------------------------
   The tester found project rows reading ": Tata Advanced Systems" (no stage), rows with no headline at all (no name),
   ISO dates inside stage notes ("on 2026-10-13") and 39 of 117 "Kind" values starting lower-case. The missing names
   and stages are a DATA gap (the project prompt fills them); these helpers only make what is on screen clean: an empty
   field never prints with its separator, and a stored value is shown in the house format. Nothing is invented: every
   fallback below is another stored field of the same record. */

const filled = (v) => v != null && String(v).trim() !== "";

/* "initial supply contract" -> "Initial supply contract": the first letter only, the rest is data and stays as stored */
export const sentenceCase = (s) => (filled(s) ? String(s).trim().replace(/^[a-z]/, (c) => c.toUpperCase()) : "");

/* every ISO date inside a sentence ("on 2026-10-13") in the one house format ("on 13 Oct 2026") */
export const plainDates = (s) => (filled(s) ? String(s).replace(/\b\d{4}-\d{2}-\d{2}\b/g, (d) => formatDate(d)) : "");

/* the record's first sentence, when it is short enough to stand as a headline */
const firstSentence = (paras) => {
  const t = (paras || []).find(filled);
  if (!t) return "";
  const m = /^(.+?[.!?])(\s|$)/.exec(String(t).trim());
  const s = (m ? m[1] : String(t).trim()).replace(/[.!?]$/, "").trim();
  return s.length <= 140 ? s : "";
};

/* The best available headline: the stored name; else the overview's first sentence ("Vietnam signed a contract with
   India for BrahMos Block-III supersonic cruise missiles"); else the kind, for the customer when one is stored; else
   "<competitor> project". Never an empty title over a stage note. */
export function projectTitle(p) {
  if (!p) return "";
  if (filled(p.name)) return String(p.name).trim();
  const lead = firstSentence(p.overview);
  if (lead) return plainDates(lead);
  if (filled(p.kind)) return sentenceCase(p.kind) + (filled(p.customer) ? ` for ${String(p.customer).trim()}` : "");
  if (filled(p.customer)) return `${filled(p.company) ? `${p.company} project` : "Project"} for ${String(p.customer).trim()}`;
  return filled(p.company) ? `${p.company} project` : "Project";
}

/* The stage word: the stored stage; else the step its stored stageRank points at in the stage track (the same step the
   panel's track already lights as "now"), so the row and the track cannot disagree; else "" (the row then prints no
   stage label and no colon). */
export function projectStage(p, steps) {
  if (!p) return "";
  if (filled(p.stage)) return String(p.stage).trim();
  const r = Number(p.stageRank);
  const s = Array.isArray(steps) && r >= 1 ? steps[r - 1] : null;
  return filled(s) ? String(s).trim() : "";
}

/* ---- country, money and plain text for the project card (owner 2026-10-25) -------------------------------------------
   The Domestic / Export filter is replaced by a Country filter: the country is WHERE THE PROJECT IS (the customer's
   country), not the company's home. serving.competitive_project has no country column, so it is read from the record's
   own text, in this order, and the first step that names a country wins:
     1. the customer ("Italian Army" -> Italy, "U.S. Army" -> United States, "Finland and Sweden" -> both);
     2. a Domestic project: the competitor's stated origin (data.competitors[cid].country);
     3. the project name ("Guided Pinaka rockets for Armenia");
     4. the location ("Toronto, Canada").
   A word counts as a country only when the dataset's own country vocabulary or the map's country table spells it so, or
   it is the plain adjective of one of those ("Swedish" -> Sweden). Nothing named -> no country: the project is left out
   of the filter's options, never filed under a guess. */

/* one spelling per country on screen (the map table holds several: "USA", "United States", ...) */
const ONE_NAME = {
  US: "United States", USA: "United States", "United States of America": "United States", "U S": "United States", "U S A": "United States",
  UK: "United Kingdom", Korea: "South Korea", "Republic of Korea": "South Korea", "Russian Federation": "Russia",
  Czechia: "Czech Republic", "The Netherlands": "Netherlands", KSA: "Saudi Arabia", UAE: "United Arab Emirates",
  "Türkiye": "Turkey", "Viet Nam": "Vietnam",
};
/* the adjective a customer is usually written with ("Indian Navy", "Royal Thai Army") -> the country it names */
const ADJECTIVE = {
  American: "United States", British: "United Kingdom", Indian: "India", Italian: "Italy", Swedish: "Sweden", Polish: "Poland",
  Danish: "Denmark", Norwegian: "Norway", Finnish: "Finland", Estonian: "Estonia", Latvian: "Latvia", Lithuanian: "Lithuania",
  Malaysian: "Malaysia", Romanian: "Romania", Czech: "Czech Republic", Slovak: "Slovakia", Slovenian: "Slovenia",
  French: "France", German: "Germany", Russian: "Russia", Canadian: "Canada", Pakistani: "Pakistan", Moroccan: "Morocco",
  Hellenic: "Greece", Greek: "Greece", Thai: "Thailand", Ukrainian: "Ukraine", Armenian: "Armenia", Israeli: "Israel",
  Turkish: "Turkey", Spanish: "Spain", Portuguese: "Portugal", Dutch: "Netherlands", Belgian: "Belgium", Swiss: "Switzerland",
  Austrian: "Austria", Hungarian: "Hungary", Bulgarian: "Bulgaria", Croatian: "Croatia", Serbian: "Serbia", Korean: "South Korea",
  Japanese: "Japan", Chinese: "China", Taiwanese: "Taiwan", Saudi: "Saudi Arabia", Emirati: "United Arab Emirates",
  Qatari: "Qatar", Egyptian: "Egypt", Philippine: "Philippines", Filipino: "Philippines", Indonesian: "Indonesia",
  Vietnamese: "Vietnam", Bangladeshi: "Bangladesh", Australian: "Australia", Brazilian: "Brazil", Mexican: "Mexico",
  Nigerian: "Nigeria", Kenyan: "Kenya", Algerian: "Algeria", Irish: "Ireland",
};
const countryName = (c) => ONE_NAME[c] || ADJECTIVE[c] || c;

function countryTerms(d) {
  if (d && d.__projectCountryTerms) return d.__projectCountryTerms;
  const terms = new Set([...countryVocabulary(d), ...geoCountryNames(), ...Object.keys(ONE_NAME), ...Object.keys(ADJECTIVE)]);
  [...terms].forEach((t) => REGIONS.test(t) && terms.delete(t));
  if (d && typeof d === "object") {
    try { Object.defineProperty(d, "__projectCountryTerms", { value: terms, enumerable: false, writable: true }); } catch (e) { /* frozen: recompute */ }
  }
  return terms;
}

/* the countries one project is in (usually one; a multi-nation buy names several); [] when no field names one */
export function projectCountries(p, d) {
  if (!p) return [];
  const terms = countryTerms(d);
  /* in the order the text names them ("Finland, Latvia, Sweden ..."), one entry per country */
  const named = (s) => {
    if (!filled(s)) return [];
    const low = String(s).toLowerCase();
    const at = (t) => {
      const i = low.indexOf(t.toLowerCase());
      return i >= 0 ? i : Math.max(0, low.indexOf(t.toLowerCase().replace(/ /g, ".")));
    };
    return [...new Set(countriesNamedIn(String(s), terms).sort((a, b) => at(a) - at(b)).map(countryName))];
  };
  const customer = named(p.customer);
  if (customer.length) return customer;
  if (p.region === "Domestic") {
    const o = companyOrigin(d, p.cid);
    if (o && !REGIONS.test(o)) return [countryName(o)];
  }
  const title = named(p.name);
  return title.length ? title : named(p.location);
}

/* ---- money ----------------------------------------------------------------------------------------------------------
   "19000 crore INR" -> "₹19,000 crore (~US$2.0 bn)": rupees in crore (or lakh) with separators, and a rough dollar figure
   from the STORED rate (data.fxRates.USD, rupees per dollar), rounded to two significant figures. No stored rate -> no
   dollar figure. "about 70 billion USD" -> "about US$70 bn". Any other value is returned as stored (a repeated unit word,
   "seven years years", is printed once). Display only: the stored value is not changed. */
const MULT = { crore: 1e7, crores: 1e7, cr: 1e7, lakh: 1e5, lakhs: 1e5, million: 1e6, mn: 1e6, m: 1e6, billion: 1e9, bn: 1e9 };
const QUALIFIER = "about|around|approximately|approx\\.?|nearly|almost|roughly|over|more than|less than|under|up to|at least|close to";
const QUAL_LEAD = new RegExp(`^(${QUALIFIER})\\s+`, "i");
const QUAL_PAREN = new RegExp(`\\s*\\((${QUALIFIER})\\)\\s*`, "i");
const CURRENCY = { INR: () => /\bINR\b|₹|\bRs\.?(?=\s|\d)|\brupees?\b/gi, USD: () => /\bUSD\b|US\$|\$/g };
const NUMBER = /^(\d{1,3}(?:,\d{2,3})+|\d+)(\.\d+)?\s*(crores?|cr|lakhs?|million|mn|m|billion|bn)?\s*(crores?|lakhs?|million|billion)?$/i;

function moneyParts(value, label, code) {
  let s = String(value == null ? "" : value);
  if (!CURRENCY[code]().test(s)) return null;
  s = s.replace(CURRENCY[code](), " ");
  let qual = "";
  const qp = QUAL_PAREN.exec(s);
  if (qp) { qual = qp[1]; s = s.replace(QUAL_PAREN, " "); }
  let each = "";
  if (/\beach\b/i.test(s)) { each = " each"; s = s.replace(/\beach\b/i, " "); }
  s = s.replace(/\s+/g, " ").trim();
  const ql = QUAL_LEAD.exec(s);
  if (ql) { qual = qual || ql[1]; s = s.slice(ql[0].length); }
  const m = NUMBER.exec(s);
  if (!m) return null;
  let unit = String(m[3] || m[4] || "").toLowerCase();
  if (!unit && /\bcrores?\b/i.test(label || "")) unit = "crore";
  if (!unit && /\blakhs?\b/i.test(label || "")) unit = "lakh";
  const stated = m[1] + (m[2] || "");
  const amount = Number(stated.replace(/,/g, "")) * (MULT[unit] || 1);
  return Number.isFinite(amount) && amount > 0 ? { amount, stated, unit, qual: qual.toLowerCase(), each } : null;
}

const upTo2 = (n, locale) => n.toLocaleString(locale, { maximumFractionDigits: 2 });

/* rupees: "₹19,000 crore", "₹4.25 lakh", "₹50,000" */
export function rupeeText(amount) {
  if (amount >= 1e7) return `₹${upTo2(amount / 1e7, "en-IN")} crore`;
  if (amount >= 1e5) return `₹${upTo2(amount / 1e5, "en-IN")} lakh`;
  return `₹${upTo2(amount, "en-IN")}`;
}

/* a rough dollar figure, two significant figures: 2.004e9 -> "2.0 bn", 3.55e6 -> "3.6 m", 527000 -> "530,000" */
export function usdRough(x) {
  const sig = (v) => (v >= 10 ? String(Number(v.toPrecision(2))) : v.toPrecision(2));
  if (x >= 1e9) return `${sig(x / 1e9)} bn`;
  if (x >= 1e6) return `${sig(x / 1e6)} m`;
  return Number(x.toPrecision(2)).toLocaleString("en-US");
}

/* a stated dollar amount, its digits kept: "70" billion -> "US$70 bn"; a bare 49295084 -> "US$49.3 m" */
function usdStated({ amount, stated, unit }) {
  if (/^(billion|bn)$/.test(unit)) return `US$${stated} bn`;
  if (/^(million|mn|m)$/.test(unit)) return `US$${stated} m`;
  if (amount >= 1e9) return `US$${(Math.round(amount / 1e7) / 100).toLocaleString("en-US")} bn`;
  if (amount >= 1e6) return `US$${(Math.round(amount / 1e5) / 10).toLocaleString("en-US")} m`;
  return `US$${amount.toLocaleString("en-US")}`;
}

/* one spec value as the card prints it; `label` is the stored spec label (it may carry the unit: "Contract value (crore)") */
export function specValue(label, value, fx) {
  const v = filled(value) ? String(value).trim() : "";
  if (!v) return "";
  const inr = moneyParts(v, label, "INR");
  if (inr && (inr.unit !== "m" || /\bmillion\b/i.test(v))) {
    const rate = Number(fx && fx.USD);
    const usd = rate > 0 ? ` (~US$${usdRough(inr.amount / rate)})` : "";
    return `${inr.qual ? `${inr.qual} ` : ""}${rupeeText(inr.amount)}${inr.each}${usd}`;
  }
  const usd = moneyParts(v, label, "USD");
  if (usd) return `${usd.qual ? `${usd.qual} ` : ""}${usdStated(usd)}${usd.each}`;
  return v.replace(/\b([A-Za-z]+)\s+\1\b/g, "$1");
}

/* A long stored spec label as a plain short one -- a fixed rule, not a rewrite of the data:
   "Programme outlay approved by Cabinet Committee on Security" -> "Approved budget"; a unit or currency in brackets
   ("Contract value (crore)", "(Swedish krona)") goes, because the value now carries it. */
export function specLabel(k) {
  const s = filled(k) ? String(k).trim() : "";
  if (/^program(me)? outlay approved\b/i.test(s)) return "Approved budget";
  return s
    .replace(/\s*\((?:crores?|lakhs?|swedish krona|INR|USD|EUR)\)/gi, "")
    .replace(/\((?:crores?|lakhs?),\s*/gi, "(")
    .trim();
}

/* the project's headline value for the at-a-glance block: a spec whose short label IS the deal's value ("Contract
   value", "Combined contract value", "Programme value", "Approved budget"), a total first; never a part of it ("Phase 2
   contract value", "Cost per gun", "Estimated value of follow-on contract"). "" when no spec is that. */
const HEADLINE = /^(total |combined |overall |gross |approved )?(contract |programme |program |order |deal |package |procurement |sale )?(value|budget|outlay)\b/i;
const NOT_HEADLINE = /\b(per|each|share|option|estimate|estimated|expected|follow-on|potential|previous|modification|not signed)\b/i;
const HAS_CURRENCY = /\b(INR|USD|EUR|GBP|SEK|NOK|DKK|PLN|CZK|CAD|KRW|THB|AUD|JPY|CHF)\b|₹|\$|€|£|\bcrores?\b/i;
export function projectValue(p, fx) {
  const ok = ((p && p.specs) || []).filter((x) => x && filled(x.v) && HEADLINE.test(specLabel(x.k)) && !NOT_HEADLINE.test(`${x.k} ${x.v}`)
    && HAS_CURRENCY.test(`${x.k} ${x.v}`));
  const s = ok.find((x) => /^(total|combined|overall|gross)\b/i.test(specLabel(x.k))) || ok[0];
  return s ? specValue(s.k, s.v, fx) : "";
}

/* ---- the timeline, in plain words ------------------------------------------------------------------------------------
   A `label_change` step is pipeline bookkeeping (prompts/story.py writes "Trials -> Production (Milestone C approval and
   move to full-rate produc…)", cut at 50 characters): it never reaches the client. On the review build it is shown as a
   plain sentence ("Stage moved from Trials to Production"), marked review only. A step's `changed` note that reads like a
   change log (an arrow) or was cut ("…") is not shown either. */
const LABEL_CHANGE = /^\s*label[\s_-]*change\s*$/i;
const CHANGE_LOG = /\s(?:->|→)\s|…\s*\)?\s*$|\.\.\.\s*$/;
export function timelineSteps(p, review = false) {
  if (!p) return [];
  if (!Array.isArray(p.steps) || !p.steps.length) {
    return (p.timeline || []).map((e) => ({ date: e.date, line: e.label, changed: "", expected: !!e.expected, url: null, review: false }));
  }
  return p.steps.flatMap((t) => {
    if (LABEL_CHANGE.test(String(t.type || ""))) {
      if (!review) return [];
      const m = /^(.+?)\s(?:->|→)\s(.+?)(?:\s*[:(]|$)/.exec(String(t.changed || ""));
      /* a move to or from "none" or a stance word is not a stage move: nothing to show */
      const stage = (x) => x && !/^(none|unknown|watch|threat)$/i.test(x.trim());
      return m && stage(m[1]) && stage(m[2]) ? [{ date: t.date, line: `Stage moved from ${m[1].trim()} to ${m[2].trim()}`, changed: "", expected: false, url: t.url, review: true }] : [];
    }
    const changed = filled(t.changed) && !CHANGE_LOG.test(String(t.changed)) && String(t.changed).trim().toLowerCase() !== "none" ? String(t.changed).trim() : "";
    return [{ date: t.date, line: t.line, changed, expected: t.type === "planned", url: t.url, review: false }];
  });
}
