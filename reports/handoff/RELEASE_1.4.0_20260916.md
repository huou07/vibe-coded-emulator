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

## UNVERIFIED

- Linux/Windows **runtime** of 1.4.0: DEB/Flatpak built only (Linux launch smoke
  was done for 1.3.0); the Windows 1.4.0 EXE was **not** launched on the VM
  (1.3.0 had a launch smoke).
- A phone driving a *running* desktop game (client verified live; the running
  core was not observed on desktop).
- macOS remains ad-hoc signed / not notarized (no Apple credentials).
