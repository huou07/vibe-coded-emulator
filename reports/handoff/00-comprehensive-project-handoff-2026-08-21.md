# AN3 Arcade — Comprehensive Project Handoff

Date: 2026-08-21 (Asia/Ho_Chi_Minh)
Status: **CURRENT PRODUCTION SNAPSHOT**
Audience: future owner / developer / operator
Secrets: **This document intentionally contains no password, token, cookie, SSH credential, Wi-Fi credential, environment value, database user record, or Cloudflare credential.**

## 1. Executive summary

**Ăn 3 Tô Cơm (AN3 Arcade)** is a bilingual Vietnamese/English private game-library website at `https://an3tocom.space`. Python serves the library, authentication, admin tools, SQLite-backed metadata, uploads, ROM byte ranges, and a same-origin EmulatorJS asset cache. Actual emulation is intentionally **client-side**: the browser runs EmulatorJS/WebAssembly/canvas and the server never emulates ROMs.

Production has completed its migration to the current machine at LAN address `192.168.1.8`. The former server is now powered off and is **out of scope** per the current owner instruction. Do not restart, migrate back to, or modify it without a new explicit request.

The current production service, Cloudflare Tunnel, and daily backup timer are active and enabled. The SQLite database is healthy (`PRAGMA integrity_check = ok`) and currently contains 71 games. Admin monitoring and a physical-keyboard autofocus correction have been deployed after the migration.

## 2. Current production at a glance

| Area | Current state |
| --- | --- |
| Public site | `https://an3tocom.space` via Cloudflare Tunnel |
| LAN app address | `192.168.1.8:8091` |
| Health | `/health` returns production status; latest observed asset version `ef1c8a3df6b8` |
| App service | `an3-arcade.service`: active + enabled |
| Tunnel | `cloudflared.service`: active + enabled |
| Backup | `an3-arcade-backup.timer`: active + enabled; daily persistent timer |
| Database | `/srv/an3-arcade/arcade.db`, SQLite WAL, integrity `ok`, 16 tables, 71 games |
| Data footprint | about 2.4 GiB under `/srv/an3-arcade` |
| Access policy | Public play/download; account features require login; admin operations and monitoring require server-side admin authorization |
| Production hostname | `debian` |

### Operational source of truth

The current service, static/network state, and this handoff are more authoritative than older prose in `README.md`.

`README.md` contains historical details that are **not current production configuration**, including the old `.11` LAN address, earlier TV Box/staging instructions, and an older PWA shell marker. Do not copy its deployment target or network values into production commands without reconciling them with the current server inventory below.

## 3. Repository and working-tree state

| Field | Value |
| --- | --- |
| Repository | `an3-arcade` |
| Branch | `ui/production-ux-refresh` |
| Current committed HEAD | `542ef985ddd22435cad00695b065dda1be4f80d3` (`docs(player): add P1 closeout handoff`) |
| Relation to origin | ahead 23 commits |
| Current local validation after monitoring/keyboard work | 19 tests pass; Python compile, Node syntax checks, deploy-shell syntax, and `git diff --check` pass |

The working tree is intentionally dirty. Preserve it. Do **not** use `git reset --hard`, `git clean -fdx`, broad checkout, or history rewrite.

Known dirty/untracked paths at this snapshot include:

- `app.py`, `static/site.css`, `static/site.js`, and `tests/test_integration.py`: include pre-existing enrichment-review work plus current monitoring work; do not discard or blindly deploy as an arbitrary whole package.
- `static/player.js` and `tests/test_regression_invariants.py`: retain prior P0/P1 player invariants and the post-migration physical-keyboard focus correction.
- `tests/test_monitoring.py`: focused admin-monitoring coverage.
- `reports/roadmap/`, `reports/server-migration/`, `reports/handoff/`, and `reports/.DS_Store`: report artifacts; `.DS_Store` must not be committed.

The live production hashes observed on 2026-08-21 match the current workspace for `app.py`, `site.js`, and `site.css`; `player.js` was then deployed as a targeted, backed-up one-file keyboard fix. Test files are local verification material and are not served by production.

## 4. Original direction and non-negotiable architecture

### Product direction

