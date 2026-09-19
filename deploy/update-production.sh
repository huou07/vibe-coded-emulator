#!/usr/bin/env bash
set -euo pipefail

# Production-only in-place release. It invokes the retained application and
# SQLite backup helper before changing code, but never reads staging paths.

if [[ "$#" -ne 2 ]]; then
  echo "usage: update-production.sh /path/to/source-archive.tgz expected-static-asset" >&2
  exit 2
fi

ARCHIVE="$1"
EXPECTED_ASSET="$2"
APP_ROOT=/opt/an3-arcade
APP_BACKUPS=/opt/an3-arcade-backups
DATA_ROOT=/srv/an3-arcade
UNIT=an3-arcade.service
HEALTH_URL=http://127.0.0.1:8091/health
TMP="$(mktemp -d /tmp/an3-production-release.XXXXXX)"
STAMP="$(date +%Y%m%d-%H%M%S)"
APP_BACKUP="$APP_BACKUPS/$STAMP"

cleanup() {
  rm -rf -- "$TMP"
  rm -f -- "$ARCHIVE"
}
trap cleanup EXIT

[[ -r "$ARCHIVE" ]] || { echo "Production archive is not readable." >&2; exit 1; }
tar -xzf "$ARCHIVE" -C "$TMP"
[[ -f "$TMP/app.py" && -d "$TMP/static" && -f "$TMP/deploy/an3-arcade.service" && -f "$TMP/deploy/backup-production-current.sh" && -f "$TMP/deploy/rollback-production.sh" && -f "$TMP/deploy/seed-azahar-core.sh" && -f "$TMP/deploy/rollback-azahar-core.sh" && -f "$TMP/deploy/retire-production-rom-library.sh" && -f "$TMP/tools/verify-release-catalog.py" && -f "$TMP/bug_report.py" && -f "$TMP/netcode.py" && -f "$TMP/sync_engine.py" && -f "$TMP/qrcodegen.py" && -f "$TMP/LICENSE" && -f "$TMP/THIRD_PARTY_NOTICES.md" && -f "$TMP/native-offline/releases/catalog.json" ]] || {
  echo "Production archive has an unexpected layout." >&2
  exit 1
}
find "$TMP" -type f -name '._*' -delete

ASSET="$(python3 - "$TMP/static" <<'PY'
import hashlib
import os
import sys

root = sys.argv[1]
digest = hashlib.sha256()
for directory, directories, filenames in os.walk(root):
    directories.sort()
    for name in sorted(filenames):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        relative = os.path.relpath(path, root).replace(os.sep, "/")
        digest.update(relative.encode("utf-8"))
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
print(digest.hexdigest()[:12])
PY
)"
[[ "$ASSET" == "$EXPECTED_ASSET" ]] || {
  echo "Archive asset does not match the local preflight." >&2
  exit 1
}

AN3_BACKUP_STAMP="$STAMP" bash "$TMP/deploy/backup-production-current.sh"
python3 "$TMP/tools/verify-release-catalog.py" >/dev/null

install -d -m 0755 "$APP_ROOT" "$APP_ROOT/static" "$APP_ROOT/native-offline/releases"
install -m 0755 "$TMP/app.py" "$APP_ROOT/app.py"
install -m 0644 "$TMP/bug_report.py" "$APP_ROOT/bug_report.py"
install -m 0644 "$TMP/netcode.py" "$APP_ROOT/netcode.py"
install -m 0644 "$TMP/sync_engine.py" "$APP_ROOT/sync_engine.py"
install -m 0644 "$TMP/qrcodegen.py" "$APP_ROOT/qrcodegen.py"
install -m 0644 "$TMP/LICENSE" "$APP_ROOT/LICENSE"
install -m 0644 "$TMP/THIRD_PARTY_NOTICES.md" "$APP_ROOT/THIRD_PARTY_NOTICES.md"
cp -a "$TMP/static/." "$APP_ROOT/static/"
# The consolidated release intentionally retires only the former offline-app
# bundle. The application snapshot above retains these files for rollback; no
# database, ROM, save, or other static feature is removed here.
for obsolete in offline-app.js offline-app.css offline-app.webmanifest offline-app-service-worker.js; do
  rm -f -- "$APP_ROOT/static/$obsolete"
