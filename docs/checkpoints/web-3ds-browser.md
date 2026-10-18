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
4. **Sustained play.** The run covers seconds. Frame pacing, long-session
   stability and the real gameplay budget stay with
   `docs/features/web-player.md` and `vce-gameplay-performance`.
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
