#!/usr/bin/env bash
# Save /api/dataset of a running backend to fixtures/kssl_dataset.json (default: the test live backend).
#   bash scripts/snapshot_dataset.sh [url]
set -euo pipefail
cd "$(dirname "$0")/.."
URL="${1:-http://127.0.0.1:8610/api/dataset}"
mkdir -p fixtures
curl -sf "$URL" -o fixtures/kssl_dataset.json.tmp
mv fixtures/kssl_dataset.json.tmp fixtures/kssl_dataset.json
echo "wrote fixtures/kssl_dataset.json ($(wc -c < fixtures/kssl_dataset.json) bytes) from $URL"
