# Audit group B: Products, Product Evaluation (Positioning), Gap Analysis

Scope: routes `products`, `positioning`, `gap-competitive`.
Read-only audit, 2026-10-16. Schema reference: `docs/audit_v2/schema_v2_columns.txt`. Backend reference: `backend/app.py` (single file, 576 lines).
DB state checked: every table named below is EMPTY in the local `serving` / `ui` schemas (0 rows), so everything here is traced from code, not from data.

Legend. Kind: STORED, COMPUTED-JS, COMPUTED-BACKEND, CHROME, INVENTED, NO-COLUMN. Action: map, keep, hide, remove, decide.
"Served today" = what `GET /api/dataset` actually puts in the payload (not just `data.database.*`, which carries raw tables but no page reads them).

---

## 0. Headline findings

1. **The backend serves almost nothing the Products page needs.** `build_competitors` hard-codes `"products": []` and `"competitorNews": {}` (`backend/app.py:164`, `:521`). `competitive_product`, `_specification`, `_program`, `_news`, all four `client_product*` tables, and `competitive_product_evaluation*` are read by no builder. Today the Products page lists no competitor products; KSSL products are guessed from matchup rows (`Products.jsx:934-964`).
2. **When products have no specs the page prints invented specs, invented programmes and a keyword-picked stock photo** (`Products.jsx:427-483`, `:485-599`, `:351-424`). With the empty backend list this is mostly dormant, but it fires the moment any product exists without specs.
3. **The parity / edge view would NOT show a prompt's output directly.** The stored `edge_score` is copied to `m.edge` (`app.py:456`) and then overwritten in the browser by `computeSpecEdge` (`dataset.js:397-399`). That function needs `spec.cn`, `spec.kn` and `spec.hi` (`edge.js:91`). The backend sends no `cn`/`kn` at all and `hi: None` (`app.py:429`), and the schema has no direction column. Result: every matchup gets `edge = null`, the dossier says "NO SPEC-LEVEL EDGE", the gap block is empty (`specs.js:370`), and Gap Analysis shows "No scored comparisons yet" (`GapAnalysis.jsx:124`). `decision_level`, `better_side` (served as `win`) and `gap_value` (served as `gap`) are never read by any JS. Details in sections 3 and 5.
4. **Gap Analysis is 100% computed in the browser and carries a large body of authored prose.** There is no stored gap table in the new schema. The aggregation rules are legitimate "computed from DB values" if they read the right columns, but `gapAnalysis.js` carries ~80 hand-written sentences, some with figures, plus severity ladders (sections 1.3 and 2). The route is archived (off the rail, still routed: `route.js:22-23`, `:55`).
5. **Join-key type defects in the new schema** block exact joins: `competitive_matchup.competitor_product_id` is `bigint` but `competitive_product.product_id` is `uuid`; `competitive_product_news.matchup_id` is `uuid` but `competitive_matchup.matchup_id` is `bigint`; `competitive_product_evaluation.kssl_product_id` is `uuid` but `client_product.client_product_id` is `bigint`. The UI currently compensates with fuzzy name matching (`Products.jsx:60-161`, `:972-977`), which is a computed join that guesses. See section 4.
6. **Numeric columns arrive as strings.** `json_value` turns `Decimal` into `str` (`app.py:42-43`), so `edge_score`, `gap_value`, `*_value_numeric` reach the browser as `"62.5"`, not `62.5`. Any JS that tests `typeof s.cn === "number"` (`specs.js:286`) fails unless the backend casts.

---

## 1. Per-page tables

### 1.1 Products (`src/pages/competitive/Products.jsx`, route `products`)

Reachability note: the left roster excludes the client (`Products.jsx:735`), so the KSSL branch (`:934-964`) is only reachable through a global-search jump (`takePending`, `:839-855`).

**Left sidebar (company roster)**

| UI element | dataset key / field | served today? | new-schema column to use | Kind | Action |
|---|---|---|---|---|---|
| Company list membership and order (`Products.jsx:727-780`) | `data.competitors`, `data.compOrder` | yes: `competitive_competitor` row via `build_competitors` (`app.py:140-167`), alphabetised by `roster.js` | `competitive_competitor.competitor_id`, `display_name` | STORED, plus COMPUTED-JS merge: name-key dedupe at `Products.jsx:756-777` and `dedupeCompanies.js` via `dataset.js:139` | keep list; remove both dedupe heuristics (duplicates are a data problem, not a UI one) |
| "Companies (N)" count (`:1233`) | `filteredCompanyRoster.length` | n/a | none | CHROME + count | keep |
| Company name (`:1322`) | `competitors[cid].name` | yes: `display_name`, else `legal_name` (`app.py:152`) | `competitive_competitor.display_name` | STORED + COMPUTED-JS transform `cleanCompanyName` (`:37-42`): cuts at the first "(" and the first "-", strips Pvt/Ltd/Inc/Corp. Truncates "Rolls-Royce" to "Rolls" | map; remove transform |
| Threat dot colour (`:1321`) | `competitors[cid].threat` | yes: `threat_level` (`app.py:154`) | `competitive_competitor.threat_level` | STORED + INVENTED default `co.threat \|\| "watch"` (`:744`). Colour rule: `high`=threat, `fav`=fav, anything else watch | map; no value means no dot; decide the allowed vocabulary (not defined in schema) |
| Country filter options (`:862-865`, `:1238-1251`) | `companyCountries(d,cid)` (`countryFacet.js`): union of footprint keys `geoData[cid]`, country names mined out of `global_locations` prose, and `hq` parts that match a vocabulary built from geo, tenders and matchups | not directly: `hq`, `global_locations` served raw (`app.py:158,160`), footprint from `competitive_geo_company_presence` | `competitive_competitor.origin_country` (single value) or `competitive_competitor_location.country` (many; not read) | COMPUTED-JS heuristic (string mining) | map to `origin_country`; decide whether a multi-country filter is wanted (then serve `competitive_competitor_location`) |
| Category filter options (`:705-707`, `:866-869`) | distinct `co.products[].category` through `formatCategoryTitle` | NOT served (`products: []`, `app.py:164`) | `competitive_product.category` (`category_filter` is the normalised key) | COMPUTED-JS (distinct) | map |
| Revenue-tier filter (`:800-804`, `:1270-1285`) | `revenueTierOf(co)` (`revenueFacet.js`): `co.revenue_filter`, else parse `co.sales` text, convert with an FX table, bucket at 5000 / 1000 crore | NOT served: `revenue_tier` not mapped; `annual_revenue` is served as `sales` (`app.py:162`) but as a bare number string the parser cannot read, so every company lands in "unknown" | `competitive_competitor.revenue_tier` (also `annual_revenue`, `revenue_currency`) | COMPUTED-JS + INVENTED constants (FX 8500/9300/11000/100 at `revenueFacet.js:23`, thresholds, label wording with figures at `:14-19`) | map to stored `revenue_tier` only; delete derivation and FX; label text = stored tier text (decide) |
| Company search box (`:1288-1296`) | name, sector, cid (`c.hq` is never put on the row, so that term is dead) | n/a | none | CHROME | keep |

