#!/usr/bin/env bash
set -euo pipefail

# Create the audited staging archive consumed by the staging rebuild/update
# scripts. It contains source plus only catalog-verified installers;
# historical release bytes never travel to staging again.

if [[ "$#" -ne 1 ]]; then
  echo "usage: package-staging.sh /absolute/path/to/an3-arcade-stage.tgz" >&2
  exit 2
fi

OUTPUT="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$OUTPUT" = /* ]] || { echo "Output path must be absolute." >&2; exit 2; }
[[ ! -e "$OUTPUT" ]] || { echo "Refusing to overwrite: $OUTPUT" >&2; exit 1; }

# Netplay deployment material is staging-only. It is intentionally excluded
# from the production package; ordinary player releases can still carry the
# reviewed relay manifest without enabling it.
PAYLOAD="$(mktemp -d -t an3-arcade-stage-payload.XXXXXX)"
SOURCE_ARCHIVE="$PAYLOAD/source.tar"
trap 'rm -rf -- "$PAYLOAD"' EXIT
python3 "$ROOT/tools/verify-release-catalog.py" --print-filenames > "$PAYLOAD/artifacts.txt"
NATIVE_ARTIFACTS=()
while IFS= read -r artifact; do NATIVE_ARTIFACTS+=("$artifact"); done < "$PAYLOAD/artifacts.txt"
rm -f -- "$PAYLOAD/artifacts.txt"

for artifact in "${NATIVE_ARTIFACTS[@]}"; do
  [[ -f "$ROOT/native-offline/releases/$artifact" && ! -L "$ROOT/native-offline/releases/$artifact" ]] || {
    echo "Verified staging installer is unavailable: $artifact" >&2
    exit 1
  }
done

COPYFILE_DISABLE=1 tar --no-xattrs \
  --exclude='native-offline/.gradle' \
  --exclude='native-offline/.signing' \
  --exclude='native-offline/dist' \
  --exclude='native-offline/work' \
  --exclude='*/work' \
  --exclude='*/__pycache__' \
  --exclude='*/.flatpak-builder' \
  --exclude='*/.cxx' \
  --exclude='native-offline/node_modules' \
  --exclude='native-offline/releases/*' \
  --exclude='native-offline/src-tauri/target' \
  --exclude='native-offline/src-tauri/gen/android/.gradle' \
  --exclude='native-offline/src-tauri/gen/android/build' \
  --exclude='native-offline/src-tauri/gen/android/app/build' \
  --exclude='native-offline/src-tauri/gen/android/local.properties' \
  --exclude='*.DS_Store' \
  -cf "$SOURCE_ARCHIVE" -C "$ROOT" app.py bug_report.py netcode.py sync_engine.py qrcodegen.py LICENSE THIRD_PARTY_NOTICES.md static deploy README.md \
  Dockerfile.rust-netplay Dockerfile.rust-netplay.dockerignore \
  compose.rust-netplay.staging.yml docs/netplay-staging.md docs/native-offline.md \
  native-offline
tar -xf "$SOURCE_ARCHIVE" -C "$PAYLOAD"
install -d -m 0755 "$PAYLOAD/native-offline/releases"
install -m 0644 "$ROOT/native-offline/releases/catalog.json" "$PAYLOAD/native-offline/releases/catalog.json"
for artifact in "${NATIVE_ARTIFACTS[@]}"; do
  install -m 0644 "$ROOT/native-offline/releases/$artifact" "$PAYLOAD/native-offline/releases/$artifact"
  install -m 0644 "$ROOT/native-offline/releases/$artifact.sha256" "$PAYLOAD/native-offline/releases/$artifact.sha256"
done
rm -f -- "$SOURCE_ARCHIVE"
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$OUTPUT" -C "$PAYLOAD" .
tar -tzf "$OUTPUT" | grep -E '(^|/)\._|(^|/)\.DS_Store$' >/dev/null && {
  echo "AppleDouble or Finder metadata found in archive." >&2
  exit 1
} || true
