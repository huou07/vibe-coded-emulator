#!/bin/sh
# Direct access to the bundled native player for package verification and
# runtime smoke. The user-facing application is the Tauri shell
# (`an3-offline-native`); this wrapper only exposes the gameplay runtime that
# the shell launches, with its core directory resolved inside the Flatpak.
AN3_OFFLINE_LIBDIR=/app/lib/VibeCodedEmulator/runtime/linux-x86_64
export AN3_OFFLINE_LIBDIR
exec /app/lib/VibeCodedEmulator/runtime/linux-x86_64/an3-offline-native "$@"
