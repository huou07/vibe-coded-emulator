# Player Layering Contract

The player’s interaction order is intentional and must be preserved when changing player UI.

1. Emulator canvas / game content is the base layer.
2. AN3 virtual controls sit above the game (`#tvPad`, normally z-index 26) and receive touch input only when shown and safe.
3. Transient player HUD sits above controls: the status rail is z-index 30 and toolbar actions are z-index 40.
4. AN3 panels and modal-like surfaces sit above the HUD: player options are z-index 60 and save-slot options are z-index 65.

## Input precedence

The visual order also defines the input order and must stay stable:

1. Native EmulatorJS menus/settings and dialogs receive their own taps before
   any stage interaction. The root NDS bridge rejects any event whose target
   or composed path is inside that protected UI; it never falls back to the
   source canvas for a menu-origin event.
2. AN3 toolbar, options/save panels, and modal controls receive their own taps
   before any stage interaction.
3. AN3 virtual controls receive a pointer only on an actual control. The
   persistent `Touch` button only changes their visibility; it must not change
   keyboard or touchscreen mapping.
4. The NDS/3DS canvas receives all remaining touch input. In particular, the
   virtual-pad root is pointer-transparent outside its controls except while
   the player is intentionally arranging controls.
5. Physical keyboard events remain owned by EmulatorJS. AN3 must never trap
   normal game keyboard input.

Virtual-control editing is a two-step, persistent flow: open player options,
choose **Kéo thả / Move**, drag controls, then reopen player options and
choose **Xong / Done**. Positions are stored per system and orientation as
soon as a drag ends and are written again on Done; a cancelled pointer capture
must not discard the final layout.

For NDS, the initial layout is selected before core boot: portrait uses
Top/Bottom and a wide display uses the melonDS Left/Right layout. 3DS follows
the same rule through Azahar libretro's `citra_layout_option` (`default` or
`side_by_side`), so its own framebuffer remains authoritative for touchscreen
mapping. Rotation after a game has started shows a restart notice rather than
silently changing a core geometry mid-frame.

## TV console mode

The browser may monitor whether a compatible remote receiver is available, but
it never enumerates or auto-selects televisions: receiver selection remains a
browser permission prompt. After the player connects to the user-selected TV,
the local game surface is transparent but continues rendering into the remote
stream. The toolbar, physical keyboard, virtual controls, and remaining
touchscreen hit-area stay local, turning the computer or phone into the
console controller. The temporary TV-mode visibility of virtual controls does
not overwrite the saved `Touch` preference; using Touch during TV mode resumes
the normal persistent setting.

## EmulatorJS-menu exception

An open native EmulatorJS menu takes interaction priority over AN3 virtual controls. `static/player.js` detects its visible menu nodes and toggles `emulator-menu-open` on the player stage. In that state `#tvPad.show` is moved to z-index 19 and its pointer events are disabled. This prevents a large NDS control from blocking a native menu item.

The same state also makes the gameplay bridge inert underneath the menu. The
source canvas may remain structurally present and pointer-enabled for normal
gameplay, but a pointer/touch event whose target or `composedPath()` contains
`.ejs_menu_bar`, `.ejs_context_menu`, `.ejs_popup_body`, an AN3 panel, a
toolbar action, or a virtual control is returned to the UI owner without
`preventDefault()`, source-canvas resolution, or synthetic NDS dispatch. If a
menu opens during an active NDS gesture, the bridge sends one release and
clears pointer/touch tracking before the menu takes over.

The AN3 player-options panel must close before opening the native menu and must not open over an active native menu. Do not add sticky player UI above the canvas without checking this state.

## Validation when changing layers

- Test GBA and NDS startup, fullscreen, save state, keyboard input, virtual-pad input, and NDS touchscreen input.
- Open the EmulatorJS menu with the pad visible, resized, and in fullscreen. Native menu controls must remain clickable.
- Confirm app panels retain keyboard focus and do not cover an already open native menu.
