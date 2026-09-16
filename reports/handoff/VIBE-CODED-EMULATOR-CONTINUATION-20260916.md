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

## Update — 2026-09-16 (ninth session, part 3): skills/agents + CodeGraph

- Created project-local `.opencode/skills/an3-build`, `an3-staging-deploy`,
  `an3-player-regression`, `an3-codegraph-first` and
  `.opencode/agent/player-verifier`, `release-coordinator`,
  `staging-browser-verify`. Frontmatter validated (name/description for skills;
  description/mode for agents). They encode the version-bump rule, per-platform
  build commands, staging deploy/smoke, the player guard list, the
  CodeGraph-first workflow, and the AVD/Playwright verification flows.
- `codegraph sync` in `apps-web` → "Already up to date" (the daemon kept the
  index current during the session), so the previously-stale symbols are
  indexed.
- Restart opencode to load the new skills/agents.

**Still open:** controller native injection; LAN discovery/transfer; sync wiring
in `app.py`; Windows/Linux 1.3.0 runtime smokes; Switch companion.

## Update — 2026-09-16 (tenth session): cross-device sync wiring

**Step 4 (partial) — sync modes + LAN discovery wired into `app.py`.**
- `SYNC_ENABLED` (staging/development) + `GOOGLE_DRIVE_ENABLED`
  (`AN3_GOOGLE_CLIENT_ID`). Off/LAN selectable; Drive/LAN+Drive advertised
  **unavailable** and rejected with 409 until owner credentials exist.
- Per-device mode (`sync_settings` keyed by the hashed visitor cookie);
  `POST /api/sync/plan` runs the pure `sync_engine` (direction + reason per file,
  transport, conflict counts); `POST /api/sync/resolve` keep local/remote/both;
  in-memory subnet-scoped LAN registry (`announce`/`peers`, 90 s TTL, address
  disclosed only to the same /24); `/sync` page + `static/sync.js`.
- All `/api/sync/*` and `/sync` 404 in production. Guard RG-087; 12 new tests;
  suite **254 tests, 0 failures**.
- **Runtime VERIFIED** on staging (asset `e792e8578089`): settings default off →
  set lan persisted; drive 409; plan returned `download`/`remote-changed`;
  announce returned the peer at `192.168.1.6`; Playwright `/sync` saved `lan`
  and listed the peer with no console errors.
- Report: `reports/handoff/SYNC_WIRING_20260916.md`.

**UNVERIFIED / not done:** byte-level LAN device-to-device transfer; Google Drive
transport (needs owner OAuth); real second LAN device.

**Still open:** controller native injection; LAN byte transfer; Google routes/
UI; Windows 1.3.0 runtime smoke; Switch companion.

## Update — 2026-09-16 (tenth session, part 2): Switch companion design note

**Step 7 (design only, no integration).** Wrote
`docs/vibe-coded-switch-companion.md`:

- Researched 2026-09-16: **Eden** is the maintained Switch core
  (GPL-3.0-or-later; Windows/Linux/macOS/Android), chosen as the first companion;
  Sudachi's canonical repo is a backup and Citron is a further fork (fallbacks);
  still no libretro Switch core.
- Owner already accepted GPLv3. The design isolates the companion as a
  **separate process, never linked**, adds a `CompanionSystem` interface (not
  `NativeSystem`, not libretro), and keeps the GPL boundary on the companion.
- Safety: never bundle keys/firmware/commercial ROMs; `sync_engine` already
  excludes firmware/keys; no compatibility or performance claims.
- Phase 1 = one desktop platform + a legal homebrew NRO launch/Exit/save smoke,
  pending owner sign-off (three open questions at the end of the note).
- Updated `docs/vibe-coded-platform.md` §11 and the roadmap blocker/step 7.

**Still open:** controller native injection; LAN byte transfer; Google routes/UI;
Windows 1.3.0 runtime smoke; Switch Phase 1 (needs sign-off).

## Update — 2026-09-16 (tenth session, part 3): Windows 1.3.0 launch smoke

