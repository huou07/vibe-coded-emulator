#!/usr/bin/env bash
# Canonical, staging-only release-train entrypoint. It can either run on one
# matching host or coordinate a frozen source snapshot across the authorized
# Mac, Debian and Windows builders. It never deploys or publishes.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
native_root="$root/native-offline"
scope=""
command=""
platforms=()
coordinated=0
frozen_source=""

# These aliases are deliberately overridable for an authorized builder setup.
linux_builder="${AN3_LINUX_BUILDER:-build-host}"
windows_builder="${AN3_WINDOWS_BUILDER:-windows-build-host}"
ssh_cmd=(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes)
scp_cmd=(scp -o BatchMode=yes -o StrictHostKeyChecking=yes)

die() { printf '%s\n' "ERROR: $*" >&2; exit 2; }
note() { printf '%s\n' "$*"; }
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
require_command() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

usage() {
  cat <<'USAGE'
Usage: tools/release-train.sh --staging [--coordinated --frozen-source FILE] <freeze|verify|prepare|build> [web|macos|android|linux-deb|linux-flatpak|windows|all]

This is the one canonical staging-only release entrypoint for the
VibeCodedEmulator release train. `freeze` creates an immutable source and
verified web-dependency-cache snapshot. `--coordinated build all` extracts
that exact snapshot into isolated roots on the real Mac, Debian and Windows
builders, invokes the existing per-platform builders, and collects candidates
without deploying them. It never publishes, signs for production, or
substitutes a browser renderer for a native platform target.

freeze and coordinated build also write LICENSE_INVENTORY.json, sbom.cdx.json,
SHA256SUMS and a SECRET_SCAN.json secret/private-data report next to
SOURCE_FROZEN.json. Set AN3_REQUIRE_KNOWN_LICENSES=1 to fail the train when any
component still lacks a license, and AN3_REQUIRE_CLEAN_ARTIFACTS=1 to fail it
when the artifact scan reports a secret or private-data finding (publication
gates; both report-only by default).
USAGE
}

