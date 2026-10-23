# License audit — Vibe Coded Emulator (2026-10-21; Azahar provenance updated 2026-10-23)

Scope: the account-free core-only application distributed by this repository —
the Python web server (`app.py`, `bug_report.py`, `netcode.py` and
`qrcodegen.py`), web client (`static/`), Tauri desktop shells
(`native-offline/src-tauri/`), portable native player
(`native-offline/native-runtime/`), Android app, and bundled, linked, or served
dependencies. Account, cloud-sync, CMS/analytics and phone-controller surfaces
are not part of this product. Method: repository inspection, bundled license
files, `cargo metadata --locked` for exact Cargo package license fields, npm
lock metadata, the Android `armReleaseRuntimeClasspath` and
`x86ReleaseRuntimeClasspath` reports and cached Maven POM/JAR notices, plus
upstream license records. Ambiguous cases are called out
explicitly rather than assumed.

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
| Vibe Coded Emulator original code (`app.py`, `bug_report.py`, `netcode.py`, `qrcodegen.py`, `static/*`, `native-offline/src-tauri/src/*` except vendor, `native-offline/native-runtime/*` except vendor, `native-runtime/platform/android` Kotlin/C++ hosts) | this repository | GPL-3.0-or-later (owner's choice) | Vibe Coded Emulator project owner | Owner-authorized | Add `LICENSE`, SPDX headers, README/notices |
| `qrcodegen.py` (vendored) | Project Nayuki | MIT | Project Nayuki | Compatible | Keep MIT header; noted in notices |
| Azahar libretro 2126.1.2 (`azahar_libretro.dylib` / `.so`) | SHA-256-pinned 2126.1.2 release assets; macOS Eden-companion build uses source commit `9e6f523a57fac9564ac0bf8286db3c3702d301ec` | GPL-2.0-or-later | Azahar Emulator Project | Compatible (GPLv2-or-later → GPLv3) | Preserve notices and per-platform manifests; ship license text; publish corresponding source offer |
| melonDS DS libretro 1.3.1 | github.com/JesseTG/melonds-ds @ bc4e4b6… | GPL-3.0-or-later | melonDS DS contributors | Compatible | Same as above |
| mGBA libretro 0.11-219-e31759b | github.com/mgba-emu/mgba @ e31759b… | MPL-2.0 | mGBA contributors | Compatible with conditions (MPL file-level copyleft; combined work GPLv3) | Ship MPL-2.0 text; note file-level copyleft |
| MoltenVK 1.4.2 | KhronosGroup/MoltenVK | Apache-2.0 | The Khronos Group | Compatible | Ship license; keep NOTICE if upstream provides one |
| `libretro.h` (native + Android assets) | RetroArch team | Permissive (MIT-style; see bundled `libretro.h.LICENSE.txt`) | RetroArch team | Compatible | Keep bundled license file |
| EmulatorJS 4.2.3 (served to the browser and cached by the native shells) | github.com/EmulatorJS/EmulatorJS | GPL-3.0 | EmulatorJS contributors | Compatible | Document; state that the app serves it and where its source is |
| EmulatorJS-Netplay relay (Docker, separate service) | EmulatorJS/EmulatorJS-Netplay | Apache-2.0 | EmulatorJS contributors | Compatible | Dockerfile already ships the upstream license |
| Tauri 2 + `tauri-plugin-dialog` | crates.io | Apache-2.0 OR MIT | Tauri contributors | Compatible | Notices only |
| Native Rust graph (480 package records in `native-offline/src-tauri/Cargo.lock`) | crates.io | Per-package license fields resolved from locked Cargo metadata | respective crate authors | Compatible | Preserve lockfile and generated inventory |
| Historical `rust-gateway` graph (183 package records; not shipped in app packages) | crates.io | Per-package license fields resolved from locked Cargo metadata | respective crate authors | Compatible | Retain source notices; gateway remains inactive |
| `@tauri-apps/cli` | npm | Apache-2.0 OR MIT | Tauri contributors | Compatible | Build-time only; notices only |
| AndroidX/Kotlin Android runtime graph (`armReleaseRuntimeClasspath`, `x86ReleaseRuntimeClasspath`) | Google Maven, Maven Central | Apache-2.0; see resolved-graph audit below | respective authors, including AOSP and Google | Compatible | Preserve graph reports and license evidence |
| Google Material Components 1.13.0 (resolved version) | Google Maven | Apache-2.0 | Google LLC | Compatible | Notices only |
| Guava ListenableFuture 1.0 | Google Guava | Apache-2.0 | Google | Compatible | Record upstream license source |
| Apache Commons Compress 1.21 | Apache | Apache-2.0 | The Apache Software Foundation | Compatible | Keep embedded `META-INF/LICENSE.txt` and notice |
| XZ for Java 1.9 | tukaani.org | Public domain | Lasse Collin | Compatible | Notices only |
| Lucide icons (`static/ui-*.svg`) | lucide.dev | ISC | Lucide Icons and Contributors | Compatible | `static/LUCIDE-LICENSE.txt` retained |
| Pixelify Sans, Roboto Condensed (`static/fonts/`) | Google Fonts | SIL OFL 1.1 | respective font authors | Compatible (OFL; fonts not relicensed) | `static/fonts/OFL-*.txt` retained; do not relicense the font files |
| Brand/icon/artwork assets (`brand-logo.png`, `icon-*.png`, `default-cover.png`, `offline-hero-pixel-v2.png`) | this repository | GPL-3.0-or-later (owner's) | project owner | Owner-authorized | Covered by `LICENSE`; no third-party artwork bundled |
| Python standard library (runtime, not distributed) | CPython | PSF-2.0 | Python Software Foundation | Not distributed | None |

## Components deliberately not present

- **No commercial ROMs, no test ROMs, no `prod.keys`/`title.keys`, no firmware,
  no BIOS** are tracked. Legal test ROMs live only in untracked work
  directories. This is required by the Switch plan and already enforced.
- No proprietary SDK is bundled into the distributed artifacts beyond the
  platform OS frameworks linked by the toolchains (which are not redistributed
  as source).

## Android runtime graph evidence

On 2026-10-21, the Android `armReleaseRuntimeClasspath` and
`x86ReleaseRuntimeClasspath` reports each contained 80 unique Maven
coordinates, including platform constraints, with identical selected coordinate
sets. POM metadata identified
Apache-2.0 for 77 coordinates and Public Domain for one. Two POMs omitted license
metadata: the resolved Commons Compress 1.21 JAR contains its Apache-2.0
`META-INF/LICENSE.txt`, and Guava ListenableFuture 1.0 is covered by the official
[Google Guava Apache-2.0 license](https://github.com/google/guava). The graph has
no unresolved license values. The resolved Material Components version is 1.13.0.

The dependency graph is resolved from Gradle/Maven metadata rather than a checked-in
Gradle lockfile. Retain the dependency report and corresponding license inventory
with each Android release; regenerate with
`./gradlew :app:dependencies --configuration armReleaseRuntimeClasspath` from
`native-offline/src-tauri/gen/android`.

## Ownership note

The owner states they own the original Vibe Coded Emulator code. Git history
shows only owner/automation author identities, no third-party contributors.
No file in this repository claims the owner owns Eden, Azahar, melonDS DS, mGBA,
MoltenVK, EmulatorJS, or any other third-party component; those remain under
their own copyrights and licenses.
