# Web 3DS — making Nintendo 3DS playable in the browser

Read when: the task is to make 3DS games play in the browser, or to diagnose why
they do not.

Skip when: the work is native 3DS (Azahar libretro core in the installed app) or
Eden/Switch. The browser never carries the Switch companion.

## Status

**Not playable.** Owner report 2026-10-18: the Web build plays GBA and NDS but
cannot play 3DS. No browser 3DS run for the current source exists, so the failing
stage is `UNVERIFIED` — do not write a cause into a document until it is
reproduced.

Two things are already recorded and must be respected:

- RG-078: **no browser-only 3DS playback lock may be reintroduced.** The play
  control is bound only to `androidThreeDsUnavailable`/`html5`, and
  `browserThreeDsUnavailable` must stay absent. A fix that hides 3DS is not a fix.
- The same guard records (2026-09-15) that browser Azahar wasm did not present
  video: `getVideoDimensions()` returned `-1`, there was no audio context, and the
  source and presentation canvases were black with both the cached `latest` and
  the CDN `nightly` cores. That was recorded as an upstream limitation, not a
  product decision. The repaired `latest/data-v2` Azahar runtime in this
  repository postdates that record, which is exactly why a retest comes first.

What *does* exist is real wiring, not a missing feature flag:

| Piece | Where | State |
| --- | --- | --- |
| `3ds` mapped to the `azahar` core | `static/player.js` | present |
| Threaded-core path (`psp`, `3ds`) | `static/player.js` | present |
| WebGL2 requirement for `3ds` | `static/player.js` | present, reads `requiresWebgl2` (not `defaultWebGL2`) |
| `data-v2` asset path for the repaired Azahar runtime | `static/player.js` | present |
| Repaired runtime bytes | tracked under the Android asset tree and `native-offline/shared/web-runtime-lock.json` | `GOOD` — 22/22 locked assets match |
| Diagnostics hook (`?debug3ds=1`) | `static/player.js` | present |

So the gap is a runtime failure between asset fetch, core initialisation and the
first presented frame — not an unimplemented feature.

## Hypotheses to test (not conclusions)

Each is falsifiable; record which one the run actually shows.

1. **Threaded WASM needs a cross-origin-isolated context.** Azahar is in the
   threaded-core list. If the server does not send the isolation headers the
   core needs, the failure is an init error, not a visual bug.
2. **The `data-v2` asset fetch is blocked or stale** — a service-worker cache
   hit for the old path, a 404 in the proxy, or a lock mismatch.
3. **WebGL2 capability differs from the reported capability** — the browser
   reports WebGL2, the worker cannot get a context, or the fallback path is not
   taken.
4. **First-load cost crosses a timeout** — the repaired core is large; a bounded
   load budget may abort before the first frame.
5. **The upstream video limitation still holds for the repaired core** — the
   core loads and runs but never presents a frame. If this is what the run shows,
   report it as a dated upstream blocker with the exact evidence. Do not
   reintroduce a browser-only lock and do not claim 3DS on the Web.

## First steps (do these before changing code)

1. Reproduce in the canonical browser lane with `?debug3ds=1`, using a lawful
   user-owned 3DS fixture and the browser lane's documented prerequisites
   (`docs/UI_TESTING.md`).
2. Capture: the network requests for `data-v2`, the core init error (if any), the
   renderer/capability report, and whether a frame is ever presented.
3. Write the observed failing stage into this page with the date, the command and
   the exact error text. Only then choose a fix.

## Acceptance

- A lawful 3DS fixture reaches the first rendered frame in the browser lane on
  this host, with the run recorded (command, exit code, observable state).
- The run and the fix are recorded here and in the tracker; then the hosted
  browser lane is the authority.
- No claim is made for 3DS on the Web beyond the lane that was actually run.
- The core contract and the core cache key are unchanged, or the change is
  explicitly justified with its migration.

## Constraints

- No Eden/Switch on the web.
- No ROMs, firmware, keys or saves in the repository or in evidence.
- Do not weaken the core contract, the capability report order or the cache key
  to make 3DS start.
- If the cause is server headers, the Web product remains stdlib-only.

## Related

- [web-player](web-player.md), [core-selection](core-selection.md)
- `docs/UI_TESTING.md`, `docs/REGRESSION_GUARDS.md`
- `static/player.js`, `app.py`
