# TVBox read-only operations audit

Status: PARTIAL PASS; no host mutation performed.

Observed with bounded read-only SSH commands on 2026-08-11:

- `an3-arcade.service`, `an3-arcade-staging.service`, and `cloudflared.service`: `active`.
- Production and staging application/data paths exist separately, and both environment files are mode `0600`. Secret values were not read.
- Production backup inventory contains `arcade-predeploy-20260809-183156.db` (249,856 bytes).
- No dedicated AN3/SQLite backup timer was found. The only matching timer was `dpkg-db-backup.timer`; scheduled AN3 backup/restore verification remains OPEN.
- Cloudflared is enabled and active, running from a token-file path without exposing the token. Status showed registered tunnel connections, alongside transient `network is unreachable` QUIC errors. This confirms service state, not Cloudflare WAF/rate-limit/Bot configuration.

No service restart, file write, database access, restore, or production deployment was performed.
