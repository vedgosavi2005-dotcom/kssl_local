# DB change notes from frontend changes

Frontend-only changes that touch what a table holds or how it is used. **Nothing here has been applied to any
database**; each entry says what would change if the DB side is ever aligned.

## 2026-10-17 · "Competitor Moment" renamed "Competitor Movement"

Frontend: the rail label (`src/lib/route.js`), the page eyebrow, the drawer view/title and the empty text
(`src/pages/competitive/ThreatAnalysis.jsx`). The route key stays `threat-analysis`, and code names stay `moment*`.

DB impact: **none required.** The label is front-end chrome; no table carries the visible word today
(no `staging_ui` row contains "moment"). Only names would differ, if renamed for consistency later:
- staging/serving tables `competitive_competitor_moment`, `competitive_competitor_moment_source`,
  `competitive_competitor_moment_analysis`
- ui tables `competitive_competitor_moment_level`, `competitive_competitor_moment_time_window`,
  `ui_competitor_moment_metric`, `ui_competitor_moment_view_state`
- prompt `prompts/moment.yml` (its output text should say "movement" where it addresses the reader)

## 2026-10-17 · Competitor Profile: "Global locations" removed

Frontend: the Global Locations row of Company details, its line in Print/Export, and its field in the Copy
payload (`src/pages/competitive/Profile.jsx`; the unused `.cp-loc-*` CSS deleted).

DB impact: `serving.competitive_competitor_location` (318 rows, 50 competitors in local staging;
loaded by `backend/location_load.py`, shipped as `competitors[].global_locations` by
`backend/areas/a_competitive.py`) is **no longer displayed on the profile**. It is **still read** by the
country filter (`src/lib/countryFacet.js` unions geo footprint + global_locations + HQ), so the table and its
loader stay needed. Drop it only if the country filter stops using it too.

## 2026-10-17 · Geo Footprint rebuilt to the reference (Cummins :8101) layout

Frontend (`src/lib/geo.js`, `src/pages/competitive/Geo.jsx`):
- market list: the client row in the client colour reading "<client> present"; badges "◉ overlap" / "◎ category only",
  country badges "◉ N contested" / "◎ N category only"
- client → country: the reference overlap table (Rival · Overlapping categories · Matched pairs · Datasheet outcome ·
  Presence), then "What this means for <client>" (the stored geo analysis, moved here from the top of the market list)
- rival → country: "Products <rival> sells" with each product's client counter and verdict pill, and the product
  comparison pane (grouped spec table, ▲ on the winning side, gap, "ahead on" lines, qualitative differences)

Everything is read from existing stored rows; nothing is paired or graded in the browser. **No table change required.**
Tables read: `serving.competitive_geo_company_presence` (overlap_status, matched_ranges, activity),
`serving.competitive_matchup` (+ `_specification`: win, gap, group; edge_score -> verdict via the Product Evaluation
thresholds), `serving.competitive_product` (category; the rival list shows products in the client's categories plus any
with a stored comparison), `serving.competitive_geo_analysis`.

Data gaps that leave parts of the reference layout empty (DB/prompt side, **not implemented**):
1. `competitive_geo_company_presence.matched_ranges` is empty on almost every row, so "Overlapping categories" falls back
   to the categories of the stored comparisons with that rival (or "—"); the "meets <client> in …" line never shows.
2. `competitive_matchup.edge_score` is NULL on 21 of 43 local pairs -> pill "Not decided: no stored verdict" and those
   pairs do not count in "Datasheet outcome".
3. `competitive_matchup_specification.win` is set on 34 of 469 spec rows and `gap` is mostly NULL -> few ▲ marks,
   empty Gap column and no "<side> is ahead on" lines.
4. No per-matchup datasheet/source link is shipped (the reference prints "<rival> datasheet ↗ · <client> datasheet ↗"
   under each comparison) -> would need the matchup's source URLs (e.g. a `competitive_matchup_source` table or the two
   products' source_url) added to the matchup payload.
