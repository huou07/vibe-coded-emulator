# Vibe Coded Emulator 2.1.0 — native Phone Controller + all-platform build (2026-09-17)

Workspace: `/Users/meomeo/Documents/edit an3tocom apps&web` (branch `apps-web`).
Staging: `http://192.168.1.8:8092`, asset `f2c429f14adc`, release
`/opt/an3-arcade-staging/releases/20260917-035348-f2c429f14adc`.
Production untouched. Google/Drive is explicitly out of scope for this session.

## What shipped

### Web/consumer layer (previous deploy, unchanged this round)
Controller/sync/multiplayer product surfaces, truthful controller state, pad
redesign, NDS/3DS touch, nearby-host discovery, Advanced Diagnostics.

### Native Phone Controller (this round)
- **Android Controller Mode lives in the library Settings** (`Settings → Phone
  Controller`), not only inside a running game. It uses the same app-scoped
  `An3ControllerHost`/`ControllerClient` as the in-game menu — one implementation.
- `NativeGameActivity` runs in an isolated `:game` process, so a new
  `ControllerHostService` (main process) bridges the host to the game:
  resolved buttons/axes/stylus cross via `Messenger`; the raw host token never
  crosses the boundary.
- The desktop Rust host now **acknowledges applied frames** and reports the
  running **system**, and only acknowledges while a native game is actually
  running (`native_input_ready`). Phone layout auto-selects GBA/NDS/3DS.
- Phone stylus is forwarded to the Android game process via the same pointer
  contract as the on-screen touch (`x*255`, `y*191`).
- Server `POST /api/controller/ack` accepts an optional bounded `system` and
  `GET /api/controller/link` returns it.

### Release engineering
- **Every packaged app moved to 2.1.0** (including the previously stale
  `src-tauri/Cargo.toml` and the native `web/index.html` cache-busting strings).
- Release catalog lists only 2.1.0 installers with fresh size + SHA-256 +
  sidecars; `tools/verify-release-catalog.py` → `RELEASE_CATALOG=PASS (5)`.

## Artifacts (2.1.0)

| Platform | Size | SHA-256 (short) | Built on |
| --- | --- | --- | --- |
| macOS DMG | 44,793,057 | `29a811a8…` | MacBook (this host) |
| Android APK | 49,668,840 | `ba4c650a…` | MacBook |
| Linux DEB | 45,564,448 | `7f98c149…` | Dell Debian |
| Linux Flatpak | 29,132,832 | `19da3fca…` | Dell Debian |
| Windows EXE | 47,001,772 | `60658f27…` | Windows 11 VM |

All five installer download URLs return **200** on staging.

## Verification actually run

- Python suite **283 tests, 0 failures**; node contract suites pass; `cargo test
  --lib controller_host` 9 passed + live probes; `cargo check` clean.
- **Android (AVD `codex-nds-api35`, arm64 API 35)** — full flow: Settings →
  Phone Controller → Start (session `QZHYTZ`, no ROM loaded) → phone paired →
  GBA fixture launched → layout auto-switched to **gba**, status **Connected**,
  four phone `Start` presses advanced the game to **NEW GAME / OPTION**; NDS
  fixture auto-selected **nds** with the touchscreen, and a stylus drag reached
  the game process. Leaving and re-entering a game kept the session.
- **macOS DMG** — mounts, `CFBundleShortVersionString=2.1.0`, ad-hoc codesign
  verifies, launches and stays alive. Rust host **live staging probe PASS**
  (session `GRFDHN`).
- **Linux DEB** — `dpkg-deb -x`, `ldd` clean, app launches and stays alive under
  Xvfb+openbox. Rust host **live staging probe PASS** (session `KYGD74`).
- **Linux Flatpak** — installs (`space.an3tocom.offline 2.1.0`) and runs under
  Xvfb.
- **Windows EXE** — silent install to `C:\AN3\app100` (exit 0), FileVersion/
  ProductVersion **2.1.0**, launches, 46.2 MB RSS, 6 WebView2 children. VM shut
  down gracefully; autostart remains disabled.
- Web regression (staging): `/controller`, `/sync`, `/multiplayer`,
  `/diagnostics` render with no overflow at 390/820/1440.

## UNVERIFIED (explicit)

- **Windows interactive gameplay/controller** — Session 0, no Vulkan ICD; only a
  launch smoke was possible.
- **Linux GUI click-through** — WebKitGTK paints nothing under Xvfb, so the
  library Controller Mode card could not be clicked headlessly; the host network
  path was verified with the live probe instead.
- **macOS GUI click-through / real phone** — no assistive-access permission for
  UI scripting; verified by launch + live host probe, not by clicking the card.
- **NDS/3DS stylus effect on a visibly reactive title** — the drag is delivered
  to the game process (frames change) but no touch-reactive fixture was used.
- **Sync client-store integration / true peer-to-peer LAN transfer** and the
  conflict UI population remain unimplemented (server-mediated LAN rendezvous
  only).

## Notes

- The Dell needed a rebuild of the Rust host for system reporting; a stray macOS
  `._*` AppleDouble file in a synced tarball broke the Windows Tauri build once
  and was removed (macOS metadata only).
- No secrets, tokens, device serials, or production paths are recorded here.
