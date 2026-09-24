#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Build and run the deterministic native save round-trip test on macOS arm64.
set -euo pipefail
cd "$(dirname "$0")/.."

core="vendor/libretro/macos-arm64/mgba_libretro.dylib"
work="$(mktemp -d -t an3-save-test)"
rom="$work/an3-homebrew-test.gba"
savedir="$work/saves"
bin="$work/an3-native-save-roundtrip"
mkdir -p "$savedir"

[[ -f "$core" ]] || { echo "missing macOS mGBA core: $core" >&2; exit 3; }
python3 ../tools/testrom/gba_homebrew_test.py "$rom" >/dev/null

clang++ -std=c++20 -O1 -I native-runtime/core -I vendor/moltenvk/macos-arm64/include \
    tests/test_native_save_roundtrip.cpp native-runtime/core/libretro_host.cpp \
    -o "$bin"

"$bin" "$core" "$rom" "$savedir"
echo "NATIVE_SAVE_ROUNDTRIP=PASS"
