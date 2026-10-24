#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
repo_root="$(cd .. && pwd)"
bash "$repo_root/tools/disk-preflight.sh" 'Android staging package' "$repo_root"
# Prefer rustup's compiler so the installed Android standard library is used.
if [[ -d /opt/homebrew/opt/rustup/bin ]]; then
  export PATH="/opt/homebrew/opt/rustup/bin:$PATH"
fi
# Java and the Android SDK live in host-specific places: the hosted Linux
# builders export JAVA_HOME/ANDROID_HOME, a macOS developer relies on Homebrew's
# JDK and the standard Library path, and a Linux developer may only have `java`
# on PATH. Defaulting JAVA_HOME to a macOS path made a Linux host fail the guard
# below with a misleading "Java 17 and Android NDK are required".
if [[ -z "${JAVA_HOME:-}" && "$(uname -s)" == "Darwin" ]]; then
  JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
fi
if [[ -n "${JAVA_HOME:-}" ]]; then export JAVA_HOME; fi
if [[ -z "${ANDROID_HOME:-}" && -n "${ANDROID_SDK_ROOT:-}" ]]; then
  ANDROID_HOME="$ANDROID_SDK_ROOT"
fi
if [[ -z "${ANDROID_HOME:-}" ]]; then
  for candidate in "$HOME/Library/Android/sdk" "$HOME/Android/Sdk" "$HOME/Android/sdk" /usr/local/lib/android/sdk; do
    if [[ -d "$candidate" ]]; then ANDROID_HOME="$candidate"; break; fi
  done
fi
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export NDK_HOME="${NDK_HOME:-$ANDROID_HOME/ndk/26.3.11579264}"
java_binary="${JAVA_HOME:+$JAVA_HOME/bin/java}"
java_binary="${java_binary:-$(command -v java || true)}"
[[ -n "$java_binary" && -x "$java_binary" && -d "$NDK_HOME" ]] || {
  echo "Java 17 and Android NDK are required (JAVA_HOME=${JAVA_HOME:-unset}, NDK_HOME=$NDK_HOME)." >&2
  exit 1
}
bash scripts/build-android-runtime.sh
npm run prepare-web
# Build the optimized release variant (keeps the shared Android Debug signing
# identity via build.gradle.kts) so the bundled native shell is small and fast.
# The previous debug APK shipped a ~149 MB unoptimized shell library, which
# caused device memory pressure/ANR and crashes for the 3DS native path.
npm run tauri -- android build --target aarch64 --apk
SOURCE_APK="src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release.apk"
[[ -f "$SOURCE_APK" ]] || SOURCE_APK="src-tauri/gen/android/app/build/outputs/apk/release/app-release.apk"
# Derive the artefact name from the Android version field so a version bump can
# never publish under a stale filename.
VERSION="$(node -p "require('./src-tauri/tauri.android.conf.json').version")"
RELEASE_APK="${AN3_RELEASE_DIR:-releases}/vibecodedemulator-${VERSION}-android-arm64-staging.apk"
[[ -f "$SOURCE_APK" ]] || { echo "Android build completed without its expected APK: $SOURCE_APK" >&2; exit 1; }
mkdir -p "$(dirname "$RELEASE_APK")"
install -m 0644 "$SOURCE_APK" "$RELEASE_APK"
printf 'ANDROID_STAGING_APK=%s\n' "$RELEASE_APK"
# `shasum` is a Perl tool that is not guaranteed on a Linux builder; `sha256sum`
# is the coreutils equivalent. Prefer whichever exists so the same script runs
# on both hosts.
if command -v sha256sum >/dev/null 2>&1; then
  ANDROID_STAGING_SHA256="$(sha256sum "$RELEASE_APK" | awk '{print $1}')"
else
  ANDROID_STAGING_SHA256="$(shasum -a 256 "$RELEASE_APK" | awk '{print $1}')"
fi
printf 'ANDROID_STAGING_SHA256=%s\n' "$ANDROID_STAGING_SHA256"
echo 'Android release variant signed with the shared debug identity built; runtime acceptance is still required before publication.'
