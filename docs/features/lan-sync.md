# LAN Sync — save transfer between two peers

Read when: you work on save transfer between two devices on the same LAN, peer
discovery, integrity checks, conflict choice, or the native sync commands.

Skip when: the task is phone-as-controller input ([phone-controller](phone-controller.md))
or cloud sync (removed; not a product feature).

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| Conflict engine (5 per-file decisions, never a silent overwrite) | `GOOD` | `sync_engine.py` is pure and unit-tested (`tests/test_sync_engine.py`) |
| Server-side sync API (`/api/sync/*`) | development/test fixture only | `docs/LAN_PEER_ARCHITECTURE.md`: the server is not a relay, blob store or rendezvous service |
| Web peer transport | `GOOD` at source level | `static/lan-peer.js`, `static/sync.js`, `static/sync-transfer.js`; `tests/sync_transfer.test.mjs`, `tests/lan_peer.test.mjs` |
| Native peer transport | `GOOD` at source level | `native-offline/src-tauri/src/lan_peer.rs`, `lan_host.rs`, `sync_peer.rs`; `tests/native_sync.test.mjs`, `tests/test_native_sync_command.py` |
| Two real peers transferring a save on one LAN with internet off | `UNVERIFIED` | No two-peer run recorded for the current source; see `docs/checkpoints/direct-lan-controller.md` |
| Gameplay impact of a transfer in flight | `UNVERIFIED` | No measurement |

## Code map

- `sync_engine.py` — pure decision engine: transport choice, conflict decisions,
  `last_synced_hash` loop prevention.
- `static/lan-peer.js` — browser peer: discovery, direct TCP session, transfer.
- `static/sync.js`, `static/sync-transfer.js` — UI and transfer orchestration.
- `native-offline/src-tauri/src/lan_peer.rs`, `lan_host.rs`, `sync_peer.rs` —
  native peer host and client.
- `docs/LAN_PEER_ARCHITECTURE.md` — the binding contract (including what the
  server is *not*).

## Invariants

- Two peers on the same LAN talk directly. The server is never a relay, blob
  store or rendezvous service, and the old `/api/sync/*` routes are development
  and test fixtures, not the product path.
- A conflict is never resolved by a silent overwrite: the user chooses, and the
  record keeps local/cloud/both.
- Integrity is checked before delivery; a hash mismatch is a failure, not a retry
  loop.
- Google/Drive sync stays removed.
- A transfer must not corrupt an unrelated save, and must not overwrite a save
  the user chose to keep.

## How to verify

```sh
python3 -m unittest tests.test_sync_engine tests.test_sync_api tests.test_native_sync_command
node --test --test-concurrency=1 tests/sync_transfer.test.mjs tests/lan_peer.test.mjs tests/native_sync.test.mjs
```

Source tests prove the engine and the transports compile and behave on fixtures.
They do not prove a transfer. Acceptance needs two real peers, internet
disconnected, discovery → pairing → transfer → hash match → conflict choice →
reconnect, with the exact peers and code revisions recorded.

## Open work

1. Run and record the two-peer transfer for the current source; fill the
   `UNVERIFIED` rows in the checkpoint with exact peer identities and revisions.
2. Measure gameplay while a transfer runs (frame pacing), since a transfer that
   stutters the game is a product defect.
3. Expose the flow in the native UI where the entry point does not yet exist;
   coordinate with [ui-shell](ui-shell.md) so the entry is discoverable.

## Related

- [phone-controller](phone-controller.md), [saves](saves.md),
  [ui-shell](ui-shell.md)
- `docs/LAN_PEER_ARCHITECTURE.md`,
  `docs/checkpoints/direct-lan-controller.md`
