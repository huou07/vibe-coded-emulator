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

## PHASE_B — SHARED ASYNCHRONOUS SAVE PERSISTENCE

### Implementation

Phase B commit: `f6478e4` (`fix(runtime): move portable save writes to bounded worker`).

- The bounded/coalescing `SavePersistenceWorker` now lives in
  `native-offline/native-runtime/core/save_persistence_worker.h`, with the
  previous macOS include path retained as a thin compatibility include.
- The shared worker owns temporary-file write, flush, POSIX fsync or Windows
  commit, and atomic replacement. It coalesces repeated snapshots by path,
  bounds distinct pending paths at sixteen, bounds asynchronous completions at
  sixteen per path, propagates failures, and drains accepted work on shutdown.
- The worker is named `AN3 Save Worker` on Apple, Linux, and Android. The
  existing macOS `AzaharHost` behavior and API remain source-compatible.
- `NativeCoreHost` now copies core-owned state/SRAM bytes under its core mutex,
  releases that ownership, and then submits the immutable snapshot to the
  worker. Manual/final `write_and_wait` calls wait only after the core lock is
  released. Shutdown captures SRAM before unloading the core, then waits for
  durability outside the lock.
- `queue_save_auto()` and `queue_save_ram()` are explicit nonblocking APIs for
  periodic saves. Android and the shared Linux/Windows runtime use them for
  periodic autosave/SRAM persistence. Manual commands and final shutdown saves
  retain durable completion semantics. Background worker failures are surfaced
  through `NativeCoreHost::status()`.
- No core-specific rendering, input, layout, hardware backend, 3DS path,
  Switch/Eden path, or removed network feature was changed.

### Phase B verification

- `native-offline/tests/test_save_persistence_worker.cpp`: `SAVE_PERSISTENCE_WORKER=PASS`.
  This covers worker-thread ownership, same-path latest-snapshot coalescing,
  bounded distinct paths and completions, nonblocking periodic enqueue while a
  write is held, atomic replacement, failure propagation, durable completion,
  and shutdown drain.
- Native/runtime contracts and regressions: 75 tests passed.
- Android native runtime contracts: 24 tests passed when the existing
  read-only MoltenVK header dependency was supplied; the checkout-only run is
  `BLOCKED_EXTERNAL` for that absent untracked header, with no source assertion
  failure.
- Lawful generated GBA native host save/state roundtrip: `RESULT: PASS`.
  The run proved presented frames, A-button mutation, slot restoration, 32 KiB
  SRAM durability, and fresh-host SRAM restoration (`AN3B` counter `00` to
  `01`) using the existing mGBA dependency copy and
  `tools/testrom/gba_homebrew_test.py` fixture.
- `git diff --check`: passed before the implementation commit. Only the ten
  Phase B files were staged for `f6478e4`.

### Evidence classification

- Shared worker contracts and portable API boundary: `UNIT_VERIFIED`.
- Lawful GBA state/SRAM host roundtrip: `INTEGRATION_VERIFIED`.
- Android/Linux/Windows packaged performance and physical-device behavior:
  `UNVERIFIED`; no platform package was rebuilt in this phase.
- macOS v3.3.2 runtime behavior: preserved by the compatibility include and
  existing macOS regression contracts; no new packaged macOS run was claimed.

## PHASE_B_STATUS

`IMPLEMENTED` and `UNIT_VERIFIED`, with the lawful native GBA save roundtrip
`INTEGRATION_VERIFIED`. The portable production source no longer performs
frontend filesystem write/fsync/rename work on periodic save cadence.

## NEXT

Phase C: give portable GBA/NDS sessions one explicit core-owner thread on
Android/Linux/Windows. Keep input as atomic/latest state plus bounded discrete
commands, preserve 3DS hardware ownership, and do not begin frame-handoff or
audio changes until the owner-thread boundary is tested.

## PHASE_C — PORTABLE SINGLE CORE-OWNER RUNTIME

### Implementation

Phase C commit: `dbf869856c86ee0bb61590acff0019ac86bbc2e7`
(`fix(runtime): give portable sessions one core owner`).

- Added shared `NativeCoreSession`, which schedules `NativeCoreHost::run_one`
  and all running-core mutations on one owner thread. Save/load state, auto
  save, SRAM queue/flush, state import/export, layout, core options, pause, and
  speed cross a bounded 128-command queue. Rapid pause/resume/speed controls
  coalesce; discrete save/load and layout commands remain queued in order.
- Linux and Windows now start the session worker after initial core setup and
  use the session for input, controls, saves, layout, and status. The SDL/GTK
  loop no longer runs the core or schedules frames; it only pumps platform
  events and bounded persistence commands. Bounded `--frames` runs pause the
  owner at the requested boundary so final state export and `stop()` still use
  the owner thread.
- Android's existing session worker remains the core owner. Core-option JSON is
  now refreshed by that worker and returned from a protected cache, removing
  the last direct option query from the Android UI thread.
- Linux SDL/OpenGL metrics and SDL audio metrics are protected for concurrent
  owner-thread presentation/audio callbacks and UI diagnostics. The existing
  3DS hardware path and Switch/Eden path were not changed.
- Build scripts include the shared session source for Linux staging and
  Windows runtime builds. No removed networking or Sync surface was restored.

### Phase C verification

- Portable owner-thread fixture harness: `NATIVE_CORE_SESSION=PASS`; six
  bounded frames ran on a thread different from the caller, the session stayed
  commandable at the boundary, an owner-thread save produced a state file, and
  `stop()` left the host stopped.
