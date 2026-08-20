# AN3 Arcade — P1.7 Validation Ledger

Date: 2026-08-20 (Asia/Ho_Chi_Minh)

## Current status

`P1_STATUS=STAGING_MOBILE_FOLLOW_UP_PENDING_PHYSICAL_RETEST`

P1.1–P1.6 source changes are committed and the combined working state passes the 15-test local suite, JavaScript syntax checks, Python compilation, and `git diff --check`. P0 source invariants for canvas-only NDS touch acquisition, native-menu priority, touch-pad capability policy, keyboard focus, fullscreen shell, and save-state controls continue to pass.

The original P1 staging release `20260820-211604-p1` was followed by staging-only mobile follow-up release `20260820-215934-p1-mobile-fix`, health asset `49eeea612e77`. Its immediate rollback target is `20260820-211604-p1`. The follow-up keeps a pad visible on a short mobile stage and sets the verified EmulatorJS FPS HUD default to `show`; see `08-mobile-follow-up.md`. No production system has been modified.

## Required remaining gates

| Environment | Required checks | Status |
| --- | --- | --- |
| Staging browser | Health, asset version, GBA/NDS startup, Low-end/recommended profile restarts, 1/1.5/2/1 speed, global/selected-button reset, and native NDS menu hit testing | PASS |
| Owner validation reported | Save/load, physical keyboard/remapping, PWA refresh, weak-device performance, and speed changes | PASS (reported) |
| Android phone, Redmi 15 5G | GBA/NDS pad issue resolved separately; NDS audio crackles at reported 30–50 FPS. Firefox is frequent; Chrome/Mi Browser occur during scene changes; phone speaker and Bluetooth both reproduce it. | Audio follow-up experiment pending |
| Staging browser follow-up | Non-fullscreen 390×844 viewport with GBA/NDS pad shown; native EmulatorJS FPS value is `show` on both systems | PASS; responsive evidence only |
| Android Chrome (Firefox if practical) | Touch defaults, pad before fullscreen, portrait/landscape/fullscreen, NDS touchscreen coverage, native-menu priority, and NDS audio | Pending physical retest |

Do not deploy production automatically. After these gates pass, publish a `READY_FOR_P1_PRODUCTION_APPROVAL` handoff with the staging release identifier, asset version, device/browser results, test result, rollback point, backup status, and the explicit request for production approval.
