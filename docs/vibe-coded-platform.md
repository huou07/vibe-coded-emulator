# Vibe Coded Emulator — platform architecture and feature status

This document describes the systems added or changed for the Vibe Coded
Emulator expansion, and states plainly what is implemented versus what is
designed but not yet wired in. It replaces nothing in the existing AN3
operations/staging docs; those still govern deployment.

Dates and version numbers below reflect the current source tree.

## 1. System architecture

| Surface | Technology | Location |
| --- | --- | --- |
| Web + API | Flask, server-rendered, `BaseHTTPRequestHandler` router | `app.py` |
| Web player | EmulatorJS (libretro cores via proxy) + custom WASM renderer worker | `static/player.js`, `static/player-runtime.js`, `static/renderer-worker.js` |
| Native desktop | Tauri 2 + Rust shell + Objective-C++/SDL adapters | `native-offline/` |
| Native cores | libretro host (mGBA, melonDS DS, Azahar) | `native-offline/native-runtime/` |
| Netplay relay | EmulatorJS-Netplay Rust relay (staging-only) | `rust-gateway/`, `Dockerfile.rust-netplay` |
| Sync core (new) | Transport-agnostic sync planning | `sync_engine.py` |
| Google sync | **Removed** — not a product feature. See `docs/archive/checkpoint-google-sync-removal.md` | — |
| Shared networking (new) | Pairing, sessions, controller, rooms | `netcode.py` |

## 2. Emulator core abstraction

- Native cores implement one libretro host (`NativeCoreHost` /
  `libretro_host.{h,cpp}`) with systems `GBA`, `NDS`, `ThreeDS`
  (`NativeSystem` enum). Save states, core options and screen layout all flow
  through this one contract.
- The web player uses EmulatorJS cores (mGBA for GBA, melonDS for NDS, Azahar
  for 3DS) selected per game by server-provided config.
- Adding a system means adding a core that satisfies one of these two
  contracts. There is no third path.

## 3. Renderer selection (unchanged by this work)

Per-platform paths are preserved and are **not** collapsed into one backend:

| Platform | Path |
| --- | --- |
| macOS / Apple Silicon | Azahar native Vulkan → bundled MoltenVK → Metal; GBA/NDS software frames uploaded through Vulkan |
| Android | Vulkan preferred, core/GPU fallback preserved |
| Linux | SDL/Vulkan presenter, OpenGL only for software cores |
| Windows | SDL/Vulkan loader with existing fallback |
| Web | `renderer-worker.js`: WebGPU when available, WebGL2 fallback, bounded latest-frame ring |

Per-core rendering differences are intentionally retained (for example melonDS
compatibility renderer vs native, Azahar side-by-side layout).

## 4. Branding

- Product name is **Vibe Coded Emulator** on web, native menus and packaging.
- `static/icon-192.png`, `static/icon-512.png`, `native-offline/src-tauri/icons/**`
  and the Android/iOS icon sets are generated from the provided app-icon PNG.
- `static/brand-logo.png` (transparent brand artwork) is used in the web header
  and the native sidebar; it is not repeated across other screens.
- Internal identifiers (`AN3_*` env vars, `AN3PlayerRuntime`, the
  `space.an3tocom.offline` application id, on-disk save paths) are deliberately
  **unchanged** to avoid a user-data migration.

## 5. Save states and autosave

### Web (`static/player.js`, `static/player-runtime.js`)

- Manual slots 1–10 are unchanged.
- A dedicated autosave record (`<slug>:auto`) is stored in the same IndexedDB
  store via `QuickSaveManager.getAuto/putAuto`. It can never overwrite a manual
  slot.
- Autosave modes: **Off, On game exit, Every 30s, Every 10s, Every 5s**
  (stored per device in `localStorage` key `vibe-autosave-v1`).
- Unchanged state is skipped using a SHA-256 digest of the state bytes, so a
  periodic timer does not write to IndexedDB when nothing changed.
- Writes are a single IndexedDB transaction (atomic per record); periodic
  autosave runs on a timer, never on the render loop.
- **Exit Game** (in the player options, and the back control) performs a bounded
  best-effort final autosave when an autosave mode is on, then returns to the
  library. A `pagehide` flush covers tab close/navigation.

### Native macOS (`native-offline/src-tauri/src/azahar_host.mm`)

