/* Company Profile: everything the corpus holds about one rival, assembled in one place.

   The rule this file exists to keep: a section appears only when it has rows. Four of
   the things a profile is normally expected to carry — leadership, facilities, sales
   figures, a forward timeline — are NOT in this corpus at all, and there is no field
   they could be read from. They are named in `NOT_COLLECTED` and rendered as an
   explicit absence, because an empty box under a heading reads as "nothing is
   happening" when the truth is "nobody has collected this".

   Two joins here are easy to get wrong, and both have burnt this codebase before:
     * `competitors` is keyed by SLUG, `companySources` by DISPLAY NAME. Joining a
       profile on the wrong one returns undefined for all thirty companies.
     * patents attach through `PATENTS.byCompetitor[cid]`, which adaptPatents() builds
       by token-matching legal assignee names to trading names. `byAssignee[name]` is
       the raw index and misses on exactly the cases the adapter exists to fix. */

import { revenueTierOf } from "./revenueFacet.js";
import { unescapeEntities } from "./html.js";
import { companyCountries, companyOrigin } from "./countryFacet.js";
import { compareCards } from "./overview.js";
import { threatOf } from "./threat.js";

/* These fields are rendered as TEXT, not injected as HTML, so an entity in the record
   ("Defence &amp; Aerospace" on Kongsberg) reaches the screen as the five literal
   characters. Decode once, here, rather than at each of the eight render sites. */
const txt = (s) => unescapeEntities(s || "").trim();

/* The ONE capitalisation rule for every category, sector and industry label.
 *
 * There used to be three, and they disagreed on more than case. lib/profile.js
 * title-cased without touching the rest of a word, so 'defense services' became
 * 'Defense Services' here and 'Defence Services And Solutions' there; Products.jsx
 * carried its own formatCategoryTitle with a different acronym list that lower-cased
 * the tail; and a third helper handled product specs. The two defaults were not even
 * spelled the same way -- 'Defence & Aerospace' against 'Defense Systems' -- so the
 * same empty field read British in one view and American in the next.
 *
 * Deliberately returns "" for an empty input. The old sector formatter answered
 * 'Defence & Aerospace', and profile.js passed the HEADQUARTERS field through it, so
 * every competitor with no recorded HQ displayed its head office as 'Defence &
 * Aerospace' -- 136 of 178 served competitors have no hq value. A default belongs to
 * the field that wants one, not to the formatter every field shares. */
/* No acronym list lives here (it held defence, currency and company abbreviations): casing follows the
   stored text. The label rule below raises the first letter of a lower-case or mixed-case word and lower-cases
   the rest of it; a word that carries a digit, and a word that is ALL capitals (ARI, BAE, UK), is kept exactly
   as stored. An all-capitals token is never altered. */
/* A separator that separates nothing is a defect, not a word. Partner labels arrive
   as "Saab," and "Merlin,", and one of those joined into a list prints "Saab,, Foo" --
   the double comma reported on L&T's product content (FE 31). Collapse a repeated
   comma, reattach a floating one, and drop one that leads or trails. A thousands
   separator ("1,000 hp") is none of these and is untouched. */
export function tidySeparators(raw) {
  return String(raw == null ? "" : raw)
    .replace(/\s+([,;])/g, "$1")
    .replace(/([,;])(?:\s*[,;])+/g, "$1")
    .replace(/·(?:\s*·)+/g, "·")
    .replace(/^[\s,;·]+|[\s,;·]+$/g, "")
    .trim();
}

/* EVERY word is capitalised, connectors included: "Defence Services And Solutions",
   not "... and Solutions". Conventional title case lower-cases short connectors, and
   the first pass did that, but the house style here is Pascal case across the board --
   one rule with no exception list is also the only version that cannot drift. */

/* The listed acronym, whole, or its plural with the small s it came with: "UAVs",
   "MRAPs", "ATGMs" -- never "UAVS", never "Uavs". Shared by the label rule and the
   product rule so the two cannot disagree on what an acronym is.

   The plural reading needs a stem of three letters or more. With two-letter stems
   it misfires on other acronyms: "EOS" is a company, not the plural of EO, and
   "IRS" is not two infrareds. Measured over the 482 company and partner labels in
   the served set, that was the only misreading the rule produced. */