- Small, self-hosted, bilingual web library for games the owner is permitted to distribute.
- Fast browse/search/play experience on desktop and mobile, with a pixel/arcade visual system.
- Public viewing, playing, and downloading; authentication only for social/account actions.
- Admin dashboard for content, accounts, reports, operational analytics, and lightweight current-state monitoring.
- Browser-local offline/PWA library without pretending that it synchronizes user data or shared site content.

### Architecture invariants

1. **Client-side emulation only.** Python streams static ROM/data bytes; EmulatorJS runs in the browser.
2. **NDS uses melonDS and auto-start.** `EJS_startOnLoaded=true`; do not revert to the historical DeSmuME/manual-start path.
3. **NDS ZIP behavior is deliberate.** The original ZIP remains available for download; playable GB/GBA/NDS ZIPs may be safely prepared or delivered so the browser/core infers the correct inner filename.
4. **HTTP Range is required** for ROM/game-file delivery. Real GBA and NDS checks returned HTTP `206` with correct `Content-Range`.
5. **Offline core storage is contractual.** EmulatorJS core records are stored in IndexedDB database `EmulatorJS-core`, object store `core`; AN3 also maintains Cache Storage `an3-arcade-cores-v1`.
6. **PWA offline data is browser-local.** It is not an account sync system and must not be described as one.
7. **NDS virtual-pad/menu layering is contractual.** See `docs/player-layering.md` and section 11 of this handoff.
8. **Never copy a live SQLite main file without WAL discipline.** Use SQLite Online Backup API / `Connection.backup()` for consistent backups and migration snapshots.
9. **No secret exposure.** Do not print, commit, paste, or report environment-file values, password hashes, session material, tunnel tokens, Wi-Fi credentials, or SSH credentials.

## 5. Application layout and data model

### Deployment paths

| Path | Role | Ownership/mode observed |
| --- | --- | --- |
| `/opt/an3-arcade` | application tree | root-owned; current tree about 1.8 MiB |
| `/opt/an3-arcade/app.py` | Python entrypoint | `root:root`, mode `0755` |
| `/srv/an3-arcade` | persistent data tree | app-writable through service allow-list; about 2.4 GiB |
| `/srv/an3-arcade/arcade.db` | SQLite database | application database; WAL journal mode |
| `/srv/an3-arcade/backups` | consistent DB backups and manifests | service write target |
| `/etc/an3-arcade.env` | protected non-secret-listed configuration location | `root:root`, mode `0600`; **values are not in this document** |
| `/etc/cloudflared/token` | protected tunnel token location | `root:root`, mode `0600`; **value is not in this document** |
| `/etc/systemd/system/` | AN3/timer/tunnel unit definitions | root-owned |
| `/opt/an3-arcade-backups` | targeted code rollback archives | used by historical/full deployment and the 2026-08-21 keyboard-fix backup |

### Persistent content directories

- `roms/`: owner-uploaded ROM/archive files.
- `prepared-roms/`: safe extracted handheld ROMs generated from eligible ZIPs for browser play; preserves the original upload/archive.
- `covers/`, `screenshots/`: public artwork/media.
- `proposal-covers/`, `proposal-screenshots/`: admin-only enrichment-review media until approved.
- `uploads/`: resumable upload staging.
- `custom/`: sandboxed HTML5 game assets.
- `emulatorjs-cache/`: same-origin cached EmulatorJS stable/latest assets.
- `backups/`: consistent database copies and content manifests.

### SQLite schema (16 tables)

- Identity/session: `users`, `sessions`.
- Catalogue/community: `games`, `ratings`, `comments`, `favorites`, `reports`.
- Site/admin analytics: `site_settings`, `page_views`, `play_events`.
- Game media/history: `game_screenshots`, `game_updates`.
- Enrichment workflow: `game_enrichment_proposals`.
- Resumable transfer: `upload_sessions`.

Foreign keys are enabled for connections. Database connections enable WAL journal mode and use a bounded timeout. The schema creates/updates additive columns at startup where required.

### Supported system catalogue

