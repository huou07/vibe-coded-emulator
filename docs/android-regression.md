# AN3 Android regression and private PWA procedure

Use the tools in `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/android/` for every staging-first Android pass. The detailed operating instructions are in `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/android/README.md`.

The harness defaults to `http://192.168.1.8:8092`, does not select or record a device serial, and permits production only through an explicit opt-in that is outside routine P3 regression work. It does not root the device, install APKs, inspect accounts/personal files, use `run-as`, or inspect arbitrary browser tabs.

Required scope: homepage search/filter/scroll/reload retention; login layout/input; authorized Pokémon Emerald GBA startup, virtual Start, fullscreen and save/load; authorized Pokémon Mystery Dungeon: Explorers of Sky NDS startup, melonDS, tap/drag coverage, native menu, virtual pad, rotation/fullscreen and local save/load.

For PWA E2E, use only the private path: staging → SSH local forward `127.0.0.1:18092` → `adb reverse tcp:18092 tcp:18092` → Android `http://localhost:18092`. Verify `window.isSecureContext` before Service Worker/install/offline claims; never disable browser security, expose staging publicly, change Cloudflare, or leave the reverse mapping after the test.

The current P3 result is documented in `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/android-regression/2026-08-23-p3-harness-and-pwa.md`. It is a documented blocker until an authorized ADB device can complete the runtime assertions.
