# VibeCodedEmulator staging artifact manifest

**Run:** `2026-09-08-multimodel-release-train`  
**Environment:** staging only  
**Staging asset:** `df14d4aa2d9a`  
**Release path:** `/opt/an3-arcade-staging/releases/20260912-164924-df14d4aa2d9a`  
**Rollback target:** `/opt/an3-arcade-staging/releases/20260911-230833-bef86865b122`

The Release Center catalog is fail-closed: an item is downloadable only when its local release path, size, and SHA-256 match this manifest. HTTP stream downloads from staging were verified against every available item below. Production was not accessed or changed.

| Platform | Format | Filename | Bytes | SHA-256 | Evidence/status |
| --- | --- | --- | ---: | --- | --- |
| macOS arm64 | DMG | `vibecodedemulator-0.4.4-macos-aarch64.dmg` | 42,282,073 | `762f1e8122c0b3455ed4a43509c001eb9a12adb252a398b5310c4ac9f8cb90f3` | HTTP parity PASS; ad-hoc staging signature and disk-image verification passed. OWNER-VERIFIED smooth GBA/NDS gameplay and audible audio. |
| Android arm64 | APK | `vibecodedemulator-0.4.4-android-arm64-staging.apk` | 87,703,074 | `128780ed3f21cbf2ac4b158fcd02fc60bd97e92c9b9ded90918f52ad7a3faa24` | HTTP parity PASS; APK Signature Scheme v2 verified. OWNER-VERIFIED smooth GBA/NDS gameplay and audible audio; AVD native Vulkan/GLES3/layout/archive/control/save acceptance completed. Android 3DS remains unadvertised pending qualifying audio acceptance. |
| Linux amd64 | DEB | `vibecodedemulator-0.4.4-linux-amd64.deb` | 1,812,216 | `7b8672db446a73c8dcf78220b77feb1501d9a0ae6958623fa74ba9319a3a7b49` | HTTP parity PASS; authorized Debian native GBA/Vulkan and NDS/OpenGL Xvfb smoke passed. |
| Linux amd64 | Flatpak | `an3-offline-0.4.4-linux-amd64-staging.flatpak` | 1,805,368 | `65f72ed64935cd958d1e977dcbbb3a2e3ecad5e29d8c6746be76c9916a525a50` | HTTP parity PASS; authorized Debian native GBA/Vulkan and NDS/OpenGL Xvfb smoke passed. |
| Windows x64 | EXE | — | — | — | BLOCKED: no authorized real Windows build/signing/runtime host; no artifact or download URL exists. |

## Verification record

- Local SHA-256 sidecars for all four available installers: PASS.
- Staging archive inspection: contained exactly the four listed installers and each hash matched the local release tree.
- Staging `/health`: `ok=true`, `environment=staging`, `asset_version=df14d4aa2d9a`.
- Staging `/download-app/artifacts.json` and streamed downloads: every available item matched this size/SHA-256 table; Windows remained blocked.
- Explicit Python regression suite: 119 tests PASS. Release Center/package subset: 30 tests PASS.

## Limits retained

- Owner audio evidence is observational, not fabricated automated audio evidence.
- Android 3DS implementation is present but still hidden: visible frames/input/layout/save states do not substitute for qualifying emitted/audible 3DS audio.
- Linux smoke used Xvfb and SDL dummy audio; it is package/runtime evidence, not a claim of human-audible Linux audio.