**Step 5 (Windows) — launch smoke done; gameplay still UNVERIFIED.**
- Started `an3-win11-build` on the Dell on demand, copied the verified
  1.3.0 installer (46,720,549 B), installed silently (`/S`, exit 0), launched
  `C:\AN3\app100\an3-offline-native.exe` (FileVersion **1.3.0**):
  `alive, responding=True`, 32.3 MB RSS, **6 `msedgewebview2.exe`** children →
  the WebView2 UI initialized.
- Stopped the app, then shut the VM down from inside Windows (`shutdown /s`);
  `shut off`, `Autostart: disable`.
- **Not claimed:** any Windows gameplay/rendering/audio/input (Session 0, no
  Vulkan ICD, GDI Generic GL 1.1). Guard RG-088; report
  `reports/handoff/WINDOWS_1.3.0_LAUNCH_SMOKE_20260916.md`.

**Plan status:** steps 1, 2, 3, 6 done+verified; step 4 sync wiring + LAN
discovery done (byte transfer open); step 5 Android verified/Linux+Windows launch
smokes done; step 7 Switch design note written (implementation needs sign-off).

**Still open:** controller native injection; LAN byte transfer; Google routes/UI;
Switch Phase 1; Windows interactive gameplay.

## Update — 2026-09-16 (tenth session, part 4): multipeer input sync verified

- Corrected the multiplayer model: the **staged web** EmulatorJS build has **no
  WebRTC** — netplay is relay-mediated **input lockstep** (each peer runs its
  own core; `sync-control` messages + state snapshots), gated upstream behind
  `EJS_DEBUG_XX && EJS_EXPERIMENTAL_NETPLAY`. Our bridge calls
  `openNetplayMenu()` directly.
- `GameManager.simulateInput` already routes into `netplay.simulateInput` when
  `isNetplay`, so the AN3 virtual pad and phone controller participate.
- **VERIFIED** (Chrome/Playwright, two pages, live relay): guest
  `simulateInput(0,7,1)/(0,7,0)` ×6 appeared on the host as 12 remote
  `gameManager.functions.simulateInput` calls.
- Updated RG-086, the bridge report, and the roadmap. Peer **video** is not a
  thing in this build; the Android asset bundle (with WebRTC) is not what
  staging serves.

**Still open:** controller native injection; LAN byte transfer; Google routes/UI;
Switch Phase 1; Windows interactive gameplay; real two-machine rooms.

## Update — 2026-09-16 (eleventh session): Android native phone-controller host

**Native injection (Android first).** The Android app is now a
phone-controller **host**:
- `ControllerClient.kt` creates a session on the configured staging controller
  server, polls `/api/controller/state`, maps the phone frame to the same
  libretro indices as the web (`tests.test_multiplayer_api.ControllerButtonParityTests`),
  and injects through the same `input`/`directionalInput` path as the on-screen
  pad. The raw host token never leaves the object.
- General-tab "Phone controller · staging" section (server URL, live status,
  Start/Stop); input applies only while the menu is closed and releases on
  stop/destroy.
- `network_security_config.xml` permits cleartext only for the staging host;
  `POST /api/controller/session` accepts a bounded `ttlSeconds` (60–3600) so a
  game session outlives the 2-minute web pairing window.
- Version: **Android 1.3.0 → 1.4.0** (desktop stays 1.3.0). APK
  `vibecodedemulator-1.4.0-android-arm64-staging.apk` (49,587,834 B,
  `3c7518a2…`); catalog PASS; deployed asset `e792e8578089`.
- **Runtime VERIFIED** (AVD): session `0M656E` (3594 s) → `Phone connected`,
  and six `start` presses from the Mac advanced the GBA title to the
  NEW GAME / OPTION menu. Guard RG-089; report
  `reports/handoff/ANDROID_NATIVE_CONTROLLER_20260916.md`.

**Still open:** macOS/Linux/Windows native injection; LAN byte transfer; Google
routes/UI; Switch Phase 1; Windows interactive gameplay.

## Update — 2026-09-16 (twelfth session): desktop native phone-controller host

