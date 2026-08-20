# AN3 Arcade — P1.7 Validation Ledger

Date: 2026-08-20 (Asia/Ho_Chi_Minh)

## Current status

`P1_STATUS=PRODUCTION_DEPLOYED_KNOWN_DEFECT_ACCEPTED`

P1.1–P1.6 source changes are committed and the combined working state passes the 15-test local suite, JavaScript syntax checks, Python compilation, and `git diff --check`. P0 source invariants for canvas-only NDS touch acquisition, native-menu priority, touch-pad capability policy, keyboard focus, fullscreen shell, and save-state controls continue to pass.

The original P1 staging release `20260820-211604-p1` was followed by staging-only mobile follow-up release `20260820-215934-p1-mobile-fix`, health asset `49eeea612e77`. Its immediate rollback target is `20260820-211604-p1`. The follow-up keeps a pad visible on a short mobile stage and sets the verified EmulatorJS FPS HUD default to `show`; see `08-mobile-follow-up.md`.

The owner explicitly approved production deployment while accepting the unresolved NDS mobile audio defect. Production was deployed on 2026-08-20 with health asset `aa8faa00dc8a`; its five changed files match staging byte-for-byte. The production backup is `/opt/an3-arcade-backups/20260820-225248-p1-production/p1-files.tar.gz`. See `09-production-release.md`.

## Required remaining gates

| Environment | Required checks | Status |
| --- | --- | --- |
| Staging browser | Health, asset version, GBA/NDS startup, Low-end/recommended profile restarts, 1/1.5/2/1 speed, global/selected-button reset, and native NDS menu hit testing | PASS |
| Owner validation reported | Save/load, physical keyboard/remapping, PWA refresh, weak-device performance, and speed changes | PASS (reported) |
| Android phone, Redmi 15 5G | GBA/NDS pad issue resolved separately; NDS audio crackles at reported 30–50 FPS. Firefox is frequent; Chrome/Mi Browser occur during scene changes; phone speaker and Bluetooth both reproduce it. | Audio follow-up experiment pending |
| Staging browser follow-up | Non-fullscreen 390×844 viewport with GBA/NDS pad shown; native EmulatorJS FPS value is `show` on both systems | PASS; responsive evidence only |
| Android Chrome (Firefox if practical) | Touch defaults, pad before fullscreen, portrait/landscape/fullscreen, NDS touchscreen coverage, native-menu priority | PASS (owner validation) |
| NDS audio, Redmi 15 5G | Chrome Low-end/1×/VSync disabled still crackles; Firefox more frequent; speaker and Bluetooth both reproduce | KNOWN DEFECT ACCEPTED FOR P1 RELEASE |

P1 is complete. Do not change the known audio defect under this release without a separately scoped core/runtime investigation and validation plan.
