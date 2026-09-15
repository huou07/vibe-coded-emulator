# P3 — deterministic web-facing features

Status: COMPLETE, 2026-09-09. Production was not accessed.

Added Auto/WebGPU/WebGL2 selection to the existing player options panel. Choices are saved locally and applied on explicit restart. A renderer query parameter takes precedence, including explicit Auto. Requested and effective status remain separate from the pending selection. Storage failures are reported without preventing an explicit URL-based restart.

Added expandable diagnostics and Copy Diagnostics. An explicit scalar allowlist includes system, runtime core (null when unavailable), source FPS, presentation FPS, rendered/dropped/replaced counts, worker/OffscreenCanvas, render p95/p99, DPR, source/backing resolution, pixel count, security/isolation, WebGPU availability and fallback reason. Raw exceptions are not copied: known failure stages receive fixed text, and other reasons receive a generic fallback explanation. No cookies, credentials, paths, ROM data or device identifiers are read for copying. Unknown core is not replaced with a guessed runtime identity.

## Regression fixed

Live staging reproduced old service-worker query-insensitive matching returning old CSS for the new player page, clipping the new controls. Player CSS now uses /static/v/<asset>/site.css, is in the route allowlist and service-worker shell, and has immutable delivery. The formerly stale origin now displays the correct grid with no panel overflow. Generic page CSS and core-cache behavior remain intact.

## Validation

- Before: full 93 Python tests and renderer/touch baseline passed.
- After final code: 93 Python tests and 12 Node tests passed; JavaScript syntax and diff checks passed. New tests cover persistence, query precedence, denied storage, safe diagnostics serialization and immutable exact-byte CSS delivery.
- Desktop Chromium: WebGPU selection and restart reached effective WebGPU. Final asset Auto reached effective WebGPU with visibly animated NDS intro. Final Copy Diagnostics reported Copied. New controls expand/close successfully. Runtime core identity is unavailable and shown as null.
- Final asset loaded through the previously stale localhost origin: versioned CSS and grid styles confirmed; no horizontal page/panel overflow.
- Android 15 ARM64 AVD, Chrome 124: final asset requested WebGPU/effective WebGL2 with requestAdapter fallback shown; portrait 320 CSS px panel x10/width300 fits, diagnostics expanded without horizontal overflow. Landscape panel fits and scrolls vertically. An inherited browser zoom of 1.196875 initially clipped the visual viewport; returning it to 1 restored normal portrait layout. Screenshots are under reports/staging/p3-20260909.
- Fullscreen click in hidden desktop browser did not enter fullscreen (document.fullscreenElement remained null): fullscreen acceptance UNVERIFIED. Native-menu command closed the AN3 panel; extended menu/input/fullscreen runtime matrix remains UNVERIFIED. Existing source ownership, touch and fallback behavior tests pass; no touch/canvas/renderer backend architecture changed.
- AVD visible gameplay remains subject to the P2 black-output limitation. This phase does not claim physical Redmi gameplay acceptance or performance improvement.

## Staging

Final asset e9cca6502858; release /opt/an3-arcade-staging/releases/20260909-194251-e9cca6502858; rollback /opt/an3-arcade-staging/releases/20260909-152355-56d5a972da2d. Health reports staging and expected asset. Source and served hashes match:

| File | SHA-256 |
| --- | --- |
| site.css | 878c50c4ffa6840ab8611df9482235f17536b0e2880e81fbfbe67b9fb5fca7e8 |
| player.js | 3ac4e6b676f2eb8f3760927972bf93c5a36890a4f7240ad62e6ab6ab8233f7a5 |
| player-runtime.js | 55292dacf66bde25c91ab4f2834407b7cc6026d4bd0ba0ec49d377b8aa4713aa |
| renderer-worker.js | 7d94e71fa9223560a2a492a9f7f54ffee41a07faff7b335b50e041cc384e0bf4 |
| nds-touch.js | 3d879130a8df25a9393accaa835d4bcf755c93e72c0fd87810617f34324274f0 |

Changed this phase: app.py, static/player-runtime.js, static/player.js, static/site.css, static/service-worker.js, tests/web_renderer_behavior.test.js, tests/test_integration.py, tests/test_regression_invariants.py and release documentation. Intentional dirty tree preserved. Next phase P4, Sol Light; no P4 edits performed.
