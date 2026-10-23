#!/usr/bin/env bash
# One-time, from this PC: fill the databases of the NEW AWS live server from VPS1 -- after bootstrap.sh, before deploy.sh.
#   KSSL_AWS_HOST=<elastic-ip> bash deploy/aws/init_db.sh [git-ref]
# 1. ships the committed code (git archive) and starts only the database container
# 2. creates the app role kssl_app (password read on the server from its own deploy/.env) and both databases
# 3. connects VPS1 to AWS (deploy/aws/link_vps1.sh: VPS1's key, push script, 5-minute cron)
# 4. VPS1 copies its kssl_serving straight to AWS (structure + data; the usage log and Ask Parallax history are left out), then
#    the first push_live.sh run brings the dead-link table and the card pictures.
# AWS keeps no review data: its kssl_staging holds only staging.source_link and media (what the live API reads).
# Refuses when the server's kssl_serving already holds tables: it never overwrites a live database.
set -euo pipefail
cd "$(dirname "$0")/../.."
REF="${1:-v2}"
envval() { [ -f .env ] && sed -n "s/^$1=//p" .env | tail -1 | tr -d "\"'\r"; }
AH="${KSSL_AWS_HOST:-$(envval KSSL_AWS_HOST)}"; AU="${KSSL_AWS_USER:-ubuntu}"
VH="${KSSL_VPS_HOST:-$(envval KSSL_VPS_HOST)}"; VU="${KSSL_VPS_SSH_USER:-$(envval KSSL_VPS_SSH_USER)}"
[ -n "$AH" ] && [ -n "$VH" ] && [ -n "$VU" ] || { echo "set KSSL_AWS_HOST, KSSL_VPS_HOST, KSSL_VPS_SSH_USER"; exit 1; }
O=(-o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15)
AWS=(ssh -i "${KSSL_AWS_KEY:-$HOME/.ssh/kssl_aws.pem}" "${O[@]}" "$AU@$AH")
VPS=(ssh -i "$HOME/.ssh/kssl_vps" "${O[@]}" "$VU@$VH")

echo "== shipping $(git rev-parse --short "$REF") to AWS and starting the database"
git archive --format=tar "$REF" | gzip | "${AWS[@]}" 'set -e; cd /opt/kssl-v2 && tar -xzf - && cd deploy && docker compose up -d db'

echo "== role and databases"
"${AWS[@]}" 'bash -s' <<'REMOTE'
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
$P -d kssl_staging -c "CREATE SCHEMA IF NOT EXISTS staging; CREATE SCHEMA IF NOT EXISTS media;"
REMOTE
git show "$REF:db/setup/38_source_link.sql" | "${AWS[@]}" 'docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -U kssl_admin -d kssl_staging'

echo "== connect VPS1 to AWS"
KSSL_AWS_HOST="$AH" bash deploy/aws/link_vps1.sh

echo "== live database (VPS1 kssl_serving -> AWS)"
"${VPS[@]}" "docker exec kssl2-db pg_dump -U kssl_admin -d kssl_serving -Fc --no-owner --no-privileges \
    --exclude-table-data='activity.*' --exclude-table-data='parallax_agent.*' \
  | ssh -i /opt/kssl-v2/aws/id_aws -o BatchMode=yes -o ServerAliveInterval=15 $AU@$AH \
      'docker exec -i kssl2-db pg_restore -U kssl_admin -d kssl_serving --no-owner --no-privileges --exit-on-error'"

echo "== first push (dead links + pictures, ~460 MB)"
"${VPS[@]}" 'bash /opt/kssl-v2/aws/push_live.sh --force'

echo "init done. Next: KSSL_AWS_HOST=$AH bash deploy/aws/deploy.sh"
