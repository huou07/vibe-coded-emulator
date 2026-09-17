# an3-eden-bridge — C ABI between Vibe Coded Emulator and Eden

Status: **bridge ABI implemented and tested; the Eden-backed implementation links
and runs on macOS.** A legal homebrew NRO (nx-hbmenu v3.6.1) loads, the GPU
initialises, and the lifecycle passes its smoke test (50 checks, 0 failures).
Frame readback and input are later milestones. See
`docs/checkpoints/eden-native-integration.md`.

## Layout

```
native/eden-bridge/
  include/an3_eden_bridge.h   public, versioned C ABI (opaque handles only)
  src/an3_eden_internal.h     shared internal definitions
  src/an3_eden_bridge.cpp     dispatcher: validation, lifecycle, exception containment
  src/backend_null.cpp        fallback backend (no Eden): clear UNAVAILABLE errors
  src/backend_eden.cpp        Eden backend (compiled only with AN3_EDEN_ENABLED)
  src/cocoa_surface.{h,mm}    macOS Cocoa CAMetalLayer host for Eden's renderer
  tests/bridge_smoke.c        standalone C smoke test (runs with either backend)
  integration/CMakeLists.txt  builds the bridge inside Eden's tree
  integration/vma_impl.cpp    the single VulkanMemoryAllocator implementation TU
  CMakeLists.txt
```

## Build

```bash
# Bridge only (null backend), plus the smoke test:
cmake -S native/eden-bridge -B build/eden-bridge -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/eden-bridge
ctest --test-dir build/eden-bridge --output-on-failure
```

With Eden, the backend is compiled **inside Eden's build tree** so it can link
Eden's `core` target; see "Eden build" below.

## Eden build (macOS, pinned revision)

Eden is **not** vendored; it is built out-of-tree and pinned by commit.

```bash
git clone --depth 1 https://git.eden-emu.dev/eden-emu/eden.git /tmp/eden
cd /tmp/eden && git fetch --depth 1 origin 7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c
git checkout FETCH_HEAD
# macOS prerequisites: cmake ninja autoconf automake libtool glslang (brew)
# Append the integration subdirectory to Eden's top-level CMakeLists.txt:
#   add_subdirectory("${AN3_EDEN_BRIDGE_DIR}/integration" an3_eden_bridge)
cmake -S /tmp/eden -B /tmp/eden-build -G Ninja \
  -DAN3_EDEN_BRIDGE_DIR="$PWD/native/eden-bridge" \
  -DENABLE_QT=OFF -DYUZU_CMD=OFF -DENABLE_LIBUSB=OFF \
  -DENABLE_WERROR=OFF -DENABLE_DEBUG_TOOLS=OFF -DENABLE_RESHADE=OFF \
  -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/eden-build --target an3_eden_bridge_smoke -j 10
```

### Two build-integration facts (see RG-108)

- Eden compiles every target with `-fno-rtti`, so `core` emits no
  `typeinfo for Core::Frontend::EmuWindow`; the bridge is therefore compiled
  `-fno-rtti` too.
- VMA is header-only and Eden defines `VMA_IMPLEMENTATION` only in a frontend TU
  (all disabled here), so `integration/vma_impl.cpp` supplies the single
  implementation. Do not also build an Eden frontend into the same target.

### Running

Eden's macOS renderer needs MoltenVK and a Cocoa `CAMetalLayer`; there is no
headless surface path in the pinned revision. The bridge creates an offscreen
layer (`src/cocoa_surface.mm`). Point Eden at MoltenVK with `LIBVULKAN_PATH`:

```bash
export LIBVULKAN_PATH="/tmp/eden/.cache/cpm/moltenvk/v1.4.1-ryujinx/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib"
# Error paths (no content):
/tmp/eden-build/bin/an3_eden_bridge_smoke
# Real legal homebrew content (nx-hbmenu v3.6.1 is ISC-licensed):
/tmp/eden-build/bin/an3_eden_bridge_smoke /path/to/hbmenu.nro
```

Without `LIBVULKAN_PATH`, initialise still succeeds but `load` reports
`ErrorVideoCore` because the Vulkan library cannot be opened.

## Integration design

### Required Eden subsystems

`core` (CPU/ARM, kernel, services, loaders), `video_core` (GPU + Vulkan
renderer), `audio_core`, `hid_core`, `input_common`, `network`, `common`.

### Required frontend services

- `Core::Frontend::EmuWindow` (this is the boundary the bridge implements).
- `Service::AM::FrontendAppletParameters` — the bridge sets
  `applet_id = AppletId::Application` as Eden's frontends do.
- A `Core::Frontend::GraphicsContext` from `CreateSharedContext()`.

### Startup sequence (mirrors Eden's own frontends)

1. `Core::System::Initialize()`.
2. Set the content provider and filesystem, then
   `GetFileSystemController().CreateFactories(...)` and `GetUserChannel().clear()`.
3. `System::Load(emu_window, path, params)`.
4. `GPU().Start()`, `GetCpuManager().OnGpuReady()`, `System::Run()`.
5. On stop/shutdown, `System::ShutdownMainProcess()` exactly once.

### Graphics

Eden owns a Vulkan device and its own swapchain/WSI. On macOS the bridge supplies
an offscreen `CAMetalLayer`; on Windows/Linux a real Win32/X11/Wayland surface is
required (not implemented yet). Frame readback into the caller's callback is a
later milestone and is never faked — `run_frame` currently invokes no pixels.

### Thread ownership

One `an3_eden_core` handle must be used from a single thread at a time. The ABI
is not thread-safe by design; callers serialize.

### Error propagation

No exceptions cross the ABI (`guard()` catches everything). Failures return
`an3_eden_status`; `an3_eden_last_error` carries a short diagnostic.

### Known upstream limitation (RG-111)

A `System::Load()` failure that reaches `ShutdownMainProcess()` (for example
`ErrorVideoCore`) terminates in Eden's `noexcept` `Process` destructor because it
unregisters kernel objects after the kernel list container was reset. The bridge
avoids the path by making the load succeed (a real presentation surface is
required); it cannot catch the termination.

### Platform limitations

- **macOS (first target)**: Apple Silicon + MoltenVK (verified).
- **Linux**: the Dell has only the Mesa software rasterizer (lavapipe) and no
  cmake/ninja, so it is not a runtime target.
- **Windows/Android**: not started; Android needs NDK/JNI adaptations.

### Licensing

Eden is GPL-3.0-or-later at the pinned commit; the bridge is a new original work
under the same license. Combined distributions must ship Eden's corresponding
source at the pinned revision and preserve its notices (see
`docs/licensing/eden-integration-feasibility.md`).
