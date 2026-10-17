# Prompt files: format and how they run

One YAML file per prompt in `prompts/`, plus `_shared.yml` (system prompt + envelope + context
blocks). `prompts/signal.yml` is the reference example — copy its shape.

## Why YAML + a runner
- **Nothing client-specific is typed into a prompt.** `{{client.*}}` and the `context` blocks are
  filled from kssl_staging at run time (client_account, client_product, competitive_competitor,
  competitive_product, technology_category, ui lookup tables). When the client's Excel changes the
  products, competitors or categories, the next run of every prompt uses the new lists.
- **Routines.** A routine (scheduled job) just runs `python -m prompts.run --due`: each prompt's
  `cadence` and the run log decide what runs. Re-running is safe: the same subject gives the same
  ids, so a re-run updates its cards (they show as "changed" in the review copy).
- **Everything lands in kssl_staging** and waits for Approve in the review copy (:5180).

## Fields
| Field | Meaning |
|---|---|
| `id`, `title`, `version` | identity; bump `version` when the task text changes (forces re-runs) |
| `fills` | tables this prompt writes |
| `shows_on` | where the result appears on the UI |
| `cadence` | `daily` / `weekly` / `quarterly` / `on_demand` (routine scheduling) |
| `model`, `web_search` | override the `_shared.yml` defaults (research prompts: `web_search: true`) |
| `subject.key`, `subject.query` | SQL on kssl_staging; one run per row; `key` column makes the run unique |
| `subject.documents` | how the runner gets source text: `{from: url, field: <col>}` (fetch page text), `{from: sql, query: ...}` (rows as text), `{from: source_document, field: <col>}` (harvested text from the raw layer, see "Foundations") |
| `context` | context blocks to render (see `_shared.yml` `context_blocks`) |
| `task` | the task text. Placeholders: `{{client.<col>}}`, `{{subject.<col>}}`, `{{context.<block>}}`, `{{documents}}` |
| `output` | per table the model may write: `card` (true = one review card per record), `key`, `columns` rules, `loader` (columns the loader fills), `children` |
| `derive` | optional named loader steps run after loading (`prompts/derive.py`), e.g. `matchup_edge` |
| `handler` | a module in `prompts/` that applies the model's answer instead of the generic loader (`news` -> `news_merge.apply`); `output` is then documentary only |

Column rules: `required`, `max` (characters), `enum` (allowed values), `type: date|number`,
`judgement` (needs `_reason`), `from_ref: ref_<thing>` (the loader resolves a name to an id / name).

## References the loader resolves (names -> ids), all on kssl_staging
| ref | resolves to |
|---|---|
| `ref_competitor` | competitive_competitor.competitor_id (display_name, short_name or legal_name, case-insensitive) |
| `ref_product` | competitive_product.product_id (product_name, within ref_competitor if given) |
| `ref_client_product` | client_product.client_product_id (product_name) |
| `ref_category` | technology_category: the category_name for text columns, category_id for *_id columns |
| `ref_tender` | market_tender.tender_id (title or notice_reference / tender_number) |
| `ref_opportunity` | market_opportunity.opportunity_id (title) |
| `ref_location` | competitive_geo_location.location_id (country_name; created if missing — the loader may create geo locations and technology_company / technology_source rows, never competitors or products) |
| `ref_innovation` | technology_innovation.innovation_id (title) |
An unresolved name is not invented: the run is logged with the name under "unresolved" and that row is dropped.

## Ids and re-runs
Card ids are deterministic: uuid columns get uuid5 of `prompt id | subject key | table | n`; bigint
columns a 63-bit hash of the same. Loading a card first deletes that card's previous bundle in
staging (the card row + its children), so a re-run replaces, never duplicates.

## Sources and reasons
Every `_sources` entry -> one `staging.fact_source` row (table, row id, column, url, quote,
source_tier from backend/sources.py). Every `_reason` -> one fact_source row with
`source_tier = 'judgement'`, `source_url = 'judgement'`, `quote = <reason>`. Both show in Trace.