5. The reference product row carries a class line (rating band · rating · frequency · type); `competitive_product` only
   has `category`, so the row shows the category. A stored product class / key-rating column would fill it.
6. Presence words are the stored activity (Local production / Licensed production / Export / Sales and service /
   Sourcing); the reference's "builds here / exports in / partner" are not mapped.

## 2026-10-17 · Market > Global Requirements: OPPORTUNITY tag, WATCH pill, Key points

Frontend: every stored requirement card (`req-<requirement_id>`) carries the lane kind `requirement` (`src/lib/dataset.js`),
so its row shows the yellow "OPPORTUNITY" tag (`marketLane().tagWord`, `.dirtag.k-requirement`) and its detail panel the
"WATCH" pill (`marketLane().panelStance`); the panel's "Key points" shows the stored strategic assessment when the
record has no article statements (`src/components/detailPanel/DetailPanel.jsx`).

DB impact: **no table change required.** Key points read `serving.market_global_requirement.strategic_assessment`
(already shipped as the detail's `why`). Notes, **not implemented**:
1. The WATCH pill and the OPPORTUNITY tag are the lane's words (every global requirement is a perceived opportunity on
   watch, as in the reference); `market_global_requirement` has **no stance column**. If requirements ever need their
   own stance (threat / watch per row), add one (e.g. `market_global_requirement.direction` with the threat|watch check)
   and have `requirement_assessment`/the prompt fill it; the panel would then read it instead of the lane word.
2. The reference's key points are 1-4 bullets; the stored assessment is one paragraph, shown as one bullet. A stored
   bullet list (e.g. a `market_global_requirement_point` child table, or an array column) would give separate bullets.

## 2026-10-17 · Market > Tenders: Matched products and Competitor fit

Frontend (`src/pages/market/Tenders.jsx`, `src/styles/tender.css`): both sections already existed and render whenever
the tender carries the rows. Fixed how the stored rows print:
- a matched product's pill shows the stored percentage, else the stored fit word ("partial fit"), else "— fit"
  (it printed a bare " fit" because `fit_percent` is empty on most rows)
- a stored match line is `[label, value]` (`market_tender_product_match_line`); it printed a ▼ and dropped the label.
  It now prints "• Label: value"; an arrow only for a reference-style `[up|down, text]` line
- the rival's fit pill is readable (it was white on white) and reads "<word> fit"

DB impact: **no table change required.** Data gaps (DB/prompt side, **not implemented**):
1. Coverage: of 292 open/closing tenders in local staging only 87 have a `market_tender_product_match` row and 53 a
   `market_tender_competitor_fit` row (132 have a `market_tender_fit_assessment`). Every other tender shows neither
   section -- `tender_assessment` needs to run on the live tenders.
2. `market_tender_product_match` has no rationale column; the reference card carries a one-line reason under each matched
   product. 422 of 607 matches also have no `_line` rows, so they show only the product and the fit. A
   `match_rationale text` column (filled by the prompt) would give every card its reason line.
3. `fit_percent` is set on 69 of 607 matches; the pill falls back to the fit word.

## 2026-10-17 · Technology: ADOPTABLE / stage pill / "<client> behind" labels

Checked against the reference: ADOPTABLE (Technology overview) and the "<client> behind / at parity / ahead" pill
(Innovations) were already wired. Frontend change: the Innovations row pill now prints the short stage word of the
stored maturity code (`technology_innovation.maturity` -> LAB / IN DEVELOPMENT / IN PRODUCTION / FIELDED / IN SERVICE,
words in `src/lib/innovation.js` MAT_LAB) as the reference does; the stored sentence
(`technology_innovation_status.maturity_label`) moved to the pill's tooltip and stays in the detail panel.

DB impact: **no table change required.** Data gaps (**not implemented**):
1. Position: 14 of 15 local innovations store gap `unknown` and no `position_label`, so only one row carries a
   "KSSL behind" pill. The prompt (`innovation_detail`) has to assess the client position for each innovation.