- Autosave is a single mode popup: **Off, On game exit, Every 30s, Every 10s,
  Every 5s** (`an3.native-auto-save-mode.v1`), with backwards-compatible reading
  of the previous `an3.native-auto-save.v1` boolean + interval keys.
- It now uses the **same shared model** as Android/Linux: titles/tokens come from
  `shared/player-ui.json` (`an3::player_ui::auto_save_titles/tokens`) and the
  token is parsed by `native-runtime/core/auto_save_mode.h`
  (`an3::parse_auto_save_mode`). The macOS shell no longer keeps a private copy
  of the titles/tokens.
- An explicit **Exit Game** control writes a final autosave when enabled, then
  stops the session and returns to the library.
- Autosave still writes to `<rom_id>.autosave.state` through the existing atomic
  writer, separate from quick slots 1–10.

### Native Android and Linux

- Both now expose the same single mode as macOS: **Off, On game exit, Every 30s,
  Every 10s, Every 5s**. The titles/tokens come from the shared
  `native-offline/shared/player-ui.json` model and are generated into
  `NativePlayerUi.kt` and `player_ui.h`; all three native shells (macOS, Android,
  Linux) parse the persisted token through `native-runtime/core/auto_save_mode.h`,
  so the platforms cannot drift.
- The Android menu persists the mode in `autosave-mode` (migrating the previous
  `autosave` boolean + `autosave-interval` keys through `NativeAutoSave`) and
  sends one `autosave-mode` command; the Linux GTK panel sends the same token.
- `native-runtime/core/auto_save_mode.h` parses the token identically for both:
  `off`, `exit`, and any positive numeric interval (so a legacy 60/120/300 value
  keeps working). Periodic modes save on their own timer; the `exit` mode writes
  one final atomic snapshot on the stop path.
- Verified on hardware/VM:
  - **Android (arm64 API 35 AVD, debug build installed):** native mGBA ran at
    59 fps; the Save States menu shows one Auto Save spinner with **Off / On
    game exit / Every 30s / Every 10s / Every 5s**, no checkbox or interval
    control; `autosave-mode` persisted in prefs; "Every 5 seconds" wrote
    `<rom>.autosave.state` on a timer; "On game exit" wrote nothing on the timer
    and wrote the autosave as the game activity stopped.
  - **Linux (Debian builder, native runtime under Xvfb with a legal GBA ROM):**
    the GTK Save States tab shows the same single Auto Save combo with all five
    modes; "Every 5 seconds" wrote the autosave, and "On game exit" wrote it when
    returning to the library.
  - Shared-header parse unit test, Android `jni_runtime.cpp` compile + link and
    Kotlin compile, and a rebuilt
    `releases/vibecodedemulator-1.1.0-android-arm64-staging.apk`.

## 6. Google sign-in and Drive sync (removed)

Google cloud sync is not a product feature. The OAuth/Drive client module and
its tests were deleted on 2026-10-13; `app.py` now hard-codes
`GOOGLE_DRIVE_ENABLED = False`, so `POST /api/sync/settings` and `/plan` always
answer 409 `drive-unavailable` and the UI never advertises the option.

Local saves, LAN save/state transfer and the pure `sync_engine` decision core
are unaffected. See `docs/archive/checkpoint-google-sync-removal.md`.

## 7. Sync engine and conflict resolution

`sync_engine.py` is pure and unit-tested. It owns:

- Sync modes: **Off, Local network, Google Drive, Local + Google Drive**.
- LAN-first transport selection: prefer a same-LAN peer, fall back to Drive.
- Per-file decisions: upload, download, delete propagation, no-op, or conflict.
- Conflict rule: if local and remote both changed since the last successful
  sync, it is a conflict — never a silent overwrite. Resolutions are
  **keep local / keep cloud / keep both**.
- Loop prevention: after a transfer the new hash is recorded as
  `last_synced_hash`, so a file moved over LAN is not re-flagged as a Drive
  conflict.

**Not done:** the local index table, the transfer/RPC endpoints, the LAN
discovery/transfer transport, and the Sync settings page.

## 8. Local-network sync

Designed on top of `sync_engine` with `choose_transport`. Same-LAN devices use a
direct transfer; the cloud is used only when LAN is unavailable or disabled.
**Not implemented:** mDNS/UDP discovery and the device-to-device transfer
endpoint.

