# Audit group C: Partnerships, Projects, Geo Footprint, Patents

Scope: routes `partnerships`, `projects`, `geo`, `patents-comp`. Read-only audit; no code was edited.
Method: every value was traced component -> `src/lib` helper -> `data.X` key (`src/lib/dataset.js` `wireDataset`, `backend/app.py` `build_*`) -> DB column; then mapped to `docs/audit_v2/schema_v2_columns.txt`.

## 0. Ground truth (what the backend serves today)

All 36 tables used by these four pages hold **0 rows** in the live DB (checked with `count(*)` on every `serving.competitive_partnership*`, `client_partner*`, `competitive_project*`, `competitive_geo*`, `competitive_patent*`, `competitive_competitor*`, `client_account` and the 12 `ui.*` tables of these pages). "Served today" below therefore means "mapped by `backend/app.py`", not "has data".

| Dataset key | Built at | Content |
|---|---|---|
| `competitors[id].partners` | `backend/app.py:163` | hard-coded `[]` for every competitor. **Partnerships has no data path at all.** |
| `KSSL_PARTNERS` | `app.py:536` | hard-coded `[]` (client_partner* never read) |
| `PATENTS` | `app.py:532` | hard-coded `{"byArea":{},"byAssignee":{},"_meta":{"total":0}}` (competitive_patent_* never read) |
| `projects`, `projectsConfig` | `build_projects` `app.py:246-282` | maps 14 of 23 `competitive_project` columns; `overview`, `specs` hard-coded `[]`; no timeline, sources, stageRank |
| `geoData`, `geoComps`, `geoCountries` | `build_geo` `app.py:285-315` | maps `competitive_geo_company_presence` + `competitive_geo_location` + `competitive_geo_product` only |
| `REL_LABEL`, `COMPSYN`, `FIELDSYN`, `TRACEIDS`, `actLabel`, `CAT_META`, `counterRules`, `KSSL_CATS`, `sourceRegistry` | not emitted | read by partners.js / geo.js; all `undefined` today (see sections 1 and 3) |

**Schema join gaps that break these pages even once data is loaded**

| Gap | Evidence | Effect |
|---|---|---|
| `competitive_project.competitor_id` is `bigint`; `competitive_competitor.competitor_id` is `uuid` | `information_schema` | `build_projects` does `competitors.get(text(cid))` (`app.py:255`) and `if cid in competitors` (`app.py:281`): never matches, so the Projects left sidebar (competitor list) is empty and `company` falls back to `company_display`. |
| `competitive_geo_company_presence.competitor_id` is `bigint` (uuid in competitor table) | same | `data.competitors[geoComp.id]` is `undefined` in Geo.jsx (`:155`, `:208`), so threat/sector/hq/products of the rival never resolve. |
| `competitive_partnership.partner_id` is `uuid`; `client_partner.client_partner_id` is `bigint` | same | No key to join a rival's partner to the client's partner; shared-partner overlap can only be a name comparison (section 3). |
| `competitive_patent_portfolio.competitor_id` is `uuid` (OK) but there is no client row / client_id | schema | Patents cannot show "KSSL's own filings" (section 1, Patents). |

**Backend bugs visible on these pages even with data**

| Bug | Where | Effect |
|---|---|---|
| `latest` emitted as `{date, note}`, UI reads `latest.label` | `app.py:264` vs `Projects.jsx:425` | drawer prints "2026-03: undefined" |
| `assessment.read` emitted as a string, UI treats it as an array (`.length`, `.map`) | `app.py:265` vs `Projects.jsx:507-508` | `TypeError: read.map is not a function` as soon as a project has an assessment; crashes the drawer |
| geo `src` set to `relationship_text` | `app.py:310` | `rawSources()` (`Geo.jsx:90`) renders free text as a hyperlink URL |
| geo `c` (activity code) set to `presence.activity_type` raw text; `data.actLabel` not served | `app.py:306`, `Geo.jsx:99` | works only because `activityLabel()` falls back to the raw code; CSS classes `ri-act lp/pt/ex/sv/bf` and `geo.dirForAct` expect codes, not text |
| `companyOrigin()` reads `competitors[id].country` (`countryFacet.js:103`), backend emits `origin` (`app.py:155`) | | "Head office" tooltip badge and origin never fire |
| presence with no product rows gets a blank pseudo-record `[{}]` (`app.py:301-302`) | | counted as a "footprint record" named "Unnamed footprint record" |

Legend for the tables: Kind = STORED / COMPUTED-JS / COMPUTED-BACKEND / CHROME / INVENTED / NO-COLUMN. Action = map / keep / hide / remove / decide. "P" = `competitive_partnership`, "CP" = `client_partner`.

---

## 1A. Partnerships (`src/pages/competitive/Partnerships.jsx`, `src/lib/partners.js`)

Partner row fields the UI reads (all `undefined` today because `partners: []`): `id label name kind ptype rel country status ended confidence date as_of deal note insight mean src srcnote basis image sig cid shared koel clientTie overlapChecked`. Mapped one by one in the second table.

### Page elements

| UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Client name in empty-state copy | `data.client.short \|\| name \|\| "KSSL"` `Partnerships.jsx:27` | `client_account.brand_name/client_name` (`app.py:466-468`); fallback literal "KSSL" | `client_account.brand_name` | STORED + INVENTED fallback `"KSSL"` (`:27`, also `data.client?.id \|\| "KSSL"` `:40,42,156,180`) | map; drop literal fallback |
| Left list: competitor names | `data.compOrder`, `competitors[k].name` `:255-266,:534` | `competitive_competitor.display_name\|legal_name` (`app.py:152`) | `competitive_competitor.display_name` | STORED (sorted by name in `roster.js:11-20`: COMPUTED-JS) | keep |
| Left list: status dot colour | `co.dir \|\| "watch"` `:533` | `dir` not emitted for rivals (only client) | `competitive_competitor.threat_level` | INVENTED default (every rival renders the "watch" dot) | map to `threat_level`, no default |
| Left list: count per competitor | `(co.partners \|\| []).length` `:496-497,536` | `[]` | `COUNT(competitive_partnership)` per `competitor_id` (or `mapped_partner_count`) | COMPUTED-JS: raw relationship rows, not distinct companies (differs from graph count) | decide: stored `mapped_partner_count` vs computed; make list and graph agree |
| Left list search | name + sector + hq + partner names + literal word "overlap" if shared `:255-263` | partners empty | name/`industry_sector`/`headquarters`/`partner_name`; overlap flag computed | COMPUTED-JS (`"overlap"` token injected by code) | keep search, drop injected token |
| Country filter "All countries (N)" | `facetOptionsByName(rivalIds, companyCountries)` `:169-171`, `countryFacet.js` `companyCountries` | built from geoData keys + `global_locations` text parse + hq parts + tender/matchup countries | `competitive_competitor.origin_country` (or `competitive_competitor_location.country`) | COMPUTED-JS multi-source union (rule: footprint keys UNION `global_locations` named countries UNION hq parts that appear in a country vocabulary built from geo, tenders, matchups) | decide: filter on stored `origin_country` only |
| Centre title `"{name} · alliance network"` | `:553` | | `display_name` | CHROME + STORED | keep |
| Empty graph copy | `:556-561` "...or pick Regions to see {client}'s partners by country" | | | CHROME, but the sentence is false: `ksslCo` (`:146-154`) is built and never used, Regions mode draws the selected rival (`gc = c` `:155`) | fix copy; delete `ksslCo` |
| Graph: company hub | `c.name` `typeGraphSvg` | | `display_name` | STORED | keep |
| Graph: category nodes ("Technology", "Supplier", "Joint Venture", "MoU / Strategic", "Acquisition", "Other") and colours | `PG_TYPE_META` `partners.js:1106-1113`, key = `pgTypeKey(row.rel)` `:1114` | `rel` code not served | `competitive_partnership.partner_type` (free text varchar 128) | **NO-COLUMN for `rel`**: grouping needs a 6-way code. Labels/colours in code = vocabulary. | decide: group by distinct `partner_type` value (labels from DB, colours cycled) |
| Graph: "N PARTNERS" under each category | `${g.nodes.length} PARTNERS` `:1379,1563` | | | COMPUTED-JS: distinct canonical companies in that bucket | keep after node rule decided |
| Graph: region mode (flag per country) | `pgRegionGroups` `:1207`, country from `r.country` else `DEFENSE_FIRM_COUNTRIES` regex lookup by company name `:1167-1205` | | `competitive_partnership.region` | COMPUTED-JS + **INVENTED** (see 2) | map `region`; remove name->country table; unknown -> "Unknown" bucket (already exists `:1212`) |
| Flags | `countryFlagDisc` `countryFlags.js` (834 lines, 51 flags, 108 alias keys) | | | CHROME (artwork); name->flag-key map is vocabulary, not company data | keep; "GLOBAL" disc is the fallback |
| Partner leaf nodes: label, sub-label (type), red ring if overlap | `pgNodes` `:752`, `tieKindShort` `:600` | | `partner_name`, `partner_type`; overlap computed | COMPUTED-JS | map |
| Leaf cap 16 per branch | `Math.min(focus.nodes.length,16)` `:1567` | | | COMPUTED-JS silent truncation (no "+N more" label) | decide |
| Legend: hub name, type colours, "Country / Region", "Overlapping Partner" | `:690-714` | | | CHROME | keep |
| Zoom/pan/group-by controls | `viewBoxStr` `:112-122`, toolbar | | `ui.competitive_partnership_graph.group_by/zoom_level` exist, unread | CHROME / view state | keep (state stays in memory) |
| Drawer head `"{name} · Mapped Partners"` / "Relationship detail" | `:406-409` | | | CHROME | keep |
| Drawer roster header `"{name} ALLIANCE NETWORK (TOP 40 OF N MAPPED PARTNERS)"` | `partners.js:2362-2369` | | | COMPUTED-JS: cap 40 and rank `pgEvidence` (+2 URL src, +1 typed, +1 jv/tech/licen/acq/manuf, + min(rows,4)), overlaps first (`:774-777`) | decide: rank by stored order |
| Roster card: partner name | `p.label` | | `partner_name` | STORED | map |
| Roster card: overlap badge "Overlapping Partner" | `overlapBadge` `:646-660` -> `overlapState` `:618` | `shared/koel` never set | none on rival side; client side `client_partner_relationship.competitor_overlap` (boolean, unjoinable) | COMPUTED-JS name match (section 3) | decide: add column |
| Roster card: type chip | `tieKind(p)` = `p.ptype \|\| REL_SHORT[p.rel] \|\| p.kind \|\| "Partner"` `:592-595` | | `partner_type` | STORED + fallback chain (REL_SHORT code->label map `:580-587`, literal "Partner") | map `partner_type`; drop fallbacks |
| Roster card: country | `p.countries.join \|\| p.country \|\| "—"` `:2394` | | `region` | STORED / COMPUTED (countries collected from merged names) | map |
| Roster card: 2-line note | `p.note \|\| p.insight \|\| "Strategic defense manufacturing and supply tie."` `:2381` | | `description` | **INVENTED fallback sentence presented as data** | map `description`; empty -> nothing |
| "View Relationship Detail ->" , "Click on any partner card..." | `:2372,2400` | | | CHROME | keep |
| Tie view hero: `"{rival} <-> {partner}"`, type pill, status tag, confidence tag, country | `tieHtml` `:2120-2121`, `statusTag` `:536-556`, `confTag` `:563-566` | | `competitive_partnership_relationship_detail.relationship_title`, `type`, `confidence`; status NO-COLUMN | STORED (title/type/confidence); status: NO-COLUMN | map; hide status tag |
| Status tag "ended / in talks / announced / last seen YYYY / as of YYYY" | `statusTag` `:536` rule: `status` code; else if `as_of` year <= current year - `STALE_YEARS`(2) -> "last seen" | | `as_of_date` / `stated_as_of` | COMPUTED-JS rule stated at `:531,:547-555` (uses `new Date()`), plus status codes with **no column** | decide: keep "as of YYYY" only; hide ended/talks/announced |
| Confidence tag (official / corroborated / single source) with tooltips | `CONF_TAG` `:558-562` | | `relationship_confidence` | CHROME tooltips; values must equal these three codes | keep if DB values match, else show raw |
| Relationship cards (CARD 1..n): category line `TYPE · COUNTRY`, date, title, excerpt, source | `cards` `:1988-2043` built from the row (+ sibling rows of same canonical company) | | `competitive_partnership_evidence` (`card_number`, `evidence_text`, `evidence_type`, `relationship_label`, `scope`, `as_of_date`, `source_*`) | COMPUTED-JS: one synthetic card per row + one "STRATEGIC READ" card + sibling cards. Evidence table is the stored equivalent and is **unread** | map cards to `competitive_partnership_evidence` rows |
| Card text lines "Type:/Scope:/Deal:/Recorded:/Source note:/Confidence:/Basis for the type:/Stated as of:/Active in:" | `:1976-1986` | | `partner_type`, `relationship_scope`, (deal: none), `as_of_date`, `source_note`, `relationship_confidence`, `basis_for_type`, `stated_as_of`, `region` | CHROME labels + STORED values; "Deal" NO-COLUMN | map; hide Deal |
| "STRATEGIC READ" card / "PARTNERSHIP STRATEGIC IMPACT" box | `p.insight` / `p.mean`, with regex surgery removing `Threat:`/`Opening:`/`[CORE]` segments `:1930-1945` | | none (`competitive_partnership.description` / evidence `evidence_text` are the nearest) | NO-COLUMN; stored text is rewritten in code | hide until a column is chosen; remove regexes |
| Source line `Source Publisher: {url}` | `source: real(p.src)` `:1995`, rendered `:2070-2073` (`card.url` is never set, so it is never a link) | | `source_publisher`, `source_article_url`, `source_article_title` | BUG: prints the URL under the label "Source Publisher" | map to `source_publisher` + `source_article_url` |
| Hero image / "No image published with this article" | `p.image` `:2081-2092` | | `relationship_detail.image_state` | images are not data here (rule 4 spirit) | hide image block |
| Header Copy/Export/Print report | `report` `Partnerships.jsx:176-249` | | | COMPUTED-JS from the above; reads `selCo.threat` (served), `selCo.assess` (not served) | keep; drop `assess` |
| `REL_LABEL` fallback `rel[tp.rel]` | `:177,:215,:233` | not served | | dead fallback | remove |
| "Field-level read", "Structural weaknesses", "What their web reveals", "Read on this competitor" (COMPSYN/FIELDSYN) | `compReportHtml` `:1839`, `fieldReadHtml` `:2154`, handlers `Partnerships.jsx:773,785` | not served; **functions are never called** (`drawerBody` only calls `tieHtml`/`allPartnersRosterHtml` `:400-404`) | none | dead; content is generated analysis | remove |

### Partner-row field map (what must exist for the page to show anything)