2. "IN PRODUCTION" appears only for maturity code `prod`; no local innovation has it today (12 dev, 2 fielded, 1 lab).
3. Coverage: the 15 innovations sit in 3 of 10 domains (Protected & Armoured Vehicles, UAVs & Drones, Missiles & Air
   Defence); the other tabs (Artillery first) are empty until `innovation_discovery` fills them.

## 2026-10-17 · Layout fixes, rupee display, revenue-tier filter

Frontend only: profile news cards line up (fixed 3-line headline, one-line meta/source; the news list's category chip
no longer overruns the source column); Partnership's expand button sits clear of the header line; the Top opportunity,
Market outlook, Awarded/Active/Closed and By-category tables use fixed column widths with wrapped, 3-line-clamped
text; the Market Intelligence category filter is plain text (no category colours); the "Data: …" footers under the
Market Intelligence tables are removed; stored codes such as `need_stated` read as words; a long metric value
steps down a size and clamps to two lines; the Competitor Profile always shows the revenue-tier filter under the
origin filter.

DB impact / gaps (**not implemented**):
1. **Indian rupees.** Value totals are now formatted in rupees, Indian style (`₹ 472 Cr`, `₹ 8.5 L`, see
   `src/lib/tenderValue.js`). An INR amount is shown directly; any other currency is converted **only with a stored
   exchange rate**, read from the dataset key `fxRates` (`{ "USD": <rupees per unit>, … }`). No rate exists in the DB
   today, so non-INR amounts still show in their own currency. To switch everything to rupees: add a rates table
   (e.g. `serving.fx_rate (currency_code char(3) primary key, inr_per_unit numeric not null, as_of_date date not null,
   source_url text)`) and have the backend ship it as `fxRates`. No rate is written in code.
2. The Top opportunity "Tender value" tile prints the stored `market_top_opportunity_metric.formatted_value` text
   ("UAH 2.41 bn · CZK …"), which the frontend cannot convert. The `top_opportunity` lane should write this metric in
   INR (formatted_value in ₹ Cr, amount_value in rupees, currency_code `INR`) once rates exist.
3. Revenue tier: no competitor carries a revenue tier in local staging (`competitive_competitor.revenue_filter` empty),
   so the filter shows "No revenue tier on record yet" until the competitor prompt / Excel load fills it.
4. `market_tender` / `market_award` stage codes (`need_stated`, `approved_funded`, `rfi`) are displayed as words; a
   stored label column would let the wording be edited without code.

## 2026-10-18 · Competitive overview: story timeline drawn like the Projects timeline

Frontend (`src/components/detailPanel/DetailPanel.jsx`): the signal panel's "Story timeline" uses the Projects timeline
look (`.pj-time`: dot rail, formatted date, event line, change note in grey, source chip); steps whose stored type is
"Label change" (a stance moving, not an event) are not listed; "planned" steps read "(expected)". **No table change.**
Note: story steps with no date print "date not stated" (`story_step` rows without `step_date`); the prompt should date them.

## 2026-10-18 · Card date = the article's publication date (DB change, approved by the user)

Problem: competitive cards showed `competitive_signal.event_date` (the date of the event the prompt read in the article),
not the article's publication date; 81 cards had no date, 56 more showed a date other than the publication date.

Done:
1. **Schema** `db/setup/15_signal_published_date.sql`: `competitive_signal.published_date date` in staging and serving
   (applied to local `kssl_staging` / `kssl_serving`; wired into `db/make_databases.sh` and `deploy/deploy_vps.sh`).
   Approve copies it with the card.
2. **Backfill** (local staging): 281 from the article's stored record (`source_document.published_at`, matched on
   `competitive_signal_detail.source_url`); 57 more from the article page's own date markers
   (`scripts/backfill_published_dates.py`: JSON-LD datePublished/dateCreated, published-time meta, a publish `<time>`
   or date-classed element, URL date; future / pre-2000 dates ignored; only NULLs written). Now 338 of 474 dated.
