# Web phone-controller binding + pairing QR — staging verification (2026-09-16)

Ordered-plan step 2. All evidence below is from the actual runs; nothing is
claimed beyond them.

## What changed

- `app.py`
  - `import qrcodegen` (vendored, MIT — see below).
  - `controller_join_url(scheme, host, code)` builds the absolute join URL from
    the request's own `Host` header, validated by regex; caller values are never
    used.
  - `controller_qr_svg(text)` renders a self-contained SVG (one `<rect>`, one
    `<path>`, explicit `width`/`height`, no scripts, no external refs).
  - `GET /api/controller/qr.svg?code=` serves that SVG (`image/svg+xml`,
    `no-store`), gated by `CONTROLLER_ENABLED` (production 404).
  - `Handler.read_optional_json()` drains an ignored POST body; fixes a
    keep-alive corruption bug (RG-082).
  - `controller_create_session` drains its body.
  - Player page: `controllerEnabled` in the player config, a `Phone controller`
    button in Advanced, and a `#ctrlPhonePanel` (code, link, QR, status).
  - `/controller` host page: `#ctrlQr`.
- `static/player.js`: the player page is the pairing host. It creates a session,
  shows code/link/QR, polls `/api/controller/state` at 250 ms, and applies the
  phone's latest frame through the same `input()` / `analogInput()` path the
  on-screen pad uses. Input is applied only while `gameStarted && !runtimeFailed
  && !emulator-menu-open`; it releases all buttons/axes on disconnect, panel
  close, session end, and `pagehide`.
- `static/controller.js`: the host panel sets the QR image source.
- `static/site.css`: `.ctrl-qr` styling.
- `qrcodegen.py`: vendored Project Nayuki QR encoder (MIT), sha256
  `9f4ed1dd201dcb92b1bc0d6e14f46c754bcff0ce48580c5d7e8ace8f6926c8ef`.
- `deploy/package-staging.sh`, `deploy/package-production.sh`,
  `deploy/update-production.sh`: ship `qrcodegen.py`.

Version bump: none. No packaged native artifact changed, so no native version
was bumped (the rule applies to packaged apps).

## Build / test

- `python3 -m py_compile app.py qrcodegen.py` PASS.
- `node --check static/player.js` PASS; `node --check static/controller.js` PASS.
- Full suite: **237 tests, 0 failures** (baseline 225; +12 guards/tests).
- Player regression guards (AGENTS list) before/after the `player.js` +
  `site.css` edit: `tests.test_regression_invariants`,
  `tests.test_web_nds_touch_behavior`, `tests.test_native_regression_guards`,
  `tests.test_shared_player_ui` → OK; `node tests/web_nds_touch_behavior.test.js`
  → ok; `node tests/web_renderer_behavior.test.js` → 11/11 pass.
- QR correctness: the vendored encoder's module matrices from a rendered PNG
  were decoded with OpenCV (`cv2.QRCodeDetector`) across LOW/MEDIUM/QUARTILE/HIGH
  and versions 1..18 — all payloads recoverable (three auto-mask cases needed a
  different mask in OpenCV, i.e. detector weakness, not encoder error).

## Staging deploy

- `source tools/ssh/staging-env.sh && tools/ssh/check-staging-key.sh` →
  `STAGING_SSH_KEY_AUTH=PASS`.
- `./deploy-stage.sh` → `STAGING_DEPLOY=PASS`, asset `51d627516e1a`, release
  `/opt/an3-arcade-staging/releases/20260916-141246-51d627516e1a`, rollback
  `/opt/an3-arcade-staging/releases/20260916-140759-51d627516e1a`.
- `/health` 200 `environment=staging`; `/api/controller/qr.svg?code=AB12CD` 200
  `image/svg+xml`; `/controller` serves `#ctrlQr`; `/play/pokemon-emerald`
  serves `controllerEnabled` + `#ctrlPhonePanel`.

## Runtime acceptance — "a phone moves the game" (VERIFIED)

Chrome via playwright-cli against `http://192.168.1.8:8092`:

1. Host: opened `/play/pokemon-emerald`; waited for
   `EJS_emulator.gameManager.simulateInput` (emulator running); wrapped
   `simulateInput` to record calls; opened `#playerControls` → `#phoneController`;
   read pairing code `EG9JFT`; `#ctrlPhoneQr` rendered (`naturalWidth=41`).
2. Phone: opened `/controller/join?code=EG9JFT`; `#ctrlConnect` → `Connected`;
   held the `Right` button 400 ms then released.
3. Host observed `simulateInput(0,7,1)` then `simulateInput(0,7,0)`; host status
   `Phone connected · 117s`.

So phone input reached the emulator input path end-to-end on staging.

Also verified: the `/controller` QR PNG decodes (OpenCV) to
`http://192.168.1.8:8092/controller/join?code=39EW5E`.

Evidence: `/Users/meomeo/Documents/edit an3tocom apps&web/reports/staging/controller-qr-20260916.png`

## UNVERIFIED

- **Android/Linux/Windows/macOS native input injection** from the phone — not
  implemented in this phase; only the web player host binding exists.
- Real-phone camera scan of the QR (decoded programmatically, not by a phone).
- Two-machine phone→host across separate devices (single browser, two pages).
- Google/relay/LAN items remain out of scope for this step.

## Regression found and fixed during verification

RG-082 (keep-alive body drain). The first E2E run surfaced
`501 Unsupported method ('{"deviceId":"host-player"}GET')` on the host console.
Root cause: `controller_create_session` ignored its body. Fixed and now guarded
by `test_session_create_consumes_its_body_on_a_keepalive_connection`.
