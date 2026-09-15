#!/usr/bin/env bash
set -euo pipefail

# One-time, staging-only host bootstrap.  Run this as root on the authorized
# staging host after copying the reviewed helper scripts there with the strict
# host-key control path.  It does not build/start containers or touch legacy
# application, SQLite, ROM, session, backup, or production paths.

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

assert_secure_root_env() {
  local file="$1" mode group_digit other_digit
  [[ -f "$file" && ! -L "$file" ]] || die "Staging shadow env file is unsafe: $file"
  [[ "$(stat -c '%U' -- "$file")" == root ]] || die "Staging shadow env file must be root-owned: $file"
  mode="$(stat -c '%a' -- "$file")" || die "Cannot read staging shadow env permissions: $file"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || die "Staging shadow env mode is invalid: $file"
  group_digit="${mode: -2:1}"
  other_digit="${mode: -1}"
  (( (10#$group_digit & 2) == 0 && (10#$other_digit & 2) == 0 )) \
    || die "Staging shadow env file must not be group- or other-writable: $file"
}

[[ "$(id -u)" -eq 0 ]] || die 'This helper bootstrap must run as root.'
[[ "$#" -le 1 ]] || { printf 'usage: install-rust-shadow-staging-helper.sh [source-directory]\n' >&2; exit 2; }

SOURCE_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
UPDATE_SOURCE="$SOURCE_DIR/update-rust-shadow-staging.sh"
ROLLBACK_SOURCE="$SOURCE_DIR/rollback-rust-shadow-staging.sh"

[[ -f "$UPDATE_SOURCE" ]] || die "Missing update helper: $UPDATE_SOURCE"
[[ -f "$ROLLBACK_SOURCE" ]] || die "Missing rollback helper: $ROLLBACK_SOURCE"

STATE_ROOT=/opt/an3-rust-shadow-staging
ENV_FILE=/etc/an3-rust-shadow-staging.env

install -d -o root -g root -m 0755 "$STATE_ROOT" "$STATE_ROOT/releases" "$STATE_ROOT/incoming"
install -o root -g root -m 0755 "$UPDATE_SOURCE" /usr/local/sbin/an3-rust-shadow-staging-release
install -o root -g root -m 0755 "$ROLLBACK_SOURCE" /usr/local/sbin/an3-rust-shadow-staging-rollback

# Do not overwrite a reviewed host configuration. Compose derives the gateway
# loopback bind from AN3_SHADOW_STAGE_PORT and pins Redis to 127.0.0.1:16379;
# neither listener is configurable through this file. The upstream remains the
# isolated legacy staging service, never production.
if [[ ! -e "$ENV_FILE" && ! -L "$ENV_FILE" ]]; then
  umask 027
  cat > "$ENV_FILE" <<'EOF'
# Root-owned configuration for the Rust gateway shadow on staging only.
AN3_SHADOW_STAGE_PORT=18093
AN3_GATEWAY_UPSTREAM=http://192.168.1.8:8092
AN3_GATEWAY_CACHE_TTL_SECONDS=60
AN3_GATEWAY_CACHE_MAX_BODY_BYTES=5242880
AN3_GATEWAY_CONNECT_TIMEOUT_SECONDS=5
AN3_GATEWAY_HEALTH_TIMEOUT_SECONDS=5
EOF
  chown root:root "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
fi

assert_secure_root_env "$ENV_FILE"

printf 'STAGING_SHADOW_HELPER_INSTALL=PASS\n'
printf 'STAGING_SHADOW_RELEASE_HELPER=%s\n' /usr/local/sbin/an3-rust-shadow-staging-release
printf 'STAGING_SHADOW_ROLLBACK_HELPER=%s\n' /usr/local/sbin/an3-rust-shadow-staging-rollback
printf 'STAGING_SHADOW_ENV=%s\n' "$ENV_FILE"
