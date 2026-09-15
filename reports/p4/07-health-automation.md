# P4 lightweight health automation

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

Installed the read-only `/usr/local/sbin/an3-arcade-health` helper on the host. It checks production and staging health/asset responses, `cloudflared.service`, the backup timer, both database integrity checks, and `/srv` disk use.

Latest run:

- Production healthy, asset `46a5125abb00`
- Staging healthy, asset `46a5125abb00`
- Cloudflared active
- Backup timer active
- Production and staging SQLite integrity: `ok`
- `/srv` disk: 3% used

`HEALTH_AUTOMATION=PASS`

