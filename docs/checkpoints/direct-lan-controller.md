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

## Gotchas already learned

- Accepted TCP sockets inherit the listener's non-blocking mode on Unix — call
  `set_nonblocking(false)` before `set_read_timeout`.
- The message kind must be `k`; `t` is the touch tuple.
- The Windows Tauri build breaks if macOS `._*` AppleDouble files are copied
  into the source tree (exclude `._*` from sync tarballs).
- Android `NativeGameActivity` runs in `:game`; the controller host lives in the
  main process and forwards input through `ControllerHostService`.
