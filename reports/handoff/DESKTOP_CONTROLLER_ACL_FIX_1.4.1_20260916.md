# Desktop controller ACL fix + Linux GUI end-to-end (1.4.1, 2026-09-16)

## Bug found (and why it mattered)

The first time the feature was exercised in the real app, the Settings → Phone
controller panel reported:

```
Command native_controller_status not allowed by ACL
```

The three controller commands were registered in `lib.rs` and named in
`capabilities/default.json`, but they were missing from the Tauri
`AppManifest::commands([...])` list in `build.rs`, so Tauri never generated the
`allow-native-controller-*` permissions and the WebView was denied. **The 1.4.0
desktop artifacts shipped with a non-functional controller panel** (Android was
unaffected — it uses Kotlin, not Tauri commands).

Fix: added the three commands to `build.rs`, plus a guard
(`tests.test_offline_consolidation`) that derives every `#[tauri::command]` from
`src/*.rs`, requires each in `build.rs`, and requires its
`allow-<kebab>` capability entry.

## Linux GUI end-to-end (VERIFIED)

On the Dell with `openbox` installed (owner-authorized) over Xvfb:

1. Launched the installed 1.4.1 app, imported the legal GBA fixture, started
   native play (runtime window + GTK controls).
2. Settings → Phone controller → **Start** → pairing code `FM9MVQ` shown
   (`reports/staging/linux-desktop-controller-session.png`).
3. Paired from the MacBook as the phone; the app showed
   **`Phone connected · 3518s`**
   (`reports/staging/linux-desktop-controller-connected.png`).
4. Sent eight `start` press/release frames from the Mac.
5. The running GBA advanced to its **NEW GAME / OPTION** menu
   (`reports/staging/linux-desktop-game-after.png`, before:
   `linux-desktop-game-before.png`).

This is the full desktop chain: phone → staging API → Tauri host poll →
`set_native_input` → `INPUT` on the runtime's stdin → core → visible game.

## 1.4.1 artifacts (all five served 200 by staging)

| Platform | Artifact | Size | sha256 (short) |
| --- | --- | --- | --- |
| macOS | vibecodedemulator-1.4.1-macos-aarch64.dmg | 44,806,337 | `80899d0d…` |
| Android | vibecodedemulator-1.4.0-android-arm64-staging.apk (unchanged) | 49,587,834 | `3c7518a2…` |
| Linux DEB | vibecodedemulator-1.4.1-linux-amd64.deb | 45,515,398 | `5594b071…` |
| Linux Flatpak | an3-offline-1.4.1-linux-amd64-staging.flatpak | 29,105,496 | `d206a015…` |
| Windows | vibecodedemulator-1.4.1-windows-x64-staging.exe | 46,794,903 | `88be4c1f…` |

- `RELEASE_CATALOG=PASS (5 installers)`; suite **259 tests, 0 failures**.
- Staging asset `e792e8578089`, release
  `/opt/an3-arcade-staging/releases/20260916-175421-e792e8578089`,
  rollback `20260916-164416-e792e8578089`.
- macOS 1.4.1 mounts, `CFBundleShortVersionString 1.4.1`, binary contains
  `native_controller_status`, launches and stays alive.
- Windows 1.4.1 installs silently (exit 0), reports FileVersion 1.4.1, launches
  and responds with 6 `msedgewebview2` children; VM shut down
  (`shut off`, `Autostart: disable`).

## UNVERIFIED

- macOS/Windows **GUI** phone pairing (Linux GUI is verified; macOS/Windows only
  build/launch).
- A phone driving a running macOS/Windows game.
- Windows gameplay/rendering (Session 0, no Vulkan ICD).
