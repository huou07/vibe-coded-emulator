# P4 staging QA and Android regression

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Target: staging only.

## Staging QA

- Public homepage, offline page, GBA and NDS player routes: PASS
- HTTP Range download: PASS
- Authenticated admin dashboard and monitoring: PASS
- Quick Edit page and update path: PASS
- Enrichment proposal path: PASS
- Batch preview and explicit-confirmation apply path: PASS
- A temporary QA game and its cascading enrichment proposal were deleted at the end: PASS

`STAGING_QA=PASS`

## Physical Android player regression

- Homepage: PASS
- GBA: virtual Start, visible gameplay, and FPS: PASS
- NDS: current-layout direct gestures and virtual-pad tap: PASS; after a longer cold start, visible dual-screen gameplay reached 50 FPS.
- Fullscreen: enter and exit were visually confirmed with separate live coordinates.

`ANDROID_REGRESSION=PASS`

The PWA offline-local-library flow is tracked separately in `02-pwa-offline-e2e.md` and is not included in this Android player-regression pass.
