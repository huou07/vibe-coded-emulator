# Current phase

NDS TOUCH RECOVERY — COMPLETE

Phase A recorded the clean `ed0a32d` baseline before source changes, corrected
two stale integration expectations, and passed the explicit full suite. Phase B
added fail-closed staging/development-only `?ndsdebug=1` observability and
isolated the first failing boundary: `hybrid-root` forwards valid PointerEvent
movement but every synthetic MouseEvent movement delta is zero while the running
melonDS core defaults to relative Mouse mode.

Phase C used both allowed P1 candidates. C01 `geometry-only` restored non-zero
relative MouseEvent movement and proved the core-rendered cursor moves in both
axes, but review rejected it as final because raw CSS-pixel deltas change scale
between portrait, landscape, and fullscreen. C02 `geometry-mapped` maps the live
rendered 256x384 viewport to an integer bottom-screen-local 256x192 target and
emits target-to-target mouse deltas. Hardening commit `15697a6` rejects stale
out-of-bounds WebGL viewport values after rotation.

The final local gate passes 6/6. Staging is healthy on commit `15697a6`, asset
`def955887c68`. Android 15 AVD evidence passes startup, first tap, exact 3x3
targets, horizontal/vertical/diagonal drag, 1.5-second hold, release, portrait,
live rotation, landscape, fullscreen, stale-viewport fallback, and a 6,649,584
byte save state. Controlled fullscreen frames prove the melonDS cursor moved 85
rendered pixels for the mapped `+102` DS X delta and 40 rendered pixels for the
mapped `+48` DS Y delta, exactly matching the measured viewport scales.

The default remains `hybrid-root`; `geometry-mapped` remains query-only in the
now-deployed production code. Physical evidence accepted the final P1 candidate,
so P2/P3 are not started.

A real-phone report now passes startup, click, cursor movement/animation, all
drag directions, hold/release, virtual pad, fullscreen, and save-state for C02.
Firefox Android also passes normal play. The user explicitly waived
portrait/landscape testing for this phone. The final promotion gate passes 6/6;
staging remains healthy on `def955887c68`.

The user explicitly approved production deployment. `deploy.sh` completed,
production now serves asset `def955887c68`, the service and backup timer are
active/enabled, and code/database rollback artifacts were created. Public AVD
smoke passed with melonDS startup and fail-closed diagnostics. See
`reports/production-readiness/13-nds-touch-production-deployment.md`.
