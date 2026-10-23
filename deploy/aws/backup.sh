#!/usr/bin/env bash
# Daily backup of both databases, run by cron on the server (set up by deploy/aws/bootstrap.sh). Keeps 7 days in
# /opt/kssl-v2/backups; also copies to S3 when KSSL_BACKUP_BUCKET is set in deploy/.env and the AWS CLI is configured.
set -euo pipefail
dir=/opt/kssl-v2/backups
day=$(date -u +%Y%m%d)
for db in kssl_serving kssl_staging; do
  docker exec kssl2-db pg_dump -U kssl_admin -d "$db" -Fc > "$dir/${db}_$day.dump.part"
  mv "$dir/${db}_$day.dump.part" "$dir/${db}_$day.dump"        # a half-written dump never looks like a good one
done
find "$dir" -name 'kssl_*.dump' -mtime +7 -delete
bucket=$(sed -n 's/^KSSL_BACKUP_BUCKET=//p' /opt/kssl-v2/deploy/.env | tr -d "\"'\r")
if [ -n "$bucket" ]; then
  for db in kssl_serving kssl_staging; do aws s3 cp --only-show-errors "$dir/${db}_$day.dump" "s3://$bucket/$day/"; done
fi
echo "$(date -u +%FT%TZ) backup ok"
