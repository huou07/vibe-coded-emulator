# Physical Android evidence — C02 geometry-mapped

Recorded: `2026-08-12T07:01:57+07:00`

The user reported testing the active, exact C02 staging candidate on a real
phone and confirmed all of the following:

```text
SOURCE=user report in the active recovery task
CANDIDATE=geometry-mapped
STAGING_COMMIT=15697a634360e3d9ae66bf4b5176333ce53ba5a3
STAGING_ASSET=def955887c68
STARTUP=PASS
CLICK=PASS
CURSOR_MOVEMENT=PASS
```

This is physical-device evidence and upgrades those three acceptance items beyond
the AVD. Browser name/version, device model, and the rest of the matrix were not
reported, so they are deliberately not inferred.

## Remaining physical scope

```text
3X3_CORNERS_AND_CENTER=OPEN
HORIZONTAL_DRAG=OPEN
VERTICAL_DRAG=OPEN
DIAGONAL_DRAG=OPEN
HOLD=OPEN
RELEASE=OPEN
PORTRAIT=OPEN
LANDSCAPE=OPEN
VIRTUAL_PAD=OPEN
FULLSCREEN=OPEN
SAVE_STATE=OPEN
FIREFOX_ANDROID=OPEN or documented exception
```

## Post-physical technical gate

Immediately after the user report:

```text
node --check static/player.js                         PASS
node --check static/offline.js                        PASS
node --check static/service-worker.js                 PASS
PYTHONPYCACHEPREFIX=/tmp/an3-nds-postphysical-pycache compile app.py PASS
bash -n deploy.sh deploy-stage.sh                     PASS
git diff --check                                      PASS
python3 -m unittest discover -s tests -v              PASS (6/6)
STAGING_HEALTH=PASS; environment=staging; asset=def955887c68
```

## Gate

```text
PHYSICAL_BASIC_SMOKE=PASS
PHYSICAL_FULL_MATRIX=PARTIAL
PRODUCTION=untouched and not approved
NEXT_ACTION=Collect the remaining matrix results on the same exact candidate URL, then stop for explicit production approval only if all required evidence is PASS or an exception is documented.
```
