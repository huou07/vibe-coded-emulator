# AN3 Arcade — P1.6 Grouped Player Settings UX

Date: 2026-08-20 (Asia/Ho_Chi_Minh)  
Commit: `1420ce0` (`feat(player): group player options safely`)

## Delivered behavior

- Online and offline player panels now share the same logical order: Performance, Speed, Controls (where a virtual pad exists), Game & saves, and Advanced.
- The More button opens the AN3 player panel for every emulated system. It closes the save-slot panel and moves keyboard focus to Close.
- Touch controls and the in-panel show/hide control are exposed only for GB, GBA, and NDS—the systems with AN3 virtual controls. Other systems no longer get an inert Touch toolbar button.
- Compact session speed remains limited to GBA/NDS, the cores validated for it. The panel does not expose an unvalidated speed control for other cores.
- Native EmulatorJS configuration remains in Advanced as **Open EmulatorJS menu**. It is not duplicated or replaced by AN3 controls.
- The PWA shell cache is `an3-arcade-pwa-v26` so installed clients refresh the revised player HTML and JavaScript.

## NDS native-menu protection

P1.6 keeps the P0 priority contract intact:

- A mutation/visibility observer marks the player stage `emulator-menu-open` when an EmulatorJS menu is actually visible.
- While that state is active, the virtual pad drops below the native menu and becomes pointer-inert.
- The AN3 options panel closes before opening the native menu; it also refuses to open over an already visible native menu.

The full stacking contract is documented in [`docs/player-layering.md`](../../docs/player-layering.md).

## Validation status

| Gate | Result |
| --- | --- |
| Online GBA panel grouping, focus, and in-panel pad visibility toggle | PASS — local browser smoke |
| Non-custom-core More behavior and absence of an inert Touch toolbar button | PASS — local browser smoke |
| Online/offline source parity and native-menu priority invariants | PASS — local combined suite |
| JavaScript/Python syntax and whitespace check | PASS |
| Full local suite | PASS — 15 tests |
| Staging NDS menu/pad interaction and real-device accessibility | Pending; staging activation blocked by unavailable non-interactive authentication |
| Production | Not touched |
