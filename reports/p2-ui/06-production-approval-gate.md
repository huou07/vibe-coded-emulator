# AN3 Arcade — P2 production approval gate

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Release state

| Environment | Service | Asset | Result |
| --- | --- | --- | --- |
| Production | `an3-arcade.service` active | `ef1c8a3df6b8` | Read-only health check passes; no P2 deployment occurred. |
| Isolated staging | `an3-arcade-staging.service` active | `9cf7de4b8d0b` | Isolated LAN topology, minimal dataset, public-page QA, and emulator-canvas smoke checks pass; authenticated/device-only checks remain open. |

## Included P2 work

- LAN-only isolated staging topology and guarded stage-release updater;
- user-controlled home library update notice instead of unsolicited reload;
- service-worker network bypass for live API responses and resilient monitor scheduling;
- CPU-package temperature selection and verified-unavailable power telemetry;
- correction ensuring unavailable power renders as unavailable rather than zero;
- design-system/page-contract documentation and scoped UI QA for library, login, offline, and dashboard.

## Evidence

- `python3 -m unittest discover -s tests`: 21 tests pass.
- Python/JavaScript/shell syntax checks and `git diff --check` pass.
- Staging health, direct LAN reachability, and the separate minimal SQLite/ROM fixture dataset pass after the rebuild.
- Guest admin-metrics access is correctly denied with `no-store`; the ten-sample authenticated monitor check remains open until a staging-only admin account is available.
- Production and staging service health were checked read-only; their asset versions remain different.

## Decision required

Production deployment is intentionally **not** performed. Approve a production release only after reviewing this scope and explicitly authorizing the deployment. Until then, staging remains the candidate and production stays on its current release.