while (($#)); do
  case "$1" in
    --staging) scope="staging" ;;
    --coordinated) coordinated=1 ;;
    --frozen-source)
      shift
      (($#)) || die "--frozen-source needs a manifest path."
      frozen_source="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    freeze|verify|prepare|build)
      [[ -z "$command" ]] || die "Choose one command."
      command="$1"
      ;;
    web|macos|android|linux-deb|linux-flatpak|windows|all)
      platforms+=("$1")
      ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

[[ "$scope" == "staging" ]] || die "This release train is staging-only; pass --staging explicitly."
[[ -n "$command" ]] || die "Choose freeze, verify, prepare, or build."
((${#platforms[@]})) || platforms=(all)

host_kernel="$(uname -s)"
blocked=0
failed=0

run_verify() {
  PYTHONPYCACHEPREFIX="$root/work/release-train-pycache" \
    python3 -m unittest discover -s "$root/tests" -p 'test_*.py' -q
  node "$root/tests/web_nds_touch_behavior.test.js"
  node "$root/tests/web_renderer_behavior.test.js"
  npm --prefix "$native_root" run check
  git -C "$root" diff --check
}

run_prepare() {
  npm --prefix "$native_root" run prepare-web
}

verify_dependency_cache() {
  node - "$native_root" <<'NODE'
const {createHash} = require("crypto");
const {readFileSync} = require("fs");
const {join} = require("path");
const root = process.argv[2];
const lock = JSON.parse(readFileSync(join(root, "shared/web-runtime-lock.json"), "utf8"));
const cache = process.env.AN3_DEPENDENCY_CACHE || join(root, "work/dependency-cache");
for (const [name, expected] of Object.entries(lock)) {
  let bytes;
  try { bytes = readFileSync(join(cache, expected)); } catch { throw new Error(`Missing frozen dependency cache item: ${name}`); }
  const actual = createHash("sha256").update(bytes).digest("hex");
  if (actual !== expected) throw new Error(`Corrupt frozen dependency cache item: ${name}`);
}
NODE
}

build_macos() {
  if [[ "$host_kernel" != "Darwin" ]]; then note "MACOS_DMG=BLOCKED (requires a macOS builder)"; blocked=1; return; fi
  if ! npm --prefix "$native_root" run build:macos; then
    note "MACOS_DMG=FAILED (builder returned an error)"
    failed=1
  fi
}

build_android() {
  if [[ "$host_kernel" != "Darwin" ]]; then note "ANDROID_APK=BLOCKED (current Android staging builder is macOS)"; blocked=1; return; fi
  if ! bash "$native_root/scripts/build-android-staging.sh"; then
    note "ANDROID_APK=FAILED (builder returned an error)"
    failed=1
  fi
}

build_linux_deb() {
  if [[ "$host_kernel" != "Linux" ]]; then note "LINUX_DEB=BLOCKED (requires the authorized Linux builder)"; blocked=1; return; fi
  if ! bash "$native_root/scripts/build-linux-staging.sh" deb; then
    blocked=1
  fi
}

build_linux_flatpak() {
  if [[ "$host_kernel" != "Linux" ]]; then note "LINUX_FLATPAK=BLOCKED (requires the authorized Linux builder)"; blocked=1; return; fi
  if ! bash "$native_root/scripts/build-linux-staging.sh" flatpak; then
    blocked=1
  fi
}

build_windows() {
  case "$host_kernel" in
    MINGW*|MSYS*|CYGWIN*)
      if ! powershell -ExecutionPolicy Bypass -File "$native_root/scripts/build-windows-staging.ps1"; then
        note "WINDOWS_EXE=FAILED (builder returned an error)"
        failed=1
      fi
      ;;
    *) note "WINDOWS_EXE=BLOCKED (requires a real Windows builder)"; blocked=1 ;;
  esac
}

run_artifact_secret_scan() {
  # Byte-level secret/private-data scan of the evidence bundle and the built
  # artifacts. Writes SECRET_SCAN.json and never prints a matched value. Set
  # AN3_REQUIRE_CLEAN_ARTIFACTS=1 to make any finding fail the train
  # (default: report only, like the unknown-licence gate).
  local evidence_out="$1" artifact_dir="${2:-}"
  require_command python3
  [[ -f "$root/tools/release-artifact-scan.py" ]] || die "tools/release-artifact-scan.py is missing; cannot scan release artifacts."
  local targets=("$evidence_out")
  if [[ -n "$artifact_dir" && "$artifact_dir" != "$evidence_out" ]]; then
    targets+=("$artifact_dir")
  fi
  local report="$evidence_out/SECRET_SCAN.json" status=0
  python3 "$root/tools/release-artifact-scan.py" \
    --config "$root/tools/publication/.gitleaks.toml" \
    --json "$report" "${targets[@]}" || status=$?
  if ((status == 2)); then
    die "The artifact secret scan could not run; refusing to continue without it."
  fi
  if ((status == 1)); then
    if [[ "${AN3_REQUIRE_CLEAN_ARTIFACTS:-0}" == "1" ]]; then
      note "RELEASE_ARTIFACT_SCAN_GATE=FAIL; inspect $report and rotate any real credential before publication."
      exit 3
    fi
    note "RELEASE_ARTIFACT_SCAN=REPORT report=$report (advisory; set AN3_REQUIRE_CLEAN_ARTIFACTS=1 to fail the train)"
    return 0
  fi
  note "RELEASE_ARTIFACT_SCAN=CLEAN report=$report"
}

emit_release_evidence() {
  # Deterministic licence inventory, CycloneDX SBOM and SHA-256 manifest.
  # $1 frozen source tree to read, $2 output dir, $3 optional artifact dir,
  # $4 optional fixed SBOM timestamp. Set AN3_REQUIRE_KNOWN_LICENSES=1 to make
  # the unknown-licence publication gate fail the train (default: report only).
  local evidence_root="$1" out="$2" artifacts="${3:-}" timestamp="${4:-}"
  require_command python3
  [[ -f "$root/tools/release-evidence.py" ]] || die "tools/release-evidence.py is missing; cannot emit release evidence."
  [[ -d "$evidence_root" ]] || die "Release evidence source tree is unavailable: $evidence_root"
  local args=(--root "$evidence_root" --out "$out")
  if [[ -n "$artifacts" ]]; then args+=(--artifacts "$artifacts"); fi
  if [[ -n "$timestamp" ]]; then args+=(--timestamp "$timestamp"); fi
  if [[ "${AN3_REQUIRE_KNOWN_LICENSES:-0}" == "1" ]]; then
    args+=(--fail-on-unknown)
  fi
  mkdir -p "$out"
  python3 "$root/tools/release-evidence.py" "${args[@]}"
  run_artifact_secret_scan "$out" "$artifacts"
}

create_frozen_source() {
  [[ "$host_kernel" == "Darwin" ]] || die "Create the cross-host frozen snapshot on the authorized Mac builder."
  for tool in tar shasum node python3; do require_command "$tool"; done
  node "$native_root/scripts/generate-player-ui.mjs" --check
  verify_dependency_cache
  git -C "$root" diff --check
  local stamp evidence_timestamp freeze_dir source_archive cache_archive source_hash cache_hash manifest
  stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  # CycloneDX metadata.timestamp is ISO-8601; the directory stamp is not.
  evidence_timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  freeze_dir="${AN3_FREEZE_OUTPUT_DIR:-$root/work/release-train/source-freeze-$stamp}"
  [[ ! -e "$freeze_dir" ]] || die "Refusing to overwrite source freeze root: $freeze_dir"
  [[ -d "$native_root/work/dependency-cache" ]] || die "Verified dependency cache is missing; run the staging prepare step first."
  mkdir -p "$freeze_dir"
  source_archive="$freeze_dir/source.tar.gz"
  cache_archive="$freeze_dir/dependency-cache.tar.gz"
  (
    cd "$root"
    COPYFILE_DISABLE=1 tar -czf "$source_archive.partial" \
      --exclude='.DS_Store' \
      --exclude='*/__pycache__' \
      --exclude='native-offline/node_modules' \
      --exclude='native-offline/work' \
      --exclude='native-offline/releases' \
      --exclude='native-offline/dist' \
      --exclude='native-offline/src-tauri/target' \
      --exclude='native-offline/src-tauri/gen/android/app/src/main/assets' \
      --exclude='native-offline/src-tauri/gen/android/app/src/main/jniLibs' \
      --exclude='native-offline/src-tauri/gen/android/.gradle' \
      --exclude='native-offline/src-tauri/gen/android/buildSrc/.gradle' \
      --exclude='native-offline/src-tauri/gen/android/buildSrc/build' \
      --exclude='native-offline/src-tauri/gen/android/build' \
      --exclude='native-offline/src-tauri/gen/android/app/build' \
      --exclude='native-offline/src-tauri/gen/android/app/.cxx' \
      AGENTS.md README.md LICENSE THIRD_PARTY_NOTICES.md app.py .gitignore static tests tools native-offline native
    COPYFILE_DISABLE=1 tar -czf "$cache_archive.partial" native-offline/work/dependency-cache
  )
  mv "$source_archive.partial" "$source_archive"
  mv "$cache_archive.partial" "$cache_archive"
  source_hash="$(sha256 "$source_archive")"
  cache_hash="$(sha256 "$cache_archive")"
  manifest="$freeze_dir/SOURCE_FROZEN.json"
  python3 - "$manifest" "$source_archive" "$source_hash" "$cache_archive" "$cache_hash" <<'PY'
import json, sys
path, source, source_hash, cache, cache_hash = sys.argv[1:]
with open(path, "w", encoding="utf-8") as handle:
    json.dump({
        "version": 1,
        "sourceArchive": source,
        "sourceSha256": source_hash,
        "dependencyCacheArchive": cache,
        "dependencyCacheSha256": cache_hash,
    }, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
  note "SOURCE_FROZEN_MANIFEST=$manifest"
  note "SOURCE_FROZEN_SHA256=$source_hash"
  note "DEPENDENCY_CACHE_SHA256=$cache_hash"

  # Evidence must describe the frozen archive, not the mutable working tree, so
  # read the licence inputs straight out of the just-sealed source archive.
  local evidence_root="$freeze_dir/.frozen-source"
  [[ ! -e "$evidence_root" ]] || die "Refusing to overwrite evidence source root: $evidence_root"
  mkdir -p "$evidence_root"
  tar -xzf "$source_archive" -C "$evidence_root" \
    THIRD_PARTY_NOTICES.md \
    native-offline/package-lock.json \
    native-offline/src-tauri/Cargo.lock \
    native-offline/src-tauri/tauri.conf.json \
    native-offline/src-tauri/tauri.android.conf.json
  emit_release_evidence "$evidence_root" "$freeze_dir" "$freeze_dir" "$evidence_timestamp"
  rm -rf "$evidence_root"
  note "RELEASE_EVIDENCE_DIR=$freeze_dir"
}

read_frozen_source() {
  [[ -n "$frozen_source" ]] || die "--coordinated build requires --frozen-source from this script's freeze command."
  [[ -f "$frozen_source" ]] || die "Frozen source manifest is unavailable: $frozen_source"
  local fields
  fields="$(python3 - "$frozen_source" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
keys = ("sourceArchive", "sourceSha256", "dependencyCacheArchive", "dependencyCacheSha256")
values = []
for key in keys:
    value = data.get(key)
    if not isinstance(value, str) or not value or "\t" in value or "\n" in value:
        raise SystemExit(f"invalid frozen source manifest field: {key}")
    values.append(value)
print("\t".join(values))
PY
)"
  local source_archive source_hash cache_archive cache_hash
  IFS=$'\t' read -r source_archive source_hash cache_archive cache_hash <<< "$fields"
  [[ -f "$source_archive" && -f "$cache_archive" ]] || die "Frozen source archive or cache archive is unavailable."
  [[ "$(sha256 "$source_archive")" == "$source_hash" ]] || die "Frozen source archive hash does not match its manifest."
  [[ "$(sha256 "$cache_archive")" == "$cache_hash" ]] || die "Frozen dependency cache hash does not match its manifest."
  printf '%s\t%s\t%s\t%s\n' "$source_archive" "$source_hash" "$cache_archive" "$cache_hash"
}

extract_frozen_tree() {
  local destination="$1" source_archive="$2" cache_archive="$3"
  [[ ! -e "$destination" ]] || die "Refusing to overwrite frozen build root: $destination"
  mkdir -p "$destination"
  tar -xzf "$source_archive" -C "$destination"
  tar -xzf "$cache_archive" -C "$destination"
  [[ -f "$destination/native-offline/package.json" && -d "$destination/native-offline/work/dependency-cache" ]] || die "Frozen source extraction is incomplete."
}

windows_ps() {
  local host="$1" payload="$2" encoded
  encoded="$(printf '%s' "$payload" | python3 -c 'import base64, sys; print(base64.b64encode(sys.stdin.read().encode("utf-16le")).decode("ascii"))')"
  "${ssh_cmd[@]}" "$host" "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded"
}

coordinated_build_all() {
  [[ "$host_kernel" == "Darwin" ]] || die "The coordinated matrix starts on the authorized Mac builder."
  [[ "${#platforms[@]}" -eq 1 && "${platforms[0]}" == "all" ]] || die "--coordinated requires exactly 'build all' so every artifact uses one frozen source snapshot."
  for tool in ssh scp tar shasum node npm python3; do require_command "$tool"; done
  local frozen_fields source_archive source_hash cache_archive cache_hash
  frozen_fields="$(read_frozen_source)"
  IFS=$'\t' read -r source_archive source_hash cache_archive cache_hash <<< "$frozen_fields"
  local source_id attempt_id run_id run_root artifacts mac_source linux_root windows_root
  local evidence_timestamp
  source_id="${source_hash:0:16}"
  # CycloneDX metadata.timestamp is ISO-8601; the run id is not.
  evidence_timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # A frozen source snapshot can need a retry after a host-only interruption.
  # Keep every attempt isolated so a diagnostic root from the prior attempt
  # cannot become an input to the next one or prevent a clean retry.
  attempt_id="${AN3_COORDINATED_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
  [[ "$attempt_id" =~ ^[A-Za-z0-9._-]+$ ]] || die "AN3_COORDINATED_RUN_ID may contain only letters, digits, dot, underscore, and dash."
  run_id="$source_id-$attempt_id"
  run_root="${AN3_COORDINATED_OUTPUT_DIR:-$root/work/release-train/build-$run_id}"
  [[ ! -e "$run_root" ]] || die "Refusing to overwrite coordinated build root: $run_root"
  artifacts="$run_root/artifacts"
  mac_source="$run_root/macos-source"
  linux_root="/tmp/an3-release-train-$run_id"
  windows_root="C:/AN3/release-train-$run_id"
  mkdir -p "$artifacts"

  # Derive every expected artifact name from the version metadata the app actually
  # uses, so a version bump cannot silently leave a stale hard-coded filename in
  # the coordinated matrix. Android has its own version field.
  local desktop_version android_version
  desktop_version="$(node -p "require('$native_root/src-tauri/tauri.conf.json').version")"
  android_version="$(node -p "require('$native_root/src-tauri/tauri.android.conf.json').version")"
  local mac_name apk_name aab_name deb_name flatpak_name exe_name
  mac_name="vibecodedemulator-${desktop_version}-macos-aarch64.dmg"
  apk_name="vibecodedemulator-${android_version}-android-arm64-staging.apk"
  aab_name="vibecodedemulator-${android_version}-android-arm64-staging.aab"
  deb_name="vibecodedemulator-${desktop_version}-linux-amd64.deb"
  flatpak_name="an3-offline-${desktop_version}-linux-amd64-staging.flatpak"
  exe_name="vibecodedemulator-${desktop_version}-windows-x64-staging.exe"

  # Build the Mac artifacts from an extracted copy too: a later edit of the
  # working tree cannot silently alter a supposedly frozen matrix.
  extract_frozen_tree "$mac_source" "$source_archive" "$cache_archive"
  if [[ ! -d "$mac_source/native-offline/node_modules" ]]; then
    if [[ -d "$native_root/node_modules" ]]; then
      ln -s "$native_root/node_modules" "$mac_source/native-offline/node_modules"
    else
      (cd "$mac_source/native-offline" && npm ci)
    fi
  fi
  AN3_DEPENDENCY_CACHE="$mac_source/native-offline/work/dependency-cache" AN3_REQUIRE_DEPENDENCY_CACHE=1 \
    AN3_RELEASE_DIR="$artifacts" npm --prefix "$mac_source/native-offline" run build:macos
  AN3_DEPENDENCY_CACHE="$mac_source/native-offline/work/dependency-cache" AN3_REQUIRE_DEPENDENCY_CACHE=1 \
    AN3_RELEASE_DIR="$artifacts" bash "$mac_source/native-offline/scripts/build-android-staging.sh"

  # The remote roots are unique, never reuse a previous candidate, and receive
  # only the frozen source and verified dependency cache—not local build output.
  "${ssh_cmd[@]}" "$linux_builder" "test ! -e '$linux_root' && mkdir -p '$linux_root'"
  "${scp_cmd[@]}" "$source_archive" "$cache_archive" "$linux_builder:$linux_root/"
  "${ssh_cmd[@]}" "$linux_builder" "export PATH=\"\$HOME/.cargo/bin:\$PATH\" && cd '$linux_root' && tar -xzf source.tar.gz && tar -xzf dependency-cache.tar.gz && mkdir releases && AN3_DEPENDENCY_CACHE='$linux_root/native-offline/work/dependency-cache' AN3_REQUIRE_DEPENDENCY_CACHE=1 AN3_RELEASE_DIR='$linux_root/releases' bash native-offline/scripts/build-linux-staging.sh deb && AN3_DEPENDENCY_CACHE='$linux_root/native-offline/work/dependency-cache' AN3_REQUIRE_DEPENDENCY_CACHE=1 AN3_RELEASE_DIR='$linux_root/releases' bash native-offline/scripts/build-linux-staging.sh flatpak"
  "${scp_cmd[@]}" "$linux_builder:$linux_root/releases/$deb_name" "$artifacts/"
  "${scp_cmd[@]}" "$linux_builder:$linux_root/releases/$flatpak_name" "$artifacts/"

  local init_windows extract_windows
  init_windows=$(cat <<'PS'
$ErrorActionPreference = 'Stop'
$root = '__ROOT__'
if (Test-Path -LiteralPath $root) { throw "Refusing to overwrite coordinated Windows root: $root" }
New-Item -ItemType Directory -Path $root | Out-Null
PS
)
  init_windows="${init_windows//__ROOT__/$windows_root}"
  windows_ps "$windows_builder" "$init_windows"
  "${scp_cmd[@]}" "$source_archive" "$cache_archive" "$windows_builder:$windows_root/"
  extract_windows=$(cat <<'PS'
$ErrorActionPreference = 'Stop'
$root = '__ROOT__'
& tar.exe -xzf (Join-Path $root 'source.tar.gz') -C $root
if ($LASTEXITCODE -ne 0) { throw 'Cannot extract frozen source archive.' }
& tar.exe -xzf (Join-Path $root 'dependency-cache.tar.gz') -C $root
if ($LASTEXITCODE -ne 0) { throw 'Cannot extract frozen dependency cache archive.' }
$native = Join-Path $root 'native-offline'
$env:AN3_DEPENDENCY_CACHE = Join-Path $native 'work/dependency-cache'
$env:AN3_REQUIRE_DEPENDENCY_CACHE = '1'
if (!(Test-Path -LiteralPath $env:AN3_DEPENDENCY_CACHE)) { throw 'Frozen dependency cache is incomplete.' }
Push-Location $native
try {
  if (!(Test-Path -LiteralPath (Join-Path $native 'node_modules'))) {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Windows npm install failed.' }
  }
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $native 'scripts/build-windows-runtime.ps1')
  if ($LASTEXITCODE -ne 0) { throw 'Windows native runtime build failed.' }
  $env:AN3_RELEASE_DIR = Join-Path $root 'releases'
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $native 'scripts/build-windows-staging.ps1')
  if ($LASTEXITCODE -ne 0) { throw 'Windows NSIS build failed.' }
} finally {
  Pop-Location
}
PS
)
  extract_windows="${extract_windows//__ROOT__/$windows_root}"
  windows_ps "$windows_builder" "$extract_windows"
  "${scp_cmd[@]}" "$windows_builder:$windows_root/releases/$exe_name" "$artifacts/"

  local artifact expected
  for expected in "$mac_name" "$apk_name" "$aab_name" "$deb_name" "$flatpak_name" "$exe_name"; do
    artifact="$artifacts/$expected"
    [[ -s "$artifact" ]] || die "Expected coordinated artifact is missing: $artifact"
  done
  (
    cd "$artifacts"
    shasum -a 256 \
      "$mac_name" \
      "$apk_name" \
      "$aab_name" \
      "$deb_name" \
      "$flatpak_name" \
      "$exe_name" > ARTIFACTS.sha256
  )
  cp "$frozen_source" "$run_root/SOURCE_FROZEN.json"
  note "COORDINATED_SOURCE_SHA256=$source_hash"
  note "COORDINATED_RUN_ID=$run_id"
  note "COORDINATED_ARTIFACTS=$artifacts"

  # Preserve roots when diagnosing a failed build. A successful matrix has
  # already copied its candidates and manifests locally, so remove only these
  # exact disposable roots unless a release engineer explicitly retains them.
  if [[ "${AN3_KEEP_REMOTE_BUILD_ROOTS:-0}" != "1" ]]; then
    "${ssh_cmd[@]}" "$linux_builder" "rm -rf -- '$linux_root'"
    local cleanup_windows
    cleanup_windows=$(cat <<'PS'
$ErrorActionPreference = 'Stop'
$root = '__ROOT__'
if ($root -notlike 'C:/AN3/release-train-*') { throw 'Unexpected Windows disposable root.' }
Remove-Item -LiteralPath $root -Recurse -Force
PS
)
    cleanup_windows="${cleanup_windows//__ROOT__/$windows_root}"
    windows_ps "$windows_builder" "$cleanup_windows"
  fi

  # Emit the evidence bundle next to SOURCE_FROZEN.json after the disposable
  # remote roots are gone, so a failed publication gate cannot leak them.
  emit_release_evidence "$mac_source" "$run_root" "$artifacts" "$evidence_timestamp"
  note "RELEASE_EVIDENCE_DIR=$run_root"
}

