# AN3 Arcade P3 — Android harness and localhost PWA attempt

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Harness

The staging-first Android regression harness is available at `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/android/`. Its safety and use instructions are in `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/android/README.md`.

The harness defaults to `http://192.168.1.8:8092`; its production path requires an explicit `--allow-production` override and is not part of P3 staging acceptance. It has no device selector and therefore never records a serial. It neither roots the phone nor reads accounts, personal files, Android IDs, IMEIs, MAC addresses, or arbitrary browser tabs.

`bash -n` passed for every tool. The current authorized-device result is recorded at `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/android-regression/2026-08-23-device-discovery-host-adb.txt`; the earlier blocked discovery reports remain historical troubleshooting evidence only.

## Physical-device result

```text
TEST=device-discovery
DEVICE=physical Android
RESULT=PASS
EVIDENCE=Host-level ADB probe returned device after USB debugging authorization. Android version, Chrome version, and logical screen size were recorded; no serial or private Android data was read, recorded, or displayed.
RUNTIME_ASSERTION=Android 16; Chrome 151.0.7922.171; logical screen 1080x2340.
KNOWN_LIMITATION=The workspace sandbox cannot see host USB; hardware commands must use the approved host-level execution path. The harness still has no device selector and never records a serial.
REPORT=/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/android-regression/2026-08-23-device-discovery-host-adb.txt
```

## Physical-device staging baseline

These results exercise the still-live P2.15 staging asset `9cf7de4b8d0b`; they are harness and baseline evidence, not acceptance of the local P3 candidate, which has not been deployed to staging.

| Test | Result | Evidence |
| --- | --- | --- |
| Homepage mobile smoke | PASS | HTTP 200, Chrome VIEW intent, and foreground-only screenshot: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/android-regression/2026-08-23-homepage-smoke.txt` |
| GBA route and virtual Start | PASS with visual-startup observation | Authorized route HTTP 200 and one current-layout Start tap at `420,1443`: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/android-regression/2026-08-23-gba-smoke.txt`. The initial canvas remained white while reporting 60 FPS; treat the tap path as passed, not as a claim that gameplay was visually completed. |
| NDS touch, virtual pad, native menu | PASS | Current-layout canvas gestures, one virtual-pad tap, and native performance menu opened without selecting any setting: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/android-regression/2026-08-23-nds-smoke.txt`. NDS later rendered gameplay after startup. |
| Fullscreen enter and exit | PASS | Separate live coordinates were used because the browser chrome disappears on entry: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/android-regression/2026-08-23-fullscreen-smoke.txt`. |

The fullscreen tool now requires separately measured `--enter-toggle` and `--exit-toggle` coordinates. This prevents reuse of a pre-fullscreen coordinate after the layout shifts. The initial same-coordinate run was not treated as acceptance evidence and was overwritten by the corrected passing report above.

## USB-localhost PWA offline E2E

The intended private path is implemented by `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/android/smoke-pwa.sh`: a pre-existing private localhost tunnel is verified, the script adds `adb reverse tcp:18092 tcp:18092`, opens only `http://localhost:18092/`, captures staging evidence only while the approved browser is foreground, and removes the reverse mapping on exit.

The Android prerequisite is now available. The preflight was attempted and stopped safely because no existing private tunnel was healthy on `127.0.0.1:18092`. No SSH tunnel, reverse mapping, browser-security bypass, WAN exposure, Cloudflare change, or production change was made. The required `window.isSecureContext`, Service Worker, manifest/install, network-loss/relaunch, local library, core/ROM, offline launch, and recovery assertions therefore remain unexecuted.

```text
ANDROID_REGRESSION_HARNESS=PASS
PWA_OFFLINE_E2E=DOCUMENTED_BLOCKER
BLOCKER=No private localhost SSH forward is available on 127.0.0.1:18092. Password-based SSH helpers are not permitted; establish non-interactive key/agent authentication first.
RUNTIME_ASSERTION=smoke-pwa.sh stopped before adb reverse because http://127.0.0.1:18092/health was unavailable.
```

After key/agent authentication is available, create the private forward, rerun `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/android/smoke-pwa.sh`, then follow the visible offline diagnostic sequence in `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/android/README.md`. Do not replace this documented blocker with a PASS unless all runtime assertions complete.
