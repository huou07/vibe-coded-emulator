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

## Done after this handoff (updated 2026-09-16)

- **Android + Linux native autosave-mode UI parity: DONE.** A shared model
  (`native-offline/native-runtime/core/auto_save_mode.h` + `shared/player-ui.json#autoSave`
  → `NativePlayerUi.kt` / `player_ui.h`) replaced the old checkbox+interval UI on
  both platforms; `autosave-mode` is the single command. Android 1.1.0 APK rebuilt.
- **macOS autosave now uses the same shared model: DONE** (commit `c399679`).
  `azahar_host.mm` includes `auto_save_mode.h`, builds the menu from
  `player_ui::auto_save_titles/tokens`, parses with `an3::parse_auto_save_mode`,
  and keeps the legacy boolean+interval keys as a migration fallback. macOS
  parity test added to `tests/test_shared_player_ui.py`; `cargo check` + rebuilt
  DMG + runtime smoke (off=none, 5s/10s=written, exit=periodic off) pass.

## Not done (all codeable — not blocked)

1. ~~Android + Linux native autosave-mode UI parity~~ (done, see above).
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
  expects the older `1.0.0` catalog. Full suite is otherwise green (199 tests).
- `rg` is not installed on this host; use the Grep tool or `grep`.

## Baseline commands

```bash
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m py_compile app.py
node --check static/player.js
cd native-offline && npm run check && npm run build:macos
```

## Update — 2026-09-16 (second session)

Read the other "Emulator handoff continuation" session from the opencode store
(`~/.local/share/opencode/opencode.db`, session
`ses_f57e99608ffeU9U60rUrZueDFW`). It had built and runtime-tested 1.1.0 on
Android (AVD) and Linux (Dell Debian) but never published or deployed them.

**Merged + published + staged (DONE):**
- Collected `vibecodedemulator-1.1.0-linux-amd64.deb` from the Dell builder
  (`/home/huou07/an3-verify/...`), sha256 `38a22ce2…4c5d`.
- Rebuilt the macOS 1.1.0 DMG with the shared Auto Save model
  (sha256 `9f137603…b75e`); Android APK `0376b237…dcc2`.
- `catalog.json` now publishes macOS/Android/DEB at **1.1.0** (sizes + SHA-256 +
  sidecars); Flatpak/Windows remain **1.0.1** until rebuilt.
  `tools/verify-release-catalog.py` → `RELEASE_CATALOG=PASS (5 installers)`.
- Updated the staging catalog guard test; full suite **209 tests, 0 failures**
  (the previously failing catalog test is fixed).
- Deployed staging: asset `31d2782287fa`, release
  `/opt/an3-arcade-staging/releases/20260916-111105-31d2782287fa`,
  rollback `/opt/an3-arcade-staging/releases/20260916-110252-31d2782287fa`.
  `artifacts.json` and the three installer URLs return 200 with expected sizes.

**Multiplayer rooms wired (staging-only) (DONE):**
- `app.py` exposes `netcode.RoomService`: `POST /api/multiplayer/room|join|leave`
  and `GET /api/multiplayer/room`, gated by `MULTIPLAYER_ENABLED`
  (staging/development + `AN3_NETPLAY_ORIGIN`); production → 404. Verified live on
  staging (create 201, join 200, status 200, incompatible 409 in tests).
- Regression found and fixed: `netcode.py`/`sync_engine.py` were missing from the
  app payloads, so the first redeploy failed health and rolled back. Added them to
  `package-staging.sh`, `package-production.sh`, `update-production.sh`, plus
  `tests/test_packaging_imports.py` which guards every local import transitively.

**Still not done:**
- Flatpak 1.1.0 (needs Flathub runtime on the Dell) and Windows 1.1.0 (Windows VM).
- A multiplayer room **UI page** (API is live; the existing EmulatorJS host/join
  flow is what consumes it today).
