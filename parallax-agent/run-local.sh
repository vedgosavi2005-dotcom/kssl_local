#!/usr/bin/env bash
# Run the product AND Parallax Analyst on this machine without Docker.
#
# Needs: PostgreSQL 16 client+server binaries on PATH (Homebrew: postgresql@16),
#        Python 3.10+, Node 18+ (only if the widget has not been built).
# Everything it creates lives in parallax-agent/.local (database, Python env, logs):
# delete this folder and nothing of it remains. The product's own files are only read.
#
#   ./run-local.sh        start (idempotent)      ./stop-local.sh   stop
#   product + chatbot:    http://localhost:$AGENT_PORT  (ports: adapter/run-product.sh)
set -euo pipefail
cd "$(dirname "$0")"
HERE="$PWD"; ROOT="$(cd .. && pwd)"; LOCAL="$HERE/.local"; mkdir -p "$LOCAL"
# how this product version is created, seeded, built and started (and its ports): the adapter knows
source adapter/run-product.sh
PGPORT="${PGPORT:-5499}"; PRODUCT_PORT="${PRODUCT_PORT:-8600}"; AGENT_PORT="${AGENT_PORT:-8098}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
unset ANTHROPIC_BASE_URL || true   # never let a shell-level proxy setting redirect the agent
PY="$LOCAL/venv/bin/python"; UVICORN="$LOCAL/venv/bin/uvicorn"
PG_USER="${PG_USER:-postgres}"             # the adapter may name another superuser (e.g. kssl)
PSQL=(psql -q -h 127.0.0.1 -p "$PGPORT" -U "$PG_USER")
DSN="host=127.0.0.1 port=$PGPORT dbname=$PRODUCT_DB user=$PG_USER"

[ -f .env ] || { cp .env.example .env; echo "Created .env - add your OPENROUTER_API_KEY (or ANTHROPIC_API_KEY) and re-run."; exit 1; }

echo "1/4 database"
if ! pg_isready -q -h 127.0.0.1 -p "$PGPORT"; then
  [ -d "$LOCAL/pg" ] || initdb -D "$LOCAL/pg" -U "$PG_USER" --auth=trust -E UTF8 >/dev/null
  pg_ctl -D "$LOCAL/pg" -o "-p $PGPORT -k ''" -l "$LOCAL/pg.log" -w start >/dev/null
fi
SEED=0
if ! "${PSQL[@]}" -d postgres -tAc "select 1 from pg_database where datname='$PRODUCT_DB'" | grep -q 1; then
  "${PSQL[@]}" -d postgres -c "CREATE DATABASE $PRODUCT_DB" >/dev/null
  product_db_init
  SEED=1
fi

echo "2/4 python environment"
[ -x "$LOCAL/venv/bin/python" ] || python3 -m venv "$LOCAL/venv"
"$LOCAL/venv/bin/pip" install -q --disable-pip-version-check -r service/requirements.txt
if [ "$SEED" = 1 ]; then product_db_seed; fi

echo "3/4 chat widget and product frontend"
# the widget bundles adapter/product.json: rebuild when it is missing or the adapter changed
if [ ! -f service/static/widget.js ] || [ adapter/product.json -nt service/static/widget.js ]; then
  (cd widget && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npx vite build >/dev/null)
fi
product_dist || { echo "the product's built frontend is missing: $PRODUCT_DIST"; exit 1; }

echo "4/4 services"
stop_port() { lsof -ti tcp:"$1" -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true; }
stop_port "$PRODUCT_PORT"; stop_port "$AGENT_PORT"; [ -n "${PRODUCT_WEB_PORT:-}" ] && stop_port "$PRODUCT_WEB_PORT"; sleep 1
# the product backend, exactly as shipped (its own code, its own folder)
# (`;` not `&&` inside: only the server goes to the background, so no shell lingers holding stdout)
product_backend_start
# the agent service + gateway
(cd service || exit 1; KSSL_DSN="$DSN" PRODUCT_API="http://127.0.0.1:$PRODUCT_PORT" PRODUCT_DIST="$PRODUCT_DIST" PRODUCT_WEB="${PRODUCT_WEB:-}" nohup "$UVICORN" main:app \
   --host 127.0.0.1 --port "$AGENT_PORT" > "$LOCAL/agent.log" 2>&1 < /dev/null &)
for i in $(seq 1 40); do curl -fs -o /dev/null "http://127.0.0.1:$AGENT_PORT/api/agent/status" && break || sleep 1; done
curl -fs "http://127.0.0.1:$AGENT_PORT/api/agent/status" >/dev/null || { echo "agent service did not start - see $LOCAL/agent.log"; exit 1; }
echo
echo "Product with Parallax Analyst:  http://localhost:$AGENT_PORT"
echo "Logs: $LOCAL/agent.log  $LOCAL/product.log"