**Right pane, catalogue view**

| UI element | dataset key / field | served today? | new-schema column to use | Kind | Action |
|---|---|---|---|---|---|
| Header "{Company} Product Portfolio" (`:1690`) | company name | see above | `display_name` | CHROME + STORED | keep |
| Category group heading (`:1766`) | `product.category` = `formatCategoryTitle(obj.category \|\| co.sector)` (`:998`); default "Defence Systems" (`:48`, `:1060`) | competitor products: not served; KSSL: `m.cat` = matchup `category_code` (`app.py:440`) | rival: `competitive_product.category`; client: `client_product.category` (+ `subcategory`) | STORED + INVENTED fallbacks (sector, "Defence Systems") | map; remove fallbacks; empty category shows the chrome label "Uncategorised" |
| Per-category count chip (`:1769`) | `prodList.length` | n/a | `competitive_product.category_count` exists, unread | COMPUTED-JS (count of what is shown) | keep computed; ignore stored column (it would disagree under a search) |
| Collapse state (`:810-818`) | local state | n/a | `competitive_product.is_collapsed` (UI state stored in a data table) | CHROME | keep local; column is not needed |
| Product card name (`:1830`) | `product.name` = `formatProductName(stripCompanyPrefix(name,...))` (`:989`) | NOT served (rival); client from `m.bf` (`:936-956`) | rival: `competitive_product.product_name`; client: `client_product.product_name` | STORED + display transform | map |
| Product card image (`:1846`) | `getProductImage` (`:351-424`) | n/a | `competitive_product.image_url`, `client_product.image_url` exist | INVENTED (keyword stock-photo pick, see section 2) | hide (rule 4); remove the function and both tables of URLs |
| "View Specs ->" button, Search box, Category select | local | n/a | none | CHROME | keep |
| Empty state `No products found for X matching "Y"` (`:1903`) | | n/a | none | CHROME (wording wrong when no search text is typed) | keep, reword |
| KSSL product list (`:934-964`) | derived from matchups: unique `client_product_name`, first matchup wins (`:942`) | indirectly, via matchup | `client_product.product_name`, `category`, `subcategory`, `product_family`, `model_code`, `status` | COMPUTED-JS (reverse-engineering a catalogue from comparisons) | map to `client_product`; decide how KSSL is selected (needs a sidebar entry from `client_account.client_name`) |

**Right pane, product detail ("View Specs")**

| UI element | dataset key / field | served today? | new-schema column to use | Kind | Action |
|---|---|---|---|---|---|
| Title "{Company} - {Product}" (`:1367`) | names | see above | names | STORED | keep |
| Photo + "Photo source: ..." (`:1394-1403`) | `getProductImage`, `imageSource` | not served | `image_url`, `image_source_url` | INVENTED / STORED | hide |
| Technical specifications table (`:1431`) | `getResolvedSpecs(product)` (`:427-483`): own `product.specs` else a hard-coded block chosen by name/category keywords | rival specs: NOT served (`products: []`); KSSL specs: taken from the first matchup's client values (`:944`, `specs.js:138-149`) | rival: `competitive_product_specification` (`spec_label`, `spec_value`, `unit`, `source_count`, `source_url`); client: `client_product_specification` (`spec_name`, `value_text`/`value_numeric`, `unit`, `spec_group`, `display_order`) | STORED path + INVENTED fallback (section 2) | map; remove `getResolvedSpecs` fallback; no rows means chrome empty text. Use an ordered list, not an object keyed by label (object drops duplicate labels and `display_order`) |
| Spec value + unit text | `specValueWithUnit(v,u)` (`specs.js:23-34`) | n/a | `spec_value` + `unit` | COMPUTED-JS formatting | keep |
| "Programs" list (`:1475-1515`) | `getProductPrograms` (`:485-599`): 100% hard-coded | not served | rival: `competitive_product_program` (`program_title`, `authority`, `program_date`, `status`, `status_color`, `description`); client: `client_product_program` (`program_name`, `program_type`, `owner`, `start_date`, `end_date`, `status`, `description`) | INVENTED | remove function; read tables; hide section if none |
| Programme status colour (`:1499`, `statusColor: "#34d399"` etc.) | hard-coded hex per invented row; fallback `#34d399` | n/a | `competitive_product_program.status_color` (rival only); none for client | INVENTED colour | decide: use stored colour for rival, neutral chip for client |
| Programme date line `{authority} . {date}` (`:1509`) | invented strings "Jan 2024 - Present" | n/a | `program_date` (rival, one date); `start_date`/`end_date` (client) | INVENTED | map |
| "Product comparison" block: side A / side B / reason (`:1537-1561`) | `getProductComparison` (`:601-667`): matchup by id, else fuzzy name match, else a fabricated matchup `dyn-...` pushed INTO `data.matchups` with invented verdict and `cv: "Verified"`, `kv: "Sovereign"` | partly (matchups via `build_matchups`) | pairing via `competitive_matchup.client_product_id` / `competitor_product_id`; sides from `competitor_name`, `competitor_product_name`, `client_product_name`; reason from `match_basis` (not served) | INVENTED + COMPUTED-JS fuzzy join + mutation of shared data | remove invention; show only when a stored matchup exists; hide otherwise |
| "Open comparison" button (`:1564-1588`) | `jumpTo("competitive","positioning",{matchupId})` | n/a | `matchup_id` | CHROME | keep |
| News pill row (`:1613-1625`) | distinct `article.category` of the product's articles | NOT served (`competitorNews: {}`, `app.py:521`) | `competitive_product_news.category` | COMPUTED-JS (distinct) | map |
| News cards: title, date, source, link (`:1629-1666`) | `productNews(data,cid,name)` (`news.js:228`) from `data.competitorNews`, with fallbacks (below) | NOT served | `competitive_product_news.headline`, `published_date`, `publisher`, `article_url` (table not read) | STORED path + INVENTED fallbacks | map; remove fallbacks |
| News fallback chain (`:1068-1081`) | if no article names the product: company news whose text contains the product or category; else `allCompany.slice(0,6)` | n/a | none | COMPUTED-JS that presents company news as product news | remove |
| Card category/date/source defaults (`:1654`, `:1656`, `:1662`) | `item.category \|\| "Defence"`, `"Recent"`, `"demo . defence-daily.example"` | n/a | none | INVENTED defaults | remove; show nothing when empty |
| Card image (`:1647`) | `item.image \|\| getProductImage(...)` | n/a | none | INVENTED | hide |
| Live Google News mentions (`:1088-1105`, `:1629`) | `/api/pulse` | not via dataset | none | out of DB by decision (rule 5) | keep |
| Header Copy / Export / Print (`:1148-1218`) | built from the same values | n/a | same | CHROME + same sources | keep |
| Rail badge count for Products (`overview.js:750-767`) | distinct competitor product names from matchups plus `co.products` | matchups only | `count(competitive_product)` | COMPUTED-JS | map |

