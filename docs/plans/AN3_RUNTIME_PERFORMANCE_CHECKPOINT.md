# AN3 Runtime Performance Checkpoint

## Scope and baseline

- Source baseline: `80c3fe48a0d7da204a19a8a22abb98905da43145` (`v3.3.1`).
- Worktree/branch: `perf/runtime-architecture` (local checkout path intentionally
  omitted from the release-facing checkpoint).
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
window. There are no post-warm-up drops and no presentation intervals above 1.5x,
2x, or 3x budget. Duplicate records are
display opportunities that kept the last drawable visible; they do not resubmit
Vulkan work. The native smoke renderer summary reports save-worker I/O p95 2 ms;
the per-frame trace `save_io_ms` field remains zero because worker I/O is
aggregated in renderer metrics rather than attributed to each core sample.
RSS rose from roughly 179.7 MB at the warm-up boundary to a 179.7 MB peak and
ended at roughly 179.2 MB in this run.

The normal-profile SRAM readback also passed without profile reset or data
deletion: the 32 KiB file retained the `AN3B` signature, its counter advanced
from `0f` to `10`, and its timestamp advanced after a fresh launch/close.

## Lawful fixture provenance

All fixture bytes below were kept outside the repository under
`/tmp/an3-fixtures-20260928`; no third-party binary is committed.

