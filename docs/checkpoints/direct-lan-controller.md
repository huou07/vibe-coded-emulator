# Checkpoint — Direct LAN controller (AN3 Controller LAN v1)

Updated: 2026-10-14. This checkpoint is the durable task record for direct
LAN phone-controller work. Status below separates code/test evidence from
packaged and two-device acceptance.

## Status

| Milestone | Status |
| --- | --- |
| Six-digit pairing code, expiry and one-use pairing | Implemented in Android and desktop source; Android runtime UNVERIFIED |
| Direct Android discovery and encrypted TCP host/client | Implemented in `ControllerClient.kt`; source checks pass, runtime UNVERIFIED |
| Android game input bridge across the isolated game process | Implemented in `An3ControllerHost.kt` and `ControllerHostService.kt`; runtime UNVERIFIED |
| In-app host/join entry points | Implemented in native shell source; actual packaged UI UNVERIFIED |
| GBA/NDS/3DS pad layouts, touch and utility actions | Implemented in native shell source; visual/device acceptance UNVERIFIED |
| Release-all on focus loss, explicit stop and transport loss | Implemented in shell/client source; device behavior UNVERIFIED |
| Token-based reconnect after a dropped Android session | Implemented in current Android source; pending native compile and two-device runtime acceptance |
| Two real peers, internet disconnected, per-host platform acceptance | Not run; no Android device is connected on this worker |
| Regression/source checks | GOOD for the current local project gate; see evidence below |

## Protocol — AN3 Controller LAN v1

- UDP multicast discovery: group **239.255.43.3**, port **47831**. Hosts
  advertise every 2s using the public peer envelope
  `{"an3":"peer","service":"an3-peer","v":1,"id":"<device id>","name":"<label>","port":47832,"capabilities":["controller"]}`.
  Android advertises only the controller capability; no pairing or account
  secrets appear in the discovery record.
- Control: TCP port **47832**, persistent stream, frames = 4-byte big-endian length + body.
- Plaintext handshake:
  - controller → host: `{"k":"hello","v":1,"pub":"<b64 SEC1 uncompressed P-256>","id":"<device id>","name":"<controller label>","capability":"controller"}`
  - host → controller: `{"k":"hello","v":1,"pub":"<b64>","id":"<host id>","name":"<host label>"}`
- Key exchange: ephemeral **P-256 ECDH**; shared secret = x-coordinate.
  `salt = SHA256("an3-ctrl-v1|" + secret)` where `secret` is the **6-digit pairing code**
  (first pairing) or the **32-byte session token** (reconnect). `key = HKDF-SHA256(ikm=shared, salt, info="an3-ctrl|v1|session", L=32)`.
  The code/token is never transmitted.
- Encrypted frames: `[12-byte nonce || AES-256-GCM ciphertext+tag]`.
  nonce = 4-byte direction (`0x00000001` phone→host, `0x00000002` host→phone) + 8-byte counter.
  Counter starts at 0 per direction; TCP ordering makes gaps impossible on a live connection.
- Message kinds (**`k`**, never `t` — `t` is reserved for the touch tuple so
  `frame_input` keeps working):
  - `auth` (phone→host, counter 0) — proves the code/token by AEAD success.
  - `ready` (host→phone) — `{"k":"ready","token":"<b64 32B|null>","system":"gba"}`.
  The desktop and updated Android hosts issue a session token on first pairing;
  Android retains it only in process memory, pins reconnect discovery to the
  paired host id, and sends no token in status or discovery data.
  - `state` (phone→host) — `{"k":"state","s":seq,"b":[names],"a":[lx,ly,rx,ry],"t":[x,y]?}`,
    plus an optional one-shot utility list
    `"u":[{"action":"QUICK_SAVE"|"SPEED_UP"|"SPEED_DOWN"|"OPEN_MENU","sequence":N}]`.
    Actions are the canonical ids from
    `native-offline/shared/input-actions-schema.json` with a per-press
    sequence, dispatched once through the shared host sink; an unsupported
    action advances nothing and a retried frame never re-runs. Implemented in
    `lan_host.rs::apply_state` (`dispatch_utilities` over the `u` array) and
    covered by the direct-transport integration test (canonical
    `QUICK_SAVE`, retry ignored).
  - `ack` (host→phone) — `{"k":"ack","s":seq,"inputActive":bool,"system":"gba"}`.
