#!/usr/bin/env bash
# Copy the local staging data (schemas staging + staging_ui + media of kssl_staging) to the VPS staging DB.
# media holds the stored card images (media.image, ~400 MB): card image columns point at /api/image/<id>.
#   bash db/sync_staging_to_vps.sh            (KSSL_SYNC_TARGET=local:<db> restores into a local DB instead -- a dry run)
# Each copied table is dropped and recreated on the target from the local one (schema + rows) in ONE
# transaction: on any error the target keeps its previous staging. The VPS serving DB is never touched
# (it changes only through Approve on the VPS review site).
# Not copied:
#   staging.review_decision          -- the VPS review site's own Reject decisions
#   raw layer / bookkeeping rows     -- prompt inputs, never displayed (tender_raw alone is ~950 MB). Their table STRUCTURE goes
#                                       (empty on the VPS), so both review sites list the same tables (owner 2026-10-25);
#                                       prompt_run gets its rows in a slim copy below.
set -euo pipefail
MEDIA=1       # cleared below when the VPS already holds the same image set
ENV_FILE="$(dirname "$0")/../.env"
envval() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | tr -d "\"'\r"; }
VPS_HOST="${KSSL_VPS_HOST:-$(envval KSSL_VPS_HOST)}"      # host and user live in the gitignored .env (the repo is public)
VPS_USER="${KSSL_VPS_SSH_USER:-$(envval KSSL_VPS_SSH_USER)}"
EXCLUDE=(staging.review_decision)
NO_ROWS=(staging.tender_raw staging.source_document staging.news_candidate staging.prompt_run staging.spec_dictionary)
args=(); for t in "${EXCLUDE[@]}"; do args+=(--exclude-table="$t"); done
for t in "${NO_ROWS[@]}"; do args+=(--exclude-table-data="$t"); done
GRANTS="GRANT USAGE ON SCHEMA staging, staging_ui, media TO kssl_app;
        GRANT ALL ON ALL TABLES IN SCHEMA staging, staging_ui, media TO kssl_app;
        GRANT ALL ON ALL SEQUENCES IN SCHEMA staging, staging_ui, media TO kssl_app;"

dump() {
  docker exec kssl-pg pg_dump -U kssl -d kssl_staging -n staging -n staging_ui ${MEDIA:+-n media} \
      --clean --if-exists --no-owner --no-privileges "${args[@]}" \
    | sed -e '/^DROP SCHEMA /d' -e 's/^CREATE SCHEMA \(.*\);$/CREATE SCHEMA IF NOT EXISTS \1;/' \
          -e '/^CREATE TRIGGER ops_log/d'
  # the pipeline-log triggers (db/setup/33) stay local: the pipeline runs here, and the copy must not need the ops schema there
}

# The copy as the target runs it, in its one transaction: the pipeline-log history view (ops.step_history, db/setup/34) reads
# staging tables the copy drops and recreates, so it is dropped first and rebuilt from 34 at the end -- only where the target
# has the ops schema (a kssl_test_* dry-run DB may not).
payload() {
  echo "DROP VIEW IF EXISTS ops.step_history;"
  dump
  echo "SELECT to_regnamespace('ops') IS NOT NULL AS has_ops \\gset"
  echo "\\if :has_ops"
  cat db/setup/34_pipeline_history.sql
  echo "\\endif"
}

TARGET="${KSSL_SYNC_TARGET:-vps}"
echo "== $(date '+%F %T') local kssl_staging -> $TARGET"
if [[ "$TARGET" == local:* ]]; then
  db="${TARGET#local:}"
  case "$db" in kssl_test_*) ;; *) echo "refusing: local dry-run target must be kssl_test_*"; exit 1;; esac
  payload | docker exec -i kssl-pg psql -v ON_ERROR_STOP=1 -q -1 -U kssl -d "$db" >/dev/null
  docker exec kssl-pg psql -U kssl -d "$db" -Atc "select 'tables: ' || count(*) from pg_tables where schemaname in ('staging','staging_ui','media')"
else
  [ -n "$VPS_HOST" ] && [ -n "$VPS_USER" ] || { echo "set KSSL_VPS_HOST and KSSL_VPS_SSH_USER in .env"; exit 1; }
  SSH=(ssh -i "${KSSL_SSH_KEY:-$HOME/.ssh/kssl_vps}" -o ConnectTimeout=20 -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=8 "$VPS_USER@$VPS_HOST")
  # media (~400 MB of images) goes only when the VPS image set differs: a full copy over a slow link was cut twice (2026-10-22)
  IMGQ="select coalesce(md5(string_agg(image_id::text, ',' order by image_id)), 'none') from media.image"
  here=$(docker exec kssl-pg psql -U kssl -d kssl_staging -Atc "$IMGQ")
  there=$("${SSH[@]}" "docker exec kssl2-db psql -U kssl_admin -d kssl_staging -Atc \"$IMGQ\"" 2>/dev/null || echo missing)
  if [ "$here" = "$there" ]; then MEDIA=; echo "   media: same image set on both sides, not sent"; else echo "   media: image set differs, sending it"; fi
  payload | gzip | "${SSH[@]}" 'gunzip | docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -1 -U kssl_admin -d kssl_staging >/dev/null'
  # staging.prompt_run rows, slim (owner 2026-10-25: the VPS review shows the same prompt cost as here): the review drawer's
  # per-signal cost (db/setup/24) reads it. The table itself came with the payload; prompt text, raw output and per-call
  # details (194 of its 200 MB) stay local.
  PR_COLS=$(docker exec kssl-pg psql -U kssl -d kssl_staging -Atc "SELECT string_agg(quote_ident(attname), ', ' ORDER BY attnum) FROM pg_attribute
            WHERE attrelid = 'staging.prompt_run'::regclass AND attnum > 0 AND NOT attisdropped AND attname NOT IN ('prompt_text', 'raw_output', 'details')")
  { echo "TRUNCATE staging.prompt_run;"
    echo "COPY staging.prompt_run ($PR_COLS) FROM STDIN;"
    docker exec kssl-pg psql -U kssl -d kssl_staging -c "COPY (SELECT $PR_COLS FROM staging.prompt_run ORDER BY started_at, run_id) TO STDOUT"
    echo '\.'
  } | gzip | "${SSH[@]}" 'gunzip | docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -1 -U kssl_admin -d kssl_staging >/dev/null'
  echo "   prompt_run: $("${SSH[@]}" "docker exec kssl2-db psql -U kssl_admin -d kssl_staging -Atc 'SELECT count(*) FROM staging.prompt_run'") runs (slim)"
  echo "$GRANTS" | "${SSH[@]}" 'docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -U kssl_admin -d kssl_staging'
  "${SSH[@]}" "docker exec kssl2-db psql -U kssl_admin -d kssl_staging -Atc \"select 'VPS staging tables: ' || count(*) from pg_tables where schemaname in ('staging','staging_ui','media')\""
fi
echo "== done $(date '+%F %T')"
