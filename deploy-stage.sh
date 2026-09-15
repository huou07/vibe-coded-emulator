#!/usr/bin/env bash
set -euo pipefail

# Package and switch the isolated staging source release. This script never
# reads, writes, copies, or restarts production. The only sudo command is the
# root-owned, owner-installed staging release helper; it never executes an
# updater uploaded from /tmp.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_DIR="$(mktemp -d -t an3-arcade-staging.XXXXXX)"
ARCHIVE="$ARCHIVE_DIR/an3-arcade-staging.tgz"
REMOTE_ARCHIVE="/tmp/an3-arcade-staging-$STAMP.tgz"
REMOTE_RELEASE_HELPER="/usr/local/sbin/an3-arcade-staging-release"
trap 'rm -rf -- "$ARCHIVE_DIR"' EXIT

# The shared staging control path requires a verified persistent host key and
# disables password/keyboard-interactive fallback.  Keep this release path
# aligned with the handoff rather than duplicating a weaker SSH option set.
# shellcheck disable=SC1091
source "$ROOT/tools/ssh/staging-common.sh"
"$ROOT/tools/ssh/check-staging-key.sh"

"$ROOT/deploy/package-staging.sh" "$ARCHIVE"
command scp "${AN3_STAGING_SSH_ARGS[@]}" "$ARCHIVE" "$AN3_STAGING_SSH_TARGET:/tmp/"
staging_ssh "mv /tmp/$(basename "$ARCHIVE") '$REMOTE_ARCHIVE'; sudo -n '$REMOTE_RELEASE_HELPER' '$REMOTE_ARCHIVE'; status=\$?; rm -f -- '$REMOTE_ARCHIVE'; exit \$status"
printf 'STAGING_DEPLOY=PASS\n'
