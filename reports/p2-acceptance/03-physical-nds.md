# P2.15 physical NDS acceptance

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Device and scope

The test used a real Android touchscreen running Chrome Android against staging only (`http://192.168.1.8:8092`). The phone was USB-debugging connected. Android system touch injection was used for repeatable taps, holds, drags and screenshots; it exercises the real Chrome/mobile event path, but it is not a substitute for an independently observed human-finger stylus trace.

No production service, database, account, session, ROM, fixture or asset was accessed or changed.

## First physical Chrome session

The authorized title **Pokémon Mystery Dungeon: Explorers of Sky** was opened from `/game/pokemon-mystery-dungeon-explorers-of-sky` and started in Chrome Android.

- The player auto-started without a manual-start control, reached an active game screen, and reported approximately 42–60 FPS.
- The player exposed the NDS/melonDS path and status `Đang chơi` (playing).
- Direct screen gestures were sent to the game area: tap, hold/release, horizontal drag, vertical drag, diagonal drag, centre, and all four corner areas. The game did not crash or leave a stuck application overlay. A transient black frame settled to the game menu. The game did not expose a reliable visible stylus marker, so exact stylus-coordinate fidelity is not claimed from this evidence alone.
- The custom virtual pad was shown and hidden. A held B press visibly entered its pressed state, showing that Chrome Android delivered the touch to the pad layer. This was not treated as sufficient proof of every in-game NDS button mapping.
- The player options panel opened and scrolled correctly. The native EmulatorJS menu then opened with pause, save/load, controls, cache, fullscreen and settings entries, and closed without changing emulator settings.
- Slot 1 was saved locally on this Android device, acquired a timestamp and enabled Load. Loading it produced the player notice `Đã nạp slot 1` (Slot 1 loaded). This confirms a device-local save/load round trip; it did not write a server-side save.
- Element fullscreen entered successfully in Chrome Android (browser chrome and status bar were hidden) and exited back to the normal Chrome view. The phone was temporarily rotated to landscape and then restored to its original locked-portrait settings (`accelerometer_rotation=0`, `user_rotation=0`). The active game continued at roughly 52–57 FPS through the orientation and fullscreen transitions.

## Cold-start diagnosis and staging correction

The original fresh Chrome and Firefox observations showed `Đang chơi` and 60 FPS with a white canvas. Read-only response inspection established a concrete delivery defect: the player URL ended in `.nds` while its response was an inline ZIP. EmulatorJS chooses whether to decompress from the URL filename, so the ZIP could be supplied to melonDS as though it were a raw NDS file.

The staging-only correction retains the original ZIP and Range delivery but keeps the `.zip` suffix in the player URL. It was released as `/opt/an3-arcade-staging/releases/20260823-111241-p215-nds-url` after a successful staging health check. No staging database, ROM, user, session or fixture was copied or changed, and production was not accessed for the release.

## Final Chrome Android acceptance

A fresh Chrome Android navigation using a distinct query URL initially showed the transitional white-canvas state, then completed startup and rendered the game. The player was left on the recommended **Cân bằng** profile; the low/legacy option was selected only as a diagnostic and reset before the final interaction pass.

- The visible game ran at approximately 52–56 FPS, reached the title/menu flow and remained live after direct tap, hold/release, horizontal, vertical and diagonal gestures plus centre/corner coverage. It did not crash or leave a stuck overlay. As with the first run, this title has no visible stylus marker, so the evidence covers the Android touch event path rather than a separate human-finger coordinate trace.
- Player options and the device-local slot panel accepted touch. Slot 2 saved at 11:19 and then showed the in-app notice `Đã nạp slot 2` after Load. This is a local-device state only, not a server-side write.
- The virtual controls remained visible over the correct NDS layout and the game continued to render after the interaction sequence.
- Fullscreen entered, retained the rendered game, toolbar and virtual controls, then exited back to normal Chrome layout with the game still live. The original Chrome session had already covered portrait-to-landscape-to-portrait restoration and the native EmulatorJS menu.

## Firefox Android status

Firefox Android was practical to test and is explicitly recorded rather than hidden. On the same device, a fresh post-correction player remained a white canvas at 60 FPS after an extended wait. Its **Cân bằng** and device-local low/legacy renderer profiles both reproduced the result. The profile was reset and verified as recommended/balanced after the test.

This is a browser-specific compatibility limitation. The required primary real-device Chrome Android acceptance passes; Firefox does not currently provide a usable NDS session on this device. It is not a reason to claim Firefox support.

## Result

`PHYSICAL_NDS=PASS` (Chrome Android primary acceptance)

`FIREFOX_ANDROID_NDS=KNOWN_LIMITATION` (white canvas at 60 FPS with default and legacy renderer; profile restored)
