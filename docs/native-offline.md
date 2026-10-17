# AN3 Offline native app

`native-offline/` is a Tauri 2 application with a Rust shell. Its bundled UI
contains only the local-ROM picker/library and player. It does not package
`app.py`, the SQLite database, dashboard, account routes, shared-library pages,
or any server ROM.

The player deliberately keeps the existing interaction contract:

1. Menu
2. Virtual controls (including the existing Touch on/off control and the
   Move → drag → Done persistence flow)
3. NDS/3DS/system touch surface
4. Computer physical keyboard

## Build locally

Install a supported Rust toolchain and the platform prerequisites for Tauri 2,
then run from `native-offline/`:

```sh
npm install
npm run check
npm run build:macos
```

On Linux, `npm run build:deb` routes to `native-offline/scripts/build-linux-staging.sh deb`: it
verifies the pinned libretro cores, compiles the native player, stages
`vendor/runtime/linux-x86_64/`, and only then packages the Tauri shell. It needs
one input the repository does not carry: the EmulatorJS runtime assets. The
`/stable` files come from the public EmulatorJS CDN, but `/latest/data-v2/*` is
the repaired Azahar runtime and is published only by a seeded AN3 runtime source
(`AN3_OFFLINE_RUNTIME_SOURCE`, default `http://127.0.0.1:8092/emulatorjs`) or by
a pre-populated frozen dependency cache (`AN3_DEPENDENCY_CACHE`). Without either,
the build stops on that asset and names the boundary instead of packaging a shell
with a broken 3DS runtime.

The build script copies only `static/` plus `native-offline/web/` into the
Tauri frontend bundle. The macOS package includes pinned native mGBA, melonDS
DS, and Azahar libretro cores plus the Vulkan/MoltenVK renderer dependencies,
so playing an imported ROM does not need a first-run core download. Locally
selected ROMs and play data remain on the device.

On Android, GBA and NDS run in the packaged player. Nintendo 3DS ROMs are
copied to AN3's private application storage and can be handed by a read-only,
per-ROM Android content URI to the installed Azahar native companion. After
installing that companion, complete its one-time setup before choosing a 3DS
game in AN3. This is the performance-first route and keeps the ROM out of
shared external storage.

On macOS Apple Silicon, GBA, NDS, and 3DS run through bundled libretro cores
inside the EmulatorRust window: mGBA, melonDS DS, and Azahar respectively. No
separately installed or launched emulator app is used. 3DS uses Azahar's
native Vulkan renderer; GBA and NDS use native CPU emulation and upload their
software frames through Vulkan → bundled MoltenVK → Metal. The overlay retains
the player contract—Menu → virtual controls → touchscreen → physical
keyboard—and streams the selected local ROM directly from app-private storage
rather than materializing it in WebKit. For NDS, click the game display or
choose **Lock cursor** to control the touchscreen with relative pointer
movement; the first Esc releases the cursor and the second Esc returns to the
library. 3DS accepts decrypted 3DS/3DSX/CCI/CXI-style files; ZIP archives and
CIA install packages are intentionally rejected until an in-app installer is
implemented.

## Platform release commands

- macOS: run `npm run build:macos` on macOS. It makes the `.app` then a DMG
  with an ad-hoc signature for staging. Sign and notarize the generated
  application with an Apple Developer identity before publishing a DMG.
- Windows: run `npm run build:windows` on Windows and sign the generated installer
  before publishing NSIS/MSI output.
- Linux: run `npm run build:deb` on Debian/Ubuntu to produce the
  target-compatible DEB. A Flatpak is built from that verified DEB in the
  Flatpak runtime so it carries the runtime's correct WebKit/GTK libraries.
  The `flatpak/` manifest uses the DEB only as its local build source and
  creates a standalone `.flatpak`; it does not publish the application to
  Flathub.
- Android: install Android Studio/SDK, run `npm run android:init` once, then
  `npm run android:build`; sign the APK/AAB with the Android release key.
- iOS: on macOS with Xcode and an Apple Developer team, run
  `npm run ios:init` once, then `npm run ios:build`; archive/sign in Xcode for
  TestFlight or App Store delivery.

No binary URL should be published until its build and platform signature are
available. The staging web route `/download-app/source` exposes this source
bundle only on staging/development; production returns 404. Built installer
files are served only from `native-offline/releases/` through the staging-only
`/download-app/release/<filename>` route, never from the application database
or ROM folders.

The Android ARM64 staging APK is signed with an isolated debug/testing key so
that it can be installed for staging validation. It is not a Play-distribution
or long-lived release signing identity; a production APK/AAB must be rebuilt
and signed with the owner-controlled release key.

## Performance boundary

Tauri removes the browser-tab/PWA shell and packages an OS WebView with a Rust
host. On macOS Apple Silicon, GBA/NDS/3DS use native in-process libretro cores.
This is deliberately precise: mGBA and melonDS DS remain CPU emulators whose
frames are uploaded over Vulkan/MoltenVK/Metal; only Azahar uses a Vulkan
emulation renderer. Native core licensing, save compatibility, input behavior,
and mobile packaging remain system-specific and are documented in the bundled
third-party notices.
