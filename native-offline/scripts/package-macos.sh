#!/usr/bin/env bash
set -euo pipefail

# Tauri's default DMG layout helper needs full Xcode on this host. The app
# bundle itself is built by Tauri; this uses macOS' native disk-image utility
# to create the direct-download installer from that verified bundle.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/src-tauri/target/release/bundle/macos/VibeCodedEmulator.app"
# Derive the artefact name from the desktop version field so a version bump can
# never publish under a stale filename.
VERSION="$(node -p "require('./src-tauri/tauri.conf.json').version")"
OUTPUT="${AN3_RELEASE_DIR:-$ROOT/releases}/vibecodedemulator-${VERSION}-macos-aarch64.dmg"

[[ -d "$APP" ]] || { echo "macOS app bundle is unavailable: $APP" >&2; exit 1; }
mkdir -p "$(dirname "$OUTPUT")"
# The embedded graphics runtime is loaded from Resources at run time, so sign
# it explicitly before signing the outer bundle. This stays ad-hoc for staging;
# a release certificate/notarization is required before a public distribution.
codesign --force --sign - "$APP/Contents/Resources/azahar/macos-arm64/azahar_libretro.dylib"
codesign --force --sign - "$APP/Contents/Resources/libretro/macos-arm64/mgba_libretro.dylib"
codesign --force --sign - "$APP/Contents/Resources/libretro/macos-arm64/melondsds_libretro.dylib"
codesign --force --sign - "$APP/Contents/Resources/azahar/macos-arm64/libMoltenVK.dylib"
# The Switch companion is a self-contained subprocess: sign it and the dylibs
# it bundles so the installed app can launch it without development paths.
if [[ -d "$APP/Contents/Resources/switch/macos-arm64" ]]; then
  for lib in "$APP/Contents/Resources/switch/macos-arm64/lib/"*.dylib; do
    [[ -e "$lib" ]] && codesign --force --sign - "$lib"
  done
  codesign --force --sign - "$APP/Contents/Resources/switch/macos-arm64/an3_switch_companion"
  chmod +x "$APP/Contents/Resources/switch/macos-arm64/an3_switch_companion"
else
  echo "WARNING: the Switch companion is not bundled; Switch will report unavailable." >&2
fi
codesign --force --deep --entitlements "$ROOT/src-tauri/native-staging.entitlements" --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
hdiutil create -volname "VibeCodedEmulator" -srcfolder "$APP" -ov -format UDZO "$OUTPUT"
hdiutil verify "$OUTPUT"
printf 'MACOS_DMG=%s\n' "$OUTPUT"
