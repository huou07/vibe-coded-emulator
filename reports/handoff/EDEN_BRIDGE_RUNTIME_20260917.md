# Eden native bridge — link + runtime report (2026-09-17)

Continues Vibe Coded Emulator 2.1.0. Status labels are used exactly:
**Implemented and tested**, **Implemented but not runtime-verified**,
**In progress**, **Blocked**, **Not started**.

## Status overview

| Item | Status |
| --- | --- |
| Milestone B — Eden-backed bridge links + runs the smoke test | Implemented and tested |
| Milestone B+ — legal homebrew NRO (nx-hbmenu v3.6.1) loads and starts | Implemented and runtime-verified (macOS) |
| Milestone D — frame readback/presentation to AN3 | Blocked engineering (see below) |
| Milestone E — input / audio / saves / app UI | Not started |
| Milestone C — Rust/AN3 integration | Not started |

## Delivered

- **Link integration fixed** (`native/eden-bridge/integration/CMakeLists.txt`):
  - The bridge is compiled `-fno-rtti` to match Eden. Eden compiles every target
    `-fno-rtti` (`src/CMakeLists.txt`), so `core` emits the vtable but **no**
    `typeinfo for Core::Frontend::EmuWindow`; the derived `EmuWindow` previously
    referenced a symbol that does not exist.
  - `integration/vma_impl.cpp` supplies the one `VMA_IMPLEMENTATION` TU. VMA is
    header-only and Eden instantiates it only in a frontend TU
    (`src/yuzu/main_window.cpp`, `src/yuzu_cmd/yuzu.cpp`, Android `native.cpp`),
    all disabled with `-DENABLE_QT=OFF -DYUZU_CMD=OFF`.
  - `Vulkan::Headers`, `Vulkan::UtilityHeaders` and
    `GPUOpen::VulkanMemoryAllocator` are linked explicitly because `core` links
    `video_core` PRIVATE. The `-force_load` workaround was removed.
- **Lifecycle correctness** (`src/backend_eden.cpp`, `src/an3_eden_bridge.cpp`):
  - `kernel_initialized` tracks whether a `Load` left Eden's kernel initialised,
    and `System::ShutdownMainProcess()` is called exactly once (on
    `ErrorGetLoader`, on `stop`/`shutdown`, and never twice).
  - A successful load now enters `State::Loaded`; `start` is allowed only from
    `Loaded`; pause/resume use `System::Pause()`/`System::Run()`.
  - `params.applet_id = AppletId::Application`, logging initialisation, content
    provider + filesystem factories before load, and `GPU().Start()` +
    `GetCpuManager().OnGpuReady()` before `System::Run()` — matching Eden's own
    frontend startup.
- **macOS presentation host** (`src/cocoa_surface.{h,mm}`): an offscreen
  `CAMetalLayer` (no `NSWindow`/`NSApplication`). Eden's pinned
  `Vulkan::CreateSurface()` has no Headless branch, so without a Cocoa surface
  the GPU fails to initialise.
- **Smoke test** (`tests/bridge_smoke.c`): optional content path argument,
  status/loader-error diagnostics, and input checks that accept `UNSUPPORTED`
  (input is not implemented yet).

## Verification actually performed

- Repository suite: **285 tests, OK** (`python3 -m unittest discover -s tests`).
- Null-backend bridge build: **38 checks, 0 failures**.
- Eden backend, non-existent content (no Vulkan library): **39 checks,
  0 failures**; `load` → `UNSUPPORTED`, clean shutdown (no crash).
- Eden backend, real content, macOS Apple M5 + MoltenVK 1.4.1
  (`LIBVULKAN_PATH=/tmp/eden/.cache/cpm/moltenvk/v1.4.1-ryujinx/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib`):
  **50 checks, 0 failures**. Output includes
  `an3-eden-bridge loaded …/hbmenu.nro`,
  `an3-eden-bridge run_frame: frame callbacks=0`,
  `an3-eden-bridge smoke: 50 checks, 0 failures`; Eden logs show a `VkDevice`
  created (27 extensions) and system archives synthesised. Frame callbacks = 0
  because no readback exists (none is faked).
- Standalone probe: an offscreen `CAMetalLayer` yields a present-capable
  `VkSurfaceKHR` under MoltenVK (device 0 queues 0–3 support present).

### Test content

`nx-hbmenu` v3.6.1 (`switchbrew/nx-hbmenu`, **ISC**, freely redistributable),
`hbmenu.nro`, 2,455,539 bytes, SHA-256
`6cf6d130515723ebe0041c2479420caf9726895087439ff7b2e528c2ed39c100`. Downloaded to
a temporary directory; not committed.

## Blockers

### Requires the owner

1. **Public source repository URL** — still a placeholder; no combined binary may
   be published until the GPL corresponding-source condition is satisfiable.
2. **Windows/Linux runtime hardware** — the Dell has only the Mesa software
   rasterizer and no cmake/ninja.

### Engineering

3. **Frame delivery (Milestone D)** — `run_frame` invokes no pixel callback.
   Eden renders to its own swapchain; delivery needs a swapchain copy/readback or
   a shared presentation surface.
4. **Input/audio/saves (Milestone E)** — the corresponding ABI calls return
   `UNSUPPORTED`.
5. **Eden upstream defect (RG-111)** — a `Load` failure that reaches
   `ShutdownMainProcess()` then destroys the local `Process` (for example
   `ErrorVideoCore`) terminates inside a `noexcept` destructor. The bridge avoids
   the path; tolerating GPU-init failure needs an Eden patch or upstream fix.

## Licensing status

Unchanged and compliant: the bridge is GPL-3.0-or-later; Eden is pinned by commit
and not vendored. No keys/firmware/commercial ROM is bundled.

## Staging / production status

Untouched. Nothing Switch-related is deployed and no Switch feature is
advertised. No packaged artifact changed, so no app version bump was required.

## Changed files

Added: `native/eden-bridge/integration/vma_impl.cpp`,
`native/eden-bridge/src/cocoa_surface.h`, `native/eden-bridge/src/cocoa_surface.mm`.
Modified: `native/eden-bridge/integration/CMakeLists.txt`,
`native/eden-bridge/src/backend_eden.cpp`,
`native/eden-bridge/src/an3_eden_bridge.cpp`,
`native/eden-bridge/tests/bridge_smoke.c`, `native/eden-bridge/README.md`,
`docs/checkpoints/eden-native-integration.md`, `docs/REGRESSION_GUARDS.md`
(RG-108…RG-111).
