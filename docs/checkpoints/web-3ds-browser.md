# Checkpoint — Browser 3DS

Updated: 2026-10-18 (worker `dsh-worker` on the Debian x86_64 host). Unfinished
work for making 3DS playable in the browser. `docs/features/web-3ds.md` carries
status and the recorded run; `docs/REGRESSION_GUARDS.md` RG-160 carries the
guard. This is the only browser-3DS tracker.

Evidence vocabulary is the repository's: `GOOD` (the named live check is current
for this source), `UNVERIFIED` (the implementation exists, no live check), and
`BROKEN` (a live check failed).

## Closed 2026-10-18

| Item | Evidence |
| --- | --- |
| The failing stage was reproduced and named, not guessed | `GET /emulatorjs/latest/data-v2/cores/azahar-thread-wasm.data` → **502**, then the CDN fallback died with `TypeError: Failed to fetch` under COEP |
| The Web server can reach its own repaired runtime | `cached_emulator_asset` consults the lock-verified vendored `latest/data-v2` copy before the network; `tests/test_web_3ds_runtime.py` proves cold-cache delivery, drift rejection and an untouched plain channel |
| The playable gate reads a real audio context | `static/player.js` records the contexts the platform constructs, before the core loads; `AUDIO_STARTED state:running` in the live run |
| A lawful fixture reaches the first presented frame | canonical browser lane, 2 pass / 0 fail / 0 skipped, `THREAD_POOL_READY`, three canvas captures with 2795–3681 distinct colours |

## Closed 2026-10-19 — speed

| Item | Evidence |
| --- | --- |
| The browser was running DynCom, not an optimised backend | shipped bundle `azahar` 2.0.3 = `EmulatorJS/azahar@62cfcfb`, no `src/core/arm/fastinterp`, `ENABLE_GENERIC`; `use_cpu_jit` default true reaches the Dynarmic-less else-branch, and `use_fastinterp` was never consulted |
| FastInterp is compiled in and selected | upstream `98932aee` (PR #2376) ported onto the shipped base; the core logs `AN3PROF backend=FastInterp` from the selection point in an instrumented build, and the shipped bundle carries the same selection code |
| The interpreter was the dominant per-frame cost | instrumented `retro_run`/`RunLoop` timers: 8.1 ms per frame, 7.9 ms of it ARM interpreter, on the Intel UHD 770 |
| The threaded core was unpaced | `vsync:"disabled"` in `static/player.js`; measured 40.7 fps (0.68x) with DynCom and 116.6 fps (1.95x) with FastInterp on the same machine. A core-side LCD limiter now holds 59.83 fps = 1.00x in three of three trials |
| Frame-time tails improved | software renderer p50 37.99 → 27.73 ms, p95 43.45 → 36.77 ms, p99 52.62 → 41.37 ms |
| A rebuilt core reaches returning players | header `must-revalidate` for `.data`/reports plus network-first in the service worker; live two-load check with a persistent profile reports `refreshed: true` |
| The build is reproducible | `tools/build-azahar-wasm.sh` (pinned emsdk 3.1.71, fork commit, FastInterp commit, RetroArch harness commit) + `tools/install-azahar-core.py`; patches in `tools/azahar-wasm/` |

## Open work

1. **A hosted browser lane cannot hold this yet.** The fixture is a lawful
   user-owned file and must never enter the repository, so the hosted browser job
   skips the 3DS case with its reason; a hosted `GOOD` would need an owner-supplied
   fixture or a synthetic homebrew image produced by a tracked generator. Until
   then every hosted run is `UNVERIFIED` for browser 3DS.
2. **Other browsers and platforms.** Chromium on Debian x86_64 is the only
   configuration run. Firefox and Safari, and the packaged desktop/Android
   webviews, are `UNVERIFIED`.
3. **Audible audio.** This host has no PCM device. A running `AudioContext` is
   not audible output; audio correctness, latency and underruns are `UNVERIFIED`.
4. **Sustained play.** The performance arms cover 20 s each with a homebrew menu,
   not a game session. Long-session stability, thermal behaviour, and a heavy
   commercial scene stay `UNVERIFIED`; only a lawful homebrew fixture was used.
5. **A heavy scene.** 3ds-hbmenu is a light workload. A GPU/compute-heavy lawful
   fixture was not obtained, so the "heavy scene" arm of the acceptance matrix is
   `UNVERIFIED` and the improvement is only proven where the interpreter
   dominates.
5. **The `WebGL: INVALID_ENUM: bindTexture: invalid target` warnings.** Recorded
   during the 3DS run and repeated until the context stops reporting. They did not
   prevent frames, so they are not blocking, but the core's GL shim binding an
   invalid texture target is unresolved and should be confirmed upstream before
   any rendering-quality claim.
6. **`getVideoDimensions()` through the public handle.** The player's own
   milestone reported the dimensions; a direct `EJS_emulator` probe returned no
   handles, so any future documentation should read the player's diagnostics, not
   `EJS_emulator`.

## Reproduce

```sh
# Lawful fixture: devkitPro/3ds-hbmenu v2.4.3 boot.3dsx, 383400 bytes,
# sha256 9c95ef995e34f7fce2dab7bf3d6ff19d952837d032586a11256f5ae0b2a3fee6.
# Keep it outside the repository.
AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium \
AN3_3DS_FIXTURE=/path/to/boot.3dsx \
  node --test tests/web-runtime.test.mjs

python3 -m unittest tests.test_web_3ds_runtime
```

## Related

- [web-3ds](../features/web-3ds.md), [core-selection](../features/core-selection.md),
  [web-player](../features/web-player.md)
- `docs/REGRESSION_GUARDS.md` RG-078 (no browser-only lock), RG-160 (this fix),
  `docs/UI_TESTING.md`
