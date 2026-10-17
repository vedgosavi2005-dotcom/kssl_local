/* Task 6: record data lives in the database, not in modules. One assertion per MAPPING B row:
   the module (or the constant inside it) is gone, and the dataset fixture holds what replaced it.
     node test_records_gone.mjs */
import fs from "node:fs";

let bad = 0;
const ck = (name, ok) => { console.log(`  ${ok ? "ok  " : "FAIL"} ${name}`); if (!ok) bad++; };
const src = (f) => (fs.existsSync(f) ? fs.readFileSync(f, "utf8") : null);
const gone = (f) => ck(`${f} is deleted`, !fs.existsSync(f));
const lacks = (f, re, what) => { const s = src(f); ck(`${f} has no ${what}`, s !== null && !re.test(s)); };

["src/lib/competitorProjects.js", "src/lib/newsLenses.js", "src/lib/glance.js", "src/lib/signalCountry.js",
 "src/lib/dedupeCompanies.js", "src/lib/ipc.js", "src/lib/footprint.js", "src/lib/shortlist.js", "src/lib/tickers.js"].forEach(gone);

lacks("src/lib/projects.js", /export const (PROJECTS_DATA|PROJECT_STAGES|PROJECT_FILTERS|PROJECT_SEQ)/, "project constants");
lacks("src/lib/roster.js", /export const ROSTER|applyRoster/, "company roster");
lacks("src/lib/companyNames.js", /COMPANY_NAMES/, "expansion table");
lacks("src/lib/partnerCategories.js", /export const (PARTNER_CATEGORIES|CATEGORY_GROUPS)/, "category tables");
lacks("src/lib/partners.js", /export const (OV_KIND|OV_DEF)|const (CONF_TAG|REL_SHORT)|PG_REGION_ALIAS|DEFENSE_FIRM_COUNTRIES/, "overlap prose, tag tables or region guesses");
lacks("src/lib/gapAnalysis.js", /GAP_WHY|gapWhyBlock/, "interpretation prose");
lacks("src/lib/specs.js", /SPEC_SYNONYMS/, "synonym table");
lacks("src/lib/patents.js", /const COUNTRY_ALIAS/, "country alias table");
lacks("src/lib/countryFacet.js", /const REGIONS\s*=/, "region word list");
lacks("src/lib/orgident.js", /isJunkPartner|const (NATIONAL|ALIASES)\b/, "junk gate or alias maps");
lacks("src/lib/revenueFacet.js", /REVENUE_LABEL|CRORE_PER_BN/, "tier labels or FX");
lacks("src/lib/gapModel.js", /CR_PER_MILLION|parseCr/, "FX table");
lacks("src/lib/reports.js", /MAT_LAB_REPORT|real, sourced competitor|real where sourced/, "invented report sentences");
lacks("src/lib/dataset.js", /VERIFIED_KSSL_ROSTER|applyRoster|dedupeCompanies/, "fallback partner roster or merge");
lacks("src/pages/competitive/Partnerships.jsx", /VERIFIED_KSSL_PARTNERS/, "second partner roster");
lacks("src/pages/competitive/Products.jsx", /PRODUCT_IMAGE_MAP|CATEGORY_POOLS|getResolvedSpecs|getProductPrograms|Counterpart|"Verified"|"Sovereign"/, "stock photos, fabricated specs/programmes or matchups");
lacks("src/pages/competitive/Profile.jsx", /DUMMY_NEWS_DATES|FALLBACK_NEWS_IMAGES|getLeaderPsychology|cleanNewsCategory|policy-watch|Key Executive/, "invented dates, photos, leader profiles or role");

lacks("src/lib/profile.js", /ACRONYMS|acronymForm/, "acronym list");
lacks("src/lib/gapAnalysis.js", /DAP 2020|SCOMET|Indian defence orders/, "procurement-rule prose");
lacks("src/lib/partners.js", /\|\| "Other"/, "Other fallback");
/* no client name typed into logic: a quoted "KSSL" or Kalyani literal outside comments */
["src/lib/specs.js", "src/lib/gapModel.js", "src/lib/search.js", "src/pages/competitive/Products.jsx"].forEach((f) => {
  const code = (src(f) || "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  ck(`${f} has no KSSL / Kalyani literal in code`, !/["'`(\/^]\s*(KSSL|Kalyani)\b/.test(code));
});
console.log(bad ? `\n${bad} FAILED` : "\nok - no record constant is left in code");
process.exit(bad ? 1 : 0);
