# Android native session recovery — 2026-10-08

## Change

Android `NativeGameActivity` now persists its resume intent through Activity
recreation. The JNI runtime can import the successful `.suspend.state` snapshot
from disk after the isolated game process has been recreated. Suspend snapshots
are written atomically; the existing failed-export path removes a previous
snapshot, so failed exports cannot restore stale progress.

Android's packaged version was bumped from 3.2.1 to 3.2.2 in
`native-offline/src-tauri/tauri.android.conf.json`. Desktop artifacts were not
rebuilt, so their `package.json`/`package-lock.json` and
`native-offline/src-tauri/tauri.conf.json` versions remain 3.2.1. Regression
guards RG-129 and RG-136 are recorded in `docs/REGRESSION_GUARDS.md`.

## Validation

- Baseline before the edit: `python3 -m unittest tests.test_android_native_runtime tests.test_native_regression_guards` — 50 tests passed.
- After the edit: the same command — 52 tests passed.
- `node --test tests/native_sync.test.mjs tests/sync_transfer.test.mjs` — 22 tests passed, including generated Android asset parity.
- `git diff --check` — passed.

## Staging package build

The Android staging build completed successfully with the repository's
`scripts/build-android-staging.sh`. The build compiled the JNI runtime and
Kotlin Activity, generated the Android asset bundle, and produced
`/tmp/an3-android-session-recovery-3.2.2/vibecodedemulator-3.2.2-android-arm64-staging.apk`.
Package metadata reports application id `space.an3tocom.offline`, version
3.2.2, version code 3002002, and ABI `arm64-v8a`. APK signature verification
passed. SHA-256:
`3e4e2a0e060601c8829ac1f49a1527ab4478dc4a09c392237400b8fe3b7c6ad6`.

The build refreshed the generated Android copies of `native-app.js` and
`native-sync.js`; those copies now match their source files byte for byte. The
matching Node guard passes. A package version check caught an unnecessary
desktop version bump: the Flatpak recipe still points to the 3.1.0 Linux
artifact, and Linux was not rebuilt. The desktop version fields were restored
to 3.2.1; Android keeps its independent 3.2.2 version. The staged APK is held
under `/tmp`, was not added to the release catalog, and was not published.

The broader `tests.test_phase_a_branding_autosave_exit` suite has one unrelated
pre-existing failure: its Flatpak-version guard expects the Linux recipe to
track the desktop version, while the recipe still references the 3.1.0 DEB.
No matching current Linux artifact was built in this Android task; resolve the
Linux package and release metadata together before claiming cross-platform
release parity.

## Runtime status

Packaged Android Activity recreation, process-death recovery, rendered frame,
input, and console/runtime-error acceptance were not exercised in this session.
No Android device or emulator was available. Runtime status is **UNVERIFIED**;
the source guards do not establish packaged behavior.
