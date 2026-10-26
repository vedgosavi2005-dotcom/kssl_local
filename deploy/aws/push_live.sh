#!/usr/bin/env bash
# Runs ON VPS1 every 5 minutes (cron, installed by deploy/aws/link_vps1.sh): keeps the AWS live site equal to VPS1's live data.
# VPS1 is the only place anything is written; AWS is a read-only copy of it, except the AWS site's own usage log.
#  1. live data: when VPS1's serving / ui tables changed since the last push, every serving + ui table is copied to AWS in ONE
#     transaction (one pg_dump snapshot, TRUNCATE + COPY). On any error AWS keeps its previous data. AWS's activity schema is never touched.
#  2. the two staging tables the live API reads (backend/app.py): staging.source_link (dead link -> archive copy) with every
#     push, and media (card pictures, ~460 MB) only when VPS1's image set differs from AWS's.
#  3. pulls the AWS site's new usage-log rows (activity.event / activity.recording) into VPS1's serving DB, so the review site's
#     analytics and session replays include AWS visits. AWS ids are not kept (both sides number their own rows); the last AWS
#     id pulled is the watermark.
#   bash /opt/kssl-v2/aws/push_live.sh [--force]        (log: /opt/kssl-v2/aws/push.log)
set -euo pipefail
D=/opt/kssl-v2/aws
. "$D/push.env"                                    # KSSL_AWS_HOST, KSSL_AWS_USER (written by link_vps1.sh)
exec 9>"$D/push.lock"; flock -n 9 || exit 0        # a slow push (the pictures) is never overlapped by the next run
SSH=(ssh -i "$D/id_aws" -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=8
     -o StrictHostKeyChecking=accept-new "$KSSL_AWS_USER@$KSSL_AWS_HOST")
q()      { docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -At -U kssl_admin -d "$1"; }              # SQL on stdin, VPS1
aws_q()  { "${SSH[@]}" "docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -At -U kssl_admin -d $1"; }  # same, on AWS
aws_tx() { gzip | "${SSH[@]}" "gunzip | docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -1 -U kssl_admin -d $1 >/dev/null"; }
log()    { echo "$(date -u +%FT%TZ) $*"; }

# ---- 1 + 2: live data -----------------------------------------------------------------------------------------------------
# ponytail: "changed" = the write counters of the serving / ui tables + the dead-link table. A Postgres crash resets the
# counters, which only costs one extra (identical) push.
# (written to a file at top level, not inside $( ): a failing query must stop the run, not hash an empty answer)
{ q kssl_serving <<<"SELECT md5(string_agg(relid::regclass::text || n_tup_ins || '/' || n_tup_upd || '/' || n_tup_del, ',' ORDER BY relid))
                     FROM pg_stat_user_tables WHERE schemaname IN ('serving', 'ui')"
  q kssl_staging <<<"SELECT count(*) || '/' || coalesce(max(checked_at)::text, '') FROM staging.source_link"; } > "$D/live.fp.new"
fp=$(md5sum < "$D/live.fp.new" | cut -c1-32)
if [ "${1:-}" = --force ] || [ "$fp" != "$(cat "$D/live.fp" 2>/dev/null)" ]; then
  { echo "SET LOCAL kssl.approve = 'on';"          # the serving guard (db/setup/04): the push is a publish, like Approve
    # TRUNCATE, not DELETE: the API reads tables without ORDER BY, so ties (e.g. tenders with the same dates) show in storage
    # order; refilled empty tables store the rows in VPS1's order, where DELETE + COPY reuses freed space and scrambles it.
    # ponytail: readers wait for the push (seconds); a deterministic ORDER BY in backend/app.py would remove the need.
    q kssl_serving <<<"SELECT 'TRUNCATE ' || string_agg(format('%I.%I', schemaname, tablename), ', ') || ';' FROM pg_tables WHERE schemaname IN ('serving', 'ui')"
    docker exec kssl2-db pg_dump -U kssl_admin -d kssl_serving --data-only -n serving -n ui --no-owner --no-privileges
  } | aws_tx kssl_serving
  { echo "DELETE FROM staging.source_link;"
    echo "COPY staging.source_link (url, status, archive_url, archived_at, checked_at) FROM STDIN;"
    q kssl_staging <<<"COPY staging.source_link (url, status, archive_url, archived_at, checked_at) TO STDOUT"
    echo '\.'
  } | aws_tx kssl_staging
  echo "$fp" > "$D/live.fp"
  log "live data pushed: $(aws_q kssl_serving <<<"SELECT count(*) FROM pg_tables WHERE schemaname IN ('serving', 'ui')") tables"
