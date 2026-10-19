#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Install the current Vibe Coded Emulator Linux DEB from the production release
# catalog. The catalog is the single source of truth for the artifact filename,
# architecture and SHA-256; nothing about a release is hardcoded here.
#
# Usage:
#   install-deb.sh [--dry-run] [--base-url URL] [--version] [--help]
set -euo pipefail

SCRIPT_NAME="install-deb.sh"
SCRIPT_VERSION="1.0.0"
BASE_URL="${AN3_BASE_URL:-}"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Install Vibe Coded Emulator from the production release catalog (Linux DEB).

Usage:
  install-deb.sh [options]

Options:
  --dry-run        Resolve and verify the package but do not install it.
  --base-url URL   Download site origin (for example the site you downloaded this
                   script from). Required unless AN3_BASE_URL is already set.
  --version        Print this script's version and exit.
  -h, --help       Show this help and exit.

The script downloads the DEB named by the production catalog, verifies its
SHA-256 against that catalog, and only then installs it with apt (or dpkg when
apt is unavailable). It never installs from an unverified file.
USAGE
}

log()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { printf 'install-deb: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --base-url) [[ -n "${2:-}" ]] || die "--base-url needs a value"; BASE_URL="${2%/}"; shift 2 ;;
    --version) printf '%s %s\n' "$SCRIPT_NAME" "$SCRIPT_VERSION"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
done

if [[ -z "$BASE_URL" ]]; then
  die "no download site set. Pass --base-url URL (or export AN3_BASE_URL). The Linux section of the download page shows the exact command for your site."
fi

[[ "$(uname -s)" == "Linux" ]] || die "this installer only supports Linux (detected: $(uname -s))"

case "$(uname -m)" in
  x86_64|amd64) ARCH="amd64" ;;
  *) die "this release publishes a Linux amd64 DEB only; detected architecture: $(uname -m)" ;;
esac

DOWNLOADER=""
if command -v curl >/dev/null 2>&1; then DOWNLOADER="curl"
elif command -v wget >/dev/null 2>&1; then DOWNLOADER="wget"
else die "curl or wget is required to download the package"; fi

fetch() {
  # fetch URL DEST
  if [[ "$DOWNLOADER" == "curl" ]]; then
    curl --fail --show-error --silent --location --max-time 600 --output "$2" "$1"
  else
    wget --quiet --tries=2 --timeout=60 --output-document="$2" "$1"
  fi
}

json_field() {
  # json_field FILE FORMAT KEY -> prints matching artifact's "filename", "sha256", "download_url"
  local file="$1" format="$2" key="$3" arch="$4"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$file" "$format" "$key" "$arch" <<'PY'
import json, sys
path, fmt, key, arch = sys.argv[1:5]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
for item in data.get("artifacts", []):
    if item.get("format") == fmt and item.get("architecture") in (arch, "x86_64", "amd64"):
        value = item.get(key)
        if value:
            print(value)
        sys.exit(0)
sys.exit(3)
PY
  elif command -v jq >/dev/null 2>&1; then
    jq -r --arg f "$format" --arg a "$arch" --arg k "$key" \
      '.artifacts[] | select(.format==$f) | select(.architecture==$a or .architecture=="x86_64" or .architecture=="amd64") | .[$k] // empty' \
      "$file" | head -n1
  else
    die "python3 or jq is required to read the release catalog"
  fi
}

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/an3-deb-install.XXXXXX")"
cleanup() { rm -rf -- "$WORKDIR"; }
trap cleanup EXIT

CATALOG="$WORKDIR/artifacts.json"
CATALOG_URL="$BASE_URL/download-app/artifacts.json"
log "Fetching release catalog: $CATALOG_URL"
fetch "$CATALOG_URL" "$CATALOG" || die "could not download the release catalog"

FILENAME="$(json_field "$CATALOG" DEB filename "$ARCH")" || die "no Linux DEB for $ARCH in the release catalog"
EXPECTED_SHA="$(json_field "$CATALOG" DEB sha256 "$ARCH")" || die "release catalog has no SHA-256 for the DEB"
DOWNLOAD_PATH="$(json_field "$CATALOG" DEB download_url "$ARCH" || true)"
[[ -n "$DOWNLOAD_PATH" ]] || DOWNLOAD_PATH="/download-app/release/$FILENAME"
if [[ "$DOWNLOAD_PATH" == http* ]]; then ARTIFACT_URL="$DOWNLOAD_PATH"; else ARTIFACT_URL="$BASE_URL${DOWNLOAD_PATH}"; fi

log "Release artifact: $FILENAME"
log "Downloading: $ARTIFACT_URL"
fetch "$ARTIFACT_URL" "$WORKDIR/$FILENAME" || die "could not download $FILENAME"

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA="$(sha256sum "$WORKDIR/$FILENAME" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  ACTUAL_SHA="$(shasum -a 256 "$WORKDIR/$FILENAME" | awk '{print $1}')"
else
  die "sha256sum or shasum is required to verify the download"
fi

if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  die "SHA-256 mismatch for $FILENAME (expected $EXPECTED_SHA, got $ACTUAL_SHA); refusing to install"
fi
log "SHA-256 verified: $ACTUAL_SHA"

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "Dry run: verified $FILENAME without installing."
  exit 0
fi

if command -v apt-get >/dev/null 2>&1 && command -v apt >/dev/null 2>&1; then
  log "Installing with apt (handles dependencies): $FILENAME"
  if [[ "$(id -u)" -eq 0 ]]; then apt install -y "$WORKDIR/$FILENAME"
  elif command -v sudo >/dev/null 2>&1; then sudo apt install -y "$WORKDIR/$FILENAME"
  else die "root or sudo is required to install the package"; fi
elif command -v dpkg >/dev/null 2>&1; then
  warn "apt is unavailable; falling back to dpkg -i (dependencies are not resolved automatically)"
  if [[ "$(id -u)" -eq 0 ]]; then dpkg -i "$WORKDIR/$FILENAME"
  elif command -v sudo >/dev/null 2>&1; then sudo dpkg -i "$WORKDIR/$FILENAME"
  else die "root or sudo is required to install the package"; fi
else
  die "neither apt nor dpkg is available; this system cannot install a DEB"
fi

log "Installed Vibe Coded Emulator. Launch it from your application menu or run: an3-offline-native"
