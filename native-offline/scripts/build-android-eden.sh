#!/usr/bin/env bash
# Build the pinned Eden Android core with the AN3 JNI adapter and stage the
# resulting arm64 library for the Tauri Android package. Eden remains an
# upstream, GPL-licensed core; AN3 supplies only the small C ABI/JNI boundary.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EDEN_COMMIT="${AN3_EDEN_COMMIT:-7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c}"
EDEN_ROOT="${AN3_EDEN_ROOT:-/tmp/an3-eden-full.3KCtFH/repo}"
JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home}"
ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export JAVA_HOME ANDROID_HOME

[[ -x "$JAVA_HOME/bin/java" ]] || { echo "Android Eden requires Java 17 at $JAVA_HOME" >&2; exit 2; }
[[ -x "$EDEN_ROOT/src/android/gradlew" ]] || { echo "Pinned Eden Android checkout is missing at $EDEN_ROOT" >&2; exit 2; }
[[ "$(git -C "$EDEN_ROOT" rev-parse HEAD)" == "$EDEN_COMMIT" ]] || {
  echo "Eden checkout is not pinned to $EDEN_COMMIT" >&2
  exit 2
}
[[ -d "$ANDROID_HOME/ndk/28.2.13676358" ]] || {
  echo "Android NDK 28.2.13676358 is required for the pinned Eden Android build" >&2
  exit 2
}

# Keep the build reproducible while avoiding a second fork of Eden in the AN3
# repository: these are the only two upstream CMake insertions required to
# compile the tracked AN3 bridge and its JNI entry points.
python3 - "$EDEN_ROOT/CMakeLists.txt" "$EDEN_ROOT/src/android/app/src/main/jni/CMakeLists.txt" "$ROOT/../native/eden-bridge" <<'PY'
from pathlib import Path
import sys

root_cmake, android_cmake, bridge = map(Path, sys.argv[1:])
root = root_cmake.read_text()
marker = 'if(DEFINED AN3_EDEN_BRIDGE_DIR)'
assignment = f'set(AN3_EDEN_BRIDGE_DIR "{bridge.as_posix()}")\n'
root_changed = False
insertion = (
    '\nif(DEFINED AN3_EDEN_BRIDGE_DIR)\n'
    '    add_subdirectory("${AN3_EDEN_BRIDGE_DIR}/integration" an3_eden_bridge)\n'
    'endif()\n'
)
if assignment not in root:
    root = assignment + root
    root_changed = True
if marker not in root:
    needle = '\nadd_subdirectory(src)\n'
    if needle not in root:
        raise SystemExit('Eden root CMakeLists.txt has no source insertion point')
    root = root.replace(needle, insertion + needle, 1)
    root_changed = True
if root_changed:
    root_cmake.write_text(root)

android = android_cmake.read_text()
source = '    ${AN3_EDEN_BRIDGE_DIR}/android/an3_eden_android_jni.cpp\n'
if source not in android:
    android = android.replace(
        '    native_post_processing.cpp\n',
        '    native_post_processing.cpp\n' + source,
        1,
    )
    anchor = 'target_link_libraries(yuzu-android PRIVATE audio_core common core input_common frontend_common video_core)\n'
    if anchor not in android:
        raise SystemExit('Eden Android CMake target shape changed')
    android = android.replace(
        anchor,
        anchor + 'target_link_libraries(yuzu-android PRIVATE an3_eden_bridge)\n'
        'target_include_directories(yuzu-android PRIVATE "${AN3_EDEN_BRIDGE_DIR}/include")\n'
        'set_target_properties(yuzu-android PROPERTIES OUTPUT_NAME an3_eden_android)\n',
        1,
    )
    android_cmake.write_text(android)
PY

cd "$EDEN_ROOT/src/android"
./gradlew :app:assembleMainlineRelWithDebInfo --no-daemon --console=plain --max-workers=4

eden_lib="$(find "$EDEN_ROOT/src/android/app/build" -path '*/lib/arm64-v8a/liban3_eden_android.so' -type f -print -quit)"
[[ -f "$eden_lib" ]] || {
  echo "Eden Android build did not emit liban3_eden_android.so" >&2
  exit 3
}

destination="$ROOT/src-tauri/gen/android/app/src/main/jniLibs/arm64-v8a"
mkdir -p "$destination"
install -m 0644 "$eden_lib" "$destination/liban3_eden_android.so"
# RelWithDebInfo is the upstream Android build variant that exposes the
# supported CMake target, but its DWARF strings contain developer checkout
# paths. Strip only debug sections before the library enters APK/AAB packaging;
# this preserves code and symbols needed by the JNI ABI while preventing local
# paths from becoming release metadata.
llvm_strip="$(find "$ANDROID_HOME/ndk/28.2.13676358/toolchains/llvm/prebuilt" -name llvm-strip -print -quit)"
[[ -n "$llvm_strip" && -x "$llvm_strip" ]] || {
  echo 'Android Eden build did not find the NDK llvm-strip tool.' >&2
  exit 3
}
"$llvm_strip" --strip-debug "$destination/liban3_eden_android.so"
mkdir -p "$ROOT/src-tauri/gen/android/app/src/main/assets/native-core-licenses"
eden_license=""
for candidate in "$EDEN_ROOT/LICENSE.txt" "$EDEN_ROOT/LICENSE"; do
  if [[ -f "$candidate" ]]; then eden_license="$candidate"; break; fi
done
if [[ -n "$eden_license" ]]; then
  install -m 0644 "$eden_license" \
    "$ROOT/src-tauri/gen/android/app/src/main/assets/native-core-licenses/EDEN-GPL-3.0-or-later.txt"
fi
eden_sha="$(shasum -a 256 "$destination/liban3_eden_android.so" | awk '{print $1}')"
eden_size="$(stat -f '%z' "$destination/liban3_eden_android.so" 2>/dev/null || stat -c '%s' "$destination/liban3_eden_android.so")"
printf '{"core":"Eden","upstream":"https://git.eden-emu.dev/eden-emu/eden","commit":"%s","abi":"arm64-v8a","library":"liban3_eden_android.so","size":%s,"sha256":"%s"}\n' \
  "$EDEN_COMMIT" "$eden_size" "$eden_sha" \
  > "$ROOT/src-tauri/gen/android/app/src/main/assets/native-core-licenses/eden-manifest.json"
printf 'ANDROID_EDEN_LIBRARY=%s\nANDROID_EDEN_SHA256=%s\n' "$destination/liban3_eden_android.so" "$eden_sha"
