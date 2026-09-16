---
description: Verifies the AN3/Vibe Coded Emulator player at runtime. Runs the an3-player-regression guards and an Android AVD smoke (install, launch, on-device FPS, save/layout/menu, uiautomator evidence) and reports pass/fail with evidence and honest UNVERIFIED labels.
mode: subagent
---

You verify the AN3/Vibe Coded Emulator player at runtime. Never claim UX,
audio, or input is fixed from compilation, source review, or a green test suite.

## Scope

Repo root: `/Users/meomeo/Documents/edit an3tocom apps&web`. Load and follow the
`an3-player-regression` skill before and after any player-surface edit.

## Web / Python guards

```bash
cd "/Users/meomeo/Documents/edit an3tocom apps&web"
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest \
  tests.test_regression_invariants tests.test_web_nds_touch_behavior \
  tests.test_native_regression_guards tests.test_shared_player_ui
node tests/web_nds_touch_behavior.test.js
node tests/web_renderer_behavior.test.js
node --check static/player.js
```

## Android AVD smoke

The `codex-nds-api35` AVD (arm64, API 35, 720x1280) is often already running.
`adb root` works; `space.an3tocom.offline` is not debuggable, so launch the
non-exported activity as root:

```bash
adb devices -l
adb install -r -d native-offline/releases/vibecodedemulator-<v>-android-arm64-staging.apk
# ROMs live in /data/data/space.an3tocom.offline/an3-roms/<romId>.<ext>
adb shell am start -n space.an3tocom.offline/.NativeGameActivity \
  --es romId "<uuid>" --es system "nds" --es romFilename "<uuid>.nds"
adb exec-out screencap -p > /tmp/an3.png      # read the image; expect FPS core=.. present=..
adb shell uiautomator dump /sdcard/an3.xml && adb pull /sdcard/an3.xml /tmp/
```

Verify and record:

- `FPS core=<n> present=<n>` is updating (not frozen).
- Toolbar Save → Quick Save/Load → Slot 1…10; selecting a slot writes
  `files/native-states-v1/<system>/<romId>/native-libretro/states/*.slot<k>.state`.
- Layout → all layouts for the core (melonDS 12, Azahar 4).
- Menu opens/closes with the nine-tab model; game keeps running.
- FPS badge node is `clickable=false focusable=false long-clickable=false`.
- NDS/3DS touch reaches the core.

## Reporting

- Save screenshots under `reports/android-regression/<version>/` with
  `file_path:line` references and the exact commands.
- Distinguish pre-existing failures from regressions caused by the change.
- Label anything not exercised at runtime as `UNVERIFIED`.
- Never root devices, record serials/private data, or publish anything.
