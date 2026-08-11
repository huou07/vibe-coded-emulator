# EXP-C01 — Geometry-only relative mouse movement

Recorded: `2026-08-12T00:40:05+07:00`

```text
ID=EXP-C01-geometry-only
HYPOTHESIS=The hybrid-root bridge loses the relative MouseEvent movement that the running melonDS Mouse mode polls because PointerEvent and MouseEvent synthesis share one last-point cache.
CONTROL=/play/pmd-eos?touch=hybrid-root&ndsdebug=1
ONE_CHANGE=For geometry-only, keep separate pointer/mouse coordinate history and expose the computed CSS delta on the synthetic MouseEvent.
OBSERVABLE=Same-gesture native, forwarded PointerEvent, forwarded MouseEvent, exact runtime mouse state, core-rendered virtual cursor, hold, and release.
EXPECTED_IF_TRUE=Forwarded mousemove deltas become non-zero and directionally match PointerEvent deltas; the melonDS virtual cursor moves in both axes; startup/click/release remain intact.
EXPECTED_IF_FALSE=Mouse deltas remain zero, the virtual cursor remains fixed, startup/click regresses, or release state remains latched.
RESULT=PARTIAL on Android 15 AVD: browser, bridge, exact-runtime, and directional melonDS cursor movement pass, but raw CSS-pixel deltas do not preserve finger/cursor scale across rendered viewport sizes.
CONCLUSION=C01 proves the missing relative-mouse layer and real core movement, but it is not the final P1 candidate because mapped scale/alignment is unproven and predictably wrong outside a 1:1 render scale.
NEXT_ACTION=Use the second and final P1 candidate, EXP-C02 geometry-mapped, to convert the live rendered viewport to integer DS-local cursor targets before emitting relative mouse deltas.
```

## Why this is not a repeated historical candidate

```text
WHAT_IS_DIFFERENT=Historical delta was mouse-only/non-root. geometry-only preserves the hybrid-root root TouchEvent listener and pointer-then-mouse order, but prevents the pointer synthesis from consuming the following mouse synthesis's relative-coordinate history.
WHY_PREVIOUS_FAILURE_DOES_NOT_RULE_THIS_OUT=Historical delta did not preserve the best click/startup control and never proved a non-zero MouseEvent delta at the running core boundary. Phase B proved hybrid-root's pointer delta but also proved every forwarded mousemove delta was exactly zero.
WHAT_NEW_SIGNAL_THIS_EXPERIMENT_PRODUCES=The same AVD drag produces non-zero forwarded mousemove deltas only in geometry-only, and the core-drawn melonDS cursor moves directionally in rendered frames. It does not prove 1:1 finger alignment.
```

The query-only candidate does not change the default, listener target, event order,
`preventDefault`, capture, layout, or core option. The default remains
`hybrid-root`. `geometry-only` keeps the same root TouchEvent path and dispatches
PointerEvent before MouseEvent, exactly as the control does.

Post-experiment review found that C01 forwards raw CSS-pixel movement directly
to a core that consumes each unit as one DS cursor pixel. The measured content
scales were 1.25 in portrait, 0.4375 in landscape, and about 0.832 in fullscreen.
Consequently C01 correctly restores direction and motion, but cannot make the
stylus follow the finger at a consistent scale. This is why C01 is recorded as
PARTIAL rather than promoted to physical acceptance.

## First failing boundary

The live core reported these selected options:

```text
melonds_touch_mode|Mouse; Mouse|Touch|Joystick|disabled
melonds_screen_layout|Top/Bottom; ...
melonds_screen_gap|0; ...
video dimensions=256x384
```

The cached running assets are:

```text
melonds_libretro.js SHA256=07fb6dc287a24b05006980a4f6427fb07b60ac658e3d51935c3ec2f9062c5190
melonds_libretro.wasm SHA256=944049ac4beb60dd304c1596dfa56ba0fd8fb7aa817031ec291e47fc5c3a0856
```

Exact runtime tracing established that canvas mouse callbacks accumulate DOM
`movementX/Y`, the rwebinput poll snapshots and clears those deltas each frame,
and plain `RETRO_DEVICE_MOUSE` X/Y reads that snapshot. Button bit 0 remains
latched until mouseup. Target-relative `clientX/Y` are a separate absolute path;
the runtime does not read the synthetic `offsetX/Y` or `layerX/Y` overrides.

The official legacy melonDS source then reads `RETRO_DEVICE_MOUSE` X/Y and left
button in default Mouse mode, adds the relative deltas directly to its
bottom-screen-local 256x192 cursor, clamps them, calls `NDS::TouchScreen` while
pressed, and draws a virtual cursor. This provides a complete source-backed
chain from the corrected DOM field to the rendered core cursor.

