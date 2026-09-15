#!/usr/bin/env bash
# Run by build-windows-runtime.ps1 inside the official MSYS2 UCRT64 toolchain.
set -euo pipefail
root="$(cygpath -u "$1")"
cd "$root"
[[ "$MSYSTEM" == UCRT64 ]] || { echo 'UCRT64 x64 toolchain is required.' >&2; exit 2; }
pkg-config --exists sdl2 vulkan gtk+-3.0
mkdir -p work/windows-runtime
g++ -std=c++20 -O2 -DNDEBUG -DNOMINMAX -DSDL_MAIN_HANDLED -Wall -Wextra \
  -Inative-runtime \
  native-runtime/core/libretro_host.cpp \
  native-runtime/video/vulkan/vulkan_backend.cpp \
  native-runtime/platform/linux/linux_runtime.cpp \
  native-runtime/platform/linux/linux_controls.cpp \
  native-runtime/platform/linux/sdl_audio_backend.cpp \
  native-runtime/platform/linux/sdl_gl_backend.cpp \
  $(pkg-config --cflags --libs sdl2 vulkan gtk+-3.0) \
  -lopengl32 -pthread -o work/windows-runtime/an3-native-runtime.exe
pacman -Q > work/windows-runtime/toolchain-packages.txt