done
find "$APP_ROOT/static" -type f -name '._*' -delete
find "$APP_ROOT/static" -type d -exec chmod 0755 {} +
find "$APP_ROOT/static" -type f -exec chmod 0644 {} +
install -m 0644 "$TMP/native-offline/releases/catalog.json" "$APP_ROOT/native-offline/releases/catalog.json"
while IFS= read -r artifact; do
  install -m 0644 "$TMP/native-offline/releases/$artifact" "$APP_ROOT/native-offline/releases/$artifact"
  install -m 0644 "$TMP/native-offline/releases/$artifact.sha256" "$APP_ROOT/native-offline/releases/$artifact.sha256"
done < <(python3 "$TMP/tools/verify-release-catalog.py" --print-filenames)
find "$APP_ROOT/native-offline/releases" -type f -exec chmod 0644 {} +

install -o root -g root -m 0644 "$TMP/deploy/an3-arcade.service" /etc/systemd/system/an3-arcade.service
install -o root -g tvshare -m 0750 "$TMP/deploy/an3-arcade-backup.sh" /usr/local/libexec/an3-arcade-backup
install -o root -g root -m 0644 "$TMP/deploy/an3-arcade-backup.service" /etc/systemd/system/an3-arcade-backup.service
install -o root -g root -m 0644 "$TMP/deploy/an3-arcade-backup.timer" /etc/systemd/system/an3-arcade-backup.timer
install -o root -g root -m 0755 "$TMP/deploy/an3-arcade-health.sh" /usr/local/sbin/an3-arcade-health
install -o root -g root -m 0755 "$TMP/deploy/an3-arcade-turbostat.sh" /usr/local/libexec/an3-arcade-turbostat
install -o root -g root -m 0440 "$TMP/deploy/an3-arcade-turbostat.sudoers" /etc/sudoers.d/an3-arcade-turbostat
install -o root -g root -m 0755 "$TMP/deploy/backup-production-current.sh" /usr/local/sbin/an3-arcade-backup-current
install -o root -g root -m 0755 "$TMP/deploy/rollback-production.sh" /usr/local/sbin/an3-arcade-rollback-production
install -o root -g root -m 0755 "$TMP/deploy/seed-azahar-core.sh" /usr/local/sbin/an3-arcade-seed-azahar-core
install -o root -g root -m 0755 "$TMP/deploy/rollback-azahar-core.sh" /usr/local/sbin/an3-arcade-rollback-azahar-core
install -o root -g root -m 0755 "$TMP/deploy/retire-production-rom-library.sh" /usr/local/sbin/an3-arcade-retire-rom-library
visudo -cf /etc/sudoers.d/an3-arcade-turbostat >/dev/null

systemctl daemon-reload
systemctl enable "$UNIT"
systemctl enable --now an3-arcade-backup.timer
systemctl restart "$UNIT"

for attempt in $(seq 1 30); do
  HEALTH="$(curl --fail --silent --show-error --connect-timeout 3 "$HEALTH_URL" || true)"
  if [[ "$HEALTH" == *'"environment": "production"'* && "$HEALTH" == *"\"asset_version\": \"$ASSET\""* ]]; then
    printf 'PRODUCTION_RELEASE=PASS\n'
    printf 'PRODUCTION_ASSET=%s\n' "$ASSET"
    printf 'PRODUCTION_APP_BACKUP=%s\n' "$APP_BACKUP"
    exit 0
  fi
  sleep 1
done

systemctl status "$UNIT" --no-pager -l
exit 1
