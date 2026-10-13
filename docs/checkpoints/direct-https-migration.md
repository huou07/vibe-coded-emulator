# Direct HTTPS migration — an3tocom.space

Branch `feature/phone-controller-cross-platform`, surveyed 2026-10-13.

Status: **READY_FOR_OWNER_ACTION**. The candidate configuration is written and
reviewed. Nothing on the production path has been changed, and the existing
Cloudflare Tunnel is still the live public route.

## What is actually deployed today

Verified on the host, not inferred:

| Fact | Evidence |
| --- | --- |
| Public site is served through a Cloudflare Tunnel | `cloudflared tunnel run --token-file /etc/cloudflared/token` (pid 2142, root); response header `server: cloudflare` |
| Tunnel upstream | `127.0.0.1:8091`, per `deploy/cloudflared-config.yml.example` |
| Production app | `/opt/an3-arcade/app.py`, systemd unit `an3-arcade.service`, user `tvshare`, pid 1368129 |
| Production backend bind | **`0.0.0.0:8091`** — all interfaces, not loopback |
| Staging backend bind | `192.168.1.8:8092` — LAN only, correct |
| Caddy | **not installed**, not running, nothing on :80/:443/:8088 |
| A Caddyfile is deployed but inactive | `/opt/an3-arcade/deploy/Caddyfile` exists; `http_port 8088`, `reverse_proxy 127.0.0.1:8091` |
| Router forwards | 80→8088, 443→8088, 18088→18088, 3478→3478 — the targets 8088, 18088 and 3478 have **nothing listening** |

Reachability of the public IPv4 from the LAN (hairpin):

```
public 123.21.137.86:80    -> Connection refused
public 123.21.137.86:443   -> Connection refused
public 123.21.137.86:8088  -> Connection refused
public 123.21.137.86:3478  -> Connection refused
public 123.21.137.86:18088 -> no answer (filtered)
control 192.168.1.8:8091   -> OPEN
```

The public address answers and refuses, so the router rules reach this host.
Nothing is behind them yet.

## CGNAT and IPv6

| Question | Answer | How it was determined |
| --- | --- | --- |
| Publicly routable IPv4? | **Yes** — `123.21.137.86` | Outbound lookup; address is not private and not in `100.64.0.0/10` |
| Behind CGNAT? | **No** | Not in the carrier-grade NAT range |
| IPv6? | Host has IPv6 on `wg0` (the NetBird overlay). Whether a *global* IPv6 prefix is delegated to the LAN is **UNVERIFIED** from this host | No global-scope IPv6 on the LAN interfaces |

So direct HTTPS is technically feasible on IPv4. Do not assume IPv6 is
available for the same purpose until it is checked on the router.

## Production security probes (read-only, 2026-10-13)

| Probe | Result | Assessment |
| --- | --- | --- |
| `/static/../../../../etc/passwd` | 404 | blocked |
| `/static/%2e%2e%2f...` encoded traversal | 400 | blocked |
| `/.env`, `/AGENTS.md`, `/app.py` | 404 | not served |
| `/.git/config` | 404 | not served |
| Reflected `<script>alert(1)</script>` in `?q=` | 404, no reflection | no XSS |
| Malformed query | `{"error": "not found"}` | terse, no stack trace |
| CORS preflight from `https://evil.example` | no `Access-Control-Allow-*` | no cross-origin access |
| `Host: evil.example` | 403 | rejected |
| `/admin`, `/metrics`, `/debug`, `/api/admin`, `/server-status` | 404 | not exposed |
| `/health` | 200 | intentional |

Response headers already in production are strong and correctly chosen for
EmulatorJS/WASM — `worker-src 'self'`, `object-src 'none'`, no `unsafe-inline`,
plus HSTS, `X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN`,
`Referrer-Policy: no-referrer` and a restrictive `Permissions-Policy`. **Do not
replace this with a generic stricter CSP.** It would break the emulator worker.

## Cloudflare DNS mode decision

