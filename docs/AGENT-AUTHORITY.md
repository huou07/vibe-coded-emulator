# Agent authority on this host

Date: 2026-10-17. Source: the owner's direct instruction in the AEH session of
that date. This file exists so a later agent does not have to ask again. It
grants no host privilege and does not override the invariants in `AGENTS.md`,
`docs/REGRESSION_GUARDS.md` or the publication gate.

## Granted without further approval

- Cohesive commits on the working branch, pushes to `origin`
  (`huou07/vibe-coded-emulator`), and pull requests.
- Publishing a stable release and updating the VCE web production service
  (`an3-arcade.service`, the public game library) **after** the project's own
  gates pass: `bash tools/verify-project.sh`, the sanitizing publication gate
  (`tools/build-public-snapshot.sh` + `tools/publication-check.sh`), and the
  licence/third-party notices requirements. Production changes stay inside that
  documented procedure; do not improvise a deploy path.
- Running the local lanes on this host: `bash tools/verify-project.sh`, the web
  runtime lane, and the native static/source checks.
- Using the owner's Playwright CLI and browser cache for real browser evidence:
  `~/.local/share/playwright-cli` and `~/.cache/ms-playwright`. On this host only
  Chromium exists, so select it with `AN3_PLAYWRIGHT_BROWSER=chromium`. Test
  against the project's own local server and synthetic data — never against real
  user data, real accounts or production endpoints.
- Cleaning up leftovers from the 2026-10 migration: stale paths, orphaned
  untracked files and superseded tool references may be committed or removed
  when the current source supports it; record what changed and why.

## Not granted

- Host `sudo`, host account/group changes or host ACL changes.
- Reading owner credentials, personal media or private NAS content. Only the
  exact GitHub CLI files the owner approved are readable, and only for
  publishing this repository.
- Force-pushing `main`, rewriting tags, or discarding unrelated work.
- Bundling ROMs, firmware, keys or user saves; reviving removed Google sync;
  claiming server-relayed multiplayer; or substituting browser evidence for
  native evidence.

## Verified facts about this host (do not re-derive)

| Fact | Value |
|---|---|
| Source gate | `bash tools/verify-project.sh` passes: 479 tests, 20 skipped, 5/5 sections |
| Web runtime lane | runnable directly: `AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium XDG_CACHE_HOME=<tmp> node --test tests/web-runtime.test.mjs` — 1/1 pass in ~14s |
| Rust for native | CI pins 1.88.0; this host has 1.98.0. `~/.cargo` is **not writable** by the worker, so new crate downloads need a project-local `CARGO_HOME` |
| Native Linux | **unblocked 2026-10-17**: the gameplay runtime is now vendored at `native-offline/vendor/runtime/linux-x86_64/` (ELF `an3-offline-native`, SHA-256 `94a5e701bf97a5363c27736221ca48f7e7c6a9a6c13e9275cf7503195b076e6c`, staged by `bundle-linux-runtime.mjs` and integrity-verified). It builds with one compiler command — see `native-offline/scripts/build-linux-staging.sh` — and it offers real native evidence without a GUI: `--rom PATH --system gba --headless --frames N --capture out.png --status-json`. The Tauri shell still needs `npm ci` in `native-offline` (`@tauri-apps/cli`); the registry is reachable. The `vce-linux` entry in the retired capabilities file is archival |
| Android | **unavailable**: no SDK, NDK, `adb`, AVD or emulator on this host, and this UID is not in the `kvm` group. Do not claim Android evidence from here |
| macOS / Windows | not buildable on this host; their evidence comes from hosted CI and the publication snapshot workflow |
| Unreadable paths | `deploy/shadow/` is owner-only, so `git status` prints `Permission denied` for it. Those are not changes; the Hub counts status from stdout only |
| GitHub | `gh` is authenticated as `huou07` through the owner-approved file exception; `git push` needs `-u` on this branch because no upstream is configured |

## Evidence discipline

A local pass proves source behaviour on this host for this tree. It is not
packaged acceptance, and it does not replace the hosted run for the exact SHA.
Keep each claim in its class and disclose what was not verified — in particular,
never present a browser journey as native application evidence.
