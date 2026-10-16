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
| `subject.documents` | how the runner gets source text: `{from: url, field: <col>}` (fetch page text), `{from: sql, query: ...}` (rows as text) |
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
| competitive_news_article.category, competitive_product_news.category (prompt `news`) | Contract & order, Partnership / JV, Product launch & testing, Delivery & induction, Export, Financial results, Stock & market, Facility & capacity, Leadership & corporate, Non-defence business, Other (signal skips Stock & market, Non-defence business and Other) |

## Extensions (implemented in prompts/spec.py, prompts/vocab.py, prompts/loader.py, prompts/derive.py)

Output-spec keys
| Key | Meaning |
|---|---|
| column rule `enum_from` | allowed values from `context.<block>` (the code left of ` = ` in each rendered line) or `ui.<table>.<col>` (distinct values in staging_ui); compared case-insensitively, stored as listed |
| `loader_only: true` | table the loader builds, never the model (an output record naming it is rejected). Rows: one per stage step (`from_ui.<t>.<c>` tokens), one per evidence row (`copy_of_evidence_*`), one per distinct cited spec url (matchup source), or `rows:` |
| `rows: [ {col: token-or-text} ]` | fixed loader rows in order; a row whose `copy_of_*` value is empty is skipped; a plain word is text |
| `update_only: true` | the record names an existing row through its declared `refs` entry (e.g. `ref_filing`) and only the listed columns are updated; nothing is inserted or deleted |
| `replace: all_rows` | when the run loads anything, every previous row of the table (and its fact_source rows) is deleted first |
| `refs: {ref_x: table.col}` | extra reference the table takes; the resolved row is available to `resolved_*` and `copy_from_*` tokens. Names a column through `from_ref` instead when the id/name is stored |
| `from_ref` on child tables | same as on cards; a text column receives the name, an id column the id |
| `transient: {name: rules}` | a model field that is validated but not stored (`check`, `source_url`, `country`); read with `transient.<name>`; with `from_ref` it carries the resolved name |
| `creates: {table: {loader: {...}}}` | find-or-create `technology_source` (by url) / `technology_company` (by name); the id token is `id_of_technology_<source\|company>_found_or_created_by_<url\|display_name\|display_label>`; created ids are stable (hash of the url / name) |
| `derive: [step]` | hooks run after the rows are written: `matchup_edge`, `geo_match_edge`, `geo_rollup`, `tender_fit`, `renumber_signals` |
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