The Hostinger screen shows custom authoritative nameservers
(`barbara.ns.cloudflare.com`, `drew.ns.cloudflare.com`), so DNS is served by
Cloudflare and any record change must be made in Cloudflare, not Hostinger.

| Option | What the browser sees | Trade-off |
| --- | --- | --- |
| **A. Proxied (orange cloud), no tunnel** | Cloudflare edge still terminates TLS; origin speaks HTTPS to Caddy over 443 | Keeps WAF, DDoS protection and CDN. Origin IP stays hidden. Origin must still hold a valid certificate. Adds one extra hop, so the latency win is small. |
| **B. DNS-only (grey cloud)** | Browser connects straight to `123.21.137.86` | Removes the Cloudflare HTTP proxy. **Exposes the home IP.** Removes WAF and hides nothing. Latency gain is real but unmeasured here. |

Recommendation: **start with Option A.** It is the smallest change that proves
the new origin works, keeps the DDoS/WAF protection, and keeps the rollback
trivial. Measure Option B only if A proves correct and latency is still the
complaint. Do not assume direct mode is faster — measure it.

## Cutover checklist

Every step is owner/root action. Steps 1–3 change nothing the public depends on.

1. **Bind the backend to loopback.** Edit the systemd unit
   (`EnvironmentFile=/etc/an3-arcade.env`) so the app listens on `127.0.0.1`
   instead of `0.0.0.0`, then `systemctl restart an3-arcade`. This closes the
   current LAN-wide exposure of 8091 regardless of what happens next.
   Confirm: `ss -tln | grep 8091` must show `127.0.0.1:8091`.
2. **Install Caddy** and drop the reviewed config into place:
   ```
   apt install caddy
   install -m 0644 -o root -g root deploy/caddy-production.Caddyfile /etc/caddy/Caddyfile
   ```
   Replace `YOUR_EMAIL@example.com` with a mailbox the owner controls.
3. **Start Caddy** and confirm it obtained a certificate:
   ```
   systemctl enable --now caddy
   journalctl -u caddy -n 50
   ```
   Look for the certificate issuance lines for `an3tocom.space` and
   `www.an3tocom.space`. HTTP-01 validation needs inbound 80, which the router
   already forwards to 8088.
4. **Verify from outside the LAN** (mobile data, not Wi-Fi):
   ```
   curl -I https://an3tocom.space/
   curl -I --resolve an3tocom.space:443:123.21.137.86 https://an3tocom.space/
   openssl s_client -connect an3tocom.space:443 -servername an3tocom.space </dev/null
   ```
   Confirm a valid certificate, correct Host routing, working static assets,
   and a working WebSocket (LAN Sync / Phone Controller) upgrade.
5. **Switch the Cloudflare DNS record** for `an3tocom.space` and
   `www.an3tocom.space`. Leave proxied (Option A) for the first switch.
6. **Only then** stop the tunnel: `systemctl disable --now cloudflared`.
   Do not do this before step 4 passes.

## Rollback

The tunnel is the rollback path and it is still running.

```
systemctl disable --now caddy          # stop competing for 80/443
systemctl enable --now cloudflared     # restore the previous public route
```

DNS reverts by re-enabling the tunnel record at Cloudflare. No data migration is
involved: the application keeps its state in `/srv/an3-arcade` either way.

## Remaining owner items found during this audit

- `/opt/an3-arcade/deploy/Caddyfile` contains a real personal Gmail address as
  the ACME contact. The repository template correctly uses a placeholder. Replace
  it with an owner-controlled address when installing Caddy.
- `0.0.0.0:18880` and `0.0.0.0:18099` are listening on all interfaces and are
  not VCE services — nothing in this repository configures them. Identify them
  and bind them to loopback if they are private tooling. They are **not**
  Internet-exposed today because the router forwards only 80, 443, 18088 and
  3478; keep it that way and do not add forwards for them.
- Remove the router forwards for **18088** and **3478** unless a specific public
  service needs them. Nothing on this host serves either port.
- If any deployed environment still exports `AN3_GOOGLE_CLIENT_ID`, it is now
  inert after the Google sync removal and can be dropped.
