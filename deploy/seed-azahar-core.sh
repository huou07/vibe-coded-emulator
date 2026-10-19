#!/usr/bin/env bash
set -euo pipefail

# Install one checked, official EmulatorJS Azahar bundle into a selected
# server-side cache. This never reads or writes SQLite, ROMs, sessions, or the
# browser's client-side core cache.

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "$(id -u)" -ne 0 ]]; then
  die 'Run the Azahar core seed helper as root.'
fi
if [[ "$#" -ne 3 ]]; then
  printf 'usage: an3-arcade-seed-azahar-core /absolute/azahar-core.tgz sha256 staging|production\n' >&2
  exit 2
fi

BUNDLE="$1"
EXPECTED_SHA256="$2"
ENVIRONMENT="$3"
case "$ENVIRONMENT" in
  staging) CACHE_ROOT=/srv/an3-arcade-staging/emulatorjs-cache ;;
  production) CACHE_ROOT=/srv/an3-arcade/emulatorjs-cache ;;
  *) die 'Environment must be staging or production.' ;;
esac

[[ "$BUNDLE" = /* && -f "$BUNDLE" && ! -L "$BUNDLE" ]] || die 'Bundle must be a regular file at an absolute path.'
[[ "$EXPECTED_SHA256" =~ ^[a-f0-9]{64}$ ]] || die 'Expected SHA-256 must be a lowercase digest.'
ACTUAL_SHA256="$(sha256sum "$BUNDLE" | awk '{print $1}')"
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || die 'Bundle SHA-256 does not match the approved artifact.'

TMP="$(mktemp -d /tmp/an3-azahar-core.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
tar -xzf "$BUNDLE" -C "$TMP"
[[ -f "$TMP/azahar-thread-wasm.data" && ! -L "$TMP/azahar-thread-wasm.data" ]] || die 'Azahar threaded core data is missing or unsafe.'
[[ -f "$TMP/reports/azahar.json" && ! -L "$TMP/reports/azahar.json" ]] || die 'Azahar core report is missing or unsafe.'
[[ "$(find "$TMP" -type f -printf '%P\n' | sort)" == $'azahar-thread-wasm.data\nreports/azahar.json' ]] || die 'Bundle contains an unexpected file set.'
[[ "$(stat -c '%s' "$TMP/azahar-thread-wasm.data")" -gt 1048576 ]] || die 'Azahar core data is unexpectedly small.'
python3 - "$TMP/reports/azahar.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    report = json.load(handle)
options = report.get("options") or {}
# EmulatorJS build reports use ``core`` (the CDN's older reports used
# ``name``), so accept the canonical build field and retain compatibility with
# a verified legacy report without weakening the threaded/WebGL2 checks.
if report.get("core", report.get("name")) != "azahar" or options.get("requireThreads") is not True or options.get("requiresWebgl2") is not True:
    raise SystemExit("Azahar report does not declare the required threaded WebGL2 core.")
if not report.get("buildStart"):
    raise SystemExit("Azahar report is missing build metadata.")
PY

CORE_DIR="$CACHE_ROOT/latest/cores"
REPORT_DIR="$CORE_DIR/reports"
BACKUP_DIR="$CACHE_ROOT/backups/azahar/$(date +%Y%m%d-%H%M%S)"
install -d -o tvshare -g tvshare -m 0750 "$CORE_DIR" "$REPORT_DIR" "$BACKUP_DIR"
if [[ -f "$CORE_DIR/azahar-thread-wasm.data" ]]; then
  cp -a -- "$CORE_DIR/azahar-thread-wasm.data" "$BACKUP_DIR/"
fi
if [[ -f "$REPORT_DIR/azahar.json" ]]; then
  cp -a -- "$REPORT_DIR/azahar.json" "$BACKUP_DIR/"
fi

install -o tvshare -g tvshare -m 0640 "$TMP/azahar-thread-wasm.data" "$CORE_DIR/azahar-thread-wasm.data"
install -o tvshare -g tvshare -m 0640 "$TMP/reports/azahar.json" "$REPORT_DIR/azahar.json"
printf 'AZAHAR_CORE_SEED=PASS\n'
printf 'AZAHAR_CORE_ENVIRONMENT=%s\n' "$ENVIRONMENT"
printf 'AZAHAR_CORE_BUNDLE_SHA256=%s\n' "$ACTUAL_SHA256"
printf 'AZAHAR_CORE_BACKUP=%s\n' "$BACKUP_DIR"
