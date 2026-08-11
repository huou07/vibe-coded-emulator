# AN3 Arcade handoff — 2026-08-11

## Workspace and provenance

- New workspace: `/Users/meomeo/Documents/Codex/2026-08-11/an3-arcade`
- Legacy reference (read-only): `/Users/meomeo/Documents/Codex/2026-08-08/v/outputs/an3-arcade`
- Legacy Git metadata: unavailable; source was copied from the legacy working tree.
- Source baseline commit: `d389e226542436a470a051e37d82da46695fcebd`
- Current repository HEAD: `d142d06a1392da1fb763e37cbce4996c736e26b8`
- Staging release candidate: `fd84f27a0ef006f3931e14ff99be2e12aa3b6091`

## Current architecture

Single-host Python standard-library HTTP app with SQLite WAL and static PWA assets. ROMs, covers, screenshots, and database remain server-side; EmulatorJS/WASM, canvas, saves, and game emulation run client-side. Staging and production use separate service/config/data paths.

## Changes in this session

- Imported the legacy working tree into a new workspace without modifying legacy.
- Added session memory, bootstrap/audit/production-readiness reports, repository safety rules, and this handoff.
- Removed DeSmuME fallback candidates from offline core selection; NDS offline selection is melonDS-only.
- Updated README to document melonDS auto-start, NDS touch bridge, EmulatorJS IndexedDB core storage, report-first selection, NDS ZIP delivery, and PWA limitations.
- Added explicit regression tests for melonDS startup/touch, IndexedDB core contract, report-first selection, persistent cache, and NDS ZIP/Range behavior.

## Verified evidence

- Local baseline: 5/5 tests PASS.
- JavaScript syntax, shell syntax, and Python compilation PASS (compile uses a writable cache prefix because the default environment cache path is restricted).
- Local SQLite Online Backup API rehearsal: integrity check `ok`, WAL mode retained.
- Release package excludes local `data/`, `work/`, tests, reports, and `.codex/`.
- Staging deployment completed for the release candidate; live asset `747d7cd08c55`.
- Staging browser smoke: GBA and NDS reached `Sẵn sàng`; NDS canvas had `pointer-events:auto`, `touch-action:none`, and `data-an3-nds-touch=1`; no browser warning/error logs.
- Staging NDS delivery: ZIP, 46,342,391 bytes; Range `bytes=0-15` returned HTTP 206 and exactly 16 bytes.
- Staging `/offline` UI reports mGBA and melonDS cores downloaded with sizes and enabled delete controls.
- Read-only production HTTPS headers show Cloudflare, HSTS, CSP, no-sniff, and expected security policies; Cloudflare WAF/rate-limit/Bot configuration remains unverified.
- Read-only TVBox audit: application, staging, and tunnel services active; production backup file exists; no dedicated AN3 backup timer found; Cloudflared has registered connections but also transient network errors.
- Added and locally verified scheduled-backup deployment assets (SQLite backup, media manifest, service, timer); not activated in production.
- Production health: PASS, current live asset `7f143995ae30`. Production code was not deployed.

## Open gates

- Save-state export did not produce a browser download event; keep OPEN.
- Real Chrome Android/Firefox Android finger-touch verification remains OPEN.
- Installed PWA offline after network loss/restart remains OPEN.
- Full approximately 1.7 GB 3DS upload remains OPEN.
- Cloudflare WAF/rate-limit/Bot configuration verification remains OPEN.
- Production backup/preflight and explicit production approval remain OPEN.

## Safety status

No production code or database restore was performed. No secrets, passwords, tokens, cookies, or environment values are included here. Do not deploy production until every required gate passes and the user gives explicit production approval.

## Exact next step

Re-run staging health, then complete save-state export and any available staging E2E checks. Resolve the manual/device and Cloudflare gates. Prepare production preflight and stop at `READY_FOR_PRODUCTION_APPROVAL`; do not deploy production without explicit approval.
