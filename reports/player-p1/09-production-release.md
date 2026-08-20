# AN3 Arcade — P1 Production Release

Date: 2026-08-20 (Asia/Ho_Chi_Minh)

## Authorization and scope

The owner explicitly approved production deployment after staging validation and explicitly accepted `P1-KD-001` (NDS mobile audio crackle on Redmi 15 5G) without a fix. P1 is complete; the audio issue is recorded in `08-mobile-follow-up.md` and requires separate future scope.

## Release

- Production health asset: `aa8faa00dc8a`
- Service: `an3-arcade.service` active
- Backup: `/opt/an3-arcade-backups/20260820-225248-p1-production/p1-files.tar.gz`
- Files deployed from validated staging release:
  - `app.py`
  - `static/offline.js`
  - `static/player.js`
  - `static/service-worker.js`
  - `static/site.css`

The five deployed files were verified byte-for-byte against staging after activation. No game data, ROM, save data, emulator cache, or unrelated enrichment work was deployed.

## Validation evidence

- Local suite: 15/15 PASS before release; JavaScript syntax, Python compilation, and `git diff --check` PASS.
- Staging: health PASS; GBA/NDS startup, profiles, speed, pad scaling, settings UX, P0 NDS menu/touch priority, non-fullscreen mobile pad, and FPS-default checks PASS.
- Owner device: save/load, keyboard/remapping, PWA, weak-device performance, speed, mobile pad, and fullscreen paths PASS.
- Production: health endpoint reports `environment: production`; homepage, public GBA play route, and public NDS play route return HTTP 200; player asset contains the FPS-default and canvas-only NDS-touch markers.

The production service restart waits for readiness; no rollback was required. An earlier preflight retry rolled back automatically before release due to a shell health-parser quoting error, not an application fault; production was verified healthy before the successful release.
