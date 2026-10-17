# KSSL port of the 137Parallax UI: field-by-field mapping

Produced by Task 1 of the Cummins UI port (analysis only, no code changed). Every later task reads this file.
Source app (read-only): `C:\Users\HARICHANDRA\Downloads\cummins-demo-clean\cummins-demo\frontend\src` ($C), its docs `UI_CONTRACT.md` s15 and s18 and `contract_shapes.json` ($CD), and `parallax-cummins-arabia-datapack/dataset.json` ($CP).
KSSL side: `backend/app.py`, `backend/areas/a_competitive.py`, `b_products.py`, `c_network.py`, `d_market_tech.py`, the live `/api/dataset` and `/api/manifest` (62 `ui` tables, 90 `serving` tables, re-read after v2 commit 5fa86e1 added four text columns to `competitive_competitor`; the ui-port branch must merge v2 before the backend task).

## How to read this file

Rules in force (from `context.md`): nothing hardcoded, default or fabricated; every value on screen traces to a DB column through `/api/dataset`; browser math is limited to counts, sorts, filters, sums, date windows, spec comparison of stored specs, graph layout and sentences that only join dataset values.

`disposition` in section A:

| value | meaning |
|---|---|
| `existing` | a KSSL column already holds the value; the backend only renames or reshapes it |
| `derived-ok` | the value is allowed math or a join over existing columns (in the backend or the browser) |
| `new-table` | the value is a judgement, estimate or content with no KSSL column; section C adds it (a new table or a new column on an existing table) |
| `not-shipped` | accepted by ruling R3: the UI reads the field but treats its absence as normal (optional enrichment, pipeline artefact, or unread); no column, no table, the backend omits it and the UI shows its existing empty state |
| `remove-genset` | the logic or wording is genset / kVA / data-centre / AED / SAR / Saudi / Gulf or Cummins-market specific; removed, not ported |
| `hidden:<key>` | kept in code, gated by `ui.section_visibility` (missing key = hidden): gap-analysis, finances, stock, parallax-read, swot, strategic-positioning, product-images, chat |

`read by` uses base file names (all JS/JSX base names under `$C/src` are unique). Dataset column names are written `schema.table.column`; `serving.*` has the same table under `staging.*` in the review copy (`KSSL_VIEW=review`).

Controller rulings R3 to R9 are copied in section F and are already applied to every row of A to E. Label lookups: there is no extra label global; the UI reads `data.database.ui.<table>` / `data.database.serving.<table>` (already shipped by `/api/dataset`) through one helper `uiText(data, 'ui.<table>', {keyColumn: keyValue}, 'labelColumn')`; a missing row or empty cell renders the em dash, never a literal.

## A. Dataset globals

One row per field the Cummins frontend reads (or, for globals Cummins ships and nobody reads, one row saying so). Grouped by global.

### client

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| client | id | overview.js, profile.js, partners.js, search.js, shortlist.js, Geo.jsx, Partnerships.jsx, Products.jsx, dataset.js, geo.js, marketOutlook.js, tenderIntel.js | existing | serving.client_account.client_id (dataset.js re-resolves it from the competitors row with dir='client'; every literal fallback `\|\| "Cummins Arabia"` is deleted) |
| client | name | dataset.js (adaptPatents), TopBar.jsx, Tenders.jsx, Overview.jsx, DataProvider.jsx | existing | serving.client_account.client_name (backend today: first non-empty of client_name, legal_name, brand_name) |
| client | short | TopBar.jsx, Overview.jsx, SignalCard.jsx, DetailPanel.jsx, MatchupList.jsx, MatchupDossier.jsx, Positioning.jsx, Patents.jsx, Innovation.jsx, Tenders.jsx, TenderCockpit.jsx, MarketOutlook.jsx, GeoMap.jsx | existing | serving.client_account.brand_name (backend today: first non-empty of brand_name, client_name). Missing value renders the em dash, never a literal |
| client | brand, sector, website, locale, currency, magnitude | (never read; UI_CONTRACT s17) | not-shipped | no reader; do not ship |

### competitors  (dict cid -> company row; the client also appears as one row with dir='client')

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| competitors | (key) cid | everywhere | existing | serving.competitive_competitor.competitor_id (client row key = serving.client_account.client_id) |
| competitors | name | Profile.jsx, Products.jsx, Partnerships.jsx, Patents.jsx, ThreatAnalysis.jsx, search.js, shortlist.js, dedupeCompanies.js, profile.js | existing | serving.competitive_competitor.display_name (client row: client_account.client_name) |
| competitors | short | (no reader of competitors[x].short; client.short is the only reader of a short name) | not-shipped | - |
| competitors | legal (full legal name) | companyNames.js (competitorFullName, detailLine, listLine), Profile.jsx, Projects.jsx, ThreatAnalysis.jsx | existing | serving.competitive_competitor.legal_name. Replaces the hardcoded COMPANY_NAMES map (section B). Empty = show display_name |
| competitors | dir ('client' marks the client row) | dataset.js, roster.js, overview.js, partners.js, shortlist.js | derived-ok | backend sets dir='client' on the client_account row only; rivals carry no dir |
| competitors | sector | Profile.jsx, Products.jsx, Partnerships.jsx, profile.js, search.js, partners.js | existing | serving.competitive_competitor.industry_sector. The formatSectorName() fallback "Defence & Aerospace" is removed (empty renders the em dash) |
| competitors | hq | Profile.jsx, profile.js, countryFacet.js, search.js, shortlist.js, geo.js, GeoMap.jsx | existing | serving.competitive_competitor.headquarters |
| competitors | country (country of origin: Profile origin filter, Products, GeoMap) | countryFacet.js (companyOrigin), Profile.jsx, shortlist.js, GeoMap.jsx | existing | serving.competitive_competitor.origin_country |
| competitors | (client row) hq, country, sector, strategic_positioning | Profile.jsx, Products.jsx, Geo.jsx (the client appears in the same dict) | existing | for the row with dir='client' the sources are serving.client_account.headquarters, country, industry_sector, strategic_positioning (competitive_competitor has no row for the client) |
| competitors | threat (drives the coloured dot) | Profile.jsx, Products.jsx, ThreatAnalysis.jsx, Projects.jsx, geo.js, overview.js | existing | serving.competitive_competitor.threat_level, shipped as stored (threat / watch / fav). Ruling R7: the UI adopts the stored words; every comparison `=== "high"` / `=== "low"` is re-keyed to threat / fav |
| competitors | assess (analyst read of the rival) | Profile.jsx, profile.js, Partnerships.jsx, partners.js (compReportHtml) | hidden:parallax-read | serving.competitive_competitor.parallax_read |
| competitors | strategic_positioning | Profile.jsx, profile.js | hidden:strategic-positioning | serving.competitive_competitor.strategic_positioning. The invented fallback paragraph in Profile.jsx ("is actively scaling indigenous manufacturing...") is deleted |
| competitors | strengths[], weaknesses[] | Profile.jsx (swList) | hidden:swot | serving.competitive_competitor_swot.statement where swot_type is the strength / weakness type |
| competitors | starting_year | Profile.jsx, profile.js | existing | serving.competitive_competitor.starting_year_text (verbatim text, qualifiers kept), else the number serving.competitive_competitor.starting_year. Columns added on v2 by commit 5fa86e1 (db/setup/08); the ui-port branch must merge v2 first |
| competitors | company_size | Profile.jsx, profile.js | existing | serving.competitive_competitor.employee_count_text (verbatim), else the number employee_count (v2 5fa86e1) |
| competitors | sales ({value,detail}[] or {text,fy}) | Profile.jsx (firstFigure), profile.js, revenueFacet.js | existing | {text: serving.competitive_competitor.revenue_text, fy: financial_year} (v2 5fa86e1); only when revenue_text is empty, {text: annual_revenue + ' ' + revenue_currency} (a join of stored values) |
| competitors | revenue_filter (revenue tier key) | revenueFacet.js (revenueTierOf), Profile.jsx, Products.jsx | existing | serving.competitive_competitor.revenue_tier (stored word shown as is; the INR-crore thresholds in revenueFacet.js are removed, section B) |
| competitors | global_locations (string[] or {value,name}[]) | Profile.jsx, profile.js, countryFacet.js | existing | serving.competitive_competitor_location.location_name (one entry per row for the competitor_id) |
| competitors | leadership[].value | Profile.jsx, profile.js (sourcedRows) | existing | serving.competitive_leader.full_name |
| competitors | leadership[].detail (role) | Profile.jsx | existing | serving.competitive_leader.role_title |
| competitors | leadership[].url | Profile.jsx, profile.js | existing | serving.competitive_leader.role_source_url |
| competitors | leadership[].full_name | Profile.jsx | existing | serving.competitive_leader.full_name |
| competitors | leadership[].line (verbatim source line; sourcedRows drops rows without it) | profile.js (sourcedRows) | not-shipped | no KSSL column. The port must relax sourcedRows to `value && url` (ruling R6) |
| competitors | leadership[].photo, .photo_source, .bio_source | Profile.jsx (PersonAvatar, LeaderPage) | not-shipped | no photo column; avatar falls back to initials (derived-ok from serving.competitive_leader.avatar_initials). Local photo files in public/local-photos are not ported (section B) |
| competitors | leadership[].experience[] {company, role, from, to} | Profile.jsx (LeaderPage) | existing | serving.competitive_leader_record where record_type='experience': institution_or_employer, role_or_degree, start_date, end_date (a free-text headline line is shipped as text when role/org are not split) |
| competitors | leadership[].education[] {institution, degree, from, to} | Profile.jsx (LeaderPage) | existing | serving.competitive_leader_record where record_type='education': institution_or_employer, role_or_degree, start_date, end_date |
| competitors | support_leadership, facilities, updates, threatNote, center, site, srcs | profile.js (counts / unused fields), partners.js (srcs, center fallbacks), dedupeCompanies.js (site) | not-shipped | no KSSL column and nothing displayed depends on them (profile.js only counts them; dedupe-by-site goes with dedupeCompanies.js) |
| competitors | ticker | Profile.jsx, mockStockHistory.js, pulseFetch.js, tickers.js | hidden:stock | serving.competitive_stock_quote.ticker |
| competitors | products[] | Products.jsx, search.js, tenderIntel.js, geo.js, profile.js, dedupeCompanies.js | derived-ok | next block |
| competitors | partners[] | Partnerships.jsx, partners.js, overlap.js, overview.js, profile.js | derived-ok | partner block below |
| compOrder | (ordered cid list) | profile.js (rosterOf), Partnerships.jsx, Patents.jsx, Products.jsx, dataset.js, roster.js (sortCompaniesByName) | derived-ok | competitor_id list from serving.competitive_competitor, sorted by display_name in the browser (clients first); the roster.js whitelist is deleted (section B) |

### competitors[cid].products[]  (the client row carries its own catalogue, today client_product)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| products | id | Products.jsx | existing | serving.competitive_product.product_id / serving.client_product.client_product_id |
| products | name | Products.jsx, search.js, productLink.js | existing | serving.competitive_product.product_name / serving.client_product.product_name |
| products | category | Products.jsx, search.js | existing | serving.competitive_product.category / serving.client_product.category |
| products | country | Positioning.jsx (compareProducts), Products.jsx | existing | serving.competitive_product.country |
| products | specs (object label -> value string) | Products.jsx, specs.js, tenderIntel.js | derived-ok | serving.competitive_product_specification (spec_label -> spec_value + unit) / serving.client_product_specification (spec_name -> value_text or value_numeric + unit). The hardcoded fallback getResolvedSpecs() is deleted (section B) |
| products | source, source_url, sources[], tier | Products.jsx | existing | serving.competitive_product_specification.source_url, source_count / serving.client_product_source (source_label, source_url, source_type) |
| products | programs[] {title, authority, status, statusColor, date, description} | Products.jsx (after getProductPrograms() is deleted) | existing | serving.competitive_product_program (program_title, authority, status, status_color, program_date, description) / serving.client_product_program (program_name, owner, status, start_date, description) |
| products | news (productNews) | Products.jsx via news.js | derived-ok | serving.competitive_product_news (headline, article_url, published_date, publisher, category, comparison_reason) |
| products | matchupId | Products.jsx | existing | serving.competitive_matchup.matchup_id joined on competitor_product_id / client_product_id |
| products | image, imageSource | Products.jsx, Thumb.jsx | hidden:product-images | serving.client_product.image_url / serving.competitive_product.image_url |
| products | incomplete, band, hz, kva, series ("Genset"), specs["Data centre rating"], specs["Standby rating"/"Prime rating"/"Cylinders"/...] | Products.jsx (cardSpecs, line 1852-1866), tenderIntel.js, marketOutlook.js, geo.js | remove-genset | genset rating-band logic; the card spec strip is rebuilt from the first N dataset specs |

