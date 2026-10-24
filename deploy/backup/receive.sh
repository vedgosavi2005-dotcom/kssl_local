#!/usr/bin/env bash
# Backup receiver on the DC and VPS2 (installed by deploy/backup/install.sh into ~/kssl2-backup).
# It is the FORCED COMMAND of VPS1's backup key, so over ssh that key can only:
#   put <kssl2-YYYYmmddTHHMMZ.tar>   store stdin as a NEW file (never overwrites, max 20 GB), print its sha256
#   status                            print the newest 3 backups and the last restore test line (verify.log)
# It can never read, list beyond that, overwrite or delete a backup: a break-in on VPS1 cannot wipe the copies.
# Run locally (cron), never over ssh:
#   receive.sh prune <days> [weeks]   keep every backup of the last <days> days + the newest of each ISO week for <weeks> weeks
set -euo pipefail
H="$(cd "$(dirname "$0")" && pwd)"; D="$H/dumps"; mkdir -p "$D"
NAME_RE='^kssl2-[0-9]{8}T[0-9]{4}Z\.tar$'

if [ -n "${SSH_ORIGINAL_COMMAND+x}" ]; then
  set -- $SSH_ORIGINAL_COMMAND
  case "${1:-}" in put|status) ;; *) echo "only put / status over ssh" >&2; exit 2 ;; esac
fi

case "${1:-}" in
  put)
    [[ "${2:-}" =~ $NAME_RE ]] || { echo "bad name" >&2; exit 2; }
    [ ! -e "$D/$2" ] || { echo "exists" >&2; exit 3; }
    head -c 21474836480 > "$D/.$2.part"
    mv "$D/.$2.part" "$D/$2"
    sha256sum "$D/$2" | cut -d' ' -f1 ;;
  status)
    ls -1t "$D" | grep -E "$NAME_RE" | head -3 || true
    tail -1 "$H/verify.log" 2>/dev/null || echo "no restore test yet" ;;
  prune)
    days=${2:?days}; weeks=${3:-0}; now=$(date -u +%s); declare -A kept_week=()
    for f in $(ls -1 "$D" | grep -E "$NAME_RE" | sort -r); do            # newest first
      t=$(date -u -d "${f:6:8} ${f:15:2}:${f:17:2}" +%s); age=$(( (now - t) / 86400 )); w=$(date -u -d "@$t" +%G%V)
      if (( age < days )); then kept_week[$w]=1; continue; fi
      if (( age < weeks * 7 )) && [ -z "${kept_week[$w]:-}" ]; then kept_week[$w]=1; continue; fi
      rm -f "$D/$f"; echo "$(date -u +%FT%TZ) pruned $f"
    done ;;
  *) echo "usage: receive.sh put NAME | status | prune DAYS [WEEKS]" >&2; exit 2 ;;
esac
