#!/usr/bin/env bash
# Foreground-only loopback tunnel for the Android PWA localhost preflight.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/staging-common.sh"

port="${1:-18092}"
[[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || ssh_die "Usage: $0 [localhost-port]"

printf 'STAGING_PWA_TUNNEL=127.0.0.1:%s -> 192.168.1.8:8092\n' "$port"
exec ssh "${AN3_STAGING_SSH_ARGS[@]}" \
  -o ExitOnForwardFailure=yes \
  -N -L "127.0.0.1:${port}:192.168.1.8:8092" \
  "$AN3_STAGING_SSH_TARGET"
