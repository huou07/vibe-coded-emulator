# EmulatorRust / AN3 Arcade — System Inspection Handoff

> Evidence-based inspection of the repository and reachable **staging** runtime. This is architectural documentation, not a source-code dump.

## Current release-train authority — 2026-09-12

This continuation supersedes older current-status statements below wherever artifact bytes, availability, owner audio evidence, Linux status, or the staging asset differ. Historical inspection remains intact for provenance.

| Surface | Current status | Current evidence |
|---|---|---|
| Web | PARTIAL | Current HTTP staging asset `df14d4aa2d9a` reports requested WebGPU/effective WebGL2 at `requestAdapter`: the origin is insecure and `navigator.gpu` is absent. This is the correct fallback, not proof of a successful-WebGPU regression. Source behavior tests preserve WebGPU preferred → WebGL2 fallback and require `effective=webgpu` after successful initialization. |
| macOS DMG | PARTIAL | `vibecodedemulator-0.4.4-macos-aarch64.dmg`, 42,282,073 bytes, SHA-256 `762f1e8122c0b3455ed4a43509c001eb9a12adb252a398b5310c4ac9f8cb90f3`; codesign/disk-image verification passed. OWNER-VERIFIED: current GBA/NDS gameplay and actual audible audio are smooth. A fresh post-build human acceptance was not separately recorded. |
| Android APK | PARTIAL | `vibecodedemulator-0.4.4-android-arm64-staging.apk`, 87,703,074 bytes, SHA-256 `128780ed3f21cbf2ac4b158fcd02fc60bd97e92c9b9ded90918f52ad7a3faa24`; APK v2 signature verified. AVD acceptance covered native NDS Vulkan/GLES3, layouts, input, controls, archives, saves, and persistence. OWNER-VERIFIED: current GBA/NDS gameplay and actual audible audio are smooth. |
| Android 3DS | UNADVERTISED | Portable Azahar/libretro Vulkan hardware presentation booted legal homebrew with visible advancing frames, input, persisted layout, and save states. Tested homebrew did not provide qualifying confirmed audio samples, so the system is intentionally hidden and not accepted. |
| Linux DEB | VERIFIED | Authorized Debian built the native SDL/libretro package; GBA/Vulkan and NDS desktop OpenGL fallback Xvfb smokes ran with SDL audio configured. `vibecodedemulator-0.4.4-linux-amd64.deb` is 1,812,216 bytes, SHA-256 `7b8672db446a73c8dcf78220b77feb1501d9a0ae6958623fa74ba9319a3a7b49`. |
| Linux Flatpak | VERIFIED | Authorized Debian built the native Flatpak; the same GBA/Vulkan and NDS desktop OpenGL fallback Xvfb smokes ran. `an3-offline-0.4.4-linux-amd64-staging.flatpak` is 1,805,368 bytes, SHA-256 `65f72ed64935cd958d1e977dcbbb3a2e3ecad5e29d8c6746be76c9916a525a50`. |
| Windows EXE | BLOCKED | Shared portable source is prepared, but no real Windows Vulkan build/signing/runtime host is available. No EXE is claimed or published. |

Staging deployment is **PASS**: `/opt/an3-arcade-staging/releases/20260912-164924-df14d4aa2d9a` is live with preserved rollback target `/opt/an3-arcade-staging/releases/20260911-230833-bef86865b122`. The Release Center exposes exactly the macOS DMG, Android APK, Linux DEB, and Linux Flatpak; streamed staging downloads matched local catalog size/SHA-256 for all four. Production was untouched.

## Current release-train authority — 2026-09-11

This continuation supersedes older status claims where it names current source, current artifact bytes, or current runtime evidence. It preserves the historical inspection below.

| Surface | Current status | Current evidence |
|---|---|---|
| Web | PARTIAL | Web renderer/touch contract suite passed and staging asset `bef86865b122` is live. The web renderer remains WebGPU preferred → WebGL2 fallback and was not mixed into native gameplay; a full fresh browser gameplay matrix was not reaccepted in this continuation. |
| macOS DMG | PARTIAL | `vibecodedemulator-0.4.4-macos-aarch64.dmg`, 42,976,820 bytes, SHA-256 `b63b3e61708c532c899b1a8e7283af5d200c648a9465deef1f3d54f1d5fb2870`; codesign and disk-image verification passed. Fresh exact-bundle GBA/NDS ran 59–60 FPS using Vulkan → MoltenVK → Metal; the compact nine-section menu, save controls and Escape draft discard were visible. Speaker audibility and a new 3DS long-run are not accepted. |
| Android APK | PARTIAL | `vibecodedemulator-0.4.4-android-arm64-staging.apk`, 74,229,651 bytes, SHA-256 `cd98c834d5730f532b6e68a373072231c2519780822db9c6c30ff65e00086ff6`; APK v2 signature verified. Exact ARM64 AVD candidate ran native NDS under Vulkan and explicit GLES3, exercised rotation, both persisted NDS layouts with tap/drag/release, menu drafts, slots, Auto Save and state transfer. Speaker audibility is unverified; Android 3DS is intentionally unavailable. |
| Linux DEB | BLOCKED | Authorized Debian current-source build exited 3 rather than emit a browser-only package: the portable desktop surface/audio/OpenGL adapter and package integration are absent. |
| Linux Flatpak | BLOCKED | Same current-source native gate; no verified DEB input exists, so no Flatpak was fabricated. |
| Windows EXE | BLOCKED | Deterministic PowerShell path and shared portable core contracts are present, but a real Windows Vulkan build/signing/runtime host is unavailable; no `.exe` exists. |

Cross-platform consolidation completed in this continuation: renderer contracts and Core Options ABI now live in `native-offline/native-runtime/core/`, while macOS and Android act as adapters. The canonical `tools/release-train.sh --staging` entrypoint validates/prepares/builds only matching host targets, fails closed for unavailable targets, and never deploys or touches production. The staging deploy path was tightened so it packages only the two current verified installers and never creates/uploads a production archive or production release script.

All current-source checks passed before final staging publication: 110 Python tests, web NDS touch behavior, 11 web renderer behavior cases, native JavaScript syntax checks, and diff validation. Staging asset `bef86865b122` was then published at `/opt/an3-arcade-staging/releases/20260911-230833-bef86865b122`; health, Release Center manifest, and HTTP download size/SHA-256 parity passed for both available artifacts. Linux/Windows remain correctly blocked with no download. Production was not read, changed, restarted, or packaged.

## Inspection metadata

| Field | Value |
|---|---|
| Inspection date | 2026-09-07 (Asia/Ho_Chi_Minh) |
| Repository | /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade |
| Branch | ui/production-ux-refresh |
| HEAD commit | 542ef985ddd22435cad00695b065dda1be4f80d3 |
| Working tree | **DIRTY**; 106 modified/untracked status entries were present before this documentation-only change. Existing changes were preserved. |
| Existing handoff input | HANDOFF_PATH was supplied as a placeholder rather than a concrete path. The latest relevant handoff read was reports/handoff/18-emulatorrust-0.4.3-phase1-macos-web-staging-2026-09-07.md; older handoffs and the full-system handoff were also consulted. |
| Output path used | /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/SYSTEM_INSPECTION_HANDOFF.md |
| Staging URL | http://192.168.1.8:8092 |
| Staging health observed | ok=true, environment=staging, asset_version=6a70df830ac0 |
| Staging release observed | /opt/an3-arcade-staging/releases/20260907-112953-6a70df830ac0 via current symlink |
| Staging service observed | an3-arcade-staging.service, active and enabled |
| Production scope | No production HTTP request, deployment, restart, package, rollback, or data mutation was performed. |

### Evidence and redaction policy

The facts below come from repository files, symbols, line ranges, build/test output, and read-only staging checks performed in this inspection. Values that could identify credentials or private authentication material are intentionally omitted: passwords, password hashes, auth pepper, cookies, tokens, OAuth material, signing secrets, private keys, and key fingerprints. The private LAN staging IP is included only because it is the documented staging endpoint needed to reproduce the inspection; it is not an authentication secret.

The earlier inventory-style material was deliberately replaced with architecture and traceability.

## 1. Executive Summary

AN3 Arcade is a Python/SQLite web application with a browser EmulatorJS player and a separate Tauri 2 native macOS shell named EmulatorRust. The web server handles accounts, game metadata, uploads, library pages, service-worker/PWA assets, and health/metrics. The native shell packages the same front-end assets and adds an in-process native libretro host for GBA, NDS, and 3DS. Native macOS does not launch an external emulator application.

The native core split is:

- **GBA:** bundled mGBA libretro core, CPU emulation and software framebuffer.
- **NDS:** bundled melonDS DS libretro core, CPU emulation and software framebuffer; touch/cursor handling is hosted by the native view.
- **3DS:** bundled Azahar libretro core with the libretro hardware/Vulkan interface; native Vulkan frames are presented without a software readback path.

The intended native graphics path is Vulkan 1.1 through the bundled MoltenVK dynamic library to Metal on macOS. GBA/NDS software frames use reusable persistent-mapped host-visible staging buffers and a device-local image; 3DS uses the core-provided Vulkan image/synchronization path. Successful frames do not recreate Vulkan objects and do not call queue/device idle waits. Resource reconfiguration, failed-submit recovery, resize, and shutdown can wait for the device by design.

The web layer currently keeps EmulatorJS as the owner of the WASM core, canvas, and audio. AN3’s JavaScript layer composes session, input, persistence, and capability abstractions around that owner. URL renderer preferences (?renderer=webgpu and ?renderer=webgl2) are accepted for capability/telemetry and testing, but AN3 does **not** yet implement a WebGPU texture upload backend, OffscreenCanvas render worker, SharedArrayBuffer framebuffer ring, or AudioWorklet. The selected WebGPU preference safely falls back to the existing EmulatorJS canvas/WebGL path.

Staging is healthy and isolated at 192.168.1.8:8092, with an immutable versioned asset prefix. Current inspection tests passed: 49 Python unit tests, Python byte-compilation, JavaScript syntax checks, native npm checks, four Rust tests, shell syntax checks, DMG verification, and codesign verification. A browser smoke navigation reached the staging player URL, but the current browser automation surface could not expose enough DOM state to independently assert “Ready”; the prior handoff’s Ready result is therefore recorded as historical evidence, not as a current-run claim.

The largest gap is web renderer/thread architecture: the desired Main Thread/UI, Emulator Worker/WASM, Render Worker/OffscreenCanvas, and AudioWorklet split is documented as future work rather than implemented. Native Vulkan hardening is substantially present, but real-ROM long-run telemetry for CPU time, memory, audio underruns, and end-to-end latency remains incomplete.

## 2. Repository Overview

### 2.1 Product boundaries

The repository contains four cooperating surfaces:

1. **Python web service (app.py)** — HTTP/1.1 threaded server, SQLite persistence, authentication, uploads, library, player boot routes, static/core asset delivery, health/metrics, and staging-only operational endpoints.
2. **Browser player (static/)** — EmulatorJS boot/configuration, AN3 player session abstraction, touch/virtual controls, fullscreen/layout management, offline IndexedDB/OPFS library, service worker, and UI styles.
3. **Native offline application (native-offline/)** — Tauri shell, embedded front-end distribution, local-ROM picker/library, in-process libretro bridge, native AppKit controls, AVFoundation audio, and Vulkan/MoltenVK presenter.
4. **Optional Rust staging components (rust-gateway/ and netplay compose files)** — a thin explicitly configured staging reverse proxy and a separate staging-only Socket.IO relay. Neither was observed as active in the current listener check.

### 2.2 Top-level areas

