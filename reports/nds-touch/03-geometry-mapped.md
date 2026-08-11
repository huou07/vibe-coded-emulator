# EXP-C02 — Mapped DS cursor geometry

Recorded: `2026-08-12T01:19:49+07:00`

```text
ID=EXP-C02-geometry-mapped
HYPOTHESIS=C01 restored the relative mouse field consumed by melonDS, but forwarding CSS pixels directly makes cursor scale depend on the rendered viewport. Mapping each finger sample through the live core viewport to an integer 256x192 DS touchscreen target, then emitting target-to-target deltas, should preserve the proven Mouse-mode path while making the stylus follow the finger.
CONTROL=/play/pmd-eos?touch=geometry-only&ndsdebug=1
ONE_CHANGE=For geometry-mapped only, resolve the displayed 256x384 core viewport, map the bottom half to DS-local 256x192 coordinates, and expose integer target deltas on the synthetic MouseEvent.
OBSERVABLE=Exact mapped targets, forwarded mouse deltas, core-rendered cursor position, startup, hold/release, orientation, fullscreen, save-state, and stale-viewport fallback.
EXPECTED_IF_TRUE=Grid points map to the intended DS coordinates and the core-rendered cursor lands at the corresponding scaled pixels in both axes without changing the default or core option.
EXPECTED_IF_FALSE=Scale varies by orientation, the cursor and finger diverge, the first tap fails, release sticks, or stale renderer geometry produces an incorrect target.
RESULT=PASS on Android 15 AVD at browser, bridge, exact-runtime, mapped-coordinate, and melonDS-rendered-cursor layers; physical Android remains OPEN.
CONCLUSION=C02 is the second and final P1 candidate. Stop at the physical Android gate; do not start P2/P3 unless physical evidence rejects or materially limits C02.
NEXT_ACTION=Use one exact C02 URL on physical Chrome Android, then the same URL on Firefox Android or record a justified exception.
```

## Why C01 does not rule this out

```text
WHAT_IS_DIFFERENT=C01 emits raw CSS-pixel deltas. C02 converts the live rendered core viewport to an absolute DS-local target and emits the integer difference from the last core cursor target.
WHY_PREVIOUS_FAILURE_DOES_NOT_RULE_THIS_OUT=C01 proved the event field, runtime poll, button path, and core cursor can move. Its failure is a measured scale-domain mismatch, not a failure of relative Mouse mode.
WHAT_NEW_SIGNAL_THIS_EXPERIMENT_PRODUCES=Exact 3x3 DS targets plus controlled rendered frames whose cursor displacement equals the target delta multiplied by the measured core viewport scale.
```

C02 preserves the `hybrid-root` root TouchEvent listener, canvas resolution,
PointerEvent-then-MouseEvent order, prevention behavior, lack of pointer capture,
core layout, and core options. The default remains `hybrid-root`; both C01 and
C02 are query-only staging candidates.

## Source and runtime contract

The running core reports:

```text
melonds_touch_mode|Mouse; Mouse|Touch|Joystick|disabled
melonds_screen_layout|Top/Bottom; ...
melonds_screen_gap|0; ...
video dimensions=256x384
```

Exact cached-runtime tracing established that rwebinput accumulates DOM
`movementX/Y`, snapshots and clears it at the input poll, and returns those
values for plain `RETRO_DEVICE_MOUSE`. The left-button bit remains set until
mouseup. The core's default Mouse mode adds those relative values directly to a
bottom-screen-local 256x192 cursor and clamps the result.

The package value `2.0.2` is generic EmulatorJS core-bundle metadata, not the
melonDS version. The official legacy `EmulatorJS/melonDS` source identifies
melonDS `0.9.3`; commit `18a057d` is a strong deployed-era provenance inference,
not a cryptographic binary-to-source match. `melonds_touch_mode=Touch` is valid
and case-sensitive. The historical `core-touch` failure is instead confounded by
an event-dispatch mismatch and duplicate-binding risk.

Cached runtime assets used for the trace:

```text
melonds_libretro.js SHA256=07fb6dc287a24b05006980a4f6427fb07b60ac658e3d51935c3ec2f9062c5190
melonds_libretro.wasm SHA256=944049ac4beb60dd304c1596dfa56ba0fd8fb7aa817031ec291e47fc5c3a0856
```

## Implementation and local gate

