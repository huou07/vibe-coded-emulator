# NDS playback and the touch bridge

Read when: you touch NDS playback, the melonDS startup contract, the touch
surface, the virtual pad, or input precedence over the canvas.

Skip when: the change is GBA/3DS-only with no shared input or layering effect.

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| melonDS as the NDS core, `EJS_startOnLoaded = true` | `GOOD` | Source and browser tests; no start-button gate |
| NDS touch bridge and `geometry-mapped` default | `GOOD` | `tests/test_web_nds_touch_behavior.py`, `tests/web_nds_touch_behavior.test.js` |
| `hybrid-root` rollback variant | `GOOD` | Selectable variant kept for regression |
| Input precedence: menu → virtual controls → touch surface → keyboard | `GOOD` at source level | `docs/player-layering.md`; layered UI tested in source |
| Real-device touch feel and latency | `UNVERIFIED` | No device run recorded on this host |

## Code map

- `static/nds-touch.js` — touch bridging between the canvas and the core.
- `static/player-ui.js` — virtual pad, touch toggle, move/drag/Done flow.
- `static/site.css` — layering and the control geometry.
- `docs/player-layering.md` — the binding interaction order.
- `docs/ui-page-contract.md` — DOM IDs the pages and tests depend on.

## Invariants

- NDS uses melonDS. No DeSmuME, no manual-start workaround, no start-button gate.
- The touch bridge, the custom virtual pad and the `geometry-mapped` default stay
  intact; `hybrid-root` remains as the rollback.
- Menu, virtual controls, the touch surface and the physical keyboard keep their
  precedence order; a new overlay is inserted, never reordered.
- The screen layout follows [screen-layout](screen-layout.md); do not hardcode
  geometry that the layout schema owns.

## How to verify

```sh
python3 -m unittest tests.test_web_nds_touch_behavior
node --test --test-concurrency=1 tests/web_nds_touch_behavior.test.js
bash tools/verify-project.sh
```

Before and after a canvas/input/layering change, run the matching guards listed
in `docs/REGRESSION_GUARDS.md` and honour `docs/player-layering.md`.

## Open work

- Device-level touch feel remains `UNVERIFIED`. When an Android device or the
  dedicated AVD is available ([android](android.md)), record a real touch run
  rather than a DOM-only assertion.

## Related

- [web-player](web-player.md), [screen-layout](screen-layout.md),
  [saves](saves.md)
- `docs/player-layering.md`, `docs/ui-page-contract.md`,
  `docs/REGRESSION_GUARDS.md`
