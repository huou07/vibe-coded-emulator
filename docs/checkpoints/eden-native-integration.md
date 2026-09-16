# Checkpoint — Eden native integration (continuing)

Updated after each completed phase. Recovery: nothing here rewrites history; all
work is additive commits on `apps-web`. To undo a phase, revert its commit.

## Resume state (verified 2026-09-16)

- Branch `apps-web`; last commit before this work: `57de898`
  (GPLv3 licensing transition).
- Version **2.0.0** on all five platforms; GPL-3.0-or-later applied.
- Test suite: **271 tests, 0 failures** (verified by running it).
- Existing GBA/NDS/3DS libretro path untouched; per-platform renderers unchanged.
- Staging: asset `973c9002b67f`.
- Eden pinned: **`7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c`** (verified in the
  clone: `git log -1` shows that SHA).

## Blockers found (require owner)

1. **Public source repository URL is unresolved.** `git remote -v` is a local
   path; no deployment config or metadata exposes a public URL. The README uses
   the placeholder `https://REPLACE-WITH-PUBLIC-REPOSITORY-URL` and
   `AN3_SOURCE_REPOSITORY` overrides it. **Do not publish new combined binaries
   until this is provided** (local integration continues).
2. **No legal Switch test content.** Milestone E needs a homebrew NRO whose
   redistribution/use rights are verified, or one the owner provides. Not
   available in this environment.
3. **Hardware for runtime verification.** The Dell has no hardware Vulkan
   (`vendorID 0x10005` = lavapipe, Mesa software rasterizer) and lacks
   cmake/ninja. macOS (this MacBook, Apple Silicon) is the integration target;
   it has a real GPU via Metal/MoltenVK.

## Completed phases

### Phase 0 — verification (done)

- Read the checkpoint, licensing audit, distribution-compliance and Eden
  feasibility docs, plus `docs/vibe-coded-switch-companion.md`.
- Verified git state, versions, and that the suite passes (271).
- Checked macOS and Dell toolchains/hardware (above).

### Phase 1 — C ABI bridge + smoke test (Implemented and tested)

- `native/eden-bridge/` — versioned C ABI (`include/an3_eden_bridge.h`),
  dispatcher with handle/state validation and exception containment
  (`src/an3_eden_bridge.cpp`), a `null` backend
  (`src/backend_null.cpp`), CMake build and a C smoke test
  (`tests/bridge_smoke.c`).
- **Test result:** builds clean; `an3_eden_bridge_smoke` → `38 checks, 0
  failures` in the null-backend build (ABI version, null/invalid handles,
  use-before-initialise, idempotent stop/shutdown, UNAVAILABLE diagnostics).
- Not runtime-verified against Eden yet (Phase 3).

### Phase 2 — Eden baseline build (Milestone A, DONE)

- Cloned `git.eden-emu.dev/eden-emu/eden` and checked out the pinned SHA.
- Installed build tooling on macOS (cmake, ninja, autoconf/automake/libtool,
  glslang).
- Configure succeeded:
  `cmake -S /tmp/eden -B /tmp/eden-build -G Ninja -DENABLE_QT=OFF -DYUZU_CMD=OFF
  -DENABLE_LIBUSB=OFF -DENABLE_WERROR=OFF -DENABLE_DEBUG_TOOLS=OFF
  -DENABLE_RESHADE=OFF -DCMAKE_BUILD_TYPE=Release` → `CONFIGURE_EXIT=0`.
- **`cmake --build /tmp/eden-build --target core -j 10` → `BUILD_EXIT=0`**;
  `src/core/libcore.a` produced (1314 targets: Boost 1.92, cubeb, FFmpeg deps,
  all Eden subsystems). Exact commands recorded in
  `native/eden-bridge/README.md`.

### Phase 3 — Eden-backed bridge (compiles; link integration in progress)

- Added `src/backend_eden.cpp` (headless `EmuWindow`, `Core::System` lifecycle,
  `System::Load` result mapping) and `integration/CMakeLists.txt` which builds
  the bridge inside Eden's tree.
- **Compiles cleanly against Eden's real headers** (`backend_eden.cpp.o` built
  against `core/core.h`, `core/frontend/emu_window.h`, `graphics_context.h`,
  `am/applet_manager.h`).
- **Link is not complete.** `an3_eden_bridge_smoke` fails to link with:
  - `typeinfo for Core::Frontend::EmuWindow` undefined (weak typeinfo reference
    from a derived class does not pull the archive member; needs
    `-force_load` or an explicit strong reference), and
  - `vmaAllocateMemory` / `vmaCreateAllocator` undefined — Eden's
    `GPUOpen::VulkanMemoryAllocator` (FetchContent external project,
    `VMA_BINARY_DIR=/tmp/eden-build/_deps/vulkanmemoryallocator-build`) is not
    linked by the standalone target.
- Fix path (next step): link the same library set as Eden's own frontend
  (`yuzu_cmd`, built with `-DYUZU_CMD=ON`) and add
  `-Wl,-force_load,<libcore.a>`. Both are build-integration details, not
  architecture changes.
- Not runtime-verified: `initialize`/`load` have not executed yet.

## Next step

Finish the Milestone A link integration (build `yuzu_cmd` as the reference link
set, force-load `libcore.a`, link VMA), then run
`/tmp/eden-build/bin/an3_eden_bridge_smoke` with `backend=eden` to verify
create/initialize/shutdown and the error paths against real Eden.

