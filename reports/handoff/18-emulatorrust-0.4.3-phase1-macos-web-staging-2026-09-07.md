# EmulatorRust 0.4.3 — Phase 1 macOS + Web staging handoff

Date: 2026-09-07

## Scope and release boundary

- Completed the Phase 1 native-renderer hardening and web cache/deployment work in the staging tree.
- A detailed repository-wide architecture summary is available at [`reports/system-summary/AN3-ARCADE-FULL-SYSTEM-SUMMARY-2026-09-07.md`](../system-summary/AN3-ARCADE-FULL-SYSTEM-SUMMARY-2026-09-07.md).
- Staging endpoint: `http://192.168.1.8:8092`.
- Production was not accessed, changed, restarted, or packaged.
- Active staging release: `/opt/an3-arcade-staging/releases/20260907-112953-6a70df830ac0`.
- Staging health: `ok=true`, `environment=staging`, `asset_version=6a70df830ac0`.

## Architecture: before → after

- Native rendering remains behind `VulkanFrontend`/`NativeRendererMetrics`; state, input, menu, and persistence stay in host/session code.
- `VideoSource` supports both `SoftwareFramebuffer` and `NativeGpuFrame`. `EmulatorSession`, `EmulatorCore`, `VideoBackend`, `InputRouter`, `AudioPipeline`, `SaveStateManager`, and `QuickSaveManager` boundaries are explicit in the web player layer.
- GBA/NDS use software framebuffer → Vulkan → MoltenVK → Metal. 3DS/Azahar keeps the native Vulkan image/semaphore path, with no frontend GPU → CPU → GPU copy.

## Native macOS Vulkan work

- GBA/NDS slots own reusable staging buffers, persistently mapped memory, image, command buffer, fence, and semaphores. Successful frames do not create/recreate textures, buffers, or pipelines.
- Cores that expose `RETRO_ENVIRONMENT_GET_CURRENT_SOFTWARE_FRAMEBUFFER` write directly into the reusable mapped upload slot. RGB565/XRGB/1555 paths avoid CPU format conversion; conversion is a fallback.
- Upload storage is bounded to 2–3 slots. Benchmarking selected **two slots** as the default: it matches three-slot throughput while keeping the latency bound smaller.
- Fence/semaphore reuse waits only when reusing a slot. There is no `vkQueueWaitIdle()`/`vkDeviceWaitIdle()` in the normal per-frame path.
- CoreVulkan failure/replacement/shutdown now drains pending one-shot acquire/release semaphores through a persistent command buffer, matching image-ownership/layout barriers and a fence before state is discarded. This prevents semaphore ownership leaks and stops presentation after an unrecoverable renderer error.
- 3DS/Azahar remains native-GPU throughout the frontend; software upload counters stay at zero for that path.

## Web renderer and cache architecture

- `?renderer=webgpu` and `?renderer=webgl2` are accepted test selectors. The current EmulatorJS integration still owns WASM, canvas, and audio lifecycle; WebGPU/OffscreenCanvas/AudioWorklet workers were therefore not faked.
- `webgpu` currently falls back safely to the bundled EmulatorJS WebGL/WebGL2 canvas with an explicit notice; this is not claimed as a real WebGPU backend.
- The player layer is prepared for a future Main/UI + Emulator Worker + Render Worker/OffscreenCanvas + AudioWorklet split. `VideoSource`/`VideoBackend` are adapters, not a second copy of the EmulatorJS core.
- Service-worker boot assets now use an immutable versioned path (`/static/v/6a70df830ac0/{offline.js,player-runtime.js,player.js}`), while `/service-worker.js` is rendered with the active asset version. Old versioned aliases return 404, preventing upgrade-stale boot scripts.
- Renderer allocation and frame-pacing boundaries remain reusable; the current browser smoke validates route selection and boot readiness, not a new WebGPU implementation.

## Compatibility retained

