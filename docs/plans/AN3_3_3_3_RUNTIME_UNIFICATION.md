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

## PHASE_E — PORTABLE AUDIO CLEANUP

### Implementation

Phase E was split into three focused commits:

- `ff5010f0903d4c57f8d64ce5a93f6ed9b62a7c7b`
  (`fix(audio): bound portable SDL audio buffering`)
- `e655001e4e277b1f7f8a061ab1a1d633b918c209`
  (`perf(android): qualify low-latency AAudio negotiation`)
- `5240c1b6e08aa3fd1dbeacd0b7397d4f4ce48dbc`
  (`fix(audio): cap SDL conversion staging`)

The Linux/Windows SDL backend now allocates one reusable conversion buffer for
the existing bounded output queue. Normal submits reuse that storage; a resize
is allowed only when SDL reports more converted data than the initialized
capacity. Queue limit, observed maximum depth, submitted frames, and dropped
frames are exposed in the native diagnostics panel. The existing 160 ms queue
policy was deliberately left unchanged because no physical device measurements
were available to justify a new latency target. Oversized input batches are
consumed/dropped, and converted output larger than the reusable staging buffer
is drained in fixed-size chunks, so the SDL stream and staging path remain
bounded under unusual rate-conversion ratios.

The Android AAudio backend now tries low-latency exclusive mode first, retries
with an unspecified rate when an exact rate is rejected, and falls back through
the existing shared-mode exact/unspecified-rate path. Exclusive mode is
optional; shared mode remains a complete compatibility path. The actual sharing
mode, performance mode, frames per burst, buffer size/capacity, and AAudio xrun
count are captured in `AAudioMetrics` and included in the native diagnostics.
No API-28-only usage/content-type setters were added to the API-26 product
path, and no default was changed based on unmeasured hardware behavior.

### Phase E verification

- Linux SDL audio source contracts: 14 tests passed after the staging cap; the
  backend also passed C++20 warning-enabled syntax compilation with SDL2 and
  the existing external Vulkan headers.
- Android native runtime contracts: 27 passed with the existing read-only
  MoltenVK header dependency supplied from the release worktree. The fresh
  checkout-only fixture remains `BLOCKED_EXTERNAL` solely for that absent
  untracked header.
- Android NDK 28 targeted syntax compilation passed for `aaudio_backend.cpp`,
  `jni_runtime.cpp`, and the AAudio fixture. A host stub run of the AAudio
  fixture passed both exclusive success and simulated shared fallback paths;
  the fixture also verified the new stream telemetry fields.
- `git diff --check` and staged checks passed for all three focused commits.
  Only the SDL-audio files and matching regression tests or the Android-audio
  files and matching regression tests belonging to each logical change were
  staged.

### Evidence classification

- Bounded SDL conversion storage and AAudio negotiation/fallback contracts:
  `UNIT_VERIFIED` and `INTEGRATION_VERIFIED` with deterministic fixtures.
- Physical Android latency, xrun rate, exclusive-mode availability, and
  Linux/Windows device latency/underrun behavior: `UNVERIFIED`; no claim of
  improvement is made without hardware measurements.
- macOS audio, Android surface/render teardown, 3DS audio/render ownership,
  and Switch/Eden audio transport: preserved and not refactored in Phase E.

## PHASE_E_STATUS

`IMPLEMENTED` and `UNIT_VERIFIED` for bounded portable audio storage and safe
AAudio negotiation. Device-level performance remains explicitly unverified.

## NEXT

Phase F: perform the final NDS renderer software-versus-hardware A/B only where
lawful fixtures and backend support exist; preserve the software default unless
measured correctness and performance evidence justify a platform-specific
change.

## PHASE_F — NDS RENDERER A/B

No renderer change was made. The pinned melonDS core still receives
`melonds_render_mode=software` and `melonds_threaded_renderer=enabled`. The
macOS host accepts hardware-render callbacks only for `system == "3ds"`; an
NDS `RETRO_ENVIRONMENT_SET_HW_RENDER` request is rejected and no supported
NDS hardware context is exposed. The accepted NDS default therefore remains
software.

### Lawful fixture provenance recovered

