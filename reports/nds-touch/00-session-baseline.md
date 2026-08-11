# NDS Touch Recovery — Session Baseline

Recorded: `2026-08-11T23:37:43+07:00`

## Repository baseline

```text
WORKSPACE=/Users/meomeo/Documents/Codex/2026-08-11/an3-arcade
BRANCH=main
HEAD=ed0a32d50944f32bda9052bc6e41be3173d7f2c4
PRE_REPORT_DIRTY_STATE=clean
CONTROL=hybrid-root
LATEST_EXPERIMENT=core-touch (FAILED: game did not start/click/move)
PHYSICAL_ANDROID=OPEN
PRODUCTION_TOUCH_DEPLOY=NOT APPROVED / NOT DEPLOYED
```

The source and live staging `static/player.js` both select `hybrid-root` when the
NDS route has no `touch` query parameter. `core-touch` remains query-only and is
not the default.

Recent history begins with:

```text
ed0a32d Add melonDS core touch mode staging variant
2cb9fd9 Make PWA navigation fallback pathname aware
a19ac94 Promote hybrid root touch candidate
097c37d Make hybrid root NDS touch the default
90ec601 Record Android AVD touch verification
```

`git diff --check` passed before this report was created.

## Staging baseline

```text
URL=http://192.168.1.11:8092
HEALTH=PASS
ENVIRONMENT=staging
ASSET_VERSION=2c0b9d35db77
LIVE_DEFAULT_TOUCH=hybrid-root
LIVE_CORE_TOUCH_QUERY_PRESENT=yes
LIVE_EJS_START_ON_LOADED=true
```

The live asset state is newer than the asset identifier quoted in the handoff,
but its default/control semantics match local HEAD. Production was not touched.

## Previously failed or unproven variants

Authoritative handoff result:

```text
baseline       startup/click intermittent; no movement
native         startup/click intermittent; no movement
root           startup/click intermittent; no movement
touch          startup/click intermittent; no movement
touch-passive  startup/click; no movement
pointer-no-capture  no startup/click/movement
root-touch     no startup/click/movement
overlay        no startup/click/movement
delta          DOM/core movement not proven
pointer-touch  core movement not proven
hybrid         core movement not proven
hybrid-root    startup/click; DOM delta observed; stylus movement unproven
core-touch     no startup/click/movement
```

No prior event-level result is treated as a core-level stylus pass.

## Phase A command results

Syntax/static checks:

```text
node --check static/player.js                    PASS
node --check static/offline.js                   PASS
node --check static/service-worker.js            PASS
bash -n deploy.sh                                PASS
bash -n deploy-stage.sh                          PASS
PYTHONPYCACHEPREFIX=/tmp/an3-pycache
  python3 -m compileall -q app.py                 PASS
git diff --check                                 PASS
```

The planner's literal command produced no meaningful suite result:

```text
python3 -m unittest -v
Ran 0 tests in 0.000s
OK
```

Because `tests/` is not discovered by that invocation in this checkout, the
actual full suite was run explicitly:

```text
python3 -m unittest discover -s tests -v
Ran 5 tests in 0.607s
FAILED (failures=1)
```

The first sandboxed run could not bind the localhost test server
(`PermissionError: [Errno 1] Operation not permitted`). Re-running outside the
sandbox proved that this was an environment limitation, then exposed one real
assertion failure:

```text
tests/test_integration.py expects: an3-arcade-pwa-v16
static/service-worker.js serves:   an3-arcade-pwa-v17
```

The implementation value `v17` corresponds to commit `2cb9fd9` and the handoff's
pathname-aware PWA cache change. This was a stale regression assertion, not an
application regression. After correcting it, the suite exposed one more stale
exact-format assertion from commit `ed0a32d`:

```text
tests/test_integration.py expected the former single-line EJS_defaultOptions assignment
static/player.js now keeps retroarch_core:"melonds" in a multiline object so core-touch
can add a query-only option
```

That assertion was narrowed to the invariant it is meant to protect:
`retroarch_core:"melonds"`. No player behavior was changed. The complete suite
then passed:

```text
python3 -m unittest discover -s tests -v
Ran 5 tests in 0.499s
OK
```

README PWA shell documentation was also aligned from v16 to v17.

## Gate

```text
PHASE_A=PASS
FULL_TEST_SUITE=PASS (5/5 explicit discovery)
SOURCE_BEHAVIOR_CHANGES=none
NEXT_ACTION=Phase B behavior-neutral instrumentation
```