- Android native runtime contracts and fixture tests: 26 passed with the
  existing read-only MoltenVK header dependency supplied. The normal checkout
  invocation remains `BLOCKED_EXTERNAL` only for that absent untracked header.
- Linux/portable contracts and regressions: 68 passed.
- Save persistence regression: `SAVE_PERSISTENCE_WORKER=PASS`.
- Lawful generated GBA native save/state roundtrip: `RESULT: PASS`, including
  frame presentation, A-button mutation, state restoration, 32 KiB SRAM
  durability, and fresh-host SRAM restoration.
- `native_core_session.cpp` passed C++20 warning-enabled syntax compilation;
  `git diff --check` passed before commit. Only Phase C implementation,
  synchronization, fixture, build, and matching regression files were staged
  for `dbf869856c86ee0bb61590acff0019ac86bbc2e7`.

### Evidence classification

- Portable core-owner boundary and bounded command behavior:
  `INTEGRATION_VERIFIED` with the native fixture harness.
- Android owner-thread option boundary: `UNIT_VERIFIED`; packaged Android
  performance and physical-device behavior remain `UNVERIFIED`.
- Linux/Windows packaged runtime and physical-device behavior:
  `UNVERIFIED`; this phase did not rebuild or launch packaged desktop
  artifacts.
- macOS v3.3.2 runtime behavior: preserved; no macOS runtime code was changed.

## PHASE_C_STATUS

`IMPLEMENTED` and `INTEGRATION_VERIFIED` for the portable owner-thread
boundary. Phase D (bounded software-frame handoff/presentation decoupling) is
the next implementation phase; audio and 3DS renderer work remain deferred.

## NEXT

Phase D: add a bounded two- or three-slot software-frame handoff for portable
GBA/NDS presenters without changing the macOS queue, 3DS hardware ownership,
or the established input/save contracts.

## PHASE_D — BOUNDED PORTABLE SOFTWARE-FRAME HANDOFF

### Implementation

Phase D commit: `257cb98e1b5dc60efa2ed7b4437696858727b076`
(`fix(runtime): decouple portable software presentation`).

- Added `NativeSoftwareFrameQueue`, a reusable three-slot handoff for the
  portable SDL/Vulkan/OpenGL GBA/NDS path. The core-owner callback publishes
  immutable slot contents and returns; the SDL/GTK platform thread drains the
  oldest ready slot and owns the wrapped presenter call.
- The queue is FIFO at normal depth, replaces only the oldest ready slot when
  all three slots are full, and never overwrites a slot being presented. It
  accepts direct framebuffer writes when the core provides them, copies only
  when the callback buffer or pitch requires it, bounds frame geometry and
  storage, records drops/duplicates/maximum depth, and releases incomplete
  direct-frame slots after each `retro_run`.
- Linux and Windows non-3DS runtime wiring now keeps SDL/GL/Vulkan presentation
  off the core-owner critical path. The existing Linux/Windows 3DS
  core-provided hardware path remains direct. Android presentation remains on
  its runtime-owned render thread because its Vulkan/GL surface context cannot
  safely be consumed by a separate presenter in this phase; no Android surface
  or teardown behavior was changed. macOS v3.3.2 is untouched.
- Build source lists and the focused queue fixture cover the new portable
  adapter. No core-specific rendering, input, layout, backend selection,
  3DS initialization, Switch/Eden transport, or removed network feature was
  changed.

### Phase D verification

- Portable contract/regression suite: 70 tests passed, including the Linux
  queue wiring and metric guards.
- Standalone warning-enabled queue fixture: `SOFTWARE_FRAME_QUEUE=PASS`;
  three-frame FIFO order, oldest-ready replacement under a full queue,
  bounded depth, duplicate opportunity accounting, incomplete-frame release,
  and shutdown behavior all passed.
- Portable owner-thread fixture after the Phase D source changes:
  `NATIVE_CORE_SESSION=PASS`.
- Shared save worker regression after the Phase D source changes:
  `SAVE_PERSISTENCE_WORKER=PASS`.
- Lawful generated GBA native save/state roundtrip after the Phase D source
  changes: `RESULT: PASS`, including frame presentation, A-button mutation,
  state restoration, 32 KiB SRAM durability, and fresh-host SRAM restoration.
- Android native runtime contracts: 26 passed with the existing read-only
  MoltenVK header dependency supplied from the release worktree. The fresh
  checkout-only fixture remains `BLOCKED_EXTERNAL` solely because that
  dependency is intentionally untracked here.
- `git diff --check` and staged `git diff --cached --check` passed before the
  implementation commit. Only the nine Phase D implementation/build/test
  files were staged for `257cb98e1b5dc60efa2ed7b4437696858727b076`.

### Evidence classification

- Portable bounded frame handoff and presenter-thread ownership:
  `INTEGRATION_VERIFIED` with the native queue fixture and contract suite.
- GBA save/state and SRAM behavior: `INTEGRATION_VERIFIED`.
- Android packaged presentation, Linux/Windows packaged frame pacing, and
  physical-device performance: `UNVERIFIED`; no packaged runtime was rebuilt
  or claimed here.
- macOS v3.3.2 runtime behavior, 3DS hardware rendering, and Switch/Eden
  hosted transport: preserved and not refactored in Phase D.

## PHASE_D_STATUS

`IMPLEMENTED` and `INTEGRATION_VERIFIED` for the portable Linux/Windows
software-presenter boundary. Phase E (portable audio cleanup) is next; no
audio defaults were changed in Phase D.

## NEXT

Phase E: investigate portable Android AAudio and Linux/Windows SDL audio
buffering/allocation behavior with bounded measurements, preserving safe
fallbacks and avoiding any change to the accepted macOS, 3DS, or Switch paths.
