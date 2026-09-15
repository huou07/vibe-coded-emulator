# AN3 Arcade — Analytics session correction and staging handoff

Date: 2026-08-24 (Asia/Ho_Chi_Minh)  
Scope: correct dashboard Visit/Play session counting and make production-script preparation an enforced staging-release rule. Player source was not edited.

## Production verification before this candidate

The owner-run release completed with `PRODUCTION_RELEASE=PASS`, asset `82a775a3c988`, and retained application backup `/opt/an3-arcade-backups/20260824-082957`. A separate public health check then returned production asset `82a775a3c988`.

## Root cause and correction

`page_views` previously deduplicated one visitor separately for each route. A single browsing session could therefore add separate Visit rows for the home page, a game page, Offline, and the player route. `play_events` used a shorter ten-minute duplicate window.

- Visit is now one visitor session per 30 minutes regardless of route.
- Play is now one visitor + game session per 30 minutes.
- The dashboard applies the same 30-minute session grouping to historical rows, so existing historical chart points no longer count route navigation/reloads as separate visits.
- The chart remains local-calendar-day based and includes the current partial day.

## New staging-release rule

`docs/staging.md` now requires each `deploy-stage.sh` run to confirm all of:

- `PRODUCTION_RELEASE_READY=PASS`;
- `PRODUCTION_RELEASE_SCRIPT`;
- `PRODUCTION_ASSET`.

`tests/test_monitoring.py` has a regression test that checks the deployment script packages the matching production archive, uploads the owner-run script, and prints those required outputs.

## Validation and isolated staging release

- `python3 -m unittest discover -s tests -v`: 27/27 passing.
- Python and JavaScript syntax, deploy-shell syntax, and `git diff --check`: pass.
- Staging SSH key preflight: `STAGING_SSH_KEY_AUTH=PASS`.
- Staging release: `STAGING_RELEASE=PASS`, asset `82a775a3c988`.
- Staging health: environment `staging`, asset `82a775a3c988`.
- Authenticated staging dashboard: both canvases use 14 live session-based daily values, static sample values are absent, and browser console has no errors.

## Prepared owner-run production candidate

The staging deployment prepared but did not run production:

```bash
sudo bash /tmp/deploy-an3-production-20260824-084627.sh
```

Expected asset: `82a775a3c988`.

Production deployment requires a new explicit owner confirmation after this staging candidate is accepted.
