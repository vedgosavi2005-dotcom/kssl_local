# kssl2 backups: VPS1 → DC + VPS2

VPS1's `kssl2-db` is the only place KSSL data is written (staging + serving + the pipeline log). This folder keeps copies of it
elsewhere, in two kinds:

| Copy | Where | How fresh | Protects against |
|---|---|---|---|
| **Dated backups** (pg_dump of every database + roles, one tar) | DC: 14 days + one per week for 13 weeks · VPS2: one a day for 14 days | every 6 h (00:20, 06:20, 12:20, 18:20 UTC); VPS2 gets the 00:20 one | mistakes (a bad Approve, a dropped table), VPS1 lost |
| **Standby** (streaming replica, read-only) | DC, `127.0.0.1:5471` | seconds behind | VPS1 lost: promote it and carry on |

The standby copies mistakes instantly; the dated backups are what you go back to after one.

## How it works

- `backup.sh` (VPS1, root cron) dumps, then sends the tar to each receiver over its own key. On the receivers that key's
  forced command is `receive.sh`, which only accepts `put <new file>` and `status`: the key cannot read, overwrite or delete
  backups, so a break-in on VPS1 cannot wipe them. Each receiver echoes the stored file's sha256, which must match.
- Every run is logged in the pipeline log (`ops.run` with notes `kssl2 database backup`, its `ops.step` rows `backup.*` and
  an `ops.note` each), so it shows on the review site: dump size, each copy, the standby's lag, the DC's last restore test.
- `verify.sh` (DC, 03:10 UTC) restores the newest backup into a throwaway `postgres:16` container and checks every database
  has tables and rows. Its last line reaches the next backup run via `receive.sh status`.
- `receive.sh prune` (03:40 UTC) applies the retention on each receiver.
- The standby (`standby/docker-compose.yml`) is a `postgres:16` replica fed through an SSH tunnel container. On VPS1 the
  tunnel key has a forced `/bin/false` and may only forward to `127.0.0.1:5460`. VPS1 holds changes for it in the replication
  slot `dc_standby`, capped at 4 GB (`max_slot_wal_keep_size`): a standby that is away longer is dropped and must be re-seeded.

## Install / update

Hosts live in `deploy/backup/.env.backup` (gitignored; template `backup.env.example`). From the PC, in Git Bash:

```bash
bash deploy/backup/install.sh                 # vps2 dc vps1: receivers, crons, backup job, one first run
bash deploy/backup/install.sh standby         # replication on VPS1 + the DC standby (seeds once)
bash deploy/backup/install.sh dc              # one part only (vps2 | dc | vps1 | standby)
bash deploy/backup/test_receive.sh            # self-check of receive.sh
```

Re-running is safe. Logs: VPS1 `/opt/kssl-v2/backup/backup.log`, DC `~/kssl2-backup/verify.log` and `prune.log`.

## Restore a dated backup

```bash
tar -xf kssl2-<stamp>.tar && cd <stamp> && sha256sum -c SHA256SUMS
createdb kssl_serving_restored && pg_restore -d kssl_serving_restored --no-owner -j 4 kssl_serving.dump   # same for kssl_staging
```

To put it back on VPS1, take a fresh backup first (`bash /opt/kssl-v2/backup/backup.sh`), then restore into the real
database names inside `kssl2-db`. Serving only changes through Approve: a restore into `kssl_serving` needs the approve
flag on its session, like `push_live.sh`: `PGOPTIONS="-c kssl.approve=on" pg_restore ...`.

## Switchover: VPS1 is gone, the DC standby takes over

1. Check the standby is current: `docker exec kssl2-standby-db-1 psql -U kssl_admin -d postgres -c "SELECT pg_last_xact_replay_timestamp()"`.
2. Stop the tunnel so nothing reconnects to the old VPS1: `cd ~/kssl2-backup/standby && docker compose stop tunnel`.
3. Promote: `docker exec kssl2-standby-db-1 psql -U kssl_admin -d postgres -c "SELECT pg_promote()"`. It is now a normal,
   writable database. `install.sh standby` refuses to touch a promoted volume.
4. Point the live copy at it: AWS is fed by `push_live.sh`, which runs on VPS1. Run it from the DC (or a new VPS1 restored
   from the standby) with `/opt/kssl-v2/aws/push.env` and the AWS key, or rebuild VPS1 from a dump and run
   `deploy/aws/link_vps1.sh` again.
5. When VPS1 is back: rebuild it from the promoted database (pg_dump → restore), make it the writer again, then re-seed the
   standby: on the DC `docker compose down` + `docker volume rm kssl2-standby_data`, on VPS1
   `SELECT pg_drop_replication_slot('dc_standby')`, then `bash deploy/backup/install.sh standby`.
