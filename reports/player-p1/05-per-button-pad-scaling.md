# AN3 Arcade — P1.5 Safe Individual Virtual-pad Scaling

Date: 2026-08-20 (Asia/Ho_Chi_Minh)  
Commits: `bd96836` (`feat(player): add safe individual pad sizing`), `803a6ec` (`fix(player): guard pad scale transitions`)

## Delivered behavior

- Individual sizing is an advanced, relative 50–200% control. 100% means the selected control’s approved default before the global scale is applied.
- It reuses P1.4’s `buttonScales` schema; no second migration or new layout key is introduced.
- Candidate bounds use the actual `.tvCtrl` hitbox, not just its child artwork. Before an increase is saved, the player predicts the control rectangle with the same edge clamp used for rendering and rejects off-pad or overlapping controls.
- Checks are event-driven: target change, slider input, reset, drag completion, resize, orientation, fullscreen, and a pad visibility change. There is no continuous geometry polling.
- The UI separates reset actions: reset selected size, reset all individual sizes, reset current-orientation layout, and reset all virtual controls. The smaller reset scopes do not change global scale, opacity, visibility, or other layout data.

## Edge-case handling

- A hidden pad cannot be measured safely, so the player must show controls before increasing an individual size. Reductions and resets remain available.
- An existing unsafe layout is preserved rather than silently moved. The player can reduce, move, or reset it; it cannot make the collision worse.
- The transition guard covers global-size increases, layout reset, resize, orientation, fullscreen, and pad reveal. If an already saved configuration is unsafe in a new viewport, controls are hidden and pointer-inert until made safe.

## Validation status

| Gate | Result |
| --- | --- |
| Geometry/source regression invariants | PASS in the local combined suite |
| JavaScript/Python syntax and whitespace check | PASS |
| Local full suite | PASS — 15 tests on the combined P1/P0 working state |
| 360×800, 390×844, 807×985, and landscape physical-device geometry checks | Pending staging/owner validation |
| Staging activation | BLOCKED by unavailable non-interactive staging authentication; no remote release was activated |
| Production | Not touched |
