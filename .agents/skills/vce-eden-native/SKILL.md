---
name: vce-eden-native
description: Use when integrating or extending Switch/Eden support in the installed VCE app — companion discovery, launch, focus, input, save, stop, the library surface, per-platform companion builds, or packaged Switch acceptance. Triggers on "add Eden", "Switch core", "Switch companion", "NX homebrew", "Eden bridge". Do not use for the browser (Eden is never carried on the Web), for GBA/NDS/3DS core work, or for a frontend-only style change.
---

# Eden / Switch in the native app

Eden is a **separately launched process**, not a libretro core. Everything below
follows from that: the frontend owns discovery, lifecycle, input forwarding and
honest status; Eden owns emulation.

## Preconditions

- Read `docs/features/switch-eden.md`,
  `docs/checkpoints/eden-native-integration.md` and
  `docs/licensing/eden-integration-feasibility.md`.
- Confirm the host you are working on actually has a companion artifact. Today
  only the macOS resource is pinned; Linux, Windows and Android have no companion
  build, so any claim for them is `UNVERIFIED` before you start.
- A lawful homebrew fixture (`AN3_SWITCH_HOMEBREW` for the source tests) is
  required for runtime evidence. No firmware, keys, ROMs or homebrew binaries are
  committed.
- Do not add `NativeSystem::Switch` or embed Eden in the player. The separate
  process is what keeps the GPL boundary and the licence notices intact.

## Procedure

1. Decide the platform row explicitly: shipped / buildable / not buildable, with
   the evidence for each. A host without a companion must not advertise Switch in
   the UI.
2. Build or link the companion for the host (`native/eden-bridge/`), keeping it a
   separate process with its own resource bundle and third-party notices.
3. Use the existing shell path in `native-offline/src-tauri/src/switch_companion.rs`:
   detect → launch → focus → input → stop → quit with the app. Reuse it; do not
   add a second lifecycle.
4. Library surface: show the companion state (not installed / installed / running
   / stopped / failed) before the user commits. Failure must be structural and
   visible, never a hang or an orphan process.
5. Save data goes to app-private storage; confirm it survives a restart without
   overwriting unrelated saves.
6. Evidence: source tests, then one packaged journey — launch, render, input,
   save, reload, exit — recorded with source SHA, artifact hash and host.

## Guard set

```sh
python3 -m unittest tests.test_switch_lifecycle tests.test_switch_failure_paths
python3 -m unittest tests.test_switch_saves tests.test_switch_audio
```

These are source checks. `tests/test_switch_ui_e2e.py` is the packaged macOS
journey; its skips elsewhere are `UNVERIFIED`, not passes.

## Rules

- Never claim Switch on the Web, on a host without a companion, or while the
  game-save/audio/gamepad rows are `UNVERIFIED`.
- Keep the frontend's GPL-3.0-or-later notices and Eden's licence texts intact.
- Do not let a failed companion leave a process behind; verify and reap.
- Update the checkpoint with the platform matrix, not with optimism.

## Stop and report

Report the host, the artifact identity, the journey steps observed, the source
tests run, the rows that remain `UNVERIFIED`, and the next discriminating action.
