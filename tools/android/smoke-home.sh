#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

report="$AN3_ANDROID_REPORT_DIR/$(date +%F)-homepage-smoke.txt"
status="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 "$AN3_STAGING_URL/" || true)"
[[ "$status" == "200" ]] || die "Staging homepage did not return HTTP 200."
open_url "$AN3_STAGING_URL/"
sleep 3
evidence="$(capture_staging_screen homepage)"
write_result "$report" "TEST=homepage-mobile-smoke" "RESULT=PASS" "EVIDENCE=$evidence; staging homepage HTTP=$status" "RUNTIME_ASSERTION=Staging HTTP 200 and Android VIEW intent completed. Search/filter/scroll and reload-retention need the separate visible interaction pass; no browser-tab inspection was used." "KNOWN_LIMITATION=Screenshots are supporting evidence only."
