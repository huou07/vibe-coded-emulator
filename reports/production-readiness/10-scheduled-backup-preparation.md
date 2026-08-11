# Scheduled backup preparation

Status: PREPARED and locally verified; not activated on production.

Added deployment assets:

- `deploy/an3-arcade-backup.sh`: consistent SQLite Online Backup API copy, integrity check, and ROM/cover/screenshot manifest.
- `deploy/an3-arcade-backup.service`: restricted oneshot service using the production environment file and `/srv/an3-arcade` write path.
- `deploy/an3-arcade-backup.timer`: daily persistent timer at 03:30 with randomized delay.
- `deploy.sh` installs and enables the timer during an explicitly approved future production deployment.

Local verification created a backup and manifest from the copied workspace database, returned `integrity_check=ok`, and passed Bash syntax. The script was corrected to avoid GNU-only `find -printf`, so it works on macOS development and Linux TVBox. The updated package was redeployed to staging; staging health and invariants passed.

Production timer activation and restore verification remain pending explicit production workflow/approval.
