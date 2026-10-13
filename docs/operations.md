# AN3 Arcade operations

## Current topology

| Surface | Address | Service/data boundary |
| --- | --- | --- |
| Production LAN | `http://192.168.1.8:8091` | `an3-arcade.service`; `/opt/an3-arcade`; `/srv/an3-arcade` |
| Staging LAN | `http://192.168.1.8:8092` | `an3-arcade-staging.service`; `/opt/an3-arcade-staging/current`; `/srv/an3-arcade-staging` |
| Public | `https://an3tocom.space` | Cloudflare Tunnel to production only |

The accepted production and staging asset is whatever the running service
reports at `/health`; confirm it live before acting on this document. The
published installer inventory is `native-offline/releases/catalog.json` and the
source revision is Git. Large per-run capture reports are not kept in this
repository, so this document cites the catalog and Git rather than a report
file.

## Safety rules

- Begin any production consideration with the latest handoff, `git status --short --branch`, `git rev-parse HEAD`, `git diff --check`, read-only health checks, and the exact staged source boundary.
- Never destructive-clean the intentional dirty worktree. Do not use `git reset --hard`, `git clean -fdx`, or broad checkout.
- Never write passwords, tokens, cookies, pepper values, production user records, device identifiers, or SSH credentials into reports, commands, commits, or documentation.
- For staging SSH, use only the verified key/agent control path in `tools/ssh/README.md`. It must run with password authentication disabled and `StrictHostKeyChecking=yes`.
- Use SQLite Online Backup for backups/snapshots; never raw-copy a live WAL database.
- Production deploy, Cloudflare/tunnel change, production data change, destructive batch operation, and migration each require separate explicit owner approval.

## Baseline validation

```bash
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m py_compile app.py
node --check static/site.js
node --check static/player.js
bash -n deploy-stage.sh deploy/update-staging.sh deploy/update-production.sh deploy/backup-production-current.sh deploy/rollback-production.sh tools/android/*.sh
git diff --check
```

Before an approval request, validate only staging-relevant paths at `http://192.168.1.8:8092`, retain the existing rollback target, and report production as unchanged.

## Lightweight host health summary

Run `deploy/an3-arcade-health.sh` directly on the authorized host for a read-only summary of production/staging health, cloudflared, the backup timer, disk consumption, and both SQLite integrity checks. It does not send telemetry or install a monitoring stack.
