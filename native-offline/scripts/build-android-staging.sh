#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Prefer rustup's compiler so the installed Android standard library is used.
if [[ -d /opt/homebrew/opt/rustup/bin ]]; then
  export PATH="/opt/homebrew/opt/rustup/bin:$PATH"
fi
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home}"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export NDK_HOME="${NDK_HOME:-$ANDROID_HOME/ndk/26.3.11579264}"
[[ -x "$JAVA_HOME/bin/java" && -d "$NDK_HOME" ]] || { echo 'Java 17 and Android NDK are required.' >&2; exit 1; }
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
printf 'ANDROID_STAGING_SHA256=%s\n' "$(shasum -a 256 "$RELEASE_APK" | awk '{print $1}')"
echo 'Android release variant signed with the shared debug identity built; runtime acceptance is still required before publication.'
