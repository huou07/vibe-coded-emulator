# Release train P2 — NDS performance diagnosis

Timestamp: 2026-09-09T15:07:11+07:00  
Status: **COMPLETE — classified insufficient evidence after authorized AVD substitution**

## Outcome

The staging player now exposes passive, separately named measurements for independent core/source delivery, presentation, frame loss/replacement, ImageBitmap acquisition, worker render, UI/rAF pacing, long tasks, DPR, source/presentation dimensions and pixels, and requested/effective renderer. Core/source FPS is calculated only from EmulatorJS core-counter deltas over wall time; it is not inferred from rAF or renderer throughput. A counter regression invalidates the rate.

No performance optimization was made. Matched MacBook Air M5 measurements at the same ROM, New Game scene, layout, speed, and settings show neither WebGPU nor WebGL2 is bottlenecked: both core and presentation rates are approximately 60 FPS, with zero dropped/replaced/skipped frames and sub-millisecond capture/worker percentiles. The Redmi 15 5G remained disconnected. The user authorized an Android Virtual Device substitute; its limitations and measurements are recorded below.

## Mac matched-scene baselines

| Metric | WebGPU | WebGL2 |
| --- | ---: | ---: |
| Core/source FPS | 60.0001 | 60.0143 |
| Presentation FPS | 60.0799 | 59.9713 |
| Dropped / replaced / skipped | 0 / 0 / 0 | 0 / 0 / 0 |
| ImageBitmap p50 / p95 / p99 ms | 0.025 / 0.060 / 0.110 | 0.035 / 0.075 / 0.110 |
| Worker render p50 / p95 / p99 ms | 0.100 / 0.190 / 0.225 | 0.025 / 0.065 / 0.090 |
| UI frame p50 / p95 / p99 ms | 16.665 / 18.540 / 18.550 | 16.665 / 18.070 / 18.540 |
| Source / presentation | 2560x1212 / 2560x1212 | 2560x1212 / 2560x1212 |
| DPR | 2 | 2 |

These desktop results rule out a desktop presentation bottleneck in this scene. They do not distinguish core CPU, phone GPU/compositing, duplicate presentation, pacing, thermal behavior, or device-specific settings on Redmi.

## Implementation and verification

- `static/renderer-worker.js`: frame replacement reporting; rolling capture, render and presentation measurements; explicit frame counts and backing dimensions.
- `static/player-runtime.js`: independent core-counter rate, UI percentiles, counter regression detection, and long-task totals.
- `static/player.js`: privacy-safe `data-p2-*` publication from the live renderer snapshot.
- `tests/web_renderer_behavior.test.js`: separation of capture/render/presentation/backing metrics and proof that core/source rate uses the independent core counter.
- Full Python suite: 93 PASS. Renderer Node suite: 9 PASS. JavaScript syntax and `git diff --check`: PASS. Dirty worktree count remained 117.

Final staging asset `af16e551490f`, release `/opt/an3-arcade-staging/releases/20260909-144343-af16e551490f`, rollback `/opt/an3-arcade-staging/releases/20260909-143353-2a6e1d919803`. Health, four-file served/source SHA-256 parity, and explicit-WebGL2 final telemetry smoke PASS. Production was untouched.

## Android Virtual Device substitution

The available `codex-nds-api35` profile is Android15 ARM64 with four virtual cores,2.5GB RAM, a320x640 display, API35 Google APIs, and Chrome124. The saved profile disables GPU acceleration. Two explicit command-line modes were tested through the private localhost tunnel to staging:

| AVD run | Result |
| --- | --- |
| Host GPU, explicit WebGL2 | Audio activation and core advancement PASS. Stable sample: core38.5001 FPS, presentation60.2774 FPS, zero drops at that snapshot, ImageBitmap p95/p99 0.410/1.025ms, worker p95/p99 0.155/0.430ms, UI p95/p99 16.67/33.34ms, source/presentation766x120, DPR1. Both presented and temporarily exposed source canvases remained black, so visible gameplay and the New Game scene were not established. |
| Host GPU, requested WebGPU | `navigator.gpu=true`, but requestAdapter failed; effective WebGL2 fallback and OffscreenCanvas remained active. Core38.5001 FPS, presentation59.9849 FPS, one skipped/dropped frame, ImageBitmap p95/p99 0.720/1.205ms, worker p95/p99 0.225/0.840ms. Output remained black. |
| SwiftShader software GPU | Startup reached100% and reported core started, then the page stopped responding to diagnostics and never produced visible gameplay. No benchmark was accepted. |

The valid advancing host-GPU samples suggest a virtual DEVICE/CPU/WASM throughput limit because core delivery is roughly38 FPS while presentation and the bitmap/worker bridge remain near60 FPS and inexpensive. The AVD runs use Apple M5 host resources and emulator GPU translation; they cannot represent Redmi GPU, CPU, thermal or Chrome152 behavior. Because output was black, the same visible scene requirement also failed. The authoritative classification is therefore **INSUFFICIENT EVIDENCE** for the reported Redmi smoothness issue. No optimization is justified by this evidence.

P2 is complete under the task's allowed insufficient-evidence classification. A future physical-device run may supplement this result, but it is not a gate for P3 under the user's AVD substitution.

Evidence: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/p2-20260909/`.
