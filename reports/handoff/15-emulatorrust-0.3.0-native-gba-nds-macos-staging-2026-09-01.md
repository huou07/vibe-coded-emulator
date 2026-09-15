# EmulatorRust 0.3.0 — native GBA/NDS macOS staging handoff (2026-09-01)

## Scope

- Deployed to staging only: `http://192.168.1.8:8092`.
- Staging release: `/opt/an3-arcade-staging/releases/20260901-155138-015ee3e98e77`.
- Production was not accessed or modified.

## Native emulation path

The Apple Silicon macOS app now runs all requested handheld systems in-process:

| System | Native core | Presentation path |
| --- | --- | --- |
| GBA | mGBA libretro | software frame upload through Vulkan 1.1 -> MoltenVK -> Metal |
| NDS | melonDS DS libretro | software frame upload through Vulkan 1.1 -> MoltenVK -> Metal |
| 3DS | Azahar libretro | native Vulkan renderer through bundled MoltenVK -> Metal |

No separate emulator application is launched.  GBA/NDS emulation remains CPU-native; the Vulkan/MoltenVK/Metal path is the efficient on-GPU frame presentation path.  Azahar continues to use its native Vulkan rendering path.

The bundled, fail-closed Apple Silicon artifacts are pinned and recorded in `native-offline/vendor/libretro/macos-arm64/manifest.json`.  mGBA is MPL-2.0; melonDS is GPL-3.0-or-later.  Their notices and source provenance are included in the native source bundle and `THIRD_PARTY_NOTICES.md`.

## Controls and NDS touch mode

- The app keeps the requested control order: game menu, on-screen controls, touch surface where supported, then physical keyboard.
- NDS uses the native libretro Pointer input mode for its touch screen.
- Clicking the NDS game surface, or using **Lock cursor**, captures and hides the macOS cursor.  Relative pointer movement controls the DS touch cursor.
- `Esc` releases capture; a subsequent `Esc` returns to the library.  Capture is also released on stop, focus loss, window removal, and deallocation.

## Installer

- Filename: `emulatorrust-0.3.0-macos-aarch64.dmg`
- SHA-256: `1a93f375a78c56206e184f629de8b7baa78e5ef48398ef55bcecfec6e5bb692d`
- Staging URL: `http://192.168.1.8:8092/download-app/release/emulatorrust-0.3.0-macos-aarch64.dmg`
- The app is ad-hoc signed; it is not notarized because Apple Developer credentials were not supplied.

## Validation

- Native macOS compile check passed with `MACOSX_DEPLOYMENT_TARGET=13.4`.
- Rust tests passed: 4 tests.
- Python test suite passed: 41 tests.
- `npm run check`, `git diff --check`, strict deep app signature verification, and `hdiutil verify` passed.
- A direct native hardware smoke run held approximately 60 FPS for eight seconds on each valid local GBA and NDS test ROM: 479 and 480 presented frames respectively.
- Staging `/health` responds successfully and the deployed DMG was downloaded back, byte-compared to the signed local artifact, hash-checked, and `hdiutil verify`-checked.

The Mac UI session was locked during manual pointer click-through, so the cursor-lock interaction was source- and compile-validated rather than visually exercised in the native window.  The implementation includes all release-safety paths listed above.
