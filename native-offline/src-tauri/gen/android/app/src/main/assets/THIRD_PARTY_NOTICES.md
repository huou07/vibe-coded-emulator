# EmulatorRust native core notices

This macOS-arm64 staging build includes the following native components.

## Azahar libretro 2126.0

`azahar_libretro.dylib` is from the official Azahar 2126.0 release and is licensed under GPL-2.0-or-later. Its GPL text is included in the app at `Resources/azahar/macos-arm64/Azahar-GPL-2.0-or-later.txt`.

- Core SHA-256: `c335492796a79c5af813c3102170f85352aa3bc49747c89a2765ae98b33753e8`
- Release archive SHA-256: `ed90792e2772bb379b831ebbe77c1aa57bdf23397d17baf638dc3b811ed8ed64`
- Upstream source, tag 2126.0: https://github.com/azahar-emu/azahar/tree/2126.0
- Official corresponding-source archive: https://github.com/azahar-emu/azahar/releases/download/2126.0/azahar-unified-source-2126.0.tar.xz

The EmulatorRust host source used with this component is in this source tree under `native-offline/src-tauri/src/azahar_host.*` and `native-offline/src-tauri/src/vulkan_frontend.*`. This staging artifact must remain accompanied by access to this source tree and the pinned upstream source above. Do not publish it as a standalone proprietary distribution.

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
