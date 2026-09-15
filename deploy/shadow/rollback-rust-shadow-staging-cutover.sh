#!/usr/bin/env bash
set -euo pipefail

# Intentionally fail closed with the paired cutover helper. No supported
# cutover can be active for this release, so this helper must never guess at
# legacy listener/systemd state or mutate retained cutover records.

printf 'STAGING_RUST_CUTOVER_ROLLBACK=DISABLED\n' >&2
printf '%s\n' \
  'ERROR: Rust shadow cutover rollback is unavailable because cutover itself is disabled in this release.' >&2
printf '%s\n' \
  'No listener, legacy service, Compose stack, cache volume, release, archive, database, or backup was changed.' >&2
exit 64
