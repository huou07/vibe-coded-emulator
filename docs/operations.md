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
- Production deploy, Cloudflare/tunnel change, production data change, destructive batch operation, and migration each require an explicit owner authorization that is current for the task. The owner instruction dated 2026-10-18 authorizes releasing versions that pass the exact-SHA CI gate and the recorded acceptance to the web production path ([`release.md`](release.md)); it is not a standing approval for unrelated production changes.

## Storage and retention

Release machinery writes outside the repository, so an unbounded history fills
the host rather than showing up as a repository problem. On 2026-10-19 that
reached 90% of a 452 GiB root: 51 production application snapshots (55 GiB), 169
staging releases (54 GiB) and failed-release records, none of it pruned by the
scripts that created it. Each writer now bounds itself.

| Variable | Default | Writer | Keeps |
| --- | --- | --- | --- |
| `AN3_BACKUP_KEEP` | `7` | `deploy/backup-production-current.sh` | newest production application snapshots under `/opt/an3-arcade-backups` |
| `AN3_STAGING_KEEP` | `3` | `deploy/update-staging.sh`, `deploy/rebuild-staging.sh` | the release `current` points at, the previous release, and the newest of the rest |
| `AN3_FAILED_RELEASE_KEEP` | `2` | `deploy/rollback-production.sh` | failed-release records under `/opt/an3-arcade-failed-releases` |

Pruning runs only after the operation in question is verified healthy, so a
failed release never loses its evidence. A pruned application snapshot is
recoverable from Git plus the SQLite snapshot under `/srv/an3-arcade/backups`; a
pruned staging release is recoverable from its release archive. Live data under
`/srv/an3-arcade`, the `current` symlink target, the newest application snapshot
and the newest failed-release record are never pruned by these variables.

## Disposable local build and scratch output

These paths are reproducible and excluded by Git. Remove them when
`tools/disk-preflight.sh` reports pressure, before a build stops on the reserve:

- `work/` — local scratch, including `work/pycache` and `work/cargo-home`.
- `native-offline/src-tauri/target/` and `native-offline/dist/` — native and web build output.
- `native-offline/node_modules/` — restored by `npm ci` in `native-offline`.

Committing build output is never the fix. If pressure returns, check the
retention variables above before deleting source, data or a retained release.

## Baseline validation

```bash
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m py_compile app.py
node --check static/site.js
node --check static/player.js
bash -n deploy-stage.sh deploy/update-staging.sh deploy/rebuild-staging.sh deploy/update-production.sh deploy/backup-production-current.sh deploy/rollback-production.sh tools/android/*.sh
git diff --check
```

Before an approval request, validate only staging-relevant paths at `http://192.168.1.8:8092`, retain the existing rollback target, and report production as unchanged.

## Lightweight host health summary

Run `deploy/an3-arcade-health.sh` directly on the authorized host for a read-only summary of production/staging health, cloudflared, the backup timer, disk consumption, and both SQLite integrity checks. It does not send telemetry or install a monitoring stack.