The server recognizes GB/GBC, GBA, NDS, 3DS (experimental/latest channel), NES, SNES, N64, PSX, PSP, Mega Drive/Genesis, Master System, Game Gear, Sega 32X/CD/Saturn, FBNeo arcade, 3DO, Atari 2600/7800/Jaguar/Lynx, PC Engine, Amiga, C64, DOOM/PrBoom, and sandboxed HTML5 packages. Detection uses extensions and archive inspection/hints; ambiguous containers are not guessed unsafely.

## 6. Feature catalogue

### Public site and accounts

- Vietnamese/English UI, shared navigation, responsive home/library/game-detail pages, search and system filters.
- Game states: Draft, Testing, Release. All are intentionally public/playable; the state is a classification, not an access restriction.
- Public play/download routes; ROM streaming has Range support.
- Login, register, account page, editable display nickname, return-to-requested-page behavior.
- One 1–5 rating per user/game (updatable), favorites, comments, and issue reports.
- Public recommended grouping favors eligible stable GBA releases.
- Game screenshots, update history, and maintainer contact settings.
- Error/recovery states, fallback artwork, CSP-safe progress components, and mobile library refinement.

### Admin dashboard

- Server-side admin gate for `/admin`, admin content APIs, proposal media, user creation/display names, site contact settings, report state, and destructive content operations.
- Create/edit/delete games; upload ROM, cover, screenshots; system auto-detection.
- Large ROM chunking (8 MiB chunks) and resumable upload sessions with TTL cleanup.
- Batch test-game upload, analytics (visits, visitors, players, top games, 14-day chart), account management, and report triage.
- AI enrichment-review workflow: proposed title/description/cover/screenshots/walkthrough/source links stay pending until an explicit admin approval. ROM is not changed by this workflow.
- **Lightweight real-time monitoring** (`GET /api/admin/system-metrics`): CPU percent, RAM, disk, uptime, app/SQLite probe, CPU/system temperature when a real sensor exists, and power only when a real `power*_input` source exists. It deliberately exposes no raw proc files, process command lines, environment values, passwords, tokens, SSH data, or Cloudflare data.
- Monitoring endpoint is admin-only, returns guest `401` and normal-user `403`, and uses `Cache-Control: no-store`. Dashboard cards refresh every 7 seconds only while the page is visible; hidden pages make no fetch. Cards have Normal/Warning/Không khả dụng/Lỗi states and responsive 4/2/1-column grid behavior.

### Player, controls, and save state

- EmulatorJS player with progress/error state, same-origin asset proxy/cache, fullscreen target, native menu integration, save-state export/import, and five local save slots.
- GB/GBA/NDS custom TVPad: touch buttons, drag layout, opacity, reset controls, global size, per-control size, and safety guards against overlap/off-screen geometry.
- NDS uses A/B/X/Y/L/R/Start/Select and keeps the DS touch screen usable.
- Desktop defaults to physical keyboard/EmulatorJS focus and hides the NDS virtual pad unless requested; touch-first devices default to a pad. The post-migration correction treats a device with hover capability as desktop even if it also has a coarse/touch pointer, so touch-screen desktops retain physical-keyboard autofocus.
- Performance profile storage is local-only (`an3-player-performance-v1`): Auto, Low-end/Battery, Balanced, Quality, Custom. The only admitted profile effect is choosing melonDS legacy compatibility rendering on next launch for Low/custom-legacy. No speculative DPR scaling, frame skipping, thread toggle, shader, or audio-latency setting is exposed.
- Session-only GBA/NDS speed: 0.5×, 1×, 1.5×, 2× using verified EmulatorJS APIs; 1× disables fast/slow mode.
- Native EmulatorJS FPS HUD defaults to `show`; existing compatible user settings are not globally overwritten.

### PWA and offline library

- Web manifest, icons, installable app shell.
- Current service-worker shell cache: `an3-arcade-pwa-v26`; core cache remains `an3-arcade-cores-v1` across shell revisions.
- Browser-local offline ROM library, system grouping, core preload/verification, local play, and removal of cached ROM/core material.
- Save slots/state and player controls are available in offline flow.
- The browser uses the same-origin `/emulatorjs/<stable|latest>/data/...` proxy/cache rather than relying directly on the CDN from every client.

## 7. Current production server inventory

### Hardware and operating system

