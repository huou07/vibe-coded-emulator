# AN3 Arcade — P5 Offline, real-time monitoring, and release handoff

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Scope: reference-led UI maintenance, device-local Offline library correctness, and dashboard operations telemetry.

## Current release state

| Environment | Health | Asset | Result |
| --- | --- | --- | --- |
| Production | pass | `67bc398fc382` | Public health endpoint passes. |
| Isolated staging | pass | `67bc398fc382` | LAN health endpoint passes; dashboard verification passes. |

The production release was owner-authorized and manually started from the server terminal using the prepared, source-only release script. The updater retained an application backup and made a consistent SQLite backup before restarting the service.

## Delivered changes

### Offline page

- Removed the eight decorative/sample game cards and every fixed `14 games` count from **Games on this device**.
- The visible list is now only `#offlineGameGrid`, rendered from the browser's existing device-local IndexedDB records. A device with no imported ROM shows the truthful empty state.
- Restored the previously hidden ROM import fields: game title, system selection, and **Add to this device**. The existing client-side flow detects system from the selected ROM, stores the selected file locally, and then re-renders the real device list.
- Kept ROM privacy intact: Offline ROMs remain in the browser/device and are not uploaded to the server.
- Kept gameplay/player internals and service-worker logic outside this scope.

### Dashboard real-time monitoring

- Replaced fixed reference values with the elements updated by `/api/admin/system-metrics`.
- Restored visible live freshness text and metric status; the existing resilient 7-second monitor scheduler remains in use.
- Temperature now displays the selected CPU-package sensor rather than a fixed visual value. Staging verification observed `41.0 °C`.
- Changed only the operational metric values in **Real-time monitoring** to a readable system monospace font. The dashboard's display/pixel typography remains unchanged elsewhere.

### Power telemetry via turbostat

- Replaced the old best-effort hwmon power scan with a bounded `turbostat` package-power read (`PkgWatt`).
- Added a root-owned, argument-free helper at `/usr/local/libexec/an3-arcade-turbostat`. It calls `/usr/sbin/turbostat` for one short sample and prints only one validated numeric result.
- Added an exact sudoers rule allowing the `tvshare` service account to execute only that helper as root. It does not permit a shell, arbitrary `sudo`, or direct `turbostat` arguments.
- Removed `NoNewPrivileges=true` from the two AN3 systemd service units. This is required for the narrowly scoped helper elevation; the rest of the service hardening and unprivileged application account remain in place.
- The application enforces a four-second subprocess limit and rejects failed, nonnumeric, negative, or implausibly large values. It renders **Không khả dụng** when a valid package-power sample cannot be obtained.
- Verified on staging after installing the helper/unit configuration: power displays `4.05 W` with status **Bình thường**.

## Defects fixed and resolution

| Defect | Cause | Resolution |
| --- | --- | --- |
| Offline list showed game artwork that was not present on the device. | Static reference showcase markup was inserted before the real IndexedDB list. | Removed showcase markup and fixed counts; retain only the runtime grid. |
| A selected Offline ROM could not be added. | Required title/system/submit controls were hidden by reference CSS. | Made the import controls visible and usable. |
| Monitor values, temperature, and freshness appeared frozen. | JavaScript updated hidden runtime nodes while static placeholder nodes remained visible. | The visible nodes now carry `data-metric-value`, `data-metric-status`, and `monitoringUpdated`. |
| Power always showed unavailable after enabling the helper. | The service's `NoNewPrivileges` setting prevented its exact sudo helper from elevating. | Removed that setting only after constraining sudo to the fixed no-argument helper. |
| Monitoring numbers were hard to read. | Reference styling applied the pixel font to operational values. | Applied a readable system monospace font to metric values only. |

## Validation evidence

