# Cross-device sync wiring — staging verification (2026-09-16)

Ordered-plan step 4. Evidence only for what was actually executed.

## What changed

- `app.py`
  - `import sync_engine`; new `sync_settings` table.
  - `SYNC_ENABLED` (staging/development) and
    `GOOGLE_DRIVE_ENABLED` (`AN3_GOOGLE_CLIENT_ID` present). Drive modes are
    advertised disabled and rejected with 409 until owner credentials exist.
  - `sync_mode_catalog`, `sync_mode_status`, `sync_same_subnet`,
    `lan_peer_snapshot` helpers; in-memory LAN registry with a 90 s TTL.
  - Routes (all staging-gated, production 404):
    - `GET/POST /api/sync/settings` — per-device mode (hashed visitor cookie).
    - `POST /api/sync/plan` — one pass through the pure `sync_engine`
      (`entries_from_records` → `build_plan` → `summarize`): direction + reason
      per logical file, transport, conflict counts.
    - `POST /api/sync/resolve` — conflict resolution keep local/remote/both.
    - `POST /api/sync/lan/announce`, `GET /api/sync/lan/peers` — subnet-scoped
      LAN presence.
  - `/sync` page: mode chooser, Drive availability, LAN device discovery.
- `static/sync.js`, `static/site.css`: the sync surface.
- `tests/test_sync_api.py`: 12 tests (settings, Drive gate, plan, resolve, LAN
  scope/TTL, production gating).

Version bump: none (no packaged native artifact changed).

## Build / test

- Full suite: **254 tests, 0 failures**.
- Player guards unaffected but re-run before commit (no player-surface files
  changed in this step).

## Staging deploy

`./deploy-stage.sh` → `STAGING_DEPLOY=PASS`, asset `e792e8578089`, release
`/opt/an3-arcade-staging/releases/20260916-150643-e792e8578089`, rollback
`/opt/an3-arcade-staging/releases/20260916-144055-0e2a7d7a1a3b`.

## Runtime verification (VERIFIED, staging)

- `/sync` → 200.
- `GET /api/sync/settings` → `mode:"off"`, modes `off/lan` available, `drive` and
  `lan_drive` `available:false`, `driveConfigured:false`.
- `POST /api/sync/settings {"mode":"lan"}` → 200 and persisted; `{"mode":"drive"}`
  → 409.
- `POST /api/sync/plan` (local hash `aaa`, remote hash `bbb`, last synced `aaa`)
  → `transport:"lan"`, `direction:"download"`, `reason:"remote-changed"`.
- `POST /api/sync/lan/announce` → peer `device-aaaaaaaa` at `192.168.1.6`,
  `sameSubnet:true`.
- Playwright `/sync`: Drive options disabled, saved `lan`, listed the announced
  peer, **no console errors**. Screenshot:
  `/Users/meomeo/Documents/edit an3tocom apps&web/reports/staging/sync-page-20260916.png`.

## UNVERIFIED

- **Byte-level LAN device-to-device transfer** — the discovery registry and the
  planning/conflict API are implemented and verified; moving the actual save
  bytes between two devices is client/native work and is not implemented here.
- **Google Drive transport** — still needs owner OAuth credentials; the module
  (`google_sync.py`) is unit-tested against an injected transport only.
- A real second LAN device (the registry was exercised from one host plus the
  browser on the same /24).
