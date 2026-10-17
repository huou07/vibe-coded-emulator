#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Resolve the Android SDK the same way on every build host. The hosted Linux
# Android builders export ANDROID_HOME (or ANDROID_SDK_ROOT); a macOS developer
# relies on the standard Library path. A hardcoded macOS default resolved an
# empty SDK on Linux.
if [[ -z "${ANDROID_HOME:-}" && -n "${ANDROID_SDK_ROOT:-}" ]]; then
  ANDROID_HOME="$ANDROID_SDK_ROOT"
fi
if [[ -z "${ANDROID_HOME:-}" ]]; then
  for candidate in "$HOME/Library/Android/sdk" "$HOME/Android/Sdk" "$HOME/Android/sdk" /usr/local/lib/android/sdk; do
    if [[ -d "$candidate" ]]; then ANDROID_HOME="$candidate"; break; fi
  done
fi
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
an3_ndk="${NDK_HOME:-$ANDROID_HOME/ndk/26.3.11579264}"
# The NDK ships one prebuilt host toolchain per build host. Hardcoding
# `darwin-x86_64` made every hosted Linux Android job die on the first compiler
# invocation with a bare `No such file or directory`; select it from the host
# instead, and name the boundary when the NDK is genuinely absent.
case "$(uname -s)" in
  Darwin) an3_ndk_host="darwin-x86_64" ;;
  Linux) an3_ndk_host="linux-x86_64" ;;
  MINGW*|MSYS*|CYGWIN*) an3_ndk_host="windows-x86_64" ;;
  *) echo "Unsupported Android build host: $(uname -s)" >&2; exit 3 ;;
esac
an3_compiler="$an3_ndk/toolchains/llvm/prebuilt/$an3_ndk_host/bin/aarch64-linux-android26-clang++"
[[ -x "$an3_compiler" ]] || {
  echo "Missing Android NDK C++ compiler: $an3_compiler" >&2
  echo "Install NDK 26.3.11579264 or point NDK_HOME at an NDK that provides the $(uname -s) host toolchain." >&2
  exit 3
}
an3_output="src-tauri/gen/android/app/src/main/jniLibs/arm64-v8a"
mkdir -p "$an3_output"
node scripts/fetch-azahar-libretro-android.mjs
"$an3_compiler" -std=c++20 -O2 -g -fPIC -shared -static-libstdc++ -Wl,-z,max-page-size=16384 \
  native-runtime/core/libretro_host.cpp \
  native-runtime/core/melonds_netplay.cpp \
  native-runtime/video/vulkan/vulkan_backend.cpp \
  native-runtime/video/opengl/gles3_backend.cpp \
  native-runtime/platform/android/aaudio_backend.cpp \
  native-runtime/platform/android/jni_runtime.cpp \
  -o "$an3_output/liban3_runtime.so" -landroid -llog -ldl -laaudio -lEGL -lGLESv3
cp vendor/libretro/android-arm64/mgba_libretro_android.so "$an3_output/libmgba_libretro_android.so"
cp vendor/libretro/android-arm64/melondsds_libretro_android.so "$an3_output/libmelondsds_libretro_android.so"
cp vendor/azahar/android-arm64/azahar_libretro_android.so "$an3_output/libazahar_libretro_android.so"
an3_licenses="src-tauri/gen/android/app/src/main/assets/native-core-licenses"
mkdir -p "$an3_licenses"
cp vendor/libretro/android-arm64/*.txt vendor/libretro/android-arm64/manifest.json "$an3_licenses/"
cp vendor/azahar/android-arm64/LICENSE vendor/azahar/android-arm64/manifest.json "$an3_licenses/"
cp native-runtime/core/vendor/libretro.h.LICENSE.txt "$an3_licenses/"
echo 'Android native runtime and verified arm64 GBA/NDS/Azahar cores packaged.'
