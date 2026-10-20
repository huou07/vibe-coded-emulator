# Switch (Eden) companion

Read when: you add, extend or test Switch/Eden support in the installed app — the
companion process, its lifecycle, the library surface, or per-platform packaging.

Skip when: the task is browser playback (the web product never carries Eden) or
a GBA/NDS/3DS core change.

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| Eden bridge as a separate macOS companion process | `GOOD` at source level | `native/eden-bridge/`; `native-offline/src-tauri/src/switch_companion.rs` |
| Discovery, launch, focus, stop, button and analog input, audio diagnostics, graceful stop | `GOOD` at source level | `switch_companion.rs`; `tests/test_switch_lifecycle.py`, `tests/test_switch_failure_paths.py` |
| Packaged macOS UI journey | `GOOD` for the recorded macOS build | `tests/test_switch_ui_e2e.py` |
| Game-level save round trip, captured audible output, physical gamepad | `UNVERIFIED` | The recorded service test explicitly does not claim a game save |
| Companion on Linux, Windows, Android | not built | No companion artifact for those hosts; the packaged Linux DEB reports `available:false` with its reason. The platform matrix is decided in `docs/checkpoints/eden-native-integration.md` |
| Switch library/UI surface in the app | `GOOD` for the honesty rule | on a companion-less host the Devices row stays hidden, the capability declaration omits `switch`, and Game Settings offers no Switch tab; a companion host still needs its packaged journey |
| Web | out of scope | Owner decision 2026-10-18: the web product does not get Eden |

| Entry point in the installed app | `GOOD` for Linux packaged + browser lane, `UNVERIFIED` on macOS/Windows | one **Optional features** switch in Settings reveals the `Devices` destination on every platform; RG-162, `tests/native_experimental_gate.test.mjs`. The 3.6.10 installers predate the surfaces themselves (built from the core-only candidate line), which is the reported "switch does nothing" defect |
No maintained libretro Switch core exists. The companion is the architecture: a
separately launched Eden process, never a core embedded in the player, and never
a firmware/key bundle.

## Code map

- `native/eden-bridge/` — bridge sources, tests, integration notes.
- `native-offline/src-tauri/src/switch_companion.rs` — companion discovery,
  lifecycle, input and status.
- `native-offline/vendor/switch/macos-arm64/` — pinned macOS companion resource.
- `native-offline/src-tauri/src/lib.rs` — the IPC commands the UI calls.
- `native-offline/web/native-bootstrap.js` — native UI wiring.
- `docs/licensing/eden-integration-feasibility.md` — why it is a separate
  process (GPL-3.0-or-later, no embedding).
- `docs/checkpoints/eden-native-integration.md` — phase record and remaining
  acceptance.

## Invariants

- Eden stays a separate process. Do not embed it, link it into the player, or add
  a `NativeSystem::Switch` core variant.
- No firmware, keys, ROMs or homebrew binaries are bundled; lawful user files
  only.
- Third-party notices and licence texts stay intact; the GPL obligations of the
  companion are not diluted by the frontend.
- The web product does not serve, proxy or bundle Eden.
- A companion that cannot start fails structurally with a user-visible reason; it
  does not leave an orphan process behind.

## What "add Eden to VCE" means

1. Platform decision first: which hosts ship a companion artifact. macOS has one.
   Linux, Windows and Android need their own companion build and their own
   evidence; a host without an artifact must not advertise Switch.
2. Library surface: choose Switch in the library, with the companion's state
   (not installed / installed / running / stopped / failed) visible before the
   user commits.
3. Lifecycle: launch, focus, stop, quit on app exit, no orphan processes, save
   store under app-private storage.
4. Acceptance: a lawful homebrew fixture launches, renders, accepts input,
   saves, reloads and exits on the named host; recorded with exact revisions.

## How to verify

```sh
python3 -m unittest tests.test_switch_lifecycle tests.test_switch_failure_paths
python3 -m unittest tests.test_switch_saves tests.test_switch_audio
```

Source tests are checks, not acceptance. The packaged journey is the evidence,
and it is `UNVERIFIED` outside the recorded macOS run. The review checkpoint
lists what the packaged run must cover.

## Open work

1. Build a companion for each additional host before claiming it; the matrix is
   recorded in `docs/checkpoints/eden-native-integration.md` and a
   companion-less host is verified not to advertise Switch.
2. Close the packaged acceptance rows: game save round trip, audible output,
   physical gamepad.
3. Make the Switch entry visible-but-honest: no Switch tile when no companion
   exists (`docs/features/ui-shell.md`).

## Related

- [native-app](native-app.md), [ui-shell](ui-shell.md), [android](android.md)
- `docs/checkpoints/eden-native-integration.md`,
  `docs/licensing/eden-integration-feasibility.md`,
  `docs/vibe-coded-switch-companion.md`
