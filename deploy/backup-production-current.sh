#!/usr/bin/env bash
set -euo pipefail

# Create retained, point-in-time production rollback evidence without touching
# the live application, ROMs, saves, or database. The updater invokes this
# helper before every release; an owner may also run it manually before a
# maintenance window. An existing backup directory is never overwritten, but
# retention is bounded: after a verified new snapshot, only the newest
# AN3_BACKUP_KEEP application snapshots are kept. An unbounded history filled
# 90% of this host's disk on 2026-10-19 (51 snapshots, 55 GiB) and is not what
# a rollback needs.

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "$(id -u)" -ne 0 ]]; then
  die 'Run this production backup helper as root.'
fi
if [[ "$#" -ne 0 ]]; then
  printf 'usage: an3-arcade-backup-current\n' >&2
  exit 2
fi

APP_ROOT="${AN3_APP_ROOT:-/opt/an3-arcade}"
APP_BACKUPS="${AN3_APP_BACKUPS:-/opt/an3-arcade-backups}"
DATA_ROOT="${AN3_DATA_DIR:-/srv/an3-arcade}"
STAMP="${AN3_BACKUP_STAMP:-$(date +%Y%m%d-%H%M%S)}"
APP_BACKUP="$APP_BACKUPS/$STAMP"
DATABASE_BACKUP="$DATA_ROOT/backups/arcade-predeploy-$STAMP.db"
DATABASE_PATH="$DATA_ROOT/arcade.db"

[[ "$STAMP" =~ ^[0-9]{8}-[0-9]{6}$ ]] || die 'Backup stamp must use YYYYMMDD-HHMMSS.'
[[ -d "$APP_ROOT" && ! -L "$APP_ROOT" ]] || die 'Current application root is missing or unsafe.'
[[ -f "$DATABASE_PATH" && ! -L "$DATABASE_PATH" ]] || die 'Current SQLite database is missing or unsafe.'
[[ ! -e "$APP_BACKUP" && ! -L "$APP_BACKUP" ]] || die "Refusing to overwrite application backup: $APP_BACKUP"
[[ ! -e "$DATABASE_BACKUP" && ! -L "$DATABASE_BACKUP" ]] || die "Refusing to overwrite database backup: $DATABASE_BACKUP"

install -d -m 0700 "$APP_BACKUPS"
install -d -o tvshare -g tvshare -m 0750 "$DATA_ROOT" "$DATA_ROOT/backups"

# Keep a complete, rollback-compatible application snapshot. If this copy
# fails, its partial evidence is intentionally retained for inspection.
cp -a -- "$APP_ROOT" "$APP_BACKUP"

# SQLite Online Backup captures a consistent WAL-aware snapshot. It is never
# a raw copy of a live database file.
python3 - "$DATABASE_PATH" "$DATABASE_BACKUP" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    result = target.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"backup integrity check failed: {result}")
finally:
    target.close()
    source.close()
PY

chmod 0600 "$DATABASE_BACKUP"
DATABASE_SHA256="$(sha256sum "$DATABASE_BACKUP" | awk '{print $1}')"

printf 'PRODUCTION_BACKUP=PASS\n'
printf 'PRODUCTION_APP_BACKUP=%s\n' "$APP_BACKUP"
printf 'PRODUCTION_DATABASE_BACKUP=%s\n' "$DATABASE_BACKUP"
printf 'PRODUCTION_DATABASE_INTEGRITY=PASS\n'
printf 'PRODUCTION_DATABASE_SHA256=%s\n' "$DATABASE_SHA256"

# Bounded retention. The rollback helper accepts any direct child of
# $APP_BACKUPS whose name is YYYYMMDD-HHMMSS, so keeping the newest snapshots
# preserves rollback while a daily release cannot grow the host without limit.
# Snapshot names sort chronologically, and the snapshot created above is the
# newest one, so it is never pruned here. A pruned snapshot is disposable: the
# released source remains in Git and the database snapshot lives under
# $DATA_ROOT/backups.
KEEP="${AN3_BACKUP_KEEP:-7}"
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || die 'AN3_BACKUP_KEEP must be a positive whole number.'
mapfile -t RETAINED < <(find "$APP_BACKUPS" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
for old in "${RETAINED[@]:$KEEP}"; do
  [[ "$old" =~ ^[0-9]{8}-[0-9]{6}$ ]] || continue
  [[ "$old" != "$STAMP" ]] || die 'Refusing to prune the snapshot created by this run.'
  rm -rf -- "$APP_BACKUPS/$old"
  printf 'PRODUCTION_PRUNED_BACKUP=%s\n' "$old"
done