| UI field | New-schema source | Kind of gap |
|---|---|---|
| `id` (row) | `competitive_partnership.relationship_id` | ok |
| node identity | `competitive_partnership.partner_id` | ok (today identity is derived by name, section 3) |
| `label` | `partner_name` | ok |
| `ptype` | `partner_type` | ok |
| `rel` (tech/supply/jv/mou/acq/other) | none | NO-COLUMN |
| `kind` (Foreign OEM / Domestic / Govt) | none | NO-COLUMN (live only as a report string and an `tieKind` fallback; the cluster logic that used it is in dead `graphSvg`) |
| `country` | `region` | ok (semantics to confirm) |
| `status`, `ended` | none (`client_partner.relationship_status` exists on client side only) | NO-COLUMN |
| `confidence` | `relationship_confidence` / evidence `confidence` | ok |
| `date`, `as_of` | `as_of_date`, detail `stated_as_of` | ok |
| `deal` | none | NO-COLUMN |
| `note` | `relationship_scope` / `description` | ok |
| `insight`, `mean` | none | NO-COLUMN |
| `src`, `srcnote` | evidence `source_url`/`source_article_url`, `source_note` | ok |
| `basis` | `basis_for_type` | ok |
| `image` | detail `image_state` | hide |
| `sig` | none | NO-COLUMN (only used in ranking `pgRowRank` `:744`) |
| `koel/shared/cid/clientTie/overlapChecked` | derived (section 3); client side `client_partner*` | decide |

---

## 1B. Projects (`src/pages/competitive/Projects.jsx`)

| UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Sidebar header "Competitors (N)" and list | `projectsConfig.competitors` (`app.py:281`) | built from project `competitor_id` joined to competitors; **join fails (bigint vs uuid)** | `competitive_project.competitor_id` + `competitive_competitor.display_name` | COMPUTED-BACKEND (distinct competitors that own a project) | map after id type fixed |
| Sidebar status dot | `c.threat === "fav"/"threat"` else watch `:231` | `competitors[cid].threat = threat_level` text | `competitive_competitor.threat_level` | STORED + INVENTED default "watch" | map; no default |
| Sidebar per-competitor count | `competitorCounts` `:79-84` | | count of `competitive_project` | COMPUTED-JS (under current search and region tab) | keep |
| "All competitors" count | sum of counts `:117-119` | | | COMPUTED-JS | keep |
| Sidebar order | by count desc `:113` | | | COMPUTED-JS | keep |
| Region/filter tabs "All N / <label> N" | `projectsConfig.filters` = hard-coded `{f:"all",l:"All"}` + `ui_project_filter` (`app.py:271-275`); counts `p.region === f.f` `:70-74` | `filter_code`, `filter_label` | `ui.ui_project_filter.filter_code/filter_label`; `competitive_project.region` | CHROME (table) + COMPUTED-JS counts; **coupling:** `filter_code` must equal `region` values | keep; document coupling |
| Sequence selector | `seqOptions` (`ui_project_sequence_option`) default `[["recent","Most recent"]]` `:49` | | `ui.ui_project_sequence_option` | CHROME; sort functions keyed `recent/stage/size` hard-coded `:31-39` (other codes silently fall back to recent `:87`) | keep; document code vocabulary |
| Sort "recent" | `latest.date` desc then `mw` desc `:32-36` | `latest_milestone_date`, `estimated_value` as `mw` (`app.py:263`) | same | COMPUTED-JS | keep |
| Sort "stage" | `stageRank` `:37` | **not served** (`stageRank` undefined) | `competitive_project_stage.stage_order` where `is_current` | COMPUTED-JS from missing input | map from `competitive_project_stage` |
| Sort "size" | `mw` `:38` | `estimated_value` | `competitive_project.estimated_value` | COMPUTED-JS (numeric; no unit shown anywhere) | keep |
| Feed row: rank "01.." | index `:336` | | | COMPUTED-JS | keep |
| Feed row title | `p.name` | `project_title` | `project_title` | STORED | keep |
| Feed row sub-line | `p.stageNote` `:341` | `stage_note` | `stage_note` | STORED | keep |
| Feed row "<stage>: company . customer . location" | `p.stage`, `company`, `customer`, `location` `:343-352` | `stage`, `company_display`, `customer`, `location` | same | STORED (company hidden when one competitor selected: COMPUTED) | keep |
| Feed row tag Threat/Watch and left stripe | `stance = assessment.stance \|\| "watch"` `:323,:391,:402`; label `stance === "threat" ? "Threat" : "Watch"` `:359,:404` | `assessment_stance` | `competitive_project.assessment_stance` | STORED + **INVENTED default** ("watch" for every project with no stance) | map; show no tag when null |
| Feed row date | `p.latest ? p.latest.date : "Undated"` `:362` | `latest` always an object (`app.py:264`), so "Undated" never shows, blank does | `latest_milestone_date` | STORED / CHROME empty-state | map; fix empty check |
| Pager "showing 1-N of N ... filtered . M total" | `:376-381` | | | COMPUTED-JS | keep |
| Empty state "No project matches ..." | `:370-372` | | | CHROME | keep |
| Drawer title | `selectedProject.name` | `project_title` | `project_title` | STORED | keep |
| Drawer fact "Competitor" | `p.company` | `company_display` | `company_display` | STORED | keep |
| Drawer fact "Kind" | `p.kind` | `kind` | `kind` | STORED | keep |
| Drawer facts "Customer", "Location" | | `customer`, `location` | same | STORED | keep |
| Drawer fact "Region" | `region === "Gulf" ? "Gulf region" : "Worldwide"` `:420` | `region` | `region` | **INVENTED**: the Gulf/Worldwide vocabulary is Cummins-Arabia content (the file's own comments say "matching xr logic in Cummins Arabia", "All 58 / Gulf region 27 / Worldwide 31") | show `region` as stored |
| Drawer fact "Stage" | `p.stage` | `stage` | `stage` | STORED | keep |
| Drawer fact "Latest milestone" | `${latest.date}: ${latest.label}` else "Undated in the record" `:422-427` | `latest = {date, note}`; UI reads `label` | `latest_milestone_date`, `latest_milestone` | STORED but **field-name mismatch bug** (prints "undefined") | map to `latest_milestone` |
| "What the project is" | `overview[]` `:442` | hard-coded `[]` | `competitive_project.what_the_project_is` (also `card_summary`) | NO data path (STORED column unmapped) | map `what_the_project_is` |
| "Current stage" stepper | `stageSteps` (global list `ui_project_stage_step`) and `i+1 < stageRank` done / `== stageRank` now `:453-461` | `stageSteps` yes; `stageRank` no | `competitive_project_stage` (`stage_name`, `stage_order`, `is_current`) per project | COMPUTED-JS from a rank that does not exist | map to per-project stage rows; done = `stage_order` < current |
| Stage note under stepper | `p.stageNote` | `stage_note` | `stage_note` | STORED | keep |
| "Specs" list | `specs[{k,v}]` `:469-481` | hard-coded `[]` | `competitive_project_specification` (`spec_label`, `spec_value`, `unit`, `display_order`) | NO data path; table unread | map (value + unit) |
| "Timeline" list with "(expected)" | `timeline[{date,label,expected}]` `:486-498` | not built | `competitive_project_timeline` (`event_date`, `event_title`, `event_description`, `is_expected`) | NO data path; table unread | map |
| "Researched to October 2026." | literal `:500` | | `competitive_project.researched_as_of` | **INVENTED date in code** | map `researched_as_of`; remove literal |
| "Strategic assessment" paragraphs | `assessment.read[]` `:507-512` | `assessment_read` string (UI needs array: crash) | `assessment_read` (also `strategic_assessment`) | STORED + bug | map; render as text |
| "No assessment on record." | `:514` | | | CHROME empty-state | keep |
| "The analyst's read for KSSL, from the dataset's record of this item." | `:516` | | | CHROME (provenance claim) | keep or reword |
| "Source" links | `sources[{label,url}]` `:520-541` | not built | `competitive_project_source` (`source_label`, `source_url`, `source_domain`) | NO data path; table unread | map |
| Header report | `useHeaderReport` `:128-147` | | | COMPUTED-JS from above | keep |
| `ksslPlatform`, `ksslAdvantage`, `grade` | emitted/unused (`app.py:266-267`) | | `kssl_platform`, `kssl_advantage`, `grade` | not displayed | decide (counters about the client) |
| `ui_project_metric`, `ui_project_view_state` | | not read | | | decide (see section 4) |

---

## 1C. Geo Footprint (`src/pages/competitive/Geo.jsx`, `components/geoMap/GeoMap.jsx`, `lib/geo.js geoBadge.js geoCountries.js footprint.js countryFlags.js`)

Served shape today: `geoData[companyId][country][]` = `{name, c, stage, since, note, src}` (`app.py:304-311`); `geoComps[] = {id,name,isBf}`; `geoCountries[]`. `dataset.js:442-459` then overwrites every client row's `c` with `"bf"` (original kept in `c0`).

| UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Map marker position | `geoCountryCoords(country)` from `COUNTRY_COORDS` `geoCountries.js:25-111` (85 hard-coded lat/lng pairs) | `latitude/longitude` not mapped | `competitive_geo_location.latitude/longitude` | **INVENTED** geographic table in code (and countries not in the table are silently not drawn, `geoPlotPlan` `:133-147`) | map lat/lng; delete table |
| Map: which countries are plotted | `servedGeoCountries(data)` `GeoMap.jsx:31-42` | `geoCountries`/`geoData` keys | `competitive_geo_location.country_name/map_label` | COMPUTED-JS (distinct served countries) | keep |
| Regions not drawn ("Europe", "Africa", ...) | `REGION_ROWS` `geoCountries.js:117` | | `competitive_geo_location.region_name` | vocabulary in code | decide |
| Marker colour green / red / amber | KSSL has rows `isKoelPresent`, else rivals>0, else amber `GeoMap.jsx:131,:154` | | `competitive_geo_location.presence_types`, `kssl_presence_summary` | COMPUTED-JS | decide: stored summary vs computed |
| Marker hollow-dashed = "estimate" | `isEstimate(row) = row.src === "syn"` `geoBadge.js:86` | not served; magic string | none | NO-COLUMN (magic value `"syn"`) | hide |
| Tooltip title: country | `ct` | | `country_name` | STORED | keep |
| Tooltip badge "KSSL Present . <acts>" / "KSSL Absent . Contested Market (warning)" / "No activity on file" | `presenceBadge` `geoBadge.js:122-146`; absent rule `own.length==0 && rivalCount>0` `:125-128` | | `kssl_presence_summary` | COMPUTED-JS **judgement from missing input**: "Absent" is asserted when no client row exists, even when the client footprint is simply not loaded (geo.js:23-39 documents exactly this fault and guards only overlap) | decide: show `kssl_presence_summary` verbatim; hide "Absent" |
| Tooltip: up to 5 companies + role | `comps.slice(0,5)` `GeoMap.jsx:158`; `companyRole` `geoBadge.js:204-212`: "Head office" + activity labels, else "Competitor" / "{client} presence" | `actLabel` not served; `origin` mismatch | `company_name`, `activity_type`, `competitive_competitor.origin_country` | COMPUTED-JS; "Head office" never fires; fallbacks "Competitor", "{client} presence" are CHROME/defaults | map origin; keep chrome |
| Tooltip "Active Companies & Material Trade", "Click point to open market product details" | `GeoMap.jsx:199,:203` | | | CHROME ("Material Trade" has no data: `COMPANY_MATERIALS = {}` `:27`) | reword; delete dead map |
| Map empty overlay | `:320` | | | CHROME | keep |
| Basemap tiles | Esri/OSM URL `GeoMap.jsx:58-63` | | | external, non-DB (not on the rule-5 exception list) | decide (flag to user) |
| Top bar "Competitor: All Rivals (N)" | `competitorsList` `Geo.jsx:152-158`: geoComps non-client with >=1 country | `company_name` | | COMPUTED-JS count | keep |
| Competitor menu: name, "N markets", dot | `presenceCount = countriesForComp.length`; dot `threat = profile.threat \|\| company.dir \|\| "watch"` `:156,:102` | rival profile never resolves (bigint/uuid) | `competitive_competitor.threat_level` | COMPUTED-JS + **INVENTED default "watch"** | map; no default |
| Top bar "Country: All Markets (N)" + per-country "N records" | `footprintCountries` `:114-124`: `geoCountries` UNION client countries, rows summed across all companies with alias spellings `COUNTRY_ALIASES` `:7-17` | | `competitive_geo_location.country_name`; `competitive_geo_company_presence.product_count` | COMPUTED-JS (record = product row, or 1 blank pseudo-row, `app.py:301`) | decide: use `product_count` |
| Country alias list (UAE/USA/UK/Russia/Korea) | `Geo.jsx:7-17`, `geoCountries.js:153-178` | | | vocabulary in code (country names, not company data) | keep or normalise in DB |
| Overlay header (market): `"{country}"`, `"N competitors active . KSSL present / KSSL footprint not recorded . X contest KSSL on indexed model matches, Y on category only"` | `headerDetails` `:217-221` | | `ui.ui_geo_country_detail_state.active_competitor_count / category_only_competitor_count / rating_matched_competitor_count / kssl_present` | COMPUTED-JS; stored equivalents exist and are unread | map the `ui_geo_country_detail_state` columns or keep computing (decide) |
| Overlay header (pair): `"{company} -> {country}"`, `"N footprint records in this market"`, pills "N <activity label>" | `:212-215` | | `ui.ui_geo_products_supplied_state.product_count/export_supply_count/sales_service_site_count/matched_model_count` | COMPUTED-JS; stored equivalents unread | same decision |
| Overlay header (competitor): `"N markets with served footprint records"` | `:223` | | | COMPUTED-JS | keep |
| Overlay header (client): `"{N} tracked competitors . N served markets . N footprint records"` | `:224-225` | | | COMPUTED-JS | keep |
| Market view: "Companies active in {country}", "N tracked entities" | `CountryMarketView` `:295-300` | | | CHROME + COMPUTED-JS (companies + 1 if client has rows) | keep |
| Market view: own row `"{client} - N footprint records . <activity> . KSSL present"`, tag = first record name | `:300` | client rows | `company_role='client'` rows | STORED + literal "KSSL present" appended by code | map; replace literal with client name from data |
| Market view: company row, badge "Confirmed overlap / Category overlap / No indexed overlap" | `company.overlap?.tier` `:302,:304` from `geoOverlap` `geo.js:203-277` | **always null today**: `CAT_META`/`counterRules` not served so `GEO_BANDS=[]` (`geo.js:54`) | `competitive_geo_company_presence.overlap_status` (+ `matched_ranges`) | COMPUTED-JS keyword engine; result today = every company reads "No indexed overlap" = **absent input rendered as a finding** | map `overlap_status`; remove engine |
| Market view: "meets KSSL in <bands>" | `overlap.bands.map(geoBandShort)` `:303` | | `matched_ranges` | COMPUTED-JS + `geoBandShort` vocabulary art->Artillery, ammo, sa, pav, mro, naval, uav, msl, pc `geo.js:116-127` (**INVENTED KSSL category vocabulary**) | map `matched_ranges` as text |
| Market view footnote "N indexed model overlaps . M category overlaps" | `:306` | | | COMPUTED-JS | keep or `ui_geo_country_detail_state` |
| Market view empty copy | `:305` | | | CHROME | keep |
| Competitor view: "Markets for X (N)", rows (country, overlap badge, "N footprint records", first record name) | `:282` | | | COMPUTED-JS | keep |
| Competitor profile: "Competitor profile", `{dir \|\| "Tracked rival"} . {threat \|\| "Threat level not reported"}` | `CompetitorDetail` `:346-348` | `dir` not served for rivals; profile unresolved | `threat_level` | CHROME fallbacks acting as data | map `threat_level` |
| Competitor profile: Sector, Headquarters, Threat | `valueOrNull(profile.sector/hq/threat)` `:348` | `industry_sector`, `headquarters`, `threat_level` | same | STORED | keep (profile unresolved until id fixed) |
| Competitor profile: "Assessment" | `profile.assess` `:348` | not served | `strategic_positioning` / `parallax_read` | hidden by rule 4 | **remove** |
| Competitor profile: "Products on profile" | `profile.products` | `[]` | `competitive_product` (other group) | | remove from Geo or decide |
| Competitor profile: "Footprint markets (N)" rows | `:348` | | | COMPUTED-JS | keep |
| Pair view: product list rows (name, "activity . stage . Since X") | `SuppliedProductsView` `:310-330`; `activityLabel` `:99` | `product_name`, `activity_type`, `presence_status`, `since_date` | `competitive_geo_product.product_name/activity_type/since_date`, presence `presence_status` | STORED (activity read from presence not product, `app.py:306`) | map product's own `activity_type` |
| Pair view: extra "Indexed matchup" rows | `indexedRows` `:312-315`: matchups of the same company+country not already named in the footprint | | | COMPUTED-JS (name/country fuzzy join) | remove |
| Pair view: "N RECORDS . M MATCHED TO A KSSL COMPARISON" | `:320` | | | COMPUTED-JS | keep |
| Pair view: KSSL counterpart name | `rowMatchup(row, matchups)` `:58-74`: normalised name containment, else >=2 shared tokens (len>2), score 100/10n | | `competitive_geo_product_match.kssl_counter_label` | COMPUTED-JS fuzzy match | map stored match |
| Pair view: "No matched KSSL model" / "Published KSSL comparison" | `:323` | | | CHROME fallbacks | keep |
| Pair view: verdict pill, colour fav if `/kssl\|kalyani\|client/i` matches the verdict text | `:324` | | `competitive_geo_product_match.evaluation_label`, `decision_level`, `qualitative_summary` | **INVENTED rule keyed to a literal client name ("kalyani")** | map `decision_level`; remove regex |
| Comparison panel header `"{kssl} vs {rival}"`, `"{n} measured comparison(s)"` | `ProductComparison` `:332-338` | | `comparison_title`, `kssl_score`, `competitor_score`, `rating_delta`, `match_basis` | COMPUTED-JS count (`compareProducts` `compareProducts.js`) | map stored |
| Comparison "Rival: ... / {client}: ..." advantages | `matchup.advComp/advBf` | from `data.matchups` | `competitive_geo_product_match.qualitative_summary` | joined from Positioning matchups | map |
| Spec table (SPEC, KSSL, rival, GAP: "X advantage", "Near parity") | `compareProducts` `:76-86` rule: both numeric, `hi` direction, gap < `EDGE_DEADBAND`(3%) -> tie, ratio > 50 -> "values look like different units - not scored" | | `competitive_geo_product_specification.spec_name/kssl_value/competitor_value/unit/gap_value/better_side` | COMPUTED-JS; stored winner/gap exist and are unread | map `better_side`, `gap_value`; remove computing |
| Table column labels SPEC / GAP | | | | CHROME | keep |
| "Selected footprint record" block (activity, stage, since, note) | `:338` | `note` = `record_note` | `record_note` | STORED | keep |
| "KSSL comparison bands" table: Category, Pairs, Result ("Rival leads x of y"/"KSSL leads"/"Near parity - n of m"/"No matched model pair"), "KSSL rule: {counter}" | `OverlapTable` `:364-366`, `outcomeText` `:106-112`, `counterRules` | `counterRules` not served | `competitive_geo_product_match` (`kssl_counter_label`, scores) | COMPUTED-JS | hide until per-band data stored |
| Source evidence list + note | `rawSources(row)` `:88-96` from `row.src/srcnote/srcs` | `src` holds `relationship_text` (bug) | `competitive_geo_source.source_label/source_url/source_type` | NO data path (table unread) | map |
| "Footprint-linked intelligence" news list | `row.geo_news[]` (`title/summary/url`) | not built | `competitive_geo_product_news` (`headline`, `publisher`, `published_date`, `article_url`) | NO data path; field names differ | map |
| Reported value, Quantity / place, Product range, rating, fuel, frequency | `PairDetail` uses `row.val/row.qty` `:290` | not mapped | `reported_value`, `quantity`, `product_range`, `rated_power_*`, `fuel_type`, `frequency_hz` | `PairDetail` (`:289`) and `CountryDetail` (`:341`) are **dead** (never rendered) | decide whether to show; else remove |
| `countryNews`, `countryOverlapCount` | `:196-206` | | | dead computations | remove |
| Dev checks | `geo.selfCheck()` `DataProvider.jsx:71`; assertions name "SH-15", "CAESAR 155mm", "ATAGS", "Spike ATGM", "Hermes 900" `geo.js:632-654` | | | INVENTED product names in code (console-only) | remove |

---

## 1D. Patents (`src/pages/competitive/Patents.jsx`, `lib/patents.js`, `lib/ipc.js`, `dataset.js adaptPatents`)

Everything shown is empty today because `PATENTS` is hard-coded empty (`app.py:532`). The page therefore always renders the "No patent filings are indexed" panel.

| UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Empty panel: "No patent filings are indexed" + paragraph | `Patents.jsx:177-199` shown when `byAssignee`/`byArea` empty | | `competitive_patent_portfolio.empty_message` | **INVENTED**: states "26 records do exist from an earlier pass and are deliberately withheld: 22 of them carry estimated rather than published patent numbers" and "The patent harvest has not landed any filings for this client" (facts about DB state typed in code; `:169-172,:189-191`) | replace with `empty_message`; remove the claims |
| Lens toggle "By rival / By technology field" | `lens` state `:34`, labels `:205-218` | | `ui.competitive_patent_view_state.active_lens`, `competitive_patent_portfolio.lens` | CHROME | keep |
| Competitor rail (names) | `data.compOrder` + `competitors[k].name` `:138-143,:266` | | `competitive_competitor.display_name` | STORED | keep |
| Competitor rail: count per competitor | `pd.records.length` `:267` | 0 | `competitive_patent_portfolio.filing_count` | COMPUTED-JS (count of tokens-matched records) | map `filing_count` |
| Default selected competitor | `savedPat.cid \|\| data.compOrder[0]` `:37` | | `ui.competitive_patent_view_state.selected_competitor_id` | COMPUTED default (first rival) | keep |
| Search boxes "Search competitor...", "Search field..." | `:138-146` | | `competitor_search_text`, `technology_search_text` (state) | CHROME | keep |
| Portfolio stats: Filings on record / Granted / Filed / Pending / "Not captured" | `patCompBody` `patents.js:316-373`, `deriveStats` `:302-313` | | `filing_count`, `granted_count`, `pending_count`, `grant_status_state`, `status_note` | COMPUTED-JS from per-record status; stored counts unread | map stored counts; show "-" when `grant_status_state` says unknown |
| "Grant status was not captured ..." sentences | `:347-350,:361-362` | | `status_note` | CHROME sentences replacing a stored note | map `status_note` |
| Category filter "All product categories (N)" and options with counts | `cats` from `r.techArea` `Patents.jsx:88-91,:286-293` | | `competitive_patent_classification.category_label/filing_count` | COMPUTED-JS | map |
| Filter by category: DOM show/hide + rewrites the count text node | `applyCatFilter` `:150-161` | | | COMPUTED-JS (DOM mutation of rendered HTML) | decide |
| Filing card: title | `title_en` first, `title` underneath `patents.js:230-236` | `title_en` not in schema | `competitive_patent_filing.title` | STORED (`title_en` NO-COLUMN) | map `title`; hide English line |
| Filing card: status badge (granted/filed/pending/"status not captured") | `norm()` `dataset.js:775-781` regex on status text; `unknown = st==="unknown" \|\| !grantStatusKnown` `patents.js:184-187` | | `competitive_patent_filing.status` | COMPUTED-JS normalisation + corpus-level flag `grantStatusKnown` (`dataset.js:861`) | map `status` verbatim |
| Filing card: assignee | `r.assignee` (field lens) | | none | NO-COLUMN | hide |
| Filing card: id / jurisdiction | `r.id`, `normCountry(jurisdiction)` `patents.js:44-72` (country name -> ISO code map for 18 countries) | | `publication_number`, `jurisdiction` | COMPUTED-JS vocabulary map | map verbatim; drop map |
| Filing card: "Filed {date} . Published {date} . Granted {date} . Pending" | `dateLine` `:191-197` | | `filed_date` only | `published`, `granted` NO-COLUMN | show `filed_date`; hide others |
| Filing card: kind code chip, "Grant {no}", "grant no. not captured" | `pub_kind`, `grant_no` `:205-213` | | none | NO-COLUMN | hide |
| Filing card: IPC chips | `r.ipc[]` | | `classification_code` (single) | one code, not a list | map single code |
| Filing card: "Classified under {subclass} {meaning}" | `ipcDescription` `ipc.js:37-50,:68-75` (12 hard-coded IPC definitions) | | `classification_text` | **INVENTED reference text in code** (classification definitions, not company claims) | map `classification_text`; delete dictionary |
| Filing card: abstract | `r.abstract` | | none | NO-COLUMN | hide |
| Filing card: relevance badge | `koel_relevance` | | none | NO-COLUMN | hide |
| Filing card: link "View patent" / "Search for this filing" | `url` or `https://patents.google.com/?q=...` fallback `patents.js:136-143` | | `patent_url` | **INVENTED link** when none stored | map `patent_url`; no fallback |
| Filing card: extra source chips | `srcs` | | none | NO-COLUMN | hide |
| Footer "Data source: sourced from Google Patents, EPO Espacenet, WIPO Patentscope, Indian Patent Office. N filings currently indexed." | `patApiNote` `patents.js:268-284`, list `:270-275` | | `competitive_patent_portfolio.data_source_note` | **INVENTED provider list**; count COMPUTED | map `data_source_note` |
| Field lens: rail of fields with counts | `patentAreas` `patents.js:528-537`, `byTechnology[a].records.length` `Patents.jsx:344` | | `competitive_patent_classification.category_label/filing_count` (sum across portfolios) | COMPUTED-JS; fallback chain (indexed -> configured `techAreas` -> `techCats`) | map; drop fallbacks |
| Field lens: "Field crowding: Open/Emerging/Crowded/Locked up" | `crowding = n>=25 "crowded" : n>=8 "emerging" : "open"` `dataset.js:995`; labels `patents.js:390-396` | | none | **INVENTED thresholds** (25, 8) and a never-reachable "locked" | hide |
| Field lens: Filings / Assignees tiles | `totalFilings`, `activeAssignees` `dataset.js:990-993` | | `filing_count`; assignees NO-COLUMN | COMPUTED-JS | keep Filings; hide Assignees |
| Field lens: summary paragraph | `meta.why \|\| meta.desc` `dataset.js:996` | `techAreaMeta[].description` | `technology_category` description | joined by exact area-name equality (`:917-919`) | decide |
| "KSSL holds N filings in this field. It is contested by M other holders." / "No KSSL filing is recorded in this field. K rivals have staked it, J with a granted patent already enforceable." | `patTechBody` `:405-432` | | none (portfolio has no client row) | COMPUTED-JS judgement text; client filings detected by `/kssl\|kssl\|bharat\s*forge/i` on assignee `dataset.js:1005` | hide |
| "Who holds filings here" list (name, N filings, countries, latest year, granted/published chips, threat chip) | `leaders` `dataset.js:913-988`; sort granted, threat, latest, name | | `portfolio.competitor_id` + classification `filing_count`; per-field granted/threat none | COMPUTED-JS aggregation; `threat` NO-COLUMN; `trend` default `"flat"` `dataset.js:974` | decide: show rival + count only |
| "Ranked by granted patents, then assessed threat, ..." caption | `patents.js:439-455` | | | COMPUTED-JS text | simplify |
| "Sparsely-patented areas: not computed ..." | `td.whitespace` null `dataset.js:1003`, `patents.js:491-503` | | none | CHROME statement of a missing analysis | hide |
| "KSSL position" box | `td.koel.position = meta.reason \|\| "No KSSL filings recorded in this field yet."` `dataset.js:1004-1007` | | none | **INVENTED fallback sentence**; `koel_position "—"` default `:993` | hide |
| Rival attribution of filings | token-overlap matching of assignee string to competitor name `dataset.js:815-911` | | `competitive_patent_portfolio.competitor_id` | COMPUTED-JS heuristic that the stored key replaces | remove |
| Header report | `Patents.jsx:99-136` | | | COMPUTED-JS | keep |

---

## 2. INVENTED content found

The brief said partners.js holds "~160 hard-coded analysis sentences". A literal sweep of every string literal with >=5 words gives 84 hits in partners.js (105 at >=4 words) and 106 in geo.js; the largest blocks of judgement text are listed below. Classification: **chrome** = explains the UI; **content** = judgement or fact about companies/markets.

### 2a. partners.js sentence inventory (classification)

| Where | Count | Class | Reachable from UI today? | Action |
|---|---|---|---|---|
| `OV_DEF` `partners.js:107-188`: 4 headings ("What an overlapping channel/supplier/service network/technology partner costs KSSL"), 4 lead clauses, 14 effect titles, 14 effect bodies (17 sentences). e.g. `:111` "the same dealer quotes KSSL and the rival from one counter, so the brand decision moves from the customer to the salesperson" | 36 strings | **content/judgement** (generic competitive analysis, identical for every rival) | **No**: only `overlapDefsHtml` `:1808` reads it; nothing calls it (removed on request, comment at `Partnerships.jsx:799-804`) | remove |
| `OV_KIND` `:73-103` maps relationship types to channel/supplier/service/tech | 25 entries | content (classification of relationship types) | only via dead `overlapHtml`/`overlapDefsHtml` | remove |
| `overlapHtml` `:1714-1801`: "All N of X's mapped partners are its own... no overlapping dealer is quoting both brands", "has a direct agreement with ... itself", "is 1 of N brands on that shelf", "holds no exclusivity" | ~11 template clauses | **content/judgement** | No (never called) | remove |
| `compReportHtml` `:1839-1903` + `fieldReadHtml` `:2154`: headings "Read on this competitor", "Structural weaknesses", "What their web reveals", "Field-level read - patterns across all N", "Bottom Line"; bodies come from `COMPSYN`/`FIELDSYN` (not served) | ~10 labels | chrome labels over stored-elsewhere content | No (never called; handlers at `Partnerships.jsx:773,785` bind nothing) | remove |
| `tieHtml` `:1924-2151` labels ("STRATEGIC READ", "PARTNERSHIP STRATEGIC IMPACT", "Select a card below to read detailed intelligence on this relationship:", "No image published with this article", "Type:/Scope:/Deal:/...") | ~20 | chrome | Yes | keep |
| `statusTag` / `confTag` / `overlapBadge` tooltips `:545-565,:634-658` ("The source says the two are in talks. Nothing is signed.", "Read from an article published in Y. Nothing since says it is still in force.", "the maker or a government publisher states it") | ~10 | chrome (explains a stored value) | Yes once data exists | keep |
| `allPartnersRosterHtml` fallback `:2381` "Strategic defense manufacturing and supply tie." | 1 | **INVENTED, presented as data** | **Yes** (any partner with empty `note` and `insight`) | remove |
| Dev check messages `selfCheck`/`geomCheck` `:2241-2337` | ~14 | dev | console only | remove with the checks |
| `DEFENSE_FIRM_COUNTRIES` `:1167-1190`: 22 regexes, ~181 company-name tokens mapping a partner name to a country ("rafael" -> Israel, "tata" -> India, "hanwha" -> South Korea ...) | ~181 tokens | **content about companies** | **Yes** (Regions graph, only when `region` is empty, `pgRegionsOf` `:1192-1198`) | remove; use `region` or "Unknown" |
| `PG_REGION_ALIAS` `:1134-1166` | 108 spellings of ~30 countries | vocabulary (normalisation) | Yes | decide: normalise at load |
| `PG_TYPE_META` `:1106-1113`, `REL_SHORT` `:580-587`, kind regexes in dead `graphSvg` `:960-965` ("airbus", "embraer", "elbit", "sparton" ...) | | vocabulary / content | PG_TYPE_META yes; graphSvg no | decide / remove |

### 2b. Other INVENTED items (file:line, quote)

| File:line | Quote / description |
|---|---|
| `lib/geo.js:335-451` `geoOvPanel`, `:454-572` `geoOwnPanel`, `:294-321`, `:576-620` | ~55 judgement sentences, e.g. "Every enquiry in X is a contested deal.", "They build it in X; the hardest version of this overlap.", "pricing power here is higher than in India", "the highest-margin volume in this market" (`:482`, `:563-564`). **None called by Geo.jsx** (dead); remove |
| `lib/geo.js:116-127` | `geoBandShort`: `art: "Artillery", ammo, sa: "Small Arms", pav: "Armour", mro, naval, uav, msl: "Missiles", pc: "Forgings"` (live: used in Geo.jsx market/overlap tables) |
| `lib/geo.js:100` | `GEO_NOTGEN = /radar\|electronic warfare\|c4i\|avionics\|aerostructure\|.../` product-class judgement |
| `lib/geoCountries.js:25-111` | 85-entry country -> lat/lng table |
| `lib/geoCountries.js:117` | `REGION_ROWS` list |
| `Geo.jsx:324` | `/kssl\|kalyani\|client/i.test(verdict) ? "fav" : "threat"` |
| `Geo.jsx:300` | literal `· KSSL present` |
| `Geo.jsx:348` | `profile.dir \|\| "Tracked rival"`, `"Threat level not reported"` |
| `geoBadge.js:128` | `"${clientLabel} Absent · Contested Market ⚠"` (judgement from missing rows) |
| `Projects.jsx:420` | `region === "Gulf" ? "Gulf region" : "Worldwide"` |
| `Projects.jsx:500` | `Researched to October 2026.` |
| `Projects.jsx:323,:391` | default stance `"watch"` |
| `Partnerships.jsx:533` | default dot `co.dir \|\| "watch"` |
| `Patents.jsx:189-191` | "26 records do exist from an earlier pass ... 22 of them carry estimated rather than published patent numbers" |
| `patents.js:270-275` | providers `["Google Patents","EPO Espacenet","WIPO Patentscope","Indian Patent Office"]` |
| `patents.js:139` | fallback `https://patents.google.com/?q=<title>` |
| `ipc.js:37-50` | 12 IPC subclass definitions |
| `dataset.js:995` | `recs.length >= 25 ? "crowded" : recs.length >= 8 ? "emerging" : "open"` |
| `dataset.js:1005-1006` | `/kssl\|kssl\|bharat\s*forge/i`; `"No KSSL filings recorded in this field yet."` |
| `dataset.js:974,993` | `trend` default `"flat"`, `koel_position` default `"—"` |
| `dedupeCompanies.js:56-61` | `PAIRS`: idv/iveco, rtx/raytheon, knds/nexter, huta-stalowa-wola/hsw with "via" evidence. Keyed by slug ids; new competitor ids are uuids so it is a no-op, and rule 1 reads `competitor.site` which is not served |
| `orgident.js:34-54` | `NATIONAL` demonym map, `ALIASES` (hal, hanwha, rafael) |
| `orgident.js:57-90` | `isJunkPartner` drops rows whose label matches `ministr\|army\|navy\|air force\|government\|...`, collective words, places (`dataset.js:242-247`) |
| `companyNames.js:50-127` | ~45 company-name/expansion entries by slug id. **Does not affect these four pages** (read by Profile and MatchupList only); slugs do not match uuid ids. Flag for the Profile owner |
| `GeoMap.jsx:27` | `COMPANY_MATERIALS = {}` already emptied (dead) |

---

## 3. Computed in the UI (rules)

### Partnerships

| Rule | File:line | Replace with |
|---|---|---|
| One node per canonical company: strip parenthetical, legal suffixes, trailing national qualifier, ALIASES, then merge when the shorter name's distinctive tokens are all contained in the longer (so "Lockheed Martin Australia/UK/Skunk Works" -> one node, countries kept) | `partners.js:64-70`, `orgident.js:104-183`, `pgNodes` `:752-779` | `competitive_partnership.partner_id` is the company identity; decide whether to drop name folding |
| Junk-partner filter | `dataset.js:242-247`, `orgident.js:68-90` | filter at load, not at render |
| Node ranking and caps: overlap first, then `pgEvidence` score (+2 http source, +1 typed, +1 jv/technolog/licen/acquir/manufactur, + min(rows,4)), then `pgRowRank` (`[CORE]` 20 / `[ADJACENT]` 10 + `sig`); roster cap 40; leaf cap 16 | `:744-791`, `:2362`, `:1567` | stored `display order`; `[CORE]`/`sig` have no columns |
| Shared-partner overlap: `partnerKey(label)` (= `orgKey`, min length 3) of each rival partner compared with each `KSSL_PARTNERS` label; match stamps `shared`, `sharedWith`; flagged rows left as is | `overlap.js:47-112`, `dataset.js:139,:701-716`; `rosterLookup` strips "(...)" `partners.js:48-54` | `client_partner.partner_name` vs `competitive_partnership.partner_name` (no id join exists). `client_partner_relationship.competitor_overlap` is a client-side boolean with no competitor reference. **Decide: add a column on `competitive_partnership` (overlap flag or `client_partner_id`)** |
| 3-state overlap (shared / direct / none / unchecked) | `overlapState` `:618-627` | collapses to 2 states without `cid`/`overlapChecked` |
| Overlap list search token | `Partnerships.jsx:262` | drop |
| Status staleness: label "last seen YYYY" when `as_of` year <= current year - 2 | `partners.js:531-555` | decide |
| Counts: raw rows in list, distinct companies in graph, "TOP 40 OF N" | `Partnerships.jsx:497`, `partners.js:1379,:2364` | `mapped_partner_count`, `ui.competitive_partnership_graph.partner_card_count` (stored, unread) |
| Insight/mean text surgery (regex removes "Threat:", "Opening:", "[CORE]") | `partners.js:1930-1945` | remove |
| HQ country facet | `countryFacet.js` `companyCountries`, `countryCanon` (most-used spelling wins) | `origin_country` |
| Graph geometry (ring radii, arcs, label collision), pan/zoom viewBox | `partners.js:1261-1711`, `Partnerships.jsx:112-122` | layout only, keep |
| Group buckets by relationship code and by country | `pgTypeGroups` `:1117`, `pgRegionGroups` `:1207` | by stored `partner_type` / `region` |

### Projects

| Rule | File:line |
|---|---|
| Search index over name/company/customer/location/kind/stage/stageNote/overview/specs | `Projects.jsx:6-20` |
| Region tab counts, per-competitor counts, total count, pager text | `:60-96,:117-119,:376-381` |
| Sorts recent / stage / size | `:23-39` |
| Competitor list sorted by project count | `:113` |
| Stage stepper done/now from `stageRank` | `:453-461` |
| Distinct competitors that own a project | `app.py:281` |

### Geo

| Rule | File:line |
|---|---|
| Overlap engine: keyword (`CAT_META[k].kw`, word-boundary regex) category detection on `name+qty+val+note`; product-class filter `GEO_NOTGEN`; overlap = same country, both in scope, shared categories; tier "spec" if any shared band has a matched pair with an index else "cat"; pair index by `compBy\|\|catKey`; verdict from `edgeVerdict(edge)` ("behind/ahead/level") | `geo.js:54-277`. **Null for everything today** (`CAT_META`, `counterRules`, `matchups[].catKey` not served) |
| `clientFootprintKnown` guard | `geo.js:40` |
| Rival test by name similarity (`coKey` strips legal/industry words) or presence in matchup corpus | `geo.js:172-200` |
| Row to KSSL counterpart (fuzzy name/token score) | `Geo.jsx:58-74` |
| Spec winner (3% deadband, 50x unit-mismatch flag) | `compareProducts.js:56-86` |
| Per-country record counts across alias spellings | `Geo.jsx:114-124` |
| Presence badge text, absent rule, marker colour/size/hollow | `geoBadge.js:122-146`, `GeoMap.jsx:131-155` |
| Head office: `origin` equals country, else last hq part found in the coordinate table | `geoCountries.js:196-213` |
| Client rows relabelled `c="bf"`, `c0` kept | `dataset.js:442-459` |
| Header counts (competitors active, KSSL present, overlap copy, activity pills) | `Geo.jsx:211-226` |
| Competitor dedupe re-keys `geoData`/`geoComps` | `dedupeCompanies.js:186-199` |
| `footprint.js`: not used by Geo; read by `shortlist.js:49` (tender scoring), out of scope | `footprint.js:9-29` |

### Patents

| Rule | File:line |
|---|---|
| Status regex normalisation granted/pending/unknown/filed | `dataset.js:775-781` |
| Jurisdiction alias to ISO code | `patents.js:44-72`, `dataset.js:798` |
| Assignee to competitor by shared distinctive tokens when `comp_id` absent | `dataset.js:815-911` |
| `grantStatusKnown`, `relevDiscriminates` corpus flags | `dataset.js:858-864` |
| Per-field holder roll-up, crowding thresholds, client filing regex | `dataset.js:913-1010` |
| `deriveStats` four buckets | `patents.js:302-313` |
| Area list (indexed, else configured, else tech categories) | `patents.js:528-537` |
| Category filter counts and DOM hide/show | `Patents.jsx:88-91,:150-161` |

---

## 4. New-schema tables for these pages that no page reads

| Table | Rows read today? | Should a page read it? |
|---|---|---|
| `serving.competitive_partnership` | No (`partners` hard-coded `[]`) | **Yes**: the only source of Partnerships rows |
| `serving.competitive_partnership_evidence` | No | **Yes**: stored equivalent of the synthetic relationship cards (`tieHtml`) |
| `serving.competitive_partnership_relationship_detail` | No | **Yes**: tie hero (title, type, confidence, stated_as_of, back action) |
| `serving.client_partner` | No (`KSSL_PARTNERS: []`) | **Yes** for the overlap join (name comparison) and the "what KSSL uses them for" read |
| `serving.client_partner_relationship` | No | **Yes** (`kssl_read`, `competitor_overlap`, `relationship_type`), after the overlap-key decision |
| `serving.client_partner_source` | No | Optional (sources of the client's partner) |
| `serving.client_partner_product` | No | No (no page shows partner products) |
| `ui.competitive_partnership_graph` | No | Optional: only view state (zoom, group_by); keep state in memory |
| `serving.competitive_project_source` / `_specification` / `_stage` / `_timeline` | No | **Yes**: all four back drawer sections that render empty or are computed from a missing rank |
| `ui.ui_project_metric` | No | Decide: could replace the header count line |
| `ui.ui_project_view_state` | No | No (runtime state) |
| `serving.competitive_geo_product_match` | No | **Yes**: replaces the fuzzy KSSL counterpart match and the verdict |
| `serving.competitive_geo_product_specification` | No | **Yes**: replaces `compareProducts` winner/gap computation |
| `serving.competitive_geo_product_news` | No | **Yes**: "Footprint-linked intelligence" list |
| `serving.competitive_geo_source` | No | **Yes**: "Source evidence" list |
| `serving.competitive_geo_location` columns `latitude`, `longitude`, `region_name`, `kssl_presence_summary`, `presence_types` | table read, columns not | **Yes**: coordinates replace the 85-entry table; summary replaces the computed badge |
| `serving.competitive_geo_company_presence` columns `overlap_status`, `matched_ranges`, `product_count`, `products_summary`, `display_order` | table read, columns not | **Yes**: replaces the keyword overlap engine |
| `serving.competitive_geo_product` columns `reported_value`, `quantity`, `product_range`, `rated_power_*`, `fuel_type`, `frequency_hz`, `activity_type`, `display_order` | table read, columns not | Decide (only dead `PairDetail` shows value/quantity) |
| `serving.competitive_competitor_location` | No | Decide (alternative source for the country facet and Geo) |
| `ui.competitive_geo_filter` | No | Optional: dropdown labels (page hard-codes "Competitor", "Country") |
| `ui.ui_geo_country_detail_state`, `ui_geo_products_supplied_state`, `ui_geo_product_comparison_state`, `ui_geo_footprint_view_state` | No | Decide: the first three hold counts (active/category-only/rating-matched competitors, product/export/service counts, comparison scores) the page computes in JS; either store-and-read or keep computing. `ui_geo_footprint_view_state` is map view state |
| `serving.competitive_patent_portfolio`, `_filing`, `_classification` | No (`PATENTS` hard-coded empty) | **Yes**: the only source for Patents; also carry `empty_message`, `data_source_note`, `status_note`, `grant_status_state` that replace invented copy |
| `ui.competitive_patent_view_state` | No | Optional (state) |

**Columns the pages need that no table has (rule 3: hide, user to decide add-or-keep-hidden)**

Partnerships: `rel` type code, `kind`, `status`/`ended`, `deal`, `insight`, `mean` (strategic impact), `sig`, explicit rival-side shared-partner flag/id (and `competitor_id` for client_partner side).
Projects: current stage per project is derivable only from `competitive_project_stage.is_current`; no unit for `estimated_value`.
Geo: estimate flag (replaces magic `src === "syn"`), per-product activity code vs text (CSS/`dirForAct`), competitor_id type alignment.
Patents: assignee, English title, grant date, publication date, grant number, kind code, abstract, relevance, threat, per-filing source list, client (KSSL) portfolio, IPC list (only one code), per-field granted/pending, `techArea` as a stored value (only classification `category_label` per portfolio).

## 5. Summary of actions

| Action | Items |
|---|---|
| remove | `OV_DEF`/`OV_KIND`/`overlapHtml`/`overlapDefsHtml`/`compReportHtml`/`fieldReadHtml`/`graphSvg`/`layoutGraph`/selfCheck/geomCheck (partners.js); `geoOvPanel`/`geoOwnPanel`/`geoOvBadge*`/`geoPickOverlap`/selfCheck and the keyword engine (geo.js); `COUNTRY_COORDS`; `DEFENSE_FIRM_COUNTRIES`; `ipc.js`; `COMPANY_MATERIALS`; `PairDetail`/`CountryDetail`/`countryNews`/`ksslCo` (dead); `PAIRS`/dedupe; `compareProducts` use in Geo; assignee-token matching; crowding thresholds; literals at the lines in section 2b |
| map | partner rows to `competitive_partnership*`; KSSL_PARTNERS to `client_partner*`; projects drawer to `what_the_project_is`, `researched_as_of`, `competitive_project_*`; geo to `latitude/longitude`, `overlap_status`, `matched_ranges`, product_match, specification, news, source; patents to the three `competitive_patent_*` tables; fix the four backend bugs and the two id-type mismatches in section 0 |
| hide | images in tie view; `Assessment`; patent assignee/abstract/relevance/threat/grant dates/English title; crowding; "KSSL holds" text; estimate marker; status/deal/insight/mean until columns exist |
| decide | node identity (partner_id vs name folding); overlap key; type grouping without `rel`; use stored counts vs computed counts; country facet source; map tiles (external); IPC text source |
