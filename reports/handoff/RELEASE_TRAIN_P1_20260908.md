# P1 — runtime blocker repair and acceptance
RUN: 2026-09-08-multimodel-release-train
Timestamp: 2026-09-08T16:32:16+07:00
STATUS: BLOCKED
NEXT_PHASE: P1 — remaining gameplay acceptance (P2 is not authorized yet)
NEXT_MODEL: Astra Medium

## Completed within P1
Native menu close and Escape now call one authoritative closeMenuDiscardingDraft method. Existing Save Settings and live-preview rollback are retained; key-map capture remains before menu close, followed by NDS cursor release and return-to-library.

Secure worker initialization failed because the isolated player response used COEP require-corp while the renderer worker did not. An isolated local browser fixture with identical worker bytes reproduced failure before execution without the worker header; adding the header enabled effective WebGPU. app.py now adds the matching header only to the renderer worker's raw and versioned routes. No security policy was relaxed. GET and HEAD integration assertions cover both routes.

A second independent WebGPU defect was proven with the original staging renderer: it displayed black while claiming hundreds of rendered frames. A diagnostic listener on a work-only original copy captured GPUValidationError: “Destination texture needs to have CopyDst and RenderAttachment usage.” The destination texture now includes RENDER_ATTACHMENT. See the primary API contract: https://www.w3.org/TR/webgpu/#dom-gpuqueue-copyexternalimagetotexture . The original renderer copy was fetched from staging; no historical file replaced current shared source.

Initialization and first-frame stages are bounded to 16 distinct names, including worker, OffscreenCanvas, adapter/device, context/configure, shader/pipeline/texture, bitmap, copy, encoder, render pass, submit and first frame. WebGPU initialization uses validation scopes and asynchronous pipeline creation; the first frame and resized textures are validated. Worker/render errors retain the stage and exception. Worker startup has a 10-second deadline. Subsequent uncaptured device errors and device loss are surfaced when rendering resumes.

The bridge retries reusable WebGL2 on a fresh presentation canvas after a worker/GPU failure because a transferred or context-bound canvas cannot be reused with another context type. External core canvas is the final fallback only after that WebGL2 attempt fails. The source remains visible until a successful presentation result. Bitmap ownership and the two-frame bound remain protected.

Boot return and presentation submission are now separate readiness milestones. Boot no longer says Playing. Submitted frames say Video active · gameplay unverified. External fallback is explicitly labelled. Optional FPS telemetry is not required for controls or core execution. No claim is made that repeated copies of a frozen source prove gameplay.

## Automated evidence
- Baseline Python: 91 PASS; focused Node touch PASS.
- Final source Python: 93 PASS, including native close-path guard, worker GET/HEAD integration assertions and renderer behavioral wrapper.
- Direct Node: touch plus 7 renderer/readiness cases, 8 PASS total.
- JS syntax, git diff --check and native npm check PASS.
- Fresh npm build:macos PASS; strict deep code signature and DMG checksum verification PASS. Ad-hoc staging signature; not notarized.
- Behavioral tests cover GPU texture flags/stages, adapter fallback, pipeline failure after context binding, failed-frame accounting/bitmap closure, fresh-canvas fallback, external fallback after WebGL2 failure, and truthful readiness for 5,000 repeated presentation frames.
Logs: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/p1-20260908

## Mounted native acceptance
Initial baseline mount /Volumes/VibeCodedEmulator: saved Show FPS on → unsaved off → Escape → reopen off, FAIL.
First repaired mount /Volumes/VibeCodedEmulator-P1: NDS Show FPS unsaved off → Escape → reopen on with Unsaved settings discarded; overlay restored, PASS. Menu close same PASS. Explicit Save off → return/relaunch NDS → off PASS; restored original on and saved. Golden Sun Dark Dawn title/intro visible.
Final mount /Volumes/VibeCodedEmulator-P1-Final: GBA (azul agua beta1.3ml) visible language screen, Menu opens, Escape discard restores saved Show FPS and live overlay. Explicit Save off survives return/relaunch GBA; original on restored and saved. Keyboard capture + Escape says Keyboard mapping cancelled and leaves menu open. Subsequent Escape closes menu; next returns to library. NDS Golden Sun Dark Dawn title/intro visible; Lock cursor then Escape leaves game open and offers Lock cursor again. Full audio, direction/latency, all save slots and 3DS interactive matrix were not re-exercised and remain UNVERIFIED, not inferred from tests. No explicit save-state writes were used for acceptance; normal existing Auto Save behavior was left in place.

