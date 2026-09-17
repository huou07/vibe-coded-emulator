# EmulatorRust native core notices

This macOS-arm64 staging build includes the following native components.

## Vibe Coded Emulator (the application itself)

The Vibe Coded Emulator application code (the Tauri shell, the portable native
runtime under `native-offline/native-runtime/`, the Android Kotlin/C++ hosts,
and the web assets) is Copyright (C) 2026 Vibe Coded Emulator contributors and
is licensed under **GPL-3.0-or-later**. The full license text is in `LICENSE`
at the repository root and should be shipped alongside this file.

## EmulatorJS 4.2.3 (served to the web player and cached by the native shells)

EmulatorJS is licensed under **GPL-3.0** by the EmulatorJS contributors
(https://github.com/EmulatorJS/EmulatorJS). The native shells cache its
`data/` and `data-v2/` distributions under `dist/emulatorjs/` and the Android
assets. Its corresponding source is the upstream repository at the version
string reported by `emulator.min.js` (`ejs_version`).

## Tauri, Rust and Android dependencies

The native shells build on Tauri 2 and `tauri-plugin-dialog` (Apache-2.0 OR
MIT), `include_dir`, `serde` and `serde_json` (MIT/Apache-2.0), and the crates
pinned in `src-tauri/Cargo.lock`. The Android build additionally uses AndroidX
WebKit/AppCompat/Activity/Lifecycle (Apache-2.0), Google Material Components
(Apache-2.0), Apache Commons Compress 1.21 (Apache-2.0) and XZ for Java 1.9
(public domain). See the repository-root `THIRD_PARTY_NOTICES.md` for the table.

## Azahar libretro 2126.1.1

`azahar_libretro.dylib` is from the official Azahar 2126.1.1 release and is licensed under GPL-2.0-or-later. Its GPL text is included in the app at `Resources/azahar/macos-arm64/Azahar-GPL-2.0-or-later.txt`.

- Core SHA-256: `90f96cc9b8e6c9570e631fd61d4e8b2ee65de00d2171ffc86068c6eb49b5d5ad`
- Release archive SHA-256: `9557400c89d463a7d163d925741172173f0c64d8096e5996239fac46eefdffd5`
- Upstream source, tag 2126.1.1: https://github.com/azahar-emu/azahar/tree/2126.1.1
- Official corresponding-source archive: https://github.com/azahar-emu/azahar/releases/download/2126.1.1/azahar-unified-source-2126.1.1.tar.xz

The EmulatorRust host source used with this component is in this source tree under `native-offline/src-tauri/src/azahar_host.*` and `native-offline/src-tauri/src/vulkan_frontend.*`. This staging artifact must remain accompanied by access to this source tree and the pinned upstream source above. Do not publish it as a standalone proprietary distribution.

## Azahar libretro 2126.1.1 — Android arm64-v8a

The Android staging package includes the official `azahar_libretro.so` as
`libazahar_libretro_android.so`, renamed only for Android package clarity. It
uses the same GPL-2.0-or-later license and corresponding source archive as the
macOS core above.

- Core SHA-256: `de4364104250bd6f7b61b06ef4286a4835924382936b89cf4836e0462305c2c3`
- Release archive SHA-256: `9b13b40be733cd182c24be45f59b382660b516d03aca73a4d3549232b91ff70c`
- Release asset: `azahar-libretro-android-arm64-v8a-2126.1.1.zip`

The portable host source is under `native-offline/native-runtime/`; it uses
Azahar's libretro Vulkan image/synchronization interface directly and does not
use a CPU readback or re-upload path for 3DS frames.

## mGBA libretro 0.11-219-e31759b

`mgba_libretro.dylib` is the mGBA libretro core. It is licensed under MPL-2.0; its license text is included in the app at `Resources/libretro/macos-arm64/mGBA-MPL-2.0.txt`.

- Core SHA-256: `085350861044d9d2ef37634a7c201f57b4816fd343bdf29cdcd09bfb754b9218`
- Pinned buildbot archive SHA-256: `1c1679f1f62c5c1bef6e9f5de111555f7600976b8a67df4d960e41e189ef9d96`
- Corresponding source: https://github.com/mgba-emu/mgba/tree/e31759b24e7a4e3899285ff720d7b573ac328ae7
- License source: https://raw.githubusercontent.com/mgba-emu/mgba/e31759b24e7a4e3899285ff720d7b573ac328ae7/LICENSE

## melonDS DS libretro 1.3.1

`melondsds_libretro.dylib` is the maintained melonDS DS libretro core. It is licensed under GPL-3.0-or-later; its license text is included in the app at `Resources/libretro/macos-arm64/melonDS-DS-GPL-3.0-or-later.txt`.

- Core SHA-256: `028c1d65db6eeafef33b29a90018fe037fcf0f643965031f3eb4a8b1ca23b57a`
- Pinned compatible macOS-arm64 buildbot archive SHA-256: `cc1667f1f0e50a06fcb2c5583d9ea38cfb8e1457cab247ee2c21c943b3275486`
- Corresponding source, v1.3.1 commit: https://github.com/JesseTG/melonds-ds/tree/bc4e4b67d2d470d7c682810a1e892cafd6f9082b
- License source: https://raw.githubusercontent.com/JesseTG/melonds-ds/bc4e4b67d2d470d7c682810a1e892cafd6f9082b/LICENSE

The archive URL is a buildbot location because the publisher's release asset currently targets a newer macOS version than this app. `scripts/fetch-gba-nds-libretro.mjs` verifies both archive and extracted-core hashes before bundling, so it fails closed if the buildbot content changes.

## MoltenVK 1.4.2

`libMoltenVK.dylib` translates Vulkan calls to Metal. It is licensed under Apache-2.0; its license is included in the app at `Resources/azahar/macos-arm64/MoltenVK-LICENSE`.

- Library SHA-256: `aef00b13bcc808adf15b85bef9ae67393d92be7ed5dfe41cad16fa809e4a4c5f`
- Release archive SHA-256: `f95765a6229cb7b915990a2890ce12ebe36a730b021545d3d52ae69ce4c4024e`
- Upstream: https://github.com/KhronosGroup/MoltenVK

## Apache Commons Compress 1.21 — Android archive inspection

The Android private-ROM importer uses Apache Commons Compress 1.21 solely to
inspect and stream one selected 7z entry. It is licensed under Apache-2.0.
The importer still enforces safe entry paths, a 256-entry bound, and 512 MiB
compressed/extracted-size limits before committing the selected file.

- Upstream: https://commons.apache.org/proper/commons-compress/

## XZ for Java 1.9 — Android 7z LZMA/LZMA2 decoding

Apache Commons Compress uses XZ for Java to decode LZMA/LZMA2 7z entries.
It is bundled only for bounded, app-private inspection and streaming of the
one selected archive entry. XZ for Java is in the public domain.

- Upstream: https://tukaani.org/xz/java.html

## Nintendo Switch companion (macOS) — Eden bridge

`Resources/switch/macos-arm64/an3_switch_companion` is Vibe Coded Emulator's
own Eden bridge (GPL-3.0-or-later), built inside Eden's tree and shipped as a
**separate process**. It statically contains Eden at the pinned commit
`7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c` (GPL-3.0-or-later; per-file
GPL-2.0-or-later/GPL-3.0-or-later). Eden is not vendored in this repository.

- Eden corresponding source: https://git.eden-emu.dev/eden-emu/eden at the pin above
- Bridge source: this repository, `native/eden-bridge/`
- GPL text shipped in the app: `Resources/switch/macos-arm64/EDEN-GPL-3.0-or-later.txt`
- Exact binary hash and the bundled third-party dylibs: `Resources/switch/macos-arm64/manifest.json`

No firmware, `prod.keys`/`title.keys` or commercial ROM is bundled; the verified
path uses legal homebrew (`.nro`) only.