export function formatLabel(raw) {
  if (!raw) return "";
  // "Counterparty" is the extractor's term; the product speaks of "Competitor"
  // everywhere on screen (QA: zero occurrences of "Counterparty").
  if (String(raw).trim().toLowerCase() === "counterparty") return "Competitor";
  const s = tidySeparators(unescapeEntities(String(raw)).replace(/&amp;/g, "&"));
  if (!s) return "";

  const token = (word) => {
    if (!word) return "";
    /* Punctuation travels with the word in a space split, so 'defense,' never matched
       the spelling rule and one comma was enough to leave 'Defense' on screen. Peel it
       off, decide on the word, then put it back. */
    const edge = word.match(/^([^A-Za-z0-9&·/-]*)(.*?)([^A-Za-z0-9&·/-]*)$/);
    if (edge && (edge[1] || edge[3]) && edge[2]) {
      return edge[1] + token(edge[2]) + edge[3];
    }
    if (word.includes("/")) return word.split("/").map(token).join("/");
    if (word.includes("-")) return word.split("-").map(token).join("-");
    if (word === "&" || word === "·") return word;
    /* A word with a digit in it is a designation -- P3TS, IP67, K9, 155mm -- and its
       case is part of the name. No list can hold every designation, and lower-casing
       the tail of one is exactly how Eviden's receiver came to print "P3ts" (FE 32). */
    if (/\d/.test(word)) return word;
    /* An all-capitals token of the stored text is kept as stored: ARI stays ARI, BAE stays BAE. Lower-casing
       its tail was how a company acronym printed as "Ari". */
    if (/[A-Z]/.test(word) && word === word.toUpperCase()) return word;
    const low = word.toLowerCase();
    // one spelling of the word this whole product is about
    if (low === "defense" || low === "defence") return "Defence";
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  };

  return s.split(/\s+/).map(token).join(" ");
}

/* A HEADLINE, unlike a label, is somebody else's sentence.

   The feed prints about 1,400 of them straight from their publishers, and the
   publishers disagree with each other: of the 138 market cards, 29 arrive in title
   case ("US Navy Seeks Carrier-Based Combat Drone Prototypes") and 109 in sentence
   case ("US Navy issues RFI for carrier-based Collaborative Combat Aircraft"), so one
   feed reads as two feeds stacked. Same split on the other two lanes -- 84/361 on
   competitive, 63/179 on technology.

   formatLabel is the WRONG tool here. It lower-cases every word it cannot find in a
   fixed acronym list, and a headline is full of acronyms no list will ever hold: RFI,
   DAPA, AMEV, HIMARS, LRAShM, KONGSBERG, HF-III. Running the label rule over headlines
   would print "Us Navy Issues Rfi For Carrier-Based Collaborative Combat Aircraft".

   So this rule only ever RAISES a letter and never lowers one. Whatever the publisher
   capitalised stays capitalised, which preserves every acronym without knowing any of
   them, and a word that does not begin with a letter is not a word to raise -- so
   "120mm", "8x8", "F-35" and a currency figure all survive untouched.

   The one hand-cut exception is the "x" of a calibre. In "30mm x 173 Airburst" that x
   is a multiplication sign; every other lone letter, "a" included, is a word and is
   raised like any other.

   Titles carry markup (bolded figures) and are injected as HTML, so tags and entities
   are stepped over rather than read as words -- without that "&amp;" comes out
   "&Amp;" and reaches the screen as five literal characters. */
const capWord = (w) => {
  const m = w.match(/^([^A-Za-z0-9]*)([a-z][\s\S]*)$/);
  return m ? m[1] + m[2].charAt(0).toUpperCase() + m[2].slice(1) : w;
};