| Area | Responsibility | Evidence |
|---|---|---|
| app.py | Web server, routes, schema, upload/detection, security headers, metrics | app.py:27-2605 |
| static/player.js | Web player boot, EmulatorJS options, controls, NDS touch, fullscreen, state UI | static/player.js |
| static/player-runtime.js | Renderer/session/input/audio/save abstractions | static/player-runtime.js:1-286 |
| static/offline.js | Browser/native offline library and ROM detection | static/offline.js |
| static/service-worker.js | Versioned PWA/core caching and offline navigation | static/service-worker.js |
| native-offline/src-tauri/src/lib.rs | Tauri commands, embedded local server, native ROM storage | native-offline/src-tauri/src/lib.rs:1-752 |
| native-offline/src-tauri/src/azahar.rs | Rust-side core registry and FFI orchestration | native-offline/src-tauri/src/azahar.rs:1-437 |
| native-offline/src-tauri/src/azahar_host.mm | Objective-C++ libretro host, AppKit UI/input, audio, save states | native-offline/src-tauri/src/azahar_host.mm |
| native-offline/src-tauri/src/vulkan_frontend.h/.mm | Vulkan/MoltenVK presentation and metrics | native-offline/src-tauri/src/vulkan_frontend.h and .mm |
| native-offline/scripts/ | Pinned core/MoltenVK fetching and native web packaging | native-offline/scripts/*.mjs |
| deploy/ | Staging package/update/rollback and optional relays | deploy/*.sh, deploy/staging |
| docs/ | Operational, native, player-layer, netplay, and regression contracts | docs/*.md |
| reports/handoff/ | Prior implementation and verification handoffs | reports/handoff/*.md |

### 2.3 Data and persistence boundaries

The server’s persistent data root is selected from environment/configuration in app.py; it includes SQLite, ROM files, covers, screenshots, uploads, prepared browser ROMs, and emulator asset cache. The native app uses its private application-data directory for imported native ROMs, per-ROM save directories, state slots, and core system files. Browser offline data is held in IndexedDB and optionally OPFS. These stores are intentionally separate; there is no implicit native-to-server ROM upload or server-to-native save synchronization.

### 2.4 Source-of-truth hierarchy

For runtime behavior, the order of authority used in this inspection was:

1. Current source and build/config files.
2. Current staging service, release symlink, health response, and headers.
3. Tests and reproducible command output from this inspection.
4. Existing handoffs and docs, explicitly marked historical when they describe earlier builds.

Where a handoff conflicts with current source or live staging (for example, a changed asset hash or an older route description), current source/live staging wins.

## 3. Application Architecture

### 3.1 System context

~~~mermaid
flowchart LR
    User --> Browser[Web browser]
    User --> Mac[EmulatorRust macOS]
    Browser --> HTTP[Python HTTP service]
    HTTP --> DB[(SQLite)]
    HTTP --> Files[ROM/media/assets]
    Browser --> EJS[EmulatorJS WASM + canvas + audio]
    Mac --> Local[Tauri loopback runtime]
    Local --> NativeUI[Embedded web UI]
    NativeUI --> FFI[libretro FFI bridge]
    FFI --> GBA[mGBA]
    FFI --> NDS[melonDS DS]
    FFI --> C3DS[Azahar]
    C3DS --> VK[Vulkan / MoltenVK / Metal]
    GBA --> SW[Software framebuffer]
    NDS --> SW
    SW --> VK
~~~

### 3.2 Native macOS process flow

~~~mermaid
sequenceDiagram
    participant UI as Tauri/WebView UI
    participant Rust as Rust commands
    participant Obj as Objective-C++ host
    participant Core as libretro core
    participant VK as VulkanFrontend
    participant M as MoltenVK/Metal

    UI->>Rust: start_native_game(rom_id, system, layout)
    Rust->>Obj: an3_native_start(...)
    Obj->>Core: dlopen + retro_* ABI init/load
    Core-->>Obj: video callbacks/audio/input requests
    Obj->>VK: initialize_software or initialize(core Vulkan)
    loop emulation frames
        Obj->>Core: retro_run()
        Core-->>Obj: software frame or hardware sentinel
        Obj->>VK: present_software or receive_image/present
        VK->>M: queue submit + presentation
    end
    UI->>Rust: stop_native_game()
    Rust->>Obj: an3_native_stop()
    Obj->>Core: context_destroy + retro_deinit
    Obj->>VK: shutdown
~~~

### 3.3 Web boot and rendering flow

~~~mermaid
flowchart TD
    Main[Main browser thread: UI/input] --> Boot[player.js]
    Boot --> Caps[Capability probe]
    Caps --> EJS[EmulatorJS manager]
    EJS --> WASM[EmulatorJS WASM/core]
    WASM --> Canvas[EmulatorJS-owned canvas]
    Canvas --> WebGL[EmulatorJS WebGL/WebGL2 path]
    Boot --> Runtime[EmulatorSession/player-runtime.js]
    Runtime --> Input[InputRouter]
    Runtime --> Save[SaveStateManager + QuickSaveManager]
    Runtime --> Pace[FramePacingMonitor]
    Runtime --> Audio[AudioPipeline observation]
    SW[service-worker.js] --> Shell[versioned app/core caches]
    BrowserStorage[(IndexedDB/OPFS)] --> Boot
~~~

The desired worker topology is not yet present in source. No new Worker, OffscreenCanvas, Atomics, or AudioWorklet construction was found in the AN3 web layer. EmulatorJS may use its own internal mechanisms, but they are outside AN3’s explicit worker contract and were not inferred as implemented by this repository.

### 3.4 Core/frame/input/audio/state relationships

    ROM import/detection
      ├─ server upload -> SQLite game + ROM file -> /play/<slug>
      ├─ browser offline -> IndexedDB/OPFS -> EJS_gameUrl
      └─ native picker -> app-data/an3-roms/<uuid>.<ext> -> native start command

    EmulatorSession
      ├─ EmulatorCore: EmulatorJS gameManager adapter (web)
      ├─ VideoSource: SoftwareFramebuffer | NativeGpuFrame contract
      ├─ VideoBackend: capability selection/diagnostics (current canvas owner)
      ├─ InputRouter: normalized actions -> EmulatorJS simulateInput (web)
      ├─ AudioPipeline: core-owned audio observation (not rAF-driven)
      ├─ SaveStateManager: raw state export/import
      ├─ QuickSaveManager: five browser slots / four native slots
      └─ FramePacingMonitor: bounded frame/p95/long-task samples

### 3.5 Lifecycle

    library -> select ROM -> infer system -> capability check -> boot core
           -> initialize video/audio/input -> run frames
           -> pause/menu -> save/load state or quick slot
           -> fullscreen/layout/touch updates
           -> stop -> flush persistence -> release core/video/audio

The native path has an additional local-runtime lifecycle: Tauri starts an embedded loopback HTTP server on desktop, navigates the window to it, and dispatches native commands. Mobile uses WebView asset loading and does not start the desktop loopback server.

## 4. Emulator Cores

### 4.1 Core registry

| System | Core | Pinned version | Native resource | Web profile | Frame path |
|---|---|---|---|---|---|
| GBA | mGBA libretro | 0.11-219-e31759b | libretro/macos-arm64/mgba_libretro.dylib | mgba | Native software framebuffer; EmulatorJS canvas in web |
| NDS | melonDS DS libretro | 1.3.1 | libretro/macos-arm64/melondsds_libretro.dylib | melonds | Native software framebuffer; EmulatorJS canvas in web |
| 3DS | Azahar libretro | 2126.0 | azahar_libretro.dylib | azahar | Native Vulkan hardware frame; EmulatorJS canvas in web |

The registry and version strings are in native-offline/src-tauri/src/azahar.rs:13-47. The web primary core map and profile flags are in static/player.js.

### 4.2 GBA — mGBA

**Initialization.** Rust validates a UUID-like native ROM id and system gba before Objective-C++ opens the mGBA dylib. CoreApi resolves required libretro symbols with dlopen/dlsym, installs environment/video/audio/input callbacks, calls retro_init, sets options, and loads the ROM. The native core is loaded from the packaged resource path; there is no search for an externally installed emulator.

**ROM and frame flow.** The ROM is imported to private app storage and exposed through a stable native URL/path. During retro_load_game, the host provides a path or reads the file into memory if the core requests data. mGBA emits a software frame through video_refresh. The host keeps the native format and pitch when they match the mapped upload slot; otherwise it performs row copy or explicit pixel conversion into the reusable staging memory. Vulkan then copies the staging buffer to a device-local image and blits to the swapchain.

**Input.** Standard libretro joypad IDs are backed by atomic button state. Default keyboard mappings are arrows, Z/X, A/S, L/J, Return, and Space; custom mappings are stored in NSUserDefaults under the versioned native mapping key. Virtual buttons are AppKit controls in the native shell and CSS/DOM controls in web.

**Audio.** The native host uses AVAudioEngine and AVAudioPlayerNode with interleaved signed 16-bit stereo buffers. The core callback queues bounded audio buffers; the queue ceiling is approximately one quarter second of samples. Browser audio remains EmulatorJS-owned.

**Save/state.** Raw libretro serialization bytes are saved atomically under the per-ROM state directory. Quick slots are numbered 1–4 in native UI. The host does not add a wrapper or convert the existing core state format.

**Shutdown and limits.** Stop drains a pending frame, destroys the core context, deinitializes the core, stops audio, shuts down Vulkan, and clears input/state. No GBA-specific rewind, netplay, or GPU frame path was found in the native code.

### 4.3 NDS — melonDS DS

**Initialization and renderer.** NDS uses the same libretro ABI sequence as GBA. Environment options explicitly select melonds_render_mode=software, threaded renderer, touch support, and top-bottom or left-right layout. The core therefore emits software frames to the native Vulkan upload path rather than a GPU-native frame.

**Dual-screen layout.** azahar_host.mm computes aspect-fit rectangles for top/bottom or side-by-side layout. The default top-bottom touch rectangle is approximately [40,360) x [240,480) in the native view coordinate convention; side-by-side uses the second-screen rectangle around [400,720) x [0,240). Exact rectangles are recalculated from current view bounds, scale, and selected layout.

**Cursor lock and touch.** The native NDS view has a Lock cursor control. Clicking/dragging the lower touch area maps mouse deltas to libretro pointer/mouse axes and asserts touch while pressed. CGAssociateMouseAndMouseCursorPosition(false) hides/confines the pointer; Escape (key code 53) releases the lock and restores the cursor. When unlocked, a second Escape is routed back toward returning to the library. Resignation of app/window focus releases the lock as a safety measure.

**Input and state.** Joypad, pointer, mouse delta, and touch pressed are atomic; the core reads them through input_state. Save/load uses the same raw state mechanism and four native quick slots. Browser NDS touch has a separate pointer-event bridge described in section 8.

**Performance path.** NDS frames are eligible for direct writes into a persistent mapped staging slot only when the core’s framebuffer pointer, format, and pitch exactly match the slot. A normal successful frame still requires one GPU buffer-to-image copy; the CPU intermediate memcpy can be eliminated.

### 4.4 3DS — Azahar

**Initialization.** Azahar is loaded from the bundled azahar_libretro.dylib and bundled MoltenVK. Environment negotiation requests Vulkan (citra_graphics_api=Vulkan), layout, resolution 1, hardware-rendering callbacks, and the libretro interface version supported by the host. Unsupported v2 negotiation is rejected rather than silently approximated.

**Native GPU frame.** The core sends a hardware-rendering frame sentinel/handle through video_refresh. VulkanFrontend::receive_image records the native image and source semaphores. present_image waits on the supplied source synchronization and blits/presents the image directly; no GPU-to-CPU readback and no CPU re-upload are used in the normal path. The host does not convert 3DS frames into the software framebuffer format.

**Layout and input.** Azahar layout is selected before boot (default or side-by-side). The native view exposes circle-pad controls, face/shoulder/start/select buttons, and touch mapping. Option+arrow combinations provide circle-pad keyboard input. A post-start rotation request displays a restart-needed message instead of mutating the running core geometry.

**Audio/state/shutdown.** Azahar sets its sample-rate option before game load, then uses the common AVAudioEngine callback and raw state slots. Stop performs the same bounded teardown as GBA/NDS and destroys the hardware context before unloading the dylib.

**Limits.** No verified 3DS network emulation was found. CIA/ZIP installation is rejected by native import until an installer/extractor exists; decrypted 3DS/3DSX/CCI/CXI-style inputs are accepted according to the extension/header rules.

## 5. Native macOS Rendering

### 5.1 Backend abstraction

vulkan_frontend.h defines a narrow presenter independent of save/input business logic. It accepts either a native hardware image (receive_image/present) or a software framebuffer (present_software, acquire_software_framebuffer). The VideoSource contract in the web runtime mirrors the same conceptual split with SoftwareFramebuffer and NativeGpuFrame kinds, although the web implementation currently reports an external core canvas.

This separation is the intended extension point for a future direct Metal backend, OpenGL fallback, or platform-specific Vulkan implementation. Those future backends are not present in Phase 1.

### 5.2 Vulkan/MoltenVK/Metal initialization

vulkan_frontend.mm:328-351 loads the bundled MoltenVK dylib with dlopen and sets the MoltenVK log level to quiet. Instance creation requests Vulkan 1.1, names the application EmulatorRust and the engine Azahar libretro, enables the Metal surface extension, chooses a physical device and one graphics/present queue, and loads function pointers. The native build links AppKit, AVFoundation, Metal, MetalKit, QuartzCore, CoreVideo, and C++.

The view supplies a CAMetalLayer-backed surface. Swapchain creation (:874-1005) requires transfer-destination usage, uses BGRA8 presentation images, prefers FIFO and uses mailbox when available, clamps image count to surface limits, and creates per-image command buffers, semaphores, fences, and image-fence tracking.

### 5.3 Reusable software upload resources

Impl::SoftwareFrameSlot owns a host-visible, host-coherent, persistently mapped staging buffer, its capacity, a device-local image, format, dimensions, bytes-per-pixel, and a direct-write flag (vulkan_frontend.mm:137-305). create_software_resources (:760-872) reuses the slot when geometry, format, capacity, and mapping remain compatible. It creates or resizes resources only at initialization, resize, format change, or capacity growth.

Supported source formats:

| Libretro format | Native bytes/pixel | Vulkan upload format | CPU conversion |
|---|---:|---|---|
| XRGB8888 | 4 | B8G8R8A8_UNORM | None when direct; row copy otherwise |
| RGB565 | 2 | R5G6B5_UNORM_PACK16 | None when direct; row copy otherwise |
| 0RGB1555 | 2 | A1R5G5B5_UNORM_PACK16 | None when direct; row copy otherwise |

When the core writes directly into the exact mapped pointer with matching pitch and format, upload_software_frame counts the frame as direct and skips an intermediate CPU copy. If the pointer or pitch differs, the host copies each row into the mapped slot. If the source format cannot be uploaded directly, it performs per-pixel conversion to the selected upload format. No converted buffer is exposed back to the core by acquire_software_framebuffer.

### 5.4 Bounded ring and frames in flight

AN3_FRAME_RING_SIZE defaults to 2 and is statically constrained to 2–3 (vulkan_frontend.mm:1-37). The ring holds PresentationFrame command/fence/semaphore state and software frame slots. On reuse, prepare_presentation_frame waits on the submitted slot fence (UINT64_MAX) before resetting it (:1155-1181). This is a bounded producer/consumer relationship: the emulator cannot grow an unbounded queue of frames, and the default two-slot configuration limits latency.

Historical benchmark evidence in handoff 18 compared ring sizes 2 and 3. Both sustained approximately 59.72 FPS with zero drops. Ring 3 measured slightly lower upload p95 but had no material throughput gain and a larger maximum buffering bound. The current source remains default two slots; this inspection did not rerun the native benchmark harness.

### 5.5 Synchronization and barriers

The successful software path records:

1. A source image barrier to transfer-destination layout.
2. vkCmdCopyBufferToImage from the mapped staging buffer.
3. A destination barrier to shader-read/transfer-source-compatible layout for blit.
4. Source-image and swapchain-image barriers around vkCmdBlitImage.
5. A final transition to present source layout.

The successful hardware path waits on source semaphores supplied by the core, inserts ownership/layout barriers, blits to the swapchain image when needed, submits once, signals render-finished, and presents. The implementation bounds accepted source wait semaphores at eight. Duplicate/null software callbacks reuse the last image rather than enqueueing an unbounded stale frame.

### 5.6 Queue submit/present and error paths

present_image (:1487-1691) acquires a swapchain image with an infinite wait for the bounded acquire operation, waits for that image’s fence, records the aspect-fit blit, submits with image-available and source semaphores, and presents. A successful frame clears one-shot source semaphore state and increments presented metrics. A failed submission/presentation drains or recreates the affected synchronization object and may destroy/recreate swapchain resources with a device wait.

discard_pending_core_frame (:1203-1288) is a recovery/replacement/shutdown path that drains a pending source frame using a reset command pool and fence. It is not executed for every successful frame. The separate CoreVulkan drain resources are created once and reused.

### 5.7 Idle waits and per-frame allocations

An exact source search found no vkQueueWaitIdle call/string. The vkDeviceWaitIdle function pointer is loaded because teardown/recovery needs it. Calls occur at:

| Location | Trigger | Hot path? |
|---|---|---|
| vulkan_frontend.mm:599 | Requested swapchain/resource destruction with wait_for_gpu | No; resize, shutdown, or error |
| vulkan_frontend.mm:789 | Software resource geometry/format/capacity reconfiguration | No; not steady-state frame upload |
| vulkan_frontend.mm:1409 | Failed presentation recovery before an upload semaphore is consumed | No; error path |

No Vulkan texture, buffer, descriptor, or pipeline creation was observed in the successful steady-state frame loop. Per-frame stack/local command data and small local C++ objects exist, but no per-frame Vulkan heap allocation was identified. The implementation still performs a GPU copy for each software frame; “minimal copy” means removal of the unnecessary CPU intermediate copy, not zero-copy from CPU memory into a device-local image.

### 5.8 Resize, fullscreen, and lifetime

Swapchain extent is checked against the current CAMetalLayer/view size; changes trigger a controlled teardown/recreate. Fullscreen is handled by the AppKit window/UI layer and causes layout and swapchain resize. Shutdown waits only where needed to guarantee safe destruction, then releases image views, swapchain, command pools, semaphores, fences, mapped memory, MoltenVK, and core resources.

### 5.9 Native renderer metrics

VulkanMetrics records presented/dropped/software upload/direct/copied/converted counts and bounded upload/present p95/p99 microsecond estimates (vulkan_frontend.h:32-47). The metrics ring is 256 samples. The smoke harness prints privacy-safe values. There are currently no integrated counters for T_emulate, CPU utilization, resident memory, or audio underruns.

## 6. Web Rendering Architecture

### 6.1 Implemented browser model

static/player-runtime.js states that EmulatorJS owns the WASM core, canvas, and audio. EmulatorCore wraps EmulatorJS gameManager state/frame APIs. VideoBackend.resolve probes WebGL/WebGL2 and navigator.gpu; it returns a diagnostic selection and marks WebGPU as a safe fallback request rather than binding a WebGPU canvas. VideoSource.snapshot exposes the conceptual software/native frame contract but currently reports external-core-canvas.

The player boot in static/player.js sets EmulatorJS options, core paths, layout, keyboard input, save intervals, and touch settings. EmulatorJS performs the actual core rendering and audio scheduling. AN3 observes frame counters and browser timing; it does not copy the full framebuffer in JavaScript each frame.

### 6.2 Renderer preference and fallback

queryRendererPreference accepts auto, webgpu, and webgl2 query values. In auto mode capability probes select a diagnostic backend. In webgpu mode, the runtime records that WebGPU was requested but safely falls back to the existing EmulatorJS/WebGL canvas because no AN3 WebGPU device/context pipeline exists. In webgl2 mode, the runtime verifies WebGL2 availability where possible. These selectors are test/configuration hooks, not proof of a custom WebGPU renderer.

### 6.3 Desired worker topology versus current source

| Desired component | Current evidence | Status |
|---|---|---|
| Main thread UI/input | player.js, DOM controls, fullscreen, pointer/keyboard handlers | Implemented |
| Emulator Worker/WASM | No AN3 new Worker; EmulatorJS may manage internals | Not implemented by AN3 / unverified inside EmulatorJS |
| Render Worker/OffscreenCanvas | No OffscreenCanvas construction | Not implemented |
| SAB framebuffer ring | Capability probe checks crossOriginIsolated/SAB; no ring allocation | Planned/partial |
| WebGPU upload/render | navigator.gpu probe only; no device/queue/texture calls | Not implemented |
| WebGL2 explicit upload | No AN3 texStorage2D, texSubImage2D, or texImage2D upload loop | Not implemented by AN3; EmulatorJS owns canvas |
| AudioWorklet | No AudioWorklet construction | Not implemented by AN3 |
| Audio independent of rAF | EmulatorJS owns audio; AudioPipeline explicitly does not use rAF | Implemented by ownership contract |

### 6.4 Frame transport and stale-frame policy

Because EmulatorJS owns the canvas, AN3 does not postMessage-copy a framebuffer each frame. FramePacingMonitor samples the core frame counter and rAF/UI timing in a bounded ring of 240 samples. droppedFrames is nullable because the current owner does not expose enough information for a reliable renderer drop count. A future worker implementation must preserve a latest-completed-frame-wins policy rather than queueing stale frames.

### 6.5 COOP/COEP/SAB prerequisites

Player pages and the native runtime set COOP/COEP/CORP headers where required. player.js rejects threaded profiles when crossOriginIsolated or SharedArrayBuffer is unavailable. Staging /offline returned COEP require-corp, COOP same-origin, CORP same-origin, and a CSP allowing the configured EmulatorJS CDN/origin. The /health endpoint intentionally has a simpler health response and does not carry the player’s COEP policy.

### 6.6 Sizing, DPR, fullscreen, and pacing

Capability probes inspect hardware concurrency, memory, device pixel ratio, viewport, screen dimensions, WebGL/WebGL2, WASM, and isolation. Fullscreen uses the Fullscreen API; resize and fullscreenchange recalculate virtual-pad and DS layout. Rotation after a game has started displays a restart-needed notice for systems whose core geometry cannot be changed safely. Audio does not depend on requestAnimationFrame. Browser frame-time measurements are diagnostics, not a replacement for core timing.

### 6.7 Browser caching and offline assets

service-worker.js uses a versioned shell cache (an3-arcade-pwa-v31-__ASSET_VERSION__) and a separate EmulatorJS core cache. ROM/API downloads bypass inappropriate cache handling. The staging asset prefix was /static/v/6a70df830ac0/; player-runtime.js and player.js returned immutable cache headers during inspection. The packaged native distribution copies static and native web assets into native-offline/dist and uses the local runtime rather than WAN requests.

## 7. Threading and Concurrency

| Domain | Mechanism | Observed behavior |
|---|---|---|
| Python HTTP | ThreadingHTTPServer-style request handling | Concurrent requests share SQLite with WAL/busy timeout and synchronized filesystem operations. |
| Native Tauri UI | Main AppKit/Tauri thread | Commands marshal native start/stop and view operations to the required main thread. |
| Native core | libretro callback/emulation context | Core calls are serialized through the host; a bounded channel coordinates start completion. |
| Native file work | Rust spawn_blocking | Native picker/import/list/remove avoid blocking the UI command path. |
| Native audio | AVAudioEngine/player node callbacks | Audio callback queues bounded PCM buffers and decrements queued-frame count on completion. |
| Native Vulkan | One graphics/present queue, frame-slot fences/semaphores | Slot reuse is bounded; mutex protects presenter state and callbacks. |
| Browser UI | Main JavaScript thread | DOM, pointer, keyboard, fullscreen, and EmulatorJS boot are handled here. |
| Browser worker split | None in AN3 source | No explicit worker/render-worker/audio-worklet architecture is implemented. |

The native presenter can block on a reused slot or swapchain image fence. This is intentional for bounded in-flight work and latency, but it means the core thread can experience a wait when GPU presentation falls behind. There is no unbounded queue and no per-frame queue-idle call.

## 8. Input System

### 8.1 Common routing precedence

Player-layer documentation defines the precedence as toolbar/menu actions, then virtual controls, then remaining canvas touch, then physical keyboard. EmulatorJS’s own menu can temporarily lower or disable the virtual pad so menu navigation is not intercepted.

### 8.2 Physical keyboard

The browser leaves physical keyboard ownership with EmulatorJS (keyboardInput=true in boot options). Native AppKit key handling maps common GBA/NDS buttons to configurable key codes stored in NSUserDefaults under an3.native-key-mappings.v1. Custom mapping UI is opened from the native menu and does not alter save-state bytes.

### 8.3 Virtual/mobile controls

player.js creates system/orientation-specific virtual pad layouts, persists user layout changes in localStorage, uses pointer events with capture, and recalculates safe areas after resize/fullscreen. offline.js and the native bootstrap distinguish desktop integrated controls from mobile browser/Android bridge controls. touch-action and pointer-events rules protect the game canvas while allowing pad buttons to receive input.

### 8.4 NDS touch and pointer

The NDS bridge supports pointer variants, coordinate normalization, synthetic pointer/mouse compatibility events, pointer capture, and document-level touch tracking. It maps client coordinates through the selected DS screen rectangles, clamps normalized values, and records a bounded debug export (an3-nds-touch-debug-v1). The native host uses mouse delta plus pressed state for a locked cursor and maps absolute touch rectangles for virtual input.

### 8.5 Cursor lock and Escape behavior

Native NDS cursor lock is explicit: click Lock cursor or the touch view, hide/associate the pointer, and accumulate movement deltas. Escape releases the lock and restores normal pointer control. App/window deactivation also releases it. A subsequent Escape is available for library/menu navigation. The web player keeps EJS_mouseLock=false by default and uses its own pointer/touch bridge; a browser pointer-lock implementation was not found in AN3 source.

### 8.6 Gamepad

No dedicated Gamepad API mapping or native HID/gamepad adapter was identified in the inspected AN3 source. EmulatorJS may provide its own gamepad support, but it was not independently verified here and should be treated as unverified.

## 9. Audio System

### 9.1 Native audio

azahar_host.mm:889-985 creates an AVAudioEngine and AVAudioPlayerNode with an interleaved signed 16-bit stereo format. The callback validates a sample rate between 8 kHz and 192 kHz, allocates an AVAudioPCMBuffer for the callback payload, copies interleaved samples, and tracks queued frames atomically. A queue ceiling of approximately sampleRate / 4 bounds latency and memory. Completion handlers decrement the queued-frame counter.

Audio starts after core load and stops during native shutdown. The architecture does not call vkQueueWaitIdle or tie audio production to display v-sync. However, current metrics do not expose underruns, callback duration, or audio queue depth over time; audio stability beyond the smoke path remains an evidence gap.

### 9.2 Web audio

AudioPipeline.snapshot identifies EmulatorJS as the audio owner, uses a core clock, and returns underruns=null because AN3 has no direct audio callback telemetry. No AudioWorklet code exists. Audio is explicitly not advanced from requestAnimationFrame, so a blocked UI frame does not intentionally become the audio clock.

## 10. Save System

### 10.1 Native raw states

The Objective-C++ host calls optional libretro serialization symbols only when all required symbols are present. It writes raw serialized bytes to save_path/states/<rom_id>.slot<slot>.state, with slots 1–4. kMaxQuickStateBytes is 512 MiB. Writes use a temporary file, flush/sync, and atomic rename. Reads validate size and pass the original bytes back to the core. No wrapper header, JSON metadata, or format conversion is introduced.

### 10.2 Browser states

SaveStateManager exports/imports the EmulatorJS game manager’s raw state bytes. QuickSaveManager stores five browser slots in IndexedDB database an3-arcade-save-slots, object store states, key format <slug>:slot:<n>, and Blob MIME application/octet-stream. This format is separate from the native raw-state path but is not changed by the native refactor.

### 10.3 Persistence and failure behavior

Native file operations are atomic and scoped to the app-data directory. Browser state errors are surfaced through player UI and do not block the render loop. Server library metadata and ROM files are separate from emulator state; no server-side save-state API was found.

## 11. ROM and Library System

### 11.1 Server upload/import

app.py:287-379 defines system extension maps and infer_system. It uses extension and filename hints; generic extensions are not deep-scanned beyond supported ZIP inspection. prepared_browser_rom extracts exactly one raw GB/GBA file from a ZIP for browser use while retaining NDS ZIP originals. Upload finalization (:2367-2432) validates extension/size, auto-detects when requested, atomically replaces the ROM, clears prepared artifacts, and updates SQLite metadata.

Upload sessions support chunked PUT/direct upload with an 8 MiB chunk size and a 24-hour TTL. The configured maximum ROM size is 8 GiB. The server supports range downloads for large assets.

### 11.2 Native import

lib.rs:539-603 canonicalizes the selected local file, rejects empty files and unsupported archives, detects system from extension/header, copies through a .part file into private an3-roms, syncs, and renames atomically. Native supported extensions include GBA (gba, raw), NDS (nds), and decrypted/launchable 3DS-style (3ds, 3dsx, z3dsx, elf, axf, cci, zcci, cxi, zcxi, app). ZIP and CIA are intentionally rejected by the in-app native importer until an installer/extractor exists.

Header probes check 3DS NCSD/NCCH magic around offset 0x100, the GBA header byte at 0xb2, and NDS ARM9 offset/size range validity. The detector returns a canonical system and extension; it does not alter ROM bytes.

### 11.3 Browser offline library

offline.js stores game records in IndexedDB database an3-arcade-offline and ROM bytes in OPFS directory an3-arcade-roms when available. It supports native URLs/paths/file handles, browser file detection, ZIP central-directory inspection, single-system inference, and large 3DS NCSD declared-length trimming. Native integrated cards call the Tauri pick_and_import_native_rom command on desktop; Android retains a legacy bridge path. There is no automatic upload to the server from the native app.

## 12. UI, Fullscreen, and Layout

### 12.1 Player layering

The player-layer contract defines the base game canvas, #tvPad at a high touch z-index, HUD/toolbars, and modal panels. Toolbar/menu actions precede virtual controls; shared site-shell selectors must not be applied to game/touch geometry. This protects NDS coordinate mapping and fullscreen behavior.

### 12.2 Native shell controls

The native AppKit view provides Menu and Pad controls, game buttons A/B/X/Y/L/R/Start/Select, NDS Lock cursor, 3DS circle pad, touch surface, fullscreen/window controls, and quick save/load slots. The Menu exposes system/layout and custom key mapping actions without owning save-state serialization logic.

### 12.3 Fullscreen and resize

Browser fullscreen calls the Fullscreen API and listens for resize/fullscreenchange to recalculate pads and DS layout. Native fullscreen is handled by the AppKit window and triggers swapchain extent checks. If a running NDS/3DS core cannot safely change orientation/layout, the UI asks for restart instead of mutating active core state.

### 12.4 Offline/native frontend

native-offline/web/index.html loads local site.css, native.css, native-bootstrap.js, offline.js, player-runtime.js, and player.js. The packaged app serves them from the embedded Tauri distribution/local runtime. Native desktop cards expose integrated GBA/NDS/3DS launch; no external emulator chooser is shown.

## 13. Build System and Exact Commands

### 13.1 Browser/server checks

Commands run during this inspection:

~~~sh
PYTHONPYCACHEPREFIX=/tmp/an3-inspection-pycache python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/an3-inspection-pycache python3 -m py_compile app.py
node --check static/player-runtime.js
node --check static/player.js
bash -n deploy-stage.sh deploy/update-staging.sh deploy/update-production.sh \
  deploy/backup-production-current.sh deploy/rollback-production.sh \
  tools/android/*.sh
git diff --check
~~~

### 13.2 Native app commands

From native-offline/:

~~~sh
npm install
npm run check
npm run build:macos
~~~

npm run check runs the fetch-script checks, web preparation, and native bootstrap checks. The package build prepares Azahar, mGBA/melonDS, MoltenVK, and web assets before invoking Tauri. The macOS build uses MACOSX_DEPLOYMENT_TARGET=13.4 tauri build --bundles app; scripts/package-macos.sh signs the app/dylibs ad hoc and creates/verifies the DMG.

Additional package scripts exist for dev, Windows, Debian, Android initialization/build, and iOS initialization/build. They were not treated as successful builds unless explicitly run and evidenced.

### 13.3 Rust tests

~~~sh
(cd native-offline/src-tauri && MACOSX_DEPLOYMENT_TARGET=13.4 cargo test)
~~~

The current inspection result was 4 passed, 0 failed, and 0 doctests.

### 13.4 Staging package/update commands

The documented staging flow is:

~~~sh
deploy/package-staging.sh
deploy/update-staging.sh <package-or-release-input>
curl --fail --silent http://192.168.1.8:8092/health
deploy/rollback-staging.sh <validated-release-directory>
~~~

The update wrapper computes the asset hash, installs a timestamped release, switches current, restarts only an3-arcade-staging.service, polls the staging health endpoint, and restores the previous symlink on failure. The dangerous deploy/rebuild-staging.sh is a separate explicit data-rebuild tool and was not run.

## 14. Dependencies, Versions, and Licenses

### 14.1 Native application

| Dependency | Version/pin | Role | License/evidence |
|---|---|---|---|
| Tauri | 2.x; CLI ^2.10.0 | Desktop shell/WebView/commands | Cargo/npm manifests; upstream license not duplicated here |
| Rust | project toolchain; gateway requires 1.88 | Native bridge and presenter | Cargo.toml/lock files |
| mGBA libretro | 0.11-219-e31759b | GBA core | MPL-2.0, verified by fetch script |
| melonDS DS libretro | 1.3.1 | NDS core | GPL-3.0-or-later, verified by fetch script |
| Azahar libretro | 2126.0 | 3DS core | GPL-2.0-or-later, verified by fetch script |
| MoltenVK | 1.4.2 | Vulkan-to-Metal translation | Apache-2.0, verified by fetch script |
| Apple frameworks | macOS 13.4 minimum | AppKit, AVFoundation, Metal, MetalKit, QuartzCore, CoreVideo | Apple SDK frameworks |

native-offline/src-tauri/Cargo.toml uses include_dir, serde, tauri, tauri-plugin-dialog, cc, and tauri-build. Exact resolved transitive versions are in lock files and were not expanded here beyond runtime-relevant pins.

### 14.2 Web/server

The server is Python standard-library oriented with SQLite. EmulatorJS runtime assets are fetched/packaged by prepare-web.mjs from the configured CDN/staging origin and served under versioned paths. The browser uses standard IndexedDB, OPFS, Fullscreen, Pointer Events, WebGL capability probes, and WASM support.

### 14.3 Optional Rust services

rust-gateway/Cargo.toml describes an3-rust-gateway 0.1.0, Rust 1.88, MIT, Axum 0.7.9, reqwest 0.12.7 with rustls, Redis 0.27.6, Tokio 1.40, Serde/JSON, SHA-2, and tracing. The netplay relay is a separate staging-only Rust/Socket.IO component pinned to a documented upstream commit. Neither optional service was observed listening in the current staging check.

### 14.4 Supply-chain verification

The fetch scripts pin archive/core/license hashes for Azahar, mGBA/melonDS, and MoltenVK before packaging. tauri.conf.json includes pinned native dylib manifests and third-party notices. This inspection did not alter or regenerate those assets.

## 15. Staging Deployment

### 15.1 Observed topology

Read-only staging checks showed:

- Host name: debian.
- Service: an3-arcade-staging.service, active and enabled since 2026-09-07 11:29:53 +07.
- Main process: /usr/bin/python3 /opt/an3-arcade-staging/current/app.py.
- Current release: /opt/an3-arcade-staging/releases/20260907-112953-6a70df830ac0.
- Listener: 192.168.1.8:8092; the service intentionally does not bind 127.0.0.1:8092.
- Service resource snapshot: 6 tasks, approximately 38.2 MiB current memory, 1.239 seconds CPU at the check.
- Health from the bound staging address: {"ok":true,"environment":"staging","asset_version":"6a70df830ac0",...}.

The loopback health probe failed because the service is bound to the LAN staging address, not because the service was unhealthy. No staging gateway listener on the optional 18093 port was observed.

### 15.2 Release flow

deploy/update-staging.sh creates a source-only package/release, computes the static asset version, installs it below /opt/an3-arcade-staging/releases/, sets ownership and the current symlink, restarts only the staging systemd unit, and polls the staging health endpoint. It maintains current.next/previous-release information for recovery. deploy/rollback-staging.sh validates that a requested release lies directly under the staging releases directory, switches the symlink, restarts the same unit, and reverts if health fails.

### 15.3 Health and headers

During this inspection:

- /health returned HTTP 200 and the staging JSON above.
- /offline returned COOP same-origin, COEP require-corp, CORP same-origin, Cache-Control no-store, and the player CSP.
- Versioned player-runtime.js (10,136 bytes) and player.js (92,955 bytes) returned HTTP 200 with immutable caching.
- EmulatorJS loader.js returned HTTP 200 with immutable caching and range support.

### 15.4 Production separation

Repository deployment files describe production as a separate service/port and public reverse-proxy target. This inspection did not request production HTTP, inspect production data, restart production, package production, or run the production deployment script. The staging-only scope remains a hard boundary.

## 16. Network Architecture

### 16.1 HTTP routes

The Python handler serves public pages, /api/library-version, authentication/account routes, /offline, /download-app, /core-preload/<system>, /game/<slug>, /play/<slug>, /service-worker.js, versioned static/core assets, ROM/media files, /health, and staging-only source/release download routes. POST handlers cover auth, ratings, favorites, comments, reports, uploads, administrative operations, and enrichment proposals.

### 16.2 Browser asset and ROM transport

Static and EmulatorJS assets are served same-origin or through the configured CDN proxy/cache. ROM downloads support HTTP Range. The service worker uses network-first navigation with cached shell fallback and bypasses cache handling for ROM/API requests that must remain current or private.

### 16.3 Native local communication

Desktop Tauri starts a local runtime server on 127.0.0.1:38471 (NATIVE_RUNTIME_PORT) backed by embedded dist, then navigates the app window to that runtime. The runtime serves assets and private native ROM URLs under /_an3/rom/. Mobile uses WebViewAssetLoader and does not expose the desktop loopback server.

### 16.4 Optional relay/gateway

The optional Rust shadow gateway is configured only when AN3_GATEWAY_UPSTREAM is supplied and is designed for staging loopback port 18093. The optional netplay relay listens on staging LAN port 8094, with origin allowance passed only when the staging origin variable is configured. No production relay is enabled by these files. No WebRTC implementation was verified in the current AN3 source.

### 16.5 Headers and isolation

The Python handler emits CSP, COOP, CORP, nosniff, Permissions-Policy, Referrer-Policy, and X-Frame-Options. Player pages receive the stronger COEP requirement needed for threaded WASM/SAB profiles. The native Tauri configuration mirrors COOP/COEP/CORP and allows the packaged WASM/CSP requirements.

## 17. Security Boundaries

### 17.1 Trust boundaries

    Internet/browser
      -> HTTP handler + rate limits + CSRF/session checks
      -> SQLite/filesystem data root

    Native user-selected file
      -> canonicalization/extension/header validation
      -> private app-data ROM store
      -> in-process libretro dylib

    Player WebView
      -> same-origin local runtime (desktop)
      -> Tauri command allowlist and scoped asset path

### 17.2 Input and upload validation

Server upload size, extension, chunk size, TTL, and atomic finalization are enforced in app.py. ZIP extraction rejects ambiguous/multiple unsupported content according to system rules. Native import canonicalizes paths, rejects traversal/empty files, uses a private destination, and writes through a temporary suffix before rename. UUID-like native ids are strictly validated in Rust.

### 17.3 Web security

Sessions use secure cookie/CSRF logic in app.py; auth prefers scrypt with PBKDF2 fallback for legacy records. Public static/core/ROM/health routes avoid unnecessary session lookup. CSP and cross-origin isolation headers are route-specific. The exact auth pepper, bootstrap admin values, cookie values, and other secret configuration are intentionally not documented.

### 17.4 Native dynamic libraries

The native host loads only bundled/pinned core and MoltenVK paths or a documented development fallback. It does not search for arbitrary external emulator applications. The Tauri asset scope limits native ROM serving to the app-data ROM directory. The remaining risk is inherent native dylib execution; packaging hashes/manifests and ad-hoc code signing provide integrity evidence but not notarization.

## 18. Tests and Validation

### 18.1 Commands run in this inspection

| Command/check | Result |
|---|---|
| python3 -m unittest discover -s tests -v with isolated pycache | **PASS** — 49 tests passed |
| python3 -m py_compile app.py | **PASS** |
| node --check static/player-runtime.js | **PASS** |
| node --check static/player.js | **PASS** |
| (cd native-offline && npm run check) | **PASS** |
| (cd native-offline/src-tauri && MACOSX_DEPLOYMENT_TARGET=13.4 cargo test) | **PASS** — 4 passed, 0 failed, 0 doctests |
| git diff --check | **PASS** |
| bash -n deployment/Android scripts | **PASS** |
| DMG stat/SHA-256 | **PASS** — 42,214,995 bytes; SHA-256 9b918342b755ab19781ccc86787b4c7c58955e29166f9fa4022e3d4ed53e63f3 |
| hdiutil verify DMG | **PASS** |
| codesign --verify --deep --strict --verbose=2 EmulatorRust.app | **PASS** — valid on disk/designated requirement |
| Staging curl /health | **PASS** — HTTP 200, staging JSON |
| Staging SSH key preflight | **PASS**; key material itself is not recorded here |

### 18.2 Browser smoke evidence

Current inspection navigation loaded http://192.168.1.8:8092/core-preload/gba?renderer=webgpu in the Codex in-app browser. The automation DOM/accessibility surface was sparse and a read-only page evaluation failed because document.createElement was unavailable in that sandbox. Therefore this inspection does **not** claim current-run player Ready. The latest prior handoff (18, dated 2026-09-07) records both WebGPU-preference and WebGL2-preference preload routes reaching Ready with no page error; that is historical evidence and should be rerun in a full browser harness.

### 18.3 Not tested or not measurable here

- Real-ROM GUI gameplay on macOS was not executed in this inspection because the available GUI automation was locked down.
- No long-run native soak was run.
- No current-run FPS/latency benchmark was run; historical benchmark figures are clearly labeled in sections 5 and 19.
- CPU utilization, resident memory over time, T_emulate, and native audio underrun counts are not currently exposed by the metrics interface.
- No independent WebGPU/WebGL2 custom texture upload test exists in AN3 because those backends are not implemented.
- No verified gamepad-specific test or 3DS network-emulation test was found.

## 19. Performance-Critical Paths

| Target | Emulation | Video path | Main cost/risk | Current evidence |
|---|---|---|---|---|
| GBA native | mGBA retro_run | software frame -> mapped staging -> buffer-to-image -> blit/present | CPU core plus one GPU copy; direct mapped write conditional | Historical real-core ~59.72 FPS, zero drops |
| NDS native | melonDS retro_run | software frame -> mapped staging -> buffer-to-image -> blit/present | software dual-screen composition and touch/input latency | Historical real-core ~59.87 FPS, zero drops |
| 3DS native | Azahar retro_run | native Vulkan image/semaphores -> blit/present | GPU workload and synchronization; no CPU readback | Historical real-core ~58.47 FPS, no software uploads |
| GBA web | EmulatorJS WASM | EmulatorJS-owned WebGL/canvas | WASM/core plus browser compositor; AN3 does not upload | Current AN3 custom renderer not implemented |
| NDS web | EmulatorJS WASM | EmulatorJS canvas + pointer bridge | touch mapping, threaded core isolation, browser scheduling | Historical preload Ready only; no frame telemetry |
| 3DS web | EmulatorJS/Azahar profile | EmulatorJS WebGL/WebGL2 canvas | high GPU/WASM demand, threaded/SAB prerequisites | webgl2Required profile; no custom WebGPU |

### 19.1 Historical native benchmark

The latest prior handoff recorded a mock direct-frame AppKit harness over four seconds: 237 frames (59.25 FPS), 237 direct frames, zero copied/converted/dropped frames, state save/load 1/1, upload p95/p99 195/208 microseconds, and present p95/p99 305/325 microseconds. Ring-size measurements were approximately 59.72 FPS with zero drops for both ring 2 and ring 3; ring 3 had slightly lower upload p95 but no material throughput gain. These numbers are not new measurements from this inspection and should not be interpreted as a production workload guarantee.

### 19.2 What the optimization changes actually remove

For GBA/NDS native, the optimization removes an avoidable CPU-side intermediate copy when the core ABI can write directly to a mapped slot. It does not remove the required GPU transfer from host-visible staging memory into the device-local image. Reusable resources remove descriptor/image/buffer creation churn. The bounded ring overlaps safe CPU/GPU work but can wait at slot reuse to control latency. For 3DS, the important optimization is preserving the native GPU image/semaphore path and avoiding readback/re-upload entirely.

## 20. Current Optimization Status

| Optimization/requirement | Status | Evidence/qualification |
|---|---|---|
| Persistent mapped software upload memory | **YES** | SoftwareFrameSlot maps host-visible coherent staging memory once and reuses it. |
| Direct core write into upload memory | **PARTIAL** | Used only when pointer, pitch, format, and capacity exactly match; ABI support is conditional. |
| Reuse textures/images/buffers in steady state | **YES** | Creation is init/resize/format/capacity/recovery only. |
| Avoid per-frame Vulkan pipeline creation | **YES** | No per-frame pipeline creation found. |
| Avoid vkQueueWaitIdle per frame | **YES** | No call/string found. |
| Avoid vkDeviceWaitIdle per successful frame | **YES** | Calls are resize/reconfiguration/error/shutdown paths only. |
| Bounded 2–3 frame ring | **YES** | Compile-time 2–3 bound, default 2. |
| Triple buffering selected by benchmark | **PARTIAL** | Ring 3 measured historically but no material gain; default remains 2. |
| 1–2 frames in flight / low latency | **PARTIAL** | Two-slot default and fence reuse provide a bound; exact platform latency not continuously measured. |
| Correct source/destination barriers | **YES** | Explicit barriers around upload/blit/present and hardware source semaphores. |
| Native 3DS no GPU-to-CPU-to-GPU copy | **YES** | Hardware image path; no software upload count for historical 3DS run. |
| WebGPU backend | **NO** | Only capability probe and safe fallback. |
| WebGL2 explicit reusable texture upload | **NO** | AN3 has no texStorage2D/texSubImage2D upload loop; EmulatorJS owns canvas. |
| SAB framebuffer ring | **NO** | Isolation/SAB capability is probed, no ring implementation. |
| Render Worker/OffscreenCanvas | **NO** | No AN3 worker/offscreen construction. |
| AudioWorklet pipeline | **NO** | No AudioWorklet code. |
| Audio independent of rAF | **YES** | EmulatorJS owns audio; AN3 does not schedule it from rAF. |
| Native frame-time telemetry | **PARTIAL** | Upload/present p95/p99 exist; emulate/CPU/memory/audio underruns do not. |
| Web dropped-frame telemetry | **UNVERIFIED** | Runtime field is nullable and no current-run renderer drop count was observed. |

## 21. Technical Debt and Risks

### P0 — release-blocking or correctness-critical

1. **WebGPU preference is not a WebGPU renderer.** Evidence: VideoBackend.resolve probes navigator.gpu but never creates an adapter/device/queue/texture. Impact: a user selecting ?renderer=webgpu still depends on EmulatorJS’s WebGL/canvas path. Direction: implement and test a real backend or clearly expose capability/fallback state.
2. **Worker/SAB architecture is absent from AN3.** Evidence: no new Worker, OffscreenCanvas, or Atomics. Impact: UI responsiveness and large-frame-copy goals are not met by the repository itself. Direction: design explicit ownership and synchronization before claiming the target architecture.

### P1 — high impact

1. **Native metrics omit core and audio timing.** Evidence: VulkanMetrics has upload/present p95/p99 but no T_emulate, CPU, memory, or underruns. Impact: optimization decisions cannot be validated end-to-end. Direction: add opt-in telemetry and repeat real-ROM/long-run tests.
2. **Native presenter can block core work at bounded fence reuse.** Evidence: prepare_presentation_frame and swapchain image reuse wait on fences. Impact: GPU stalls can increase input latency even though queue growth is bounded. Direction: measure and tune ring/in-flight policy with latency data.
3. **Native importer rejects ZIP/CIA 3DS workflows.** Evidence: import_native_rom rejects those suffixes. Impact: users need decrypted/accepted formats and cannot install packaged CIA content in-app. Direction: specify a safe installer/extractor boundary before adding support.
4. **Gamepad support is not independently wired or validated.** Evidence: no dedicated Gamepad API/native HID path in inspected AN3 files. Impact: controller compatibility is uncertain. Direction: document EmulatorJS ownership or add an explicit adapter/test.

### P2 — medium impact

1. **Browser frame-drop metric is nullable.** Evidence: FramePacingMonitor.droppedFrames remains null without owner telemetry. Impact: web pacing regressions are hard to quantify.
2. **Native audio queue has a bound but no underrun counter.** Evidence: queued-frame atomic exists; no underrun metric. Impact: audio stability can regress unnoticed.
3. **Desktop browser smoke automation is limited.** Evidence: current in-app browser DOM evaluation failed. Impact: staging player readiness needs a fuller browser harness.
4. **Optional Rust gateway/netplay services are configuration-heavy and not part of the default staging process.** Evidence: explicit upstream/environment requirements and no active listener in current ss output. Impact: operators may confuse available files with active services.

### P3 — maintenance/documentation

1. Existing handoffs contain historical paths/asset versions. Impact: readers can mistake old values for current deployment state. Direction: always label historical evidence and refresh the current handoff after release.
2. Native and browser save stores are intentionally separate but this is easy to miss. Impact: users may expect cross-device save synchronization. Direction: keep the boundary explicit in product documentation.
3. Ad-hoc macOS signing is valid for local/staging distribution but not notarized release distribution. Direction: define a future signing/notarization process outside Phase 1.

## 22. Recommended Architecture

### 22.1 Current architecture to preserve

    EmulatorSession / native host
      -> EmulatorCore (libretro or EmulatorJS owner)
      -> VideoSource (software or native GPU)
      -> VideoBackend (VulkanFrontend on macOS; canvas owner on web)
      -> InputRouter / AppKit input
      -> AudioPipeline / AVAudioEngine or EmulatorJS audio
      -> SaveStateManager / QuickSaveManager

Keep save-state serialization, input policy, and library logic outside the renderer. Keep GBA/NDS software uploads and 3DS hardware images behind the same source/presenter contract. Keep native ROMs private and staging deployment isolated.

### 22.2 Future web architecture

~~~mermaid
flowchart LR
    UI[Main thread UI/input] --> IR[InputRouter]
    IR --> SABIn[Atomics/input mailbox]
    SABIn --> EW[Emulator Worker/WASM]
    EW --> VRing[SAB latest-frame ring]
    VRing --> RW[Render Worker]
    RW --> WG[WebGPU preferred]
    RW --> GL[WebGL2 fallback]
    EW --> AW[AudioWorklet ring]
    AW --> AudioOut[Audio output]
    UI --> Persist[Save/library persistence]
~~~

The future design should allocate textures/buffers/pipelines once per renderer/device, publish only the newest completed frame, handle resize through a versioned control message, and preserve a safe non-SAB fallback. It must retain EmulatorJS compatibility where a core cannot expose a raw framebuffer.

### 22.3 Future native backends

The VideoSource/VideoBackend boundary is suitable for direct Metal, OpenGL fallback, Windows/Linux/Android Vulkan, and iOS Vulkan-to-Metal. Phase 1 intentionally does not implement those backends.

## 23. Future Readiness

| Future target | Readiness | Basis/remaining work |
|---|---|---|
| iOS Vulkan-to-Metal | Partial | MoltenVK abstraction exists; Tauri/iOS scripts exist; AppKit/AVFoundation host is macOS-specific. |
| Windows Vulkan | Partial | Backend boundary is clean; no Windows presenter/core packaging verified. |
| Linux Vulkan | Partial | Same abstraction; no Linux surface/device tests in this inspection. |
| Android | Partial | WebView/legacy bridge and scripts exist; no current device runtime evidence. |
| OpenGL fallback | Planned | No backend implementation found. |
| Cloud saves | Planned | Native/browser/server stores are separate; no sync API. |
| Save synchronization | Planned | Raw formats are preserved locally; conflict/auth protocol absent. |
| LAN/WebRTC | Partial | Staging Socket.IO relay files exist; no verified WebRTC or 3DS network emulation. |
| Nintendo Switch | Unverified/planned | No target-specific build or legal/runtime boundary inspected. |
| GPU-heavy future cores | Partial | NativeGpuFrame contract and native Vulkan presenter are prepared; per-core negotiation still required. |

## 24. Important File Index

| File | Why it matters |
|---|---|
| /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/app.py | Server routes, schema, upload/detection, headers, metrics |
| static/player-runtime.js | Session/core/video/input/audio/save abstractions |
| static/player.js | EmulatorJS boot, cores, touch, fullscreen, state UI |
| static/offline.js | Browser/native ROM/library integration |
| static/service-worker.js | PWA and EmulatorJS cache policy |
| native-offline/src-tauri/src/lib.rs | Tauri commands, local server, native import/path validation |
| native-offline/src-tauri/src/azahar.rs | Core registry, MoltenVK/core path, FFI orchestration |
| native-offline/src-tauri/src/azahar_host.mm | libretro host, AppKit input, audio, state, view layout |
| native-offline/src-tauri/src/vulkan_frontend.h | Renderer abstraction and metrics interface |
| native-offline/src-tauri/src/vulkan_frontend.mm | Vulkan/MoltenVK lifecycle, upload ring, sync, presentation |
| native-offline/src-tauri/tauri.conf.json | Product identity, CSP/isolation, bundle scope, macOS minimum |
| native-offline/src-tauri/build.rs | Objective-C++/framework/compiler/link configuration |
| native-offline/scripts/fetch-azahar-libretro.mjs | Azahar pin/hash/license verification |
| native-offline/scripts/fetch-gba-nds-libretro.mjs | mGBA/melonDS pin/hash/license verification |
| native-offline/scripts/fetch-moltenvk.mjs | MoltenVK pin/hash/license verification |
| native-offline/scripts/prepare-web.mjs | Packaged web/runtime asset assembly |
| native-offline/tests/native_smoke.mm | Native smoke harness and privacy-safe metrics |
| native-offline/tests/mock_direct_frame_core.cpp | Direct mapped framebuffer test core |
| deploy/package-staging.sh | Source-only staging package |
| deploy/update-staging.sh | Staging release install/switch/health/recovery |
| deploy/rollback-staging.sh | Staging-only rollback |
| deploy/staging | systemd unit for staging |
| docs/native-offline.md | Native product scope and user interactions |
| docs/player-layering.md | Player z-index/input/layout contract |
| docs/staging.md | Staging endpoint and operational safety |
| docs/netplay-staging.md | Optional staging relay boundary |
| reports/handoff/18-emulatorrust-0.4.3-phase1-macos-web-staging-2026-09-07.md | Prior Phase 1 implementation/benchmark evidence |

## 25. Evidence and Traceability

### 25.1 Native source ranges

- native-offline/src-tauri/src/lib.rs:1-29 — local runtime port and embedded distribution.
- native-offline/src-tauri/src/lib.rs:70-191 — extension allowlist, header detection, declared-length/copy helpers.
- native-offline/src-tauri/src/lib.rs:193-537 — local runtime HTTP serving, range handling, COOP/COEP/CORP/CSP.
- native-offline/src-tauri/src/lib.rs:539-669 — native ROM import/list/remove.
- native-offline/src-tauri/src/azahar.rs:13-47 — pinned GBA/NDS/3DS core registry.
- native-offline/src-tauri/src/azahar.rs:115-168 — MoltenVK/core path resolution.
- native-offline/src-tauri/src/azahar.rs:287-423 — native start/stop/input orchestration.
- native-offline/src-tauri/src/azahar_host.mm:206-280 — libretro ABI resolver and optional state symbols.
- native-offline/src-tauri/src/azahar_host.mm:286-429 — start/stop and hardware/software renderer initialization.
- native-offline/src-tauri/src/azahar_host.mm:440-499 — raw serialized state save/load and atomic files.
- native-offline/src-tauri/src/azahar_host.mm:501-630 — atomic input and NDS touch/cursor mapping.
- native-offline/src-tauri/src/azahar_host.mm:683-852 — libretro environment negotiation, video callbacks, input reads.
- native-offline/src-tauri/src/azahar_host.mm:889-985 — audio queue and keyboard mapping.
- native-offline/src-tauri/src/azahar_host.mm:989-1475 — AppKit controls, fullscreen, NDS lock/Escape, 3DS touch/pad.
- native-offline/src-tauri/src/vulkan_frontend.mm:137-305 — presenter state, ring, software slots, metrics.
- native-offline/src-tauri/src/vulkan_frontend.mm:328-596 — MoltenVK, Vulkan instance/device/queue setup.
- native-offline/src-tauri/src/vulkan_frontend.mm:760-872 — persistent-mapped software resource creation/reuse.
- native-offline/src-tauri/src/vulkan_frontend.mm:874-1013 — swapchain creation/recreation.
- native-offline/src-tauri/src/vulkan_frontend.mm:1130-1288 — hardware image receive and bounded drain path.
- native-offline/src-tauri/src/vulkan_frontend.mm:1294-1485 — software upload/direct path and recovery.
- native-offline/src-tauri/src/vulkan_frontend.mm:1487-1691 — shared submit/present/barrier path.
- native-offline/src-tauri/src/vulkan_frontend.mm:1709-1768 — metrics/sync wrappers.

### 25.2 Web source ranges/contracts

- static/player-runtime.js:1-286 — EmulatorSession, VideoSource, VideoBackend, InputRouter, save/quick-save, audio and frame pacing.
- static/player.js — primary core map, capability probe, EmulatorJS options, state UI, virtual pads, NDS touch, fullscreen.
- static/offline.js — IndexedDB/OPFS, ZIP/header inference, native picker bridge.
- static/service-worker.js — shell/core caches and navigation/ROM fetch policy.
- native-offline/web/native-bootstrap.js — desktop integrated native systems and Tauri launch bridge.
- native-offline/web/index.html — packaged native front-end asset order.

### 25.3 Server/deployment evidence

- app.py:27-120 — directories, limits, environment, staging netplay origin.
- app.py:287-510 — system detection, ZIP preparation, EmulatorJS proxy cache.
- app.py:515-652 — SQLite schema and migrations.
- app.py:659-715 — authentication hashing/bootstrap boundary.
- app.py:1538-2000 — handler headers, static/range/routes/health.
- app.py:2002-2605 — POST APIs, upload finalization/chunks/proposals.
- deploy/update-staging.sh — release switch, service restart, health rollback.
- deploy/rollback-staging.sh — validated staging rollback.
- deploy/rebuild-staging.sh — explicit data rebuild; not executed.
- deploy/staging — staging systemd unit.
- docs/staging.md and docs/operations.md — documented staging topology and safety rules.

### 25.4 Live staging evidence

Read-only checks performed against staging showed the URL, health JSON, response headers, current release symlink, active systemd unit, process command, service memory/CPU snapshot, and listener binding recorded in sections 1 and 15. The staging SSH preflight returned STAGING_SSH_KEY_AUTH=PASS; no key path contents or credential material are included.

## 26. Unknowns and Final Consistency Pass

### 26.1 Explicit unknowns

1. Whether a particular EmulatorJS release internally creates workers or uses OffscreenCanvas is not established by AN3 source; this handoff only claims that AN3 does not create or control those objects.
2. Browser WebGPU availability on a user’s device is not proof that the AN3 WebGPU backend exists; current code falls back.
3. Exact real-ROM CPU utilization, memory peak, T_emulate, frame latency, and audio underrun rates require a telemetry-enabled long-run run.
4. Gamepad behavior may exist inside EmulatorJS but was not independently verified in this inspection.
5. No 3DS network-emulation compatibility claim is made.
6. Mobile Android/iOS runtime behavior was not device-tested in this inspection.
7. Optional Rust gateway/netplay files describe deployable components but current staging listener evidence did not show them active.
8. Historical benchmark values are not a substitute for a current release benchmark.

### 26.2 Consistency and safety checks completed

- Repository path, branch, and HEAD were captured from the current checkout.
- Dirty working-tree state was preserved; no reset/checkout/clean operation was used.
- Critical source paths cited above exist in the repository.
- The output path is the only file intentionally added by this inspection.
- No source code, build configuration, staging release, service, production asset, or production data was modified.
- No inventory-only heading was added.
- No SSH private key, password, token, cookie, OAuth secret, auth pepper, or signing secret is present in this document.
- Claims marked historical, partial, planned, unverified, or unknown are not presented as current successful tests.
- Native vkQueueWaitIdle absence and the three non-hot-path vkDeviceWaitIdle call sites were checked by exact source search.
- WebGPU/worker/SAB/AudioWorklet absence was checked by source search rather than inferred from documentation alone.

### 26.3 Handoff conclusion

Phase 1’s native macOS renderer hardening is materially implemented for the documented GBA/NDS software and 3DS native-GPU paths: resources are reusable, software upload memory is persistently mapped, the frame ring is bounded, synchronization is explicit, and successful frames avoid queue/device idle waits. The staging deployment is healthy and isolated. The web abstraction layer is clean enough to host future worker/WebGPU/WebGL2 backends, but those backends are not yet implemented by AN3 and must not be claimed as complete until they are built and tested. The next evidence-producing step is a real-ROM macOS and browser-harness run that records end-to-end timing, frame pacing, audio underruns, and input latency without touching production.

## 27. Phase 1 completion addendum — 2026-09-07

This addendum is authoritative for the Phase 1 implementation and staging verification below. Sections above describe the pre-change inspection state and are retained as historical context.

### 27.1 What is now implemented

- The native Vulkan/MoltenVK renderer was not rewritten. Persistent mapped staging, the bounded two-slot default ring, explicit semaphore/fence/barrier synchronization, the native 3DS Vulkan image path, and the existing no-per-frame-wait-idle behavior remain intact.
- Native host telemetry was added without hot-path logging: T_emulate samples with p95/p99, audio queue depth/max depth, underrun/overrun counters, presented/dropped/direct/copied/converted counts, and getter-time Mach RSS/CPU user/system snapshots. The audio underrun value is explicitly a queue-drain estimate because the current AVAudioEngine integration does not expose a reliable callback counter.
- `static/renderer-worker.js` is a real renderer bridge. It owns an OffscreenCanvas when available, tries WebGPU first for the requested default, and falls back to a reusable WebGL2 backend. The WebGPU backend creates an adapter/device/context, reusable texture/sampler/shader/pipeline state, and uses `copyExternalImageToTexture`; the WebGL2 backend allocates its texture/program once and uses `texStorage2D` where supported plus `texSubImage2D` per frame.
- Frame transport is bounded and latest-frame-wins. The source canvas remains EmulatorJS-owned; completed frames are copied into `ImageBitmap` objects for the presenter. AN3 does not claim raw framebuffer ownership, an Emulator Worker/WASM split, or a SharedArrayBuffer ring because the current EmulatorJS API does not expose a safe raw-framebuffer handoff.
- Audio remains EmulatorJS/core-owned. No AudioWorklet was introduced because doing so would risk core/audio synchronization.
- Renderer status now separates requested and effective backends. A WebGPU request is reported as WebGPU requested and WebGL2 effective when WebGPU is unavailable; it is never reported as WebGPU merely because it was requested.
- Web quick-save UI and queries now expose exactly four slots. Existing IndexedDB slot-5 records are ignored, not deleted, so existing saved data is not unexpectedly removed.

### 27.2 Requested versus effective renderer evidence

| Staging case | Requested | Effective | Presenter evidence |
|---|---|---|---|
| GBA, `?renderer=webgpu` | WebGPU | WebGL2 | OffscreenCanvas worker path active; source canvas hidden, AN3 canvas visible |
| GBA, `?renderer=webgl2` | WebGL2 | WebGL2 | OffscreenCanvas worker path active |
| NDS, `?renderer=webgpu` | WebGPU | WebGL2 | OffscreenCanvas worker path active; core reached Playing |
| 3DS, direct LAN HTTP | WebGPU | external-core-canvas | Core refused to start because the non-secure LAN origin reported no usable cross-origin isolation |
| 3DS, localhost SSH tunnel | WebGPU | external-core-canvas | The page reached core startup/Playing, but the large game-data download later failed with a network error before a canvas was exposed |

The current browser harness reported `navigator.gpu` unavailable for the LAN staging page, so no claim is made that a live frame was rendered by WebGPU. The WebGPU implementation is present and built; its effective runtime path needs a secure browser/device with WebGPU support for a direct WebGPU benchmark.

### 27.3 Current staging measurements

- Final staging asset: `5c7dd5617fd3`.
- Release: `/opt/an3-arcade-staging/releases/20260907-141024-5c7dd5617fd3`.
- Rollback target retained by the staging release helper: `9251f3e94e07`.
- Source-only staging archive SHA-256: `b062a16547a2d8d04e71b2b81e2dc55c6cd3610eb6ba124c2722465fc252b7c6`.
- GBA WebGPU-requested/WebGL2-effective smoke: approximately 60.33 FPS over a three-second counter interval (181 rendered frames), dropped frames remained 0, renderer p95 approximately 0.1 ms and p99 approximately 0.2 ms.
- GBA explicit WebGL2 smoke: approximately 61.33 FPS over three seconds (184 rendered frames); five startup drops were observed and no additional drops occurred during the measured interval; p95 approximately 0.1 ms and p99 approximately 0.2 ms.
- NDS WebGPU-requested/WebGL2-effective smoke reached `Playing`, with OffscreenCanvas active, four save slots, zero observed drops in the sample, and renderer p95/p99 approximately 0.1/0.2 ms.
- 3DS was not marked pass: the direct staging origin is HTTP and cannot provide the required secure isolated context; the localhost attempt reached core startup but failed during game-data download. This is a test limitation, not a false WebGPU/SAB claim.
- The browser harness did not expose trustworthy main-thread CPU time or memory data, and web audio queue/underrun counters remain core-owned/null. The native telemetry fields are ready for a real-ROM native run; no synthetic fixture is represented as a gameplay benchmark.

### 27.4 Tests and build evidence

Passed:

- `PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests` — 54 tests.
- JavaScript syntax checks for `static/` and `native-offline/web/`.
- Shell syntax checks for staging/operations scripts.
- `git diff --check`.
- `npm run check` in `native-offline`.
- `cargo check --manifest-path native-offline/src-tauri/Cargo.toml`.
- `cargo test --manifest-path native-offline/src-tauri/Cargo.toml` — 4 Rust unit tests passed.
- `npm run prepare-web`.
- `MACOSX_DEPLOYMENT_TARGET=13.4 npm run build` — `EmulatorRust.app` built successfully; notarization was skipped because Apple credentials were unavailable.
- Live staging browser checks for GBA, NDS, renderer requested/effective reporting, OffscreenCanvas presenter activation, and exactly four quick-save rows.

### 27.5 Remaining limitations and staging safety

The exact EmulatorJS limitation remains: its current integration does not expose a safe raw framebuffer owner or transfer API, so AN3 cannot safely move the core/WASM into an Emulator Worker or implement a SAB framebuffer ring without replacing/rebuilding the core runtime. The safe incremental maximum is the ImageBitmap-to-render-worker bridge implemented here. Audio remains EmulatorJS-owned for the same correctness reason.

Deployment was staging-only. Health returned asset `5c7dd5617fd3`; production release scripts, production services, and production data were not contacted or modified. The staging SSH preflight used the authorized key-only path and passed strict host verification. No SSH fingerprint or credential material is recorded in this handoff.

## 28. VibeCodedEmulator rename, ten slots, native state files, settings and FPS — 2026-09-07

This section is authoritative for the follow-up implementation. Scope was limited to the macOS native app and the web staging release. Production endpoints, production release scripts, production services, and production data were not accessed or modified.

### 28.1 Files changed

- Web UI/runtime: `app.py`, `static/player-runtime.js`, `static/offline.js`, `static/player.js`.
- Native app identity and packaging: `native-offline/package.json`, `native-offline/package-lock.json`, `native-offline/src-tauri/Cargo.toml`, `native-offline/src-tauri/tauri.conf.json`, `native-offline/scripts/package-macos.sh`, and the UniformTypeIdentifiers framework link in `native-offline/src-tauri/build.rs`.
- Native UI/core bridge: `native-offline/web/index.html`, `native-offline/web/native-bootstrap.js`, `native-offline/src-tauri/src/lib.rs`, `native-offline/src-tauri/src/azahar.rs`, `native-offline/src-tauri/src/azahar_host.h`, `native-offline/src-tauri/src/azahar_host.mm`, and `native-offline/src-tauri/src/vulkan_frontend.mm`.
- Regression contracts: `tests/test_integration.py`, `tests/test_native_renderer_contract.py`, `tests/test_offline_consolidation.py`, and `tests/test_phase1_renderer_contract.py`.
- This handoff was appended; earlier inspection sections remain historical context.

### 28.2 Rename and compatibility strategy

- User-facing macOS product/window/menu/About strings, native shell errors, macOS `.app` name, and DMG name are now `VibeCodedEmulator`; the artifact is `vibecodedemulator-0.4.4-macos-aarch64.dmg`.
- The bundle identifier remains `space.an3tocom.offline`. Native application-data directories and state paths remain unchanged, including `an3-roms`, `mgba`, `melondsds`, `azahar`, and the existing `states` layout.
- The browser IndexedDB database remains `an3-arcade-save-slots`, object store `states`, database version `1`, key format `<slug>:slot:<n>`, and raw Blob payload format. The native key-mapping preference key also remains `an3.native-key-mappings.v1`.
- Because these persistence identifiers were preserved, no destructive rename migration was needed. Existing ROM/library/save/settings data continues to resolve under the old stable identifiers. Other-platform placeholder filenames such as the pending Windows/Android/Linux entries remain outside this macOS/web scope and are not presented as new macOS artifacts.

### 28.3 Quick Save 1–10

- Web player markup, offline player markup, and native AppKit settings rows now expose `Slot 1` through `Slot 10`.
- Web quick saves still use the v1 IndexedDB/object-store/key format and raw state bytes. The prior hidden slot 5 is now included by the same reader; no slot is deleted, migrated destructively, or silently rewritten. Slots 6–10 use the same existing record format.
- Native quick saves still use the existing per-ROM paths `<save>/states/<rom_id>.slot<n>.state`; validation is now 1–10, with the old 1–4 paths untouched. The state bytes remain the raw core `retro_serialize` format.
- Live staging evidence: the GBA player displayed all ten slots; slot 10 saved and then loaded successfully. Source-contract tests cover slot 5 retention and the v1 database contract.

### 28.4 Native `.state` import/export

- `AzaharHost` now exposes `an3_native_export_state` and `an3_native_import_state` and uses the existing core `retro_serialize`/`retro_unserialize` APIs without an AN3 wrapper format.
- Export uses an AppKit `NSSavePanel`, defaults to `VibeCodedEmulator.state`, enforces the `.state` extension, and writes through a bounded atomic temporary-file → flush/fsync → rename path. It is independent of quick-save slots.
- Import uses an AppKit `NSOpenPanel` restricted to `.state`/`.savestate`, accepts only regular files with size greater than zero and at most 512 MiB, reports read/incompatibility errors, and never overwrites a quick-save slot.
- The native C++ build and contract tests cover these paths. A fresh real-ROM native import/export run was not available in this validation window, so cross-core GBA/NDS/3DS compatibility is a known limitation below.

### 28.5 Native settings architecture

- The AppKit menu is now a scrollable grouped settings surface with `General`, `Graphics`, `Audio`, `Input`, `Emulation`, `Save States`, and `About` sections.
- Persisted settings are limited to implemented controls: start-fullscreen preference, Show FPS, audio volume, mute, and the existing custom keyboard mapping. The renderer row reports the actual Vulkan 1.1 → bundled MoltenVK → Metal path; no fake renderer/VSync/resolution toggle was added. NDS/3DS layout text reflects the existing layout behavior, and experimental timing options remain unexposed.
- Save States contains quick-save/load rows 1–10 plus the native Import/Export actions. Existing Pad, cursor-lock, virtual-button, and library controls remain in place.
- Settings persistence is implemented with `NSUserDefaults` keys scoped to the native app and does not enter emulator state bytes.

### 28.6 Native FPS overlay

- `AN3AzaharView` reads `an3_native_presented_frames()` from the existing Vulkan presentation telemetry after each completed draw, rather than adding a synthetic timer or per-frame log.
- The overlay is off by default when no prior preference exists, is a small top-right label, updates no more often than every 0.333 seconds, and displays the backend as `%.1f FPS · Vulkan`. It does not change NDS touch coordinate conversion or input routing.
- The implementation is compiled and covered by source-contract tests. A real native gameplay FPS capture with GBA/NDS/3DS was not completed in this validation window.

### 28.7 Validation completed

Passed:

- `PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests` — 56 tests.
- JavaScript syntax checks for the changed web/native bootstrap files.
- `npm run check` in `native-offline`.
- `MACOSX_DEPLOYMENT_TARGET=13.4 cargo test --manifest-path src-tauri/Cargo.toml -- --nocapture` — 4 Rust unit tests passed; native Objective-C++ compiled.
- `git diff --check`.
- Native app bundle signature verification: `VibeCodedEmulator.app` is valid on disk and satisfies its designated requirement. `CFBundleDisplayName`/`CFBundleName` are `VibeCodedEmulator`; `CFBundleIdentifier` is still `space.an3tocom.offline`; version is `0.4.4`.
- DMG verification: `hdiutil verify` passed. Artifact size is 42,187,157 bytes and SHA-256 is `a611c95649a9b0d1d9bb56f49b9bc7a3af169052475e87280473234fddec6170`.
- Web staging health/download checks: asset `54b2e3b7750f`, release `/opt/an3-arcade-staging/releases/20260907-150423-54b2e3b7750f`, rollback target `/opt/an3-arcade-staging/releases/20260907-141024-5c7dd5617fd3`. The staging DMG endpoint returned HTTP 200, the expected content length, and the same SHA-256 as the local artifact.
- Live web staging GBA smoke (`Pokemon Emerald`) reached `Playing`; ten quick-save rows were visible; slot 10 save and load both reported success.
- Live web staging NDS smoke (`Pokémon Mystery Dungeon: Explorers of Sky`) reached `Playing`. With `?renderer=webgpu`, the page reported WebGPU requested and WebGL2 effective; the stage reported OffscreenCanvas active, 0 dropped frames, and rendered frames. The browser reported no WebGPU capability, so this is a verified fallback, not a WebGPU-rendered claim.

### 28.8 Known limitations

- No fresh native real-ROM session was run for GBA/NDS/3DS, native import/export, native settings persistence, native fullscreen, native NDS touch, physical key remapping, audio playback, or native FPS capture. The native build, C++ compile, source contracts, artifact verification, and existing native architecture checks pass, but these runtime claims remain unverified for this release.
- The web staging in-app browser exposed the fullscreen control but did not enter browser fullscreen during the smoke attempt; no fullscreen pass is claimed from that attempt. Touch controls and audio controls were present in the live player, but no perceptual hardware/audio-latency claim is made.
- WebGPU was unavailable in the current browser context. The WebGPU implementation remains present, while the tested effective path was WebGL2 fallback.
- EmulatorJS remains the owner of the web core/source canvas/audio. No SAB/raw-framebuffer/Emulator Worker ownership claim was added.
- No production deployment, production health check, production release, or production data operation was performed.

## 29. Staging quality/functionality pass — 2026-09-07

This section supersedes earlier follow-up unknowns for the checks listed here. Scope remained the macOS native staging app and the web staging source; production was not contacted or modified.

### 29.1 Implemented changes

- Native AppKit settings now include real core-announced options, persisted per-system values, audio latency and resampler controls, live audio diagnostics, Auto Save with 60/120/300-second intervals, and Load Auto Save. Auto Save uses `<save>/states/<rom_id>.autosave.state`; quick slots remain independent raw core state files 1–10.
- Native speed controls are real scheduler controls for 0.5x, 1x, 2x, 4x, and 8x. The scheduler advances bounded `retro_run()` work and audio input is resampled at the selected effective rate.
- Escape precedence is implemented as key-map capture cancellation, menu close, NDS cursor release, then return to library. The speed row moves above the bottom controls below 600 px so its buttons remain inside the native window; the volume row is width-constrained to the settings stack with a 0–100 slider and value label.
- NDS relative mouse deltas now pass through one explicit platform transform with right/down positive; absolute touch coordinates use the corresponding normalized transform. No `CGGetLastMouseDelta` or second Y inversion remains.
- Native staging signing now carries `com.apple.security.cs.disable-library-validation` for bundled ad-hoc libretro plugins and `com.apple.security.cs.allow-jit` for melonDS ARM JIT. This is staging runtime packaging configuration; no production signing or release was performed.
- Web 3DS diagnostics now record secure-context/isolation/SAB state, core-asset request metadata, ROM milestones, loader/WASM/core-load milestones, source-canvas availability, first frame, audio start, and thread-pool readiness. The page does not report 3DS playable until the source canvas, first frame, and running audio are all observed; timeout is an explicit failure.

### 29.2 Validation evidence

Passed:

- `python3 -m unittest discover -s tests -p 'test_*.py'` — 64 tests.
- `cargo test` under `native-offline/src-tauri` — 4 Rust unit tests passed; Objective-C++ native host compiled.
- `npm run check` under `native-offline`.
- `node --check static/player.js` and `git diff --check`.
- `npm run build:macos` — native app built, ad-hoc signed, DMG created, and `hdiutil verify` returned a valid checksum.
- Final app bundle deep signature verification passed. Final staging entitlements contain library validation disablement and JIT permission. Bundle resources include Azahar, MoltenVK, mGBA, and melonDS DS arm64 binaries.

Fresh native runtime evidence on the rebuilt/post-package `VibeCodedEmulator.app`:

- Local Golden Sun NDS ROM reached the native player. AX state exposed `0.5x`, `1x`, `x2`, and Lock cursor controls; the settings menu exposed ten quick slots, Auto Save, and live `Core 32728 Hz · Output 48000 Hz · Hardware 48000 Hz` diagnostics with `underrun 0 · overrun 0` at observation.
- Local Pokémon X 3DS ROM reached the native player and reported `60.1 FPS · Vulkan`; its settings menu exposed the same real core/output/hardware rates and zero underrun/overrun at observation.
- Escape was verified in sequence: with NDS settings open, first Escape closed the settings and left the game controls visible; second Escape restored the library.
- No perceptual audio-quality claim is made from accessibility inspection alone; the native queue/rate diagnostics were stable at the observed checks.

### 29.3 Web staging and deployment status

- Read-only staging health is reachable and reports `{"ok": true, "environment": "staging", "asset_version": "54b2e3b7750f"}`. This is the pre-existing staging asset, not this pass.
- The local source static asset version for this pass is `3a257e271678`.
- Deployment was not performed: `tools/ssh/check-staging-key.sh` returned `Permission denied (publickey,password)`. No archive was uploaded, no staging service was restarted, and no production path was attempted.
- Consequently, live browser 3DS runtime milestones for this pass are unverified. The source now fails honestly on non-secure/non-isolated staging rather than claiming playable 3DS; a future staging run needs the owner-authorized key-only SSH path and a secure isolated browser origin before it can claim first frame/audio/thread-pool evidence.

### 29.4 Artifact and remaining blocker

- DMG: `native-offline/releases/vibecodedemulator-0.4.4-macos-aarch64.dmg`
- DMG size: 42,218,886 bytes.
- DMG SHA-256: `799e8f32839337966774d8fc6a52ab33387eb4aabbfe8904fab584d22b8786b2`.
- Native app bundle: `native-offline/src-tauri/target/release/bundle/macos/VibeCodedEmulator.app`.
- The remaining blocker is staging SSH authorization for deployment and browser verification; native staging runtime checks and artifact verification are complete. No production claim is implied.

## 30. Staging deployment follow-up — 2026-09-07

This section supersedes the deployment blocker in section 29 after the owner supplied the authorized staging identity path. Production remains untouched.

- Key-only staging preflight passed with `STAGING_SSH_KEY_AUTH=PASS`; no key contents or credential material are recorded.
- Staging-only archive SHA-256: `8770edc93edcd74ff2ba19806ac8718f6083d1e2f557ddc23bf36ec531bc23bf`; archive size 486,760,131 bytes.
- The staging release helper completed with `STAGING_RELEASE=PASS`.
- Active release: `/opt/an3-arcade-staging/releases/20260907-171534-3a257e271678`.
- Active asset: `3a257e271678`.
- Rollback target: `/opt/an3-arcade-staging/releases/20260907-150423-54b2e3b7750f`.
- Read-only `/health` verification returned `ok: true`, `environment: staging`, and asset `3a257e271678`.
- Live staging browser verification of `/play/test-3ds-file-decrypted-pokemon-x-europe-enjafrdeesitko?debug3ds=1` reached the new player diagnostics but stopped honestly at 0% with `This core needs an isolated player page with SharedArrayBuffer.` The staging page is HTTP, so `isSecureContext`/cross-origin isolation/SAB prerequisites are unavailable. No web 3DS playable-render pass is claimed until staging is served from an approved secure isolated origin.
- No production archive, production release script, production service, production health endpoint, or production data path was contacted.

## 31. Regression stabilization pass — 2026-09-07 18:30 ICT

### 31.1 User-reported regressions

The packaged app had a landscape reset, NDS/3DS audio silence, NDS cursor lag
after the direction fix, a GBA crash, and Audio Volume slider overflow. These
were real user observations and supersede the earlier PASS-like telemetry.

### 31.2 GBA crash

The captured report `an3-offline-native-2026-09-07-171854.ips` was SIGABRT on
thread 0 while AppKit constructed an mGBA Core Options popup. Root cause was a
misdeclared libretro Core Options v2 ABI (missing categorized description/info
members, plus v2-intl treated as v1). `core_options.h` now uses the actual v2
layout and `azahar_host.mm` captures v2-intl as v2. Packaged GBA reached 60 FPS
and rendered its menu; the original abort did not recur.

### 31.3 Audio

At 1× the packaged NDS diagnostics reported core/effective 32728 Hz and
output/hardware 44100 Hz. The first repair exposed a terminal converter state
(`EndOfStream`, zero frames); the final repair uses explicit S16-interleaved to
Float32-planar conversion and `NoDataNow` between realtime batches. Packaged
NDS then reported converter failures 0, status InputRanDry, player/engine
running and scheduled output queue. Bounded metrics record peak/non-zero data.
The selected title's first bounded callback snapshot was silent (peak/nonzero
zero), so this document makes no unsupported perceptual-speaker claim; a human
must still listen to gameplay for GBA/NDS/3DS and exercise speed transitions.

### 31.4 Layout

`an3.native-screen-layout.v1.<system>` is now read without writes and defaults
to the historical Side-by-Side layout. NDS/3DS launch receives `preserve` from
the web bridge; melonDS's launch value is marked updated and GET_VARIABLE
returns left-right for Side-by-Side. Opening the menu cannot mutate this key.
The packaged NDS menu showed Side by Side after launch.

### 31.5 NDS cursor

The corrected positive screen-facing transform remains. At 1× the scheduler
now calls exactly one `retro_run()` per draw rather than fractional 0/2 calls;
mouse deltas remain atomically accumulated and are not tied to UI/FPS timers.

### 31.6 Volume UI

The row now has leading and trailing anchors to stack content, a flexible
low-hugging slider with only a minimum width, and a visible percent label. The
packaged NDS menu showed Volume, slider, and 50% together. Narrow/fullscreen
visual measurements remain a required human acceptance check.

### 31.7 Protected features

The packaged menu retained ten slots, independent Auto Save, speed buttons,
Escape-first source state machine, FPS, Import/Export, Core Options, and the
Vulkan → MoltenVK → Metal architecture. The native 3DS GPU-image path and
no-per-frame-idle contract are guarded in tests.

### 31.8 Regression guard infrastructure

Root `AGENTS.md` now requires the handoff/ledger read, baseline plus post-edit
tests, no broad reverts, and packaged runtime evidence. New
`docs/REGRESSION_GUARDS.md` records RG-001 through RG-014 and their owners,
automated guards, repro steps, and acceptance criteria.

### 31.9 Performance

No global Vulkan waits or per-frame logging were added. The 1× scheduler has
one core frame per draw; audio diagnostics are bounded snapshots. Packaged NDS
held about 60 FPS during the check. No before/after perceptual or CPU benchmark
claim is made.

### 31.10 Tests

`python3 -m unittest tests.test_native_regression_guards tests.test_native_staging_contract -v`: 30 passed.
`python3 -m unittest discover -s tests -p 'test_*.py' -q`: 88 passed.
`cargo test` in `native-offline/src-tauri`: 4 passed.
`npm run build:macos`: passed, including code-sign and DMG verification.

### 31.11 Artifact

Version: 0.4.4. App:
`native-offline/src-tauri/target/release/bundle/macos/VibeCodedEmulator.app`.
DMG: `native-offline/releases/vibecodedemulator-0.4.4-macos-aarch64.dmg`.
DMG size: 42,238,800 bytes. SHA-256:
`a36a0251355a7e2380497601aad6bef93f9f8ca208b2156b29af374ace414bdf`.
The package script and final direct checks reported `codesign` valid and
`hdiutil verify` valid.

### 31.12 Staging

Active staging asset remains `3a257e271678`; rollback target remains
`54b2e3b7750f`. No staging deploy was performed in this native stabilization
pass, and production was not contacted.

### 31.13 Remaining limitations

The live web 3DS secure-context blocker remains as documented in section 30.
Perceptual audio, 3DS ROM, narrow/fullscreen slider geometry, and cursor feel
must be signed off on a human-controlled packaged-app run; telemetry does not
substitute for those checks.

## 32. Settings tabs + renderer audit — 2026-09-07 19:20 +07

### 32.1 Settings architecture

The native menu was changed from one vertically stacked settings document to
an AppKit `NSTabView`. The exact tabs are **General, Graphics, Audio,
Keyboard, Controller, Emulation, Save States, Diagnostics, and About**. Each
tab owns its own bounded vertical scroll view; reaching Keyboard no longer
requires scrolling through Audio or state controls. The panel targets up to
820px wide and 620px tall, clamps inside the drawable with 12px margins, and
each tab document is remeasured to the available content width. The flexible
volume row remains constrained on both sides of its Audio tab content.

The visible Save Settings action is an explicit persistence boundary for
frontend preferences. Fullscreen preference, FPS overlay, volume, mute,
latency, and resampler quality are loaded into a draft. Closing the menu with
an unsaved draft restores persisted controls; Save Settings writes the draft
and gives a compact “Settings saved” confirmation. FPS is safe live preview.
Raw core-state bytes are never involved in settings persistence.

Core options remain dynamically enumerated from the libretro environment API,
grouped by announced category and identified by actual core namespace plus
option key (`mgba`, `melondsds`, or `azahar`). The UI shows valid announced
values only and flags restart-required choices. Controller mapping is honestly
reported as native responder/core-owned because there is no independent HID
remapping backend. Renderer backend is read-only: Vulkan 1.1 → bundled
MoltenVK → Metal.

### 32.2 Renderer and audio audit

Source inspection confirms the protected native paths remain unchanged:

| Path | Classification | Evidence |
|---|---|---|
| Native GBA | GOOD / NO CHANGE JUSTIFIED | Persistent mapped software staging, bounded two-slot ring, reusable image/resources, no successful-frame idle wait. |
| Native NDS | GOOD / NO CHANGE JUSTIFIED | Same minimal-copy software route; no input/touch code was changed. |
| Native 3DS | GOOD / NO CHANGE JUSTIFIED | Native GPU image/semaphore path reaches VulkanFrontend without normal CPU readback/re-upload. |
| Web GBA / NDS | GOOD / NO CHANGE JUSTIFIED | Existing bounded worker WebGPU-preferred/WebGL2-fallback implementation was not changed. |
| Web 3DS | UNVERIFIED | Secure-context/isolation and real boot/audio evidence remain required; no claim of live WebGPU was made. |

No renderer change was made because the current source gives no measurable
regression justification. Native audio diagnostics already refresh at 2 Hz and
expose core/effective/output/hardware rate, PCM signal counters, queue depth,
underruns/overruns, converter state, and player/engine state. The native 3DS
crackle remains unresolved: this pass did not claim an audible fix or change
the shared audio scheduling path.

### 32.3 Validation and release state

`cargo test --manifest-path native-offline/src-tauri/Cargo.toml`: 4 passed.
`python3 -m unittest tests.test_native_regression_guards tests.test_native_renderer_contract tests.test_phase1_renderer_contract tests.test_integration tests.test_regression_invariants`: 57 passed.

The updated native app and DMG were built locally with `npm run build:macos`.
`codesign --verify --deep --strict` passed and `hdiutil verify` passed. The
artifact is `native-offline/releases/vibecodedemulator-0.4.4-macos-aarch64.dmg`
(42,226,363 bytes; SHA-256
`35f6abcb09f1ef321b0eab467daf9b19f33a35a9478adf86c0d6f42c5ec36e87`).
No packaged-app human ROM smoke, renderer benchmark, staging deploy, or
production action was performed. In particular, audio perceptual quality and
actual GBA/NDS/3DS gameplay remain human runtime acceptance items.

## 33. Renderer backend audit + required handoff — 2026-09-07 19:40 +07

### 33.1 Scope, settings, and release state

This is a source-contract and read-only staging audit of the current dirty
workspace, not a claim of human-perceived runtime acceptance. Branch:
`ui/production-ux-refresh`; HEAD: `542ef985ddd22435cad00695b065dda1be4f80d3`.
Pre-existing dirty work was preserved. No renderer source was modified by this
audit; no staging deployment and no production action occurred.

Native Settings changed from one long scroll document to `NSTabView` tabs:
**General, Graphics, Audio, Keyboard, Controller, Emulation, Save States,
Diagnostics, About**. A tab scrolls only its own content. The panel clamps
inside the drawable, targets 820×620 maximum, and keeps the Audio volume row
constrained to both content edges with a 72px-priority minimum slider width.

Save Settings is an explicit draft/persistence boundary for fullscreen, FPS,
volume, mute, latency, and resampler quality. Closing unsaved Settings restores
persisted values; FPS is the safe live-preview exception. Core-option changes
are staged until Save Settings. The core options UI dynamically captures
legacy/v2/v2-intl libretro declarations, exposes only announced values, groups
by announced category, keys persistence by `mgba`/`melondsds`/`azahar` plus
option key, and flags restart-required values. It does not invent a bitrate,
renderer switch, unsafe numeric range, or HID remapper. Controller is honestly
reported as native-responder/core-owned.

The current locally built artifact remains
`native-offline/releases/vibecodedemulator-0.4.4-macos-aarch64.dmg`
(42,226,363 bytes; SHA-256
`35f6abcb09f1ef321b0eab467daf9b19f33a35a9478adf86c0d6f42c5ec36e87`).
Its codesign and hdiutil verification passed. The renderer audit did not change
the package payload.

### 33.2 Native renderer audit

| Path | Classification | Evidence | Change |
|---|---|---|---|
| GBA / mGBA | GOOD / NO CHANGE JUSTIFIED | Reusable host-visible persistent staging, reusable device image, explicit copy/barriers, bounded ring size 2, and direct/copy/convert counters. | None. |
| NDS / melonDS | GOOD / NO CHANGE JUSTIFIED | Same minimal-copy software path and ring as GBA. Cursor, touch, layout, speed, and audio scheduler were not touched. | None. |
| 3DS / Azahar | GOOD / NO CHANGE JUSTIFIED | Hardware-frame sentinel reaches `receive_image`/`present`; source semaphores and layout/ownership barriers are consumed before blit/present. No normal GPU→CPU→GPU path. | None. |

`AN3_FRAME_RING_SIZE` defaults to 2 and is compile-time constrained to 2–3.
Neither successful `upload_software_frame` nor `present_image` contains
`vkQueueWaitIdle` or `vkDeviceWaitIdle`. Device idle calls remain only in
resize/reconfiguration, failed-submit recovery, swapchain recovery, or
teardown. Software frames still make one necessary GPU staging-buffer →
device-image copy; this is minimal-copy, not “zero-copy.”

`an3_native_get_renderer_metrics` and `native_smoke` expose FPS, frames/drop,
direct/copied/converted upload counts, upload/present p95/p99, T_emulate
p95/p99, audio queue/max, underrun/overrun, RSS, and CPU time. No real ROM was
provided for this audit, so all live metric values are **UNVERIFIED** rather
than fabricated.

### 33.3 Web renderer audit

The implementation is a real bridge, not a capability-only claim: EmulatorJS
owns WASM/source canvas; `RendererBridge` obtains completed `ImageBitmap`
frames; a presentation canvas transfers to a Worker via
`transferControlToOffscreen` when supported; and a two-frame latest-wins policy
drops stale video but never audio. Pending/replaced ImageBitmaps are closed.

The worker WebGPU route calls `requestAdapter`, `requestDevice`, obtains and
configures a WebGPU canvas context, creates reusable sampler/shader/pipeline,
retains texture except on resize, calls `copyExternalImageToTexture`, and
submits a render pass. WebGL2 compiles/links once per backend, uses
`texStorage2D` where valid, and performs frame updates with `texSubImage2D`.
Failure to start WebGPU falls back to WebGL2, then `external-core-canvas`, with
the exact reason.

`AN3RendererStatus` separately publishes requested and effective backend,
worker/offscreen state, render/drop counters, transport, and p95/p99. Therefore
`?renderer=webgpu` is not treated as proof that WebGPU is active.

| Web path | Classification | Runtime evidence |
|---|---|---|
| GBA web | GOOD / NO CHANGE JUSTIFIED | Source/contracts verified; no live ROM execution during this audit. |
| NDS web | GOOD / NO CHANGE JUSTIFIED | Source/contracts verified; no live ROM execution during this audit. |
| 3DS web | UNVERIFIED | Player requires core init plus source canvas, first frame, and running audio; staging HTTP cannot prove secure WebGPU/SAB/isolation. |

Read-only staging health at `http://192.168.1.8:8092/health` reported
`environment=staging`, asset `3a257e271678`, and healthy status. It is HTTP,
so it is not a secure context; even with COOP, it cannot validate live
WebGPU/SAB/crossOriginIsolated. Security headers were not weakened. A verified
HTTPS origin or owner-authorized localhost tunnel is still required for web
backend/3DS runtime proof.

### 33.4 3DS audio and validation

Native 3DS crackle is **UNRESOLVED**. Stable FPS is not used as an audio
diagnosis. Existing bounded diagnostics record core/effective/output/hardware
rates, input/output PCM signal, callback counts, AVAudioConverter status,
scheduled buffers, player/engine state, queue depth/max, underruns, and
overruns. No audible capture or source evidence isolated a discontinuity,
resampler error, converter mismatch, or scheduler defect; no speculative
renderer/shared-audio change was made.

Completed checks in this audit:

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`: **89 passed**.
- `npm --prefix native-offline run check`: passed.
- `cargo test --manifest-path native-offline/src-tauri/Cargo.toml`: **4 passed**.

Still required before claiming runtime acceptance: packaged GBA/NDS/3DS launch
and audible checks; NDS cursor/touch/fullscreen and layout persistence; tab
geometry at narrow/desktop/fullscreen sizes; native real-ROM metric captures;
and a secure-origin web run verifying requested/effective backend, worker
ownership, and 3DS source-canvas/first-frame/audio milestones.

## 34. Complete historical regression consolidation and web NDS recovery — 2026-09-07 21:47 +07

### 34.1 Authority, inputs, and preservation

This section supersedes the earlier source-only `GOOD / NO CHANGE JUSTIFIED`
classification for web GBA/NDS. It is the authoritative audit for the current
dirty workspace and the current staging release. Branch:
`ui/production-ux-refresh`; HEAD before the targeted edit:
`542ef985ddd22435cad00695b065dda1be4f80d3`. Existing dirty work was preserved;
no broad revert, reset, checkout, rebase, or destructive cleanup was used.

All 23 Markdown handoffs in `reports/handoff/` were read, in chronological
content order, before editing the ledger:

1. `reports/handoff/00-comprehensive-project-handoff-2026-08-21.md`
2. `reports/handoff/01-p2-15-staging-acceptance-2026-08-23.md`
3. `reports/handoff/02-p3-operational-ux-and-automation-2026-08-23.md`
4. `reports/handoff/03-p4-reliability-release-engineering-2026-08-23.md`
5. `reports/handoff/04-p4-production-release-2026-08-23.md`
6. `reports/handoff/05-p5-offline-monitoring-release-2026-08-23.md`
7. `reports/handoff/06-dashboard-offline-staging-2026-08-24.md`
8. `reports/handoff/07-analytics-session-staging-2026-08-24.md`
9. `reports/handoff/08-admin-tab-layout-staging-2026-08-24.md`
10. `reports/handoff/09-admin-tab-layout-production-2026-08-24.md`
11. `reports/handoff/10-rust-gateway-offline-pwa-staging-2026-08-24.md`
12. `reports/handoff/11-offline-pwa-production-2026-08-24.md`
13. `reports/handoff/12-system-wide-performance-pause-2026-08-27.md`
14. `reports/handoff/13-player-staging-candidate-2026-08-29.md`
15. `reports/handoff/14-native-offline-staging-2026-08-29.md`
16. `reports/handoff/13-emulatorrust-0.1.1-staging-2026-08-30.md`
17. `reports/handoff/14-emulatorrust-0.2.0-vulkan-macos-staging-2026-08-31.md`
18. `reports/handoff/15-emulatorrust-0.1.2-macos-staging-pending-2026-08-31.md`
19. `reports/handoff/16-emulatorrust-0.1.2-macos-staging-2026-08-31.md`
20. `reports/handoff/15-emulatorrust-0.3.0-native-gba-nds-macos-staging-2026-09-01.md`
21. `reports/handoff/17-emulatorrust-0.4.2-phase1-macos-web-staging-2026-09-02.md`
22. `reports/handoff/18-emulatorrust-0.4.3-phase1-macos-web-staging-2026-09-07.md`
23. `reports/handoff/SYSTEM_INSPECTION_HANDOFF.md`

The pre-edit ledger had RG-001 through RG-014. It now contains RG-001 through
RG-046 in `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/docs/REGRESSION_GUARDS.md`, with a 46-row audit matrix and explicit static, behavioral, and live status. The full Python suite was 89 tests before this work and is 91 tests after it.

### 34.2 Reconstructed regression history

The historical sequence is now represented by the ledger rather than isolated
handoff PASS claims:

- The initial NDS failures were legacy DeSmuME/manual start, wrong relative
  signs, stale viewport geometry, and first-tap/Android retargeting. The
  durable path became melonDS auto-start, NDS ZIP delivery, geometry-mapped
  root input, source-canvas coordinate mapping, and document-level release.
- Virtual-pad changes repeatedly competed with the game canvas and EmulatorJS
  menu. The durable layering contract is game output base, `#tvPad` buttons
  above it, toolbar/options/save above the pad, and the native menu exception
  with the pad inert below it.
- Native packaged regressions then exposed landscape layout reset, NDS/3DS
  audio silence, NDS cursor lag after the direction fix, a GBA AppKit crash,
  and Volume overflow. They were fixed separately: explicit layout
  persistence, S16 interleaved→Float32 planar audio plus realtime
  `NoDataNow`, atomic input with one 1× core frame per draw, actual Core
  Options v2/v2-intl ABI/namespace handling, and a flexible volume row.
- Native Vulkan hardening added persistent mapped software buffers, a bounded
  2/3-frame ring, and a 3DS GPU image path without normal readback or per-frame
  idle waits. Web renderer work later added a source canvas → ImageBitmap →
  Render Worker/OffscreenCanvas presentation bridge with WebGL2 fallback.
- The earlier web audit treated source contracts and `Playing` as enough to
  call GBA/NDS good. The current staging run disproved that for NDS touch and
  exposed why the claim was unsafe.

### 34.3 Current symptom, reproduction, last known good, and root cause

Reproduction on the pre-fix staging asset `3a257e271678`:

1. Open the real NDS player with `?renderer=webgpu&ndsdebug=1`.
2. Wait for the page to announce `Playing`.
3. Inspect `#game` and call `document.elementFromPoint()` over the game and
   lower-screen area.
4. The DOM contains hidden `canvas.ejs_canvas` and visible
   `canvas.an3-render-canvas`. The presentation canvas is above the source and
   was computed as `pointer-events:auto` because the old
   `protectNdsCanvas()` selected every canvas and forced `auto!important`.
5. Root touch resolution used `hit.closest("#game canvas")`, so it selected
   the presentation canvas. EmulatorJS input listeners remained on the source
   canvas. The gesture therefore dispatched without an exception but the game
   did not respond.

The current page could still say `Playing` and report no console warning, so
this was a silent interaction failure, not a core-load error. The last known
good implementation is the geometry-mapped root bridge before the presentation
canvas was introduced, historical commit `3eba5b1`, with Android Chrome
verification recorded in the early handoffs.

### 34.4 Exact targeted fix and files

The fix is intentionally narrow and does not copy or revert an old full source
file:

- Added `static/nds-touch.js`, the shared source-canvas resolver and
  Top/Bottom/Left/Right scaled/letterboxed 256×192 mapper.
- Changed `static/player.js` to resolve only
  `#game canvas:not(.an3-render-canvas)`, dispatch root touch to that source,
  reject mapped presses outside the touch screen, and preserve release/cancel
  handling. NDS and 3DS canvas protection no longer binds or changes the
  presentation layer.
- Added a CSS belt-and-suspenders rule in `static/site.css` keeping
  `.an3-render-canvas` pointer-inert.
- Added the helper to `app.py`’s versioned player asset allowlist/routes and to
  the service-worker shell; added it to the native offline script order.
- Added `tests/web_nds_touch_behavior.test.js` and
  `tests/test_web_nds_touch_behavior.py` for source ownership, Top/Bottom,
  Left/Right, scaled/letterboxed mapping, rejection of the other screen and
  margins, and press/move/release sequencing. Existing integration and
  regression tests now verify the versioned helper route.

### 34.5 Architecture after the fix

The current web path is:

`Main UI / player.js` → EmulatorJS `#game .ejs_canvas` source →
`createImageBitmap(source)` → `RendererBridge` → transferred presentation
`OffscreenCanvas` → Render Worker (`WebGPU` when available, otherwise
`WebGL2`) → visible `.an3-render-canvas`.

The source canvas owns EmulatorJS input. The presentation canvas is output-only,
has `pointer-events:none`, and is excluded from protection/listener binding.
The NDS root bridge resolves the source even if a browser reports a
presentation hit, maps the configured touch-screen half, dispatches core input
to the source, and releases on end/cancel. `#tvPad`, native menu precedence,
toolbar, save/options panels, and physical keyboard remain separate owners.

### 34.6 Why the 89-test suite missed it and what was added

The old 89 tests asserted source strings, HTTP routes, renderer contracts,
native ABI/scheduler paths, and server behavior. They did not create a DOM with
two canvases, did not assert pointer-event hit ownership, did not execute the
mapper with Left/Right geometry or letterbox margins, and did not load a real
NDS ROM in a browser while exercising down/move/up/cancel. The old selector
assertion accepted any `#game canvas`, which was exactly the regression.

The new Level-2 tests use the real shared mapper and resolver and now run under
the full suite. Level-3 remains mandatory: a real staged browser or packaged
app must prove visible frames and responding input; static and behavioral tests
cannot promote an interactive feature to `GOOD`.

### 34.7 Verification before and after

Before the edit:

- Existing ledger: RG-001–RG-014.
- Baseline: `PYTHONPYCACHEPREFIX=/private/tmp/an3-pycache-regression-baseline python3 -m unittest discover -s tests -p 'test_*.py' -q` — 89 passed.
- Read-only staging: healthy, asset `3a257e271678`, active release
  `/opt/an3-arcade-staging/releases/20260907-171534-3a257e271678`.
- Live pre-fix DOM: visible presentation canvas was the hit target; no
  console warning explained the dead touch path.

After the edit:

- Ledger: RG-001–RG-046; matching AGENTS rules added.
- `python3 -m unittest tests.test_web_nds_touch_behavior tests.test_regression_invariants tests.test_integration tests.test_offline_consolidation -q` — 30 passed.
- `PYTHONPYCACHEPREFIX=/private/tmp/an3-pycache-regression-final python3 -m unittest discover -s tests -p 'test_*.py' -q` — 91 passed.
- Staging key-only preflight: `STAGING_SSH_KEY_AUTH=PASS`.
- Staging release: `STAGING_RELEASE=PASS`, asset `ccb7a58e54dd`, release
  `/opt/an3-arcade-staging/releases/20260907-214907-ccb7a58e54dd`, rollback
  target `/opt/an3-arcade-staging/releases/20260907-171534-3a257e271678`.

### 34.8 Live staging verification and honest remaining status

The real staging browser was reloaded at the same NDS player URL with
`renderer=webgpu`, `ndsdebug=1`, and a cache-busting smoke marker. The new
versioned scripts were present. The live DOM showed:

- Source: `canvas.ejs_canvas`, opacity `0`, pointer events `auto`, touch action
  `none`, z-index `1`, `data-an3-nds-touch=1`.
- Presentation: `canvas.an3-render-canvas`, opacity `1`, pointer events
  `none`, touch action `none`, z-index `2`, no NDS-touch dataset.
- `elementFromPoint()` over both center and lower-screen coordinates returned
  `canvas.ejs_canvas`, proving the presentation no longer owns the hit.
- Staging status was `Playing`; stage telemetry reported requested `webgpu`,
  effective `webgl2`, offscreen `true`, rendered frames `7921`, dropped frames
  `0`, p95 `0.1ms`, and p99 `0.3ms` at capture time.

This is a successful live ownership/renderer smoke, but not a complete visual
gameplay acceptance: the browser screenshot remained black, and the current
automation surface cannot expose the page’s listener internals or inject a
physical Android touch. The UI click/drag smoke produced no additional console
diagnostic beyond Chromium’s generic `UnknownError`. Therefore web NDS is
still `PENDING`/`UNVERIFIED` for visible gameplay and perceptual touch response
until a real device or an equivalent browser pointer-touch harness confirms
lower-screen press, continuous movement, release/cancel, both layouts,
fullscreen/resize, pad/menu precedence, and keyboard passthrough.

The 3DS HTTP/SAB/WebGPU secure-origin limitation and the native 3DS audio
crackle on Redmi 15 5G remain documented known gaps; neither was relabeled as
fixed by this task. Native packaged gameplay/audio evidence remains historical
unless rerun against the current package.

### 34.9 AGENTS and production boundary

`AGENTS.md` now requires a ledger/handoff search before editing any protected
file or symbol, matching guard execution before and after edits, explicit
behavioral/live evidence for interactive claims, source-canvas ownership for
NDS touch, and recording asset/release/ROM/runtime/error details for staging.

Production was untouched: no production HTTP request, production health/data
read, production deploy/restart/rollback, production symlink change, or
production service mutation was performed. Only the isolated staging release
was packaged, transferred, switched, and health-validated.

### 34.10 Final staging refresh after release-edge guard — 2026-09-07 21:59 +07

The outside-screen release correction was packaged and promoted separately so
the final live artifact includes the guaranteed `mouseup`/`touchend` path even
when a captured gesture ends outside the mapped DS touchscreen:

- `STAGING_SSH_KEY_AUTH=PASS`.
- `STAGING_RELEASE=PASS`, asset `46ef122fd81d`, release
  `/opt/an3-arcade-staging/releases/20260907-215649-46ef122fd81d`.
- Rollback target:
  `/opt/an3-arcade-staging/releases/20260907-214907-ccb7a58e54dd`.
- Read-only `/health` returned `ok=true`, `environment=staging`, and
  `asset_version=46ef122fd81d`.
- Versioned `nds-touch.js`, `player.js`, and `renderer-worker.js` returned
  HTTP 200 with immutable caching headers.
- Final browser DOM again showed the source canvas as the hit target and the
  presentation canvas as pointer-inert. Renderer telemetry showed requested
  WebGPU, effective WebGL2, OffscreenCanvas worker active, 727 rendered frames,
  zero dropped frames, and p95/p99 render time `0.2ms` at capture time.

The final screenshot remained black and the browser automation surface cannot
prove a physical Android touch or expose listener internals. Three coordinate
click/drag actions preserved `Playing` but produced Chromium’s generic
`UnknownError` in the browser console. Accordingly, the final release proves
the corrected DOM ownership and bounded renderer status, but web NDS remains
`PENDING`/`UNVERIFIED` for visible gameplay and perceptual touch response.
The next required live check is a real device or equivalent pointer-touch
harness covering both layouts, release outside the touchscreen, fullscreen,
resize, pad/menu precedence, and keyboard passthrough.

## Web NDS menu/touch layering regression — 2026-09-07 23:02 +0700

### User-observed symptom

The user reported that the latest NDS touchscreen recovery restored input to
the EmulatorJS source canvas but the NDS touch surface again covered or
intercepted the game menu. Settings could not be opened or used reliably. The
required contract is ownership by active surface: gameplay owns gameplay touch;
native menu, Settings, AN3 panels, toolbar, and virtual controls own their own
events; the presentation canvas never owns input.

### Historical matching regression and proven fix

The historical handoff recorded the same failure as “NDS menu blocked by
virtual controls.” The cause was refreshed stacking that placed the virtual pad
above the native EmulatorJS menu, combined with a root bridge that could fall
back to an arbitrary canvas. The successful fix was to keep the native menu
above the pad, toggle `emulator-menu-open`, move `#tvPad` to z-index 19 and
make it pointer-inert while that class is open, and begin a direct NDS gesture
only from a real game canvas. Menu/dialog input was never rebound to the source
canvas.

### Current recurrence root cause

The source-canvas recovery added a valid fallback for a presentation-canvas
hit, but the resolver had no protected-owner exclusion. A menu descendant
could therefore reach the `#game` root, be resolved back to `.ejs_canvas`, and
receive synthesized NDS input even though the menu was visually above it. The
root listener also performed the gameplay acceptance path before checking the
full protected target/composed path. The current source/presentation CSS was
not the primary failure: the leak was logical event ownership.

### Before-fix DOM and event evidence

On staging asset `46ef122fd81d`, the live player showed the correct renderer
relationship: source `canvas.ejs_canvas` opacity 0, pointer-events `auto`,
z-index 1; presentation `canvas.an3-render-canvas` opacity 1,
pointer-events `none`, z-index 2; `#game` z-index 20. With the pad and native
menu open, the existing CSS correctly computed `#tvPad` at z-index 19 with
pointer-events `none`, and a native `.ejs_context_menu` row was pointer-active
inside `#game` at z-index 9 (therefore above the stage stacking context).

The menu row’s actual hit was a native anchor/button whose composed path ran
through `.ejs_context_menu` and `#game`. The old root bridge did not reject
that path and its source resolver returned the source canvas as a fallback;
the root path could therefore accept the event and synthesize gameplay input.
The browser automation surface could inspect DOM, z-index, pointer-events,
and menu state but could not expose the page’s custom `ndsdebug` object or
inject a trusted physical touch, so the trusted-event dispatch count is
recorded as a harness limitation rather than guessed.

### Exact fix

- Added a shared protected-owner selector and composedPath-aware
  `isProtectedUiTarget()` in `static/nds-touch.js`.
- `resolveSourceCanvas()` now returns `null` for EmulatorJS menu/settings,
  AN3 panels/dialogs, toolbar actions, `#tvPad`, and nested virtual controls;
  presentation hits still resolve only to the source canvas.
- `static/player.js` now checks protected ownership before preventDefault,
  source resolution, pointer capture, or synthetic NDS dispatch in both touch
  and pointer root paths.
- `emulator-menu-open` remains driven by the existing MutationObserver and
  menu click refresh. Opening the menu releases one active NDS press and
  clears tracking. Blur, hidden visibility, fullscreen change, pointercancel,
  and touchcancel also release the active root gesture.
- Existing scoped CSS remains the deliberate stacking fix:
  `#tvPad.show` is z-index 26 and control-owned while closed; under
  `.emulator-menu-open` it is z-index 19 and pointer-inert. The source canvas
  remains structurally pointer-enabled; the presentation canvas remains
  output-only with `pointer-events:none`. No renderer-worker, latest-frame-wins,
  ImageBitmap, OffscreenCanvas, WebGPU/WebGL2, core, or source-canvas recovery
  architecture was changed.

### Changed files

- `static/nds-touch.js`
- `static/player.js`
- `tests/web_nds_touch_behavior.test.js`
- `tests/test_web_nds_touch_behavior.py`
- `tests/test_regression_invariants.py`
- `docs/player-layering.md`
- `docs/REGRESSION_GUARDS.md`
- `AGENTS.md`
- `reports/handoff/SYSTEM_INSPECTION_HANDOFF.md`

`static/site.css` and `static/renderer-worker.js` were inspected and retained;
no renderer architecture or presentation-canvas interactivity was introduced.

### Automated verification

- `node tests/web_nds_touch_behavior.test.js` — PASS.
- Focused Python web-touch/regression tests — 17 PASS.
- Full Python suite — 91 PASS.
- JavaScript syntax checks and `git diff --check` — PASS.
- The realistic DOM covers source/presentation canvases, nested EmulatorJS
  menu elements, Settings, toolbar, tvPad, virtual button, dialogs, both
  Top/Bottom and Left/Right mapping, menu-open release, immediate post-close
  gameplay, presentation inertness, and fullscreen/resize ownership.
- Android harness preflight — `DEVICE_CONNECTED=no`; no Android result is
  claimed.

### Live staging acceptance

Staging only was deployed and health-verified as asset `45ba4629b867`, active
release `/opt/an3-arcade-staging/releases/20260907-225435-45ba4629b867`, with
rollback target `/opt/an3-arcade-staging/releases/20260907-224817-c63a1a99ccf7`.
The page was loaded with `renderer=webgpu&ndsdebug=1`.

- Gameplay/render: visible NDS frame; status `Playing`; rendered frames
  advanced from 33,949 to 34,071 during the post-close gameplay smoke.
- Menu: first Context Menu interaction opened the native menu; the stage had
  `emulator-menu-open`; the menu was pointer-active and the pad was z-index 19
  and pointer-inert.
- Settings: Settings opened on the first menu interaction. Graphics Settings
  opened, and the FPS value control responded.
- No leakage contract: protected-owner resolver, composedPath exclusion, and
  menu-open release are covered by the behavioral suite and source assertions.
  The live browser could not expose custom `ndsdebug` globals or create a
  trusted touch event, so this remains a physical-touch harness limitation.
- Close: after returning to gameplay, the menu class settled closed, the pad
  returned to z-index 26, source pointer-events stayed `auto`, presentation
  pointer-events stayed `none`, and the next gameplay click advanced frames
  immediately.
- Virtual pad: the Up button accepted a click with menu closed; the following
  gameplay action remained responsive.
- Fullscreen/resize: Enter/Exit Fullscreen changed the live viewport from
  624×837 to 2560×1440 and back. After each transition the source remained
  pointer-enabled, presentation remained pointer-inert, and the pad/menu
  precedence settled back to the closed state. Both layout mappings are also
  exercised in the automated Top/Bottom and Left/Right tests.
- Renderer: requested `webgpu`, effective `webgl2`, OffscreenCanvas worker
  active, 64,244 rendered frames, 4 dropped frames, p95 `0.1ms`, p99 `0.2ms` at
  final capture. One generic browser-automation `UnknownError` was logged;
  no renderer or application stack failure was observed.

The overall Web NDS label remains `PENDING`/`UNVERIFIED` because the mandatory
trusted-device gameplay touch and `ndsdebug` dispatch inspection were not
available. The menu/settings ownership regression itself is fixed and live
staging-verified; Web NDS must not be called `GOOD` until touchscreen gameplay
response and menu/settings interaction are both confirmed by the same trusted
touch path.

### Updated guards and production boundary

RG-015, RG-017, RG-018, RG-019, RG-026, RG-033, RG-035, RG-036, RG-044, and
RG-047 were updated. RG-047 is the new distinct invariant: protected UI events
must never be redirected into the NDS source canvas. `AGENTS.md` now requires
the gameplay-touch, menu-precedence, Settings-clickability, virtual-pad,
source/presentation ownership, release/cancel, fullscreen, and resize suites
before and after any protected player/layer edit.

Production was untouched: no production deploy, restart, rollback, symlink
change, production health read, or production data mutation was performed.

## Web NDS mobile zero-movement tap regression — 2026-09-07 23:35 +07

### User symptom

The authoritative report is: desktop web NDS tap works; mobile phone web NDS
drag works; a normal short mobile tap does not.  Drag is therefore not treated
as proof of touch acceptance.  A mobile `DOWN → UP` with no MOVE is a required
first-class interaction.

### Historical match

The original Android repair sequence is preserved in the 2026-08-11/12
history: first-tap fallback work was rolled back in commit `f4a0bc3`, then the
root `touchstart` bridge, document-level `touchmove`/`touchend`,
`changedTouches` lookup, and geometry-mapped melonDS path were established.
Commit `3eba5b1` promoted that Android-successful geometry-mapped path.  It
accepted an actual mapped down before recording the touch owner; the current
source/presentation fixes are retained and were not reverted.

### Event comparison

| Event/stage | Desktop tap | Mobile tap | Mobile drag |
| --- | --- | --- | --- |
| Physical evidence | User-verified working; no trusted desktop trace collected in this pass | User-verified failing; Android device unavailable for trace | User-verified working; Android device unavailable for trace |
| Root bridge synthetic down | Normal desktop mouse reaches EmulatorJS | Dispatched, then bridge treated it as rejected | Dispatched, then native pointer movement could still reach the core |
| Logical owner/release before fix | Not applicable to desktop mouse | Missing because hybrid dispatch returned `undefined` | Missing from TouchEvent bridge; visible motion could come from leaked native pointer events |
| Logical owner/release after fix | Unchanged desktop mouse path | Expected `logical-down`, `moveCount=0`, `logical-up`; live Android result pending | Expected one down, moves, one up; live Android result pending |

The first source-level divergent stage was the mobile `touchstart` acceptance
check: `geometry-mapped` sent the hybrid pointer/mouse down but
`dispatchNdsEvent()` returned `undefined`; `if (!canvas || !dispatchNdsEvent())
return` therefore abandoned ownership before `preventDefault()` and before the
matching `touchend` could release it.  This is a lifecycle/return-contract bug,
not renderer, geometry, UI layering, or a fabricated DOM-click issue.

### Fix and tap semantics

- `dispatchNdsPointer()` and the hybrid dispatcher now report dispatch success;
  in hybrid mode the result is the geometry-mapped synthetic mouse dispatch.
- `AN3NdsTouchBridge.createTouchGestureOwner()` owns exactly one first valid
  finger. Its lifecycle is immediate `logical-down`, optional moves, and one
  `logical-up`/cancel. There is no movement threshold or tap timeout.
- `touchend` remains keyed from `changedTouches` as well as `touches`; a second
  finger cannot release or take over the active NDS finger.
- Protected UI is rejected before ownership. The EmulatorJS source canvas is
  still the only gameplay owner and `.an3-render-canvas` remains output-only.
- `ndsdebug=1` has bounded physical-event fields (target, composed path,
  touch-list counts, capture/default state) and logical/synthetic records with
  event family, ID, mapped point, source canvas, acceptance/reason, duration,
  move count, and pressed transition. No production logging was enabled.

### Regression guard and automated tests

RG-048 now specifically protects zero-movement mobile taps in
`docs/REGRESSION_GUARDS.md`. `tests/web_nds_touch_behavior.test.js` exercises:
pointer tap; realistic TouchEvent start/end; Chromium pointer/touch ownership;
tap versus drag; immediate tap; menu/settings/virtual-control exclusion; three
successive taps; tap after drag; tap after a menu-close boundary; and
Top/Bottom plus Left/Right coordinate mapping. The Python wrapper and
regression-invariant test protect the production wiring.

### Staging and mobile runtime evidence

- Previous staging asset/release:
  `45ba4629b867` / `/opt/an3-arcade-staging/releases/20260907-225435-45ba4629b867`.
- Active staging asset/release:
  `21ea96a1f4d5` / `/opt/an3-arcade-staging/releases/20260907-233126-21ea96a1f4d5`.
- Rollback target: `/opt/an3-arcade-staging/releases/20260907-225435-45ba4629b867`.
- Health: staging service active; `/health` returned `ok=true`,
  `environment=staging`, and asset `21ea96a1f4d5`.
- The staged desktop browser reached `Playing`; the source canvas was
  `canvas.ejs_canvas` with `pointer-events:auto`, while the presentation canvas
  had `pointer-events:none`. This is a layering smoke only, not mobile proof.
- Android Chrome: **UNVERIFIED**. The owner-authorized harness preflight
  recorded `DEVICE_CONNECTED=no`; no serial or private device data was read.
- Android Firefox: **UNVERIFIED** for this change (historical white-canvas
  limitation remains separate and is not represented as a pass).

The real mobile sequence and all requested mobile acceptance checks remain
pending an authorized connected phone. Production remains untouched.

## Web NDS mobile zero-movement tap regression — 2026-09-08 00:21 +07

### User symptom

Desktop web NDS tap and drag were user-verified working. On mobile phone web,
drag worked while a normal stationary short tap did not. A drag is not treated
as proof of touch acceptance.

### Historical match

The original Android repair was read from the 2026-08-11/12 handoffs and the
reference commits `f4a0bc3`, `c532f0c`, and `3eba5b1`. It established the
geometry-mapped root TouchEvent path, source-canvas coordinates,
document-level release, `changedTouches` end lookup, and the pointer+mouse
compatibility dispatch used by melonDS. This pass retained the present
source/presentation and protected-UI fixes; it did not revert current code.

### Event comparison

| Event/stage | Desktop tap | Mobile tap (Android Chrome) | Mobile drag (Android Chrome) |
| --- | --- | --- | --- |
| Physical path | User-verified native mouse down/up on `canvas.ejs_canvas` | Native `pointerdown`, `touchstart`, `pointerup`, `touchend`; `touchend.touches=0`, `changedTouches=1` | Same start/end plus native moves |
| Root logical path | Direct source-canvas desktop path | One accepted `logical-down`, `moveCount=0`, `logical-up` | One accepted down, 42 logical moves, one up |
| Source and capture | User-verified working | `canvas.ejs_canvas`; native pointer capture succeeded | `canvas.ejs_canvas`; document touch lifecycle retained owner |
| Pre-fix release | N/A | Synthetic up followed down in 3–6 ms | Parent EmulatorJS menu observer cancelled the gesture |
| Fixed result | Unchanged | Release is latched through one animation/input-frame boundary, then one synthetic pointer/mouse up | Immediate one release; no menu cancellation |

The first mobile divergence is therefore the physical TouchEvent lifecycle:
desktop does not enter it. The mobile down was not lost (A); it reached the
source and created a logical press. The first observed failure was B: an
unmoved press was released before the emulator could observe it. The trace
also found a separate drag regression: compatibility mouse moves bubbled into
EmulatorJS’s desktop-menu observer. C is controlled by TouchEvent ownership of
one identifier; native pointer observations do not create a second logical
gesture. D is ruled out by the recorded `changedTouches=1` end. E remains
scoped—`preventDefault()` runs only after gameplay ownership and synthetic
pointer/mouse semantics remain explicit. F is ruled out: no DOM `click` is
synthesized or consumed for the NDS tap.

### Root cause and fix

`createTapReleaseLatch()` holds only an accepted, zero-move release until the
next browser input-frame boundary. It uses `requestAnimationFrame`, not an
arbitrary millisecond delay; movement and cancel/forced release remain
immediate. The latch is flushed before a new physical gesture and on the
existing menu/blur/fullscreen release paths, so it cannot make a stuck touch.

The historical pointer+mouse compatibility events are still delivered to the
EmulatorJS source canvas. Their synthetic mouse members carry `pointerType:
"touch"` and are stopped at the source canvas after same-target core listeners
run, so they do not bubble to the parent-only desktop menu observer. Native
mouse, menu, Settings, toolbar, and virtual-pad events are not stopped or
redirected.

`ndsdebug=1` remains bounded (160 entries). It now records physical target,
path, touch-list counts, source/capture/default fields and logical action,
family, id, mapped coordinate, acceptance/reason, duration, move count,
pressed state, and `releaseState`. A valid real tap shows `logical-down`, zero
moves, `logical-up` with `latched-next-input-frame`, then one released
synthetic up.

### RG-048 and automated tests

RG-048 was corrected to protect the actual zero-move failure rather than a
superseded dispatcher-return theory. `tests/web_nds_touch_behavior.test.js`
now covers pointer and realistic TouchEvent taps, Chromium event-family
ownership, tap versus drag, a very-short one-frame latch, protected UI,
repeated taps, tap after drag/menu, and Top/Bottom plus Left/Right mapping.
The Python regression guards assert the live latch, exactly-once flush,
source-only event shield, and existing source/presentation contract.

### Mobile runtime evidence

An owner-authorized physical Android device was used without recording a
serial or account data: Android 16, Chrome 152.0.7977.75. On the staged page:

- Short tap: PASS at bridge level. One down at mapped `128,9`, zero moves,
  one latched up, and one released synthetic up; no menu open.
- Five consecutive short taps: PASS at bridge level. Five downs, five zero-move
  ups, and zero cancels.
- Drag: PASS at bridge level. One logical gesture, 42 moves, one immediate
  release, zero logical cancel, and native menu remained hidden.
- Drag then immediate tap: PASS at bridge level. The following tap had zero
  moves and a fresh `latched-next-input-frame` release, with zero cancels.
- Virtual-pad A tap: PASS ownership check. It created no NDS logical input.
- Android Firefox 155.0.1: staging URL launch completed, but no equivalent
  debug inspection or in-game response was available; recorded separately as
  UNVERIFIED, not combined with Chrome.

The page reported `started=true` but `runtimeCore=null` and a frame counter
stalled at 5, leaving no visible/advancing NDS gameplay state with which to
verify a known in-game UI action, long stationary press, menu-close gameplay
tap, layouts, fullscreen, or orientation. That renderer/core condition was
not modified because the reported input regression is independent and the
renderer is protected. Accordingly Web NDS is **not GOOD**: the bridge-level
Android Chrome result is a pass, while the required end-to-end game-action
acceptance is still UNVERIFIED.

### Staging and production boundary

- Previous staging asset/release: `cbe509a99153` /
  `/opt/an3-arcade-staging/releases/20260908-001442-cbe509a99153`.
- Active staging asset/release: `50d711002677` /
  `/opt/an3-arcade-staging/releases/20260908-001932-50d711002677`.
- Rollback target: the previous `cbe509a99153` release.
- Health: active staging service and `/health` returned `ok=true`,
  `environment=staging`, asset `50d711002677`; staged `player.js` and
  `nds-touch.js` hashes matched the working tree.
- Production was untouched: no production deployment, restart, health read,
  rollback, or data operation occurred.

## Full release integrity / renderer / regression audit — 2026-09-08 09:42 +0700

Release readiness: **BLOCKED**, with concrete findings below. This audit did
not add features, optimize or change the renderer/input/native host source.
The release candidate is for staging verification, not production approval.

## Current authority and touch acceptance

**OWNER-VERIFIED PHYSICAL DEVICE PASS** — owner personally confirmed actual
NDS touchscreen tap, drag, and gameplay response on Redmi 15 5G / Android Chrome.
The owner confirmed Pokémon Mystery Dungeon: Explorers of Sky as the comparison
ROM. This is owner runtime evidence, not an automated result. It supersedes
older bridge-only and physical-touch-pending statements for that same behavior.
It does not establish Firefox, every layout, fullscreen, orientation, long-press,
or menu-close subcase. Android Firefox remains UNVERIFIED, with its historical
white-canvas limitation retained separately.

The connected harness independently reported Android 16, Chrome 152.0.7977.75,
1080×2340, DEVICE_CONNECTED=yes. No serial, account or private identifier was
recorded. Existing zero-movement tests pass; no new touch patch was warranted.
RG-048 retains the actual one-frame release-latch and source-only compatibility
event shield history. The superseded undefined-return hypothesis stays in its
historical dated handoff, not the current root-cause status.

## Source and staging parity

Before publication: asset `50d711002677`, release
`/opt/an3-arcade-staging/releases/20260908-001932-50d711002677`.
Earlier rollback asset: `cbe509a99153`.
After publishing the fresh DMG using repository `deploy/package-staging.sh`
and owner-installed `/usr/local/sbin/an3-arcade-staging-release`:

- Active asset: `50d711002677` (web source unchanged).
- Active release: `/opt/an3-arcade-staging/releases/20260908-093537-50d711002677`.
- Immediate rollback: `/opt/an3-arcade-staging/releases/20260908-001932-50d711002677`.
- Health: HTTP 200, `ok=true`, `environment=staging`, expected asset.
- Staging is bound to `192.168.1.8:8092`; a loopback port probe is not its health check.
- Strict host-key checking and key-only authentication passed.
- Production was untouched: no production health, restart, deploy or data operation.
  The wrapper that also prepares production artifacts was not used.

All six raw deployed files match the working tree by SHA-256:

| File | SHA-256 |
| --- | --- |
| static/player.js | `301592285ec3c9c0e2c6d060eb154a6475c59d69c2c16d0475590fb814791531` |
| static/player-runtime.js | `5546b3013e7026aceb32a09f95879e24d00d1880b6e21b73fa54ce01c9f3b0f1` |
| static/renderer-worker.js | `854c373f246ccb9e18590b5c5be9127741470f0fe4538a10adc59d4fc12bd2aa` |
| static/nds-touch.js | `3d879130a8df25a9393accaa835d4bcf755c93e72c0fd87810617f34324274f0` |
| static/site.css | `3c7cd43af1af2bb7a5d374e0354c1029d703a7b9496bb9a61c602353143d9ac1` |
| static/service-worker.js | `92d4d12666f0f0ae8bc1795d33b88e526a78abf5a72b12a26edc413fdd6a6143` |

The browser DOM on desktop and physical Android loaded player.js,
player-runtime.js, renderer-worker.js and nds-touch.js under
`/static/v/50d711002677/`. CSS uses `/static/site.css?v=50d711002677`.
Those HTTP responses matched source. The service worker is served at
`/service-worker.js?v=50d711002677`: app.py substitutes `__ASSET_VERSION__`, so
its served hash intentionally differs from the raw file; exact substituted
payload comparison PASS. Four versioned JS routes returned immutable caching;
service worker returned no-cache. LAN HTTP is not a secure isolated runtime
merely because isolation headers exist. A localhost-only SSH tunnel was tested
separately; no TLS warning or browser security protection was bypassed.

## Renderer truth table — current asset only

Values are snapshots, not full-game benchmark averages. Worker-active for LAN
Android is evidenced by successful offscreen frame-result messages and current
worker implementation; there is no separate public workerActive field.
Desktop DOM does not expose the complete fallback reason, recorded as unavailable.

| Runtime | requestedBackend | effectiveBackend | fallbackReason | workerActive | offscreenActive | renderedFrames | droppedFrames | p95 ms | p99 ms |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| Desktop Chromium LAN explicit WebGL2 | webgl2 | webgl2 | none observed | inferred active | true | 794 → 5440 | 0 | 0.2 | 0.2 |
| Android Chrome LAN explicit WebGL2 | webgl2 | webgl2 | empty | active frame-result path | true | 1354 → 4906 | 1 → 1 | 0.4 | 0.7 |
| Desktop Chromium LAN WebGPU request | webgpu | webgl2 | unavailable in DOM | inferred active | true | 2023 | 0 | 0.2 | 0.4 |
| Android Chrome LAN WebGPU request | webgpu | webgl2 | WebGPU was requested, but the effective backend is webgl2. | active frame-result path | true | 1235 | 1 | 0.7 | 1.3 |
| Desktop Chromium localhost WebGPU request | webgpu | external-core-canvas | unavailable in DOM | inactive bridge | false | 0 | 0 | unavailable | unavailable |
| Android Chrome localhost WebGPU request | webgpu | external-core-canvas | Render worker failed. | failed initialization | false | 0 | 0 | null | null |

Android secure-origin capability reported `webgpuAvailable=true`. Therefore this
is **WebGPU initialization FAIL**, not “device has no WebGPU”. No live WebGPU
PASS is claimed. The fallback chain itself needs investigation before acceptance.

WebGL2 worker transport is live-proven, but **visible advancing NDS gameplay was
not proven in these explicit-backend audit launches**. Desktop showed a white
screen/FPS overlay or black output; Android showed black output with Playing.
Counters alone do not promote these runs to gameplay PASS. This separate launch
failure does not revoke the owner's working-session tap/drag evidence.

Secure desktop console recorded EmulatorJS update-check fetch failure and wake
lock permission denial. Neither is established as the cause of the game/worker
failure. No general “no errors” claim is made.

## Redmi smoothness: core versus presentation

Same asset and server ROM route were used on Mac and Redmi. A matching advancing
gameplay scene and equal saved settings were **not achieved**; consequently a
valid cross-device gameplay benchmark cannot be claimed.

Measured physical Android WebGL2 window:

- `performance.now`: 34018.70 → 93379.30 ms (59.3606 seconds).
- Worker presentation: 1354 → 4906 = 3552 frames, approximately **59.84 fps**.
- Core `gameManager.getFrameNum()`: **5 → 5**, observed delta **0 fps**.
- FramePacing coreFrames: 4 → 4; longTasks 10; UI p95/p99 about 16.8 ms.
- Browser visible=true, EmulatorJS paused=false; screenshot black.
- `getFrameNum()` wraps core export `get_current_frame_count`; it is not the
  renderer's frame counter. No independent core callback sampling was available
  to prove that export's accuracy in this stalled session.

Classification of the sampled run: **stalled core/boot or invalid core telemetry,
while presentation continues**. It is not evidence of a presentation-throughput
bottleneck. Classification of the owner's visibly less-smooth working gameplay:
**UNRESOLVED**. A 0.7 ms renderer p99 does not exonerate every graphics cost and
cannot identify core CPU, frame duplication, pacing, thermal or settings causes.
No optimization was started. Required next evidence is a reproducible advancing
scene on both devices and independent core-frame production measurements.

## Fresh packaged app and download parity

`npm run build:macos` rebuilt current source, produced the app and fresh DMG,
passed deep strict codesign verification and hdiutil checksum verification.
The artifact is ad-hoc signed staging output; it is not notarized public output.
It was mounted read-only and launched from the mount. Process executable path
confirmed `/Volumes/VibeCodedEmulator/VibeCodedEmulator.app/Contents/MacOS/an3-offline-native`.
An earlier mount in the same audit used `/Volumes/VibeCodedEmulator 2/`.

Fresh DMG SHA-256:
`5e0de9ea7280b59f8ac71dc3f7dfd1e9bbcbd8c28ad9b57421055ee4d21c8d01`.
Old staging download SHA-256:
`35f6abcb09f1ef321b0eab467daf9b19f33a35a9478adf86c0d6f42c5ec36e87`.
After staging publication, a fresh HTTP download returned the **exact fresh hash**.
Thus stale DMG parity is resolved; no old `54b2...` package evidence was inherited.

Native Golden Sun Dark Dawn reached visible NDS gameplay. All nine tabs were
clicked and their contents inspected: General, Graphics, Audio, Keyboard,
Controller, Emulation, Save States, Diagnostics, About. Screenshots confirmed
the visible tabbed panel. Controller remapping is explicitly unimplemented;
this was not represented as a working feature. Save States exposes slots 1–10,
including 5, and separate Auto Save/import/export; no user save was overwritten
by an explicit test action. Normal pre-existing Auto Save remained enabled.

Save Settings functional test:

1. Toggle Show FPS off and press Save Settings: “Settings saved” appears.
2. Return to library, relaunch NDS, reopen Graphics: Show FPS remains off — PASS.
3. Restore original Show FPS on and save — PASS; original preference restored.
4. Toggle without saving and close via Menu: reopening restores saved value
   and shows “Unsaved settings discarded.” — PASS.
5. Toggle without saving and close via Escape: reopening retains unsaved value
   and live overlay remains changed — **FAIL**.

Exact source cause: keyDown Escape branch hides `_menu_panel` directly and
never invokes `discardSettingsDraft`; `toggleMenu:` does invoke it. This is
an explained current RG-025/RG-028 regression in both current source and fresh
staging package. No native host fix was silently bundled into an audit artifact.
The general nine-tab and explicit-save tests pass; full Settings acceptance does
not. Other native systems' live audio, input, save, and renderer checks are
UNVERIFIED on this fresh artifact rather than inherited from older packages.

## Tests and ledger reconciliation

- Node focused NDS behavior suite PASS, including all zero-movement cases.
- Focused Python: web touch 2 PASS; regression invariants 15 PASS.
- Full Python suite: 91 PASS before and after documentation reconciliation.
- JavaScript syntax checks and git diff --check PASS before reconciliation;
  post-documentation checks recorded in the audit test log.
- Existing source and behavior tests did not detect the Escape draft defect;
  tests passing is not interactive acceptance.
- Every RG-001–RG-048 now has current source/staging/package/owner evidence scope.
- Every audit-matrix live row is reconciled; historical evidence is retained in
  `REGRESSION_GUARDS-before-integrity-20260908.md` and historical incidents.
- RG-033/RG-044/RG-048 no longer describe owner-confirmed tap/drag as pending.
  RG-038 points to current asset/release. Expanded touch subcases stay distinct.
- Renderer architecture, input ownership, source/presentation pointer contract,
  menu guards and mapping code were unchanged. Their complete live regression
  matrix is not newly asserted as PASS merely because source was retained.

## Release-readiness table

| Requirement | Current result | Explanation / remaining evidence |
| --- | --- | --- |
| Ledger contradictions | RECONCILED | 48 guards and matrix; history retained |
| Owner actual mobile tap + drag | OWNER-VERIFIED PHYSICAL DEVICE PASS | Not automation; no Firefox generalization |
| Current six-file staging parity | PASS | Raw hashes and expected served payloads |
| Explicit WebGL2 | PARTIAL / acceptance blocked | Worker frames advance; audit game output does not |
| LAN WebGPU fallback | PASS fallback reporting | Effective WebGL2; no WebGPU PASS |
| Secure WebGPU | FAIL | Capable Android runtime: Render worker failed; external core fallback |
| Redmi working-game bottleneck | UNRESOLVED | Captured stalled launch is not owner's advancing scene |
| Fresh DMG build/mount/launch | PASS | Exact fresh SHA and mounted process |
| Nine Settings tabs | PASS | Each tab exercised |
| Explicit Save Settings | PASS | Survives NDS relaunch; original preference restored |
| Escape draft discard | REGRESSION — EXPLAINED | keyDown bypasses discardSettingsDraft |
| Staging DMG parity | PASS | Fresh downloaded hash matches |
| Production | UNTOUCHED | No production operation |
| Overall release readiness | BLOCKED | No feature/optimization work may proceed yet |

There is no unexplained stale artifact or unlabeled regression. There are real,
explicit acceptance blockers; this report does not turn them into PASS.


Detailed report: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/FULL_RELEASE_INTEGRITY_20260908.md`.
Raw current evidence: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/integrity-20260908`.

## Multi-model release train P1 — 2026-09-08T16:32:16+07:00

**P1 BLOCKED; overall release readiness remains BLOCKED.** This section supersedes the integrity audit's current claims about Settings Escape, worker startup, artifact parity and boot labels, while preserving historical evidence.

Native Escape and Menu share discard-close; fresh mounted final DMG validates draft rollback and Save Settings persistence. Secure worker rejection was traced to missing worker COEP; matching require-corp enables WebGPU. Missing RENDER_ATTACHMENT independently caused black WebGPU copies and is fixed. Fresh-canvas WebGL2 fallback and explicit readiness milestones are tested. 93 Python tests PASS; Node touch/renderer PASS.

Staging asset 11290264c01d, release /opt/an3-arcade-staging/releases/20260908-112644-11290264c01d, rollback /opt/an3-arcade-staging/releases/20260908-093537-50d711002677. Four player-JS served hashes match. Final DMG SHA 37e24bf1d1d6c44ff3267c5649b16010f8bce076cc0bac632cddf17d431b975c matches fresh staged download. Production untouched.

Current secure desktop WebGPU and WebGL2 worker frames advance, but NDS gameplay remains black. A controlled source-only run also fails with white core output/FPS overlay, so the unresolved source/boot defect exists without presentation. No gameplay PASS, FPS diagnosis or optimization is claimed. Android is currently disconnected; prior owner-confirmed Redmi tap/drag/gameplay touch PASS remains valid and separate. Extended runtime matrix remains UNVERIFIED.

Next assignment remains P1 (Astra Medium), not P2. Read /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P1_20260908.md and /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_STATE.md. Full evidence: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/p1-20260908.


## P1 completion — 2026-09-09T09:29:59+07:00
P1 COMPLETE; supersedes earlier P1 remaining blank-screen blocker, not overall release readiness. Direct secure staging WebGPU and controlled WebGL2 recovery reach New Game and advancing dialogue. Suspended audio at frame5 resumes on trusted canvas activation; brief0.585ms automation presses were unreliable,133.8ms virtual A succeeded. No new source/deployment. Existing mounted native Escape/Save PASS retained. Redmi absent; prior owner evidence preserved. All93 Python/8 Node tests PASS. Asset11290264c01d, production untouched. Next assignment P2, Sol Medium; no P2 work executed.
Completion report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P1_20260909_COMPLETION.md

## P2 diagnosis checkpoint — 2026-09-09T14:45:14+07:00

P2 is BLOCKED at the required Redmi comparison. Passive core/source, presentation, loss/replacement, bitmap, worker, UI pacing, long-task, dimension/DPR and renderer telemetry is deployed on staging asset af16e551490f. Core/source FPS uses only independent EmulatorJS core-counter deltas over wall time and becomes null after regression. Matched Mac New Game WebGPU/WebGL2 samples both hold approximately60 core and presentation FPS with zero dropped/replaced/skipped frames and sub-millisecond bitmap/worker costs. These samples do not identify the Redmi bottleneck. DEVICE_CONNECTED=no, so no affected-device BEFORE exists and no optimization was made. 93 Python/9 Node plus syntax/diff PASS; four-file staging parity and final WebGL2 telemetry smoke PASS. Release /opt/an3-arcade-staging/releases/20260909-144343-af16e551490f; rollback /opt/an3-arcade-staging/releases/20260909-143353-2a6e1d919803. Production untouched.

Continue P2 with Sol Medium after reconnecting Redmi. Report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P2_20260909.md

## P3 current authority — 2026-09-09

P3 COMPLETE. Added persisted Auto/WebGPU/WebGL2 choice, requested/effective/fallback display, expandable safe diagnostics and Copy Diagnostics. Reproduced stale query-cached CSS clipping and fixed player CSS with pathname versioning plus offline-shell entry. Final staging e9cca6502858, release /opt/an3-arcade-staging/releases/20260909-194251-e9cca6502858, rollback /opt/an3-arcade-staging/releases/20260909-152355-56d5a972da2d. 93 Python/12 Node tests, syntax/diff and five-file served parity PASS. Desktop copy/animated output and AVD options UI portrait/landscape PASS. Fullscreen did not activate in hidden browser; extended input/menu/fullscreen runtime remains UNVERIFIED. No P4 work. Production untouched. Next P4, Sol Light.

Report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P3_20260909.md

## P2 completion after authorized AVD substitution — 2026-09-09T15:07:11+07:00

P2 COMPLETE under the permitted insufficient-evidence classification. The user authorized `codex-nds-api35` instead of physical Redmi. Android15 ARM64/Chrome124 host-GPU WebGL2 advanced at about38.5 core FPS while presentation remained about60 FPS with sub-millisecond bitmap/worker costs, suggesting a virtual DEVICE/CPU/WASM limit. Both source and presentation remained black, so visible gameplay and the matched New Game scene failed. Requested WebGPU failed at requestAdapter and correctly fell back to WebGL2. SwiftShader reached completed startup but became diagnostically unresponsive without visible gameplay. The AVD uses Apple M5 host resources and cannot represent Redmi GPU/CPU/thermal/browser behavior; no optimization was justified or made. Staging remains asset af16e551490f; no redeployment. Production untouched. Next P3, Astra Light.

Report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P2_20260909.md

## P4 artifact publication — 2026-09-09

P4 COMPLETE. Staging now exposes a machine-readable five-category artifact manifest and matching Release Center. Eligibility requires an explicit evidence allowlist plus exact size and SHA-256. macOS DMG 0.4.4 and Android APK 0.1.1 pass and are downloadable; Linux DEB, Linux Flatpak and Windows EXE remain blocked without links. Service-worker packaging includes the page assets while installer/source downloads bypass caches and the manifest stays network-only. 94 Python and 12 Node tests pass. Live staging downloads matched both hashes; unlisted artifacts returned 404. Asset `8ecb7b06ad8c`, release `/opt/an3-arcade-staging/releases/20260909-195906-8ecb7b06ad8c`, rollback `/opt/an3-arcade-staging/releases/20260909-194251-e9cca6502858`. Production untouched. Next P5, Astra Medium.

Report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P4_20260909.md
