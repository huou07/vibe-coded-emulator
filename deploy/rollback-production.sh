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

# Restore the units and helpers the retained snapshot actually carries. The
# previous assumption was that $APP_ROOT/deploy always held them; on this host it
# held four files, so a real rollback aborted on the first missing helper while
# the service was stopped. A rollback must never depend on an optional file.
for unit in an3-arcade.service; do
  [[ -f "$APP_ROOT/deploy/$unit" ]] || { systemctl daemon-reload; systemctl restart "$UNIT"; die "Snapshot has no $unit; kept the installed unit."; }
done
[[ -f "$APP_ROOT/deploy/an3-arcade.service" ]] && install -o root -g root -m 0644 "$APP_ROOT/deploy/an3-arcade.service" /etc/systemd/system/an3-arcade.service
[[ -f "$APP_ROOT/deploy/an3-arcade-backup.sh" ]] && install -o root -g tvshare -m 0750 "$APP_ROOT/deploy/an3-arcade-backup.sh" /usr/local/libexec/an3-arcade-backup
[[ -f "$APP_ROOT/deploy/an3-arcade-backup.service" ]] && install -o root -g root -m 0644 "$APP_ROOT/deploy/an3-arcade-backup.service" /etc/systemd/system/an3-arcade-backup.service
[[ -f "$APP_ROOT/deploy/an3-arcade-backup.timer" ]] && install -o root -g root -m 0644 "$APP_ROOT/deploy/an3-arcade-backup.timer" /etc/systemd/system/an3-arcade-backup.timer
[[ -f "$APP_ROOT/deploy/an3-arcade-health.sh" ]] && install -o root -g root -m 0755 "$APP_ROOT/deploy/an3-arcade-health.sh" /usr/local/sbin/an3-arcade-health
[[ -f "$APP_ROOT/deploy/an3-arcade-turbostat.sh" ]] && install -o root -g root -m 0755 "$APP_ROOT/deploy/an3-arcade-turbostat.sh" /usr/local/libexec/an3-arcade-turbostat
[[ -f "$APP_ROOT/deploy/an3-arcade-turbostat.sudoers" ]] && install -o root -g root -m 0440 "$APP_ROOT/deploy/an3-arcade-turbostat.sudoers" /etc/sudoers.d/an3-arcade-turbostat
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
[[ -f /etc/sudoers.d/an3-arcade-turbostat ]] && visudo -cf /etc/sudoers.d/an3-arcade-turbostat >/dev/null

systemctl daemon-reload
systemctl enable "$UNIT"
systemctl enable --now an3-arcade-backup.timer
systemctl restart "$UNIT"

for attempt in $(seq 1 30); do
  HEALTH="$(curl --fail --silent --show-error --connect-timeout 3 "$HEALTH_URL" || true)"
  if [[ "$HEALTH" == *'"environment": "production"'* ]]; then
    ASSET="$(sed -n 's/.*"asset_version": "\([a-f0-9]*\)".*/\1/p' <<<"$HEALTH")"
    # Bounded retention for failed-release records. Each record carries a whole
    # application tree, and an unbounded set filled /opt on 2026-10-19. Older
    # records are pruned only here, after this rollback is verified healthy; a
    # rollback that fails still keeps its evidence untouched.
    KEEP="${AN3_FAILED_RELEASE_KEEP:-2}"
    if [[ "$KEEP" =~ ^[1-9][0-9]*$ ]] && [[ -d "$FAILED_RELEASES" ]]; then
      mapfile -t FAILED_RECORDS < <(find "$FAILED_RELEASES" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
      for old in "${FAILED_RECORDS[@]:$KEEP}"; do
        rm -rf -- "${FAILED_RELEASES:?}/$old"
        printf 'PRODUCTION_PRUNED_FAILED_RELEASE=%s\n' "$old"
      done
    fi
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
