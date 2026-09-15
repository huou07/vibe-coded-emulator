# AN3 Arcade — P2.0 Current-State Audit

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Scope: read-only source and live-server audit before P2 implementation.

## Workspace

| Field | Current value |
| --- | --- |
| Workspace | \`/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade\` |
| Branch | \`ui/production-ux-refresh\` (ahead 23) |
| HEAD | \`542ef985ddd22435cad00695b065dda1be4f80d3\` |
| Diff health | \`git diff --check\` passes |
| Dirty tracked files | \`app.py\`, \`static/player.js\`, \`static/site.css\`, \`static/site.js\`, \`tests/test_integration.py\`, \`tests/test_regression_invariants.py\` |
| Dirty untracked paths | \`reports/.DS_Store\`, \`reports/handoff/\`, \`reports/roadmap/\`, \`reports/server-migration/\`, \`tests/test_monitoring.py\` |

The dirty tree is intentional. No reset, clean, checkout, history rewrite, or production deployment has been performed.

## Live production facts

| Field | Status |
| --- | --- |
| Production health | \`PASS\` — environment reports \`production\`; health endpoint responded during the audit |
| Production asset | \`ef1c8a3df6b8\` |
| Production service | \`an3-arcade.service\`: active |
| Tunnel | \`cloudflared.service\`: active |
| Backup timer | \`an3-arcade-backup.timer\`: active |
| Current staging service | inactive; no \`/opt/an3-arcade-staging\` or \`/srv/an3-arcade-staging\` tree exists |
| PWA shell marker | \`an3-arcade-pwa-v26\` |

This confirms that the legacy staging references are not a current staging topology. Production remains untouched while P2 staging is created.

## Reliability findings

### Main-page unsolicited reload

\`static/site.js\` contains a 15-second \`/api/library-version\` poll for the home game grid. If the returned version differs, it calls \`location.reload()\` automatically. This is a confirmed source-level root cause for an unsolicited reload while browsing without a search query.

### Realtime monitor

The dashboard scheduler is present and starts a seven-second polling interval. The service worker currently caches ordinary same-origin GET responses, including \`/api/admin/system-metrics\`. It therefore serves the first monitoring response from Cache Storage on later polls even when \`fetch(..., {cache: "no-store"})\` is used. This is the confirmed source-level root cause of the apparent frozen sample.

### Temperature

The current backend selects the first sorted thermal zone, which is \`INT3400 Thermal\` (20.0°C at audit), not the CPU package. The host exposes both:

- \`thermal_zone4\` — \`x86_pkg_temp\`, 33.0°C at audit;
- \`coretemp\` — \`Package id 0\`, 32.0°C at audit.

P2 will select the CPU-package source deterministically and report its source without exposing raw system files.

### Power

No readable \`power*_input\` file was found. Intel RAPL domains exist, but their \`energy_uj\` counters are not readable by the audited service account. No wattage will be fabricated or enabled by weakening service hardening.

## Invariants retained

Client-side emulation, melonDS auto-start, NDS touch/layering, desktop physical-keyboard behavior, HTTP Range, the EmulatorJS IndexedDB/core cache contract, browser-local offline data, admin-only monitoring, SQLite WAL backup discipline, and production/staging separation remain in force.

## P2 reliability outcome

An isolated staging release is now active on loopback port 8092. It uses a separate release tree, SQLite Online-Backup clone, data directory, environment file, service unit, and sessions-free staging database. It serves asset `8664ffc25b5d`; production remains on `ef1c8a3df6b8`.

The staging service was observed continuously for the P2.2 browsing gate. A deliberate staging-only library fingerprint change produced the non-blocking refresh notice and did not invoke a page reload. The service stayed active without restart or error log throughout the observation. The final health response reports `environment=staging`.

P2.2–P2.5 pass their acceptance criteria:

- user-controlled home-library refresh, retaining query/filter/scroll state for that voluntary reload;
- monitor API cache bypass plus a visibility-aware, bounded polling scheduler; ten samples advanced their timestamps;
- deterministic CPU-package temperature selection, observed at roughly 32–37°C; and
- verified unavailable power telemetry (`null` / `unavailable`) rather than invented consumption.

The owner-admin visual monitor check passes through an already signed-in staging browser session; no credentials were entered into the browser. It showed fresh normal CPU/RAM/disk/temperature/uptime/app states and an explicit unavailable power value. A late JavaScript `null`-to-zero coercion was found during that check, corrected, locally regression-tested, and redeployed only to staging.

## Next action

Reliability Gate passes. Create the shared design-system and page-contract documentation, then apply the approved UI unification only in staging. Production deployment remains blocked on explicit user approval.