| System | Upstream provenance and license | Artifact and reproducible acquisition | Previous AN3 evidence |
| --- | --- | --- | --- |
| NDS | [`devkitPro/nds-examples`](https://github.com/devkitPro/nds-examples), commit `f1ba715a451c6407f8b0f805999d0153062ff552`, selected `Graphics/3D/Picking`; `main.cpp` contains an explicit public-domain dedication. The repository root has no separate license file, so no repository-wide license is assumed. | Build the selected example with `devkitpro/devkitarm:20260610` (image digest `sha256:116afba8df8453961de2936ffab20dd441edf4d682856c1ec8b0e53d7ed0bbf5`); output `Picking.nds`, 196,608 bytes, SHA-256 `90f13a49ff06ce60e91a69df2ae9ffe6bb32a523a9f65f5845f3ea1fab14f61b`. | Packaged launch `1/1`, ten-minute health `30/30`, approximately 59.8 FPS, trace and keyboard-path evidence recorded in commit `37197079ec58757bf4719df609194498c18d4c2b`. |
| 3DS | [`16BitWonder/3DS-TEST`](https://github.com/16BitWonder/3DS-TEST), commit `e5b13872f0c1207cb9c86e18e710c8f1fa269fb8`, MIT license. | Artifact `3DS-TEST.3dsx`, 1,020,500 bytes, SHA-256 `a9fac712e9a6e937ec3d3d3228d8031d94030f3bec3462d9048897f3be638050`, acquired from the pinned public repository commit. | Packaged launch `1/1`, ten-minute health `30/30`, approximately 60 FPS, trace and keyboard-path evidence recorded in commit `37197079ec58757bf4719df609194498c18d4c2b`. |
| Switch | [`switchbrew/nx-hbmenu`](https://github.com/switchbrew/nx-hbmenu), tag `v3.6.1` / commit `fd26270a4e4b6994886a57b0738d98229ab4094e`, ISC license (`LICENSE.md`). | Official release asset `nx-hbmenu_v3.6.1.zip` (SHA-256 `4790c58fdd75c4bcc644fa8135fa11c380cb3ebaf685e400e336031972410ee7`); extracted `hbmenu.nro`, 2,455,539 bytes, SHA-256 `6cf6d130515723ebe0041c2479420caf9726895087439ff7b2e528c2ed39c100`. | Existing 620-second Eden soak: 37,179 frames, 37,140 publishes, zero drops/rejections/copy errors, normal shutdown, recorded in commit `80e6db23cb0e714409ff55dfca4fb93587e23d84`. |

### Phase F verification

- Current-candidate NDS packaged E2E passed `1/1`. The 620-second run collected
  121/121 five-second health samples; every sample stayed `running=true`, the
  presented-frame counter increased strictly from `9` to `36,874` (delta
  `36,865`), and shutdown emitted trace `/tmp/an3-333-nds-trace.jsonl`
  (37,332 samples; SHA-256
  `175e27a654be4c0574de8034c4b6cb476636b0e80b3f83b65f5774524f39a06f`).
  After a 30-second warm-up, frame interval p50/p95/p99/max was
  `16.667833/17.754875/18.386916/25.763375 ms`; emulation
  `2.906249/3.143083/3.253124/5.020124 ms`; presentation
  `0.516125/0.613500/0.680666/0.863125 ms`; queue p95/max `2/2` (host
  capacity `3`); drops/duplicates `0/0`; audio xrun high-water `1`; RSS
  `384,958,464→384,401,408` bytes, peak `384,991,232`. The generated fixture
  has no save-game roundtrip or reliable audible output.
- A same-fixture NDS software-versus-hardware A/B was not runnable: the
  current pinned host rejects NDS hardware negotiation by contract and only
  exposes hardware callbacks to the existing 3DS path. Status:
  `UNVERIFIED_UNSUPPORTED_BY_PINNED_CORE`. No default change or speculative
  renderer enablement was attempted.
- Current-candidate 3DS packaged E2E passed `1/1`. The 620-second run collected
  121/121 health samples; every sample stayed `running=true`, the presented
  frame counter increased strictly from `5` to `36,879` (delta `36,874`),
  and shutdown emitted trace `/tmp/an3-333-3ds-trace.jsonl` (37,228 samples;
  SHA-256 `296776b561e10eaf38e6518ce84cf56702ef80b729e191dde716457c6c3dda09`).
  After warm-up, synchronous core interval p50/p95/p99/max was
  `16.666834/17.509208/17.616666/1058.400375 ms`; emulation
  `0.887791/1.070042/1.166249/1045.151333 ms`; drops/duplicates/audio
  xruns `0/0/0`. The one approximately 1.06-second interval at 527.57
  seconds was isolated; no recurring late-run stall appeared. Direct hardware
  presentation does not populate the software presentation-duration/queue
  fields. 3DS initialization, renderer, input, layout, and backend selection
  were not modified.
- Current-candidate Switch regression used the exact recorded companion
  (`an3_switch_companion` SHA-256
  `f2658152c3d57f461dfb71e1f4b8d2728ae241a8a720a7bf19e5a3735d749708`) and
  the verified `hbmenu.nro`: lifecycle stress and audio-path suites passed
  `5/5`, including five clean cycles, rapid stop, crash/restart, a real audio
  backend, and stable diagnostics. The Eden source/hosted-frame tree is
  unchanged from `v3.3.2`, so the prior 620-second soak remains valid for this
  candidate: 37,179 frames, 37,140 publishes, zero drops/rejections/copy
  errors, normal shutdown.

## PHASE_F_STATUS

`CURRENT_CANDIDATE_VERIFIED_WITH_LIMITATIONS`: lawful NDS, 3DS, and Switch
fixtures were recovered and current-candidate runtime evidence was collected.
The NDS software default remains accepted; the requested hardware A/B is
`UNVERIFIED_UNSUPPORTED_BY_PINNED_CORE`. Fixture save roundtrips and physical
audible output remain unverified where the lawful test images do not provide a
reliable observable path.

## FINAL_RUNTIME_UNIFICATION_STATUS

Phases A–E are implemented with focused commits and deterministic host/contract
verification. Phase F is intentionally evidence-limited as recorded above.
The branch remains development-only: `main`, `v3.3.2`, and all release or
production deployment state are unchanged.

## REQUIRED FINAL CHECKPOINT

### BASE

`v3.3.2`: `7110fc3977233b006b6905c50e6dd081b714d4a9`

### FINAL_CANDIDATE_SHA

`5240c1b6e08aa3fd1dbeacd0b7397d4f4ce48dbc` (last product-source commit;
the later commits on this branch are checkpoint documentation only).

### PRODUCT_COMMITS

- `f6478e4eb438c30069f73f395517146f3972d10b` — shared bounded async save worker
- `dbf869856c86ee0bb61590acff0019ac86bbc2e7` — portable single core owner
- `257cb98e1b5dc60efa2ed7b4437696858727b076` — bounded software presentation
- `ff5010f0903d4c57f8d64ce5a93f6ed9b62a7c7b` — bounded SDL audio buffering
- `e655001e4e277b1f7f8a061ab1a1d633b918c209` — AAudio negotiation/telemetry
- `5240c1b6e08aa3fd1dbeacd0b7397d4f4ce48dbc` — capped SDL conversion staging

### HOSTED CI

`PENDING`: the exact candidate has not yet been dispatched to the GitHub-hosted
workflow. This checkpoint will be updated with the review-branch head SHA,
workflow run ID, and job results before any release decision.

### ARCHITECTURE BEFORE

Portable Linux/Windows ran the core, synchronous presenter, and SDL event loop
in one cadence path; portable save/state persistence could enter filesystem I/O
from core-owned operations; Android had a core worker but synchronous software
presentation and no negotiated AAudio mode telemetry. macOS GBA/NDS already had
the accepted owner/FIFO/save-worker architecture and was left intact.

### ARCHITECTURE AFTER

The portable runtime now has one core owner for active software sessions,
immutable save snapshots handed to a bounded persistence worker, and a bounded
three-slot FIFO software-frame handoff for Linux/Windows GBA/NDS. The platform
presenter owns SDL/GL/Vulkan presentation; 3DS hardware and Switch/Eden remain
on their existing ownership paths. Android retains its runtime-owned render
thread and bounded backend slots, with safe AAudio exclusive/shared fallback.

### SAVE PERSISTENCE

- macOS: existing v3.3.2 `SavePersistenceWorker` — `INTEGRATION_VERIFIED` by
  preserved contracts.
- Android: shared snapshot worker and owner-thread command boundary —
  `UNIT_VERIFIED`; physical package behavior `UNVERIFIED`.
- Windows: shared snapshot worker through the portable session —
  `UNIT_VERIFIED`; packaged behavior `UNVERIFIED`.
- Linux: shared snapshot worker through the portable session —
  `INTEGRATION_VERIFIED` in host fixtures; packaged behavior `UNVERIFIED`.

### CORE OWNERSHIP

- macOS: existing dedicated software core thread — `INTEGRATION_VERIFIED` by
  preserved v3.3.2 contracts.
- Android: existing native worker plus protected option cache — `UNIT_VERIFIED`.
- Windows: `NativeCoreSession` owner thread — `INTEGRATION_VERIFIED`.
- Linux: `NativeCoreSession` owner thread — `INTEGRATION_VERIFIED`.

### PRESENTATION

- macOS: existing three-slot software FIFO — preserved, `INTEGRATION_VERIFIED`.
- Android: runtime-owned bounded Vulkan/GLES slots; no unsafe separate presenter
  introduced — `UNIT_VERIFIED`, device behavior `UNVERIFIED`.
- Windows: three-slot FIFO consumed by the platform loop; 3DS remains direct
  hardware — `INTEGRATION_VERIFIED` by the queue fixture.
- Linux: three-slot FIFO consumed by the SDL/GTK loop; 3DS remains direct
  hardware — `INTEGRATION_VERIFIED` by the queue fixture.

### AUDIO

- macOS: accepted v3.3.2 path preserved — `UNIT_VERIFIED` by existing guards.
- Android: exclusive low-latency attempt with shared fallback, burst/buffer/
  xrun telemetry — `INTEGRATION_VERIFIED` by the deterministic stub; physical
  latency `UNVERIFIED`.
- Windows: bounded SDL queue and reusable conversion staging — `UNIT_VERIFIED`;
  physical latency/underruns `UNVERIFIED`.
- Linux: bounded SDL queue and reusable conversion staging — `UNIT_VERIFIED`;
  physical latency/underruns `UNVERIFIED`.

### GBA

Lawful generated mGBA fixture save/state/SRAM roundtrip —
`INTEGRATION_VERIFIED` (`RESULT: PASS`), including input mutation, state
restoration, atomic 32 KiB SRAM persistence, and fresh-host readback.

### NDS

Software renderer remains forced and its core/layout/input contracts remain
`UNIT_VERIFIED`. Current-candidate launch/performance is `INTEGRATION_VERIFIED` by the
recovered `Picking.nds` fixture and the 620-second trace above. Renderer A/B
is `UNVERIFIED_UNSUPPORTED_BY_PINNED_CORE`.

### 3DS

Existing Vulkan/OpenGL hardware ownership, shader guards, and backend contracts
were preserved — `UNIT_VERIFIED`; current-candidate packaged launch and
620-second runtime are `INTEGRATION_VERIFIED` with the recovered lawful
`3DS-TEST.3dsx` fixture.

### SWITCH

Eden hosted-frame transport was not refactored. Existing hosted-frame ring and
core-only surface contracts remained green — `UNIT_VERIFIED`.

### PERFORMANCE RESULTS

- Bounded software queue fixture: `SOFTWARE_FRAME_QUEUE=PASS`.
- Core-owner fixture: `NATIVE_CORE_SESSION=PASS`.
- Save worker fixture: `SAVE_PERSISTENCE_WORKER=PASS`.
- Final broad source/contract suite: 107 tests `UNIT_VERIFIED`/`INTEGRATION_VERIFIED`.
- Post-cap Linux audio suite: 14 tests passed; Android suite: 27 tests passed.
- No absolute FPS/latency improvement claim is made for packaged or physical
  Android/Linux/Windows devices without those runs.

### KNOWN LIMITATIONS

- The fresh worktree intentionally lacks the untracked MoltenVK header copy;
  fixture invocations that use the checkout path are `BLOCKED_EXTERNAL`. Runs
  using the existing read-only dependency copy passed.
- GTK development headers and full Linux package dependencies are not installed
  on this Mac, so no packaged Linux/Windows runtime was rebuilt locally.
- The lawful NDS/3DS/Switch fixture provenance is recorded above; their
  binaries remain outside the AN3 repository. NDS hardware A/B remains
  `UNVERIFIED_UNSUPPORTED_BY_PINNED_CORE`; fixture save/audio limits remain
  explicit.
- The known tao/Tauri Android teardown issue remains `BLOCKED_UPSTREAM` and was
  not changed.

### REGRESSIONS

`git diff --check` and staged checks passed for every logical commit. The
v3.3.2 base tag and the release worktree remain untouched. No Sync, Phone
Controller, LAN, account, cloud, or other removed feature was restored.

### RELEASE READINESS

`REVIEW_ONLY`: source changes are committed on
`perf/3.3.3-runtime-unification`; `main`, `v3.3.2`, GitHub release state, and
production deployment were not changed. A separate hosted-CI and release
acceptance session is required before publishing any v3.3.3 candidate.
