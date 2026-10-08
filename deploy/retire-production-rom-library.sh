#!/usr/bin/env bash
set -euo pipefail

# Withdraw all server-ROM publication from production while preserving a
# root-owned rollback record. This helper never deletes ROMs or production
# backups; it moves the two app-owned ROM roots into a timestamped archive and
# clears their public database references.

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$(id -u)" -eq 0 ]] || die 'Run this production ROM-retirement helper as root.'
[[ "$#" -eq 0 ]] || { printf 'usage: an3-arcade-retire-rom-library\n' >&2; exit 2; }

DATA_ROOT="${AN3_DATA_DIR:-/srv/an3-arcade}"
ARCHIVE_ROOT="${AN3_ROM_RETIRE_ARCHIVE_ROOT:-/srv/an3-arcade-retired-roms}"
STAMP="${AN3_ROM_RETIRE_STAMP:-$(date +%Y%m%d-%H%M%S)}"
DATABASE_PATH="$DATA_ROOT/arcade.db"
ARCHIVE="$ARCHIVE_ROOT/$STAMP"

[[ "$DATA_ROOT" = /* && "$ARCHIVE_ROOT" = /* ]] || die 'Production roots must be absolute.'
[[ "$ARCHIVE_ROOT" != "$DATA_ROOT" && "$ARCHIVE_ROOT" != "$DATA_ROOT"/* ]] || die 'ROM archive root must not be inside live data.'
[[ "$STAMP" =~ ^[0-9]{8}-[0-9]{6}$ ]] || die 'Archive stamp must use YYYYMMDD-HHMMSS.'
[[ -d "$DATA_ROOT" && ! -L "$DATA_ROOT" ]] || die 'Production data root is missing or unsafe.'
[[ -f "$DATABASE_PATH" && ! -L "$DATABASE_PATH" ]] || die 'Production SQLite database is missing or unsafe.'
[[ ! -e "$ARCHIVE" && ! -L "$ARCHIVE" ]] || die 'Refusing to overwrite a ROM archive.'

install -d -m 0700 "$ARCHIVE_ROOT"
install -d -m 0700 "$ARCHIVE"
DATABASE_BACKUP="$ARCHIVE/arcade-before-rom-retirement.db"

python3 - "$DATABASE_PATH" "$DATABASE_BACKUP" <<'PY'
import sqlite3
import sys

source_path, target_path = sys.argv[1:]
source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
target = sqlite3.connect(target_path)
try:
    source.backup(target)
    result = target.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"database backup integrity check failed: {result}")
finally:
    target.close()
    source.close()
PY
chmod 0600 "$DATABASE_BACKUP"

for name in roms prepared-roms; do
  source="$DATA_ROOT/$name"
  if [[ -e "$source" || -L "$source" ]]; then
    [[ -d "$source" && ! -L "$source" ]] || die "Live ROM root is unsafe: $name"
    mv -- "$source" "$ARCHIVE/$name"
  fi
  install -d -o tvshare -g tvshare -m 0750 "$DATA_ROOT/$name"
done

RETIRED_COUNT="$(python3 - "$DATABASE_PATH" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(games)")}
    required = {"rom_path", "rom_name", "file_size", "published", "updated_at"}
    if not required.issubset(columns):
        raise SystemExit("games table lacks the expected ROM retirement columns")
    connection.execute("BEGIN IMMEDIATE")
    count = connection.execute("SELECT COUNT(*) FROM games WHERE COALESCE(rom_path, '') <> '' OR COALESCE(rom_name, '') <> ''").fetchone()[0]
    connection.execute("UPDATE games SET rom_path='', rom_name='', file_size=0, published=0, updated_at=strftime('%s','now') WHERE COALESCE(rom_path, '') <> '' OR COALESCE(rom_name, '') <> ''")
    connection.commit()
    print(count)
except Exception:
    connection.rollback()
    raise
finally:
    connection.close()
PY
)"

printf 'PRODUCTION_ROM_LIBRARY_RETIRED=PASS\n'
printf 'PRODUCTION_ROM_ARCHIVE=%s\n' "$ARCHIVE"
printf 'PRODUCTION_ROM_RECORDS_RETIRED=%s\n' "$RETIRED_COUNT"