### competitors[cid].partners[]  (rival partnership ties)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| partners | id | partners.js, Partnerships.jsx | existing | serving.competitive_partnership.relationship_id |
| partners | label | partners.js, Partnerships.jsx, overlap.js, search.js | existing | serving.competitive_partnership.partner_name |
| partners | ptype | partners.js, Partnerships.jsx | existing | serving.competitive_partnership.partner_type |
| partners | rel (category key: dist, dealer, jv, tech, ...) | partnerCategories.js, partners.js, dataset.js | derived-ok | slug of serving.competitive_partnership.partner_type, looked up in the new ui.partner_category (section C) |
| partners | kind ('Foreign OEM' etc.; used for clustering and a "Foreign-IP" stat) | partners.js, Partnerships.jsx | not-shipped | no column; the keyword clustering by kind/label regex is removed (a judgement); grouping uses rel |
| partners | sig (significance) | partners.js, search.js | not-shipped | no column; ordering falls back to stored order |
| partners | note | partners.js | existing | serving.competitive_partnership.description |
| partners | date, as_of | partners.js (statusTag, asOfYear) | existing | serving.competitive_partnership.as_of_date |
| partners | country | partners.js (pgRegionsOf), Partnerships.jsx | existing | serving.competitive_partnership.region. The DEFENSE_FIRM_COUNTRIES regex guess in partners.js is removed (section B) |
| partners | confidence | partners.js (confTag), Partnerships.jsx | existing | serving.competitive_partnership.relationship_confidence |
| partners | status, ended ('active'/'ended'/'announced'/'exploring') | partners.js (statusTag), Partnerships.jsx | not-shipped | no competitor-side status column (client_partner.relationship_status exists only for the client) |
| partners | deal | partners.js, Partnerships.jsx | not-shipped | no column; shown only when present |
| partners | insight ("[CORE]/[ADJACENT]" marker plus text) | partners.js (pgRowRank, closenessOf), Partnerships.jsx | not-shipped | no column; the bracket-marker convention is a Cummins pipeline artifact |
| partners | verdict, impact (the tie's read for the client; replaces `mean`) | partners.js, partnerCategories.js (verdictOf, impactText) | new-table | new columns serving.competitive_partnership.client_verdict and client_impact (section C2), shipped as two fields exactly as stored. Only a stored threat or watch verdict renders (a pill with the stored stance word); any other stored verdict (ruling R22) draws no verdict |
| partners | src (url) | partners.js (pgEvidence) | derived-ok | serving.competitive_partnership_evidence.source_url (first row by card_number) |
| partners | srcnote | Partnerships.jsx | existing | serving.competitive_partnership.source_note |
| partners | cid (partner is itself a tracked company) | partners.js, dataset.js, overlap.js | derived-ok | serving.competitive_partnership.partner_id when it equals a competitive_competitor.competitor_id |
| partners | koel / shared / sharedWith (also a partner of the client) | partners.js, overlap.js, dataset.js, Partnerships.jsx | derived-ok | label match against KSSL_PARTNERS (overlap.js markOverlaps): a deterministic join, kept. Stored flag also available: serving.client_partner_relationship.competitor_overlap |
| partners | image | partners.js (tie drawer) | not-shipped | no column |
| partners | evidence[], detail (KSSL-only evidence cards and relationship detail) | (no Cummins reader) | not-shipped | serving.competitive_partnership_evidence and ..._relationship_detail have no Cummins reader; not re-applied (ruling R8); the data stays in the tables |

### competitorNews  (dict cid -> articles, newest first)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| competitorNews | id | news.js, ThreatAnalysis.jsx | existing | serving.competitive_news_article.article_id (moment rows: competitive_competitor_moment.moment_id) |
| competitorNews | title | news.js, Profile.jsx, ThreatAnalysis.jsx | existing | serving.competitive_news_article.headline (moment rows: competitive_competitor_moment.title) |
| competitorNews | description (excerpt) | news.js, ThreatAnalysis.jsx, Profile.jsx | new-table | new column serving.competitive_news_article.description (C2); moment rows: competitive_competitor_moment.what_happened |
| competitorNews | source (publisher) | news.js, Profile.jsx, ThreatAnalysis.jsx | existing | serving.competitive_news_article.publisher (moment: source_label, else source_domain) |
| competitorNews | date | news.js, Profile.jsx, ThreatAnalysis.jsx | existing | serving.competitive_news_article.published_date (moment: movement_date) |
| competitorNews | category | news.js, Profile.jsx, ThreatAnalysis.jsx | existing | serving.competitive_news_article.category (moment: category) |
| competitorNews | url | news.js, Profile.jsx, ThreatAnalysis.jsx | existing | serving.competitive_news_article.article_url (moment: source_url) |
| competitorNews | image | news.js, Thumb.jsx | existing | serving.competitive_news_article.image_url (moment: image_url). FALLBACK_NEWS_IMAGES in Profile.jsx is deleted |
| competitorNews | story_key, continues_url, duplicate_of_url | news.js (collapseThreads) | not-shipped | no columns; threads simply do not collapse |
| competitorNews | is_trending | (not read) | not-shipped | - |
| competitorNews | level (Moment page filter and tag) | ThreatAnalysis.jsx | existing | serving.competitive_competitor_moment.grade, shipped as the stored level_code (ui.competitive_competitor_moment_level.level_code, e.g. high / watch / opportunity; ruling R7). Only moment rows carry it; ruling R4: the Moment page keeps only competitorNews rows that have a level, plain news rows stay in Profile and Products. Code comparisons against THREAT / WATCH / FAV are re-keyed to the stored codes |
| competitorNews | analysis (text before "Action:") | ThreatAnalysis.jsx | existing | serving.competitive_competitor_moment.kssl_analysis |
| competitorNews | country | ThreatAnalysis.jsx (countryFact) | existing | serving.competitive_competitor_moment.country_name |
| competitorNews | card (id used for the lenses and the SIGNAL_COUNTRY lookup) | ThreatAnalysis.jsx | derived-ok | serving.competitive_competitor_moment.moment_id; the SIGNAL_COUNTRY table is deleted (section B) |
| competitorNews | lenses [{view,text}] (was NEWS_LENSES[card]) | ThreatAnalysis.jsx | existing | serving.competitive_competitor_moment_analysis (view_name, analysis_text, display_order) keyed by moment_id. Replaces newsLenses.js (section B) |

### competitorMetrics, competitorStructure, competitorMoment, productFacets  (shipped by one side only)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| competitorMetrics | mentions_window and all other fields | Profile.jsx (assigned to a variable, never rendered) | not-shipped | no reader renders it |
| competitorStructure | all fields | (no reader) | not-shipped | - |
| competitorMoment | items, competitors, timeWindows, levels | (no Cummins reader; ThreatAnalysis reads competitorNews) | not-shipped | KSSL-only global today. Its rows feed competitorNews (above) instead (ruling R4) |
| productFacets | country, revenueTier per competitor | (no Cummins reader; Profile and Products filter off competitors[].country and revenue_filter) | not-shipped | KSSL-only global; superseded by competitors.country and competitors.revenue_filter |

### overviewConfig  (3 lanes: competitive, market, technology; dataset.js rebuilds cards, titles and tile defs at wire time)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| overviewConfig | <lane>.title | Layout.jsx, Overview.jsx, dataset.js | existing | labels live in section E: ui.competitive_navigation.view_label, ui.market_top_opportunity_view.page_heading, ui.technology_overview_view.page_heading. dataset.js literals "Top opportunity" and "Technology Knowledge" are deleted |
| overviewConfig | <lane>.cnt (count-line template) | Layout.jsx, dataset.js, overview.js (viewMetaFor) | derived-ok | count words come from E; the sentence "latest tenders that fit Cummins Arabia + perceived opportunities to act on" and the technology equivalent are marketing copy and are deleted (count + label only) |
| overviewConfig | <lane>.metrics[] {l, v, unit, sub, act, dot, delta, src, warn} | MetricsStrip.jsx, overview.js (metricsFor), dataset.js | derived-ok | tile LABELS: section E (ui.*_metric.metric_label, ui.market_top_opportunity_view.*_metric_label); VALUES are counts/sums over cards and tenders (allowed math). `sub` warning sentences ("no served threat signal is assigned...") are chrome honest-empty text |
| overviewConfig | <lane>.groups[] {n, h, s, dirs, tags} | overview.js (buildFeed), dataset.js | derived-ok | group heading text: section E; membership by dir/tag is allowed filtering. Hardcoded group headings in dataset.js ("Competitor Advancements", "Adoptable Advances", "Latest Tenders", "Perceived Opportunities", and straplines) are deleted or moved to E |
| overviewConfig | <lane>.filters[] {f, l, c, tag, dirs} | FeedFilters.jsx, overview.js (filterMatch), dataset.js | derived-ok | pill labels: section E (ui.technology_overview_filter, ui.market_filter); filters are by dir/tag |
| overviewConfig | <lane>.dirWord, badgeClass, tagWord, hideFilterButtons | Overview.jsx, dataset.js | derived-ok | presentation maps ({threat:'Threat', watch:'Watch'} words): E. The literals "TENDER" / "OPPORTUNITY" / "Advancement" / "Adoptable" are replaced by ui.* labels (E) |
| overviewConfig | <lane>.cards (built from the lane cards) | Layout.jsx, Overview.jsx, overview.js | derived-ok | recomputed in the browser from competitiveCards / marketCards / techCards |
| overviewConfig | <lane>.shortlist, overviewShortlist (qualified/demoted counts) | dataset.js, shortlist.js | not-shipped | removed: overviewShortlist keeps only cards with card.impact==='direct' and severity high/medium inside a hardcoded client footprint (shortlist.js, footprint.js TIERS); it is a judgement, not allowed math. Ruling R5: the feed shows the stored cards ordered by stored sequence |
| overviewMetrics | all (empty lists in the reference data) | (never read) | not-shipped | - |

### *Cards = competitiveCards / techCards / marketCards  (feed cards; the three lanes share the shape)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| *Cards | id | SignalCard.jsx, Overview.jsx, dataset.js, search.js | existing | serving.competitive_signal.signal_id / serving.technology_overview_article.article_id |
| *Cards | dir (threat, watch, fav) | SignalCard.jsx, overview.js (compareCards, filterMatch), FeedFilters.jsx | derived-ok | lower(serving.competitive_signal.classification) / lower(serving.technology_overview_article.direction). threat.js refineThreat() (regex re-grading of dir and severity) is deleted |
| *Cards | rank | SignalCard.jsx, overview.js | derived-ok | re-ranked in the browser after sort; the stored order is serving.competitive_signal.sequence_no / technology_overview_article.sequence_no |
| *Cards | title | SignalCard.jsx, dataset.js, search.js | existing | serving.competitive_signal.title / serving.technology_overview_article.title |
| *Cards | uiTitle | SignalCard.jsx, dataset.js | not-shipped | no column (display title = title) |
| *Cards | meta | overview.js (category sort), globalRequirements.js, marketOutlook.js (cardMeta), search.js | existing | serving.competitive_signal.category / technology_overview_article.category_text. Market lane: joined string, see marketCards below |
| *Cards | company | SignalCard.jsx, profile.js, search.js, shortlist.js | existing | serving.competitive_signal.company_id -> competitive_competitor.display_name / technology_overview_article.primary_company_id -> technology_company.display_name |
| *Cards | competitor (rival name; present only for competitor-advance tech cards) | overview.js (isRivalCard), shortlist.js | derived-ok | set from technology_overview_article.classification = 'competitor_advance' (name = primary company); adoptable cards carry none |
| *Cards | lens | overview.js (lensSet), threat.js | existing | serving.technology_overview_article.lens (competitive lane: not-shipped) |
| *Cards | sowhat | SignalCard.jsx, Overview.jsx (search), search.js | existing | serving.competitive_signal.summary / technology_overview_article.card_summary |
| *Cards | ksslImpact, ksslImpactKind | SignalCard.jsx, DetailPanel.jsx, dataset.js | existing | serving.competitive_signal_detail.why_it_matters (kind derived from classification: threat / rival-advance / tech-advance). The retired-kind rule in the Cummins backend is not needed |
| *Cards | ago (date) | SignalCard.jsx, overview.js (dateVal), dataset.js | existing | serving.competitive_signal.event_date / technology_overview_article.published_on (else article_date). urlDate() upgrade from a permalink stays (deterministic) |
| *Cards | tags | overview.js (cardHasTag), search.js, dataset.js | derived-ok | serving.competitive_signal.category; technologyAttention() appends 'rival' or 'adopt' (allowed tagging by classification) |
| *Cards | sec[] | overview.js (depth sort + tie-break), threat.js | not-shipped | no column; depth sort is already off the menu |
| *Cards | url | dataset.js, news.js (detail index), shortlist.js | existing | serving.competitive_signal_detail.source_url |
| *Cards | image | Thumb.jsx, news.js | existing | serving.competitive_signal.thumbnail_url / technology_overview_article.image_url |
| *Cards | severity, severityRank, impact, threatWhy | overview.js (compareCards), shortlist.js, threat.js, Overview.jsx (report payload) | not-shipped | Cummins threat_gate output; no KSSL column (ruling R5). compareCards orders by direction, then date, then stored sequence_no; the 'severity not assessed' label is not rendered |
| *Cards | summary, glance | dataset.js (copies onto details), DetailPanel.jsx | derived-ok | glance = details.facts (below) |
| *Cards | kind, match | SignalCard.jsx, DetailPanel.jsx, dataset.js (tender cards) | derived-ok | tender cards are synthesised from tenders in dataset.js (kept); kind is the 'rival'/'adopt' tag |

### marketCards  (market lane: tender cards synthesised in dataset.js + global-requirement and pipeline signals)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| marketCards | global-requirement cards (isGlobalCard = meta contains "Global") | globalRequirements.js, Layout.jsx, Overview.jsx, marketOutlook.js | derived-ok | one card per serving.market_global_requirement row: id=requirement_id, title=title, meta joins [category, region, deadline/date] with ' · ' (region value carries the "Global" token from the dataset, not a literal), sowhat=strategic_assessment, ago=deadline |
| marketCards | pipeline / demand signals ("Pipeline · country · segment · date") | marketOutlook.js (cardMeta, drivers, segments) | derived-ok | serving.market_opportunity_update joined on opportunity_id to serving.market_opportunity: meta joins [update_type, location_text, category, update_date] with ' · '; title=headline; sowhat=narrative (ruling R6) |
| marketCards | tender cards ("Tender · ... closes ...") | dataset.js (tenderCards), overview.js | derived-ok | built in the browser from tenders (kept as allowed math; wording "Strong fit" / "Worth qualifying" comes from market_tender.lean_text, not a literal) |

### details  (dict card id -> panel)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| details | rank ("LATEST TENDER · 01" label) | dataset.js (tender details) | derived-ok | label word is chrome (E), the number is the position |
| details | dir | DetailPanel.jsx | derived-ok | lower(classification / direction) |
| details | title | DetailPanel.jsx, dataset.js | existing | serving.competitive_signal_detail.drawer_title / technology_overview_article.title |
| details | facts [[label, value, quote]] | DetailPanel.jsx, overview.js (signalDate), signalCountry.js, Projects.jsx, chat.js | existing | serving.competitive_signal_evidence (evidence_group='fact': label, value, quote) / serving.technology_overview_fact (ui_label, fact_value, proof_text) |
| details | glance [[k,v]] (Cummins-only enrichment) | DetailPanel.jsx | derived-ok | = facts; no separate column |
| details | what | DetailPanel.jsx, globalRequirements.js, news.js | existing | serving.competitive_signal_detail.what_article_says / technology_overview_article.article_says |
| details | why | globalRequirements.js, news.js, chat.js | existing | serving.competitive_signal_detail.why_it_matters / technology_overview_article.client_narrative |
| details | summary | DetailPanel.jsx | not-shipped | no separate column; `what` is shown |
| details | lens (statement rows -> "Key points" bullets via articleBullets) | DetailPanel.jsx, detail.js | derived-ok | serving.competitive_signal_evidence (evidence_group='key_point': value) / serving.technology_overview_key_point.point_text, reshaped to rows |
| details | url | DetailPanel.jsx, globalRequirements.js | existing | serving.competitive_signal_detail.source_url |
| details | srcs [{label,url}] | DetailPanel.jsx, html.js (srcChips), globalRequirements.js | existing | serving.competitive_signal_detail.source_name + source_url, plus evidence rows (evidence_group='source') / serving.technology_overview_source -> technology_source (label, source_url) |
| details | provenance | DetailPanel.jsx | existing | serving.competitive_signal_detail.provenance / technology_overview_source.provenance_status |
| details | image | DetailPanel.jsx | existing | serving.competitive_signal.thumbnail_url / technology_overview_article.image_url |
| details | ksslImpact, ksslImpactKind | DetailPanel.jsx | existing | serving.competitive_signal_detail.why_it_matters; eyebrow text from serving.competitive_signal_detail.impact_eyebrow replaces the hardcoded map {threat:"Threat to Cummins Arabia", ...} in DetailPanel.jsx (E) |
| details | suggest[] | DetailPanel.jsx -> AskBox.jsx | hidden:chat | serving.competitive_signal_detail.ask_box_query |
| details | kind, match (tender detail) | DetailPanel.jsx, dataset.js | derived-ok | tender details are synthesised from tenders |
| details | actions, pursue, uiTitle | (dataset.js sets actions: [] ; DetailPanel does not read them) | not-shipped | - |

### matchups  (dict id -> pair)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| matchups | (key) id | Positioning.jsx, MatchupList.jsx | existing | serving.competitive_matchup.matchup_id |
| matchups | cat | MatchupList.jsx, MatchupDossier.jsx, Tenders.jsx, reports.js, gapModel.js | existing | serving.competitive_matchup.category_code |
| matchups | catKey | geo.js | derived-ok | slug(category_code); POS_CATS/CAT_KEY below |
| matchups | comp ("Maker · Product") | MatchupList.jsx (splitComp), MatchupDossier.jsx, Positioning.jsx, search.js | derived-ok | competitor_name + ' · ' + competitor_product_name (serving.competitive_matchup) |
| matchups | compBy (maker) | MatchupList.jsx, profile.js, news.js | existing | serving.competitive_matchup.competitor_name |
| matchups | bf / anchor (client product) | MatchupList.jsx, MatchupDossier.jsx, Positioning.jsx, compareProducts.js | existing | serving.competitive_matchup.client_product_name |
| matchups | country | MatchupList.jsx, compareProducts.js, countryFacet.js | existing | serving.competitive_matchup.competitor_country |
| matchups | global (prime benchmark flag) | MatchupList.jsx, MatchupDossier.jsx | not-shipped | no column |
| matchups | reason (why the pair was matched) | dataset.js (pairingReason), shortlist-neutral, Products.jsx | existing | serving.competitive_matchup.match_basis |
| matchups | verdict, verdictH | MatchupDossier.jsx, Positioning.jsx | existing | serving.competitive_matchup.verdict, verdict_headline |
| matchups | edge (0-100; 50 = parity) | MatchupDossier.jsx, specs.js, Positioning.jsx, reports.js | existing | serving.competitive_matchup.edge_score. dataset.js overwrites it with computeSpecEdge(); the port keeps the stored score and only a generic dead-band comparison (ruling R6) |
| matchups | specDims, specDecided | MatchupDossier.jsx, Positioning.jsx | existing | serving.competitive_matchup.comparable_spec_count (sourced_spec_count) |
| matchups | specs[].l | specs.js, edge.js, MatchupDossier.jsx, compareProducts.js | existing | serving.competitive_matchup_specification.spec_label |
| matchups | specs[].cv / kv (value text) | specs.js, MatchupDossier.jsx | existing | competitor_value_text or competitor_value_numeric / client_value_text or client_value_numeric |
| matchups | specs[].cn / kn (numeric) | edge.js, specs.js, compareProducts.js | existing | competitor_value_numeric / client_value_numeric |
| matchups | specs[].u | specs.js | existing | serving.competitive_matchup_specification.unit |
| matchups | specs[].hi (higher is better) | edge.js, specs.js, compareProducts.js | derived-ok | from better_side and the two numerics: true if better_side='client' and kn>cn (or competitor and cn>kn); false if the opposite; null when equal or unjudged |
| matchups | specs[].p, cp, kp (provenance 's') | specs.js | not-shipped | no column; source dots omitted |
| matchups | specs[].group, win, gap, state | (KSSL v2 only) | existing | spec_group, better_side, gap_value, comparability_state - kept on the row for the edge-basis and parity chips |
| matchups | advBf[] / advComp[] | MatchupDossier.jsx, reports.js | existing | serving.competitive_matchup_advantage.advantage_text where side='client' / 'competitor' |
| matchups | advBfQ / advCompQ (qualitative) | MatchupDossier.jsx | not-shipped | no separate qualitative list; all advantages ship in advBf/advComp |
| matchups | det, srcs, news_image, product_news, gen, ks_thin, bfBy, revenue_filter | reports.js (det "Provenance"), (rest unread or optional) | not-shipped | serving.competitive_matchup_source is available as srcs [{label,url}] if the dossier shows sources (SHOW_POSITIONING_SOURCES is false) |
| matchups | _cp (rival product id) | geo.js (pairOfProduct) | remove-genset | used only by the geo kVA compare popup |
| matchups | gap strip (matchupGapHtml, gapModel) | MatchupDossier.jsx, specs.js, Tenders.jsx, Innovation.jsx | hidden:gap-analysis | derived model; not shipped |
| POS_CATS | [key,label][] | MatchupList.jsx, geo.js | derived-ok | distinct serving.competitive_matchup.category_code, sorted (backend today) |
| CAT_KEY | label -> key | MatchupList.jsx | derived-ok | same |

### tenders

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| tenders | id | Tenders.jsx, TenderCockpit.jsx, overview.js, search.js | existing | serving.market_tender.tender_id |
| tenders | title | Tenders.jsx, tenderRow.js, search.js | existing | serving.market_tender.title (title_localized when empty) |
| tenders | issuer | Tenders.jsx, tenderRow.js, marketOutlook.js | existing | serving.market_tender.issuer_display (else buyer_name) |
| tenders | country | Tenders.jsx, MarketOverview.jsx, marketOverview.js | existing | serving.market_tender.country_name |
| tenders | cat | Tenders.jsx, marketOverview.js, marketOutlook.js, reports.js | existing | serving.market_tender.category_text |
| tenders | value | Tenders.jsx, MarketOverview.jsx, gapModel.js (parseCr) | existing | serving.market_tender.value_text for display; value_amount + value_currency for sums. Ruling R9: no FX anywhere. parseCr / CR_PER_MILLION in gapModel.js are deleted; value tiles show one total per stored currency (e.g. 'USD 1.2 bn · EUR 9 m'), and a tender without value_amount is counted only in the 'N of M publish an amount' sub-line |
| tenders | qty | tenderRow.js, Tenders.jsx | derived-ok | quantity + ' ' + quantity_unit |
| tenders | deadline and closingDate (both served as the ISO closing date; the wire recomputes dl/deadline/timing) | tenderCalc.js, tenderRow.js, Tenders.jsx | existing | serving.market_tender.closing_date (NOT deadline_text) in BOTH fields: wireTendersWithRealDays sets closingDate = served deadline and then replaces deadline with "N days left", so a tender served without deadline loses its closing date |
| tenders | closingDate | MarketOverview.jsx, overview.js, tenderRow.js | derived-ok | = closing_date (set by wireTendersWithRealDays) |
| tenders | dl, timing, statusClass, isLive | tenderCalc.js, Tenders.jsx, overview.js (bucketTenders) | derived-ok | recomputed from closing_date (date window math). Stored days_remaining / is_live are advisory |
| tenders | posted | tenderRow.js, dataset.js | existing | serving.market_tender.published_date |
| tenders | status (open, awarded, closed, ...) | overview.js (bucketTenders), Tenders.jsx | existing | serving.market_tender.status |
| tenders | urlKind (notice, portal, award) | Tenders.jsx, overview.js | existing | serving.market_tender.url_kind |
| tenders | url | Tenders.jsx, MarketOverview.jsx, dataset.js | existing | serving.market_tender.source_url |
| tenders | srcs [{label,url}] | Tenders.jsx, marketOverview.js (portalRows), html.js | existing | serving.market_tender_source (portal_name or publisher, source_url, is_primary first) |
| tenders | desc | Tenders.jsx, dataset.js | existing | serving.market_tender.description |
| tenders | summary, gist | dataset.js (tender cards) | derived-ok | summary = description; gist falls to tenderGist() (join of title, category, country: allowed). Cummins LLM text columns are not needed |
| tenders | reqNote | Tenders.jsx, dataset.js | not-shipped | no column; `desc` is shown instead |
| tenders | req [[label, value]] | Tenders.jsx, tenderRow.js, marketOutlook.js, tenderIntel.js | derived-ok | flatten serving.market_tender_requirement into label/value rows (backend today builds requirements[].rows) plus ['Published', published_date] and ['Closes', closing_date] |
| tenders | matches [{n, fit, pct, lines [[dir, html]]}] | Tenders.jsx, DetailPanel.jsx, SignalCard.jsx, reports.js | existing | serving.market_tender_product_match (match_label -> n, fit_grade -> fit, fit_percent -> pct as 'NN%') and market_tender_product_match_line (line_label = 'up'/'down', line_value). Loader convention for line_label must be 'up'/'down' |
| tenders | rank | Tenders.jsx, overview.js (counts) | existing | serving.market_tender.rank_position |
| tenders | fit (verdict word) | Tenders.jsx | existing | serving.market_tender.kssl_fit, shipped as stored: strong / partial / weak (ruling R7; Cummins strong/partial/poor is not translated) |
| tenders | clientFit (was cumminsFit: strong, partial, weak) | TenderCockpit.jsx, overview.js, marketOutlook.js | existing | serving.market_tender.kssl_fit (or market_tender_fit_assessment.kssl_fit); ruling R7: the field is renamed clientFit everywhere in the port and the stored words strong / partial / weak are compared as they are |
| tenders | revenueEstimate / expectedRevenue | Tenders.jsx | existing | serving.market_tender.expected_revenue_text (else market_tender_fit_assessment.revenue_estimate_text) |
| tenders | revenueMid (number, estimate midpoint) | marketOutlook.js, tenderIntel.js | derived-ok | midpoint of serving.market_tender_fit_assessment.revenue_estimate_min and revenue_estimate_max (math over a stored estimate) |
| tenders | lean, leanTxt | overview.js, tenderRow.js, reports.js, chat.js | existing | serving.market_tender.lean_code, lean_text |
| tenders | competitorFit [{company, products[], incumbent, fit, why}] | Tenders.jsx, TenderCockpit.jsx, tenderIntel.js, marketOutlook.js | existing | serving.market_tender_competitor_fit (competitor_name -> company, competitor_product_display or competitor_products_text -> products, fit_label -> fit, fit_rationale -> why). incumbent: not-shipped |
| tenders | competitors (channel names) | Tenders.jsx, tenderIntel.js, chat.js | not-shipped | no column; tenderIntel channel analysis is removed |
| tenders | actions [{do, due}] | tenderIntel.js, TenderCockpit.jsx | existing | serving.market_next_move (action_text -> do, due_date -> due) joined on tender_id; cockpit rows come from topOpportunities.nextMoves |
| tenders | pursuit, statusChecked, stage, createdAt, extension, milestone | tenderIntel.js, tenderCalc.js, tenderRow.js | remove-genset | pre-tender "pursuit" and status-checked logic belong to tenderIntel (genset); served stage text replaced by market_tender_closing_window.milestone_text where displayed |
| tpAllCountries | [country] | Tenders.jsx, countryFacet.js | existing | serving.market_filter_option.option_label where filter_type='country' |
| tpAllCats | [category] | Tenders.jsx | existing | serving.market_filter_option.option_label where filter_type='category' |

> DECISION (user, 2026-10-17): the Market > Top opportunity page no longer reads topOpportunities. Like Cummins it builds its tables in the browser from the stored fields (src/lib/tenderIntel.js): Top tenders = open tenders with a stored clientFit/fit, ordered strong > partial > weak, then the nearest closingDate, then the larger valueAmount (no stored fit = not listed); model = matches[0].n, rival = competitorFit[0], revenue = revenueEstimate / expectedRevenue / value as stored, else a dash (never computed); Projects = data.projects (stage note, the project's own competitor as the rival, a stored fit/model/revenue only when the project carries one); Next moves = tenders[].actions not yet due. The topOpportunities tables and their backend stay as they are, unread by this page. The tender card (Tenders.jsx) always prints Buyer, Country, Category, Value, Status and the client fit row; an empty cell prints the chrome.js empty word.

### topOpportunities  (KSSL-only global that feeds TenderCockpit; Cummins computes the same tables from tenders with tenderIntel.js - ruling R6)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| topOpportunities | topTenders[].tenderId, title, issuer, country, rank | TenderCockpit.jsx (after port) | existing | serving.market_top_opportunity_tender.tender_id, rank_position; title/issuer/country from market_tender |
| topOpportunities | topTenders[].decides | TenderCockpit.jsx ("Decides" column; Cummins shows the closing date) | existing | serving.market_top_opportunity_tender.decides |
| topOpportunities | topTenders[].ksslFit / ksslModel / rivalToBeat / revenue | TenderCockpit.jsx | existing | serving.market_top_opportunity_tender.kssl_fit, kssl_model, rival_to_beat, revenue_text |
| topOpportunities | projectsBeforeTender[] (id, title, issuer, country, stage, ksslFit, ksslModel, rivalToBeat, revenue) | TenderCockpit.jsx | existing | serving.market_top_opportunity_project (+ market_opportunity.title, buyer_name, where_it_stands, kssl_fit, kssl_model, rival_to_beat, revenue_text) |
| topOpportunities | nextMoves[] (action, due, tenderTitle) | TenderCockpit.jsx | existing | serving.market_next_move.action_text, due_text/due_date, tender_title |
| topOpportunities | metrics[], notes{topTenders, projects, nextMoves} | TenderCockpit.jsx, MarketOverview.jsx tiles | existing | serving.market_top_opportunity_metric; ui.market_top_opportunity_view.*_description (E) |

### awards  (past tender awards; Cummins ships it from awards.json via the datapack)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| awards | segment | marketOutlook.js, MarketOutlook.jsx | new-table | serving.market_award.segment (section C) |
| awards | winner, brand, buyer, site | MarketOverview.jsx, marketOutlook.js, MarketOutlook.jsx | new-table | serving.market_award.winner, brand, buyer, site |
| awards | title, title_ar, programme, tender_no | MarketOverview.jsx | new-table | serving.market_award.title, title_local, programme, tender_number |
| awards | date, year | MarketOverview.jsx, marketOutlook.js | new-table | serving.market_award.award_date, award_year |
| awards | value (amount + currency), bids | MarketOverview.jsx, marketOutlook.js | new-table | serving.market_award.value_amount, value_currency, value_text, bids. Values stay in their original currency (ruling R9): neither the loader nor the browser converts; MarketOutlook totals are per currency |
| awards | country, url, source | MarketOverview.jsx | new-table | serving.market_award.country_name, source_url (source_tier) |

### globalRequirements (KSSL dataset key) and the Global Requirements page

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| globalRequirements | (KSSL list: id, title, buyer, country, region, cat, value, dl, deadline, status, desc, ksslFit, ksslModel, strategicAssessment, specs, sources) | (Cummins reads no dataset key by this name; globalRequirements() is a lib function over marketCards) | derived-ok | serving.market_global_requirement (+ _specification, _source): becomes marketCards + details rows (marketCards block above). The what/why/srcs on the detail panel: what=description, why=strategic_assessment, srcs=market_global_requirement_source |

### geoComps / geoData / geoCountries / geoPresence / actLabel / CAT_META / counterRules

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| geoComps | id | Geo.jsx, GeoMap.jsx, geo.js, roster.js | existing | serving.competitive_geo_company_presence.competitor_id (client row: client_id, company_role='client') |
| geoComps | name | Geo.jsx, geo.js | existing | serving.competitive_geo_company_presence.company_name |
| geoComps | isBf (is the client) | Geo.jsx, geo.js, geoBadge.js, roster.js, dataset.js | derived-ok | company_role='client' |
| geoComps | dir (marker colour) | GeoMap.jsx, geo.js | existing | serving.competitive_competitor.threat_level (via competitor_id) |
| geoComps | hq | GeoMap.jsx (isHeadOffice), geoCountries.js | existing | serving.competitive_competitor.headquarters |
| geoData | [cid][country] -> rows | Geo.jsx, GeoMap.jsx, geo.js, overview.js, dataset.js, shortlist.js | derived-ok | serving.competitive_geo_company_presence (company, location_id -> competitive_geo_location.country_name) with its competitive_geo_product rows; the client row keys by client_id. the dataset.js step that forces c='bf' on all client rows is deleted (client rows are the ones of geoComps.isBf) |
| geoData | row.name | Geo.jsx, GeoMap.jsx | existing | serving.competitive_geo_product.product_name |
| geoData | row.c (activity) | Geo.jsx, GeoMap.jsx, geoBadge.js | existing | serving.competitive_geo_product.activity_type, shipped as the stored word (the seed stores words such as 'Local production', 'Export'; there are no lp/pt/ex/sv/bf codes). CSS class = slug of the word. The client is identified by geoComps.isBf (company_role='client'), not by the code 'bf'; geoBadge CLIENT_ACT and the dataset.js step that forces c='bf' on client rows are deleted |
| geoData | row.val | Geo.jsx | existing | serving.competitive_geo_product.reported_value |
| geoData | row.since | Geo.jsx | existing | serving.competitive_geo_product.since_date |
| geoData | row.qty | Geo.jsx | existing | serving.competitive_geo_product.quantity |
| geoData | row.stage | Geo.jsx, partners.js | existing | serving.competitive_geo_company_presence.presence_status (presence-level; products carry none) |
| geoData | row.note | Geo.jsx, GeoMap.jsx | existing | serving.competitive_geo_product.record_note |
| geoData | row.src ('syn' = illustrative marker; evidence badges) | geoBadge.js (isEstimate), Geo.jsx | not-shipped | no illustrative flag; every shipped row is sourced, so the "analytical estimate" badges never show |
| geoData | row.srcnote | Geo.jsx | existing | serving.competitive_geo_source.source_label (for the geo_product_id) |
| geoData | row.srcs [{label,url}] | Geo.jsx | existing | serving.competitive_geo_source.source_label, source_url (geo_product_id / presence) |
| geoData | row.geo_news, c0 | Geo.jsx (marketNews), dataset.js | existing | serving.competitive_geo_product_news (headline, article_url, published_date, publisher); c0 is set by dataset.js |
| geoData | rows' kVA/rating/Hz fields (ratedPower, fuel, hz) | geo.js, tenderIntel.js | remove-genset | - |
| geoCountries | [country] (display order) | GeoMap.jsx, countryFacet.js, shortlist.js | derived-ok | serving.competitive_geo_location.country_name (sorted by name; backend today) |
| geoPresence | list of {comp: name, ...} (profile.js filters it by company name for the 'Country presence' count) | profile.js | derived-ok | flatten serving.competitive_geo_company_presence to a list with comp = company_name. KSSL's current geoPresence is a dict keyed by company id; the Cummins reader needs a list (a dict would throw on .filter) |
| actLabel | code -> label | Geo.jsx, geoBadge.js | derived-ok | identity map built from the distinct stored activity_type words (label = the word); the fixed Cummins words (Local production, Partner/licence, Exports in, Sales/service) are deleted from code |
| CAT_META | key -> {label, kw[], desc} (keyword classifier for geo rows) | geo.js | remove-genset | keyword classification of rows into kVA/defence bands is a judgement; replaced by stored serving.competitive_geo_company_presence.overlap_status, matched_ranges |
| counterRules | [{band, label, product, note}] (which client product counters which band) | geo.js (koelCounter, geoBandLabel) | remove-genset | replaced by stored serving.competitive_geo_product_match.kssl_counter_label (+ decision_level, evaluation_label, rating_delta) |
| KSSL_CATS | client product categories | dataset.js (market opportunity filter), threat.js | derived-ok | distinct serving.client_product.category |
| CAT_ALIASES | keyword -> category (Profile news search) | Profile.jsx (productCategoryOf) | not-shipped | search matches title/excerpt/category only; alias expansion is dropped |

### geo overlap panels

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| geo overlap | geoOverlap / geoOwnPanel / geoProductCompare / CMP_GROUPS / band tooltips | geo.js, Geo.jsx | remove-genset | built on kVA bands, keyword bands and invented analysis sentences ("Open ground...", "price... higher than in India"). Stored equivalents: competitive_geo_company_presence.overlap_status, matched_ranges, product_count, products_summary, relationship_text; competitive_geo_location.kssl_presence_summary; competitive_geo_product_match (+_specification) for the model compare popup |

### PATENTS  (Cummins ships flat rows byArea / byAssignee; adaptPatents derives byCompetitor / byTechnology)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| PATENTS | techAreas[] | Patents.jsx, patents.js | derived-ok | distinct serving.competitive_patent_filing.area_label (new column, C3) |
| PATENTS | _meta.total | overview.js (nav count), patents.js | derived-ok | count of serving.competitive_patent_filing rows |
| PATENTS | _meta.providers[] | patents.js (patApiNote; fallback list "Google Patents, EPO..., Indian Patent Office" is deleted) | existing | serving.competitive_patent_portfolio.data_source_note (empty -> note omitted) |
| PATENTS | record.no | Patents.jsx, patents.js | existing | serving.competitive_patent_filing.publication_number (else filing_id) |
| PATENTS | record.title | patents.js | existing | serving.competitive_patent_filing.title |
| PATENTS | record.assignee | patents.js, dataset.js | derived-ok | competitive_competitor.display_name via competitive_patent_portfolio.competitor_id |
| PATENTS | record.comp_id | dataset.js (adaptPatents) | existing | serving.competitive_patent_portfolio.competitor_id (the token-matching fallback is deleted) |
| PATENTS | record.status | patents.js, dataset.js | existing | serving.competitive_patent_filing.status |
| PATENTS | record.filed | patents.js | existing | serving.competitive_patent_filing.filed_date |
| PATENTS | record.granted, published, grant_no, pub_kind, title_en, doc_id | patents.js | not-shipped | no columns; the UI already shows 'status not captured' / 'grant no. not captured' honest states |
| PATENTS | record.country (jurisdiction) | patents.js, dataset.js | existing | serving.competitive_patent_filing.jurisdiction |
| PATENTS | record.ipc[] | patents.js, ipc.js | derived-ok | [serving.competitive_patent_filing.classification_code]; ipc.js SUBCLASS meanings are replaced by classification_text (section B) |
| PATENTS | record.abstract | patents.js | not-shipped | no abstract column; the IPC-field line shows classification_text instead |
| PATENTS | record.area (tech area) | dataset.js, Patents.jsx | new-table | new column serving.competitive_patent_filing.area_label (C3): the stored classification of the filing into a field. competitive_patent_classification is per portfolio and has no link to a filing, so no join or text match is used |
| PATENTS | record.threat | dataset.js, patents.js (holder chip) | new-table | new column serving.competitive_patent_filing.threat_level (C2) |
| PATENTS | record.relev (relevance to the client) | dataset.js, patents.js (pat-relev chip) | new-table | new column serving.competitive_patent_filing.client_relevance (C2) |
| PATENTS | record.url | patents.js | existing | serving.competitive_patent_filing.patent_url (the invented Google Patents search URL fallback is deleted) |
| PATENTS | record.srcs | patents.js | not-shipped | - |
| PATENTS | byTechnology[area].summary | patents.js, dataset.js | existing | serving.technology_category.category_description (was techAreaMeta.why\|\|desc) |
| PATENTS | byTechnology[area].crowding (open/emerging/crowded/locked) | patents.js (patTechBody) | new-table | serving.patent_field_assessment.crowding, keyed by area_label (C2). dataset.js thresholds (>=25 crowded, >=8 emerging) are deleted |
| PATENTS | byTechnology[area].koel.position (client position in the field) | patents.js | new-table | serving.patent_field_assessment.client_position_note (C) |
| PATENTS | byTechnology[area].whitespace | patents.js | not-shipped | always null in Cummins ("not computed" honest line) |
| PATENTS | stats (filings, assignees, granted/pending) and leaders[] (holders with counts) | patents.js, dataset.js | derived-ok | counts over filing rows (allowed math); stored counts exist: competitive_patent_portfolio.filing_count, granted_count, pending_count |
| techAreaMeta | area (display name) | dataset.js | existing | serving.technology_category.category_name (ui_name via technology_category_ui_label) |
| techAreaMeta | desc | dataset.js | existing | serving.technology_category.category_description |
| techAreaMeta | maturity, position, trend, reason, why | dataset.js (adaptPatents) | not-shipped | unused outputs, except `reason` which is serving.patent_field_assessment.client_position_note (above); trend is not displayed |
| techCats | [{id, name}] | Innovation.jsx, Patents.jsx, search.js, overview.js, reports.js | existing | serving.technology_category.category_id, category_name (ui label: technology_category_ui_label.ui_name) |

### innovations  (dict category id -> list)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| innovations | t | Innovation.jsx, search.js, reports.js | existing | serving.technology_innovation.title |
| innovations | mat (lab, dev, prod, fielded) | Innovation.jsx, innovation.js, reports.js | existing | serving.technology_innovation.maturity (words other than the four are shown as stored; MAT_LAB maps the four to display text) |
| innovations | gap (behind, parity, ahead) | Innovation.jsx, innovation.js | existing | serving.technology_innovation.client_position |
| innovations | driver | Innovation.jsx, profile.js, search.js | derived-ok | names of serving.technology_innovation_company rows joined with ', ' |
| innovations | horizon | Innovation.jsx, reports.js | existing | serving.technology_innovation_status.horizon_text (else technology_innovation.horizon_year) |
| innovations | body (list description and Background) | Innovation.jsx, DetailPanel-neutral, search.js | existing | serving.technology_innovation.background_what_it_is (list_description is also available as the short list line) |
| innovations | impact | Innovation.jsx, reports.js | existing | serving.technology_innovation.why_matters_to_kssl |
| innovations | whatsNew | Innovation.jsx, reports.js | existing | serving.technology_innovation.whats_new |
| innovations | compNote | Innovation.jsx, reports.js | existing | serving.technology_innovation.competitive_note |
| innovations | sources, url, srcs [{label,url}] | Innovation.jsx, reports.js | existing | serving.technology_innovation_source -> serving.technology_source (label, source_url) |
| innovations | action | (not read) | not-shipped | - |

### client partners, syntheses, source registry

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| KSSL_PARTNERS | id | partners.js, Partnerships.jsx | existing | serving.client_partner.client_partner_id |
| KSSL_PARTNERS | label | overlap.js, partners.js, dataset.js | existing | serving.client_partner.partner_name |
| KSSL_PARTNERS | cid | dataset.js, partners.js | derived-ok | exact, case-insensitive match of serving.client_partner.partner_name to competitive_competitor.display_name or legal_name (client_partner_id is bigint and competitor_id is uuid, so the keys cannot be joined) |
| KSSL_PARTNERS | ptype, rel | partners.js | existing | serving.client_partner.partner_type (rel = slug via ui.partner_category) |
| KSSL_PARTNERS | country | partners.js | existing | serving.client_partner.country |
| KSSL_PARTNERS | note | partners.js | derived-ok | serving.client_partner_relationship.description (first row) |
| KSSL_PARTNERS | role (the client's role in the tie) | partners.js (ovRole via koel.role) | existing | serving.client_partner.strategic_role |
| KSSL_PARTNERS | status | partners.js (statusTag) | existing | serving.client_partner.relationship_status |
| KSSL_PARTNERS | date, as_of | partners.js (asOfYear) | existing | serving.client_partner.relationship_start_date |
| KSSL_PARTNERS | mean, insight (what the tie means) | partners.js | existing | serving.client_partner_relationship.kssl_read (first row) |
| KSSL_PARTNERS | kind, sig, deal | partners.js | not-shipped | no columns |
| KSSL_PARTNERS | (fallback roster VERIFIED_KSSL_ROSTER / VERIFIED_KSSL_PARTNERS) | dataset.js, Partnerships.jsx | remove-genset | hardcoded roster of ten partners (section B); the dataset is the only source, an empty list shows the empty state |
| REL_LABEL | rel -> label | partners.js, Partnerships.jsx | existing | ui.partner_category.category_label (C); today KSSL ships none |
| COMPSYN | [cid].thesis | partners.js (compReportHtml) | new-table | serving.competitive_synthesis.thesis (C) |
| COMPSYN | [cid].vulns[] {title, from[], intel} | partners.js | new-table | serving.competitive_synthesis_vulnerability.title, from_labels, intel (C) |
| COMPSYN | [cid].strat {thesis, pattern, sowhat} | partners.js | new-table | serving.competitive_synthesis.strategy_thesis, strategy_pattern, strategy_sowhat (C) |
| COMPSYN | preds, moves | (never read) | not-shipped | - |
| TRACEIDS | [cid][vulnIndex] -> partner ids | partners.js (traceNodeIds) | new-table | serving.competitive_synthesis_vulnerability.traced_relationship_ids (C) |
| FIELDSYN | patterns[] {field/t, pattern/e, implication/s, n, total} | partners.js (fieldReadHtml) | new-table | serving.competitive_field_synthesis (row_kind='pattern') (C) |
| FIELDSYN | bottom / bottomLine | partners.js | new-table | serving.competitive_field_synthesis (row_kind='bottom_line') (C) |
| sourceRegistry | [{company,label,url,kind}] | partners.js (fieldReadHtml "All tracked sources") | not-shipped | no registry table; the sources list under the field-level read is omitted |
| companySources | company -> urls | profile.js (buildProfile.sources; not rendered) | not-shipped | - |
| chatSuggest | keyed suggestion strings | (Cummins UI never reads it) | hidden:chat | - |

### projects  (Cummins reads the constant PROJECTS_DATA; the port reads data.projects, KSSL global already shipped)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| projects | id | Projects.jsx, projects.js | existing | serving.competitive_project.project_id |
| projects | cid | Projects.jsx, projects.js | existing | serving.competitive_project.competitor_id |
| projects | company | Projects.jsx, projects.js | existing | serving.competitive_project.company_display (else competitive_competitor.display_name) |
| projects | name | Projects.jsx, projects.js | existing | serving.competitive_project.project_title |
| projects | kind | Projects.jsx | existing | serving.competitive_project.kind |
| projects | region (Gulf / Worldwide) | projects.js (counts, filter), Projects.jsx | existing | serving.competitive_project.region (value comes from data; the label "Gulf region" is E; the Gulf-specific filter option is dropped unless the data holds it) |
| projects | customer, location | Projects.jsx | existing | serving.competitive_project.customer, location |
| projects | stage | Projects.jsx | existing | serving.competitive_project.stage |
| projects | stageRank | projects.js (sort), Projects.jsx (stepper) | existing | serving.competitive_project_stage.stage_order of the row with is_current |
| projects | stageNote | Projects.jsx, projects.js | existing | serving.competitive_project.stage_note |
| projects | mw (size sort) | projects.js | remove-genset | power rating (MW) sort is removed from PROJECT_SEQ |
| projects | specs [{k, v}] | Projects.jsx, projects.js | existing | serving.competitive_project_specification (spec_label -> k, spec_value (+unit) -> v) |
| projects | timeline [{date, label, expected}] | Projects.jsx | existing | serving.competitive_project_timeline (event_date, event_title, is_expected) |
| projects | latest {date, label} | projects.js, Projects.jsx | existing | serving.competitive_project.latest_milestone_date, latest_milestone |
| projects | overview (string[]) | Projects.jsx, projects.js | existing | serving.competitive_project.what_the_project_is (wrapped into a one-element array) |
| projects | assessment {stance, read[]} | Projects.jsx, projects.js | existing | serving.competitive_project.assessment_stance, assessment_read (+ strategic_assessment) |
| projects | sources [{label,url}] | Projects.jsx | existing | serving.competitive_project_source (source_label, source_url) |
| projects | AS_OF ("Researched to ...") | Projects.jsx | existing | serving.competitive_project.researched_as_of |
| projects | PROJECT_STAGES, PROJECT_FILTERS, PROJECT_SEQ, STANCE_WORD | Projects.jsx, projects.js | existing | ui.ui_project_stage_step.stage_name, ui.ui_project_filter, ui.ui_project_sequence_option (E); already shipped as projectsConfig |

### values created at wire time (not dataset keys; listed so nobody ships them)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| geoRows, techItems | (flattened chat knowledge) | dataset.js, chat.js | hidden:chat | built in the browser from geoData / innovations; not shipped |
| overviewShortlist, signalTheme, themeSignals, __newsDetailIdx, __countryVocab | (browser caches / vestigial empties) | dataset.js, news.js, countryFacet.js | derived-ok | created at wire time, not dataset keys; not shipped. overviewShortlist itself is removed (ruling R5) |
| BAND_LABEL | band key -> label (client product category by kVA band) | Products.jsx | remove-genset | genset rating band; the category shown is the product's stored category |

### new top-level globals the port introduces

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| sectionVisibility | {section_key: boolean visible} | Layout.jsx, route.js, Sidebar.jsx, Profile.jsx, Products.jsx, TopBar.jsx, search.js, MalloryChat.jsx, ScopeChat.jsx, AskBox.jsx | new-table | backend builds dataset.sectionVisibility = { [section_key]: visible } from ui.section_visibility (C1); the UI helper isVisible(data, key) returns true only for an explicit visible=true, so a missing key is hidden |
| (labels) no new global | ui.* label text for every row of section E marked ui-table | all pages | existing | the UI reads the rows already shipped in data.database.ui.<table> and data.database.serving.<table> with one helper, uiText(data, 'ui.<table>', {keyColumn: keyValue}, 'labelColumn'); a missing row or empty cell renders the em dash. Nothing is added to the backend for labels |

### KSSL-only globals with no Cummins reader (kept so the Review layer and Trace keep working)

| global | field | read by | disposition | KSSL source |
|---|---|---|---|---|
| database | all ui + serving tables verbatim | (KSSL Trace/Review layer) | existing | backend/app.py load_all_tables |
| databaseSchema | manifest | (KSSL) | existing | backend/app.py load_schema_manifest |
| review | per-card approve/reject status (review backend only) | (KSSL Review.jsx) | existing | backend/review.py statuses |
| clientProducts | client catalogue list | (no Cummins reader; client products ride on competitors[client].products) | not-shipped | folded into competitors[client_id].products |
| geoLocations | location list | (no Cummins reader) | not-shipped | folded into geoCountries / GeoMap coordinates (competitive_geo_location.latitude, longitude) |
| projectsConfig | filters, seqOptions, stageSteps | (Cummins reads constants) | existing | ui.ui_project_filter / _sequence_option / _stage_step (replaces PROJECT_FILTERS/PROJECT_SEQ/PROJECT_STAGES) |

## B. Hardcoded data in code

Every constant array or object that holds records or sentences, in `lib/*.js` and also the page files that carry the same kind of constant. Counts are measured on the copied sources.

### B1. Record constants the brief names

| constant | file | records | target global | table / disposition |
|---|---|---|---|---|
| PROJECTS_DATA | competitorProjects.js | 58 projects, 8 competitors (3,407 lines) | projects (the page now reads data.projects) | existing tables serving.competitive_project, _stage, _specification, _timeline, _source (all 1:1 with the constant's fields, see A: projects). File deleted. Cummins fields mw and the Gulf/Worldwide filter are genset/region specific (remove-genset) |
| PROJECT_STAGES, AS_OF | competitorProjects.js | 4 stage names; 1 date | projectsConfig.stageSteps; projects[].researchedAsOf | ui.ui_project_stage_step.stage_name / serving.competitive_project.researched_as_of (both exist) |
| NEWS_LENSES | newsLenses.js | 36 articles keyed by card id, 154 lens paragraphs (each lens = {view, text}, writes Cummins-specific analysis) | competitorNews[].lenses | serving.competitive_competitor_moment_analysis (view_name, analysis_text, display_order). File deleted. The prose is analysis - never browser data |
| PARTNER_CATEGORIES, CATEGORY_GROUPS | partnerCategories.js | 15 categories (with {C} definitions, colours) in 4 groups | REL_LABEL / partner legend | new ui.partner_category (section C1). Colours stay in code as a palette indexed by display_order. The genset channel categories (packager, rental fleet supply, dealer, exclusive distributor) are written only if the KSSL data uses them |
| OV_KIND, OV_DEF | partners.js | 4 overlap kinds (channel, supplier, service, tech) x 2-6 effect paragraphs about "what an overlapping X costs KSSL" | partner drawer 'overlap' text | new ui.partner_overlap_kind + ui.partner_overlap_effect (C1). Prose is analysis; rows ship empty until written. The literal word KSSL inside it is data, not code |
| CONF_TAG, REL_SHORT, OVERLAP_BADGE | partners.js | 3 confidence tags; 13 short relationship words; 4 badge labels | partner chips | confidence word = stored competitive_partnership.relationship_confidence (shown as stored); REL_SHORT -> ui.partner_category.short_label; OVERLAP_BADGE labels are chrome (client name from data) |
| PG_REGION_ALIAS, DEFENSE_FIRM_COUNTRIES | partners.js | 108 country-name aliases in many languages; 22 company-name regexes -> country | partners[].country | both deleted (ruling R6 for PG_REGION_ALIAS). A company-to-country guess is a fabricated fact; competitive_partnership.region already holds the stated region |
| glance MEANING, GLANCE_KEYS | glance.js | 17 glosses | (none: glanceMeaning is imported nowhere) | dead module, deleted |
| reports.js templates | reports.js | positioningReportHtml, techReportHtml, MAT_LAB_REPORT (4 maturity words) | Print/CEO briefing | kept as templates that join dataset values and data.client.short only. Sentences that assert something the DB does not hold ("is a real, sourced competitor mapped to ... by role and spec class", "Competitive & market figures drawn from the platform dataset (real where sourced, estimated where marked)") are deleted. MAT_LAB_REPORT -> technology_innovation_status.maturity_label |

### B2. Other exported or module-level record constants found in $C/src

| constant | file | records | target global | table / disposition |
|---|---|---|---|---|
| ROSTER | roster.js | 45 company-id groups | competitors / compOrder | deleted with applyRoster(): the roster is every row of serving.competitive_competitor (sorted by display_name in the browser, allowed) |
| COMPANY_NAMES | companyNames.js | 41 entries (expands / full / note / noExpansion + a source tag) | competitors[].legal | serving.competitive_competitor.legal_name. The "workbook" source tags are Cummins pipeline artifacts. initialisms/companyShort heuristics stay only if they act on stored names |
| PAIRS | dedupeCompanies.js | 4 company merge pairs (idv/iveco, rtx/raytheon, knds/nexter, hsw) | competitors | deleted; the loader dedupes (competitor_id is unique) |
| SIGNAL_COUNTRY | signalCountry.js | 54 card ids -> country or region | details.facts Country | deleted; the country is a stored fact (technology_overview_fact / competitive_signal_evidence label 'Country') or competitive_competitor_moment.country_name |
| TICKERS, ID_ALIAS, NOT_LISTED_NOTE | tickers.js | 44 tickers; 18 id aliases; 28 'not listed' notes | competitors[].ticker | hidden:stock - serving.competitive_stock_quote.ticker, empty_message / availability_state (the 'not listed' sentence is the stored empty_message). The tables are deleted, not kept as constants |
| mockStockHistory.js generator | mockStockHistory.js | deterministic fake price series | Profile StockPage | hidden:stock - code kept but gated off; it must not render for KSSL. Inline fallback prices in Profile.jsx (3140.50 / 3692.50 and a fake series) are deleted outright |
| VERIFIED_KSSL_ROSTER | dataset.js | 10 partner records (DRDO, Rafael, AM General, ...) | KSSL_PARTNERS | deleted; serving.client_partner is the only source |
| VERIFIED_KSSL_PARTNERS | Partnerships.jsx | same 10 records, second copy | KSSL_PARTNERS | deleted |
| TIERS, UNRESOLVED, LINES, GRADES, ALIAS, LINE_WORDS | footprint.js | 5 client footprint rows (India, Armenia, UAE, US, Spain) with source URLs and tiers; 1 unresolved region | (client footprint) | deleted with shortlist.js; the client footprint is competitive_geo_company_presence where company_role='client' |
| DEMONYM, INDIA_PLACES | shortlist.js | 81 demonym->country pairs; 33 Indian place names | overviewShortlist | deleted with overviewShortlist (ruling R5) |
| NON_KSSL / PLATFORM / INDIA / EXPORT regexes, SEV | threat.js | 4 defence keyword regexes + 3 severity grades | cards severity / dir | deleted: browser re-grading of threat vs watch is a judgement |
| ASSUME, MAIN_RX, OEM_RX, TIED, GENSET_RX, BUILD_RX | tenderIntel.js | win probabilities, lag days, genset/OEM keyword regexes, 4 tied channels | tenders (cockpit) | deleted (remove-genset); TenderCockpit reads data.topOpportunities (A: topOpportunities) |
| SEG_ALIAS, SEGMENT_LABEL, BANDS, WINDOW_DAYS | marketOutlook.js | 5 genset segment aliases; 1 label; 11 kVA bands; 183 days | MarketOutlook | SEG_ALIAS, SEGMENT_LABEL, BANDS and sizes() deleted (remove-genset). WINDOW_DAYS is a date-window constant (chrome) |
| CR_PER_MILLION, parseCr | gapModel.js | FX table (US$, A$, EUR, GBP, AED, MYR -> INR crore) and a value parser | tenders[].value tiles, marketAttention | deleted (ruling R9: no FX anywhere). Value tiles use serving.market_tender.value_amount + value_currency and show one total per stored currency; marketAttention takes the first 20 open tenders in stored rank_position order (unranked after, newest first) and computes no score. gapModel.js stays (hidden:gap-analysis) but carries no severity, urgency, rank score or exposure figure |
| REVENUE_LABEL, CRORE_PER_BN, CUR | revenueFacet.js | 4 tier labels with INR-crore thresholds; FX table | competitors[].revenue_filter | deleted; tier word = serving.competitive_competitor.revenue_tier as stored |
| IPC SUBCLASS | ipc.js | 12 defence IPC subclasses with meanings | PATENTS record.ipc | deleted; text = serving.competitive_patent_filing.classification_text |
| COUNTRY_ALIAS | patents.js | 18 country-name -> ISO2 pairs | PATENTS record.country | folded into countryFlags.js (allowlisted neutral lookup, ruling R6) and removed from patents.js; the region words of countryFacet.js:196 move to geoCountries.js the same way |
| NATIONAL, ALIASES, COLLECTIVE, PLACES, FORCE_RX, QTY_RX, VAGUE_RX | orgident.js | demonym map; 3 company aliases (HAL, Hanwha, Rafael); junk-partner word lists | partners[].label | isJunkPartner() and ALIASES deleted (the loader keeps junk out; no hardcoded company aliases). fold()/orgKey() string normalisers stay |
| GAP_DIM, GAP_ORDER, GAP_WHY, GAP_OWN, GAP_MINDEC... | gapAnalysis.js | 12 category-scoped measurement keys (Weight, power density, ...), interpretation prose per category | Gap Analysis page | hidden:gap-analysis - code kept, gated. The interpretation table GAP_WHY is hardcoded analysis and would have to move to the DB before the section is ever switched on |
| MAT_LAB and the offline answer templates | chat.js | maturity map; answer sentences | MalloryChat / ScopeChat / AskBox | hidden:chat |
| EDGE_AXIS, EDGE_RANGE, EDGE_DEADBAND_BY, EDGE_GROUPS, EDGE_DEADBAND, EDGE_CAP | edge.js | pairing-axis names (Calibre, MTOW, Length, Barrel), plausibility ranges (Crew, Speed), fuel/weight/footprint groups | matchups[].edge | remove-genset assumptions (standby fuel / dry weight / per-kVA). The stored edge_score is shipped; computeSpecEdge keeps only the generic dead-band maths (ruling R6) |
| SPEC_SYNONYMS | specs.js:155 (mirror of backend/app.py _SPEC_SYNONYMS) | 18 label merges (combat weight, empty weight, mass -> weight; speed, top speed -> max speed; caliber -> calibre ...) | specKey(), fillSpecs(), spec comparison | deleted. Merging distinct labels fabricates comparability. Specs are compared on the stored spec_label only; a pair whose labels differ is two rows |
| PRODUCT_IMAGE_MAP | Products.jsx | 96 product-name -> unsplash photo | product thumbnails | hidden:product-images (and the entries are defence stock photos) |
| CATEGORY_POOLS, getProductImage, strHash | Products.jsx | 11 keyword pools with 42 stock photo URLs | product thumbnails | hidden:product-images |
| getResolvedSpecs | Products.jsx | 5 fabricated spec sets (UAV, missile, ammo, small arms, generic) | competitors[].products[].specs | deleted. Missing specs show the empty state; the DB tables hold real specs |
| getProductPrograms | Products.jsx | 5 fabricated programme sets with invented dates and authorities | products[].programs | deleted; serving.competitive_product_program / client_product_program |
| getProductComparison | Products.jsx | fabricates a matchup (verdict "leads on comparable specifications", specs 'Verified'/'Sovereign') in browser memory | matchups | deleted; the link goes to the stored matchup via matchupIds |
| DUMMY_NEWS_DATES, FALLBACK_NEWS_IMAGES, cleanNewsCategory | Profile.jsx | 20 invented dates; 9 unsplash URLs; a keyword->category map | competitorNews dates / images / category | deleted (an invented date or photo is fabricated). The demo source name 'demo · policy-watch.example' is deleted |
| getLeaderPsychology | Profile.jsx | 4 invented leader profiles (named Adani, L&T leaders + generic text); its result is never rendered | leadership | deleted (dead code and fabricated) |
| ACRONYMS (casing list) | profile.js | 150 acronyms incl. KSSL, DRDO, SAR | text casing | deleted; casing is the stored text. (Typographic only, but it contains SAR and defence acronyms) |
| COUNTRY_KEY_MAP and the flag drawing | countryFlags.js | country name -> flag key | geoCountries / flags | allowlisted neutral lookup (kept) |
| COUNTRY_COORDS | geoCountries.js | country -> [lat, lng] | GeoMap | allowlisted neutral lookup (kept); the client row's coordinates also exist in serving.competitive_geo_location.latitude/longitude |
| ENTITIES, URL classifiers, symbol shapes, CLIENT_ACT | html.js, articleUrl.js (ARTICLE, INDEX, UNKNOWN, INDEX_NOTE, INDEX_THUMB), categorySymbols.js, geoBadge.js | HTML entity table; URL-pattern classes; SVG category glyphs; the activity code 'bf' | (none) | neutral technical constants, no records: kept (INDEX_NOTE/INDEX_THUMB are honest-state text, chrome) |
| local photos | public/local-photos/*.jpg | 4 BEL executive photos | leadership[].photo | not ported |
| product photos | public/product-images/*.jpg | 125 files named by competitor id and product | products[].image | not ported (hidden:product-images; spec s7.1 excludes Cummins product photos) |
| operator twin page | public/ops/index.html, twin.html | crawler panels | - | not ported (data-centre crawler dashboard, remove-genset) |

### B3. Hardcoded literals inside logic that stand in for data (found while reading)

| literal | file | stands in for | disposition |
|---|---|---|---|
| "India" as the client's country | compareProducts.js:49 | client product row country in the Positioning compare | delete; no country is shown for client products unless stored |
| "Defence & Aerospace" fallback | profile.js formatSectorName | competitors[].sector | delete; empty -> em dash |
| "KSSL · " / "Kalyani Strategic Systems · " name prefixes stripped by regex | specs.js, Products.jsx, MatchupList.jsx, MatchupDossier.jsx | matchup client product names | replace by stripping a prefix derived from data.client.short / name |
| "Ministry of Defence", DAP 2020 indigenous-content gloss | Tenders.jsx (req-gloss paragraph) | tenders[].req | delete the paragraph (invented domain explanation) |
| "26 records do exist from an earlier pass ... 22 of them carry estimated patent numbers" | Patents.jsx (empty state) | PATENTS | delete; chrome empty state only ("No patent filings are indexed") |
| "Cummins Arabia can learn from or adopt", "geopolitical & demand moves ... can act on" and other group straplines | dataset.js | overviewConfig.groups.s | delete (straplines were already removed from rendering by the owner) |
| Currency note "values in USD (SAR 0.2667, KWD 3.25)" | MarketOverview.jsx, MarketOutlook.jsx | awards value labels | delete; ruling R9: no rate exists anywhere, awards keep their own currency (serving.market_award.value_amount + value_currency) and are totalled per currency |
| Fallback role "Key Executive / Officer" | Profile.jsx:531 | leadership[].role | em dash when serving.competitive_leader.role_title is empty |
| Fallback category "Defence" and cleanNewsCategory() default | Profile.jsx:88, 1084; Products.jsx:1696 | competitorNews[].category | em dash; category is the stored text |
| Fallback categories "Defence Systems", "Uncategorised", "Update" | Products.jsx:48, 1115; marketOverview.js:89 catOf; news.js:57; shortlist.js:429 | product / tender / news category | em dash; no invented category name |
| Fallback source "Unattributed" | SourceLink.jsx:34, 88; Profile.jsx:1087 | competitorNews[].source | em dash when publisher is empty (the host name derived from the url is allowed) |
| Fallback "Awarded / Settled" and timing "Awarded - programme concluded" | tenderCalc.js:28-29 | tenders[].deadline / timing for awarded tenders | the stored closing date; timing words come from the stored status |
| Fallback "Upcoming" stage | TenderCockpit.jsx:30 | projects before tender: stage | goes with R6 (the cockpit reads topOpportunities, stage = market_top_opportunity_project.where_it_stands) |
| Fallback names "Main Company", "This partner", "Partner", "Other", "Competitor" | partners.js:615, 623, 678, 910, 2052; specs.js:57, 100, 307; reports.js:59 | partner / company names in the graph and spec headings | em dash or the stored name |
| Verdict heading fallback "Positioning verdict" | MatchupDossier.jsx:85 | matchups[].verdictH | em dash; stored serving.competitive_matchup.verdict_headline |
| MarketOutlook "Next expected" date and "overdue" flag (last record + median gap) | marketOutlook.js:211-216; MarketOutlook.jsx | Repeat buyers table | deleted: a forecast / estimate computed in the browser. The columns Buyer, Tenders and awards, Value (per currency) and Last (a date) stay: counts and dates are allowed math |
| MarketOutlook segment trend words (rising / falling / steady) and the act sentence built from them | marketOutlook.js:105-110 | Where demand is heading table | the thresholds (1.25 / 0.75) are an arbitrary judgement: deleted. The table shows the two counted windows and the signed percentage change (allowed math); the "What to do" column is serving.market_segment_assessment.recommendation (section C2) |

## C. New tables

Final DDL-level list. Ids follow the existing schema (uuid keys for competitor and relationship ids, bigint for category, tender and market ids). Every content table (C2) gets `source_url text` and `source_tier text`; C1 tables are configuration. Each C1 table is created twice (`staging_ui.X` and `ui.X`); each C2 table and C3 column twice (`staging.X` and `serving.X`; the one ui column on `staging_ui` and `ui`). Serving copies get the `only_via_approve` guard trigger like all others (registration details in C1).

### C1. New ui tables  (staging_ui.X in kssl_staging and ui.X in kssl_serving)

| definition | replaces / holds |
|---|---|
| `ui.section_visibility(section_key text primary key, visible boolean not null, note text)` | replaces: nothing (new gate). Keys: gap-analysis, finances, stock, parallax-read, swot, strategic-positioning, product-images, chat. Shipped as dataset.sectionVisibility = { [section_key]: visible }; a missing key is hidden. KSSL seed rows: all eight with visible=false |
| `ui.partner_category(category_key text primary key, group_key text not null, group_label text not null, category_label text not null, short_label text, definition text, overlap_kind text, display_order integer not null)` | replaces: PARTNER_CATEGORIES, CATEGORY_GROUPS (partnerCategories.js), REL_LABEL, REL_SHORT (partners.js). The relationship legend: category_key = slug of competitive_partnership.partner_type; label and definition text may contain {rival} and {client} placeholders (joins of dataset values); overlap_kind picks the OV_KIND bucket. Colours stay in code, indexed by display_order. This is generic legend text (one row per relationship type, not a fact about one company), so it is configuration: no source_url / source_tier |
| `ui.partner_overlap_kind(overlap_kind text primary key, kind_label text not null, lead text, display_order integer not null)` | replaces: OV_DEF[kind].label and .lead (partners.js): heading and one-line lead of "what an overlapping channel / supplier / service / technology partner costs the client". Generic explanatory text, configuration |
| `ui.partner_overlap_effect(effect_id bigint generated by default as identity primary key, overlap_kind text not null references ui.partner_overlap_kind(overlap_kind), display_order integer not null, effect_title text not null, effect_text text not null)` | replaces: OV_DEF[kind].fx pairs (2-6 per kind). Ships empty until written |
| Registration of the C1 tables | no backend/review.py change: setup_tables() lists every table of staging_ui automatically (review.py:278-282), so each C1 table gets one Approve / Unpublish per table. Do NOT add them to SERVING_TABLES: that tuple holds serving.* reference tables and setup_tables() pairs every entry with schema 'serving'. Create them in a new file db/setup/09_ui_port_tables.sql that db/make_databases.sh applies to the staging DB (after 08) and to the serving DB (after build "$SRV"); put the guard trigger (the CREATE TRIGGER only_via_approve statement of db/setup/04_serving_db.sql lines 32-40) for each new ui and serving table in that same file, because 04 only covers the tables that exist when it runs. Add fictional rows ('... (TEST)') for every new table and column in a new db/test_seed_full/90_ui_port.sql |

### C2. New content tables  (staging.X in kssl_staging and serving.X in kssl_serving; every one has source_url text and source_tier text; each gets a GRAPH entry in backend/review.py shaped (key column, reviewed?, [(fk column, parent table)]))

| definition | replaces / holds |
|---|---|
| `serving.competitive_synthesis(competitor_id uuid primary key references serving.competitive_competitor(competitor_id), thesis text, strategy_thesis text, strategy_pattern text, strategy_sowhat text, source_url text, source_tier text)` | replaces: COMPSYN[cid].thesis and COMPSYN[cid].strat {thesis, pattern, sowhat} (partners.js compReportHtml: "Read on this competitor", "What their web reveals"). GRAPH: "competitive_synthesis": ("competitor_id", False, [("competitor_id", "competitive_competitor")]) |
| `serving.competitive_synthesis_vulnerability(vulnerability_id uuid primary key default gen_random_uuid(), competitor_id uuid not null references serving.competitive_synthesis(competitor_id), display_order integer not null, title text not null, intel text, from_labels text, source_url text, source_tier text)` | replaces: COMPSYN[cid].vulns[] {title, from[], intel}; from_labels holds the "from" chips one per line (the browser splits on newline). GRAPH: "competitive_synthesis_vulnerability": ("vulnerability_id", False, [("competitor_id", "competitive_synthesis")]) |
| `serving.competitive_synthesis_vulnerability_trace(trace_id uuid primary key default gen_random_uuid(), vulnerability_id uuid not null references serving.competitive_synthesis_vulnerability(vulnerability_id), relationship_id uuid not null references serving.competitive_partnership(relationship_id), source_url text, source_tier text)` | replaces: TRACEIDS[cid][i] (the partner ties a vulnerability traces to); a link table instead of an array column so Trace and the review signature keep working. GRAPH: "competitive_synthesis_vulnerability_trace": ("trace_id", False, [("vulnerability_id", "competitive_synthesis_vulnerability")]) |
| `serving.competitive_field_synthesis(synthesis_id uuid primary key default gen_random_uuid(), row_kind text not null check (row_kind in ('pattern','bottom_line')), display_order integer not null, field_title text, pattern text, implication text, support_count integer, support_total integer, bottom_line text, source_url text, source_tier text)` | replaces: FIELDSYN.patterns[] {field/t, pattern/e, implication/s, n, total} and FIELDSYN.bottom / bottomLine (partners.js fieldReadHtml, the "Field-level read"). GRAPH: "competitive_field_synthesis": ("synthesis_id", True, []) |
| `serving.market_award(award_id bigint generated by default as identity primary key, segment text, winner text, brand text, buyer text, site text, country_name text, programme text, title text, title_local text, tender_number text, award_date date, award_year integer, value_amount numeric, value_currency text, value_text text, bids integer, source_url text, source_tier text)` | replaces: the awards global read by MarketOverview.jsx "Past awards" and marketOutlook.js winners / segments / buyers (only the fields those screens print). The value stays in its original currency: no conversion in the loader or the browser (ruling R9); same pattern as market_tender.value_amount / value_currency / value_text. GRAPH: "market_award": ("award_id", True, []) |
| `serving.market_segment_assessment(segment text primary key, recommendation text, source_url text, source_tier text)` | replaces: the `act` sentence per segment built in marketOutlook.js segments() ("Prioritise: ...", "Watch: ...", "Steady, nothing open fits"), shown in the "What to do" column. A recommendation is a judgement; ships empty (the cell shows the em dash). segment matches market_tender.category_text and market_award.segment. GRAPH: "market_segment_assessment": ("segment", True, []) |
| `serving.patent_field_assessment(area_label text primary key, crowding text, client_position_note text, source_url text, source_tier text)` | replaces: dataset.js adaptPatents crowding thresholds (25 / 8 filings) and techAreaMeta.reason (printed as "<client> position" in the field analysis). area_label equals competitive_patent_filing.area_label (C3); one prompt run writes both and a relabel must rewrite both. GRAPH: "patent_field_assessment": ("area_label", True, []) |

### C3. Columns added to existing tables  (the serving.* ones also on staging.*; the ui.* one also on staging_ui.*)

| definition | replaces / holds |
|---|---|
| `serving.competitive_partnership ADD client_verdict text, ADD client_impact text` | replaces: partners[].mean ("Threat: ...") that partnerCategories.js verdictOf / meanText parses and the drawer prints as "What it means for <client>". client_verdict is stored as the analyst wrote it; the backend ships `verdict` and `impact` as two fields (no re-casing, no joined string); only threat and watch draw a verdict (R22) |
| `serving.competitive_news_article ADD description text` | replaces: competitorNews[].description, the excerpt printed on news cards and used in search and product-news matching (Profile.jsx, news.js) |
| `serving.competitive_patent_filing ADD threat_level text, ADD client_relevance text, ADD area_label text` | replaces: PATENTS record.threat (holder "assessed threat" chip), record.relev (relevance chip) and record.area (the filing's technology field, which Cummins matched by text). threat and relevance are judgements and ship empty |
| `ui.competitive_metric ADD metric_key text` | replaces: the label-text matching in overview.js metricsFor. Values for the competitive tiles: threats, watch, companies_tracked. A tile is drawn only when a row with that key exists, and its label is the metric_label of that row (section E2) |

## D. Strings

Every hit of `/cummins|genset|kva|data.?cent|\bAED\b|\bSAR\b|saudi|gulf/i` in `$C/src`, `$C/index.html` and `$C/public/ops` (the only other public text file). Dispositions:

- `client-field`: the literal is replaced by `data.client.short` / `data.client.name` (or, for identifiers like `cumminsFit`, renamed neutrally), or deleted together with the sentence it sat in. No literal client name may survive in `src/`, `index.html`, `public/`, `dist/`.
- `dataset-field`: the text or vocabulary now comes from a DB column.
- `remove-genset`: genset / kVA / data-centre / AED / SAR / Saudi / Gulf logic or wording; removed with its feature, not ported.
- `allowlisted`: a neutral country lookup (the two allowlisted files) or a neutral region word proposed for them.

Binary files `public/local-photos/*.jpg` and `public/product-images/*.jpg` contain the word in their metadata only and are not ported (section B).

### D1. Two data files: every hit is data, replaced by DB rows (disposition `dataset-field`)

| file | hits | lines |
|---|---|---|
| src/lib/competitorProjects.js | 296 | 5, 18, 30, 59, 64, 90, 120, 125, 159, 180, 185, 241, 258, 262, 267, 292, 297, 303, 327, 343, 348, 369, 374, 394, 399, 464, 471, 472, 486, 495, 496, 498, 501, 506, 520, 526, 530, 535, 550, 551, 553, 556, 564, 581, 586, 601, 602, 603, 604, 607, 616, 632, 637, 656, 657, 667, 671, 691, 696, 715, 716, 756, 771, 772, 777, 782, 796, 802, 806, 811, 826, 827, 837, 861, 866, 931, 946, 947, 957, 986, 992, 998, 1003, 1007, 1008, 1010, 1013, 1043, 1048, 1054, 1063, 1064, 1066, 1082, 1108, 1113, 1119, 1127, 1129, 1130, 1131, 1154, 1169, 1170, 1175, 1176, 1186, 1190, 1199, 1200, 1245, 1301, 1326, 1331, 1335, 1351, 1356, 1377, 1386, 1416, 1431, 1433, 1438, 1439, 1445, 1462, 1463, 1468, 1473, 1493, 1498, 1504, 1513, 1516, 1517, 1518, 1519, 1520, 1532, 1552, 1557, 1567, 1576, 1577, 1616, 1626, 1646, 1654, 1675, 1680, 1731, 1737, 1745, 1748, 1777, 1778, 1783, 1788, 1789, 1838, 1889, 1950, 2005, 2010, 2025, 2026, 2028, 2036, 2057, 2075, 2076, 2077, 2078, 2079, 2087, 2108, 2127, 2128, 2133, 2154, 2159, 2178, 2179, 2210, 2229, 2230, 2261, 2280, 2281, 2283, 2286, 2315, 2316, 2321, 2336, 2337, 2338, 2339, 2342, 2371, 2372, 2377, 2396, 2397, 2428, 2442, 2443, 2444, 2445, 2446, 2449, 2458, 2470, 2475, 2480, 2481, 2500, 2525, 2530, 2548, 2549, 2550, 2551, 2552, 2560, 2594, 2600, 2609, 2610, 2611, 2612, 2620, 2630, 2636, 2640, 2645, 2651, 2696, 2730, 2746, 2751, 2769, 2797, 2807, 2814, 2815, 2825, 2840, 2849, 2853, 2889, 2890, 2915, 2956, 2961, 2962, 2971, 2972, 2980, 2987, 2992, 3002, 3007, 3012, 3023, 3027, 3028, 3029, 3034, 3035, 3049, 3094, 3124, 3144, 3149, 3210, 3224, 3225, 3226, 3227, 3228, 3236, 3256, 3261, 3267, 3279, 3282, 3295, 3316, 3322, 3327, 3328, 3333, 3334, 3352, 3397 |
| src/lib/newsLenses.js | 126 | 10, 14, 18, 22, 31, 35, 39, 43, 56, 60, 64, 73, 77, 81, 94, 98, 102, 106, 119, 123, 127, 140, 144, 148, 161, 165, 169, 173, 182, 186, 190, 194, 198, 207, 211, 215, 228, 232, 236, 240, 253, 257, 261, 274, 282, 299, 303, 316, 320, 324, 337, 341, 354, 362, 366, 375, 379, 383, 396, 400, 404, 408, 421, 425, 429, 438, 442, 446, 450, 459, 463, 467, 471, 480, 484, 488, 492, 501, 505, 509, 513, 522, 526, 534, 538, 547, 551, 555, 559, 568, 572, 576, 580, 593, 597, 601, 605, 622, 626, 647, 660, 664, 668, 672, 676, 685, 693, 697, 701, 710, 714, 718, 722, 726, 735, 739, 747, 760, 764, 768, 772, 781, 785, 789, 793, 797 |

### D2. Code, comments and tests (328 hits)

| file:line | matched text | disposition |
|---|---|---|
| src/api/competitorService.js:3 | `/* The 31 tracked rivals: sector, HQ, kVA range, CPCB IV+ readiness, assessment.` | remove-genset |
| src/components/detailPanel/DetailPanel.jsx:143 | `threat: "Threat to Cummins Arabia",` | client-field |
| src/components/detailPanel/DetailPanel.jsx:152 | `}[detail.ksslImpactKind] \|\| "How Cummins Arabia is impacted"}` | client-field |
| src/components/detailPanel/DetailPanel.jsx:269 | `me="eyebrow">Matched {data.client?.short \|\| "Cummins Arabia"} product</span>` | client-field |
| src/components/geoMap/GeoMap.jsx:185 | `?.id] \|\| data.geoData[data.client?.short \|\| "Cummins Arabia"])) \|\|` | client-field |
| src/components/geoMap/GeoMap.jsx:190 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/components/geoMap/GeoMap.jsx:198 | `src, so an analytical estimate (the client's Saudi Arabia and Europe rows are` | remove-genset |
| src/components/marketOutlook/MarketOutlook.jsx:122 | `carry a value (converted to USD by the pack: SAR 0.2667, KWD 3.25). ${win.serviceAwards} of the priced` | remove-genset |
| src/components/marketOutlook/MarketOutlook.jsx:140 | `note={'the kVA and frequency buyers need, against the ${client} catal` | remove-genset |
| src/components/matchupDossier/MatchupDossier.jsx:170 | `<span>{data.client?.short \|\| "Cummins Arabia"} analytics</span>` | client-field |
| src/components/matchupList/MatchupList.jsx:24 | `/* The competitor-product list: kVA band → KSSL anchor product → the rivals paired` | remove-genset |
| src/components/matchupList/MatchupList.jsx:38 | `ide === "client" ? '${data.client?.short \|\| "Cummins Arabia"} products' : p.cat;` | client-field |
| src/components/matchupList/MatchupList.jsx:202 | `<option value="">All {data.client?.short \|\| "Cummins Arabia"} Products</option>` | client-field |
| src/components/matchupList/MatchupList.jsx:272 | `className="ma-koel">{data.client?.short \|\| "Cummins Arabia"}</span> {anchor}{" "}` | client-field |
| src/components/signalCard/SignalCard.jsx:40 | `lassName="kph-label">{data.client?.short \|\| "Cummins Arabia"} Product:</span>` | client-field |
| src/components/tenderCockpit/TenderCockpit.jsx:66 | `<td><span className={'ti-fit ${t.cumminsFit}'}>{FIT[t.cumminsFit]}</span></td>` | client-field |
| src/components/tenderCockpit/TenderCockpit.jsx:82 | `<span className="ovc-note">no genset tender yet: the main contractor buys the gensets once` | remove-genset |
| src/components/tenderCockpit/TenderCockpit.jsx:110 | `<td><span className={'ti-fit ${t.cumminsFit}'}>{FIT[t.cumminsFit]}</span></td>` | client-field |
| src/components/topBar/TopBar.jsx:202 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia"}</span>` | client-field |
| src/lib/categorySymbols.js:5 | `n crosshairs target, Other network, plus the genset-channel set:` | remove-genset |
| src/lib/chat.js:6 | `or kVA band out of the question and answers from the whole co` | remove-genset |
| src/lib/chat.js:27 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/chat.js:180 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/chat.js:227 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/compareProducts.js:27 | `n buildProductIndex(matchups, clientShort = "Cummins Arabia") {` | client-field |
| src/lib/countryFacet.js:196 | `oceania\|global\|worldwide\|scandinavia\|nordics\|gulf\|mena\|emea\|apac)$/i;` | allowlisted |
| src/lib/countryFlags.js:103 | `// Saudi Arabia` | allowlisted |
| src/lib/countryFlags.js:104 | `"saudi arabia": "saudi_arabia",` | allowlisted |
| src/lib/countryFlags.js:105 | `ksa: "saudi_arabia",` | allowlisted |
| src/lib/countryFlags.js:597 | `case "saudi_arabia": {` | allowlisted |
| src/lib/dataset.js:247 | `and the Mitsubishi utility accounts from the Cummins set */` | client-field |
| src/lib/dataset.js:365 | `nce-tech: competitor advancements + advances Cummins Arabia can adopt",` | client-field |
| src/lib/dataset.js:394 | `s: "— defence-tech from elsewhere Cummins Arabia can learn from or adopt" },` | client-field |
| src/lib/dataset.js:432 | `only the measured specs plus kvaDeltaPct (a signed rating delta, a different` | remove-genset |
| src/lib/dataset.js:484 | `.id \|\| d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/dataset.js:550 | `.id \|\| d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/dataset.js:679 | `? "latest tenders that fit Cummins Arabia + perceived opportunities to act on"` | client-field |
| src/lib/dataset.js:718 | `s: "— tenders that fit Cummins Arabia: strong fit, geo presence, high value, closing` | client-field |
| src/lib/dataset.js:720 | `s: "— geopolitical & demand moves Cummins Arabia can act on (no tender required)" },` | client-field |
| src/lib/dataset.js:1046 | `position: (meta && meta.reason) \|\| "No Cummins Arabia filings recorded in this field yet.",` | client-field |
| src/lib/edge.js:8 | `Power Rating (kW)    = Power Rating (kVA) x 0.8000   (sd 0.0009)` | remove-genset |
| src/lib/edge.js:9 | `Engine Output (kW)   = Power Rating (kVA) x 0.8696   (sd 0.0010)` | remove-genset |
| src/lib/edge.js:18 | `is the axis matchups are paired on (nearest kVA` | remove-genset |
| src/lib/edge.js:19 | `o the residual is a pairing artefact: a 3000 kVA set is a different` | remove-genset |
| src/lib/edge.js:20 | `product from a 2500 kVA set, not a better one. The residual is reported separa` | remove-genset |
| src/lib/edge.js:21 | `as the kVA delta.` | remove-genset |
| src/lib/edge.js:23 | `SIZE-DEPENDENT specs are compared per kVA. A 1250 kVA set burns more litres per` | remove-genset |
| src/lib/edge.js:24 | `hour than a 1010 kVA set because it makes more power; per kVA that becomes` | remove-genset |
| src/lib/edge.js:118 | `perKva: false,` | remove-genset |
| src/lib/edge.js:169 | `export function edgeVerdict(e, clientName = "Cummins Arabia") {` | client-field |
| src/lib/edge.js:170 | `const short = (clientName \|\| "Cummins Arabia").toUpperCase();` | client-field |
| src/lib/edge.js:171 | `const name = clientName \|\| "Cummins Arabia";` | client-field |
| src/lib/edge.js:243 | `ok(e([CAL(155, 155), MR(48, 40)]) < 50, "Cummins Arabia worse on range must be <50");` | client-field |
| src/lib/edge.js:244 | `ok(e([CAL(155, 155), MR(40, 48)]) > 50, "Cummins Arabia better on range must be >50");` | client-field |
| src/lib/gapAnalysis.js:8 | `s advantages on different dimensions CANCEL. Cummins vs KG1-750WS` | client-field |
| src/lib/gapAnalysis.js:12 | `kW/kg and sq.m/kVA are not fungible: a buyer does not average their spec` | remove-genset |
| src/lib/gapAnalysis.js:22 | `t led power-to-weight by 29% in the 376-1500 kVA band — on 1 of` | remove-genset |
| src/lib/gapAnalysis.js:256 | `ction gapRivals(matchups, cat, clientName = "Cummins Arabia") {` | client-field |
| src/lib/gapAnalysis.js:347 | `// KSSL's 1 in the 16-75 kVA band, yet its index margin is -9.3, so the bar and` | remove-genset |
| src/lib/gapAnalysis.js:522 | `function gapDimGrid(rivals, clientName = "Cummins Arabia") {` | client-field |
| src/lib/gapAnalysis.js:593 | `val">rival ${tot.win} · level ${tot.level} · Cummins Arabia ${tot.loss}</span>';` | client-field |
| src/lib/gapAnalysis.js:594 | `h += '<span class="ga-acc-label">Cummins Arabia owns vs</span><span class="ga-acc-val">${ksslOw` | client-field |
| src/lib/gapAnalysis.js:661 | `"seg": "Manpower-constrained European, Gulf and East Asian armies, and anyone facing counter-batte` | remove-genset |
| src/lib/gapAnalysis.js:766 | `function gapWhyBlock(rivals, clientName = "Cummins Arabia") {` | client-field |
| src/lib/gapAnalysis.js:812 | `/* The whole right-hand canvas for one kVA band, as one string. Rows carry` | remove-genset |
| src/lib/gapAnalysis.js:820 | `unction gapComparisons(rivals, clientName = "Cummins Arabia", held = 0) {` | client-field |
| src/lib/gapAnalysis.js:869 | `nction gapCategoryBody(rivals, clientName = "Cummins Arabia", held = 0) {` | client-field |
| src/lib/gapModel.js:16 | `8.3, "a$": 5.5, $: 8.3, "€": 9.0, "£": 10.5, aed: 2.26, myr: 1.9 };` | remove-genset |
| src/lib/gapModel.js:22 | `const m = s.match(/(US\$\|A\$\|\$\|€\|£\|AED\|MYR)\s*([\d.]+)\s*(B\|bn\|billion\|M\|mn\|million)?/i);` | remove-genset |
| src/lib/gapModel.js:35 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/gapModel.js:116 | `({ l: x.l, pct: Math.round(-x.raw * 100), perKva: !!x.perKva }));` | remove-genset |
| src/lib/gapModel.js:120 | `({ l: x.l, pct: Math.round(x.raw * 100), perKva: !!x.perKva }));` | remove-genset |
| src/lib/gapModel.js:282 | `> shared category vocabulary, built from the kVA bands` | remove-genset |
| src/lib/geo.js:21 | `ient && (d.client.id \|\| d.client.short)) \|\| "Cummins Arabia";` | client-field |
| src/lib/geo.js:106 | `/* geoKvaSpan's defence equivalent: the "span" of an offering is` | remove-genset |
| src/lib/geo.js:109 | `function geoKvaSpan(txt) {` | remove-genset |
| src/lib/geo.js:131 | `// the genset bands, by rating` | remove-genset |
| src/lib/geo.js:132 | `sub500: "under 500 kVA",` | remove-genset |
| src/lib/geo.js:133 | `mid: "500-1,000 kVA",` | remove-genset |
| src/lib/geo.js:134 | `hhp: "1,001-2,000 kVA",` | remove-genset |
| src/lib/geo.js:135 | `vhhp: "2,001-3,000 kVA",` | remove-genset |
| src/lib/geo.js:136 | `dc: "over 3,000 kVA",` | remove-genset |
| src/lib/geo.js:223 | `Comps also carries customers (telecom tower, data-centre operators),` | remove-genset |
| src/lib/geo.js:263 | `/ two disagree. Caterpillar's row claims "13 kVA - 4000+ kVA" but its catalogue` | remove-genset |
| src/lib/geo.js:264 | `// here starts at 500 kVA, so three of its five bands have no model pair at all.` | remove-genset |
| src/lib/geo.js:330 | `' contest Cummins Arabia here on class-matched models">◉ ${spec} contest` | remove-genset |
| src/lib/geo.js:343 | `return '<span class="gv-good">Cummins Arabia leads ${p.koel} of ${p.graded}</span>';` | remove-genset |
| src/lib/geo.js:345 | `pan class="gv-mid">split - rival ${p.rival}, Cummins Arabia ${p.koel}${p.level ? ', level ${p.level}' : ""}` | remove-genset |
| src/lib/geo.js:350 | `For every overlapping band, each matched Cummins / rival model pair, spec by spec, with who wins each` | remove-genset |
| src/lib/geo.js:352 | `the competitor's value, kv Cummins Arabia's. A pair is ahead for whoever wins more direct` | remove-genset |
| src/lib/geo.js:353 | `d with no matched pair says so and names the Cummins line that would answer it by rating. */` | remove-genset |
| src/lib/geo.js:378 | `koel: ["gc-koel", "Cummins Arabia has the superior product"],` | remove-genset |
| src/lib/geo.js:384 | `["Ratings", /rating\|kva\|kw\b\|prime\|standby/i],` | remove-genset |
| src/lib/geo.js:405 | `-score">${r.dirn ? '${nm.short} ${r.rival} · Cummins ${r.koel} · level ${r.level} (of ${r.dirn} decided row` | remove-genset |
| src/lib/geo.js:407 | `h += lead("rival", nm.short) + lead("koel", "Cummins Arabia");` | remove-genset |
| src/lib/geo.js:408 | `'<table class="gc-tbl"><tr><th>Spec</th><th>Cummins Arabia<br>${escAll(stripCo(x.bf))}</th><th>${nm.short}` | remove-genset |
| src/lib/geo.js:425 | `s own products in this market, each with its Cummins answer ----` | remove-genset |
| src/lib/geo.js:426 | `The list a reader scans first: every genset the rival's catalogue carries, smallest first, with th` | remove-genset |
| src/lib/geo.js:427 | `Cummins model it is matched to (if any) and who wins the datas` | remove-genset |
| src/lib/geo.js:428 | `ProductCompareHtml). A model with no matched Cummins model is listed too and` | remove-genset |
| src/lib/geo.js:429 | `list is the rival's range, not only the part Cummins can answer. */` | remove-genset |
| src/lib/geo.js:438 | `const kvaOf = (p) => {` | remove-genset |
| src/lib/geo.js:439 | `s["Prime rating"])) \|\| "").match(/([\d.]+)\s*kva/i);` | remove-genset |
| src/lib/geo.js:445 | `.filter((p) => /genset/i.test(p.category \|\| ""))` | remove-genset |
| src/lib/geo.js:446 | `.map((p) => ({ p, x: pairOfProduct(p.id), kva: kvaOf(p) }));` | remove-genset |
| src/lib/geo.js:447 | `dRank(a.p.band) - bandRank(b.p.band)) \|\| ((a.kva \|\| 1e9) - (b.kva \|\| 1e9)));` | remove-genset |
| src/lib/geo.js:454 | `rows.length} models · ${paired} matched to a Cummins Arabia model</span></div>';` | remove-genset |
| src/lib/geo.js:455 | `pl-hint">Pick a model to compare it with its Cummins Arabia counterpart on the right.</div>';` | remove-genset |
| src/lib/geo.js:456 | `rows.forEach(({ p, x, kva }) => {` | remove-genset |
| src/lib/geo.js:458 | `? CMP_WORD[r.who] : ["gc-none", "No matched Cummins model"];` | remove-genset |
| src/lib/geo.js:459 | `eta = [p.band ? geoBandLabel(p.band) : null, kva ? '${kva} kVA' : null, p.hz ? '${p.hz} Hz' : null, p.c` | remove-genset |
| src/lib/geo.js:462 | `ter${x ? "" : " none"}"><span class="rc-lab">Cummins Arabia counter</span> ' +` | remove-genset |
| src/lib/geo.js:468 | `right-hand pane: one rival model against its Cummins counterpart` | remove-genset |
| src/lib/geo.js:476 | `No ${nm.name} datasheet row is matched to a Cummins Arabia model of the same rating and frequency${cr && c` | remove-genset |
| src/lib/geo.js:479 | `return { title: '${p.name}: no Cummins counterpart', html: h + "</table></div>" };` | remove-genset |
| src/lib/geo.js:495 | `"<li><b>No Cummins Arabia footprint is on file.</b> Every overlap test co` | remove-genset |
| src/lib/geo.js:496 | `"Cummins Arabia's in the same country, and the served footprint` | remove-genset |
| src/lib/geo.js:497 | `f ‘uncontested’.</b> Rivals may well overlap Cummins Arabia here; nothing " +` | remove-genset |
| src/lib/geo.js:506 | `-why"><span class="gw-l">What this means for Cummins Arabia</span><ul>' +` | remove-genset |
| src/lib/geo.js:507 | `"<li><b>Nothing here contests Cummins Arabia on a like-for-like platform.</b> No rival in th` | remove-genset |
| src/lib/geo.js:508 | `'into ${ct} that meets Cummins Arabia’s ${geoSpanText(k.span)}.</li>' +` | remove-genset |
| src/lib/geo.js:522 | `} rival${rs.length === 1 ? "" : "s"} overlap Cummins Arabia in ${ct}' +` | remove-genset |
| src/lib/geo.js:524 | `'<span class="geo-ov-sp">Cummins Arabia ${geoSpanText(k.span)}</span></div>';` | remove-genset |
| src/lib/geo.js:536 | `out = '<span class="gv-good">Cummins Arabia leads ${r.koel} of ${r.graded}</span>';` | remove-genset |
| src/lib/geo.js:552 | `-why"><span class="gw-l">What this means for Cummins Arabia</span><ul>';` | remove-genset |
| src/lib/geo.js:565 | `.length - spec.length} share a category with Cummins Arabia but have no matched pair on file, so they are l` | remove-genset |
| src/lib/geo.js:569 | `'into ${ct} in a category Cummins Arabia also covers, but no class-matched model pair is` | remove-genset |
| src/lib/geo.js:580 | `", so Cummins Arabia is holding that ground on price, financing or s` | remove-genset |
| src/lib/geo.js:590 | `d: ${open.map(geoBandShort).join(", ")}.</b> Cummins Arabia’s portfolio covers ' +` | remove-genset |
| src/lib/geo.js:592 | `'${open.length === 1 ? "it" : "them"}, so Cummins Arabia quotes unopposed within the tracked set - the h` | remove-genset |
| src/lib/geo.js:594 | `i><b>No open ground here.</b> Every category Cummins Arabia’s portfolio covers in ${ct} is reached by at le` | remove-genset |
| src/lib/geo.js:595 | `so there is no category in this market where Cummins Arabia quotes unopposed.</li>";` | remove-genset |
| src/lib/geo.js:598 | `rint rows on this page · categories from the Cummins Arabia category ' +` | remove-genset |
| src/lib/geo.js:612 | `tip: 'Cummins Arabia - present in ${n} market${n === 1 ? "" : "s"}',` | remove-genset |
| src/lib/geo.js:624 | `tip: 'Overlap with Cummins Arabia not assessed${selCountry ? ' in ${selCountry}'` | remove-genset |
| src/lib/geo.js:630 | `tip: 'No overlap with Cummins Arabia${selCountry ? ' in ${selCountry}' : ""} - no ov` | remove-genset |
| src/lib/geo.js:640 | `tip: 'Overlaps Cummins Arabia${where} - confirmed on class-matched models in` | remove-genset |
| src/lib/geo.js:647 | `tip: 'Shares a category with Cummins Arabia${where}, but no class-matched model pair is on` | remove-genset |
| src/lib/geo.js:660 | `const S = (t) => geoKvaSpan(t);` | remove-genset |
| src/lib/geo.js:675 | `155mm rival product must be countered by the Cummins Arabia artillery line");` | remove-genset |
| src/lib/geo.js:678 | `"a radar row has no like-for-like Cummins Arabia counter",` | remove-genset |
| src/lib/geo.js:768 | `geoKvaSpan,` | remove-genset |
| src/lib/geoBadge.js:85 | `exactly this case -- the Saudi Arabia and Europe rows are both src='syn'. */` | remove-genset |
| src/lib/geoBadge.js:150 | `The client has rows in three places: India, Saudi Arabia and "Europe". Only one of` | remove-genset |
| src/lib/geoBadge.js:152 | `d, which is separately its own row), and the Saudi` | remove-genset |
| src/lib/geoCountries.js:18 | `, Norway, Finland and Taiwan appeared in the Gulf of Guinea. The hash also` | allowlisted |
| src/lib/geoCountries.js:78 | `"Saudi Arabia": [23.8859, 45.0792],` | allowlisted |
| src/lib/globalRequirements.js:4 | `y or supply outside any one buyer's country: Cummins Inc.'s data-centre order book,` | remove-genset |
| src/lib/globalRequirements.js:22 | `"a", title: "T", meta: "Capacity · Global · Data centre · 02 Oct 2026", ago: "02 Oct 2026" }, { id: "c", tit` | remove-genset |
| src/lib/globalRequirements.js:24 | `category !== "Capacity" \|\| r[1].segment !== "Data centre" \|\| r[1].why !== "W") throw new Error("globalRequire` | remove-genset |
| src/lib/marketOutlook.js:30 | `const SEG_ALIAS = { "Data centres": "Data centre", "Grid reliability": "Utility", "Re` | remove-genset |
| src/lib/marketOutlook.js:38 | `/* a market card's meta: "Pipeline · Saudi Arabia · Data centre · 24 Sep 2026" (or without a segm` | remove-genset |
| src/lib/marketOutlook.js:45 | `const revenueOf = (t) => (t.cumminsFit === "poor" ? 0 : Number(t.revenueMid) \|\| 0);` | client-field |
| src/lib/marketOutlook.js:46 | `const fits = (t) => t.cumminsFit === "strong" \|\| t.cumminsFit === "partial";` | client-field |
| src/lib/marketOutlook.js:149 | `const bandOf = (kva) => BANDS.find(([lo, hi]) => kva >= lo && kva < hi);` | remove-genset |
| src/lib/marketOutlook.js:150 | `(hi >= 1e9 ? '${lo.toLocaleString("en-US")}+ kVA' : '${lo.toLocaleString("en-US")}-${hi.toLocaleString(` | remove-genset |
| src/lib/marketOutlook.js:151 | `const kvaOf = (p) => {` | remove-genset |
| src/lib/marketOutlook.js:153 | `tring(s).replace(/,/g, "").match(/([\d.]+)\s*kVA/i);` | remove-genset |
| src/lib/marketOutlook.js:157 | `ient && (d.client.id \|\| d.client.short)) \|\| "Cummins Arabia";` | client-field |
| src/lib/marketOutlook.js:159 | `own, name: p.name, hz: Number(p.hz) \|\| null, kva: kvaOf(p) })));` | remove-genset |
| src/lib/marketOutlook.js:163 | `(d.tenders \|\| []).filter((t) => t.rank && t.cumminsFit !== "poor").forEach((t) => {` | client-field |
| src/lib/marketOutlook.js:165 | `map((n) => byName.get(n)).find((x) => x && x.kva && x.hz))` | remove-genset |
| src/lib/marketOutlook.js:166 | `p((m) => byName.get(m.n)).find((x) => x && x.kva && x.hz);` | remove-genset |
| src/lib/marketOutlook.js:169 | `const b = bandOf(p.kva);` | remove-genset |
| src/lib/marketOutlook.js:177 | `at.filter((p) => p.own && p.hz === r.hz && p.kva && bandOf(p.kva)[0] === r.lo).map((p) => p.name);` | remove-genset |
| src/lib/marketOutlook.js:180 | `(d.tenders \|\| []).filter((t) => t.rank && t.cumminsFit !== "poor").length, rows: out };` | client-field |
| src/lib/marketOutlook.js:253 | `eq: [["Published", "01 Oct 2026"]], rank: 1, cumminsFit: "strong", revenueMid: 1e6, country: "Kuwait", issu` | client-field |
| src/lib/marketOutlook.js:262 | `marketCards: [{ meta: "Pipeline · Saudi Arabia · Service · 02 Oct 2026", title: "S" }, { meta:` | remove-genset |
| src/lib/marketOutlook.js:263 | `", hz: 50, specs: { "Standby rating": "1,100 kVA" } }] }, R: { products: [{ name: "R1", hz: 50, specs:` | remove-genset |
| src/lib/marketOutlook.js:265 | `[{ cat: "Healthcare", status: "evaluation", cumminsFit: "partial", revenueMid: 5, title: "X" }]);` | client-field |
| src/lib/marketOutlook.js:271 | `iced === 2 && z.key === "50 Hz · 1,000-1,250 kVA" && z.covered` | remove-genset |
| src/lib/marketOutlook.js:272 | `ceAwards === 0 && drivers(d)[0].country === "Saudi Arabia"` | remove-genset |
| src/lib/marketOverview.js:319 | `"rather than letting a Cummins Arabia line go unnamed.",` | client-field |
| src/lib/orgident.js:61 | `africa america middle east indo pacific nato gulf scandinavia nordics spain italy norway sweden finland` | remove-genset |
| src/lib/overview.js:680 | `adopt: "advances Cummins Arabia can adopt",` | client-field |
| src/lib/overview.js:726 | `((k) => k !== ((d.client && d.client.id) \|\| "Cummins Arabia")).length;` | client-field |
| src/lib/overview.js:747 | `(k) => k !== ((d.client && d.client.id) \|\| "Cummins Arabia"),` | client-field |
| src/lib/overview.js:749 | `[k]) => k !== ((d.client && d.client.id) \|\| "Cummins Arabia")).reduce((n, [, v]) => n + (v ? v.length : 0),` | client-field |
| src/lib/overview.js:757 | `nst clientId = (d.client && d.client.id) \|\| "Cummins Arabia";` | client-field |
| src/lib/overview.js:784 | `(d.tenders \|\| []).filter((t) => t.rank && t.cumminsFit !== "poor");` | client-field |
| src/lib/overview.js:834 | `if (k !== ((d.client && d.client.id) \|\| "Cummins Arabia") && c.partners) allianceCount += c.partners.le` | client-field |
| src/lib/overview.js:842 | `((k) => k !== ((d.client && d.client.id) \|\| "Cummins Arabia")).length;` | client-field |
| src/lib/overview.js:843 | `) => k !== ((d.client && d.client.short) \|\| "Cummins Arabia")).length;` | client-field |
| src/lib/overview.js:846 | `[k]) => k !== ((d.client && d.client.id) \|\| "Cummins Arabia"))` | client-field |
| src/lib/overview.js:872 | `cnt: "Cummins Arabia products mapped to rival products by spec categ` | client-field |
| src/lib/overview.js:882 | `DATA.length} competitor projects on record · Gulf and worldwide',` | remove-genset |
| src/lib/overview.js:926 | `cnt: "Technology developments tracked across Cummins Arabia product domains",` | client-field |
| src/lib/overview.js:936 | `cnt: "Where Cummins Arabia trails rivals, from the Positioning spec compar` | client-field |
| src/lib/partnerCategories.js:4 | `ys (tech, supply, jv, mou, acq, other), so a genset rival's distributors, dealers,` | remove-genset |
| src/lib/partnerCategories.test.mjs:7 | `const file = new URL("../../../parallax-cummins-arabia-datapack/dataset.html.json", import.meta.url);` | client-field |
| src/lib/partnerCategories.test.mjs:34 | `ef names both parties, the category, and the Cummins read; no raw tags", { skip: !d }, () => {` | client-field |
| src/lib/partnerCategories.test.mjs:40 | `assert.ok(html.includes("What it means for Cummins Arabia") && html.includes("Threat"));` | client-field |
| src/lib/partners.js:658 | `, "#6b6a63", "rgba(120, 118, 110, 0.2)", "No Cummins Arabia overlap"],` | client-field |
| src/lib/partners.js:685 | `t CLIENT_CID = (d.client && d.client.id) \|\| "Cummins Arabia";` | client-field |
| src/lib/partners.js:689 | `competitor (Cummins lists Powerica three times). */` | client-field |
| src/lib/partners.js:757 | `for a channel partner that means three, so Cummins drew three separate nodes` | client-field |
| src/lib/partners.js:1172 | `"saudi arabia": "Saudi Arabia", "suudi arabistan": "Saudi Ara` | remove-genset |
| src/lib/partners.js:1733 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/partners.js:1827 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/partners.js:1858 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/partners.js:1943 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/partners.js:2237 | `nt && (d.client.short \|\| d.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/lib/patents.js:419 | `? '<b>Cummins Arabia holds ${koelFilings} filing${koelFilings !== 1` | client-field |
| src/lib/patents.js:426 | `"<b>No Cummins Arabia filing is recorded in this field.</b> " +` | client-field |
| src/lib/patents.js:463 | `c(l.name)}${l.isClient ? ' <i class="wh-you">Cummins Arabia</i>' : ""}</span>' +` | client-field |
| src/lib/patents.js:482 | `${esc(l.threat)}" title="Assessed threat to Cummins Arabia">${esc(l.threat)}</span>') +` | client-field |
| src/lib/patents.js:506 | `<div class="ws-koel"><span class="ws-koel-l">Cummins Arabia position</span>' +` | client-field |
| src/lib/productLink.js:20 | `] }, A: { products: [{ name: "KD1000" }] }, "Cummins Arabia": { products: [{ name: "C800D6E (S17 Centum Ser` | client-field |
| src/lib/productLink.js:21 | `r(d, "C800D6E (S17 Centum Series)").cid === "Cummins Arabia"` | client-field |
| src/lib/profile.js:46 | `"APFSDS", "ISR", "ISTAR", "SAR", "AESA", "AIS", "SATCOM", "HUD", "FLIR", "IRST",` | remove-genset |
| src/lib/profile.js:320 | `st clientCid = (d.client && d.client.id) \|\| "Cummins Arabia";` | client-field |
| src/lib/profile.js:455 | `st clientCid = (d.client && d.client.id) \|\| "Cummins Arabia";` | client-field |
| src/lib/projects.js:3 | `Gulf reference projects, each read from the dataset's own r` | remove-genset |
| src/lib/projects.js:10 | `{ f: "Gulf", l: "Gulf region" },` | remove-genset |
| src/lib/projects.js:59 | `{ act: "gulf", l: "In the Gulf region", v: String(projects.filter((` | remove-genset |
| src/lib/projects.js:69 | `const ps = [mk("a", "X", "Gulf", 4, 10, "2026-10-01"), mk("b", "Y", "Worldwide", 2, 3` | remove-genset |
| src/lib/projects.js:73 | `ojectFeed({ projects: ps, cid: "X", filter: "Gulf" });` | remove-genset |
| src/lib/projects.test.mjs:7 | `const file = new URL("../../../parallax-cummins-arabia-datapack/dataset.html.json", import.meta.url);` | client-field |
| src/lib/projects.test.mjs:18 | `assert.ok(["Gulf", "Worldwide"].includes(p.region), '${p.id} region');` | remove-genset |
| src/lib/projects.test.mjs:28 | `r with projects on record is covered, in the Gulf and worldwide", () => {` | remove-genset |
| src/lib/projects.test.mjs:31 | `t.ok(PROJECTS_DATA.some((p) => p.region === "Gulf") && PROJECTS_DATA.some((p) => p.region === "Worldwide` | remove-genset |
| src/lib/projects.test.mjs:39 | `assert.equal(cat.counts.Gulf + cat.counts.Worldwide, cat.counts.all);` | remove-genset |
| src/lib/reports.js:13 | `${escAll(m.comp \|\| "")} vs ${escAll(m.bf \|\| "Cummins Arabia")}</div>' +` | client-field |
| src/lib/reports.js:15 | `'<div class="tr-verdict parity"><b>Cummins Arabia specification not publicly disclosed.</b></div>` | client-field |
| src/lib/reports.js:16 | `"")} is a real, sourced competitor mapped to Cummins Arabia's ${escAll((m.bf \|\| "counterpart").replace(/^KS` | client-field |
| src/lib/reports.js:18 | `? '<div class="tr-sec"><div class="tr-sec-h">Cummins Arabia Advantages To Press</div><div class="tr-body">$` | client-field |
| src/lib/reports.js:54 | `</div><div class="trep-class">CONFIDENTIAL · Cummins Arabia</div></div>' +` | client-field |
| src/lib/reports.js:60 | `'<p style="margin-top:6px"><b>Cummins Arabia leads:</b> ${leads.bf.length ? escAll(leads.bf.` | client-field |
| src/lib/reports.js:65 | `div class="trep-sec"><div class="trep-h">3 · Cummins Arabia advantages to press</div><p>${(m.advBf \|\| []).m` | client-field |
| src/lib/reports.js:72 | `- ${escAll(t.country)}, ${escAll(t.value)} · Cummins Arabia match: ${` | client-field |
| src/lib/reports.js:81 | `: ${srcRow ? escAll(srcRow[1]) : "on file"}. Cummins Arabia specs sourced where marked.</div>' +` | client-field |
| src/lib/reports.js:97 | `behind: "Cummins Arabia is BEHIND the leaders",` | client-field |
| src/lib/reports.js:98 | `parity: "Cummins Arabia is AT PARITY",` | client-field |
| src/lib/reports.js:99 | `ahead: "Cummins Arabia is AHEAD",` | client-field |
| src/lib/reports.js:127 | `</div><div class="trep-class">CONFIDENTIAL · Cummins Arabia</div></div>' +` | client-field |
| src/lib/reports.js:132 | `class="trep-h">3 · Strategic implication for Cummins Arabia</div><p>${iv.impact.replace(/<b>\[Analysis\][^<` | client-field |
| src/lib/reports.js:139 | `in this domain where the technology bears on Cummins Arabia's bid:</p>" +` | client-field |
| src/lib/search.js:62 | `nst clientId = (d.client && d.client.id) \|\| "Cummins Arabia";` | client-field |
| src/lib/shortlist.js:94 | `Israeli: "Israel", Saudi: "Saudi Arabia", Egyptian: "Egypt", Turkish: "Turkey",` | remove-genset |
| src/lib/shortlist.js:131 | `(data && data.client && data.client.id) \|\| "Cummins Arabia";` | client-field |
| src/lib/shortlist.js:244 | `eturn { keep: false, reason: "does not hit a Cummins Arabia line" };` | client-field |
| src/lib/shortlist.js:286 | `best) return { keep: false, reason: "outside Cummins Arabia's markets" };` | client-field |
| src/lib/shortlist.js:288 | `rn { keep: true, tier: T2, reason: "a market Cummins Arabia is bidding in, not selling in" };` | client-field |
| src/lib/shortlist.js:290 | `ue, tier: best.tier, reason: "critical, on a Cummins Arabia line, in a Cummins Arabia market" };` | client-field |
| src/lib/shortlist.js:300 | `p: true, tier: null, reason: "critical, on a Cummins Arabia line, in a Cummins Arabia market" };` | client-field |
| src/lib/specs.js:56 | `<div class="sb-side bf"><span class="sb-who">Cummins Arabia</span><span class="sb-num">${specValueWithUnit(` | client-field |
| src/lib/specs.js:95 | `'<span class="sb-who bf">Cummins Arabia</span>' +` | client-field |
| src/lib/specs.js:333 | `an><span class="sb-key"><i class="k-bf"></i> Cummins Arabia</span></div>';` | client-field |
| src/lib/specs.js:358 | `itor stronger</span><span>Parity</span><span>Cummins Arabia stronger</span></div>' +` | client-field |
| src/lib/specs.js:361 | `an><span class="sb-key"><i class="k-bf"></i> Cummins Arabia</span><span class="sb-key"><i class="k-win"></i` | client-field |
| src/lib/specs.js:412 | `? "Cummins Arabia leads"` | client-field |
| src/lib/specs.js:427 | `h += '<div class="mug-desc">Cummins Arabia leads on the fields both products publish. Reco` | client-field |
| src/lib/specs.js:438 | `} in ${esc(m.cat)} that Cummins Arabia can bid on right now. This spec gap directly af` | client-field |
| src/lib/specs.js:440 | `ck a tender to see its full requirements and Cummins Arabia's fit.</div>';` | client-field |
| src/lib/specs.js:448 | `a technology-frontier gap in this category - Cummins Arabia trails the state of the art here too.</div>';` | client-field |
| src/lib/specs.js:451 | `where the technology frontier is moving past Cummins Arabia. It compounds the competitive gap - Cummins Ara` | client-field |
| src/lib/tenderIntel.js:5 | `_fit.py): revenueMid (an ESTIMATE midpoint), cumminsFit, competitorFit,` | remove-genset |
| src/lib/tenderIntel.js:10 | `// chance Cummins Arabia books the genset share, by where the tender sta` | remove-genset |
| src/lib/tenderIntel.js:12 | `// how much of the value a fit grade lets Cummins serve` | remove-genset |
| src/lib/tenderIntel.js:14 | `// decision -> genset purchase order: a direct supply/works tender orders so` | remove-genset |
| src/lib/tenderIntel.js:15 | `award; a main contract / EPC / PPP buys its gensets a year or so after award` | remove-genset |
| src/lib/tenderIntel.js:20 | `// a Cummins set within 12 % of the rival's rating covers it (about` | remove-genset |
| src/lib/tenderIntel.js:21 | `// a 2,188 kVA set against a 1,875 kVA rival is a 17 % oversize, i.e.` | remove-genset |
| src/lib/tenderIntel.js:27 | `hai\|baudouin\|perkins\|fg wilson\|generac\|volvo\|cummins\|aggreko\|altaaqa\|jubaili\|kanoo power\|w[aä]rtsil[aä]\|sie` | remove-genset |
| src/lib/tenderIntel.js:28 | `/* channels whose genset line is a rival brand: a route, but not a neutral one` | remove-genset |
| src/lib/tenderIntel.js:32 | `const fits = (t) => t.cumminsFit && t.cumminsFit !== "poor";` | remove-genset |
| src/lib/tenderIntel.js:38 | `s today. Not a tender that merely contains a genset inside a larger package: a metro` | remove-genset |
| src/lib/tenderIntel.js:42 | `main contracts and pre-tender projects whose genset package is bought later.` | remove-genset |
| src/lib/tenderIntel.js:43 | `nce contract, a construction package with no genset in its title, a` | remove-genset |
| src/lib/tenderIntel.js:45 | `const GENSET_RX = /generator\|genset\|generating set\|back-?up (electr` | remove-genset |
| src/lib/tenderIntel.js:47 | `const direct = (t) => GENSET_RX.test(t.title \|\| "") && !MAIN_RX.test(t.title \|\| "")` | remove-genset |
| src/lib/tenderIntel.js:95 | `return mid(t) * (ASSUME.fitWeight[t.cumminsFit] \|\| 0) * ASSUME.pWin[stageOf(t)];` | remove-genset |
| src/lib/tenderIntel.js:100 | `/* rated kVA and frequency of a catalogue product, from its View Sp` | remove-genset |
| src/lib/tenderIntel.js:103 | `tring(s).replace(/,/g, "").match(/([\d.]+)\s*kVA/i);` | remove-genset |
| src/lib/tenderIntel.js:104 | `return { kva: m ? Number(m[1]) : null, hz: Number(p.hz) \|\| null };` | remove-genset |
| src/lib/tenderIntel.js:115 | `{ k: "Genset revenue in play", v: sum(all.filter((t) => t.cumminsFi` | remove-genset |
| src/lib/tenderIntel.js:116 | `{ k: "Fits a Cummins model today", v: sum(all.filter((t) => t.cumminsFit ==` | remove-genset |
| src/lib/tenderIntel.js:120 | `/* 2. forecast of win-weighted genset orders by quarter */` | remove-genset |
| src/lib/tenderIntel.js:167 | `nst own = catalogue.filter((p) => p.own && p.kva);` | remove-genset |
| src/lib/tenderIntel.js:172 | `if (!rp \|\| !rp.kva) return;` | remove-genset |
| src/lib/tenderIntel.js:174 | `.some((p) => Math.abs(p.kva - rp.kva) / rp.kva <= ASSUME.gapTolerance);` | remove-genset |
| src/lib/tenderIntel.js:179 | `const lo = Math.floor(rival.kva / 250) * 250;` | remove-genset |
| src/lib/tenderIntel.js:180 | `caleString()}–${(lo + 250).toLocaleString()} kVA';` | remove-genset |
| src/lib/tenderIntel.js:220 | `return { t, date: d.date, est: d.est, fit: t.cumminsFit, v: mid(t), cat: t.cat };` | remove-genset |
| src/lib/tenderRow.js:211 | `lean === "go" ? " Graded a strong fit for Cummins Arabia's portfolio."` | client-field |
| src/lib/tenderRow.js:212 | `"maybe" ? " Graded worth qualifying against Cummins Arabia's portfolio."` | client-field |
| src/lib/threat.js:38 | `omer\|buyer)\|spanish\|estonian\|polish\|egyptian\|saudi\|qatari\|for the u\.?s\.? army\|u\.?s\.? army\|european\|na` | remove-genset |
| src/lib/threat.js:65 | `threatWhy: 'Cummins Arabia partners with ${card.company}; its advances are` | client-field |
| src/lib/threat.js:79 | `"Outside Cummins Arabia's product segments (ISR / electro-optics / rada` | client-field |
| src/lib/threat.js:91 | `threatWhy: "An Indian / MoD procurement in a Cummins Arabia product line — a direct home-market threat.",` | client-field |
| src/lib/threat.js:101 | `"A foreign export win in a Cummins Arabia line — it does not touch Cummins Arabia's prote` | client-field |
| src/pages/competitive/GapAnalysis.jsx:33 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Geo.jsx:40 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Geo.jsx:281 | `range/.test(p.name \|\| "") \|\| /diesel and gas gensets/.test(p.name \|\| "") \|\| p.c === "bf";` | remove-genset |
| src/pages/competitive/Geo.jsx:536 | `ta[data.client?.id \|\| data.client?.short \|\| "Cummins Arabia"] \|\|` | client-field |
| src/pages/competitive/Geo.jsx:690 | `ta[data.client?.id \|\| data.client?.short \|\| "Cummins Arabia"] \|\|` | client-field |
| src/pages/competitive/Partnerships.jsx:27 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Partnerships.jsx:40 | `Order.find((k) => k !== (data.client?.id \|\| "Cummins Arabia") && data.competitors[k])) \|\| null;` | client-field |
| src/pages/competitive/Partnerships.jsx:42 | `d] && savedPart.cid !== (data.client?.id \|\| "Cummins Arabia")` | client-field |
| src/pages/competitive/Partnerships.jsx:164 | `id: (data.client && data.client.id) \|\| "Cummins Arabia",` | client-field |
| src/pages/competitive/Partnerships.jsx:177 | `der.filter((k) => k !== (data.client?.id \|\| "Cummins Arabia") && data.competitors[k]),` | client-field |
| src/pages/competitive/Partnerships.jsx:195 | `ientId = (data.client && data.client.id) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Partnerships.jsx:271 | `.filter((k) => k !== (data.client?.id \|\| "Cummins Arabia"))` | client-field |
| src/pages/competitive/Patents.jsx:25 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Positioning.jsx:138 | `ame = (data.client && data.client.short) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Positioning.jsx:148 | `ort = (data.client && data.client.short) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Positioning.jsx:253 | `<div className="pn">{data.client?.short \|\| "Cummins Arabia"} · —</div>` | client-field |
| src/pages/competitive/Products.jsx:629 | `sideB: m.bf \|\| "Cummins Arabia Counterpart",` | client-field |
| src/pages/competitive/Products.jsx:734 | `entCid = (data.client && data.client.id) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Products.jsx:735 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/pages/competitive/Products.jsx:989 | `let name = rawBf.replace(/^(KSSL\|Cummins Arabia)\s*·\s*/i, "").trim();` | client-field |
| src/pages/competitive/Products.jsx:1852 | `assName="pc-tag">{p.series \|\| p.category \|\| "Genset"}</span>` | remove-genset |
| src/pages/competitive/Products.jsx:1866 | `{p.specs && p.specs["Data centre rating"] ? "Data-centre rated" : ""}` | remove-genset |
| src/pages/competitive/Projects.jsx:12 | `competitor is working on or pursuing, in the Gulf and worldwide. The competitors are` | remove-genset |
| src/pages/competitive/Projects.jsx:54 | `["Region", p.region === "Gulf" ? "Gulf region" : "Worldwide"], ["Stage", p.stage],` | remove-genset |
| src/pages/competitive/Projects.jsx:92 | `v className="pj-note">The analyst's read for Cummins Arabia, from the dataset's record of this item.</div>` | client-field |
| src/pages/market/MarketOverview.jsx:648 | `generator supply, standby power and genset O&amp;M contracts already awarded, newest first · {fmt` | remove-genset |
| src/pages/market/Tenders.jsx:97 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/pages/overview/Overview.jsx:90 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/pages/technology/Innovation.jsx:24 | `(data.client.short \|\| data.client.name)) \|\| "Cummins Arabia";` | client-field |
| src/state/DataProvider.jsx:92 | `Could not load the Cummins Arabia dataset - {error}` | client-field |
| src/styles/geo.css:94 | `irst-child{white-space:nowrap}   /* "(> 1500 kVA)" must not break */` | remove-genset |
| src/styles/geo.css:626 | `beside the popup the list column is narrow: Cummins' answer column is shown in the popup, so drop it here` | client-field |
| index.html:6 | `<title>137Parallax — Cummins Arabia Competitive Intelligence</title>` | client-field |
| public/ops/twin.html:215 | `/* Datacentre crawler panels */` | remove-genset |
| public/ops/twin.html:290 | `<h2>Datacentre crawler · live <span class="h2note" id="crawlNote"><` | remove-genset |
| public/ops/twin.html:347 | `/* ---------- Datacentre crawler (vite proxies /crawler -> VPS crawl dashboar` | remove-genset |
| public/ops/twin.html:479 | `plain:"Bots at the datacentre fetch pages from ~500 defence sources — company site` | remove-genset |

Totals: allowlisted 7, client-field 149, dataset-field 422, remove-genset 172 (all 750 hits).

## E. Labels and UI config

> **Chrome restore (binding).** Section E below mapped every label to a `ui.*` column and the front end once read them. That
> is reversed: those labels are front-end code (`src/lib/route.js`, `src/lib/chrome.js`) exactly as the Cummins UI defines
> them, and the front end reads no chrome `ui` table. Only the serving tables are data. The E5 helper `uiText.js` and
> `lanes.js` are deleted. The mapping rows below stay as a record of which `ui` column is the nearest equivalent.


Ruling R2: every on-screen label or config the Cummins UI hardcodes, mapped to an existing `ui.*` table and column where one exists (the backend then ships it and the UI reads it). Client or domain words (client name, products, categories, countries, units) always come from the data. Neutral chrome with no `ui.*` table stays in code and is listed as `chrome`. Every `ui-table` entry names one `schema.table.column` and, where the table has several rows, the row key (`where col = value`). The UI reads it from `data.database` with `uiText()` (see the top of this file); no new global. A label either comes from a real text column or is neutral `chrome`; there is no literal fallback for a missing DB value.

### E1. Shell, navigation, pillars

| label/config | where (file) | disposition |
|---|---|---|
| Pillar name Market | route.js PILLAR_LABEL; TopBar.jsx; AppState.jsx; SubHead.jsx | ui-table ui.market_pillar.display_name (the single row) |
| Pillar name Technology | same | ui-table ui.technology_pillar.pillar_name (the single row) |
| Pillar name Competitive | same | chrome (no text column exists: ui.competitive_pillar.active_pillar holds the code 'competitive', not a label) |
| Pillar order competitive, market, technology | route.js PILLARS | chrome |
| Wordmark "137Parallax" (the product brand, not the client) | TopBar.jsx; DataProvider.jsx boot screens | chrome |
| Browser tab title | index.html:6 | dataset-field: document.title is set at runtime to client.short (serving.client_account.brand_name); the static html carries only the chrome word "137Parallax" |
| Client chip in the top bar | TopBar.jsx:202 | dataset-field client.short (serving.client_account.brand_name) |
| Search box placeholder "Search intelligence (Ctrl+K)" | TopBar.jsx | chrome (one global control; the ui placeholders are per pillar or view) |
| Search result group names (Competitors, Products, Signals & Intel, Tenders, Innovations), "No results for", "Searched ..." scope sentence | search.js GROUP_LABEL; TopBar.jsx | chrome (counts in the sentence are derived-ok) |
| Print Report button text and print sheet title "137PARALLAX INTELLIGENCE BRIEF" | SubHead.jsx; report.js HDR | chrome (ui.competitive_pillar.print_report_action is a boolean; ui.market_pillar.print_report_label and ui.technology_pillar.print_report_label exist but the Cummins UI has one button for all pillars) |
| Rail item Overview (competitive) | route.js RAIL; Sidebar.jsx | ui-table ui.competitive_navigation.view_label where view_key='overview' |
| Rail item Competitor Profile | same | ui-table ui.competitive_navigation.view_label where view_key='profile' |
| Rail item Competitor Moment (view threat-analysis) | same | ui-table ui.competitive_navigation.view_label where view_key='moment' |
| Rail item Products | same | ui-table ui.competitive_navigation.view_label where view_key='products' |
| Rail item Product Evaluation (view positioning) | same | ui-table ui.competitive_navigation.view_label where view_key='evaluation' |
| Rail item Partnership (view partnerships) | same | ui-table ui.competitive_navigation.view_label where view_key='partnerships' |
| Rail item Projects | same | ui-table ui.competitive_navigation.view_label where view_key='projects' |
| Rail item Geo Footprint | same | ui-table ui.competitive_navigation.view_label where view_key='geo' |
| Rail item Patent (view patents-comp) | same | ui-table ui.competitive_navigation.view_label where view_key='patents' |
| Rail item Top opportunity (view m-overview) | route.js RAIL | ui-table ui.market_view.rail_label where view_id='top-opportunity' |
| Rail item Tenders (view tender) | same | ui-table ui.market_view.rail_label where view_id='tenders' |
| Rail item Global Requirements (view global-requirement) | same | ui-table ui.market_view.rail_label where view_id='global-requirement' |
| Rail item Market Intelligence (view m-report) | same | ui-table ui.market_view.rail_label where view_id='market-intelligence' |
| Rail item Overview (technology) | route.js RAIL | ui-table ui.technology_ui_view.view_label where view_key='overview' |
| Rail item Innovations (view innovation) | same | ui-table ui.technology_ui_view.view_label where view_key='innovation' |
| Rail order | Sidebar.jsx | ui-table order columns: ui.competitive_navigation.view_sequence, ui.market_view.rail_order, ui.technology_ui_view.display_order |
| Rail index numbers 01, 02, ... | route.js RAIL.ix | chrome |
| Rail count badges | Sidebar.jsx; overview.js navCounts | derived-ok counts (the ui.*.record_count / rail_count columns are not used) |
| Page heading of each competitive view | Layout.jsx; overview.js viewMetaFor.title | ui-table ui.competitive_navigation.view_label (same row as the rail item) |
| Page heading of each market view | same | ui-table ui.market_view.view_title (same row as the rail item) |
| Page heading of each technology view | same | ui-table ui.technology_ui_view.page_heading (same row as the rail item) |
| Page count lines ("N companies tracked · everything we track on one rival", "Demand shape, spec and requirement", ...) | overview.js viewMetaFor.cnt; Layout.jsx | chrome (counts derived-ok; neutral words only). Phrases naming the client or a region ("<client> products mapped to rival products", "Gulf and worldwide", "tracked across <client> product domains") use data.client.short or are dropped |
| Hidden-view titles Finances, Gap Analysis | overview.js viewMetaFor | hidden:finances, hidden:gap-analysis |
| Boot messages, error and Retry text | DataProvider.jsx | chrome (no client name in the text) |
| Empty-view notice "no view named ... pick one from the rail" | Layout.jsx | chrome |

### E2. Overview feed (all three pillars)

| label/config | where (file) | disposition |
|---|---|---|
| Sequence control label and menu, technology overview | overview.js SEQ_OPTIONS, SEQ_LABEL; FeedFilters.jsx | ui-table ui.technology_ui_view.sequence_label and sequence_options (jsonb [{code, label}]) where view_key='overview'; the stored codes newest / oldest / threat are implemented as sorts (date desc, date asc, direction then date) |
| Sequence control label and menu, competitive and market overview | same | chrome (words "Sequence", "Priority (threats first)", "Most recent"; no text column exists for these two pillars) |
| Feed search placeholder, technology | FeedFilters.jsx | ui-table ui.technology_ui_view.search_placeholder where view_key='overview' |
| Feed search placeholder, competitive and market | FeedFilters.jsx | chrome ("Search") |
| Direction pills All / Threat / Watch (competitive) | dataset.js overviewConfig filters; overview.js | chrome keyed by the stored direction code (threat, watch) |
| Direction pill and group heading "Competitor advances" (technology) | dataset.js groups, filters | ui-table serving.technology_metric.metric_label where metric_key='competitor_advances' |
| Direction pill and group heading "Adoptable" (technology) | same | ui-table serving.technology_metric.metric_label where metric_key='adoptable' |
| Direction pill and group heading "Latest tenders" (market) | dataset.js groups, filters | ui-table ui.market_top_opportunity_view.latest_tenders_metric_label (single row) |
| Direction pill and group heading "Perceived opportunities" (market) | same | ui-table ui.market_top_opportunity_view.perceived_opportunities_metric_label (single row) |
| Pill "All" and group straplines | dataset.js | chrome ("All"); straplines deleted |
| Direction words on cards (Threat, Watch, Advancement, Adoptable, TENDER, OPPORTUNITY) | dataset.js dirWord, tagWord; Overview.jsx; DetailPanel.jsx DIR_WORD | chrome keyed by the stored code |
| Tiles competitive: Competitive threats / Watch signals / Companies tracked | overview.js metricsFor | ui-table ui.competitive_metric.metric_label where metric_key in ('threats','watch','companies_tracked') (metric_key is the new column of C3). The tile value is a browser count chosen by the key; a key with no row draws no tile |
| Tiles technology: Competitor advances / Adoptable / Innovations tracked | overview.js metricsFor | ui-table serving.technology_metric.metric_label where metric_key in ('competitor_advances','adoptable','innovations_tracked'). The value is a browser count chosen by the key (innovations_tracked replaces the Cummins "Domains tracked", counted over innovations) |
| Tiles market top opportunity: Latest tenders / Strong fits / Tender value / Perceived opportunities | overview.js metricsFor; dataset.js | ui-table ui.market_top_opportunity_view.latest_tenders_metric_label, strong_fits_metric_label, tender_value_metric_label, perceived_opportunities_metric_label (single row); the unit note for the value tile is tender_value_metric_note |
| Tiles market report: Active tenders / Markets / Source portals / Value disclosed | marketOverview.js marketMetrics | ui-table ui.market_metric.metric_label where metric_id in ('active-tenders','markets','source-portals','value-disclosed') |
| Tiles projects: Projects tracked / Competitors covered / Read as a threat | projects.js projectMetrics | chrome (ui.ui_project_metric rows belong to a view state, not to the page); the Gulf tile is removed (remove-genset) |
| Blank tiles "Analytical lenses" and "All signals" | overview.js BLANK_TILES; MetricsStrip.jsx | chrome (drawn as empty placeholders, no text) |
| Tile binding | overview.js metricsFor; marketOverview.js | binding is by key, never by label text: competitive ui.competitive_metric.metric_key (C3), technology serving.technology_metric.metric_key, market report ui.market_metric.metric_id, market top the four fixed columns of ui.market_top_opportunity_view. The label text of a row can change in the DB without breaking a count |
| Tile units and value-disclosed total | overview.js; marketOverview.js | dataset-field: per-currency totals from serving.market_tender.value_amount + value_currency (ruling R9), e.g. "USD 1.2 bn · EUR 9 m"; no "USD m" literal |
| Tile warning subs ("no served threat signal is assigned a threat direction - not assessed", "not wired - no measurement ...") | overview.js metricsFor | chrome (honest-empty text) |
| Tile sub-line TILE_LABELS (contested bids, by value; ... sorted by relevance; advances <client> can adopt) | overview.js TILE_LABELS; Layout.jsx | chrome; the client phrase uses data.client.short |
| Empty-feed and filter notes ("no signals served yet", "no signals match this filter") | overview.js emptyFeedNote; Overview.jsx | chrome (ui.competitive_overview_feed.empty_message is a message per filter-state row, not one text) |
| Pager "showing 1-50 of N", Prev, Next | Overview.jsx | chrome |
| "date not known" | overview.js NO_DATE_LABEL | chrome (the "severity not assessed" label is not rendered, ruling R5) |
| Time and size constants: FEED_PAGE_SIZE 50, ATTENTION_DAYS 14, ATTENTION_HEAD 20, TECH_ATTENTION_HEAD 30, SEARCH_MIN_CHARS 2, search limits | overview.js; search.js | chrome (UI tuning, not content) |
| Signal detail eyebrows: At a glance, What the article says, Key points, Source, Provenance, Close | DetailPanel.jsx | chrome (ui.technology_overview_detail_panel has one row per article, and the competitive lane has no equivalent table) |
| Impact eyebrow ("Threat to <client>", "Demand in a client line", "Technology advance", "Competitor advance", "How <client> is impacted") | DetailPanel.jsx:143-152 | dataset-field serving.competitive_signal_detail.impact_eyebrow (replaces the hardcoded map) |
| Tender-detail eyebrows ("Tender", "What this tender is about", "Matched <client> product") | DetailPanel.jsx | chrome (client from data) |
| Card caption "<client> Product:" | SignalCard.jsx | chrome (client from data) |

### E3. Market pillar

| label/config | where (file) | disposition |
|---|---|---|
| Top opportunity page heading | Layout headTitle | ui-table ui.market_top_opportunity_view.page_heading (single row) |
| Section titles Top tenders / Projects to win before they tender / Next moves | TenderCockpit.jsx eyebrows | ui-table ui.market_top_opportunity_view.top_tenders_section_label, projects_section_label, next_moves_section_label |
| Section notes under each title (ranking and estimate caveat) | TenderCockpit.jsx ovc-note | ui-table ui.market_top_opportunity_view.top_tenders_description, projects_description, next_moves_description |
| Cockpit column headers (Rank, Tender, Decides, <client> fit, <client> model, Rival to beat, Revenue; Project, Where it stands; Due, Action) | TenderCockpit.jsx | chrome (client word from data.client.short) |
| Fit grade words (Good, Partial, Not a fit) | TenderCockpit.jsx FIT | dataset-field: the stored serving.market_top_opportunity_tender.kssl_fit text is printed as it is; the map is deleted (stored words strong / partial / weak, ruling R7) |
| Market Intelligence tab "Market outlook" | MarketOverview.jsx SECTIONS | ui-table ui.market_intelligence_tab.tab_label where tab_id='outlook'; a tab with no row is not drawn |
| Market Intelligence tab "Number of active tenders" | same | ui-table ui.market_intelligence_tab.tab_label where tab_id='active' |
| Market Intelligence tab "By category" | same | ui-table ui.market_intelligence_tab.tab_label where tab_id='by-category' |
| Market Intelligence tabs "Awarded" and "Closed" | same | ui-table ui.market_intelligence_tab.tab_label where tab_id='awarded' / 'closed' |
| Tab order | same | ui-table ui.market_intelligence_tab.tab_order |
| Tenders page heading and sort note | Tenders.jsx; tenderRow.js | ui-table ui.market_tenders_view.page_heading and sort_label where view_code='tenders' |
| Country / Category filter labels (tenders and Market Intelligence) | Tenders.jsx; MarketOverview.jsx | ui-table ui.market_tenders_view.country_filter_label, category_filter_label where view_code='tenders' |
| Filter bar word "Filter", "All (N)", "Clear" | MarketOverview.jsx; Tenders.jsx | chrome |
| Market Intelligence block titles (Where demand is heading, Who wins, Repeat buyers, What is driving it) and column headers | MarketOutlook.jsx | chrome; "Sizes buyers need" and the kVA columns are removed (remove-genset) |
| Closing-window buckets (1-7 days, 8-14, 15-30, 30+, No date published) | marketOverview.js WINDOWS | chrome (date-window labels) |
| Past awards headings and columns (Past awards, Awarded, Contract, Winner, Value, Bids, Source) | MarketOverview.jsx | chrome |
| Chart palette hues | marketOverview.js SERIES; MarketOverview.jsx WINDOW_COLORS | chrome |
| Tender assessment panel headings (Tender Assessment, Tender details, What the tender requires, Matched <client> products, Expected revenue (estimate), Competitor fit, Source) | Tenders.jsx | chrome (ui.market_tender_assessment_view holds one row per tender with the tender title in panel_title, so it is not a label table) |
| Tender call-to-action ("Open the tender notice", "Open the tender portal", "Read the award announcement", "Pursue this tender") and its note | Tenders.jsx ctaLabel, ctaNote | chrome keyed by the stored url_kind (notice, portal, award) |
| Tender parameter labels (Buyer, Country, Category, Value, Quantity, Published, Closing date, Status, Source) and "not on record" | tenderRow.js TENDER_PARAMS, NOT_ON_RECORD | chrome |
| Tender requirement row codes: description, scope_text, requirement_note, equipment_scope, rating_band, use_case, quantity, category_text, source_text, published_date, closing_date -> Description, Scope, Note, Equipment, Rating band, Use case, Quantity, Category, Source, Published, Closing date. A code not in this list is a stored scope_bullet_label and prints as stored | tenderRow.js reqLabel (used by Tenders.jsx, chat.js); marketOutlook.js and tenderRow.js read published_date / closing_date / quantity by code | chrome (the backend writes no English label, ruling R12) |
| Fit words on the cockpit (strong / partial / weak) and the "What to do" sentence per segment | TenderCockpit.jsx; MarketOutlook.jsx | dataset-field: the stored kssl_fit word and serving.market_segment_assessment.recommendation print as they are (read from data.database.serving.market_segment_assessment); a segment with none shows a dash |
| Tenders empty state | Tenders.jsx | ui-table ui.market_view.empty_state_text where view_id='tenders' |
| Top opportunity empty state | Overview.jsx; TenderCockpit.jsx | ui-table ui.market_view.empty_state_text where view_id='top-opportunity' |
| Market Intelligence empty state | MarketOverview.jsx | ui-table ui.market_view.empty_state_text where view_id='market-intelligence' |
| Global Requirements page heading | GlobalRequirement.jsx; Layout.jsx | ui-table ui.market_global_requirement_view.page_heading (single row) |
| Global Requirements filter labels and empty text | same | ui-table ui.market_global_requirement_filter.filter_label where filter_type='country' / 'category' / 'status'; ui.market_global_requirement_view.empty_state_text |

### E4. Competitive pillar

| label/config | where (file) | disposition |
|---|---|---|
| Moment time-window chips | ThreatAnalysis.jsx PRESETS | ui-table ui.competitive_competitor_moment_time_window.time_window_label, with day_count for the window and is_default for the preselected chip (order display_order). The stored windows (30d, 90d, 1y) replace Today / Week / Month; an "All dates" chip is chrome |
| Moment level words and tag class | ThreatAnalysis.jsx LEVEL_WORD, PILL, DIR | ui-table ui.competitive_competitor_moment_level.level_label and tag_class where level_code = the moment's stored grade |
| Moment panel headings (At a glance, What happened, Analysis, Deeper analysis by view, Source) | ThreatAnalysis.jsx | chrome ("Analysis - what it means for <client>" uses data.client.short) |
| Profile section titles and field names (Company Details, Starting Year, Headquarters, Global Locations, Company Size, Annual Revenue / Sales, Industry / Sector, Leadership, Company Latest News) | Profile.jsx | chrome |
| Profile titles Strategic Positioning, Parallax Read, Strengths, Weaknesses | Profile.jsx | hidden:strategic-positioning, hidden:parallax-read, hidden:swot |
| Profile news windows (Last 30 days, 3 months, 6 months, 12 months, All time) and list range options | news.js NEWS_WINDOWS; Profile.jsx | chrome (date windows) |
| Profile origin and revenue filters ("All origins (N)", "All revenue tiers") | Profile.jsx; revenueFacet.js | chrome; the tier words are the stored serving.competitive_competitor.revenue_tier |
| "Origin not established" | Profile.jsx UNKNOWN_ORIGIN | chrome |
| Honest-empty strings (NOT_COLLECTED: no officer named, no plant named, no revenue published, no dated event) | profile.js NOT_COLLECTED | chrome |
| Products sidebar filters and search placeholders, "Latest news naming <product>" | Products.jsx | chrome |
| Product group name for a product with no category | Products.jsx formatCategoryTitle, groupedProducts; marketOverview.js catOf | dataset-field: the stored category; none stored shows the em dash (no invented "Defence Systems" or "Uncategorised") |
| Product evaluation tab Analytics | MatchupDossier.jsx TABS | ui-table ui.competitive_positioning_tab.tab_label where tab_code='analytics' |
| Product evaluation tab Spec Comparison | same | ui-table ui.competitive_positioning_tab.tab_label where tab_code='spec_comparison' |
| Product evaluation tab order and enable flag | same | ui-table ui.competitive_positioning_tab.display_order; is_enabled=false hides the tab |
| Product evaluation list labels (Competitor Products, All Companies, All Categories, All <client> Products, All Countries, Compare Any Two Products, Select a rival model) | MatchupList.jsx; Positioning.jsx | chrome (client from data) |
| Edge gauge words (<CLIENT> AHEAD, NEAR PARITY, <CLIENT> BEHIND, INSUFFICIENT MEASURED DATA) and scale labels | edge.js edgeVerdict; specs.js | chrome (client from data); the 58 / 42 bands are a presentation threshold over the stored edge_score |
| Partnership drawer headings (Relationships, Intelligence, Structural weaknesses, What their web reveals, Field-level read, All tracked sources) | partners.js; Partnerships.jsx | chrome |
| Partner relationship type names, short names and definitions | partnerCategories.js; partners.js | ui-table ui.partner_category.category_label, short_label, definition where category_key = slug(partner_type) (new table, C1) |
| Overlap kind headings and effects | partners.js OV_DEF | ui-table ui.partner_overlap_kind.kind_label, lead; ui.partner_overlap_effect.effect_title, effect_text (new tables, C1) |
| Overlap badge text ("Overlapping Partner", "Direct Partner", "No <client> overlap") | partners.js OVERLAP_BADGE | chrome (client from data) |
| Projects filter labels | projects.js PROJECT_FILTERS; Projects.jsx | ui-table ui.ui_project_filter.filter_label where filter_code = the code (is_default marks the preselected); the "All" pill is chrome; the Gulf pill exists only if the table has such a row |
| Projects sequence menu | projects.js PROJECT_SEQ | ui-table ui.ui_project_sequence_option.sequence_label where sequence_code in (recent, stage, value); "Largest (MW)" is removed |
| Projects stage stepper | projects.js STAGE_WORDS; Projects.jsx | ui-table ui.ui_project_stage_step.stage_name (order stage_order) |
| Projects stance words (Threat, Watch) | projects.js STANCE_WORD | chrome keyed by the stored stance code |
| Projects panel headings (At a glance, What the project is, Current stage, Specs, Timeline, Strategic assessment, Source, "Researched to <date>") | Projects.jsx | chrome; the note "The analyst's read for <client>" uses data.client.short |
| Geo dropdown labels (Company, Country) | Geo.jsx | ui-table ui.competitive_geo_filter.filter_label where filter_type='company' / 'country'; option text "All companies" / "All countries" is ui.competitive_geo_filter.option_label where selected_value='all' |
| Geo activity words | actLabel; geoBadge.js; Geo.jsx | dataset-field: the stored serving.competitive_geo_product.activity_type word is the label and its slug the CSS class (see A: geoData row.c); the Cummins words are deleted |
| Geo role words (Head office, Competitor) and badges ("<client> Absent - Contested Market", "<client> Present", "No activity on file") | geoBadge.js | chrome (client from data) |
| Patents lens buttons (By rival, By technology field), list placeholders, stat labels (Granted, Filed, Pending, Filings, Assignees) | Patents.jsx; patents.js | chrome |
| Patents crowding words (Open field, Emerging, Crowded, Locked up) | patents.js crowdMap | chrome keyed by the stored serving.patent_field_assessment.crowding value (open, emerging, crowded, locked) |
| Patent honest states ("status not captured", "grant no. not captured", "Live patent search not yet connected", "Search failed") | patents.js | chrome |

### E5. Technology pillar

| label/config | where (file) | disposition |
|---|---|---|
| Overview page heading | Layout.jsx; dataset.js (title "Technology Knowledge") | ui-table ui.technology_ui_view.page_heading where view_key='overview' |
| Innovation page heading | Innovation.jsx | ui-table ui.technology_ui_view.page_heading where view_key='innovation' |
| Innovation category tab names | Innovation.jsx | ui-table serving.technology_category_ui_label.ui_name (already shipped as techCats[].name) |
| Innovation list heading | Innovation.jsx | ui-table ui.technology_innovation_view.list_heading (single row); empty text ui.technology_innovation_view.empty_state_text |
| Innovation maturity words | innovation.js MAT_LAB; reports.js | dataset-field serving.technology_innovation_status.maturity_label (the stored maturity code stays the colour key) |
| Innovation position words (<client> behind / at parity / ahead) | Innovation.jsx GAP_LAB, GAP_HEAD, GAP_VERB | dataset-field serving.technology_innovation_status.position_label; pill words GAP / WATCH / AHEAD are chrome keyed by the stored client_position; headings "Why <client> is behind..." are chrome (client from data) |
| Innovation detail headings (Innovation Detail, Why this matters to <client>, What's new, Background - what it is, Status, Maturity, Driven by, Horizon, Sources) | Innovation.jsx | chrome (ui.technology_innovation_detail_panel holds one row per innovation with the title in panel_title) |
| "not assessed", "not stated" | innovation.js NOT_ASSESSED, NOT_STATED | chrome |

### E6. Hidden by ui.section_visibility (labels stay in code and are gated with the section)

| label/config | where (file) | disposition |
|---|---|---|
| Gap Analysis labels, Gap strip in the matchup dossier, "Why this gap matters" | GapAnalysis.jsx; gapAnalysis.js; specs.js matchupGapHtml | hidden:gap-analysis |
| Finances page | Finances.jsx | hidden:finances |
| Stock card, price history, tickers | Profile.jsx; mockStockHistory.js; tickers.js | hidden:stock |
| Parallax Read, Strengths, Weaknesses, Strategic Positioning | Profile.jsx | hidden:parallax-read, hidden:swot, hidden:strategic-positioning |
| Product photos and keyword stock images | Products.jsx; Thumb.jsx | hidden:product-images |
| Chat dock, scoped chat, Ask box | MalloryChat.jsx; ScopeChat.jsx; AskBox.jsx; chat.js | hidden:chat |

### E5. Task 11 fix round 1: what is wired, what was decided

The helper is `src/lib/uiText.js` (`uiText`, `uiList`, `filterOptions`, `stanceWords`): a stored cell or "", never a literal. The lanes are built in `src/lib/lanes.js`.

New table (db/setup/09_ui_port_tables.sql, staging_ui + ui, guard trigger, seeded in db/test_seed_full/90_ui_port.sql): `ui.filter_option(filter_group, option_code, option_label, badge_label, display_order)`, PK (filter_group, option_code). One row per filter pill and card badge word. Groups: `stance` (threat, watch: the only stances), `market-feed` (tenders, opportunities), `technology-feed` (competitor-advances, adoptable). It supersedes the E2 rows that mapped the market and technology pills to metric label columns. A group with no rows draws no pills; a stance row under any code other than threat or watch is ignored.

| label/config | wired to | status |
|---|---|---|
| Competitive overview tiles | ui.competitive_metric.metric_label where metric_key in (threats, watch, companies_tracked); bound by key | wired |
| Competitive overview pills, badge words, DetailPanel and Projects stance words | ui.filter_option group `stance` | wired |
| Competitive overview heading "Competitive Intelligence" | no ui column holds it | chrome (decision; the other competitive headings are the stored view_label) |
| Technology tiles | serving.technology_metric.metric_label where metric_key in (competitor_advances, adoptable, innovations_tracked); bound by key; innovations_tracked counts innovations | wired |
| Technology pills, group headings, badge (Adoptable) | ui.filter_option group `technology-feed` | wired |
| Technology heading, sequence menu, sequence label, search placeholder | ui.technology_ui_view (page_heading, sequence_options newest/oldest/threat, sequence_label, search_placeholder) | wired |
| Market top-opportunity tiles | ui.market_top_opportunity_view four metric label columns; bound by the column | wired |
| Market top-opportunity heading | ui.market_top_opportunity_view.page_heading | wired |
| Market feed pills, group headings, TENDER / OPPORTUNITY badges | ui.filter_option group `market-feed` | wired |
| Market report tiles | ui.market_metric.metric_label by metric_id | wired |
| Rail labels, rail order, page headings (three pillars) | ui.competitive_navigation, ui.market_view, ui.technology_ui_view; a view with no row is not drawn | wired |
| Market Intelligence tabs (label, order) | ui.market_intelligence_tab; a tab with no row is not drawn | wired |
| Moment time-window chips and the Profile news windows | ui.competitive_competitor_moment_time_window (label, day_count, is_default); the "All" reset chip is chrome | wired |
| Moment level words and class | ui.competitive_competitor_moment_level; only a threat or watch tag draws a word or a pill | wired |
| Country, category, revenue, origin filters (options and counts) | distinct stored values of the rows on screen; the word "All" is chrome | data |
| Tenders and Market Intelligence filter labels, Tenders sort note | ui.market_tenders_view (country_filter_label, category_filter_label, sort_label) | wired (fix round 2) |
| Top-opportunity section titles | ui.market_top_opportunity_view (top_tenders_, projects_, next_moves_section_label) | wired |
| Product Evaluation tab labels, order, enabled flag | ui.competitive_positioning_tab | wired |
| Pillar names Market, Technology | ui.market_pillar.display_name, ui.technology_pillar.pillar_name | wired; Competitive is chrome (no ui table holds it) |
| Impact eyebrow | serving.competitive_signal_detail.impact_eyebrow (details[id].eyebrow); none stored, none drawn | wired |
| Page empty texts: Tenders, Top opportunity, Market Intelligence, Global Requirements | ui.market_view.empty_state_text by view_id; ui.market_global_requirement_view.empty_state_text | wired |
| Global Requirements filter labels and sort note | ui.market_global_requirement_filter, ui.market_global_requirement_view | no place to render (that page has no filter controls) |
| Sequence menu and search placeholder, competitive and market overview | no stored text | chrome |

Decision: there is no favourable stance. The only stances are threat and watch (uiText.STANCES). A row stored with any other stance has no stance: no pill, no colour, not counted, not on the competitive overview (the Cummins rule that dropped its third stance from that feed, stated without the word). The geo client marker is class `client`; the green accent token is `--ok`.

## F. Rulings

Controller rulings R3 to R9, copied verbatim from `progress.md`. They are binding and already applied to the rows of A to E.

- Ruling R3 (O-1): `not-shipped` disposition and C3 column additions accepted — spec allows "a column (and therefore a table, if none exists)". — Cost if wrong: none.
- Ruling R4 (O-2): backend ships news + moment rows in competitorNews (moment rows carry level/analysis/card); Moment page filters to rows with `level` (one-line UI filter). — Why: keeps Cummins page code; KSSL tables stay separate. — Cost if wrong: a moment shows in profile news; visible, easy fix.
- Ruling R5 (O-3): severity/impact/shortlist ordering removed; feed ordered by stored sequence. — Why: judgement with no column; DB rule. — Cost if wrong: feed order differs from :8101; add a judgement column later.
- Ruling R6 (O-4,O-6,O-7,O-8,O-10): accepted as proposed (stored edge_score + generic comparison; relax leadership filter to value&&url; TenderCockpit reads data.topOpportunities; marketCards composition; fold neutral lookups into allowlisted files). — Cost if wrong: localized rework.
- Ruling R7 (O-5): UI adopts KSSL vocab (threat/watch/fav; strong/partial/weak); field cumminsFit → clientFit. — Why: DB values are the truth; no translation layer. — Cost if wrong: small label edits.
- Ruling R8 (O-9): KSSL v2-only UI features with no Cummins equivalent (partnership evidence drawer, geo product-match popup, tender product-match %, matchup sources panel) are NOT re-applied this round; data stays in tables; listed to the user at finish. — Why: user asked for the Cummins UI, same for both clients. — Cost if wrong: user asks to restore them; code exists on v2.
- Ruling R9 (value tiles, no FX): mixed-currency values are never converted in the browser; tiles show per-currency totals (or count only when no value). — Why: no fabricated FX. — Cost if wrong: tile layout tweak.

Where they show up in this file:

- R3: the `not-shipped` rows of A and the column additions of C3.
- R4: A competitorNews (level, lenses) and the competitorMoment row; E4 moment level words.
- R5: A overviewConfig shortlist, `*Cards` severity / impact; B shortlist.js and threat.js rows.
- R6: A matchups edge, leadership line, topOpportunities, marketCards; B COUNTRY_ALIAS, PG_REGION_ALIAS, edge.js rows.
- R7: A competitors threat, tenders fit and clientFit, competitorNews level; E tiles and fit words.
- R8: A partners evidence / detail; the geo product-match, tender-match and matchup-source tables stay in the DB without a UI.
- R9: A tenders value, awards value; B CR_PER_MILLION; C2 market_award (value_amount, value_currency, value_text); E tile units. No FX anywhere, in code or in the loader.

## G. Task 7 notes (remove-genset, judgements read from data)

- Deleted with their features: tenderIntel.js engine (ASSUME, win weights, forecast, channels, gap bands), shortlist.js, footprint.js, threat.js re-grader, marketOutlook sizes()/BANDS/SEG_ALIAS/trend words/next-expected, geo.js band and counter engine and model-compare popup, GAP_DIM table, edge.js assumptions (axes, ranges, groups, per-kVA).
- Read from data instead: tender fit (`clientFit`), revenue (`revenueMid` or null), cockpit rows (`topOpportunities`, stored order), competitor threat (`threat`), patent crowding (`techAreaMeta[].crowding`) and position note (`reason`), segment recommendation, geo overlap (`geoPresence[].overlap`, `.ranges`), edge (`matchups[].edge`, `specDims`, `specDecided`), lean sentence (`leanTxt`).
- Global requirements are the rows of `data.globalRequirements`; their feed cards and every cross-link use the `req-` card id. Browser-built tender cards use the `tender-` prefix.
- Ordering (R5): direction, date, stored `seq`; the Latest Tenders head is the first twenty open tenders by stored `rank`.