## 9. Remote controller

`netcode.py` implements the host side of a low-latency controller session:

- Pairing with a short, ambiguity-free code (`generate_pairing_code`) and a
  bearer token stored only as a SHA-256 digest.
- `ControllerState` frames with bit-packed buttons, omitted zero axes and a
  monotonic sequence number.
- **Latest-state-wins**: duplicate and out-of-order frames are dropped, not
  buffered, so packet loss does not add latency; `needs_resync` tells the host
  to request a full state after a reconnect.
- Rate limiting for pairing attempts.

**Wired (staging-only):** `app.py` exposes the session as a small JSON API —
`POST /api/controller/session` (host creates, returns a pairing code + host
token), `POST /api/controller/pair` (phone pairs with the code), `POST
/api/controller/state` (phone submits a frame), `POST /api/controller/disconnect`
and token-authenticated `GET /api/controller/state` (host reads the latest
state). Sessions have a 2-minute TTL, are reaped on every mutating request, and
are gated by `CONTROLLER_ENABLED` (staging/development); production returns 404.
Pages: `/controller` (host — pairing code, join link, live status) and
`/controller/join` (phone touch pad → `static/controller.js`), verified live on
staging (create → pair → submit → host read). Transport is the same-origin HTTP
JSON API for both directions; a QR renderer and binding the host state into the
live EmulatorJS input path are the remaining pieces. No unauthenticated
controller endpoint is exposed.

## 10. Multiplayer / rooms

`netcode.py` `RoomService` provides room creation, invite codes (short TTL),
join validation, host identity, role-authenticated tokens, reconnect, expiry,
reaping and disconnect handling. Compatibility is verified from
`GameSignature` (**system + core + ROM content hash**) before any session is
established, and the ROM is never transferred to satisfy the check. Only an
opaque signaling hint is stored, never a raw host IP.

The existing EmulatorJS-Netplay Rust relay remains the staging transport. Core-
specific netplay behaviour is **not** uniform: any per-system netplay must be
evaluated per core (GBA, NDS, 3DS differ) and is **not implemented** here.

**Wired (staging-only):** `app.py` now exposes the room service as a small JSON
API — `POST /api/multiplayer/room` (create), `POST /api/multiplayer/join`,
`POST /api/multiplayer/leave`, `GET /api/multiplayer/room?code=&token=`
(status). It is gated by `MULTIPLAYER_ENABLED` (staging/development **and** a
configured `AN3_NETPLAY_ORIGIN`), so production returns 404 for every room
endpoint. Responses carry the relay origin (never a raw host IP) and the
validated system/core/ROM-hash signature; join is rate-limited and rejects a
mismatched game with HTTP 409. Covered by `tests/test_multiplayer_api.py`
(create/join/status, incompatible 409, unknown room 404, token check, disabled
404, host-leave-ends-room, guest-leave-rejoin). A dedicated room UI page is not
built yet; the API is consumed by the existing EmulatorJS host/join flow.

## 11. Nintendo Switch (research only — no integration)

Findings from current research (August 2026):

- **Eden** (`eden-emu`, GPLv3) is the actively maintained Yuzu fork with Windows,
  Linux, macOS, Android and FreeBSD builds. Citron and Sudachi are further
  forks; Ryujinx is discontinued (Ryubing continues it); Yuzu/Suyu are dead.
- **Licensing (resolved 2026-09-16):** the project is now licensed
  **GPL-3.0-or-later** (`LICENSE`); the earlier `LicenseRef-proprietary`
  statement no longer applies. Linking a GPLv3 Switch core into that app is
  compatible, and the combined work must carry the GPL obligations
  (`docs/licensing/distribution-compliance.md`). See
  `docs/licensing/eden-integration-feasibility.md` for the Eden verdict: the
  blocker is technical, not licensing.
- **Architecture blocker:** there is no maintained **libretro** Switch core, and
  the Yuzu-family emulators are standalone applications with their own
  frontend. The existing `NativeCoreHost` libretro abstraction cannot host them;
  integration would need a separate launched companion/frontend (similar to the
  Android Azahar companion) or a new core abstraction.
- **Always:** no firmware, `prod.keys`, `title.keys`, or commercial ROMs may be
  bundled. Users must supply their own.

