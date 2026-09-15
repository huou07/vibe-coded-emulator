#!/usr/bin/env bash
set -euo pipefail

# Intentionally fail closed. The current bridge-network gateway cannot safely
# reach a legacy Python service rebound to host loopback, so a port cutover
# would be misleading. This helper performs no filesystem, Docker, systemd, or
# listener operation and is retained only to prevent an older invocation path
# from silently doing the wrong thing.

printf 'STAGING_RUST_CUTOVER=DISABLED\n' >&2
printf '%s\n' \
  'ERROR: Rust shadow cutover is not supported in this release; the gateway remains loopback-only on its shadow port.' >&2
printf '%s\n' \
  'No listener, legacy service, Compose stack, cache volume, release, archive, database, or backup was changed.' >&2
exit 64
