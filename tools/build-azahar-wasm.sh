#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Reproduce the browser 3DS core bundle (`latest/data-v2/cores/azahar-thread-wasm.data`).
#
# The bundle the browser runs is not built by this repository's normal toolchain:
# it is an EmulatorJS core archive produced by EmulatorJS's own build harness
# around an Azahar libretro core. This script pins every input so the artifact in
# `native-offline/.../assets/emulatorjs/` can be rebuilt byte-for-byte in
# principle, and so a future change to it is a diff of pinned revisions rather
# than an unexplained binary swap.
#
# Inputs (all upstream, none vendored by this script):
#   * EmulatorJS/azahar  @ 62cfcfb5e488f158f5f7ba83b725bb0ddd04da44  (base the
#     shipped 2.0.3 bundle was built from; carries the Emscripten patches)
#   * azahar-emu/azahar  @ 98932aee  FastInterp (upstream PR #2376), cherry-picked
#     onto that base — the shipped bundle has no interpreter other than DynCom
#   * EmulatorJS/RetroArch @ the revision in tools/azahar-wasm/retroarch-commit.txt
#     (the emscripten link harness that produces the .wasm/.js pair)
#   * emscripten 3.1.71
#
# The two patches in this directory are the complete local delta:
#   0001-upstream-fastinterp-98932ae.patch   the upstream interpreter, verbatim
#   0002-vce-web-backend-and-pacing.patch    backend selection + LCD pacing
#
# Usage:
#   tools/build-azahar-wasm.sh [work-dir]      # default work/azahar-wasm
#
# Requirements: network access, ~10 GB free disk, one build at a time. The build
# takes 20-40 minutes with -j6 and needs roughly 6 GB of RAM.
set -euo pipefail

WORK="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/work/azahar-wasm}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMSDK_VERSION=3.1.71
FORK=62cfcfb5e488f158f5f7ba83b725bb0ddd04da44
FASTINTERP=98932aee

die() { printf 'AZAHAR_WASM_BUILD=FAIL %s\n' "$*" >&2; exit 1; }
note() { printf 'AZAHAR_WASM_BUILD %s\n' "$*"; }

mkdir -p "$WORK"
export TMPDIR="$WORK/tmp"
mkdir -p "$TMPDIR"

if [ ! -d "$WORK/emsdk" ]; then
  note "installing emscripten $EMSDK_VERSION"
  git clone --depth 1 https://github.com/emscripten-core/emsdk "$WORK/emsdk"
  ( cd "$WORK/emsdk" && ./emsdk install "$EMSDK_VERSION" && ./emsdk activate "$EMSDK_VERSION" )
fi
# shellcheck disable=SC1091
source "$WORK/emsdk/emsdk_env.sh" >/dev/null 2>&1
command -v emcc >/dev/null || die "emcc is not on PATH after activating emsdk"

if [ ! -d "$WORK/ejs-azahar" ]; then
  note "fetching the EmulatorJS Azahar fork"
  git clone https://github.com/EmulatorJS/azahar "$WORK/ejs-azahar"
fi
cd "$WORK/ejs-azahar"
git fetch --depth 60 origin "$FORK" || die "cannot fetch the pinned fork commit"
git checkout -f "$FORK"
git submodule update --init --depth 1 --recursive
if ! git rev-parse --verify -q "$FASTINTERP" >/dev/null; then
  git remote add upstream https://github.com/azahar-emu/azahar 2>/dev/null || true
  git fetch --filter=blob:none upstream master
fi
# Apply the two patches only when the tree does not already carry them.
if ! grep -q "HAVE_FASTINTERP" src/core/CMakeLists.txt; then
  git apply "$HERE/azahar-wasm/0001-upstream-fastinterp-98932ae.patch" \
    || die "the FastInterp patch no longer applies to $FORK"
fi
if ! grep -q "CPU backend: FastInterp" src/core/core.cpp; then
  git apply "$HERE/azahar-wasm/0002-vce-web-backend-and-pacing.patch" \
    || die "the VCE backend/pacing patch no longer applies"
fi

note "configuring"
rm -rf build-emscripten
mkdir -p build-emscripten
emcmake cmake -S . -B build-emscripten \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-pthread -msimd128" \
  -DCMAKE_C_FLAGS="-pthread -msimd128" \
  -DENABLE_LIBRETRO=ON -DENABLE_QT=OFF -DENABLE_SDL2=OFF -DENABLE_TESTS=OFF \
  -DENABLE_CUBEB=OFF -DENABLE_OPENAL=OFF -DENABLE_VULKAN=OFF -DENABLE_LIBUSB=OFF \
  -DENABLE_SCRIPTING=OFF -DENABLE_WEB_SERVICE=OFF -DENABLE_SOFTWARE_RENDERER=OFF \
  -DENABLE_GENERIC=ON -DENABLE_LTO=OFF -DBUILD_SHARED_LIBS=OFF
emmake make -C build-emscripten -j"${JOBS:-6}"

