# Phone Controller — a phone as a direct LAN controller

Read when: you work on pairing a phone as a controller, pairing codes and tokens,
controller input dispatch, reconnect, or release-all on focus/transport loss.

Skip when: the task is save transfer ([lan-sync](lan-sync.md)) or gamepad support
through the operating system (not this feature).

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| Pairing: 6-digit code, expiry, one-use, rate limit, token stored as a digest | `GOOD` | `netcode.py`; `tests/test_netcode.py` |
| Controller state frames (bit-packed, latest-state-wins, `needs_resync`) | `GOOD` | `netcode.py` and its tests |
| Server routes (`/api/controller/*`) | development/test fixture only | `docs/LAN_PEER_ARCHITECTURE.md`; the product path is a direct peer |
| Web controller UI (`/controller`, `/controller/join`) | `GOOD` at source level | `static/controller.js`, `static/controller-utility.js` |
| Desktop host in the native shell | `GOOD` at source level | `native-offline/src-tauri/src/controller_host.rs`; `tests/test_phone_controller_hosts.py` |
| Android client and host bridge | `GOOD` at source level | `ControllerClient.kt`, `An3ControllerHost.kt`, `ControllerHostService.kt` |
| Two real devices, internet off, live gameplay input | `UNVERIFIED` | Recorded staging pairing is dated and not two-device gameplay |
| Input release on focus loss / disconnect / explicit stop | `GOOD` at source level | Covered by native controller pad tests; device behaviour `UNVERIFIED` |

## Code map

- `netcode.py` — pairing code generation, token digest, controller state.
- `static/controller.js`, `static/controller-utility.js` — phone UI and actions.
- `static/input-actions.js` — the shared input action model.
- `native-offline/src-tauri/src/controller_host.rs` — desktop-side host.
- `native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/`
  — `ControllerClient.kt`, `An3ControllerHost.kt`, `ControllerHostService.kt`.
- `docs/LAN_PEER_ARCHITECTURE.md` — pairing/transport contract.
- `docs/checkpoints/direct-lan-controller.md` — milestone record.

## Invariants

- Pairing is one-use and expires; a consumed token cannot be replayed.
- The phone talks to the host directly on the LAN; no server relay or rendezvous.
- Latest-state-wins with an explicit resync path; a dropped session does not
  leave a button held.
- Release-all runs on focus loss, explicit stop and transport loss.
- Input reaches the same action model as the on-device pad and keyboard; do not
  create a second input path.

## How to verify

```sh
python3 -m unittest tests.test_netcode tests.test_phone_controller_hosts
node --test --test-concurrency=1 tests/native_controller_pad.test.mjs tests/controller_utility.test.js
```

Acceptance needs two real devices on one LAN with internet disconnected:
discover → pair with a fresh code → play → release on focus loss → disconnect →
reconnect with the token (or pair again) → no stuck input. Record devices,
revisions and the observed latency/failures.

## Open work

1. Record the two-device gameplay run; today every device row is `UNVERIFIED`.
2. Make the entry point discoverable in the native UI without adding clutter —
   coordinate with [ui-shell](ui-shell.md).
3. Confirm the phone UI works against the packaged desktop host, not only the
   development server.

## Related

- [lan-sync](lan-sync.md), [android](android.md), [ui-shell](ui-shell.md)
- `docs/LAN_PEER_ARCHITECTURE.md`,
  `docs/checkpoints/direct-lan-controller.md`
