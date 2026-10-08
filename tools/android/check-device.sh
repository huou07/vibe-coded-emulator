#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

report=""
if [[ "${1:-}" == "--report" ]]; then
  report="${2:-}"
  [[ -n "$report" ]] || die "--report requires an absolute output path."
  [[ "$report" = /* ]] || die "Report path must be absolute."
fi

if ! command -v adb >/dev/null 2>&1 || [[ "$(adb get-state 2>/dev/null || true)" != "device" ]]; then
  note "DEVICE_CONNECTED=no"
  [[ -z "$report" ]] || write_result "$report" "TEST=device-discovery" "RESULT=BLOCKED" "EVIDENCE=No authorized ADB device was available; no serial was read or recorded." "RUNTIME_ASSERTION=adb get-state did not return device." "KNOWN_LIMITATION=Authorize USB debugging, then rerun."
  exit 2
fi

require_browser
note "DEVICE_CONNECTED=yes"
note "ANDROID_VERSION=$(android_version)"
note "BROWSER_PACKAGE=$AN3_BROWSER_PACKAGE"
note "BROWSER_VERSION=$(browser_version)"
note "LOGICAL_SCREEN_SIZE=$(logical_screen_size)"
[[ -z "$report" ]] || write_result "$report" "TEST=device-discovery" "RESULT=PASS" "EVIDENCE=Authorized ADB connection and approved browser package detected." "RUNTIME_ASSERTION=adb get-state returned device." "KNOWN_LIMITATION=No serial, IMEI, Android ID, MAC, account, or personal-file data was read."
