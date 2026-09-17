# Checkpoint — Eden native integration (continuing)

Updated after each completed phase. Recovery: nothing here rewrites history; all
work is additive commits on `apps-web`. To undo a phase, revert its commit.

## Resume state (verified 2026-09-17)

- Branch `apps-web`; Eden pinned at `7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c`.
- Version **2.1.0** on all five packaged platforms; GPL-3.0-or-later.
- Test suite: **285 tests, OK** (`python3 -m unittest discover -s tests`).
- Existing GBA/NDS/3DS libretro path untouched; per-platform renderers unchanged.
- Staging: asset version unchanged. **Nothing Switch-related is deployed** and
  no Switch feature is advertised.
- The Eden bridge is its own out-of-tree build; nothing under `native-offline/`
  or the web player changed, so no packaged artifact was rebuilt.

## Status overview

| Item | Status |
| --- | --- |
| Phase 0 — checkpoint/state verification | Implemented and tested |
| Phase 1 — C ABI bridge + smoke test (null backend) | Implemented and tested |
| Milestone A — Eden configured + `core` built at the pinned commit | Implemented and tested |
| Milestone B — Eden-backed bridge links + runs the smoke test | **Implemented, built, and runtime-verified** |
| Milestone B+ — a real legal homebrew NRO (nx-hbmenu v3.6.1) loads and starts | **Implemented and runtime-verified (macOS, MoltenVK)** |
| Milestone C — Rust/AN3 integration | Not started |
| Milestone D — frame readback / presentation to the AN3 surface | Blocked engineering (see below) |
| Milestone E — input, audio, saves, app UI | Not started |

## Completed phases

### Phase 0 — verification (done)

Read the checkpoint, licensing audit, distribution-compliance and Eden
feasibility docs, plus `docs/vibe-coded-switch-companion.md`; verified git state,
versions, and that the suite passed.

### Phase 1 — C ABI bridge + smoke test (Implemented and tested)

`native/eden-bridge/`: versioned C ABI (`include/an3_eden_bridge.h`), dispatcher
with handle/state validation and exception containment
(`src/an3_eden_bridge.cpp`), a `null` backend, CMake build, and a C smoke test
(`tests/bridge_smoke.c`). Null-backend build: 38 checks, 0 failures.

### Phase 2 — Eden baseline build (Milestone A, DONE)

`core` built at the pinned SHA on macOS (`CONFIGURE_EXIT=0`, `BUILD_EXIT=0`,
`src/core/libcore.a`). Commands in `native/eden-bridge/README.md`.

### Phase 3 — link integration (Milestone B, DONE — previously the two blockers)

Both link items from the 2026-09-16 report are resolved:

1. **RTTI**: Eden compiles all targets with `-fno-rtti`, so `core` emits **no**
   `typeinfo for Core::Frontend::EmuWindow` (the vtable is emitted, the typeinfo
   is not). The bridge is now compiled `-fno-rtti` (it uses no RTTI), so the
   derived `EmuWindow` no longer references a symbol that does not exist.
2. **VMA**: `vmaAllocateMemory` and friends were undefined because VMA is
   header-only and Eden instantiates it in exactly one frontend TU, all disabled
   in this build. `integration/vma_impl.cpp` now provides that single
   implementation. `core` links `video_core` PRIVATE, so the Vulkan/VMA header
   targets are linked to the bridge explicitly.

Build integration changes are in `integration/CMakeLists.txt`; the fragile
`-force_load` workaround was removed.

### Phase 4 — runtime verification + real content (DONE, macOS)

- Fixed a lifecycle crash: Eden's `System::Load()` calls
  `KernelCore::Initialize()` before validating content, so a load that fails can
  leave kernel state behind; destroying `Core::System` without shutting it down
  crashes in `~KernelCore::Impl`. The bridge now shuts the kernel down exactly
  once (`kernel_initialized` flag) and never twice.
- Fixed the dispatcher: a successful load now enters `State::Loaded`, `start`
  only from `Loaded`, and pause/resume use `System::Pause()`/`System::Run()`.
- Fixed `Load` parity with Eden frontends: `params.applet_id =
  AppletId::Application`, logging initialisation, content provider + filesystem
  factories before load, and `GPU().Start()` + `GetCpuManager().OnGpuReady()`
  before `System::Run()`.
- Added a macOS presentation host: Eden's pinned `Vulkan::CreateSurface()` has no
  Headless branch, so `src/cocoa_surface.mm` creates an offscreen `CAMetalLayer`
  (no window) that MoltenVK accepts as a present-capable surface.

**Runtime results** (macOS, Apple M5, MoltenVK 1.4.1 via `LIBVULKAN_PATH`):

- `an3_eden_bridge_smoke` (backend `eden`, non-existent content): **39 checks,
  0 failures**, clean shutdown (no crash).
- `an3_eden_bridge_smoke <hbmenu.nro>`: **50 checks, 0 failures** — nx-hbmenu
  v3.6.1 (legal homebrew, ISC) loads, the GPU initialises, the process starts,
  pause/resume/stop/shutdown all succeed. Frame callbacks = 0 (no readback yet).

## Blockers

### Requires the owner

1. **Public source repository URL** — `git remote -v` is a local path; the README
   still holds `https://REPLACE-WITH-PUBLIC-REPOSITORY-URL`. No combined binary
   may be published until this exists (GPL corresponding-source condition).
2. **Runtime hardware for Windows/Linux** — the Dell has only the Mesa software
   rasterizer (lavapipe) and no cmake/ninja; macOS is the only verified runtime.

### Engineering (I can continue)

3. **Frame readback/presentation (Milestone D)** — `run_frame` does not yet
   invoke the caller's callback with pixels. Eden renders to its own Vulkan
   swapchain on the `CAMetalLayer`; delivering frames to AN3 needs either a
   swapchain image copy/readback or a shared presentation surface hosted by the
   AN3 process. No pixel data is faked.
4. **Input/audio/saves (Milestone E)** — `submit_button`/`submit_analog`/
   `save_data` return `AN3_EDEN_ERR_UNSUPPORTED`; wiring Eden's HID services is
   the next milestone. The smoke test accepts `OK` or `UNSUPPORTED` for these.
5. **Eden upstream defect (recorded, RG-111)** — a `Load` failure that runs
   `ShutdownMainProcess()` then destroys the local `Process` (e.g.
   `ErrorVideoCore`) terminates in a `noexcept` destructor. Tolerating GPU-init
   failure needs an Eden patch or an upstream fix.

## Licensing status

Unchanged and compliant for the bridge itself: an original work under
GPL-3.0-or-later; Eden is GPL-3.0-or-later at the pinned revision and is fetched
and pinned by commit, not vendored. If Eden is ever shipped in a binary, the
release must include Eden's corresponding source at the pinned commit and
preserve its notices.

## Next step

Milestone D: frame delivery. Decide between (a) a swapchain image copy/readback
into a callback-owned buffer (simplest, no extra window) and (b) a hosted AN3
window/CAMetalLayer shared with the bridge. Then Milestone E: HID input mapping
from the libretro button ids already defined in the ABI.

## Test-content note

Legal verification content used: `nx-hbmenu` v3.6.1
(`switchbrew/nx-hbmenu`, ISC), downloaded to a temporary directory
(`hbmenu.nro`, 2,455,539 bytes, SHA-256
`6cf6d130515723ebe0041c2479420caf9726895087439ff7b2e528c2ed39c100`). It is not
committed to this repository.
