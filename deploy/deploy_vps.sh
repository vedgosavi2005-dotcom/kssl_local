#!/usr/bin/env bash
# Deploy a committed ref (default v2) to the VPS (compose project kssl2 in /opt/kssl-v2) and bring the
# VPS serving schema up to date.   bash deploy/deploy_vps.sh [git-ref]
#   1. ships `git archive <ref>` (committed files only -- never the working tree) to /opt/kssl-v2.
#      backend/ src/ public/ are replaced whole (no stale files); everything else is overwritten in place,
#      so untracked files on the VPS (.env secrets) are kept.
#   2. docker compose build + up -d in /opt/kssl-v2/deploy
#   3. applies the idempotent setup SQL to kssl_serving (staging tables arrive with db/sync_staging_to_vps.sh)
#      and grants the app role access to every table.
# Secrets stay on the VPS; nothing here prints them.
set -euo pipefail
cd "$(dirname "$0")/.."
REF="${1:-v2}"
ENV_FILE="$(dirname "$0")/../.env"
envval() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | tr -d "\"'\r"; }
VPS_HOST="${KSSL_VPS_HOST:-$(envval KSSL_VPS_HOST)}"      # host and user live in the gitignored .env (the repo is public)
VPS_USER="${KSSL_VPS_SSH_USER:-$(envval KSSL_VPS_SSH_USER)}"
[ -n "$VPS_HOST" ] && [ -n "$VPS_USER" ] || { echo "set KSSL_VPS_HOST and KSSL_VPS_SSH_USER in .env"; exit 1; }
SSH=(ssh -i "$HOME/.ssh/kssl_vps" -o ConnectTimeout=20 -o BatchMode=yes "$VPS_USER@$VPS_HOST")
PSQL_VPS="docker exec -i kssl2-db psql -v ON_ERROR_STOP=1 -q -U kssl_admin"

echo "== shipping $(git rev-parse --short "$REF") ($REF)"
git archive --format=tar "$REF" | gzip | "${SSH[@]}" \
  'set -e; cd /opt/kssl-v2 && rm -rf backend src public && tar -xzf - && echo "   unpacked"'

echo "== build + up"
"${SSH[@]}" 'cd /opt/kssl-v2/deploy && docker compose build -q && docker compose up -d &&
  docker ps --format "{{.Names}} {{.Status}}" | grep kssl2'

echo "== serving schema"
# the SQL comes from the SAME committed ref as the code (never the working tree): a file not committed in $REF is skipped
for f in db/setup/08_competitor_text_columns.sql db/setup/11_foundations.sql db/setup/09_ui_port_tables.sql db/setup/15_signal_published_date.sql db/setup/21_fx_rate.sql db/setup/16_signal_rule_s2.sql db/setup/18_tender_notice_merge.sql db/setup/20_matchup_advantage_kind.sql db/setup/22_product_description_status.sql; do
  if git cat-file -e "$REF:$f" 2>/dev/null; then echo "   $f"; git show "$REF:$f" | "${SSH[@]}" "$PSQL_VPS -d kssl_serving"; else echo "   skip $f (not committed in $REF)"; fi
done
for db in kssl_serving kssl_staging; do
  "${SSH[@]}" "$PSQL_VPS -d $db" <<'SQL'
DO $$ DECLARE s text; BEGIN
  FOR s IN SELECT nspname FROM pg_namespace WHERE nspname IN ('ui','serving','staging','staging_ui') LOOP
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO kssl_app', s);
    EXECUTE format('GRANT ALL ON ALL TABLES IN SCHEMA %I TO kssl_app', s);
    EXECUTE format('GRANT ALL ON ALL SEQUENCES IN SCHEMA %I TO kssl_app', s);
  END LOOP; END $$;
SQL
done

echo "== health"
"${SSH[@]}" 'for c in kssl2-api kssl2-api-review; do
  docker exec $c python -c "import urllib.request,sys; print(sys.argv[1], urllib.request.urlopen(\"http://127.0.0.1:8600/api/health\").status)" $c; done'