### 1.2 Product Evaluation (`Positioning.jsx`, `MatchupList.jsx`, `MatchupDossier.jsx`, `specs.js`, `edge.js`, `compareProducts.js`, `reports.js`)

Backend mapping for a matchup (`build_matchups`, `app.py:410-460`): `id`=`matchup_id`; `comp`=`competitor_name` + " . " + `competitor_product_name`; `bf`=`anchor`=`client_product_name`; `compBy`=`competitor_name`; `cat`=`category_code`; `country`=`competitor_country`; `verdict`=`verdict_headline` else `verdict`; `edge`=`edge_score`; `global`=False; per spec `{l,u,cv,kv,hi:None,gap,win}`; specs sorted by label (`:452`); advantages by side.
Not served at all from `competitive_matchup`: `competitor_id`, `competitor_product_id`, `client_product_id`, `decision_level`, `match_basis`, `comparable_spec_count`, `sourced_spec_count`, and the second of the two verdict columns. Not served from the spec table: `comparability_state`, `spec_group`, `display_order` (ignored), numerics when a text value exists, direction.

**Left list**

| UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Category groups (`MatchupList.jsx:118-160`) | `POS_CATS`, `CAT_KEY` (slug of `category_code`, `app.py:440-459`) | yes | `competitive_matchup.category_code` | STORED, shown through `titleCaseHeadline` (`MatchupList.jsx:17-21`); the column is named "code" but used as a label | keep; decide that `category_code` carries the human label (no separate label column exists) |
| "Uncategorised" bucket (`:20`, `:120`) | fallback for unknown category | n/a | none | CHROME | keep |
| Group count badge, "N rivals" per anchor, anchor order by rival count (`:112`, `:155-176`, `:288-292`) | counts and sort | n/a | none | COMPUTED-JS (count, sort) | keep |
| Anchor heading "KSSL {product}" (`:280`) | `m.anchor` | yes | `competitive_matchup.client_product_name` | STORED | keep |
| Row headline, competitor product (`:299`) | `splitComp(m.comp)` re-splits the string the backend just joined (`:9-14`); `formatProductName` applied in `dataset.js:270-278` | yes, as joined string | `competitive_matchup.competitor_product_name` | COMPUTED-BACKEND concat + COMPUTED-JS split | map the field directly; drop split |
| Row sub-line, maker abbreviation (`:300`) | `companyShort(company)` (`companyNames.js:220-231`): looks up a hard-coded table of company expansions, else turns a long name into its initials ("BSB"-style) | n/a | `competitive_competitor.short_name` (join by `competitor_id`, not served in matchup) or `competitor_name` | INVENTED table (`companyNames.js`, e.g. `:84` `adani: { full: "Adani Defence & Aerospace" ...}`) + COMPUTED-JS initialism | map to `short_name`; remove table and initialism rule |
| Filters: Company, Category, KSSL product, Country (`:176-231`) | `compBy`, `cat`, `anchor`, `country` | yes | `competitor_name`, `category_code`, `client_product_name`, `competitor_country` | STORED; cascading options computed (`:76-110`) | keep |
| Search text (`:144-147`) | includes `m.title` and the words "global prime benchmark" when `m.global` | `title` not served; `global` always False (`app.py:457`) | none | dead / INVENTED term | remove both |
| Empty text `No competitor products served yet` (`:313`) | | n/a | none | CHROME | keep |
| "Compare Any Two Products" pickers (`:236-267`) | `buildProductIndex(matchups)` (`compareProducts.js:27-53`): every rival and client product mentioned in any matchup | indirectly | rival: `competitive_product`; client: `client_product` | COMPUTED-JS reverse index, with INVENTED defaults: client country `"India"` (`:49`), category `"Other"` (`:35`) | rework to read the product tables; remove defaults |

**Right pane: free comparison (`Positioning.jsx:11-72`, `compareProducts.js:55-86`)**

| UI element | field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Header: product names, maker, country (`Positioning.jsx:25-31`) | index entries | derived | product tables; maker = `competitor_name`; country = `competitive_product.country` (rival), NO-COLUMN for client | COMPUTED-JS + INVENTED "India" | map; hide client country |
| Row winners and "N leads on X of Y" (`compareProducts.js:55-70`) | rule: both sides numeric, a direction `hi` exists, gap = abs(a-b)/mean, under 3% = tie, ratio over 50x = "different units, not scored" | no: no `cn`/`kn` served and `hi=None`, so nothing is ever scored | spec numerics: `client_product_specification.value_numeric`; rival spec has NO numeric column (`spec_value` is text); direction has NO column | COMPUTED-JS | decide: add numeric + direction columns, or hide winners and show values side by side only |
| "different units, not scored" note, `row.note` | from ratio rule | n/a | none | COMPUTED-JS | keep with the rule if scoring is kept |
| Footer text "gaps under 3% count as level" (`:64-67`) | restates the rule | n/a | none | CHROME explaining UI | keep |

**Right pane: matchup dossier**

| UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Eyebrow category (`MatchupDossier.jsx:55`) | `m.cat` | yes | `category_code` | STORED | keep |
| Badge "N specs compared on both sides" (`:59-71`) | `m.specDims` = `computeSpecEdge(m).n` (`dataset.js:409`) | derived (hidden by `.srcbadge{display:none !important}`, `shell.css:162`) | `competitive_matchup.comparable_spec_count` (not served) | COMPUTED-JS | map column; badge currently invisible, so decide keep-hidden |
| Names `m.comp` vs `m.bf` (`:74-83`) | | yes (joined) | `competitor_name` + `competitor_product_name`, `client_product_name` | STORED | keep |
| Verdict label (`:85`) | `m.verdictH \|\| "Positioning verdict"`; `verdictH` is never served | no | `competitive_matchup.verdict_headline` | CHROME default; the stored headline is currently collapsed into the body | map `verdict_headline` as the label, `verdict` as the body |
| Verdict body, rendered as HTML (`:86-89`) | `m.verdict` with two regex deletions ("Based only on values sourced for both products", "on N of M comparable field(s)") | yes, but `verdict_headline` wins when present (`app.py:455`) so the long `verdict` is dropped | `competitive_matchup.verdict` | STORED + COMPUTED-JS text surgery | map; remove regexes (clean at source); render as text |
| Gap block (`:93-101`, `specs.js:367-456`) | `matchupGapHtml(m, gapModel)` | derived from `m.edge` (null today, so block empty) | `edge_score`, `decision_level` | COMPUTED-JS, with INVENTED templates (section 2) | decide: keep only a verdict band from stored values; hide exposure and correlate chips |
| Gap word "Critical / High / Moderate gap . N" | rule `behind=(50-edge)/50`; `mag=round(behind*100)`; Critical at 70 or more, High at 40 or more; `. N` is `severity_pct` weighted by tender exposure (`gapModel.js:341-343`) | derived | `edge_score`, `decision_level` | COMPUTED-JS | decide (see section 3) |
| "Rs X exposed" chip (`specs.js:420`) | sum of live tender values in the category: `parseCr(t.value)` with FX `CR_PER_MILLION` (`gapModel.js:16-27`) over `tender.value` text | tenders served, `matches` not | `market_tender.value_amount` + `value_currency` | COMPUTED-JS + INVENTED FX | hide |
| Sentence "On the fields both products publish, X leads by about N%." (`specs.js:425`) | N = `(50-edge)/50*100`, which is the index distance, not a spec lead | derived | none | INVENTED template with a misleading number | remove |
| Cross-pillar chips "live tenders" and tech note (`specs.js:432-452`) | `rec.correlates` from `gapModel.js:395-421`; needs `tender.matches` (not served) and `innovation.gap` (not served) | no | none | COMPUTED-JS over unserved fields | hide |
| Product profile line under each name (`MatchupDossier.jsx:21-23`, `:104-112`) | spec row whose label is the sentinel `"Product (sourced)"` | no | none | NO-COLUMN (label sentinel hack) | hide |
| Tab labels "Analytics", "Spec Comparison" (`:6-9`) | const `TABS` | n/a | `ui.competitive_positioning_tab.tab_label` exists, unread | CHROME | keep; reading the ui table is optional |
| Advantage lists, both sides (`:129-170`) | `m.advBf`, `m.advComp` from `competitive_matchup_advantage` by `side` (`app.py:411-417`; accepts client/kssl/bf and competitor/rival/comp; order ignored) | yes | `advantage_text`, `side`, `display_order`, `source_id` | STORED | map; sort by `display_order`; fix `side` vocabulary; render as text (today `dangerouslySetInnerHTML` after `advantageText` strips `adv-src` anchors, `specs.js:203-209`) |
| "None recorded from the sources for this matchup." | | n/a | none | CHROME | keep |
| Spec header names (`:177-180`) | `m.comp`, `m.bf` | yes | same | STORED | keep |

**Spec Comparison panel (`specs.js:278-364`) and the parity / edge visual**

| UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Gauge word "KSSL BEHIND / NEAR PARITY / KSSL AHEAD . {n}" (`specs.js:356`) | `edgeVerdict(edge)` (`edge.js:154-166`): 58 or more = ahead, 42 to 57 = parity, below 42 = behind | edge overwritten, null (see 0.3) | `edge_score` (number) and `decision_level` (integer, meaning undefined) | COMPUTED-JS from a COMPUTED-JS number | map to stored; decide `decision_level` coding |
| Gauge marker position (`specs.js:353`, `:357`) | `left: edge%` | same | `edge_score` | COMPUTED-JS | map |
| Gauge scale captions "Competitor stronger / Parity / KSSL stronger" | | n/a | none | CHROME | keep |
| Basis chips "up/down Label N%" (`edgeBasis`, `edge.js:170-188`) | the decided dimensions with `\|a\|`, `+` when clamped at 40% | no | `better_side` + `gap_value` + `spec_label` | COMPUTED-JS | derive from stored columns |
| Spec row label and unit (`specs.js:54`, `:93`) | `s.l`, `s.u` | yes | `spec_label`, `unit` | STORED | keep |
| Spec values (`specs.js:97`, `:102`) | `s.kv`, `s.cv` = text, else numeric (`app.py:427-428`) | yes (text wins; numeric dropped when text exists) | `client_value_text`/`client_value_numeric`, `competitor_value_text`/`competitor_value_numeric` | STORED | keep; serve both |
| Quantitative-or-not split (`specs.js:286`) | `typeof s.cn === "number" && typeof s.kn === "number" && s.hi !== null` | NO: `cn`/`kn` not served, `hi` always null | `comparability_state` | COMPUTED-JS gate | map to `comparability_state` |
| Bar widths (`specs.js:66-70`) | longer bar = 100%, other = value/max, minimum 4% | no | numerics | COMPUTED-JS | map (cast Decimal strings) |
| Winner highlight and "leads" badge (`specs.js:72-89`) | gap=(hi-lo)/hi; leads only if direction known and gap >= 5%; tier decisive >= 35, clear >= 15, marginal >= 5; "leads" printed only for decisive/clear | no | `better_side`, `gap_value` | COMPUTED-JS | use stored `better_side`; tier from `gap_value`; note the 5% here versus 3% in `edge.js:60` (a row can read "parity" yet count in the index) |
| "parity" tag per row, "lower is better" note (`specs.js:88-89`) | derived; direction from `s.hi` | no | `better_side = level` (parity); direction has NO column | COMPUTED-JS / NO-COLUMN | parity from stored; hide the direction note |
| Provenance dot after every value (`specs.js:47-49`, `:251-253`, `:337`) | `s.p`/`s.kp`/`s.cp` are never served, so `dot(undefined)` returns the "synthetic" dot (`provdot x`, `shell.css:181`) on EVERY value | no | none (use `fact_source` later) | INVENTED default presented as a data flag | remove |
| Qualitative chips and "not sourced" / "no counterpart published" (`specs.js:250-276`) | `noCounterpart` flag never served; `has(v)` tests for `"—"` | no | `comparability_state` | CHROME wording + unserved flag | map the wording to a stored state |
| Rows shown only when both sides present and KSSL value not /undisclosed/ (`specs.js:313-318`) | | n/a | `comparability_state` | COMPUTED-JS (regex on text) | map |
| States "NOTHING COMPARED ON BOTH SIDES", "NO SPEC-LEVEL EDGE", section headings (`specs.js:322-334`, `:291-301`) | | n/a | none | CHROME | keep |
| Legend (`specs.js:361`) | first word of competitor name, "KSSL" | n/a | none | CHROME | keep |
| Per-value source links (`srcLine`, `specs.js:233`) | `SHOW_POSITIONING_SOURCES = false` (`:151`) | not served | `competitive_matchup_source`, `fact_source` | switched off | decide whether sources are shown |
| Header Copy / Export "No verdict on file." (`Positioning.jsx:149-216`) | verdict, specs, advantages, `edge` | same | same | CHROME + same sources | keep |
| Empty right pane "Select a rival model" / "KSSL . -" (`:242-257`) | | n/a | none | CHROME | keep |
| Rail badge `counts.positioning` (`overview.js:714-721`) | distinct competitor names across matchups | yes | `count(distinct competitor_name)` | COMPUTED-JS | keep as a stated count |
| Header tile text "rating-matched rivals" (`overview.js:679`), page subtitle (`:861-863`) | | n/a | none | CHROME (legacy generator wording) | review wording |
| `positioningReportHtml` (`reports.js:8-110`) | not called from any file | n/a | n/a | dead code with an INVENTED sentence (`:17`) | remove |

### 1.3 Gap Analysis (`GapAnalysis.jsx`, `gapAnalysis.js`, `gapModel.js`, route `gap-competitive`, archived)

