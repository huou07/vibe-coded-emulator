# Finish VCE

Owner authority for this work is recorded in [../AGENT-AUTHORITY.md](../AGENT-AUTHORITY.md):
you may commit, push to `origin`, open pull requests, publish a stable release
and update the VCE web production service **after** the project's own gates pass.
You do not need to ask for those again, and you must not ask for host privileges
that file does not grant.

## Objective

Complete VCE's remaining end-user journeys and keep the web, desktop and native
builds consistent. Work from `docs/checkpoints/` and the active roadmap; do not
invent a second tracker.

## Start from the repository, not from this file

1. `AGENTS.md`, then `docs/README.md`, `docs/REGRESSION_GUARDS.md`,
   `docs/UI_TESTING.md` and the relevant active checkpoint.
2. Establish the real state before editing: branch, HEAD, dirty files, and the
   production service state. Preserve unrelated work; never discard it.
3. Create a persisted goal for this objective and continue across rounds until
   the journeys are accepted or explicitly reported as blocked. Do not stop
   after planning, after implementing, or after one green run.

## Lanes and their true state on this host

| Lane | Command | State |
|---|---|---|
| Source gate | `bash tools/verify-project.sh` | 479 tests, 20 skipped — see the known failure below |
| Web runtime (real browser) | `AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium XDG_CACHE_HOME=<tmp> node --test tests/web-runtime.test.mjs` | PASS (1/1, ~14s) |
| an3ctl browser self-test | `AN3_PLAYWRIGHT_BROWSER=chromium node --test tests/an3ctl.test.mjs` | **FAIL** — see below |
| Native Linux runtime | `native-offline/vendor/runtime/linux-x86_64/an3-offline-native --help` | **BUILT 2026-10-17** — vendored, integrity-verified, links clean, and supports `--headless --frames N --capture out.png --status-json` |
| Native desktop shell | `cd native-offline && npm ci && npm run build:deb` | needs `npm ci`; `@tauri-apps/cli` is not installed and the rest of the toolchain is present |
| Native Linux journey | `native-offline/vendor/runtime/linux-x86_64/an3-offline-native --rom <fixture> --system gba --headless --frames N --capture out.png --status-json` | **runnable now** — registry a real bounded journey and record it in the native checkpoint |
| Android / macOS / Windows | no SDK, emulator or toolchain on this host | hosted CI only |

Only Chromium exists on this host, so select it with
`AN3_PLAYWRIGHT_BROWSER=chromium`; the verified default stays Chrome.

### Known failure to resolve first

`tests/an3ctl.test.mjs` → `web: launch, inspect, act, read back, and shut down
cleanly` fails at line 89 (`tree.ok !== true`). The identical manual sequence
succeeds with the same parameters (start on 8097, `app state`, `ui tree --path
/games --limit 40`), so the defect is in the test or in the shared `an3-web`
session/isolation, not in the page. Fix the cause; do not weaken the assertion.
While investigating, `tools/check-docs-refs.py` and `tests.test_licensing` are
green, and `deploy/shadow` is owner-only — `git status` printing
`Permission denied` for it is not a change.

## Constraints

- Resource-bounded work: serialise heavy jobs, respect `MemAvailable` and disk
  headroom, bound timeouts, and clean up whole process groups.
- Never substitute browser evidence for native evidence, and never claim a
  platform you did not run.
- Preserve the invariants: browser-local offline ROM/saves, the EmulatorJS core
  contract and cache key, layering/input precedence, ten quick slots, autosave,
  Exit Game, and `static/` serving both web and native UI.
- The Rust shadow gateway cutover stays permanently blocked.
- The publication path is `tools/build-public-snapshot.sh` plus
  `tools/publication-check.sh` (gitleaks). It fails closed; never bypass it.

## Sequence

1. Resolve the known failure above, then re-run the full source gate.
2. Take the next unverified journey, reproduce it with synthetic fixtures using
   the real commands, and fix the first gap you actually observe.
3. Re-run the affected lanes and the full gate after each coherent change.
4. Commit, push, open a pull request, let exact-SHA CI decide, repair genuine
   failures, and merge through the normal workflow.
5. Release and update the production service only when the gates pass, using the
   documented release train — never an improvised deploy.
6. Continue to the next journey and report what remains unverified.
