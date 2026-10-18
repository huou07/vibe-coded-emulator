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
# Apple Silicon uses 16 KiB VM pages. A default 4 KiB ad-hoc signature is
# rejected by dyld as "Invalid Page" before the core can start, so every
# native image in the staging bundle must use the host page granularity.
codesign --force --pagesize 16384 --sign - "$APP/Contents/Resources/azahar/macos-arm64/azahar_libretro.dylib"
codesign --force --pagesize 16384 --sign - "$APP/Contents/Resources/libretro/macos-arm64/mgba_libretro.dylib"
codesign --force --pagesize 16384 --sign - "$APP/Contents/Resources/libretro/macos-arm64/melondsds_libretro.dylib"
codesign --force --pagesize 16384 --sign - "$APP/Contents/Resources/azahar/macos-arm64/libMoltenVK.dylib"
# The Switch companion is a self-contained subprocess: sign it and the dylibs
# it bundles so the installed app can launch it without development paths.
if [[ -d "$APP/Contents/Resources/switch/macos-arm64" ]]; then
  for lib in "$APP/Contents/Resources/switch/macos-arm64/lib/"*.dylib; do
    [[ -e "$lib" ]] && codesign --force --pagesize 16384 --sign - "$lib"
  done
  switch_dir="$APP/Contents/Resources/switch/macos-arm64"
  companion="$switch_dir/an3_switch_companion"
  codesign --force --pagesize 16384 --sign - "$companion"
  chmod +x "$companion"
  # Ad-hoc signing changes the executable bytes. Refresh the bundled
  # provenance record before signing the outer app so the installed package's
  # manifest describes the actual companion it contains.
  node --input-type=module - "$switch_dir/manifest.json" "$companion" <<'NODE'
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
const [manifestPath, companionPath] = process.argv.slice(2);
const bytes = readFileSync(companionPath);
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
manifest.sha256 = createHash("sha256").update(bytes).digest("hex");
manifest.size = bytes.length;
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
NODE
else
  echo "WARNING: the Switch companion is not bundled; Switch will report unavailable." >&2
fi
codesign --force --deep --pagesize 16384 --entitlements "$ROOT/src-tauri/native-staging.entitlements" --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
# The mounted installer must offer the standard drag-to-install target.  Tauri's
# default DMG layout helper is unavailable here (no full Xcode), so assemble the
# volume explicitly: the signed app bundle plus an /Applications symlink,
# arranged with a clean Finder icon layout.  The app bundle is copied (never
# mutated) so its signature stays valid.
VOLUME_NAME="VibeCodedEmulator"
APP_NAME="$(basename "$APP")"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/an3-dmg.XXXXXX")"
STAGE="$WORK/stage"
RW_DMG="$WORK/an3-installer-rw.dmg"
mkdir -p "$STAGE"
DEV_ENTRY=""
cleanup_dmg() {
  if [[ -n "$DEV_ENTRY" ]]; then
    hdiutil detach "$DEV_ENTRY" >/dev/null 2>&1 || hdiutil detach "$DEV_ENTRY" -force >/dev/null 2>&1 || true
  fi
  rm -rf -- "$WORK"
}
trap cleanup_dmg EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "$VOLUME_NAME" -srcfolder "$STAGE" -ov -format UDRW -fs HFS+ "$RW_DMG" >/dev/null
# Mount at the standard /Volumes path so Finder can address the volume by name;
# a custom -mountpoint is invisible to Finder and breaks the layout AppleScript.
ATTACH_OUT="$(hdiutil attach "$RW_DMG" -nobrowse)"
DEV_ENTRY="$(printf '%s\n' "$ATTACH_OUT" | awk '/Apple_HFS|Apple_APFS/ {print $1; exit}')"
MOUNT_POINT="$(printf '%s\n' "$ATTACH_OUT" | grep -o '/Volumes/[^[:space:]]*' | head -1)"
[[ -n "$MOUNT_POINT" && -d "$MOUNT_POINT" ]] || { echo "Failed to mount the read-write installer image" >&2; exit 1; }
VOLUME_ACTUAL="$(basename "$MOUNT_POINT")"
LAYOUT=0
if osascript >/dev/null 2>&1 <<APPLESCRIPT
tell application "Finder"
  tell disk "$VOLUME_ACTUAL"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {120, 120, 680, 460}
    set opts to the icon view options of container window
    set arrangement of opts to not arranged
    set icon size of opts to 128
    set position of item "$APP_NAME" of container window to {160, 170}
    set position of item "Applications" of container window to {420, 170}
    close
    open
    update without registering applications
    delay 1
  end tell
end tell
APPLESCRIPT
then LAYOUT=1; fi
sync
hdiutil detach "$DEV_ENTRY" >/dev/null 2>&1 || hdiutil detach "$DEV_ENTRY" -force >/dev/null 2>&1 || true
DEV_ENTRY=""
hdiutil convert "$RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$OUTPUT" -ov >/dev/null
hdiutil verify "$OUTPUT"
if [[ "$LAYOUT" == "1" ]]; then
  echo "MACOS_DMG_LAYOUT=FINDER"
else
  echo "MACOS_DMG_LAYOUT=BASIC (Applications target present; Finder icon layout skipped)" >&2
fi
printf 'MACOS_DMG=%s\n' "$OUTPUT"
