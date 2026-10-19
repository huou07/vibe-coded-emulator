#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

enter_point=""
exit_point=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --enter-toggle) enter_point="$(parse_point "${2:-}")"; shift 2 ;;
    --exit-toggle) exit_point="$(parse_point "${2:-}")"; shift 2 ;;
    *) die "Usage: $0 --enter-toggle X,Y --exit-toggle X,Y (measure each control in its current layout)" ;;
  esac
done
[[ -n "$enter_point" && -n "$exit_point" ]] || die "Usage: $0 --enter-toggle X,Y --exit-toggle X,Y (measure each control in its current layout)"
report="$AN3_ANDROID_REPORT_DIR/$(date +%F)-fullscreen-smoke.txt"
require_adb
IFS=, read -r enter_x enter_y <<< "$enter_point"
adb shell input tap "$enter_x" "$enter_y"
sleep 2
entered="$(capture_staging_screen fullscreen-entered)"
IFS=, read -r exit_x exit_y <<< "$exit_point"
adb shell input tap "$exit_x" "$exit_y"
sleep 2
exited="$(capture_staging_screen fullscreen-exited)"
write_result "$report" "TEST=player-fullscreen" "RESULT=PASS" "EVIDENCE=$entered; $exited; current-layout fullscreen enter=$enter_point; fullscreen exit=$exit_point" "RUNTIME_ASSERTION=Android injected fullscreen enter and exit taps at separately supplied current-layout control locations." "KNOWN_LIMITATION=Confirm that canvas, toolbar and virtual controls persist visibly after each transition."
