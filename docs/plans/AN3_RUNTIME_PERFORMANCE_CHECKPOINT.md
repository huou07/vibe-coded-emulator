# AN3 Runtime Performance Checkpoint

## Scope and baseline

- Source baseline: `80c3fe48a0d7da204a19a8a22abb98905da43145` (`v3.3.1`).
- Worktree/branch: `/Users/meomeo/Documents/an3-runtime-performance` /
  `perf/runtime-architecture`.
- This checkpoint covers the macOS runtime performance remediation only. It does
  not publish, tag, deploy, or change the Android tao/Tauri teardown blocker.
- The lawful M5 fixture is the generated GBA homebrew fixture from
  `tools/testrom/gba_homebrew_test.py`; no commercial ROM or fabricated fixture
  was used.

Phase A established the telemetry and the packaged bottleneck. The old packaged
path ran `retro_run` from the AppKit/MTKView display callback while the video
callback synchronously called `present_software`. The old packaged trace
(`/tmp/an3-tauri-m5.jsonl`) measured:

| metric | old packaged result |
| --- | --- |
| emulation p50/p95/p99/max | 16.491 / 17.199 / 17.544 / 27.609 ms |
| presentation p50/p95/p99/max | 16.109 / 16.824 / 17.202 / 27.139 ms |
| frame interval p50/p95/p99/max | 16.675 / 17.447 / 17.809 / 116.142 ms |
| intervals >2x / >3x | 2 / 2 |
| dropped / duplicated frames | 0 / 0 |
| audio xruns | 24 |

Source inspection confirmed `queue_present` was reached synchronously from
`retro_run` on the old MTKView path. The deterministic native harness did not
show recurring GBA stalls, so the packaged callback ownership and presentation
boundary were the measured risk to address.

## Implemented change

Primary implementation commit: **`580ca82`** (`fix(perf): decouple macos core cadence and bound presentation`).

- macOS software cores (`gba` and `nds`) now run `retro_run`, input sampling,
  audio submission, save snapshots, and core timing on one owned worker thread.
- The AppKit draw callback only presents from a bounded three-slot FIFO frame
  queue and observes audio recovery. It does not run the core or perform save
  work.
- A full bounded ring overwrites the oldest ready frame and records a drop;
  normal display jitter consumes ready frames FIFO. When no new frame is ready,
  the last drawable remains visible and telemetry records a duplicate without a
  second Vulkan submission.
- `3ds` retains its synchronous hardware-renderer path; no NDS/3DS core
  initialization, renderer, input, layout, or backend selection was changed.
- AVAudioPlayerNode recovery clears a stale queued count and restarts the node
  after a route/output stop, keeping the existing bounded audio path.
- The trace ring is bounded at 65,536 samples (over 18 minutes at 60 Hz) and
  records a separate presentation interval. Build dependencies now include the
  telemetry and save-worker headers so native changes rebuild reliably.
- Save persistence remains owned by the existing bounded/coalescing `AN3 Save
  Worker`; file open/write/flush/fsync/atomic rename stay off the core and draw
  paths. The renderer contract tests assert that boundary.

## Packaged M5/GBA verification

Final trace: `/tmp/an3-tauri-m5-fifo-final.jsonl` (18 MB, 35,635 frame records;
the trace was dumped on normal Escape shutdown). The process wall-clock run was
about ten minutes; the first 1,800 frames (~30 seconds) are treated as warm-up,
leaving 563.9 seconds (~9.4 minutes) of measured steady state.

Post-warm-up results:

| metric | result |
| --- | --- |
| presentation interval p50/p95/p99/max | 16.668 / 17.963 / 18.636 / 19.707 ms |
| presentation intervals >1.5x / >2x / >3x | 0 / 0 / 0 |
| core interval p50/p95/p99/max | 16.752 / 18.620 / 20.240 / 22.205 ms |
| emulation p50/p95/p99/max | 0.851 / 1.157 / 1.366 / 2.241 ms |
| presentation duration p50/p95/p99/max | 0.665 / 1.021 / 1.171 / 1.496 ms |
| video-ready to display p50/p95/p99/max | 13.068 / 17.967 / 20.163 / 23.778 ms |
| dropped / duplicate display opportunities | 0 / 154 |
| frame queue p95 / max | 2 / 2 (capacity 3) |
| cumulative audio xruns | 0 |
| non-zero save snapshots | 113; p50 434 us, p95 748 us, max 787 us |

The one startup drop and startup >2x/>3x interval are outside the warm-up
window. There are no post-warm-up drops or budget misses. Duplicate records are
display opportunities that kept the last drawable visible; they do not resubmit
Vulkan work. The native smoke renderer summary reports save-worker I/O p95 2 ms;
the per-frame trace `save_io_ms` field remains zero because worker I/O is
aggregated in renderer metrics rather than attributed to each core sample.
RSS rose from roughly 179.7 MB at the warm-up boundary to a 179.7 MB peak and
ended at roughly 179.2 MB in this run.

The normal-profile SRAM readback also passed without profile reset or data
deletion: the 32 KiB file retained the `AN3B` signature, its counter advanced
from `0f` to `10`, and its timestamp advanced after a fresh launch/close.

## Verification record

- Focused suite: 72 tests passed:
  `tests.test_perf_telemetry`, `tests.test_native_renderer_contract`,
  `tests.test_native_regression_guards`, `tests.test_phase1_renderer_contract`,
  `tests.test_phase_a_branding_autosave_exit`,
  `tests.test_native_staging_contract`, and `tests.test_native_input_contract`.
- Android native runtime contract suite: 24 tests passed.
- Objective-C++ syntax-only compile: passed.
- `cargo build --manifest-path native-offline/src-tauri/Cargo.toml --locked`:
  passed; only the existing nine Rust warnings remain.
- `git diff --check`: passed before the implementation commit and will be
  rerun for this checkpoint commit.
- The four generated schema files and generated Android/vendor outputs were not
  staged. Unrelated worktrees and caches were preserved.

## Platform and core status

| scope | status | evidence/limit |
| --- | --- | --- |
| macOS GBA M5 | `INTEGRATION_VERIFIED` | packaged FIFO trace, audio, queue, and SRAM readback above |
| macOS NDS | `UNIT_VERIFIED` | shared-host contracts only; no lawful runtime fixture |
| macOS 3DS | `UNIT_VERIFIED` | synchronous path kept unchanged; no lawful runtime fixture |
| Switch | `UNVERIFIED_NO_LAWFUL_FIXTURE` | no lawful runtime fixture supplied |
| Android / Windows / Linux absolute performance | `UNVERIFIED` | source and contract coverage only; no hosted M5 acceptance |
| tao/Tauri Android teardown | `BLOCKED_UPSTREAM` | separate known issue; not changed here |

## Next action

Run cross-platform hosted/physical acceptance and release review in a separate
authorized session. This branch is not pushed, tagged, released, or deployed by
this performance-remediation session.
