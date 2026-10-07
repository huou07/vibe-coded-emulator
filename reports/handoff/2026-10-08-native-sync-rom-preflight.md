# Native Sync ROM preflight handoff — 2026-10-08

## Exact state

- Repository: `/Users/meomeo/Documents/edit an3tocom apps&web`
- Branch: `feature/phone-controller-cross-platform`
- Starting HEAD: `a1a6e3c0a1a003bdfa79d8f177bce1082af82a20`
- Product fix commit: `d06c7c4` (`fix(sync): preflight peers before ROM hashing`)
- Sync handoff commit: `cd4246b` (`docs: record native save sync preflight handoff`)
- Public snapshot cache fix: `eba34c9` (`fix(release): exclude bytecode caches from public snapshots`)
- Packaged app version: `3.2.1` in `package.json`, `package-lock.json`, and both Tauri configs.
- Existing unrelated untracked reports, plans, screenshots, and Playwright files remain untouched.

## Completed

Native `syncGame()` now verifies that a compatible trusted peer is connected
before invoking the ROM SHA-256 command. The Sync save button reports the
connection check, ROM identity read, and save transfer stages. The hash still
runs on Tauri's blocking worker. Two Node tests cover the no-peer fast failure
and the connected-peer progress ordering. Regression guard RG-129 records the
contract and its live acceptance requirement.

## Verification

- `node --test tests/native_sync.test.mjs tests/sync_transfer.test.mjs` — 21/21 pass.
- `node --check native-offline/web/native-sync.js` and `native-app.js` — pass.
- `npm run check` in `native-offline/` — pass.
- `python3 -m unittest tests.test_offline_consolidation` — 10 pass.
- `git diff --check` — pass.
- No app package was built. No Android device/emulator or staging runtime was
  available, so packaged save-sync behavior is **UNVERIFIED**.
- The first public snapshot check correctly rejected copied Python bytecode
  caches containing a developer path. `tools/build-public-snapshot.sh` now
  excludes `__pycache__`; a fresh candidate has 482 files / 11 MB and
  `tools/publication-check.sh` passes (gitleaks: 0 findings; personal-data and
  infrastructure patterns: clean). The clean candidate's single-commit
  history scan also passes.
- Public `main` is `48fb769e875692cb0f775fa89fa2ca8d6b1f776f`. Comparing the
  sanitized snapshot with that tree reports 335 changed files, about 20,727
  insertions and 45,991 deletions; the histories are unrelated. The publishing
  script's `--adopt-remote` merge makes the snapshot win, so no push was made.
  Reconcile the public base before publication to avoid replacing newer public
  content.

## Exact next actions

1. On an available Android device or packaged target, verify that Sync save
   with no connected peer rejects promptly without reading a large ROM.
2. Connect a compatible peer and verify the status messages, save transfer,
   and persisted save result. Record artifact version/hash and runtime details.
3. Continue the existing product plan from this feature branch. Do not merge
   the unrelated public snapshot or the separate `3.3.3` release lineage into
   this checkout without resolving the history decision.
4. Before changing shared player/host code, repeat the required CodeGraph and
   regression-ledger checks. Do not access production.
5. Keep this feature branch as the local continuation source. Reconcile its
   relationship to public `main` before attempting a public snapshot push; do
   not let the snapshot merge replace the newer public tree by default.

## Pending shared-app data question

A prior turn asked whether to rerun an isolated macOS package test and whether
to keep or remove a fixture already imported into shared app storage. No answer
has arrived. Do not relaunch the shared app or alter its data until that choice
is answered; other repository work can continue independently.
