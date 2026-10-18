#!/usr/bin/env bash
# Copy the local staging data (schemas staging + staging_ui of kssl_staging) to the VPS staging DB.
#   bash db/sync_staging_to_vps.sh            (KSSL_SYNC_TARGET=local:<db> restores into a local DB instead -- a dry run)
# Each copied table is dropped and recreated on the target from the local one (schema + rows) in ONE
# transaction: on any error the target keeps its previous staging. The VPS serving DB is never touched
# (it changes only through Approve on the VPS review site).
# Not copied:
#   staging.review_decision          -- the VPS review site's own Reject decisions
#   raw layer / bookkeeping          -- prompt inputs, never displayed (tender_raw alone is ~800 MB)
set -euo pipefail
ENV_FILE="$(dirname "$0")/../.env"
envval() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | tr -d "\"'\r"; }
VPS_HOST="${KSSL_VPS_HOST:-$(envval KSSL_VPS_HOST)}"      # host and user live in the gitignored .env (the repo is public)
VPS_USER="${KSSL_VPS_SSH_USER:-$(envval KSSL_VPS_SSH_USER)}"
EXCLUDE=(staging.review_decision staging.tender_raw staging.source_document staging.news_candidate
         staging.prompt_run staging.prompt_run_stats staging.spec_dictionary)  # prompt_run_stats: view over prompt_run
args=(); for t in "${EXCLUDE[@]}"; do args+=(--exclude-table="$t"); done
GRANTS="GRANT USAGE ON SCHEMA staging, staging_ui TO kssl_app;
        GRANT ALL ON ALL TABLES IN SCHEMA staging, staging_ui TO kssl_app;
        GRANT ALL ON ALL SEQUENCES IN SCHEMA staging, staging_ui TO kssl_app;"

dump() {
  docker exec kssl-pg pg_dump -U kssl -d kssl_staging -n staging -n staging_ui \
      --clean --if-exists --no-owner --no-privileges "${args[@]}" \
    | sed -e '/^DROP SCHEMA /d' -e 's/^CREATE SCHEMA \(.*\);$/CREATE SCHEMA IF NOT EXISTS \1;/'
}

TARGET="${KSSL_SYNC_TARGET:-vps}"
echo "== $(date '+%F %T') local kssl_staging -> $TARGET"
if [[ "$TARGET" == local:* ]]; then
  db="${TARGET#local:}"
  case "$db" in kssl_test_*) ;; *) echo "refusing: local dry-run target must be kssl_test_*"; exit 1;; esac
  dump | docker exec -i kssl-pg psql -v ON_ERROR_STOP=1 -q -1 -U kssl -d "$db" >/dev/null
  docker exec kssl-pg psql -U kssl -d "$db" -Atc "select 'tables: ' || count(*) from pg_tables where schemaname in ('staging','staging_ui')"
else
  [ -n "$VPS_HOST" ] && [ -n "$VPS_USER" ] || { echo "set KSSL_VPS_HOST and KSSL_VPS_SSH_USER in .env"; exit 1; }
  SSH=(ssh -i "$HOME/.ssh/kssl_vps" -o ConnectTimeout=20 -o BatchMode=yes "$VPS_USER@$VPS_HOST")
  dump | gzip | "${SSH[@]}" 'gunzip | docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -1 -U kssl_admin -d kssl_staging >/dev/null'
  echo "$GRANTS" | "${SSH[@]}" 'docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -U kssl_admin -d kssl_staging'
  "${SSH[@]}" "docker exec kssl2-db psql -U kssl_admin -d kssl_staging -Atc \"select 'VPS staging tables: ' || count(*) from pg_tables where schemaname in ('staging','staging_ui')\""
fi
echo "== done $(date '+%F %T')"
