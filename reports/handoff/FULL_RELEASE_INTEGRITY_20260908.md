# Full release integrity audit — 2026-09-08 09:42 +0700

Release readiness: **BLOCKED**, with concrete findings below. This audit did
not add features, optimize or change the renderer/input/native host source.
The release candidate is for staging verification, not production approval.

## Current authority and touch acceptance

**OWNER-VERIFIED PHYSICAL DEVICE PASS** — owner personally confirmed actual
NDS touchscreen tap, drag, and gameplay response on Redmi 15 5G / Android Chrome.
The owner confirmed Pokémon Mystery Dungeon: Explorers of Sky as the comparison
ROM. This is owner runtime evidence, not an automated result. It supersedes
older bridge-only and physical-touch-pending statements for that same behavior.
It does not establish Firefox, every layout, fullscreen, orientation, long-press,
or menu-close subcase. Android Firefox remains UNVERIFIED, with its historical
white-canvas limitation retained separately.

The connected harness independently reported Android 16, Chrome 152.0.7977.75,
1080×2340, DEVICE_CONNECTED=yes. No serial, account or private identifier was
recorded. Existing zero-movement tests pass; no new touch patch was warranted.
RG-048 retains the actual one-frame release-latch and source-only compatibility
event shield history. The superseded undefined-return hypothesis stays in its
historical dated handoff, not the current root-cause status.

## Source and staging parity

Before publication: asset `50d711002677`, release
`/opt/an3-arcade-staging/releases/20260908-001932-50d711002677`.
Earlier rollback asset: `cbe509a99153`.
After publishing the fresh DMG using repository `deploy/package-staging.sh`
and owner-installed `/usr/local/sbin/an3-arcade-staging-release`:

- Active asset: `50d711002677` (web source unchanged).
- Active release: `/opt/an3-arcade-staging/releases/20260908-093537-50d711002677`.
- Immediate rollback: `/opt/an3-arcade-staging/releases/20260908-001932-50d711002677`.
- Health: HTTP 200, `ok=true`, `environment=staging`, expected asset.
- Staging is bound to `192.168.1.8:8092`; a loopback port probe is not its health check.
- Strict host-key checking and key-only authentication passed.
- Production was untouched: no production health, restart, deploy or data operation.
  The wrapper that also prepares production artifacts was not used.

All six raw deployed files match the working tree by SHA-256:

| File | SHA-256 |
| --- | --- |
| static/player.js | `301592285ec3c9c0e2c6d060eb154a6475c59d69c2c16d0475590fb814791531` |
| static/player-runtime.js | `5546b3013e7026aceb32a09f95879e24d00d1880b6e21b73fa54ce01c9f3b0f1` |
| static/renderer-worker.js | `854c373f246ccb9e18590b5c5be9127741470f0fe4538a10adc59d4fc12bd2aa` |
| static/nds-touch.js | `3d879130a8df25a9393accaa835d4bcf755c93e72c0fd87810617f34324274f0` |
| static/site.css | `3c7cd43af1af2bb7a5d374e0354c1029d703a7b9496bb9a61c602353143d9ac1` |
| static/service-worker.js | `92d4d12666f0f0ae8bc1795d33b88e526a78abf5a72b12a26edc413fdd6a6143` |

The browser DOM on desktop and physical Android loaded player.js,
player-runtime.js, renderer-worker.js and nds-touch.js under
`/static/v/50d711002677/`. CSS uses `/static/site.css?v=50d711002677`.
Those HTTP responses matched source. The service worker is served at
`/service-worker.js?v=50d711002677`: app.py substitutes `__ASSET_VERSION__`, so
its served hash intentionally differs from the raw file; exact substituted
payload comparison PASS. Four versioned JS routes returned immutable caching;
service worker returned no-cache. LAN HTTP is not a secure isolated runtime
merely because isolation headers exist. A localhost-only SSH tunnel was tested
separately; no TLS warning or browser security protection was bypassed.

## Renderer truth table — current asset only

Values are snapshots, not full-game benchmark averages. Worker-active for LAN
Android is evidenced by successful offscreen frame-result messages and current
worker implementation; there is no separate public workerActive field.
Desktop DOM does not expose the complete fallback reason, recorded as unavailable.

