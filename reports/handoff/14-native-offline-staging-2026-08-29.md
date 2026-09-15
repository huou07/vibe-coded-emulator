# Native offline player — staging handoff (2026-08-29)

## Scope and deployment boundary

- Implemented and deployed to **staging only**: `http://192.168.1.8:8092`.
- Current staging release: `/opt/an3-arcade-staging/releases/20260829-213527-25818a44e433`.
- The deployment command prepares a production candidate/archive under `/tmp` on the staging machine as a rollback artifact. It does **not** execute a production deployment; no production host was accessed.
- Staging Rust netplay relay was rebuilt/enabled and responds at `http://192.168.1.8:8094`.

## Native offline application

`native-offline/` is a Rust/Tauri application. It bundles the local offline player only:

- no public web home, ROM catalogue, dashboard, or admin route;
- ROMs are selected from the local device and never uploaded by the app;
- it retains the player’s established input order: menu, virtual controls, handheld touch surface where applicable, then physical keyboard;
- the web player passes a bundled `emulatorOrigin` to EmulatorJS, so installed-app gameplay does not depend on `/offline` being served by the website.

The public staging-only page is `/download-app`. Its source bundle and installer delivery routes return 404 in production mode.

## Verified installers

| Platform | Filename | Verification |
| --- | --- | --- |
| macOS Apple Silicon | `an3-offline-0.1.0-macos-aarch64.dmg` | SHA-256 `b12ce75b442a1bff5c48a91de6727c1fde2f4392f949715605ccb634840cfed5`; app signature and DMG verification passed. |
| Android arm64 (staging/test) | `an3-offline-0.1.0-android-arm64-staging.apk` | SHA-256 `dccbba1adc1b297753bdac3940610f2d9cb02e7ddba63d9d5b9c6d6804587937`; APK Signature Scheme v2 and v3 verification passed. |

The Android APK is debug/test signed and is appropriate for sideloading on staging, not app-store distribution. The macOS build is ad-hoc signed; it is not notarized because no Apple Developer signing/notarization credentials were supplied.

Both files were downloaded again from staging and hash-verified there. The source zip includes the Cargo/Android/Flatpak build sources but excludes release binaries, signing materials, target directories, Android build cache, and `local.properties`.

The staging download page now derives each button label from the real artifact
extension. It has a DEB and Flatpak target wired to their exact expected
filenames; the buttons remain disabled until those files really exist. Debian
build dependencies are currently being installed on the staging host, then the
verified DEB will be used as the input to the Flatpak manifest. No placeholder
Linux binary has been published.

## Still required before calling it native-performance validated

The installed app has a native Rust shell but uses the same EmulatorJS/WASM emulator core as the browser. It does not yet replace the emulator core with a desktop-native libretro/core integration. Therefore, the real remaining acceptance test is launching the macOS app, loading the local decrypted Pokémon X ROM, and measuring 3DS gameplay/FPS on the unlocked Mac.

The Mac UI was locked during the attempted launch/interaction test, so that last gameplay check could not be performed. The known local ROM was not copied to staging or transmitted.

Windows (`.exe`), Debian (`.deb`), Flatpak, and iOS artifacts have not been fabricated. Producing them needs their respective build environments: Windows toolchain/cross-linker, a Linux runner/container for WebKit/GTK packaging, and full Xcode plus Apple signing for iOS.

## Validation completed

- `python3 -m unittest discover -s tests -v` — 38 tests passed.
- `npm run check` in `native-offline/` passed.
- macOS code-signature verification and `hdiutil verify` passed.
- Android APK v2/v3 signature verification passed.
- Staging `/health`, native installer downloads, source-bundle isolation, and netplay `/games` endpoint passed.
