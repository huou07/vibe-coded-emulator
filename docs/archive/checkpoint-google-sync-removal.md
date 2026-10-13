# Google Sync removal — 2026-10-13

Branch `feature/phone-controller-cross-platform`. Status: **IMPLEMENTED** and
**TESTED** (server-side). No Google Drive transport exists, so nothing about
Drive gameplay or save transfer could regress.

## What was actually there

Verified before deleting anything:

- `app.py` never imported `google_sync`. The import list has no reference to it.
- The only consumers were `tests/test_google_sync.py`, a filename listed in
  `tests/test_licensing.py`, and the copy list in
  `tools/build-public-snapshot.sh`.
- Drive availability was decided by one line:
  `GOOGLE_DRIVE_ENABLED = bool(os.environ.get("AN3_GOOGLE_CLIENT_ID", ""))`.
- `static/sync.js` already refused the mode in the UI ("Cloud sync is not part of
  LAN features") and disabled the transfer button for it.

So the module was unreachable from the running application, but the env-var gate
meant an operator who set `AN3_GOOGLE_CLIENT_ID` would flip
`driveConfigured` to true and advertise a feature with no implementation behind
it. That is the misleading advertising the product is not allowed to ship.

## What changed

- Deleted `google_sync.py` and `tests/test_google_sync.py`.
- `app.py`: `GOOGLE_DRIVE_ENABLED` is now the constant `False`, with a comment
  recording why.
- `tools/build-public-snapshot.sh` no longer copies the module.
- `tools/publication/.env.example` no longer lists `AN3_GOOGLE_CLIENT_ID` /
  `AN3_GOOGLE_CLIENT_SECRET`.
- Docs and licensing tables updated: `docs/vibe-coded-platform.md` section 6 is
  now a removal note, plus `docs/vibe-coded-roadmap.md`,
  `docs/vibe-coded-continuation-prompt.md`, `docs/licensing/license-audit.md`,
  `docs/licensing/distribution-compliance.md`, `tests/test_licensing.py`.
- `tests/test_sync_api.py`: the old
  `test_drive_mode_is_accepted_when_credentials_are_configured` asserted the
  opposite of the new invariant. Replaced with
  `test_drive_mode_is_permanently_unavailable`, which checks the 409 on both
  Drive modes and `driveConfigured == false` on read-back.

## What was deliberately kept

- `sync_engine.py` and its `DRIVE` / `LAN_DRIVE` mode enum. It is the pure
  decision core, it is fully unit tested, and removing enum members would churn
  the planning surface without changing any user-visible behaviour. The modes
  are simply always rejected at the HTTP boundary now.
- All local-save behaviour, LAN save transfer, LAN save-state transfer and the
  LAN peer registry. None of it touched the Drive transport.

## Environment note

If any deployed environment still exports `AN3_GOOGLE_CLIENT_ID`, it is now
inert. Removing it from the service definition is an owner action recorded in
the final report.
