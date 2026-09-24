#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

url="$AN3_STAGING_URL/"
if [[ "${1:-}" == "--production" ]]; then
  require_production_opt_in "$AN3_PRODUCTION_URL" "${2:-}"
  url="$AN3_PRODUCTION_URL/"
elif [[ $# -gt 0 ]]; then
  die "Usage: $0 [--production --allow-production]"
fi
open_url "$url"
note "OPENED_URL=$url"
