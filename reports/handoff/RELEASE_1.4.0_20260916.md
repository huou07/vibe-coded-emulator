# Release 1.4.0 — phone controller on every platform (2026-09-16)

All five packaged apps rebuilt at **1.4.0** and deployed to staging.

## Version bump

New feature (native phone controller) → minor bump: **1.3.0 → 1.4.0** on
`tauri.conf.json` (desktop), `tauri.android.conf.json` (Android), and
`package.json`. Filenames, catalog entries, and sidecars updated together.

## Artifacts (all served 200 by staging with catalog size)

| Platform | Artifact | Size | sha256 (short) |
| --- | --- | --- | --- |
| macOS | vibecodedemulator-1.4.0-macos-aarch64.dmg | 44,810,277 | `638d44ee…` |
| Android | vibecodedemulator-1.4.0-android-arm64-staging.apk | 49,587,834 | `3c7518a2…` |
| Linux DEB | vibecodedemulator-1.4.0-linux-amd64.deb | 45,513,922 | `82ffaca9…` |
| Linux Flatpak | an3-offline-1.4.0-linux-amd64-staging.flatpak | 29,103,144 | `cc74f5a6…` |
| Windows | vibecodedemulator-1.4.0-windows-x64-staging.exe | 46,784,588 | `be5f84f9…` |

`RELEASE_CATALOG=PASS (5 installers)`; suite **258 tests, 0 failures**.
Staging asset `e792e8578089`, release
`/opt/an3-arcade-staging/releases/20260916-164416-e792e8578089`,
rollback `/opt/an3-arcade-staging/releases/20260916-162332-e792e8578089`.

## Builds

- macOS local (`npm run build:macos`), hdiutil checksum VALID; app mounts,
  `CFBundleShortVersionString 1.4.0`, launches.
- Android local (`scripts/build-android-staging.sh`); AVD-verified controller.
- Linux DEB + Flatpak on the Dell (`scripts/build-linux-staging.sh deb|flatpak`).
- Windows NSIS on the VM (`scripts/build-windows-staging.ps1`); VM shut down
  gracefully afterwards (`shut off`, `Autostart: disable`).

## Release-script hardening (bug found)

Every release script now **derives the artifact name from the version field**
instead of hardcoding it: `build-android-staging.sh`, `package-macos.sh`,
`build-linux-staging.sh` (DEB + Flatpak), `build-windows-staging.ps1`, and
`verify-flatpak-install.sh`. Historical failure just hit: the Windows script
looked for `VibeCodedEmulator_1.3.0_x64-setup.exe`, so a 1.4.0 build copied a
leftover 1.3.0 installer under the wrong filename (never published). The
Flatpak manifest/metainfo are pinned by a new test.

## VERIFIED

- All five 1.4.0 installers build, are catalogued with exact size/SHA-256 and
  sidecars, pass `verify-release-catalog.py`, and are served 200 by staging.
- Android controller end-to-end (AVD); desktop controller host logic + live
  staging probe (see the dedicated reports).

## Runtime follow-up (same day)

- **Linux 1.4.0 runtime VERIFIED** (Dell, Xvfb): DEB runtime ran the full 25 s
  smoke; the app binary ships `nativeControllerCard`; the controller host tests
  pass on Linux and the live staging probe passed; feeding the shell's `INPUT`
  lines to `--control-stdin` advanced the GBA title. See
  `reports/handoff/LINUX_1.4.0_RUNTIME_AND_CONTROLLER_20260916.md`.
- **Windows 1.4.0 launch smoke VERIFIED**: the 1.4.0 EXE installed silently
  (exit 0), the installed `an3-offline-native.exe` reports
  FileVersion/ProductVersion **1.4.0**, and it launched (`responding=True`,
  6 `msedgewebview2` children) on `an3-win11-build`; the VM was shut down
  gracefully (`shut off`, `Autostart: disable`).

## UNVERIFIED

- Windows 1.4.0 **gameplay/rendering** (Session 0, no Vulkan ICD) — launch only.
- The Tauri app autonomously writing controller `INPUT` while polling (the
  runtime side and the client side are each verified separately).
- A phone driving a *running* desktop game.
- macOS remains ad-hoc signed / not notarized (no Apple credentials).
