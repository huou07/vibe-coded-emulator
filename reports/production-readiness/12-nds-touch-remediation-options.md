# NDS touch remediation options

## Current symptom

On Android, the first tap may reach the emulator, but the Nintendo DS pointer does not follow finger movement. A later variant also stopped registering the first tap. The authoritative proof still requires a real Chrome Android or Firefox Android finger test; desktop browser automation cannot prove this behavior.

## Options considered

1. **Native EmulatorJS pointer path** — leave the canvas touch/pointer events native and only remove the virtual gamepad overlay. This has the smallest compatibility surface, but depends on the exact EmulatorJS build handling the device's pointer events.
2. **PointerEvent-to-mouse bridge** — translate `pointerdown/move/up` to canvas mouse events and normalize `offsetX/offsetY` against the canvas backing resolution. This is the original bridge and remains the primary path.
3. **TouchEvent fallback** — also listen for `touchstart/move/end/cancel` even when `PointerEvent` exists. This covers Android WebViews that expose the API but do not dispatch usable pointer events to the canvas. The current staging candidate uses this path.
4. **Unknown-pointer fallback** — accept a pointer event whose `pointerType` is empty, as some Android implementations report an incomplete pointer type. The current candidate uses this path; normal desktop mouse events remain excluded.
5. **Coordinate-source fallback** — use `clientX/clientY` when present and preserve CSS-pixel coordinates for `offsetX/offsetY` (the native browser semantics), with `pageX/pageY - scroll offset` as a source fallback. The current candidate uses this path; it no longer scales offsets into backing-store pixels.
6. **Native propagation fallback** — do not call `stopImmediatePropagation()` on the original TouchEvent, so EmulatorJS can receive the native event as well as the bridge event. The current candidate uses this path to protect the first tap.
7. **Delegated root bridge** — listen on the game root/document and resolve the canvas with `elementFromPoint()`. This is useful if a runtime replaces the canvas or a transparent overlay receives the touch, but is not enabled yet because it can steal touches from controls.
8. **Dedicated transparent touch surface** — add a canvas-aligned overlay that owns touch input and forwards normalized coordinates. This gives deterministic hit-testing, but increases z-index and fullscreen/PWA risks.
9. **EmulatorJS adapter patch** — patch or configure the exact EmulatorJS input handler to consume normalized touch coordinates directly. This is the most exact solution but couples the app to CDN/runtime internals and requires a pinned local runtime or an upstream-compatible change.
10. **Virtual-pad fallback** — expose an on-screen DS touchpad/selector as a temporary usability fallback. It does not solve the real touchscreen pointer requirement and should not be treated as completion.
11. **Rollback** — if the candidate fails the first-tap smoke test, restore the last known staging release immediately. Production remains untouched until a candidate passes the first tap and movement test on Android.

## Current candidate and evidence

The candidate combining options 2–6 was rejected by the user's Android smoke test because the game no longer accepted the first click. The runtime source was rolled back, then the safer CSS-pixel coordinate correction was applied to the click-preserving bridge. Local regression tests pass 3/3; staging reaches the ready state with an active bridge and no browser errors. Real Android finger verification remains required. No production deploy or database change was made.

The next untried implementation should be option 7 (delegated root bridge with `elementFromPoint`) behind a feature flag or separate staging release, so the click-preserving baseline remains recoverable.
