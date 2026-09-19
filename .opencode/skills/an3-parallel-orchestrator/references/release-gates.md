# Change-impact matrix and release/staging gates

Map changed subsystem → required tests. This is policy, not a fixed command list;
reuse the commands in the existing `an3-build`, `an3-player-regression`,
`an3-control-plane`, `an3-staging-deploy` and `public-release-security` skills
rather than duplicating them here.

## Change-impact matrix

| Changed subsystem | Required tests (at minimum) |
| --- | --- |
| Shared Tauri commands (`native-offline/src-tauri/src/*.rs`) | `cargo check` per target; command uniqueness + ACL/`build.rs` match (`validate_candidate.py tauri-commands`); `tests.test_offline_consolidation` |
| Frontend shared player surface (`static/player*.js`, `nds-touch.js`, `site.css`, `renderer-worker.js`) | full `an3-player-regression` guards before and after; Node behaviour suites; browser/Playwright interaction |
| Renderer / native runtime | native regression guards; affected emulator path; platform GPU/runtime check |
| Web server (`app.py`, `netcode.py`, `sync_engine.py`) | focused unittest modules + `unittest discover -s tests`; live HTTP/Playwright for changed surfaces |
| Release metadata (`catalog.json`, version files, sidecars) | `tools/verify-release-catalog.py`; `validate_candidate.py versions manifest-hash`; artifact/version/hash match |
| Docs only | spot-check against diffs; no rebuild |
| Distribution/automation | `validate_candidate.py distribution-strings`; confirm test-only bridges/tokens absent from shipped bytes |

## Staging ownership and sequence

Only Integration deploys staging, and only after the integrated HEAD passes its
mandatory tests. Never production unless the user explicitly authorizes it in the
current request.

```
integrated HEAD
→ mandatory tests (matrix above)
→ build affected artifacts
→ validate versions + hashes (verify-release-catalog.py)
→ deploy (an3-staging-deploy)
→ verify health + that each installer URL returns 200 with the expected size
→ retrieve the deployed artifact and independently verify bytes/runtime where applicable
```

A successful deploy command is not verification. If deployed bytes change after a
successful check, staging verification must run again. Keep the printed rollback
target. Record asset version, active release, browser/runtime, ROM identity, and
console errors for any runtime check.

## Release-completion status

Never collapse the run to "complete". Track dimensions separately and label partial
work. Mandatory gaps block `COMPLETE`; optional unavailable-hardware checks may stay
explicit without blocking a scoped release.