- Security properties: encryption + authentication via standard primitives
  (p256 ECDH, HKDF-SHA256, AES-256-GCM). Pairing is local-network only,
  rate-limited (6 failures/IP/minute), the code expires after 120s, is
  invalidated after one successful pairing, and never becomes the session
  credential.

## Implementation map and verification evidence

- `native-offline/src-tauri/src/lan_host.rs` and `controller_host.rs` provide
  the desktop direct host/input path. The current worker did not exercise a
  packaged desktop peer.
- `native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerClient.kt`
  implements Android multicast announce/discovery, direct TCP, P-256 ECDH,
  AES-GCM framing, one-use pairing, input/axis/touch/utility dispatch, and
  release on socket end or stop. It issues and retains host resume tokens,
  supports reconnect as a controller, and exposes only a `canReconnect` status
  flag; the token remains private to the process.
- `native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/An3ControllerHost.kt`
  shares the app-scoped controller host and input sink.
- `native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerHostService.kt`
  bridges the app and isolated game processes and releases held input when the
  game sink detaches.
- `native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/MainActivity.kt`
  exposes native start/join/send/stop/status bridge methods.
- `native-offline/web/native-app.js` contains host/join controls, GBA/NDS/3DS
  layout selection, touch/analog/button/utility actions, and blur release-all.
- `tests/test_phone_controller_hosts.py` checks Android source integration,
  capability declaration, utility dispatch and pairing guards. These are source
  checks, not Kotlin compilation or device acceptance.

## Dogfooding record — `vce-product-journeys`

- Procedure used: inspected target availability first, traced the real native
  entry points and recovery/release behavior, then updated this checkpoint with
  source evidence and remaining platform rows.
- Friction found: this checkpoint still called the Android client, host and UI
  “not started,” obscuring a real reconnect gap and overstating remaining work.
- Outcome: Android process-memory token reconnect now targets the paired host,
  keeps the token out of status/discovery, replaces a stale host socket safely,
  ignores errors from replaced sockets, and reports input inactive after loss.
  The packaged Android shell and bootstrap assets were refreshed; a regression
  guard checks both against source. Packaged/two-peer behavior remains UNVERIFIED.
- Friction found: the Android generated shell/bootstrap copies had fallen behind
  their source, and the host could continue reporting active input after a peer
  disconnected. The existing package synchronization test exposed the first
  issue; source review exposed the second.
- Outcome: regenerated the two affected assets, expanded the equality guard, and
  tied host input status/release to the currently active socket. No unrelated
  build outputs were regenerated.
- Further friction found during reconnect review: a WebView reload resets the
  phone's frame counters while the Android host retained the counters from the
  previous authenticated socket. After reconnect, fresh controller frames could
  therefore be discarded as old input.
- Outcome: reset state and utility counters inside the new authenticated socket
  activation, and added a regression guard for that boundary. The full local
  gate passes; reconnect remains UNVERIFIED on a real Android peer.
- Target evidence: `an3ctl targets --json` reported no connected Android device;
  Playwright was unavailable for the Web target. No replacement app server or
  emulator was started.
- Latest full local gate in this session: job `bash-711` was launched on
  2026-10-14 from commit `5a132d5`, after the Android reconnect implementation in
  `8f8fabc` and the CI fixes in `08c944b`/`b5be4cd`. The worktree also contained
  the preserved `app.py` and `static/site.css` edits and evidence-only changes.
  `bash tools/verify-project.sh` exited 0: 475 Python tests passed with 20
  skipped; JavaScript 90 passed with 3 skipped; native JS syntax, documentation
  references and whitespace checks passed. Playwright, Android device and local
  emulator legs were skipped because their targets were unavailable. This is
  source-gate evidence, not a clean-artifact or packaged runtime result. The
  later commits `67a81d1`, `d7d89d1` and `e8b4765` update documentation/evidence;
  the current source HEAD is `e8b4765`. No Android/Kotlin build or direct-peer
  runtime was run.