The packaged `2.0.2` value is generic EmulatorJS core-bundle metadata, not a
melonDS version. The official `EmulatorJS/melonDS` source at `18a057d` identifies
the legacy core as melonDS `0.9.3`; the archive has no source commit, so the
build-to-source match is strong provenance inference rather than a cryptographic
binary-to-commit proof. The `Touch` option is valid and case-sensitive. The old
claim that `core-touch` failed because the option was invalid is disproven; that
candidate instead had an event-model mismatch and duplicate-binding risk.

## Implementation and local gate

```text
CODE_COMMIT=2cc8fbf86b8a0ecd0f76d476d38765c137b4df9d
CANDIDATE=geometry-only (query-only)
DEFAULT=hybrid-root (unchanged)
node --check static/player.js                         PASS
node --check static/offline.js                        PASS
node --check static/service-worker.js                 PASS
PYTHONPYCACHEPREFIX=/tmp/an3-pycache compile app.py   PASS
bash -n deploy.sh deploy-stage.sh                     PASS
git diff --check                                      PASS
python3 -m unittest discover -s tests -v              PASS (6/6)
```

Regression invariants require the separate `__an3NdsLastMousePoint` and
`__an3NdsLastPointerPoint` histories, explicit geometry-only MouseEvent movement
properties, the preserved pointer-then-mouse candidate list, and the unchanged
`get("touch") || "hybrid-root"` default.

## Staging deployment

```text
COMMIT=2cc8fbf86b8a0ecd0f76d476d38765c137b4df9d
DEPLOYED_TO=staging only
DEPLOYED_AT=2026-08-12T00:20:56+07:00
STAGING_URL=http://192.168.1.11:8092
ASSET_VERSION=880839b099fb
HEALTH=PASS; environment=staging; service=active
CONTROL_URL=http://192.168.1.11:8092/play/pmd-eos?touch=hybrid-root&ndsdebug=1&run=expc01-control-2cc8fbf
HISTORICAL_C01_URL=http://192.168.1.11:8092/play/pmd-eos?touch=geometry-only&ndsdebug=1&run=expc01-final-2cc8fbf
PRODUCTION=untouched; no NDS touch promotion approval
```

The deploy script's first five loopback curls ran before port 8092 finished
coming up, but the service was active. The independent live `/health` check then
passed and returned the asset above. The served `static/player.js` contains the
candidate implementation.

## Measured geometry and 3x3 grid

AVD: `codex-nds-api35`, serial `emulator-5556`, Android 15 / API 35 /
ARM64, Chrome `124.0.6367.219`.

In portrait, the live canvas CSS/backing rect was `(0,48,320,488)` and the core
video was 256x384 with Top/Bottom and gap 0. The rendered 320x480 combined-screen
content placed the touchscreen in canvas Y `240..480`, or browser-client Y
`288..528`. The AVD browser chrome added 80 screen pixels; the table records
browser CSS coordinates, not ADB screen coordinates. The virtual-pad `show`
class was removed only transiently for the diagnostic grid so all nine canvas
points were reachable; no preference or source was changed.

| Point | Finger CSS | Canvas coordinate | Expected DS coordinate | AVD core behavior |
| --- | --- | --- | --- | --- |
| top-left | `(32,312)` | `(32,264)` | `(26,19)` | Press/release PASS; absolute reposition is not expected in Mouse mode |
| top-center | `(160,312)` | `(160,264)` | `(128,19)` | Press/release PASS; absolute reposition is not expected in Mouse mode |
| top-right | `(288,312)` | `(288,264)` | `(230,19)` | Press/release PASS; absolute reposition is not expected in Mouse mode |
| middle-left | `(32,408)` | `(32,360)` | `(26,96)` | Press/release PASS; absolute reposition is not expected in Mouse mode |
| center | `(160,408)` | `(160,360)` | `(128,96)` | Press/release PASS; absolute reposition is not expected in Mouse mode |
| middle-right | `(288,408)` | `(288,360)` | `(230,96)` | Press/release PASS; absolute reposition is not expected in Mouse mode |
| bottom-left | `(32,504)` | `(32,456)` | `(26,173)` | Press/release PASS; absolute reposition is not expected in Mouse mode |
| bottom-center | `(160,504)` | `(160,456)` | `(128,173)` | Press/release PASS; absolute reposition is not expected in Mouse mode |
| bottom-right | `(288,504)` | `(288,456)` | `(230,173)` | Press/release PASS; absolute reposition is not expected in Mouse mode |

All nine grid points produced one trusted native down/up and one forwarded
mouse down/up. Both independent histories were `null` after every release. This
grid proves press/release coverage only: C01 is a relative-delta candidate, so
the table's expected DS coordinates were not absolute cursor destinations and
must not be counted as mapped-coordinate PASS evidence.

## Drag, hold, orientation, and fullscreen evidence

