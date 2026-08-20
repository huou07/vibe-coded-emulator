# AN3 Arcade — P1 Baseline Verification

Date: 2026-08-20 (Asia/Ho_Chi_Minh)
Scope: P1 adaptive performance and player UX only. This record deliberately preserves the inherited P0 work and unrelated dirty changes.

## Workspace state

- Workspace: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade`
- Branch: `ui/production-ux-refresh` (six commits ahead of its upstream at capture time)
- HEAD: `8f82618a46d24974e31f7a7a29956b5b396f8e31` (`Add full system operations handoff`)
- `git diff --check`: PASS.
- Inherited modified files: `app.py`, `static/player.js`, `static/site.css`, `static/site.js`, `tests/test_integration.py`, and `tests/test_regression_invariants.py`.
- Inherited untracked paths: `reports/.DS_Store` and `reports/roadmap/`.
- The current-state handoff identifies `app.py`, `static/site.css`, `static/site.js`, and `tests/test_integration.py` as a separate enrichment-review flow. The uncommitted P0 player patch is also preserved unchanged.

## P0 inherited state

The authoritative P0 record is green: production deployment, staging health, weak-device performance, Android touch, desktop keyboard/remapping, fullscreen, and save-state were owner-validated on 2026-08-20. P1 must retain these invariants:

- EmulatorJS stays client-side, with browser-local/IndexedDB core storage and offline support.
- NDS stays on `melonds` with auto-start and the NDS touch bridge.
- A root NDS gesture starts only on an actual game canvas.
- When the EmulatorJS menu is visible, it receives interaction priority; the custom NDS pad is below it and pointer-inert.
- Desktop defaults to physical keyboard with an optional persisted NDS virtual-pad override; touch-first devices default to the pad.
- Fullscreen targets `player-shell`; GBA/NDS startup and save-state remain intact.

## Fresh local verification

| Check | Result | Notes |
| --- | --- | --- |
| `git status --short --branch` | PASS | Captured above; no reset, clean, or unrelated modification performed. |
| `git rev-parse HEAD` / recent log | PASS | Matches the current-state handoff SHA. |
| `git diff --check` | PASS | No whitespace errors. |
| Python suite | PASS, 12/12 | `python3 -m unittest discover -s tests -v`; rerun with the local loopback permission required by the suite. |
| Python syntax | PASS | `python3 -m py_compile app.py` with a workspace-local bytecode cache. |
| JavaScript syntax | PASS | `static/player.js`, `static/site.js`, `static/offline.js`, and `static/service-worker.js`. |
| Deployment script syntax | PASS | `deploy.sh`, `deploy-stage.sh`, and `deploy/an3-arcade-backup.sh`. |
| P0 source regression assertions | PASS | Included in the 12-test suite. |

## P1.0 decision

`P1_STATUS=READY_FOR_CAPABILITY_AUDIT`

No fresh evidence shows a P0 regression. Physical-device and staging checks are recorded as inherited evidence and will be re-validated against the P1 staging candidate before any production consideration. P1.1 must establish actual EmulatorJS/core capabilities before changing player behavior.
