#!/usr/bin/env bash
# Install / update the kssl2 backups from the PC (Git Bash). Idempotent: re-run after changing any file in deploy/backup.
#   bash deploy/backup/install.sh [vps2] [dc] [vps1] [standby]     default: vps2 dc vps1  (standby only when named)
#     vps2     receiver (receive.sh as the forced command of VPS1's backup key) + daily prune (14 days)
#     dc       receiver + nightly restore test (verify.sh) + prune (14 days + weekly for 13 weeks)
#     vps1     backup.sh + its key + ./receivers + root cron every 6 h, then one backup run
#     standby  replication role on VPS1 + the DC standby (tunnel + postgres), seeded once with pg_basebackup
# Hosts come from deploy/backup/.env.backup (gitignored; template backup.env.example): the repo is public.
# The DC is reached through VPS1: the PC's networks often cannot reach the DC's ssh port.
set -euo pipefail
cd "$(dirname "$0")"
. ./.env.backup
VPS2_PORT=${VPS2_PORT:-22}; VPS1_IP=${VPS1_SSH#*@}
VPS1=(ssh -i "$VPS1_KEY" -o BatchMode=yes -o ConnectTimeout=20 "$VPS1_SSH")
VPS2=(ssh -i "$VPS2_KEY" -p "$VPS2_PORT" -o BatchMode=yes -o ConnectTimeout=20 "$VPS2_SSH")
DC=(ssh -i "$DC_KEY" -p "$DC_PORT" -o BatchMode=yes -o ConnectTimeout=20
    -o ProxyCommand="ssh -i $VPS1_KEY -o BatchMode=yes -W %h:%p $VPS1_SSH" "$DC_SSH")
B1=/opt/kssl-v2/backup
send(){ local dest=$1; shift; "$@" "mkdir -p \$(dirname $dest) && cat > $dest && chmod 700 $dest"; }   # send PATH ssh... < file
cron(){ local tag=$1 line=$2; shift 2; "$@" "(crontab -l 2>/dev/null | grep -v '# $tag\$'; echo '$line # $tag') | crontab -"; }

backup_pub(){   # VPS1's backup key (made once)
  "${VPS1[@]}" "mkdir -p $B1 && { [ -f $B1/id_backup ] || ssh-keygen -q -t ed25519 -N '' -C kssl2-backup-vps1 -f $B1/id_backup; } && cat $B1/id_backup.pub"
}
receiver(){     # receiver <name> <ssh...>: receive.sh + the forced-command key line for VPS1's backup key
  local name=$1; shift; local pub; pub=$(backup_pub)
  send '~/kssl2-backup/receive.sh' "$@" < receive.sh
  "$@" "bash -s" <<EOF
set -e; mkdir -p ~/kssl2-backup/dumps; ak=~/.ssh/authorized_keys; [ -f \$ak.pre-kssl2-backup ] || cp -p \$ak \$ak.pre-kssl2-backup
{ grep -v ' kssl2-backup-vps1\$' \$ak || true; echo "command=\"\$HOME/kssl2-backup/receive.sh\",restrict,from=\"$VPS1_IP\" $pub"; } > \$ak.new
cat \$ak.new > \$ak; rm \$ak.new; echo "$name receiver ready: \$(df -h ~ | tail -1 | awk '{print \$4}') free"
EOF
}

do_vps2(){ receiver vps2 "${VPS2[@]}"; cron kssl2-backup-prune '40 3 * * * bash ~/kssl2-backup/receive.sh prune 14 0 >> ~/kssl2-backup/prune.log 2>&1' "${VPS2[@]}"; }
do_dc(){
  receiver dc "${DC[@]}"
  send '~/kssl2-backup/verify.sh' "${DC[@]}" < verify.sh
  cron kssl2-backup-verify '10 3 * * * bash ~/kssl2-backup/verify.sh >/dev/null 2>&1' "${DC[@]}"
  cron kssl2-backup-prune '40 3 * * * bash ~/kssl2-backup/receive.sh prune 14 13 >> ~/kssl2-backup/prune.log 2>&1' "${DC[@]}"
}
do_vps1(){
  backup_pub >/dev/null
  send $B1/backup.sh "${VPS1[@]}" < backup.sh
  printf 'dc   %s %s all\nvps2 %s %s 00\n' "$DC_SSH" "$DC_PORT" "$VPS2_SSH" "$VPS2_PORT" | "${VPS1[@]}" "cat > $B1/receivers"
  cron kssl2-backup "20 */6 * * * bash $B1/backup.sh >> $B1/backup.log 2>&1" "${VPS1[@]}"
  echo "== first backup run (to every receiver)"; "${VPS1[@]}" "KSSL_BACKUP_ALL=1 bash $B1/backup.sh 2>&1 | tee -a $B1/backup.log" || true
}
do_standby(){
  echo "== replication on VPS1 (role, pg_hba line, 4 GB cap on what the slot may hold; reload, no restart)"
  "${VPS1[@]}" "bash -s" <<'EOF'
set -e; B=/opt/kssl-v2/backup; [ -f $B/repl.pass ] || { openssl rand -hex 24 > $B/repl.pass; chmod 600 $B/repl.pass; }
P="docker exec -i kssl2-db psql -U kssl_admin -d postgres -v ON_ERROR_STOP=1 -q"
$P -v pw="$(cat $B/repl.pass)" <<'SQL'
DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kssl_repl') THEN CREATE ROLE kssl_repl REPLICATION LOGIN; END IF; END $$;
ALTER ROLE kssl_repl PASSWORD :'pw';
ALTER SYSTEM SET max_slot_wal_keep_size = '4GB';
SQL
docker exec kssl2-db sh -c 'f=$PGDATA/pg_hba.conf; grep -q "^host replication kssl_repl " $f || echo "host replication kssl_repl all scram-sha-256" >> $f'
$P -c "SELECT pg_reload_conf()" >/dev/null; echo "   ok"
EOF
  echo "== DC standby"
  local dcip tpub pw
  send '~/kssl2-backup/standby/docker-compose.yml' "${DC[@]}" < standby/docker-compose.yml
  tpub=$("${DC[@]}" "cd ~/kssl2-backup/standby && { [ -f tunnel_key ] || ssh-keygen -q -t ed25519 -N '' -C kssl2-dc-standby -f tunnel_key; } && chmod 644 tunnel_key && echo 'VPS1_SSH=$VPS1_SSH' > .env && cat tunnel_key.pub")
  dcip=$("${DC[@]}" "curl -s --max-time 10 https://checkip.amazonaws.com" || true)
  # the tunnel key on VPS1 root: no shell, no command (forced /bin/false), only a forward to kssl2-db, only from the DC
  local line="command=\"/bin/false\",restrict,port-forwarding,permitopen=\"127.0.0.1:5460\""
  [ -n "$dcip" ] && line="$line,from=\"$dcip\""
  "${VPS1[@]}" "bash -s" <<EOF
set -e; ak=~/.ssh/authorized_keys; [ -f \$ak.pre-kssl2-backup ] || cp -p \$ak \$ak.pre-kssl2-backup
{ grep -v ' kssl2-dc-standby\$' \$ak || true; echo '$line $tpub'; } > \$ak.new
cat \$ak.new > \$ak; rm \$ak.new
EOF
  pw=$("${VPS1[@]}" "cat $B1/repl.pass")
  "${DC[@]}" "bash -s" <<EOF
set -e; cd ~/kssl2-backup/standby
docker compose up -d tunnel && docker compose create db >/dev/null 2>&1
state=\$(docker run --rm -v kssl2-standby_data:/d alpine:3.20 sh -c 'if [ -f /d/standby.signal ]; then echo standby; elif [ -f /d/PG_VERSION ]; then echo primary; else echo empty; fi')
case \$state in
  primary) echo "   the volume holds a NON-standby database (promoted?): not touching it"; exit 1 ;;
  empty)   echo "   seeding with pg_basebackup"
           for i in \$(seq 30); do docker compose exec -T tunnel nc -z 127.0.0.1 5460 2>/dev/null && break; sleep 2; done
           docker run --rm --network kssl2-standby_default -v kssl2-standby_data:/var/lib/postgresql/data --user postgres \
             postgres:16 pg_basebackup -d "host=tunnel port=5460 user=kssl_repl password=$pw" \
             -D /var/lib/postgresql/data -R -C -S dc_standby -X stream ;;
  standby) echo "   already a standby" ;;
esac
docker compose up -d db
EOF
  echo "== check"; "${VPS1[@]}" "docker exec kssl2-db psql -U kssl_admin -d postgres -Atc \"SELECT slot_name, active FROM pg_replication_slots\""
}

for part in ${*:-vps2 dc vps1}; do echo "######## $part"; "do_$part"; done
