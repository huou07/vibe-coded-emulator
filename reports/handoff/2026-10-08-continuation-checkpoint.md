# VCE continuation checkpoint

Date: 2026-10-08
Branch: `feature/phone-controller-cross-platform`
Base HEAD before this checkpoint's tooling fix: `be8de71d8677bd400635dfe943aa1095dccc15f8`

## Linux staging packages

The local DEB and staging Flatpak build results, checksums, source pins, and
verification limits are recorded in
`reports/handoff/2026-10-08-linux-3.2.1-staging-packages.md`. The packages
remain staged and are not in the release catalog.

## Android packaged runtime and an3ctl

- Installed Android arm64 APK: `/tmp/an3-android-session-recovery-3.2.2/vibecodedemulator-3.2.2-android-arm64-staging.apk`
- SHA-256: `3e4e2a0e060601c8829ac1f49a1527ab4478dc4a09c392237400b8fe3b7c6ad6`
- Android 15 `an3qa-api35` was run with a dedicated temporary data image under
  `/tmp/an3-android-avd-isolated-20261008`; pre-existing AVD data was not used.
- Packaged app opened to the library and Settings successfully. This is UI
  smoke evidence only; a user-imported ROM gameplay journey was not verified.
- The old `an3ctl rom load` implementation ignored failure to copy into the
  app-private directory and treated `Starting:` as proof of success, although
  Android had denied the non-exported game Activity. `romLoad` now checks the
  copy and launch results and returns success only after
  `NativeGameActivity` becomes resumed. Guard `RG-137` and tests
  `tests/an3ctl_android_adapter.test.mjs` cover this contract.
- Revalidation against the packaged APK on the isolated Android 15 emulator:
  `an3ctl rom load /tmp/an3-linux-staging-3.2.1/smoke-loop.gba --target android
  --system gba --json` exited 6 (`E_ACTION_FAILED`) and reported
  `Permission denied` for `/data/data/space.an3tocom.offline/an3-roms/...`.
  This is the accurate limitation for the release APK; use the app's in-app
  ROM import flow for gameplay verification.
- `node --test tests/an3ctl.test.mjs tests/an3ctl_android_adapter.test.mjs`:
  6 passed, 2 skipped (Android-device and native-player cases require their
  optional targets). The isolated emulator was stopped after validation.

## Public repository state

At the time checked on 2026-10-08, public GitHub `main` was at
`48fb769e875692cb0f775fa89fa2ca8d6b1f776f` with release `v3.3.3`; local
development HEAD is a divergent private line. Do not push the local branch or
replace public `main` with a clean snapshot of older code. No publication or
catalog update occurred in this session. Reconcile the public line before any
future requested publication, then run the mandatory public-release security
workflow.

## Remaining verification

- Linux packages still need ordinary packaged-app acceptance: graphical launch,
  live input, audio, Flatpak installation, and an offline user journey.
- Android needs ROM import through the actual library picker followed by
  packaged gameplay, input, save/resume, and lifecycle verification. The
  current `an3ctl rom load` shortcut cannot access a release app's private
  storage and is not an alternative to that user journey.
- No production deployment or public push is authorized by this checkpoint.
