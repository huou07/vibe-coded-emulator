# AN3 Arcade — Migration A10: Final Cutover Plan

Date: 2026-08-21 (Asia/Ho_Chi_Minh)  
Status: `PASS — CUTOVER COMPLETE`

## Passed gates

`STATIC_IP`, target baseline, initial data seed, initial DB integrity, private parity, target backup, and SSH access to both hosts all pass.

## Completed cutover (2026-08-21)

- Owner approval was received for the final freeze, protected token transfer, and traffic switch.
- The old AN3 service was stopped; a final SQLite Online Backup passed `PRAGMA integrity_check = ok` and contained 71 games.
- The frozen non-DB delta transferred 28,667 bytes. Source, staged, and installed final DB hashes were matched after stale target WAL/SHM sidecars were removed; target integrity check was `ok`, with 71 games.
- Target AN3, Cloudflare Tunnel, and the backup timer are active and enabled. The tunnel token is installed as `root:root` mode `0600`; the temporary staged token was removed without its value being printed.
- Public HTTPS `/health` returns production status; public GBA byte-range streaming returned `206` and guest `/admin` redirects to `/login`.
- New host networking is persistent at `192.168.1.8/24`, default route via `192.168.1.1` on `wlp0s20f3`.
- A post-cutover database backup passed integrity verification.
- The old AN3 and Cloudflare services are stopped and disabled, but their files and data are retained for rollback.

## Required final sequence

1. Owner approval received for the short old-production write freeze and public-origin switch.
2. Protected token privately transferred without printing, committing, or reporting its value.
3. x86_64-compatible cloudflared installed on target and verified before activation.
4. Old writes frozen; final SQLite Online Backup and frozen non-DB delta installed and verified on target.
5. Old tunnel stopped before the target tunnel was started. At no point were two writable origins active against divergent SQLite data.
6. Public health, guest admin protection, GBA HTTP Range, target logs, service state, backups, and network route verified. Old host retained for rollback.

## Rollback

If public validation fails: stop target tunnel, restore/start old app if necessary, start old tunnel, and validate old public health. Do not delete or repurpose the old host.
