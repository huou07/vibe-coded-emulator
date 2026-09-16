# Vibe Coded Emulator — continuation handoff (2026-09-16)

Session ended mid-program by user request ("continue in new session"). This file
records exactly what is done, verified, and next. It is factual; nothing here is
claimed beyond what was run.

## Canonical paths

- Main working tree (dirty, where builds/edits happen):
  `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade`
- Clean checkpoint worktree/branch:
  `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/vibe-coded-emulator`
  (branch `vibe-coded-emulator`, commit `466a592`)
- Feature/status doc: `docs/vibe-coded-platform.md`
- Staging: `http://192.168.1.8:8092` (asset `b595becf54a6`,
  release `/opt/an3-arcade-staging/releases/20260916-031344-b595becf54a6`,
  rollback target `/opt/an3-arcade-staging/releases/20260916-012702-73db1627eb30`)

Staging SSH: export `AN3_STAGING_SSH_IDENTITY_FILE=/Users/meomeo/.ssh/an3_codex_ed25519`
and `AN3_STAGING_SSH_KNOWN_HOSTS=/Users/meomeo/.ssh/known_hosts`, then run
`tools/ssh/check-staging-key.sh` (must print `STAGING_SSH_KEY_AUTH=PASS`).
Deploy with `./deploy-stage.sh`. Production was never touched and must not be
without explicit owner approval.

## Done and verified

### Branding
- Product name **Vibe Coded Emulator** on web (`app.py` `SITE_NAME`, title,
  footer, auth copy, offline page, `server_version`), manifest, native shell.
- Icons generated from the provided app-icon PNG: `static/icon-192.png`,
  `static/icon-512.png`, and all native icons via
  `./node_modules/.bin/tauri icon <png>` (icns/ico/Android/iOS/Windows logos).
- `static/brand-logo.png` (transparent artwork) used in the web header
  (`.brand-logo` in `static/site.css`) and the native sidebar
  (`.native-brand-logo` in `native-offline/web/native.css`).
- Internal identifiers (`AN3_*`, `AN3PlayerRuntime`, `space.an3tocom.offline`,
  save paths) deliberately unchanged.

### Exit Game + autosave
- Web (`static/player.js`, `static/player-runtime.js`, `app.py`): dedicated
  autosave record (`:<slug>:auto`, `getAuto`/`putAuto`), modes
  **off / exit / 30 / 10 / 5** in `localStorage` `vibe-autosave-v1`, SHA-256
  no-op skip, single-transaction writes, timer off the render loop,
  `pagehide` flush, **Exit Game** control (`#exitGame`) and `.player-back`.
- macOS native (`native-offline/src-tauri/src/azahar_host.mm`): mode popup
  (`an3.native-auto-save-mode.v1`, backwards-compatible), `Exit Game` menu item,
  `auto_save_on_exit()`, `save_auto_state` on exit.
- Native version bumped 1.0.1 → **1.1.0** everywhere source-side.

### Native macOS build + runtime (VERIFIED)
- `cargo check` compiles the `.mm`; `npm run build:macos` produced
  `native-offline/releases/vibecodedemulator-1.1.0-macos-aarch64.dmg`
  (hdiutil checksum VALID).
- Harness (built ad hoc from `native-offline/tests/native_smoke.mm` + the two
  `.mm` files), legal fixtures in
  `work/unified-player-20260913/windows-runtime-fixtures-e54608021fa25cba/`:
  - GBA 57–59 fps, NDS 54 fps, 0 dropped, 0 audio underruns.
  - save/load slot 1: `state_save=1 state_load=1`.
  - autosave: `off`→none, `5`→written, `10`→written, `exit`→periodic off.

### New reusable modules (unit-tested, NOT wired to routes/UI)
- `sync_engine.py` — sync modes, LAN-first transport, conflict-safe planning
  (keep local / cloud / both), loop prevention, firmware/keys ineligible.
