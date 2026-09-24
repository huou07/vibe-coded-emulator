#!/usr/bin/env bash
# Shared safe primitives for the AN3 staging-first Android regressions.
# This file deliberately never selects, prints, or stores a device serial.
set -euo pipefail

ANDROID_TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AN3_ROOT="$(cd "$ANDROID_TOOLS_DIR/../.." && pwd)"
AN3_STAGING_URL="${AN3_STAGING_URL:-http://192.0.2.8:8092}"
AN3_PRODUCTION_URL="${AN3_PRODUCTION_URL:-http://192.0.2.8:8091}"
AN3_ANDROID_REPORT_DIR="${AN3_ANDROID_REPORT_DIR:-$AN3_ROOT/reports/android-regression}"
AN3_BROWSER_PACKAGE="${AN3_BROWSER_PACKAGE:-com.android.chrome}"

die() { printf '%s\n' "ERROR: $*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

require_adb() {
  command -v adb >/dev/null 2>&1 || die "adb is required."
  [[ "$(adb get-state 2>/dev/null || true)" == "device" ]] || die "No authorized Android device is connected. Enable USB debugging and authorize this Mac."
}

android_version() {
  adb shell getprop ro.build.version.release 2>/dev/null | tr -d '\r' | sed -n '1p'
}

logical_screen_size() {
  adb shell wm size 2>/dev/null | tr -d '\r' | sed -n 's/^Physical size: //p' | sed -n '1p'
}

browser_version() {
  adb shell dumpsys package "$AN3_BROWSER_PACKAGE" 2>/dev/null | tr -d '\r' | sed -n 's/.*versionName=//p' | sed -n '1p'
}

require_browser() {
  adb shell cmd package list packages "$AN3_BROWSER_PACKAGE" 2>/dev/null | tr -d '\r' | grep -qx "package:$AN3_BROWSER_PACKAGE" || die "Browser package $AN3_BROWSER_PACKAGE is unavailable. Set AN3_BROWSER_PACKAGE to an installed browser package."
}

require_staging_url() {
  [[ "$1" == "$AN3_STAGING_URL" || "$1" == "$AN3_STAGING_URL/" ]] || die "This command defaults to staging only. Production requires the explicit --allow-production path."
}

require_production_opt_in() {
  [[ "$1" == "$AN3_PRODUCTION_URL" || "$1" == "$AN3_PRODUCTION_URL/" ]] || die "Unexpected production URL."
  [[ "${2:-}" == "--allow-production" ]] || die "Production requires --allow-production; do not use it for routine regressions."
}

open_url() {
  local url="$1"
  require_adb
  require_browser
  adb shell am start -W -a android.intent.action.VIEW -d "$url" "$AN3_BROWSER_PACKAGE" >/dev/null
  note "ANDROID_VIEW_INTENT=PASS"
}

require_browser_foreground() {
  local focus
  focus="$(adb shell dumpsys window windows 2>/dev/null | tr -d '\r' | sed -n '/mCurrentFocus/p' | sed -n '1p')"
  # Android 16 can omit mCurrentFocus from the `window windows` subsection while
  # retaining it in the complete window dump. Both checks only match the
  # approved browser package and never emit other foreground-app details.
  if [[ "$focus" != *"$AN3_BROWSER_PACKAGE"* ]]; then
    focus="$(adb shell dumpsys window 2>/dev/null | tr -d '\r' | sed -n '/mCurrentFocus/p' | sed -n '1p')"
  fi
  [[ "$focus" == *"$AN3_BROWSER_PACKAGE"* ]] || die "Refusing to capture: the approved browser is not foreground. Open staging first."
}

safe_label() {
  [[ "$1" =~ ^[A-Za-z0-9._-]{1,80}$ ]] || die "Label must use only letters, digits, dot, dash, or underscore."
}

capture_staging_screen() {
  local label="$1" output
  safe_label "$label"
  require_adb
  require_browser_foreground
  mkdir -p "$AN3_ANDROID_REPORT_DIR"
  output="$AN3_ANDROID_REPORT_DIR/$(date +%Y%m%d-%H%M%S)-$label.png"
  adb exec-out screencap -p > "$output"
  [[ -s "$output" ]] || die "Android screenshot capture failed."
  printf '%s\n' "$output"
}

write_result() {
  local report="$1"
  shift
  mkdir -p "$(dirname "$report")"
  {
    printf 'DATE=%s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'DEVICE=physical Android\n'
    printf 'ANDROID_VERSION=%s\n' "$(android_version || true)"
    printf 'BROWSER_PACKAGE=%s\n' "$AN3_BROWSER_PACKAGE"
    printf 'BROWSER_VERSION=%s\n' "$(browser_version || true)"
    printf 'LOGICAL_SCREEN_SIZE=%s\n' "$(logical_screen_size || true)"
    printf 'STAGING_URL=%s\n' "$AN3_STAGING_URL"
    printf '%s\n' "$@"
  } > "$report"
  printf '%s\n' "$report"
}

parse_box() {
  local value="$1" width height
  [[ "$value" =~ ^([0-9]+),([0-9]+),([1-9][0-9]*),([1-9][0-9]*)$ ]] || die "Game box must be X,Y,WIDTH,HEIGHT from the current staging layout."
  width="${BASH_REMATCH[3]}"; height="${BASH_REMATCH[4]}"
  (( width >= 20 && height >= 20 )) || die "Game box is too small."
  printf '%s\n' "$value"
}

parse_point() {
  [[ "$1" =~ ^[0-9]+,[0-9]+$ ]] || die "Point must be X,Y from the current staging layout."
  printf '%s\n' "$1"
}
