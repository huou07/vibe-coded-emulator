# Scheduled backup preparation

Status: PREPARED and locally verified; not activated on production.

Added deployment assets:

- `deploy/an3-arcade-backup.sh`: consistent SQLite Online Backup API copy, integrity check, and ROM/cover/screenshot manifest.
- `deploy/an3-arcade-backup.service`: restricted oneshot service using the production environment file and `/srv/an3-arcade` write path.
- `deploy/an3-arcade-backup.timer`: daily persistent timer at 03:30 with randomized delay.
- `deploy.sh` installs and enables the timer during an explicitly approved future production deployment.

Local verification created a backup and manifest from the copied workspace database, returned `integrity_check=ok`, and passed Bash syntax. The script was corrected to avoid GNU-only `find -printf` and to create the backup directory before `mktemp`, so it works on macOS development and Linux TVBox. The backup-fixed package was redeployed to staging; staging health passed with asset `747d7cd08c55`.

The script was also run against staging Linux data at `/srv/an3-arcade-staging`: SQLite integrity returned `ok`, WAL mode was retained, the database backup and manifest were mode `0600`, and the manifest contained 2 entries. A corrected staging restore drill copied the backup to a temporary database, returned integrity `ok`, found 15 tables and 2 games, then removed only the temporary restore. Production timer activation and production restore verification remain pending explicit production workflow/approval.
