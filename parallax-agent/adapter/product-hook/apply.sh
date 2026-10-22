#!/usr/bin/env bash
# OPTIONAL: add the 7-line add-on hook to the product (see AppState.patch). The chatbot works
# without it (it falls back to reading React internals); the hook makes navigation
# independent of the product's internals. The original is backed up under
# parallax-agent/.local/product-backup; ./revert.sh restores it byte for byte. In this
# product version the frontend is built by run-local.sh into .local/product-web, which
# rebuilds when the source changes, so nothing else is touched.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../../.. && pwd)"; BACKUP="$(cd ../.. && pwd)/.local/product-backup"
F="$ROOT/src/state/AppState.jsx"
if grep -q "__parallaxApp" "$F"; then echo "hook already applied"; exit 0; fi
mkdir -p "$BACKUP" && cp "$F" "$BACKUP/AppState.jsx"
(cd "$ROOT" && patch -p1 --forward < "$OLDPWD/AppState.patch")
echo "hook applied (revert with ./revert.sh); restart with ../../run-local.sh to rebuild the frontend"
