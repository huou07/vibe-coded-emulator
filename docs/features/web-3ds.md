# Web 3DS — making Nintendo 3DS playable in the browser

Read when: the task is to make 3DS games play in the browser, or to diagnose why
they do not.

Skip when: the work is native 3DS (Azahar libretro core in the installed app) or
Eden/Switch. The browser never carries the Switch companion.

## Status

**Playable on this host, in the canonical browser lane, with a lawful fixture, and
playable on the public production surface over HTTPS.** The public check ran on
`https://an3tocom.space/offline` on 2026-10-19 with the lawful devkitPro/3ds-hbmenu
v2.4.3 `boot.3dsx`: the import succeeds and the player reaches ready with two canvases,
no notice and no page errors, with `isSecureContext` true. The same page opened on a LAN
IP over plain HTTP cannot run it, because the threaded core needs `SharedArrayBuffer`
and a secure context; the 3DS card says so there instead of failing at launch.
Measured 2026-10-18 on the Debian x86_64 host; the hosted browser job is the
authority and does not carry a fixture, so its 3DS case skips with its reason.

Two defects were reproduced live before anything was changed, and both are fixed
(RG-160):

1. **The asset stage never completed.** `GET
   /emulatorjs/latest/data-v2/cores/azahar-thread-wasm.data` and
   `.../cores/reports/azahar.json` answered **502**. The repaired runtime is
   published only by a pinned project build — the public CDN has no
   `latest/data-v2` path — so on a host whose server cache had not been seeded by
   `deploy/seed-azahar-core.sh`, the core never loaded. `app.py` reached only its
   cache and the CDN, never the locked vendored copy the repository already
   tracks. Fixed: `cached_emulator_asset` now consults the lock-verified vendored
   runtime before the network, exactly as `prepare-web.mjs` does for the desktop.
2. **The playable gate could never pass.** It required a running `AudioContext`
   reachable from `EJS_emulator`, which this runtime never exposes: the core
   creates its context inside its own glue. The overlay stayed on "did not reach
   ... running audio output" while frames were already presenting. Fixed:
   `static/player.js` records the contexts the platform constructs and the gate
   reads those, so the requirement stays real without inventing a second source
   of truth.

What the 2026-09-15 record described is now explained and no longer current. The
recorded `getVideoDimensions() = -1` and "no audio context" were consequences of
the two defects above: the core never loaded at all on an unseeded host, and the
audio handle it looked for does not exist on this runtime. With the vendored
runtime delivered, `getVideoDimensions()` reports `400x480` and the recorded
context reaches `running`.

Two recorded constraints still hold:

- RG-078: **no browser-only 3DS playback lock may be reintroduced.** The play
  control is bound only to `androidThreeDsUnavailable`/`html5`, and
  `browserThreeDsUnavailable` must stay absent. No lock was added.
- The EmulatorJS core contract (`EmulatorJS-core` / `core` / `?EJS_KEYS!`), the
  core cache key `an3-arcade-cores-v1`, and the `data-v2` URL shape are
  unchanged; the Web product stays stdlib-only and never carries Eden.

### Speed: the confirmed causes and what changed (2026-10-19)

Two defects explained the reported slowness, and both were measured before they
were touched.

1. **The browser ran the DynCom interpreter, not an optimised backend.** The
   shipped bundle (`azahar` 2.0.3) was built from `EmulatorJS/azahar@62cfcfb`, a
   February-2026 Azahar with `-DENABLE_GENERIC=ON` and no `src/core/arm/fastinterp`
   at all. `citra_use_cpu_jit` defaults to *true*, so `Core::System::Init` took the
   `#if CITRA_ARCH(x86_64) || CITRA_ARCH(arm64)` else-branch, instantiated
   `ARM_DynCom` and logged "CPU JIT requested, but Dynarmic not available". With
   `use_cpu_jit` true, the `use_fastinterp` branch was never even reached: the
   option existed but could not change anything. Upstream FastInterp (PR #2376,
   `azahar-emu/azahar@98932aee`, first release 2127.0-alpha1) is now compiled in,
   the build no longer claims a JIT it does not have, and the core logs the
   backend it selected (`CPU backend: FastInterp`).
2. **The threaded core was never paced, so its speed was whatever the CPU
   afforded.** `static/player.js` sets `vsync:"disabled"` for every launch, and
   the EmulatorJS frontend only waits for a browser frame when VSync is on
   (`frontend/drivers/platform_emulatorjs.c`). Unpaced, the same build ran at
   0.72x real time with DynCom and 1.95x with FastInterp on one machine. The core
   now waits for the 3DS LCD boundary (59.8261 Hz) only when it is *ahead*, so
   real-time play is restored without adding a stall when the hardware is behind.

Measured on the lawful devkitPro/3ds-hbmenu v2.4.3 fixture, Chromium on the
Debian x86_64 host, same page and server for every arm; three 20 s trials each,
mean reported.