- `google_sync.py` — OAuth 2.0 PKCE S256, token exchange/refresh/revoke,
  Drive `drive.appdata` client (multipart + resumable), SHA-256 appProperties.
- `netcode.py` — pairing/room codes, token digests, sliding rate limiter,
  latest-state-wins `ControllerSession`, `RoomService` with
  system+core+ROM-hash compatibility.
- Tests: `tests/test_sync_engine.py` (18), `tests/test_google_sync.py` (14),
  `tests/test_netcode.py` (23), `tests/test_phase_a_branding_autosave_exit.py` (8).

### Staging
- `./deploy-stage.sh` → `STAGING_DEPLOY=PASS`; smoke: `/health` OK, home shows
  `Vibe Coded Emulator` + `brand-logo.png`, icons/manifest served, deployed
  `player.js` contains `vibe-autosave-v1`.

## Not done (all codeable; ran out of session budget — not blocked)

1. **Android + Linux native autosave-mode UI parity.** Android:
   `native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameOverlay.kt`
   (checkbox `"Auto Save (state snapshot)"` + `choice("Auto Save interval", …, 60/120/300)`)
   and `native-offline/native-runtime/platform/android/jni_runtime.cpp`
   (`cmd=="autosave"`, `cmd=="autosave-interval"`, stop-time
   `if (autosave) s.host.save_auto(error)`). Linux:
   `native-offline/native-runtime/platform/linux/linux_controls.{h,cpp}` and
   `linux_runtime.cpp` (same enabled+interval model). Replace with the single
   Off/On-exit/30/10/5 mode and a save-on-exit stop path. Update
   `tests/test_android_native_runtime.py` (asserts `'"autosave-interval"'` and
   `'if (autosave) s.host.save_auto(error)'`) and `tests/test_linux_native_runtime.py`.
   Then rebuild the APK (`npm run android:build` / `scripts/build-android-staging.sh`)
   and Linux packages (`scripts/build-linux-staging.sh` on Linux).
2. **Wire `netcode`/`sync_engine` into `app.py`:** controller routes + phone
   page + QR, `/sync/*` settings + mode, `/multiplayer/*` rooms connected to the
   existing EmulatorJS-Netplay relay (`docs/netplay-staging.md`, `AN3_NETPLAY_ORIGIN`,
   `deploy/enable-staging-netplay.sh`). No unauthenticated controller endpoint may
   be exposed to the internet.
3. **LAN discovery + device-to-device transfer** in the native shell (mDNS/UDP
   broadcast + HTTP transfer), reusing `sync_engine` planning.
4. **Google route wiring is intentionally skipped** (user said stop); the client
   module and tests remain.
5. **Switch companion:** GPLv3 accepted; still needs the separate-companion
   architecture (no maintained libretro Switch core). See
   `docs/vibe-coded-platform.md` §11.
6. **Release catalog** still lists 1.0.1 installers; the new 1.1.0 macOS DMG is
   not published. Update `native-offline/releases/catalog.json` + `.sha256` only
   when the corresponding artifacts are actually built/uploaded.

## Environment notes / gotchas

- macOS has **CommandLineTools only (no full Xcode)**; `tauri build`/`cc` still
  work, `xcodebuild` does not. The macOS app is **ad-hoc signed, not notarized**
  (no Apple credentials) — staging/development only.
- The main worktree is intentionally dirty with prior uncommitted work; do not
  destructive-clean it. The clean checkpoint lives in the separate worktree.
- Pre-existing failing test (unrelated): `test_integration.SystemInferenceTests.
  test_current_staging_catalog_names_only_the_current_verified_installers`
  expects the older `1.0.0` catalog. Full suite is otherwise green (195 tests).
- `rg` is not installed on this host; use the Grep tool or `grep`.

## Baseline commands

```bash
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m py_compile app.py
node --check static/player.js
cd native-offline && npm run check && npm run build:macos
```
