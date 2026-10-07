# Android native game startup fix

Date: 2026-10-08
Branch: `feature/phone-controller-cross-platform`
Base HEAD: `572f802` (`fix(an3ctl): verify Android ROM load success`)

## Failure and fix

The packaged 3.2.2 app accepted the in-app ROM import, then crashed immediately
when the real library card launched `NativeGameActivity`. Android's
`data_app_native_crash` report showed a SIGSEGV in
`std::__ndk1::mutex::lock()` from `NativeCoreHost::Impl::initialize`, with the
stack pointer below the mapped game-thread stack. That initialization hashed
the ROM identity using a 1 MiB local array. The array is now a heap-backed
vector; hashing and the identity behavior are unchanged.

The Android package version was bumped from 3.2.2 to 3.2.3 (bug-fix patch).
Regression guard RG-138 records the failure and validation.

## Artifact and checks

- APK: `/Users/meomeo/Documents/edit an3tocom apps&web/native-offline/releases/vibecodedemulator-3.2.3-android-arm64-staging.apk`
- Size: `50352593` bytes
- SHA-256: `25fed3a499ae3f5e82d2a1e379fedd8a9de560b52cc84f8d5d92de28b630a655`
- Sidecar: `vibecodedemulator-3.2.3-android-arm64-staging.apk.sha256`
- Signature: APK v2 verified; Android Debug signer SHA-256
  `b48f3cdecc39349a75b66817aaad645a861d538be34835f290a2aa570c3beb4b`, matching
  the prior 3.2.2 staging APK.
- `python3 tools/verify-release-catalog.py`: PASS (5 installers).
- `python3 -m unittest tests.test_android_native_runtime tests.test_native_renderer_contract tests.test_native_regression_guards`:
  PASS (62 tests).

## Packaged Android 15 validation

The APK installed on an isolated copy of AVD `an3qa-api35`; the pre-existing
AVD data image was not used. The generated 260-byte GBA fixture was copied to
Downloads and imported through the app's actual Add ROM → Android document
picker path. The library card then launched `NativeGameActivity`, which stayed
resumed with the `:game` process alive for a 60-second soak. Quick Save Slot 1
and Quick Load Slot 1 completed without terminating the activity. Logcat had
zero fatal signals during the soak. Back returned to the library, and the same
library card relaunched the game successfully with the process still alive and
no fatal signal. The visible output from this synthetic fixture is not a game
image, so this is startup, save/load, clean-exit/relaunch, and process-stability
evidence only; homebrew-game video, audio, live input, and longer session
acceptance remain open.

The earlier 3.2.2 tombstone remains in the isolated emulator's crash history;
the 3.2.3 session produced no new fatal signal. The isolated emulator was
stopped after validation.

## Remaining work

The APK is staged locally. It is not pushed or deployed. Public GitHub `main`
remains newer and divergent; any requested publication must be reconciled to
the current public source and pass the clean-snapshot security workflow.
