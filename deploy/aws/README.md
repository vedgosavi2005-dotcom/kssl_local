# Deploying KSSL on AWS

This guide moves the live site and the review site from the current VPS to AWS. It uses **option A** from the AWS estimate in `backend/flood_report.py` (`AWS_OPTIONS`): one **Amazon Lightsail** server running the same Docker Compose stack the VPS runs today:

- Postgres
- live API and review API
- live site and review site
- **Caddy**, which provides HTTPS (it replaces the Traefik that the VPS host already had)

Nothing here has been deployed. The scripts were checked locally: the Compose files merge, the Caddy config validates, the shell scripts parse, and a trial restore of the live database into a fresh Postgres 16 container succeeded.

## 1. What it costs

These are AWS list prices from 22 Oct 2026 for the Mumbai region (ap-south-1). Re-check them in the Lightsail console or the AWS Pricing Calculator before you buy.

| Item | Monthly | Notes |
|---|---|---|
| Lightsail Linux, **4 GB** RAM, 2 vCPU, 80 GB SSD, 4 TB transfer, public IPv4 | **$24** (≈ $0.79/day) | Recommended. The 2 GB plan ($12) is too small once the review site and its 1.7 GB review database run too. |
| Static IP | $0 | Free while attached to the instance. |
| Automatic daily snapshots (whole-disk backup) | ~$1–3 | $0.05 per GB-month of snapshot data. |
| S3 bucket for database backups (optional) | < $0.10 | About 1 GB of dumps. |
| Route 53 hosted zone (optional) | $0.50 | Only if the DNS moves to AWS; a domain bought elsewhere can keep its DNS there. |
| **Total** | **≈ $25–28** | |

Not included above:
- **Page recordings:** these use the server's disk. They are capped at 1 GB a day under abuse; real use is a few MB per hour. The 80 GB disk covers this, but agree a retention period.
- **Model calls:** the daily routine (news, signals, prompts) keeps running on this PC with the `claude` CLI login and pushes data with `sync`. Running it on AWS would need an Anthropic API key and its own model costs. As a reference, the last flood cost about $36 for 20 cards.
- **Ask Parallax:** stays off, as on the VPS.

The other options from the estimate:
- **B. Managed** (S3 + CloudFront, ECS Fargate, ALB, RDS): about **$50/month**, roughly four times option A. AWS then handles database backups, patching and fail-over.
- **C. Static** (dataset file on S3 + CloudFront): about **$0.30/month**. It needs a code change, and the review site would have to stay on a PC or a small server.

## 2. AWS account (once)

1. **Create the account** at aws.amazon.com: company e-mail, card, phone check. Choose the free **Basic** support plan.
2. **Secure the root user:**
   - Turn on MFA for it.
   - Create an admin user in **IAM Identity Center** (or IAM), named `kssl-admin`, with AdministratorAccess and MFA.
   - From then on, sign in only as that user.
3. **Billing guard rails:** go to Billing → **Budgets** and create a monthly cost budget of **$40**, with e-mail alerts at 80% and 100%.
4. **Region:** select **Asia Pacific (Mumbai) ap-south-1** in the top bar, and use it for everything below.

## 3. The server (Lightsail console)

5. **Create the instance:**
   1. Go to Lightsail → Create instance.
   2. Choose **Linux/Unix → OS only → Ubuntu 24.04 LTS**.
   3. Choose the **$24 plan (4 GB)**.
   4. Name it `kssl-prod`.
   5. Under SSH key: **create new** → `kssl-aws` → download it.
   6. Save the key on this PC as `~/.ssh/kssl_aws.pem`. In Git Bash run `chmod 600 ~/.ssh/kssl_aws.pem`.
   7. Turn on **Automatic snapshots** (daily) on the instance's Snapshots tab.
6. **Networking:**
   - **Static IP:** create one and attach it to `kssl-prod`.
   - **Firewall (IPv4 and IPv6):**
     - **SSH 22:** allow only your office or home IP (*Restrict to IP address*).
     - **HTTP 80** and **HTTPS 443:** open to all.
     - Delete any other rule.
7. **DNS:** create two **A records** pointing at the static IP, at your domain registrar or in Route 53:
   - one for the live site (e.g. `kssl.example.com`)
   - one for the review site (e.g. `review.kssl.example.com`)

   Wait until `nslookup kssl.example.com` returns the static IP.

## 4. Install (from this PC, Git Bash, in `kssl_local`)

```bash
export KSSL_VPS_HOST=<static-ip> KSSL_VPS_SSH_USER=ubuntu KSSL_SSH_KEY=~/.ssh/kssl_aws.pem
```

8. **Prepare the server** (installs Docker and the clock sync, adds swap, creates `/opt/kssl-v2` with random database passwords, and schedules the daily backup):
   ```bash
   ssh -i $KSSL_SSH_KEY ubuntu@$KSSL_VPS_HOST 'bash -s' < deploy/aws/bootstrap.sh
   ```
9. **Fill in the secrets on the server**, which never go into git:
   ```bash
   ssh -i $KSSL_SSH_KEY ubuntu@$KSSL_VPS_HOST
   docker run --rm caddy:2.8.4 caddy hash-password --plaintext 'CHOOSE-A-REVIEW-PASSWORD'
   nano /opt/kssl-v2/deploy/.env
   ```
   - Set `LIVE_HOST` and `REVIEW_HOST` to the two DNS names.
   - Set `REVIEW_PASSWORD_HASH` to the hash printed above, in **single quotes**: `REVIEW_PASSWORD_HASH='$2a$14$...'`.
   - Keep the review password in your password manager.