## Run log: `staging.prompt_run`
One row per run: prompt id + version, subject key, model, time, tokens in/out, cost, status
(`loaded` / `skipped` / `rejected` / `failed`), skip reason, error, unresolved names, the prompt
text sent and the raw output. `--due` skips subjects already run with the same prompt version.

## CLI
    python -m prompts.run signal --limit 5             # 5 newest subjects not yet run
    python -m prompts.run signal --subject <key>       # one subject
    python -m prompts.run signal --limit 1 --print-prompt   # show the filled prompt, no call
    python -m prompts.run signal --dry-run             # call the model, validate, do not load
    python -m prompts.run --due                        # routine entry point: every prompt by cadence
    python -m prompts.run --list                       # prompts, cadence, last run, pending subjects

## Allowed values the pages expect (keep prompts and pages in sync)
| Column(s) | Values |
|---|---|
| competitive_signal.classification, competitive_competitor.threat_level, competitive_project.assessment_stance, technology_overview_article.direction | threat, watch, fav |
| competitive_signal_evidence.evidence_group | fact, key_point |
| technology_overview_article.classification | competitor_advance, adoptable |
| competitive_competitor_moment.grade | a level_code from ui.competitive_competitor_moment_level (context block `moment_levels`) |
| competitive_matchup_specification.better_side, competitive_geo_product_specification.better_side | client, competitor, equal |
| competitive_matchup_specification.comparability_state | comparable, one_sided, not_comparable |
| competitive_matchup_advantage.side | client, competitor |
| competitive_matchup.decision_level | loader: 1 = client behind, 2 = near parity, 3 = client ahead (from edge_score) |
| competitive_partnership.relationship_confidence | official, corroborated, single_source |
| competitive_geo_company_presence.overlap_status | confirmed, category, none |
| competitive_patent_filing.status | granted, pending, filed |
| market_tender.status | open, closing, awarded, closed |
| market_tender.lean_code | go, maybe, pass, won, closed |
| kssl_fit / fit_grade / fit_label (tender, opportunity, requirement) | strong, partial, weak |
| market_tender.url_kind | notice, portal, award |
| technology_innovation.client_position | behind, parity, ahead |
| client_partner.partner_type, client_partner_relationship.relationship_type (prompt `client_partner_research`) | Supplier, Customer, Licensor, Joint venture, Technology partner, MoU / teaming |
| technology_category.category_name; every `category` / `product_range` / `category_text` column | the client Excel's 10 categories (db/setup/12_vocabulary.sql): Artillery, Ammunition, Protected & Armoured Vehicles, Armoured Vehicle MRO, Small Arms, Marine / Naval, Missiles & Air Defence, UAVs & Drones, Precision Components & Forgings, Other |
| competitive_news_article.category, competitive_product_news.category (prompt `news`) | Contract & order, Partnership / JV, Product launch & testing, Delivery & induction, Export, Financial results, Stock & market, Facility & capacity, Leadership & corporate, Non-defence business, Other (signal skips Stock & market, Non-defence business and Other) |

## Extensions (implemented in prompts/spec.py, prompts/vocab.py, prompts/loader.py, prompts/derive.py)

