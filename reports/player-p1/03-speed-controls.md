# AN3 Arcade — P1.3 Session Speed Controls

Date: 2026-08-20 (Asia/Ho_Chi_Minh)
Commits: `2db68e5` (`feat(player): add session speed controls`), `49e4429` (`fix(pwa): refresh player speed assets`)
Staging release: `20260820-145923` at `http://192.168.1.11:8092`

## Delivered behavior

- GBA and NDS player options now have a compact, session-only speed control: 0.5x, 1x, 1.5x, and 2x. It starts at 1x and does not create or update AN3 browser persistence.
- Controls become available only after `onGameStart` (or the non-NDS game-manager readiness path) and only when all four verified EmulatorJS APIs are present: fast-forward ratio/toggle and slow-motion ratio/toggle.
- Returning to 1x turns both fast-forward and slow-motion off. A runtime error safely resets the session control to 1x and displays an existing player notice.
- The existing EmulatorJS fast-forward and slow-motion settings are hidden pre-boot so the compact player control is the authoritative surface. EmulatorJS still shows its separate `Speed Options` category for Rewind; its Fast Forward and Slow Motion controls are absent.
- Online and offline GBA/NDS player markup match. The PWA shell cache is `an3-arcade-pwa-v22` so installed clients refresh the new player assets.

## Staging result

| Check | Result |
| --- | --- |
| Staging health after release restart | PASS (`environment: staging`, asset version `baae4642a937`) |
| NDS startup (`pmd-eos`) | PASS — reached in-game state |
| NDS compact speed sequence | PASS — 1x -> 1.5x -> 2x -> 1.5x -> 1x -> 0.5x; game remained in-game, then reset to 1x |
| NDS native settings | PASS — Fast Forward and Slow Motion controls absent; Rewind remains in its own native category |
| GBA startup (`super-mario-advance-4-super-mario-bros-3-usa`) | PASS — reached in-game state |
| GBA compact speed sequence | PASS — 1x -> 1.5x -> 1x; game remained in-game |
| Browser console errors | PASS — none observed for either core |

## Scope and remaining validation

- This validates the browser staging path only. It does not replace P1.7 owner-device checks for physical keyboard, touch, fullscreen, save/load, Android browsers, or weak hardware.
- No production server or production release was changed.