3. **Backend** (`backend/areas/a_competitive.py`): card `ago` = `published_date`; the event date ships as `eventDate`.

Follow-up done by the prompts lane (kssl-52, 2026-10-18): the loader writes `published_date` (loader token
`article_published_date`: `source_document.published_at` for the article URL, else the subject's own date; future dates
dropped; else NULL) and `signal.yml` maps it; the harvester reads date-classed elements and labelled dates
(`<b>Date:</b> 27 Apr, 2022`), and `backend/news.py` falls back to JSON-LD `dateCreated`. brahmos.com
`brahmos-in-media/N` pages are the articles' own reprint pages (not listings): 53 brahmos + 1 geaerospace dated from their
`Date:` label. **Now 392 of 474 dated.**

knds.com (2026-10-18): the article pages carry no date, but each LISTING card does ("14 October 2026", Strapi
`publicationDate`). `scripts/knds_listing_dates.mjs` opens knds.com/en/press-releases (and /en/news), presses
"Load more" until all cards are loaded and maps article URL -> card date: 36 of the 38 knds signals dated (NULLs only).
The 2 left are /en/news posts, whose listing shows no date. **Now 428 of 474 dated.** The harvester should do the same
for knds (listing date by URL) so new knds articles arrive dated.

Still undated (46), left NULL on purpose ("date not known", nothing guessed): 2 knds.com news posts, 11 signals with no
source URL, and pages that state no date or could not be fetched.

Open question: 60 dated cards are older than a year (all 53 brahmos pieces date 2006-2025: archive reprints). With the
card date now the publication date they read as years old; an age cut on the overview (or a lower sequence) is a
product decision, not made here.

## 2026-10-18 · Competitive pillar spec: 10-threat cap, risk order, probability-impact matrix; Products revenue filter

Frontend/backend (no table change): the competitive card ships its stored `time_to_effect` and
`in_client_market` (`backend/areas/a_competitive.py`); threats are ordered probability x impact, then sooner effect, then in
a client market (`compareRisk`, `src/lib/overview.js`); at most `THREAT_CAP` = 10 threats are offered on the overview
(`capThreats`). The probability-impact matrix is the backend classification (user, 2026-10-18): it is not drawn in the UI. Products always shows the revenue-tier filter (empty -> "No revenue tier on
record yet").

Prompt/DB side, handed to the prompts lane (**not implemented here**):
1. Watch is everything not a threat (460); the spec's watch is "not yet materialised, not immediate, may become
   significant". `derive.signal_label` needs a rule that drops (or does not store) materialised low-impact events.
2. `signal_label` still emits `fav` (3 rows); the spec has threat and watch only.
3. No funding indicator (spec: "increase in funding"); the six impact dimensions have none.
4. Competitor qualification (same product line AND same market) is not tested per company; competitors are the fixed list.
   A stored per-competitor qualification (e.g. `competitive_competitor.qualifies` + reason) and a new-entrant candidate
   list would cover the spec.

## Card dates, second pass (2026-10-18)

`scripts/backfill_published_dates.py` reads three more date places, each checked against the 416 already-dated
articles before it was trusted:
- an element holding only a date right under the page's title heading (MBDA's date pill): 97 of 99 agree;
- a press-release dateline opening a paragraph ("Lucknow, June 03, 2022:"; Adani Defence);
- URL timestamps `...20260511140100` (ANI) and `/20260615-` (France 24);
- a `meta_date`-style class holding only a date (chakranewz byline); a date equal to today is ignored (site header
  clocks gave 2026-10-18 on bharatshakti / globaldefensecorp).
Sites that refuse a plain request are read in a real browser: `node scripts/browser_pages.mjs urls.txt pages.json`, then
`--pages pages.json` (aviationweek dated this way; ndtv, naval-technology, airforce-technology, militaryembedded refuse
the browser too). **20 more dated, now 438 of 474** (NULLs only, local staging).

