/* Company Profile: one rival's stored facts, assembled for the Profile page.

   Everything comes from the competitor row (data.competitors[cid], built from
   serving.competitive_competitor + _location + _leader + _leader_record by
   backend/areas/a_competitive.py). A section appears only when it has rows; a field
   with no stored value is left out by the page. Nothing here is a default, a rewrite
   of a stored value, or a judgement. */

import { unescapeEntities } from "./html.js";
import { companyOrigin } from "./countryFacet.js";
import { revenueTierOf } from "./revenueFacet.js";

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
const ACRONYMS = new Set([
  "EW", "UAV", "UAS", "C-UAS", "CUAS", "C4I", "C4ISR", "C4", "C2", "OEM", "R&D", "PSU",
  "MBT", "ARV", "HMV", "ICV", "ATGM", "BVR", "JV", "FCV", "RCWS", "RWS", "LMG", "SPH",
  "AD", "OFB", "AI", "MRO", "EO/IR", "EO", "IR", "GPS", "GNSS", "RF", "VTOL", "HE",
  "APFSDS", "ISR", "ISTAR", "SAR", "AESA", "AIS", "SATCOM", "HUD", "FLIR", "IRST",
  "KSSL", "DRDO", "BDL", "BEL", "L&T", "IAF", "BAE", "IAI", "HAL", "JSW", "BHEL",
  "ISRO", "ADA", "NAL", "USA", "US", "UK", "EU", "UN", "UAE", "NATO", "HQ",
  // platform designations, from the product-name formatter this replaced: without
  // them 'BMP-2' comes back 'Bmp-2' and 'MK1' comes back 'Mk1'
  "BMP", "APC", "IFV", "SPG", "MK1", "MK2", "MK3", "T", "LCA", "ATV",
  /* The acceptance sheet (FE 12, FE 32, FE 34, T 20): the roster and its products
     carry these and the list did not, so the sector dropdown printed "Ari", "Mraps",
     "Usvs" and "(Astt)" against a profile heading that printed them correctly.
     Plurals are NOT listed -- the formatter keeps the small s itself (UAVs, MRAPs). */
  "ARI", "SAM", "MRSAM", "LRSAM", "QRSAM", "SHORAD", "VSHORAD", "GBAD", "MANPADS",
  "ASTT", "DSRV", "OPV", "USV", "UGV", "UUV", "AUV", "ROV", "MRAP", "FPV", "PRS",
  "CTAS", "IHE", "HEAT", "ERA", "APS", "MLRS", "MRLS", "MBRL", "ATAGS", "FICV",
  "LMV", "LAV", "JLTV", "ACV", "AMV", "LCH", "LAH", "HALE", "MALE", "NSM", "ESSM",
  "THAAD", "NASAMS", "GMLRS", "MMP", "RPG", "HMG", "GPMG", "IWI", "CIWS", "ASW",
  "AAW", "SSK", "SSN", "AIP", "SIGINT", "ELINT", "COMINT", "ECM", "ECCM", "ESM",
  "DIRCM", "EOD", "IED", "CBRN", "NBC", "NVG", "AR",
]);

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
const acronymForm = (word) => {
  const up = word.toUpperCase();
  if (ACRONYMS.has(up)) return up;
  if (up.length > 3 && up.endsWith("S") && ACRONYMS.has(up.slice(0, -1))) return up.slice(0, -1) + "s";
  return null;
};

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
    const acr = acronymForm(word);
    if (acr) return acr;
    if (word.includes("/")) return word.split("/").map(token).join("/");
    if (word.includes("-")) return word.split("-").map(token).join("-");
    if (word === "&" || word === "·") return word;
    /* A word with a digit in it is a designation -- P3TS, IP67, K9, 155mm -- and its
       case is part of the name. No list can hold every designation, and lower-casing
       the tail of one is exactly how Eviden's receiver came to print "P3ts" (FE 32). */
    if (/\d/.test(word)) return word;
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
  return titleCaseHeadline(s).replace(/[A-Za-z][A-Za-z0-9&]*/g, (w) => acronymForm(w) || w);
}

/* PROPER title case for a notice/headline title (operator: "everything in proper Pascal
   case"). Unlike titleCaseHeadline, which only RAISES, this also LOWERS ordinary all-caps
   words (BRAND-NAME -> Brand-Name, ONLY -> Only) while PRESERVING what must not be touched:
     - listed acronyms via acronymForm (USA, UAV, UAS, UAVs ...)
     - mixed-case designations (sUAS, BrahMos)
     - any token carrying a digit (M109, K9, YFQ-44A)
   Minor words (of, and, for ...) go lower unless they lead the title. A hyphen is a word
   break, so each side is cased on its own. */
