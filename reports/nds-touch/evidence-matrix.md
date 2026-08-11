# NDS Touch Evidence Matrix

`PASS` is scoped to the named layer. Browser/DOM evidence is never treated as a
melonDS stylus or physical-device pass.

| Experiment | Hypothesis | Startup | First tap | Native event | DOM movement | Mapped coordinates | Runtime pointer state | Stylus movement | Hold | Release | AVD | Physical Android | Regression | Conclusion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Historical `baseline` | Browser native path might suffice | Intermittent | Intermittent | Observed in some runs | No useful movement | Unproven | Unproven | FAIL | Unproven | Unproven | Mixed | OPEN | Historical | Rejected as fix |
| Historical `native` / `root` / `touch` | Alternate DOM binding fixes movement | Mixed | Mixed | Mixed | Event-level only | Unproven | Unproven | FAIL | Unproven | Unproven | Mixed | OPEN | Historical | Rejected as fix |
| Historical `touch-passive` | Avoiding prevention preserves runtime input | PASS | PASS | PASS | No stylus movement | Unproven | Unproven | FAIL | Unproven | Unproven | FAIL for goal | OPEN | Historical | Rejected |
| Historical `pointer-no-capture` / `root-touch` / `overlay` | Capture/target choice is the blocker | FAIL | FAIL | Mixed | FAIL | Unproven | Unproven | FAIL | FAIL | FAIL | FAIL | OPEN | Historical | Rejected |
| Historical `delta` / `pointer-touch` / `hybrid` | Synthetic delta/pointer delivery reaches core | Mixed | Mixed | PASS | PASS in browser | Partially observed | Unproven | Unproven | Unproven | Unproven | Event proof only | OPEN | Historical | Core effect unproven |
| `hybrid-root` control | Root TouchEvent plus pointer-then-mouse preserves startup/input | PASS | PASS in prior user report; browser input re-observed | PASS | PASS | PASS for whole-canvas formula | Unproven | Unproven | Browser events PASS | Browser events PASS | PASS for browser/runtime scope | OPEN | PASS | Control only, not movement fix |
| Historical `core-touch` | melonDS touch-mode option enables stylus | FAIL | FAIL | Mixed/duplicate risk | Unproven | Unproven | Unproven | FAIL | FAIL | FAIL | FAIL | OPEN | PASS locally | Rejected; never default |
| `EXP-B01-observability` | Passive recorder exposes the first failing layer without behavior change | PASS | PASS at browser/bridge layer | PASS (`isTrusted=true`) | PASS | PASS; portrait/landscape/fullscreen geometry recorded | Not instrumented | Unproven | PASS at event layer | PASS at event layer | PASS for diagnostics; fullscreen drag injection inconclusive | OPEN | PASS 6/6 | Phase B PASS; proceed to P1 geometry |

The authoritative detailed historical outcomes remain in
`reports/nds-touch/00-session-baseline.md`. New experiments must add a row here
before their family is declared accepted or rejected.

