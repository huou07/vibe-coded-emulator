# Storage preflight continuation handoff — 2026-10-09

## Workspace and preservation

- Active workspace: `/Users/meomeo/Documents/edit an3tocom apps&web`
- Branch/HEAD at continuation start: `feature/phone-controller-cross-platform` / `ad71997613d0fd143266355be7b68f238f5e587f`
- The workspace had extensive pre-existing modified and untracked files. They were preserved; no cleanup, reset, staging, commit, package build, or publish was performed.
- The sibling `an3-333-runtime-unification` checkout remains outside this change. Its newer source/version state must not be silently copied into this older active branch.

## Change completed

Added a non-destructive disk-space preflight before local macOS, Windows, Linux DEB/Flatpak, and Android package builds. Defaults warn below 40 GiB and stop below a 25 GiB reserve. The check only reads available space and never deletes files.

- POSIX helper: `tools/disk-preflight.sh`
- Windows helper: `tools/disk-preflight.ps1`
- Wired through `native-offline/package.json`, the Android and Linux staging scripts, and the Windows staging script.
- Added pass/warning/stop/invalid-threshold coverage and entrypoint-order assertions in `tests/test_disk_preflight.py`.
- Added the workflow guard to `docs/REGRESSION_GUARDS.md`.

## Verification

- `python3 -m unittest tests.test_disk_preflight tests.test_native_staging_contract tests.test_release_train_versions`: **15 passed**.
- Prior active-workspace baseline for native runtime/input/renderer/menu/staging guards: **75 passed** before these workflow edits.
- `bash -n` on the POSIX preflight and modified shell entrypoints: passed.
- `git diff --check`: passed.
- `native-offline/package.json` JSON parse: passed.
- Current host reports 143 GiB available; no build or emulator process was active at the recorded snapshot.
- PowerShell is unavailable on this Mac. Windows helper execution is therefore **UNVERIFIED** and must be exercised on the authorized Windows builder before claiming Windows runtime validation.

## Related runtime evidence and limits

The installed VCE 3.3.1 app was closed by the user, freeing loopback port 38471. The existing durable candidate handoff records that the VCE 3.3.12 candidate test-only flow passed import of the lawful fixture, native session stayed running, and the presented-frame counter advanced. Candidate pixel correctness, input, audio, and save behavior remain unverified. Do not repeat the candidate run unless needed; use that handoff evidence and its exact artifact identity.

The active branch is older than the public 3.3.3 checkpoint and the newer sibling checkout. Do not package or bump this branch until source lineage is reconciled. No public push/release or staging/production deployment was performed.

## Next work

1. Reconcile the authorized source lineage and choose the correct continuation checkout without disturbing dirty work.
2. Run the PowerShell preflight on Windows and retain the existing 25 GiB reserve policy.
3. Continue the requested cross-platform product audit from the current checkpoint, distinguishing static checks from live package/runtime evidence.
4. Keep the disposable Android AVD lifecycle item explicitly **UNVERIFIED** until safely exercised or implemented with evidence.
