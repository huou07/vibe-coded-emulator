# EmulatorRust 0.1.1 — staging handoff (2026-08-30)

## Scope and deployment

- Deployment was made only to the staging host at `192.168.1.8:8092`.
- Active staging asset version: `39259ec705bd`.
- Staging release directory: `/opt/an3-arcade-staging/releases/20260830-204018-39259ec705bd`.
- Rollback target reported by the staging release helper: `/opt/an3-arcade-staging/releases/20260830-154350-4e626eff3b6b`.
- Production was not contacted or changed.

## Delivered artifacts

| Platform | Artifact | Verification |
| --- | --- | --- |
| macOS Apple Silicon | `emulatorrust-0.1.1-macos-aarch64.dmg` | `codesign --verify --deep --strict` passed; `hdiutil verify` passed |
| Android ARM64 | `emulatorrust-0.1.1-android-arm64-staging.apk` | APK Signature Scheme v2 and v3 verification passed |

The staging downloads were fetched back and matched the local artifacts byte-for-byte. Windows, Linux, and iOS 0.1.1 installers are deliberately not exposed as completed releases: their required build/test hosts were unavailable.

## Runtime changes

- Product/window/android app label is `EmulatorRust`, version `0.1.1`.
- Player defaults have VSync disabled; NDS uses the melonDS `16-bit` audio option.
- NDS and 3DS clear stale EmulatorJS per-core local settings, preserving the requested physical-keyboard default for 3DS.
- Input ordering and the existing Menu → virtual controls → system touch → physical keyboard contract were left intact.
- Android 3DS now imports into private storage with a 1 MiB buffered stream, trims a padded NCSD image to its valid payload when safe, then hands the read-only private URI to the installed Azahar native companion.
- Desktop 3DS calls the installed Azahar companion for an imported private ROM; browser fallback remains unchanged when no native bridge exists.

## Test evidence

- Source checks passed: JavaScript syntax, Python compilation, Rust `cargo check`, and `git diff --check`.
- Repository suite passed: 39 tests.
- On the ARM64 Android AVD:
  - GBA Pokémon Emerald imported and reached the game boot screen at the displayed 60 FPS.
  - NDS Metal Slug 7 imported and reached its title screen with the melonDS core. The AVD uses SwiftShader and was started with `-no-audio`; its displayed ~33 FPS and audio cannot represent physical-device performance.
  - A decrypted Pokémon X NCSD image imported in 9 seconds. Its source file was 2.15 GB and the valid private payload was 1.75 GB. The app opened Azahar `EmulationActivity`, rendered the Pokémon X language-selection screen, and logged Vulkan with VSync false, resolution factor 1, shader cache enabled, and no fatal exception.
- macOS UI test is pending because the Mac was locked at the time of test. The 0.1.1 DMG itself was built and verified.

## Environment blockers

- Debian test host `192.168.1.12` had no reachable SSH port. Do not install Wine/Proton or build/test the Windows/Linux installers on the staging host as a substitute.
- This Mac has only Command Line Tools: no Xcode app, `simctl`, or `xcodebuild`. An iOS simulator and signed IPA require full Xcode plus an Apple Developer signing team.
- No physical Android device was visible to `adb` during the final pass.

## Cleanup

- Android AVD stopped.
- ADB server stopped.
- Gradle daemon stopped.
- EmulatorRust local loopback test process stopped.
- The staging systemd service remains active because it is the deployed test environment.
