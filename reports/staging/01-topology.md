# P2.1b staging topology

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

| Field | Actual value |
| --- | --- |
| URL | `http://192.168.1.8:8092` |
| Service | `an3-arcade-staging.service` (enabled, active) |
| Listener | `192.168.1.8:8092` only |
| Code root | `/opt/an3-arcade-staging/current` |
| Active release | `/opt/an3-arcade-staging/releases/20260823-111241-p215-nds-url` |
| Data root | `/srv/an3-arcade-staging` |
| Database | `/srv/an3-arcade-staging/arcade.db` |
| ROM root | `/srv/an3-arcade-staging/roms` |
| Asset | `9cf7de4b8d0b` |
| Source revision | `542ef985ddd22435cad00695b065dda1be4f80d3` plus the intentionally dirty P2 candidate |
| Release archive | source-only archive SHA-256 `2c243257c6588599b0a2fc7dd9cd9fa9688a016bddc0e883ca9cea03130b967e` |

The service retains the existing hardening boundary: it runs as `tvshare`, has
`ReadWritePaths=/srv/an3-arcade-staging`, `MemoryMax=1G`, `CPUQuota=200%`,
`ProtectSystem=strict`, `ProtectHome=true`, and `PrivateTmp=true`. It has no
write allow-list for `/srv/an3-arcade`.

UFW permits TCP/8092 only from `192.168.1.0/24` to `192.168.1.8`.
Cloudflare was not changed; the production tunnel and service remain separate.

## Repeatable release process

`deploy/p2-package-staging.sh` creates a source-only archive while excluding
macOS AppleDouble sidecars. `deploy/p2-rebuild-staging.sh` creates/replaces the
isolated staging dataset, verifies health, and rolls back its staging state on
failed health. `deploy/p2-update-staging.sh` performs later code-only release
switches and restores the preceding release on failed health. `._*` files are
removed from staging releases so metadata cannot affect asset identity.

No production code, data, service, asset, firewall rule, or Cloudflare
configuration was changed.

## P2.15 staging acceptance identity

`admin1` is a staging-only administrator created for P2.15 acceptance. It was used to verify the authenticated dashboard and real-time monitor UI. Its password is deliberately excluded from topology, handoff, repository, reports, shell history and commits; use the owner-approved secret channel when access is required. This identity has no production counterpart and does not grant production access.

## Codex SSH runbook

Use the current LAN host and non-root operator account:

```bash
AN3_ASKPASS="$PWD/work/an3-ssh-askpass.sh"
AN3_KNOWN_HOSTS="$PWD/work/an3-known-hosts"
SSH_ASKPASS="$AN3_ASKPASS" SSH_ASKPASS_REQUIRE=force DISPLAY=:0 \
  ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile="$AN3_KNOWN_HOSTS" \
  huou07@192.168.1.8 'hostname && id'
```

`$AN3_ASKPASS` must be a task-local executable (`chmod 700`) that prints the
currently owner-authorized password supplied out of band. Never put that
password in this handoff, the repository, shell history, a report, or a
commit; remove the helper when the task finishes.

For a reviewed, bounded root operation, send exactly one password line to
`sudo` over the encrypted SSH connection. Do not open an unrestricted root
shell and do not use this pattern for unreviewed commands:

```bash
"$AN3_ASKPASS" | SSH_ASKPASS="$AN3_ASKPASS" SSH_ASKPASS_REQUIRE=force DISPLAY=:0 \
  ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile="$AN3_KNOWN_HOSTS" \
  huou07@192.168.1.8 \
  "sudo -S -p '' systemctl is-active an3-arcade-staging.service"
```
