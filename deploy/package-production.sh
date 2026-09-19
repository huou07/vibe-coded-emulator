#!/usr/bin/env bash
set -euo pipefail

# Create a production candidate containing reviewed application source and only
# the exact installers named in the verified release catalog.  The archive is
# an allowlist: runtime caches, ROM data, credentials, and historical releases
# never cross this boundary.

if [[ "$#" -ne 1 ]]; then
  echo "usage: package-production.sh /absolute/path/to/an3-arcade-production.tgz" >&2
  exit 2
fi

OUTPUT="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$OUTPUT" = /* ]] || { echo "Output path must be absolute." >&2; exit 2; }
[[ ! -e "$OUTPUT" ]] || { echo "Refusing to overwrite: $OUTPUT" >&2; exit 1; }

PAYLOAD="$(mktemp -d -t an3-arcade-production-payload.XXXXXX)"
SOURCE_ARCHIVE="$PAYLOAD/source.tar"
trap 'rm -rf -- "$PAYLOAD"' EXIT
python3 "$ROOT/tools/verify-release-catalog.py" --print-filenames > "$PAYLOAD/artifacts.txt"
NATIVE_ARTIFACTS=()
while IFS= read -r artifact; do NATIVE_ARTIFACTS+=("$artifact"); done < "$PAYLOAD/artifacts.txt"
rm -f -- "$PAYLOAD/artifacts.txt"

for artifact in "${NATIVE_ARTIFACTS[@]}"; do
  [[ -f "$ROOT/native-offline/releases/$artifact" && ! -L "$ROOT/native-offline/releases/$artifact" ]] || {
    echo "Verified production installer is unavailable: $artifact" >&2
    exit 1
  }
  [[ -f "$ROOT/native-offline/releases/$artifact.sha256" && ! -L "$ROOT/native-offline/releases/$artifact.sha256" ]] || {
    echo "Verified production installer sidecar is unavailable: $artifact" >&2
    exit 1
  }
done

# Netplay is staging-only. Keep it and all build outputs out of the payload.
COPYFILE_DISABLE=1 tar --no-xattrs \
  --exclude='deploy/enable-staging-netplay.sh' \
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
  -cf "$SOURCE_ARCHIVE" -C "$ROOT" app.py bug_report.py netcode.py sync_engine.py qrcodegen.py LICENSE THIRD_PARTY_NOTICES.md static deploy README.md tools/verify-release-catalog.py

tar -xf "$SOURCE_ARCHIVE" -C "$PAYLOAD"
install -d -m 0755 "$PAYLOAD/native-offline/releases"
install -m 0644 "$ROOT/native-offline/releases/catalog.json" "$PAYLOAD/native-offline/releases/catalog.json"
for artifact in "${NATIVE_ARTIFACTS[@]}"; do
  install -m 0644 "$ROOT/native-offline/releases/$artifact" "$PAYLOAD/native-offline/releases/$artifact"
  install -m 0644 "$ROOT/native-offline/releases/$artifact.sha256" "$PAYLOAD/native-offline/releases/$artifact.sha256"
done
rm -f -- "$SOURCE_ARCHIVE"
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$OUTPUT" -C "$PAYLOAD" .

# Fail closed for sensitive names and recognisable live credential shapes.
# Report only the archive member and generic class, never a matched value.
python3 - "$OUTPUT" <<'PY'
import re
import sys
import tarfile

archive = sys.argv[1]
blocked_name = re.compile(r"(^|/)(?:\.env(?:\..*)?|id_(?:rsa|ed25519|ecdsa|dsa)(?:\.pub)?|[^/]+\.(?:pem|key|p12|pfx|jks|keystore))$", re.I)
markers = (
    ("private-key", re.compile(br"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-access-key", re.compile(br"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(br"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("slack-token", re.compile(br"\bxox[baprs]-[A-Za-z0-9-]{15,}\b")),
    ("openai-token", re.compile(br"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
)
with tarfile.open(archive, "r:gz") as bundle:
    for member in bundle.getmembers():
        name = member.name.lstrip("./")
        if name.startswith("native-offline/releases/"):
            continue
        if name.startswith("._") or blocked_name.search(name):
            raise SystemExit(f"Sensitive filename in production archive: {name}")
        if not member.isfile() or member.size > 5 * 1024 * 1024:
            continue
        contents = bundle.extractfile(member).read()
        for label, marker in markers:
            if marker.search(contents):
                raise SystemExit(f"Credential-shaped content ({label}) in production archive member: {name}")
PY

tar -tzf "$OUTPUT" | grep -E '(^|/)\._|(^|/)\.DS_Store$' >/dev/null && {
  echo "AppleDouble or Finder metadata found in archive." >&2
  exit 1
} || true
if tar -tzf "$OUTPUT" | grep -Fqx 'deploy/enable-staging-netplay.sh'; then
  echo "Staging-only netplay helper was included in the production archive." >&2
  exit 1
fi
printf 'PRODUCTION_PACKAGE=PASS\n'
