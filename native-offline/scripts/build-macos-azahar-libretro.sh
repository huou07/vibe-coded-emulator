#!/usr/bin/env bash
# Build the pinned Azahar libretro core with sanitized compiler paths.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="2126.1.2"
SOURCE_COMMIT="9e6f523a57fac9564ac0bf8286db3c3702d301ec"
JOBS="${AN3_AZAHAR_JOBS:-2}"
TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
WORK="$(mktemp -d "$TEMP_ROOT/an3-azahar-macos.XXXXXX")"
SOURCE="$WORK/source"
BUILD="$WORK/build"
trap 'rm -rf -- "$WORK"' EXIT

[[ "$(uname -s)" == Darwin ]] || { echo 'Pinned macOS Azahar build requires macOS.' >&2; exit 2; }
for tool in git cmake ninja lipo strip python3; do
  command -v "$tool" >/dev/null || { echo "Missing Azahar build prerequisite: $tool" >&2; exit 2; }
done

git clone --depth 1 --recurse-submodules --branch "$VERSION" \
  https://github.com/azahar-emu/azahar.git "$SOURCE"
ACTUAL_COMMIT="$(git -C "$SOURCE" rev-parse HEAD)"
[[ "$ACTUAL_COMMIT" == "$SOURCE_COMMIT" ]] || {
  echo "Azahar source commit mismatch: expected $SOURCE_COMMIT, received $ACTUAL_COMMIT" >&2
  exit 2
}

# Map every runner-owned checkout and temporary path before C++ embeds __FILE__
# strings or debug metadata into the distributed core.
PATH_MAP="-ffile-prefix-map=${HOME:?}=/an3-runner"
if [[ -n "${RUNNER_TEMP:-}" ]]; then
  PATH_MAP+=" -ffile-prefix-map=$RUNNER_TEMP=/an3-runner-temp"
fi
cmake -S "$SOURCE" -B "$BUILD" -G Ninja \
  -DENABLE_LIBRETRO=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=13.4 \
  "-DCMAKE_C_FLAGS=$PATH_MAP" \
  "-DCMAKE_CXX_FLAGS=$PATH_MAP"
cmake --build "$BUILD" --target citra_libretro --config Release --parallel "$JOBS"

CORE="$BUILD/bin/Release/azahar_libretro.dylib"
[[ -s "$CORE" ]] || { echo "Pinned Azahar build did not emit $CORE" >&2; exit 3; }
lipo -verify_arch arm64 "$CORE"
strip -x "$CORE"

python3 - "$SOURCE" "$CORE" "$ROOT/vendor/azahar/macos-arm64" "$SOURCE_COMMIT" "$VERSION" "$PATH_MAP" <<'PY'
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

source, core, destination = map(Path, sys.argv[1:4])
commit, version, path_map = sys.argv[4:]
license_bytes = (source / "license.txt").read_bytes()
license_sha = hashlib.sha256(license_bytes).hexdigest()
expected_license_sha = "a77e81713ddfe05f9f7f3a3c46de4147f82b5fe9d6e5e24af96e36a6de53f613"
if license_sha != expected_license_sha:
    raise SystemExit(f"Azahar license hash mismatch: {license_sha}")

submodules = []
status = subprocess.run(
    ["git", "-C", str(source), "submodule", "status", "--recursive"],
    check=True, text=True, stdout=subprocess.PIPE,
).stdout
for line in status.splitlines():
    match = re.fullmatch(r" ([0-9a-f]{40}) (.+)", line)
    if not match:
        raise SystemExit(f"Azahar submodule is missing or changed: {line[:160]}")
    submodules.append({"commit": match.group(1), "path": match.group(2)})

destination.mkdir(parents=True, exist_ok=True)
core_target = destination / "azahar_libretro.dylib"
license_target = destination / "LICENSE"
shutil.copy2(core, core_target)
license_target.write_bytes(license_bytes)
manifest = {
    "engine": "Azahar libretro",
    "version": version,
    "platform": "macOS arm64",
    "core": core_target.name,
    "sha256": hashlib.sha256(core_target.read_bytes()).hexdigest(),
    "sourceUrl": f"https://github.com/azahar-emu/azahar/tree/{commit}",
    "sourceCommit": commit,
    "buildMethod": "pinned-source",
    "buildTarget": "citra_libretro",
    "compilerPathMap": "runner-home=>/an3-runner; runner-temp=>/an3-runner-temp",
    "submodules": submodules,
    "licenseUrl": f"https://raw.githubusercontent.com/azahar-emu/azahar/{version}/license.txt",
    "licenseSha256": license_sha,
    "license": "GPL-2.0-or-later",
    "licenseName": license_target.name,
    "upstream": "https://github.com/azahar-emu/azahar",
}
(destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + chr(10), encoding="utf-8")
print(f"AZAHAR_SOURCE_BUILD=VERIFIED commit={commit} core_sha256={manifest['sha256']} submodules={len(submodules)}")
PY
