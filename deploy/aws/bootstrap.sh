#!/usr/bin/env bash
# One-time setup of a NEW AWS EC2 live server (Ubuntu 24.04) for KSSL. Run it ON the server, from this PC:
#   ssh -i ~/.ssh/kssl_aws.pem ubuntu@<elastic-ip> 'bash -s' < deploy/aws/bootstrap.sh
# Installs Docker + compose, keeps the clock on real UTC (chrony), adds 4 GB swap (the web image build needs it next to
# Postgres on a 2 GB t4g.small), creates /opt/kssl-v2 with a secrets file (random DB passwords; LIVE_HOST = the free sslip.io
# name of this server's public IP), links the Caddy override and schedules the daily database backup. Safe to run twice.
# Prints no secret.
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

if [ ! -f /opt/kssl-v2/deploy/.env ]; then        # secrets live only here (never in git)
  tok=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/meta-data/public-ipv4)   # the Elastic IP
  umask 077
  cat > /opt/kssl-v2/deploy/.env <<EOF
LIVE_HOST=kssl.${ip//./-}.sslip.io
POSTGRES_PASSWORD=$(openssl rand -hex 24)
APP_PASSWORD=$(openssl rand -hex 24)
KSSL_BACKUP_BUCKET=
EOF
fi

# daily backup of both databases at 02:30 UTC (deploy/aws/backup.sh keeps 7 days on the server, + S3 when a bucket is set)
( crontab -l 2>/dev/null | grep -v '# kssl-backup' || true
  echo '30 2 * * * bash /opt/kssl-v2/deploy/aws/backup.sh >> /opt/kssl-v2/backups/backup.log 2>&1 # kssl-backup' ) | crontab -

echo "bootstrap done: the live site will be https://$(sed -n 's/^LIVE_HOST=//p' /opt/kssl-v2/deploy/.env). Next: deploy/aws/init_db.sh from the PC"
