#!/usr/bin/env bash
# Backup of VPS1's kssl2-db: root cron every 6 h (installed by deploy/backup/install.sh into /opt/kssl-v2/backup). One run:
#   1. dumps every database (pg_dump -Fc) + the roles (pg_dumpall -g) into one tar with a SHA256SUMS file
#   2. ships the tar to each receiver in ./receivers ("name ssh-target port hours"; hours = "all" or the UTC hour that gets a
#      copy) over ./id_backup, a key that can only ADD a backup there (receive.sh is its forced command); the receiver echoes
#      the stored file's sha256, which must match
#   3. reports the DC standby (replication slot dc_standby) and the DC's last nightly restore test (verify.log)
#   4. logs every step in the pipeline log (ops.run / ops.step / ops.note in kssl_staging), so it shows on the review site
# Keeps the newest 2 tars in ./local. Exit 0 only when every step is ok.
set -uo pipefail
B="$(cd "$(dirname "$0")" && pwd)"
TS=$(date -u +%Y%m%dT%H%MZ); NAME=kssl2-$TS.tar; TAR=$B/local/$NAME; W=$B/local/$TS
SSH=(ssh -i "$B/id_backup" -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)
pg(){ docker exec -i kssl2-db psql -U kssl_admin -v ON_ERROR_STOP=1 -Atq "$@"; }

RUN=$(pg -d kssl_staging -c "INSERT INTO ops.run (run_id, kind, host, args, notes)
  VALUES (gen_random_uuid(), 'manual', 'vps1', '{\"job\": \"backup\"}', 'kssl2 database backup') RETURNING run_id") || RUN=""
OKS=0; FAILS=0
step(){   # name status seconds message [error]
  case "$2" in ok) OKS=$((OKS + 1)) ;; failed) FAILS=$((FAILS + 1)) ;; esac
  echo "$(date -u +%FT%TZ) $NAME $1 $2 ${3}s $4 ${5:-}"
  [ -n "$RUN" ] || return 0
  pg -d kssl_staging >/dev/null <<SQL || true
WITH s AS (INSERT INTO ops.step (step_id, run_id, name, script, started_at, ended_at, status, seconds, error)
           VALUES (gen_random_uuid(), '$RUN', 'backup.$1', 'deploy/backup/backup.sh', clock_timestamp() - interval '$3 seconds',
                   clock_timestamp(), '$2', $3, NULLIF(\$e\$${5:-}\$e\$, '')) RETURNING step_id)
INSERT INTO ops.note (step_id, script, kind, outcome, subject, message)
SELECT step_id, 'deploy/backup/backup.sh', 'backup', '$2', '$NAME', \$m\$$4\$m\$ FROM s;
SQL
}
finish(){
  local st=ok; [ $FAILS -gt 0 ] && st=partial; [ $OKS -eq 0 ] && st=failed
  [ -n "$RUN" ] && pg -d kssl_staging -c "UPDATE ops.run SET ended_at = clock_timestamp(), status = '$st' WHERE run_id = '$RUN'" >/dev/null
  ls -1t "$B"/local/kssl2-*.tar 2>/dev/null | tail -n +3 | xargs -r rm -f
  rm -rf "$W"; [ "$st" = ok ]; exit $?
}

# 1. dump
t=$SECONDS; err=""; mkdir -p "$W"
DBS=$(pg -d postgres -c "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1") || err="listing databases failed"
for d in $DBS; do docker exec kssl2-db pg_dump -U kssl_admin -Fc -Z6 "$d" > "$W/$d.dump" || err="$err; pg_dump $d failed"; done
docker exec kssl2-db pg_dumpall -U kssl_admin -g > "$W/roles.sql" || err="$err; roles failed"
[ -z "$err" ] && { (cd "$W" && sha256sum * > SHA256SUMS) && tar -C "$B/local" -cf "$TAR" "$TS" || err="tar failed"; }
if [ -n "$err" ]; then step dump failed $((SECONDS - t)) "The backup dump failed; nothing was sent." "$err"; finish; fi
MB=$(( $(stat -c %s "$TAR") / 1048576 )); SUM=$(sha256sum "$TAR" | cut -d' ' -f1)
step dump ok $((SECONDS - t)) "Dumped $(echo $DBS | wc -w) databases ($(echo $DBS | tr ' ' ',')) and the roles: $MB MB."

# 2. copies
HOUR=$(date -u +%H)
while read -r name target port hours; do
  [ -n "$name" ] && [ "${name:0:1}" != "#" ] || continue
  [ "$hours" = all ] || [ "$hours" = "$HOUR" ] || [ -n "${KSSL_BACKUP_ALL:-}" ] || continue   # ALL=1: every receiver (install's first run)
  t=$SECONDS
  got=$("${SSH[@]}" -p "$port" "$target" "put $NAME $SUM" < "$TAR" 2>&1 | tail -1)   # the receiver keeps it only if $SUM matches
  if [ "$got" = "$SUM" ]; then step "copy_$name" ok $((SECONDS - t)) "Stored $NAME ($MB MB) on $name; checksum matches."
  else step "copy_$name" failed $((SECONDS - t)) "Could not store $NAME on $name." "$got"; fi
done < "$B/receivers"

# 3. the DC standby: is it streaming, and how far behind
t=$SECONDS
sb=$(pg -d postgres -F '|' -c "SELECT s.active, coalesce(r.state, 'disconnected'),
       coalesce(pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), r.replay_lsn)), '?'), coalesce(date_trunc('second', r.replay_lag)::text, '0')
     FROM pg_replication_slots s LEFT JOIN pg_stat_replication r ON r.pid = s.active_pid WHERE s.slot_name = 'dc_standby'")
if [ -z "$sb" ]; then step standby skipped 0 "No DC standby set up yet."
else IFS='|' read -r active state behind lag <<< "$sb"
  if [ "$active" = t ] && [ "$state" = streaming ]; then step standby ok 0 "The DC standby is streaming: $behind behind, replay lag $lag."
  else step standby failed $((SECONDS - t)) "The DC standby is not streaming ($state). VPS1 keeps up to 4 GB of changes for it, then drops it." "$sb"; fi
fi

# 4. the DC's last nightly restore test
t=$SECONDS
dc=$(awk '$1 == "dc" {print $2, $3}' "$B/receivers")
if [ -n "$dc" ]; then
  v=$("${SSH[@]}" -p "${dc#* }" "${dc% *}" status 2>&1 | tail -1)
  vt=$(date -u -d "${v%% *}" +%s 2>/dev/null || echo 0)
  if [[ "$v" == *" OK restore test "* ]] && (( $(date -u +%s) - vt < 30 * 3600 )); then step restore_test ok $((SECONDS - t)) "${v#* }"
  else step restore_test failed $((SECONDS - t)) "No passing restore test on the DC in the last 30 hours." "$v"; fi
fi
finish
