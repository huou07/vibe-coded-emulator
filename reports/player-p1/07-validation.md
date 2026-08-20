# AN3 Arcade — P1.7 Validation Ledger

Date: 2026-08-20 (Asia/Ho_Chi_Minh)

## Current status

`P1_STATUS=STAGING_VALIDATED_DEVICE_VALIDATION_PENDING`

P1.1–P1.6 source changes are committed and the combined working state passes the 15-test local suite, JavaScript syntax checks, Python compilation, and `git diff --check`. P0 source invariants for canvas-only NDS touch acquisition, native-menu priority, touch-pad capability policy, keyboard focus, fullscreen shell, and save-state controls continue to pass.

Staging release `20260820-211604-p1` is active at the staging endpoint with health asset `587464eca777`; the previous release `20260820-145923` remains available as the rollback point. The release changes only `app.py` and the four player/PWA assets. Staging GBA/NDS startup, profiles/reset, compact speed, global and selected-button sizing, and the NDS native-menu priority path passed. No production system has been modified.

## Required remaining gates

| Environment | Required checks | Status |
| --- | --- | --- |
| Staging browser | Health, asset version, GBA/NDS startup, Low-end/recommended profile restarts, 1/1.5/2/1 speed, global/selected-button reset, and native NDS menu hit testing | PASS |
| Staging browser remaining | Save/load, fullscreen, physical keyboard/remapping, PWA refresh, and console capture | Pending owner/browser matrix |
| Desktop Chromium + Firefox | GBA/NDS startup, More panel, keyboard/remapping, fullscreen, save state, no console errors | Pending owner/browser matrix |
| Android Chrome (Firefox if practical) | Touch defaults, pad show/hide, portrait/landscape/fullscreen, controls at safe maximum, NDS touchscreen coverage, native menu priority | Pending physical device |
| Weak owner device | Frame-rate/perceived responsiveness and profile reversibility | Pending owner device |

Do not deploy production automatically. After these gates pass, publish a `READY_FOR_P1_PRODUCTION_APPROVAL` handoff with the staging release identifier, asset version, device/browser results, test result, rollback point, backup status, and the explicit request for production approval.
