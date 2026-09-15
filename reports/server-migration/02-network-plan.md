# AN3 Arcade — Migration A3: Static-IP Network Plan

Date: 2026-08-21 (Asia/Ho_Chi_Minh)  
Status: `AWAITING_OWNER_STATIC_IP_APPROVAL`

## Audited facts

| Field | Value |
| --- | --- |
| New host current address | `192.168.1.8/24` via DHCP |
| New host interface | `wlp0s20f3` (Wi-Fi) |
| Default gateway | `192.168.1.1` |
| DNS currently received | `192.168.1.11`, `1.1.1.1` |
| Network stack | ifupdown (`networking.service`) |
| Persistent config | `/etc/network/interfaces` |
| Existing source address | `192.168.1.11/24` |
| Desired static IP | **Not supplied** |
| DHCP pool / reservation evidence | **Not supplied** |

## Decision gate

No persistent address will be invented. Before any network change, the owner must approve one candidate IPv4 address in `192.168.1.0/24` that is not `.0`, `.255`, `.1`, or `.11`, and provide either router DHCP-pool/reservation evidence or explicit approval that the chosen address is safe to reserve outside the pool.

## Required safe procedure after approval

1. Record the current `/etc/network/interfaces` configuration and exact rollback command without exposing the Wi-Fi secret.
2. Keep the existing SSH session through `192.168.1.8` open.
3. Check candidate availability using more than one signal: ICMP, neighbour table, and ARP probe where supported.
4. Add the candidate temporarily to `wlp0s20f3` while retaining DHCP `192.168.1.8`.
5. Open and verify a second SSH session via the candidate address.
6. Persist the approved address through the detected ifupdown configuration, preserving Wi-Fi authentication configuration and a rollback path.
7. Validate configuration syntax and carefully reload/apply the network configuration.
8. Verify LAN routing, gateway, DNS, Internet reachability, and both SSH sessions.
9. Retire the DHCP/temporary address only after all checks pass and the ownership/reservation decision supports that result.

## Rollback principle

If temporary-address or second-SSH verification fails, retain/revert to the existing DHCP configuration while the original SSH session remains connected. Do not restart networking blindly or replace the only management address.

## 2026-08-21 execution record

Owner selected `192.168.1.8` as the desired static address. Preflight confirmed that it was the new host's active DHCP lease on `wlp0s20f3`; no competing neighbour-table entry was present. `arping` was not installed, so no additional ARP probe could be run.

The persistent ifupdown configuration was written with address `192.168.1.8/24`, gateway `192.168.1.1`, and the existing resolver order. A mode-`0600` DHCP backup was created at `/etc/network/interfaces.an3-migration-dhcp-20260821-1616` and a verified five-minute systemd rollback timer was armed before a detached reload.

The Wi-Fi link dropped during the detached reload. Second-SSH attempts to `192.168.1.8` timed out throughout and after the rollback window. The remote management path is therefore not verified and `STATIC_IP=FAIL/UNVERIFIED`. No data, application service, tunnel, or old-production setting was changed.

**Required recovery:** use local console access to the new host to restore the DHCP backup and restart networking (or reboot) before any further migration action. Do not continue Milestone A until SSH is restored and the active network state is audited again.

## Recovery and safe persistent configuration

The owner restored DHCP through local console and rebooted. Subsequent audit confirmed SSH, gateway, and DNS are healthy. Wi-Fi is operated by `dhcpcd`; forcing `ifdown` removes the active Wi-Fi management path, which caused the failed remote reload. That method is not to be retried over SSH.

The requested static configuration is now persisted in `/etc/network/interfaces` for `wlp0s20f3`:

- address: `192.168.1.8/24`
- gateway: `192.168.1.1`
- DNS: the pre-existing resolver order

A protected DHCP recovery copy was retained on the target host. The active kernel lease deliberately remains DHCP until a planned reboot, so SSH was not interrupted again. The post-reboot check must confirm the address, a non-DHCP default route, gateway, DNS, Internet, and a second SSH connection before recording `STATIC_IP=PASS`.

## Verified post-reboot result

`STATIC_IP=PASS` on 2026-08-21. `wlp0s20f3` is up at `192.168.1.8/24` with a non-DHCP default route through `192.168.1.1`; gateway, Internet, SSH, and persistent ifupdown configuration pass.

The DHCP-generated resolver file was empty after the first static boot even though direct DNS servers were reachable. The target now uses explicit external resolvers (`1.1.1.1`, `9.9.9.9`) both in the static profile and live resolver file; hostname lookup passes. UFW permits SSH and LAN-only TCP/8091. No target tunnel is active.
