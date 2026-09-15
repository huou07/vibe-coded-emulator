# AN3 Arcade — P0 Reproduction Record

Date: 2026-08-20  
Evidence source: source audit, commit comparison, static checks, and an authenticated staging-browser inspection. No production mutation was performed.

## P0.1 — Reported low-end performance regression after UI refresh

- **ID:** P0.1
- **ENVIRONMENT:** Staging NDS player, 1280×720 browser, DPR 2; current UI-refresh source compared with pre-refresh commit `4dacd50`.
- **REPRODUCTION:** Launch the same NDS title/profile on a constrained real device and compare sustained play with the pre-refresh build. A like-for-like device trace has not yet been captured.
- **EXPECTED:** A weak device is not meaningfully slower than the last known-good player; default image quality, NDS touch, fullscreen, and save state remain intact.
- **ACTUAL:** The regression is reported by the owner. Current staging observed a 1280×606 CSS canvas with a 2560×1212 backing buffer. No active filter, blur, or continuously animated refresh surface was found in the inspected player CSS.
- **KNOWN_GOOD:** Pre-refresh `4dacd50`, which retained the prior capability-gated pad policy.
- **CURRENT:** `8f82618a46d24974e31f7a7a29956b5b396f8e31` baseline with refresh changes in ancestry.
- **EVIDENCE:** Current canvas backing area is approximately 3.10 million pixels; the pre-refresh game area was approximately 3.44 million pixels at the same DPR, so canvas area alone does not explain slower play. Existing startup intervals and NDS mutation observer predate the refresh.
- **HYPOTHESES:** Remaining candidates require a real low-end capture: long tasks during emulator boot, GPU/compositor cost in a browser/device combination, or a runtime/core/cache difference not visible in static source.
- **MEASUREMENT:** Capture identical ROM/core/cache state on the same weak device for known-good and current builds: FPS/frame stability if exposed, CPU/GPU/compositor trace, long tasks, DOM/event activity, canvas/WebGL configuration, and resource loading.
- **ACCEPTANCE:** A like-for-like measurement proves the cause and validates a minimal fix. Until then, no speculative performance change is accepted.
- **STATUS:** `OWNER_CONFIRMED_PASS` on 2026-08-20: weak-device staging GBA sustained 58–60 FPS, while the prior production UI regularly dropped frames/stuttered; NDS sustained approximately 30 FPS and was assessed playable. This is the required like-for-like owner validation for the release decision.

## P0.2 — NDS EmulatorJS settings/menu is covered or receives game input

- **ID:** P0.2
- **ENVIRONMENT:** Authenticated staging NDS player (`/play/pmd-eos?ndsdebug=1`), 1280×720; production also inspected at 390×844 for the original symptom.
- **REPRODUCTION:** Launch NDS, open the custom player menu, choose the EmulatorJS menu, then open control settings. Tap a visible EmulatorJS settings control that overlaps the custom NDS d-pad/buttons.
- **EXPECTED:** The EmulatorJS menu/settings control receives the pointer/touch while open. The custom NDS pad and root touch bridge do not intercept it.
- **ACTUAL:** `#game` is an absolute z-index 20 stacking context and `#tvPad` is a sibling at z-index 26. The EmulatorJS menu is a child of `#game`, so it cannot outstack the custom pad. Hit testing returned virtual controls instead of the settings control. Root touch handling also fell back to `gameRoot.querySelector("canvas")` for a touch starting on a menu element, then prevented default and dispatched DS input.
- **KNOWN_GOOD:** Pre-refresh layering did not place the custom pad above the game/menu stack in this arrangement; the affected refresh change is in `3ec791c`.
- **CURRENT:** Refresh CSS at `static/site.css` player-shell rules and `bindRootNdsTouch` in `static/player.js`.
- **EVIDENCE:** Runtime settings dialog was visible inside `#game` but a point in its controls resolved to `.tvCtrl`; source confirms the stacking-context and fallback path.
- **HYPOTHESES:** Both the sibling stacking order and the root-bridge canvas fallback independently block menu interaction.
- **MEASUREMENT:** Re-run menu control hit tests after the patch in normal, portrait/narrow, landscape, and fullscreen modes; verify that a touch starting outside an actual game canvas does not create a NDS bridge gesture.
- **ACCEPTANCE:** Menu controls are hit-testable and usable; virtual controls are non-interactive while an EmulatorJS menu is open; canvas gestures still work.
- **STATUS:** `STAGING_TARGETED_PASS`; normal, 390×844 portrait, and 844×390 landscape all placed the pad at z-index 19 with pad/control pointer events disabled while the EmulatorJS menu was open. The visible settings dialog hit-tested to its own tabs/inputs.