| Field | Observed 2026-08-21 |
| --- | --- |
| Hardware | Dell OptiPlex Micro 7010 desktop |
| OS | Debian GNU/Linux 13 (trixie) |
| Kernel | Linux `6.12.101+deb13-amd64` |
| Architecture | x86_64 |
| CPU | 13th Gen Intel Core i5-13500T; 20 logical CPUs; 14 cores; 1 socket; 2 threads/core |
| RAM | 15 GiB physical RAM; 15 GiB swap |
| Storage | ext4 on NVMe root filesystem, 452 GiB total; about 421 GiB free at audit |
| Time | `Asia/Ho_Chi_Minh`; NTP synchronized |
| Thermal telemetry | real thermal zones present, including `x86_pkg_temp`, TCPU and coretemp-associated hwmon; observed current temperature was 35.0°C |
| Power telemetry | no reliable power input currently exposed to the app; display `Không khả dụng` |

Do not record hardware serial numbers, UUIDs, machine IDs, or Wi-Fi credentials in future handoffs unless the owner explicitly asks for their inclusion.

### Network and firewall

| Field | Current configuration |
| --- | --- |
| Active interface | `wlp0s20f3` (Wi-Fi) |
| LAN address | static `192.168.1.8/24` |
| Default gateway | `192.168.1.1` |
| Network stack | ifupdown; static profile in `/etc/network/interfaces` |
| DNS | `1.1.1.1`, `9.9.9.9` |
| SSH | TCP/22, IPv4 + IPv6 listener |
| App listener | TCP/8091 on all IPv4 addresses; firewall restricts it to LAN |
| Tunnel metrics | cloudflared local metrics listener `127.0.0.1:20241` |
| UFW default | deny incoming, allow outgoing; low logging |
| UFW allow rules | SSH; TCP/8091 only from `192.168.1.0/24` |

No WAN port forwarding or DMZ is required. Public HTTPS reaches the app through the Cloudflare Tunnel to `127.0.0.1:8091` on this host.

### Relevant installed packages and runtime versions

| Package/runtime | Observed version |
| --- | --- |
| Python | 3.13.5 |
| SQLite client | 3.46.1-7+deb13u1 |
| cloudflared | 2026.8.2 |
| rsync | 3.4.1+ds1-5+deb13u4 |
| curl | 8.14.1-2+deb13u4 |
| OpenSSH server | 10.0p1-7+deb13u4 |
| UFW | 0.36.2-9 |
| systemd | 257.13 |

The application uses Python standard-library modules and SQLite; it does **not** require Prometheus, Grafana, Loki, psutil, Docker, or a time-series database for current-state monitoring.

## 8. Systemd services, hardening, and backup

### `an3-arcade.service`

- Runs `/usr/bin/python3 /opt/an3-arcade/app.py` as `tvshare:tvshare`.
- Starts after `network-online.target`; restarts on failure with 3-second delay.
- Loads a protected environment file without disclosing its content.
- `UMask=0027`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectHome=true`, `ProtectSystem=strict`.
- Only `/srv/an3-arcade` is granted write access through `ReadWritePaths`.
- Memory ceiling: `MemoryMax=512M`.

On Debian the numeric UID differs from the former host because the old numeric UID was occupied by `polkitd`; the `tvshare` service identity and required ownership semantics were preserved.

### Backup service and timer

- Helper: `/usr/local/libexec/an3-arcade-backup`, `root:tvshare`, mode `0750` so the restricted `tvshare` oneshot unit can execute it.
- `an3-arcade-backup.service`: restricted oneshot process using the app environment and `/srv/an3-arcade` as its write path.
- Timer: daily `03:30`, `Persistent=true`, randomized delay up to 15 minutes.
- Backup method: SQLite Online Backup API, integrity check, and persistent-content manifest. It does not raw-copy a live WAL database.
- Latest post-migration/cutover backups were verified with `PRAGMA integrity_check = ok`.

### Cloudflare connector

- `cloudflared.service` is a `Type=notify` unit, waits for network online, restarts on failure, and runs a token-managed tunnel from a root-only token path.
- Token value is not in source, reports, shell history, or this handoff.
- Public ingress observed during cutover forwards `an3tocom.space` to `http://127.0.0.1:8091`.

## 9. Security model

