#!/usr/bin/env bash
# Ship committed code to the AWS live server: deploy/deploy_vps.sh in live-only mode (no review site there).
#   KSSL_AWS_HOST=<elastic-ip> bash deploy/aws/deploy.sh [git-ref]        (or KSSL_AWS_HOST in .env)
set -euo pipefail
cd "$(dirname "$0")/../.."
envval() { [ -f .env ] && sed -n "s/^$1=//p" .env | tail -1 | tr -d "\"'\r"; }
AH="${KSSL_AWS_HOST:-$(envval KSSL_AWS_HOST)}"
[ -n "$AH" ] || { echo "set KSSL_AWS_HOST"; exit 1; }
KSSL_LIVE_ONLY=1 KSSL_VPS_HOST="$AH" KSSL_VPS_SSH_USER="${KSSL_AWS_USER:-ubuntu}" \
  KSSL_SSH_KEY="${KSSL_AWS_KEY:-$HOME/.ssh/kssl_aws.pem}" bash deploy/deploy_vps.sh "$@"