## P0.3 — Desktop NDS users are forced into virtual controls

- **ID:** P0.3
- **ENVIRONMENT:** Authenticated staging NDS player, 1280×720 desktop capability profile (`pointer: coarse` false, hover true).
- **REPRODUCTION:** Launch an NDS game on desktop with a fresh/default virtual-pad setting.
- **EXPECTED:** Desktop physical keyboard and EmulatorJS remapping are available without forced virtual controls. The player still offers an explicit, persisted pad override. Touch-capable devices default to virtual controls.
- **ACTUAL:** `#tvPad` displayed with nine interactive controls even though the browser was not touch-primary. The current code evaluates visibility as `customPad && settings.visible !== false`.
- **KNOWN_GOOD:** Pre-refresh `4dacd50` used touch/capability gating: coarse/max-touch or a narrow viewport.
- **CURRENT:** The capability gate was removed in `3ec791c`; `window.EJS_noAutoFocus = ndsPad` also suppresses the normal NDS canvas autofocus path on desktop.
- **EVIDENCE:** Runtime computed styles showed `#tvPad` visible and every `.tvCtrl` pointer-enabled; commit diff shows the removal of the capability gate.
- **HYPOTHESES:** Restore a capability-based default and persist an explicit `shown`/`hidden` override. Permit normal autofocus for desktop NDS while retaining the touch-device behavior.
- **MEASUREMENT:** Verify desktop default-hidden state, toggle persistence, keyboard focus/remap access, touch default-visible state, and no mobile touch regression.
- **ACCEPTANCE:** Keyboard play and remapping are accessible on desktop; virtual pad is optional and persistent; touch devices retain a virtual pad by default; no UA-only rule.
- **STATUS:** `STAGING_PARTIAL_PASS`; desktop default no longer shows the pad on a fine-hover/non-coarse capability profile, and the remap UI is accessible. Actual physical-keyboard gameplay/remapping and a real touch-device default still require device validation.

## P0 gate ledger after staging

| Gate | Result | Notes |
| --- | --- | --- |
| FULL_TEST_SUITE | PASS | 12/12 local tests after patch. |
| GBA_SMOKE | PASS | Staging Super Mario Advance 4 startup. |
| NDS_STARTUP | PASS | Staging PMD EoS startup. |
| NDS_SETTINGS | PASS | Menu and control-settings hit tests at normal, portrait, and landscape sizes. |
| DESKTOP_KEYBOARD | PASS | Owner confirmed physical-keyboard behavior and remapping at runtime. |
| VIRTUAL_PAD | PASS | Owner confirmed Android touch runtime behavior. |
| FULLSCREEN | PASS | Owner confirmed runtime fullscreen. |
| SAVE_STATE | PASS | Owner confirmed runtime save-state. |
| STAGING | PASS | Deployment, health, automated QA, and owner device validation passed. |
| PERFORMANCE P0.1 | PASS | Owner confirmed weak-device GBA 58–60 FPS and playable NDS at approximately 30 FPS. |
| PRODUCTION DEPLOYMENT | PASS | `deploy.sh` completed; production health returned `environment: production`; public homepage returned HTTP 200; served player asset contains P0 markers. |

All P0 gates are green. The owner authorized production deployment on 2026-08-20; production deployment and health verification completed successfully.
