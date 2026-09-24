# Rendering architecture

Vibe Coded Emulator has two independent rendering paths: the browser player and
the native apps. They share no GPU code; keeping them separate is deliberate.

## Web player

- EmulatorJS drives the emulator core in WebAssembly and owns the canvas.
- `static/player-runtime.js` resolves the renderer (`WebGPU` → `WebGL2` →
  `WebGL`) and exposes a stable adapter surface to `static/player.js`.
- Presentation is drawn to a separate canvas owned by the renderer worker; the
  EmulatorJS **source** canvas stays the authoritative input target. Touch and
  pointer input always resolve to the source canvas, never the presentation
  layer. See `docs/architecture/player-layering.md`.
- The service worker precaches cores; the same-origin cache is versioned by the
  asset hash so an update cannot alias stale files.

## Native apps

- `native-offline/native-runtime/` hosts the libretro cores through a portable
  frontend (`core/libretro_host.*`) and a video-backend abstraction
  (`core/video_backend.h`).
- Per-platform presentation:
  - **macOS**: Objective-C++ host (`src-tauri/src/azahar_host.mm`,
    `vulkan_frontend.mm`) with Metal/MoltenVK and a native view; the app is
    ad-hoc signed in staging.
  - **Windows / Linux**: SDL/GTK frontends
    (`native-runtime/platform/linux/`, shared by Windows) with Vulkan preferred
    and OpenGL as the software-core fallback.
  - **Android**: `native-runtime/platform/android/` with a `SurfaceView`, Vulkan
    preferred and OpenGL ES 3 fallback; 3DS uses the core's OpenGL ES renderer
    with a frontend-owned EGL context.
- Frames stay on the GPU: there is no per-frame CPU readback, pipeline
  recreation, or `glFinish`/`glReadPixels` on the hot path. A shared frame path
  transfers handles, not pixels, where the platform allows it.
- The native input model (`NativeInput`) is snapshot-based over a libretro
  joypad bitmask plus analogue/pointer state.

## Nintendo Switch (Eden)

Eden owns its own Vulkan device and swapchain. The bridge (`native/eden-bridge/`)
starts with a headless `EmuWindow` so it can drive Eden's core without a host
surface. A hosted presentation surface must use Eden's device; Vulkan/Metal
objects are not shared across independently created devices. This path is not
runtime-verified yet.
