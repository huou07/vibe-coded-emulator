# UI shell and UX across surfaces

Read when: you work on the visual system, navigation, layout clutter, control
sizing, accessibility, or the entry points of a new feature on any surface.

Skip when: the change is emulation, transport or storage with no visible effect.

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| Design tokens (violet dark-arcade palette) | `GOOD` | `docs/design-system.md`; computed token values asserted in the browser lane |
| Control-height contract, measured at 360 px | `GOOD` | RG-159: every compact control a thumb taps at phone width clears 42 px (primary minimum 44 px); the lane publishes `compactBelow42` in `work/ui-runtime/evidence.json` and that set is empty |
| Dense desktop controls (table row actions, admin range selector, small nav toggle) | 28 px floor, not machine-checked | They live on surfaces the 360 px lane never loads; the floor is documented, the real heights are not measured |
| 360 px no-overflow contract | `GOOD` | Browser lane |
| Rendered-tree names and landmarks | `GOOD` | `tests/test_rendered_ui_accessibility.py` |
| Web header destinations | `GOOD` | one destination per purpose; the mislabelled `Offline`/`Open app downloads` duplicate chip is gone (`docs/checkpoints/ui-ux-baseline.md`, change A1) |
| Linux native UI clarity | in progress | owner report 2026-10-18: "giao diện còn khá rối" — a requirement, not a verification. The device-to-device features left the Settings stack for their own `Devices` destination (change A2); the reviewed before/after captures are the remaining step |
| Android and macOS UI | owner-accepted as a baseline | Owner report 2026-10-18; no formal review recorded |
| Entry points for Switch, LAN Sync and Phone Controller in the native UI | `GOOD` at source level | one `Devices` destination with one card and one primary action per feature; the Switch card stays hidden until a companion reports `available: true` (`docs/checkpoints/ui-ux-baseline.md`, "The entry pattern") |

## Code map

| Surface | Files |
| --- | --- |
| Tokens and shared shell | `static/theme-violet.css`, `static/site.css` |
| Shared player UI (also used natively) | `static/player-ui.js`, `static/player.js` |
| Native shell chrome and library | `native-offline/web/` (`index.html`, `native.css`, `native-app.js`) |
| Android | the committed mirror under `native-offline/src-tauri/gen/android/app/src/main/assets/` |
| Contracts | `docs/design-system.md`, `docs/ui-page-contract.md`, `docs/player-layering.md` |

## Invariants

- `static/` is shared with the native player UI and mirrored to Android: a
  visual change must be safe on all three surfaces, or explicitly scoped.
- The page contract's DOM IDs stay stable; tests and the native bridge select on
  them.
- Layer order and input precedence follow `docs/player-layering.md`.
- The two-tier control-height contract (primary ≥42 px, compact ≥42 px at phone
  width for anything a thumb taps; 28 px floor for dense desktop-only controls)
  and the 360 px no-overflow assertions are not weakened to fit a new component.
- Status is shown honestly: no Switch, LAN or controller affordance appears on a
  surface that cannot complete the flow.

## Method for a UX pass

1. Pick one surface and one journey (for example "library → launch → controls" on
   Linux native). Do not restyle everything at once.
2. Capture the before state (screenshot or rendered tree). State the concrete
   friction: competing primary actions, unlabeled icons, inconsistent spacing,
   duplicated status text.
3. Change the smallest set of styles/components. Keep tokens and contracts.
4. Re-run the browser lane and the accessibility check; then review the after
   state on the real surface. Visual judgement is a human review, recorded as
   such — automation proves contract, not taste.
5. Record before/after evidence and the friction it removed. Do not claim "cleaner"
   without the reviewed captures.

## How to verify

```sh
AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium node --test tests/web-runtime.test.mjs
python3 -m unittest tests.test_rendered_ui_accessibility
python3 tools/inspect-ui.py      # structured inspection of a running surface
bash tools/verify-project.sh
```

## Open work

1. Review the before/after captures of the 2026-10-18 pass by eye and record the
   verdict; the tracker holds the backlog, the one change per journey and the
   measurements — [`checkpoints/ui-ux-baseline.md`](../checkpoints/ui-ux-baseline.md).
2. Split the remaining Settings stack (device facts, application settings,
   per-system settings, licenses) if the reviewed captures still read as
   cluttered, and generate the bundled-asset `?v=` cache-buster from the package
   version instead of a literal.
3. Entry points for the three features are designed once and reused across
   surfaces (the `Devices` destination); the Switch row must stay hidden on a
   host without a companion.
4. A second browser-lane pass over the admin and library update-notice surfaces so
   the dense desktop controls are measured rather than merely documented
   (`docs/QUALITY.md` gap 2).

## Related

- `docs/design-system.md`, `docs/ui-page-contract.md`, `docs/player-layering.md`,
  `docs/QUALITY.md`
- [native-app](native-app.md), [android](android.md), [web-player](web-player.md),
  [switch-eden](switch-eden.md), [lan-sync](lan-sync.md),
  [phone-controller](phone-controller.md)
