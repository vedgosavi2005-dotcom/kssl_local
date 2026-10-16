# Audit D - Market pillar + Technology Innovations

Scope: Top opportunity (route `m-overview`), Market Intelligence (route `m-report`), Tenders (route `tender`, plus the archived `awarded-tenders` / `closed-tenders` routes), Global Requirements (`global-requirement`), Innovations (`innovation`), and the market metric strip.
Read-only audit. Nothing in the repo was edited.

## 0. Read this first

**Route naming (the brief's labels are swapped).** `src/lib/route.js:38-41`: `m-overview` = "Top opportunity" and renders `TopOpportunity.jsx` (`Layout.jsx:168`). `m-report` = "Market Intelligence" and renders `MarketOverview.jsx` (`Layout.jsx:166`). Both are covered below.

**State of the DB.** Every `serving.market_*`, `serving.technology_*`, `ui.market_*`, `ui.technology_*` table I checked has 0 rows (live `ui`/`serving`; the staging row-count query returned no non-empty table either). "Served today" below therefore means "what `backend/app.py` maps", not "what holds data".

**No `ui.*` table is read by any page.** `app.py` loads all of them into `data.database.ui.*` (app.py:84-107) and nothing in `src/` references `data.database` (grep: zero hits). All page headings, section labels, column headers, filter labels, empty-state text and rail labels are code literals today. The schema has a home for nearly every one of them (see section 4).

**Shorthand for files.**
`TO`=src/pages/market/TopOpportunity.jsx, `MI`=src/pages/market/MarketOverview.jsx, `TD`=src/pages/market/Tenders.jsx, `GR`=src/pages/market/GlobalRequirement.jsx, `IN`=src/pages/technology/Innovation.jsx, `mo.js`=src/lib/marketOverview.js, `tr.js`=src/lib/tenderRow.js, `tc.js`=src/lib/tenderCalc.js, `in.js`=src/lib/innovation.js, `ds.js`=src/lib/dataset.js, `ov.js`=src/lib/overview.js, `gm.js`=src/lib/gapModel.js, `LY`=src/components/layout/Layout.jsx, `app.py`=backend/app.py.

**Biggest findings (detail in sections 2-4).**
1. Many fields the UI reads are **never served**, so they render empty today: tender `posted`, `qty`, `srcs`, `matches`, `req`, `reqNote`, `competitorFit`, `revenueEstimate`, `desc` (backend sends `description`); top-opportunity `issuer`, `rivalToBeat` (backend sends `rival`), tender/project `title` (backend sends the **id** as title, app.py:492, 501); requirement `status`, `sources`; innovation `mat` (backend sends `maturity`), `body`, `horizon`, `gap`, `whatsNew`, `srcs`.
2. `app.py:386` serves `client_position` as `driver`, and the UI labels it "Driven by" (`IN:212`). Wrong column behind the label.
3. Hard defaults presented as data: Global Requirements fit defaults to "strong" (`GR:204`), KSSL model defaults to "Indigenous Defense Portfolio" (`GR:339`), value to "not disclosed" (`GR:261`), status to "Requirement Draft" (`GR:265`), countdown to "Draft Stage" (`GR:225`); Top Opportunity prints any unknown fit as "Not a fit" (`TO:128-132`).
4. `tc.js:173` overwrites the stored `closingDate` (= `closing_date`, app.py:331) with `t.deadline` (= `deadline_text`), so the real date column is lost.
5. Three different definitions of "open / closed / awarded" exist (`ov.js:389-399`, `TD:161-163`, `ds.js:502-506`) and disagree on `status === "closed"`.
6. "Top opportunity" ranking, value-in-crore totals and the shortlist are computed in JS with invented rules and an invented FX table (`gm.js:16`, `ov.js:414-433`).

---

## 1. Page tables

Column key: **Served today?** = `table.column` the backend maps, or "not served". **Kind** and **Action** use the brief's vocabulary. "NEW" = new-schema column to use.

### 1.1 Top opportunity (`m-overview`) - `TO` + `LY`

Served today (app.py:488-510): `topOpportunities.topTenders[]` = {id, **title = tender_id**, decides, ksslFit, ksslModel, rival, revenue, status}; `projectsBeforeTender[]` = {id, **title = opportunity_id**, country, stage, revenue, ksslFit, ksslModel}; `nextMoves[]` = {id, action, days, tenderTitle}. No ORDER BY anywhere (`SELECT *`, app.py:100).

| UI element | dataset key / field (file:line) | Served today? | NEW column to use | Kind | Action |
|---|---|---|---|---|---|
| Page heading "Top opportunity" | `cfg.title`, set in ds.js:313 and :640; rail label route.js:38 | literal in code | `ui.market_top_opportunity_view.page_heading` (also `ui.market_ui_navigation.view_label`) | CHROME | map |
| Header count line "N top tenders · N pre-tender targets · revenue & strategic fit ranked" | LY:130-133 | counts = array lengths; wording literal | counts computed from rows (fine); wording -> `ui.market_top_opportunity_view.sort_logic_label` | COMPUTED-JS count + INVENTED claim "revenue & strategic fit ranked" (LY:133) | map wording; keep count |
| Rail badge on "Top opportunity" | `navCounts` ov.js:779-781 = `overviewConfig.market.cards.length` = promoted tender shortlist (<=20, ov.js:413) + signal-lane "perceived opportunities" (<=24, ds.js:615-625) | not from topOpportunities at all | `ui.market_view.rail_count` (or row count of `market_top_opportunity_tender` + `_project`) | COMPUTED-JS (invented scoring, see 3.3) | map (badge must equal what the page lists) |
| Metric strip (4 tiles) above page | `marketMetrics(data.tenders)` LY:98 | computed from all tenders | `serving.market_top_opportunity_metric` (metric_key, metric_label, formatted_value, amount_value, currency_code, note) + labels `ui.market_top_opportunity_view.*_metric_label`, `tender_value_metric_note`; or `ui.market_metric` | COMPUTED-JS (see 1.6) | map |
| Section "Top tenders" + note "ranked by revenue KSSL can win × how well a KSSL model fits · revenue is an estimate" | TO:82-85 | literal | `ui.market_top_opportunity_view.top_tenders_section_label`, `top_tenders_description` | INVENTED (states a ranking rule the DB does not hold, TO:84) | map |
| Column headers Rank / Tender / Decides / KSSL fit / KSSL model / Rival to beat / Revenue | TO:91-97 | literal (client name "KSSL" hard-coded) | labels are chrome; client name from `data.client` | CHROME | keep (swap "KSSL" for client name) |
| Rank number | `idx + 1`, TO:114 | `rank_position` not served | `market_top_opportunity_tender.rank_position` (ui row: `rank_position`) | COMPUTED-JS (array index; order = DB scan order since no ORDER BY) | map; sort by rank_position |
| Tender title | `t.title`, TO:116 | **`market_top_opportunity_tender.tender_id`** (app.py:492) - an id, not a title | join `market_tender.title` via `tender_id`; or `ui.market_top_opportunity_tender_row.tender_title_display` | STORED (wrong column served) | map |
| Buyer / country sub-line | `t.country`, `t.issuer`, TO:120 | not served for tenders | `market_top_opportunity_tender` has no buyer: join `market_tender.issuer_display/buyer_name`, `country_name`; or `ui.market_top_opportunity_tender_row.buyer_location_display` | STORED via join | map |
| Decides | `t.status === "evaluation" ? "award pending" : t.decides || "—"`, TO:124 | `decides`, `status` | `market_top_opportunity_tender.decides` (display `ui..._row.decides_display`) | INVENTED mapping (status code "evaluation" -> text "award pending", TO:124) | map; drop the mapping |
| KSSL fit badge | `t.ksslFit` -> "Good"/"Partial"/else "Not a fit", TO:128-132 | `kssl_fit` | `market_top_opportunity_tender.kssl_fit`; display `ui..._row.fit_grade_display` | INVENTED (code vocabulary strong/partial; **null/unknown -> "Not a fit"** is a default shown as a finding, TO:132) | map; show stored text, empty if null |
| KSSL model | `t.ksslModel`, TO:135 | `kssl_model` | `market_top_opportunity_tender.kssl_model` (`client_model_display`) | STORED | keep |
| Rival to beat | `t.rivalToBeat`, TO:136 | key mismatch: backend sends `rival` (app.py:494), UI reads `rivalToBeat` -> always "—" | `market_top_opportunity_tender.rival_to_beat` (`rival_display`) | STORED (broken mapping) | map |
| Revenue | `t.revenue`, TO:137 | `revenue_text` | `market_top_opportunity_tender.revenue_text` (`revenue_display`) | STORED | keep |
| Row click -> open tender | `jumpTo("market","tender",{tenderTitle:title})`, TO:14-19 | passes the tender **id** as a title; Tenders.jsx matches by `x.title` (TD:219-221) so it never matches | pass `tender_id` | COMPUTED-JS (broken join) | map |
| Section "Projects to win before they tender" + note "no defense procurement tender yet: armed forces spec drafting stage · revenue is an estimate" | TO:150-153 | literal | `ui.market_top_opportunity_view.projects_section_label`, `projects_description` | INVENTED (asserts every listed project is at "spec drafting stage", TO:152) | map |
| Project title | `p.title`, TO:185 | **`opportunity_id`** (app.py:501) | `market_opportunity.title` via `opportunity_id` (`ui..project_row.project_title_display`) | STORED (wrong column served) | map |
| Project country / buyer | `p.country`, `p.issuer`, TO:188 | `country_name` served; `issuer` not | `market_top_opportunity_project.country_name`, `.buyer_name` (`buyer_location_display`) | STORED | map |
| Where it stands | `p.stage`, TO:193 | `where_it_stands` | `market_top_opportunity_project.where_it_stands` (fallback `market_opportunity.stage/current_status/latest_milestone`) | STORED | keep |
| Project KSSL fit / model / rival / revenue | TO:197-207 | fit, model, revenue served; `rival_to_beat` **not served** | `market_top_opportunity_project.kssl_fit, kssl_model, rival_to_beat, revenue_text` | STORED (fit label mapping same INVENTED default as above, TO:198-202) | map |
| Project row click | `handleOpenTender(p)` TO:174 | - | none: a pre-tender project has no tender to open; `opportunity_id` has no page | NO-COLUMN (no destination) | decide (hide click, or add an opportunity detail view reading `market_opportunity*`) |
| Section "Next moves" + "what to do this week, soonest first" | TO:220-221 | literal | `ui.market_top_opportunity_view.next_moves_section_label`, `next_moves_description` | INVENTED ("this week" is a time claim; "soonest first" is not sorted by code, TO:233) | map |
| Next move Due | `m.days === 0 ? "today" : "in N day(s)"`, TO:246-248 | `days_remaining` (stored snapshot) | `market_next_move.due_text`, or compute from `due_date` | COMPUTED-JS (wording) over stored days; null `days` prints "in null days" (TO:247) | map; use `due_text`, else compute from `due_date` and hide when null |
| Next move Action | `m.action`, TO:249 | `action_text` | `market_next_move.action_text` (`ui.market_next_move_view.action_display`) | STORED | keep |
| Next move Tender | `m.tenderTitle`, TO:252 | `tender_title` | `market_next_move.tender_title` (`tender_display`) | STORED | keep |
| Next move ordering / priority / status | none | `sequence`, `priority`, `status`, `due_date`, `tender_id`, `opportunity_id` not served | `market_next_move.sequence` etc. (`ui.market_next_move_view.row_order`) | NO read today | map `sequence` for order |
| Empty text "No top opportunities or tender pipelines are on record." | TO:70 | literal | `ui.market_view.empty_state_text` | CHROME | keep |
| Header Copy/Print report text | TO:22-57 | uses same fields | same | CHROME wording + same data | keep (inherits fixes) |

### 1.2 Market Intelligence (`m-report`) - `MI` + `mo.js`

Served today: whole `data.tenders[]` from app.py:318-346: {id, title, issuer, country, cat, description, closingDate, deadline, dl, isLive, value, expectedRevenue, lean, leanTxt, ksslFit, ksslModel, rank, url, urlKind, status}. After `wireTendersWithRealDays` (tc.js:162-184) `dl`, `deadline`, `isLive`, `closingDate` are overwritten (see section 3).

| UI element | dataset key / field | Served today? | NEW column | Kind | Action |
|---|---|---|---|---|---|
| Page heading "Market Intelligence", count line | `viewMetaFor` ov.js:890-894; LY:125-128 | literal | `ui.market_ui_navigation.view_label`, `ui.market_view.view_title` | CHROME + COMPUTED-JS counts (open/awarded/closed, section 3.1) | map |
| Four tabs: "Number of active tenders" / "By category" / "Awarded" / "Closed" | `SECTIONS` MI:40-45 | literal | `ui.market_intelligence_tab.tab_label`, `tab_order` | CHROME | map |
| Count badge on each tab | `countOf` MI:386-395: open / demandSplit(open).length / awarded / closed | counts from `bucketTenders` | `ui.market_intelligence_tab.record_count` | COMPUTED-JS | map (stored count) or keep computed, but then must equal stored |
| Country filter options and counts | `facets.countries` <- `countriesOf` mo.js:257, 338-344 | `country_name` | `serving.market_filter_option` (filter_type=country: option_label, record_count, sort_order); labels `ui.market_filter` / `ui.market_global_requirement_filter` not applicable | COMPUTED-JS (cross-facet counts, "All (N)" = number of options, MI:444) | decide: stored `record_count` ignores the other facet; either accept that or keep computed |
| Category filter options + counts + colour swatch | `cats` MI:245; `CATEGORY_COLOR` mo.js:85 | `category_text`, falling back to **`category_id`** (a bigint) at app.py:329 | `market_filter_option` (filter_type=category); label `market_tender.category_text` | COMPUTED-JS; **missing category prints as "Uncategorised"** (mo.js:89) = INVENTED label | map; hide tenders with no category rather than invent a label; remove the `category_id` fallback |
| Filter chrome "Filter", "Country", "Category", "All (N)", "N rows in X" | MI:436-505 | literal | `ui.market_filter.filter_label`, `option_label` | CHROME | keep |
| Chart "Demand split" (pie: slice size, share %, legend count) | `demandSplit(chartBase)` mo.js:201-222, MI:285 | counts from tenders | `serving.market_category_summary.active_tenders_count` per `category_id` (+`country_code`, `as_of_date`) | COMPUTED-JS: count by `cat`; share `Math.round(count/total*100)` (mo.js:215, MI:96/120); top 8 categories + folded grey "Other (N categories)" (mo.js:116) | map counts; percent stays computed |
| Pie slice names | `t.cat` | `category_text` | `market_category_summary.category_id` has no name table in the new schema | NO-COLUMN for category dimension (market has no `market_category` table) | decide: add a market category table, or use `market_tender.category_text` |
| Pie colours (9-hue SERIES) | mo.js:64-66 | - | - | CHROME (visual encoding) | keep |
| Chart "Closing window": columns "1-7 days / 8-14 / 15-30 / 30+ / No date published" | `closingWindows` mo.js:227-238, WINDOWS mo.js:23-29 | `dl` computed from `closing_date` (tc.js) | none stores bucket counts; per-tender `market_tender_closing_window.days_remaining` / `market_tender.closing_date` | COMPUTED-JS (bucket edges 7/14/30 are UI rules; dl=365 "stage" counted as 30+, mo.js:230; dl=9999 = "No date published") | keep computed from `closing_date`; edges are UI rule |
| Chart/pie tooltips (first 3 titles) | `examplesFor` MI:296-302 | `title` | `market_tender.title` | COMPUTED-JS | keep |
| Chart empty text "nothing on record states a category" / "nothing open on record" | MI:514, 527 | literal | `ui.market_view.empty_state_text` | CHROME | keep |
| Table "By category": Category, Open, Share, Markets | MI:541-595 | computed | `market_category_summary` (Open = `active_tenders_count`) | COMPUTED-JS: Share = rounded %; "Markets" = distinct `t.country` joined " · " (MI:581-589) | map counts; Markets stays computed from `market_tender.country_name` |
| Note "every open tender counted exactly once · click a row to read it in the table" | MI:545-547 | literal | `ui.market_view.empty_state_text`/none | CHROME | keep |
| Tender table: Tender (title, link) | `t.title`, `t.url`, MI:322-331 | `title`, `source_url` | `market_tender.title`, `.source_url` (`ui.market_tender_card.title_display`) | STORED | keep |
| Tender table: Where (buyer · country) | `t.issuer`, `t.country`, MI:331 | `issuer_display` or `buyer_name`; `country_name` | `market_tender.issuer_display/buyer_name`, `.country_name` | STORED | keep |
| Tender table: Category | `t.cat`, MI:369 | `category_text` | `market_tender.category_text` (`category_display`) | STORED | keep |
| Tender table: Closes | `formatDate(t.closingDate)`, MI:372 | `closingDate` is **overwritten with `deadline_text`** at tc.js:173 | `market_tender.closing_date` | STORED (broken by tc.js:173) | map; stop overwriting |
| Tender table: Source "host ↗" | `hostOf(t.url)`, MI:339, mo.js:131 | derived from `source_url` | `market_tender_source.portal_name/publisher` or `market_tender_portal.portal_name` | COMPUTED-JS (hostname parse of URL) | map to `portal_name`; fall back to nothing |
| "no URL on record", "No date published", "—" | MI:38, 343 | literal | - | CHROME | keep |
| Row sort | `reportRows` sort by `dl` asc, mo.js:335 | computed `dl` | - | COMPUTED-JS | keep |
| "Show N more of M" paging | MI:313-318 | - | - | CHROME | keep |
| Header report (Pipeline Open/Awarded/Closed + listed rows) | MI:248-275 | computed | - | COMPUTED-JS counts | keep |
| Section remembered | localStorage MI:47-55 | - | - | CHROME (per-viewer convenience) | keep |

### 1.3 Market metric strip (shows on `m-overview`, `m-report`, `tender`, `awarded-tenders`, `closed-tenders`, `global-requirement`) - `LY:92-111, 236-287`, `mo.js:141-187`, `MetricsStrip.jsx`

`marketMetrics(data.tenders)` is called with **all** tenders (open + awarded + closed). Sub-lines are not printed (MetricsStrip prints `m.sub` only when `m.warn`, MetricsStrip.jsx:134; `marketMetrics` never sets `warn`). Tiles are inert on market pages (LY:242).

| UI element | dataset key / field | Served today? | NEW column | Kind | Action |
|---|---|---|---|---|---|
| Tile label "Active tenders" | literal mo.js:156 | - | `ui.market_metric.metric_label` | CHROME | map |
| Tile value "Active tenders" | `open.length` (bucketTenders) mo.js:143,158 | computed | `ui.market_tenders_view.active_tenders_count` or `market_category_summary.active_tenders_count` summed | COMPUTED-JS | map |
| Tile "Markets" | `new Set(country).size` mo.js:144,165 | computed | `ui.market_tenders_view.markets_count` | COMPUTED-JS (over all tenders, not just open) | map |
| Tile "Source portals" | distinct `hostOf(url)` mo.js:145,172 | computed from URL hostnames | `ui.market_tenders_view.source_portals_count`, `market_category_summary.source_portals_count`, or count of `market_tender_portal` | COMPUTED-JS (hostname parse; not a portal list) | map |
| Tile "Value disclosed" (₹ crore total, unit "cr") | `Math.round(sum parseCr(t.value))`, `unit:"cr"`, mo.js:146-147,177-180 | parsed from `value_text` | `ui.market_tenders_view.value_disclosed_display`; count-only `market_category_summary.value_disclosed_count`; amounts `market_tender.value_amount` + `value_currency` | COMPUTED-JS + **INVENTED FX table** (gm.js:16: US$ 8.3, € 9.0, £ 10.5, A$ 5.5, AED 2.26, MYR 1.9 crore/million; regex over text gm.js:17-27); includes awarded and closed tenders | decide: show stored `value_disclosed_display`; no FX table exists in the schema, so a crore total needs a stored number |
| Sub-lines (not printed) | mo.js:160,166,172,181-185 | - | - | dead | remove |

### 1.4 Tenders (`tender`, archived `awarded-tenders` / `closed-tenders`) - `TD` + `tr.js` + `tc.js`

Awarded and Closed exist as (a) the `m-report` tabs in 1.2 and (b) archived routes of this same page (`LY:210-215`, route.js:54-58). Same list component, different filter predicate (`TD:157-176`).

**List (left side)**

| UI element | dataset key / field | Served today? | NEW column | Kind | Action |
|---|---|---|---|---|---|
| Page heading "Tenders" + count text "Live opportunities matched to product portfolio" | ov.js:895-898 | literal | `ui.market_tenders_view.page_heading`; count `active_tenders_count` | CHROME; "matched to product portfolio" is a claim about the data | map |
| Filter labels Product Type / Country / Category, "All countries (N)", "Search country…", "sorted by deadline" | TD:298-362, 378 | literal | `ui.market_tender_filter.filter_label/search_placeholder`, `ui.market_tenders_view.country_filter_label/category_filter_label/sort_label` | CHROME | map |
| Product Type options "Land Systems" / "Air, Naval & Missiles" and per-tender classification | `isAirNaval` regex `/uav|drone|naval|marine|missile|air defence/i` over `cat + title`, TD:154-155, 182-184, 275-281 | no column | none (`market_filter_option` could list options but nothing classifies a tender) | **INVENTED** (classification rule + the two category names in code) | hide, or decide: add a column |
| Country / Category options + counts | `facetOptions` countryFacet.js:260-274 over `scope` | `country_name`, `category_text` | `market_filter_option` | COMPUTED-JS (counts honour the other two facets) | decide (see 1.2) |
| `data.tpAllCountries`, `data.tpAllCats` ordering vocab | TD:291 | not served (empty) | `market_filter_option.sort_order` | dead | map `sort_order` |
| Tab scope open/awarded/closed | TD:157-167 | `status`, `url_kind`, `isLive`, `deadline` | `market_tender.status`, `.is_live`, `.closing_date`, `.url_kind`; `market_tender_closing_window.status` | COMPUTED-JS (rule 3.1; differs from `ov.js:389`) | decide one definition; prefer stored `status` |
| Global-search filter | TD:169-175 tokens over `title issuer cat country desc` | `desc` not served | `market_tender.description` | COMPUTED-JS | keep |
| Sort | by `dl` asc, `||999`, TD:194-197 | computed `dl` | `market_tender.rank_position` is the stored rank | COMPUTED-JS | keep (sort is "by deadline" chrome) or switch to rank |
| Card title | `smartTitleCase(row.title)` TD:460 | `title` (fallback `title_localized`, `tender_number` as id, app.py:321-326) | `market_tender.title` (`ui.market_tender_card.title_display`) | STORED + display casing | keep |
| Card countdown chip | `countdownText` TD:433-443; class `dlClass` TD:55-60 | `dl` computed | `ui.market_tender_card.countdown_display`; stored `market_tender.days_remaining`, `deadline_text` | COMPUTED-JS (3.2) | decide: stored `countdown_display` vs computed from `closing_date` |
| Card param "Buyer" | `resolveTenderRow().params[buyer]` tr.js:87-89 | `issuer_display`/`buyer_name`; fallback: regex over `t.req` rows (not served) | `market_tender.issuer_display/buyer_name` (`buyer_display`) | STORED (+ idle heuristic) | map; delete the `req` heuristic |
| Card param "Country" | tr.js:90-92 | `country_name` | `market_tender.country_name` (`country_display`) | STORED | keep |
| Card param "Category" | tr.js:93 | `category_text`/`category_id` | `market_tender.category_text` (`category_display`) | STORED | keep (drop `category_id` fallback) |
| Card param "Value" | tr.js:94-96 | `value_text` | `market_tender.value_text` (`value_display`) | STORED | keep |
| Card param "Status" | tr.js:117-126: "Awarded" if `status==="awarded"` or `url_kind==="award"`; "Closed" if `status==="closed"` or (`isLive===false` and a deadline exists); else capitalised `status` | `status`, `isLive` (computed) | `market_tender.status` (`status_display`) | COMPUTED-JS (3.1) | map to `status_display`/`status` |
| Fit bar label "{client} fit" | `clientName` TD:96 | `client_account.brand_name` | - | CHROME (client name from DB) | keep |
| Fit bar level + width + word | TD:397-431 | `kssl_fit`, `lean_code`; `matches` not served | `market_tender.kssl_fit`, `market_tender_fit_assessment.fit_grade/fit_score`, `market_tender_product_match.fit_percent`; display `ui.market_tender_card.fit_grade_display` | COMPUTED-JS + **INVENTED**: % -> grade at >=75 strong / >=45 partial (TD:413); word grades -> bar width 100/65/30% (TD:419-430); `lean_code` mapped go->strong, watch->partial, threat->weak (TD:406); reads `row.cumminsFit` (TD:405, leftover from another client) | map to stored grade; drop bar widths for words (print the word) or decide a % column |
| Empty states "No tenders match this filter" / "No tenders served yet" | TD:493-495 | literal | `ui.market_view.empty_state_text` | CHROME | keep |
| Card "Published", "Quantity", "Closing date", "Source" params | built by resolver but **hidden on the card** (DASHBOARD_PARAM_KEYS, TD:91) | - | - | - | n/a (shown in detail) |

**Detail / assessment (right side)**

| UI element | dataset key / field | Served today? | NEW column | Kind | Action |
|---|---|---|---|---|---|
| Eyebrow "Tender Assessment" | TD:517 | literal | `ui.market_tender_assessment_view.panel_title` | CHROME | map |
| Title | `smartTitleCase(t.title)` TD:518 | `title` | `market_tender.title` | STORED | keep |
| Sub-line 1: issuer · country · value | TD:520 | stored | `market_tender.issuer_display, country_name, value_text` (`panel_subtitle`) | STORED | keep |
| Sub-line 2: timing | `t.timing || t.deadline` TD:521 -> tc.js strings "closes in N days", "Awarded - programme concluded", "Closed - deadline passed", "no deadline on record" (tc.js:29, 91, 111, 152-153) | computed | `ui.market_tender_assessment_view.closing_summary`; `market_tender_closing_window.milestone_text` | COMPUTED-JS (generated sentences from a date) | map to stored `closing_summary`; keep computed only as fallback if decided |
| "{client} Fit · Rank #N" + verdict word | TD:526-549: `verdict = pct or {high,mid,low}->{strong,partial,weak}`, else `t.fit`; rank `t.rank` | `kssl_fit` (as `ksslFit`; UI reads `t.fit` -> not served), `rank_position` (as `rank`) | `market_tender.kssl_fit`, `.rank_position`; `market_tender_fit_assessment.fit_grade, fit_rank, kssl_fit_rank, fit_score`; ui `fit_grade_display`, `fit_rank_display` | COMPUTED-JS grade bands (`fitClass`: >=75 high, >=50 mid, TD:12-15 - **different cut-off (50) from the card's 45**, TD:413) | map; single stored grade, remove bands |
| Eyebrow "What the tender requires" | TD:553 | literal | `ui.market_tender_assessment_view.requirements_section_label` | CHROME | map |
| Requirement prose | `t.reqNote` (HTML) else `t.desc` TD:554-558 | **not served** (`reqNote`); description served as `description`, UI reads `desc` | `market_tender_requirement.requirement_note/scope_text/description` (by `display_order`), `market_tender.description` | STORED (key mismatch) | map; stop `dangerouslySetInnerHTML` unless HTML is a declared stored format |
| Requirement key/value rows | `t.req` [[label, html]] TD:559-564 | not served | `market_tender_requirement`: `requirement_type` (label), `scope_bullet_label/value`, `equipment_scope`, `rating_band`, `use_case`, `quantity`+`quantity_unit`, `source_text` | STORED | map |
| Glossary: "“Indigenous content” = the DAP 2020 threshold ... (50%+ for Buy Indian-IDDM). A bid that cannot declare the threshold is technically non-compliant regardless of price." | TD:565-571 | literal | none | **INVENTED** (procurement-policy content, triggered by regex on requirement text) | remove |
| Eyebrow "Matched {client} products" | TD:577 | literal | `ui.market_tender_assessment_view.matched_products_section_label` | CHROME | map |
| Match name, "N% fit", fit class | `m.n`, `m.pct`, `m.fit` TD:579-582 | `t.matches` not served | `market_tender_product_match.match_label, fit_percent, fit_grade` | STORED | map |
| Match lines with ▲/▼ | `m.lines [[up|down, html]]` TD:584-589 | not served | `market_tender_product_match_line.line_label, line_value` (**no up/down flag column**) | NO-COLUMN for the arrow direction | decide: drop the arrows or add a flag |
| "Expected revenue (estimate)" | `t.revenueEstimate || t.expectedRevenue` TD:595-599 | `expected_revenue_text` as `expectedRevenue` | `market_tender.expected_revenue_text`; `market_tender_fit_assessment.revenue_estimate_text/min/max/tier` | STORED | keep (the word "estimate" is a claim: fine if the column is an estimate) |
| "Competitor fit" cards | `t.competitorFit \|\| t.competitors` TD:602-621 | not served | `market_tender_competitor_fit.competitor_name, fit_label, competitor_product_display/competitor_products_text, fit_rationale, rank_position` | STORED | map; the badge is always styled `fit high` whatever `c.fit` says (TD:609) |
| "Tender details" rows: Buyer, Country, Category, Value, Quantity, Published, Closing date, Status, Source, Notice ref. | `factRows` TD:33-39, tr.js:34-44, 86-133 | Buyer/Country/Category/Value/Status stored; Quantity (`t.qty`), Published (`t.posted`), Source (`t.srcs`) **not served** | `market_tender.quantity`+`quantity_unit`, `.published_date`, `.closing_date`, `market_tender_source.publisher/portal_name` | STORED (+ `formatDate` display) | map |
| Notice ref. | `noticeRef` = id with prefix before first "_" removed, TD:21-26 | derived from id | `market_tender.notice_reference` (or `tender_number`); `ui.market_tender_assessment_view.notice_ref_display` | COMPUTED-JS (string surgery on id) | map |
| Closing date value | `servedDeadline` tr.js:63-71; falls back to `t.stage` text | `closingDate` overwritten (tc.js:173) | `market_tender.closing_date` | STORED (broken) | map |
| "Bid assessment" label + `lean_text` (HTML) + lean colour class | TD:639-643 | `lean_text` as `leanTxt`, `lean_code` as `lean` | `market_tender.lean_text`, `.lean_code` | STORED | keep (vocabulary of `lean_code` is code-defined: "go"/"maybe" in ds.js:546/tr.js:209, "watch"/"threat" in TD:406) |
| Source chips | `srcChips(t.srcs)` else `[{label:"Source", url}]` TD:645-657 | `source_url` only | `market_tender_source.source_url, publisher, portal_name, source_type, is_primary, access_note, status_check_url, retrieved_at` | STORED | map |
| Button "Open the tender notice / portal / Read the award announcement" + note "opens … on <host>" | `ctaLabel`/`ctaNote` TD:67-85 | `url_kind`, `source_url` | `market_tender.url_kind`, `.source_url`; `ui.market_tender_assessment_view.open_notice_label` | CHROME keyed on stored `url_kind` (host parse is computed) | keep; map label to `open_notice_label` |
| Placeholder "Ask about this tender…" | TD:679 | literal | - | CHROME | keep |
| Awarded tab: who won, award date, contract value | none | none | **no column** in `market_tender*` (no awardee/award_date) | NO-COLUMN | decide: add columns or leave the tab showing only status |
| Closing extension / "milestone" info | none | none | `market_tender_closing_window.is_extension_confirmed, extension_checked_at, milestone_text`; `market_tender.latest_milestone` | unread | decide (should be read) |
| Submission method, registration, local-presence requirement, frequency | none | none | `market_tender.submission_method, registration_requirement, local_presence_requirement, frequency`; `market_tender_portal.access_status, registration_required` | unread | decide (should be read in details) |

### 1.5 Global Requirements (`global-requirement`) - `GR`

Served today (app.py:349-375): {id, title, buyer, country, cat, value, dl, deadline, desc, ksslFit, ksslModel, strategicAssessment, specs[[label,value]]}. Not served: `status`, `sources`, `region`.

| UI element | dataset key / field | Served today? | NEW column | Kind | Action |
|---|---|---|---|---|---|
| Heading / count "N requirements on record · worldwide defence demand & capability specs" | LY:135-138; ov.js:900-903 | literal + array length | `ui.market_global_requirement_view.page_heading`; count = rows | CHROME + COMPUTED-JS count | map |
| Filter labels Country / Category, "Search country…", "sorted by requirement deadline" | GR:152-198 | literal | `ui.market_global_requirement_view.country_filter_label/category_filter_label/sort_label/filter_label`; `ui.market_global_requirement_filter.search_placeholder` | CHROME | map |
| Filter options + counts | `countryOptions`/`catOptions` GR:101-125 | `country_name`, `category` | `ui.market_global_requirement_filter.option_count`; or computed | COMPUTED-JS (counts of the other facet applied) | keep computed |
| Sort | by `dl` asc, GR:41 | `days_remaining` (stored) | - | COMPUTED-JS | keep |
| Card title | `smartTitleCase(title)` GR:242 | `title` | `market_global_requirement.title` (`ui.market_global_requirement_card.title_display`) | STORED | keep |
| Countdown chip | `row.dl`, GR:215-225 | `days_remaining` (snapshot) | `ui.market_global_requirement_card.deadline_display`; `market_global_requirement.deadline` (varchar), `.days_remaining` | COMPUTED-JS wording ("N days left"/"today"); **no closing date column, so days cannot be recomputed**; fallback `row.deadline \|\| "Draft Stage"` (GR:225) = **INVENTED default**; `Number(null)=0` makes a missing `dl` count as urgent (GR:215-218) | map to `deadline_display`; remove "Draft Stage" |
| Card Buyer | GR:249 | `buyer_name` | `market_global_requirement.buyer_name` (`buyer_display`) | STORED | keep |
| Card Country | GR:253 | `country_name` | same (`country_display`) | STORED | keep |
| Card Category | GR:257 | `category` | same (`category_display`) | STORED | keep |
| Card Value | `row.value \|\| "not disclosed"` GR:261 | `value_text` | `market_global_requirement.value_text` (`value_display`) | STORED + **INVENTED claim** "not disclosed" (absence in DB is not a statement that the buyer did not disclose) | map; show empty |
| Card Status | `row.status \|\| "Requirement Draft"` GR:265 | **not served** | `market_global_requirement.status` (`status_display`) | INVENTED default "Requirement Draft" | map; no default |
| Card fit bar | `rawFit = row.ksslFit \|\| row.fit \|\| "strong"` GR:204; width 100/65/30% GR:212 | `kssl_fit` | `market_global_requirement.kssl_fit` (`fit_display`) | **INVENTED default "strong"** (a requirement with no fit is shown as a 100% strong fit); invented bar lengths | map; no default; omit bar when null |
| Detail eyebrow "Requirement Intelligence" | GR:304 | literal | `ui.market_global_requirement_view.panel_title` / `ui.market_global_requirement_detail.panel_title` | CHROME | map |
| Detail sub-lines buyer · country · value; category · deadline-or-status | GR:307-308 | stored | same columns | STORED | keep |
| "Requirement Scope" + description | GR:313-317 | `description` as `desc` | `market_global_requirement.description` (`ui.market_global_requirement_detail.scope_label`) | STORED | keep |
| "Target Specifications" rows | `specs` GR:321-333; built by O(n^2) scan app.py:355-359, unsorted | `spec_label`, `spec_value` | `market_global_requirement_specification.spec_label, spec_value, display_order` (`specs_label`) | STORED | keep; sort by `display_order` |
| "{client} Platform Match": `${ksslFit \|\| "Strong"} Fit · ${ksslModel \|\| "Indigenous Defense Portfolio"}` | GR:339 | `kssl_fit`, `kssl_model` | `market_global_requirement.kssl_fit`, `.kssl_model` (`ui..detail.fit_label`) | **INVENTED** defaults "Strong" and "Indigenous Defense Portfolio" (content about the client's products in code) | map; no defaults |
| "Strategic Assessment" + `strategicAssessment` | GR:344-347 | `strategic_assessment` | `market_global_requirement.strategic_assessment` (`ui..detail.assessment_label`) | STORED | keep (confirm this is not the hidden "Strategic Positioning" paragraph; it is a per-requirement read) |
| Note under it: "The analyst's read for {client}, from the dataset's record of this requirement." | GR:349 | literal | - | INVENTED provenance claim (asserts who wrote it) | remove or map to a source column |
| Source links | `selectedReq.sources` GR:355-372 | **not served** | `market_global_requirement_source.source_label, source_url, source_type, display_order` (`ui..detail.source_label`) | STORED | map |
| Empty detail text "Select a global requirement to inspect …" | GR:378 | literal | `ui.market_global_requirement_view.empty_state_text` | CHROME | map |
| Empty list "No global requirements are on record." | GR:281 | literal | `market_global_requirement.empty_state_message` (NOT NULL per row, odd) / `ui..view.empty_state_text` | CHROME | map |
| Region | none | not served | `market_global_requirement.region` | unread | decide |

### 1.6 Innovations (`innovation`) - `IN` + `in.js`

Served today (app.py:378-393): `innovations[category_id][]` = {id, t=title, s=list_description, summary, driver=**client_position**, impact=why_matters_to_kssl, compNote=competitive_note, status=list_status_label|status, maturity}. `techCats` from `ui.technology_category` else `serving.technology_category` (app.py:396-407): {id, name}. No ORDER BY, so tab and list order = scan order.
Not served: `whats_new`, `background_what_it_is`, `horizon_year`, `action_note`, `assessment_outcome`, `sequence_no`, `external_id`, every `technology_innovation_status`/`_company`/`_source`/`_analysis` row, and `technology_source`.
This page shows **no metric strip** (LY:111 gates it to overview/market pages).

| UI element | dataset key / field | Served today? | NEW column | Kind | Action |
|---|---|---|---|---|---|
| Page heading "Innovation Pipeline", count line "Technology developments tracked across KSSL product domains"; rail "Innovations" | ov.js:915-919; route.js:49 | literal | `ui.technology_innovation_view.page_heading`, `list_heading`; `ui.technology_ui_navigation.page_heading`; `ui.technology_ui_view.view_label` | CHROME (count line names "KSSL product domains": a claim) | map |
| Rail badge | `counts.innovation` ov.js:789-803 = sum of list lengths | computed | `ui.technology_innovation_view.total_innovations` / `ui.technology_ui_view.rail_count` | COMPUTED-JS | map |
| Category tab names | `techCats[].name` IN:226-243 | `ui.technology_category.category_name` (fallback `canonical_name`) | `ui.technology_category.category_name` / `ui.technology_category_ui_label.ui_name` (the UI label per `tab_number`) / `serving.technology_category_ui_label.label_text, short_label` | STORED | map to `ui_name` |
| Tab number "01, 02..." | `String(i+1).padStart(2,"0")` IN:240 | index | `technology_category.tab_number` / `ui.technology_innovation_category_tab.tab_number` | COMPUTED-JS (array index) | map |
| Tab order | DB scan order | no sort | `technology_category.display_order` / `ui.technology_innovation_category_tab.tab_order` | COMPUTED-JS (implicit order) | map |
| Extra tab for an innovation whose category is not in `techCats` | ds.js:373-389: name built from the id (`k.replace(/-/g," ")` title-cased) | derived | none | **INVENTED** label | remove (an unknown category is a data error, not a tab) |
| Tab count | none shown | - | `technology_category.innovation_count`, `ui.technology_innovation_category_tab.innovation_count` | unread | decide (could show) |
| List heading "{category} · Innovations", search note | IN:257-262 | literal + name | `ui.technology_innovation_view.list_heading` | CHROME | map |
| Row title | `item.t`, `titleCaseHeadline` ds.js:183 | `title` | `technology_innovation.title` (`ui.technology_innovation_card.title_display`) | STORED + display casing | keep |
| Row maturity chip | `item.mat` + `MAT_LAB` IN:288-291, in.js:18-23 | **key mismatch**: backend sends `maturity` (app.py:390), UI reads `mat` -> never shown | `technology_innovation.maturity` / `technology_innovation_status.maturity_label` (`ui..card.maturity_display`) | INVENTED vocabulary (lab/dev/prod/fielded -> "Lab / research", "In development", "In production", "Fielded / in service", in.js:18-23; stored value is free text varchar(100)) | map to stored label; drop `MAT_LAB` |
| Row description | `item.body` with `<b>` stripped IN:292-295 | **not served** (`body`); backend sends `s` (list_description) and `summary` | `technology_innovation.list_description` or `.summary` (`ui..card.summary_display`) | STORED (key mismatch) | map |
| Row "Driven by" (`item.driver`) | IN:300 | `client_position` (**wrong column**, app.py:386) | companies: `technology_innovation_company.display_name, relationship` (`ui..card.company_display`) | STORED but wrong source | map to companies |
| Row horizon | `item.horizon` IN:301 | not served | `technology_innovation.horizon_year`, `technology_innovation_status.horizon_text` (`ui..card.horizon_display`) | STORED | map |
| Row position pill "{client} behind / at parity / ahead" | `item.gap` + `GAP_LAB` IN:26,302-306 | not served | `technology_innovation.client_position`, `technology_innovation_status.position_label` (`ui..card.client_position_display`) | INVENTED mapping of a 3-value code to sentences built from the client name | map to stored `position_label` text |
| Detail header title / sub-line | `iv.t`; `MAT_LAB[mat] · horizon · GAP_LAB[gap]` IN:356-369 | as above | `ui.technology_innovation_detail_panel.panel_title, maturity_display, horizon_display, client_position_display` | STORED once mapped | map |
| Eyebrow "Innovation Detail", Close button | IN:355, 331 | literal | `ui.technology_innovation_detail_panel.panel_title`, `close_label` | CHROME | map |
| Header pill GAP / WATCH / AHEAD | `positionPill` in.js:34-39, IN:346-349 | not served (`gap`) | `technology_innovation_status.assessment_badge` (`ui..detail_panel.assessment_badge`) | INVENTED mapping behind->"GAP", parity->"WATCH", ahead->"AHEAD" | map to `assessment_badge`; remove mapping |
| Verdict band "{client} is BEHIND / AT PARITY / AHEAD" | `GAP_VERB` IN:32, 183 | not served | `technology_innovation_status.position_label` | INVENTED composed sentence from code | map |
| "Why this matters to {client}" | `iv.impact` with `<b>[Analysis]…</b>` stripped, IN:175, 185-187 | `why_matters_to_kssl` | `technology_innovation.why_matters_to_kssl` (`ui..detail_panel.why_matters_text`) | STORED (HTML injected) | keep; label from `ui` |
| "Why {client} is behind/at parity/ahead" + `compNote` | `GAP_HEAD` IN:27-31, 189-191 | `competitive_note`; only shown when `gap` known (never) | `technology_innovation.competitive_note` (`ui..detail_panel.why_position_text`) | STORED; heading text composed from code | map; heading from `ui` |
| "What's new" | `iv.whatsNew` IN:202-204 | not served | `technology_innovation.whats_new` (`ui..detail_panel.whats_new_text`) | STORED | map |
| "Background · what it is" | `iv.body` IN:207-209 | not served | `technology_innovation.background_what_it_is` (`ui..detail_panel.background_text`) | STORED | map |
| Status block: Maturity / Driven by / Horizon / {client} position | IN:210-214; fallbacks "not stated", "not assessed" | partly served | as above | STORED + CHROME empty-state wording | map |
| Status block: Sources | `srcChips(iv.srcs / iv.url / iv.sources)` IN:215-218 | not served | `technology_innovation_source` -> `technology_source.label, url, publisher, source_type, access_status` (`ui..detail_panel.source_section_label`) | STORED | map |
| Cross-pillar strip "₹ exposure … live tenders in {cat} this gap touches" and "Reinforced across pillars" chips | `gapCorrelateStrip(gapModel,"technology",iv.t)` IN:219, gm.js:428-472 | computed from tenders + matchups by matching `koel_entity` to the innovation title | none | **COMPUTED-JS + INVENTED** (₹ via the FX table, joins on title text, gm.js:429-437) | hide (no column); decide whether to add a stored link table |
| "Recommended action" | deliberately omitted IN:205 | `action_note` unread | `technology_innovation.action_note` | policy | keep hidden |
| Assessment sections (analysis rows) | none | none | `technology_innovation_analysis.section_code, section_label, narrative, is_client_assessment, display_order` | unread; duplicates the fixed columns above | decide: render sections generically from this table and drop the fixed fields, or the reverse |
| Search filtering | `filterInnovations` in.js:48-57 over title, driver, horizon, body, impact | - | - | COMPUTED-JS | keep |
| "Generate report" (`techReportHtml`) | IN:110-116; lib/reports.js:94-160 | **no button calls it** (`generate` unused) | - | dead; contains literals "Intelligence Briefing · CEO", "CONFIDENTIAL · KSSL", "Competitive & market figures drawn from the platform dataset (real where sourced, estimated where marked)" | remove |
| Header Copy/Print report | IN:123-171 | same fields | - | CHROME + same data | keep |
| ScopeChat placeholder | IN:391 | literal | - | CHROME | keep |

**How technology categories/metrics feed these pages.** Categories feed the Innovation tabs (above) and the `d.techCats` used by search, gap model and the Technology overview tile "Domains tracked" (ov.js:602-628, computed: count of categories with >=1 innovation). Technology metric rows (`serving.technology_metric`, `ui.technology_metric`, `ui.technology_overview_metric_card`) are not read by Innovations; the Technology Overview audit owns them.

---

## 2. INVENTED content found

| file:line | quote | Verdict |
|---|---|---|
| `GR:204` | `row.ksslFit \|\| row.fit \|\| "strong"` | Asserts "strong fit" for any requirement with no fit. Remove. |
| `GR:339` | `{selectedReq.ksslFit \|\| "Strong"} Fit · {selectedReq.ksslModel \|\| "Indigenous Defense Portfolio"}` | Invents a fit grade and a client product line. Remove. |
| `GR:261` | `row.value \|\| "not disclosed"` | Asserts the buyer did not disclose a value. Empty only. |
| `GR:265` | `row.status \|\| "Requirement Draft"` | Invented status. Remove. |
| `GR:225` | `row.deadline \|\| "Draft Stage"` | Invented stage. Remove. |
| `GR:349` | "The analyst's read for {client}, from the dataset's record of this requirement." | Provenance claim not stored. Remove. |
| `TO:128-132` | `t.ksslFit === "strong" ? "Good" : … "partial" ? "Partial" : "Not a fit"` | Null/unknown fit is printed as "Not a fit" (same for projects, TO:198-202). Remove default. |
| `TO:124` | `t.status === "evaluation" ? "award pending" : t.decides` | Status code translated to prose. Use stored `decides`. |
| `TO:84` | "ranked by revenue KSSL can win × how well a KSSL model fits · revenue is an estimate" | States a ranking rule no column holds. Move to `ui.market_top_opportunity_view.top_tenders_description`/`sort_logic_label`. |
| `TO:152` | "no defense procurement tender yet: armed forces spec drafting stage" | Asserts a stage for every project. Move to `projects_description` or remove. |
| `TO:221` | "what to do this week, soonest first" | Time + sort claim. Move to `next_moves_description`. |
| `LY:133` | "revenue & strategic fit ranked" | Same ranking claim. |
| `TD:565-571` | "“Indigenous content” = the DAP 2020 threshold a bid must clear … (50%+ for Buy Indian-IDDM). A bid that cannot declare the threshold is technically non-compliant regardless of price." | Procurement-policy content in code. Remove. |
| `TD:154-155`, `182-184`, `275-281` | `/uav\|drone\|naval\|marine\|missile\|air defence/i` -> "Land Systems" vs "Air, Naval & Missiles" | Invented product-type classification and names. Hide. |
| `TD:405` | `row.cumminsFit` | Leftover from another client's deployment (reads a field that does not exist here). Remove. |
| `TD:406`, `413`, `419-430`, `12-15` | `lean "go"->"strong","watch"->"partial","threat"->"weak"`; >=75/45 and >=75/50 cut-offs; bar widths 100/65/30% | Invented grade bands and bar lengths, with two different cut-offs for the same measure. Use the stored grade. |
| `mo.js:89` | `(t && t.cat) \|\| "Uncategorised"` | A tender with no category becomes a category named "Uncategorised". |
| `mo.js:116` | `` `Other (${n} categories)` `` | Generated slice label (folding is a display rule; the label is derived). Acceptable if kept as chrome, but the 8-slice cut-off is invented. |
| `gm.js:16` | `CR_PER_MILLION = { "us$": 8.3, "a$": 5.5, "€": 9.0, "£": 10.5, aed: 2.26, myr: 1.9 }` | Invented FX rates drive every crore total. |
| `ov.js:414-433` | `lean go +100, maybe +40, geo +25, value min(30, cr/200), closing<=14d +20, top 20` | Invented scoring that picks the "shortlist" and the rail badge. Replace with stored `rank_position`. |
| `app.py:386` | `"driver": text(row.get("client_position"))` | Wrong column labelled "Driven by". |
| `app.py:492`, `:501` | `"title": text(row.get("tender_id"))`, `"title": text(row.get("opportunity_id"))` | Id served as the title. |
| `app.py:329` | `first_nonempty(row, "category_text", "category_id")` | A numeric id can appear as a category name. |
| `in.js:18-23` | `lab: "Lab / research", dev: "In development", prod: "In production", fielded: "Fielded / in service"` | Invented maturity vocabulary over a free-text column. |
| `in.js:34`, `IN:26-32` | `PILL = {behind:"GAP", parity:"WATCH", ahead:"AHEAD"}`; `` `${clientName} is AT PARITY` `` etc. | Invented verdict wording from a code. Use `position_label` / `assessment_badge`. |
| `ds.js:381-384` | category name from id: `k.replace(/-/g," ")` title-cased | Invented tab label. |
| `tr.js:195-223` (`tenderSummary`) | "…is procuring…", " Graded a strong fit for KSSL's portfolio.", " Value and quantity are not disclosed in the notice." | Re-words stored `lean`/`value`/`qty` (ok) but **asserts "not disclosed in the notice"** whenever the column is empty (not stored), and maps lean code `go` to "strong fit". Only reached by promoted market cards (ds.js:540-542) that no market page now shows (search results show the card title only). Remove with the promotion block. |
| `tr.js:177-189` (`tenderGist`) | `<item> — <category> · <country>` | Only re-words stored values (ok), but also only used by the dead promotion block. |
| `tr.js:49-56`, `87-132` | `reqRow(t, /buyer\|issuer\|…/)` | Heuristic that guesses which requirement row is the buyer/value/closing date. Idle (no `req` served). Replace by `market_tender_requirement.requirement_type`. |
| `ds.js:313,640-681` | "Top opportunity", "latest tenders that fit KSSL + perceived opportunities to act on", "tenders that fit KSSL: strong fit, geo presence, high value, closing soon" | Feed copy; only `title` is live (LY:118), the rest is dead copy making claims. Remove. |
| `ds.js:610-625` | "perceived opportunities" = signal-lane cards with `dir==="watch"` filtered by tags vs `KSSL_CATS` (never served) | Mislabels signals as opportunities; the real table `market_opportunity` is unread. Remove. |
| `reports.js:94-160` | "Intelligence Briefing · CEO", "CONFIDENTIAL · KSSL" | Unused (`generate` never called). Remove. |

---

## 3. Computed in the UI (rules)

### 3.1 Open / closed / awarded (three definitions)

| Where | Rule |
|---|---|
| `ov.js:389-399` `bucketTenders` (nav badges, m-report, tiles, search routing) | awarded = `status.toLowerCase()==="awarded"` or `urlKind==="award"`. closed = not awarded and (`isLive===false` or `dl<=0` or `deadline` contains "Closed"). open = the rest. |
| `TD:161-163` (Tenders tabs) | Same, plus closed also when `status.toLowerCase()==="closed"`. |
| `ds.js:502-507` (promotion) | Same as ov.js. |
| `tc.js:19-34` | `status` of `awarded`/`settled`, or `deadline_text` starting with "awarded" -> awarded (dl 0). |
| `tc.js:36-48` | any `stage` (never served) -> open, dl 365. |
| `tc.js:50-127` | closing date = `closingDate` / `dueDate` / `closing_date`, else a `req` row, else a "D Mon YYYY" pattern inside `deadline`; `diff = ceil(target - today)`; `<=0` -> closed ("Closed / Expired"), else open with `dl=diff`. |
| `tc.js:80-96` | no date and stored `dl` in 1..999 -> use the stored number. |
| `tc.js:134-156` | no date, `deadline` mentions closed/expired -> closed; else open with `dl=9999`, "no deadline on record". |
| `tc.js:181` | stored `is_live` is ignored; `isLive` = computed. |
| `tc.js:173` | **bug**: `closingDate: t.deadline` overwrites the stored `closing_date`. |

Effect: a stored `status="closed"` with a future or missing date is closed on the Tenders page but open on Market Intelligence and the rail. Stored candidates: `market_tender.status` (NOT NULL), `.is_live`, `.closing_date`, `.url_kind`, `market_tender_closing_window.status`. Vocabulary of `status` is not defined in the schema.

### 3.2 Days left / countdown / urgency

| Rule | Where |
|---|---|
| `dl` = whole days from the **browser clock** (local midnight) to `closing_date`, `Math.ceil` | tc.js:99-105 |
| Urgency class: <=7 urgent, <=14 soon, else normal | tc.js:87,118; TD:55-60; GR:216-218 |
| Chip text: awarded / closed / today / "1 day left" / "N days left" / `deadline` / "open" | TD:433-443 |
| Windows 1-7, 8-14, 15-30, 30+, none (9999); `dl===365` counts as 30+ | mo.js:23-29, 230 |
| Attention window `ATTENTION_DAYS = 14` | ov.js:412 |
| Global Requirements: uses the **stored** `days_remaining`, no recompute (no date column); "today" at 0, negative prints "-N days left" | GR:215-225 |
| Next moves: stored `days_remaining`; "today" / "in N day(s)" | TO:246-248 |

Stored `days_remaining` is a snapshot (see `market_tender_closing_window.as_of_date`); it goes stale. Either compute from `closing_date` / `due_date` (needs a stated rule) or show the stored `deadline_text` / `due_text`.

### 3.3 Fit grades, ranking, shortlist

| Rule | Where |
|---|---|
| Fit % -> grade: card >=75 strong, >=45 partial, else weak; detail >=75 high, >=50 mid, else low | TD:413, TD:12-15 |
| Word grade -> bar: strong/high/good 100%, partial/mid 65%, else 30% | TD:416-430, GR:206-212 |
| `lean_code` -> fit: go strong, watch partial, threat weak (TD:406); go -> "Strong KSSL fit", maybe -> "Worth qualifying" (ds.js:546) | |
| Fit badge on Top opportunity: strong "Good", partial "Partial", else "Not a fit" | TO:128-132, 198-202 |
| Rank on Top opportunity = row index | TO:114, 182 |
| Tender "Rank #N" = `rank_position` | TD:543 |
| Market attention score and top-20 cut (drives rail badge on Top opportunity) | ov.js:414-433 |
| Geo boost uses KSSL footprint countries from `geoData` | ds.js:513-515 |

### 3.4 Value -> crore

`parseCr` (gm.js:17-27): strips commas; "₹ N" taken as crore; else regex `US$|A$|$|€|£|AED|MYR` + number + optional B/M, converted with `CR_PER_MILLION` (gm.js:16); anything else (zloty, krone, koruna, "n/d") = 0. Used by: `marketMetrics` (mo.js:146-153,177), `marketAttention` (ov.js:423), `metricsFor` (ov.js:561), `buildGapModel` exposure, `formatCrore` (formatNumber.js:6-10: >=1000 -> "₹N.Nk cr"). Columns that could replace parsing: `value_amount`, `value_currency`, `value_text`; there is no FX/crore column.

### 3.5 Category shares and counts

| Rule | Where |
|---|---|
| Category count and share `Math.round(n/total*100)` over open tenders narrowed by country | mo.js:201-222, MI:96,120,174 |
| Slice order = fixed palette order from corpus rank (count desc, name asc), 9 hues, extra categories folded into "Other (N categories)" | mo.js:93-124 |
| Country / category facet counts with the other facet applied | mo.js:328-344, countryFacet.js:260-279 |
| Markets per category = distinct country list | MI:581-589 |
| Markets / Source portals tiles = distinct countries / distinct URL hostnames | mo.js:144-145 |

### 3.6 Display transforms on stored text (acceptable, listed for completeness)

`plainDashes`, `decodeAmp` (ds.js:66-120), `smartTitleCase` (TD:460, GR:242), `titleCaseHeadline` (ds.js:183), `tidySeparators` (ds.js:184), `formatDate` (tr.js, MI:372), `formatLabel` (TD:631), HTML strip of `<b>` (IN:294) and `[Analysis]` (IN:175).

---

## 4. New-schema tables for these pages that no page reads

`app.py` reads them (into `database`) but no component does. "Should read?" is my recommendation.

### 4.1 `serving` tables

| Table | Read today? | Should a page read it? |
|---|---|---|
| `market_tender` | yes, partially (unread: `buyer_organization_id`, `country_code`, `frequency`, `local_presence_requirement`, `registration_requirement`, `submission_method`, `latest_milestone`, `notice_reference`, `published_date`, `quantity`, `quantity_unit`, `value_amount`, `value_currency`, `title_localized`; read but ignored/overwritten: `is_live`, `days_remaining`, `closing_date`, `description`) | yes: Tenders details, Closing line |
| `market_tender_closing_window` | no | yes: assessment closing line (`milestone_text`, `is_extension_confirmed`, `extension_checked_at`, `as_of_date`) |
| `market_tender_competitor_fit` | no | yes: "Competitor fit" section (UI already built, TD:602-621) |
| `market_tender_fit_assessment` | no | yes: fit, rank, revenue estimate, rationale |
| `market_tender_portal` | no | yes: Source portals tile, Source column, registration/submission info |
| `market_tender_product_match` + `_line` | no | yes: "Matched products" (TD:575-593; needs a decision on the up/down arrow, no column) |
| `market_tender_requirement` | no | yes: requirements section |
| `market_tender_source` | no | yes: source chips and the CTA |
| `market_opportunity` | no | yes: project title/stage for Top opportunity (`market_top_opportunity_project` holds only the id) |
| `market_opportunity_fit_assessment` | no | optional (fit/revenue/rival detail for projects) |
| `market_opportunity_source` | no | optional (needed only if a project detail view is added) |
| `market_opportunity_update` | no | optional (same) |
| `market_top_opportunity_tender` | yes, partially (`rank_position` and `tender_id` join unused) | yes, fix mapping |
| `market_top_opportunity_project` | yes, partially (`buyer_name`, `rival_to_beat`, `rank_position` unused) | yes, fix mapping |
| `market_top_opportunity_metric` | no | yes: the four tiles on Top opportunity |
| `market_next_move` | yes, partially (`due_date`, `due_text`, `priority`, `sequence`, `status`, `tender_id`, `opportunity_id` unused) | yes |
| `market_category_summary` | no | yes: demand split / by-category counts and the tiles; only if counts are meant to be stored |
| `market_filter_option` | no | yes, if stored option lists are wanted (see 1.2 caveat on cross-facet counts) |
| `market_global_requirement` | yes (unread: `region`, `empty_state_message`, `status` not mapped) | yes |
| `market_global_requirement_source` | no | yes: Source section (GR:355-372 already reads `sources`) |
| `market_global_requirement_specification` | yes | keep; add `ORDER BY display_order` |
| `technology_category` | yes (`ui.` first, else serving) | keep; add `display_order`/`tab_number`; show `innovation_count` if wanted |
| `technology_category_ui_label` | no | yes: tab labels (`ui_name`, `short_label`) |
| `technology_innovation` | yes, partially (unread: `whats_new`, `background_what_it_is`, `horizon_year`, `action_note`, `assessment_outcome`, `sequence_no`, `external_id`, `list_secondary_value`, `pillar_id`; `maturity`/`list_description`/`summary` served but under wrong key names) | yes |
| `technology_innovation_status` | no | yes: `assessment_badge`, `position_label`, `maturity_label`, `horizon_text` |
| `technology_innovation_company` | no | yes: the real "Driven by" |
| `technology_innovation_source` + `technology_source` | no | yes: Sources row |
| `technology_innovation_analysis` | no | decide (overlaps the fixed narrative columns) |
| `technology_company` | no | only to resolve `technology_innovation_company.company_id` |
| `technology_metric`, `technology_pillar` | no | not on Innovations (Overview agent) |

### 4.2 `ui` tables (none is read by any page)

| Table | Would supply | Page |
|---|---|---|
| `market_pillar` | client name, pillar display name, search placeholder, print label | shell |
| `market_ui_navigation`, `market_view` | rail label/order/count, view title, empty text | all market pages |
| `market_metric` | metric label/subtext/unit/value | tiles |
| `market_tenders_view` | heading, filter labels, `active_tenders_count`, `markets_count`, `source_portals_count`, `value_disclosed_display`, `selected_tender_id`, sort label | Tenders + tiles |
| `market_tender_filter`, `market_filter` | filter labels/options/placeholder | Tenders, Market Intelligence |
| `market_tender_card` | `*_display` for every card field incl. `fit_grade_display`, `countdown_display` | Tenders list |
| `market_tender_assessment_view` | panel title/subtitle, section labels, `closing_summary`, `fit_grade_display`, `fit_rank_display`, `notice_ref_display`, `open_notice_label` | Tender detail |
| `market_intelligence_tab` | tab label, order, `record_count`, default filters | Market Intelligence |
| `market_top_opportunity_view` | heading, section labels and descriptions, 4 metric labels, `sort_logic_label` | Top opportunity |
| `market_top_opportunity_tender_row`, `_project_row` | rank + all `*_display` | Top opportunity |
| `market_next_move_view` | `action_display`, `due_display`, `tender_display`, `row_order` | Next moves |
| `market_global_requirement_view`, `_filter`, `_card`, `_detail`, `_view_state` | heading, filter/section labels, empty text, card `*_display`, detail labels | Global Requirements |
| `technology_ui_navigation`, `technology_ui_view` | heading, route_hash, view label, `rail_count` | Innovations |
| `technology_innovation_view` | `page_heading`, `list_heading`, `empty_state_text`, `total_innovations` | Innovations |
| `technology_innovation_category_tab`, `technology_category`, `technology_category_ui_label` | tab label, number, order, count | Innovations |
| `technology_innovation_card` | per-row `*_display` | Innovations list |
| `technology_innovation_detail_panel` | section texts + labels, `assessment_badge`, `close_label` | Innovations detail |
| `technology_metric`, `technology_pillar`, `technology_print_report_control` | tiles, pillar titles, print control | shell / Overview |

---

## 5. Fields with no column (decide: add column or keep hidden)

1. Awarded tender: awardee, award date, contract value (Awarded tab/route has nothing award-specific).
2. Match line direction (up/down arrow) on `market_tender_product_match_line`.
3. Tender product type (Land vs Air/Naval/Missiles) - no classification column.
4. Market category dimension table (names for `market_tender.category_id`, `market_category_summary.category_id`).
5. FX/crore conversion for a Value-disclosed total (only `value_amount` + `value_currency`; no rate table). Either show `ui.market_tenders_view.value_disclosed_display` or add a stored total.
6. Closing date for Global Requirements (only `deadline` varchar + `days_remaining` snapshot).
7. Destination for a pre-tender project row (no opportunity detail view reads `market_opportunity*`).
8. Cross-pillar "exposure / reinforced across pillars" strip on Innovations (computed from titles; no link table).
9. Vocabulary definitions for `status`, `lean_code`, `kssl_fit`, `url_kind`, `maturity`, `client_position`: schema does not fix them; the UI hard-codes different ones in different files.
