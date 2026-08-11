# Baseline

Status: PASS.

Checks:

- `python3 -m unittest discover -v tests`: PASS, 5/5 tests, with approved local-socket access. This includes 2 integration tests and 3 explicit regression-invariant tests.
- `node --check static/player.js`: PASS
- `node --check static/offline.js`: PASS
- `node --check static/service-worker.js`: PASS
- `bash -n deploy.sh`: PASS
- `bash -n deploy-stage.sh`: PASS
- `PYTHONPYCACHEPREFIX=/tmp/an3-arcade-pycache python3 -m compileall -q .`: PASS. The mandated default-cache invocation is environment-blocked by a protected Python cache path; this is recorded as an environment limitation, not a source failure.

The baseline review found and corrected the stale DeSmuME fallback in `static/offline.js`, added `tests/test_regression_invariants.py`, and updated the stale README. Production and staging were not contacted.
