# Native app: Tauri shell, library, player process

Read when: you work on the installed desktop app — the Tauri shell, the library
and import flow, the player child process, Exit Game, core vendoring, or the
`an3ctl` control plane.

Skip when: the task is Android-specific ([android](android.md)), browser-only
([web-player](web-player.md)), or Switch/Eden ([switch-eden](switch-eden.md)).

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| Linux DEB builds from a clean tree | `GOOD` | Built from a clean HEAD; artifact identity recorded in the checkpoint |
| Packaged shell starts and renders the library | `GOOD` | Captured shell window under Xvfb with the packaged binary |
| Library → import → player launch journey | `GOOD` | Automation E2E build of the same shell (documented test-only bridge) |
| Quick save / quick load slot 1 | `GOOD` | Byte-identical save→advance→load→re-save round trip |
| Exit Game (`Esc`) | `BROKEN` | Windows are destroyed and the loop stops, but the process lingers (≈112 MB, 0 CPU) until the next launch |
| NDS and 3DS packaged journeys | `UNVERIFIED` | Only a GBA fixture was exercised |
| Visual and audio review of gameplay | `UNVERIFIED` | The GL window is not capturable under Xvfb here; no audio device |
| Vendored Linux player integrity | `GOOD` | Manifest and pinned SHA-256 verified by the build |
| `an3ctl` deterministic control plane | `GOOD` | Real runs: status, baseline, frame diff, state round trip, input sequence |

## Code map

| Area | Where |
| --- | --- |
| Tauri host, commands, process lifecycle | `native-offline/src-tauri/src/` |
| Shell UI for the installed app | `native-offline/web/` |
| Portable libretro player (C++) | `native-offline/native-runtime/` |
| Pinned player and cores | `native-offline/vendor/runtime/linux-x86_64/` |
| Build and staging | `native-offline/scripts/build-linux-staging.sh` |
| Shared player UI copied into the bundle | `static/` through `native-offline/scripts/prepare-web.mjs` |
| Deterministic control plane | `tools/an3ctl/`, `tests/an3ctl.test.mjs` |

## Invariants

- The player keeps the interaction contract: menu → virtual controls → touch
  surface → physical keyboard.
- The shell never emulates; it owns process lifecycle and data, and the player
  owns emulation.
- A player process must not outlive its session. Exit Game means the child is
  gone, not merely idle.
- A `static/` edit is a native UI change too (the build copies it); the Android
  mirror is a separate copy ([android](android.md)).
- Vendoring is identity-based: a new player binary or core is a new recorded
  SHA-256, never an in-place overwrite of an unrecorded build.

## How to verify

```sh
bash tools/verify-project.sh
node --test --test-concurrency=1 tests/an3ctl.test.mjs
CARGO_HOME=$PWD/work/cargo-home bash native-offline/scripts/build-linux-staging.sh deb
```

The build is the long pole; run it serially, one compilation worker, with a
bounded timeout and cleanup. Source-tree runtime evidence is never packaged
acceptance.

## Open work

1. Fix the Exit Game teardown so the child process exits, then re-vendor the
   pinned Linux player with its recorded SHA-256 as its own reviewed change.
2. Record a real visual/audio review — the captured shell window and the player
   surface are still `UNVERIFIED` by a human or an image tool.
3. Extend the deterministic journey to NDS and 3DS with lawful fixtures; do not
   generalise the GBA result.

## Related

- `docs/checkpoints/native-linux-journey.md` (the only native tracker)
- [android](android.md), [switch-eden](switch-eden.md), [ui-shell](ui-shell.md),
  [saves](saves.md), [screen-layout](screen-layout.md)
- `docs/agent-control-plane.md`, `docs/native-offline.md`