Recommendation: keep Switch behind a documented, isolated core abstraction and
resolve licensing before writing integration code. Do not add a Switch core to
`NativeSystem` until then.

**Update 2026-09-16:** the owner accepted GPLv3 for the companion. The
architecture and safety design is now in
`docs/vibe-coded-switch-companion.md` (Eden as the first companion core, launched
as a separate process — never linked; no keys/firmware/commercial ROMs; no
`NativeSystem` change until sign-off). Phase 1 is a single desktop platform with
a legal homebrew NRO and a launch/Exit/save smoke.

## 12. Platform limitations

- The custom web player relies on browser codecs/canvas; server-side rendering
  is not used.
- HTTP-LAN sessions cannot install a Service Worker or persistent Cache Storage,
  so fully offline PWA behaviour needs HTTPS.
- Native 3DS on Android delegates to a separately installed companion; ZIP/CIA
  archives are deliberately rejected until an in-app installer exists.
- Google sync and LAN sync cannot be verified without credentials and two
  devices on one network.

## 13. Testing matrix (what was actually run)

Run on macOS (developer host), 2026-09-16:

| Area | Command | Result |
| --- | --- | --- |
| Full suite | `python3 -m unittest discover -s tests` | 195 tests, 1 pre-existing failure (`test_current_staging_catalog_names_only_the_current_verified_installers`, expects the previous `1.0.0` catalog) |
| Sync engine | `python3 -m unittest tests.test_sync_engine` | 18 pass |
| Netcode | `python3 -m unittest tests.test_netcode` | 23 pass |
| Phase A contracts | `python3 -m unittest tests.test_phase_a_branding_autosave_exit` | 8 pass |
| Web player render | `tests.test_integration` | rendered `/play/<slug>` includes autosave + Exit Game controls |
| JS/Python syntax | `node --check` on player scripts, `python3 -m py_compile app.py` | pass |

Not run / not verified: native builds (`npm run build:macos`, Android APK,
Windows installer), the modified `azahar_host.mm` was **not compiled**, live
Google sign-in, two-device LAN sync, remote controller on a real phone, netplay
rooms between two machines, and any Switch core. GBA/NDS/3DS runtime behaviour
is unchanged by these edits but was not re-measured here.

## 14. Screen layout chooser and toolbar Save (2026-09-16)

**Layout chooser.** The gameplay toolbar's Layout button no longer cycles
between two layouts; it opens a chooser of every layout the active core
supports.

- `native-offline/shared/native-layout-schema.json` (v2) is the single source:
  each entry has `id` (the persisted preference), `label`, `coreOption` and the
  exact `coreValue` the libretro core accepts.
  - melonDS DS: 12 layouts — left/right, right/left, top/bottom, bottom/top,
    hybrid and flipped-hybrid (focus top/bottom), large screen and flipped
    large screen (top/bottom).
  - Azahar: 4 layouts — side by side, top/bottom (`default`), single screen,
    large screen.
- `generate-player-ui.mjs` now also emits `shared/generated/native_layouts.h`
  from that schema. macOS (`azahar_host.mm`) and Linux (`linux_controls.cpp`,
  `linux_runtime.cpp`) include the generated header; Android reads the JSON
  asset (`NativeLayoutModel`). One source, no private copies.
- Picking a layout applies it live and persists it per system
  (`an3.native-screen-layout.v1.<system>` on macOS, `screen-layout-<system>` /
  `nds-layout` preferences on Android, `screen-layout.txt` on Linux). Legacy
  spellings (`side_by_side`, `top_bottom`, `left-right`, `top-bottom`) still
  resolve so an existing preference keeps working.

**Toolbar Save.** A Save button beside the speed row exposes the Save States
tab's quick actions without opening the menu: **Quick Save**, **Quick Load**,
**Auto Save now**, **Load Auto Save** (slot 1 quick save/load; auto save uses
the shared atomic writer).

**Verification.** macOS: generator `--check` OK, `cargo check` compiles the
`.mm`, `npm run build:macos` produced the 1.2.0 DMG, and the runtime smoke ran
the new NDS layouts (left-right, hybrid-top, largescreen-bottom, right-left,
bottom-top) at ~50 fps each. Linux/Android code was updated to consume the same
schema but their runtime builds were **not** rerun here.
