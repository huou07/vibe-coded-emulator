# Android 0.4.9 — 3DS long-session and suspension stability

Status: COMPLETE. Staging and owner-authorized production serve asset
`add269259a01` and publish APK `0.4.9`.

## Owner report

3DS played but crashed after a while. Acceptance: more than 4 minutes of play,
then upload to production.

## Reproduction attempt

The AVD (Android 15) could not reproduce a foreground crash: 3DS ran 12+ minutes
of in-game 3D gameplay with input, RSS flat (~577–703 MB), zero
`FATAL EXCEPTION`/`SIGSEGV`. One reproducible device-class failure appeared,
however: on **0.4.8**, pressing HOME on the 2 GB AVD killed the
`space.an3tocom.offline:game` process (`Process … has died: prev LAST`). That is
the same lifecycle window Azahar documents as an Android crash source
(surface destruction during rotation/suspension/screen-off).

## Fixes (Android-only; the shared renderer/input contracts were not changed)

1. **Main-thread scan removed.** `NativeGameOverlay.updateDiagnostics` ran
   `saveDirectory.walkTopDown().maxDepth(4)` every second on the UI thread.
   Azahar writes a shader cache into that tree, so the scan grew across a
   session and could stall/ANR the main thread. It now checks the deterministic
   `native-libretro/states/<romId>.autosave.state` file, at most every 15 s or
   when an Auto Save message arrives.
2. **Auto Save defaults on** (activity start flag, settings command and overlay
   flags) so a device kill or crash preserves progress.
3. **Surface race closed.** `jni_runtime.stop_session` now waits up to 1500 ms
   for the worker (`Session::finished`) to leave the render loop before
   detaching its join. The renderer therefore cannot touch a destroyed
   `ANativeWindow`, which is Azahar's documented Android surface-destruction
   crash class. If the worker is stuck in a driver call the join still detaches,
   so the UI thread cannot ANR.
4. **Memory pressure handled.** `NativeGameActivity` handles
   `onTrimMemory`/`onLowMemory` by requesting an Auto Save.
5. Version 0.4.9 / versionCode 4009; shell asset query strings bumped to
   `?v=0.4.9` so the WebView cannot serve a cached old library script.

## Artifact

| Platform | File | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Android arm64 | `vibecodedemulator-0.4.9-android-arm64-staging.apk` | 48,083,017 | `c98518941c213bbb350d37e7c0519a9cc4bcf07e2f5cd34d3cf7873df8a9a49a` |

`versionName 0.4.9` / `versionCode 4009`, v2 signature with the shared Android
Debug certificate `b48f3cdecc39349a75b66817aaad645a861d538be34835f290a2aa570c3beb4b`
(drop-in update). Other four installers unchanged at 0.4.5.
`tools/verify-release-catalog.py` -> `RELEASE_CATALOG=PASS (5 installers)`.

## Verification

- Canonical `tools/release-train.sh --staging verify all`: 131 Python tests, web
  NDS touch, 11 renderer cases, `npm run check`, `git diff --check` -> PASS.
- AVD Android 15 (2 GB), exact 0.4.9 APK: 337 s (5.6 min) of in-game 3D gameplay
  with button/analog input, ~577 MB RSS, zero crashes; pressing HOME left both
  the app and `:game` processes alive (0.4.8 killed `:game` on the same AVD);
  relaunch from the library worked; the nine-section native menu rendered.
- Production HTTPS: APK 200 at exact size 48,083,017 and full-download SHA-256
  `c98518941c21…`; old 0.4.8 URL 404; all five installers exact-size `no-store`.

## Deployment

- Staging `STAGING_RELEASE=PASS`, asset `add269259a01`, release
  `/opt/an3-arcade-staging/releases/20260915-204949-add269259a01`, rollback
  `/opt/an3-arcade-staging/releases/20260915-200544-add269259a01`.
- Production `PRODUCTION_RELEASE=PASS`, asset `add269259a01`, app backup
  `/opt/an3-arcade-backups/20260915-205047`, SQLite backup
  `/srv/an3-arcade/backups/arcade-predeploy-20260915-205047.db` (integrity PASS).

## Honest limitation

The owner's physical-device crash could not be reproduced on the AVD, so the
fixes target the documented Azahar Android surface/lifecycle class and main-thread
load rather than a confirmed device stack trace. If a crash still occurs, the
device `logcat` (or `adb logcat -b crash`) is required to fix the exact cause.
