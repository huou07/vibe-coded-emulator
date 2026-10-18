#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build a clean, sanitized public source snapshot from this repository.
#
# The snapshot contains only product source: no private development history,
# no AI/agent configuration, no staging reports, no vendored core binaries, no
# release artifacts, and no personal data or private infrastructure values.
#
# Usage: tools/build-public-snapshot.sh [OUTPUT_DIR]
# Default OUTPUT_DIR: <repo>/work/public-snapshot (git-ignored)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/work/public-snapshot"
TEMPLATES="$ROOT/tools/publication"

usage() {
  cat <<'USAGE'
Usage: tools/build-public-snapshot.sh [--output DIR]

  --output DIR   where to write the snapshot (default: work/public-snapshot)
  -h, --help     show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) [[ -n "${2:-}" ]] || { printf 'ERROR: --output needs a directory\n' >&2; exit 2; }; OUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) printf 'ERROR: unknown option: %s\n' "$1" >&2; exit 2 ;;
    *) OUT="$1"; shift ;;
  esac
done

die() { printf 'BUILD_SNAPSHOT=FAIL %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

[[ -d "$TEMPLATES" ]] || die "publication templates are missing: tools/publication"

note "output=$OUT"
rm -rf "$OUT"
mkdir -p "$OUT"

# --- 1. Product source at the repository root ---------------------------------
for file in app.py netcode.py qrcodegen.py \
            LICENSE THIRD_PARTY_NOTICES.md README.md .gitignore; do
  [[ -f "$ROOT/$file" ]] || die "missing source file: $file"
  cp "$ROOT/$file" "$OUT/"
done
# Application modules vary by product generation. Include the first-party
# modules present in this checkout without requiring obsolete modules that a
# newer app.py no longer imports.
for file in bug_report.py sync_engine.py; do
  [[ -f "$ROOT/$file" ]] && cp "$ROOT/$file" "$OUT/"
done
mkdir -p "$OUT/static" "$OUT/tests" "$OUT/native" "$OUT/rust-gateway" "$OUT/docs"
cp -R "$ROOT/static/." "$OUT/static/"
cp -R "$ROOT/tests/." "$OUT/tests/"
cp -R "$ROOT/native/." "$OUT/native/"
cp -R "$ROOT/rust-gateway/." "$OUT/rust-gateway/"
# Python bytecode caches can embed the developer's absolute source paths and
# are not source; never carry them into the sanitized public candidate.
find "$OUT" -type d -name '__pycache__' -prune -exec rm -rf {} +

# --- 2. Native project: source only -------------------------------------------
mkdir -p "$OUT/native-offline"
for item in src-tauri native-runtime scripts web shared tests flatpak; do
  [[ -e "$ROOT/native-offline/$item" ]] || continue
  if [[ "$item" == "src-tauri" ]]; then
    # `src-tauri/target` is a multi-gigabyte Rust build tree that this snapshot
    # deletes again below. Copying it first fills a workstation's scratch space
    # for nothing, and a full disk fails the candidate build with `cp: No space
    # left on device` instead of the assertion the test is actually making, so
    # exclude it at copy time and keep the same result.
    mkdir -p "$OUT/native-offline/$item"
    ( cd "$ROOT/native-offline/src-tauri" && tar --exclude='./target' -cf - . ) \
      | ( cd "$OUT/native-offline/$item" && tar -xf - )
  else
    cp -R "$ROOT/native-offline/$item" "$OUT/native-offline/$item"
  fi
done
for file in package.json package-lock.json THIRD_PARTY_NOTICES.md .gitignore patches; do
  [[ -e "$ROOT/native-offline/$file" ]] && cp -R "$ROOT/native-offline/$file" "$OUT/native-offline/"
done

# Generated scaffolding and caches, plus vendored third-party binaries, are not
# public source: the build scripts fetch/verify them.
rm -rf "$OUT/native-offline/src-tauri/target" \
       "$OUT/native-offline/src-tauri/gen/android/build" \
       "$OUT/native-offline/src-tauri/gen/android/app/build" \
       "$OUT/native-offline/src-tauri/gen/android/.gradle" \
       "$OUT/native-offline/native-runtime/vendor" \
       "$OUT/native-offline/dist" 2>/dev/null || true
find "$OUT/native-offline" -name 'local.properties' -delete 2>/dev/null || true

# Linux core fetchers reuse the verified upstream license texts from the
# macOS vendor cache. Keep those text files in a clean source snapshot without
# copying any vendored core binaries.
license_source="$ROOT/native-offline/vendor/libretro/macos-arm64"
license_destination="$OUT/native-offline/vendor/libretro/macos-arm64"
mkdir -p "$license_destination"
for license in mGBA-MPL-2.0.txt melonDS-DS-GPL-3.0-or-later.txt; do
  license_path="native-offline/vendor/libretro/macos-arm64/$license"
  if [[ -f "$license_source/$license" ]]; then
    cp "$license_source/$license" "$license_destination/$license"
  else
    # A linked worktree can inherit sparse-checkout rules that leave these
    # tracked text files absent from disk. Recover only an exact skip-worktree
    # path from HEAD; ordinary missing/deleted files remain a hard failure.
    index_tag="$(git -C "$ROOT" ls-files -t -- "$license_path" 2>/dev/null | cut -c1)"
    [[ "$index_tag" == "S" ]] || die "missing upstream core license: $license"
    git -C "$ROOT" show "HEAD:$license_path" > "$license_destination/$license" \
      || die "cannot recover sparse upstream core license: $license"
  fi
done

# Keep only the product-specific Android files; the rest is regenerated by
# `tauri android init`.
if [[ -d "$OUT/native-offline/src-tauri/gen" ]]; then
  keep="$(mktemp -d)"
  for path in \
    "gen/schemas" \
    "gen/android/app/src/main/java/space/an3tocom/offline" \
    "gen/android/app/src/main/AndroidManifest.xml" \
    "gen/android/app/src/main/res" \
    "gen/android/app/build.gradle.kts" \
    "gen/android/app/proguard-rules.pro" \
    "gen/android/app/src/main/assets/index.html" \
    "gen/android/app/src/main/assets/native-app.js" \
    "gen/android/app/src/main/assets/native-bootstrap.js" \
    "gen/android/app/src/main/assets/native-support.js" \
    "gen/android/app/src/main/assets/native.css" \
    "gen/android/app/src/main/assets/static/offline.js" \
    "gen/android/app/src/main/assets/static/player.js" \
    "gen/android/app/src/main/assets/static/site.js" \
    "gen/android/app/src/main/assets/static/site.css"; do
    if [[ -e "$OUT/native-offline/src-tauri/$path" ]]; then
      mkdir -p "$keep/$(dirname "$path")"
      cp -R "$OUT/native-offline/src-tauri/$path" "$keep/$path"
    fi
  done
  rm -rf "$OUT/native-offline/src-tauri/gen"
  mkdir -p "$OUT/native-offline/src-tauri"
  cp -R "$keep/gen" "$OUT/native-offline/src-tauri/gen"
  rm -rf "$keep"
fi

# --- 3. Deployment/build scripts (sanitized; required for GPL source) ---------
mkdir -p "$OUT/tools" "$OUT/deploy"
# Exclude the owner-only shadow tree at copy time. Copying deploy/ first and
# deleting deploy/shadow afterwards fails outright for a worker UID that cannot
# read the directory at all, which is how this snapshot is built off-CI.
( cd "$ROOT/deploy" && tar --exclude='./shadow' -cf - . ) | ( cd "$OUT/deploy" && tar -xf - )
rm -rf "$OUT/tools/ssh" 2>/dev/null || true
cp "$ROOT/tools/verify-release-catalog.py" "$OUT/tools/"
for file in disk-preflight.sh disk-preflight.ps1; do
  [[ -f "$ROOT/tools/$file" ]] || die "missing build helper: tools/$file"
  cp "$ROOT/tools/$file" "$OUT/tools/"
done
# This line ships a packaged Windows NDS smoke script; a published candidate that
# omitted it would leave the hosted Windows lane calling a file it does not have.
[[ -f "$ROOT/tools/windows-nds-runtime-smoke.ps1" ]] && cp "$ROOT/tools/windows-nds-runtime-smoke.ps1" "$OUT/tools/"
if [[ -d "$ROOT/tools/android" ]]; then
  cp -R "$ROOT/tools/android" "$OUT/tools/android"
  # The operator README documents the private staging harness: owner SSH key
  # filenames, a legacy checkout path and the staging host. None of it is usable
  # to a public reader, and it is exactly the private-infrastructure guidance the
  # publication gate forbids, so it is not published. The scripts stay, because
  # they are part of the build tooling.
  rm -f "$OUT/tools/android/README.md"
fi

# --- 4. Curated documentation -------------------------------------------------
mkdir -p "$OUT/docs/architecture" "$OUT/docs/licensing"
for file in licensing/license-audit.md licensing/distribution-compliance.md \
            licensing/eden-integration-feasibility.md; do
  [[ -f "$ROOT/docs/$file" ]] && cp "$ROOT/docs/$file" "$OUT/docs/$file"
done
[[ -f "$ROOT/docs/BUILD_STORAGE.md" ]] && cp "$ROOT/docs/BUILD_STORAGE.md" "$OUT/docs/BUILD_STORAGE.md"
for file in player-layering.md design-system.md; do
  [[ -f "$ROOT/docs/$file" ]] && cp "$ROOT/docs/$file" "$OUT/docs/architecture/$file"
done
cp -R "$TEMPLATES/docs/." "$OUT/docs/"

# --- 5. Overlay the publication templates ------------------------------------
cp "$TEMPLATES/CONTRIBUTING.md" "$TEMPLATES/SECURITY.md" \
   "$TEMPLATES/.gitleaks.toml" "$TEMPLATES/PROVENANCE.md" "$OUT/"
cp "$TEMPLATES/env.example.template" "$OUT/.env.example"
mkdir -p "$OUT/.github/workflows"
cp "$TEMPLATES/.github/workflows/ci.yml" "$OUT/.github/workflows/ci.yml"
# No native package workflow is published. The former native-build.yml invoked
# tools/release-train.sh, which is a private staging entrypoint that needs
# dedicated SSH builders and pinned core artifacts; the snapshot carries neither,
# so the published jobs could only fail. Cross-platform packaging stays with the
# private release train and its builders, and publication-check.sh now asserts
# that any workflow it does publish only calls scripts the candidate contains.
if [[ -e "$TEMPLATES/.github/workflows/native-build.yml" ]]; then
  die "tools/publication/.github/workflows/native-build.yml reappeared; either make it runnable from the candidate or leave it out"
fi

# --- 6. Sanitize personal data and private infrastructure --------------------
python3 - "$OUT" "$ROOT" <<'PY'
import pathlib, re, subprocess, sys, datetime

out = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2])