if [[ "$command" == "freeze" ]]; then
  ((coordinated == 0)) || die "freeze already creates the portable snapshot; do not combine it with --coordinated."
  [[ "${#platforms[@]}" -eq 1 && "${platforms[0]}" == "all" ]] || die "freeze applies to the whole cross-platform source matrix; use 'freeze all'."
  create_frozen_source
  exit 0
fi

if ((coordinated)); then
  [[ "$command" == "build" ]] || die "--coordinated is only valid with build all."
  coordinated_build_all
  exit 0
fi

for requested in "${platforms[@]}"; do
  case "$requested" in
    all)
      case "$command" in
        verify) run_verify ;;
        prepare) run_prepare ;;
        build) build_macos; build_android; build_linux_deb; build_linux_flatpak; build_windows ;;
      esac
      ;;
    web)
      case "$command" in verify) run_verify;; prepare|build) run_prepare;; esac
      ;;
    macos|android|linux-deb|linux-flatpak|windows)
      case "$command" in
        verify) run_verify ;;
        prepare) run_prepare ;;
        build)
          case "$requested" in
            macos) build_macos ;;
            android) build_android ;;
            linux-deb) build_linux_deb ;;
            linux-flatpak) build_linux_flatpak ;;
            windows) build_windows ;;
          esac
          ;;
      esac
      ;;
  esac
done

((failed == 0)) || exit 4
((blocked == 0)) || exit 3
