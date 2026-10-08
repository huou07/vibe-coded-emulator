# License audit — Vibe Coded Emulator (2026-09-16)

Scope: the combined application distributed by this repository — the Python web
server (`app.py` + modules), the web client (`static/`), the Tauri desktop
shells (`native-offline/src-tauri/`), the portable native player
(`native-offline/native-runtime/`), the Android app, and every bundled,
linked, or served dependency. Method: repository inspection, bundled license
files, `Cargo.lock`/`package.json`/Gradle metadata, and upstream project/API
lookups. Ambiguous cases are called out explicitly rather than assumed.

## Result summary

- The original Vibe Coded Emulator code is the owner's and is licensed
  **GPL-3.0-or-later** (see `LICENSE`).
- No component in the distributed app is **Incompatible** with a
  GPL-3.0-or-later combined work.
- The mixed GPL/MPL/Apache/permissive set is compatible; obligations are met by
  preserving notices and providing corresponding source (see
  `docs/licensing/distribution-compliance.md`).
- No STOP condition was triggered.

## Components

| Component | Source | License | Copyright holder | Compatibility | Required action |
| --- | --- | --- | --- | --- | --- |
| Vibe Coded Emulator original code (`app.py`, `netcode.py`, `sync_engine.py`, `google_sync.py`, `static/*`, `native-offline/src-tauri/src/*` except vendor, `native-offline/native-runtime/*` except vendor, `native-runtime/platform/android` Kotlin/C++ hosts) | this repository | GPL-3.0-or-later (owner's choice) | Vibe Coded Emulator project owner | Owner-authorized | Add `LICENSE`, SPDX headers, README/notices |
| `qrcodegen.py` (vendored) | Project Nayuki | MIT | Project Nayuki | Compatible | Keep MIT header; noted in notices |
| Azahar libretro 2126.1.1 (`azahar_libretro.dylib` / `.so`) | github.com/azahar-emu/azahar @ 2126.1.1 | GPL-2.0-or-later | Azahar Emulator Project | Compatible (GPLv2-or-later → GPLv3) | Preserve notices; ship license text; publish corresponding source offer |
| melonDS DS libretro 1.3.1 | github.com/JesseTG/melonds-ds @ bc4e4b6… | GPL-3.0-or-later | melonDS DS contributors | Compatible | Same as above |
| mGBA libretro 0.11-219-e31759b | github.com/mgba-emu/mgba @ e31759b… | MPL-2.0 | mGBA contributors | Compatible with conditions (MPL file-level copyleft; combined work GPLv3) | Ship MPL-2.0 text; note file-level copyleft |
| MoltenVK 1.4.2 | KhronosGroup/MoltenVK | Apache-2.0 | The Khronos Group | Compatible | Ship license; keep NOTICE if upstream provides one |
| `libretro.h` (native + Android assets) | RetroArch team | Permissive (MIT-style; see bundled `libretro.h.LICENSE.txt`) | RetroArch team | Compatible | Keep bundled license file |
| EmulatorJS 4.2.3 (served to the browser and cached by the native shells) | github.com/EmulatorJS/EmulatorJS | GPL-3.0 | EmulatorJS contributors | Compatible | Document; state that the app serves it and where its source is |
| EmulatorJS-Netplay relay (Docker, separate service) | EmulatorJS/EmulatorJS-Netplay | Apache-2.0 | EmulatorJS contributors | Compatible | Dockerfile already ships the upstream license |
| Tauri 2 + `tauri-plugin-dialog` | crates.io | Apache-2.0 OR MIT | Tauri contributors | Compatible | Notices only |
| `include_dir`, `serde`, `serde_json` + 445 transitive crates (`Cargo.lock`) | crates.io | MIT / Apache-2.0 / BSD family | respective authors | Compatible | Notices only; `Cargo.lock` pins exact versions |
| `@tauri-apps/cli` | npm | Apache-2.0 OR MIT | Tauri contributors | Compatible | Build-time only; notices only |
| AndroidX (`webkit`, `appcompat`, `activity-ktx`, `lifecycle-process`) | Google Maven | Apache-2.0 | The Android Open Source Project | Compatible | Notices only |
| Google Material Components | Google Maven | Apache-2.0 | Google LLC | Compatible | Notices only |
| Apache Commons Compress 1.21 | Apache | Apache-2.0 | The Apache Software Foundation | Compatible | Notices only |
| XZ for Java 1.9 | tukaani.org | Public domain | Lasse Collin | Compatible | Notices only |
| Lucide icons (`static/ui-*.svg`) | lucide.dev | ISC | Lucide Icons and Contributors | Compatible | `static/LUCIDE-LICENSE.txt` retained |
| Pixelify Sans, Roboto Condensed (`static/fonts/`) | Google Fonts | SIL OFL 1.1 | respective font authors | Compatible (OFL; fonts not relicensed) | `static/fonts/OFL-*.txt` retained; do not relicense the font files |
| Brand/icon/artwork assets (`brand-logo.png`, `icon-*.png`, `default-cover.png`, `offline-hero-pixel-v2.png`) | this repository | GPL-3.0-or-later (owner's) | project owner | Owner-authorized | Covered by `LICENSE`; no third-party artwork bundled |
| Google Drive / OAuth client module (`google_sync.py`) | this repository | GPL-3.0-or-later | project owner | Owner-authorized | Uses Google APIs at runtime only |
| Python standard library (runtime, not distributed) | CPython | PSF-2.0 | Python Software Foundation | Not distributed | None |

## Components deliberately not present

- **No commercial ROMs, no test ROMs, no `prod.keys`/`title.keys`, no firmware,
  no BIOS** are tracked. Legal test ROMs live only in untracked work
  directories. This is required by the Switch plan and already enforced.
- No proprietary SDK is bundled into the distributed artifacts beyond the
  platform OS frameworks linked by the toolchains (which are not redistributed
  as source).

## Unresolved / requires review

- **Android Gradle transitive graph** is pinned in `gen/android/build.gradle.kts`
  (Kotlin/AGP versions) and resolved from Google/Maven Central. The direct
  dependencies listed above are all Apache-2.0/public-domain; the remaining
  transitive AndroidX/Kotlin artifacts are Apache-2.0. No incompatible
  component was found, but a byte-for-byte transitive manifest is not committed;
  `gradle :app:dependencies` should be archived with the next Android release.
- **`native-offline/src-tauri/gen/android/app/src/main/assets/emulatorjs/`** is a
  cached copy of the EmulatorJS distribution. It carries no local license file;
  EmulatorJS's GPL-3.0 text is not currently bundled next to the cache. Add the
  EmulatorJS license to the app notices and link its source (done in
  `THIRD_PARTY_NOTICES.md`).

## Ownership note

The owner states they own the original Vibe Coded Emulator code. Git history
shows only owner/automation author identities, no third-party contributors.
No file in this repository claims the owner owns Eden, Azahar, melonDS DS, mGBA,
MoltenVK, EmulatorJS, or any other third-party component; those remain under
their own copyrights and licenses.
