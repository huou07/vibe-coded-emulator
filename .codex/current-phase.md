# Current phase

NDS TOUCH RECOVERY — PHYSICAL ANDROID MATRIX COMPLETION

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

The default remains `hybrid-root`; `geometry-mapped` is query-only. Production
touch code is untouched and unapproved. Do not start P2/P3 unless physical
evidence rejects or materially limits this second and final P1 candidate.

A real-phone user report now passes startup, click, and cursor movement for C02.
That is a physical basic-smoke PASS, not the complete matrix: drag axes, hold,
release, rotation, virtual pad, fullscreen, save-state, and Firefox remain
unreported. The post-physical local gate passes 6/6 and staging remains healthy
on `def955887c68`.

Next: complete the remaining physical matrix on Chrome Android, then Firefox
Android or a documented exception, using exactly:

`http://192.168.1.11:8092/play/pmd-eos?touch=geometry-mapped&ndsdebug=1&run=physical-15697a6`