Every value on this page is COMPUTED-JS from `data.matchups[*]` (their `edge`, `cat`, `compBy`, `specs`). With the present backend `edge` is null for all, so `gapCategories` (`gapAnalysis.js:432-458`) returns `[]` and the list reads "No scored comparisons yet." (`GapAnalysis.jsx:124`).

| UI element | dataset key / field | served today? | new-schema column | Kind | Action |
|---|---|---|---|---|---|
| Category list: name (`GapAnalysis.jsx:111`) | `m.cat` for matchups with `edge != null` | yes, but gated on null edge | `competitive_matchup.category_code` | STORED + gate | map |
| Category list: "{N} rivals . {N} comparisons" (`:113`) | distinct `compBy` per category; matchups with edge | derived | `competitor_name`, count of matchups | COMPUTED-JS count | keep as stated count |
| Category list: "+N / -N" balance and colour (`:95`, `:116-119`) | `balance = sum(rivalOwns - koelOwns)` over rivals (`gapAnalysis.js:449`); colour: behind if behind-rivals >= half, else level if any, else ahead | derived | `better_side` per spec | COMPUTED-JS | keep, documented |
| "Derived" chip (`:80`) | | n/a | none | CHROME (hidden by `shell.css:162`) | keep |
| Category sort (`gapAnalysis.js:452-457`) | share of rivals "behind", then count | derived | none | COMPUTED-JS | keep |
| Header "{cat} . competitive edge", sub "R rivals . T of H head-to-head comparisons . D measured spec dimensions" (`GapAnalysis.jsx:130-131`, `gapAnalysis.js:999-1008`) | counts; `held` = all matchups in category | derived | none | COMPUTED-JS count + CHROME | keep |
| Per-dimension record for a rival (`gapAnalysis.js:259-282`) | for each matchup: `computeSpecEdge(m).dims`; `a<0` = rival wins, `a>0` = KSSL wins, `a=0` level; magnitude `raw*100` | no (dims empty) | `better_side`, `gap_value`, `spec_label` | COMPUTED-JS | rewire to stored columns |
| Dimension ownership (`gapAnalysis.js:307-323`) | rival "owns" a dimension if win share of decided matchups >= 65% (`GAP_OWN`), decided >= 3 (`GAP_MINDEC`), margin >= 2 (`GAP_MINMARGIN`), comparable >= 3 and coverage >= 40% (`GAP_MINCMP`, `GAP_MINCOV`) | derived | same | COMPUTED-JS rule (constants stated at `:28-34`) | keep as stated rule |
| Dimension identity (`GAP_ORDER`, `gdmeta` `:47-199`) | exact legacy labels "Max range", "Artillery/Weight", "UAVs & Drones/Endurance", ... | no | `spec_label` (and `spec_group`) | INVENTED label vocabulary keyed to the old category names | replace with the labels actually stored; prompt must use canonical labels |
| Rival verdict chip "KSSL behind / ahead / Traded / No clear edge / Not enough data" (`:343-383`) | ownership balance, plus an override to "Traded" when the per-matchup count disagrees | derived | none | COMPUTED-JS | keep |
| Rival rows: rank, name, bar, "Owns a vs b", "Worst x/100", record bar, N, "Biggest edge" (`:942-971`) | `balance`, `rivalOwns`, `worst.edge`, `rivalWins/parity/koelWins`, `dims[0]` | derived | `edge_score`, `better_side`, `gap_value` | COMPUTED-JS; "Worst" is the minimum `edge` | keep, re-point |
| Diverging bar +/-5 (`:486-520`) | `balance`, fixed domain | derived | none | COMPUTED-JS drawing | keep |
| Severity colouring of "Worst" (`:958`) | edge < 25 =4, < 35 =3, < 42 =2, < 50 =1 | derived | `edge_score` | INVENTED thresholds | decide |
| "rival ahead / KSSL ahead / level" per comparison (`:844`) | `edge < 50`, `> 50`, `== 50` | derived | `edge_score` | COMPUTED-JS; uses 50 while the gauge uses 42/58 (`edge.js:163-165`), so the same pair reads "rival ahead" here and "near parity" in Positioning | decide one banding |
| "Every head-to-head comparison" lines with both values (`:820-866`) | `pairVals(x)` unit-converts using `cn`/`kn` ratios | no (`cn`/`kn` absent) | `*_value_text`, `unit` | COMPUTED-JS | show stored text values only; drop conversion |
| Hero block "N/R rivals hold an edge" and sentence (`:883-926`) | counts + templates | derived | none | COMPUTED-JS + CHROME templates | keep counts, keep neutral wording |
| Dimension accordion: Severity, Gap, Competitors, Top Rival, Record, KSSL owns vs, Coverage (`:526-595`) | severity from bins in `GAP_DIM`; gap = median lead `gval` | derived | `gap_value` | COMPUTED-JS + INVENTED bins | keep medians; drop bins/severity words (decide) |
| "Why It Matters" / "How to read it" / "What the edge buys them" / "Read:" paragraph (`:558-608`, `:637-810`) | `GAP_WHY`, `GAP_DIM[*].note` | no | none | INVENTED (section 2) | remove |
| Methodology footer (`:981-995`) | rule restatement plus Indian procurement commentary | n/a | none | CHROME (rule half) + INVENTED (commentary half) | keep the rule sentence, remove the rest |
| Click-through to Positioning (`GapAnalysis.jsx:138-146`) | `matchupId` | n/a | `matchup_id` | CHROME | keep |
| Rail badge `counts["gap-competitive"]` (`overview.js:805`) | count of `behind` competitive gaps from `buildGapModel` | derived | none | COMPUTED-JS | keep or drop (no rail item uses it) |
| `buildGapModel` market / technology / ecosystem branches (`gapModel.js:149-331`) | `tender.matches[].pct`, `innovation.gap`, `competitors[].partners[].mean` regex | NOT served (`app.py:324-345`, `:378-393`) | none | COMPUTED-JS over unserved fields, with INVENTED magnitudes `0.75`/`0.4` (`:237-245`), alias table (`:211-220`), FX (`:16`) | hide; these only feed the Positioning gap block and `Tenders`/`Innovation` strips |

---

## 2. INVENTED content found