**Shared Rust host for macOS/Linux/Windows.**
- `src-tauri/src/controller_host.rs`: plain HTTP/1.1 over `TcpStream` (no new
  HTTP dep), session create + poll, `frame_input()` → full `NativeInput`
  snapshot, injection through the existing `set_native_input`; releases on
  stop / 403-404 / window destroy. `serde_json` added.
- Commands `native_controller_start/stop/status`; `window.AN3NativeController`
  bridge; Settings → Phone controller card in `web/index.html` +
  `web/native-app.js`.
- `scripts/package-macos.sh` now derives the DMG name from `tauri.conf.json`
  (same fix as the Android script). Desktop version **1.3.0 → 1.4.0**.
- **Verified:** `cargo test --lib controller_host` 6/6 (incl. a real local TCP
  session lifecycle where the phone's `right` press reaches the input sink);
  Python parity guards for the web/Kotlin/Rust button maps; macOS DMG 1.4.0
  (`638d44ee…`) built, mounted, `CFBundleShortVersionString=1.4.0`, ships
  `nativeControllerCard`, app launches/stays alive; catalog PASS; staging asset
  `e792e8578089` serves the DMG 200. Suite **257 tests, 0 failures**. Guard
  RG-090; report `reports/handoff/DESKTOP_NATIVE_CONTROLLER_20260916.md`.
- **UNVERIFIED:** live desktop pairing with a real phone; Linux/Windows build
  and run (artifacts stay 1.3.0).

**Still open:** live desktop pairing; LAN byte transfer; Google routes/UI;
Switch Phase 1; Windows interactive gameplay.

## Update — 2026-09-16 (thirteenth session): 1.4.0 across all five platforms

**Every packaged app is now 1.4.0 and deployed to staging.**
- Built with the controller: macOS DMG, Android APK, Linux DEB + Flatpak on the
  Dell, Windows EXE on the VM (VM shut down gracefully, autostart disabled).
- Sizes/hashes: DMG 44,810,277 `638d44ee…` · APK 49,587,834 `3c7518a2…` ·
  DEB 45,513,922 `82ffaca9…` · Flatpak 29,103,144 `cc74f5a6…` ·
  EXE 46,784,588 `be5f84f9…`.
- `RELEASE_CATALOG=PASS`; all five URLs served 200 by staging; suite
  **258 tests, 0 failures**; asset `e792e8578089`, release
  `20260916-164416-e792e8578089`.
- **Bug found + fixed (RG-091):** the Windows/Flatpak/Linux/macOS scripts
  hardcoded the version in the artifact name; Windows would have copied a
  leftover 1.3.0 installer. All now derive the name from the version field, and
  the Flatpak manifest/metainfo are pinned by a test.
- Report `reports/handoff/RELEASE_1.4.0_20260916.md`.

**UNVERIFIED:** Linux 1.4.0 runtime, Windows 1.4.0 runtime, phone→running
desktop game.

**Still open:** live desktop pairing observation; LAN byte transfer; Google
routes/UI; Switch Phase 1.

## Update — 2026-09-16 (fourteenth session): Linux 1.4.0 runtime + controller path

- **Linux 1.4.0 runtime smoke VERIFIED** (Dell, Xvfb): extracted DEB ran the full
  25 s (EXIT=124); the installed app binary contains `nativeControllerCard`.
- **Controller client on Linux VERIFIED**: `cargo test --lib controller_host`
  6/6 on the Dell, and the live staging probe passed (session `FY5554`).
- **Runtime INPUT path VERIFIED headlessly**: feeding the shell's exact
  `INPUT 8 …` (GBA `start`) lines to `--control-stdin` advanced the game from
  the Game Freak logo to its menu; before/after in
  `reports/staging/linux-1.4.0-input-*.png`.
- Guard RG-092; report
  `reports/handoff/LINUX_1.4.0_RUNTIME_AND_CONTROLLER_20260916.md`.

**Still UNVERIFIED:** the Tauri app writing INPUT while polling (runtime side and
client side verified separately); Windows 1.4.0 runtime; a real phone driving a
running desktop game.

## Update — 2026-09-16 (fourteenth session, part 2): Windows 1.4.0 launch smoke

- Started `an3-win11-build`, copied the 1.4.0 EXE, installed silently (`/S`,
  exit 0). The installed `C:\AN3\app100\an3-offline-native.exe` reports
  **FileVersion/ProductVersion 1.4.0** and launched (`responding=True`, 45.7 MB
  RSS, 6 `msedgewebview2` children). No app process left; VM shut down
  gracefully (`shut off`, `Autostart: disable`).
- **Not claimed:** Windows 1.4.0 gameplay/rendering (Session 0, no Vulkan ICD).
  1.4.0 is now a launch smoke on Windows, matching what 1.3.0 had.

**Still UNVERIFIED:** the Tauri app autonomously writing controller INPUT while
polling; a phone driving a running desktop game; Windows gameplay.

## Update — 2026-09-16 (fifteenth session): controller chain fully unit-verified

- Added `linux_runtime::tests::input_writes_the_control_stdin_protocol`: a fake
  child receives exactly `INPUT 8 1234 -1234 7 9 1`; passes on the Dell.
- Added `tests.test_native_input_contract` guard pinning the shared
  Linux/Windows `INPUT` line format.
- Attempted the Linux Tauri GUI end-to-end under Xvfb: the app runs but its
  WebKitGTK surface renders nothing without a window manager (none installed);
  no host packages were installed. Documented, not worked around.
- Suite **259 tests, 0 failures**; catalog PASS; git clean.

**Controller chain status:** client ↔ staging (live), client → `set_native_input`
(live probe), Linux `input()` → `INPUT` line (unit test), runtime `INPUT` → core
(headless screenshot). Remaining: the app's own GUI glue and a real phone
driving a running desktop game.

## Update — 2026-09-16 (sixteenth session): desktop GUI e2e + 1.4.1 ACL fix

**Desktop end-to-end VERIFIED on Linux** (Xvfb + openbox, installed with the
owner's approval): the 1.4.1 app created session `FM9MVQ`, the MacBook paired as
the phone (`Phone connected · 3518s`), and eight `start` frames advanced the
running GBA to its NEW GAME / OPTION menu.
Evidence: `reports/staging/linux-desktop-controller-*.png`.

**Bug found and fixed (RG-093):** the Tauri commands were missing from
`build.rs`'s `AppManifest`, so 1.4.0's desktop controller panel failed with
"Command native_controller_status not allowed by ACL". Added to `build.rs` plus a
guard deriving commands from `src/*.rs`.

**1.4.1 published for desktop** (Android stays 1.4.0):
DMG 44,806,337 `80899d0d…` · DEB 45,515,398 `5594b071…` · Flatpak 29,105,496
`d206a015…` · EXE 46,794,903 `88be4c1f…`. All five URLs 200 on staging (asset
`e792e8578089`, release `20260916-175421-e792e8578089`); suite **259 tests, 0
failures**. macOS 1.4.1 mounts/launches; Windows 1.4.1 installs/launches (VM
shut down). Report
`reports/handoff/DESKTOP_CONTROLLER_ACL_FIX_1.4.1_20260916.md`.

**Still UNVERIFIED:** macOS/Windows GUI pairing; a phone driving a running
macOS/Windows game; LAN byte transfer; Google routes (needs credentials);
Switch Phase 1 (needs sign-off).

## Update — 2026-09-16 (seventeenth session): LAN save/state transfer

- New `/api/sync/lan/publish|manifest|blob` (staging-gated): eligible kinds only,
  SHA-256-verified items, 16 MiB/item + 512-item caps, in-memory with a 900 s TTL.
- **Two-device VERIFIED**: MacBook published a 1041-byte state blob → the Debian
  pulled it byte-exact (`d610c3a8…`); the Debian published a 780-byte save blob →
  the Mac pulled it byte-exact (`ea48442b…`).
- Suite **264 tests, 0 failures**; staging asset `e792e8578089`, release
  `20260916-180157-e792e8578089`. Guard RG-095; report
  `reports/handoff/LAN_TRANSFER_20260916.md`.
- This is LAN-mediated through the staging server (the LAN rendezvous); true
  peer-to-peer device listeners and client-store wiring remain.