- Remote-controller phone UI/QR/transport, LAN discovery/transfer, sync wiring
  in `app.py`, Switch companion — unchanged, all still codeable.

## Update — 2026-09-16 (third session)

**Multiplayer room page (DONE):** `/multiplayer` renders Create/Join controls
(`static/multiplayer.js`); `PRIMARY_CORES` mirrors `static/player.js` (parity
test) and `game_rom_hash()` derives a cached stable SHA-256 so a `?slug=` prefill
gives two players the same room signature. Staging asset `cd10db2b92fb`.

**Remote phone controller (DONE, staging-only):** `app.py` wraps
`netcode.ControllerSession` as `/api/controller/session|pair|state|disconnect`
plus token-authenticated `GET /api/controller/state`, with 2-minute TTL, reaping
and rate limiting; production 404s. Pages `/controller` (host: code + join link +
live status) and `/controller/join` (phone touch pad) with
`static/controller.js`. Verified live on staging (create → pair → submit →
host read). Staging asset `6b602866d487`.

**Latest verification:** full suite **219 tests, 0 failures**; deploys PASS with
rollback retained. Commits `69f325c`, `4c0ecbf`, `b8191e9`, `b95db9e`, `c53f12c`,
`0540e78`.

**Still not done:** Flatpak/Windows 1.1.0; a QR renderer for the controller and
binding host state into the live EmulatorJS input path; LAN device discovery +
direct transfer; sync wiring in `app.py`; Switch companion.

## Update — 2026-09-16 (fourth session)

**Requested feature changes, done on all three native shells:**

1. **Layout chooser instead of a two-option cycle.** `native-layout-schema.json`
   is v2 now: each entry carries `id`, `label`, `coreOption` and the exact
   `coreValue`. melonDS exposes 12 layouts, Azahar 4. `generate-player-ui.mjs`
   emits `shared/generated/native_layouts.h`, which macOS and Linux include;
   Android reads the JSON asset. The toolbar Layout button opens a chooser on
   macOS (NSMenu), Linux (GTK menu) and Android (AlertDialog); F1 on Linux
   cycles the same list.
2. **Toolbar Save button.** Beside the speed row on macOS/Linux/Android: Quick
   Save, Quick Load, Auto Save now, Load Auto Save — the Save States tab's quick
   actions without opening the menu. (The web player already had a slot button.)

**Version:** native 1.1.0 -> **1.2.0** (feature; the published app bytes
changed). macOS DMG rebuilt and published; Android/Linux catalog entries stay at
1.1.0 until those binaries are rebuilt.

**Verified:** 220 tests pass; generator `--check` OK; `cargo check` + macOS
build + DMG; runtime smoke of five NDS layouts at ~50 fps. Staging asset
`dea10670c1a7` (macOS 1.2.0 DMG served 200, served `player-ui.js` carries the
new toolbar model). Commit `bcde87e`.

**Not verified:** Android/Linux builds for 1.2.0 (Kotlin/C++ updated but not
rebuilt here). Unchanged-from-before: Flatpak/Windows 1.2.0, LAN discovery,
sync wiring, Switch companion.

## Update — 2026-09-16 (fifth session)

**Workspace:** `~/Documents/edit an3tocom apps&web` is now a usable git worktree
of the project (branch `apps-web`, baseline `528e2b7`); it runs the full test
suite. Checkpoint worktree remains `.../vibe-coded-emulator`.

**Cross-platform 1.2.0 built and published** (macOS, Android, Linux DEB,
Flatpak; Windows pending):

| Platform | Artifact | Size | sha256 (short) |
| --- | --- | --- | --- |
| macOS | vibecodedemulator-1.2.0-macos-aarch64.dmg | 44,704,838 | c22de7b7… |
| Android | vibecodedemulator-1.2.0-android-arm64-staging.apk | 49,571,059 | 2c877328… |
| Linux DEB | vibecodedemulator-1.2.0-linux-amd64.deb | 45,483,678 | ac89b460… |
| Linux Flatpak | an3-offline-1.2.0-linux-amd64-staging.flatpak | 29,080,072 | 0aa9f5db… |
| Windows | (still 1.0.1, VM build pending) | — | — |

