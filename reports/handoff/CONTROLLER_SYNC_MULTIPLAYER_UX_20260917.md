# Vibe Coded Emulator — controller / sync / multiplayer UX refactor (2026-09-17)

Workspace: `/Users/meomeo/Documents/edit an3tocom apps&web` (branch `apps-web`).
Staging: `http://192.168.1.8:8092`, asset **`f2c429f14adc`**, release
`/opt/an3-arcade-staging/releases/20260917-023241-f2c429f14adc`, rollback
`/opt/an3-arcade-staging/releases/20260917-022918-5865f46a5f3a`.
Production was never touched.

## Scope actually delivered

This session implemented the **web/consumer layer** of the refactor: the surfaces
that were exposing staging tooling to users, plus the controller input path and
the truthful connection state. Native packaged apps were **not rebuilt** (their
2.0.0 installers still bundle the previous web UI), and server-mediated LAN
rendezvous was not replaced with true peer-to-peer listeners.

### What changed (files)

- `app.py`
  - Controller: sessions carry a short `name`, a `system`, and the creator's
    subnet; new host acknowledgement `POST /api/controller/ack`, phone status
    `GET /api/controller/link`, LAN discovery `GET /api/controller/hosts`, and
    Advanced Diagnostics `GET /api/diagnostics` + `/diagnostics` page.
  - Sync: `Automatic` mode catalog, per-device content toggles (save/state/
    library/rom, rom off by default), `content` column migration.
  - Multiplayer: per-core capability map, game picker when opened without a
    slug, relay origin removed from the product surface.
  - `/controller`, `/controller/join`, `/sync`, `/multiplayer` rewritten as
    product pages; every `STAGING · …` feature label removed.
- `netcode.py`: `ControllerState` touch tuple `[x, y]`; `ControllerSession`
  acknowledgement (`ack`/`ack_sequence`/`input_active`) with a two-frame
  liveness window.
- `sync_engine.py`: `SyncMode.AUTO`, `requires_drive`, `drive_available`
  transport selection.
- `static/controller.js`, `static/sync.js`, `static/multiplayer.js` rewritten;
  new `static/diagnostics.js`; `static/player.js` phone host now injects NDS/3DS
  touch and acknowledges applied frames; `static/site.css` new surfaces + a
  non-overlapping phone pad.
- Tests: `tests/test_netcode.py`, `tests/test_sync_engine.py`,
  `tests/test_sync_api.py`, `tests/test_multiplayer_api.py`,
  `tests/test_integration.py` extended.
- `docs/REGRESSION_GUARDS.md`: RG-096 – RG-102.

### Not done / explicitly out of scope this session

- Native apps are **not rebuilt**: the Android `Controller Mode` entry in the
  library/Settings, native LAN discovery, and native rebuild/version bump are
  still open. The native in-game host code is unchanged.
- No true peer-to-peer LAN listener; LAN transfer is still the staging-server
  rendezvous (verified in RG-095). Sync still does not read/write real client
  save stores, so the conflict UI is wired to the real endpoint but not
  populated by the web build.
- Multiplayer remains relay-mediated input lockstep, GBA only.
- Google OAuth / Drive transport still needs owner credentials.

## Verification

### Automated

- Python suite: **282 tests, 0 failures** (`python3 -m unittest discover -s tests`).
- Node contract suites: `web_nds_touch_behavior`, `web_renderer_behavior`,
  `native_android_library` all pass. `node --check` clean on all changed JS.
- Playwright (local, staging mode): every new page renders with **0 console
  errors** (only the pre-existing COOP-on-HTTP notice) and **0 horizontal
  overflow** at 390×844, 820×1180, 1440×900.
- Phone pad geometry: pairwise bounding-box overlap check reports **no overlaps**
  for GBA and NDS in portrait; the `[hidden]` panel override that pushed the pad
  off-screen was found and fixed.

### Runtime, end-to-end (staging, real devices)

- **GBA drive chain (verified).** Player `/play/pokemon-emerald` hosted session
  `43F3Z7`; the phone auto-selected the GBA layout; both sides showed
  `Connected`; the phone's Start press produced `simulateInput(0,3,1)` /
  `(0,3,0)` on the live core (wrapped core observed the calls).
- **Held input + release on disconnect (verified).** Holding `right` then
  disconnecting produced `[0,7,1]` then `[0,7,0]`; the host returned to
  "Waiting for a phone…".
- **Truthful state (verified).** With no host acks the phone shows
  "Connected — input unavailable"; a scripted host ack loop flipped it to
  "Connected". Pairing alone is never reported as applied input.
- **NDS stylus path (verified).** `/play/pokemon-mystery-dungeon-explorers-of-sky`
  running; the phone showed the NDS layout; a touchscreen drag produced
  `mousedown` → four `mousemove` (advancing coordinates) → `mouseup`, all
  `pointerType:"touch"` on the source canvas.
- **Sync (verified UI/API).** `/sync` listed `auto,lan,drive(disabled),off`,
  "Google Drive sync unavailable in this build", ROM warning, per-device save.
- **Multiplayer (verified room flow).** GBA game page created room `TC08MX`; a
  same-game guest joined ("Compatible. Connecting…") and the host showed
  "Player joined. Connecting…"; the NDS game page showed "Not available for this
  system" with no Create button.
- **Reverse path also exercised:** the standalone `/controller` host + phone
  shows nearby-host discovery and pairing; it truthfully reports
  "input unavailable" because it has no emulator to apply input.

## Honest status (per the requested final report format)

- **Phone Controller: Partially verified.**
  - Implemented + verified: native-app-free phone web controller, automatic
    layout (GBA/NDS/3DS/custom), large non-overlapping pad, analog sticks,
    NDS/3DS touchscreen, haptics, truthful connection state, release-on-stop,
    LAN nearby-host discovery, advanced diagnostics.
  - Not verified: a real phone driving a **packaged macOS/Windows/Linux/Android
    app**; Android library `Controller Mode` (not implemented).
- **Sync: Partially verified.**
  - Implemented + verified: Automatic mode, plain-language modes, content
    toggles with ROM warning/off-default, device list, conflict-resolution
    endpoint, LAN manifest/blob transfer (previously verified byte-exact).
  - Not done: real client save/save-state store integration, true peer-to-peer
    transfer, Drive transport (needs credentials). Conflict UI is not populated
    by the web build because no local store is wired.
- **Multiplayer: Partially verified.**
  - Implemented + verified: game-centered Create/Join room-code flow, copy/QR,
    compatibility check messaging, per-core capability (GBA only), relay hidden
    from normal UI.
  - Not done: peer video (does not exist in this build), NDS/3DS/Switch
    multiplayer (unverified, so unadvertised).

## Devices/platforms actually tested

- macOS host (this machine) running the staging server + Chromium via
  Playwright (desktop and mobile-emulated viewports); staging server on
  `192.168.1.8:8092`. No physical Android/Windows/Linux device was exercised in
  this session; the packaged-app native injection was not re-tested.

## Controller latency

Not measured against a physical phone. The design target is low-latency
latest-state-wins with ordered transition frames and a 400 ms idle heartbeat;
`/diagnostics` exposes RTT-derived latency for the host page. No number is
claimed.

## Staging status

Deployed to staging only (`STAGING_DEPLOY=PASS`, asset `f2c429f14adc`); rollback
retained. Production untouched.
