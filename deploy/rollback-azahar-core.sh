#!/usr/bin/env bash
set -euo pipefail

# Restore one retained Azahar core snapshot without touching application code,
# SQLite, ROMs, browser data, or any other emulator core.

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die 'Run the Azahar core rollback helper as root.'
[[ "$#" -eq 1 ]] || { printf 'usage: an3-arcade-rollback-azahar-core /srv/an3-arcade/emulatorjs-cache/backups/azahar/YYYYMMDD-HHMMSS\n' >&2; exit 2; }

CACHE_ROOT=/srv/an3-arcade/emulatorjs-cache
CORE_DIR="$CACHE_ROOT/latest/cores"
REPORT_DIR="$CORE_DIR/reports"
BACKUP_ROOT="$CACHE_ROOT/backups/azahar"
TARGET="$1"

[[ "$TARGET" = "$BACKUP_ROOT"/* && "$(dirname "$TARGET")" = "$BACKUP_ROOT" ]] || die 'Rollback target must be a direct retained Azahar backup.'
[[ -d "$TARGET" && ! -L "$TARGET" ]] || die 'Rollback target is missing or unsafe.'
[[ -f "$TARGET/azahar-thread-wasm.data" && ! -L "$TARGET/azahar-thread-wasm.data" ]] || die 'Rollback core is missing or unsafe.'
[[ -f "$TARGET/azahar.json" && ! -L "$TARGET/azahar.json" ]] || die 'Rollback report is missing or unsafe.'

CURRENT_BACKUP="$BACKUP_ROOT/rollback-current-$(date +%Y%m%d-%H%M%S)"
install -d -o tvshare -g tvshare -m 0750 "$CORE_DIR" "$REPORT_DIR" "$CURRENT_BACKUP"
if [[ -f "$CORE_DIR/azahar-thread-wasm.data" ]]; then cp -a -- "$CORE_DIR/azahar-thread-wasm.data" "$CURRENT_BACKUP/"; fi
if [[ -f "$REPORT_DIR/azahar.json" ]]; then cp -a -- "$REPORT_DIR/azahar.json" "$CURRENT_BACKUP/"; fi
install -o tvshare -g tvshare -m 0640 "$TARGET/azahar-thread-wasm.data" "$CORE_DIR/azahar-thread-wasm.data"
install -o tvshare -g tvshare -m 0640 "$TARGET/azahar.json" "$REPORT_DIR/azahar.json"
printf 'AZAHAR_CORE_ROLLBACK=PASS\n'
printf 'AZAHAR_CORE_ROLLBACK_TARGET=%s\n' "$TARGET"
printf 'AZAHAR_CORE_FAILED_VERSION_BACKUP=%s\n' "$CURRENT_BACKUP"
