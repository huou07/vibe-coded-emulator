# P2.15 production backup and rollback preflight

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Read-only production evidence

| Item | Result |
| --- | --- |
| Production asset after this run | `ef1c8a3df6b8` |
| Production changed | **NO** |
| Backup timer | active; last successful run 2026-08-23 03:40:52 +07 |
| Backup service result | success / exit status 0 |
| Latest verified database backup | `arcade-20260823-034053.db` |
| Latest verified backup integrity | `PRAGMA integrity_check = ok` (opened read-only) |
| Persistent content manifest | `rom-manifest-20260823-034053.tsv` present |
| Existing targeted code rollback artifact | `/opt/an3-arcade-backups/20260821-184200-keyboard-monitoring/player.js` |

## Deployment boundary

`deploy/p2-package-staging.sh` packages only `app.py`, `static`, `deploy`, and `README.md`. The staging update script consumes that source-only archive and does not copy a database, ROM directory, user, session, or fixture into production.

The reviewed local production procedure now defaults to the active `.8` host, health-checks the LAN listener, packages code/assets only, and creates a timestamped complete `/opt/an3-arcade` rollback copy under `/opt/an3-arcade-backups/` before it changes a production file. It retains `/srv/an3-arcade` and never references `/srv/an3-arcade-staging`. Its shell syntax and the full 21-test suite passed. The procedure was **not executed** in P2.15, so production remains unchanged; creating that current code backup is deliberately the first explicit-approval action.

## Preflight status

`ROLLBACK_READY=PASS` for production-approval preflight: the current backup is integrity-verified, the exact rollback procedure is code-only and validated, and its first approved-release action is a complete timestamped code backup. No production deploy or backup creation was triggered in this acceptance run.

## Owner-approved deployment addendum

The owner approved production deployment on 2026-08-23. Before changing the application, the configured backup helper created `/srv/an3-arcade/backups/arcade-20260823-113837.db` and `rom-manifest-20260823-113837.tsv`; the database was opened read-only and `PRAGMA integrity_check` returned `ok`.

The release retained a complete code and service-definition rollback snapshot at `/opt/an3-arcade-backups/20260823-114004-p215`. It deployed only the vetted source package: `app.py`, `static`, and deployment definitions. It did not copy staging data, a database, users, sessions, ROMs, or fixtures, and did not restore any production database.

Production health changed from asset `ef1c8a3df6b8` to the accepted candidate asset `9cf7de4b8d0b` with `environment=production`. Public `/`, `/login`, and `/offline` each returned HTTP 200; unauthenticated `/api/admin/system-metrics` returned HTTP 401; `an3-arcade.service` and `an3-arcade-backup.timer` are active. No rollback was required.
