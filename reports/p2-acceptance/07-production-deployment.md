# P2.15 owner-approved production deployment

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Result

`P2.15_PRODUCTION_DEPLOYED`

The owner approved the P2.15 production release after staging acceptance. Production moved from asset `ef1c8a3df6b8` to the accepted asset `9cf7de4b8d0b` and its health endpoint reports `environment=production`.

## Safety evidence

| Item | Result |
| --- | --- |
| Fresh DB backup before release | `/srv/an3-arcade/backups/arcade-20260823-113837.db` |
| Backup integrity | read-only `PRAGMA integrity_check = ok` |
| Content manifest | `rom-manifest-20260823-113837.tsv` |
| Complete code/service rollback snapshot | `/opt/an3-arcade-backups/20260823-114004-p215` |
| Data migration or restore | none |
| Staging DB/users/sessions/ROMs/fixtures copied | none |
| Rollback required | no |

## Release and post-release smoke

Only the vetted source package was installed: `app.py`, `static`, and service/backup deployment definitions. The production application and backup timer are active. Public `/`, `/login`, and `/offline` returned HTTP 200 after the release; the protected monitor endpoint returned its expected unauthenticated HTTP 401 response.

No production account was created or used. The authenticated monitor samples and physical-device acceptance remain the recorded staging evidence; no staging credential or data was used in production.
