#!/usr/bin/env bash
# Builds the VibeCodedEmulator desktop shell for Linux on the authorized Linux
# runtime machine. The Tauri shell owns the local-ROM library and import UI and
# delegates gameplay to the bundled native SDL/GTK libretro player, so the DEB
# and Flatpak expose the same UI as the macOS and Windows applications. It is
# deliberately refusing a browser-only package: the native player contains the
# SDL window/input/audio adapters and the reusable Vulkan presenter, with
# desktop OpenGL available only for software cores.
set -euo pipefail

target="${1:-}"
case "$target" in deb|flatpak) ;; *) echo 'Usage: build-linux-staging.sh <deb|flatpak>' >&2; exit 2;; esac
[[ "$(uname -s)" == "Linux" ]] || { echo 'Linux native artifacts require a Linux builder.' >&2; exit 2; }
[[ "$(uname -m)" == "x86_64" ]] || { echo 'This staging package currently targets Linux x86_64.' >&2; exit 2; }

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build="$root/work/linux-build"
release="${AN3_RELEASE_DIR:-$root/releases}"
binary="$build/an3-offline-native"
core_dir="$root/vendor/libretro/linux-x86_64"
# Derive the artefact names from the desktop version field so a version bump can
# never publish under a stale filename.
version="$(node -p "require('$root/src-tauri/tauri.conf.json').version")"
deb_name="vibecodedemulator-${version}-linux-amd64.deb"
deb_path="$release/$deb_name"
# The Flatpak manifest intentionally consumes the DEB from this path inside
# the source tree.  A coordinated release may publish candidates elsewhere,
# so keep an exact, freshly built staging copy here for Flatpak's local source
# contract instead of allowing it to see a historical release artifact.
flatpak_deb_path="$root/releases/$deb_name"
flatpak_name="an3-offline-${version}-linux-amd64-staging.flatpak"

compiler="${CXX:-}"
if [[ -z "$compiler" ]]; then
  for candidate in c++ g++ clang++; do
    if command -v "$candidate" >/dev/null; then compiler="$candidate"; break; fi
  done
fi
[[ -n "$compiler" ]] || { echo 'Missing required C++20 compiler (c++, g++, or clang++).' >&2; exit 3; }
for command in node npm pkg-config dpkg-deb install; do
  command -v "$command" >/dev/null || { echo "Missing required Linux build command: $command" >&2; exit 3; }
done
pkg-config --exists sdl2 vulkan gtk+-3.0 || { echo 'Missing SDL2/Vulkan/GTK development packages.' >&2; exit 3; }
if [[ "$target" == "deb" ]]; then
  pkg-config --exists webkit2gtk-4.1 javascriptcoregtk-4.1 libsoup-3.0 || {
    echo 'Missing WebKitGTK 4.1 development packages required by the desktop shell.' >&2
    exit 3
  }
fi
[[ -f /usr/include/GL/gl.h ]] || { echo 'Missing desktop OpenGL development headers.' >&2; exit 3; }

node "$root/scripts/fetch-linux-gba-nds-libretro.mjs"
node "$root/scripts/fetch-azahar-desktop.mjs" linux-x86_64
node "$root/scripts/generate-player-ui.mjs" --check
[[ -f "$core_dir/mgba_libretro.so" && -f "$core_dir/melondsds_libretro.so" && -f "$core_dir/azahar_libretro.so" ]] || {
  echo 'Verified Linux GBA/NDS/3DS libretro cores are unavailable.' >&2
  exit 3
}

rm -rf "$build"
mkdir -p "$build" "$release"
# 1. The bundled native gameplay runtime (SDL window/input/audio + Vulkan/GL).
"$compiler" -std=c++20 -O2 -DNDEBUG -Wall -Wextra -Wpedantic \
  -I"$root/native-runtime" \
  "$root/native-runtime/core/libretro_host.cpp" \
  "$root/native-runtime/video/vulkan/vulkan_backend.cpp" \
  "$root/native-runtime/platform/linux/linux_runtime.cpp" \
  "$root/native-runtime/platform/linux/linux_controls.cpp" \
  "$root/native-runtime/platform/linux/sdl_audio_backend.cpp" \
  "$root/native-runtime/platform/linux/sdl_gl_backend.cpp" \
  $(pkg-config --cflags sdl2 vulkan gtk+-3.0) \
  $(pkg-config --libs sdl2 vulkan gtk+-3.0) -lGL -ldl -pthread -o "$binary"
# 2. Stage it plus the pinned cores as Tauri bundle resources.
node "$root/scripts/bundle-linux-runtime.mjs"
[[ -f "$root/vendor/runtime/linux-x86_64/manifest.json" ]] || {
  echo 'The staged Linux native runtime manifest is missing.' >&2
  exit 3
}

if [[ "$target" == "deb" ]]; then
  # 3. Build the Tauri desktop shell DEB. It embeds the prepared library/import
  # frontend and bundles the native player that was staged above.
  if [[ ! -d "$root/node_modules" ]]; then
    (cd "$root" && npm ci)
  fi
  # Never let a historical bundle be mistaken for this build: Tauri writes a
  # versioned filename and the previous release's DEB otherwise lingers here,
  # which a `find -quit` would happily reuse.
  rm -rf "$root/src-tauri/target/release/bundle/deb"
  (cd "$root" && npm run prepare-web && npm run tauri -- build --bundles deb)
  tauri_deb="$(find "$root/src-tauri/target/release/bundle/deb" -maxdepth 1 -name '*.deb' -print -quit)"
  [[ -f "$tauri_deb" ]] || { echo 'Tauri completed without its expected DEB.' >&2; exit 3; }
  install -m 0644 "$tauri_deb" "$deb_path"
  sha256sum "$deb_path" > "$deb_path.sha256"
  if [[ "$deb_path" != "$flatpak_deb_path" ]]; then
    mkdir -p "$(dirname "$flatpak_deb_path")"
    install -m 0644 "$deb_path" "$flatpak_deb_path"
    cmp -s "$deb_path" "$flatpak_deb_path" || {
      echo 'The Flatpak source DEB does not match the fresh staged DEB.' >&2
      exit 3
    }
  fi
  echo "LINUX_DEB=$deb_path"
  exit 0
fi

[[ -f "$deb_path" && -f "$flatpak_deb_path" ]] || {
  echo 'Build the verified DEB first: build-linux-staging.sh deb' >&2
  exit 3
}
cmp -s "$deb_path" "$flatpak_deb_path" || {
  echo 'The Flatpak source DEB is stale or differs from the selected staged DEB.' >&2
  exit 3
}
flatpak-builder --force-clean --disable-cache --repo="$build/flatpak-repo" \
  "$build/flatpak-build" "$root/flatpak/space.an3tocom.offline.yml"
flatpak build-bundle "$build/flatpak-repo" \
  "$release/$flatpak_name" \
  space.an3tocom.offline master \
  --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo
sha256sum "$release/$flatpak_name" > "$release/$flatpak_name.sha256"
echo "LINUX_FLATPAK=$release/$flatpak_name"
