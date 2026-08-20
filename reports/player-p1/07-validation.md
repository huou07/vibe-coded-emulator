# AN3 Arcade — P1.7 Validation Ledger

Date: 2026-08-20 (Asia/Ho_Chi_Minh)

## Current status

`P1_STATUS=LOCAL_VALIDATED_STAGING_BLOCKED`

P1.1–P1.6 source changes are committed and the combined working state passes the 15-test local suite, JavaScript syntax checks, Python compilation, and `git diff --check`. P0 source invariants for canvas-only NDS touch acquisition, native-menu priority, touch-pad capability policy, keyboard focus, fullscreen shell, and save-state controls continue to pass.

The current session cannot authenticate non-interactively to staging, so no P1.4–P1.6 overlay has been activated there. This is a deployment-access blocker, not a P0 regression. No production system has been modified.

## Required remaining gates

| Environment | Required checks | Status |
| --- | --- | --- |
| Staging | Health, asset version, GBA/NDS startup, profile restart behavior, 0.5/1/1.5/2 speed, save/load, fullscreen, physical keyboard/remap, virtual pad, native NDS menu hit testing, and PWA refresh | Pending staging access |
| Desktop Chromium + Firefox | GBA/NDS startup, More panel, keyboard/remapping, fullscreen, save state, no console errors | Pending |
| Android Chrome (Firefox if practical) | Touch defaults, pad show/hide, portrait/landscape/fullscreen, controls at safe maximum, NDS touchscreen coverage, native menu priority | Pending physical device |
| Weak owner device | Frame-rate/perceived responsiveness and profile reversibility | Pending owner device |

Do not deploy production automatically. After these gates pass, publish a `READY_FOR_P1_PRODUCTION_APPROVAL` handoff with the staging release identifier, asset version, device/browser results, test result, rollback point, backup status, and the explicit request for production approval.
