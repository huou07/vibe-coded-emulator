# AN3 Arcade — Migration A2: Target Audit

Date: 2026-08-21 (Asia/Ho_Chi_Minh)  
Status: `READ_ONLY_AUDIT=PASS`; `TARGET_READY_FOR_COPY=NO`

## Safety

This audit was read-only. The protected Wi-Fi secret was redacted; no network, firewall, package, service, or account configuration was changed.

## Host and capacity

| Item | Observed value |
| --- | --- |
| Hostname | `debian` |
| OS | Debian GNU/Linux 13.6 (trixie) |
| Architecture | `x86_64` |
| Kernel | `6.12.101+deb13-amd64` |
| CPU | 20 × 13th Gen Intel Core i5-13500T |
| Memory | 15 GiB RAM; 15 GiB swap |
| Root storage | 460.3 GiB ext4; 1.8 GiB used; 428 GiB available |
| Root inode use | 1% |
| SSH user | `huou07`, with password-authenticated sudo access |

## Network and host controls

| Item | Observed value |
| --- | --- |
| Active NIC | Wi-Fi `wlp0s20f3` |
| Current address | DHCP `192.168.1.8/24` |
| Default gateway | `192.168.1.1` |
| DNS | `192.168.1.11`, then `1.1.1.1` |
| Network stack | ifupdown (`networking.service` active/enabled) |
| Persistent config | `/etc/network/interfaces` (mode `0600`) |
| Current Wi-Fi config | `allow-hotplug wlp0s20f3`, `iface wlp0s20f3 inet dhcp`; protected key redacted |
| Ethernet NIC | `enp0s31f6`, currently down |
| SSH | active on TCP/22 (IPv4 and IPv6) |
| Time sync | NTP enabled and synchronized |
| Firewall | UFW inactive; no active nftables rule set was observed |

No static-IP address, DHCP reservation, or router DHCP-pool information has been supplied. The existing DHCP address must remain active until the owner approves a conflict-checked static address and the second-SSH-session procedure succeeds.

## Application baseline and hardware telemetry

| Item | Observed value |
| --- | --- |
| AN3 production/staging units | absent/inactive |
| AN3 paths | `/opt/an3-arcade`, `/srv/an3-arcade`, `/etc/an3-arcade.env`, and `/opt/an3-arcade-backups` are absent |
| cloudflared | absent |
| Python | 3.13.5 |
| SQLite client | installed (3.46.1) |
| rsync | not installed |
| OpenSSH server | installed (10.0p1) |
| Temperature telemetry | no readable thermal/hwmon sensor files observed |
| Power telemetry | no readable powercap source observed |

## Compatibility matrix

| Requirement | Old | New | Compatible | Action |
| --- | --- | --- | --- | --- |
| Python runtime | CPython 3.13.7 | CPython 3.13.5 | Likely, same minor series | Verify source dependencies before installing only missing requirements. |
| CPU architecture | ARM64 | x86_64 | Yes for Python source; browser EmulatorJS stays client-side | Do not transfer Python bytecode or platform-specific artifacts. |
| Persistent capacity | about 2.3 GiB data on 8.8 GiB free | 428 GiB free | Yes | Preserve data ownership/mode and capture a manifest before transfer. |
| SQLite WAL | Live WAL database | SQLite CLI available; no target DB | Yes | Use consistent online backup, never raw-copy the live main DB. |
| App service | hardened systemd unit, `tvshare:tvshare` | absent | Not yet | Recreate account, paths, env metadata, unit, hardening, and permissions after static-IP gate. |
| Content transfer | Source has application + persistent trees | `rsync` absent | Not yet | Install `rsync` only in target-preparation milestone. |
| Cloudflare Tunnel | token-managed on old host to `127.0.0.1:8091` | absent | Not yet | Prepare a reversible target-side tunnel only after private app parity. |
| Static LAN reachability | old uses `192.168.1.11/24` | new is DHCP `192.168.1.8/24` on Wi-Fi | Not yet | Owner must approve desired static IP and router-pool/reservation safety. |
| Monitoring temperature/power | not needed for migration | unavailable | N/A | Future monitoring must return clean unavailable values rather than estimates. |

## A2 conclusion

`TARGET_BASELINE=PASS`; `TARGET_PREPARATION=BLOCKED_ON_STATIC_IP_DECISION`.

The target is suitable for migration capacity-wise, but it must not receive production traffic before a safe static-IP plan, dependency/account/path replication, data transfer, and private parity testing.