- Password hashes use per-password salt with scrypt when available; PBKDF2 remains only for legacy-read/fallback compatibility.
- Session cookies are HttpOnly, SameSite=Lax, time-bounded, and Secure in HTTPS production; CSRF protects state-changing requests.
- Admin enforcement is server-side. Hiding a UI element in JavaScript is never authorization.
- Authentication, registration, ratings, upload, comments, and reports use rate limits; comment/report paths include anti-spam controls.
- Upload paths, file names, sizes, archive handling, and data-root access are validated. Resumable upload records expire after 24 hours.
- HTTP responses use CSP, HSTS under HTTPS, nosniff, Referrer Policy, Permissions Policy, COOP/CORP, anti-framing policy, and controlled cache headers.
- Public monitoring API is deliberately not public; it contains only rounded aggregate health data and `no-store` cache policy.
- Cloudflare dashboard WAF/rate-limit/Bot configuration was historically only partially verified. Do not claim those cloud-dashboard settings are configured until checked by an authorized owner.

## 10. Migration record and recovery lessons

### Completed migration

On 2026-08-21 the production application/data was migrated from the prior ARM TV Box to this x86_64 Debian host. The migration used:

1. Static-IP preparation and a console-assisted recovery when an unsafe remote Wi-Fi reload lost connectivity.
2. Initial full media seed and later rsync delta.
3. SQLite Online Backup snapshots instead of copying `arcade.db` with its live WAL/SHM sidecars.
4. Private target parity: health, home, GBA/NDS pages, Range requests, guest admin redirect, internal admin test, service worker, backup integrity, ownership, firewall.
5. Tunnel cutover only after target app/data validation; old connector stopped before new connector started.

### Important migration incidents and their fixes

- **Remote Wi-Fi reload disconnect:** applying ifupdown remotely interrupted Wi-Fi. Owner restored DHCP through console; final static configuration was verified after reboot. Future operators must not run `ifdown`/blind network reload over the only Wi-Fi SSH session.
- **Static DNS after reboot:** DHCP-generated resolver state was empty after static boot. Explicit external resolvers were configured and verified.
- **Target stale SQLite WAL/SHM:** a target test database left sidecars that conflicted with final database replacement. The final snapshot’s source/stage hashes were confirmed, stale target sidecars were removed while the app was stopped, then the snapshot was reinstalled and integrity-checked. Never open a newly installed standalone backup against stale WAL/SHM from another database state.
- **Backup-helper permissions:** source helper ownership/mode could not be executed by its `tvshare` unit. Target helper uses `root:tvshare` mode `0750`; a backup then passed.
- **Post-cutover transient outage:** the new host later became unavailable over LAN and public Cloudflare returned HTTP 530. Owner restored the server; SSH/public health were reverified before the keyboard-only deployment. Treat future 530 plus failed LAN ARP as a host/tunnel availability incident, not an application-code error.

The current owner declares the former host powered off and out of scope. Historical migration reports still describe it as rollback material; that is historical evidence, not a current authorization to operate it.

## 11. Historical defects, regressions, fixes, and retained limitations

### Fixed / accepted history

