# an3-eden-bridge — C ABI between Vibe Coded Emulator and Eden

Status: **bridge ABI implemented and tested**; the Eden-backed implementation is
in progress (see `docs/checkpoints/eden-native-integration.md`).

## Layout

```
native/eden-bridge/
  include/an3_eden_bridge.h   public, versioned C ABI (opaque handles only)
  src/an3_eden_internal.h     shared internal definitions
  src/an3_eden_bridge.cpp     dispatcher: validation, lifecycle, exception containment
  src/backend_null.cpp        fallback backend (no Eden): clear UNAVAILABLE errors
  src/backend_eden.cpp        Eden backend (compiled only with AN3_EDEN_ENABLED)
  tests/bridge_smoke.c        standalone C smoke test (runs with either backend)
  CMakeLists.txt
```

## Build

```bash
# Bridge only (null backend), plus the smoke test:
cmake -S native/eden-bridge -B build/eden-bridge -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/eden-bridge
ctest --test-dir build/eden-bridge --output-on-failure
```

With Eden (`AN3_EDEN_ENABLED=ON`) the backend is compiled inside Eden's build
tree so it can link Eden's `core` target; see "Eden build" below.

## Eden build (macOS, pinned revision)

Eden is **not** vendored; it is built out-of-tree and pinned by commit.

```bash
git clone --depth 1 https://git.eden-emu.dev/eden-emu/eden.git /tmp/eden
cd /tmp/eden && git fetch --depth 1 origin 7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c
git checkout FETCH_HEAD
# macOS prerequisites: cmake ninja autoconf automake libtool glslang (brew)
cmake -S /tmp/eden -B /tmp/eden-build -G Ninja \
  -DENABLE_QT=OFF -DYUZU_CMD=OFF -DENABLE_LIBUSB=OFF \
  -DENABLE_WERROR=OFF -DENABLE_DEBUG_TOOLS=OFF -DENABLE_RESHADE=OFF \
  -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/eden-build --target core -j 10
```

No Qt frontend is built. `core` is Eden's CMake static library
(`add_library(core STATIC …)`).

## Integration design

### Required Eden subsystems

`core` (CPU/ARM, kernel, services, loaders), `video_core` (GPU + Vulkan
renderer), `audio_core`, `hid_core`, `input_common`, `network`, `common`.

### Required frontend services

- `Core::Frontend::EmuWindow` (this is the boundary the bridge implements).
- `Service::AM::FrontendAppletParameters` (applet launch parameters).
- A `Core::Frontend::GraphicsContext` from `CreateSharedContext()`.

### Minimum native interface

The C ABI in `include/an3_eden_bridge.h`: create/destroy, initialize(keys dir,
firmware dir), load(content), start, pause/resume, run_frame(callback),
submit_button/submit_analog, save_data, stop, shutdown, plus ABI version, backend
name, status messages and per-core last error.

### Graphics

Eden owns a Vulkan device and its own swapchain/WSI. The core supports
`WindowSystemType::Headless` with `render_surface = nullptr`
(upstream comment: "the video backend will run in headless mode"), which is the
first integration step: drive the core without a host surface and, when needed,
read frames back for the caller's callback. A hosted presentation surface
(native window / `CAMetalLayer` on macOS) is the follow-on step and must use
Eden's own device — Vulkan/Metal objects are **not** shared across independently
created devices. No CPU readback is added to the existing GBA/NDS/3DS paths;
they keep their current renderers.

### Thread ownership

One `an3_eden_core` handle must be used from a single thread at a time. The ABI
is not thread-safe by design; callers serialize. `run_frame` executes on the
caller's thread. The Rust side owns a dedicated emulation thread per session.

### Error propagation

No exceptions cross the ABI (`guard()` catches everything). Failures return
`an3_eden_status`; `an3_eden_last_error` carries a short diagnostic. Explicit
codes cover invalid handles/arguments, init ordering, busy, I/O, unsupported,
unavailable and `KEYS_REQUIRED`.

### Platform limitations

- **macOS (first target)**: Apple Silicon + MoltenVK. Eden's Vulkan path needs
  MoltenVK; the repo already vendors MoltenVK 1.4.2 for macOS.
- **Linux**: the Dell has only the Mesa software rasterizer (lavapipe,
  `vendorID 0x10005`) and no cmake/ninja, so it is not a runtime target.
- **Windows/Android**: not started; Android needs NDK/JNI adaptations.

### Licensing

Eden is GPL-3.0-or-later at the pinned commit; the bridge is a new original work
under the same license. Combined distributions must ship Eden's corresponding
source at the pinned revision and preserve its notices (see
`docs/licensing/eden-integration-feasibility.md`).