Left undated on purpose: spslandforces.com prints only "Issue 2 - 2019" (no day or month; the issue page has none either),
defence-ua.com pages state no date, 2 knds.com news posts, 11 signals with no source URL, the 4 bot-walled sites.
DB idea, not implemented: a `published_precision` ('day' / 'year') column would let the card show "2019 (Issue 2)".

Note for the prompts lane: the older markup rule disagrees with the stored date on 15 of 66 dated articles (mostly
today's-date header clocks, fixed above; israeldefense.co.il picks a related item's date). Dates written earlier by that
rule should be re-checked.

## Tenders: client fit first (2026-10-18)

Frontend only. The Tenders list puts tenders with a stored client fit first (the stored match % else the grade:
strong > partial > weak), then the nearest deadline (`compareTenders` in `src/lib/tenderRow.js`, test
`test_tender_order.mjs`). The sort note reads "<client> fit first, then deadline". `ui.market_tenders_view.sort_label`
is empty in both DBs and the page never read it; if it is ever filled it should carry this wording.

## Red-team audit, frontend + API half (kssl-40, 2026-10-18)

Security:
- **CSRF on review writes**: POST /api/review* and /api/news/refresh took query params only, so another website could fire
  them from an operator's browser (127.0.0.1, or the review host once basic auth is cached). Every non-GET now needs
  `X-KSSL-Write: 1` (backend/app.py middleware; Review.jsx sends it). A custom header forces a CORS preflight, which
  allow_methods=["GET"] refuses.
- **SSRF in /api/img** (vite.config.js, served by vite preview on the VPS too; found by kssl-52): it fetched any URL and
  followed redirects. Now public http(s) hosts only, ports 80/443, no credentials, every redirect hop re-checked, 8 MB
  cap (src/lib/imgGuard.js, test_img_guard.mjs). Ceiling: DNS rebinding between check and fetch.
- Trace `sql` (display string) quoted the key raw; quotes are now doubled (the queries were already parameterised).
- Checked and fine: bad tables / actions / schemas -> 400, live backend has no write routes (404), docs off,
  /api/news params validated, review site behind Traefik basic auth.

Invented or defaulted values removed from the UI:
- formatDate() with no value printed TODAY: undated competitor moves showed today's date. Now "" -> "date not known".
- Partner overlap was guessed in the browser by folding names; now read from the stored
  `competitive_partnership.overlap_kind / overlap_client_partner_id` (served `overlap`).
- Product verdicts (AHEAD / NEAR PARITY / BEHIND, Geo "superior product") were cut from edge_score at 58 / 42 in code;
  now the stored `competitive_matchup.decision_level` (backend ships it as `decision`).
- Spec bars graded leads "decisive / clear" with 5 / 15 / 35 % bands; now the stored `better_side` only.
- Geo "KSSL Absent ⚠" when a country simply had no client row -> "KSSL not on record here".
- Leaders with no end date read "– Present"; only a stored present / current does now ("From 2018" otherwise).
- Technology feed forced every card to "watch", hiding 52 stored threats; stored threats now show.
- Undated tenders defaulted to open and counted as active; the stored status decides.
- A tender closing today read "Closed / Expired"; now "closes today".
- Requirement cards put the (future) deadline in the card date; now the stored `stage_date`.
- "Where demand is heading" (a count of collected records) renamed "Activity by segment".
- Competitor Movement header counted every news row; now the same count as the rail (rows with a level).
- Client name typed in code (partners brand check, project option wording) -> client_account.
- Metric tiles: "12 Cr" animated as "12"; only bare numbers animate now.
- Market chart: no-category ("—", 723 tenders) and the stored "Other" took hues and pushed
  "Protected & Armoured Vehicles" into grey "Other"; they are grey by meaning now.

