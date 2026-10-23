#!/usr/bin/env bash
# One-time setup of a NEW AWS Lightsail server (Ubuntu 24.04) for KSSL. Run it ON the server, from this PC:
#   ssh -i ~/.ssh/kssl_aws.pem ubuntu@<static-ip> 'bash -s' < deploy/aws/bootstrap.sh
# Installs Docker + compose, keeps the clock on real UTC (chrony), adds 4 GB swap (the web image build needs it next to
# Postgres), creates /opt/kssl-v2 with a secrets file (random DB passwords), links the Caddy override and schedules the
# daily database backup. Safe to run twice. Prints no secret.
set -euo pipefail
sudo timedatectl set-timezone UTC
sudo apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get install -yq ca-certificates curl openssl chrony unattended-upgrades
sudo systemctl enable --now chrony
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"

if [ ! -f /swapfile ]; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

sudo mkdir -p /opt/kssl-v2/deploy /opt/kssl-v2/backups
sudo chown -R "$USER:$USER" /opt/kssl-v2
ln -sfn aws/docker-compose.override.yml /opt/kssl-v2/deploy/docker-compose.override.yml   # target arrives with the first deploy

if [ ! -f /opt/kssl-v2/deploy/.env ]; then        # secrets live only here (never in git); fill the empty ones by hand
  umask 077
  cat > /opt/kssl-v2/deploy/.env <<EOF
LIVE_HOST=
REVIEW_HOST=
POSTGRES_PASSWORD=$(openssl rand -hex 24)
APP_PASSWORD=$(openssl rand -hex 24)
REVIEW_USER=review
REVIEW_PASSWORD_HASH=
REVIEW_AUTH=
KSSL_BACKUP_BUCKET=
EOF
fi

# daily backup of both databases at 02:30 UTC (deploy/aws/backup.sh keeps 7 days on the server, + S3 when a bucket is set)
( crontab -l 2>/dev/null | grep -v '# kssl-backup' || true
  echo '30 2 * * * bash /opt/kssl-v2/deploy/aws/backup.sh >> /opt/kssl-v2/backups/backup.log 2>&1 # kssl-backup' ) | crontab -

echo "bootstrap done. Next: fill LIVE_HOST, REVIEW_HOST, REVIEW_PASSWORD_HASH in /opt/kssl-v2/deploy/.env (deploy/aws/README.md step 6)"
