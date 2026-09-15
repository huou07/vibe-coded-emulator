#!/usr/bin/env bash
set -euo pipefail

# Deploy the Rust gateway only to the isolated staging-shadow helper.  This is
# intentionally separate from deploy-stage.sh/deploy.sh and cannot invoke a
# production helper.  All local source/production-review artifacts are retained
# under work/shadow-deploy-artifacts unless an owner chooses another absolute
# artifact directory.

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    die 'Neither shasum nor sha256sum is available.'
  fi
}

[[ "$#" -eq 0 ]] || { printf 'usage: deploy-rust-shadow-stage.sh\n' >&2; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="${AN3_SHADOW_ARTIFACT_ROOT:-$ROOT/work/shadow-deploy-artifacts}"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARTIFACT_DIR="$ARTIFACT_ROOT/$STAMP"
STAGING_ARCHIVE="$ARTIFACT_DIR/an3-rust-shadow-staging-$STAMP.tgz"

[[ "$ARTIFACT_ROOT" = /* ]] || die 'AN3_SHADOW_ARTIFACT_ROOT must be an absolute path.'
[[ ! -e "$ARTIFACT_DIR" && ! -L "$ARTIFACT_DIR" ]] || die "Refusing to overwrite artifact directory: $ARTIFACT_DIR"

# Source the shared staging-only transport policy. It enforces verified known
# hosts, BatchMode, public-key authentication, and disables password auth.
# shellcheck disable=SC1091
source "$ROOT/tools/ssh/staging-common.sh"
"$ROOT/tools/ssh/check-staging-key.sh"

umask 077
mkdir -p "$ARTIFACT_ROOT"
mkdir "$ARTIFACT_DIR"

printf 'STAGING_SHADOW_ARTIFACT_DIR=%s\n' "$ARTIFACT_DIR"
"$ROOT/deploy/shadow/package-rust-shadow.sh" "$STAGING_ARCHIVE"
"$ROOT/deploy/shadow/prepare-rust-shadow-production.sh" "$STAGING_ARCHIVE" "$ARTIFACT_DIR" "$STAMP"

STAGING_SHA256="$(sha256_file "$STAGING_ARCHIVE")"
REMOTE_ARCHIVE="/tmp/$(basename "$STAGING_ARCHIVE")"

# This copy targets only the verified staging host selected by staging-common.
# No production address/archive/script is ever copied or executed by this path.
command scp "${AN3_STAGING_SSH_ARGS[@]}" "$STAGING_ARCHIVE" "$AN3_STAGING_SSH_TARGET:$REMOTE_ARCHIVE"
staging_ssh "sudo -n /usr/local/sbin/an3-rust-shadow-staging-release '$REMOTE_ARCHIVE' '$STAGING_SHA256'"

printf 'STAGING_SHADOW_DEPLOY_TRANSPORT=PASS\n'
printf 'STAGING_SHADOW_LOCAL_ARCHIVE=%s\n' "$STAGING_ARCHIVE"
printf 'STAGING_SHADOW_LOCAL_SHA256=%s\n' "$STAGING_SHA256"
printf 'STAGING_SHADOW_PRODUCTION_EXECUTED=NO\n'
