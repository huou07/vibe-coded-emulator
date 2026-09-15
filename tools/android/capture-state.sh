#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

label="${1:-}"
[[ -n "$label" ]] || die "Usage: $0 LABEL"
note "SCREENSHOT=$(capture_staging_screen "$label")"