- Native save/load uses raw libretro serialization bytes and four stable quick-save slots (1–4); no save-state format migration was made.
- Existing web IndexedDB database/store and five-slot behavior remain unchanged to avoid user-data loss.
- Fullscreen, NDS touch, cursor lock with Esc release, virtual mobile controls, physical keyboard input, custom key mappings, and input ordering were preserved in their existing host/player paths.

## Files/modules changed

- Native: `native-offline/src-tauri/src/vulkan_frontend.{h,mm}`, `azahar_host.{h,mm}`, `azahar.rs`, native smoke/mock-core tests, packaging/version metadata, and `scripts/prepare-web.mjs`.
- Web: `app.py`, `static/player-runtime.js`, `static/player.js`, `static/offline.js`, `static/service-worker.js`, regression/integration tests, and generated native web assets.
- Deployment: staging release was performed only through `/usr/local/sbin/an3-arcade-staging-release`.

## Validation

- `python3 -m unittest discover -s tests -v`: **49 passed**.
- `node --check static/player-runtime.js` and `node --check static/player.js`: passed.
- `(cd native-offline && npm run check)`: passed.
- `(cd native-offline/src-tauri && MACOSX_DEPLOYMENT_TARGET=13.4 cargo test)`: **4 passed**.
- `git diff --check`: passed.
- macOS ARM64 Tauri build, deep/strict codesign verification, and DMG verification: passed. The app is ad-hoc signed and not notarized because Apple notarization credentials were not available.
- Staging health, rendered Service Worker markers, immutable current alias (200), wrong-version alias (404), and both browser preload routes were smoke-tested. Both routes reached `Ready` with no page error:
  - `/core-preload/gba?renderer=webgpu`
  - `/core-preload/gba?renderer=webgl2`

## Benchmark results

The mock direct-frame AppKit harness (4.000 s) measured 237 frames / 59.25 FPS, direct=237, copied=0, converted=0, dropped=0, state save/load=1/1, upload p95/p99=195/208 µs, present p95/p99=305/325 µs.

| Upload ring | FPS / dropped | Upload p95/p99 | Present p95/p99 | Decision |
| --- | --- | --- | --- | --- |
| 2 slots | 59.72 / 0 | 188 / 198 µs | 310 / 334 µs | default |
| 3 slots | 59.72 / 0 | 185 / 203 µs | 303 / 326 µs | no material throughput gain; larger latency bound |

Historical real-core hardware runs at the same capped target measured GBA 59.72 FPS and NDS 59.87 FPS (zero drops), and 3DS/Azahar 58.47 FPS with no software uploads. These results support pacing/stability; they do not claim an FPS increase. CPU/memory/audio-underrun and independent `T_emulate` telemetry were not available in this harness.

## Staging artifact

- Download: [emulatorrust-0.4.3-macos-aarch64.dmg](http://192.168.1.8:8092/download-app/release/emulatorrust-0.4.3-macos-aarch64.dmg)
- Local artifact: `native-offline/releases/emulatorrust-0.4.3-macos-aarch64.dmg`
- Size: **42,214,995 bytes**
- SHA-256: `9b918342b755ab19781ccc86787b4c7c58955e29166f9fa4022e3d4ed53e63f3`
- Staging download was byte-identical to the local artifact and passed `hdiutil verify`.

## Limitations and next step

- Real Emulator Worker/Render Worker + OffscreenCanvas + SharedArrayBuffer framebuffer ring + WebGPU backend + AudioWorklet migration remains pending because EmulatorJS owns those lifecycles today.
- Native visual click-through for menu/key-map/cursor capture was source/compile/harness validated; the local macOS GUI session was locked during this run.
- The provided browser fixture is intentionally not treated as a real ROM. Real-ROM GBA/NDS/3DS gameplay, audio, and long-run soak should be repeated on an unlocked macOS GUI host with licensed test ROMs.
- Next: integrate a compatible worker/WebGPU EmulatorJS build, add real-core telemetry (CPU, memory, audio underruns, `T_emulate`/`T_upload`/`T_present`), and rerun the benchmark matrix before considering a production change.
