# AN3 Arcade — Migration A8: Private Parity Test

Date: 2026-08-21 (Asia/Ho_Chi_Minh)  
Target: private LAN `192.168.1.8:8091`  
Status: `PRIVATE_PARITY=PASS`

- Target service is active with exact production asset `aa8faa00dc8a`; no Cloudflare Tunnel is installed or active on target.
- `/health`, homepage, and service worker passed. The service worker sends `Cache-Control: no-cache`.
- Real current GBA and NDS player pages passed: `pokemon-emerald` and `pokemon-mystery-dungeon-explorers-of-sky` each return 200.
- Both game-file routes honor `Range: bytes=0-15` with HTTP 206 and correct content-range headers.
- Guest `/admin` redirects to login. Internal admin-login test returned 200 for both login and dashboard; no credential value was printed.
- UFW is active: SSH is allowed and 8091 is LAN-only.
- A target consistent SQLite backup was generated and passed integrity check.

Target service identity uses `tvshare` with a new numeric UID, because source UID 988 is `polkitd` on Debian; name, group ownership, and required modes are preserved.

Source backup helper is `root:root` mode 0750 while its unit runs as `tvshare`, a pre-existing non-functional source permission mismatch. Target helper is intentionally `root:tvshare` mode 0750, allowing the validated backup timer without exposing it to unrelated users.