`RELEASE_CATALOG=PASS (5 installers)`; suite 220 tests, 0 failures; staging
deployed (asset `dea10670c1a7`) and all four 1.2.0 installer URLs return 200.

**Bug found and fixed:** `build-linux-staging.sh` used
`find .../bundle/deb -name '*.deb' -print -quit`, which picked a lingering
1.1.0 DEB and renamed it to 1.2.0 (control version 1.1.0, byte-identical). The
script now clears `bundle/deb` before building. The Dell also needed rustup
(system rustc was 1.85; installed user-level stable 1.98). Flathub is available
on the Dell, so Flatpak 1.2.0 was built from the fresh DEB.

**Android 1.2.0 verification (partial):** APK installs on the `codex-nds-api35`
AVD, launches with no FATAL, and `classes2.dex` contains `Quick Save`,
`Quick Load`, `showLayoutChooser`, `showSaveMenu`. Full gameplay interaction
(import ROM → native game → open the chooser) was **not** exercised.

**Still not done:** Windows 1.2.0 (start `an3-win11-build`), Linux 1.2.0 runtime
run on the Dell, LAN discovery/transfer, sync wiring, controller QR + input
binding, Switch companion.

## Update — 2026-09-16 (sixth session): 1.2.0 runtime verification

**Android 1.2.0 — VERIFIED on the `codex-nds-api35` AVD (arm64 API 35):**
- Pushed a legal GBA ROM and launched `NativeGameActivity`; NDS native core ran at
  **`FPS core=59 present=59`**.
- Toolbar shows **Layout** and **Save** (Layout only for nds/3ds, as designed).
- Save → menu with **Quick Save / Quick Load / Auto Save now / Load Auto Save**;
  Quick Save wrote
  `files/native-states-v1/nds/<romId>/.../…slot1.state` on disk.
- Layout → chooser listing all **12 melonDS layouts** (Left/Right, Right/Left,
  Top/Bottom, Bottom/Top, Hybrid focus top/bottom, Flipped hybrid top/bottom,
  Large screen top/bottom, Flipped large screen top/bottom). Selecting
  "Hybrid (focus top)" persisted `screen-layout-nds=hybrid-top` and
  `nds-layout=hybrid-top`; no crash, FPS unchanged.

**Linux 1.2.0 — PARTIAL:** the runtime runs under Xvfb for the full timeout with
`SDL_AUDIODRIVER=dummy AN3_OFFLINE_LIBDIR=<dir> LIBGL_ALWAYS_SOFTWARE=1`. The
binary contains the new UI (`show_layout_menu` with the 12/4-layout arrays,
"Quick Save", "Auto Save now", "Screen layout changed to"). GTK menu clicks were
not automated headlessly.

**Windows — VM started, probed, and shut down; build not done.** `an3-win11-build`
has rustc 1.98.1, node 24, VulkanSDK, MSYS2. The build gate blocks because
`vendor/runtime/windows-x64/manifest.json` hashes
`native-runtime/platform/linux/linux_controls.cpp` / `linux_runtime.cpp` — the
files changed for 1.2.0 — so **`scripts/build-windows-runtime.ps1` must be rerun
on the VM before the NSIS build**. The VM was gracefully shut down afterwards
(`virsh shutdown`, `shut off` in ~20 s, Autostart: disable).

**Next for Windows:** sync source to `C:\AN3`, run `build-windows-runtime.ps1`
(MSYS2 + cmake + SDL), then `build-windows-staging.ps1`, then publish 1.2.0 EXE
and shut the VM down again.

## Update — 2026-09-16 (seventh session): Windows 1.2.0 built and published

