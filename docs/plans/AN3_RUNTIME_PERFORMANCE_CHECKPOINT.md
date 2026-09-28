# AN3 Runtime Performance Checkpoint

## Phase A — bounded telemetry and source map

- Source baseline: `80c3fe48a0d7da204a19a8a22abb98905da43145` (`v3.3.1`).
- Worktree/branch: `perf/runtime-architecture` / `/Users/meomeo/Documents/an3-runtime-performance`.
- Status: `IMPLEMENTED` telemetry contract; M5 runtime reproduction is still `UNVERIFIED`.

### Current macOS GBA path

`MTKView::drawInMTKView` calls `AzaharHost::draw` on the AppKit/display callback. At
normal speed, one `retro_run` is executed per callback. The core's video callback
calls `VulkanFrontend::present_software`, which uploads into the bounded two-slot
ring and submits the swapchain blit/present. The existing presenter can wait for
an image acquire and an image/in-flight fence; no normal-frame `vkDeviceWaitIdle`
or `vkQueueWaitIdle` was added. Audio callbacks feed the existing bounded audio
queue and AVAudioEngine path. SRAM/state bytes are copied under the host lock and
submitted to the existing bounded/coalescing `AN3 Save Worker`; file open/write,
flush, `fsync`, and atomic rename remain worker-owned.

The current host still holds `state_mutex_` across `retro_run`, pending audio
work, periodic save snapshot submission, and the synchronous presentation call.
That is a measured architectural risk to verify with the trace; it is not yet
claimed as the sole cause of the owner's visible lag.

### Telemetry added

`native-runtime/core/perf_telemetry.h` provides a fixed 512-sample timing window,
cumulative deadline/budget counters, and a fixed 4096-frame JSONL trace ring.
Tracing is local and opt-in with `AN3_PERF_TRACE=1`; the ring is dumped only at
session stop to `AN3_PERF_TRACE_PATH` (or `/tmp/an3-perf-trace.jsonl`). The frame
record carries the core/input/emulation/video/present timestamps, acquire/fence
wait boundaries, audio fill/xruns, save snapshot and I/O fields, RSS, and
dropped/duplicated flags. The default path performs no file I/O and no network
activity from the frame callback.

Renderer metrics now expose p50/p95/p99/max for frame, emulation, upload,
presentation, acquire, and fence timings, budget miss counters, duplicate
frames, bounded queue depth, save snapshot/I/O summaries, and trace status.
`tools/summarize_perf_trace.py` deterministically summarizes a trace without
assuming 60 Hz; it uses the trace budget or the observed median cadence.

### Verification

- `tests.test_perf_telemetry`: pass (bounded contract and deterministic summary).
- `tests.test_native_renderer_contract`: pass.
- `tests.test_native_regression_guards`: pass.
- `tests.test_phase1_renderer_contract`: pass.
- `tests.test_phase_a_branding_autosave_exit`: pass.
- `tests.test_native_staging_contract`: pass.
- `tests.test_core_only_surface`: pass.
- `tests.test_native_input_contract`: pass.
- standalone C++17 compile of `perf_telemetry.h`: pass.
- standalone C++17 compile of `SavePersistenceWorker` with its test writer: pass.
- `git diff --check`: pass.

No packaged M5 trace has been captured in this phase, so no gameplay smoothness
or before/after performance result is reported yet. The Tao/Tauri Android
teardown classification remains `BLOCKED_UPSTREAM` and is out of scope.

## Next action

Build/run the exact lawful macOS GBA workload with `AN3_PERF_TRACE=1`, retain the
JSONL trace, summarize it, and correlate frame hitches with emulation, present,
acquire/fence, audio, and save fields before changing runtime ownership.
