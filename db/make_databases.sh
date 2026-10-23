#!/usr/bin/env bash
# The two KSSL databases (container kssl-pg), built from kssl_schema_from_docx.sql:
#   kssl_staging  schemas staging + staging_ui (+ staging.fact_source, staging.review_decision, staging.prompt_run): all writes go here
#   kssl_serving  schemas serving + ui (+ serving.fact_source), guard triggers: written only by Approve
#   bash db/make_databases.sh [staging_db] [serving_db]
# Idempotent and non-destructive: a database that exists is never dropped or recreated; the
# create-if-missing SQL (db/setup/03, 04) is simply re-applied.
# Backends: KSSL_STAGING_DSN / KSSL_SERVING_DSN (see backend/app.py).
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
PSQL=(docker exec -i -e PGOPTIONS="-c client_min_messages=warning" kssl-pg psql -v ON_ERROR_STOP=1 -q -U kssl)
STG="${1:-kssl_staging}"; SRV="${2:-kssl_serving}"

exists() { [ "$("${PSQL[@]}" -d postgres -At -c "SELECT 1 FROM pg_database WHERE datname = '$1'")" = 1 ]; }
build() {  # build <db> <setup sql>
    if exists "$1"; then echo "$1 exists - not recreated; re-applying $2"
    else
        echo "creating $1"
        "${PSQL[@]}" -d postgres -c "CREATE DATABASE $1"
        "${PSQL[@]}" -d "$1" < db/schema/kssl_schema_from_docx.sql
        "${PSQL[@]}" -d "$1" < db/setup/02_fix_id_types.sql
    fi
    "${PSQL[@]}" -d "$1" < "$2"
}
build "$STG" db/setup/03_staging_db.sql
"${PSQL[@]}" -d "$STG" < db/setup/05_prompt_run.sql   # prompt run log (python -m prompts.run)
"${PSQL[@]}" -d "$STG" < db/setup/06_news_candidate.sql   # news holding table (python -m backend.news -> prompts.run news)
"${PSQL[@]}" -d "$STG" < db/setup/07_page_setup.sql   # page-configuration rows the prompts need (project stages, Domestic/Export filter, pillar)
"${PSQL[@]}" -d "$STG" < db/setup/08_competitor_text_columns.sql   # competitor company-details text columns (starting_year_text, employee_count_text, revenue_text, financial_year)
"${PSQL[@]}" -d "$STG" < db/setup/09_raw_layer.sql                # raw layer: source_document + tender_raw (harvesters write, prompts read)
"${PSQL[@]}" -d "$STG" < db/setup/10_spec_dictionary.sql           # spec label -> canonical key dictionary (python -m prompts.matchup_code)
"${PSQL[@]}" -d "$STG" < db/setup/12_vocabulary.sql              # one category vocabulary (the Excel's 10) in technology_category + stored category texts
"${PSQL[@]}" -d "$STG" < db/setup/13_prompt_run_log.sql          # full per-run log columns + staging.prompt_run_stats view
"${PSQL[@]}" -d "$STG" < db/setup/11_foundations.sql              # story tables, score / glance / stage columns, ui.code_label + filter-option tables (+ code_label seed rows)
"${PSQL[@]}" -d "$STG" < db/setup/09_ui_port_tables.sql        # ui-port tables + columns (docs/ui_port/MAPPING.md C): section_visibility, filter_option, partner legend, synthesis, awards, assessments
"${PSQL[@]}" -d "$STG" < db/setup/15_signal_published_date.sql    # competitive_signal.published_date: the card date is the article's publication date
"${PSQL[@]}" -d "$STG" < db/setup/21_fx_rate.sql                 # fx_rate: official rupee rates (scripts/load_fx_rates.py), Market amounts in INR
"${PSQL[@]}" -d "$STG" < db/setup/16_signal_rule_s2.sql          # rule s2: impact_funding, competitor qualifies/reason, labels none + funding
"${PSQL[@]}" -d "$STG" < db/setup/17_vocab_sync.sql             # code_label rows for the codes the prompts write (red-team 2026-10-18)
"${PSQL[@]}" -d "$STG" < db/setup/18_tender_notice_merge.sql    # market_tender_source.notice_reference (merged re-publications)
"${PSQL[@]}" -d "$STG" < db/setup/19_product_role.sql           # product_class.role (like-for-like gate: same role inside a sub-type)
"${PSQL[@]}" -d "$STG" < db/setup/20_matchup_advantage_kind.sql  # competitive_matchup_advantage.kind (compared / stated)
"${PSQL[@]}" -d "$STG" < db/setup/22_product_description_status.sql  # product description + status (product drawer)
"${PSQL[@]}" -d "$STG" < db/setup/23_signal_risk_v3.sql          # rule s3: risk_score, risk_confidence, label_basis
"${PSQL[@]}" -d "$STG" < db/setup/24_signal_prompt_stats.sql     # view: per-signal prompt cost (review drawer)
"${PSQL[@]}" -d "$STG" < db/setup/25_leader_record_text.sql      # leader record headline -> text
"${PSQL[@]}" -d "$STG" < db/setup/26_competitor_short_details.sql  # short company details + revenue_usd (revenue filter)
"${PSQL[@]}" -d "$STG" < db/setup/27_tender_translation.sql      # tender originals kept beside the English
"${PSQL[@]}" -d "$STG" < db/setup/28_media_images.sql           # media.image: article pictures stored in the DB (/api/image/<id>)
"${PSQL[@]}" -d "$STG" < db/setup/29_text_translation.sql       # originals of translated market cells + translation cache
"${PSQL[@]}" -d "$STG" < db/setup/30_evidence_dates.sql         # story_step / signal evidence dates (as on VPS serving)
"${PSQL[@]}" -d "$STG" < db/setup/35_glance_who_wider.sql      # glance_who up to 80 characters (co-winners)
"${PSQL[@]}" -d "$STG" < db/setup/31_user_activity.sql         # activity.event: review-site usage log (not synced, not reviewed)
"${PSQL[@]}" -d "$STG" < db/setup/32_activity_replay.sql       # activity.event: user_id, move / scroll (review session replay)
"${PSQL[@]}" -d "$STG" < db/setup/36_activity_sessions.sql     # activity.event: login / logout, v_login_sessions
"${PSQL[@]}" -d "$STG" < db/setup/37_activity_recording.sql    # activity.recording: page recordings (rrweb) for exact replay
"${PSQL[@]}" -d "$STG" < db/setup/33_pipeline_log.sql          # ops.*: pipeline log (runs, steps, every row written, script notes)
"${PSQL[@]}" -d "$STG" < db/setup/34_pipeline_history.sql      # ops.step_history: live steps + steps reconstructed from table timestamps
"${PSQL[@]}" -d "$STG" < db/setup/39_flow_log.sql             # ops.step.output (full step log) + ops.note.level, for the Flow dashboard
"${PSQL[@]}" -d "$STG" < db/setup/40_prompt_run_usage_limit.sql  # prompt_run status usage_limit (a limit stop is not a failure)
"${PSQL[@]}" -d "$STG" < db/setup/38_source_link.sql           # staging.source_link: dead source links -> their archive copy
build "$SRV" db/setup/04_serving_db.sql
"${PSQL[@]}" -d "$SRV" < db/setup/08_competitor_text_columns.sql
"${PSQL[@]}" -d "$SRV" < db/setup/11_foundations.sql              # same DDL on the serving schemas (Approve copies by column name); no seed rows here
"${PSQL[@]}" -d "$SRV" < db/setup/09_ui_port_tables.sql        # same ui-port tables in serving.* / ui.*, plus their only_via_approve guard triggers
"${PSQL[@]}" -d "$SRV" < db/setup/15_signal_published_date.sql    # same column in serving.competitive_signal (Approve copies by column name)
"${PSQL[@]}" -d "$SRV" < db/setup/21_fx_rate.sql                 # same table in serving + its only_via_approve guard
"${PSQL[@]}" -d "$SRV" < db/setup/16_signal_rule_s2.sql          # same columns in serving
"${PSQL[@]}" -d "$SRV" < db/setup/18_tender_notice_merge.sql    # same column in serving
"${PSQL[@]}" -d "$SRV" < db/setup/20_matchup_advantage_kind.sql  # same column in serving
"${PSQL[@]}" -d "$SRV" < db/setup/22_product_description_status.sql  # same columns in serving
"${PSQL[@]}" -d "$SRV" < db/setup/23_signal_risk_v3.sql          # same columns in serving
"${PSQL[@]}" -d "$SRV" < db/setup/25_leader_record_text.sql      # same column in serving
"${PSQL[@]}" -d "$SRV" < db/setup/26_competitor_short_details.sql  # same columns in serving
"${PSQL[@]}" -d "$SRV" < db/setup/27_tender_translation.sql      # same columns in serving
"${PSQL[@]}" -d "$SRV" < db/setup/30_evidence_dates.sql         # same columns in serving
"${PSQL[@]}" -d "$SRV" < db/setup/35_glance_who_wider.sql      # glance_who up to 80 characters (co-winners)
"${PSQL[@]}" -d "$SRV" < db/setup/31_user_activity.sql         # activity.event: live-site usage log (outside serving/ui: no approve guard)
"${PSQL[@]}" -d "$SRV" < db/setup/32_activity_replay.sql       # activity.event: user_id, move / scroll (review session replay)
"${PSQL[@]}" -d "$SRV" < db/setup/36_activity_sessions.sql     # activity.event: login / logout, v_login_sessions
"${PSQL[@]}" -d "$SRV" < db/setup/37_activity_recording.sql    # activity.recording: page recordings (rrweb) for exact replay
for d in "$STG" "$SRV"; do
    "${PSQL[@]}" -d "$d" -At -c "SELECT '$d: ' || string_agg(nspname || '=' || n, ' ') FROM (SELECT nspname, count(*) n FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace WHERE relkind = 'r' AND nspname IN ('ui','serving','staging','staging_ui') GROUP BY nspname ORDER BY nspname) t"
done
