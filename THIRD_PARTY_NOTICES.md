# Third-party notices — Vibe Coded Emulator

Vibe Coded Emulator is licensed under `GPL-3.0-or-later` (see `LICENSE`).
It bundles, links, or serves the third-party components below. Each component
remains under its own license and copyright; this project does not relicense
any of them.

Where a component is a compiled emulator core (GPL or MPL), the release process
must keep the corresponding source available. The pinned revisions and, where
published, official source archives are listed here.

## Emulator cores

| Component | Version / revision | License | Copyright | Corresponding source |
| --- | --- | --- | --- | --- |
| Azahar libretro (`azahar_libretro.dylib`, `libazahar_libretro_android.so`) | 2126.1.1 | GPL-2.0-or-later | Azahar Emulator Project | https://github.com/azahar-emu/azahar/tree/2126.1.1 — releases also publish `azahar-unified-source-2126.1.1.tar.xz` |
| melonDS DS libretro (`melondsds_libretro.so`/`.dylib`/`.dll`) | 1.3.1 @ `bc4e4b67d2d470d7c682810a1e892cafd6f9082b` | GPL-3.0-or-later | melonDS DS contributors | https://github.com/JesseTG/melonds-ds/tree/bc4e4b67d2d470d7c682810a1e892cafd6f9082b |
| mGBA libretro (`mgba_libretro.so`/`.dylib`/`.dll`) | 0.11-219 @ `e31759b24e7a4e3899285ff720d7b573ac328ae7` | MPL-2.0 | mGBA contributors | https://github.com/mgba-emu/mgba/tree/e31759b24e7a4e3899285ff720d7b573ac328ae7 |

Core and archive SHA-256 pins, plus the bundled license texts
(`native-core-licenses/`), are recorded in
`native-offline/THIRD_PARTY_NOTICES.md`. `scripts/fetch-*.mjs` verify hashes
before bundling and fail closed if upstream content changes.

## Web player and networking

| Component | Version | License | Copyright | Notes |
| --- | --- | --- | --- | --- |
| EmulatorJS (`emulator.min.js`, loader, cores — served to the browser and cached by the native shells) | 4.2.3 | GPL-3.0 | EmulatorJS contributors | https://github.com/EmulatorJS/EmulatorJS — the web player loads it from the configured EmulatorJS origin |
| EmulatorJS-Netplay relay (separate Docker service, not part of the app binary) | pinned commit `4090ca7bda795a8b7a7596f4d41a4605b515d9c5` | Apache-2.0 | EmulatorJS contributors | `Dockerfile.rust-netplay` ships the upstream license into the image |

## Native runtime and platform libraries

| Component | License | Copyright |
| --- | --- | --- |
| MoltenVK 1.4.2 | Apache-2.0 | The Khronos Group |
| `libretro.h` (libretro API header) | Permissive (MIT-style), see `libretro.h.LICENSE.txt` | RetroArch team |
| Tauri 2, `tauri-plugin-dialog` | Apache-2.0 OR MIT | Tauri contributors |
| `include_dir`, `serde`, `serde_json` and the other crates pinned in `native-offline/src-tauri/Cargo.lock` (448 packages) | MIT / Apache-2.0 / BSD family | respective crate authors |

## Android

| Component | License | Copyright |
| --- | --- | --- |
| AndroidX WebKit / AppCompat / Activity / Lifecycle Process | Apache-2.0 | The Android Open Source Project |
| Google Material Components | Apache-2.0 | Google LLC |
| Apache Commons Compress 1.21 | Apache-2.0 | The Apache Software Foundation |
| XZ for Java 1.9 | Public domain | Lasse Collin |

## Web assets and fonts

| Component | License | Copyright |
| --- | --- | --- |
| Lucide icons (`static/ui-*.svg`) | ISC | Lucide Icons and Contributors (`static/LUCIDE-LICENSE.txt`) |
| Pixelify Sans | SIL OFL 1.1 | Pixelify Sans authors (`static/fonts/OFL-PixelifySans.txt`) |
| Roboto Condensed | SIL OFL 1.1 | Roboto Condensed authors (`static/fonts/OFL-RobotoCondensed.txt`) |
| `qrcodegen.py` | MIT | Project Nayuki |

## Not bundled

No proprietary firmware, `prod.keys`/`title.keys`, BIOS files, or commercial
ROMs are distributed. Users supply their own legally obtained game files.

## Corresponding source

The complete corresponding source for this project is the repository itself at
the revision recorded in `native-offline/releases/catalog.json` for each
release. Third-party component source is available at the links above and in
`native-offline/THIRD_PARTY_NOTICES.md`.
