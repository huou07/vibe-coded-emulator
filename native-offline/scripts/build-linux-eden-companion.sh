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
EDEN_PATH_MAP="-ffile-prefix-map=${HOME:?}=/an3-runner"

export AN3_EDEN_ROOT="$EDEN_ROOT" AN3_EDEN_COMMIT="$EDEN_COMMIT"
export AN3_EDEN_BRIDGE_ROOT="$(cd "$ROOT/../native/eden-bridge" && pwd)"
bash "$ROOT/scripts/prepare-eden-source.sh"
command -v cmake >/dev/null || { echo 'CMake is required for the Eden Linux companion.' >&2; exit 2; }
command -v ninja >/dev/null || { echo 'Ninja is required for the Eden Linux companion.' >&2; exit 2; }

if [[ ! -f "$EDEN_BUILD/CMakeCache.txt" ]]; then
  # This companion must use the system FFmpeg libraries declared by the Linux
  # package. Developer search paths can leak into ELF RUNPATH and break installs.
  env -u FFMPEG_DIR -u FFmpeg_DIR -u PKG_CONFIG_PATH -u PKG_CONFIG_LIBDIR \
    -u PKG_CONFIG_SYSROOT_DIR -u LD_LIBRARY_PATH -u LD_RUN_PATH -u CMAKE_PREFIX_PATH \
    -u CMAKE_LIBRARY_PATH -u CMAKE_INCLUDE_PATH -u LIBRARY_PATH -u CPATH \
    -u CPLUS_INCLUDE_PATH cmake -S "$EDEN_ROOT" -B "$EDEN_BUILD" -G Ninja \
      -DAN3_EDEN_BRIDGE_DIR="$ROOT/../native/eden-bridge" \
      -DENABLE_QT=OFF -DYUZU_CMD=OFF -DENABLE_LIBUSB=ON \
      -DENABLE_WERROR=OFF -DENABLE_DEBUG_TOOLS=OFF -DENABLE_RESHade=OFF \
      -DYUZU_USE_BUNDLED_SDL3=OFF -DCMAKE_BUILD_TYPE=Release \
      "-DCMAKE_C_FLAGS=$EDEN_PATH_MAP" "-DCMAKE_CXX_FLAGS=$EDEN_PATH_MAP" \
      -DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF -DCMAKE_EXPORT_PACKAGE_REGISTRY=OFF
fi

# Refuse to reuse a cache that could embed a developer path in ELF RUNPATH.
if grep -Eiq '^FFmpeg_(INCLUDE|LIBRARY)_[^:]*:.*=/(home|Users|root)/[^/]+/' \
    "$EDEN_BUILD/CMakeCache.txt"; then
  echo 'Eden cache has a developer-home FFmpeg path; choose a fresh AN3_EDEN_BUILD_ROOT.' >&2
  exit 2
fi
if ! grep -Fq -- "CMAKE_C_FLAGS:STRING=$EDEN_PATH_MAP" "$EDEN_BUILD/CMakeCache.txt" ||
   ! grep -Fq -- "CMAKE_CXX_FLAGS:STRING=$EDEN_PATH_MAP" "$EDEN_BUILD/CMakeCache.txt"; then
  echo 'Eden cache lacks the compiler source-path map; choose a fresh AN3_EDEN_BUILD_ROOT.' >&2
  exit 2
fi
env -u FFMPEG_DIR -u FFmpeg_DIR -u PKG_CONFIG_PATH -u PKG_CONFIG_LIBDIR \
  -u PKG_CONFIG_SYSROOT_DIR -u LD_LIBRARY_PATH -u LD_RUN_PATH -u CMAKE_PREFIX_PATH \
  -u CMAKE_LIBRARY_PATH -u CMAKE_INCLUDE_PATH -u LIBRARY_PATH -u CPATH \
  -u CPLUS_INCLUDE_PATH cmake --build "$EDEN_BUILD" --target an3_switch_companion -j "$JOBS"
AN3_SWITCH_COMPANION_BUILD="$EDEN_BUILD/bin/an3_switch_companion" \
  AN3_EDEN_ROOT="$EDEN_ROOT" AN3_EDEN_COMMIT="$EDEN_COMMIT" \
  node "$ROOT/scripts/prepare-switch-companion-linux.mjs"