| Core | Renderer | Pacing | Emulated rate | Speed of native |
| --- | --- | --- | --- | --- |
| DynCom (shipped) | SwiftShader | off | 25.9 fps | 0.43x |
| DynCom (shipped) | Intel UHD 770 | off | 40.7 fps | 0.68x |
| DynCom (shipped) | Intel UHD 770 | on | 43.3 fps | 0.72x |
| FastInterp | SwiftShader | off | 34.7 fps | 0.58x |
| FastInterp | Intel UHD 770 | off | 116.6 fps | 1.95x |
| **FastInterp (shipped)** | **Intel UHD 770** | **on** | **59.83 fps** | **1.00x** |

Frame-interval distribution on the software renderer, where the interpreter was
the limit: p50 37.99 → 27.73 ms, p95 43.45 → 36.77 ms, p99 52.62 → 41.37 ms.
Startup (navigation to the player clearing its own overlay) 2.61 → 2.54 s. The
audio context stayed `running` with its clock tracking wall time in every arm,
and the paced arm's rate is the LCD rate exactly, so the speed of play is correct
rather than fast-forwarded. A slow device does not lose throughput to the limiter:
interleaved headless runs measured 34.55/33.06 fps unpaced against 34.42/33.18 fps
paced.

Instrumented per-frame time on the iGPU (temporary build, not shipped): 8.1 ms per
frame of which 7.9 ms is the ARM interpreter, so the CPU backend is still the
largest single cost; a software renderer adds roughly 20 ms per frame on top of it.

**A rebuilt core no longer stays pinned in a returning browser.** The core binary
and its build report were served `immutable` for a week and the service worker
answered them cache-first, so a player who had already downloaded a core kept the
old interpreter. Both now revalidate (`public,max-age=0,must-revalidate`,
network-first with a cache fallback), verified live: a fresh profile fetched the
first core, the server's core was replaced in place, and the same profile then
received and cached the new bytes (`refreshed: true`).

### Live run, 2026-10-18

```sh
AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium \
AN3_3DS_FIXTURE=work/fixtures/an3-lawful-3ds-homebrew.3dsx \
  node --test tests/web-runtime.test.mjs      # exit 0, 2 pass, 0 fail, 0 skipped
```

Fixture: `devkitPro/3ds-hbmenu` v2.4.3 `boot.3dsx`, 383400 bytes, SHA-256
`9c95ef995e34f7fce2dab7bf3d6ff19d952837d032586a11256f5ae0b2a3fee6` — the same
lawful test content RG-078 recorded for native 3DS. It is **not** in the
repository and never will be; the lane skips without one.

Observable state: `SOURCE_CANVAS_AVAILABLE` 300x150, `AUDIO_STARTED`
`state:running`, `FIRST_VIDEO_FRAME` frame 1 at 1836 ms, `THREAD_POOL_READY`
`isolated:true`, loading overlay cleared, no page error, no failing emulator
asset. Three canvas captures around two arrow presses held 2795, 3601 and 3681
distinct colours at mean luma 112.7, 111.6, 111.6.

### What is still not claimed

- **Real hardware in a real browser window.** The performance arms above ran
  Chromium either headless (SwiftShader, software GL) or non-headless under Xvfb
  with ANGLE/Vulkan on this host's Intel UHD 770. Both are the same renderer
  Chromium uses for a user, but neither is a user's desktop session.
- **Other browsers and platforms.** Chromium on Debian x86_64 only.
- **Audible audio.** This host has no sound device; a running audio context is
  not audible output.
- **Sustained play.** The run covers seconds, not a session; the player's own
  `CORE_STARTED` carries `gameplayVerified:false`.

## Hypotheses, as tested

| # | Hypothesis | Result |
| --- | --- | --- |
| 1 | Threaded WASM needs a cross-origin-isolated context | refuted — `crossOriginIsolated:true`, `SharedArrayBuffer` present, COOP/COEP already sent for the player page |
| 2 | The `data-v2` asset fetch is blocked or stale | **confirmed** — local proxy 502, CDN fallback blocked by COEP; fixed by the locked vendored delivery |
| 3 | WebGL2 capability differs from the report | refuted — WebGL2 obtained, `WebKit WebGL` |
| 4 | First-load cost crosses a timeout | refuted — the core starts about 1.8 s after navigation |
| 5 | The upstream video limitation still holds | refuted for the repaired runtime — frames present with real, input-responsive content; the remaining gate was the unsatisfiable audio handle |

## First steps for a future regression

1. Reproduce in the canonical browser lane with `?debug3ds=1`, a lawful
   user-owned 3DS fixture and the lane's documented prerequisites.
2. Capture the network requests for `data-v2` (status, bytes), the capability
   report, the renderer, and whether the player's own loading overlay clears.
3. Write the observed failing stage into this page with the date, the command and
   the exact error text. Only then choose a fix.

## Acceptance

- A lawful 3DS fixture reaches the first rendered frame in the browser lane on
  this host, with the run recorded (command, exit code, observable state). Met.
- The run and the fix are recorded here and in the tracker; then the hosted
  browser lane is the authority.
- No claim is made for 3DS on the Web beyond the lane that was actually run.
- The core contract and the core cache key are unchanged, or the change is
  explicitly justified with its migration. Unchanged.

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
