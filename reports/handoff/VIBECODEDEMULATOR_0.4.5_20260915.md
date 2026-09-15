# VibeCodedEmulator 0.4.5 — 3DS crash fixes, desktop UI shell, release

Status: COMPLETE. Owner-authorized staging and production release of the five
0.4.5 installers.

## Reported issues and root causes

1. APK and EXE crashed when playing 3DS.
   - Root cause A (both): the pinned Azahar libretro **2126.0** core had a known
     upstream defect fixed in **2126.1.1** ("Fixed an issue where Azahar could
     instantly crash when opened on certain systems with poor Vulkan support",
     plus a Vulkan shadow-texture crash). macOS in-process rendering masked it;
     the Android and Windows portable Vulkan path hit it.
   - Root cause B (APK only): the official Azahar Android `azahar_libretro.so`
     was **4 KB page aligned** (`p_align 0x1000`), while the mGBA/melonDS cores
     were 16 KB aligned. On Android 15+ 16 KB-page devices the 3DS core's LOAD
     segments overlap after page rounding, so 3DS failed while GBA/NDS worked.
     The 2126.1.1 asset is 16 KB aligned (`p_align 0x4000`), verified on disk.
2. `.exe` UI/UX differed from `.dmg`, and `.deb`/`.flatpak` had no UI.
   - The macOS DMG renders the game in-window with a native AppKit overlay. The
     Windows and Linux apps ran a separate native SDL/GTK player, and the Linux
     packages shipped *only* that native binary (no library/import shell).
   - Fix (owner-approved pragmatic scope): the DEB and Flatpak now ship the
     shared **Tauri desktop shell** (the local-ROM library/import UI used by
     DMG/EXE) and bundle the native SDL/GTK player plus pinned cores as the
     gameplay runtime, launched by a new Linux launcher backend. Windows keeps
     the same Tauri shell and now uses the fixed 2126.1.1 core.

## Source changes

- Azahar pin 2126.0 -> 2126.1.1 (Android, macOS, Linux, Windows): new core,
  archive, source and license hashes in the fetchers and `azahar-desktop-lock.json`;
  vendored cores/manifests refreshed; `THIRD_PARTY_NOTICES.md` updated.
- Version 0.4.5 everywhere: `package.json`/lock, `Cargo.toml`, Tauri configs,
  Android `versionName`/`versionCode` (4005), build scripts, Flatpak manifest,
  web asset query strings, shared player model, catalog, and tests.
- Linux desktop shell: `src-tauri/src/linux_runtime.rs` (spawns and drives the
  bundled native player over its private control pipe), Linux dispatch in
  `azahar.rs`, close handling in `lib.rs`, `tauri.linux.conf.json` resources and
  DEB dependencies, `scripts/bundle-linux-runtime.mjs`, rewritten
  `scripts/build-linux-staging.sh` (Tauri deb + Flatpak from that deb), Flatpak
  manifest extraction of the Tauri deb plus an `an3-native-player` verification
  wrapper, and updated guard tests.

## Artifacts (0.4.5)

| Platform | File | Bytes | SHA-256 |
| --- | --- | --- | --- |
| macOS arm64 | `vibecodedemulator-0.4.5-macos-aarch64.dmg` | 42,233,372 | `4731cdd1d402df318fae825ebf56f7b49abadb3596b74c5262c6d852c507f145` |
| Android arm64 | `vibecodedemulator-0.4.5-android-arm64-staging.apk` | 86,532,054 | `71f047ac1fd12e72daaa9d6ce254727229eefc5bb4f600083488a660a3df4a28` |
| Linux amd64 | `vibecodedemulator-0.4.5-linux-amd64.deb` | 44,201,354 | `47e056f7bc995200c2eadbc3076d78fd7860d09f5235a791770ce85a517a92ef` |
| Linux amd64 | `an3-offline-0.4.5-linux-amd64-staging.flatpak` | 27,768,312 | `bbcdce68fa42cc3d34c62545f0b541c6265c48d9b494a5a94f733d5134871d3c` |
| Windows x64 | `vibecodedemulator-0.4.5-windows-x64-staging.exe` | 42,962,329 | `3e9378a13cc76952ff2fdba8b55640ce9a2630cef725808772c350a01d092757` |

Catalog `source_fingerprint`: `2f60ea77e6f5a6b3348a44876cdede1b9ac7d1aa49162d8626eecbd0eee0ac81`.
`tools/verify-release-catalog.py` -> `RELEASE_CATALOG=PASS (5 installers)`.

## Verification

- macOS: Tauri build + DMG; `hdiutil verify` VALID; mounted `VibeCodedEmulator.app`
  is 0.4.5 and ships the 2126.1.1 dylib (`strings` confirms `2126.1.1`).
- Android: fresh debug-signed APK; **v2 signature** PASS (Android Debug cert
  `b48f3cde…`, same signer as prior production APK); embedded
  `libazahar_libretro_android.so` is `de_436410…` and `p_align 0x4000` (16 KB).
