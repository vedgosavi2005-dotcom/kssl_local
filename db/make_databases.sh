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
        "${PSQL[@]}" -d "$1" < kssl_schema_from_docx.sql
        "${PSQL[@]}" -d "$1" < db/setup/02_fix_id_types.sql
    fi
    "${PSQL[@]}" -d "$1" < "$2"
}
build "$STG" db/setup/03_staging_db.sql
"${PSQL[@]}" -d "$STG" < db/setup/05_prompt_run.sql   # prompt run log (python -m prompts.run)
"${PSQL[@]}" -d "$STG" < db/setup/06_news_candidate.sql   # news holding table (python -m backend.news -> prompts.run news)
"${PSQL[@]}" -d "$STG" < db/setup/07_page_setup.sql   # page-configuration rows the prompts need (project stages, Domestic/Export filter, pillar)
build "$SRV" db/setup/04_serving_db.sql
for d in "$STG" "$SRV"; do
    "${PSQL[@]}" -d "$d" -At -c "SELECT '$d: ' || string_agg(nspname || '=' || n, ' ') FROM (SELECT nspname, count(*) n FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace WHERE relkind = 'r' AND nspname IN ('ui','serving','staging','staging_ui') GROUP BY nspname ORDER BY nspname) t"
done
