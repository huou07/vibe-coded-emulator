#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

port="${1:-18092}"
[[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || die "Usage: $0 [localhost-port]"
report="$AN3_ANDROID_REPORT_DIR/$(date +%F)-pwa-localhost.txt"
curl -fsS --connect-timeout 5 "http://127.0.0.1:$port/health" >/dev/null || die "No local staging tunnel is healthy on 127.0.0.1:$port. Start the private SSH forward first."
require_adb
adb reverse "tcp:$port" "tcp:$port"
trap 'adb reverse --remove "tcp:$port" >/dev/null 2>&1 || true' EXIT
open_url "http://localhost:$port/"
sleep 3
evidence="$(capture_staging_screen pwa-localhost)"
write_result "$report" "TEST=pwa-localhost-preflight" "RESULT=PASS" "EVIDENCE=$evidence; private adb reverse tcp:$port -> tcp:$port installed and removed on exit" "RUNTIME_ASSERTION=Android opened the private localhost staging path. Verify isSecureContext, Service Worker, manifest, install and network-loss behavior through the visible PWA diagnostic/runbook before declaring offline E2E PASS." "KNOWN_LIMITATION=This preflight never disables browser security, exposes a WAN port, or leaves adb reverse configured."
