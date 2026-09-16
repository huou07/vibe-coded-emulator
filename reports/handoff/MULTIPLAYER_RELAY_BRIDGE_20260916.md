# Multiplayer room → EmulatorJS relay bridge — staging verification (2026-09-16)

Ordered-plan step 3. Evidence only for what was actually executed.

## What changed

- `app.py`
  - `player_content_security_policy(netplay_origin)` extracted as a testable
    function and now adds the relay's `ws://`/`wss://` origin to
    `connect-src`. This is the fix that lets the EmulatorJS netplay Socket.IO
    client connect at all (RG-085).
  - Player config adds `multiplayerEnabled` and a server-computed
    `roomSignature` (`system`, `core`, `romHash` from `game_rom_hash`).
  - Player page: a `Multiplayer` button in Advanced and a `#mpPlayerPanel` with
    create/host/join/leave plus code, QR and deep link (only when the staging
    relay is configured).
  - `GET /api/multiplayer/qr.svg?slug=&code=` renders a same-origin
    `/play/<slug>?room=<code>` QR as an SVG, gated by `MULTIPLAYER_ENABLED`.
- `static/player.js`: the AN3 room *is* the relay room. `Host on relay` calls
  `emu.netplay.openRoom(code, 2, "")`; `Join relay room` validates through
  `/api/multiplayer/join` (compat check) and then resolves the relay key from
  `getOpenRooms()` and calls `emu.netplay.joinRoom(key, code)`. `?room=` deep
  links prefill the join code.
- `static/site.css`: multiplayer panel styling.

Version bump: none (no packaged native artifact changed).

## Relay

The staging relay container existed but its published port was not active.
Restarted it on staging with the reviewed compose file
(`docker compose -f <release>/compose.rust-netplay.staging.yml up -d
--force-recreate`); `/games` returns `{}` and `/list` returns rooms.
No env, firewall, production, or unrelated container was changed.

## Build / test

- Full suite: **242 tests, 0 failures**.
- Player guards re-run after the `static/player.js` + `static/site.css` edits:
  `tests.test_regression_invariants`, `tests.test_web_nds_touch_behavior`,
  `tests.test_native_regression_guards`, `tests.test_shared_player_ui` OK;
  `node tests/web_nds_touch_behavior.test.js` ok;
  `node tests/web_renderer_behavior.test.js` 11/11.

## Staging deploy

`./deploy-stage.sh` → `STAGING_DEPLOY=PASS`, final asset `0e2a7d7a1a3b`, release
`/opt/an3-arcade-staging/releases/20260916-144055-0e2a7d7a1a3b`, rollback
`/opt/an3-arcade-staging/releases/20260916-143725-5f5e15dc4b71`.

## Runtime acceptance (VERIFIED): invite code == relay room

Chrome via playwright-cli, two pages, live relay `http://192.168.1.8:8094`:

1. Host `/play/pokemon-emerald` → Multiplayer panel → Create room → code
   `B4VZ0W` (QR rendered) → Host on relay.
2. Guest `/play/pokemon-emerald` → panel → join code `B4VZ0W` → Join relay room.
3. Relay `/list` observed the room as `current:1` after host and `current:2`
   after the guest joined; both pages reported `isNetplay=true` with a connected
   Socket.IO socket; guest `owner=false`.

So the AN3 invite code is the relay room name and both peers reached the relay
room. Evidence screenshot:
`/Users/meomeo/Documents/edit an3tocom apps&web/reports/staging/multiplayer-bridge-20260916.png`.

## UNVERIFIED

- **WebRTC peer media/input sync** between the two peers (the host video stream
  and remote input over the data channel). The relay bridge and socket handshake
  are verified; the peer connection outcome was not asserted.
- Real second machine (both pages ran in one browser context).
- GBA and NDS separately; only GBA (Pokemon Emerald) was exercised here.
- 3DS netplay (no verified network-emulation path; must not be advertised).

## Bugs found and fixed during verification

- RG-085 CSP WebSocket block (above).
- Duplicated link text in the multiplayer panel (`location.origin +` an already
  absolute `href`) — fixed and re-verified on staging.