| file:line | what | quote |
|---|---|---|
| `Products.jsx:163-273` | hard-coded product-name to Unsplash photo URLs (~100 entries) | `"kalyani m4": "https://images.unsplash.com/photo-1579273166152-d725a4e2b755?auto=format&fit=crop&w=600&q=80"` |
| `Products.jsx:275-340` | category photo pools | `helicopters: [ "https://images.unsplash.com/photo-1508614589041-895b88991e3e?..."` |
| `Products.jsx:351-424` | keyword-based photo choice, vehicles pool as default | `text.includes("helicopter") \|\| text.includes("chopper") ... pool = CATEGORY_POOLS.helicopters` and `else { pool = CATEGORY_POOLS.vehicles; }` |
| `Products.jsx:427-483` | invented spec sheets by keyword | `"Endurance": "36 hours continuous flight"`, `"Indigenisation Content": "Over 60% indigenous Indian manufacturing"`, fallback `"Compliance Standard": "MIL-STD-810H & Indian MoD Def-Stan"` |
| `Products.jsx:485-599` | invented programmes with authorities, dates, colours | `title: "Indian Navy MALE UAV Induction Program"`, `authority: "Indian Navy . Porbandar Air Enclave"`, `statusColor: "#34d399"`, `description: "Delivery of 20+ composite aerostructures for Hermes 900 / Drishti-10 platforms manufactured at the Hyderabad aerospace cluster."` |
| `Products.jsx:583` | generic programme template for any product | `` `${company?.name \|\| "Indigenous"} ${product?.name \|\| "System"} Defence Acquisition Council (DAC) Mandate` `` |
| `Products.jsx:614`, `:629`, `:665` | invented pairing reasons | `` `Matched on ${m.cat \|\| cat} category and operational proximity.` `` |
| `Products.jsx:636-644` | hard-coded matchup ids and a hard-coded KSSL counterpart | `matchups["20033"] \|\| matchups["9003"]` ... `bf: "KSSL . Bharat 150"` |
| `Products.jsx:647-659` | fabricates a matchup and writes it into shared `data.matchups` | `verdict: "<b>${cName} leads on comparable specifications against ${baseMatchup.bf}.</b> Based on published defense parameters."`, `cv: s.cv \|\| "Verified", kv: s.kv \|\| "Sovereign"` |
| `Products.jsx:744` | default threat | `threat: co.threat \|\| "watch"` |
| `Products.jsx:48`, `:1060` | default category | `formatLabel(cat) \|\| "Defence Systems"` |
| `Products.jsx:998` | category falls back to the company's sector | `formatCategoryTitle(obj.category \|\| co.sector)` |
| `Products.jsx:1073-1080` | company news passed off as product news | `return allCompany.slice(0, 6);` |
| `Products.jsx:1654`, `:1656`, `:1662` | news card defaults | `item.category \|\| "Defence"`, `: "Recent"`, `item.source \|\| "demo . defence-daily.example"` |
| `Products.jsx:1498-1500` | status badge always styled green on a fallback colour | `background: "rgba(52, 211, 153, 0.15)"`, `prog.statusColor \|\| "#34d399"` |
| `revenueFacet.js:14-19`, `:23` | tier wording with figures and FX rates | `high: "High (> Rs5,000 Cr / $1B+)"`, `const CRORE_PER_BN = { usd: 8500, eur: 9300, gbp: 11000, inr: 100 }` |
| `companyNames.js:84` (table spans the file) | company expansions and short names kept in code | `adani: { full: "Adani Defence & Aerospace", src: "workbook" }` |
| `compareProducts.js:35`, `:49` | defaults in the product index | `cat: cat \|\| "Other"`, `add("client", ..., "India", ...)` |
| `specs.js:47-49`, `:251-253` | "synthetic data" dot on every value by default | `const dot = (pv) => (pv === "s" ? "" : '<span class="provdot x"></span>');` |
| `specs.js:425-452` | gap-block templates with claims and a misleading number | `leads by about ${mag}%`; `there are <b>N live tenders</b> in ${cat} that KSSL can bid on right now. This spec gap directly affects how KSSL scores on them`; `KSSL trails the state of the art here too` |
| `edge.js:51-59` | domain constants: pairing axes and plausibility ranges | `const EDGE_AXIS = ["Calibre", "MTOW", "Length", "Barrel"]`, `Crew: [1, 15]`, `Speed: [0.1, 30]` |
| `gapModel.js:16`, `:211-220`, `:237-245`, `:341`, `:349` | FX, category alias, fixed magnitudes, severity weights | `CR_PER_MILLION = { "us$": 8.3, ... }`, `mag = 0.75`, `0.35 + 0.65 * (...)`, `urgency * 0.08` |
| `gapAnalysis.js:47-174` | `GAP_DIM`: per-dimension direction, bins and an explanatory note with real-world figures | `note: "A range figure is meaningless without projectile type ... the same 155 mm barrel gives about 41 km on base-bleed and 55 km on V-LAP, a 33% swing from ammunition alone."`; `"Measured against the doctrinal soldier load - a 48 lb fighting load and 72 lb approach march (ATP 3-21.18)."` |
| `gapAnalysis.js:637-764` | `GAP_WHY`: 14 dimension essays | `one: "The rival shoots from outside the range at which KSSL's gun can reply, so the exchange is one-way."`; `seg1: "KSSL's ~500k empty bodies a year feed other fillers' lines - ..."` (a company figure in code) |
| `gapAnalysis.js:565` | fallback sentence | `"Impacts overall competitive positioning in this category."` |
| `gapAnalysis.js:799-808` | "Read:" paragraph | `Indian procurement qualifies on specification and then decides on price among everyone who qualified, after trials in Ladakh and Rajasthan that regularly overturn the datasheet.` |
| `gapAnalysis.js:981-995` | methodology footer commentary | `What decides Indian defence orders is mostly outside this comparison: DAP 2020 categorisation and indigenous content thresholds, Positive Indigenisation List embargoes, L1 price ...` |
| `gapAnalysis.js:896-926` | hero sentences | `rivals own more measured dimensions than ${clientName} in this category` (counts are computed; the framing text is fine as chrome, the figures are computed) |
| `reports.js:17` | dead function, invented assessment | `is a real, sourced competitor mapped to KSSL's ... by role and spec class` |
| `dataset.js:139` | global text rewrite of every string (`plainDashes`, `decodeAmp`) | display transform, not invented content; listed for completeness |

---

## 3. Computed in the UI (every rule)

### 3.1 The edge index and parity verdict (what the user sees as "KSSL behind / near parity / KSSL ahead")

