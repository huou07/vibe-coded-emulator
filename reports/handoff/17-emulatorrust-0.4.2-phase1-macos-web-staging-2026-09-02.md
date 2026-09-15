# EmulatorRust 0.4.2 — Phase 1 macOS + Web staging handoff

> Superseded by [EmulatorRust 0.4.3 Phase 1 handoff](18-emulatorrust-0.4.3-phase1-macos-web-staging-2026-09-07.md). The 0.4.2 artifact and staging identifiers below are historical.

Date: 2026-09-02

## Scope

- Deployed and verified staging only: `http://192.168.1.8:8092`.
- Production was not accessed, changed, restarted, or packaged.

## Architecture: before → after

- **Before:** macOS had separate software-upload and Azahar Vulkan paths; the web player held most EmulatorJS UI, persistence, and bridge code in `player.js`.
- **After:** native rendering is bounded behind `VulkanFrontend` and `NativeRendererMetrics`. GBA/NDS may acquire mapped libretro software-framebuffer memory; 3DS retains its native `VkImage` + semaphore presentation path. State, input, and UI remain host concerns.
- Web now has explicit `EmulatorSession`, `EmulatorCore`, `VideoSource`, `VideoBackend`, `InputRouter`, `AudioPipeline`, `SaveStateManager`, `QuickSaveManager`, and `FramePacingMonitor` boundaries. `VideoSource` describes both `SoftwareFramebuffer` and `NativeGpuFrame`; the current EmulatorJS canvas is an adapter rather than a new renderer implementation.

## Native Vulkan / MoltenVK / Metal

- GBA/NDS remain software framebuffer → Vulkan → MoltenVK → Metal. Each bounded slot owns a persistently mapped staging buffer, image, command buffer, fence, and semaphores. Resources are recreated on geometry/format changes, never per successful frame.
- A libretro core that supports `RETRO_ENVIRONMENT_GET_CURRENT_SOFTWARE_FRAMEBUFFER` writes directly into reusable mapped upload memory. Native raw formats avoid CPU conversion; conversion is a fallback only.
- The compile-time ring allows two or three slots; the default remains **two** to bound latency. Synchronization reuses fences/semaphores and waits only when a slot is reused. There is no `vkQueueWaitIdle()` or `vkDeviceWaitIdle()` in the normal upload/present path. Device idle is restricted to reconfiguration and the rare recovery for a signaled-but-unconsumed binary upload semaphore.
- 3DS/Azahar continues through native Vulkan images and semaphores, with no frontend GPU → CPU → GPU copy.
- Metrics expose direct/copy/convert/drop counters and bounded p95/p99 upload and present timing.

## Compatibility retained

- Native quick-save/load uses four stable slots and the exact raw `retro_serialize` / `retro_unserialize` bytes: no save-state wrapper or format migration.
- Existing web IndexedDB state storage remains `an3-arcade-save-slots` / `states` with its existing five slots, avoiding user data loss.
- Native menu exposes quick-save/load 1–4. Custom physical key mappings persist in `NSUserDefaults` under `an3.native-key-mappings.v1`.
- NDS touch/cursor-lock/Esc-release, virtual mobile controls, fullscreen, web touch, physical keyboard, and web input ordering were preserved in the relevant host/player paths.

## Web renderer boundary

- `?renderer=webgl2` requests WebGL2. `?renderer=webgpu` is recognized but currently falls back safely to the bundled EmulatorJS WebGL2/WebGL canvas and informs the user; it does **not** claim a real WebGPU backend.
- Fixed the preload temporal-dead-zone error around `queueTvDiscovery`, and updated localization preload paths to `stable/data/localization/en-US.json` and `vi-VN.json`.
- Added `player-runtime.js` to the service-worker shell cache.

## Files/modules changed

- Native: `native-offline/src-tauri/src/vulkan_frontend.{h,mm}`, `azahar_host.{h,mm}`, and `azahar.rs`.
- Native validation: `native-offline/tests/native_smoke.mm`, `native-offline/tests/mock_direct_frame_core.cpp`, `tests/test_native_renderer_contract.py`.
- Web: `static/player-runtime.js`, `static/player.js`, `static/service-worker.js`, `app.py`, and `native-offline/web/index.html`, plus regression/integration tests.

## Validation and benchmark results

- Current source check: 48 Python tests passed; `node --check` passed for `player-runtime.js` and `player.js`; native `npm run check` passed; macOS-targeted Rust tests passed (4); `git diff --check` passed.
- macOS ARM64 build passed. Local `codesign --verify --deep --strict` and `hdiutil verify` passed.
- Latest direct-frame AppKit/mock-core run (4.000 s): **237 frames / 59.25 FPS**, direct=237, copied=0, converted=0, dropped=0; raw state save/load both passed; upload p95/p99 **195/208 µs**, present p95/p99 **305/325 µs**.

| Ring | FPS / dropped | Upload p95/p99 | Present p95/p99 | Result |
| --- | --- | --- | --- | --- |
| 2 slots | 59.72 / 0 | 188 / 198 µs | 310 / 334 µs | retained default |
| 3 slots | 59.72 / 0 | 185 / 203 µs | 303 / 326 µs | no material throughput gain; larger latency bound |

- Historical real-core hardware measurements used the same capped target: GBA 59.72 FPS, NDS 59.87 FPS, both zero drops; 3DS/Azahar 58.47 FPS with no software uploads and present p95/p99 382/408 µs. These support stable pacing, not an FPS-increase claim.

## Staging artifact and smoke test

- Active release: `20260901-215838-2069cf9ab995`; health returned `ok=true`, `environment=staging`, asset version `2069cf9ab995`.
- DMG: `emulatorrust-0.4.2-macos-aarch64.dmg`, 42,194,435 bytes, SHA-256 `02cec8c6e8b59e12d8c26967400592e46b63855473f0ea9e2169e58ae120ac23`.
- Staging download was byte-identical to the local artifact and passed `hdiutil verify`.
- Browser smoke on final staging reached `Ready` without page error for both GBA preload routes: `?renderer=webgpu` (safe fallback) and `?renderer=webgl2`.

Download: `http://192.168.1.8:8092/download-app/release/emulatorrust-0.4.2-macos-aarch64.dmg`

## Remaining limitations and next step

- The real split into Emulator Worker, Render Worker/OffscreenCanvas, `SharedArrayBuffer` framebuffer ring, WebGPU backend, and AudioWorklet is **not** implemented. EmulatorJS currently owns the WASM/canvas/audio lifecycle; faking those layers would be unsafe. The new boundary prepares that migration.
- CPU, memory, audio-underrun, and independent `T_emulate` telemetry are not exposed by the current harness. The mock benchmark is not a substitute for licensed real-game benchmarking.
- Native visual click-through for menu/key-map/cursor capture was source/compile/harness validated only; the local macOS GUI session was locked.
- Next: integrate a compatible EmulatorJS worker/WebGPU build, then collect real-ROM GBA/NDS/3DS CPU/memory/audio telemetry and repeat the same before/after benchmark protocol.
