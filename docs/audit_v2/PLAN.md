# v2 plan (coordinator: Opus 5.5 plans/reviews; Sonnet 5.5 agents implement)

Order agreed with the user: **audit -> backend mapping -> clean-up -> review copy -> two databases -> prompts + HTML**. News API runs in parallel.

## 1. Audit (docs/audit_v2/A-D_*.md)
Every visible value traced to a column; kinds STORED / COMPUTED-JS / COMPUTED-BACKEND / CHROME / INVENTED / NO-COLUMN.
Default decisions (user can override): NO-COLUMN -> hide and list; INVENTED -> remove; COMPUTED-JS -> keep if the rule only uses DB values, and document it.

## 2. Backend mapping
backend/app.py stays the entry; builders split per area into backend/areas/<area>.py (one owner each), each `build(db, d)` reading `db["ui"|"serving"][table]`. Every table a page needs is served; nothing is defaulted.

## 3. Clean-up
Remove invented content from the frontend; hide NO-COLUMN fields; keep chrome.

## 4. Review copy
Same app in Vite mode "review" (:5180, localhost only) against a review backend (:8601, KSSL_VIEW=review). Every card: Approve / Reject / Unpublish / Trace; status new / changed / live / rejected. Card graph (table -> key, parents, children) rebuilt for the new tables. ui tables: one "Approve setup changes" per table.

## 5. Two databases (user decision 2026-10-16)
- `kssl_staging`  : schemas `staging` (data) + `staging_ui` (page config) + `staging.fact_source` + `staging.review_decision`. Written by Excel loaders, prompt loaders, the news job, hand inserts.
- `kssl_serving`  : schemas `serving` + `ui` + `serving.fact_source`. Read by the live UI. Written only by Approve / Unpublish (guard trigger: kssl.approve).
- Both built from kssl_schema_from_docx.sql (staging DB: same DDL, schemas renamed ui->staging_ui, serving->staging).
- Env: `KSSL_SERVING_DSN`, `KSSL_STAGING_DSN` (fallback `KSSL_DSN`).
- Live backend: reads serving DB. Review backend: reads staging DB for content, serving DB for status (new/changed/live).
- Approve: read the card bundle from the staging DB, replace it in the serving DB in ONE serving-DB transaction (atomic on the live side); the staging DB only gets the rejection bookkeeping. No cross-DB 2PC needed: status is recomputed by comparing content, so a lost bookkeeping write cannot desync.
- The old `kssl_frontend` DB stays as a backup (v1_* schemas + the current single-DB staging copy).

## Hidden (user, re-confirmed 2026-10-16)
Gap Analysis (archived + unreachable), Stock, Parallax Read, Strategic Positioning paragraph, SWOT, product images.

## 6. Data sources (user, 2026-10-16)
Excel (no prompts): competitor company details, competitor leadership, competitor products + specs, client (KSSL) data incl. client products/specs.
Prompts: everything else (signals, evaluations/matchups, partnerships, projects, geo, tenders, opportunities, global requirements, innovations, tech articles, competitor moments). News: the news job.