## Next discriminating actions

1. Compile/package the Android source on the authorized builder and resolve
   any compile or protocol failures. Tokens currently last only for the process
   lifetime; app-restart recovery remains unimplemented.
2. Run the packaged controller flow on an Android phone against each advertised
   host platform, using two peers on the same LAN with internet disconnected.
   Record discovery/join, each system layout and action, focus/network loss,
   release-all, reconnect, and stop/token lifecycle.
3. Correct any resulting UX/runtime defects, then update this checkpoint with
   artifact identity and observed outcomes. Do not mark two-device acceptance
   GOOD from source tests.

## Current-session target refresh (source `7dbe80e906da30e9b8fd4233158e02922a06f9c7`)

- The `vce-product-journeys` procedure and `an3-control-plane` target-first
  check were used on 2026-10-14. `tools/an3ctl/bin/an3ctl targets --json`
  exited 0: Web exists but `playwright-cli` is missing; no Android device is
  connected; no local player or Switch harness is installed; the macOS UI bridge
  and Linux WebKitGTK/WebDriver display path are absent; Windows is unreachable.
- No app, emulator, native build, or test peer was started. Consequently the
  packaged join/reconnect, release-all, and real LAN behavior remain
  **UNVERIFIED**. This refresh confirms the existing dependency; it does not
  replace the prior source-gate result or claim a runtime regression.
- Next discriminating action remains a native Android build on an authorized
  builder followed by two real peers on the same LAN with internet disconnected.
  Required evidence: artifact hash, discovery and pairing, each advertised host
  platform, input release on focus/network loss, reconnect, and stop/token
  lifecycle. No such builder/device is available in this worker snapshot.

## Gotchas already learned

- Accepted TCP sockets inherit the listener's non-blocking mode on Unix — call
  `set_nonblocking(false)` before `set_read_timeout`.
- The message kind must be `k`; `t` is the touch tuple.
- The Windows Tauri build breaks if macOS `._*` AppleDouble files are copied
  into the source tree (exclude `._*` from sync tarballs).
- Android `NativeGameActivity` runs in `:game`; the controller host lives in the
  main process and forwards input through `ControllerHostService`.

## Target refresh and web-lane progress (2026-10-17)

- `tools/an3ctl/bin/an3ctl targets --json` exited 0 on this host: Web is
  available with `playwright-cli` present (no branded Chrome, so the adapter
  falls back to the Playwright-bundled Chromium); Android is unavailable (no
  connected device); the emulator has no local player and its configured Linux
  and Windows SSH targets were not probed as reachable; Switch has no harness;
  macOS has no UI-control bridge; Linux lacks WebKitGTK WebDriver/display;
  Windows is unreachable. No native build, emulator, controller host or
  two-peer session was started.
- The browser lane did improve this session: the direct-LAN checkpoint's
  remaining gap is still the two-peer journey, not the web library. Browser
  evidence is now `GOOD` for the `/games` search/filter/reset journey, admin
  comment moderation and a real-browser IndexedDB quick-save round-trip
  (RG-150/RG-152/RG-153). None of that is a controller or device result.
- Two real peers on the same LAN with internet disconnected and a compiled
  Android (or desktop) build remain the next discriminating action. The
  Android token lifetime is still process-only; app-restart recovery is
  unimplemented.

## Two-peer attempt on this host, 2026-10-18 — BLOCKED on the network stack

A two-peer run was attempted with two instances of the **packaged Linux shell**
(`VibeCodedEmulator_3.2.5_amd64.deb`, sha256
`29287b38f4ab0c04768a08d7b26d3c7cd2dd81695f4d4d569c8baba11c79888b`, built with the
test-only `ui-control` feature), separate `XDG_DATA_HOME` trees, distinct device
identities, driven through their own control bridges on one host.