| Area | Symptom/root cause | Resolution / invariant |
| --- | --- | --- |
| Legacy NDS implementation | Stale documentation/offline fallback referenced DeSmuME/manual start | Corrected toward melonDS auto-start; regression coverage added. |
| NDS Android touch | First tap could work but cursor movement did not map correctly; earlier bridge variants sent wrong relative motion | `geometry-mapped` maps live canvas geometry to the DS bottom screen and emits appropriate deltas. It was validated on AVD and owner physical Android scope, then promoted as default. |
| NDS touch stale viewport | Rotation/fullscreen could use stale WebGL geometry | Reject stale viewport geometry and fall back to safe aspect-fit calculation. |
| NDS menu blocked by virtual controls | Refresh stacking placed pad above native EmulatorJS menu; root touch bridge could fall back to an arbitrary canvas | Root gesture begins only on a real `#game canvas`, remains bound to that canvas, and open EmulatorJS menu moves pad below game/inerts controls. |
| Desktop forced virtual pad / keyboard usability | Capability gate was removed during UI refresh and NDS autofocus was suppressed | Touch-first visibility policy with persisted `auto|shown|hidden`; desktop allows normal autofocus/remapping. |
| Touch-screen desktop keyboard regression after migration | Coarse pointer alone misclassified a hover-capable computer as touch-first | Deployed rule requires lack of hover capability before touch-first behavior; physical keyboard/autofocus remain available on touch-screen desktops. Real owner-device confirmation remains desirable after browser cache refresh. |
| Mobile pad vanished on short/fullscreen stage | A safety experiment hid an already-playable pad based on viewport measurement | Retained safety checks for invalid increases/moves but never hides a usable mobile pad. |
| EmulatorJS native menu priority | App option panel could compete with native menu | Player options close before native menu opens and cannot open over an active native menu. |
| PWA speed update | Player speed code changed without cache refresh | Service worker cache/version was refreshed. Current shell marker is v26. |
| AppleDouble deployment contamination | macOS `._*` files altered the server-computed asset version | `deploy.sh` uses `COPYFILE_DISABLE=1` and removes only AppleDouble artifacts in static deploy tree. |
| Initial deploy health parser | Quoting defect caused automatic rollback despite healthy app | Corrected; later deployment verified successful. |
| Backup preparation | Backup helper assumed GNU-only `find -printf` / missing directory | Corrected for macOS/Linux-compatible rehearsal, then verified on Linux. |
| Static-IP cutover | First remote reload severed Wi-Fi management | Console recovery + reboot validation; no blind remote Wi-Fi reload. |
| Admin monitoring | Need operational visibility without heavyweight observability stack | Added cheap admin-only proc/sysfs/disk/SQLite metrics; no Prometheus/Grafana/Loki/time-series DB. |

### Current known limitations / intentionally deferred work

1. **NDS audio crackle on Redmi 15 5G:** reproduced in Firefox/Chrome/Mi Browser, speaker and Bluetooth. Low profile, 1× speed, and VSync change did not prove a fix. This is an accepted P1 known defect. Do not tune interpolation, bitrate, buffer, core, or undocumented runtime options without a new core/runtime feasibility scope.
2. **Installed-PWA offline end-to-end:** UI/core-storage evidence passes, but full network-loss/restart device evidence remains incomplete.
3. **Very large upload path:** resumable chunk logic is tested locally; a full historic 1.7 GiB/3DS route has not been production-validated.
4. **Cloudflare dashboard controls:** WAF/rate-limit/Bot configuration has partial historical review only.
5. **Power monitoring:** no reliable power source is exposed on the new host, so UI must display `Không khả dụng`; do not estimate watts.
6. **Documentation drift:** README uses old server/staging/PWA values. Update it in a separately reviewed documentation task; do not treat it as current ops configuration.
7. **Production staging topology:** legacy reports refer to `.11:8092`. No current dedicated `.8` staging service is established by this handoff. Do not deploy new broad features directly to production without recreating an isolated staging plan and gaining explicit approval.

## 12. Player layering and input contract

Normal layer order:

1. Emulator canvas/game content.
2. AN3 virtual controls (`#tvPad`, normally z-index 26) when shown and safe.
3. Transient HUD/status (z-index 30) and toolbar (z-index 40).
4. AN3 player options (z-index 60) and save-slot surface (z-index 65).

Exception: when native EmulatorJS menu/dialog is visible, it takes interaction priority. Player code adds `emulator-menu-open`; pad becomes z-index 19 and pointer-inert. Never add a sticky player layer above the canvas without rechecking native-menu interaction, keyboard focus, touch, save state, and fullscreen.

NDS direct-touch handling must begin only from an actual game canvas. A touch that starts on a native menu/dialog must not be rebound to a fallback canvas or cause a game gesture.

## 13. Test and validation inventory

### Current local gates

- `python3 -m unittest discover -s tests`: 19 tests pass after monitoring and keyboard focus work.
- Focused monitoring tests cover admin allowed, guest denial, normal-user denial, `no-store`, safe response schema, bounded CPU sample behavior, sensor unavailability, and secret-field absence.
- `python3 -m py_compile app.py`: pass with writable temporary pycache location on macOS.
- `node --check static/site.js` and `node --check static/player.js`: pass.
- `bash -n deploy.sh`: pass.
- `git diff --check`: pass.