10. **Copy the data**: the live database from this PC, then the review copy through the usual sync. This runs once and refuses if the server already has a live database.
    ```bash
    bash deploy/aws/init_db.sh
    ```
11. **Deploy the code**, as you do for the VPS. This builds the images, starts all containers including Caddy, applies the database setup files and grants the app role.
    ```bash
    bash deploy/deploy_vps.sh v2
    ```
    It should end with `kssl2-api 200` and `kssl2-api-review 200`.
12. **Check it:**
    - `https://<LIVE_HOST>` opens the live site with a valid certificate. Caddy fetches the certificate in the first minute.
    - `https://<REVIEW_HOST>` asks for the review user and password.
    - Optionally, run the QA suite read-only against AWS:
      1. Open a tunnel: `ssh -i $KSSL_SSH_KEY -N -L 55461:127.0.0.1:5460 ubuntu@$KSSL_VPS_HOST`.
      2. Point the database settings at it: `KSSL_QA_SERVING_DSN` / `KSSL_QA_STAGING_DSN` → `host=127.0.0.1 port=55461 user=kssl_admin ...`.
      3. Set `KSSL_QA_LIVE_API`, `KSSL_QA_LIVE_UI`, `KSSL_QA_REVIEW_UI` and `KSSL_QA_REVIEW_AUTH`.
      4. Run `python tests/qa/run_qa.py`.

## 5. Switch over

13. While AWS is being checked, keep the VPS running.
14. When AWS is right:
    1. In this PC's `.env`, set `KSSL_VPS_HOST`, `KSSL_VPS_SSH_USER=ubuntu` and `KSSL_SSH_KEY=~/.ssh/kssl_aws.pem`. From then on `deploy`, `sync` and `publish` all go to AWS.
    2. Update `KSSL_LIVE_URL` and `KSSL_REVIEW_URL` to the new names.
    3. Keep the old VPS for a week as a fallback, then stop it.

## 6. Day to day

| Task | Command (from this PC) |
|---|---|
| Ship committed code | `bash deploy/deploy_vps.sh v2` |
| Copy new review data | `bash db/sync_staging_to_vps.sh` |
| Publish review data to live | Bulk approve locally, then `bash db/publish_all.sh vps` |
| Backups | Automatic: daily `pg_dump` on the server at 02:30 UTC (7 days kept, `/opt/kssl-v2/backups`) plus daily Lightsail snapshots |

**To restore a backup:**
```bash
docker exec -i kssl2-db pg_restore -U kssl_admin -d kssl_serving --clean --if-exists < kssl_serving_<day>.dump
```
Or restore the whole disk from a Lightsail snapshot (Snapshots → *Create new instance*).

**Off-site backups (optional):**
1. Create a private S3 bucket in ap-south-1 with *Block all public access* on and a lifecycle rule that deletes objects after 30 days.
2. Create an IAM user allowed only `s3:PutObject` on that bucket.
3. On the server, install the AWS CLI and run `aws configure` with that user's keys.
4. Set `KSSL_BACKUP_BUCKET=<bucket>` in `/opt/kssl-v2/deploy/.env`.

## 7. Checklist: what to account for

- **Security:**
  - Root MFA and an admin user with MFA.
  - SSH open only to your IP.
  - The review site is behind a password.
  - The database listens only on the server itself (127.0.0.1:5460).
  - The APIs connect as `kssl_app`, not a superuser.
  - `unattended-upgrades` installs security patches.
- **Known gap:** the live site's temporary login is a page gate only, so the API answers without a login. The real login must lock the API before any confidential data goes live.
- **Clock:** the server keeps real UTC (chrony). The local Docker database once ran 5.5 hours off, so check `timedatectl` if timestamps look wrong.
- **One server = one point of failure:**
  - **Data you can lose:** up to 24 hours (daily backups).
  - **Recovery time:** about 30 minutes from a snapshot.
  - Option B buys managed fail-over for about $50/month.
- **Usage log and page recordings grow with no limit until a retention period is set.** Decide one, e.g. 90 days.
- **Model calls and the routine stay on this PC.** AWS only serves what you `sync` and `publish`.
- **Costs:** the budget alert in step 3 warns you; look at Cost Explorer after the first month.

## Files

| File | What it does |
|---|---|
| `deploy/aws/bootstrap.sh` | One-time server setup: Docker, chrony, swap, `/opt/kssl-v2`, random database passwords, backup cron. |
| `deploy/aws/init_db.sh` | One-time copy of the live database and the review copy from this PC; refuses to overwrite a live database. |
| `deploy/aws/docker-compose.override.yml`, `deploy/aws/Caddyfile` | Caddy with automatic HTTPS for both sites, and a password on the review site. |
| `deploy/aws/backup.sh` | Daily backup of both databases (cron); optional S3 copy. |
| `deploy/deploy_vps.sh`, `db/sync_staging_to_vps.sh`, `db/publish_all.sh` | The existing scripts. They work for AWS unchanged, apart from the `KSSL_SSH_KEY` setting. |
