# Staging verification checklist

Status: BLOCKED before deployment — endpoint reachable, SSH authentication unavailable.

Current evidence:

- `http://192.168.1.11:8092/health`: PASS, `environment=staging`, live asset `7f143995ae30`.
- `https://an3tocom.space/health`: PASS, `environment=production`, live asset `7f143995ae30`.
- The new workspace computes asset `c1456f1be95e`.
- `deploy-stage.sh` was attempted and failed at SSH authentication before source transfer. A second attempt using an existing askpass helper was rejected because the credential source was not explicitly authorized for this task. No staging files were changed by these attempts.
- Read-only live inspection shows staging `/static/offline.js` still contains DeSmuME fallback candidates; therefore the new workspace has not reached staging.

## Preconditions

- Confirm `http://192.168.1.11:8092/health` resolves and returns `environment=staging`.
- Confirm the staging service and data paths are separate from production.
- Deploy only the release package produced by `deploy-stage.sh`; do not copy production data.

## Required checks

1. Run `python3 -m unittest discover -v tests` and all syntax/compile checks locally.
2. Run `./deploy-stage.sh`; wait for the script's health polling to pass.
3. Verify `/health`, asset version, and staging environment.
4. Verify `/offline` core preload for GBA and NDS. Confirm IndexedDB `EmulatorJS-core` records and `?EJS_KEYS!`; confirm delete/reload state.
5. Verify GBA and NDS player startup through EmulatorJS state and save-state export. Do not use a black/white automation screenshot as failure evidence.
6. Verify NDS touch with a real touchscreen, including the lower screen, on Chrome Android and Firefox Android where available.
7. Verify NDS ZIP response, HTTP Range, resumable upload, and no production data changes.

Evidence must include command output, URLs/statuses, release identifier, and backup/rollback target. A missing manual check remains OPEN, not PASS.
