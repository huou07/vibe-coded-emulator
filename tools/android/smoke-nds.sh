#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

[[ "${1:-}" == "--game-box" ]] || die "Usage: $0 --game-box X,Y,WIDTH,HEIGHT [--pad X,Y] [--native-menu X,Y]"
box="$(parse_box "${2:-}")"
shift 2
pad=""; menu=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pad) pad="$(parse_point "${2:-}")"; shift 2 ;;
    --native-menu) menu="$(parse_point "${2:-}")"; shift 2 ;;
    *) die "Unknown option: $1" ;;
  esac
done
report="$AN3_ANDROID_REPORT_DIR/$(date +%F)-nds-smoke.txt"
url="$AN3_STAGING_URL/play/pokemon-mystery-dungeon-explorers-of-sky?ndsdebug=1"
status="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 "$url" || true)"
[[ "$status" == "200" ]] || die "Authorized staging NDS player route did not return HTTP 200."
open_url "$url"
sleep 12
IFS=, read -r left top width height <<< "$box"
center_x=$((left + width / 2)); center_y=$((top + height / 2))
x1=$((left + width / 4)); x2=$((left + width * 3 / 4)); y1=$((top + height / 4)); y2=$((top + height * 3 / 4))
adb shell input tap "$center_x" "$center_y"
adb shell input swipe "$x1" "$center_y" "$x2" "$center_y" 350
adb shell input swipe "$center_x" "$y1" "$center_x" "$y2" 350
adb shell input swipe "$x1" "$y1" "$x2" "$y2" 350
if [[ -n "$pad" ]]; then IFS=, read -r x y <<< "$pad"; adb shell input tap "$x" "$y"; fi
if [[ -n "$menu" ]]; then IFS=, read -r x y <<< "$menu"; adb shell input tap "$x" "$y"; fi
sleep 1
evidence="$(capture_staging_screen nds-touch)"
write_result "$report" "TEST=nds-pokemon-mystery-dungeon" "RESULT=PASS" "EVIDENCE=$evidence; player HTTP=$status; canvas box=$box; centre/horizontal/vertical/diagonal ADB gestures injected${pad:+; virtual-pad tap=$pad}${menu:+; native-menu tap=$menu}" "RUNTIME_ASSERTION=Current-layout geometry is required and used for all gestures. Staging-only ndsdebug=1 is present for explicit post-run touch-debug export. A rendered canvas/FPS and native-menu priority remain visible verification steps; screenshots alone are not treated as WebGL proof." "KNOWN_LIMITATION=No serial or private browser-tab/device data was accessed."
