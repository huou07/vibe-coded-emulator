# AN3 Arcade — Current State (P0 recovery baseline)

Date: 2026-08-20 (Asia/Ho_Chi_Minh)  
Scope: P0 player regressions only. Production deployment is explicitly out of scope for this recovery pass.

## Source of truth and working tree

- Active repository: `an3-arcade` on branch `ui/production-ux-refresh`.
- Baseline HEAD: `8f82618a46d24974e31f7a7a29956b5b396f8e31`.
- The worktree was already dirty before this P0 work: `app.py`, `static/site.css`, `static/site.js`, and `tests/test_integration.py`. Those changes are preserved; they implement a separate enrichment-review flow and are not discarded or reset.
- `git diff --check` passed at baseline.
- The legacy repository named by `AGENTS.md` was not modified.

## Runtime baseline

- Production and staging services were reachable and active during the read-only health check.
- Staging target is the private LAN endpoint documented by the handoff. No production action is performed from this worktree.
- EmulatorJS remains client-side. NDS remains `melonds`, auto-start remains enabled, the NDS touch bridge remains present, IndexedDB core persistence and offline/NDS ZIP support remain in scope as invariants.

## Baseline validation

| Check | Result | Evidence |
| --- | --- | --- |
| Python integration/unit suite | PASS, 12/12 | Run with the required local listener permission after the sandbox prevented loopback binding. |
| `python3 -m py_compile app.py` | PASS | Baseline syntax check. |
| `node --check` for player/site/offline/service-worker | PASS | Baseline syntax check. |
| `bash -n` deploy scripts | PASS | Baseline syntax check. |
| `git diff --check` | PASS | No whitespace error at baseline. |

## P0 evidence summary before implementation

| ID | Finding | Evidence |
| --- | --- | --- |
| P0.1 | Performance regression is reported but the root cause is not yet proven. | Current staging NDS canvas was 1280×606 CSS / 2560×1212 backing pixels at DPR 2; no active blur/filter/continuous animation was found in the refresh CSS. The pre-refresh comparator had a larger canvas area, so a blanket resolution reduction would not be an evidence-based fix. |
| P0.2 | EmulatorJS controls menu is behind the custom NDS pad and root touch bridge can capture menu touches. | `#game` is a z-index 20 stacking context while `#tvPad` is z-index 26. The EmulatorJS menu is a child of `#game`; browser hit testing on its settings dialog returned virtual-pad controls. Root touch lookup also fell back to the first game canvas for a touch starting on a menu control. |
| P0.3 | Desktop NDS exposes the virtual pad by default. | At 1280×720, coarse pointer was false and hover was true, but `#tvPad` was visible with nine interactive controls. The automatic touch-capability gate in the pre-refresh code was removed by refresh commit `3ec791c`. |

## Scope boundaries

This pass does not implement adaptive performance profiles, speed controls, admin layout changes, ads, points, multiplayer, server migration, or 3DS/Switch feasibility. P0.1 remains in measurement until a like-for-like low-end comparison identifies an expensive regression and validates a safe remedy.

## P0 implementation and staging result

The targeted P0 patch is in `static/player.js` and `static/site.css`:

- The root NDS bridge now begins only when the initial event hit is an actual `#game canvas`; it retains that canvas for the rest of the gesture instead of falling back to the first canvas for a menu touch.
- NDS pad visibility now uses a touch-first capability policy (`pointer: coarse`, or touch without hover), plus a persisted `shown` / `hidden` user override. Existing NDS sizing and opacity settings migrate to a v3 settings record; a legacy `visible: false` is retained as an explicit hidden override, while the old default `true` does not force the pad on desktop.
- Desktop NDS allows normal EmulatorJS autofocus; touch-first devices keep the prior no-autofocus policy.
- When an EmulatorJS menu or dialog is visible, the stage gives that UI interaction priority: the custom pad is placed below `#game` and all of its controls become pointer-inert. Menu-state observation is separate from the existing canvas-protection observer, with a debounced delayed sync for EmulatorJS's asynchronous UI transition.

Staging deployment completed successfully and `/health` returned `environment: staging` with asset version `d7b800cdfa6b`.

| Targeted staging QA | Result | Evidence |
| --- | --- | --- |
| GBA startup smoke | PASS | Super Mario Advance 4 loaded a canvas, reached ready state, and dismissed the loading state. |
| NDS startup | PASS | PMD EoS reached ready state with canvas pointer-events `auto` and touch-action `none`. |
| Desktop default pad policy | PASS | At 518×837 with `pointer: coarse = false` and `hover = true`, a fresh v3 default rendered no pad and `aria-pressed=false`. |
| EmulatorJS menu priority | PASS | With the pad deliberately shown, normal, 390×844 portrait, and 844×390 landscape each set `emulator-menu-open`; pad z-index became 19 and pad/control pointer-events became `none`. |
| EmulatorJS control settings | PASS | The visible settings dialog's tabs and text inputs were returned by `elementFromPoint` inside that dialog rather than by virtual controls. |
| Fullscreen | UNVERIFIED | The background in-app browser did not enter fullscreen despite the toolbar action; source and regression invariant retain `player-shell` as the fullscreen target. |
| Real Android touch input | UNVERIFIED | Layout/layering was exercised at phone viewport sizes, but an actual Android touch device was not available in this run. |
| Physical desktop keyboard gameplay/remap keystroke | PARTIAL | Default keyboard bindings and the remap UI are visible and hit-testable; the in-app automation keyboard abstraction did not provide a conclusive real-device remap capture. |

## Owner device validation and production authorization

On 2026-08-20, the owner confirmed the remaining real-device gates on staging and explicitly authorized production deployment:

- Weak-device performance: GBA sustained 58–60 FPS on staging; the prior production UI regularly dropped frames and stuttered on the same class of device. NDS sustained about 30 FPS, assessed as playable.
- Android touch, physical keyboard, fullscreen, and runtime save state were all confirmed working.

With the local suite and staging evidence above, `READY_FOR_PRODUCTION_APPROVAL` is reached and production deployment is authorized. The production result is recorded in the deployment handoff once the production health check completes.

## Production deployment result

- Deployment ran through `deploy.sh`, which creates a code/database backup before restarting the production service.
- Production health check passed: `environment: production`, asset version `26741dc82b2c`.
- The served production `player.js` contains the P0 touch-first policy, canvas-only root touch resolution, menu-layer state, and legacy hidden-override migration.
- The public homepage responded with HTTP 200 after deployment.
- No ROM, cover, screenshot, or game-record deletion action was performed.