`geometry-mapped` uses the current WebGL viewport when it is valid. It converts
backing pixels to CSS pixels, converts WebGL's bottom-origin Y to CSS top-origin,
and maps the lower half of the default Top/Bottom frame to DS-local 256x192
targets. On mousedown it clears the viewport cache and snaps the core cursor to
the current finger target. Subsequent moves emit integer target-to-target
deltas, so fractional CSS motion is accumulated by the mapping rather than
truncated every core poll.

Chrome can briefly expose a pre-rotation WebGL viewport after the canvas has
resized. Hardening commit `15697a6` rejects any viewport outside the current
backing dimensions and uses a measured 256x384 aspect-fit fallback.

```text
IMPLEMENTATION_COMMIT=c532f0c685525e4b38e8ce3e9af890b80af4ae2d
HARDENING_COMMIT=15697a634360e3d9ae66bf4b5176333ce53ba5a3
CANDIDATE=geometry-mapped (query-only)
DEFAULT=hybrid-root (unchanged)
node --check static/player.js                         PASS
node --check static/offline.js                        PASS
node --check static/service-worker.js                 PASS
PYTHONPYCACHEPREFIX=/tmp/an3-pycache compile app.py   PASS
bash -n deploy.sh deploy-stage.sh                     PASS
git diff --check                                      PASS
python3 -m unittest discover -s tests -v              PASS (6/6)
```

Regression invariants cover the query-only candidate lists, unchanged default,
pointer-before-mouse dispatch, independent coordinate histories, mapped cursor
deltas, WebGL viewport use, stale-viewport bounds, cache invalidation, and the
fact that only historical `core-touch` can alter `melonds_touch_mode`.

## Final staging deployment

```text
COMMIT=15697a634360e3d9ae66bf4b5176333ce53ba5a3
DEPLOYED_TO=staging only
DEPLOYED_AT=2026-08-12T01:10:54+07:00
STAGING_URL=http://192.168.1.11:8092
ASSET_VERSION=def955887c68
HEALTH=PASS; environment=staging; service=active
CANDIDATE_URL=http://192.168.1.11:8092/play/pmd-eos?touch=geometry-mapped&ndsdebug=1&run=physical-15697a6
PRODUCTION=untouched; no NDS touch promotion approval
```

The deploy script's first five loopback probes again ran before port 8092 was
ready, then the service became active. An independent LAN `/health` request
passed and returned the asset and timestamp above.

## AVD environment and startup

```text
AVD=codex-nds-api35
SERIAL=emulator-5556
ANDROID=15 / API 35 / ARM64
CHROME=124.0.6367.219
CORE=melonds
CORE_MODE=Mouse
LAYOUT=Top/Bottom; gap 0
STARTUP=gameManager true; failedToStart false
SAVE_STATE=6,649,584 bytes
```

The original AVD process exited unexpectedly after the first C02 grid. This was
an emulator infrastructure interruption, not a page crash: the browser event
evidence had already completed, the same AVD was relaunched, and the critical
checks were repeated. The hardened final deployment then completed without an
AVD exit.

## Measured geometry

| State | Canvas CSS/backing | WebGL core viewport | Mapping domain |
| --- | --- | --- | --- |
| Portrait | `320x488` at `(0,48)` | `(0,8,320,480)` backing, CSS top 0 | bottom half of rendered `320x480` |
| Landscape | `640x168` at `(0,48)` | `(264,0,112,168)` | bottom half of `112x168` |
| Fullscreen landscape | `640x320` at `(0,0)` | `(213,0,213,320)` | bottom half of `213x320` |

The portrait C02 run mapped a 3x3 grid to `(26|128|230,
19|96|173)`. The final fullscreen hardened run used integer screen coordinates
whose measured targets were:

| Point | Finger CSS | DS target | Mousedown delta from previous target |
| --- | --- | --- | --- |
| top-left | `(235,176)` | `(26,19)` | `(-204,-125)` |
| top-center | `(320,176)` | `(129,19)` | `(+103,0)` |
| top-right | `(404,176)` | `(230,19)` | `(+101,0)` |
| middle-left | `(235,240)` | `(26,96)` | `(-204,+77)` |
| center | `(320,240)` | `(129,96)` | `(+103,0)` |
| middle-right | `(404,240)` | `(230,96)` | `(+101,0)` |
| bottom-left | `(235,304)` | `(26,173)` | `(-204,+77)` |
| bottom-center | `(320,304)` | `(129,173)` | `(+103,0)` |
| bottom-right | `(404,304)` | `(230,173)` | `(+101,0)` |

