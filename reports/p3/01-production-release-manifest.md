# AN3 Arcade P3.0 — P2.15 production release manifest

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Release identity

| Field | Value |
| --- | --- |
| Production asset | `9cf7de4b8d0b` |
| Staging asset | `9cf7de4b8d0b` |
| Current branch | `ui/production-ux-refresh` |
| Current committed HEAD | `542ef985ddd22435cad00695b065dda1be4f80d3` |
| P2.15 staging release | `/opt/an3-arcade-staging/releases/20260823-111241-p215-nds-url` |
| P2.15 production rollback target | `/opt/an3-arcade-backups/20260823-114004-p215` |
| P2.15 production DB backup | `/srv/an3-arcade/backups/arcade-20260823-113837.db` (historical verified `integrity_check=ok`) |

## Accepted source package

The P2 staging packager at `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/deploy/p2-package-staging.sh` archives exactly `app.py`, `static/`, `deploy/`, and `README.md`. The P2.15 handoff records that the owner-approved production release used the vetted application/static/deployment source package only; it did not copy staging or production data.

| Source evidence | SHA-256 / identity |
| --- | --- |
| `app.py` | `7ef4cd4f74e18d18439ba1398c2162a08ac76fcde52d680655ca775f7cd52465` |
| Current `static/` deterministic fingerprint | `9cf7de4b8d0b` |
| `static/site.js` | `b3e986b345bf15294706ebe6001760a525fae5692502d9e14ef9be4ac7cbd245` |
| `static/site.css` | `a402e9ca031c85f48b36b63a25855f3f032c77060afd3ef374e5ba81992edc80` |
| `static/player.js` | `f9e55c92dbc49e0668b4601159c3c55ff321ed651c934305a00132762ee0d8e6` |
| `static/service-worker.js` | `2c883f5d353dd3ad6bc1f95d7500d903f5cb84632b477c4780b0ae50c95bf40a` |
| `deploy/an3-arcade-staging.service` | `d289600c9d9fb8dc959f94f8598f6f774213492123a5ab8975cce2ee12c0c04e` |

The current `app.py` hash is the deployed P2.15 checksum recorded in `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/01-p2-15-staging-acceptance-2026-08-23.md`. The locally calculated static fingerprint and both live health endpoints agree on `9cf7de4b8d0b`.

## Release safety

- Staging and production remain separate: staging uses `192.168.1.8:8092`; production uses `192.168.1.8:8091`.
- The accepted P2.15 deployment was source/assets-only. No staging database, users, sessions, ROMs, fixtures, or production data are part of this manifest.
- This manifest is provenance only. It neither deploys nor authorizes a production change.

For the working-tree decision and classified dirty paths, see `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/p3/00-repo-reconciliation.md`.
