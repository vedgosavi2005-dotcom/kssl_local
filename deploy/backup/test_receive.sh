#!/usr/bin/env bash
# Self-check for receive.sh: the ssh guard (no prune over ssh), no overwrite, and the prune rule.  bash deploy/backup/test_receive.sh
set -euo pipefail
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cp "$(dirname "$0")/receive.sh" "$T/"; R="$T/receive.sh"; D="$T/dumps"; mkdir -p "$D"
name(){ date -u -d "$1 days ago" +kssl2-%Y%m%dT%H%MZ.tar; }

echo hello | SSH_ORIGINAL_COMMAND="put $(name 0)" bash "$R" | grep -qx "$(echo hello | sha256sum | cut -d' ' -f1)"
fail(){ echo "FAIL: $1"; exit 1; }   # (`! cmd` would not trip set -e)
echo again | SSH_ORIGINAL_COMMAND="put $(name 0)" bash "$R" 2>/dev/null && fail "overwrote a backup"
SSH_ORIGINAL_COMMAND="prune 0" bash "$R" 2>/dev/null && fail "prune ran over ssh"
echo x | SSH_ORIGINAL_COMMAND="put ../evil.tar" bash "$R" 2>/dev/null && fail "accepted a bad name"
[ "$(cat "$D/$(name 0)")" = hello ] || fail "content changed"

rm -f "$D"/*; for a in 0 1 13 15 16 30 31 60 120; do touch "$D/$(name $a)"; done
bash "$R" prune 14 13 >/dev/null
for a in 0 1 13; do [ -e "$D/$(name $a)" ]; done                                   # inside 14 days: kept
[ ! -e "$D/$(name 120)" ]                                                           # older than 13 weeks: gone
[ "$(ls "$D" | wc -l)" -le 8 ]                                                      # some weekly ones pruned or kept, never all 9
echo "receive.sh OK"