const MINOR_WORDS = new Set(["a", "an", "and", "as", "at", "but", "by", "for", "from",
  "in", "nor", "of", "on", "or", "per", "the", "to", "via", "vs", "with"]);
const caseCore = (core) => {
  const acr = acronymForm(core);
  if (acr) return acr;
  if (/[a-z]/.test(core) && /[A-Z]/.test(core)) return core; // sUAS, BrahMos
  if (/\d/.test(core)) return core;                          // M109, K9
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
    if (wi > 0 && MINOR_WORDS.has(tok.toLowerCase())) return tok.toLowerCase();
    // A token carrying a digit is a platform designation (AH-64, KC-46, YFQ-44A, BMP-2,
    // 155mm). Case each hyphen part as a designation: the digit part stays verbatim, a
    // listed acronym is raised (bmp-2 -> BMP-2), an already-capitalised alpha part is kept
    // (AH stays AH, not "Ah"), and only a bare lowercase alpha part is title-cased.
    if (/\d/.test(tok)) {
      return tok.split("-").map((part) => {
        if (/\d/.test(part)) return part;
        const acr = acronymForm(part);
        if (acr) return acr;
        if (/[A-Z]/.test(part)) return part;
        return part.charAt(0).toUpperCase() + part.slice(1);
      }).join("-");
    }
    return tok.split("-").map(casePart).join("-");
  }).join("");
}

/* The sector label rule: house capitalisation, and "" when the row has none (no default). */
export function formatSectorName(rawSector) {
  return formatLabel(rawSector);
}

/* Standardized company name formatting helper. Reads the ONE acronym list above:
   it used to carry its own sixteen, which is how three lists came to disagree. */
export function formatCompanyName(rawName) {
  if (!rawName) return "";
  let s = unescapeEntities(String(rawName)).trim();
  return s
    .split(/\s+/)
    .map((word) => {
      const acr = acronymForm(word);
      if (acr) return acr;
      if (word.includes("/")) {
        return word
          .split("/")
          .map((part) => formatCompanyName(part))
          .join(" / ");
      }
      if (word.length <= 3 && word === word.toUpperCase() && /^[A-Z]+$/.test(word)) return word;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ");
}

/* "USD 2,650": the stored annual_revenue with its stored currency code. The columns carry
   no unit (thousands / millions), so none is printed. "" when there is no amount. */
export function formatRevenue(amount, currency) {
  if (amount == null || amount === "" || !Number.isFinite(Number(amount))) return "";
  const n = Number(amount).toLocaleString("en-US");
  return currency ? `${currency} ${n}` : n;
}

/* The rivals (every competitor row but the client's), in the dataset's own order. */
export function rosterOf(d) {
  const clientCid = d.client && d.client.id;
  const order = (d.compOrder || []).filter((cid) => d.competitors[cid]);
  const rest = Object.keys(d.competitors).filter((cid) => order.indexOf(cid) < 0);
  return order
    .concat(rest)
    .filter((cid) => cid !== clientCid)
    .map((cid) => {
      const c = d.competitors[cid];
      return {
        cid,
        name: txt(c.name) || cid,
        short: txt(c.short),
        legal: txt(c.legal),
        hq: txt(c.hq),
        threat: c.threat || "",
        sector: txt(c.sector),
        origin: companyOrigin(d, cid),
        revenueTier: revenueTierOf(c),
      };
    });
}

export function buildProfile(d, cid) {
  const c = (d.competitors || {})[cid] || {};
  return {
    cid,
    _src: c._src,
    name: txt(c.name) || cid,
    short: txt(c.short),
    legal: txt(c.legal),
    sector: txt(c.sector),
    hq: txt(c.hq),
    starting_year: c.starting_year || null,
    company_size: c.company_size != null && c.company_size !== "" ? Number(c.company_size).toLocaleString("en-US") : null,
    revenue: formatRevenue(c.revenue, c.revenue_currency),
    global_locations: txt(c.global_locations),
    locations: Array.isArray(c.locations) ? c.locations : [],
    threat: c.threat || "",
    leaders: Array.isArray(c.leaders) ? c.leaders : [],
  };
}

/* Lightweight self-check run from DataProvider: every roster row builds a named profile. */
export function profileSelfCheck(d) {
  rosterOf(d).forEach((r) => {
    const p = buildProfile(d, r.cid);
    if (!p.name) throw new Error(`profile: ${r.cid} built with no name`);
    if (!Array.isArray(p.leaders) || !Array.isArray(p.locations))
      throw new Error(`profile: ${r.cid} leaders/locations are not arrays`);
  });
}
