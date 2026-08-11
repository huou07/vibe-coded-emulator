# EXP-B01 — NDS Touch Observability

Recorded: `2026-08-12T00:01:20+07:00`

```text
ID=EXP-B01-observability
HYPOTHESIS=A passive, bounded recorder can expose every browser/bridge geometry field without changing hybrid-root behavior.
CONTROL=/play/pmd-eos?touch=hybrid-root
ONE_CHANGE=staging/development-only ?ndsdebug=1 recorder and local JSON export
OBSERVABLE=native/forwarded event stream, geometry, mapping, movement, capture, orientation, fullscreen, core, and release
EXPECTED_IF_TRUE=control still starts; no-debug has no API; debug route records and exports a bounded complete stream
EXPECTED_IF_FALSE=startup/input regresses, production can enable the API, records are incomplete, or the buffer/export fails
RESULT=PASS for observability and AVD browser/bridge scope
CONCLUSION=Phase B instrumentation is usable; no melonDS stylus movement claim is made
NEXT_ACTION=EXP-C01 geometry-only using measured runtime geometry
```

## Deployment record

```text
COMMIT=f47e511ecc219f52627643dd4d6b8022f40345e0
CANDIDATE=hybrid-root + ndsdebug=1 (instrumentation only)
DEPLOYED_TO=staging only
STAGING_URL=http://192.168.1.11:8092
ASSET_VERSION=b5e759b8d6b7
HEALTH=PASS; environment=staging
CONTROL_URL=http://192.168.1.11:8092/play/pmd-eos?run=phaseb-nodebug-f47e511
TEST_URL=http://192.168.1.11:8092/play/pmd-eos?touch=hybrid-root&ndsdebug=1&run=phaseb-f47e511
PRODUCTION=untouched; diagnostics fail closed in production
```

The server only emits `ndsDebugAllowed=true` when `AN3_ENVIRONMENT` is
`staging` or `development`. The client additionally requires NDS plus the exact
query `ndsdebug=1`. The no-query production-shaped integration server emitted
`false` even when the request URL contained `ndsdebug=1`.

## Behavior-neutral implementation

- One passive capture observer; it never calls `preventDefault`, changes event
  order, captures a pointer, dispatches input, changes layout, or changes a core
  option.
- It tracks touch/pointer IDs that began inside `#game`, so document-retargeted
  movement/release is retained.
- Canvas geometry is cached per animation frame (with a 20 ms freshness bound),
  avoiding repeated synchronous layout work for native plus forwarded fan-out.
- The rolling buffer is limited to 160 events and is memory-only.
- `window.AN3NdsDebug.snapshot()` returns a copy; `exportJSON()` downloads and
  returns parseable JSON.

## Regression gate

```text
node --check static/player.js                         PASS
node --check static/offline.js                        PASS
node --check static/service-worker.js                 PASS
PYTHONPYCACHEPREFIX=/tmp/an3-pycache compile app.py   PASS
bash -n deploy.sh deploy-stage.sh                     PASS
git diff --check                                      PASS
python3 -m unittest discover -s tests -v              PASS (6/6)
```

## Android AVD evidence

```text
AVD=codex-nds-api35
SERIAL=emulator-5556
ANDROID=15 / API 35 / ARM64
CHROME=124.0.6367.219
CDP=127.0.0.1:9222
```

Fresh no-debug control:

```text
document.readyState=complete
AN3NdsDebug=undefined
gameManager=true
failedToStart=false
loadingDone=true
canvas touch marker=1
root touch marker=1
```

Fresh debug control before input:

```text
document.readyState=complete
gameManager=true
failedToStart=false
loadingDone=true
touchVariant=hybrid-root
activeCore=melonds
canvas CSS/backing=320x488 / 320x488
devicePixelRatio=1
orientation=portrait
```

A trusted ADB tap produced ten ordered records: native pointer/touch down and
up, implicit pointer capture acquire/release, followed by the existing
synthetic PointerEvent and MouseEvent bridge. Native records had
`isTrusted=true`; forwarded records had `isTrusted=false`. At the measured
center point, client `(160,270)` mapped to canvas `(160,222)` and normalized
`(0.5,0.454918...)`.

The measured tap/drag/hold sequence filled and truncated the ring:

```text
eventLimit=160
eventCount=160
first retained sequence=571
last retained sequence=730
every required schema key present=true
native non-zero movement records=36
forwarded non-zero movement records=37
release records in retained window=8
client X range=160..310
client Y range=426..520
mapped X range=160..310
mapped Y range=378..472
normalized X range=0.5..0.96875
normalized Y range=0.77459..0.96721
save-state bytes=6,649,584
```

`exportJSON()` returned JSON with schema `an3-nds-touch-debug-v1` and also
created the local AVD download. This proves the export path and buffer behavior,
not melonDS stylus movement.

After portrait input, the AVD was rotated to landscape. The same running game
remained active, canvas geometry changed to CSS/backing `640x168`, and a
measured drag recorded native plus forwarded non-zero movement and releases
with `orientation=landscape` and `screenOrientation=landscape-primary`.

Fullscreen entry passed (`document.fullscreenElement` was the NDS player stage,
viewport `640x320`, game manager still active). ADB coordinate injection did
not produce page events while fullscreen, so fullscreen drag is **INCONCLUSIVE
on this AVD input mechanism**, not a PASS or FAIL for stylus behavior. The AVD
was restored to automatic portrait rotation and the page exited fullscreen.

## Gate

```text
PHASE_B=PASS
CONTROL_REGRESSION=not observed in startup, event path, rotation, save-state, or fullscreen entry
RUNTIME_POINTER_STATE=not yet instrumented
MELONDS_STYLUS_MOVEMENT=unproven
PHYSICAL_ANDROID=OPEN
```

