---
name: vce-web-3ds
description: Use when making Nintendo 3DS playable in the browser or diagnosing why the browser 3DS core never presents a frame — Azahar wasm, the data-v2 runtime, threaded-core and WebGL2 prerequisites, or the core contract. Triggers on "3DS on the web", "azahar wasm", "3DS black screen", "data-v2", "3DS will not start in the browser". Do not use for native 3DS (the Azahar libretro core), for Eden/Switch, or for general player-UI work.
---

# Web 3DS

Use this procedure to establish where browser 3DS actually fails, fix the real
stage, and record the outcome. Never start from a theory about the cause: the
failing stage is `UNVERIFIED` until a run names it.

## Preconditions

- Read `docs/features/web-3ds.md`, `docs/features/core-selection.md` and
  `docs/features/web-player.md`.
- RG-078 is binding: **no browser-only 3DS lock may be reintroduced**, and
  `browserThreeDsUnavailable` must stay absent. Hiding the feature is not a fix.
- RG-078 also records (2026-09-15) that browser Azahar did not present video
  (`getVideoDimensions()` = `-1`, no audio context, black canvases) with both the
  cached `latest` and the CDN `nightly` cores. The repaired `latest/data-v2`
  runtime in this repository postdates that record, so the first step is a retest.
- Use a lawful user-owned fixture. No ROM, firmware, key or save enters the repo
  or the evidence.

## Procedure

1. Reproduce in the canonical browser lane with `?debug3ds=1` and the lane's
   documented prerequisites (`docs/UI_TESTING.md`).
2. Capture the failing stage, not a guess:
   - asset requests for `data-v2` (status, bytes, cache hit or miss),
   - the capability report and whether WebGL2 was actually obtained,
   - any core-init error or exception text,
   - whether the core runs but presents no frame.
3. Test the hypotheses in `docs/features/web-3ds.md` one at a time: isolation
   headers for the threaded core, stale `data-v2` cache, WebGL2 mismatch, first
   load budget, or the recorded upstream video limitation.
4. Fix the smallest real cause. If the cause is a server header, keep `app.py`
   standard-library only. If the cause is an asset path or lock, fix the path,
   not the lock.
5. Keep the EmulatorJS core contract (`EmulatorJS-core` / `core` / `?EJS_KEYS!`)
   and the cache key `an3-arcade-cores-v1` unchanged; a change needs a recorded
   migration reason.
6. Re-run the lane and record the command, exit code and observable state.
7. Update `docs/features/web-3ds.md` and the tracker with the result and date.

## Stop conditions

- If the core loads and runs but still presents no video, record it as a dated
  upstream blocker with the exact evidence and stop. Do not add a UI lock and do
  not claim 3DS on the Web.
- If the browser lane's prerequisites are unavailable, the result is
  `UNVERIFIED`; report the missing prerequisite, do not substitute static
  inspection.

## Report

State the observed failing stage, the fix (or the blocker), the lane command and
result, the fixture identity class, the contracts kept, and what remains
`UNVERIFIED` (other browsers, other platforms, sustained play).

Skip this procedure for native 3DS playback, for Switch/Eden, and for work that
does not touch the 3DS load path.
