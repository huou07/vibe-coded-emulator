#!/usr/bin/env bash
# Stop local builds before they consume the workstation's safety reserve.
set -euo pipefail

label="${1:-local heavyweight work}"
path="${2:-$PWD}"
warning_gib="${AN3_DISK_WARNING_GIB:-40}"
reserve_gib="${AN3_DISK_RESERVE_GIB:-25}"

for value in "$warning_gib" "$reserve_gib"; do
  [[ "$value" =~ ^[0-9]+$ ]] || {
    echo 'AN3_DISK_WARNING_GIB and AN3_DISK_RESERVE_GIB must be whole GiB values.' >&2
    exit 2
  }
done
(( reserve_gib <= warning_gib )) || {
  echo 'AN3_DISK_RESERVE_GIB must not exceed AN3_DISK_WARNING_GIB.' >&2
  exit 2
}

available_kib="$(df -Pk "$path" | awk 'NR == 2 { print $4 }')"
[[ "$available_kib" =~ ^[0-9]+$ ]] || {
  echo "Could not read available disk space for $label." >&2
  exit 2
}
available_gib=$((available_kib / 1048576))

if (( available_kib < reserve_gib * 1048576 )); then
  printf 'DISK_PREFLIGHT=STOP task=%s available=%sGiB reserve=%sGiB; use CI or free known disposable build outputs first.\n' \
    "$label" "$available_gib" "$reserve_gib" >&2
  exit 75
fi
if (( available_kib < warning_gib * 1048576 )); then
  printf 'DISK_PREFLIGHT=WARNING task=%s available=%sGiB warning=%sGiB reserve=%sGiB.\n' \
    "$label" "$available_gib" "$warning_gib" "$reserve_gib" >&2
else
  printf 'DISK_PREFLIGHT=PASS task=%s available=%sGiB reserve=%sGiB.\n' \
    "$label" "$available_gib" "$reserve_gib"
fi
