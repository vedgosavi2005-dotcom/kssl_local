#!/usr/bin/env bash
# Run from this PC: connects VPS1 to the AWS server and (re)installs the 5-minute push (deploy/aws/push_live.sh) on VPS1.
#   KSSL_AWS_HOST=<elastic-ip> bash deploy/aws/link_vps1.sh          (safe to run again, e.g. after push_live.sh changes)
# 1. VPS1 gets its own SSH key for AWS (/opt/kssl-v2/aws/id_aws, made on VPS1, never leaves it); its public half is added to
#    the AWS server's ubuntu user. 2. push_live.sh + its settings go to /opt/kssl-v2/aws on VPS1. 3. root's crontab on VPS1
#    runs it every 5 minutes. The AWS security group must allow SSH from VPS1's IP.
set -euo pipefail
cd "$(dirname "$0")/../.."
envval() { [ -f .env ] && sed -n "s/^$1=//p" .env | tail -1 | tr -d "\"'\r"; }
AH="${KSSL_AWS_HOST:-$(envval KSSL_AWS_HOST)}"; AU="${KSSL_AWS_USER:-ubuntu}"
VH="${KSSL_VPS_HOST:-$(envval KSSL_VPS_HOST)}"; VU="${KSSL_VPS_SSH_USER:-$(envval KSSL_VPS_SSH_USER)}"
[ -n "$AH" ] && [ -n "$VH" ] && [ -n "$VU" ] || { echo "set KSSL_AWS_HOST, KSSL_VPS_HOST, KSSL_VPS_SSH_USER"; exit 1; }
O=(-o BatchMode=yes -o ConnectTimeout=20)
VPS=(ssh -i "$HOME/.ssh/kssl_vps" "${O[@]}" "$VU@$VH")
AWS=(ssh -i "${KSSL_AWS_KEY:-$HOME/.ssh/kssl_aws.pem}" "${O[@]}" "$AU@$AH")

echo "== VPS1 key for AWS"
pub=$("${VPS[@]}" 'set -e; mkdir -p /opt/kssl-v2/aws && chmod 700 /opt/kssl-v2/aws
  [ -f /opt/kssl-v2/aws/id_aws ] || ssh-keygen -q -t ed25519 -N "" -C kssl-vps1-push -f /opt/kssl-v2/aws/id_aws
  cat /opt/kssl-v2/aws/id_aws.pub')
printf '%s\n' "$pub" | "${AWS[@]}" 'k=~/.ssh/authorized_keys; read -r p; grep -qxF "$p" $k || echo "$p" >> $k'

echo "== push script + cron on VPS1"
"${VPS[@]}" 'f=/opt/kssl-v2/aws/push_live.sh; cat > $f.new && chmod 700 $f.new && mv $f.new $f' < deploy/aws/push_live.sh   # mv: a cron run mid-copy never reads a half-written script
printf 'KSSL_AWS_HOST=%s\nKSSL_AWS_USER=%s\n' "$AH" "$AU" | "${VPS[@]}" 'cat > /opt/kssl-v2/aws/push.env'
"${VPS[@]}" '( crontab -l 2>/dev/null | grep -v "# kssl-aws-push" || true
  echo "*/5 * * * * bash /opt/kssl-v2/aws/push_live.sh >> /opt/kssl-v2/aws/push.log 2>&1 # kssl-aws-push" ) | crontab -
  ssh -i /opt/kssl-v2/aws/id_aws -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new '"$AU@$AH"' "echo VPS1 reaches AWS: \$(hostname)"'
echo "linked. First push: ssh VPS1 'bash /opt/kssl-v2/aws/push_live.sh --force'"
