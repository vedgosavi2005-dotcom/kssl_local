# KSSL live site on AWS (EC2)

AWS runs only the **live site**:
- its API
- a read-only copy of the live data

Everything is written in one place, **VPS1** (the current VPS):
- the review site and its Approve button
- the review data (staging) and the live data (serving)

VPS1 pushes the live data to AWS every 5 minutes.

```
 PC (Claude, loaders) --sync--> VPS1: review data -> Approve -> live data
                                  |  every 5 min (push_live.sh, cron on VPS1)
                                  |    live data + dead-link table + card pictures --> AWS
                                  |    AWS usage log (visits, recordings) <-- AWS
                                  v
                                AWS EC2 (Sydney): https://kssl.<ip-with-dashes>.sslip.io
```

- **Approvals happen on VPS1:** `sync` and Approve work as before.
- **AWS follows automatically:** within 5 minutes of an approval, AWS has the change.
- **VPS1's own live site stays up:** it runs next to AWS until you switch users over.
- **AWS holds no review data:** its `kssl_staging` database has only the two tables the live API reads:
  - `staging.source_link`: dead link → archive copy
  - `media`: card pictures

## What it costs

These are Sydney (ap-southeast-2) list prices, Oct 2026. The account is on the free plan, with $100 of credits until 23 Apr 2027.

| Item | Monthly |
|---|---|
| EC2 t4g.small (2 vCPU, 2 GB, Arm) | about $15.50 |
| 30 GB gp3 disk | about $3.60 |
| Public IPv4 / Elastic IP | about $3.65 |
| **Total** | **about $23**, about 4 months of the credits |

The AWS account is a "new experience" project. That kind of project is locked to its one region, **Sydney**, so Mumbai would need the paid plan plus "Activate advanced features".

## One-time setup

All steps run from this PC, in Git Bash, inside `kssl_local`.

0. **AWS resources**, created by session kssl-90 with the AWS tools:
   - key pair `kssl-aws`, saved as `~/.ssh/kssl_aws.pem`
   - security group `kssl-live-sg`: SSH from your IP and VPS1 only; 80/443 open to all
   - t4g.small Ubuntu 24.04 Arm instance with a 30 GB encrypted gp3 disk and IMDSv2
   - an Elastic IP
   - a $30 budget alert
1. **Set the server's address** for the steps below:
   ```bash
   export KSSL_AWS_HOST=<elastic-ip>
   ```
2. **Prepare the server.** This installs Docker, adds swap and a backup cron, and writes `.env` with random database passwords and `LIVE_HOST=kssl.<ip>.sslip.io`:
   ```bash
   ssh -i ~/.ssh/kssl_aws.pem ubuntu@$KSSL_AWS_HOST 'bash -s' < deploy/aws/bootstrap.sh
   ```
3. **Fill the data.** This:
   - creates the databases;
   - connects VPS1 to AWS: VPS1 gets its own key, and its push runs every 5 minutes from cron;
   - copies VPS1's live database straight to AWS;
   - runs the first push, including about 460 MB of pictures.

   It refuses to overwrite a live database that already has data.
   ```bash
   bash deploy/aws/init_db.sh
   ```
4. **Deploy the code.** This builds the images, then starts `db`, `api`, `web` and `caddy`, applies the setup SQL and checks health:
   ```bash
   bash deploy/aws/deploy.sh
   ```
5. **Check** `https://kssl.<ip-with-dashes>.sslip.io`. Caddy fetches its certificate in the first minute.

## Day to day

| Task | How |
|---|---|
| New review data | `bash db/sync_staging_to_vps.sh` (to VPS1, as before) |
| Publish | Approve on the VPS1 review site. AWS has it within 5 minutes. |
| Push to AWS now | `ssh VPS1 'bash /opt/kssl-v2/aws/push_live.sh --force'` |
| Push log | `ssh VPS1 tail /opt/kssl-v2/aws/push.log` |
| Ship code to AWS | `bash deploy/aws/deploy.sh` (VPS1 still uses `deploy/deploy_vps.sh`) |
| Change the push script | Edit `deploy/aws/push_live.sh`, then `bash deploy/aws/link_vps1.sh` |
| Backups on AWS | Daily `pg_dump` at 02:30 UTC, 7 days kept, in `/opt/kssl-v2/backups` (`backup.sh`). Optional S3 copy with `KSSL_BACKUP_BUCKET`. |

## How the push stays safe

- **All or nothing:** every serving and ui table is copied in one transaction, from one `pg_dump` snapshot. If anything fails, AWS keeps its previous data. The live API keeps answering during the push, and readers see either the old or the new data, never a mix.
- **Only on change:** the push runs only when VPS1's live tables or dead-link table changed. Pictures (about 460 MB) go only when the set of images differs.
- **AWS's usage log stays on AWS:** the push never touches AWS's activity tables. New AWS visits are copied to VPS1, so the review site's analytics and replays include them. VPS1 gives the copied rows new ids, and the last AWS id it pulled is stored in `/opt/kssl-v2/aws/*.last`.
- **The guard still holds:** on AWS, serving tables are still protected by the Approve-only guard. Only the push lifts it, and only for its own transaction.

## Files

| File | Runs where | What it does |
|---|---|---|
| `bootstrap.sh` | AWS, once | Docker, chrony, swap, `/opt/kssl-v2`, `.env` with an sslip.io `LIVE_HOST`, backup cron |
| `init_db.sh` | PC, once | databases, the VPS1 link, first copy from VPS1 |
| `link_vps1.sh` | PC | VPS1's key for AWS, push script and cron. Safe to re-run. |
| `push_live.sh` | VPS1, cron every 5 min | live data and pictures to AWS; AWS usage log back to VPS1 |
| `deploy.sh` | PC | `deploy/deploy_vps.sh` with `KSSL_LIVE_ONLY=1` against AWS |
| `docker-compose.override.yml`, `Caddyfile` | AWS | Caddy with HTTPS for the live site; review services switched off |
| `backup.sh` | AWS, cron daily | `pg_dump` of both databases, 7 days kept, optional S3 copy |

## Not done yet

These were agreed in principle and are not built:
- **Standby copies on VPS2 and the DC:** streaming replicas of VPS1.
- **Point-in-time backups.**
- **The real login on the API.** The live API still answers without one.
