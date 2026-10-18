#!/usr/bin/env bash
# Throwaway database for checking pages with fictional rows (never the real DBs).
#   bash db/make_test_db.sh [db_name] [seed.sql ...]
#     db_name defaults to kssl_v2_test; seeds default to every db/test_seed_v2/*.sql.
#     Rebuilds schema + migrations, loads the seeds into staging, then copies staging -> serving
#     so the live backend shows them (as if everything had been approved).
# Backend on it: KSSL_DSN="host=127.0.0.1 port=55432 dbname=<db_name> user=kssl password=kssl"
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
PSQL=(docker exec -i kssl-pg psql -v ON_ERROR_STOP=1 -q -U kssl)
DB="${1:-kssl_v2_test}"; shift || true
case "$DB" in kssl_v2_test*) ;; *) echo "refusing: test databases must be named kssl_v2_test*"; exit 1;; esac
SEEDS=("$@"); [ ${#SEEDS[@]} -eq 0 ] && SEEDS=(db/test_seed_v2/*.sql)

"${PSQL[@]}" -d postgres -c "DROP DATABASE IF EXISTS $DB WITH (FORCE)" -c "CREATE DATABASE $DB"
"${PSQL[@]}" -d "$DB" < db/schema/kssl_schema_from_docx.sql
for m in db/migrations/*.sql; do "${PSQL[@]}" -d "$DB" < "$m"; done
for f in "${SEEDS[@]}"; do [ -e "$f" ] && { echo "seed $f"; "${PSQL[@]}" -d "$DB" < "$f"; }; done
"${PSQL[@]}" -d "$DB" <<'SQL'
BEGIN;
SET LOCAL kssl.approve = 'on';
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT tablename, CASE schemaname WHEN 'staging' THEN 'serving' ELSE 'ui' END AS live, schemaname
             FROM pg_tables WHERE schemaname IN ('staging', 'staging_ui') AND tablename <> 'review_decision' LOOP
        EXECUTE format('DELETE FROM %I.%I', r.live, r.tablename);
        EXECUTE format('INSERT INTO %I.%I SELECT * FROM %I.%I', r.live, r.tablename, r.schemaname, r.tablename);
    END LOOP;
END $$;
COMMIT;
SQL
"${PSQL[@]}" -d "$DB" -At -c "SELECT 'rows in serving: ' || sum(n_live_tup) FROM pg_stat_user_tables WHERE schemaname = 'serving'"
