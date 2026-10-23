#!/usr/bin/env bash
# One-time: fill the databases of a NEW server (AWS) from this PC -- after bootstrap.sh, before the first deploy_vps.sh.
#   KSSL_VPS_HOST=<static-ip> KSSL_VPS_SSH_USER=ubuntu KSSL_SSH_KEY=~/.ssh/kssl_aws.pem bash deploy/aws/init_db.sh [git-ref]
# 1. ships the committed code (git archive, as deploy_vps.sh does) and starts only the database container
# 2. creates the app role kssl_app (password read on the server from its own deploy/.env) and both databases
# 3. copies the local live database kssl_serving (structure + data; the usage log and Ask Parallax history are left out),
#    then the review copy with the usual sync (db/sync_staging_to_vps.sh: staging + staging_ui + media, raw layer left out)
# Refuses when the server's kssl_serving already holds tables: it never overwrites a live database.
set -euo pipefail
cd "$(dirname "$0")/../.."
REF="${1:-v2}"
envval() { [ -f .env ] && sed -n "s/^$1=//p" .env | tail -1 | tr -d "\"'\r"; }
H="${KSSL_VPS_HOST:-$(envval KSSL_VPS_HOST)}"
U="${KSSL_VPS_SSH_USER:-$(envval KSSL_VPS_SSH_USER)}"
[ -n "$H" ] && [ -n "$U" ] || { echo "set KSSL_VPS_HOST and KSSL_VPS_SSH_USER"; exit 1; }
SSH=(ssh -i "${KSSL_SSH_KEY:-$HOME/.ssh/kssl_vps}" -o ConnectTimeout=20 -o BatchMode=yes -o ServerAliveInterval=15 "$U@$H")

echo "== shipping $(git rev-parse --short "$REF") and starting the database"
git archive --format=tar "$REF" | gzip | "${SSH[@]}" 'set -e; cd /opt/kssl-v2 && tar -xzf - && cd deploy && docker compose up -d db'

echo "== role and databases"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/kssl-v2/deploy; set -a; . ./.env; set +a
for i in $(seq 60); do docker exec kssl2-db pg_isready -U kssl_admin -q && break; sleep 2; done
P="docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -U kssl_admin"
$P -d postgres -v pw="$APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE kssl_app LOGIN PASSWORD %L', :'pw') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kssl_app') \gexec
SELECT 'CREATE DATABASE kssl_serving' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'kssl_serving') \gexec
SELECT 'CREATE DATABASE kssl_staging' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'kssl_staging') \gexec
SQL
n=$($P -d kssl_serving -Atc "SELECT count(*) FROM pg_tables WHERE schemaname IN ('serving', 'ui')")
[ "$n" = 0 ] || { echo "kssl_serving on this server already holds $n tables: refusing to overwrite it"; exit 1; }
REMOTE

echo "== live database (local kssl_serving -> server)"
docker exec kssl-pg pg_dump -U kssl -d kssl_serving -Fc --no-owner --no-privileges \
    --exclude-table-data='activity.*' --exclude-table-data='parallax_agent.*' \
  | "${SSH[@]}" 'docker exec -i kssl2-db pg_restore -U kssl_admin -d kssl_serving --no-owner --no-privileges --exit-on-error'

echo "== review copy (db/sync_staging_to_vps.sh)"
KSSL_VPS_HOST="$H" KSSL_VPS_SSH_USER="$U" bash db/sync_staging_to_vps.sh

echo "init done. Next: deploy/deploy_vps.sh with the same KSSL_VPS_HOST / KSSL_VPS_SSH_USER / KSSL_SSH_KEY (README step 8)"
