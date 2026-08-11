# Current phase

NDS TOUCH RECOVERY — PHASE C, P1 GEOMETRY-ONLY

Phase A recorded the clean `ed0a32d` baseline, corrected two stale integration
assertions without changing runtime behavior, and passed the explicit full
suite. Phase B commit `f47e511` added a fail-closed staging/development-only
`?ndsdebug=1` recorder. The regression gate passes 6/6. Staging is healthy at
asset `b5e759b8d6b7`; the no-debug control has no diagnostics global and both
control/debug pages start melonDS. Android 15 AVD evidence proves trusted native
events, forwarded Pointer/Mouse events, bounded JSON export, non-zero mapped
movement, release, save-state availability, and portrait/landscape geometry.
This remains browser/bridge evidence only: runtime Libretro pointer state and
melonDS stylus movement are unproven, and physical Android is open. Production
touch deployment is not approved and was not performed.

Next: run `EXP-C01-geometry-only` from the unchanged `hybrid-root` event model,
using measured canvas/touchscreen geometry. Reject P1 and move layers if correct
mapped coordinates still leave the stylus fixed.