The macOS local test host lacks Linux `/proc`; CPU/RAM may correctly be `unavailable` during live endpoint tests there. Deterministic unit coverage checks CPU percentage calculation. The Linux production host provides real `/proc` data.

### Production checks performed in this current state

- Public `/health`: production response and current asset observed.
- Public home page: HTTP 200.
- Guest `/api/admin/system-metrics`: HTTP 401, JSON login-required response, `Cache-Control: no-store`.
- Live services: AN3 and Cloudflare active; backup timer active.
- Database: integrity `ok` and 71 games.
- Live monitoring inputs observed: CPU, RAM, disk, uptime, 35.0°C system temperature; power unavailable.
- Latest keyboard-only deployment: player asset hash matches target; app restart health passed.

The owner’s existing admin session should be used for visual acceptance of monitoring cards and real-device physical keyboard play/remapping. No admin password was read for automation.

## 14. Safe operational runbook

All commands below require an authorized operator on the **current** server. They deliberately omit secrets.

### Health and status

```bash
curl -fsS http://127.0.0.1:8091/health
systemctl is-active an3-arcade.service cloudflared.service an3-arcade-backup.timer
systemctl status an3-arcade.service --no-pager
journalctl -u an3-arcade.service -n 100 --no-pager
journalctl -u cloudflared.service -n 100 --no-pager
```

### Backup verification

```bash
systemctl start an3-arcade-backup.service
systemctl show an3-arcade-backup.service -p Result -p ExecMainStatus
```

Use a temporary SQLite copy/Online Backup for restore testing. Never replace the live database merely to inspect a backup; do not delete WAL/SHM except in a planned, stopped-service recovery scenario with a verified standalone backup.

### Network and firewall verification

```bash
ip -4 -o addr show dev wlp0s20f3
ip route show default
ufw status verbose
```

Do not remotely cycle Wi-Fi/networking through the sole SSH connection. A reboot/console recovery plan is required for static-network edits.

### Targeted rollback for 2026-08-21 keyboard deployment

The immediately previous player asset is retained at:

```text
/opt/an3-arcade-backups/20260821-184200-keyboard-monitoring/player.js
```

Rollback only this file, preserve permissions, restart `an3-arcade.service`, then verify local and public `/health`. Do not restore the database for a static JavaScript rollback.

## 15. Deployment guidance

1. Start with a clean read-only audit: `git status --short --branch`, `git rev-parse HEAD`, `git diff --check`, current server health/services, and current file hashes.
2. Identify the exact changed-file boundary. The repository is dirty; do not package unrelated enrichment or historical P0/P1 edits accidentally.
3. Create a timestamped code backup before production changes. For any DB-affecting deployment, create and integrity-check a consistent SQLite backup as well.
4. Run local tests/syntax checks and an isolated staging plan before a broad feature deployment. Production changes require current owner approval.
5. Install changed files with root ownership/modes, restart AN3 only after the file set is complete, wait through initial connection refusals, and check `http://127.0.0.1:8091/health`.
6. Verify public `/health`, home, relevant user flow, auth boundary, and Range behavior as applicable.
7. Never invoke the legacy default target in `deploy.sh` unreviewed: historical defaults refer to the old `.11` host. Any deployment script must be reconciled to the active `.8` production host and the current owner’s approval.

## 16. Report map

| Location | What it contains |
| --- | --- |
| `reports/bootstrap/` | imported legacy handoff analysis and workspace provenance |
| `reports/production-readiness/` | initial security, backup, deployment, NDS-touch and completion matrix |
| `reports/nds-touch/` | NDS direct-touch experiment/evidence matrix |
| `reports/ui-ux/` | design audit, user journeys, component system, screenshots and QA |
| `reports/roadmap/` | P0 reproduction/current-state/backlog decisions |
| `reports/player-p1/` | capability evidence, performance profiles, speed, pad scaling, validation, production release, closeout |
| `reports/server-migration/` | source/target audit, static IP, data manifest, parity test and final cutover |
| `reports/p2-acceptance/` | P2.15 staging acceptance, rollback preflight, and the owner-approved production deployment record |
| `docs/player-layering.md` | player stacking/input contract |
| `tests/` | integration, auth redirects, regression invariants and monitoring tests |

