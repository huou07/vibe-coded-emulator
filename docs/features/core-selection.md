# Core selection and the EmulatorJS core contract

Read when: you touch which core runs, the capability report, the EmulatorJS
asset contract, the core cache, or the `data-v2` runtime path.

Skip when: you are adding a native libretro core (that is
[native-app](native-app.md)) or changing only site chrome.

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| Core contract `EmulatorJS-core` / `core` / `?EJS_KEYS!` with `version` + `ArrayBuffer` | `GOOD` | Enforced by the browser lane and the source gate |
| Selection order: report → browser capability → binary | `GOOD` | Source and tests; do not reorder |
| Cache key `an3-arcade-cores-v1` independent of shell versions | `GOOD` | Source gate |
| `data-v2` path for the repaired Azahar runtime | `GOOD` for the asset set | 22/22 locked assets match `native-offline/shared/web-runtime-lock.json` |
| 3DS selecting a core that actually starts in the browser | `UNVERIFIED` | See [web-3ds](web-3ds.md) |

## Code map

- `static/player.js` — core map (`3ds` maps to `azahar`), threaded-core list,
  WebGL2 requirement, `data-v2` path for 3DS, capability report handoff.
- `static/renderer-worker.js` — renderer selection behind the core.
- `native-offline/shared/web-runtime-lock.json` — the frozen asset lock the
  build verifies against.
- `native-offline/scripts/prepare-web.mjs` — resolves the vendored runtime before
  the network and verifies the lock.

## Invariants

- The contract shape and its `version`/`ArrayBuffer` payload do not change.
- Selection order stays report-first, then browser capability, then binary.
  A reported capability is not a binary, and a binary is not a capability.
- The lock file decides; a drifted vendored file is rejected exactly like a
  downloaded one.
- The cache key `an3-arcade-cores-v1` persists independently of the PWA shell
  version, so an offline user does not re-download cores on a shell update.
- `requiresWebgl2` (Azahar) and `defaultWebGL2` are both read; reading only the
  latter produced a non-existent `azahar-thread-legacy` binary in the past.

## How to verify

```sh
bash tools/verify-project.sh
npm --prefix native-offline run prepare-web   # only when the runtime lock is in scope
```

The `prepare-web` run verifies every locked asset; a mismatch is a failure, not a
warning. Browser-side acceptance needs the browser lane — see
`docs/UI_TESTING.md`.

## Open work

- The 3DS branch of selection is wired but unproven in a browser; the failing
  stage is the subject of [web-3ds](web-3ds.md).

## Related

- [web-player](web-player.md), [web-3ds](web-3ds.md)
- `docs/UI_TESTING.md`
