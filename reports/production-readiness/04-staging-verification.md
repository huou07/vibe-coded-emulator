# Staging verification checklist

Status: PARTIAL — deployment and browser smoke passed; host outage interrupted remaining checks.

Current evidence:

- `http://192.168.1.11:8092/health`: PASS, `environment=staging`, live asset `7f143995ae30`.
- `https://an3tocom.space/health`: PASS, `environment=production`, live asset `7f143995ae30`.
- The new workspace computes asset `c1456f1be95e`.
- `deploy-stage.sh` was attempted and failed at SSH authentication before source transfer. A second attempt using an existing askpass helper was rejected because the credential source was not explicitly authorized for this task. No staging files were changed by these attempts.
- Read-only live inspection shows staging `/static/offline.js` still contains DeSmuME fallback candidates; therefore the new workspace has not reached staging.

## Post-deploy evidence

- Staging deployment later completed using the explicitly provided SSH password. The service became `active` after transient startup refusals.
- Staging health then reported asset `747d7cd08c55`; live `player.js` contained melonDS, `EJS_startOnLoaded`, IndexedDB core storage, and report-build handling. Live `offline.js` contained melonDS and marker v7 with no DeSmuME.
- Browser smoke checks reached `Sẵn sàng` for GBA and NDS. NDS DOM evidence showed `class=ejs_canvas`, `pointer-events=auto`, `touch-action=none`, and `data-an3-nds-touch=1`; browser logs had no warning/error entries.
- Save-state download was not observed, so save-state export remains OPEN.
- During the subsequent read-only ZIP/Range check, staging became unreachable. Three health polls timed out/refused; SSH service inspection also timed out. Production then returned Cloudflare HTTP 530. This is an external host/runtime outage requiring operator recovery; no reboot or recovery mutation was attempted.
- The TVBox later recovered without intervention. Current health: staging `747d7cd08c55` PASS; production `7f143995ae30` PASS.
- Current staging NDS delivery: `Content-Type: application/zip`, `Content-Length: 46342391`, `Accept-Ranges: bytes`. A `Range: bytes=0-15` request returned `206`, `Content-Range: bytes 0-15/46342391`, and exactly 16 bytes.

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
