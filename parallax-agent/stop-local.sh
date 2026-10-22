#!/usr/bin/env bash
# Stop what run-local.sh started.
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"; LOCAL="$PWD/.local"
source adapter/run-product.sh
for p in "${AGENT_PORT:-8098}" "${PRODUCT_PORT:-8600}" ${PRODUCT_WEB_PORT:-}; do lsof -ti tcp:"$p" -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true; done
[ -d .local/pg ] && pg_ctl -D .local/pg -m fast stop >/dev/null 2>&1 || true
echo stopped
