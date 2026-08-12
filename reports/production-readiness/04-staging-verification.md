# Staging verification checklist

Status: PARTIAL — current staging technical/AVD checks pass; physical Android
acceptance remains open. The host outage below is historical.

Historical bootstrap evidence:

- `http://192.168.1.11:8092/health`: PASS, `environment=staging`, live asset `7f143995ae30`.
- `https://an3tocom.space/health`: PASS, `environment=production`, live asset `7f143995ae30`.
- The new workspace computes asset `c1456f1be95e`.
- `deploy-stage.sh` was attempted and failed at SSH authentication before source transfer. A second attempt using an existing askpass helper was rejected because the credential source was not explicitly authorized for this task. No staging files were changed by these attempts.
- Read-only live inspection shows staging `/static/offline.js` still contains DeSmuME fallback candidates; therefore the new workspace has not reached staging.

## Historical post-deploy evidence

- Staging deployment later completed using the explicitly provided SSH password. The service became `active` after transient startup refusals.
- Staging health then reported asset `747d7cd08c55`; live `player.js` contained melonDS, `EJS_startOnLoaded`, IndexedDB core storage, and report-build handling. Live `offline.js` contained melonDS and marker v7 with no DeSmuME.
- Browser smoke checks reached `Sẵn sàng` for GBA and NDS. NDS DOM evidence showed `class=ejs_canvas`, `pointer-events=auto`, `touch-action=none`, and `data-an3-nds-touch=1`; browser logs had no warning/error entries.
- Save-state download was not observed at that checkpoint, so it was OPEN in
  that snapshot. Later user/device and C02 AVD evidence supersede this state.
- During the subsequent read-only ZIP/Range check, staging became unreachable. Three health polls timed out/refused; SSH service inspection also timed out. Production then returned Cloudflare HTTP 530. This is an external host/runtime outage requiring operator recovery; no reboot or recovery mutation was attempted.
- The TVBox later recovered without intervention. Health after that recovery:
  staging `747d7cd08c55` PASS; production `7f143995ae30` PASS.
- Staging NDS delivery at that checkpoint: `Content-Type: application/zip`,
  `Content-Length: 46342391`, `Accept-Ranges: bytes`. A
  `Range: bytes=0-15` request returned `206`,
  `Content-Range: bytes 0-15/46342391`, and exactly 16 bytes.
- Staging `/offline` browser UI reports `Đã tải mgba · 1.0 MB` and `Đã tải melonds · 1.1 MB`, with delete controls enabled. This verifies the visible offline-core state for GBA/NDS; the in-app browser does not expose Service Worker/CacheStorage APIs for a deeper browser-storage assertion.

## Latest NDS recovery deployment

- Staging commit `15697a634360e3d9ae66bf4b5176333ce53ba5a3`
  deployed successfully; independent `/health` returned
  `environment=staging`, asset `def955887c68`, at
  `2026-08-12T01:10:54+07:00`.
- The full local gate passes 6/6.
- Android 15 AVD passes startup, exact mapped 3x3 targets, all drag axes,
  hold/release, rotation, fullscreen, stale-viewport fallback, and save-state
  serialization. Core-rendered cursor displacement matches the measured scale.
- A real-phone basic smoke now passes startup, click, and cursor movement for
  C02. The remaining Chrome matrix and Firefox/exception remain OPEN, so this
  checklist remains PARTIAL for promotion even though the current staging
  technical checks pass.
- Production was not queried or changed by this staging deployment.

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
