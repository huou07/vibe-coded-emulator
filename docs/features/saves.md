# Saves: quick slots, autosave, Exit Game

Read when: you change save states, the 10 quick slots, autosave modes, save
storage, Exit Game, or the save entry points of the player UI.

Skip when: the work is sync between devices ([lan-sync](lan-sync.md)) or a
purely visual change with no save path.

## Status

| Surface | Status | Evidence |
| --- | --- | --- |
| Web: slots 1–10, autosave modes, Exit Game flush | `GOOD` | Source tests; storage behaviour covered by `tests/player_save_storage.test.js` |
| Web autosave key and legacy migration | `GOOD` | `vibe-autosave-v1` in source and tests |
| Packaged Linux quick save/load (slot 1) | `GOOD` | 528448-byte state file written by the packaged player; byte-identical re-save round trip |
| Native autosave modes (shared model, Android pref, macOS defaults) | `GOOD` at source level | Generated into `NativePlayerUi.kt`, `player_ui.h`; `native-runtime/core/auto_save_mode.h` |
| Save behaviour for the new surfaces (Switch/Eden, LAN transfer targets) | `UNVERIFIED` | No packaged or two-device run recorded |

## Code map

| Area | File |
| --- | --- |
| Web quick save manager, autosave record and modes | `static/player-runtime.js` |
| Web player UI entry points (toolbar Save, Exit Game) | `static/player-ui.js` |
| Shared native autosave model | `native-offline/shared/player-ui.json`, `native-runtime/core/auto_save_mode.h` |
| Generated native UI models | `native-offline/scripts/generate-player-ui.mjs` → `NativePlayerUi.kt`, `player_ui.h` |
| Packaged state files | app-private storage: `<rom_id>.slotN.state`, `<rom_id>.autosave.state` |

## Invariants

- Ten quick slots, per-core settings, autosave and Exit Game keep working.
- Autosave never overwrites an unrelated save; the exit flush runs on Exit Game
  and on `pagehide`.
- The five modes (off / exit / 30 s / 10 s / 5 s) stay identical across surfaces;
  the persisted token form is `off|exit|<interval>`.
- A save round trip is judged by byte identity only when the serializer is
  deterministic — pause before comparing.
- User saves are never committed, published or placed in evidence.

## How to verify

```sh
node --test --test-concurrency=1 tests/player_save_storage.test.js
python3 -m unittest tests.test_phase_a_branding_autosave_exit
bash tools/verify-project.sh
```

For the packaged native path, the checkpoint's procedure is authoritative: save,
advance, load, re-save, compare bytes with the emulator paused.

## Open work

1. Keep the packaged Exit Game behaviour honest: the player currently destroys
   its windows but the process lingers — see [native-app](native-app.md). A
   teardown fix must not drop the exit autosave flush.
2. Re-establish save evidence for any surface that gains a new feature
   (Switch/Eden, LAN transfer targets) before claiming it.

## Related

- [native-app](native-app.md), [web-player](web-player.md), [lan-sync](lan-sync.md)
- `docs/checkpoints/native-linux-journey.md`
- `docs/REGRESSION_GUARDS.md` (save and autosave guards)