note "merging the core archive"
cd build-emscripten
EXCLUDES="libCatch2.a libCatch2Main.a libCatch2WithMain.a libgtest.a libgtest_main.a libgmock.a libgmock_main.a"
{
  echo "create azahar_libretro_emscripten.a"
  find . -name '*.a' -not -path './CMakeFiles/*' -not -name azahar_libretro_emscripten.a | sort | while read -r a; do
    base="${a##*/}"; skip=0
    for ex in $EXCLUDES; do [ "$base" = "$ex" ] && skip=1 && break; done
    [ $skip -eq 0 ] && echo "addlib ${a#./}"
  done
  echo "save"; echo "end"
} > merge.mri
emar -M < merge.mri

note "linking with the EmulatorJS harness"
if [ ! -d "$WORK/ejs-retroarch" ]; then
  git clone --depth 1 https://github.com/EmulatorJS/RetroArch "$WORK/ejs-retroarch"
fi
mkdir -p "$WORK/EmulatorJS/data/cores"
cd "$WORK/ejs-retroarch"
PINNED_RA="$(cat "$HERE/azahar-wasm/retroarch-commit.txt" 2>/dev/null || true)"
if [ -n "$PINNED_RA" ]; then
  git fetch --depth 1 origin "$PINNED_RA" && git checkout -f "$PINNED_RA" \
    || note "WARNING: the pinned RetroArch revision is unavailable; using the clone HEAD"
fi
cp -f "$WORK/ejs-azahar/build-emscripten/azahar_libretro_emscripten.a" \
      emulatorjs/azahar_libretro_emscripten.bc
( cd emulatorjs && emmake ./build-emulatorjs.sh --threads )

note "packing"
# build-emulatorjs.sh removes the linked .js/.wasm after archiving them, so the
# fresh archive is unpacked, given the client-sized pthread pool the shipped glue
# uses, and repacked with the metadata and license the bundle carries.
STAGE="$WORK/pack"
rm -rf "$STAGE"; mkdir -p "$STAGE"
7z x -y -o"$STAGE" "$WORK/EmulatorJS/data/cores/azahar-thread-wasm.data" >/dev/null
python3 - "$STAGE" "$WORK" <<'PY'
import json, os, shutil, sys
stage, work = sys.argv[1], sys.argv[2]
js = os.path.join(stage, "azahar_libretro.js")
text = open(js, encoding="utf-8").read()
old = "pthreadPoolSize=32;"
new = "pthreadPoolSize=Math.max(2,Math.min((navigator.hardwareConcurrency||4)-1,16));"
if text.count(old) != 1:
    raise SystemExit(f"unexpected pthreadPoolSize occurrences: {text.count(old)}")
open(js, "w", encoding="utf-8").write(text.replace(old, new))
core = {
    "name": "azahar",
    "extensions": ["3ds", "cci", "cxi", "elf", "axf", "app"],
    "makeoptions": {
        "builder": "cmake",
        "cmake_build_dir": "build-emscripten",
        "cmake_args": [
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CXX_FLAGS=-pthread -msimd128",
            "-DCMAKE_C_FLAGS=-pthread -msimd128", "-DENABLE_LIBRETRO=ON", "-DENABLE_QT=OFF",
            "-DENABLE_SDL2=OFF", "-DENABLE_TESTS=OFF", "-DENABLE_CUBEB=OFF", "-DENABLE_OPENAL=OFF",
            "-DENABLE_VULKAN=OFF", "-DENABLE_LIBUSB=OFF", "-DENABLE_SCRIPTING=OFF",
            "-DENABLE_WEB_SERVICE=OFF", "-DENABLE_SOFTWARE_RENDERER=OFF",
            "-DENABLE_GENERIC=ON", "-DENABLE_LTO=OFF",
        ],
        "output_archive": "azahar_libretro_emscripten.a",
        "arguments": [],
    },
    "options": {"requireThreads": True, "requiresWebgl2": True, "supportsMouse": True, "useKeyboard": True},
    "license": "license.txt",
    "repo": "https://github.com/EmulatorJS/azahar",
}
json.dump(core, open(os.path.join(stage, "core.json"), "w"), indent=4)
json.dump({"minimumEJSVersion": "4.3.0", "version": os.environ.get("AZAHAR_BUNDLE_VERSION", "2.1.0")},
          open(os.path.join(stage, "build.json"), "w"), indent=4)
shutil.copyfile(os.path.join(work, "ejs-azahar", "license.txt"), os.path.join(stage, "license.txt"))
PY
cd "$STAGE"
rm -f "$WORK/azahar-thread-wasm.data"
7z a -t7z "$WORK/azahar-thread-wasm.data" ./azahar_libretro.js ./azahar_libretro.wasm ./core.json ./license.txt ./build.json >/dev/null
cd "$WORK"
sha256sum azahar-thread-wasm.data | tee azahar-thread-wasm.data.sha256
note "PASS"
note "Install it with tools/install-azahar-core.py, then update"
note "native-offline/shared/web-runtime-lock.json and the served report."
