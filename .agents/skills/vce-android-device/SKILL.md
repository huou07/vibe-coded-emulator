---
name: vce-android-device
description: Use when building, installing or testing the VCE Android app — the dedicated VCE AVD, the hosted arm64 build lane, the committed asset mirror, adb/instrumentation runs, or Android device acceptance. Triggers on "Android build", "install the APK", "AVD", "emulator", "adb", "Android regression", "mirror". Do not use for emulator core or packaging decisions on other platforms, or for a Web-only change.
---

# Android lane

Two different things are called "Android testing" here and they are not
interchangeable: a **hosted build lane** proves an APK builds; a **device run**
proves the app works. Never report one as the other.

## Preconditions

- Read `docs/features/android.md`, `docs/android-regression.md` and the mirror
  guard (RG-156).
- The owner authorized **one Android AVD dedicated to VCE** on this Debian host
  (2026-10-18), for example `vce-api35`. Never attach to, reconfigure, snapshot or
  stop the AVD that OR is using.
- One resource-intensive job at a time: check RAM and disk first, share the
  native lock, bound the timeout, clean up the whole process group afterwards.
- The Android assets under `native-offline/src-tauri/gen/android/app/src/main/assets/`
  are a **committed mirror** of `static/` and `native-offline/web/`; no build step
  regenerates it.

## Procedure

1. If you edited `static/` or `native-offline/web/`, re-copy the file into the
   Android assets and run `python3 tools/check-native-mirror.py`.
2. Build with the project's builder — `native-offline/scripts/build-android-staging.sh`
   — or use the hosted lane's artifact; never hand-roll a Gradle path the project
   does not use. Record the artifact size and SHA-256.
3. For the hosted lane, wait for the run that names the exact SHA. The lane states
   in its own job name that there is no device acceptance.
4. Device run, on the dedicated AVD: boot it, install the recorded artifact,
   then execute one journey — library → import a lawful fixture → launch →
   input/touch → quick save/load → exit → relaunch. Record the AVD name, API
   level, image and the installed artifact hash.
5. For 3DS, the Azahar companion is a separate installed app; AN3 hands it a
   read-only per-ROM content URI. Record whether the companion was present.
6. Re-run the mirror check and `bash tools/verify-project.sh` after the change.

## Evidence classes

- **Build lane** green: the APK compiles on the hosted runner. Nothing more.
- **AVD run**: device-class evidence for the journey executed. It is not packaged
  acceptance on physical hardware, and it is not a Play-readiness statement.
- **Physical device**: needs the owner's device or a hosted device lane; record it
  separately.

The staging APK is signed with a debug/testing key. A production APK/AAB requires
the owner release identity — that is not a worker action.

## Rules

- Do not reuse, disturb or snapshot OR's AVD; do not run two emulators at once.
- Do not weaken the mirror check to keep an edit local.
- Do not claim device acceptance from a build-lane artifact.
- Keep fixtures lawful and out of the repository; keep the installed app's data
  under app-private storage.

## Stop and report

Report the AVD identity, the artifact identity, the journey steps and results,
the lanes run, and every row that remains `UNVERIFIED`. Update
`docs/features/android.md` with the dated result.
