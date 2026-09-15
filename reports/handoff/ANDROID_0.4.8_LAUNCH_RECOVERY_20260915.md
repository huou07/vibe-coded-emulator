# Android 0.4.8 — native launch recovery, no UI locks

Status: COMPLETE. Staging and owner-authorized production serve asset
`add269259a01` and publish APK `0.4.8`.

## Owner report

NDS/3DS would not play on the owner's device. The production APK was still
0.4.7 and showed a dead-end "Native ROM is unavailable". The owner asked to
remove the UI locks rather than add another one.

## Root cause

`MainActivity.launchNative(romId, system)` resolved the ROM with
`nativeRomFile(romId, system)`, which only matched
`dataDir/an3-roms/<romId>.<ext>`. When a record's stored id no longer matched
its copied file (a WebView store restored without the private file, or a legacy
record), the lookup returned `null` and the launch failed with the dead-end
string. The library had no recovery path, so the card appeared permanently
locked. A browser-only 3DS lock added earlier the same day (RG-078) was also a
lock the owner rejected.

## Fix

- Removed the browser-only 3DS lock (RG-078 superseded). The play control is
  bound only to the installed Android capability declaration
  (`androidThreeDsUnavailable`) and the `html5` system.
- `MainActivity.nativeRomFile(romId, system, expectedSize)` tries the exact
  `<romId>.<ext>` file first, then a unique ROM of the same system whose byte
  length equals the recorded size. `launchNativeSized(romId, system, size)` is
  the new bridge method; the legacy 2-argument `launchNative` is kept for older
  library assets.
- `static/offline.js` passes `game.size` to the native launcher and, only when
  a ROM is genuinely absent, adds an enabled one-tap "Nhập lại ROM"
  (`data-repair-native`) that re-imports for the same record id and continues
  straight into native play. No supported system is ever disabled.
- Version bumped 0.4.7 -> 0.4.8 / versionCode 4008 (bug-fix patch bump per
  `AGENTS.md`). Native shell asset query strings bumped to `?v=0.4.8` so a
  WebView cannot serve a cached old `offline.js`.

## Artifact

| Platform | File | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Android arm64 | `vibecodedemulator-0.4.8-android-arm64-staging.apk` | 48,080,829 | `9fb8b5c4b1f1e81490f306e97b797ff56d219fb4510a5507767b7be1834a1de6` |

`versionName 0.4.8` / `versionCode 4008`, v2 signature PASS with the shared
Android Debug certificate `b48f3cdecc39349a75b66817aaad645a861d538be34835f290a2aa570c3beb4b`
(drop-in update). Other four installers are unchanged at 0.4.5.
`tools/verify-release-catalog.py` -> `RELEASE_CATALOG=PASS (5 installers)`;
catalog `source_fingerprint` `e25cc6c1a3d7bfe6941e5d7196b5868af320d76136c78c23006e384e02253ddd`.

## Verification

- Canonical `tools/release-train.sh --staging verify all`: 131 Python tests, web
  NDS touch, 11 renderer cases, `npm run check`, `git diff --check` -> PASS.
- AVD Android 15 with the exact 0.4.8 APK installed:
  - `launchNativeSized(<fresh uuid>, "nds", 268435456)` against the real 256 MB
    NDS file returned `""` and resumed `NativeGameActivity` with the `:game`
    process running; the same call through the legacy `launchNative` returned
    "Native ROM is unavailable", proving the recovery is the new code path.
  - The genuinely missing-file card showed the error note plus the enabled
    "Nhập lại ROM" button (no dead end).
  - The real NDS card launched through the normal UI click.
- Production HTTPS: APK returns 200 with exact size and, on full download,
  SHA-256 `9fb8b5c4…`; the old 0.4.7 URL returns 404; all four versioned
  `static/v` assets byte-parity with source; the deployed `offline.js` contains
  no `browserThreeDsUnavailable` and does contain `repairNativeRom`;
  `/games`, `/api/library-version` and `/game/*` remain 404.

## Deployment

- Staging `STAGING_RELEASE=PASS`, asset `add269259a01`, release
  `/opt/an3-arcade-staging/releases/20260915-200544-add269259a01`, rollback
  `/opt/an3-arcade-staging/releases/20260915-184351-0c307876a21f`.
- Production `PRODUCTION_RELEASE=PASS`, asset `add269259a01`, release
  `production-32090271423455aa`, application backup
  `/opt/an3-arcade-backups/20260915-200650`, SQLite backup
  `/srv/an3-arcade/backups/arcade-predeploy-20260915-200650.db` (integrity PASS).
- Host `/tmp` deploy files were removed after the release.

## Notes for the owner

- If a ROM card still fails to launch, the ROM file itself is no longer in the
  app's private storage (for example after a device-to-device restore that
  copied the library index but not the ROM files). The card now offers a
  one-tap "Nhập lại ROM" that fixes it in place without deleting the record.
  Re-importing the same file once restores that title.
- Browser 3DS remains an upstream Azahar WebAssembly limitation
  (`getVideoDimensions() = -1`, no audio context, black output). It is no longer
  blocked in the UI at the owner's direction; GBA/NDS play in the browser and
  all three systems play natively.
