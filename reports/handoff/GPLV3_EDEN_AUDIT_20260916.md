# Engineering report — GPLv3 licensing audit + Eden evaluation (2026-09-16)

Concise report for the licensing transition and the Eden investigation. Nothing
here is claimed beyond what was run or verified.

## 1. License audit summary

Full table: `docs/licensing/license-audit.md`. Findings:

- The repository had **no `LICENSE`** and no license declaration in the app
  config; only third-party notices existed. The old README still described the
  earlier "Ăn 3 Tô Cơm" web game.
- Every bundled/linked/served component is compatible with a
  **GPL-3.0-or-later** combined work. No STOP condition was triggered.
- No commercial ROMs, `prod.keys`, firmware, or BIOS are present anywhere in the
  tree; legal test ROMs live only in untracked work directories.

## 2. GPL-compatible components

- **Azahar libretro 2126.1.1** — GPL-2.0-or-later (compatible via "or later").
- **melonDS DS libretro 1.3.1** — GPL-3.0-or-later.
- **mGBA libretro 0.11-219** — MPL-2.0 (GPL-compatible; file-level copyleft).
- **EmulatorJS 4.2.3** (served/cached) — GPL-3.0.
- **EmulatorJS-Netplay relay** (separate service) — Apache-2.0.
- **MoltenVK 1.4.2** — Apache-2.0; **libretro.h** — permissive.
- **Tauri 2**, `tauri-plugin-dialog`, `include_dir`, `serde`, `serde_json` and
  448 crates pinned in `Cargo.lock` — MIT/Apache-2.0/BSD.
- **AndroidX / Material / Apache Commons Compress** — Apache-2.0;
  **XZ for Java** — public domain.
- **Lucide** — ISC; **Pixelify Sans / Roboto Condensed** — SIL OFL 1.1;
  **qrcodegen** — MIT.

## 3. Incompatible or unresolved components

- **None incompatible.**
- Requires review (documented, not blocking): a byte-for-byte Android Gradle
  transitive manifest is not committed (direct deps are Apache-2.0/public
  domain; transitive are Apache-2.0). Archive `gradle :app:dependencies` with
  the next Android release.

## 4. Files created or modified

Created: `LICENSE` (official GPLv3 text, sha256 `3972dc97…`),
`THIRD_PARTY_NOTICES.md` (root), `docs/checkpoints/gplv3-eden-integration.md`,
`docs/licensing/license-audit.md`, `docs/licensing/distribution-compliance.md`,
`docs/licensing/eden-integration-feasibility.md`, `tests/test_licensing.py`.

Modified: `README.md` (rewritten with licensing), `app.py` (LICENSE constants,
`/licenses` + `/licenses/gpl-3.0.txt` routes, footer link, `licenses_page`),
`static/site.css` (licenses styles), `native-offline/web/index.html` (Licenses
card), `native-offline/THIRD_PARTY_NOTICES.md` (+ Android asset copy), all five
`native-offline` version fields → `2.0.0`, Flatpak manifest/metainfo,
`deploy/package-staging.sh`, `deploy/package-production.sh`,
`deploy/update-production.sh`, `native-offline/src-tauri/tauri.conf.json`
(bundle `LICENSE`), `native-offline/src-tauri/gen/android/app/src/main/assets/LICENSE`,
82 original source files (SPDX headers), plus catalog/tests/handoff docs.

## 5. Copyright and attribution changes

- Original code now declares `SPDX-License-Identifier: GPL-3.0-or-later` and
  `SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors` (84 files).
- Third-party files were **not** touched (verified: `qrcodegen.py` and
  `libretro.h` carry no GPL stamp).
- **No §7(b) attribution notice was added.** The plain GPL notices plus the
  retained third-party notices already meet the owner's goals; an extra term
  would be an unnecessary restriction. Forks need not keep the name/logo/UI.
- **Open item for the owner:** the README's source URL is the placeholder
  `https://REPLACE-WITH-PUBLIC-REPOSITORY-URL` (overridable via
  `AN3_SOURCE_REPOSITORY`). No URL was invented. Replace it with the real public
  repository before a public release.

## 6. Exact Eden source commit

`7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c` (2026-09-16),
`https://git.eden-emu.dev/eden-emu/eden`, license GPL-3.0-or-later with
per-file SPDX (`LICENSES/`: Apache-2.0, BSD, MIT, MPL-2.0, LGPL-3.0-or-later…).

## 7. Direct integration architecture — status: BLOCKED (technical)

Eden exposes **no embeddable/FFI interface**: `src/core` is a CMake static
library (`add_library(core STATIC …)`) with a C++ API and a large dependency
graph (`common`, `video_core`, `audio_core`, `hid_core`, `network`,
`shader_recompiler`, `dynarmic`, Boost/SDL2/Vulkan/FFmpeg/…); `src/ffi`,
`src/c_api` and `src/libretro` do not exist; the frontends are Qt6 applications.
Direct integration therefore requires writing and maintaining a new C++/C
capability layer plus a Vulkan presentation bridge — substantial first-party
work, not achievable or verifiable in this environment (and no legal Switch test
content is available to run Steps A–G). Per the instructions, a companion-process
substitute was **not** silently introduced. Details and the incremental path are
in `docs/licensing/eden-integration-feasibility.md`.

**Switch is not integrated. No Switch functionality is claimed.**

## 8. Supported platforms (existing cores, unchanged)

macOS (Metal/MoltenVK; ad-hoc signed, not notarized), Windows (Vulkan/OpenGL),
Linux (Vulkan/OpenGL), Android (Vulkan/OpenGL ES), plus the web player.

## 9. Build and test results

- Suite: **271 tests, 0 failures** (264 + 7 licensing).
- Built 2.0.0: macOS DMG, Android APK, Linux DEB + Flatpak, Windows EXE.
- `RELEASE_CATALOG=PASS (5 installers)`.
- Verified the GPL notices are inside the packages: macOS app `Resources/LICENSE`
  + notices; Android `assets/LICENSE`, `assets/THIRD_PARTY_NOTICES.md`,
  `assets/native-core-licenses/*`; DEB `/usr/lib/VibeCodedEmulator/LICENSE` +
  notices + core license texts; Flatpak (built from the DEB); Windows install
  root `LICENSE` + `THIRD_PARTY_NOTICES.md`.

## 10. Performance measurements

None claimed. No renderer or core code was changed; the licensing/notices work
does not alter the emulation paths.

## 11. Staging deployment status

Deployed to staging only: asset `973c9002b67f`, release
`/opt/an3-arcade-staging/releases/20260916-210751-973c9002b67f`, rollback
`20260916-180157-e792e8578089`. Verified: `/licenses` 200,
`/licenses/gpl-3.0.txt` 200 (35,149 bytes), all five 2.0.0 installer URLs 200
with the catalog sizes. **Production untouched.**

## 12. Remaining limitations and blockers

- **Eden/Switch direct integration: not done** (technical blocker above).
- Public **source repository URL** is a placeholder — owner must supply it.
- Android Gradle transitive license manifest not yet archived.
- macOS remains ad-hoc signed / not notarized (no Apple credentials).
- Windows 2.0.0 is built/lauched only (no gameplay verified); Linux runtime
  smoke was done for earlier versions; the 2.0.0 packages were not re-run as
  games on this pass.
- The owner should confirm legal copyright-holder wording ("Vibe Coded Emulator
  contributors") if they want a specific entity or personal name.
