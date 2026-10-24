#!/usr/bin/env bash
# Nightly restore test on the DC (sysadmin cron, installed by deploy/backup/install.sh into ~/kssl2-backup): restores the
# newest kssl2 backup into a throwaway postgres:16 container and checks every database comes back with tables and rows.
# One line per run in verify.log; receive.sh "status" hands the last line to VPS1's backup run for the pipeline log.
set -uo pipefail
H="$(cd "$(dirname "$0")" && pwd)"; C=kssl2-restore-test
log(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$H/verify.log"; }
F=$(ls -1t "$H"/dumps/kssl2-*.tar 2>/dev/null | head -1)
[ -n "$F" ] || { log "FAIL restore test: no backups yet"; exit 1; }
T=$(mktemp -d); trap 'docker rm -f $C >/dev/null 2>&1; rm -rf "$T"' EXIT
tar -xf "$F" -C "$T" && cd "$T"/* && sha256sum -c --quiet SHA256SUMS || { log "FAIL restore test $(basename "$F"): checksum"; exit 1; }
chmod -R a+rX "$T"
docker rm -f $C >/dev/null 2>&1
docker run -d --name $C -e POSTGRES_PASSWORD=restore-test -v "$PWD:/restore:ro" postgres:16 >/dev/null
# the image's first start runs a temporary server for init, then the real one: wait for the second "ready"
for i in $(seq 90); do [ "$(docker logs $C 2>&1 | grep -c 'ready to accept connections')" -ge 2 ] && break; sleep 2; done
out=""; bad=""
for f in *.dump; do
  d=${f%.dump}
  if docker exec $C createdb -U postgres "$d" &&
     docker exec $C pg_restore -U postgres -d "$d" --no-owner --no-privileges --exit-on-error -j 4 "/restore/$f"; then
    out="$out $d: $(docker exec $C psql -U postgres -d "$d" -Atqc "ANALYZE" -c "SELECT count(*) || ' tables, '
      || coalesce(sum(greatest(c.reltuples, 0))::bigint, 0) || ' rows' FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')");"
  else bad="$bad $d"; fi
done
if [ -z "$bad" ]; then log "OK restore test $(basename "$F"):$out"; else log "FAIL restore test $(basename "$F"): could not restore$bad"; exit 1; fi
