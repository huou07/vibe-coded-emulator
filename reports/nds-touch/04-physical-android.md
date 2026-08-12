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
ALL_DRAG_DIRECTIONS=PASS
HOLD=PASS
RELEASE=PASS
SAVE_STATE=PASS
FULLSCREEN=PASS
CURSOR_ANIMATION=PASS
VIRTUAL_PAD=PASS
PORTRAIT_LANDSCAPE=WAIVED by explicit user instruction; not needed on this phone
FIREFOX_ANDROID=PASS; normal play confirmed
```

This is physical-device evidence and upgrades those three acceptance items beyond
the AVD. Browser name/version, device model, and the rest of the matrix were not
reported, so they are deliberately not inferred.

## Physical acceptance scope

```text
PRIMARY_REAL_PHONE_BROWSER=PASS; browser name/version not reported
FIREFOX_ANDROID=PASS
PORTRAIT_LANDSCAPE=explicitly waived by the user for this phone
UNREPORTED_DEVICE_METADATA=model and browser version
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
PHYSICAL_FULL_MATRIX=PASS with the explicit portrait/landscape waiver
PRODUCTION=untouched and not approved
NEXT_ACTION=Run the final production preflight, then stop for explicit production approval.
```
