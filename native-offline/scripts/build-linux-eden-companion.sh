#!/usr/bin/env bash
# Configure and build the pinned Eden companion on the authorized Linux
# builder. This is deliberately separate from the libretro runtime build: the
# Switch core owns its own Vulkan window, input and audio path.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EDEN_COMMIT="${AN3_EDEN_COMMIT:-7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c}"
EDEN_ROOT="${AN3_EDEN_ROOT:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/an3-eden-$EDEN_COMMIT}"
EDEN_BUILD="${AN3_EDEN_BUILD_ROOT:-$ROOT/work/eden-linux-build}"
JOBS="${AN3_EDEN_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

export AN3_EDEN_ROOT="$EDEN_ROOT" AN3_EDEN_COMMIT="$EDEN_COMMIT"
export AN3_EDEN_BRIDGE_ROOT="$(cd "$ROOT/../native/eden-bridge" && pwd)"
bash "$ROOT/scripts/prepare-eden-source.sh"
command -v cmake >/dev/null || { echo 'CMake is required for the Eden Linux companion.' >&2; exit 2; }
command -v ninja >/dev/null || { echo 'Ninja is required for the Eden Linux companion.' >&2; exit 2; }

if [[ ! -f "$EDEN_BUILD/CMakeCache.txt" ]]; then
  cmake -S "$EDEN_ROOT" -B "$EDEN_BUILD" -G Ninja \
    -DAN3_EDEN_BRIDGE_DIR="$ROOT/../native/eden-bridge" \
    -DENABLE_QT=OFF -DYUZU_CMD=OFF -DENABLE_LIBUSB=ON \
    -DENABLE_WERROR=OFF -DENABLE_DEBUG_TOOLS=OFF -DENABLE_RESHade=OFF \
    -DYUZU_USE_BUNDLED_SDL3=OFF -DCMAKE_BUILD_TYPE=Release
fi
cmake --build "$EDEN_BUILD" --target an3_switch_companion -j "$JOBS"
AN3_SWITCH_COMPANION_BUILD="$EDEN_BUILD/bin/an3_switch_companion" \
  AN3_EDEN_ROOT="$EDEN_ROOT" AN3_EDEN_COMMIT="$EDEN_COMMIT" \
  node "$ROOT/scripts/prepare-switch-companion-linux.mjs"