- Linux: authorized Debian built the Tauri DEB and the Flatpak from it; DEB
  clean-install extraction shows the shell, the bundled native player/cores and
  the correct dependencies; bundled native player `--help` PASS; the Tauri shell
  launches under Xvfb (still running at timeout); Flatpak fresh-user install +
  `an3-native-player --help` -> `FLATPAK_CLEAN_INSTALL=PASS`.
- Windows: authorized Windows 11 VM rebuilt the portable runtime
  (`WINDOWS_NATIVE_RUNTIME=VERIFIED 47 PE files`) and the NSIS installer
  (`WINDOWS_DONE`). Hardware Vulkan/3DS gameplay was not re-verified in the VM.
- Verification suite: 126/128 Python cases pass; `web_nds_touch`, `web_renderer`
  and `npm run check` pass; `git diff --check` clean; catalog PASS.

## Deployment

- Staging: `STAGING_RELEASE=PASS`, asset `7d2750ed8173`, release
  `/opt/an3-arcade-staging/releases/20260915-121311-7d2750ed8173`, rollback
  `/opt/an3-arcade-staging/releases/20260915-111333-baa8a060f571`.
- Production: `PRODUCTION_RELEASE=PASS`, asset `7d2750ed8173`, release id
  `production-2b3a673f1a5b429f`, application backup
  `/opt/an3-arcade-backups/20260915-121440`, SQLite backup
  `/srv/an3-arcade/backups/arcade-predeploy-20260915-121440.db`.
- Public HTTPS returns HTTP 200 with the exact catalog sizes for all five
  installers (`no-store`/`BYPASS` on the APK).
- Lifecycle: Windows VM shutdown issued; Dell disposable build root removed.

## Follow-up: APK 3DS crash hardening — 2026-09-15 (same 0.4.5 release)

The owner reported the APK still exited 5–8 s into 3DS gameplay. The AVD cannot
reproduce the owner's device crash (it ran a legal 3DS `.3dsx` for 60 s+), so the
release was hardened against the device-specific failure classes:

- The Android staging APK is now built as an optimized **release variant** signed
  with the shared Android Debug identity (drop-in update). The previous debug
  APK shipped a ~149 MB unoptimized `liban3_offline_native.so`; the release APK
  is 48,078,249 bytes with a 23 MB shell library, removing device memory
  pressure/ANR risk. `build.gradle.kts` keeps R8/minify off and the debug signer.
- `android:largeHeap="true"` and `android:hardwareAccelerated="true"`.
- `NativeGameActivity` runs in an isolated `:game` process so the 3DS core's
  memory is separate from the WebView shell and a native fault cannot take down
  the whole library task.
- **AAudio failure is no longer fatal.** `jni_runtime.cpp` used to stop the whole
  game on any `AAUDIO` error; it now stops the stream once and keeps rendering
  gameplay silently. This was the most likely "game exits by itself" device bug.
- Rebuilt APK: `vibecodedemulator-0.4.5-android-arm64-staging.apk`, 48,078,249
  bytes, SHA-256 `afc3f474f3bcabd15daa647631ded1480c3b873a4a4ff83ec27704292880bc2f`,
  versionName 0.4.5 / versionCode 4005, v2-signature PASS (Android Debug cert
  `b48f3cde…`), Azahar `2126.1.1` core remains 16 KB aligned (3 LOAD segments at
  `0x4000`). Catalog updated (`source_fingerprint`
  `dd5b081b472301df735e6b8cd5cf7a148ef26341aba553ac4ca6712c3e1ca03a`); other four
  installers unchanged. Catalog verifier PASS.

Deployed: production `PRODUCTION_RELEASE=PASS`, asset `7d2750ed8173`, release
`production-a1785e5a04384c87`, backup `/opt/an3-arcade-backups/20260915-124743`;
staging `STAGING_RELEASE=PASS` release
`/opt/an3-arcade-staging/releases/20260915-124820-7d2750ed8173`. Public APK
download returns 48,078,249 bytes (`no-store`/`BYPASS`).

## APK 0.4.6 — "Re-import ROM for native playback" blocker — 2026-09-15

Owner report: the APK showed **"Re-import ROM for native playback"** on NDS/3DS
cards and blocked playback.

Root cause: the Android native import stores `nativePath` (`/native-rom/<uuid>.<ext>`)
and not a loopback `nativeUrl`, but `static/offline.js`'s `nativeRomIdForGame`
only recovered the ROM id from `nativeUrl`. Records without `nativeRomId` (any
import from an older APK) therefore had no native id, so the card label fell back
to "Play now" and `android-staging.js` disabled it with "Re-import ROM for native
playback".

Fixes:
- `static/offline.js`: `nativeRomIdForGame` now also recovers the UUID from
  `nativePath`, so existing imported GBA/NDS/3DS records play natively with no
  re-import.
