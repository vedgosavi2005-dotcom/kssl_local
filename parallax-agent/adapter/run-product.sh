# Sourced by ../run-local.sh and ../stop-local.sh: how to create, seed, build and start THIS
# version of the product (KSSL_Deploy v2) on this machine. Paths are relative to the repo root
# ($ROOT, the folder that holds parallax-agent/). Available: $ROOT $LOCAL $PGPORT $PRODUCT_PORT
# $DSN $PY $UVICORN and the PSQL array. The product's own files are only read: its frontend is
# built in a scratch copy under .local/, never at the repo root.
#
# Locally this runs the repo's fictional test pair (db/make_test_pair.sh --approve-all:
# kssl_test_staging + kssl_test_serving, every name "(TEST)"). The chatbot reads the LIVE
# database (serving + ui schemas), as the product's live UI does. To point it at a real
# kssl_serving, set KSSL_DSN to it instead (the analytics views and the read-only role are
# created there on startup).

# ports for this copy (5699 / 8710 / 8298): the repo reserves 8610 / 8611 for its own test backends
PGPORT="${PGPORT:-5699}"; PRODUCT_PORT="${PRODUCT_PORT:-8710}"; AGENT_PORT="${AGENT_PORT:-8298}"
# the product's web server (vite preview, as its deploy runs it) answers /api/img and /api/pulse
PRODUCT_WEB_PORT="${PRODUCT_WEB_PORT:-5779}"; PRODUCT_WEB="http://127.0.0.1:$PRODUCT_WEB_PORT"

PRODUCT_DB=kssl_test_serving                     # the live (serving) database the UI reads
PG_USER=kssl                                     # the repo's scripts connect as kssl
PRODUCT_DIST="$LOCAL/product-web/dist"           # the product's built frontend (served with the widget added)

# The repo's db/make_*.sh run psql through `docker exec kssl-pg`; without Docker, a stand-in
# runs the same psql against the local cluster in .local/pg.
_docker_shim() {
  mkdir -p "$LOCAL/bin"
  cat > "$LOCAL/bin/docker" <<'SHIM'
#!/usr/bin/env bash
# stand-in for `docker exec [-i] [-e K=V] kssl-pg <cmd...>`: runs <cmd> against the local cluster
[ "$1" = exec ] || { echo "docker shim: only 'exec' is supported" >&2; exit 1; }
shift
while [ $# -gt 0 ]; do case "$1" in -i|-t|-it|-ti) shift;; -e) export "$2"; shift 2;; kssl-pg) shift; break;; *) shift;; esac; done
export PGHOST="${PGHOST:-127.0.0.1}" PGPORT="${KSSL_LOCAL_PGPORT:-5699}"
exec "$@"
SHIM
  chmod +x "$LOCAL/bin/docker"
}

product_db_init() {                              # both test databases, the repo's own way
  _docker_shim
  (cd "$ROOT" && PATH="$LOCAL/bin:$PATH" KSSL_LOCAL_PGPORT="$PGPORT" bash db/make_test_pair.sh --approve-all >"$LOCAL/db-init.log" 2>&1) \
    || { echo "db/make_test_pair.sh failed - see $LOCAL/db-init.log"; return 1; }
  # The fictional seed never marks a competitor as qualifying, so the live UI (which shows only
  # qualifying competitors) would show none. In this throwaway test database only, mark them
  # qualifying through the product's own approval switch, as Approve would.
  "${PSQL[@]}" -d "$PRODUCT_DB" -v ON_ERROR_STOP=1 -c "BEGIN; SET LOCAL kssl.approve = 'on';
    UPDATE serving.competitive_competitor SET qualifies = true,
      qualification_reason = coalesce(qualification_reason, 'test seed: shown for local testing') WHERE qualifies IS NOT TRUE;
    COMMIT;" >/dev/null
}

product_db_seed() { :; }                         # make_test_pair.sh seeds and approves the fictional data

product_dist() {                                 # build the repo-root frontend in .local/product-web when missing or older than the source
  local web="$LOCAL/product-web"
  if [ -f "$PRODUCT_DIST/index.html" ] && [ -z "$(find "$ROOT/src" "$ROOT/index.html" "$ROOT/vite.config.js" -newer "$PRODUCT_DIST/index.html" -print -quit)" ]; then
    return 0
  fi
  mkdir -p "$web"
  rsync -a --delete "$ROOT/src" "$ROOT/index.html" "$ROOT/vite.config.js" "$ROOT/package.json" "$ROOT/package-lock.json" "$web/"
  [ -d "$ROOT/public" ] && rsync -a --delete "$ROOT/public" "$web/"
  (cd "$web" && { [ -d node_modules ] || npm ci --no-audit --no-fund --silent; } && npx vite build >/dev/null 2>&1)
  [ -f "$PRODUCT_DIST/index.html" ]
}

product_backend_start() {                        # the product API on $PRODUCT_PORT and its web server, exactly as shipped (live view)
  (cd "$ROOT" || exit 1; PYTHONDONTWRITEBYTECODE=1 KSSL_DSN="$DSN" nohup "$UVICORN" backend.app:app \
     --host 127.0.0.1 --port "$PRODUCT_PORT" > "$LOCAL/product.log" 2>&1 < /dev/null &)
  (cd "$LOCAL/product-web" || exit 1; KSSL_API_TARGET="http://127.0.0.1:$PRODUCT_PORT" nohup npx vite preview \
     --host 127.0.0.1 --port "$PRODUCT_WEB_PORT" --strictPort > "$LOCAL/product-web.log" 2>&1 < /dev/null &)
}