patterns = [
    (re.compile(r"/Users/meomeo/Documents/edit an3tocom apps&web"), "<PROJECT_ROOT>"),
    (re.compile(r"/Users/meomeo/Documents/Codex/[^\s\"')\]]*"), "<LEGACY_CHECKOUT>"),
    (re.compile(r"/Users/meomeo/([A-Za-z0-9._/-]*)"), r"~/<REDACTED_PATH>"),
    (re.compile(r"/Users/meomeo"), "~"),
    (re.compile(r"192\.168\.1\.(\d{1,3})"), r"192.0.2.\1"),
    (re.compile(r"192\.168\.251\.(\d{1,3})"), r"192.0.2.\1"),
    (re.compile(r"an3tocom\.space"), "example.com"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail)\.[A-Za-z]{2,}"), "YOUR_EMAIL@example.com"),
    (re.compile(r"an3_codex_ed25519"), "YOUR_SSH_KEY"),
    (re.compile(r"\ban3-dell\b"), "build-host"),
    (re.compile(r"\ban3-win11-build\b"), "windows-build-host"),
    (re.compile(r"\bhuou07\b"), "YOUR_GITHUB_USER"),
    (re.compile(r"\bmeomeo\b"), "developer"),
]
binary_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff2", ".ttf", ".icns", ".dll", ".dylib", ".so", ".bin"}