- `native-offline/web/android-staging.js`: the guard no longer disables or
  relabels a system this APK ships a core for. It only disables a genuinely
  unsupported system ("Native core unavailable"). The UI is never blocked.

Testing (AVD, legal fixtures): injected a legacy record (only `nativePath`, no
`nativeRomId`); the 3DS card rendered **"Chơi 3DS native", enabled**, and clicking
it launched the native activity (top-resumed, `:game` process running, no
tombstone). Verified native launch success (`""`) for all three real stored ROMs —
GBA `1b44de30…gba`, NDS `58a4d7a3…nds`, 3DS `3d500001-…3ds`. Guard unit tests and
the suite pass (only the two pre-existing web-route assertions fail).

Version: Android `versionName 0.4.6`, `versionCode 4006`, via
`tauri.android.conf.json` (desktop artifacts stay 0.4.5). Optimized release
variant, shared Android Debug signing identity, Azahar 2126.1.1 core still 16 KB
aligned. APK: `vibecodedemulator-0.4.6-android-arm64-staging.apk`, 48,078,569
bytes, SHA-256 `1de05c5a57c6c14b6e813d24a4acbfea42e9ce8f6f45acec4c2c57725fd674f5`.
Catalog `source_fingerprint` `ba58f5ca91a3da60b9094e6b174f90d4071bcc65b64d5a44623cc6e845d942b9`;
verifier PASS; old 0.4.5 APK URL returns 404.

Deployed: production `PRODUCTION_RELEASE=PASS`, asset `03571122269a`, release
`production-4f8675692fc5a41a`, backup `/opt/an3-arcade-backups/20260915-132526`;
staging `STAGING_RELEASE=PASS` release
`/opt/an3-arcade-staging/releases/20260915-132605-03571122269a`. Public APK
returns 48,078,569 bytes. AVD shut down.

## APK 0.4.7 — removed front-end playback locks — 2026-09-15

Owner report: the app still told them to "play as native" and they could not
play. Root causes were the remaining front-end locks plus a stale WebView cache:

- `native-bootstrap.js` redirected any Android `?play` request back to the
  library, silently killing the requested session.
- `static/offline.js` carried a large-3DS lock (`embeddedThreeDsLimit`) and a
  "Large 3DS ROMs need the native engine... Choose Play 3DS native" toast, plus a
  "Large ROM: native Azahar..." note.
- The native shell referenced its assets at `?v=0.4.5`, so an updated APK could
  keep serving the WebView-cached old library/bootstrap JS — the owner kept
  seeing the pre-fix behavior.

Fixes:
- Removed the Android `?play` redirect, the large-3DS size lock and its toast
  and note. Nothing in the front end refuses playback any more.
- `nativeRomIdForGame` now falls back to the record's own `id` on the native
  app, so **every** imported GBA/NDS/3DS ROM resolves to native playback with no
  re-import (verified with records that stored only an id).
- Bumped native-shell asset query strings to `?v=0.4.7` so the WebView fetches
  the new JS instead of a cached copy.

Testing (AVD, legal fixtures): injected GBA/NDS/3DS records storing **only**
`id`. All cards rendered "Chơi <SYS> native", enabled; `launchNative` returned
success (`""`) for all three; `NativeGameActivity` was top-resumed with the
`:game` process running and no tombstone. Guard/suite tests pass (only the two
pre-existing web-route assertions fail).

Version: Android `0.4.7` / `versionCode 4007` (bug-fix patch bump per the new
owner versioning rule now in `AGENTS.md`). APK:
`vibecodedemulator-0.4.7-android-arm64-staging.apk`, 48,077,849 bytes, SHA-256
`b713909da2c8deade20ab1f1ded79de423089179a5b0d3cf88e33589b1615da9`; catalog
`source_fingerprint` `d55c3b7f14bb2cba513fb900ee55f1bb4acaf82c2e6790ffe0598439d843c755`;
verifier PASS; old 0.4.6 APK URL returns 404.

Deployed: production `PRODUCTION_RELEASE=PASS`, asset `690bcb150246`, release
`production-…`, backup `/opt/an3-arcade-backups/20260915-134451`; staging
`STAGING_RELEASE=PASS` release
`/opt/an3-arcade-staging/releases/20260915-134525-690bcb150246`. Public APK
returns 48,077,849 bytes. AVD shut down.

## Known limitations / follow-ups

- Windows real hardware Vulkan/3DS gameplay and audio audibility remain
  unverified (the build VM has no Vulkan ICD and no interactive desktop).
- Real in-window desktop parity (macOS AppKit overlay ported to Windows/Linux)
  was intentionally out of scope per the owner's pragmatic decision; Windows and
  Linux run the shared Tauri library UI with the native player as the game window.
- Two pre-existing `tests/test_integration.py` web-route assertions (`/login`
  auth-shell route and the public drafts/enrichment flow) fail in this worktree
  and are unrelated to the native apps; they were not changed by this release.