| Runtime | requestedBackend | effectiveBackend | fallbackReason | workerActive | offscreenActive | renderedFrames | droppedFrames | p95 ms | p99 ms |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| Desktop Chromium LAN explicit WebGL2 | webgl2 | webgl2 | none observed | inferred active | true | 794 → 5440 | 0 | 0.2 | 0.2 |
| Android Chrome LAN explicit WebGL2 | webgl2 | webgl2 | empty | active frame-result path | true | 1354 → 4906 | 1 → 1 | 0.4 | 0.7 |
| Desktop Chromium LAN WebGPU request | webgpu | webgl2 | unavailable in DOM | inferred active | true | 2023 | 0 | 0.2 | 0.4 |
| Android Chrome LAN WebGPU request | webgpu | webgl2 | WebGPU was requested, but the effective backend is webgl2. | active frame-result path | true | 1235 | 1 | 0.7 | 1.3 |
| Desktop Chromium localhost WebGPU request | webgpu | external-core-canvas | unavailable in DOM | inactive bridge | false | 0 | 0 | unavailable | unavailable |
| Android Chrome localhost WebGPU request | webgpu | external-core-canvas | Render worker failed. | failed initialization | false | 0 | 0 | null | null |

Android secure-origin capability reported `webgpuAvailable=true`. Therefore this
is **WebGPU initialization FAIL**, not “device has no WebGPU”. No live WebGPU
PASS is claimed. The fallback chain itself needs investigation before acceptance.

WebGL2 worker transport is live-proven, but **visible advancing NDS gameplay was
not proven in these explicit-backend audit launches**. Desktop showed a white
screen/FPS overlay or black output; Android showed black output with Playing.
Counters alone do not promote these runs to gameplay PASS. This separate launch
failure does not revoke the owner's working-session tap/drag evidence.

Secure desktop console recorded EmulatorJS update-check fetch failure and wake
lock permission denial. Neither is established as the cause of the game/worker
failure. No general “no errors” claim is made.

## Redmi smoothness: core versus presentation

Same asset and server ROM route were used on Mac and Redmi. A matching advancing
gameplay scene and equal saved settings were **not achieved**; consequently a
valid cross-device gameplay benchmark cannot be claimed.

Measured physical Android WebGL2 window:

- `performance.now`: 34018.70 → 93379.30 ms (59.3606 seconds).
- Worker presentation: 1354 → 4906 = 3552 frames, approximately **59.84 fps**.
- Core `gameManager.getFrameNum()`: **5 → 5**, observed delta **0 fps**.
- FramePacing coreFrames: 4 → 4; longTasks 10; UI p95/p99 about 16.8 ms.
- Browser visible=true, EmulatorJS paused=false; screenshot black.
- `getFrameNum()` wraps core export `get_current_frame_count`; it is not the
  renderer's frame counter. No independent core callback sampling was available
  to prove that export's accuracy in this stalled session.

Classification of the sampled run: **stalled core/boot or invalid core telemetry,
while presentation continues**. It is not evidence of a presentation-throughput
bottleneck. Classification of the owner's visibly less-smooth working gameplay:
**UNRESOLVED**. A 0.7 ms renderer p99 does not exonerate every graphics cost and
cannot identify core CPU, frame duplication, pacing, thermal or settings causes.
No optimization was started. Required next evidence is a reproducible advancing
scene on both devices and independent core-frame production measurements.

## Fresh packaged app and download parity

`npm run build:macos` rebuilt current source, produced the app and fresh DMG,
passed deep strict codesign verification and hdiutil checksum verification.
The artifact is ad-hoc signed staging output; it is not notarized public output.
It was mounted read-only and launched from the mount. Process executable path
confirmed `/Volumes/VibeCodedEmulator/VibeCodedEmulator.app/Contents/MacOS/an3-offline-native`.
An earlier mount in the same audit used `/Volumes/VibeCodedEmulator 2/`.

Fresh DMG SHA-256:
`5e0de9ea7280b59f8ac71dc3f7dfd1e9bbcbd8c28ad9b57421055ee4d21c8d01`.
Old staging download SHA-256:
`35f6abcb09f1ef321b0eab467daf9b19f33a35a9478adf86c0d6f42c5ec36e87`.
After staging publication, a fresh HTTP download returned the **exact fresh hash**.
Thus stale DMG parity is resolved; no old `54b2...` package evidence was inherited.