The 160-record ring truncates the leading part of long drags. Sums below are for
the retained records only and are not presented as the full gesture distance.

| Test | Retained forwarded mousemove | Non-zero | Retained delta | Release |
| --- | ---: | ---: | --- | --- |
| Portrait horizontal | 39 | 39 | `(+205.439,0)` | PASS; both histories null |
| Portrait vertical | 39 | 39 | `(0,+152.399)` | PASS; both histories null |
| Portrait diagonal | 39 | 39 | `(+205.439,+154.080)` | PASS; both histories null |
| Landscape horizontal | 39 | 39 | `(+89.888,0)` | PASS; both histories null |
| Fullscreen horizontal | 39 | 39 | `(+129.399,0)` | PASS; both histories null |

For each candidate drag, the forwarded MouseEvent direction and retained sum
matched the independent forwarded PointerEvent stream. A 1.5-second stationary
hold recorded native down-to-up `1500 ms`, forwarded mouse down-to-up `1499 ms`,
buttons `1 -> 0`, and cleared both histories.

These are raw CSS deltas. They prove continuous input and direction, not
finger/cursor scale or absolute alignment. In particular, the same physical
distance produces a different number of DS cursor pixels as the combined-screen
viewport is resized.

Landscape geometry was CSS/backing `640x168`, with the actual WebGL viewport
`(264,0,112,168)`. Fullscreen entry used the real page control and produced
viewport `640x320`, canvas CSS/backing `640x320`, and WebGL viewport
`(213,0,213,320)`. Candidate movement and release passed in both states. The AVD
was restored to automatic portrait rotation and non-fullscreen afterward.

## Same-build control differential

The same measured landscape drag was run after a clean navigation to the fresh
`hybrid-root` control on the same target and deployed build:

| Stream | Control records | Control non-zero | Candidate records | Candidate non-zero |
| --- | ---: | ---: | ---: | ---: |
| Native pointermove | 38 | 37 | 38 | 37 |
| Forwarded pointermove | 39 | 39 | 39 | 39 |
| Forwarded mousemove | 39 | **0** | 39 | **39** |

The control's retained forwarded mouse delta was exactly `(0,0)` while the
candidate's was `(+89.888,0)`. Both released. This isolates the one changed
field without attributing native or pointer movement to melonDS Mouse mode.

## Core-rendered movement proof

After Android's one-time fullscreen education overlay was dismissed, the
melonDS virtual cursor was visible as an inverted 4x4 block in the DS bottom
screen. Controlled frame comparisons gave directional 2D movement:

```text
LEFTWARD_GESTURE=forwarded mousemove delta negative X, zero Y
BEFORE_CURSOR_BOX=(339,278)..(342,281)
AFTER_CURSOR_BOX=(300,278)..(303,281)
RENDERED_RESULT=39 pixels left; Y unchanged

UPWARD_GESTURE=forwarded mousemove delta zero X, negative Y
BEFORE_CURSOR_BOX=(300,278)..(303,281)
AFTER_CURSOR_BOX=(300,239)..(303,241)
RENDERED_RESULT=39 pixels up; X unchanged
```

The X comparison contained exactly two changed 16-pixel connected components:
the old and new 4x4 cursor boxes. The Y comparison contained those cursor boxes
plus a separate small game-menu animation component. The cursor direction
matched the forwarded MouseEvent deltas in both comparisons.

Diagnostic frame hashes:

```text
before X=1d8d66a1b586796e07ecc677fb66daef08e0a9ab2d4d557a0a56c0f5376df652
after X / before Y=ca38a9fb481fc4bdec337f6f809c5e7175fb6850eb6b5ee6e951bdb4ab7f3d2f
after Y=0958ffa867f56088a4ffad80f760efa32e7e907579e14c88169c6fa3e5e5a7e6
```

This is a melonDS-rendered directional-movement PASS on the AVD, not merely
browser event movement. It is not an alignment/scale PASS. A fresh historical
C01 page also reported normal startup,
`gameManager=true`, `failedToStart=false`, melonDS, Mouse mode, 256x384 video,
and a `6,649,584`-byte save state.

## Gate

```text
P1_C01_AVD=PARTIAL
FIRST_FAILING_LAYER=hybrid-root forwarded MouseEvent movementX/Y
FIXED_LAYER=independent relative mouse-coordinate history plus explicit MouseEvent movement values
REMAINING_C01_GAP=raw CSS-pixel delta is not mapped to the 256x192 DS cursor domain
SECOND_GEOMETRY_CANDIDATE=EXP-C02 geometry-mapped used as the final P1 budget
P2_NATIVE_SURFACE=not started
P3_DIRECT_LIBRETRO=not started; no supported direct pointer API was found
PHYSICAL_ANDROID_C01=not requested because C01 failed the scale/alignment review
PRODUCTION=untouched and not approved
```
