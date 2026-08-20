# AN3 Arcade — P1.4 Safe Global Virtual-pad Scaling

Date: 2026-08-20 (Asia/Ho_Chi_Minh)  
Commit: `f3d6546` (`feat(player): add safe global pad scaling`)

## Delivered behavior

- The player stores pad settings locally with a versioned model: NDS uses `an3-pad-settings-v4:nds`; GB/GBA use their `v2` system key. Existing coordinate-layout keys are unchanged.
- The global control is deliberately conservative: 70–100%. It only lets players shrink the approved layout. A larger fixed cap would make the approved NDS face-button arrangement overlap on narrow phones.
- Effective control size is `globalScale × system base scale × individual multiplier`. NDS retains its approved base sizes (D-pad 1.4; Start/Select 0.7); other controls start at 1.0.
- The migration preserves an existing control’s effective visual and hit-target size. Legacy NDS v3 and GB/GBA v1 absolute `sizes` values are converted to relative multipliers before the new global scale is applied.
- Reset overall size restores only the global scale. It does not discard a layout, individual sizes, opacity, or NDS visibility preference.

## Safety contract

- A global increase is accepted only when the current real control hitboxes fit within the active pad area and do not overlap.
- Saved layout positions remain raw percentages. Rendering may clamp a position to the visible edge; that temporary clamp is never written back as a user layout change.
- When a viewport, orientation, fullscreen transition, or visibility change makes a stored layout unsafe, the pad is visually hidden and pointer-inert until the player reduces sizes, moves controls, or resets. This preserves the user’s stored preferences without allowing accidental overlapping input.

## Validation status

| Gate | Result |
| --- | --- |
| Source migration and P0 regression invariants | PASS in the local combined suite |
| JavaScript/Python syntax and whitespace check | PASS |
| Local full suite | PASS — 15 tests on the combined P1/P0 working state |
| Staging release | PASS — `20260820-211604-p1`, health asset `587464eca777` |
| Staging GBA/NDS startup and P0 source markers | PASS — both reached play state; canvas-only root touch and native-menu layer markers retained |
| Staging global-scale interaction | PASS — NDS 70% shrink and reset to 100% work in the live player |
| Physical-device validation | Pending Android and weak-owner-device checks |
| Production | Not touched |

P1.5 supplies the per-button geometry validation that backs the global-scale guard. Owner-device checks remain required before any P1 production approval.
