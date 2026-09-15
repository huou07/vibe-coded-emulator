#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
an3_ndk="${NDK_HOME:-$ANDROID_HOME/ndk/26.3.11579264}"
an3_compiler="$an3_ndk/toolchains/llvm/prebuilt/darwin-x86_64/bin/aarch64-linux-android26-clang++"
an3_output="src-tauri/gen/android/app/src/main/jniLibs/arm64-v8a"
mkdir -p "$an3_output"
node scripts/fetch-azahar-libretro-android.mjs
"$an3_compiler" -std=c++20 -O2 -g -fPIC -shared -static-libstdc++ -Wl,-z,max-page-size=16384 \
  native-runtime/core/libretro_host.cpp \
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