Found, for the database lane:
- Local `kssl_serving` is entirely `db/test_seed_full` (invented companies, img.example.com). The VPS serving DB is clean.
  Reseeding local serving needs the user's go-ahead.
- 723 of 1,626 tenders carry no category.
- techCards still store a "fav" stance (176); the UI shows it as watch.

Left as is (judged chrome or display): Positioning free compare marks the better stored number (EDGE_DEADBAND 'tie');
the Technology rival / adoptable lanes split on the stored competitor field; partners' 2-year "last seen" note;
companyShort acronyms.

## Year-only card dates (2026-10-18, user: "take year")

- `competitive_signal.published_precision` text ('year' / 'month', NULL = full date), staging + serving, CHECK constraint;
  added to `db/setup/15_signal_published_date.sql` (idempotent; already run by make_databases.sh and deploy_vps.sh).
  Applied to local kssl_staging and kssl_serving.
- `scripts/backfill_published_dates.py`, last rule: a magazine issue line ">Issue 2 - 2019<" stores 2019-01-01 with
  precision 'year' (SP's Land Forces). Written: 1 signal (its duplicate was removed by the dedupe).
- Backend `published_text()` ships "2019" (year) / "2019-05" (month); `formatDate` keeps a bare year as the year.
- For the prompts lane: the loader and harvester should write published_precision when only a year or month is known.

Local kssl_serving reset (user: remove all test data): every row in the 174 serving tables is db/test_seed_full (0 keys
shared with staging); the ui schema is already empty. The TRUNCATE was blocked by the session's safety classifier, so it
waits for the user to run it or allow it.

## Duplicate tenders merged: one procurement = one tender (2026-10-18, user decision 3; kssl-52)

Local staging only (backup of every touched table taken first). `python -m backend.harvest_tenders --merge [--dry-run]`.
- Scope = the user's groups (same title + buyer + closing date), with the portal rule inside each group:
  Prozorro / DECP (France) / Diavgeia records are never merged (each record IS its own procurement, contract or decision:
  14 Prozorro groups and 1 DECP group stay separate); UK Find a Tender notices merge only when they share the OCDS `ocid`
  (2 UK groups have different ocids: separate); a group whose notices name different winners is not merged (2 groups:
  "Procurement of 40mm Grenades", "Carbine weapon scope and mounts" - separate lots / contracts).
- Result: 84 groups, 110 duplicate tenders merged; tenders 1,626 -> 1,516; 0 notices lost: every notice stays a
  `market_tender_source` row (1,626 rows) with its notice number in the new column `market_tender_source.notice_reference`
  (db/setup/18_tender_notice_merge.sql, staging + serving; wired in make_databases.sh and deploy_vps.sh).
- Kept tender = most assessment rows, then the latest notice; it takes the latest notice's status / closing fields, the
  earliest published_date, and any value it lacked from the others. Children (fit, matches, competitor fit, eligibility,
  requirements, closing windows, top-opportunity rows, next moves) move when the kept tender has none of that kind, else
  the duplicate's copy is dropped (assessments 685 -> 645). Raw notices, opportunities, story steps and fact_source rows
  are re-pointed. Awards rebuilt: 503 -> 461 (one award per tender).
- Going forward: `stage()` attaches a re-publication / corrigendum (same ocid, or same title + buyer + deadline) to the
  existing tender as a secondary source row instead of a new stub; award notices without a deadline are merged after
  extraction by `market_rollups merge` (first step of the routine run; winner check included). The tender prompt runs once
  per tender (its primary source; latest raw notice), not once per merged notice. Category summary counts distinct tenders.
- Found, not caused by the merge: 331 raw notices point at tenders removed earlier (an older prune); they are status
  'staged', so the harvester will not re-stage them. Open.

## Only qualifying competitors reach the UI (2026-10-18, user decision 5; kssl-52)

User: "on ui show only those competitor which qualifies in backend keep all and when some new news comes and it matches the
qualify criteria put them on ui".
- The database keeps every competitor and row. `backend/areas/a_competitive.visible_database()` (called first in
  `app.build_dataset`) builds the dataset from a view without the competitors whose `qualifies` is not true (NULL = not
  testable = hidden): rows naming one by id, every row hanging off a removed row (review.GRAPH, transitively: products,
  specs, matchups, signals, partnerships, projects, patents, stories, movements ...), rival rows naming one by name (tender
  competitor fit, opportunity rivals), technology companies of that name and the articles they lead; a rival_to_beat /
  rival_display / selected_competitor_id naming one is emptied. Applies to :8600 and :8601 alike.
- Leak check: `python -m scripts.check_hidden_competitors` (exit 1 on a leak). Now: 50 stored, 37 qualify, 37 shipped +
  the client; 0 hidden ids in the dataset; hidden names remain only inside free text of other cards, and one product of
  Kongsberg named after its teaming partner (Patria NEMO). Review :8601: 132 competitive cards (121 watch, 11 threat).
- Re-test after EVERY load: prompts/run.py (every loaded run, handler prompts included), the Excel loads
  (backend/excel_load.py), product-class runs (client_subtype, matchup_class), and the geo derive hook. A competitor that
  starts to qualify appears on the next dataset.

Year-only dates (for kssl-40): nothing to change in the loader or harvester today. The loader's published_date comes from
`source_document.published_at` (a full date) or the news job's date, so its precision is a full date (NULL); the harvester
never stores a year-only date (a bare year is not parsed as a date). A year-only date exists only through the backfill rule.
If harvest-time year dates are wanted, `source_document` needs its own precision column first.

Follow-up (same day, kssl-52), from kssl-40's on-screen check and the user's question "Anduril makes drones, why ...":
- Bug fixed in `qualify_competitors`: country names were compared as written, so an origin stored as "US" / "UK" never
  matched a market stored as "United States". Every country now goes through `staging.country_reference` (name, ISO code,
  aliases). Anduril and AeroVironment now qualify (same line: loitering munitions / large multirotor UAS, as KSSL's Bayonet,
  Cleaver and Bharat 150; same market: the United States, where KSSL's 155 mm Mobile Tactical Cannon bid with AM General is
  on record as a planned export). 39 of 50 qualify.
- Leak fixed: two tech cards carried company "HII" (stored as "Huntington Ingalls Industries"). The filter and the leak check
  now use every name the news job knows (db/news_aliases.csv via `backend.news.subject_for`: search name, aliases, conditional
  acronyms such as HII); an alias shared with a shown company ("KNDS" in "Nexter (KNDS France)") is not used.
  Leak check: 0 hidden ids, no name-valued field holds a hidden company (the Kongsberg "Patria NEMO" product name stays).

## Market amounts in INR (2026-10-18, user request)

- New setup table `fx_rate` (currency_code PK, inr_per_unit, as_of_date, source_label, source_url) in staging + serving,
  `db/setup/21_fx_rate.sql` (serving guarded by only_via_approve; wired in make_databases.sh and deploy_vps.sh; listed in
  review.SERVING_TABLES so the review site approves it as a whole table).
- `scripts/load_fx_rates.py --write`: 30 rates. ECB euro reference rates crossed via INR (EUR 1 = INR 106.864, 16 Oct
  2026); UAH from the National Bank of Ukraine (UAH 1 = INR 2.1165), which the ECB does not quote. Re-run to refresh.
- Backend ships `fxRates` (e_ui_port). The browser converts with these only: Tenders "Value disclosed", tender card
  Value, award values, segment / winner totals. A currency with no stored rate keeps its own code.
- Live: serving.fx_rate is empty until the fx_rate setup table is approved on the review site.
- Not converted: amounts inside headlines / prose, and global requirement value_text (free text, the source's words).
- Prompts lane: the Top opportunity "Tender value" tile is stored text from backend/market_rollups.py; asked to convert it
  with fx_rate.