Output-spec keys
| Key | Meaning |
|---|---|
| column rule `enum_from` | allowed values from `context.<block>` (the code left of ` = ` in each rendered line) or `ui.<table>.<col>` (distinct values in staging_ui) or `code_label.<table>.<col>` (active codes of ui.code_label); compared case-insensitively, stored as listed |
| `loader_only: true` | table the loader builds, never the model (an output record naming it is rejected). Rows: one per stage step (`from_ui.<t>.<c>` tokens), one per evidence row (`copy_of_evidence_*`), one per distinct cited spec url (matchup source), or `rows:` |
| `rows: [ {col: token-or-text} ]` | fixed loader rows in order; a row whose `copy_of_*` value is empty is skipped; a plain word is text |
| `update_only: true` | the record names an existing row through its declared `refs` entry (e.g. `ref_filing`) and only the listed columns are updated; nothing is inserted or deleted |
| `replace: all_rows` | when the run loads anything, every previous row of the table (and its fact_source rows) is deleted first |
| `refs: {ref_x: table.col}` | extra reference the table takes; the resolved row is available to `resolved_*` and `copy_from_*` tokens. Names a column through `from_ref` instead when the id/name is stored |
| `from_ref` on child tables | same as on cards; a text column receives the name, an id column the id |
| `transient: {name: rules}` | a model field that is validated but not stored (`check`, `source_url`, `country`); read with `transient.<name>`; with `from_ref` it carries the resolved name |
| `creates: {table: {loader: {...}}}` | find-or-create `technology_source` (by url) / `technology_company` (by name); the id token is `id_of_technology_<source\|company>_found_or_created_by_<url\|display_name\|display_label>`; created ids are stable (hash of the url / name) |
| `derive: [step]` | hooks run after the rows are written: `matchup_edge`, `geo_match_edge`, `geo_rollup`, `tender_fit`, `renumber_signals`, and the foundations hooks `signal_label`, `moment_grade`, `story_link`, `tech_direction`, `pursue_label`, `requirement_state`, `award_to_signal`, `filter_options` (see "Foundations" below) |
| `key: [...]` | id seed after `prompt_id | subject`; a card key longer than that leaves the subject's other cards alone on a re-run (otherwise the last run's rows are replaced) |

