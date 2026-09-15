# P4 approved production release

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Authorization: explicit owner approval received after the P4 approval payload.

## Release result

`PRODUCTION_DEPLOYMENT=PASS`

The production release was performed through direct SSH with strict host-key verification and sudo. It packaged only the current application source and deployment tooling; it did not read or copy staging data.

## Preflight

- Production app source, static asset, application unit, backup script, backup unit, backup timer, and health helper matched the staging-proven source before release.
- Expected production asset: `46a5125abb00`.
- Expected release SHA: `542ef985ddd22435cad00695b065dda1be4f80d3`.

## Release safeguards and outcome

- Retained production application snapshot: `/opt/an3-arcade-backups/20260823-163722`.
- Created and retained consistent predeploy SQLite backup: `/srv/an3-arcade/backups/arcade-predeploy-20260823-163722.db`.
- The backup executable was installed as `root:tvshare` mode `0750`, preserving the timer service's executable access.
- Production service restarted and returned the expected production health/asset contract.
- No database schema migration, production-data import, staging DB/user/session/ROM copy, or synthetic fixture transfer occurred.

## Post-deploy verification

```text
PRODUCTION_POSTDEPLOY_HEALTH=PASS
PRODUCTION_ASSET=46a5125abb00
AN3_ARCADE_SERVICE=active
AN3_ARCADE_BACKUP_TIMER=active
CLOUDFLARED_SERVICE=active
PRODUCTION_DB_INTEGRITY=ok
STAGING_DB_INTEGRITY=ok
STAGING_ASSET=46a5125abb00
PRODUCTION_APP_BACKUP=RETAINED
PRODUCTION_DB_BACKUP=RETAINED
```

The original P4 approval handoff remains an accurate record of the state before this owner-approved production release.