changed = 0
for path in out.rglob("*"):
    if not path.is_file() or path.suffix.lower() in binary_suffixes:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    original = text
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        changed += 1

revision = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip() or "unknown"
today = datetime.date.today().isoformat()
provenance = out / "PROVENANCE.md"
provenance.write_text(provenance.read_text(encoding="utf-8")
                      .replace("SNAPSHOT_DATE", today)
                      .replace("SOURCE_REVISION", revision), encoding="utf-8")
print(f"sanitized files: {changed}; revision: {revision}")
PY

# --- 7. Fail if any personal/infrastructure pattern survived ------------------
# A grep error must not read as "nothing survived sanitisation". Absolute host
# paths and `~/` are included here: a home directory that resolves on one machine
# does not resolve anywhere else, and it describes a person's layout. The
# publication gate scans for the same patterns on its own copy of the candidate.
# `-I` skips binary assets, whose byte streams can contain any pattern by chance;
# text leaks are still caught, and the gate's own scan ignores binaries too.
survivor_error=""
survivors="$(grep -rlIE "/Users/[A-Za-z]|/home/[A-Za-z0-9._-]+/|(^|[^A-Za-z0-9_])~/|192\.168\.[0-9]+\.|an3tocom\.space|[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail)\.|\bmeomeo\b|an3_codex" -- "$OUT" 2>/tmp/an3-survivor.err)" \
  || survivor_error="$(head -5 /tmp/an3-survivor.err)"
rm -f /tmp/an3-survivor.err
[[ -z "$survivor_error" ]] || die "post-sanitisation scan could not complete: $survivor_error"
if [[ -n "$survivors" ]]; then
  die "personal-data or infrastructure patterns remain in the snapshot: $(printf '%s' "$survivors" | tr '\n' ' ')"
fi

note "files=$(find "$OUT" -type f | wc -l | tr -d ' ') size=$(du -sh "$OUT" | cut -f1)"
note "BUILD_SNAPSHOT=PASS $OUT"
