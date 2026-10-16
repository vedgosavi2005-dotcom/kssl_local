# Audit A: Overview (competitive + technology), signal drawer, Competitor Profile, Competitor Moment, sidebar/top bar/search

Scope: `Overview.jsx` (routes `#p=competitive&v=overview`, `#p=technology&v=t-overview`), `DetailPanel.jsx`, `SignalCard.jsx`, `lib/overview.js`, `detail.js`, `threat.js`, `glance.js`, `shortlist.js`, `MetricsStrip`, `Profile.jsx` (+ LeaderPage, news), `lib/profile.js`, `news.js`, `roster.js`, `revenueFacet.js`, `countryFacet.js`, `companyNames.js`, `ThreatAnalysis.jsx`, `Sidebar`, `TopBar`, `search.js`. Market overview (`m-overview`) is not covered.

Method: every value traced component -> lib helper -> `data.X` (`wireDataset` in `src/lib/dataset.js`, `build_*` in `backend/app.py`) -> table.column. "Served today" is judged from `backend/app.py` (577 lines). All my tables are empty in the local DB, so I also loaded the live app at :5178 (Playwright) to confirm the empty-state behaviour quoted below.

## 0. What `app.py` serves for my pages today (the whole list)

| data key | built from | notes |
|---|---|---|
| `competitors[cid]` | `serving.competitive_competitor` (app.py:140-167) | `name`=display_name or legal_name; `short`=short_name; `threat`=threat_level (raw); `origin`=origin_country; `sector`=industry_sector; `description`=parallax_read; `hq`=headquarters; `starting_year`; `global_locations` (text); `company_size`=employee_count; `sales`=annual_revenue (Decimal -> string). `partners` and `products` are always `[]`. NOT served: legal_name (except as name fallback), revenue_currency, revenue_tier, strategic_positioning, leaders, locations, news |
| `competitiveCards` / `marketCards` / `techCards` | `serving.competitive_signal` (app.py:170-192) | lane picked by `classification` prefix: starts with "tech" -> technology, "market" -> market, else competitive (app.py:176-177). `dir`=classification (raw), `rank`=sequence_no, `title`, `company`=company_id (a UUID string), `meta`=`tags`=category, `ago`=event_date (ISO), `lens`=lane title, `sowhat`=summary, `url`=`row.get("source_url")` which is a column competitive_signal does NOT have (always ""), `sec`=[]. NOT served: severity, severityRank, impact, competitor, kind, image, uiTitle, ksslImpact, glance, facts, thumbnail_url |
| `details[signal_id]` | `serving.competitive_signal_detail` (app.py:193-204) | `title`=drawer_title; `summary`=why_it_matters (!); `what`=what_article_says; `why`=why_it_matters; `lens`=[]; `url`=source_url. NOT served: dir, facts, glance, srcs, provenance, source_name, impact_eyebrow, ask_box_query, image |
| `competitorMoment` | `competitive_competitor`, `competitive_competitor_moment`, `ui.competitive_competitor_moment_time_window`, `ui.competitive_competitor_moment_level` (app.py:208-243) | see section 1F |
| `competitorNews` | not built (`{}`, app.py:521) | `competitive_news_article` is never read |
| `overviewConfig.*` | `empty_config` (app.py:485): title "", cnt "", filters [], groups [], metrics [] | `competitive` has NO tiles and NO filter pills today; `technology` is entirely re-written in `dataset.js:314-358` |
| `database.{ui,serving}.<table>` | every table, raw (app.py:84-107) | available to the UI but no page of mine reads it |
| client | `serving.client_account` (app.py:463-481) | `client.short`=brand_name or client_name |

Findings from the live app (empty DB): Competitive Overview shows no metric tiles and no pill row; Technology Overview shows three hard-coded tiles (COMPETITOR ADVANCES / ADOPTABLE ADVANCES / DOMAINS TRACKED), the heading "Technology Knowledge" and the group header "COMPETITOR ADVANCEMENTS" with no data; every sidebar count shows `0`; the Competitor Moment page logs "Warning: Maximum update depth exceeded" (infinite re-render loop, see section 5).

## 1. Per-page tables

Kind: STORED / COMPUTED-JS / COMPUTED-BACKEND / CHROME / INVENTED / NO-COLUMN. Action: map / keep / hide / remove / decide.

### 1A. Competitive Overview feed (`#p=competitive&v=overview`)

