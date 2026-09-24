#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Assembles the test-only macOS automation app used by `an3ctl` UI-driven E2E.
# It is the existing distribution .app with the `ui-control` cargo feature
# compiled into its executable and written to a *separate* bundle, so a release
# build is never overwritten. Distribution builds deliberately do not compile
# the bridge; never ship this app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${AN3_MACOS_APP:-$ROOT/src-tauri/target/release/bundle/macos/VibeCodedEmulator.app}"
BIN="$ROOT/src-tauri/target/release/an3-offline-native"
OUT="${AN3_AUTOMATION_APP:-$ROOT/src-tauri/target/release/bundle/macos/VibeCodedEmulatorAutomation.app}"

[[ -d "$APP" ]] || {
  echo "Distribution app bundle is unavailable: $APP (run npm run build:macos first)" >&2
  exit 1
}
[[ "$OUT" != "$APP" ]] || { echo "The automation bundle must not overwrite the distribution app." >&2; exit 1; }

cargo build --release --features ui-control --manifest-path "$ROOT/src-tauri/Cargo.toml"

python3 - "$BIN" <<'PY'
import sys
data = open(sys.argv[1], "rb").read()
if b"AN3_UI_CONTROL_FILE" not in data:
    raise SystemExit("the built executable does not expose the ui-control bridge")
PY

rm -rf "$OUT"
cp -R "$APP" "$OUT"
cp "$BIN" "$OUT/Contents/MacOS/an3-offline-native"
codesign --force --deep --sign - "$OUT"
codesign --verify --deep --strict --verbose=2 "$OUT"
printf 'MACOS_AUTOMATION_APP=%s\n' "$OUT"
