#!/usr/bin/env bash
set -euo pipefail

TVBOX_HOST="${TVBOX_HOST:-192.168.1.8}"
TVBOX_USER="${TVBOX_USER:-root}"
AN3_ADMIN_NAME="${AN3_ADMIN_NAME:-an3admin}"
AN3_ADMIN_PASSWORD="${AN3_ADMIN_PASSWORD:-}"
PRODUCTION_HEALTH_URL="${PRODUCTION_HEALTH_URL:-http://${TVBOX_HOST}:8091/health}"

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="$(mktemp -t an3-arcade.XXXXXX.tgz)"
REMOTE_ARCHIVE="/tmp/an3-arcade-deploy-$$.tgz"
trap 'rm -f "$ARCHIVE"' EXIT

COPYFILE_DISABLE=1 tar -czf "$ARCHIVE" -C "$PACKAGE_DIR" app.py static deploy README.md
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$ARCHIVE" "$TVBOX_USER@$TVBOX_HOST:$REMOTE_ARCHIVE"

ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$TVBOX_USER@$TVBOX_HOST" bash -s -- "$REMOTE_ARCHIVE" "$AN3_ADMIN_NAME" "$AN3_ADMIN_PASSWORD" "$PRODUCTION_HEALTH_URL" <<'REMOTE'
set -euo pipefail
archive="$1"
admin_name="$2"
admin_password="${3:-}"
health_url="$4"
tmp="$(mktemp -d /tmp/an3-install.XXXXXX)"
trap 'rm -rf "$tmp" "$archive"' EXIT
tar -xzf "$archive" -C "$tmp"

stamp="$(date +%Y%m%d-%H%M%S)"
if [ -d /opt/an3-arcade ]; then
  install -d -m 0700 /opt/an3-arcade-backups
  cp -a /opt/an3-arcade "/opt/an3-arcade-backups/$stamp"
fi

install -d -m 0755 /opt/an3-arcade /opt/an3-arcade/static
install -m 0755 "$tmp/app.py" /opt/an3-arcade/app.py
cp -a "$tmp/static/." /opt/an3-arcade/static/
find /opt/an3-arcade/static -type f -name '._*' -delete
find /opt/an3-arcade/static -type d -exec chmod 0755 {} +
find /opt/an3-arcade/static -type f -exec chmod 0644 {} +
install -d -o tvshare -g tvshare -m 0750 /srv/an3-arcade

if [ -f /srv/an3-arcade/arcade.db ]; then
  install -d -m 0750 /srv/an3-arcade/backups
  python3 -c 'import sqlite3,sys; source=sqlite3.connect(sys.argv[1]); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()' \
    /srv/an3-arcade/arcade.db "/srv/an3-arcade/backups/arcade-predeploy-$stamp.db"
fi

if [ ! -f /etc/an3-arcade.env ]; then
  [ -n "$admin_password" ] || { echo 'AN3_ADMIN_PASSWORD is required for the first deployment' >&2; exit 1; }
  umask 077
  printf '%s\n' \
    'AN3_APP_DIR=/opt/an3-arcade' \
    'AN3_DATA_DIR=/srv/an3-arcade' \
    'AN3_HOST=0.0.0.0' \
    'AN3_PORT=8091' \
    'AN3_BASE_URL=http://192.168.1.11:8091' \
    "AN3_ADMIN_NAME=$admin_name" \
    "AN3_ADMIN_PASSWORD=$admin_password" \
    'AN3_COOKIE_SECURE=0' > /etc/an3-arcade.env
fi

install -m 0644 "$tmp/deploy/an3-arcade.service" /etc/systemd/system/an3-arcade.service
install -D -m 0750 "$tmp/deploy/an3-arcade-backup.sh" /usr/local/libexec/an3-arcade-backup
install -m 0644 "$tmp/deploy/an3-arcade-backup.service" /etc/systemd/system/an3-arcade-backup.service
install -m 0644 "$tmp/deploy/an3-arcade-backup.timer" /etc/systemd/system/an3-arcade-backup.timer
systemctl daemon-reload
systemctl enable an3-arcade.service
systemctl enable --now an3-arcade-backup.timer
systemctl restart an3-arcade.service

for _ in $(seq 1 30); do
  if curl -fsS "$health_url"; then
    echo
    systemctl is-active an3-arcade.service
    exit 0
  fi
  sleep 2
done

systemctl status an3-arcade.service --no-pager -l
exit 1
REMOTE
