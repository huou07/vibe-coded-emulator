# 1.3.0 runtime verification — Android + Linux (2026-09-16)

Ordered-plan step 1. Evidence only for what was actually executed. Nothing here
is claimed beyond the runs below.

## Android 1.3.0 — VERIFIED (runtime)

- Artifact: `native-offline/releases/vibecodedemulator-1.3.0-android-arm64-staging.apk`
  (`versionCodeName=1.3.0`, `space.an3tocom.offline`), installed with
  `adb install -r -d` on the running `codex-nds-api35` AVD (arm64, API 35,
  720x1280 @ 240dpi). Install: Success.
- Game: `NativeGameActivity`, system `nds`, test ROM id
  `58a4d7a3-4e63-4cae-a430-f0972275c52b` (melonDS DS). Ran at
  **`FPS core=59 present=59`**.
- **Save 10-slot dialog — VERIFIED.** Toolbar `Save` → menu with
  `Quick Save… / Quick Load… / Auto Save now / Load Auto Save`; `Quick Save…` →
  list of **Slot 1 … Slot 10**. Selecting Slot 1 wrote
  `files/native-states-v1/nds/<romId>/native-libretro/states/<romId>-*.slot1.state`
  (19,498,039 B, mtime 2026-09-16 13:50).
- **Layout chooser — VERIFIED.** Toolbar `Layout` → radio list with all **12**
  melonDS layouts (Left/Right … Flipped large screen bottom), current selection
  `Hybrid (focus top)`; CANCEL closed it.
- **FPS badge pointer-inert — runtime attributes VERIFIED.** `uiautomator dump`
  shows the FPS node (`android.widget.TextView`, `FPS core=59 present=59`) with
  `clickable="false" focusable="false" long-clickable="false"`, bounds
  `[187,195][532,231]`. The badge stayed visible and updated while the game ran.
  The full behavioural case (a control *directly beneath* the badge being
  pressed through it) is **UNVERIFIED** — no control overlaps the badge in the
  tested layouts.
- **Menu — VERIFIED (open/close).** Toolbar `Menu` opened the nine-tab menu
  (General/Graphics/Audio/Keyboard/Controller/Emulation/Save States/…,
  title `VibeCodedEmulator · melonDS DS native`); Back closed it; game continued
  at 59 fps. The menu-first pointer-precedence guard is source-verified
  (`NativeGameActivity.touch` + `surface.setOnTouchListener` both bail on
  `overlay.isMenuOpen()`); the interactive held-pointer case is **UNVERIFIED**
  because an Android modal Dialog consumes off-panel touches.
- **NDS touch reaches the core — VERIFIED.** In the hybrid layout the bottom
  screen showed the name-entry keyboard; tapping the `a` key produced `a` in the
  name field (one character registered).

Evidence screenshots (absolute paths):
`/Users/meomeo/Documents/edit an3tocom apps&web/reports/android-regression/1.3.0/`
`01-save-menu.png`, `02-quicksave-slots.png`, `03-quicksave-slot1-written.png`,
`04-nds-touch-keyboard.png`, `05-menu-open.png`, `06-menu-closed-fps59.png`,
`07-layout-chooser.png`.

## Linux 1.3.0 — PARTIAL (launch smoke + binary evidence)

- Artifact: `vibecodedemulator-1.3.0-linux-amd64.deb` on `an3-dell`
  (`/home/huou07/an3-verify/native-offline/releases/`), extracted with
  `dpkg-deb -x`.
- `an3-native-player --help` parses (GBA/NDS/3DS, renderer, layout).
- Runtime ran for the full `timeout 25s` under
  `xvfb-run -a env SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1
  AN3_OFFLINE_LIBDIR=<extracted runtime dir>` with the legal GBA fixture
  (`~/an3-verify/legal-gba.gba`) → **EXIT=124** (still running; launch proved,
  not gameplay). One benign `dbind-WARNING` (no AT-SPI bus).
- Binary contains the 1.3.0 UI: `show_layout_menu` (12- and 4-layout
  `native_layouts` arrays), `Quick Save`, `Quick Load`, `Auto Save now`,
  `Load Auto Save`, `Screen layout changed to`, the 12-layout labels.
- GTK menu clicks are **UNVERIFIED** (not automated headlessly).

## Still open

- Windows 1.3.0 runtime (never run interactively) — ordered-plan step 5.
- FPS badge behavioural overlap case and menu-first held-pointer case — need a
  scripted pointer sequence; not caused by 1.3.0.
