# an3-eden-bridge — C ABI between Vibe Coded Emulator and Eden

Status: **bridge ABI implemented and tested; the Eden-backed implementation links
and runs on macOS.** A legal homebrew NRO (nx-hbmenu v3.6.1) loads, the GPU
initialises, and the lifecycle passes its smoke test (69 checks, 0 failures with
input). Sustained rendering is stable (RG-115 fixed: the layer is hosted on a
hidden window) and **buttons/analog work** through Eden's virtual_gamepad engine
(RG-116). Frame readback into the caller's callback is the remaining milestone.
See `docs/checkpoints/eden-native-integration.md`.

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
# Machine-readable, deterministic (agent/CI):
/tmp/eden-build/bin/an3_eden_bridge_smoke --json --frames 1 /path/to/hbmenu.nro
#   -> AN3CTL_STATUS {"target":"switch",...,"result":"PASS"}
```

`--frames N` runs exactly N emulated frames after start. **Known limitation:**
more than a handful of frames aborts on macOS (MoltenVK drawable failure on the
unhosted `CAMetalLayer`); see `docs/REGRESSION_GUARDS.md` RG-115. Load + a few
frames are verified; sustained rendering is not.

Without `LIBVULKAN_PATH`, initialise still succeeds but `load` reports
`ErrorVideoCore` because the Vulkan library cannot be opened.

## Input

`an3_eden_submit_button` / `an3_eden_submit_analog` write into Eden's
`virtual_gamepad` engine, which Eden's `EmulatedController` already binds for
player 1 (`LoadVirtualGamepadParams`). The bridge owns one `InputSubsystem`
(created before `Core::System` so the engine factory is registered when HIDCore
builds its devices). `an3_eden_get_button` / `an3_eden_get_analog` read Eden's
emulated-controller state back, so a test proves the input reached the emulator.
The analog ABI takes a stick selector (`AN3_EDEN_STICK_LEFT/RIGHT`).

## Saves

Eden owns writing save data. `an3_eden_get_save_dir` reports Eden's
`EdenPath::SaveDir`, and `an3_eden_save_data(path)` exports that tree to `path`
(a recursive copy) so AN3 can back it up or sync it without touching the live
saves.

## Companion (production boundary)

`an3_switch_companion` is the separate-process Switch component. AN3 **launches**
it (it never links Eden into the AN3 binary), so the GPL boundary stays on the
companion.

```bash
# Windowed play (visible AppKit window; keyboard input):
AN3_EDEN_WINDOW_VISIBLE=1 \
  LIBVULKAN_PATH=<moltenvk dylib> \
  an3_switch_companion /path/to/hbmenu.nro --visible

# Automation / CI (hidden, line protocol on stdin):
printf 'button A down\nbutton A up\nanalog L 0.5 -0.25\nstatus\nquit\n' | \
  an3_switch_companion /path/to/hbmenu.nro --seconds 5
```

Windowed keyboard map: A/S→Y/X, Z/X→B/A, Q/W→L/R, E/R→ZL/ZR, Return→Plus,
Delete→Minus, arrows→d-pad, Space→A. Stdin protocol: `button <name> <down|up>`,
`analog <L|R> <x> <y>`, `status`, `quit`; it emits `AN3CTL_ACK` per command and
`AN3CTL_STATUS {"target":"switch",…}` on start/stop.

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
