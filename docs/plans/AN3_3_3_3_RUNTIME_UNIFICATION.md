# AN3 3.3.3 Runtime Unification Checkpoint

## Scope and safety

This document tracks the cross-platform runtime architecture work authorized for
AN3 3.3.3. The product remains core-only and local-first. Phone Controller, LAN
Sync, Full Library Sync, peer discovery, account/login, cloud sync, and new
networking are out of scope. The known tao/Tauri Android teardown issue remains
`BLOCKED_UPSTREAM` and is not changed here.

No product source has been changed in Phase A. The v3.3.2 macOS architecture
and its release worktree are preserved.

## BASE_SHA

`7110fc3977233b006b6905c50e6dd081b714d4a9` (`v3.3.2`, `github/main` at the
verified public release point).

## BRANCH

`perf/3.3.3-runtime-unification`

## WORKTREE

`/Users/meomeo/Documents/an3-333-runtime-unification`

The existing `/Users/meomeo/Documents/an3-runtime-performance` release/checkpoint
worktree and all other worktrees were left untouched.

## CURRENT_RUNTIME_TOPOLOGY

### macOS GBA/NDS

`AzaharHost` already owns a dedicated `software_core_thread_` running
`core_thread_loop()` and `run_one_core_frame_locked()`. Software output is
published through the bounded three-slot `kSoftwareFrameQueueCapacity` FIFO and
consumed by the MTKView presenter. The existing `SavePersistenceWorker` owns
atomic file writes, fsync, rename, coalescing, bounded pending work, failure
reporting, and clean join. This is the accepted v3.3.2 architecture and will be
preserved.

### macOS 3DS

Azahar hardware/Vulkan rendering remains on the existing synchronous path. No
Phase A evidence justifies changing its core initialization, hardware context,
renderer, layout, input, or backend selection.

### Android GBA/NDS

`jni_runtime.cpp` already starts one dedicated session worker and routes lifecycle
and command execution through it. The worker is the normal caller of
`NativeCoreHost::run_one()`, but periodic, manual, suspend, and exit saves still
call synchronous portable save APIs from that thread. Software presentation is
still performed synchronously by the libretro video callback through the portable
video backend.

### Android 3DS

The shared portable host selects the existing Android Vulkan or GLES hardware
path, including the existing Azahar software-PICA and shader-cache guards. The
hardware path is preserved for later evidence-based work.

### Linux GBA/NDS

`linux_runtime.cpp` owns the SDL event loop, wall-clock deadline scheduler,
input, presentation backend, and `NativeCoreHost::run_one()` call in one general
loop. The software SDL GL backend uploads the callback framebuffer and calls
`SDL_GL_SwapWindow()` synchronously. Autosave, quick save, export, and shutdown
save calls remain synchronous portable host operations.

### Windows GBA/NDS

`build-windows-runtime.sh` compiles the same portable `libretro_host.cpp`, Linux
runtime loop, SDL audio, and SDL GL sources inside the official MSYS2 UCRT64
build. Windows therefore inherits the portable synchronous core/presentation/save
boundaries and will receive the same shared-runtime changes as Linux.

### Linux/Windows 3DS

The portable runtime requires the Vulkan hardware backend for 3DS and rejects
the OpenGL fallback. The existing core-provided GPU image path is retained.

### Switch / Eden companion

Switch uses the separate Eden companion and hosted-frame transport. Its bounded
hosted-frame ring and lifecycle/audio contracts are independent of
`NativeCoreHost`; this work does not rewrite that path.

## KNOWN_SYNCHRONOUS_IO

The portable host performs atomic file open/write/flush/fsync/rename directly in
`write_atomic()`. `NativeCoreHost::Impl::write_save_ram()` snapshots core memory
and writes the `.srm` synchronously; `flush_save_ram()` holds `mutex_` while doing
so. `state()` serializes or unserializes under the same mutex and performs the
state-file write synchronously. `shutdown_locked()` flushes the battery save
before unloading the core. Android, Linux, and Windows adapters can therefore
pause normal runtime cadence on save filesystem work.

