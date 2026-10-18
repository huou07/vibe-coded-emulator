# Web player (browser product)

Read when: you are changing browser playback, the Web player UI, ROM delivery,
the EmulatorJS proxy, or any page served by `app.py`.

Skip when: the work is native-only (`docs/features/native-app.md`), packaging
(`docs/features/android.md`), or a server/admin feature with no playback effect.

## Status

| Surface | Status | Evidence |
| --- | --- | --- |
| GBA in the browser | `GOOD` | Browser lane (`tests/web-runtime.test.mjs`) plus the source gate; continuous play is `UNVERIFIED` |
| NDS in the browser (melonDS) | `GOOD` | melonDS core, `EJS_startOnLoaded = true`, touch bridge covered by `tests/test_web_nds_touch_behavior.py` and `tests/web_nds_touch_behavior.test.js` |
| 3DS in the browser | not playable | Owner report 2026-10-18 (requirement, not verification); no browser 3DS evidence exists. Cause and plan: [web-3ds](web-3ds.md) |
| Emulator-loop frame timing | `GOOD` when the gate runs | RG-158: the vendored runtime's `--status-json` reports a measured `frameMs` distribution (p50/p95/p99/max over 600 frames); the lane asserts the tail and the throughput bound |
| Sustained display frame pacing and audio underruns | `UNVERIFIED` | `docs/QUALITY.md` gap 1: the lane runs headless with a null audio backend (`audioMeasured:false`), and the browser side samples `uiFrame*` without a lane asserting them |
| Netplay rooms | staging-only, not a product claim | `docs/ARCHITECTURE.md` scope; do not build a product claim on the staging transport |

## Code map

| Area | File |
| --- | --- |
| HTTP routes, sessions, ROM and ZIP delivery, EmulatorJS proxy | `app.py` |
| Player bootstrap, core contract, core selection | `static/player.js` |
| Runtime sampling, save and autosave plumbing | `static/player-runtime.js` |
| Renderer worker (WebGPU → WebGL2) | `static/renderer-worker.js` |
| Offline/PWA shell and cache | `static/offline.js`, `static/service-worker.js` |
| Shared player UI (also shipped to native) | `static/player-ui.js`, `static/site.css` |

`app.py` is Python standard library only. It stores and serves data; it never
emulates and never proxies gameplay traffic.

## Invariants

- Emulation stays client-side; offline ROMs and saves stay browser-local.
- The EmulatorJS core contract stays `EmulatorJS-core` / `core` / `?EJS_KEYS!`
  with `version` and `ArrayBuffer` data.
- Core selection stays report-first, then browser capability, then binary; the
  cache key `an3-arcade-cores-v1` is independent of shell versions.
- NDS serves the original ZIP where appropriate; Range requests and chunked
  upload keep working.
- The NDS touch bridge and its `geometry-mapped` default (with the `hybrid-root`
  rollback) stay intact.

## How to verify

```sh
bash tools/verify-project.sh
node --test --test-concurrency=1 tests/web_nds_touch_behavior.test.js
AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium node --test tests/web-runtime.test.mjs
```

The browser lane needs its own prerequisites; read the evidence classes in
`docs/UI_TESTING.md` before claiming a rendered result. A skipped lane is
`UNVERIFIED`. Browser evidence never establishes packaged or native acceptance.

## Open work

1. Make 3DS playable in the browser — [web-3ds](web-3ds.md). This is the current
   product gap on this surface.
2. UI/UX of the shared shell — [ui-shell](ui-shell.md).

## Related

- [core-selection](core-selection.md), [nds-touch](nds-touch.md),
  [saves](saves.md), [ui-shell](ui-shell.md)
- `docs/UI_TESTING.md` (evidence classes, canonical browser lane)
- `docs/REGRESSION_GUARDS.md` (guard IDs cited from tests)
