# Vibe Coded Emulator native third-party notices

Vibe Coded Emulator is licensed under **GPL-3.0-or-later**. The full license
is included as `LICENSE` alongside this file.

This notice applies to the native macOS, Windows, Linux, and Android packages.
Platform-specific core versions, source revisions, archive hashes, and
packaged binary hashes are recorded in the corresponding files under
`vendor/` and in `native-offline/releases/catalog.json` for published
artifacts. Each bundled component retains its own license and copyright.

## EmulatorJS 4.2.3

EmulatorJS is licensed under **GPL-3.0** by the EmulatorJS contributors:
<https://github.com/EmulatorJS/EmulatorJS>. The native shells cache its
`data/` and `data-v2/` distributions under `dist/emulatorjs/` and in the
Android assets. Its corresponding source is the upstream repository at the
version reported by `emulator.min.js` (`ejs_version`).

## Tauri, Rust, and Android dependencies

The native shells use Tauri 2, `tauri-plugin-dialog` (Apache-2.0 OR MIT),
`include_dir`, `serde`, and `serde_json` (MIT/Apache-2.0), plus the crates
pinned in `src-tauri/Cargo.lock`. The Android package also uses AndroidX
WebKit/AppCompat/Activity/Lifecycle (Apache-2.0), Google Material Components
(Apache-2.0), Apache Commons Compress 1.21 (Apache-2.0), and XZ for Java 1.9
(public domain). See the repository-root `THIRD_PARTY_NOTICES.md` for the
project-wide component table.

## Emulator cores

### Azahar libretro 2126.1.1

Azahar is licensed under **GPL-2.0-or-later**. The full license text is
`native-core-licenses/Azahar-GPL-2.0-or-later.txt`.

- Upstream source: <https://github.com/azahar-emu/azahar/tree/2126.1.1>
- Corresponding-source archive:
  <https://github.com/azahar-emu/azahar/releases/download/2126.1.1/azahar-unified-source-2126.1.1.tar.xz>

The macOS and Android cores are the official release builds. The host source
that loads the core is in `native-offline/src-tauri/src/` and
`native-offline/native-runtime/`.

### mGBA libretro

mGBA is licensed under **MPL-2.0**. The full license text is
`native-core-licenses/mGBA-MPL-2.0.txt`.

- Corresponding source, revision
  `e31759b24e7a4e3899285ff720d7b573ac328ae7`:
  <https://github.com/mgba-emu/mgba/tree/e31759b24e7a4e3899285ff720d7b573ac328ae7>
- License source:
  <https://raw.githubusercontent.com/mgba-emu/mgba/e31759b24e7a4e3899285ff720d7b573ac328ae7/LICENSE>

The macOS and Android cores use this pinned source. The Windows core is built
from the same revision with the compatibility patch documented by its
platform manifest.

### melonDS DS libretro 1.3.1

melonDS DS is licensed under **GPL-3.0-or-later**. The full license text is
`native-core-licenses/melonDS-DS-GPL-3.0-or-later.txt`.

- Corresponding source, revision
  `bc4e4b67d2d470d7c682810a1e892cafd6f9082b`:
  <https://github.com/JesseTG/melonds-ds/tree/bc4e4b67d2d470d7c682810a1e892cafd6f9082b>
- License source:
  <https://raw.githubusercontent.com/JesseTG/melonds-ds/bc4e4b67d2d470d7c682810a1e892cafd6f9082b/LICENSE>

### MoltenVK 1.4.2

MoltenVK translates Vulkan calls to Metal and is licensed under
**Apache-2.0**. The full license text is
`native-core-licenses/MoltenVK-LICENSE`.
Upstream project: <https://github.com/KhronosGroup/MoltenVK>.

## Nintendo Switch companion (macOS) — Eden bridge

The `an3_switch_companion` bridge is Vibe Coded Emulator code licensed under
**GPL-3.0-or-later**. It is built in Eden's tree and shipped as a separate
process. Eden is pinned to
`7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c` and is licensed under
**GPL-3.0-or-later**, with per-file GPL-2.0-or-later/GPL-3.0-or-later terms.
Eden is not vendored in this repository.

- Eden source at the pinned revision: <https://git.eden-emu.dev/eden-emu/eden>
- Bridge source: `native/eden-bridge/`
- Eden license text: `native-core-licenses/EDEN-GPL-3.0-or-later.txt`
- Binary and bundled-library details: the macOS Switch vendor manifest

No firmware, `prod.keys`/`title.keys`, or commercial ROM is bundled. The
supported path uses legal homebrew (`.nro`) only.

## Other packaged components

- Apache Commons Compress 1.21 is used by the Android private-ROM importer
  to inspect and stream a selected 7z entry. It is licensed under
  **Apache-2.0**. The importer enforces safe entry paths, a 256-entry bound,
  and 512 MiB compressed/extracted-size limits.
- XZ for Java 1.9 is used by Apache Commons Compress for LZMA/LZMA2 decoding
  and is in the **public domain**. Upstream: <https://tukaani.org/xz/java.html>.

The project does not distribute proprietary firmware, `prod.keys`/`title.keys`,
BIOS files, or commercial ROMs. Users supply their own legally obtained game
files.
