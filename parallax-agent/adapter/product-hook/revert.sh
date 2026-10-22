#!/usr/bin/env bash
# Undo apply.sh: restore the product's original AppState.jsx from the backup.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../../.. && pwd)"; BACKUP="$(cd ../.. && pwd)/.local/product-backup"
[ -f "$BACKUP/AppState.jsx" ] || { echo "no backup found - nothing to revert"; exit 0; }
cp "$BACKUP/AppState.jsx" "$ROOT/src/state/AppState.jsx"
echo "product restored to its original AppState.jsx"
