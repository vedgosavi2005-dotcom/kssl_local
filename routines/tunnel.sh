#!/usr/bin/env bash
# SSH tunnel to the VPS database: local port 55460 -> the VPS's 127.0.0.1:5460 (kssl2-db).
#   bash routines/tunnel.sh        keep this window open while you work; Ctrl+C closes the tunnel
# Host and user come from the gitignored .env (KSSL_VPS_HOST, KSSL_VPS_SSH_USER) or the environment.
ENV_FILE="$(dirname "$0")/../.env"
envval() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | tr -d "\"'\r"; }
HOST="${KSSL_VPS_HOST:-$(envval KSSL_VPS_HOST)}"
SSH_USER="${KSSL_VPS_SSH_USER:-$(envval KSSL_VPS_SSH_USER)}"
[ -n "$HOST" ] && [ -n "$SSH_USER" ] || { echo "set KSSL_VPS_HOST and KSSL_VPS_SSH_USER in .env (see routines/SETUP.md)"; exit 1; }
KEY="$HOME/.ssh/kssl_vps"
LOCAL_PORT=55460
REMOTE=127.0.0.1:5460

up() { (echo > "/dev/tcp/127.0.0.1/$LOCAL_PORT") 2>/dev/null; }

[ -f "$KEY" ] || { echo "ssh key not found: $KEY (see routines/SETUP.md)"; exit 1; }
if up; then echo "port $LOCAL_PORT is already open - a tunnel (or something else) is running. Nothing to do."; exit 0; fi

ssh -i "$KEY" -N -L "$LOCAL_PORT:$REMOTE" -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
    -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" &
pid=$!
trap 'kill $pid 2>/dev/null; echo "tunnel closed"' EXIT INT TERM

for _ in $(seq 1 20); do
    up && break
    kill -0 $pid 2>/dev/null || { echo "ssh stopped - check the key and the network"; exit 1; }
    sleep 1
done
up || { echo "port $LOCAL_PORT did not open"; exit 1; }
echo "tunnel open: localhost:$LOCAL_PORT -> $HOST ($REMOTE).  Keep this window open; Ctrl+C (or close it) to stop."
wait $pid