| # | UI element | dataset key / field (file:line) | served today? | new-schema column to use | Kind | Action |
|---|---|---|---|---|---|---|
| O1 | Page heading "Competitive Intelligence" | `headTitle = cfg.title or meta.title` (Layout.jsx:118); `viewMetaFor().overview.title` (overview.js:841) | no: cfg.title is "" (app.py:485); falls to the code literal | ui.competitive_navigation.view_label (view_key=overview) | CHROME | keep (may map) |
| O2 | Count line "N signals" (print sheet only; hidden on screen, SubHead.jsx:93) | `countLine` (Layout.jsx:122-161): `${cards.length} ${cfg.cnt tail or "signals"}` | computed | ui.competitive_overview_feed.visible_signal_count (stored, unused) | COMPUTED-JS | keep (print only) |
| O3 | Metric tiles (labels) | `cfg.metrics` (overview.js:479-546 binds by label) | NOT served: `metrics: []` so no tiles render | ui.competitive_metric.metric_label (+ display_order) | NO-COLUMN today (labels absent) | map |
| O4 | Tile values: Competitive threats, Watch signals, Companies tracked | `metricsFor` (overview.js:538-540) | computed in browser | ui.competitive_metric.metric_value, as_of_date (stored text) | COMPUTED-JS | decide: store (load script writes counts) or keep computing |
| O5 | Tiles "Analytical lenses" and "All signals" | `BLANK_TILES` (overview.js:477; MetricsStrip.jsx:93) | rendered as empty cells | none | CHROME (blank slots) | remove (do not reserve empty slots) |
| O6 | Tile warning sublines ("no served competitive signal is assigned a threat direction - not assessed") | overview.js:509, 519, 543-546 | computed | none | CHROME | keep |
| O7 | Tile click doors (jump to Partnership / Product Evaluation, filter feed) | Layout.jsx:246-285; `tilePredicate` overview.js:686-709 | n/a | none | CHROME | keep |
| O8 | Direction pills (All / Threat / Watch) labels | `cfg.filters` (Overview.jsx:315) | NOT served: `filters: []`, no pills render | none (ui.competitive_overview_feed.threat_filter holds only the selected value) | NO-COLUMN (labels) | decide: pill wording as CHROME keyed on classification values |
| O9 | Pill counts | `filterCounts` (Overview.jsx:265-273) = cards passing tile+search+pill predicate | computed | none | COMPUTED-JS | keep |
| O10 | Feed search box | `visibleExceptDir` (Overview.jsx:116-126): every token must occur in lower-cased `title company tags sowhat ago facts what why` | computed over card+detail | ui.competitive_overview_feed.local_search_query is state only | COMPUTED-JS | keep |
| O11 | Sequence select ("Priority (threats first)", "Most recent") | `SEQ_OPTIONS` (overview.js:21-24); default `readFeedSeq` (overview.js:320-329) | code literal | ui.competitive_overview_feed.sequence_mode (selected value only) | CHROME | keep |
| O12 | Order of cards | `compareCards` (overview.js:131-146), `buildFeed` (overview.js:156-222) | computed | competitive_signal.sequence_no (stored, ignored) | COMPUTED-JS | decide: show by stored sequence_no or keep rule (section 3) |
| O13 | Rank number "01" on a card | `rank: String(n+1)` after sort (overview.js:175); the served `rank`=sequence_no (app.py:181) is overwritten | sequence_no served then discarded | competitive_signal.sequence_no | COMPUTED-JS | decide |
| O14 | Card title | `card.uiTitle or card.title` (SignalCard.jsx:36) | competitive_signal.title (app.py:182) | competitive_signal.title | STORED | map (keep) |
| O15 | Card title/description text rewriting | `decodeAmp`, `plainDashes` (dataset.js:66,104,139), `titleCaseHeadline` (dataset.js:157; profile.js:165-178): "&amp;" -> "&", em dash -> " - ", every word's first letter raised | applied to all strings | none | COMPUTED-JS | decide (alters stored text) |
| O16 | Card description line | `card.ksslImpact or card.sowhat` (SignalCard.jsx:37) | competitive_signal.summary (app.py:190); ksslImpact not served | competitive_signal.summary | STORED | map (keep) |
| O17 | Direction badge word | `cfg.dirWord[c.dir] or c.dir` (Overview.jsx:70-71); dirWord `{}` | raw classification string printed | competitive_signal.classification | STORED (raw) | decide: expected casing/values (test insert uses lowercase "threat"; CSS classes `dir-threat`, DIR_WORD keys are lowercase) |
| O18 | Direction dot colour / `data-dir` | `refineThreats` (dataset.js:143; threat.js:54-119) may overwrite `dir` | classification then JS override | competitive_signal.classification | INVENTED | remove (keyword reclassification, section 2 item 1) |
| O19 | Date on card | `when = signalDate(card,data)` (overview.js:235-255), else `card.ago`, else "date not known" (SignalCard.jsx:67) | `ago` = event_date ISO text, shown as raw "2026-09-01" (not formatted) | competitive_signal.event_date | COMPUTED-JS (format) | map; format with formatDate |
| O20 | "date not known" | overview.js:122 | n/a | n/a | CHROME | keep |
| O21 | Company (not printed on the card; used by search, report rows, tile, shortlist) | `card.company = text(company_id)` (app.py:183) = a UUID | UUID served | join competitive_signal.company_id -> competitive_competitor.display_name (company_id vs competitor_id naming needs user confirmation) | NO-COLUMN (as served) | decide |
| O22 | Source URL on card (`card.url`) | app.py:189 reads `source_url` from competitive_signal (column does not exist) | not served (always "") | competitive_signal_detail.source_url | NO-COLUMN as coded | map |
| O23 | Card "KSSL Product:" row | `card.match` (SignalCard.jsx:38-43) | market tender cards only; not served for signals | none | CHROME (dead for my pillars) | remove from signal card |
| O24 | Thumbnail | competitive_signal.thumbnail_url | not served; overview card draws no image | competitive_signal.thumbnail_url | n/a | decide (user said product images hidden; signal image undecided) |
| O25 | Which cards are on the feed at all (shortlist, cap 30, rest pushed into rival news) | `overviewShortlist` (dataset.js:300-304; shortlist.js:237-372) | today: 0 cards qualify (no impact/severity served) so lane is "unscored" and passes whole (shortlist.js:322) | none | COMPUTED-JS (INVENTED rules) | decide/remove (section 2 item 2) |
| O26 | Pager: "showing a-b of N signals" / "filtered - T total", page size 50 | `paginateFeed` (overview.js:350-385); `FEED_PAGE_SIZE` 258 | computed | none | COMPUTED-JS + CHROME | keep |
| O27 | Empty-state text ("no signals served yet", "no signals match ...") | `emptyFeedNote` (overview.js:937-942) | literal | ui.competitive_overview_feed.empty_message | CHROME | keep (or map) |
| O28 | Selecting a card | `data.details[id]` must exist or the click does nothing (Overview.jsx:133-135) | details keyed by signal_id | competitive_signal_detail.signal_id | STORED | keep |
| O29 | Print report rows ("Company - Title", sowhat, severity, impact, date, url) | Overview.jsx:200-241 | computed from cards | none | COMPUTED-JS | keep (fields severity/impact are null) |
| O30 | Sidebar badge on "Overview" | `counts.overview` (overview.js:736-739) = shortlist length | computed | ui.competitive_navigation.record_count | COMPUTED-JS | decide |

### 1B. Technology Overview feed (`#p=technology&v=t-overview`)

| # | UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|---|
| T1 | Page heading "Technology Knowledge" | `cfg.title` hard-coded (dataset.js:326) | literal in code | ui.technology_overview_view.page_heading or ui.technology_ui_view.page_heading | CHROME (value exists in DB) | map |
| T2 | Count line tail "recent defence-tech: competitor advancements + advances KSSL can adopt" (print only) | dataset.js:327 | literal | none | CHROME (describes content) | decide |
| T3 | Tile labels "Competitor advances", "Adoptable advances", "Domains tracked", "Analytical lenses", "All signals" | `metrics` hard-coded (dataset.js:344-350) | literal; shown even with zero data | serving.technology_metric.metric_label / ui.technology_metric.metric_label / ui.technology_overview_metric_card.metric_label | INVENTED (labels in code) | map |
| T4 | Tile values | `metricsFor` technology branch (overview.js:602-628): rival = cards tagged "rival"; adopt = tagged "adopt"; Domains = innovation categories having at least 1 row | computed | serving.technology_metric.metric_value / ui.technology_overview_metric_card.metric_value | COMPUTED-JS | decide (store vs compute) |
| T5 | Tile subline "no competitor advancement is served" etc. | overview.js:617-627 | computed warning | none | CHROME | keep |
| T6 | Card source | `d.techCards` = competitive_signal rows whose classification starts with "tech" (app.py:176-177) | served from the competitive table | serving.technology_overview_article (+ ui.technology_overview_signal_card) | NO-COLUMN (wrong table) | map |
| T7 | Card title / description | `title`, `sowhat` | competitive_signal.title / summary | technology_overview_article.title, card_summary (or summary); ui.technology_overview_signal_card.title_display, narrative_display | STORED | map |
| T8 | Card badge word ("Adoptable", blank for competitor advance) | `tagWord {rival:"", adopt:"Adoptable"}` (dataset.js:334); `labelFor` Overview.jsx:70 | literal; `kind` derived, see T9 | technology_overview_article.classification; ui.technology_overview_signal_card.classification_display | INVENTED | map |
| T9 | Stream kind rival vs adopt | `isRivalCard`: `card.competitor` non-empty (overview.js:449-451); `competitor` is NOT served so every card becomes "adopt" | rule on an unserved field | technology_overview_article.direction / classification, or technology_overview_company.relationship_type (which one defines "competitor advance" needs the user) | COMPUTED-JS | decide |
| T10 | Direction forced to "watch" on every card | `withTag` (overview.js:452-455) | overrides stored classification | technology_overview_article.classification | INVENTED | remove |
| T11 | Head cap: 30 cards, 18 competitor + 12 adopt, newest first | `technologyAttention` (overview.js:448-466) | computed; hides the rest | none | COMPUTED-JS (invented limit) | remove or decide |
| T12 | Group header shown when feed empty "Competitor Advancements" (eyebrow) | dataset.js:353-357; Overview.jsx:301-303 | literal | none | CHROME | keep |
| T13 | Card date | `card.ago` (event_date) -> signalDate | event_date of competitive_signal | technology_overview_article.published_on / article_date / published_label; ui.technology_overview_signal_card.published_date_display | COMPUTED-JS (format) | map |
| T14 | Card rank | re-numbered 01.. (overview.js:175) | computed | technology_overview_article.sequence_no; ui.technology_overview_signal_card.rank_position | COMPUTED-JS | decide |
| T15 | Sequence select | `SEQ_OPTIONS` (overview.js:21) | literal | ui.technology_overview_view.sequence_options, sequence_value, sequence_label; ui.technology_ui_view.sequence_options | CHROME | map (optional) |
| T16 | Search placeholder "Search" | FeedFilters.jsx:34 | literal | ui.technology_overview_view.search_placeholder | CHROME | keep |
| T17 | Filter pills hidden (`hideFilterButtons`) | dataset.js:338-343 | literal | ui.technology_overview_filter (filter_type, option_values, selected_value) | CHROME | keep hidden |
| T18 | Pager text | Overview.jsx:384-387 | computed | ui.technology_overview_view.total_signals, showing_from, showing_to (stored, unused) | COMPUTED-JS | keep |
| T19 | Sidebar badge "Overview" (technology) | `counts["t-overview"]` (overview.js:800-802) = capped list length | computed | ui.technology_ui_view.record_count | COMPUTED-JS | decide |