export function titleCaseHeadline(raw) {
  if (!raw) return "";
  const words = (part) =>
    // a hyphen is a word break: 'carrier-based' -> 'Carrier-Based'
    part.replace(/[^\s-]+/g, (w, at, s) =>
      w === "x" && /\d[a-z]*\s*$/.test(s.slice(0, at)) && /^\s*\d/.test(s.slice(at + 1))
        ? w
        : capWord(w));
  return String(raw)
    .split(/(<[^>]*>|&[a-zA-Z#][a-zA-Z0-9]*;)/)
    // odd slots are the tags and entities the split captured; only text is touched
    .map((part, i) => (i % 2 ? part : words(part)))
    .join("");
}

/* A PRODUCT NAME is neither a label nor a headline, and it took the wrong rule on
   each side of the same screen.

   The dataset funnel cased products with titleCaseHeadline (raise only), so "nag
   carrier" became "Nag Carrier" and "uav swarms" became "Uav Swarms". Products.jsx
   then ran formatLabel over the SAME names, which lower-cases every word outside the
   list: "NAMICA (Nag carrier)" printed "Namica (Nag Carrier)", Eviden's "P3TS" printed
   "P3ts", ARI's "(ASTT)" and "(DSRV)" printed "(Astt)" and "(Dsrv)". Two rules, so the
   heading and the line under it disagreed on one product (FE 32, FE 33, FE 34).

   This is the one product rule, and it is the headline rule plus the acronym list:
   nothing is ever lowered (a designation no list holds -- K9, YFQ-44A, BrahMos --
   survives untouched), and a listed acronym typed in lower case is raised whole so
   it prints in full upper case wherever it appears (T 20). Entities are decoded
   because every site that prints a product prints it as text. */
export function formatProductName(raw) {
  if (!raw) return "";
  const s = tidySeparators(unescapeEntities(String(raw)).replace(/&amp;/g, "&"));
  if (!s) return "";
  return titleCaseHeadline(s);
}

/* Title case for a notice/headline title. A lower-case word is raised; the rest of a mixed word is
   lowered. What must not be touched is kept exactly as stored (R15):
     - an ALL-CAPITALS token (ARI, BAE, (TEST), OR) -- display reflects the stored text
     - mixed-case designations (sUAS, BrahMos)
     - any token carrying a digit (M109, K9, YFQ-44A)
   Minor words (of, and, for ...) go lower unless they lead the title, and unless they are all capitals.
   A hyphen is a word break, so each side is cased on its own. */
const allCaps = (t) => /[A-Z]/.test(t) && t === t.toUpperCase();
const MINOR_WORDS = new Set(["a", "an", "and", "as", "at", "but", "by", "for", "from",
  "in", "nor", "of", "on", "or", "per", "the", "to", "via", "vs", "with"]);
const caseCore = (core) => {
  if (/[a-z]/.test(core) && /[A-Z]/.test(core)) return core; // sUAS, BrahMos
  if (/\d/.test(core)) return core;                          // M109, K9
  if (allCaps(core)) return core;                            // ARI, BAE, TEST
  return core.charAt(0).toUpperCase() + core.slice(1).toLowerCase();
};
const casePart = (part) => {
  // peel leading/trailing punctuation so "AI," or "(DSRV)" still resolves on the core
  const m = part.match(/^([^A-Za-z0-9]*)([\s\S]*?)([^A-Za-z0-9]*)$/);
  return m && m[2] ? m[1] + caseCore(m[2]) + m[3] : part;
};
export function smartTitleCase(raw) {
  if (!raw) return "";
  let wi = -1;
  return String(raw).split(/(\s+)/).map((tok) => {
    if (tok === "" || /^\s+$/.test(tok)) return tok;
    wi += 1;
    if (wi > 0 && MINOR_WORDS.has(tok.toLowerCase()) && !allCaps(tok)) return tok.toLowerCase();
    // A token carrying a digit is a platform designation (AH-64, KC-46, YFQ-44A, BMP-2,
    // 155mm). Case each hyphen part as a designation: the digit part stays verbatim, a
    // listed acronym is raised (bmp-2 -> BMP-2), an already-capitalised alpha part is kept
    // (AH stays AH, not "Ah"), and only a bare lowercase alpha part is title-cased.
    if (/\d/.test(tok)) {
      return tok.split("-").map((part) => {
        if (/\d/.test(part)) return part;
        if (/[A-Z]/.test(part)) return part;
        return part.charAt(0).toUpperCase() + part.slice(1);
      }).join("-");
    }
    return tok.split("-").map(casePart).join("-");
  }).join("");
}

/* Sector carries a default because a competitor with no sector is still in this
   industry; headquarters and the rest use formatLabel directly and stay blank. */
export function formatSectorName(rawSector) {
  return formatLabel(rawSector) || "";
}

/* Standardized company name formatting helper. Reads the ONE acronym list above:
   no acronym list: the stored casing is kept for short capitals. */
export function formatCompanyName(rawName) {
  if (!rawName) return "";
  let s = unescapeEntities(String(rawName)).trim();
  return s
    .split(/\s+/)
    .map((word) => {
      if (word.includes("/")) {
        return word
          .split("/")
          .map((part) => formatCompanyName(part))
          .join(" / ");
      }
      // an all-capitals token of the stored name is kept as stored (ARI, BAE, KONGSBERG)
      if (/[A-Z]/.test(word) && word === word.toUpperCase()) return word;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ");
}

/* Three of these four are now HARVESTED from the maker's own site — see
   pipeline/harvest/. What remains genuinely uncollected is the forward timeline, and a
   company with no harvested rows still shows the honest absence rather than an empty box.

   `sourcedSections` decides per COMPANY, not globally: Saab has leadership and sales but
   no facilities row, and printing "not collected" under a heading we did fill for the
   company next to it would be worse than either. */
export const NOT_COLLECTED = {
  leadership: "no officer named on this company's own pages",
  facilities: "no plant or site named on this company's own pages",
  sales: "no revenue or order-book figure published on this company's own pages",
  timeline: "no dated event series - news coverage on record, not a programme calendar",
};

/* A harvested field: [{value, detail, url, line}]. `line` is the VERBATIM sentence the
   value was read from, so the panel can show its evidence exactly as the tender and
   matchup surfaces do. Anything that is not that shape is ignored rather than rendered —
   a half-written row is how a "sourced" badge ends up over nothing. */
export function sourcedRows(c, field) {
  const v = c && c[field];
  if (!Array.isArray(v)) return [];
  /* `line` (the quoted sentence) is written by the old corpus fill only; rows loaded from the
     client's Excel (leaders, facilities) carry name + source url and no quote, so the url is
     the requirement. */
  return v.filter((r) => r && r.value && r.url);
}

/* `updates` is an HTML STRING on ten companies and an always-EMPTY ARRAY on the other
   twenty, and `if ([])` is true — which is how a "Latest updates" heading came to sit
   over nothing on twenty rivals. Read it through here or not at all. */
export function updatesHtml(c) {
  const u = c && c.updates;
  if (typeof u === "string") return u.trim() || "";
  if (Array.isArray(u) && u.length) return u.join("");
  return "";
}

function nameKey(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/* The rivals, in the dataset's own order, with a density figure so the list can show
   which companies are actually worth opening. */
export function rosterOf(d) {
  const clientCid = (d.client && d.client.id);
  /* the same country expression the Products and Partnerships sidebars filter on */
  const order = (d.compOrder || []).filter((cid) => d.competitors[cid]);
  const rest = Object.keys(d.competitors).filter(
    (cid) => order.indexOf(cid) < 0,
  );
  return order
    .concat(rest)
    .filter((cid) => cid !== clientCid)
    .map((cid) => {
      const p = buildProfile(d, cid);
      return {
        cid,
        name: p.name,
        threat: p.threat,
        sector: p.sector,
        countries: companyCountries(d, cid),
        /* where it is FROM, for the Competitor filter. `countries` above is where
           it is RECORDED -- a presence list, which is a different question. */
        origin: companyOrigin(d, cid),
        // revenue band (High / Mid / Emerging / not on record), as the Products sidebar uses
        revenueTier: revenueTierOf(d.competitors[cid]),
        /* how many of the seven backed sections this company actually fills —
           the honest "is there anything here" signal */
        filled: p.sections.filter((s) => s.rows).length,
        total: p.sections.length,
      };
    });
}

export function buildProfile(d, cid) {
  const c = (d.competitors || {})[cid] || {};
  const name = txt(c.name) || cid;
  const nk = nameKey(name);

  /* "everywhere", per the operator -- this list is the other place signal cards are
     sequenced, and it was in serve order (signal_card.ord), which is a storage order:
     rivals first, then coarse month. So a company's own page could open on a low-severity
     card from the same month as a high-severity one. The SAME comparator as the feed,
     not a second rule that happens to agree today. */
  const cards = []
    .concat(d.competitiveCards || [], d.marketCards || [], d.techCards || [])
    .filter((x) => nameKey(x.company) === nk)
    .sort(compareCards(d));

  const matchups = Object.entries(d.matchups || {})
    .filter(([, m]) => nameKey(m.compBy) === nk)
    .map(([id, m]) => ({ id, ...m }));

  const development = [];
  Object.entries(d.innovations || {}).forEach(([domain, list]) => {
    (list || []).forEach((iv) => {
      if (nameKey(iv.driver) === nk) development.push({ domain, ...iv });
    });
  });

  const presence = (d.geoPresence || []).filter((g) => nameKey(g.comp) === nk);

  /* .records, NOT the index entry. adaptPatents builds byCompetitor[cid] as
     { stats, records } -- an OBJECT -- so this handed the panel a thing whose .length
     is undefined, the Patents section counted `undefined` rows for every rival that has
     filings, and profileSelfCheck's "patents is object, not an array" threw on the
     first such rival. DataProvider catches that, so the whole self-check suite has been
     ending in a logged error and never reaching "self-checks complete". A rival with NO
     filings took the `|| []` branch and looked fine, which is why this survived: it is
     broken exactly where there is data. */
  const patents = (((d.PATENTS && d.PATENTS.byCompetitor) || {})[cid] || {}).records || [];

  const sources = (d.companySources || {})[name] || [];

  const leadership = sourcedRows(c, "leadership");
  const facilitiesRows = sourcedRows(c, "facilities");
  const salesRows = sourcedRows(c, "sales");

  const sections = [
    { key: "updates", label: "Latest updates", rows: updatesHtml(c) ? 1 : 0 },
    { key: "products", label: "Products", rows: (c.products || []).length },
    { key: "matchups", label: "Matchups", rows: matchups.length },
    { key: "development", label: "In development", rows: development.length },
    { key: "news", label: "News", rows: cards.length },
    { key: "partners", label: "Partnerships", rows: (c.partners || []).length },
    { key: "presence", label: "Country presence", rows: presence.length },
    { key: "patents", label: "Patents", rows: patents.length },
    { key: "leadership", label: "Leadership", rows: leadership.length },
    { key: "facilities", label: "Facilities", rows: facilitiesRows.length },
    { key: "sales", label: "Sales", rows: salesRows.length },
  ];

  return {
    cid,
    _src: c._src,
    name,
    sector: formatSectorName(c.sector),
    /* NOT formatSectorName: that returns 'Defence & Aerospace' for an empty value, and
       136 of 178 served competitors have no hq, so each of them displayed that sector
       string as its head office. An absent headquarters must render as absent. */
    hq: formatLabel(c.hq),
    site: c.site || "",
    /* The 2026-09-01 columns. They have to be listed here or they stop at this
       function: the Profile panel reads the profile object, not the raw competitor
       row, so a column can pass the view AND the backend allowlist and still never
       reach the screen. That is exactly the gap the hand-typed dossiers filled. */
    starting_year: c.starting_year || null,
    company_size: txt(c.company_size) || null,
    strategic_positioning: txt(c.strategic_positioning) || null,
    global_locations: c.global_locations || [],
    threat: threatOf(c),
    threatNote: txt(c.threatNote),
    /* assess and updates are HTML by design and are injected, not printed */
    assess: c.assess || "",
    updates: updatesHtml(c),
    products: (c.products || []).map((x) =>
      typeof x === "string" ? txt(x) : x),
    matchups,
    development,
    cards,
    partners: c.partners || [],
    presence,
    patents,
    leadership,
    support_leadership: c.support_leadership || [],
    facilities: facilitiesRows,
    /* the Excel writes one {text, fy} object, not rows; Profile's firstFigure reads both shapes */
    sales: salesRows.length ? salesRows : (c.sales && !Array.isArray(c.sales) ? c.sales : salesRows),
    sources,
    sections,
  };
}

/* ── self-check ───────────────────────────────────────────────────────────────
   Runs from DataProvider over the WHOLE roster, because the shape hazards here are
   per-company: the ten string-`updates` rivals, the twenty empty-array ones, the
   fourteen with no country rows and the twenty-four with no news card. A profile
   builder that only ever ran on the first company would pass every one of them. */
export function profileSelfCheck(d) {
  const roster = rosterOf(d);
  if (!roster.length) return; // an empty database is a valid state (nothing approved yet), not a broken roster
  const clientCid = (d.client && d.client.id);
  if (roster.some((r) => r.cid === clientCid))
    throw new Error("profile: the client is listed as its own competitor");
  roster.forEach((r) => {
    const p = buildProfile(d, r.cid);
    if (!p.name) throw new Error(`profile: ${r.cid} built with no name`);
    /* A column can clear the serving_live view AND the backend allowlist and still
       stop here, because the panel reads this object rather than the raw row --
       which is how the Profile page ended up with hand-typed company facts. If the
       dataset carries a value and the profile does not, say so loudly. */
    ["starting_year", "company_size", "strategic_positioning"].forEach((k) => {
      const src = (d.competitors || {})[r.cid] || {};
      if (src[k] != null && src[k] !== "" && p[k] == null)
        throw new Error(`profile: ${r.cid}.${k} is in the dataset but dropped by buildProfile`);
    });
    if (typeof p.updates !== "string")
      throw new Error(`profile: ${r.cid} updates is ${typeof p.updates}, not a string`);
    ["products", "matchups", "development", "cards", "partners", "presence", "patents", "sources"]
      .forEach((k) => {
        if (!Array.isArray(p[k]))
          throw new Error(`profile: ${r.cid}.${k} is ${typeof p[k]}, not an array`);
      });
  });
  /* A profile keyed on the wrong id space returns undefined everywhere and still
     renders — silently empty. If NOTHING in the roster has a single row, that is what
     has happened, not a thin corpus. */
  if (!roster.some((r) => r.filled > 0))
    throw new Error("profile: every company is empty - check the cid/name join");
}
