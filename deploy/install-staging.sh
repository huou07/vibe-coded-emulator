#!/usr/bin/env bash
set -euo pipefail

# Entry point for first installs. The rebuild procedure
# is intentionally safe for both an absent service and a stale staging tree.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/rebuild-staging.sh" "$@"
