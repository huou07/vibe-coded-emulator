# Vibe Coded Emulator 2.2.0 — all-platform rebuild + staging deploy (2026-09-17)

Staging-only. Production was not touched. Every packaged app was rebuilt from the
committed source on its own builder and moved from 2.1.0 to **2.2.0** so the new
bytes never overwrite the published 2.1.0 artifacts (RG-112).

## Version bump

`2.1.0` → `2.2.0` (minor: rebuild of the existing feature set). Applied to
`package.json`, `src-tauri/tauri.conf.json`, `src-tauri/tauri.android.conf.json`,
`src-tauri/Cargo.toml`, `src-tauri/Cargo.lock`, `web/index.html` (cache-busting +
displayed version), the Flatpak manifest + metainfo, the regenerated Android asset
copy, and the catalog. Version assertions in `tests/test_phase_a_branding_autosave_exit.py`
and `tests/test_integration.py` were updated.

## Artifacts (gitignored; sidecars + catalog tracked)

| Format | Filename | Size | SHA-256 |
| --- | --- | --- | --- |
| macOS DMG | `vibecodedemulator-2.2.0-macos-aarch64.dmg` | 44,894,345 | `9886088642cd471731195272d64c50177919a9cc2f6c3e67a172c01310457d4b` |
| Android APK | `vibecodedemulator-2.2.0-android-arm64-staging.apk` | 49,747,084 | `0546c3438da05d4a014f2e2cbe24e98173ff5d3408a2e9484eac8d48e0403d40` |
| Linux DEB | `vibecodedemulator-2.2.0-linux-amd64.deb` | 45,647,902 | `deff093d9801d55b82c5b0450054952b1075ccf7df12ec2053f0b760c8c46eb2` |
| Linux Flatpak | `an3-offline-2.2.0-linux-amd64-staging.flatpak` | 29,187,832 | `3a4528dc5dd3a04ca2cb71f24bc233d0d7a973f01186785b85628922bf73f00a` |
| Windows EXE | `vibecodedemulator-2.2.0-windows-x64-staging.exe` | 47,014,767 | `7af7d49a03fef8361024128b7de0b36e7993a208e45517354937103322110a4a` |

`tools/verify-release-catalog.py` → **RELEASE_CATALOG=PASS (5 installers)**.

## Build hosts and path

- **macOS + Android** (Mac, Apple Silicon): `npm run build:macos`,
  `bash scripts/build-android-staging.sh`.
- **Linux** (authorized Debian builder `an3-dell`): the 2.2.0 source was rsynced
  into `~/an3-verify/native-offline` (reusing `node_modules` and the warm 4.3 GB
  `target`), then `build-linux-staging.sh deb` and `... flatpak`.
- **Windows** (`an3-win11-build`, started on demand via `sudo virsh`): a frozen
  source archive + verified dependency cache were copied to
  `C:\AN3\release-2.2.0`, then `build-windows-runtime.ps1` (the runtime was rebuilt
  because `native-runtime/core/core_options.h` changed since it was last staged)
  and `build-windows-staging.ps1`. The bundle needed the repo-root `LICENSE` and
  `static/`, which were sent separately. The VM was shut down from inside Windows
  and `virsh domstate` confirmed `shut off`.

## Runtime evidence actually observed

- **macOS DMG**: mounts; `CFBundleShortVersionString=2.2.0`,
  `CFBundleVersion=2.2.0`; `codesign --verify --deep --strict` OK; app launches
  and stays alive; resources include `LICENSE`, `THIRD_PARTY_NOTICES.md` and the
  pinned cores.
- **Android APK**: installs on AVD `codex-nds-api35`; `versionName=2.2.0`,
  `versionCode=2002000`; `MainActivity` displays in 323 ms; the native library
  `liban3_offline_native.so` loads; the Play/Library/Settings/Help/About library
  UI renders; no `FATAL`/`AndroidRuntime` crash.
- **Linux DEB**: extracts; `Version: 2.2.0`, `Package: vibe-coded-emulator`,
  `Architecture: amd64`; `ldd` reports no missing libraries; launches under
  Xvfb + openbox and stays alive (only an AT-SPI accessibility-bus warning).
- **Linux Flatpak**: installs as `space.an3tocom.offline` 2.2.0
  (commit `de8407dbf958…`); runs under Xvfb and stays alive.
- **Windows EXE**: silent-installs to `C:\AN3\app220`; installed exe reports
  FileVersion/ProductVersion 2.2.0; launches and stays alive with 6 WebView2
  child processes.

## Staging deploy

```
STAGING_SSH_KEY_AUTH=PASS
STAGING_RELEASE=PASS
STAGING_ASSET=f2c429f14adc
STAGING_RELEASE_PATH=/opt/an3-arcade-staging/releases/20260917-111331-f2c429f14adc
STAGING_ROLLBACK_TARGET=/opt/an3-arcade-staging/releases/20260917-035348-f2c429f14adc
STAGING_DEPLOY=PASS
```

Post-deploy smoke (`http://192.168.1.8:8092`): `/health` → `ok`, staging,
release `staging-a946235cf1ac4ce3`; `/download-app/artifacts.json` lists only
2.2.0 installers; each installer URL returns **200 with the exact expected
size**; `/`, `/download-app`, `/multiplayer`, `/controller`, `/diagnostics`
and `/api/diagnostics` return 200 (`/help` is not a route). The download page
shows `2.2.0`.

## Tests

- `python3 -m unittest discover -s tests` → **285 tests, OK**.
- `node tests/web_nds_touch_behavior.test.js`, `node tests/web_renderer_behavior.test.js`
  → ok; `npm --prefix native-offline run check` → ok; `git diff --check` clean.

## Honest gaps

- Interactive gameplay/GUI click-through is **UNVERIFIED** on Windows (Session 0,
  no Vulkan ICD), Linux (WebKitGTK under Xvfb) and macOS (no assistive-access
  UI scripting). Only process/launch/UI-render evidence was collected.
- `catalog.source_fingerprint` was left at the inherited 2.1.0 value: the repo has
  no generator for it (it was recorded directly in an earlier catalog), so no new
  value was invented.
- The custom `tools/release-train.sh --coordinated` path hard-codes `0.4.5`
  artifact filenames and was therefore **not** used; the per-platform builders
  were run directly. That staleness is a separate follow-up.
