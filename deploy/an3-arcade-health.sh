#!/usr/bin/env bash
set -euo pipefail

# Lightweight, read-only AN3 operations summary. Run this on the host as an
# account that can read the two data roots and systemd unit state.

PRODUCTION_URL="${AN3_PRODUCTION_HEALTH_URL:-http://127.0.0.1:8091/health}"
STAGING_URL="${AN3_STAGING_HEALTH_URL:-http://192.0.2.8:8092/health}"
PRODUCTION_DB="${AN3_PRODUCTION_DB:-/srv/an3-arcade/arcade.db}"
STAGING_DB="${AN3_STAGING_DB:-/srv/an3-arcade-staging/arcade.db}"

health_asset() {
  local label="$1" url="$2" expected="$3" response
  response="$(curl --fail --silent --show-error --connect-timeout 5 "$url" || true)"
  if [[ "$response" == *"\"environment\": \"$expected\""* && "$response" == *'"asset_version":'* ]]; then
    printf '%-14s healthy  %s\n' "$label" "$(sed -n 's/.*"asset_version": "\([a-f0-9]*\)".*/asset=\1/p' <<<"$response")"
  else
    printf '%-14s unhealthy\n' "$label"
  fi
}

unit_state() {
  local label="$1" unit="$2"
  printf '%-14s %s\n' "$label" "$(systemctl is-active "$unit" 2>/dev/null || true)"
}

db_state() {
  local label="$1" database="$2" result
  result="$(python3 - "$database" <<'PY'
import sqlite3
import sys

try:
    connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    try:
        print(connection.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        connection.close()
except Exception:
    print("unavailable")
PY
)"
  printf '%-14s %s\n' "$label" "$result"
}

printf 'AN3 HEALTH\n'
health_asset production "$PRODUCTION_URL" production
health_asset staging "$STAGING_URL" staging
unit_state cloudflared cloudflared.service
unit_state backup-timer an3-arcade-backup.timer
db_state production-db "$PRODUCTION_DB"
db_state staging-db "$STAGING_DB"
printf '%-14s %s\n' disk "$(df -P /srv | awk 'NR==2 {print $5 " used (" $4 " blocks free)"}')"
