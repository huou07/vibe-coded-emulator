# P1 resume — web NDS boot/code-path map

Date: 2026-09-08. Scope: read-only source mapping for staging asset
`11290264c01d`; no staging, production, browser, or source mutation was
performed by this report.

## Current fact boundary

The P1 handoff records all three paths failing visible gameplay for the same
NDS ROM: staged WebGPU and WebGL2 report submitted presentation frames but
are black; a local, bridge-free source-only proxy is white and shows the
EmulatorJS FPS overlay. Therefore the presentation bridge is not sufficient to
explain the remaining defect. It may still hide a successful source frame, but
the common remaining boundary is EmulatorJS/melonDS boot and its source canvas
output. Source: `reports/handoff/RELEASE_TRAIN_P1_20260908.md`, “Renderer
acceptance — current asset” and “Remaining blockers”.

## Boot and core selection

| Step | Evidence | Result |
| --- | --- | --- |
| Page configuration | `app.py:1257-1262` creates `system`, `channel`, ROM URL, and no alternate NDS core field. | Server config does not select a conflicting web NDS core. |
| Primary selection | `static/player.js:48-53` maps `nds` to `melonds`; `static/player.js:997-998` sets `EJS_core` to the requested system. | EmulatorJS requests the NDS profile. |
| Forced core | `static/player.js:1018-1029` sets `retroarch_core:"melonds"`, `melonds_screen_layout`, and `melonds_audio_bitrate` before adding `loader.js` (`1063-1074`). | The NDS boot code explicitly selects melonDS; no source branch switches NDS to another named core. |
| Legacy switch | `static/player.js:94-105` derives `forceLegacyNds` from persisted performance settings; `1051` assigns it to `EJS_forceLegacyCores`. | This is a real alternate NDS binary/configuration switch. A prior local `an3-player-performance-v1` value of low/custom+legacy changes the launch. It is the highest-value boot variable to record in the next reproduction. |
| Report/core artifact | `static/player.js:247-303` fetches `cores/reports/melonds.json`, derives `melonds[-legacy]-wasm.data`, and stores it in IndexedDB. | This report-first artifact selection is **preload-only** (`307-310` returns before normal boot). Normal emulator boot delegates asset selection to the external EmulatorJS loader, so a successful preload does not prove the runtime loader selected the same artifact. |
| Browser mode | `static/player.js:428` makes NDS a custom-pad system; `1047` therefore always sets `EJS_browserMode = 2` for NDS. | This is a common NDS-only EmulatorJS launch-mode change and should be A/B logged, but no source evidence establishes its semantics or that it is faulty. |

## Canvas and renderer ownership

1. EmulatorJS owns the source canvas, core, and audio; AN3 has no raw
   framebuffer contract (`static/player-runtime.js:4-10`). Its source lookup is
   `#game canvas:not(.an3-render-canvas)` (`354-366`).
2. Once `EJS_onGameStart` fires, NDS calls `finishLoading()` (`player.js:1053-1062`),
   which marks the core booted and starts the optional renderer bridge
   (`196-215`). Thus `onGameStart` proves core-load callback completion, not a
   nonblank source frame.
3. The bridge creates a separate absolute, pointer-inert target canvas above
   the source (`renderer-worker.js:487-506`), captures the source via
   `createImageBitmap` (`616-652`), and hides the source only after a rendered
   presentation result (`537-544`, `636-646`). This matches the P1 truthfulness
   contract: repeated copies can be black/white/frozen while counters rise.
4. The target's backing size follows source `canvas.width`/`height` or CSS
   bounds (`renderer-worker.js:481-485`), then both worker backends set target
   size from each captured bitmap (`35-41`, `140-161`, `279-307`). The worker
   accepts a `resize` message (`397-399`), but the bridge never sends one; its
   per-frame size path is the effective resize mechanism. No direct renderer
   sizing call changes the source canvas.
5. The source-only white output means `createImageBitmap`, the offscreen canvas,
   WebGPU texture flags, and WebGL2 presentation shaders are outside the
   minimal failing path. P1 already repaired WebGPU `COPY_DST` plus
   `RENDER_ATTACHMENT` at `renderer-worker.js:146-153`.

## Touch and source context interactions

The touch bridge intentionally resolves only the source canvas and makes the
presentation layer output-only (`static/nds-touch.js:2`, `38-50`; 
`player.js:772-825`). This preserves RG-015/RG-017. It is not involved before
the first visible source frame.

One concrete ownership risk is worth preserving for diagnosis: the touch
geometry path calls `canvas.getContext("webgl2") || canvas.getContext("webgl")`
on the source canvas (`player.js:599-620`). It runs only after user touch via
`mapNdsCursor` (`632-639`, `672-675`), after the observed blank boot. It cannot
explain an untouched launch, but must not be moved earlier or used as an eager
capability probe because it would compete with EmulatorJS for context ownership.

## FPS and readiness

`fps:"show"` is passed as an EmulatorJS default option (`player.js:1006-1008`).
The overlay is diagnostic only. `playbackReadiness` reports `video-submitted`
once the bridge has rendered at least one bitmap, explicitly leaves
`gameplayVerified:false`, and treats external source display separately
(`player-runtime.js:387-397`). The P1 handoff's white source + FPS overlay is
therefore evidence that the page reached EmulatorJS UI/render-loop territory,
not evidence of advancing melonDS output.

## Ranked next checks (no fix proposed)

1. In one controlled staging/local reproduction, capture before/after-loader
   values for `EJS_core`, `EJS_defaultOptions.retroarch_core`,
   `EJS_forceLegacyCores`, `EJS_browserMode`, runtime manager core, and the
   exact loader-fetched melonds report/data URL. This separates the explicit
   melonDS configuration from the loader's actual selected artifact.
2. Repeat with fresh browser storage/profile (or record the existing
   `an3-player-performance-v1` value) and explicitly compare native vs legacy
   NDS renderer selection. This targets the only persistent NDS artifact switch
   in local source without touching player-layer code.
3. Before any touch, sample the source canvas `width`, `height`, client rect,
   `getVideoDimensions`, and a single safe visual pixel/frame signature over
   time. Compare source-only and bridge-active runs. Do not use FPS HUD or
   bridge rendered-frame count as the advancing-frame signal.
4. If the source remains white under a verified native artifact and unchanged
   browserMode, inspect the pinned EmulatorJS loader/core build and melonDS
   report/options next. Avoid a presentation, touch, or renderer change: each
   is downstream of the bridge-free failure and protected by RG-015/017/032/033.

