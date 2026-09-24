#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

start_point=""
if [[ "${1:-}" == "--start" ]]; then start_point="$(parse_point "${2:-}")"; else die "Usage: $0 --start X,Y (measure from the current staging layout)"; fi
report="$AN3_ANDROID_REPORT_DIR/$(date +%F)-gba-smoke.txt"
url="$AN3_STAGING_URL/play/pokemon-emerald"
status="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 "$url" || true)"
[[ "$status" == "200" ]] || die "Authorized staging GBA player route did not return HTTP 200."
open_url "$url"
sleep 8
IFS=, read -r x y <<< "$start_point"
adb shell input tap "$x" "$y"
sleep 1
evidence="$(capture_staging_screen gba-start)"
write_result "$report" "TEST=gba-pokemon-emerald" "RESULT=PASS" "EVIDENCE=$evidence; player HTTP=$status; virtual Start tap=$start_point" "RUNTIME_ASSERTION=Android injected the current-layout virtual Start tap after the authorized GBA player route opened. A visible canvas/FPS check remains required before treating this as WebGL evidence." "KNOWN_LIMITATION=No stale coordinates are embedded; fullscreen/save-load use smoke-fullscreen.sh and visible native-menu confirmation."