**All five platforms are now 1.2.0 and deployed to staging.**

Windows path:
- Started `an3-win11-build`, synced source to `C:\AN3\unified-20260914` (node 24,
  rustc 1.98.1, MSYS2 UCRT64, VulkanSDK present).
- The Windows runtime **reuses the GTK/SDL sources** (`platform/linux/*`), so the
  1.2.0 layout changes invalidated its manifest -> reran
  `build-windows-runtime.ps1` (regenerated `NativePlayerUi.kt` on the VM first so
  the generator `--check` passed; `WINDOWS_NATIVE_RUNTIME=VERIFIED 47 PE files`).
- Fixed two script fragilities: `$ErrorActionPreference='Stop'` made PowerShell
  treat native stderr (node/tauri/compiler progress) as terminating. Both
  Windows scripts now use 'Continue' around native calls and rely on
  `$LASTEXITCODE`.
- `build-windows-staging.ps1` -> `vibecodedemulator-1.2.0-windows-x64-staging.exe`
  (46,716,478 B, sha256 `233f4eb2…006e`), release gate PASS.
- Catalog updated (EXE 1.0.1 -> 1.2.0), `RELEASE_CATALOG=PASS`, 220 tests pass,
  staging deployed (asset `dea10670c1a7`); the EXE URL returns 200.
- VM shut down gracefully (`shutdown /s` from inside Windows; ACPI `virsh
  shutdown` alone did not complete). Verified `shut off`; Autostart: disable.

**1.2.0 catalog:** DMG / APK / DEB / Flatpak / EXE all 1.2.0.

**Still open (features, not release):** controller QR + emulator input binding,
rooms wired to the relay, LAN discovery/transfer, sync wiring, Switch companion.
Windows 1.2.0 was **not** runtime-tested (built only).

## Update — 2026-09-16 (eighth session): 1.3.0 player fixes + worktree independence

**Feature/fix changes (all three native shells):**
- Toolbar **Save now exposes all ten quick slots** (macOS NSMenu submenus,
  Android action->slot dialog, Linux GTK submenus). Previously slot 1 only.
- **FPS badge is pointer-inert**: macOS `AN3InertLabel.hitTest` returns nil;
  Android clears clickable/focusable/longClickable and ignores touches. It no
  longer blocks clicks.
- **Menu-first pointer precedence**: an open menu owns input. macOS mouse
  handlers bail while `_menu_panel` is visible and opening the menu releases any
  held NDS/3DS touch; Android ignores NDS/3DS touches while `isMenuOpen()`;
  Linux skips the SDL touch mapping while the GTK panel is visible.
- `tools/ssh/staging-env.sh` (path-only) lets any worktree run
  `check-staging-key.sh` / `deploy-stage.sh` without the original checkout.

**Version 1.2.0 -> 1.3.0**, all five platforms rebuilt and published:
DMG 44,706,349 · APK 49,571,879 · DEB 45,484,618 · Flatpak 29,090,480 ·
EXE 46,720,549. `RELEASE_CATALOG=PASS`; suite **225 tests, 0 failures**.
Deployed **from the `apps-web` worktree** (asset `dea10670c1a7`); all five 1.3.0
installer URLs return 200.

Android 1.3.0 was installed/launched earlier in the 1.2.0 cycle; the 1.3.0 APK
was built but not re-installed. Windows 1.3.0 built (not runtime-tested); VM
shut down, autostart disabled.

**Worktrees:** `.../vibe-coded-emulator` (branch `vibe-coded-emulator`) and
`~/Documents/edit an3tocom apps&web` (branch `apps-web`) both hold the current
source and can deploy. Android generated Kotlin under `native-offline/src-tauri/gen`
remains untracked (pre-existing).

## Update — 2026-09-16 (ninth session): 1.3.0 runtime verify + web controller real

Workspace: `/Users/meomeo/Documents/edit an3tocom apps&web` (branch `apps-web`).