| Step | Where | Rule |
|---|---|---|
| Entry | `dataset.js:397-419` | For every matchup: `ce = computeSpecEdge(m)`; `m.edge = ce.edge` (overwrites the stored `edge_score`); `m.specDims = ce.n`; `m.specDecided = ce.decided` |
| Eligible spec rows | `edge.js:83-117` | A row votes only if: label does not contain `Calibre`, `MTOW`, `Length` or `Barrel` (`:51`, `:72`); no `classAxis` flag; `cn`, `kn`, `hi` all non-null; value inside `EDGE_RANGE` for Crew / Crew-pax / Speed (`:55-59`) |
| Per-row advantage | `edge.js:95-100` | `a = (kn - cn) / ((cn+kn)/2) * (hi ? 1 : -1)`; `\|a\| < 3%` (`EDGE_DEADBAND`, `:60`) becomes 0; clamped to +/-0.40 (`EDGE_CAP`, `:61`) |
| Index | `edge.js:134-147` | decided = rows with a not 0. None decided means `edge = null` and no verdict. Else `leadK` = rows with a > 0 (KSSL ahead); `raw = 100*leadK/decided`; `edge = round(50 + (raw-50) * decided/(decided+1))`, clamped 2..98 |
| Examples | derived | 1 of 1 decided led by KSSL = 75; 0 of 1 = 25; 1 of 2 = 50; 2 of 3 = 63 |
| Word | `edge.js:154-166` | `edge >= 58` KSSL AHEAD; `42..57` NEAR PARITY; `< 42` KSSL BEHIND; null = "INSUFFICIENT MEASURED DATA" |
| Gauge | `specs.js:350-363` | Marker at `left: edge%`; basis chips from decided dims sorted by `\|a\|`; "up/down label pct%" with `+` at the 40% cap (`edge.js:170-188`) |
| Gap-block band | `specs.js:377-413` | `behind = (50-edge)/50`; `> 0.02` behind, `< -0.02` ahead, else parity. Behind magnitude `round(behind*100)`; band Critical `>= 70`, High `>= 40`, else Moderate |
| Gap severity number | `gapModel.js:337-349` | `severity = magnitude * (0.35 + 0.65*exposure/maxExposure)`; `severity_pct = round(severity*100)`; printed after "Critical/High/Moderate gap" |
| Row bar widths and winner | `specs.js:66-89` | see section 1.2; uses 5% threshold, not 3% |
| Row tiers | `specs.js:84-87` | gap relative to larger value: `>= 35` decisive, `>= 15` clear, `>= 5` marginal |

Consumers of `m.edge` beyond these pages: `gapModel.js:95`, `gapAnalysis.js:261,436`, `chat.js`, `reports.js`, `Positioning.jsx:154,176,211`.

### 3.2 Counts, rankings and groupings

| What | Where | Rule |
|---|---|---|
| Rail badge Product Evaluation | `overview.js:714-721` | distinct competitor names across matchups |
| Rail badge Products | `overview.js:750-767` | distinct lower-cased competitor product names across matchups and `co.products` |
| Rail badge Gap | `overview.js:805` | count of `behind` competitive gaps from `buildGapModel` |
| Matchup list groups and counts | `MatchupList.jsx:118-176` | group by category, then anchor; anchors sorted by rival count; rivals alphabetical |
| Cascading filter options | `MatchupList.jsx:76-110` | each option set computed with its own filter excluded |
| Products category facet, country facet, revenue facet | `Products.jsx:862-869`, `countryFacet.js`, `revenueFacet.js` | distinct values over roster rows with counts |
| Product grouping and counts | `Products.jsx:1054-1065`, `:1769` | group by category; count of shown |
| Gap rival ownership, verdict, ranking | `gapAnalysis.js:253-430` | rules in section 1.3; rank order behind, contested, ahead, nodata, then net ownership, severity, record, N |
| Gap category ranking | `gapAnalysis.js:452-457` | share of rivals behind |
| Free comparison scoring | `compareProducts.js:55-86` | rule in section 1.2 |

### 3.3 Display transforms (not content, but they change stored text)

`plainDashes`, `decodeAmp` on the whole dataset (`dataset.js:139`); `formatProductName` on `comp`/`bf`/`anchor` (`dataset.js:270-278`) and product names; `titleCaseHeadline` on category labels (`MatchupList.jsx:17-21`); `formatCategoryTitle` and `formatLabel` on product categories and KSSL spec labels (`Products.jsx:48`, `:944`); `cleanCompanyName` (`:37-42`); `stripCompanyPrefix` (`:130-138`); `pairingReason` (`specs.js:225-231`) which deletes a sentence from `m.reason`; `advantageText` (`specs.js:203-209`). Recommendation: keep a single case/dash rule if wanted, but delete the ones that cut or delete words (`cleanCompanyName`, `pairingReason`, `advantageText`, the two verdict regexes).

---

## 4. New-schema tables for these pages that no page reads, and whether one should

| Table | Read today? | Should a page read it? |
|---|---|---|
| `serving.competitive_product` | no (`products: []`, `app.py:164`) | **Yes**: Products catalogue (name, category, country). `image_url`, `image_source_url` stay unread (images hidden). `category_filter`, `category_count`, `is_collapsed`, `product_search_query` are UI-state-like columns; not needed |
| `serving.competitive_product_specification` | no | **Yes**: Products spec table |
| `serving.competitive_product_program` | no | **Yes**: Products programmes (replaces invented text) |
| `serving.competitive_product_news` | no | **Yes**: Products news (news-job output). Needs `product_id` join; `matchup_id` is `uuid` vs matchup `bigint` |
| `serving.client_product` | no | **Yes**: KSSL branch of Products. Note its columns (`rated_power_value`, `prime_rating`, `standby_rating`, `frequency_hz`, `fuel_type`) are generator-set vocabulary; decide whether they display as spec rows |
| `serving.client_product_specification` | no | **Yes** |
| `serving.client_product_program` | no | **Yes** |
| `serving.client_product_source` | no | Optional (sources) |
| `serving.competitive_matchup` | partly | **Yes, fully**: also serve `decision_level`, `match_basis`, `comparable_spec_count`, `sourced_spec_count`, `competitor_id`, `competitor_product_id`, `client_product_id`; serve `verdict_headline` and `verdict` as two fields; cast numerics |
| `serving.competitive_matchup_specification` | partly | **Yes, fully**: serve `better_side`, `gap_value`, `comparability_state`, `spec_group`, `display_order`, both text and numeric values |
| `serving.competitive_matchup_advantage` | yes (order and `source_id` ignored) | Fix ordering; decide on `source_id` |
| `serving.competitive_matchup_source` | no | Decide (needed only if per-matchup sources are shown again) |
| `serving.competitive_product_evaluation`, `_evaluation_spec` | no | **Probably no.** It duplicates `competitive_matchup*` (same pair, verdict, spec comparison, comparability state) but without numerics, `better_side`, `gap_value` or `edge_score`, and with `uuid` product ids that do not match `client_product` (`bigint`). Decide: drop, or declare it the Products-page "compare" feed and fix the id types |
| `serving.competitive_competitor` | yes (partly) | Serve `short_name` (already), `revenue_tier`, `annual_revenue`, `revenue_currency`, `origin_country`, `threat_level` |
| `serving.competitive_competitor_location` | no | Optional (multi-country filter) |
| `serving.fact_source` | excluded in `load_all_tables` (`app.py:94`) | Later, for per-value sources |
| `ui.competitive_positioning_tab` | no | Optional (tab labels; currently chrome in code) |
| `ui.competitive_positioning_view_state`, `ui.competitive_product_view_state` | no | **No.** Per-viewer UI state; a shared DB row cannot hold it. Selection is kept in memory (`viewState`) |
| `ui.competitive_navigation` | no | Optional (rail labels are chrome in `route.js:25-37`) |

Schema defects to settle before prompts are written (user decision):