fi

IMGQ="SELECT coalesce(md5(string_agg(image_id::text, ',' ORDER BY image_id)), 'none') FROM media.image"
if [ "$(q kssl_staging <<<"$IMGQ")" != "$(aws_q kssl_staging <<<"$IMGQ" 2>/dev/null || echo missing)" ]; then
  docker exec kssl2-db pg_dump -U kssl_admin -d kssl_staging -n media --clean --if-exists --no-owner --no-privileges \
    | sed -e '/^DROP SCHEMA /d' -e 's/^CREATE SCHEMA \(.*\);$/CREATE SCHEMA IF NOT EXISTS \1;/' \
    | aws_tx kssl_staging
  aws_q kssl_staging <<<"GRANT USAGE ON SCHEMA media TO kssl_app; GRANT SELECT ON ALL TABLES IN SCHEMA media TO kssl_app;"
  log "pictures pushed: $(aws_q kssl_staging <<<"SELECT count(*) FROM media.image") images"
fi

# ---- 3: the AWS site's usage log -> VPS1 -----------------------------------------------------------------------------------
pull() {                                               # pull <table> <id column>
  local t=$1 id=$2 last cols got
  last=$(cat "$D/$t.last" 2>/dev/null || echo 0)
  cols=$(q kssl_serving <<<"SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position) FROM information_schema.columns
                            WHERE table_schema = 'activity' AND table_name = '$t' AND column_name <> '$id'")
  got=$( { echo "CREATE TEMP TABLE x ON COMMIT DROP AS SELECT $id, $cols FROM activity.$t LIMIT 0;"
           echo "COPY x FROM STDIN;"
           aws_q kssl_serving <<<"COPY (SELECT $id, $cols FROM activity.$t WHERE $id > $last ORDER BY $id LIMIT 50000) TO STDOUT"
           echo '\.'
           echo "INSERT INTO activity.$t ($cols) SELECT $cols FROM x ORDER BY $id;"
           echo "SELECT coalesce(max($id), $last) || ' ' || count(*) FROM x;"
         } | docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -At -1 -U kssl_admin -d kssl_serving )
  # ponytail: the watermark is written after the commit; a crash between the two re-pulls those rows once (duplicates)
  echo "${got%% *}" > "$D/$t.last.tmp" && mv "$D/$t.last.tmp" "$D/$t.last"
  [ "${got##* }" = 0 ] || log "usage log: ${got##* } new AWS $t rows"
}
pull event event_id
pull recording rec_id

# terms acceptances (db/setup/42; key user_name + terms_version, no id): tiny, so copy them all and keep what VPS1 has.
# Skipped until the table exists on both sides.
has_terms="SELECT to_regclass('activity.terms_acceptance') IS NOT NULL"
if [ "$(q kssl_serving <<<"$has_terms")" = t ] && [ "$(aws_q kssl_serving <<<"$has_terms")" = t ]; then
  cols=$(q kssl_serving <<<"SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position) FROM information_schema.columns
                            WHERE table_schema = 'activity' AND table_name = 'terms_acceptance'")
  got=$( { echo "CREATE TEMP TABLE x ON COMMIT DROP AS SELECT $cols FROM activity.terms_acceptance LIMIT 0;"
           echo "COPY x FROM STDIN;"
           aws_q kssl_serving <<<"COPY (SELECT $cols FROM activity.terms_acceptance) TO STDOUT"
           echo '\.'
           echo "WITH i AS (INSERT INTO activity.terms_acceptance ($cols) SELECT $cols FROM x ON CONFLICT DO NOTHING RETURNING 1) SELECT count(*) FROM i;"
         } | docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -At -1 -U kssl_admin -d kssl_serving )
  [ "$got" = 0 ] || log "usage log: $got new AWS terms acceptances"
fi
