---
name: an3-player-regression
description: Use before and after editing the AN3/Vibe Coded Emulator web player surface (static/player.js, static/nds-touch.js, static/site.css, static/renderer-worker.js, static/player-runtime.js, or shared player-model files) to run the required regression guards and record honest GOOD/UNVERIFIED evidence. Triggers on "player regression", "guard tests", "touch behavior", "menu precedence", "virtual pad", "before player edit".
---

# AN3 player regression guards

Any edit to `static/player.js`, `static/nds-touch.js`, `static/site.css`, or
`static/renderer-worker.js` that affects player canvas/input/layers must run the
matching guards **before and after** the edit, in the repo root.

## Run these

```bash
cd "/Users/meomeo/Documents/edit an3tocom apps&web"

# Python guards
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest \
  tests.test_regression_invariants \
  tests.test_web_nds_touch_behavior \
  tests.test_native_regression_guards \
  tests.test_shared_player_ui

# Node behavior suites
node tests/web_nds_touch_behavior.test.js
node tests/web_renderer_behavior.test.js

# Syntax + full suite
node --check static/player.js
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests
```

## Protected behaviors these cover

- Web NDS gameplay touch resolves the EmulatorJS **source** canvas; presentation
  and renderer canvases are output-only and pointer-inert.
- Top/Bottom and Left/Right, scaled and letterboxed; mapPoint for each layout.
- Pointer capture, release and cancel; exactly one release per press; a press
  outside the touch screen is rejected.
- Menu precedence: an open menu owns input (never leaks into emulation); AN3
  settings/toolbar/virtual-pad controls own their touches.
- Virtual-pad precedence and Settings clickability.
- Fullscreen / resize must not change touch ownership.
- The player keeps renderer presentation non-interactive.

## Before editing, read

- `docs/REGRESSION_GUARDS.md` and `reports/handoff/SYSTEM_INSPECTION_HANDOFF.md`.
- `docs/player-layering.md` for any player-shell change.

## Honest labeling

- Static/source checks and a green test suite are **not** interactive
  acceptance.
- If a browser or packaged runtime was not exercised, record `UNVERIFIED`, not
  `GOOD`.
- Player input, canvas, overlay, and virtual-pad geometry changes are separate
  tasks with their own guards.
- Add every newly fixed regression to `docs/REGRESSION_GUARDS.md` with its
  validation before finishing.
