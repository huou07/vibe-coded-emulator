# Android host and the Android lane

Read when: you change the Android host, the committed Android asset mirror, the
Android build script, AVD/device testing, or the Android 3DS companion handoff.

Skip when: the change is desktop-only or Web-only, unless it edits `static/` —
that changes Android content too, through the mirror.

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| Android host (activities, overlay, controller bridge, generated models) | `GOOD` at source level | `native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/` |
| Committed asset mirror matching `static/` and `native-offline/web/` | `GOOD` | `tools/check-native-mirror.py`, the `native-mirror` section of the local gate (RG-156) |
| Hosted Android arm64 build lane | `GOOD` at the recorded revisions | `.github/workflows/native-build.yml` on `ubuntu-24.04`; build lane only, no device acceptance |
| Device / AVD acceptance (install, launch, play, save, touch, layout) | `UNVERIFIED` | No device run recorded for the current source |
| Android 3DS route (Azahar companion, read-only content URI) | `GOOD` at source level; runtime `UNVERIFIED` | `docs/native-offline.md`; no companion installed on any recorded run |
| Signing | debug/testing key only | A production APK/AAB needs the owner release key |

## Code map

- `native-offline/src-tauri/gen/android/` — host project, activities, overlay,
  controller service, generated settings/layout models.
- `native-offline/src-tauri/gen/android/app/src/main/assets/` — the committed
  mirror of `static/` and `native-offline/web/`. **No build step regenerates it.**
- `native-offline/scripts/build-android-staging.sh` — the staging builder the
  release train calls.
- `tools/check-native-mirror.py` — the mirror guard.
- `tools/android/` — build helper scripts (the operator README there is not
  published).

## Invariants

- The mirror matches its source. An edit to `static/` or `native-offline/web/`
  that is not re-copied into the Android assets fails the gate.
- The Android lane builds with the pinned NDK; the builder selects the host
  toolchain from `uname`, never a hardcoded macOS path.
- The 3DS companion is a separate installed app; AN3 hands it a read-only,
  per-ROM content URI and keeps the ROM in private storage.
- A build-lane success is not device acceptance. The lane's job says so.
- Release signing uses the owner identity; the debug key is staging only.

## Testing on this host (owner authorization, 2026-10-18)

The owner permits an Android AVD on this Debian host **dedicated to VCE**. Rules:

- Create and use a VCE-specific AVD (for example `vce-api35`). Do not attach to,
  reconfigure, snapshot or stop the AVD that OR is using.
- One resource-intensive job at a time; check RAM and disk before starting;
  serialize with the shared native lock; bounded timeout and full cleanup.
- Record AVD name, API level, image, the installed artifact hash, and the exact
  commands. An emulator run is device-class evidence, not packaging acceptance.

## How to verify

```sh
python3 tools/check-native-mirror.py
bash tools/verify-project.sh
# hosted lane (authoritative for the build):
#   .github/workflows/native-build.yml -> ubuntu-24.04, NDK pinned, arm64 APK
# local device lane (after creating the dedicated AVD):
#   install the staged APK, then run the import -> play -> save -> exit journey
```

## Open work

1. Create the dedicated VCE AVD and record one full install-and-play journey;
   every device row above is `UNVERIFIED` today.
2. Record the Android 3DS companion handoff with a lawful fixture, or record why
   it cannot run on the AVD image.
3. Keep the build lane green per revision; it is a build lane, not acceptance.

## Related

- [native-app](native-app.md), [ui-shell](ui-shell.md), [switch-eden](switch-eden.md),
  [phone-controller](phone-controller.md)
- `docs/android-regression.md`, `docs/UI_TESTING.md`
