# Review copy + two databases — spec (coordinator)

## Databases (user decision 2026-10-16)
- `kssl_staging` DB: schemas `staging` (= serving tables) and `staging_ui` (= ui tables), plus `staging.fact_source`, `staging.review_decision`. Everything is written here (Excel loaders, prompt loaders, news job, hand inserts).
- `kssl_serving` DB: schemas `serving` + `ui` + `serving.fact_source`. Read by the live UI. Written only by Approve / Unpublish; guard triggers refuse other writes unless `SET LOCAL kssl.approve = 'on'`.
- Same Postgres container (kssl-pg, port 55432, user kssl/kssl). Both built from `kssl_schema_from_docx.sql` + the id-type fix (`db/migrations/002_fix_id_types.sql` logic). In the staging DB the schemas are renamed ui -> staging_ui, serving -> staging.
- Env: `KSSL_SERVING_DSN`, `KSSL_STAGING_DSN`; each falls back to `KSSL_DSN` (keeps today's single-DB setup and the kssl_v2_test* test DBs working, where both schemas live in one DB).
- The old `kssl_frontend` DB is kept as a backup. Move what is in its `staging`/`staging_ui` today (news rows, 4 real test competitors + 4 products, fact_source rows) into `kssl_staging`.

## Backends
- Live (default, :8600): `/api/dataset` reads kssl_serving (`ui`, `serving`).
- Review (`KSSL_VIEW=review`, :8601, localhost): `/api/dataset` reads kssl_staging (`staging_ui`, `staging`) under the keys "ui"/"serving", plus `review` = statuses. Routes `POST /api/review?table=&key=&action=approve|reject|undo|unpublish`, `POST /api/review/table?schema=ui|serving&table=&action=approve|unpublish` (table-level), `GET /api/review/trace?table=&key=`. Review routes return 404 on the live backend.
- `backend/news.py` writes staging DB (`KSSL_STAGING_DSN`); its GET reads the DB of the current view.

## Cards and bundles
A card = one row of a REVIEWED table. Bundle = the row + its non-reviewed descendants (recursively). Approve replaces the card's bundle in serving with the staging bundle (+ matching fact_source rows) in ONE serving-DB transaction; the parent card(s) must already be live ("Approve its competitor first"). Unpublish removes the card and everything under it (incl. reviewed descendants) from serving. Reject stores the signature of the rejected version in `staging.review_decision`; a different later version is pending again. Status per card: new / changed / live / rejected (+ `live` flag), computed by comparing bundle signatures (ignore created_at/updated_at/fetched_at/retrieved_at).

GRAPH (table: key column; parents (fk -> table); children are the non-reviewed tables listing it as parent):
- client_account: client_id
- client_product: client_product_id; client_id -> client_account. Children: client_product_specification, client_product_program, client_product_source (client_product_id)
- client_partner: client_partner_id; client_id -> client_account. Children: client_partner_product, client_partner_relationship, client_partner_source (client_partner_id)
- competitive_competitor: competitor_id. Children: competitive_competitor_location, competitive_competitor_swot, competitive_stock_quote (-> competitive_stock_series by stock_id), competitive_patent_portfolio (-> competitive_patent_classification by portfolio_id) (all by competitor_id unless noted)
- competitive_leader: leader_id; competitor_id -> competitive_competitor. Child: competitive_leader_record (leader_id)
- competitive_news_article: article_id; competitor_id -> competitive_competitor
- competitive_product: product_id; competitor_id -> competitive_competitor. Children: competitive_product_specification, competitive_product_program (product_id)
- competitive_product_news: product_news_id; product_id -> competitive_product
- competitive_matchup: matchup_id; competitor_product_id -> competitive_product, client_product_id -> client_product, competitor_id -> competitive_competitor. Children: competitive_matchup_specification, competitive_matchup_advantage, competitive_matchup_source (matchup_id)
- competitive_partnership: relationship_id; competitor_id -> competitive_competitor. Children: competitive_partnership_evidence, competitive_partnership_relationship_detail (relationship_id)
- competitive_project: project_id; competitor_id -> competitive_competitor. Children: competitive_project_source, _specification, _stage, _timeline (project_id)
- competitive_geo_location: location_id
- competitive_geo_company_presence: presence_id; location_id -> competitive_geo_location, competitor_id -> competitive_competitor (null for the client's own presence). Child: competitive_geo_product (presence_id) -> its children competitive_geo_product_match (geo_product_id) -> competitive_geo_product_specification (match_id); competitive_geo_product_news (geo_product_id); competitive_geo_source (geo_product_id)
- competitive_patent_filing: publication_number (fall back to filing_id if you find publication_number null in data); portfolio_id -> competitive_patent_portfolio (portfolio is non-reviewed; it is live once its competitor is approved)
- competitive_signal: signal_id; company_id -> competitive_competitor. Children: competitive_signal_detail, competitive_signal_evidence (signal_id)
- competitive_competitor_moment: moment_id; competitor_id -> competitive_competitor. Children: competitive_competitor_moment_analysis, competitive_competitor_moment_source (moment_id)
- market_tender: tender_id. Children: market_tender_closing_window, _competitor_fit, _fit_assessment, _requirement, _source, _product_match (tender_id); market_tender_product_match_line (tender_match_id -> market_tender_product_match)
- market_top_opportunity_tender: top_opportunity_tender_id; tender_id -> market_tender
- market_opportunity: opportunity_id. Children: market_opportunity_fit_assessment, _source, _update (opportunity_id)
- market_top_opportunity_project: top_opportunity_project_id; opportunity_id -> market_opportunity
- market_next_move: next_move_id
- market_global_requirement: requirement_id. Children: market_global_requirement_specification, _source (requirement_id)
- technology_innovation: innovation_id. Children: technology_innovation_status, _company, _source, _analysis (innovation_id)
- technology_overview_article: overview_article_id. Children: technology_overview_fact, _key_point, _company, _source (overview_article_id)
Not in GRAPH (unused by any page): competitive_product_evaluation, competitive_product_evaluation_spec.

TABLE-LEVEL approval (no cards; one "Approve setup changes" per table, replaces the whole live table): every `ui.*` table, and the serving reference/summary tables: technology_pillar, technology_category, technology_category_ui_label, technology_company, technology_source, technology_metric, market_tender_portal, market_category_summary, market_filter_option, market_top_opportunity_metric. Status per table: new / changed / live (compare whole-table signatures).

Cross-DB copy: read bundle rows from the staging DB, write them to the serving DB with explicit column lists (INSERT ... VALUES via psycopg2.extras.execute_values); adapt json/jsonb values with psycopg2.extras.Json; keep column order from information_schema of the serving table. The staging and serving tables have identical columns.

## Frontend (review copy)
Same app in Vite mode "review" (`npm run dev:review`, :5180, host 127.0.0.1 only, proxy /api -> :8601, defines VITE_REVIEW=1). A `ReviewProvider` (wrapping the app in DataProvider) holds statuses; `<Review src={item._src} />` renders the status badge + Approve / Reject / Undo / Unpublish / Trace for any object carrying `_src: {t, k, id}` (backend M2 rule). A floating banner shows counts (new/changed/live/rejected) and a "Setup tables" panel for table-level approvals. Trace drawer: staging table + SQL (click to copy), every column with its fact_source quotes, what differs from live (old value under the new), live rows that approve would remove, parent link (trace it), child tables. In the live build all of it renders nothing.
Reference implementation for the single-DB, old schema: `git show db-driven:backend/review.py`, `git show db-driven:src/components/review/Review.jsx`, `git show db-driven:src/styles/review.css` (port and adapt; do not checkout that branch).