Pseudo-refs: `ref_client_spec` (client_product_specification.spec_name, of the matchup's / match's client product), `ref_competitor_spec` (competitive_product_specification.spec_label, of the subject's / geo product's competitor product), `ref_opportunity` (when given on market_opportunity the existing opportunity is extended: only its children are written), `ref_filing` (batch handle F001.. of the subject's patent batch). Declared refs that are not found drop the row and are logged under "unresolved".

Loader values (`loader:` map). Computed per row when it is written; `derive.<step>` and `keep` leave the column to the hook / to the stored row.
| Value | Result |
|---|---|
| `new_id` `new_id_if_missing` `new_id_or_ref_<x>` | deterministic id (uuid5 / 63-bit hash of prompt, subject, table, n [+ key parts]); `_or_ref_` uses the given `ref_<x>`'s id and extends that row |
| `parent_id` `index` `index_plus_1_of_output_order` | parent key; 1-based position among siblings / among the cards of the table |
| `subject.<col>` | column of the subject row (also `subject_id_when_competitor` / `_when_client`); a card keyed by it is UPDATED in place when the row exists, never deleted |
| `run_date` `run_time` `now` | date / timestamp of the run |
| `rank_by_<col>_desc` | stable rank = days from 2100-01-01 back to the date (newer = smaller); no renumbering of other rows; null date = run date. `rank_by_country` = alphabetical position among this run's cards |
| `copy_of_<col>`, `copy_of_<prefix>_<col>`, `<column>` | copy from this row, else a related row (parent, driver source row, sibling, child) whose table ends with `<prefix>`, else the referenced row |
| `copy_from_client_spec[_else_none|_else_competitor_spec]` `copy_from_competitor_spec` `parse_plain_number_of_competitor_spec_value_else_null` | fields of the resolved spec rows, chosen by the target column (unit, spec_group, *_value_text / *_numeric) |
| `resolved_<ref>_<id|name|col>` | the resolved reference row |
| `transient.<f>` `host_of_source_url` `host_of_url` `from_ui.<table>.<col>` `constant_<word>` `same_as_<col>` `keep` `keep_stub_value` | as named |
| `name_of_<id col>` `title_of_<id col>` `country_reference_table[_of_country|_of_opportunity_country_code]` `technology_pillar_id` `technology_pillar_name` | lookups: staging name tables; `staging.country_reference` (iso code, lat/lng, region; not listed = NULL + warning); the single `technology_pillar` row |
| `count_children` `count_evidence_cards` `true_when_evidence_exists` `join_child_product_names` `count_partners_of_competitor` `title_of_latest_past_timeline_event` `date_of_latest_past_timeline_event` `matched_when_a_product_match_exists_else_no_match` `sort_by_fit_label_strong_partial_weak_then_output_order` `company_id_of_the_developer_row` `names_of_that_competitors_products_in_the_category` | roll-ups over the written rows |
| `uuid5_of_casefolded_<col>` `category_id_dash_slug_of_title` `label_of_<col>` `due_date_formatted_as_d_mon_yyyy` `single_source_unless_publisher_is_official` `competitor_when_ref_competitor_resolves_else_third_party` `stage_name_equals_project_stage` `status_is_open` `sibling_source_id` `distinct_cited_spec_source_url` | small named rules |
| `"{subject.display_name} - {col} - {year of col}"` | template; `{{client.name}}` placeholders are filled; a `{key: text}` map picks by whichever column of the row or its parents holds one of the keys (null stays null) |
| `true` / `false` / number | literal |

Other behaviour
- Documents: a subject placeholder inside a `from: sql` query is a bound parameter. A `from: url` field that is null is skipped; with several documents a page that cannot be read is noted in the prompt and the run goes on (a single-document run fails).
- `_sources` entries with `url: null` + a `quote` cite a stored input row: fact_source gets source_url `stored row`, tier `stored`. Quotes that name a fetched document are checked against its text; a quote not found is logged as a warning.
- Re-runs: the rows written by the last loaded run of the subject (staging.prompt_run.loaded) are deleted first, except subject-owned rows (updated in place) and, for keyed-beyond-subject prompts, the other cards.
- `--due` / bulk runs: a prompt keyed by an entity (competitor, category, pair, tender, innovation...) re-runs a subject once its cadence period has passed since its last run; one keyed by an event (`article_id`, `source_id`) never re-runs a subject at the same version. `recurring: true|false` in a prompt file overrides. Prompts run in dependency order (news, signal, moment, partnership, project, geo, matchup, tender, tender_assessment, opportunity, top_opportunity, global_requirement, innovation_discovery, innovation_detail, tech_article, patent_classification).

## Foundations (prompt rebuild, phase 2): derived labels, text checks, stories

Source: docs/audit_v2/PROMPT_LOGIC_FABLE_REVIEW.md. Schema: db/setup/11_foundations.sql (staging AND serving). Code: prompts/derive.py, prompts/story.py,
prompts/plain_english.py, prompts/raw_docs.py, prompts/spec.py (rules), prompts/loader.py + vocab.py (tokens).

### New column and table rules (prompts/spec.py)
| Rule | Where | Meaning |
|---|---|---|
| `plain: warn` / `strict` / `off` (or `true` = warn) | column rule, or table-level map `plain: {col: strict}` / list `plain: [a, b]` (= warn) | Plain-English lint of that text column (A.0.3). `warn`: every finding is a warning in `prompt_run.details.warnings`. `strict`: the HARD findings reject the record, the soft ones still only warn. Hard: a sentence over 32 words, a banned phrase (leverage, synergy, ecosystem, robust, cutting-edge, state-of-the-art, game-changer, going forward, strategic imperative, capability enhancement, end-to-end, strengthens its position, extends its footprint, poses a threat to, positions itself, unprecedented; not inside quotation marks), "KSSL should". Soft: a sentence over 20 words; an acronym (3+ capitals, not on the whitelist) used before it is explained as "ABC (what it is)" (once per record, across all its columns); a statement of absence ("no stated route", "no direct overlap", ... except the fixed sentence "No <product> product line is touched; kept because ..."); the record-level reading-level proxy (average sentence 17 words, average word 5.3 letters; warn only). A column without a `plain` rule is not linted. |
| glance limits | built in | `glance_who` / `glance_where` / `glance_impact` max 40, `glance_third_party` / `glance_when` max 60 (rejected over length, like `max`); `glance_move` must be one of Order, Contract, Selection, Delivery, Induction, Trial, Launch, JV, MoU, Acquisition, Capacity, Export approval, Policy, Supply deal, Cancellation. Also built in: `change_note` 160, `kssl_relevance` 200, `product_variant` 60. A prompt's own `max` / `enum` / `enum_from` overrides them. |
| `count: {min, max, where, min_action}` | table rule on a child table | Rows of that child table per card. `where: {col: value}` counts only matching rows (key points = `evidence_group: key_point`). Too few rejects the CARD (`min_action: warn` only warns); too many keeps the first `max` and warns. |
| `dedupe: {column, against, threshold, where}` | table rule on a child table | Drops a child row whose `column` text restates the card's `against` columns (e.g. `[title, summary]`): more than `threshold` (default 0.6) of its content words are already there. A row that repeats an earlier kept row (70 % both ways) is dropped too. Each drop is a warning. Runs before `count`. |
| `unknown_when_empty: <block>` or `{block, action: reject\|coerce}` | column rule | The column rests on a context block (`in_client_market` on `client_markets`, `overlap_kind` on `client_partners`). While that block renders "none on record" the only allowed value is `unknown`: `reject` (default) rejects the record, `coerce` stores `unknown` and warns. `specmod.enum_sources` computes `empty.<block>` for it; the block must be in the prompt's `context:` list (checked by the loader self-test). |
| `reason_pointer: true` | table rule | A judgement's `_reason` must share a number, name or word (4+ letters) with a sourced field's value or quote (A.0.2); otherwise a warning. |

### Loader tokens added (prompts/vocab.py)
| Value | Result |
|---|---|
| `article_image_url` | `competitive_signal.thumbnail_url`: the subject's `image_url`; else the image stored on `competitive_news_article` for the same url; else the page's og:image (backend/news.py `parse_page`, one fetch; skipped when env `KSSL_NO_IMAGE_FETCH` is set or `Loader.fetch_images = False`); else null. |
| `derive.<step>` on a NOT NULL text column | the loader inserts an empty placeholder and the hook sets the value (`classification: derive.signal_label`). |

### Code-derived labels (prompts/derive.py; the model scores, code labels, `rule_version` is stored on the row)
| Hook | Fills | Rule |
|---|---|---|
| `signal_label` | competitive_signal.impact, impact_dimension, impact_dimension_2, classification, rule_version (`s1`); competitive_signal_detail.glance_impact | impact = max of the six `impact_*` scores (the first listed dimension wins a tie; `_2` = the next dimension scoring 4+). **fav** = direction `favourable` and probability >= 4 (checked first). **threat** = probability >= 4 and impact >= 4 and time_to_effect in (lt_1y, 1_3y) and (in_client_market = yes, or dimension in supply_chain / partnerships / policy_export) and (subtype_match in same / adjacent, or dimension in supply_chain / partnerships). **watch** = everything else: any unknown or missing input fails its test. A card with no probability and no dimension score keeps the model's label (watch if it gave none). |
| `moment_grade` | competitive_competitor_moment.grade | label of `signal_id`'s signal: threat -> high, watch -> watch, fav -> opportunity |
| `tech_direction` | technology_overview_article.direction, horizon, horizon_source, rule_version (`t1`) | threat = classification in (competitor_advance, threat_to_position) and relevance >= 4 and maturity >= 3; fav = adoptable and relevance >= 3; else watch. No stated horizon: maturity 5 -> lt_2y, 3-4 -> 2_5y, 1-2 -> gt_5y, with `horizon_source = rule`. |
| `pursue_label` | fit_assessment.attractiveness, ability, pursue_label, rule_version (`p1`); market_tender.lean_code | attractiveness = round(mean(value_score, strategic_score)). ability: strong fit 5 (fit_percent >= 75) else 4, partial 3, weak 1; -1 per not_met eligibility item that is not a hard bar, -2 once for a hard bar (not_met and fixable = no), floor 1; -1 when 2+ rivals fit strongly and one has presence; +1 when KSSL or a KSSL partner is on record in the buyer's country; clamp 1-5. Label: pass = weak fit or a hard bar; pursue = A >= 3 and W >= 4; position = A >= 3 and W = 3, or A >= 4 and W = 2 with every gap fixable; monitor = the rest. lean_code: pursue go, position maybe, monitor watch, pass pass. List it AFTER `tender_fit`. |
| `requirement_state` | market_global_requirement.status_state | unconfirmed when last_confirmed is older than 9 months (stages up to rfi) or 3 months (rfp_tender), or missing; else current |
| `award_to_signal` | competitive_signal (+ detail, story) | STUB: a tender with `awarded_to` naming one tracked competitor becomes a signal: probability 5, orders impact 4 (3 if KSSL did not assess it strong / partial), time_to_effect lt_1y, in_client_market from the client presence rows, label by `signal_label`. Not done: the geo Sells row. |
| `story_link` | story, story_step, `story_id` on the card | see Stories. List it after `signal_label` / `tech_direction`. |
| `filter_options` | ui.competitive_filter_option, ui.technology_filter_option, market_filter_option | rebuilt as a whole from the distinct stored values with counts; labels from ui.code_label. `derive.rebuild_filter_options(cur, data='serving', ui='ui', live=True)` does the same in the serving DB (to be called from Approve). |

Typical lists: signal `[signal_label, story_link]`; tender assessment `[tender_fit, pursue_label]`; technology article `[tech_direction, story_link]`; a prompt that should refresh the option lists adds `filter_options`.

### Stories (prompts/story.py)
- Key (code): `pillar:party:subject:country:family`, blanks kept, e.g. `competitive:hanwha:k9:pl:order`; family in programme, order, delivery, trial, partnership, capacity, policy, demand, technology.
- The prompt is shown the competitor's open stories (last 365 days, at most 15) as `T<8 hex>: key - last step (date)`: `story.stories_block(cur, competitor_id=..., pillar='competitive')` (the text, or "none on record"). It answers with the transient `story_ref` = a handle or `new`; the transient fields `story_kind` (family), `story_country` (name or ISO) and `story_product` (catalogue name) feed the key. An EXACT KEY MATCH WINS over the model's answer in both directions; an unknown handle makes a new story with a warning.
- Each card is one step (`story_step`: date, type, one line <= 120, source, probability, impact, `label_after`). Steps are replaced, not duplicated, when a card is loaded again. After each load the label timeline is rebuilt from the steps: when the label changes between two consecutive steps a `label_change` step is written ("watch -> threat: probability 3 -> 5 (contract signed)", <= 120 characters) and, for an upward change, `story.escalated_at` is set. An older article arriving late takes its place by date and does not change the current state.
- Cards linked: competitive_signal, competitive_product_news, market_global_requirement, market_opportunity, technology_overview_article (their `story_id`). For market cards the label is the stage; for the others it is the card's label.
- `story` and `story_step` are in backend/review.py GRAPH (story = a reviewed card, steps = its children).

### Raw-layer documents (prompts/raw_docs.py; for prompts/render.py to call)
`documents: [{from: source_document, field: article_url, min_chars: 400, cap: 12000}, {from: url, field: article_url}]`: `raw_docs.resolve(cur, entry, subject)` returns the harvested text of the subject's url, or `[]` (text shorter than `min_chars`, or no row), and the runner goes on to the next entry. A roll-up prompt reads `{from: source_document, competitor: competitor_id, days: 90, limit: 20, cap_each: 3000}` (documents attributed to the competitor, nothing fetched). Block format: `[SOURCE <url>]` then the text.

### Code lists and filter options (ui.code_label, ui.*_filter_option)
`ui.code_label (table_name, column_name, code, label, tag_class, tooltip, display_order, is_active, value_from, value_to, is_default)` holds every allowed value of the new enum columns and the lists that were typed into the frontend (seed rows and the file:line of each list: db/setup/11_foundations.sql). A prompt takes an enum from it with the column rule `enum_from: code_label.<table>.<column>` (e.g. `code_label.competitive_signal.time_to_effect`): the active codes in display order, read from staging_ui at run time, so a new value is a row, not a prompt edit. The existing forms stay: `context.<block>` and `ui.<table>.<column>` (distinct values).
