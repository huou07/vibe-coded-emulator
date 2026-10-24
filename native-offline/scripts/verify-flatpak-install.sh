#!/usr/bin/env bash
# Verify the exact single-file Flatpak from a clean, disposable user install.
# The bundle must carry its runtime repository so an ordinary Linux Mint-style
# Flatpak install can acquire org.gnome.Platform instead of relying on a
# builder's pre-existing runtime cache.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(node -p "require('$root/src-tauri/tauri.conf.json').version")"
bundle="${1:-$root/releases/an3-offline-${version}-linux-amd64-staging.flatpak}"
app_id="space.an3tocom.offline"

[[ -f "$bundle" && ! -L "$bundle" ]] || { echo "Flatpak bundle is unavailable: $bundle" >&2; exit 2; }
command -v flatpak >/dev/null || { echo "Flatpak is required for installation verification." >&2; exit 2; }

verification_root="$(mktemp -d -t an3-flatpak-install.XXXXXX)"
cleanup() { rm -rf -- "$verification_root"; }
trap cleanup EXIT

export XDG_DATA_HOME="$verification_root/data"
export XDG_CACHE_HOME="$verification_root/cache"
mkdir -p "$XDG_DATA_HOME" "$XDG_CACHE_HOME"

flatpak --user install --noninteractive "$bundle"
flatpak --user info "$app_id" >/dev/null
flatpak run --command=an3-native-player "$app_id" --help >/dev/null
echo "FLATPAK_CLEAN_INSTALL=PASS"

# A caller that supplies a legal local test ROM gets an actual native runtime
# smoke after the clean installation. A timeout is expected: the emulator is
# still running, which proves launch rather than merely argument parsing.
if [[ -n "${AN3_FLATPAK_SMOKE_ROM:-}" ]]; then
  [[ -f "$AN3_FLATPAK_SMOKE_ROM" ]] || { echo "Configured Flatpak smoke ROM is unreadable." >&2; exit 2; }
  command -v timeout >/dev/null || { echo "timeout is required for Flatpak runtime smoke." >&2; exit 2; }
  command -v xvfb-run >/dev/null || { echo "xvfb-run is required for Flatpak runtime smoke." >&2; exit 2; }
  smoke_system="${AN3_FLATPAK_SMOKE_SYSTEM:-gba}"
  smoke_renderer="${AN3_FLATPAK_SMOKE_RENDERER:-opengl}"
  set +e
  timeout 15s xvfb-run -a flatpak run --command=an3-native-player --env=SDL_AUDIODRIVER=dummy "$app_id" \
    --rom "$AN3_FLATPAK_SMOKE_ROM" --system "$smoke_system" --renderer "$smoke_renderer"
  smoke_status=$?
  set -e
  [[ "$smoke_status" -eq 124 ]] || { echo "Flatpak runtime ended unexpectedly: $smoke_status" >&2; exit "$smoke_status"; }
  echo "FLATPAK_RUNTIME_SMOKE=PASS"
fi