- `python3 -m unittest discover -s tests -v`: **24/24 passing**.
- Python compile, JavaScript syntax, shell syntax, and `git diff --check`: pass.
- Staging browser check:
  - no sample Offline cards;
  - truthful empty state when no local ROM exists;
  - import file/title/system/submit controls visible and enabled;
  - no browser console errors;
  - monitoring values and statuses populated from the live API;
  - power: `4.05 W`; temperature: `41.0 °C`.
- Read-only health checks confirm both environments report asset `67bc398fc382`.
- Player and PWA asset checks were preserved during the UI/offline work; no game gameplay behavior, database schema, or service-worker behavior was intentionally changed by this P5 scope.

## SSH, staging, and production operating procedure

### Security rules

- Use the approved SSH key and strict host-key verification. Never use password authentication in automation.
- Do not put passwords, private-key material, API tokens, session cookies, or sudo credentials in scripts, command history, reports, or chat.
- Do not use the legacy broad deploy script. Do not copy staging databases, sessions, users, or ROM data to production.
- Staging is isolated and LAN-only. Production deployment always requires a new explicit owner confirmation after the candidate has been tested.

### Staging release and QA

1. Run the test and syntax suite locally.
2. Deploy staging with the approved identity configuration:

   ```bash
   AN3_STAGING_SSH_IDENTITY_FILE=<approved-key-path> ./deploy-stage.sh
   ```

3. Confirm `STAGING_RELEASE=PASS` and the expected `STAGING_ASSET`.
4. In the staging browser, verify the affected UI and functions. For monitoring, wait at least one refresh interval and confirm values, freshness text, and status labels update without console errors.
5. For a first installation or after the turbostat helper/unit changes, run the owner-approved, narrowly scoped server setup script and confirm it returns a numeric watt sample.

### Production preparation (automatic on every staging deploy)

`deploy-stage.sh` now also performs these non-production actions after packaging the staging candidate:

- creates a matching source-only production archive;
- uploads it to `/tmp/an3-arcade-production-<timestamp>.tgz` on the server;
- creates and uploads `/tmp/deploy-an3-production-<timestamp>.sh`, prefilled with the matching static asset;
- prints `PRODUCTION_RELEASE_READY=PASS`, archive path, script path, and asset.

This preparation does **not** restart, modify, or deploy production.

### Owner-run production deployment

1. Owner explicitly approves the exact tested staging candidate.
2. Owner runs the prepared script manually in the server terminal:

   ```bash
   sudo bash /tmp/deploy-an3-production-<timestamp>.sh
   ```

3. Expect `PRODUCTION_RELEASE=PASS`, the expected asset, and a retained application backup path.
4. Perform read-only verification:

   ```bash
   curl --fail --silent --show-error https://an3tocom.space/health
   ```

5. Check the production dashboard with an authorized admin session. Confirm the monitor reports live CPU, memory, disk, temperature, uptime, application health, and package power where supported.

## Relevant files

- `app.py` — Offline markup; safe `turbostat` helper invocation; monitor API wiring.
- `static/site.css` — Offline import control styling and readable monitoring values.
- `static/offline.js` — pre-existing IndexedDB rendering/import behavior used by the corrected Offline UI.
- `static/site.js` — pre-existing live-monitor refresh loop now updates visible nodes.
- `deploy/an3-arcade-turbostat.sh` — fixed root-owned `PkgWatt` helper.
- `deploy/an3-arcade-turbostat.sudoers` — exact helper-only sudo authorization.
- `deploy/an3-arcade*.service` — service unit change required for the narrow helper elevation.
- `deploy/update-staging.sh`, `deploy/update-production.sh`, `deploy-stage.sh` — helper installation and automatic production-release preparation.
- `tests/test_monitoring.py` — validation of fixed helper invocation and invalid output handling.

## Explicit non-inclusions

- No passwords, private keys, tokens, or credential values are recorded here.
- No production database schema migration.
- No production data import from staging.
- No modification of game emulator/player internals or gameplay mechanics.
- No change to PWA/service-worker behavior in this scope.
