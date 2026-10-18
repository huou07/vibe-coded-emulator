---
name: vce-lan-peer
description: Use when working on LAN Sync (save transfer between two devices) or Phone Controller (a phone as a direct LAN controller) end to end — peer discovery, pairing, transport, integrity, conflict choice, reconnect, release-all, or the two-peer evidence run. Triggers on "LAN sync", "send my save to the other device", "phone as controller", "pairing code", "peer transfer", "release-all". Do not use for server-only API work, for cloud/Drive sync (removed), or for gameplay performance measurement.
---

# LAN peer features: LAN Sync and Phone Controller

Both features are **direct peer-to-peer on one LAN**. The server is not a relay,
blob store or rendezvous service; the old `/api/sync/*` and `/api/controller/*`
routes are development and test fixtures. Two real peers are the only acceptance
that counts.

## Preconditions

- Read `docs/features/lan-sync.md` or `docs/features/phone-controller.md`, then
  `docs/LAN_PEER_ARCHITECTURE.md` (binding) and the milestone record in
  `docs/checkpoints/direct-lan-controller.md`.
- Two real peers on the same LAN, internet disconnected, with lawful fixtures.
  An emulator plus a phone, or two desktops. Record both revisions and artifacts.
- A phone-controller change is also an Android-mirror change: `static/` is
  copied into the committed Android assets, gated by `tools/check-native-mirror.py`
  (RG-156).

## Procedure — LAN Sync

1. Establish the peer pair (announce/discover) and record how each peer was
   identified; no server in the path.
2. Transfer one save set. Verify integrity before delivery: size and hash match
   on both sides, no partial file left behind.
3. Exercise conflict choice: a save that differs on both sides is never
   overwritten silently. Keep local / keep remote / keep both, per the engine's
   decisions; `last_synced_hash` prevents a re-sync loop.
4. Repeat the transfer while the game is running and note the gameplay effect.
5. Disconnect mid-transfer and reconnect: the recovery must not corrupt either
   save.
6. Record peers, revisions, hashes, timings and failures.

## Procedure — Phone Controller

1. Pair with a fresh 6-digit code: expiry, one use, rate limit; the token is
   stored as a digest.
2. Play with real input; confirm the phone reaches the same input action model
   as the on-device pad and keyboard, with no second input path.
3. Exercise release-all on host focus loss, explicit stop and transport loss; a
   dropped session must not leave a button held.
4. Reconnect with the token after a dropped session, or pair again.
5. Confirm the phone UI works against the packaged host, not only a development
   server.

## Commands

```sh
python3 -m unittest tests.test_sync_engine tests.test_sync_api tests.test_native_sync_command
python3 -m unittest tests.test_netcode tests.test_phone_controller_hosts
node --test --test-concurrency=1 tests/sync_transfer.test.mjs tests/lan_peer.test.mjs \
  tests/native_sync.test.mjs tests/native_controller_pad.test.mjs \
  tests/controller_utility.test.js
```

Source tests prove the engine and transports on fixtures. They never prove a
peer transfer or a device pairing.

## Rules

- No relay, no rendezvous, no server-mediated transfer as the product path.
- Never resolve a conflict by overwriting; the user chooses.
- Never leave a held button after a disconnect.
- Do not claim two-peer acceptance from loopback tests or a staging server run.
- Google/Drive sync stays removed.

## Stop and report

Report the two peer identities, their revisions, the steps observed, integrity
and conflict results, the reconnect/release results, the gameplay effect, and the
rows that remain `UNVERIFIED`. Update the feature page and the milestone
checkpoint with the dated result.
