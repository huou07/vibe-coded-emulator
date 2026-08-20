# Player Layering Contract

The player’s interaction order is intentional and must be preserved when changing player UI.

1. Emulator canvas / game content is the base layer.
2. AN3 virtual controls sit above the game (`#tvPad`, normally z-index 26) and receive touch input only when shown and safe.
3. Transient player HUD sits above controls: the status rail is z-index 30 and toolbar actions are z-index 40.
4. AN3 panels and modal-like surfaces sit above the HUD: player options are z-index 60 and save-slot options are z-index 65.

## EmulatorJS-menu exception

An open native EmulatorJS menu takes interaction priority over AN3 virtual controls. `static/player.js` detects its visible menu nodes and toggles `emulator-menu-open` on the player stage. In that state `#tvPad.show` is moved to z-index 19 and its pointer events are disabled. This prevents a large NDS control from blocking a native menu item.

The AN3 player-options panel must close before opening the native menu and must not open over an active native menu. Do not add sticky player UI above the canvas without checking this state.

## Validation when changing layers

- Test GBA and NDS startup, fullscreen, save state, keyboard input, virtual-pad input, and NDS touchscreen input.
- Open the EmulatorJS menu with the pad visible, resized, and in fullscreen. Native menu controls must remain clickable.
- Confirm app panels retain keyboard focus and do not cover an already open native menu.
