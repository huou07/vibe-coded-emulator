#!/usr/bin/env bash
# Build and stage the pinned Eden companion before the canonical macOS package.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
EDEN_COMMIT="${AN3_EDEN_COMMIT:-7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c}"
EDEN_ROOT="${AN3_EDEN_ROOT:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/an3-eden-$EDEN_COMMIT}"
EDEN_BUILD="${AN3_EDEN_BUILD_ROOT:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/an3-eden-build-$EDEN_COMMIT}"
JOBS="${AN3_EDEN_JOBS:-4}"
export AN3_EDEN_ROOT="$EDEN_ROOT" AN3_EDEN_COMMIT="$EDEN_COMMIT"
export AN3_EDEN_BRIDGE_ROOT="$REPO_ROOT/native/eden-bridge"

[[ "$(uname -s)" == Darwin ]] || { echo 'macOS Eden companion requires a macOS builder.' >&2; exit 2; }
for tool in cmake ninja autoconf automake glslang; do
  command -v "$tool" >/dev/null || { echo "Missing macOS Eden build prerequisite: $tool" >&2; exit 2; }
done

bash "$ROOT/scripts/prepare-eden-source.sh"
cmake -S "$EDEN_ROOT" -B "$EDEN_BUILD" -G Ninja \
  -DAN3_EDEN_BRIDGE_DIR="$AN3_EDEN_BRIDGE_ROOT" \
  -DENABLE_QT=OFF -DYUZU_CMD=OFF -DENABLE_LIBUSB=OFF \
  -DENABLE_WERROR=OFF -DENABLE_DEBUG_TOOLS=OFF -DENABLE_RESHade=OFF \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "$EDEN_BUILD" --target an3_switch_companion -j "$JOBS"

companion="$EDEN_BUILD/bin/an3_switch_companion"
[[ -f "$companion" ]] || { echo "Pinned Eden build did not emit $companion" >&2; exit 3; }
AN3_SWITCH_COMPANION_BUILD="$companion" \
AN3_EDEN_ROOT="$EDEN_ROOT" \
AN3_EDEN_COMMIT="$EDEN_COMMIT" \
  npm --prefix "$ROOT" run build
bash "$ROOT/scripts/package-macos.sh"
