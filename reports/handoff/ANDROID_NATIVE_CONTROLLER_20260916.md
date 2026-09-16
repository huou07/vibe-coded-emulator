# Android native phone-controller host — staging verification (2026-09-16)

Ordered-plan step 2 follow-up ("native injection"). Android is the first native
platform; macOS/Linux/Windows are not implemented yet.

## What changed

- `native-offline/.../offline/ControllerClient.kt` (new) — staging-only host:
  creates a session, polls `/api/controller/state`, maps the phone frame onto
  the same libretro indices the web player uses, and calls back per button/axis.
  The raw host token never leaves the object and is never logged.
- `NativeGameOverlay.kt` — a General-tab "Phone controller · staging" section:
  server URL field, live status, and a Start/Stop action. Input is applied only
  while the menu is closed (`shouldApply = { !isMenuOpen() }`) and is released on
  stop.
- `NativeGameActivity.kt` — stops the controller on `onDestroy`.
- `AndroidManifest.xml` + `res/xml/network_security_config.xml` — cleartext
  stays disabled by default and is permitted only for the staging host
  (`192.168.1.8`) and loopback, so plain-HTTP LAN pairing works without opening
  the whole app.
- `app.py` — `POST /api/controller/session` now accepts a bounded `ttlSeconds`
  (60–3600, default 120) so a native game session outlives the web pairing
  window.
- `scripts/build-android-staging.sh` — derives the artifact name from
  `tauri.android.conf.json` so a version bump cannot publish a stale filename.
- Version: Android **1.3.0 → 1.4.0** (new feature). Desktop artifacts stay
  1.3.0.

## Build / test

- `bash scripts/build-android-staging.sh` → `vibecodedemulator-1.4.0-android-arm64-staging.apk`
  (49,587,834 B, sha256 `3c7518a2809335c8687c153c08bb2c6e8d427ff0712924c167dff202af4397ba`),
  Kotlin compiled clean.
- Full suite green after the catalog/version test updates.
- `tools/verify-release-catalog.py` → `RELEASE_CATALOG=PASS (5 installers)`.

## Staging deploy

`./deploy-stage.sh` → `STAGING_DEPLOY=PASS`, asset `e792e8578089`, release
`/opt/an3-arcade-staging/releases/20260916-155256-e792e8578089`; the 1.4.0 APK
URL returns 200 with the catalog size/sha.

## Runtime acceptance (VERIFIED, AVD `codex-nds-api35`)

1. Installed the 1.4.0 APK (`versionCode=1004000`), launched the GBA fixture;
   `FPS core=59 present=59`.
2. In-game Menu → General → **Start phone controller** → the app created a
   staging session and showed `Pairing code 0M656E · waiting for a phone ·
   3594s` (the 1-hour TTL the native host requests).
3. From the Mac, paired as the phone (`POST /api/controller/pair`) and sent six
   `start` press/release frames.
4. The Android host reported `Phone connected · no input · 3479s`, the action
   became **Stop phone controller**, and the game advanced from the **Game Freak
   logo** to the **NEW GAME / OPTION** main menu.

Screenshots:
`/Users/meomeo/Documents/edit an3tocom apps&web/reports/android-regression/`
`1.4.0-phone-controller.png`, `1.4.0-phone-before.png`, `1.4.0-phone-after.png`.

## UNVERIFIED

- macOS/Linux/Windows native injection (not implemented).
- Android controls beyond a digital button (`start`); axes/analog and the other
  buttons are mapped but not exercised here.
- The feature only works when the native device can reach the configured
  controller server; on a device that cannot reach the staging host it reports
  "Controller unavailable".
