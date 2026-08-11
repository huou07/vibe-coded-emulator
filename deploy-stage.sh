#!/usr/bin/env bash
set -euo pipefail

# Deploy the current source tree to the isolated staging service. The target
# needs /etc/an3-arcade-staging.env before the first deployment.
TVBOX_HOST="${TVBOX_HOST:-192.168.1.11}"
TVBOX_USER="${TVBOX_USER:-root}"
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="$(mktemp -t an3-arcade-stage.XXXXXX.tgz)"
REMOTE_ARCHIVE="/tmp/an3-arcade-stage-$$.tgz"
trap 'rm -f "$ARCHIVE"' EXIT

tar -czf "$ARCHIVE" -C "$PACKAGE_DIR" app.py static deploy README.md
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$ARCHIVE" "$TVBOX_USER@$TVBOX_HOST:$REMOTE_ARCHIVE"

ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$TVBOX_USER@$TVBOX_HOST" bash -s -- "$REMOTE_ARCHIVE" <<'REMOTE'
set -euo pipefail
archive="$1"
root=/opt/an3-arcade-staging
releases="$root/releases"
tmp="$(mktemp -d /tmp/an3-stage-install.XXXXXX)"
trap 'rm -rf "$tmp" "$archive"' EXIT

test -f /etc/an3-arcade-staging.env || { echo 'Missing /etc/an3-arcade-staging.env' >&2; exit 1; }
tar -xzf "$archive" -C "$tmp"
stamp="$(date +%Y%m%d-%H%M%S)"
release="$releases/$stamp"
previous="$(readlink -f "$root/current" 2>/dev/null || true)"

install -d -m 0755 "$release" /srv/an3-arcade-staging
cp -a "$tmp/app.py" "$tmp/static" "$tmp/deploy" "$tmp/README.md" "$release/"
find "$release" -type d -exec chmod 0755 {} +
find "$release" -type f -exec chmod 0644 {} +
install -m 0644 "$release/deploy/an3-arcade-staging.service" /etc/systemd/system/an3-arcade-staging.service
chown -R tvshare:tvshare /srv/an3-arcade-staging
ln -sfn "$release" "$root/current"
systemctl daemon-reload
systemctl enable an3-arcade-staging.service
systemctl restart an3-arcade-staging.service

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8092/health | grep -q '"environment": "staging"'; then
    systemctl is-active an3-arcade-staging.service
    exit 0
  fi
  sleep 1
done

if [ -n "$previous" ]; then
  ln -sfn "$previous" "$root/current"
  systemctl restart an3-arcade-staging.service || true
fi
systemctl status an3-arcade-staging.service --no-pager -l
exit 1
REMOTE
