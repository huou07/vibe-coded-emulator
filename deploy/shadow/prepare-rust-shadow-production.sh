#!/usr/bin/env bash
set -euo pipefail

# Produce an auditable, source-identical production-review artifact whenever a
# staging candidate is prepared.  This script intentionally never contacts a
# production host, starts a production container, changes a tunnel, or writes
# production data.  The generated owner-run script remains gated for a future,
# separate explicit approval.

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

if [[ "$#" -ne 3 ]]; then
  printf 'usage: prepare-rust-shadow-production.sh /absolute/staging-source.tgz /absolute/artifact-dir YYYYMMDD-HHMMSS\n' >&2
  exit 2
fi

SOURCE_ARCHIVE="$1"
ARTIFACT_DIR="$2"
STAMP="$3"

[[ "$SOURCE_ARCHIVE" = /* && -f "$SOURCE_ARCHIVE" && ! -L "$SOURCE_ARCHIVE" ]] || die 'Source archive must be a regular file at an absolute path.'
[[ "$ARTIFACT_DIR" = /* && -d "$ARTIFACT_DIR" && ! -L "$ARTIFACT_DIR" ]] || die 'Artifact directory must be an existing non-symlink absolute directory.'
[[ "$STAMP" =~ ^[0-9]{8}-[0-9]{6}$ ]] || die 'Artifact stamp must be YYYYMMDD-HHMMSS.'

PRODUCTION_ARCHIVE="$ARTIFACT_DIR/an3-rust-shadow-production-candidate-$STAMP.tgz"
PRODUCTION_SCRIPT="$ARTIFACT_DIR/deploy-an3-rust-shadow-production-$STAMP.sh"
PRODUCTION_REVIEW="$ARTIFACT_DIR/an3-rust-shadow-production-review-$STAMP.txt"
[[ ! -e "$PRODUCTION_ARCHIVE" && ! -L "$PRODUCTION_ARCHIVE" ]] || die "Refusing to overwrite: $PRODUCTION_ARCHIVE"
[[ ! -e "$PRODUCTION_SCRIPT" && ! -L "$PRODUCTION_SCRIPT" ]] || die "Refusing to overwrite: $PRODUCTION_SCRIPT"
[[ ! -e "$PRODUCTION_REVIEW" && ! -L "$PRODUCTION_REVIEW" ]] || die "Refusing to overwrite: $PRODUCTION_REVIEW"

# The review artifact has byte-identical Rust/Docker source to the candidate
# sent to staging.  It is not copied to, or run against, production here.
cp -p -- "$SOURCE_ARCHIVE" "$PRODUCTION_ARCHIVE"
SOURCE_SHA256="$(sha256_file "$SOURCE_ARCHIVE")"
PRODUCTION_SHA256="$(sha256_file "$PRODUCTION_ARCHIVE")"
[[ "$SOURCE_SHA256" == "$PRODUCTION_SHA256" ]] || die 'Production review artifact checksum differs from its staging source artifact.'

{
  printf 'AN3 Rust shadow production review artifact\n'
  printf 'prepared_at=%s\n' "$STAMP"
  printf 'source_archive=%s\n' "$SOURCE_ARCHIVE"
  printf 'source_sha256=%s\n' "$SOURCE_SHA256"
  printf 'production_archive=%s\n' "$PRODUCTION_ARCHIVE"
  printf 'production_sha256=%s\n' "$PRODUCTION_SHA256"
  printf 'status=PREPARED_ONLY_NOT_EXECUTED\n'
  printf 'scope=source-identical review artifact; no production configuration, host, database, service, tunnel, or container was touched\n'
  printf 'approval=requires a fresh explicit owner approval and an owner-run production-specific helper in a separate future change\n'
} > "$PRODUCTION_REVIEW"

{
  printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' ''
  printf '%s\n' '# Prepared only. Codex never executes this file or contacts production.'
  printf 'ARCHIVE=%q\n' "$PRODUCTION_ARCHIVE"
  printf 'EXPECTED_SHA256=%q\n' "$PRODUCTION_SHA256"
  printf '%s\n' 'APPROVAL_TOKEN="${AN3_RUST_SHADOW_PRODUCTION_OWNER_APPROVAL:-}"'
  printf '%s\n' 'HELPER="${AN3_RUST_SHADOW_PRODUCTION_RELEASE_HELPER:-/usr/local/sbin/an3-rust-shadow-production-release}"'
  printf '%s\n' ''
  printf '%s\n' 'if [[ "$APPROVAL_TOKEN" != "EXPLICIT_OWNER_APPROVAL" ]]; then'
  printf '%s\n' '  echo "Production shadow artifact is prepared only; a fresh explicit owner approval is required." >&2'
  printf '%s\n' '  exit 64'
  printf '%s\n' 'fi'
  printf '%s\n' '[[ -x "$HELPER" ]] || { echo "Production-specific release helper is not installed: $HELPER" >&2; exit 65; }'
  printf '%s\n' 'echo "Owner-approved production invocation only; this path is outside the staging deployment workflow."'
  printf '%s\n' 'exec sudo -- "$HELPER" "$ARCHIVE" "$EXPECTED_SHA256"'
} > "$PRODUCTION_SCRIPT"
chmod 0700 "$PRODUCTION_SCRIPT"

printf 'PRODUCTION_SHADOW_RELEASE_READY=PASS\n'
printf 'PRODUCTION_SHADOW_ARTIFACT=%s\n' "$PRODUCTION_ARCHIVE"
printf 'PRODUCTION_SHADOW_RELEASE_SCRIPT=%s\n' "$PRODUCTION_SCRIPT"
printf 'PRODUCTION_SHADOW_REVIEW=%s\n' "$PRODUCTION_REVIEW"
printf 'PRODUCTION_SHADOW_ASSET=%s\n' "${PRODUCTION_SHA256:0:12}"
printf 'PRODUCTION_SHADOW_EXECUTED=NO\n'