Native Golden Sun Dark Dawn reached visible NDS gameplay. All nine tabs were
clicked and their contents inspected: General, Graphics, Audio, Keyboard,
Controller, Emulation, Save States, Diagnostics, About. Screenshots confirmed
the visible tabbed panel. Controller remapping is explicitly unimplemented;
this was not represented as a working feature. Save States exposes slots 1–10,
including 5, and separate Auto Save/import/export; no user save was overwritten
by an explicit test action. Normal pre-existing Auto Save remained enabled.

Save Settings functional test:

1. Toggle Show FPS off and press Save Settings: “Settings saved” appears.
2. Return to library, relaunch NDS, reopen Graphics: Show FPS remains off — PASS.
3. Restore original Show FPS on and save — PASS; original preference restored.
4. Toggle without saving and close via Menu: reopening restores saved value
   and shows “Unsaved settings discarded.” — PASS.
5. Toggle without saving and close via Escape: reopening retains unsaved value
   and live overlay remains changed — **FAIL**.

Exact source cause: keyDown Escape branch hides `_menu_panel` directly and
never invokes `discardSettingsDraft`; `toggleMenu:` does invoke it. This is
an explained current RG-025/RG-028 regression in both current source and fresh
staging package. No native host fix was silently bundled into an audit artifact.
The general nine-tab and explicit-save tests pass; full Settings acceptance does
not. Other native systems' live audio, input, save, and renderer checks are
UNVERIFIED on this fresh artifact rather than inherited from older packages.

## Tests and ledger reconciliation

- Node focused NDS behavior suite PASS, including all zero-movement cases.
- Focused Python: web touch 2 PASS; regression invariants 15 PASS.
- Full Python suite: 91 PASS before and after documentation reconciliation.
- JavaScript syntax checks and git diff --check PASS before reconciliation;
  post-documentation checks recorded in the audit test log.
- Existing source and behavior tests did not detect the Escape draft defect;
  tests passing is not interactive acceptance.
- Every RG-001–RG-048 now has current source/staging/package/owner evidence scope.
- Every audit-matrix live row is reconciled; historical evidence is retained in
  `REGRESSION_GUARDS-before-integrity-20260908.md` and historical incidents.
- RG-033/RG-044/RG-048 no longer describe owner-confirmed tap/drag as pending.
  RG-038 points to current asset/release. Expanded touch subcases stay distinct.
- Renderer architecture, input ownership, source/presentation pointer contract,
  menu guards and mapping code were unchanged. Their complete live regression
  matrix is not newly asserted as PASS merely because source was retained.

## Release-readiness table

| Requirement | Current result | Explanation / remaining evidence |
| --- | --- | --- |
| Ledger contradictions | RECONCILED | 48 guards and matrix; history retained |
| Owner actual mobile tap + drag | OWNER-VERIFIED PHYSICAL DEVICE PASS | Not automation; no Firefox generalization |
| Current six-file staging parity | PASS | Raw hashes and expected served payloads |
| Explicit WebGL2 | PARTIAL / acceptance blocked | Worker frames advance; audit game output does not |
| LAN WebGPU fallback | PASS fallback reporting | Effective WebGL2; no WebGPU PASS |
| Secure WebGPU | FAIL | Capable Android runtime: Render worker failed; external core fallback |
| Redmi working-game bottleneck | UNRESOLVED | Captured stalled launch is not owner's advancing scene |
| Fresh DMG build/mount/launch | PASS | Exact fresh SHA and mounted process |
| Nine Settings tabs | PASS | Each tab exercised |
| Explicit Save Settings | PASS | Survives NDS relaunch; original preference restored |
| Escape draft discard | REGRESSION — EXPLAINED | keyDown bypasses discardSettingsDraft |
| Staging DMG parity | PASS | Fresh downloaded hash matches |
| Production | UNTOUCHED | No production operation |
| Overall release readiness | BLOCKED | No feature/optimization work may proceed yet |

There is no unexplained stale artifact or unlabeled regression. There are real,
explicit acceptance blockers; this report does not turn them into PASS.
