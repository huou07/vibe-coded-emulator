# NDS touch remediation options

## Current symptom and acceptance boundary

The original Android failure was: the first tap could reach melonDS, but the DS
cursor did not follow finger movement. Phase B located the first failing field:
the click-preserving `hybrid-root` bridge forwarded non-zero PointerEvent motion
but zero MouseEvent `movementX/Y`, while the core's default Mouse mode polls the
relative mouse device. Android AVD evidence now passes for the mapped candidate,
but a real Chrome/Firefox Android finger test remains authoritative.

## Options considered

1. **Native EmulatorJS path** — leave canvas touch handling native. The deployed
   rwebinput path records native touch for `RETRO_DEVICE_POINTER`, but legacy
   melonDS defaults to the separate relative Mouse device.
2. **PointerEvent-to-mouse bridge** — translate pointer events to canvas mouse
   events. Historical variants did this without preserving the click/startup
   control or proving the exact mouse field the core consumes.
3. **TouchEvent fallback** — listen for `touchstart/move/end/cancel` when Android
   exposes PointerEvent but canvas targeting is unreliable. The root candidates
   use this event source.
4. **Unknown-pointer fallback** — accept an empty `pointerType`. This applied to
   historical PointerEvent candidates; C02's controlling input is the root
   TouchEvent path.
5. **Coordinate mapping** — the exact runtime derives canvas-local absolute
   position from `clientX/Y` and the target rectangle; it ignores synthetic
   `offsetX/Y` overrides. C02 uses `clientX/Y`, the live rendered core viewport,
   and the default combined-screen layout to produce DS-local integer targets.
6. **Native propagation fallback** — avoid `stopImmediatePropagation()` on the
   original TouchEvent so the first-tap/native path remains available. C02
   preserves the `hybrid-root` behavior.
7. **Delegated root bridge** — listen on the game root and resolve the current
   canvas. This became the click-preserving `hybrid-root` control. It preserves
   startup/release but alone does not populate relative mouse movement.
8. **Dedicated transparent touch surface** — add a canvas-aligned native surface.
   This remains P2 if the final geometry candidate fails physical validation.
9. **EmulatorJS adapter patch** — pin/patch the exact runtime input adapter. This
   couples the app to runtime internals and is not warranted while P1 remains
   viable.
10. **Direct Libretro input** — no supported direct pointer API or safe numeric
    `simulate_input` mapping was found; no IDs were guessed.
11. **Virtual touchpad fallback** — a usability workaround, not completion of
    direct finger-follow touch.
12. **Rollback** — keep the default `hybrid-root` and all candidates query-only
    until the physical gate and explicit production approval pass.

## Candidate history and current evidence

`EXP-C01-geometry-only` gave synthesized PointerEvent and MouseEvent independent
last-point histories and exposed computed raw CSS movement on MouseEvent. It
proved the missing field reaches the exact runtime and moves the melonDS cursor
in both axes. It is PARTIAL, not the final candidate: the core consumes one
movement unit as one DS pixel, so raw CSS movement scales incorrectly at the
measured portrait, landscape, and fullscreen render sizes.

`EXP-C02-geometry-mapped` preserves the C01 event isolation but maps every finger
sample through the live 256x384 rendered viewport to an integer bottom-screen
256x192 target. It then emits target-to-target deltas on MouseEvent. Commit
`15697a6` also rejects a WebGL viewport that falls outside the current backing
dimensions and uses aspect-fit geometry during the post-rotation stale window.

Final AVD evidence on staging asset `def955887c68` includes exact 3x3 targets,
all three drag axes, hold/release, portrait, rotation, landscape, fullscreen,
injected stale-viewport fallback, and a 6,649,584-byte save state. Controlled
frames showed:

```text
DS delta (+102,0) -> rendered cursor delta (+85,0), expected 84.87
DS delta (0,+48)  -> rendered cursor delta (0,+40), expected 40
```

Local regression passes 6/6. Detailed records are in
`reports/nds-touch/02-geometry-only.md` and
`reports/nds-touch/03-geometry-mapped.md`. Production was not changed.

## Staging test pages

Historical pages remain available for differential diagnosis, but the physical
gate uses only the one C02 URL below.

- Baseline: `http://192.168.1.11:8092/play/pmd-eos?touch=baseline`
- Native EmulatorJS path: `http://192.168.1.11:8092/play/pmd-eos?touch=native`
- Delegated root bridge: `http://192.168.1.11:8092/play/pmd-eos?touch=root`
- TouchEvent-only bridge: `http://192.168.1.11:8092/play/pmd-eos?touch=touch`
- TouchEvent without preventDefault: `http://192.168.1.11:8092/play/pmd-eos?touch=touch-passive`
- PointerEvent without pointer capture: `http://192.168.1.11:8092/play/pmd-eos?touch=pointer-no-capture`
- Delegated root TouchEvent bridge: `http://192.168.1.11:8092/play/pmd-eos?touch=root-touch`
- Delegated root PointerEvent bridge: `http://192.168.1.11:8092/play/pmd-eos?touch=overlay`
- Synthetic mouse movement deltas: `http://192.168.1.11:8092/play/pmd-eos?touch=delta`
- TouchEvent-to-PointerEvent bridge: `http://192.168.1.11:8092/play/pmd-eos?touch=pointer-touch`
- Hybrid MouseEvent + PointerEvent bridge: `http://192.168.1.11:8092/play/pmd-eos?touch=hybrid`
- Root hybrid control: `http://192.168.1.11:8092/play/pmd-eos?touch=hybrid-root`
- Historical core Touch experiment: `http://192.168.1.11:8092/play/pmd-eos?touch=core-touch`
- C01 raw relative repair: `http://192.168.1.11:8092/play/pmd-eos?touch=geometry-only`
- C02 mapped geometry: `http://192.168.1.11:8092/play/pmd-eos?touch=geometry-mapped`

The default with no query remains `hybrid-root`. `melonds_touch_mode=Touch` is a
valid, case-sensitive core option, but historical `core-touch` did not isolate
that device path and risked duplicate canvas/root bindings; its failure is not
evidence that the option is invalid.

## Physical Android gate

Use exactly:

`http://192.168.1.11:8092/play/pmd-eos?touch=geometry-mapped&ndsdebug=1&run=physical-15697a6`

Test Chrome first, then the same URL in Firefox if available: startup, first
tap, corners/center, horizontal/vertical/diagonal drag, hold, release, portrait,
landscape, virtual pad, fullscreen, and save state. Record only PASS, FAIL, or
PARTIAL. AVD success must not be promoted to physical PASS.