### 1C. Signal detail drawer (`DetailPanel.jsx`, opened from both overviews)

| # | UI element | dataset key / field (file:line) | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|---|
| D1 | Stance pill "Threat / Watch / Favourable" | `detail.dir or "watch"` (DetailPanel.jsx:26) -> DIR_WORD (line 9) | details carry no `dir`, so every drawer says "Watch" | competitive_signal.classification | INVENTED (default presented as data) | map (take from the card's classification), remove default |
| D2 | Pill for technology (Adoptable / none) | `badge` prop (Overview.jsx:436-442) | see T8 | technology_overview_article.classification | INVENTED | map |
| D3 | Drawer title | `detail.title` = drawer_title (app.py:198), recased (dataset.js:189-190) | yes | competitive_signal_detail.drawer_title | STORED | keep |
| D4 | Lead image | `detail.image` (DetailPanel.jsx:120) | not served | competitive_signal.thumbnail_url / technology_overview_article.image_url | NO-COLUMN as coded | decide |
| D5 | "How KSSL is impacted" box (eyebrow + text) | `detail.ksslImpact`, eyebrow by `ksslImpactKind` (DetailPanel.jsx:136-153) | not served | text: competitive_signal_detail.why_it_matters; eyebrow: competitive_signal_detail.impact_eyebrow | NO-COLUMN as coded | map (eyebrow words are CHROME fallback) |
| D6 | "At a glance" rows | `detail.glance` or `detail.facts` filtered by DROPPED_FACTS (DetailPanel.jsx:72-86); label through `formatLabel` (line 174) | not served (section header still prints with no rows) | competitive_signal_evidence (evidence_group, label, value, quote=tooltip, source_url); technology_overview_fact (fact_label/ui_label, fact_value, proof_text) | NO-COLUMN as coded | map; hide header when no rows |
| D7 | Fact label rewrite ("Counterparty" -> "Competitor"; hide rows named stance/date/publisher/primary lens; recase) | profile.js:99-132, DetailPanel.jsx:72 | applied to stored labels | none | INVENTED | remove |
| D8 | "What the article says" | `detail.summary or detail.what` (DetailPanel.jsx:203-211); backend sets summary = why_it_matters (app.py:199) | so this heading shows why_it_matters text and what_article_says is never shown | competitive_signal_detail.what_article_says; technology_overview_article.article_says | STORED (wrongly mapped) | map |
| D9 | "Key points" bullets | `articleBullets(detail.lens)` (detail.js:50-60): split each lens row on first "—", strip tags, capitalise, max 4 | `lens: []` so none | competitive_signal_evidence (the group holding propositions); technology_overview_key_point.point_text/point_no/evidence_text | NO-COLUMN as coded | map |
| D10 | Source chips | `srcChips(detail.srcs) or srcChips([{url}])` (DetailPanel.jsx:43-45; html.js:148); chip text = URL host, truncated to 34 chars | url only | competitive_signal_detail.source_url, source_name (unused); technology_overview_source -> technology_source.label/publisher/url | COMPUTED-JS (host as label) | map (use source_name) |
| D11 | "provenance - ..." line | `detail.provenance` (DetailPanel.jsx:291-303) | not served | competitive_signal_detail.provenance; technology_overview_source.provenance_status | NO-COLUMN as coded | map |
| D12 | Ask box (suggested question) | `AskBox` returns null (askBox/AskBox.jsx) | not shown | competitive_signal_detail.ask_box_query | NO-COLUMN (stub) | hide |
| D13 | Section eyebrows "At a glance", "What the article says", "Key points", "Source" | DetailPanel.jsx | literal | ui.technology_overview_detail_panel.at_a_glance_label, what_article_says_label, key_points_label, source_label, provenance_label (technology only) | CHROME | keep (map for technology) |
| D14 | Tender branch (not my pages) | DetailPanel.jsx:36-42, 77-79, 264-284 | market only | n/a | n/a | out of scope |
| D15 | glance.js gloss text ("the company this signal is about" ...) | glance.js:32-50 | imported nowhere now | none | INVENTED (dead file) | remove file |

### 1D. Competitor Profile (`#p=competitive&v=profile`): list column and company details

| # | UI element | dataset key / field (file:line) | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|---|
| P1 | Roster membership (who is listed) | `rosterOf` (profile.js:319-348) over `data.competitors` minus client; after `dedupeCompanies` merge | competitive_competitor rows | competitive_competitor.competitor_id | STORED | keep |
| P2 | Hard-coded company merges (idv+iveco, rtx+raytheon, knds+nexter, huta-stalowa-wola+hsw) and "same site" merge | `PAIRS`, `aliasMap` (dedupeCompanies.js:52-57, 80-110); runs first in wireDataset (dataset.js:139) | applied to roster | none | INVENTED | remove (DB holds one row per company) |
| P3 | Roster sort (client first then A-Z by name) | `sortCompaniesByName` (roster.js:7-19) | computed | competitive_competitor.display_name | COMPUTED-JS | keep |
| P4 | Name in list and heading | `competitorFullName(cid, name)` (companyNames.js:188-195): `COMPANY_NAMES[cid]` (slug keys, never match a UUID) else served name | display_name or legal_name | competitive_competitor.display_name; full name: legal_name | STORED + INVENTED table | map; remove COMPANY_NAMES |
| P5 | Hard-coded full names / notes table (aweil, iwi, idv, norinco, saab "Saab AB", sss-defence note "defence division of Stumpp Schuele & Somappa, established 2017", ...) | `COMPANY_NAMES` (companyNames.js:50-127), `detailLine` (178-184) | in code | competitive_competitor.legal_name | INVENTED | remove |
| P6 | "Entity Note" row (shown only when it differs from the name) | Profile.jsx:857-864 from P5 | in code | none | INVENTED | remove (hide) |
| P7 | Threat dot colour in list | `r.threat === "high" ? threat : "low" ? fav : watch` (Profile.jsx:794); threat = threat_level raw | raw value; test data uses "High" so every row falls to "watch" | competitive_competitor.threat_level | COMPUTED-JS + INVENTED default (no value renders as "watch") | decide (value vocabulary, case) ; no dot when null |
| P8 | List search box | Profile.jsx:448-459: tokens in `name full-name sector hq cid` (also the top-bar query) | computed | none | COMPUTED-JS | keep |
| P9 | Origin filter options + counts ("France (6)", "All origins (N)", "Origin not established") | `facetOptionsByName(roster, origin or UNKNOWN_ORIGIN)` (Profile.jsx:383-385, 361); `companyOrigin` reads `co.country` (countryFacet.js:103-107) but backend sends `origin` | key mismatch: origin is null for every row | competitive_competitor.origin_country | COMPUTED-JS (distinct values + counts) | map (fix key); "Origin not established" CHROME |
| P10 | Revenue tier filter options and labels ("High (> ₹5,000 Cr / $1B+)", "Mid (₹1,000 - ₹5,000 Cr)", "Emerging (< ₹1,000 Cr)", "Revenue not on record") | `revenueOptions`, `REVENUE_LABEL` (revenueFacet.js:14-19, 56-63) | tier read from `revenue_filter` (not served), else parsed from `sales` text (needs a unit word; served value is a plain number so always "unknown") | competitive_competitor.revenue_tier | INVENTED (band definitions in code) + COMPUTED-JS | map: show stored tier text as the label |
| P11 | Tier computation | `revenueTierOf`: parse text, FX table `usd 8500, eur 9300, gbp 11000, inr 100` crore per bn (revenueFacet.js:23), cut-offs 5000 / 1000 crore (line 48) | in code | competitive_competitor.revenue_tier | INVENTED | remove |
| P12 | Default selected company | first of roster (Profile.jsx:396), remembered in memory per pillar (viewState) | computed | ui.competitive_profile_view_state.selected_competitor_id | COMPUTED-JS | keep |
| P13 | Starting Year | `p.starting_year` (profile.js:421) or "—" (Profile.jsx:334) | yes | competitive_competitor.starting_year | STORED | keep |
| P14 | Headquarters | `tidyHq(formatLabel(hq))` (profile.js:415; Profile.jsx:335; countryFacet.js:65-75): drops street/house/postcode segments, keeps last 3 parts, recases | yes (raw headquarters) | competitive_competitor.headquarters | COMPUTED-JS | decide (show as stored) |
| P15 | Global Locations chip | hard-coded `<span className="cp-loc-chip">India</span>` (Profile.jsx:885) on every company | in code | competitive_competitor.global_locations (text) and/or competitive_competitor_location.location_name/location_type/country | INVENTED | remove; map |
| P16 | Company Size | `p.company_size = txt(employee_count)` (profile.js:422), "—" if 0/empty | yes (integer) | competitive_competitor.employee_count | STORED | keep |
| P17 | Annual Revenue / Sales | `firstFigure(p.sales)` (Profile.jsx:288-305). `p.sales` is rebuilt as `sourcedRows(c,"sales")`, which accepts only arrays (profile.js:294-298), so the served annual_revenue string is dropped and the row always reads "—" | value served but lost | competitive_competitor.annual_revenue + revenue_currency (format "currency amount") | COMPUTED-JS (format) | map |
| P18 | Industry / Sector | `formatSectorName(sector)` = `formatLabel(x) or "Defence & Aerospace"` (profile.js:250-252; Profile.jsx:907) | industry_sector served | competitive_competitor.industry_sector | INVENTED default + recase | remove fallback |
| P19 | "Strategic Positioning" paragraph | `p.strategic_positioning or p.assess or "<name> is actively scaling indigenous manufacturing capabilities..."` (Profile.jsx:913-917) | strategic_positioning NOT served; `assess` NOT served | competitive_competitor.strategic_positioning | INVENTED (sentence in code) | hide (rule 4) |
| P20 | "PARALLAX READ" box | `assess` or sentence "<name> is the incumbent specification across primary domestic defence tenders..." (Profile.jsx:919-931) | app.py puts parallax_read in `description`, which this page never reads | competitive_competitor.parallax_read | INVENTED (sentence in code) | hide (rule 4) |
| P21 | STRENGTHS / WEAKNESSES boxes with "0" and "No strengths on record." | Profile.jsx:933-956 (count `0` typed in code) | nothing read | competitive_competitor_swot (swot_type, statement, record_count, empty_message) | INVENTED (constant 0) | hide (rule 4) |
| P22 | Leadership grid (name, role) | `p.leadership = sourcedRows(c,"leadership")` (profile.js:390) -> `leadershipList` (Profile.jsx:513-526) | `leadership` not served | competitive_leader.full_name, role_title, organization, avatar_initials, role_source_url | NO-COLUMN as coded | map |
| P23 | Role fallback "Key Executive / Officer" | Profile.jsx:518 | in code | competitive_leader.role_title | INVENTED | remove |
| P24 | Leader avatar | photo if `/local-photos/..` or http(s) (Profile.jsx:246-259) else initials from `getInitials` (36-42; default "EX") | photo not served | competitive_leader.avatar_initials (no photo column) | COMPUTED-JS (initials) | map avatar_initials; remove "EX" |
| P25 | "Support Leadership" section | `p.support_leadership` (profile.js:439) | not served; fallbacks "Supporting Executive", "Executive Officer" typed (Profile.jsx:535-537) | no column distinguishes support from main leadership | NO-COLUMN | hide, decide |
| P26 | Empty-state lines ("No executive officers published on public record." etc.) | Profile.jsx:988, 1022, 1063, 1155 | literal | competitive_leader_record.empty_message (records only) | CHROME | keep |
| P27 | Section headings, row labels, "Competitors" eyebrow | Profile.jsx | literal | none | CHROME | keep |

### 1E. Competitor Profile: leader page (click a leadership card)

| # | UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|---|
| L1 | Name | `leader.fullName or leader.name` (Profile.jsx:143) | not served | competitive_leader.full_name | NO-COLUMN as coded | map |
| L2 | Role / organisation line | `leader.role` + `current ? current.company : companyName` (Profile.jsx:145-146) | not served | competitive_leader.role_title, organization | NO-COLUMN as coded | map |
| L3 | "Current Position" block | `current = experience entry whose end is empty/"present/current/now"` (Profile.jsx:105,121,153-159); else falls back to role + company name | derived | competitive_leader.role_title + organization; records with record_type experience and end_date null | COMPUTED-JS | keep rule, document |
| L4 | Professional Experience rows (role, company, "2018 – Present · 8 yrs") | `experience[]` (Profile.jsx:164-176); `tenureText` (107-116) uses `new Date().getFullYear()` and treats empty end as "Present" | not served | competitive_leader_record (record_type, role_or_degree, institution_or_employer, start_date, end_date) | COMPUTED-JS (tenure) | map |
| L5 | Education rows (degree, institution, years) | `education[]` (Profile.jsx:184-196) | not served | competitive_leader_record (record_type education) | NO-COLUMN as coded | map |
| L6 | "News Related to X" | name-token match over company articles; if fewer than 2 match, shows the first 4 company articles anyway (Profile.jsx:123-132) | derived from news (not served) | no leader-news column | INVENTED (fallback shows unrelated articles as related) | remove fallback; hide section if no match |
| L7 | Source links (Role / Career & education / Photo) | `leader.source, bioSource, photoSource` (Profile.jsx:230-238) | not served | competitive_leader.role_source_url; competitive_leader_record.source_url | NO-COLUMN as coded | map (drop Photo) |
| L8 | "No career history on public record." / "No education on public record." | Profile.jsx:178,198 | literal | competitive_leader_record.empty_message | CHROME | keep |

### 1F. Competitor Profile: news sections ("Company Latest News" cards and "News" table)

| # | UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|---|
| N1 | Article source | `data.competitorNews[cid]` (news.js:186-202) | `{}` (app.py:521): sections show "No sourced article in the corpus names X." | competitive_news_article (competitor_id, headline, article_url, publisher, category, published_date, image_url) | NO-COLUMN as coded | map |
| N2 | Title | `item.title` recased by `titleCaseHeadline` (dataset.js:186-187) | not served | competitive_news_article.headline | STORED + COMPUTED-JS recase | map |
| N3 | Publisher | `item.source or host of url or "Unattributed"` (Profile.jsx:59-70, 1102, 216) | not served | competitive_news_article.publisher | STORED + INVENTED fallback | map; remove "Unattributed" |
| N4 | Category on card | `item.category or "Defence"` (Profile.jsx:1099); in shape(): `row.category or "Update"` (news.js:57) | not served | competitive_news_article.category | STORED + INVENTED fallback | map; remove fallbacks |
| N5 | Category in table column | `cleanNewsCategory` (Profile.jsx:72-79): keyword buckets Financial / Government / Workforce / Markets, everything else "Defence" | rewrites the stored category | competitive_news_article.category | INVENTED (keyword mapping + default) | remove; show stored text |
| N6 | Category pills | hard-coded `["All", "<Name> Updates", "Defence", "Financial", "Government", "Workforce", "Markets"]` (Profile.jsx:1071); match = substring either way (610-615) | in code | distinct competitive_news_article.category; ui.competitive_news_view.category_filter | INVENTED (vocabulary in code) | map (options from data) |
| N7 | Date on card / row | `item.ago = formatDate(date)` (news.js:58); table `fmtNewsDate` (Profile.jsx:44-57, year fallback 2026) | not served | competitive_news_article.published_date | COMPUTED-JS (format) | map |
| N8 | Image on card | `item.image` -> `Thumb` (Profile.jsx:1092-1096); an image already used by an earlier card is blanked (news.js:195-200) | not served | competitive_news_article.image_url | COMPUTED-JS (de-duplication) | map; remove blanking |
| N9 | Which cards show (grid of 9) | `displayList` (Profile.jsx:1086-1090): if filtered list under 9 it shows the unfiltered list, or filtered+unfiltered concatenated | computed | none | INVENTED (ignores the pill/window; can repeat articles) | remove |
| N10 | Window select "Last 30 days / 3 months / 6 months / 12 months / All time", default 12m | `NEWS_WINDOWS`, `NEWS_WINDOW_DEFAULT` (news.js:275-283); cut-off from browser clock `Date.now()` (news.js:296-304) | literal | ui.competitive_news_view.published_range, date_filter | CHROME + COMPUTED-JS | keep |
| N11 | Cap 15 cards / 20 table rows then "Show the remaining N" | `NEWS_MAX` (news.js:273), Profile.jsx:1159,1223 | computed | ui.competitive_news_view.page_size | CHROME | keep |
| N12 | Articles hidden or merged: same URL folded; same publisher + same day + title overlap >= 0.4 dropped; link judged "publisher index" by URL pattern and excluded from the cards and the date filter | `dedupeArticles` (news.js:114-183), `sourceKind` (articleUrl.js:64-81), Profile.jsx:590-597 | computed | none | COMPUTED-JS (heuristics) | decide (hides stored rows) |
| N13 | Table search / date range chips ("Last 7 days" ... "Custom range") | Profile.jsx:1134-1142, 710-728 | computed | ui.competitive_news_view.search_query, custom_start_date, custom_end_date | CHROME + COMPUTED-JS | keep |
| N14 | Product-category match in table search | `productCategoryOf(text, data.CAT_ALIASES)` (Profile.jsx:85-92, 712) | `CAT_ALIASES` not served: contributes nothing | none | NO-COLUMN | remove |
| N15 | Signals folded into a rival's news ("also move that signal into the news section") | `foldDemotedIntoNews` (shortlist.js:384-436), category `c.tags or "Update"` at 423 | needs competitorNews + demoted cards | none | INVENTED | remove |
| N16 | Live Google News headlines | `fetch("/api/pulse?...")` stored in `pulse` state (Profile.jsx:468-479) | `pulse` is never rendered anywhere in Profile.jsx | none (live, by decision) | CHROME | decide (decision says it stays, currently invisible) |
| N17 | Stock | competitive_stock_quote/series | removed in code (Profile.jsx:1114) | n/a | n/a | keep hidden |

### 1G. Competitor Moment (`#p=competitive&v=threat-analysis`)

| # | UI element | dataset key / field (ThreatAnalysis.jsx) | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|---|
| M1 | Competitor list (left) and "Competitors (N)" | `data.competitorMoment.competitors` = every competitive_competitor row (app.py:210-218), N = length (:146) | yes (all competitors, not only those with moves) | competitive_competitor.display_name, short_name | STORED + COMPUTED-JS (count) | keep |
| M2 | Dot colour per competitor | `threat === "fav" ? fav : "threat" ? threat : watch` (:209) | raw threat_level; Profile uses high/low, this page fav/threat, so all dots are "watch" | competitive_competitor.threat_level | COMPUTED-JS + INVENTED default | decide (one vocabulary) |
| M3 | Count next to each competitor | `compMoves.filter(m.cid === comp.cid)` (:60-70); shows all or window count (:216) | moment.competitor_id is bigint, competitor.competitor_id is uuid: never equal | competitive_competitor_moment.competitor_id | COMPUTED-JS | map (fix id type) |
| M4 | "All competitors" count | `displayedMoves.length` (:177): changes with the selected competitor | computed | none | COMPUTED-JS | fix (use total) |
| M5 | Heading "All competitors" or the competitor name | `activeTitle` (:96) | n/a | display_name | CHROME + STORED | keep |
| M6 | Sub line "N moves in this window - K graded a threat" | `displayedMoves.length`; K = items with `level === "THREAT"` (:97) | computed; level code typed in code | ui.competitive_competitor_moment_level.level_code | COMPUTED-JS | keep, read the code from the ui table |
| M7 | Time-window chips (labels) | `momentData.timeWindows` from ui table (app.py:236-237) | yes | ui.competitive_competitor_moment_time_window.time_window_label, day_count, display_order | STORED | keep |
| M8 | Initial window "all" | `useState("all")` and "Show all dates" button use id "all" (:26, :343) | literal; ui table has `is_default` | ui.competitive_competitor_moment_time_window.is_default | INVENTED (assumed code "all") | map |
| M9 | From / To date boxes and "Today = newest move, DD Mon YYYY" | window start = newest move date minus day_count days (:32-49, 280-284) | computed from data, not from today | none | COMPUTED-JS | keep, document |
| M10 | Move row: date | `formatDate(m.date)` local function: "Oct 16, 2026" style, "Undated" if empty (:5-15) | movement_date | competitive_competitor_moment.movement_date | COMPUTED-JS (format differs from the app's "16 Oct 2026") | map; reuse utils/formatDate |
| M11 | Move row: "category - country" | `m.category`, `m.country` (:311) | category; country_name or countries | competitive_competitor_moment.category, country_name, countries, region | STORED | keep |
| M12 | Move row: image slot text | `m.program.split(" ")[0]` upper-cased (:305-307): first word of the programme in a box | program_name | competitive_competitor_moment.image_url (unused), program_name | INVENTED (derived pseudo-image) | decide: show image_url or remove box |
| M13 | Move row: company | `m.company` = company_display (:317) | yes | competitive_competitor_moment.company_display | STORED | keep |
| M14 | Level pill (label + colour) | `levels[m.level]` else `{label: m.level, tagClass: "neutral"}` (:291, 318); m.level = grade raw | label and tag_class from ui table | ui.competitive_competitor_moment_level.level_label, tag_class; moment.grade must equal level_code | STORED | keep |
| M15 | Move row: source name | `m.source` = source_label or source_domain (app.py:233) | yes | competitive_competitor_moment.source_label / source_domain | STORED | keep |
| M16 | Move row: title, description | `m.title`, `m.description` = description or what_happened (app.py:230) | yes; card_summary never used | moment.title, card_summary (card text), description | STORED | decide (which column feeds the list line) |
| M17 | Sort newest first | `.sort(date desc)` (:87) | computed; display_order ignored | competitive_competitor_moment.display_order | COMPUTED-JS | decide |
| M18 | Drawer header colour | THREAT -> threat, OPPORTUNITY -> fav, else watch (:360-366) | level codes typed in code | ui.competitive_competitor_moment_level.tag_class | INVENTED (codes) | map |
| M19 | Drawer facts: Company, Date, Category, "Country / Region" (country only), "Strategic Program", Source | :391-398 | yes except region | moment.company_display, movement_date, category, country_name, region, program_name, source_label | STORED (labels CHROME) | map region |
| M20 | "What happened" | `selectedMove.whatHappened or description` (:412); `whatHappened` not served, backend prefers description so the same text appears in the list and here | description served | competitive_competitor_moment.what_happened | STORED (mapped to wrong column) | map |
| M21 | "Analysis - what it means for KSSL" | `ksslAnalysis or analysis` = kssl_analysis (:418; app.py:231) | yes | competitive_competitor_moment.kssl_analysis | STORED | keep |
| M22 | "Deeper analysis - by view" | `selectedMove.deeperAnalysis` (:422-444) | not served | competitive_competitor_moment_analysis (view_name, analysis_text, display_order) | NO-COLUMN as coded | map |
| M23 | Source link in drawer | `selectedMove.url` (:447-473) | not served | competitive_competitor_moment.source_url; competitive_competitor_moment_source (publisher, source_domain, source_url) | NO-COLUMN as coded | map |
| M24 | Empty state "No move by X in this window." + "Show all dates" | :332-348 | literal | none | CHROME | keep |
| M25 | Print report | `useHeaderReport({heading, facts})` not memoised (:106-124): print sheet reads `h`/`rows`, so it prints "This view publishes no summary" | n/a | none | CHROME | fix |
| M26 | Page metrics | ui.ui_competitor_moment_metric (metric_label, metric_value, metric_unit) | not read; page shows computed counts only | ui.ui_competitor_moment_metric | n/a | decide |

### 1H. Sidebar, top bar, search

| # | UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|---|
| S1 | Rail labels (Overview, Competitor Profile, Competitor Moment, ..., Innovations) | `RAIL` (route.js:29-54) | literal | ui.competitive_navigation.view_label, ui.technology_ui_view.view_label | CHROME | keep |
| S2 | Rail count: Overview | `counts.overview` (overview.js:737-739) = shortlist card count | computed | ui.competitive_navigation.record_count | COMPUTED-JS | decide |
| S3 | Rail count: Competitor Profile | `counts.profile` = competitors minus client (overview.js:743-745) | computed | ui.competitive_navigation.record_count | COMPUTED-JS | keep |
| S4 | Rail count: Competitor Moment | `counts["threat-analysis"] = 0` (overview.js:746) | typed constant, always 0 | count of competitive_competitor_moment | INVENTED | map (compute or store) |
| S5 | Rail count: Products, Product Evaluation, Partnership, Projects, Geo, Patent (other owners) | overview.js:721-788 (Projects = list length, Finances typed 0 at :748, patents `_meta.total`) | computed / constants | ui.competitive_navigation.record_count | COMPUTED-JS / INVENTED | other group |
| S6 | Rail count: Technology Overview, Innovations | overview.js:800-803 | computed | ui.technology_ui_view.record_count, rail_count | COMPUTED-JS | decide |
| S7 | Count shown when missing | `counts[item.view] ?? "—"` (Sidebar.jsx:37) | n/a | none | CHROME | keep |
| S8 | Wordmark "137Parallax", pillar tabs | TopBar.jsx:91, `PILLAR_LABEL` | literal | ui.competitive_pillar.brand_name, ui.technology_pillar.pillar_name | CHROME | keep |
| S9 | Client name chip (top right) | `data.client.short or name` (TopBar.jsx:18, 203) | client_account.brand_name or client_name | serving.client_account.brand_name | STORED | keep |
| S10 | Fallback client label/id "KSSL" | fallback `"KSSL"` after `||` (SignalCard.jsx:40, DetailPanel.jsx:266, Overview.jsx:74, overview.js:723/737/743/754/836, dataset.js:446, roster/shortlist) | in code | serving.client_account | INVENTED | remove |
| S11 | Search placeholder, group labels, "No results", footer text | TopBar.jsx:135-193; search.js:23-29 | literal | ui.technology_ui_navigation.global_search_placeholder (technology), ui.market_pillar.global_search_placeholder | CHROME | keep |
| S12 | Search hits: competitors (name, sector, hq, id), signals (title, company, tags, sowhat, meta), plus products/tenders/innovations (other owners) | search.js:69-158 | computed over the served dataset; signal "company" is a UUID; client row is also searchable as a competitor | none | COMPUTED-JS | keep; fix company join and exclude client |
| S13 | "Searched N competitors, M matched products, K signals ..." | TopBar.jsx:51-62 | computed | none | COMPUTED-JS | keep |
| S14 | Print Report button | SubHead.jsx | literal | ui.competitive_pillar.print_report_action, ui.technology_pillar.print_report_label | CHROME | keep |

## 2. INVENTED content found

| # | file:line | quote / what it does |
|---|---|---|
| 1 | src/lib/threat.js:27-38, 54-106 | keyword regex lists `NON_KSSL` ("isr", "radar", "software", "satellite", "submarine", ...), `PLATFORM`, `INDIA`, `EXPORT`; a competitive card whose title matches NON_KSSL and not PLATFORM is forced to `dir: "watch"` with `threatWhy: "Outside KSSL's product segments (...)"`; Indian/MoD text raises severity. Judgement written in code, overrides stored classification (called from dataset.js:143) |
| 2 | src/lib/shortlist.js:54-372 | `SHORTLIST_MAX = 30`, `MIN_QUALIFIED = 8`; keeps a card only if rival, `impact === "direct"`, `severity` high (medium for Indian rivals), country named in text found by regex; `DEMONYM` map (86-118) and `INDIA_PLACES` list (200-209) are hard-coded geography vocabulary |
| 3 | src/pages/competitive/Profile.jsx:885 | `<span className="cp-loc-chip">India</span>` printed as Global Locations for every company |
| 4 | Profile.jsx:916 | `` `${displayName} is actively scaling indigenous manufacturing capabilities across core defence, aerospace, and tactical systems. The company converts technological partnerships into sovereign programs ...` `` (Strategic Positioning fallback) |
| 5 | Profile.jsx:928 | `` `${displayName} is the incumbent specification across primary domestic defence tenders and tri-services modernisation programmes. ...` `` (Parallax Read fallback) |
| 6 | Profile.jsx:939, 950 | constant `0` strength/weakness counts and "No strengths on record." / "No weaknesses on record." |
| 7 | Profile.jsx:518, 535-537 | `r.detail or "Key Executive / Officer"`, `"Supporting Executive"`, `"Executive Officer"` |
| 8 | Profile.jsx:36-37 | `getInitials`: `if (!name) return "EX"` |
| 9 | Profile.jsx:59-70, 216, 1102 | `"Unattributed"` publisher fallback |
| 10 | Profile.jsx:1099; news.js:57; shortlist.js:423 | category fallbacks `"Defence"` and `"Update"` |
| 11 | Profile.jsx:72-79 | `cleanNewsCategory`: keyword map to Financial / Government / Workforce / Markets, default `"Defence"` |
| 12 | Profile.jsx:1071 | category pill vocabulary `["All", "... Updates", "Defence", "Financial", "Government", "Workforce", "Markets"]` |
| 13 | Profile.jsx:1086-1090 | grid shows unfiltered or concatenated articles when the filter leaves fewer than 9 |
| 14 | Profile.jsx:123-132 | `if (matched.length >= 2) ...; return (companyArticles).slice(0, 4)`: unrelated news shown under "News Related to X" |
| 15 | src/lib/profile.js:250-252 | `formatSectorName`: `formatLabel(rawSector) || "Defence & Aerospace"` |
| 16 | profile.js:103 | `"Counterparty"` shown as `"Competitor"`; DetailPanel.jsx:72 hides facts named stance/date/publisher/primary lens |
| 17 | src/lib/companyNames.js:50-127 | `COMPANY_NAMES`: full names and notes for ~45 companies ("Saab AB", "Indo-Russian Rifles Private Limited", "defence division of Stumpp Schuele & Somappa, established 2017", "not an abbreviation - the letters do not stand for anything") |
| 18 | src/lib/dedupeCompanies.js:52-57 | `PAIRS`: idv/iveco, rtx/raytheon, knds/nexter, huta-stalowa-wola/hsw, plus merge by same site |
| 19 | src/lib/revenueFacet.js:14-19, 23, 48 | band names with rupee thresholds, FX rates `{usd: 8500, eur: 9300, gbp: 11000, inr: 100}`, tier cut-offs 5000 / 1000 crore |
| 20 | src/lib/dataset.js:326-358 | technology pillar: title "Technology Knowledge", tile labels, filter labels "Competitor Advancements" / "Adoptable Advances", `tagWord: { rival: "", adopt: "Adoptable" }`, `dirWord: ... "Advancement"` |
| 21 | src/lib/overview.js:452-455 | `withTag` sets `dir: "watch"` on every technology card regardless of stored classification |
| 22 | src/lib/overview.js:448, 463-465 | `TECH_ATTENTION_HEAD = 30`, 60% rival share: caps what the technology overview shows |
| 23 | src/components/detailPanel/DetailPanel.jsx:26 | `detail.dir || "watch"`: every drawer shows a "Watch" pill (details carry no dir) |
| 24 | overview.js:746, 852 | `counts["threat-analysis"] = 0` and `cnt: "0 competitor moments on record"` (also "0 projects", "0 financial records", lines 748, 873, 878): fake counts in rail and print header |
| 25 | src/pages/competitive/ThreatAnalysis.jsx:26, 343 | assumed window code `"all"`; :97, :361-366 assumed level codes `THREAT` / `OPPORTUNITY`; :305-307 programme first word as image |
| 26 | Overview.jsx:74, SignalCard.jsx:40, DetailPanel.jsx:266, overview.js (client id) | fallback client name/id `"KSSL"` |
| 27 | src/components/detailPanel/DetailPanel.jsx:139-149 | eyebrow wording per impact kind ("Threat to KSSL", "Demand in a KSSL line", "Technology advance", "Competitor advance") when impact_eyebrow is not read |
| 28 | src/lib/glance.js:32-50 | gloss sentences per fact key (file is imported by nothing) |
| 29 | Profile.jsx:361 | `UNKNOWN_ORIGIN = "Origin not established"` used as a data bucket in the origin filter |

## 3. Computed in the UI (needs JS/script, versus stored value shown directly)

Rules the browser applies after the data is loaded. "Stored" means no JS step is needed beyond display.

| # | Element | Rule (file:line) | Alternative if the user wants it stored |
|---|---|---|---|
| 1 | Threat vs watch on a feed card | takes `classification` verbatim as `dir`, then `refineThreats` re-labels by keyword (threat.js:54-106; dataset.js:143) | show classification as stored (remove step) |
| 2 | Which signals are on the overview | competitive: shortlist rules (shortlist.js:237-372), cap 30, remainder moved to rival news; technology: cap 30 split 18/12 (overview.js:456-466) | show all rows of the table in the stored order |
| 3 | Order of cards | priority: direction rank threat 0 < watch 1 < fav 2, then graded before ungraded (`severityRank` is not served so all are ungraded), then newest date, then `severityRank`, then number of `sec` lenses (overview.js:121, 131-146); "Most recent": date desc then the same tie-break (overview.js:165-166) | order by competitive_signal.sequence_no |
| 4 | Rank number | position after sorting, 2-digit (overview.js:175) | sequence_no / rank_position |
| 5 | Date text on a card | `signalDate`: prefer details facts "Date", else `ago`; zero-pad day (overview.js:235-255); sort key `dateVal` (overview.js:40-57) | format event_date once |
| 6 | Headline casing, "&amp;" and em-dash rewriting | dataset.js:66,104,139,157 | store the final text |
| 7 | Tile numbers (competitive) | threats = count dir "threat"; watch = count dir "watch"; companies = distinct company; "—" when zero (overview.js:502-505, 538-540) | ui.competitive_metric.metric_value |
| 8 | Tile numbers (technology) | rival / adopt = count of cards tagged; domains = innovation categories with rows (overview.js:603-616) | serving.technology_metric.metric_value |
| 9 | Pill counts, pager range, "N of M" lines | Overview.jsx:265-273; overview.js:350-385; Layout.jsx:140-162 | none needed |
| 10 | Rail counts | profile = competitors minus client; overview = feed length; t-overview = feed length (overview.js:737-745, 800-802) | ui.*_navigation.record_count, ui.technology_ui_view.record_count |
| 11 | Roster order | client first, then by name (roster.js:7-19) | none |
| 12 | Origin filter options and counts | distinct `origin or "Origin not established"` with counts (Profile.jsx:383; countryFacet.js:260-279) | none |
| 13 | Revenue tier of a company | from `revenue_filter` else text parse with FX table (revenueFacet.js:43-51) | competitive_competitor.revenue_tier |
| 14 | Headquarters line | `tidyHq`: remove street / house number / postcode parts, keep last 3 (countryFacet.js:65-75) | show headquarters as stored |
| 15 | Revenue text | `firstFigure` (Profile.jsx:288-305); needs a "currency amount" format rule | annual_revenue + revenue_currency |
| 16 | Leader avatar initials | first letter of first and last word after removing titles (Profile.jsx:36-42) | competitive_leader.avatar_initials |
| 17 | Current position and tenure | current = experience with empty or "present" end; tenure = end year (or this year) minus start year (Profile.jsx:105-116, 121) | none |
| 18 | News: window, cap, de-duplication, index-link detection, image de-duplication, 9-card grid | news.js:114-183, 195-200, 296-310; articleUrl.js:64-81; Profile.jsx:590-616, 1086-1090 | show competitive_news_article rows as stored, newest first |
| 19 | Moment: window start/end | newest `movement_date` minus `day_count` days (ThreatAnalysis.jsx:32-49) | none |
| 20 | Moment: counts per competitor, "graded a threat" count | filter by competitor and window; count `level === "THREAT"` (ThreatAnalysis.jsx:60-70, 97) | ui.ui_competitor_moment_metric |
| 21 | Moment: sort | date desc (ThreatAnalysis.jsx:87) | display_order |
| 22 | Technology tile subline (domain names joined with "·") | overview.js:621-627 | none |
| 23 | Global search hits and the "Searched ..." line | search.js, TopBar.jsx:51-62 | none |
| 24 | Competitor dots (threat colour) | map of threat_level strings to colour class (Profile.jsx:794; ThreatAnalysis.jsx:209) | none |

Shown directly from a stored value (no JS step beyond display): card title and summary text, drawer title/summary/what/why text, source URL, starting year, employee count, sector, headquarters (modulo P14), moment title/description/analysis/category/country/company/source, time-window and level labels.

## 4. New-schema tables that belong to my pages but are not read by any page

| table | what it holds | should a page read it? |
|---|---|---|
| serving.competitive_signal_evidence | evidence_group, label, value, quote, source_url per signal | yes: drawer "At a glance" and "Key points" (D6, D9) |
| serving.competitive_competitor_location | location_name, location_type, country, source_url | yes: Global Locations chips (P15) |
| serving.competitive_leader / competitive_leader_record | leaders, experience/education rows | yes: Leadership, LeaderPage (P22-L8) |
| serving.competitive_news_article | company news | yes: both news sections (N1-N8) |
| serving.competitive_competitor_moment_analysis | view_name, analysis_text | yes: "Deeper analysis" (M22) |
| serving.competitive_competitor_moment_source | publisher, source_url | yes: drawer source (M23) |
| serving.competitive_competitor_swot | SWOT statements | no (hidden by decision) |
| serving.competitive_stock_quote / competitive_stock_series | stock | no (hidden by decision) |
| serving.fact_source | per-column source_url, publisher, quote | optional: source chip next to each company fact |
| serving.technology_overview_article, _company, _fact, _key_point, _source; technology_source | technology signal cards and drawer | yes: replace the competitive_signal "tech" lane (T6-T9, D6-D11) |
| serving.technology_metric, technology_pillar, technology_category, technology_company | tiles, pillar name, domains, company names | yes: T3-T4 |
| ui.competitive_metric | metric_label, metric_value, as_of_date | yes: O3-O4 |
| ui.competitive_navigation, competitive_pillar, competitive_ui_state | rail labels and counts, brand, drawer/loading state | optional: S1-S8 |
| ui.competitive_overview_feed | empty_message, sequence_mode, threat_filter, local_search_query, visible_signal_count | optional (state + empty message) |
| ui.competitive_news_view | category_filter, date_filter, published_range, custom dates, page_size, search_query | optional: N6, N10-N13 |
| ui.competitive_profile_view_state | selected_competitor_id, news_category, news_range, ... | optional (state) |
| ui.ui_competitor_moment_metric, ui_competitor_moment_view_state | moment metrics, from/to, time_window, selected ids | optional |
| ui.technology_overview_view, _filter, _metric_card, _signal_card, _detail_panel, _detail_section | tech overview page config and pre-rendered display fields | yes if technology overview is to be 100% DB-driven |
| ui.technology_ui_navigation, technology_ui_view, technology_pillar, technology_print_report_control, technology_metric, technology_category(+_ui_label) | rail, headings, counts, print label | optional |

## 5. Bugs and mismatches found on the way (worth fixing in the same pass)

| # | where | problem |
|---|---|---|
| 1 | ThreatAnalysis.jsx:106-124 | `useHeaderReport` receives a new object every render, so the page loops ("Maximum update depth exceeded", confirmed in the live app); also uses keys `heading`/`facts` where the print sheet reads `h`/`rows` |
| 2 | competitive_competitor_moment.competitor_id is bigint, competitive_competitor.competitor_id is uuid; also moment_id bigint | counts per competitor can never match (M3); decide the id type |
| 3 | app.py:183 and `competitive_signal.company_id` | UUID passed as the company name; no join to a name |
| 4 | app.py:189 | reads `source_url` from competitive_signal (no such column) |
| 5 | app.py:199 | `summary` set to why_it_matters, so the drawer shows it under "What the article says" |
| 6 | app.py:155 vs countryFacet.js:105 | backend key `origin`, UI reads `country`: origin filter always empty |
| 7 | app.py:162 vs profile.js:294 | `sales` served as a string, profile expects an array of rows: revenue always "—" |
| 8 | app.py:157 vs Profile.jsx | parallax_read served as `description`, never read; `strategic_positioning`, `revenue_tier`, `revenue_currency`, `legal_name` not served |
| 9 | Profile.jsx:468-479 | `/api/pulse` fetched but result never shown |
| 10 | search.js:69 | client row in `data.competitors` is offered as a searchable competitor; opening it loads the client's profile |
| 11 | classification value vocabulary | threat.js/overview.js/DetailPanel expect lowercase threat/watch/fav; the schema holds free `varchar(20)`; lane routing by "tech"/"market" prefix (app.py:176-177) conflicts with classification meaning threat/watch |

## 6. Summary

156 rows in section 1: COMPUTED-JS 46, CHROME 31, INVENTED 29, STORED 25, NO-COLUMN 21, n/a 4 (rows already tagged "+" with a second Kind are counted under the first). Section 2 lists 29 invented items; section 3 lists 24 computed rules.
