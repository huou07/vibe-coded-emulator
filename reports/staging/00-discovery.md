# P2.1b staging discovery

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Classification

**STAGING_FOUND_BUT_BROKEN**

An `an3-arcade-staging.service` instance exists and is active, with a
separate code root, data root, database, and environment file. It is not a
usable P2.1b staging endpoint because it binds only to `127.0.0.1:8092`.
`http://192.168.1.8:8092/health` is refused, whereas loopback health returns
`200`, `environment=staging`, and asset `8664ffc25b5d`.

## Read-only observations

| Item | Observation |
| --- | --- |
| Service | `an3-arcade-staging.service` enabled and active |
| Code root | `/opt/an3-arcade-staging/current` |
| Data root | `/srv/an3-arcade-staging` (`tvshare:tvshare`, `0750`) |
| Environment file | `/etc/an3-arcade-staging.env` (`root:root`, `0600`; values not read or recorded) |
| Listener | `127.0.0.1:8092` only |
| Guardrails | `MemoryMax=1G`, `CPUQuota=200%`, `ReadWritePaths=/srv/an3-arcade-staging` |
| Staging DB | separate SQLite file; integrity check `ok` |
| Production baseline | `an3-arcade.service` active; `/health` reports asset `ef1c8a3df6b8` |

The staging database currently contains 72 games, 72 non-empty ROM metadata
rows, no named UI fixtures, and two current staging sessions. The data tree
also contains a broad media copy. This does not meet the required minimal
two-ROM / 8–15 fixture dataset and must be replaced rather than reused as a
test dataset.

No production file, service, database, asset, tunnel, or firewall rule was
changed during discovery. No environment values, credentials, cookies, or
session material are recorded here.

## Rebuild decision

Reuse the existing service name and staging-specific paths, but replace its
stale staging release data with a freshly created isolated data root. The
rebuild will bind only `192.168.1.8:8092` for LAN access, keep Cloudflare
unchanged, use a SQLite Online Backup snapshot only as the source for the two
authorized test records, clear all copied session/user/community data, copy
only the two selected ROM files, and add synthetic no-ROM UI fixtures.
