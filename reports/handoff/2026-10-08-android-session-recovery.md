# Android native session recovery — 2026-10-08

## Change

Android `NativeGameActivity` now persists its resume intent through Activity
recreation. The JNI runtime can import the successful `.suspend.state` snapshot
from disk after the isolated game process has been recreated. Suspend snapshots
are written atomically; the existing failed-export path removes a previous
snapshot, so failed exports cannot restore stale progress.

Packaged app version fields were bumped from 3.2.1 to 3.2.2 in
`native-offline/package.json`, `native-offline/package-lock.json`,
`native-offline/src-tauri/tauri.conf.json`, and
`native-offline/src-tauri/tauri.android.conf.json`. Regression guard RG-136 is
recorded in `docs/REGRESSION_GUARDS.md`.

## Validation

- Baseline before the edit: `python3 -m unittest tests.test_android_native_runtime tests.test_native_regression_guards` — 50 tests passed.
- After the edit: the same command — 52 tests passed.
- `git diff --check` — passed.

## Runtime status

Packaged Android Activity recreation, process-death recovery, rendered frame,
input, and console/runtime-error acceptance were not exercised in this session.
No Android device or emulator was available. Runtime status is **UNVERIFIED**;
the source guards do not establish packaged behavior.
