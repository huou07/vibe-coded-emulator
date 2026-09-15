# P4 local security audit

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Scope: read-only host inspection; Cloudflare dashboard/API access was not provided.

| Control | Observed state | Result |
| --- | --- | --- |
| Production listener | `0.0.0.0:8091` | verified |
| Staging listener | `192.168.1.8:8092` only | verified LAN binding |
| SSH listener and policy | TCP 22 on IPv4 and IPv6; public-key auth enabled; password auth enabled; keyboard-interactive disabled; root login key-only; X11 forwarding enabled; max auth tries 6 | verified |
| UFW / local packet filter | UFW, nftables and iptables tooling/rules are absent | verified; no host firewall is presently enforced by these mechanisms |
| App service identity | both app units run as `tvshare` | verified |
| systemd hardening | `NoNewPrivileges`, `PrivateTmp`, `ProtectHome`, `ProtectSystem=strict`, scoped `ReadWritePaths`, and memory caps present | verified |
| Service exposure analysis | `systemd-analyze security` reports 8.3 EXPOSED because syscall/network allow-list controls are absent and `UMask=0027` is group-readable | recorded follow-up |
| Environment files | `/etc/an3-arcade*.env` are `0600 root:root` | verified |
| Data roots | production `0750 tvshare:tvshare`; staging `0755 tvshare:tvshare` | verified; staging mode is a recorded follow-up |
| Backup root and executable permissions | backup root `0750 tvshare:tvshare`; backup executable `0750 root:tvshare` | verified; executable ownership was repaired so its `tvshare` systemd service can run |
| Cloudflare WAF / rate limit / Bot settings | no authorized dashboard or API evidence | **UNVERIFIED** |

`LOCAL_SECURITY_AUDIT=PASS`  
`CLOUDFLARE_SECURITY=DOCUMENTED_UNVERIFIED`

No Cloudflare, firewall, SSH, systemd-hardening, or production application setting was changed. The backup executable group was corrected as part of the completed restore drill.