| Defect | Where | Proposal |
|---|---|---|
| Join id types disagree | `competitive_matchup.competitor_product_id` bigint vs `competitive_product.product_id` uuid; `competitive_product_news.matchup_id` uuid vs `competitive_matchup.matchup_id` bigint; `competitive_product_evaluation.kssl_product_id` uuid vs `client_product.client_product_id` bigint | Make the pairs the same type, or accept name-based joins by the loader (loader resolves ids, as the memory notes say) |
| No spec direction | no `higher_is_better` anywhere | Either add the column (then JS or loader can score) or have the prompt state `better_side` itself (recommended below) |
| `decision_level` and `better_side` and `comparability_state` have no defined vocabulary | integer / varchar(30) / varchar(40) | Fix the coding in the conventions file (proposal in section 5) |
| No category label column | `category_code` used as a label | Prompt writes the human label into `category_code`, or add `category_label` |
| No product description, no verdict label, no client product country, no top-story flag | see UI rows above | hide, or add columns |

---

## 5. Parity table: prompt -> UI

### 5.1 What the UI would do today if a prompt filled the matchup tables

Not show the parity view. `competitive_matchup.edge_score` and `decision_level` and the spec `better_side` / `gap_value` / `comparability_state` would land in the DB and reach `/api/dataset` only as `edge`, `win`, `gap`. The browser then discards `edge` and re-derives from `cn`/`kn`/`hi`, which are absent, giving null (section 0.3). So a JS or backend change is required in any case; a loader script is required only if the prompt should not compute the aggregates itself.

### 5.2 Proposed contract (recommended)

| Output | Table.column | Who produces it | How the UI consumes it |
|---|---|---|---|
| Pair identity | `competitive_matchup.client_product_name`, `competitor_name`, `competitor_product_name`, `competitor_country`, `category_code`, `match_basis`; ids resolved by the loader | prompt (names), loader (ids) | list, headings, filters |
| Verdict | `verdict_headline` (short label), `verdict` (one paragraph) | prompt | dossier label and body (needs backend to serve both) |
| Per-spec row | `competitive_matchup_specification`: `spec_label` (canonical, same wording across matchups so Gap Analysis can group), `spec_group`, `unit`, `client_value_text`, `client_value_numeric`, `competitor_value_text`, `competitor_value_numeric`, `display_order` | prompt (values as published, null if unpublished) | paired bars, chips |
| Per-spec judgement | `comparability_state` (proposal: `comparable`, `one_sided`, `not_comparable`), `better_side` (`client`, `competitor`, `level`), `gap_value` (unsigned percent, `abs(client - competitor) / mean * 100`, the same symmetric measure as `edge.js:95-98`) | prompt (it knows the direction: lower weight is better) with a loader check that numerics agree with `better_side` and that gaps under 3% are `level` | bar winner, "leads" tier, basis chips |
| Aggregates | `competitive_matchup.comparable_spec_count`, `sourced_spec_count`, `edge_score`, `decision_level` | **loader script, deterministic**, not the LLM: over rows with `comparability_state = comparable`, `dec` = rows where `better_side <> level`, `leadK` = rows where `better_side = client`; `edge_score = null` if `dec = 0`, else `round(50 + (100*leadK/dec - 50) * dec/(dec+1))` clamped 2..98 (the rule already in `edge.js:134-147`, which the comments there say mirrors the pipeline); `decision_level` from `edge_score` with the same 42 / 58 band (proposal: 1 = KSSL behind, 2 = near parity, 3 = KSSL ahead, null = insufficient) | gauge word and marker |
| Advantages | `competitive_matchup_advantage`: `side` (`client` / `competitor`), `advantage_text` (plain text), `display_order` | prompt | two analytics lists |
| Sources | `competitive_matchup_source`, `fact_source` | prompt, loader | not shown today |

### 5.3 What must change in code for the parity view to render from those columns (no script at read time)

| Change | File | Effect |
|---|---|---|
| Serve numbers as numbers and pass every column | `backend/app.py` `build_matchups` | cast `Decimal` to float for `edge_score`, `gap_value`, `*_value_numeric`; add `decision`, `matchBasis`, `comparable`, `sourced`; per spec add `cn`, `kn`, `state`, `win`=`better_side`, `gap`; honour `display_order` |
| Stop overwriting the stored index | `src/lib/dataset.js:397-419` | read `m.edge` and `m.decision` as served; delete the `computeSpecEdge` loop (or keep it only as a self-check) |
| Read the stored winner | `src/lib/specs.js:72-89`, `:286` | use `s.win` for lead/parity, `s.state` for the quantitative gate, `s.gap` for the tier; drop the `hi` dependency |
| Read the stored basis | `src/lib/edge.js:170-188` | build chips from `s.win` and `s.gap` |
| Re-point Gap Analysis | `src/lib/gapAnalysis.js:259-282` | build the per-dimension record from `s.win` / `s.gap` / `s.l` instead of `computeSpecEdge(m).dims` |

Alternative if the user prefers to keep scoring in JS: add a direction column (`higher_is_better`) to the spec table and serve `cn`/`kn`/`hi`; the existing `computeSpecEdge` then works, but the stored `edge_score`, `decision_level`, `better_side` and `gap_value` become decoration that could disagree with the screen, which is the exact fault `edge.js:120-130` already records (database, API and screen showed three different numbers). The recommendation is one source: the loader computes, the UI reads.

### 5.4 Gap Analysis

There is no table for gaps and no prompt should write one. The page is an aggregation of `competitive_matchup` (`category_code`, `competitor_name`, `edge_score`) and `competitive_matchup_specification` (`spec_label`, `better_side`, `gap_value`, `comparability_state`) done in the browser (or in `app.py`) by the ownership rules in section 1.3. Once the five code changes above are made and the prompt uses canonical `spec_label` wording, it renders with no further script. What must go is every sentence of authored commentary (section 2): the page can state counts, ownership, medians and the rule used, not why a dimension matters. The route is archived; if it is brought back it needs a rail entry.

---

## 6. Items for the user to decide (add column vs keep hidden)

1. Spec direction (`higher_is_better`): add, or rely on prompt-stated `better_side`.
2. Vocabulary and coding: `decision_level`, `better_side`, `comparability_state`, `threat_level`, advantage `side`.
3. `category_code` as display label, or add `category_label`.
4. Product description line in the dossier ("Product (sourced)"): no column; hide.
5. Verdict label: serve `verdict_headline` as label and `verdict` as body.
6. Programme colour: `status_color` exists for rival programmes only.
7. KSSL entry in the Products sidebar (client currently excluded) and which `client_product` columns count as specs.
8. Country filter source: `origin_country` (one) or `competitive_competitor_location` (many).
9. Revenue tier label wording (stored text, no thresholds in code).
10. Keep or drop `competitive_product_evaluation*` (duplicate of matchup tables with mismatched id types).
11. Per-matchup and per-spec sources: show again via `competitive_matchup_source` / `fact_source`, or keep switched off (`specs.js:151`).
12. One banding for "ahead / parity / behind": the gauge uses 42 / 58, the Gap page uses 50 and 42/25/35.