The grid produced 90 diagnostic records: nine trusted downs/ups, nine forwarded
mouse downs/ups, and nine releases with `buttons=0`. The custom virtual pad was
disabled only at the runtime style layer during coordinate diagnostics so all
canvas points were reachable; no source or stored preference was changed.

## Gesture and release matrix

Final fullscreen gestures on asset `def955887c68`:

| Test | Forwarded mousemove | Non-zero | Move-only mapped delta | Release |
| --- | ---: | ---: | --- | --- |
| Horizontal `(26,96)->(230,96)` | 19 | 19 | `(+204,0)` | `buttons=0` |
| Vertical `(129,19)->(129,173)` | 19 | 19 | `(0,+154)` | `buttons=0` |
| Diagonal `(26,19)->(230,173)` | 19 | 19 in both axes | `(+204,+154)` | `buttons=0` |
| Stationary center hold | 0 | 0 expected | native down/up `1499 ms` | `buttons 1->0` |

Earlier C02 portrait runs likewise passed horizontal, vertical, and diagonal
movement, 1.5-second hold, release, and cleared both isolated histories. The
final hardened build re-passed portrait center mapping, live rotation,
landscape center/right mapping, fullscreen 3x3, all three drag axes, hold,
release, and save-state serialization.

## Stale viewport hardening proof

The previously observed stale value was injected for one landscape tap while
the actual canvas backing was `640x168`:

```text
INJECTED_WEBGL_VIEWPORT=(0,8,320,480)
CANVAS_BACKING=(640,168)
PREVIOUS_CURSOR=(231,96)
FINGER=landscape center
EXPECTED_FALLBACK_TARGET=(128,96)
FORWARDED_MOUSEDOWN_DELTA=(-103,0)
FORWARDED_MOUSEUP_BUTTONS=0
RESTORED_WEBGL_VIEWPORT=(264,0,112,168)
RESULT=PASS
```

Without the bounds guard, that impossible viewport would have mapped the same
finger near the right edge and changed Y. The observed `(-103,0)` proves C02
used the aspect-fit fallback and preserved the correct center target.

## Core-rendered coordinate proof

The emulator was paused around each screenshot so the 3x4 melonDS virtual
cursor could be isolated. From DS center `(128,96)` to right `(230,96)`, the
forwarded mousedown delta was `(+102,0)` and the rendered cursor moved:

```text
OLD_CURSOR_BOX=(318,238)..(320,241)
NEW_CURSOR_BOX=(403,238)..(405,241)
RENDERED_DELTA=(+85,0)
EXPECTED_X=(230-128)*213/256=84.87 pixels
DIFF=exactly two 12-pixel cursor components; no other changed pixels
```

From right `(230,96)` to lower-right `(230,144)`, the forwarded delta was
`(0,+48)` and the rendered cursor moved:

```text
OLD_CURSOR_BOX=(403,238)..(405,241)
NEW_CURSOR_BOX=(403,278)..(405,281)
RENDERED_DELTA=(0,+40)
EXPECTED_Y=48*320/384=40 pixels
DIFF=old/new 12-pixel cursor components plus one unrelated 24-pixel menu animation component
```

Screenshot hashes:

```text
center=81a1862e1d9088f88d7694009b080d96f3f7c909c19243b110cbb816103222fa
right=45c88c6337817f0e2928cc0b76e9bd6035c5e3874e411b89a135913363685bac
right-lower=2dacf37f5bc71bdf508db30c3b299aacb49f7ed40db0385cdb2d5c2932fe5ee8
```

This is exact mapped core-render evidence in both axes. It closes the scale gap
identified in C01, but it does not replace a real-finger physical-device test.

## Gate

```text
P1_C01=PARTIAL; relative mouse layer and direction proven, scale rejected
P1_C02_AVD=PASS; final P1 candidate
DEFAULT=hybrid-root unchanged
P2_NATIVE_SURFACE=not started
P3_DIRECT_LIBRETRO=not started; no supported direct pointer API was found
PHYSICAL_ANDROID_CHROME=OPEN
PHYSICAL_ANDROID_FIREFOX=OPEN or documented exception required
PRODUCTION=untouched and not approved
```