## 17. Handoff checklist for the next session

- [ ] Read this file, `reports/roadmap/00-current-state.md`, `reports/player-p1/10-handoff.md`, `docs/player-layering.md`, and relevant migration reports before changing player or production behavior.
- [ ] Treat current `.8` host as the only in-scope production server unless owner says otherwise.
- [ ] Preserve the dirty worktree and avoid secrets in console output, tests, commits, reports, and chat.
- [ ] Confirm production service/tunnel/backup status before any operation.
- [ ] Keep client-side emulation, melonDS auto-start, NDS touch bridge, IndexedDB core contract, PWA browser-local model, ZIP/Range handling, and player layer contract intact.
- [ ] Do not reopen accepted NDS audio work or make speculative runtime changes without new owner scope.
- [ ] Verify admin monitoring from an owner-held admin session and keyboard/remapping on the affected physical device after browser cache refresh.
- [ ] Do not change the former powered-off server.

---

This handoff is a snapshot, not a substitute for an operational approval. Treat live service state and current owner instructions as authoritative when they conflict with historical reports.

## 18. P2.1b isolated staging update (2026-08-23)

The historical note that no dedicated `.8` staging service existed is now
superseded. The current staging service is
`an3-arcade-staging.service`, active at `http://192.168.1.8:8092`, listening
only on the LAN address and protected by a UFW rule scoped to
`192.168.1.0/24`. Its code root is `/opt/an3-arcade-staging/current`; its
entire writable root is `/srv/an3-arcade-staging`; its protected environment
file is `/etc/an3-arcade-staging.env`. The service has `MemoryMax=1G`,
`CPUQuota=200%`, and no write access to `/srv/an3-arcade`.

The active staging asset is `9cf7de4b8d0b`. Its database contains two
authorized ROM-backed functional records (Pokémon Emerald/GBA and Pokémon
Mystery Dungeon: Explorers of Sky/NDS) plus ten no-ROM UI fixtures. Sessions,
users, and broad copied production media were removed; a fresh staging-only
authentication pepper is used. The production service remains active on asset
`ef1c8a3df6b8`, and Cloudflare was not changed.

Use `deploy/p2-package-staging.sh`, `deploy/p2-rebuild-staging.sh`, and
`deploy/p2-update-staging.sh` for later staging work. The detailed evidence is
in `reports/staging/`. Authenticated dashboard/monitor sampling and physical
NDS touch/fullscreen/save-state acceptance remain open and do not authorize a
production deployment.

Codex SSH access uses `huou07@192.168.1.8` with a temporary owner-authorized
`SSH_ASKPASS` helper, `SSH_ASKPASS_REQUIRE=force`, `DISPLAY=:0`,
`StrictHostKeyChecking=accept-new`, and a task-local `UserKnownHostsFile`.
The complete secret-safe connection and bounded-`sudo` examples are in
`reports/staging/01-topology.md`. Never store the password in this handoff or
repository, and remove the helper after the task.

## 19. P2.15 owner-approved production deployment (2026-08-23)

The P2.15 candidate accepted in isolated staging was deployed to production
only after explicit owner approval. Production is healthy at asset
`9cf7de4b8d0b` (previous asset: `ef1c8a3df6b8`).

Before the release, a fresh consistent production backup was created at
`/srv/an3-arcade/backups/arcade-20260823-113837.db`, with matching
`rom-manifest-20260823-113837.tsv`; a read-only SQLite integrity check
returned `ok`. A complete pre-release application and service-definition
rollback snapshot remains at
`/opt/an3-arcade-backups/20260823-114004-p215`.

The release installed only vetted application/static/deployment source. It did
not copy or restore staging databases, users, sessions, ROMs, or UI fixtures;
it did not restore a production database. Post-release `/`, `/login`, and
`/offline` returned HTTP 200, the unauthenticated monitor endpoint returned
HTTP 401, and the production application service and backup timer are active.
No rollback was required. See
`reports/handoff/01-p2-15-staging-acceptance-2026-08-23.md` and
`reports/p2-acceptance/07-production-deployment.md` for the complete P2.15
record.
