#!/usr/bin/env bash
set -euo pipefail

# Create the reviewed, source-only artifact for the Rust shadow gateway.  This
# path intentionally excludes every legacy runtime/data path, including SQLite,
# ROMs, sessions, static PWA data, local build artifacts, and env files.

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

if [[ "$#" -ne 1 ]]; then
  printf 'usage: package-rust-shadow.sh /absolute/path/to/an3-rust-shadow-staging.tgz\n' >&2
  exit 2
fi

OUTPUT="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

[[ "$OUTPUT" = /* ]] || die 'Output path must be absolute.'
[[ ! -e "$OUTPUT" && ! -L "$OUTPUT" ]] || die "Refusing to overwrite: $OUTPUT"

required=(
  rust-gateway/Cargo.toml
  rust-gateway/Cargo.lock
  rust-gateway/src/lib.rs
  rust-gateway/src/main.rs
  rust-gateway/docker-healthcheck.sh
  rust-gateway/README.md
  Dockerfile.rust-gateway
  Dockerfile.rust-gateway.dockerignore
  compose.rust-shadow.staging.yml
  deploy/shadow/install-rust-shadow-staging-helper.sh
  deploy/shadow/update-rust-shadow-staging.sh
  deploy/shadow/rollback-rust-shadow-staging.sh
)

for path in "${required[@]}"; do
  [[ -f "$ROOT/$path" ]] || die "Required Rust shadow release file is missing: $path"
done

# A source artifact must never be a vehicle for local credentials or compiled
# output.  The runtime config belongs only to the root-owned host env file.
if find "$ROOT/rust-gateway" -type f \( -name '.env' -o -name '.env.*' -o -name '*.pem' -o -name '*.key' \) -print -quit | grep -q .; then
  die 'Refusing to package an env file or private key from rust-gateway.'
fi

COPYFILE_DISABLE=1 tar --no-xattrs \
  --exclude='rust-gateway/target' \
  --exclude='rust-gateway/target/*' \
  --exclude='**/.DS_Store' \
  --exclude='**/._*' \
  -czf "$OUTPUT" -C "$ROOT" \
  rust-gateway Dockerfile.rust-gateway Dockerfile.rust-gateway.dockerignore compose.rust-shadow.staging.yml deploy/shadow

archive_listing="$(tar -tzf "$OUTPUT")"
if printf '%s\n' "$archive_listing" | grep -Eq '(^|/)(\._|\.DS_Store|\.env($|\.)|target/)'; then
  die 'Refusing archive with metadata, env, or build-output files.'
fi

for path in "${required[@]}"; do
  printf '%s\n' "$archive_listing" | grep -Fxq "$path" || die "Archive is missing: $path"
done

printf 'SHADOW_SOURCE_ARCHIVE=%s\n' "$OUTPUT"
printf 'SHADOW_SOURCE_SHA256=%s\n' "$(sha256_file "$OUTPUT")"
