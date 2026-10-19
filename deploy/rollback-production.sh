#!/usr/bin/env bash
set -euo pipefail

# Restore a retained production application snapshot. This is intentionally a
# code/static rollback only: SQLite and user ROM data remain untouched.

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "$(id -u)" -ne 0 ]]; then
  die 'Run this production rollback helper as root.'
fi
if [[ "$#" -ne 1 ]]; then
  printf 'usage: an3-arcade-rollback-production /opt/an3-arcade-backups/YYYYMMDD-HHMMSS\n' >&2
  exit 2
fi

APP_ROOT=/opt/an3-arcade
APP_BACKUPS=/opt/an3-arcade-backups
FAILED_RELEASES=/opt/an3-arcade-failed-releases
DATA_ROOT=/srv/an3-arcade
UNIT=an3-arcade.service
HEALTH_URL=http://127.0.0.1:8091/health
TARGET="$1"

[[ "$TARGET" = "$APP_BACKUPS"/* ]] || die 'Rollback target must be inside /opt/an3-arcade-backups.'
[[ "$(dirname "$TARGET")" == "$APP_BACKUPS" ]] || die 'Rollback target must be directly inside /opt/an3-arcade-backups.'
STAMP="$(basename "$TARGET")"
[[ "$STAMP" =~ ^[0-9]{8}-[0-9]{6}$ ]] || die 'Rollback target must use the retained YYYYMMDD-HHMMSS snapshot name.'
[[ -d "$TARGET" && ! -L "$TARGET" ]] || die 'Rollback target is missing or unsafe.'
[[ -f "$TARGET/app.py" && -d "$TARGET/static" && -f "$TARGET/deploy/an3-arcade.service" ]] || die 'Rollback target has an unexpected application layout.'
[[ -d "$APP_ROOT" && ! -L "$APP_ROOT" ]] || die 'Current application root is missing or unsafe.'
[[ -d "$DATA_ROOT" && ! -L "$DATA_ROOT" ]] || die 'Production data root is missing or unsafe.'

FAILED="$FAILED_RELEASES/${STAMP}-$(date +%Y%m%d-%H%M%S)"
[[ ! -e "$FAILED" && ! -L "$FAILED" ]] || die 'Refusing to overwrite an existing failed-release record.'
NEXT="${APP_ROOT}.rollback-next-${STAMP}-$(date +%Y%m%d-%H%M%S)"
[[ ! -e "$NEXT" && ! -L "$NEXT" ]] || die 'Refusing to overwrite a pending rollback tree.'
install -d -m 0700 "$FAILED_RELEASES"

# Copy and validate first so an unreadable snapshot cannot take the current
# service offline. The pending tree is intentionally retained for inspection
# if copying fails; this helper never deletes rollback evidence.
cp -a -- "$TARGET" "$NEXT"
[[ -f "$NEXT/app.py" && -d "$NEXT/static" && -f "$NEXT/deploy/an3-arcade.service" ]] || die 'Copied rollback tree has an unexpected layout.'

systemctl stop "$UNIT"
mv -- "$APP_ROOT" "$FAILED"
mv -- "$NEXT" "$APP_ROOT"

install -o root -g root -m 0644 "$APP_ROOT/deploy/an3-arcade.service" /etc/systemd/system/an3-arcade.service
install -o root -g tvshare -m 0750 "$APP_ROOT/deploy/an3-arcade-backup.sh" /usr/local/libexec/an3-arcade-backup
install -o root -g root -m 0644 "$APP_ROOT/deploy/an3-arcade-backup.service" /etc/systemd/system/an3-arcade-backup.service
install -o root -g root -m 0644 "$APP_ROOT/deploy/an3-arcade-backup.timer" /etc/systemd/system/an3-arcade-backup.timer
install -o root -g root -m 0755 "$APP_ROOT/deploy/an3-arcade-health.sh" /usr/local/sbin/an3-arcade-health
install -o root -g root -m 0755 "$APP_ROOT/deploy/an3-arcade-turbostat.sh" /usr/local/libexec/an3-arcade-turbostat
install -o root -g root -m 0440 "$APP_ROOT/deploy/an3-arcade-turbostat.sudoers" /etc/sudoers.d/an3-arcade-turbostat
if [[ -f "$APP_ROOT/deploy/backup-production-current.sh" ]]; then
  install -o root -g root -m 0755 "$APP_ROOT/deploy/backup-production-current.sh" /usr/local/sbin/an3-arcade-backup-current
fi
if [[ -f "$APP_ROOT/deploy/rollback-production.sh" ]]; then
  install -o root -g root -m 0755 "$APP_ROOT/deploy/rollback-production.sh" /usr/local/sbin/an3-arcade-rollback-production
fi
if [[ -f "$APP_ROOT/deploy/rollback-azahar-core.sh" ]]; then
  install -o root -g root -m 0755 "$APP_ROOT/deploy/rollback-azahar-core.sh" /usr/local/sbin/an3-arcade-rollback-azahar-core
fi
if [[ -f "$APP_ROOT/deploy/retire-production-rom-library.sh" ]]; then
  install -o root -g root -m 0755 "$APP_ROOT/deploy/retire-production-rom-library.sh" /usr/local/sbin/an3-arcade-retire-rom-library
fi
visudo -cf /etc/sudoers.d/an3-arcade-turbostat >/dev/null

systemctl daemon-reload
systemctl enable "$UNIT"
systemctl enable --now an3-arcade-backup.timer
systemctl restart "$UNIT"

for attempt in $(seq 1 30); do
  HEALTH="$(curl --fail --silent --show-error --connect-timeout 3 "$HEALTH_URL" || true)"
  if [[ "$HEALTH" == *'"environment": "production"'* ]]; then
    ASSET="$(sed -n 's/.*"asset_version": "\([a-f0-9]*\)".*/\1/p' <<<"$HEALTH")"
    printf 'PRODUCTION_ROLLBACK=PASS\n'
    printf 'PRODUCTION_ROLLBACK_TARGET=%s\n' "$TARGET"
    printf 'PRODUCTION_FAILED_RELEASE=%s\n' "$FAILED"
    printf 'PRODUCTION_ASSET=%s\n' "$ASSET"
    printf 'PRODUCTION_DATABASE=UNTOUCHED\n'
    exit 0
  fi
  sleep 1
done

systemctl status "$UNIT" --no-pager -l
die 'Rollback target was restored but production health did not return.'
