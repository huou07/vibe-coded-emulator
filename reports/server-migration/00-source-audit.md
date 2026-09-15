# AN3 Arcade — Migration A1: Source Audit

Date: 2026-08-21 (Asia/Ho_Chi_Minh)  
Status: `READ_ONLY_AUDIT=PASS`

## Safety

This audit was read-only. It did not read environment-file values, Cloudflare token values, cookies, user records, or session data. No production service, database, firewall, network, or tunnel setting was changed.

## Host and capacity

| Item | Observed value |
| --- | --- |
| Hostname | `tvbox` |
| OS | Ubuntu 25.10 (Questing Quokka) |
| Architecture | `aarch64` |
| Kernel | `6.12.56-meson64` |
| CPU | 4 × ARM Cortex-A53 |
| Memory | 1.8 GiB RAM; 768 MiB swap |
| Root storage | 14.3 GiB ext4; 4.8 GiB used; 8.8 GiB available |
| Root inode use | 4% |

## Network and host controls

| Item | Observed value |
| --- | --- |
| Primary LAN NIC | `eth0` |
| Source LAN address | `192.168.1.11/24` |
| Default gateway | `192.168.1.1` |
| DNS resolvers | `1.1.1.1`, `9.9.9.9`, local resolver `127.0.0.1` |
| Network stack | `systemd-networkd` active |
| SSH | active |
| Time sync | NTP enabled and synchronized |
| Firewall | UFW active; SSH allowed; production app port `8091/tcp` restricted to `192.168.1.0/24`; staging `8092/tcp` also LAN-restricted |

## Application and runtime

| Item | Observed value |
| --- | --- |
| Production unit | `an3-arcade.service`, active |
| Execution | `/usr/bin/python3 /opt/an3-arcade/app.py` |
| Working directory | `/opt/an3-arcade` |
| Service identity | `tvshare:tvshare` (UID/GID 988) |
| Service hardening | `NoNewPrivileges`, `PrivateTmp`, `ProtectHome`, `ProtectSystem=strict`, `ReadWritePaths=/srv/an3-arcade`, `MemoryMax=512M` |
| Python | 3.13.7 |
| Production listener | `0.0.0.0:8091` |
| Production health | PASS: `environment=production`, asset `aa8faa00dc8a` |
| Staging listener/health | `0.0.0.0:8092`; PASS: asset `49eeea612e77` |

`/etc/an3-arcade.env` exists with owner `root:root`, mode `0600`; only variable names were inspected. The service environment references application/data location, bind host/port, base URL, admin identity/password, cookie policy, and auth pepper. Values were not read.

## Persistent data and database

| Path | Size | Files | Notes |
| --- | ---: | ---: | --- |
| `/opt/an3-arcade` | 1,621,170 bytes | 48 | Application deployment tree; `root:root`, mode `0755` |
| `/srv/an3-arcade` | about 2.3 GiB | 586 | Persistent tree; `tvshare:tvshare`, mode `0750` |
| `roms` | 2,177,179,174 bytes | 71 | Persistent content |
| `prepared-roms` | 226,077,436 bytes | 11 | Persistent content |
| `covers` | 12,176,830 bytes | 96 | Persistent content |
| `screenshots` | 7,345,828 bytes | 215 | Persistent content |
| `proposal-covers` | 1,447,110 bytes | 37 | Persistent content |
| `proposal-screenshots` | 4,083,677 bytes | 111 | Persistent content |
| `emulatorjs-cache` | 28,083,401 bytes | 31 | Preserve exact deployed cache |
| `backups` | 4,706,304 bytes | 11 | Existing persistent backups |
| `uploads`, `custom` | 0 bytes | 0 | Present but empty at audit |

Live SQLite database: `/srv/an3-arcade/arcade.db`, `tvshare:tvshare`, mode `0640`.

- Journal mode: `wal`
- Integrity: `ok`
- Tables: 16
- Main database: 1,171,456 bytes
- Live WAL: 4,136,512 bytes
- Shared-memory file: 32,768 bytes

The live WAL is material. Migration must use a consistent SQLite backup, not a raw main-DB copy or a blind copy of WAL/SHM files.

## Backup and tunnel topology

- `an3-arcade-backup.timer` is enabled for daily backup at 03:30 with up to 15 minutes randomized delay.
- The existing P1 deployment archives remain under `/opt/an3-arcade-backups/`; the accepted production rollback archive is present.
- `cloudflared.service` is active on this host and is token-managed. Secret token data was not read.
- Cloudflared logs verify ingress rule 0 forwards to `http://127.0.0.1:8091`. Therefore a migration cannot change the public origin merely by copying application data; Cloudflare Tunnel configuration/service must be cut over after private parity passes.

## A1 conclusion

`SOURCE_BASELINE=PASS` and `OLD_SERVER_PRESERVATION=REQUIRED`.

The old server remains the only public writable production origin and the rollback target. No migration/cutover action has been performed.
