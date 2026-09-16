# Desktop native phone-controller host — build + logic verification (2026-09-16)

Step 2 follow-up ("native injection"), desktop platforms. This adds the shared
Rust host for macOS/Linux/Windows. Android was already done (1.4.0).

## What changed

- `src-tauri/src/controller_host.rs` (new) — one platform-agnostic host:
  - plain HTTP/1.1 over `std::net::TcpStream` (the controller service is a LAN
    HTTP origin; https is refused explicitly), no new HTTP dependency;
  - creates a session (`ttlSeconds` 3600), polls `/api/controller/state`, and
    applies the phone frame through the existing `set_native_input` path, so
    macOS, Linux and Windows all share it;
  - `frame_input()` maps the frame to a full `NativeInput` snapshot (libretro
    button bits + circle/cstick) with the axis-engaged d-pad mirroring the web;
  - releases input on stop, session end (403/404), and stops on window destroy.
- `src-tauri/Cargo.toml` — adds `serde_json` (already in the Tauri tree).
- `src-tauri/src/lib.rs` — `mod controller_host`, commands
  `native_controller_start/stop/status`, registered in the handler.
- `web/native-bootstrap.js` — `window.AN3NativeController` (desktop only).
- `web/index.html` + `web/native-app.js` — a **Settings → Phone controller** card
  (server URL, pairing code, live status, Start/Stop).
- `scripts/package-macos.sh` — derives the DMG name from `tauri.conf.json` so a
  version bump cannot publish a stale filename.
- Version: desktop **1.3.0 → 1.4.0** (`package.json`, `tauri.conf.json`).
  Linux/Windows artifacts remain 1.3.0 in the catalog until rebuilt; the code
  path is shared and already in the tree.

## Verification (what was actually run)

- **Rust tests (6 passed)** — `cargo test --lib controller_host`:
  - `frame_input` button/axis mapping and the empty (unpaired) frame;
  - `parse_base` (http only, port parsing, rejects https/bare host);
  - `http_request` status/body parsing against a scripted local TCP server;
  - **full session lifecycle** against that server: create session → poll →
    the phone's `right` press reaches an injected input sink (`buttons & (1<<7)`)
    → `status()` reports running/paired/input → `stop()`.
  - the button map equals the shared web indices (`button_map_tests`).
- **Python guards** — `tests.test_multiplayer_api.ControllerButtonParityTests`
  now asserts the Rust map, the Kotlin map, and the web map are identical
  (12 entries). Full suite **257 tests, 0 failures**.
- `node --check` on the new/changed JS.
- **macOS build + launch smoke**: `npm run build:macos` produced
  `vibecodedemulator-1.4.0-macos-aarch64.dmg` (44,810,277 B,
  sha256 `638d44ee…`), `hdiutil verify` VALID. Mounted, `CFBundleShortVersionString`
  = **1.4.0**, the bundled UI contains `nativeControllerCard`, and the app
  launched and stayed alive (10 s, no stderr). Closed and detached.
- **Live probe against staging** (ignored by default; run with
  `AN3_CONTROLLER_TEST_BASE=http://192.168.1.8:8092 cargo test --lib live_staging -- --ignored --nocapture`):
  the desktop client created a **real** session (code `X911XP`), paired as a
  phone, submitted `right` frames, and the input sink received the press. This
  exercises the real server's field names and the full poll/apply loop, not just
  canned JSON.
- **Staging**: `./deploy-stage.sh` → `STAGING_DEPLOY=PASS`, asset
  `e792e8578089`, release `/opt/an3-arcade-staging/releases/20260916-162332-e792e8578089`;
  the 1.4.0 DMG URL returns 200 with the catalog size.
  `RELEASE_CATALOG=PASS (5 installers)`.

## UNVERIFIED

- **A phone driving a *running desktop game*** — the client is verified live
  against staging and the app builds/launches, but no phone was connected while
  a macOS game was playing, so the final core-injection link is not observed
  end-to-end on desktop (Android has that observation).
- **Linux/Windows compile and run** — the module is platform-agnostic and macOS
  compiles it; the Linux/Windows builds were not run and their artifacts remain
  1.3.0.
- The analog stick and buttons other than the mapped set are covered by the
  mapping test only, not by a live phone.

## Rollback / notes

- No behavior changes when the controller is not started: the commands are
  inert, the card is hidden unless `window.AN3NativeController` exists, and
  `set_native_input` is only called from the host thread while a session runs.
