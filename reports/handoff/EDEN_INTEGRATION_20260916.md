# Eden native integration — progress report (2026-09-16)

Continues Vibe Coded Emulator 2.0.0. Status labels are used exactly:
**Implemented and tested**, **Implemented but not runtime-verified**,
**In progress**, **Blocked**, **Not started**.

## Status overview

| Item | Status |
| --- | --- |
| Phase 0 — verify checkpoint/state | Implemented and tested |
| Phase 1 — C ABI bridge + smoke test (null backend) | Implemented and tested |
| Milestone A — Eden configured + `core` built at the pinned commit | Implemented and tested |
| Eden backend `backend_eden.cpp` — compiles against Eden headers | Implemented but not runtime-verified |
| Milestone B (Eden-backed) — link + run the smoke test | In progress (2 link items) |
| Milestone C — Rust integration | Not started |
| Milestones D–G (rendering, homebrew launch, input/audio, app UI) | Blocked (see below) |

## Delivered

- `native/eden-bridge/` — the C++ bridge:
  - `include/an3_eden_bridge.h`: versioned C ABI (opaque handles only, no C++
    types), status codes, frame callback, libretro-compatible button ids.
  - `src/an3_eden_bridge.cpp`: handle/state validation, idempotent
    stop/shutdown, exception containment, per-core diagnostics.
  - `src/backend_null.cpp`: honest fallback (UNAVAILABLE, never fake success).
  - `src/backend_eden.cpp`: headless `EmuWindow` + `Core::System` lifecycle +
    `System::Load` result mapping (compiles against Eden at the pinned SHA).
  - `tests/bridge_smoke.c`: standalone C smoke test.
  - `integration/CMakeLists.txt`: builds the bridge inside Eden's tree.
  - `README.md`: integration design (subsystems, frontend services, minimum
    interface, graphics, threads, errors, platform limits).
- `docs/checkpoints/eden-native-integration.md`: running checkpoint.
- Eden pinned at **`7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c`** and built.

## Verification actually performed

- Suite: **271 tests, 0 failures** (unchanged by the bridge).
- Bridge smoke test (null backend): **38 checks, 0 failures** — ABI version,
  null/invalid handles, use-before-initialise for every entry point, invalid
  port/button ids, idempotent stop/shutdown, UNAVAILABLE diagnostics.
- Eden build: configure `CONFIGURE_EXIT=0`; `cmake --build --target core
  -j 10` → `BUILD_EXIT=0`, `src/core/libcore.a` produced (1314 targets).
- `backend_eden.cpp` compiled successfully against Eden's real headers.

## Blockers

### Requires the owner
1. **Public source repository URL** — `git remote -v` is a local path; nothing in
   the deployment config or metadata exposes a public URL. The README/
   `AN3_SOURCE_REPOSITORY` still hold a placeholder. **No new combined binaries
   may be published until this exists** (GPL corresponding-source condition).
2. **Legal homebrew Switch test content** — Milestone E needs an NRO whose
   redistribution/use rights are verified, or one you provide. Without it, game
   boot cannot be verified and Switch must stay unadvertised.

### Engineering (I can continue)
3. **Eden link integration** (Milestone B with `backend=eden`):
   - `typeinfo for Core::Frontend::EmuWindow` is undefined:
     `frontend/emu_window.cpp.o` defines the methods and vtable but emits no
     typeinfo symbol, so a derived class with RTTI in another TU cannot resolve
     it. Fix: compile the bridge with matching RTTI/visibility flags, or mirror
     how Eden's own frontends obtain it.
   - `vmaAllocateMemory` undefined: Eden's `GPUOpen::VulkanMemoryAllocator`
     (FetchContent) implementation object is not linked by the standalone
     target. Fix: build with `-DYUZU_CMD=ON` and reuse that target's link set.
4. **Hardware for runtime rendering verification**: the Dell has only the Mesa
   software rasterizer (lavapipe, `vendorID 0x10005`) and no cmake/ninja, so it
   is not a runtime target. The macOS MacBook (Apple Silicon) is the integration
   target; it has no full Xcode (CommandLineTools only), which did not block the
   `core` build.

## Licensing status

Unchanged and compliant for the bridge itself: it is an original work under
GPL-3.0-or-later and Eden is GPL-3.0-or-later at the pinned revision. No Eden
source is vendored into this repository (it is fetched and pinned by commit).
If Eden is ever shipped in a binary, the release must include Eden's
corresponding source at the pinned commit and preserve its notices.

## Staging status

Unchanged: asset `973c9002b67f`, healthy. **Nothing Switch-related is deployed**
and no Switch feature is advertised. Production untouched.