| core | source and exact revision | license/provenance | artifact and SHA-256 |
| --- | --- | --- | --- |
| NDS | [`devkitPro/nds-examples`](https://github.com/devkitPro/nds-examples), commit `f1ba715a451c6407f8b0f805999d0153062ff552`; selected `Graphics/3D/Picking` source | The selected `main.cpp` contains an explicit public-domain dedication. The repository root has no separate license file; the test records that fact rather than assuming a repository-wide license. Source-built with the official `devkitpro/devkitarm:20260610` image, digest `sha256:116afba8df8453961de2936ffab20dd441edf4d682856c1ec8b0e53d7ed0bbf5`. Command: `docker run --rm -v /tmp/an3-fixtures-20260928/nds-examples:/build -w /build/Graphics/3D/Picking devkitpro/devkitarm:20260610 make` | `Picking.nds`, 196,608 bytes, `90f13a49ff06ce60e91a69df2ae9ffe6bb32a523a9f65f5845f3ea1fab14f61b` |
| 3DS | [`16BitWonder/3DS-TEST`](https://github.com/16BitWonder/3DS-TEST), commit `e5b13872f0c1207cb9c86e18e710c8f1fa269fb8` | MIT (`LICENSE`); public prebuilt from the repository, with display, controls, and button-sound code documented by its README | `3DS-TEST.3dsx`, 1,020,500 bytes, `a9fac712e9a6e937ec3d3d3228d8031d94030f3bec3462d9048897f3be638050` |
| Switch | [`switchbrew/nx-hbmenu`](https://github.com/switchbrew/nx-hbmenu), release tag `v3.6.1`, commit `fd26270a4e4b6994886a57b0738d98229ab4094e` | ISC (`LICENSE.md`); official release asset, not a commercial dump | `hbmenu.nro`, 2,455,539 bytes, `6cf6d130515723ebe0041c2479420caf9726895087439ff7b2e528c2ed39c100` |

The official [`devkitPro/3ds-examples`](https://github.com/devkitPro/3ds-examples)
checkout was also inspected at commit `be2001fee08cf8ec7d3366e095e83f6f75da8942`
(its README marks the examples public domain), but the MIT-licensed 3DS-TEST
prebuilt was used for the runtime gate because it already exercises controls and
sound. No commercial ROM, firmware, key, or questionable download source was
used.

## NDS/3DS/Switch runtime acceptance

The packaged macOS automation bundle was rebuilt from this branch with the
test-only `ui-control` feature in an isolated `/private/tmp` Cargo target. The
existing production/native source and the accepted GBA architecture were not
changed. Each packaged gate imported the real fixture through the picker, used
the real launch control, held `native-status=running`, and required the native
presented-frame counter to advance.

| core | runtime evidence | measured result | remaining limit |
| --- | --- | --- | --- |
| NDS / melonDS | Packaged macOS launch passed (`1/1`). The ten-minute health run collected 30/30 structured samples; all were `running=true`, with strictly increasing presented frames (`536→35,387`) and no failed reads. A normal Escape shutdown emitted trace `/tmp/an3-nds-trace2-session-20260928.jsonl` (2,226 frames, 37.12 seconds of traced cadence; SHA-256 `67348c0274e8c1f25775e7805adc6568f0e217f9908304218d42a243f43872c1`). | Core interval p50/p95/p99/max `16.722/18.093/19.007/19.708 ms`; presentation interval `16.662/17.596/17.773/33.017 ms`; emulation `2.051/3.030/3.158/3.448 ms`; presentation duration `0.441/0.597/0.724/51.182 ms`; queue max `3` (capacity 3); `3` drops, `5` duplicate opportunities, `2` audio xruns, and `save_io_ms=0`. | The generated Picking example has no save-game roundtrip. Keyboard D-pad/A/B/Start events were dispatched through the native window while frames continued to advance (`705→770`); this proves the input path stayed live, not a fixture-specific visual effect. Audible output was not captured. |
| 3DS / Azahar | Packaged macOS launch passed (`1/1`). The ten-minute health run collected 30/30 samples; all were `running=true`, with strictly increasing presented frames (`383→35,334`). Trace `/tmp/an3-3ds-trace-session-20260928.jsonl` spans 622.56 seconds of frame cadence (37,332 frames; SHA-256 `3475fa3627ab3cabf5d69f683adc5a74fffd11c4c436414b05f64055ff9881b2`). | Synchronous core interval p50/p95/p99/max `16.666/17.317/17.568/155.260 ms`; emulation duration `0.797/1.056/1.179/152.956 ms`; `0` drops, `0` duplicates, queue `0`, audio xruns `0`, and `save_io_ms=0`. Frame-interval outliers were `>1.5B/>2B/>3B = 4/4/3`: three startup events and one 33.52 ms late-run event; they were isolated rather than recurring. | 3DS initialization, renderer, input, layout, and backend selection were not modified. The fixture has no save-game roundtrip; keyboard D-pad/A/B/Start events were dispatched while frames continued (`590→655`). Audible output was not physically captured. Shader-cache/hardware-vs-software A/B was not changed or claimed. |
| Switch / Eden companion | The current bundled companion binary (manifest SHA-256 `f2658152c3d57f461dfb71e1f4b8d2728ae241a8a720a7bf19e5a3735d749708`) loaded the official NRO. The 620-second run `/tmp/an3-switch-soak-20260928.log` ended normally with `AN3CTL_STATUS ... mode=stopped ... frames=37179 ... result=PASS`; hosted-frame hooks published real 1280×720 IOSurface frames. | 37,140 sampled publishes (1,239 sampled hook records), `dropped=0`, `rejected=0`, `copy_errors=0`; 63 status records all remained `PASS`; first-frame import reported 3,686,400 bytes and non-zero pixels. Input protocol, audio diagnostics, and isolated save/lifecycle/audio suites remain `8/8` as recorded above. Log SHA-256: `34956e054d27f6960856bdd9ae3d0f4c88e55b5c032a68de01ab2f195b90e156`. | Audible output and a game-level save roundtrip remain unverified because nx-hbmenu writes no game save and no loopback capture was available. The 14 logged errors were the known host/teardown conditions (4K fast-memory mapping, optional MoltenVK features, no network interface, abandoned shutdown queue, and missing Eden play-time file); none caused a frame drop, restart, or non-PASS exit. |

The acceptance evidence does not identify a new recurring NDS, 3DS, or Switch
presentation bottleneck. The measured risk remains the original macOS callback
ownership boundary addressed by `580ca82`: NDS software cores stay on the owned
worker with a bounded FIFO, 3DS keeps its unchanged synchronous hardware path,
and Switch's separate companion/hosted-frame ring remained lossless in the
sustained run.

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
- Fixture acceptance: packaged NDS and 3DS E2E passed `1/1` each; Switch
  companion save/audio/lifecycle suites passed `8/8`; Eden bridge null CTest
  passed `1/1`; focused contracts and regression guards passed `54` tests.
- Current-head deterministic gates: Python product/runtime suites passed `71`
  tests with one fixture-gated skip; core-only/API/integration/release-scan
  suites passed `80`; Node suites passed `77` with two environment skips; the
  portable Rust gateway passed `8`; `npm run check`, Python syntax, and
  post-baseline Gitleaks passed.
- `git diff --check`: passed before the implementation commit and will be
  rerun for this checkpoint commit.
- The four generated schema files and generated Android/vendor outputs were not
  staged. Unrelated worktrees and caches were preserved.

## Platform and core status

| scope | status | evidence/limit |
| --- | --- | --- |
| macOS GBA M5 | `INTEGRATION_VERIFIED` | packaged FIFO trace, audio, queue, and SRAM readback above |
| macOS NDS | `INTEGRATION_VERIFIED` | lawful source-built devkitPro fixture; packaged launch, ten-minute health, trace, and input-path evidence above; save/audio effect limits recorded |
| macOS 3DS | `INTEGRATION_VERIFIED` | lawful MIT 3DS-TEST fixture; packaged launch, ten-minute health, synchronous trace, and input-path evidence above; save/audio effect limits recorded |
| Switch | `INTEGRATION_VERIFIED` | lawful ISC nx-hbmenu fixture; companion 65-second hosted-frame run, input/audio diagnostics, and isolated save/lifecycle suites above |
| Android / Windows / Linux absolute performance | `UNVERIFIED` | source and contract coverage only; no hosted M5 acceptance |
| tao/Tauri Android teardown | `BLOCKED_UPSTREAM` | separate known issue; not changed here |

## AN3 CROSS-PLATFORM RELEASE READINESS

This is a readiness determination only. No tag, release, deployment, or public
push was performed.

| field | value |
| --- | --- |
| `FINAL_SOURCE_SHA` | `37197079ec58757bf4719df609194498c18d4c2b` |
| `PRODUCT_CHANGE_SHA` | `580ca82854ee7a7c8e80fb54c138892069a2971d` |
| `PRODUCT_TREE_SHA/IDENTITY` | `044cfd6ad0f6ea1695deb0fe8a7ec29b80e29633` / Vibe Coded Emulator native runtime |
| `CURRENT_HEAD_TREE_SHA` | `df46629f6379fab49fd9df38e7105bf4ee411d48` (checkpoint-only changes after the product tree) |
| `HOSTED_CI_RUN` | `BLOCKED_EXTERNAL`: neither `580ca82` nor `3719707` exists on a public GitHub ref. The nearest successful reference matrix is [run 36294640316](https://github.com/huou07/vibe-coded-emulator/actions/runs/36294640316) at unrelated snapshot `9b7d7be`; it is not evidence for this source. |
| `ARTIFACT_MANIFEST` | `UNAVAILABLE_EXACT_SOURCE`: no CI-produced DMG/APK/EXE/DEB/Flatpak exists for `3719707`; local temporary bundles are not substituted. |

### Core × platform matrix

| core | macOS | Android | Windows | Linux |
| --- | --- | --- | --- | --- |
| GBA | `PHYSICAL_VERIFIED` local packaged M5 and SRAM readback | `UNVERIFIED_PHYSICAL_DEVICE` / exact-source hosted run unavailable | `UNVERIFIED_PHYSICAL_DEVICE` | `BLOCKED_EXTERNAL` exact-source package unavailable; public baseline hit a melonDS pin failure in the shared Linux build path |
| NDS | `INTEGRATION_VERIFIED` lawful fixture, launch, health, trace, input | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` | `BLOCKED_EXTERNAL` exact-source package unavailable |
| 3DS | `INTEGRATION_VERIFIED` lawful fixture, launch, health, trace, input | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` | `BLOCKED_EXTERNAL` exact-source package unavailable |
| Switch | `INTEGRATION_VERIFIED` Eden companion soak and service suites | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` |

### Gate matrix

| gate | macOS | Android | Windows | Linux |
| --- | --- | --- | --- | --- |
| Build/package | `INTEGRATION_VERIFIED` local product tree | `BLOCKED_EXTERNAL` exact SHA absent from GitHub | `BLOCKED_EXTERNAL` exact SHA absent from GitHub | `BLOCKED_EXTERNAL` exact SHA absent from GitHub |
| Launch/input | `INTEGRATION_VERIFIED` for GBA/NDS/3DS; Switch companion protocol | `UNVERIFIED` current source | `UNVERIFIED` current source | `UNVERIFIED` current source |
| Audio | `INTEGRATION_VERIFIED` diagnostics; audible capture remains unverified for NDS/3DS/Switch | `UNVERIFIED` | `UNVERIFIED` | `UNVERIFIED` |
| Save | `PHYSICAL_VERIFIED` GBA SRAM; Switch service-level only | `UNVERIFIED` current source | `UNVERIFIED` current source | `UNVERIFIED` current source |
| Frame pacing | `PHYSICAL_VERIFIED` GBA; `INTEGRATION_VERIFIED` NDS/3DS | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` |
| Sustained run | `PHYSICAL_VERIFIED` GBA/NDS/3DS; Switch 620-second companion soak | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` |
| Physical hardware | `PHYSICAL_VERIFIED` Apple M5 host | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` | `UNVERIFIED_PHYSICAL_DEVICE` |

### Performance gates

- GBA post-warm-up presentation p95/p99 were `17.963/18.636 ms` against
  `B=16.743 ms` (`1.073B/1.113B`), with `>2B=0`, `>3B=0`, audio xruns `0`,
  emulation p95/p99 `1.157/1.366 ms`, queue p95/max `2/2` of capacity `3`,
  and save-worker I/O off the core/draw path.
- NDS trace budget was `16.715 ms`; presentation p95/p99 were
  `17.596/17.774 ms`, `>2B=0`, `>3B=0`, emulation p95/p99 `3.030/3.158 ms`,
  queue max `3`, and no acquire/fence or save I/O. The paired ten-minute
  health run was `30/30`.
- 3DS trace budget was `16.667 ms`; frame p95/p99 were `17.317/17.568 ms`,
  emulation p95/p99 `1.056/1.179 ms`, and the four isolated tail events are
  classified above. Its synchronous path has no presentation queue telemetry.
- Switch's static homebrew fixture does not provide meaningful frame-pacing
  percentiles; the 620-second hosted-frame soak is the applicable gate.

### Architecture invariants

The current-head suites continue to verify the owned macOS software-core
worker, bounded three-slot presentation FIFO, save-worker ownership of file I/O,
audio recovery, telemetry bounds, input semantics, capability/settings parity,
and absence of Phone Controller, LAN Sync, Full Library Sync, account/login, and
cloud runtime. No production architecture changed after `580ca82`.

### Known limitations and blockers

- Exact-source GitHub Actions and exact-source packaged artifact verification
  cannot occur until this local-only revision is made available on a review ref;
  this session is not authorized to push it.
- The latest public baseline matrix [run 36350670791](https://github.com/huou07/vibe-coded-emulator/actions/runs/36350670791)
  failed Linux DEB because the mutable melonDS nightly extracted SHA is now
  `3a2533677b458e1f2199748a001465a95c7a2e5f8b725ba054e1db93ebe39b77`, while
  the source pins `a217ebd98a68745591cf68bdf35342d73b9044f2a3e6a6071c165dc632ae7cf9`.
  No speculative pin update was made.
- The same public run's Android settings job hit the known tao/Tauri FORTIFY
  abort in an unexpected process; it remains `BLOCKED_UPSTREAM`.
- Android, Windows, and Linux absolute performance and physical hardware remain
  unverified. NDS/3DS fixture save roundtrips and audible output remain
  unverified where the lawful fixtures do not exercise them.

### Release readiness

`NOT_RELEASE_READY` — no new macOS runtime regression was found, but the exact
source hosted matrix and artifact provenance gates are incomplete, and the
public build path currently has a reproducible Linux dependency-pin failure plus
the known Android tao/Tauri blocker.

### Commits

- `580ca82854ee7a7c8e80fb54c138892069a2971d` — production runtime remediation.
- `37197079ec58757bf4719df609194498c18d4c2b` — lawful fixture/runtime evidence.
- This session adds only the readiness/checkpoint documentation above.

## Next action

Publish this exact source on an authorized review ref, run the full hosted
matrix from `37197079ec58757bf4719df609194498c18d4c2b`, and verify the resulting
artifact manifest before any release decision.
