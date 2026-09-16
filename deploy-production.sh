#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Production release: package the reviewed source, verify it, and switch the
# live production install with its own backup + health gate.
#
# Runs only when AN3_PRODUCTION_APPROVED=1 is set: production changes require the
# owner's explicit approval in the current request.
#
# Usage: AN3_PRODUCTION_APPROVED=1 ./deploy-production.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_DIR="$(mktemp -d -t an3-arcade-production.XXXXXX)"
ARCHIVE="$ARCHIVE_DIR/an3-arcade-production.tgz"
REMOTE_ARCHIVE="/tmp/an3-arcade-production-$STAMP.tgz"
REMOTE_UPDATER="/tmp/an3-arcade-production-update-$STAMP.sh"
trap 'rm -rf -- "$ARCHIVE_DIR"' EXIT

die() { printf 'PRODUCTION_DEPLOY=FAIL %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

[[ "${AN3_PRODUCTION_APPROVED:-0}" == "1" ]] || die "production requires explicit approval: re-run with AN3_PRODUCTION_APPROVED=1"

# The staging control path (same host) supplies the verified key settings.
if [[ -f "$ROOT/tools/ssh/staging-env.sh" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/tools/ssh/staging-env.sh"
fi
# shellcheck disable=SC1091
source "$ROOT/tools/ssh/staging-common.sh"
"$ROOT/tools/ssh/check-staging-key.sh" >/dev/null

note "packaging"
"$ROOT/deploy/package-production.sh" "$ARCHIVE"

# Asset fingerprint must match the host's own computation algorithm exactly.
EXPECTED_ASSET="$(python3 - "$ROOT/static" <<'PY'
import hashlib, os, sys
root = sys.argv[1]
digest = hashlib.sha256()
for directory, directories, filenames in os.walk(root):
    directories.sort()
    for name in sorted(filenames):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        digest.update(os.path.relpath(path, root).replace(os.sep, "/").encode("utf-8"))
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
print(digest.hexdigest()[:12])
PY
)"

note "security preflight on the payload"
STAGE="$(mktemp -d -t an3-prod-preflight.XXXXXX)"
tar -xzf "$ARCHIVE" -C "$STAGE"
# User-facing surfaces must carry no credentials or personal data. Operational
# scripts under deploy/ legitimately reference the private host and are not
# served to users, so they are excluded from this scan.
if grep -rlE "AN3_GOOGLE_CLIENT_SECRET=[A-Za-z0-9_-]{8,}|AN3_AUTH_PEPPER=[A-Za-z0-9]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail)\." \
     "$STAGE/app.py" "$STAGE/static" 2>/dev/null | grep -q .; then
  rm -rf "$STAGE"
  die "user-facing payload contains credential or personal-data patterns"
fi
for required in app.py netcode.py sync_engine.py qrcodegen.py LICENSE THIRD_PARTY_NOTICES.md; do
  [[ -f "$STAGE/$required" ]] || { rm -rf "$STAGE"; die "payload is missing $required"; }
done
rm -rf "$STAGE"
note "preflight: clean"

note "uploading"
command scp "${AN3_STAGING_SSH_ARGS[@]}" "$ARCHIVE" "$AN3_STAGING_SSH_TARGET:$REMOTE_ARCHIVE"
command scp "${AN3_STAGING_SSH_ARGS[@]}" "$ROOT/deploy/update-production.sh" "$AN3_STAGING_SSH_TARGET:$REMOTE_UPDATER"

note "switching production (host backup + health gate)"
staging_ssh "sudo -n bash '$REMOTE_UPDATER' '$REMOTE_ARCHIVE' '$EXPECTED_ASSET'; status=\$?; rm -f -- '$REMOTE_ARCHIVE' '$REMOTE_UPDATER'; exit \$status"

note "PRODUCTION_ASSET=$EXPECTED_ASSET"
printf 'PRODUCTION_DEPLOY=PASS\n'