Three defects were found and two were fixed:

1. **The packaged app could not run two instances.** The local game runtime bound
   the fixed loopback port 38471, and the Tauri capability pinned the remote IPC
   origin to `http://127.0.0.1:38471/*`, so the documented isolation knob
   (`AN3_NATIVE_RUNTIME_PORT`) made the second instance's WebView load an origin
   that had no IPC at all: every bridge call answered "the web UI did not answer
   in time". Fixed by enumerating the second loopback origin (`38472`) in
   `native-offline/src-tauri/capabilities/default.json`. The origin stays
   loopback-only and explicit; an ephemeral port (`AN3_NATIVE_RUNTIME_PORT=0`)
   still has no IPC, which is now a stated limitation rather than a silent one.
2. **A failed direct-LAN action hid its own reason.** A Tauri command rejection is
   a plain string, so `error?.message` is undefined and the join handler replaced
   the transport's reason with one generic sentence. With `describeError` the same
   run reported **"No AN3 controller host was found on the local network."**
   Guarded by `tests/test_phone_controller_hosts.py::DirectLanFailurePathTests`.
3. **Nothing else could run: this host does not deliver multicast to a
   same-host listener.** Reproduced outside the product with two plain UDP
   sockets (`work/phaseC/multicast-loopback-repro.txt`): with the sender's
   `IP_MULTICAST_LOOP` enabled and the receiver joined to `239.255.43.3:47831`,
   **nothing is received** under any of four interface selections
   (`ANY/ANY/ANY`, `ANY/ANY/enp0s31f6`, `ANY/enp0s31f6/enp0s31f6`,
   `enp0s31f6` on all three), while a **unicast** datagram to `192.168.1.8:47831`
   is received. `ip route get 239.255.43.3` reports
   `multicast 239.255.43.3 dev enp0s31f6 src 192.168.1.8 … rt_offload_failed`.
   Peer discovery is multicast-only by design, so the two instances never saw each
   other's advertisements and `join()` returned the discovery timeout above.

**The missing prerequisite is a second network stack**: two peers on one LAN
where multicast actually crosses the wire — physical devices, or a second
host/VM bridged onto the LAN. The VCE-dedicated AVD does not supply it either:
the Android emulator puts the guest behind QEMU user-mode NAT, which does not
bridge the LAN or carry the discovery group. Every two-peer and two-device row in
this file therefore stays `UNVERIFIED`, and the acceptance detail that remains
unexercised is: discovery → transfer → hash match → conflict choice → reconnect
for LAN Sync, and fresh code → play → release-all on focus loss / explicit stop /
transport loss → reconnect for the controller.

### What was established without two peers

| Check | Evidence |
| --- | --- |
| Two packaged instances coexist with separate storage and identities | both `/diag` answered; `systems="gba,nds,3ds"`, distinct instance ids in the discovery payload |
| The host imports and runs the lawful synthetic GBA fixture | `game-launch` clicked, `native-status` `data-state=running`, text "Native game window opened. Menu: F2 · Pad: F3 · Next Layout: F1" |
| The host issues a fresh six-digit pairing code and the controller accepts it as input | `controller-code` `183123`/`014182`, field filled with 6 digits, join handler passed its own `/^\d{6}$/` validation |
| A pairing failure reaches the user with its real cause | "No AN3 controller host was found on the local network." |
| Direct-transport source contracts | `tests/test_sync_engine.py`, `tests/test_sync_api.py`, `tests/test_native_sync_command.py`, `tests/test_netcode.py`, `tests/test_phone_controller_hosts.py` — 95 pass, 0 fail |
| Direct-transport JavaScript contracts | `tests/sync_transfer.test.mjs`, `lan_peer.test.mjs`, `native_sync.test.mjs`, `native_controller_pad.test.mjs`, `controller_utility.test.js` — 36 pass, 0 fail, 0 skipped |

No internet was disconnected for this attempt; the blocker is local multicast, and
no AN3 server was in the path (no server process was started at all).