## Exact staging state
Asset: 11290264c01d
Release: /opt/an3-arcade-staging/releases/20260908-112644-11290264c01d
Rollback: /opt/an3-arcade-staging/releases/20260908-093537-50d711002677
Health: PASS, environment staging, expected asset.
Current player.js, player-runtime.js, renderer-worker.js and nds-touch.js served SHA parity: PASS. Worker COEP require-corp and immutable caching: PASS.
DMG: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/native-offline/releases/vibecodedemulator-0.4.4-macos-aarch64.dmg
Bytes: 42282987
SHA-256: 37e24bf1d1d6c44ff3267c5649b16010f8bce076cc0bac632cddf17d431b975c
Fresh staged download SHA equals local SHA: PASS.
Parity evidence: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/p1-20260908/staging-parity.json
Build log: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/p1-20260908/native-packaged-source-build.log
Publication log: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/p1-20260908/deployment.log
Only package-staging.sh and the owner-installed staging release helper were used. The wrapper that prepares production artifacts was not used. Production was untouched: no production HTTP request, health, deployment, data, restart, service, symlink or rollback operation.

## Renderer acceptance — current asset
Runtime: Codex in-app Chromium on Mac, secure localhost-only staging SSH tunnel; ROM Pokémon Mystery Dungeon: Explorers of Sky. Screenshots were visually inspected through computer-use tools; these are not owner statements or benchmark measurements.

| Request | Effective | Worker/offscreen | Frames snapshot | Drops | p95 / p99 ms | Visible gameplay |
| --- | --- | --- | ---: | ---: | --- | --- |
| WebGPU | webgpu | true | 4852 | 0 | 0.465 / 0.595 | FAIL: black output |
| WebGL2 | webgl2 | true | 1898 | 2 | 0.580 / 1.645 | FAIL: black output |
| Source-only controlled local proxy | external-core-canvas | false | not applicable | not applicable | not measured | FAIL: white source plus EmulatorJS FPS overlay |

Both staged backend runs label gameplay unverified. The source-only proxy changes only the served presentation bridge in a local diagnostic surface and forwards GETs to staging; it changes no staged files and uses the same core/ROM route. Its source failure shows that the remaining boot/display defect exists independently of the new presentation renderer. It does not prove a specific core root cause, source-frame rate or performance bottleneck.
Synthetic fixtures DO display advancing output with effective WebGPU after both fixes; missing worker COEP reproduces worker failure and fresh-main-thread WebGL2 fallback. Synthetic frames are not gameplay acceptance.

## Remaining blockers and handoff
DISCOVERED ISSUE: Web NDS fails visible gameplay even without the presentation bridge in the controlled desktop launch.
REPRODUCTION: open the stated current staging ROM with renderer=webgpu or renderer=webgl2; black presentation. Local source-only diagnostic at work/p1-source-proxy.py produces white source/FPS output. Do not claim core FPS from presentation counts or overlay text.
LIKELY OWNER: EmulatorJS/melonDS boot/source-output integration; exact cause unresolved.
BLAST RADIUS: web NDS gameplay acceptance and cross-device performance baseline.
RECOMMENDED MODEL: Astra Medium for remaining P1 diagnosis/acceptance.

Physical Android: DEVICE_CONNECTED=no in this phase, so secure Android WebGPU, fresh tap/drag/menu/layout/fullscreen checks are UNVERIFIED. Preserve prior OWNER-VERIFIED Redmi 15 5G Chrome tap, drag and gameplay response PASS separately; this phase does not revoke it. Device availability is not evidence of GPU incapability.

P1 cannot be COMPLETE because visible web gameplay and affected-device acceptance are missing. P2 must not begin: there is not yet an advancing scene for a valid performance comparison. No performance optimization, Renderer Settings UI, P2–P8 implementation or platform port work was done. After P1 acceptance is complete, the planned P2 recommendation remains Sol Medium; it is not the current handoff.

## Files changed in P1
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/app.py
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/static/player.js
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/static/player-runtime.js
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/static/renderer-worker.js
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/native-offline/src-tauri/src/azahar_host.mm
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tests/test_integration.py
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tests/test_native_regression_guards.py
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tests/test_web_renderer_behavior.py
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tests/web_renderer_behavior.test.js
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/docs/REGRESSION_GUARDS.md
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_STATE.md
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/SYSTEM_INSPECTION_HANDOFF.md
- /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P1_20260908.md
- Generated packaged web assets under /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/native-offline/dist and final app/DMG build outputs.
- Evidence under /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/p1-20260908; scratch diagnostic fixtures under /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/work.