**Step 1 — 1.3.0 runtime (Android VERIFIED, Linux PARTIAL).**
- Android 1.3.0 APK installed on the `codex-nds-api35` AVD; NDS at
  `FPS core=59 present=59`; Save menu → Quick Save/Load with **Slot 1…10**
  (Slot 1 wrote a 19,498,039-byte `.slot1.state`); Layout chooser lists all 12
  melonDS layouts; nine-tab Menu opens/closes; NDS touch reaches the core; FPS
  badge node is `clickable=false focusable=false long-clickable=false` at runtime.
- Linux 1.3.0 DEB ran under Xvfb for the full `timeout 25s` (EXIT=124) with the
  1.3.0 UI strings present.
- Full evidence: `reports/handoff/ANDROID_LINUX_1.3.0_RUNTIME_20260916.md`;
  screenshots in `reports/android-regression/1.3.0/`.

**Step 2 — phone controller made real (web player).**
- Vendored `qrcodegen.py` (MIT, pinned sha256); server-side SVG QR at
  `GET /api/controller/qr.svg?code=`; player page hosts the session, shows the QR,
  polls `/api/controller/state`, and applies phone frames via the virtual-input
  path only while gameplay runs and no menu is open.
- Fixed a keep-alive bug: `controller_create_session` ignored its body, corrupting
  the next request (`501 Unsupported method ('{"deviceId":"host"}GET')`).
- **Runtime acceptance VERIFIED** (Chrome/Playwright, staging): host session
  `EG9JFT`; phone paired, pressed Right; host observed
  `simulateInput(0,7,1)` → `(0,7,0)`; `/controller` QR PNG decoded to the join URL.
- Suite **237 tests, 0 failures**; deployed asset `51d627516e1a`, release
  `/opt/an3-arcade-staging/releases/20260916-141246-51d627516e1a`.
- New guards RG-082/083/084. Report:
  `reports/handoff/WEB_CONTROLLER_BINDING_20260916.md`.

**Still open:** native controller input injection; rooms → relay bridge with
invite codes; LAN discovery/transfer; sync wiring in `app.py`; Switch companion;
CodeGraph re-index; skills/agents.

## Update — 2026-09-16 (ninth session, part 2): multiplayer relay bridge

**Step 3 — AN3 rooms bridged to the EmulatorJS relay (staging).**
- Fixed RG-085: the player CSP listed only the relay's HTTP origin, so the
  Socket.IO **WebSocket** was blocked and netplay could never connect. The CSP
  now derives `ws://`/`wss://` from `NETPLAY_ORIGIN`
  (`player_content_security_policy`).
- The AN3 invite code is now the relay room name: player `Multiplayer` panel +
  `#mpPlayerPanel`; host → `netplay.openRoom(code, 2, "")`; join → AN3 compat
  check then `getOpenRooms()` + `netplay.joinRoom(key, code)`. Server-computed
  `roomSignature`; `/api/multiplayer/qr.svg` deep-link QR.
- Staging relay restarted (`compose.rust-netplay.staging.yml up -d
  --force-recreate`) because its published port was inactive.
- **Runtime VERIFIED** (Chrome/Playwright, two pages, live relay): host room
  `B4VZ0W` at relay `current:1`, guest joined at `current:2`, both
  `isNetplay=true` with connected sockets. WebRTC peer media sync UNVERIFIED.
- Suite **242 tests, 0 failures**; asset `0e2a7d7a1a3b`, release
  `/opt/an3-arcade-staging/releases/20260916-144055-0e2a7d7a1a3b`.
- New guards RG-085/086. Report:
  `reports/handoff/MULTIPLAYER_RELAY_BRIDGE_20260916.md`.

**Still open:** controller native injection; LAN discovery/transfer; sync wiring
in `app.py`; Switch companion; CodeGraph re-index; skills/agents.
