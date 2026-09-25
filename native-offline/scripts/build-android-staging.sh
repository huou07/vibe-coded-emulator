#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Rust embeds file!()/panic locations from the dependency graph in native
# binaries even in release mode. Remap the local checkout prefix so Android
# artifacts never disclose the builder's home directory or handle.
an3_home_prefix="${HOME%/}"
export RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }--remap-path-prefix=${an3_home_prefix}=/an3-home"
# Prefer rustup's compiler so the installed Android standard library is used.
if [[ -d /opt/homebrew/opt/rustup/bin ]]; then
  export PATH="/opt/homebrew/opt/rustup/bin:$PATH"
fi
if [[ -z "${JAVA_HOME:-}" ]]; then
  case "$(uname -s)" in
    Darwin) JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home" ;;
    Linux) JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")" ;;
    *) echo 'Android staging requires a supported macOS or Linux builder.' >&2; exit 1 ;;
  esac
fi
sdk_root="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [[ -z "$sdk_root" ]]; then
  case "$(uname -s)" in
    Darwin) sdk_root="$HOME/Library/Android/sdk" ;;
    Linux) sdk_root="$HOME/Android/Sdk" ;;
  esac
fi
export JAVA_HOME ANDROID_HOME="$sdk_root" ANDROID_SDK_ROOT="$sdk_root"
export NDK_HOME="${NDK_HOME:-$ANDROID_HOME/ndk/26.3.11579264}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$NDK_HOME}"
[[ -x "$JAVA_HOME/bin/java" && -d "$NDK_HOME" ]] || { echo 'Java 17 and Android NDK are required.' >&2; exit 1; }
bash scripts/build-android-runtime.sh
# The Android package version is authoritative for the About panel and the
# asset cache-busting query. tauri.android.conf.json overrides package.json, so
# inject it explicitly instead of letting the desktop version leak into the APK.
export AN3_APP_VERSION="$(node -p "require('./src-tauri/tauri.android.conf.json').version")"
npm run prepare-web
# Build the optimized release variant (keeps the shared Android Debug signing
# identity via build.gradle.kts) so the bundled native shell is small and fast.
# The previous debug APK shipped a ~149 MB unoptimized shell library, which
# caused device memory pressure/ANR and crashes for the 3DS native path.
rm -rf src-tauri/gen/android/app/build/outputs/apk src-tauri/gen/android/app/build/outputs/bundle
npm run tauri -- android build --target aarch64 --apk --aab
SOURCE_APK="$(find src-tauri/gen/android/app/build/outputs -type f -path '*release*' -name '*.apk' -print -quit)"
SOURCE_AAB="$(find src-tauri/gen/android/app/build/outputs -type f -path '*release*' -name '*.aab' -print -quit)"
# Derive the artefact name from the Android version field so a version bump can
# never publish under a stale filename.
VERSION="$(node -p "require('./src-tauri/tauri.android.conf.json').version")"
RELEASE_APK="${AN3_RELEASE_DIR:-releases}/vibecodedemulator-${VERSION}-android-arm64-staging.apk"
RELEASE_AAB="${AN3_RELEASE_DIR:-releases}/vibecodedemulator-${VERSION}-android-arm64-staging.aab"
[[ -f "$SOURCE_APK" ]] || { echo "Android build completed without a release APK." >&2; exit 1; }
[[ -f "$SOURCE_AAB" ]] || { echo "Android build completed without a release AAB." >&2; exit 1; }
mkdir -p "$(dirname "$RELEASE_APK")"
install -m 0644 "$SOURCE_APK" "$RELEASE_APK"
install -m 0644 "$SOURCE_AAB" "$RELEASE_AAB"
if [[ "${AN3_BUILD_ANDROID_TESTS:-0}" == "1" ]]; then
  gradle_root="src-tauri/gen/android"
  (
    cd "$gradle_root"
    ./gradlew --no-daemon --console=plain --max-workers=2 \
      :app:assembleArm64ReleaseAndroidTest \
      :app:testArm64ReleaseUnitTest
  )
  SOURCE_TEST_APK="$(find "$gradle_root/app/build/outputs/apk/androidTest" -type f -name '*.apk' -print -quit)"
  [[ -f "$SOURCE_TEST_APK" ]] || { echo 'Android release instrumentation APK was not produced.' >&2; exit 1; }
  RELEASE_TEST_APK="${AN3_RELEASE_DIR:-releases}/vibecodedemulator-${VERSION}-android-arm64-staging-androidTest.apk"
  install -m 0644 "$SOURCE_TEST_APK" "$RELEASE_TEST_APK"
  (cd "$(dirname "$RELEASE_TEST_APK")" && shasum -a 256 "$(basename "$RELEASE_TEST_APK")" > "$(basename "$RELEASE_TEST_APK").sha256")
  printf 'ANDROID_STAGING_TEST_APK=%s\n' "$RELEASE_TEST_APK"
  printf 'ANDROID_STAGING_TEST_SHA256=%s\n' "$(shasum -a 256 "$RELEASE_TEST_APK" | awk '{print $1}')"
fi
printf 'ANDROID_STAGING_APK=%s\n' "$RELEASE_APK"
printf 'ANDROID_STAGING_SHA256=%s\n' "$(shasum -a 256 "$RELEASE_APK" | awk '{print $1}')"
printf 'ANDROID_STAGING_AAB=%s\n' "$RELEASE_AAB"
printf 'ANDROID_STAGING_AAB_SHA256=%s\n' "$(shasum -a 256 "$RELEASE_AAB" | awk '{print $1}')"
echo 'Android release variant signed with the shared debug identity built; runtime acceptance is still required before publication.'