The macOS host is different: its core thread makes the required core-owned
snapshot, then `SavePersistenceWorker` performs filesystem work off the core and
presentation paths. Manual durable-save waits are part of the existing macOS
contract and are not being redesigned in Phase A.

## KNOWN_CORE_PRESENT_COUPLING

Portable `NativeCoreHost::run_one()` holds `mutex_` across input sampling and
`retro_run()`. The libretro video callback can call
`video_->present_software()` before `retro_run()` returns. On Linux/Windows GL
this includes texture upload, draw, and `SDL_GL_SwapWindow()`. Android software
backends similarly remain presentation-callback driven. Thus display/GPU timing
can currently extend the core-owner critical section.

The macOS GBA/NDS path has already separated those boundaries with its owned core
thread and bounded software-frame FIFO. The 3DS hardware paths remain coupled by
design until measured evidence requires otherwise.

## KNOWN_AUDIO_LATENCY_PATHS

Android `AAudioBackend` uses a low-latency callback, shared mode, negotiated
sample-rate fallback, and bounded ring-style buffering with xrun counters. This
is existing behavior; no audio change is part of Phase A.

Linux SDL audio uses `SDL_QueueAudio()` with a bounded queue limit of roughly
160 ms (`queue_limit_frames_`) and a reusable conversion buffer. Windows uses the
same source path. Audio submission remains synchronous from the portable core
callback, but device queue growth is bounded.

macOS keeps its accepted bounded AVAudio path and recovery behavior. Switch/Eden
uses its existing companion audio contract.

## REMOVED-FEATURE BOUNDARY

The v3.3.2 core-only surface and native runtime contracts contain no new
Phone Controller, LAN Sync, Full Library Sync, account/login, cloud-sync, or
peer-discovery listeners. Phase A introduced none.

## PHASE_A_BASELINE

### Deterministic source/contract suite

Command:

```text
python3 -m unittest \
  tests.test_native_renderer_contract \
  tests.test_native_regression_guards \
  tests.test_android_native_runtime \
  tests.test_linux_native_runtime \
  tests.test_phase1_renderer_contract \
  tests.test_perf_telemetry \
  tests.test_core_only_surface \
  tests.test_eden_hosted_frame_ring
```

Result: 98 tests executed; 97 passed. One test was `BLOCKED_EXTERNAL` during
its local C++ fixture build because this fresh worktree does not contain the
untracked `native-offline/vendor/moltenvk/macos-arm64/include/vulkan` headers
required by the test's compile command. No source assertion failed. The same
fixture was rerun without source changes using the existing read-only MoltenVK
header copy from `/Users/meomeo/Documents/an3-runtime-performance` and passed
(`1/1`, native harness exit 0, expected `frames=5 begin=5 presented=5 states=3`).

The baseline output is preserved at `/tmp/an3-333-phase-a-baseline.log`.

### Evidence classification

- Existing static renderer, regression, Linux, Android, telemetry, core-only,
  and Switch hosted-frame contracts: `UNIT_VERIFIED` (97 tests in the suite).
- Portable fake-libretro host behavior: `UNIT_VERIFIED` with the dependency
  header supplied from the existing release worktree; the unmodified checkout
  invocation is `BLOCKED_EXTERNAL` by the absent untracked header.
- Android/Linux/Windows absolute runtime performance and physical-device
  behavior: `UNVERIFIED` in this Phase A source-only baseline.
- Known tao/Tauri Android teardown: `BLOCKED_UPSTREAM` (separate issue; no
  changes attempted).

## PHASE_A_STATUS

`IMPLEMENTED` (checkpoint-only documentation) and `UNIT_VERIFIED` for the
baseline contracts listed above. No product implementation was changed.

## NEXT

Phase B: introduce one shared bounded/coalescing portable save-persistence
worker. First prove worker-thread ownership, latest-snapshot/coalescing,
bounded backlog, atomic durability, failure propagation, clean drain, and
manual-wait-outside-core-ownership contracts before changing Android/Linux/
Windows production behavior.
