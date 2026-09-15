# AN3 Arcade — Offline PWA and Rust gateway staging handoff

Date: 2026-08-24 (Asia/Ho_Chi_Minh)  
Scope: safe refactor delivery to isolated staging only. Production was not
contacted, changed, cut over, or deployed.

## Release state

| Surface | Status | Evidence |
| --- | --- | --- |
| Existing Python staging app + Offline PWA | deployed and retained | public health at \`192.168.1.8:8092\` reports asset \`c59445f5a677\` |
| Existing Python staging rollback | retained | \`/opt/an3-arcade-staging/releases/20260824-160210-ab2ef82683e4\` |
| Rust gateway + Redis Docker shadow | deployed, loopback-only | release \`/opt/an3-rust-shadow-staging/releases/20260824-183759-f40597961920\` |
| Production | untouched | \`STAGING_SHADOW_PRODUCTION_EXECUTED=NO\`; no production helper or cutover was run |

The normal public staging endpoint remains the existing Python service at
\`http://192.168.1.8:8092/\`. It was intentionally not replaced. Its
read-only health response is \`{"ok": true, "environment": "staging",
"asset_version": "c59445f5a677"}\`.

The Rust shadow is reachable only on the staging host at
\`127.0.0.1:18093\`; it proxies to the Python staging endpoint and adds
\`x-an3-gateway: rust-shadow\`. Redis is reachable only at
\`127.0.0.1:16379\`. Neither has a Docker-published port.

## Immutable rollback material

Do not delete or overwrite any of these paths.

- Full local project snapshot:
  \`/Users/meomeo/Documents/Codex/2026-08-24/users-meomeo-documents-codex-2026-08-3/outputs/an3-arcade-backups/an3-arcade-pre-refactor-20260824-20260824-165102.tar.gz\` —
  SHA-256 \`2a8b236b60ea5db1c2e1fd9a889d4b0fc61d642c6ed8c5f9483bcbd9470d2ea9\`;
  gzip test passed.
- Local SQLite copies and the complete rollback record:
  \`/Users/meomeo/Documents/Codex/2026-08-24/users-meomeo-documents-codex-2026-08-3/outputs/an3-arcade-backups/\`.
- Restricted staging snapshot:
  \`/var/backups/an3-arcade-staging/20260824-165800-pre-rust-refactor\`.
  - \`staging-code-tree.tar.gz\` — SHA-256
    \`26e1d38d806cae5965b895cec01da73148a01851e8db1c8244dc9fa05349e68d\`.
  - \`staging-data-excluding-live-sqlite-quiesced-20260824-170500.tar.gz\` —
    SHA-256
    \`a339c8525733dad2f6e95f1d7d0273418ba5e7efeebd91345651387ce14d8ba7\`.
  - \`arcade-20260824-170053.db\` — integrity checked before release; SHA-256
    \`a4b47da58cc2546382544ed8be112874370c896882d356987166cf139870109d\`.

No database migration, deletion, data copy, ROM copy, session copy, backup
deletion, or Redis volume deletion was performed.

## Delivered Offline PWA

\`/offline-app/\` is a standalone anonymous, game-only application. It
deliberately omits account, dashboard, admin, analytics, CSRF, and server-side
library data. ROMs, save data, and selected core assets stay in browser-local
IndexedDB and Cache Storage; the player uses the established local
\`AN3OfflineLibrary\` contract without uploading a ROM.

- The page recognizes supported ROM file names and ZIP hints, offers local
  save/play/download/delete actions, and retains the existing player toolbar,
  save slots, touch control, options, performance profile, and virtual pad.
- The existing Nintendo 3DS Azahar path is preserved and is available in the
  core chooser when the browser/device supports it.
- The dedicated worker caches only the Offline PWA shell and permitted emulator
  core assets. Its cache name carries the deployed asset fingerprint, so a new
  release updates the shell instead of silently reusing stale files.
- \`Tạo shortcut trên máy\` invokes the browser-native install prompt when the
  browser offers one; otherwise it exposes browser-specific shortcut guidance.
  The browser, rather than application JavaScript, creates the desktop
  shortcut.
- Nintendo Switch files (\`.nsp\`, \`.xci\`, \`.nca\`, \`.nsz\`, \`.xcz\`) are
  recognized and explicitly blocked from save, core preload, and launch.
  There is no working web Switch core in this release, so no fake or unsafe
  launcher was added. The current official EmulatorJS core list includes
  \`azahar\` for 3DS but no Switch core:
  <https://emulatorjs.org/docs4devs/cores/>.

The LAN staging service is plain HTTP. The route is deployed there, but real
Service Worker/PWA install behavior needs HTTPS (or localhost) in a browser.
It was verified through a temporary localhost-only strict SSH tunnel; adding a
certificate, public hostname, or tunnel requires a separate owner decision.

## Rust / Redis / Docker implementation

The Rust work is a safe first phase, not a claim that all business logic was
rewritten. Python remains the source of truth for application routes, SQLite,
player behavior, database contents, and existing feature logic. This preserves
the current UI and core behavior while exercising a performant Rust edge path.

- \`rust-gateway/\` contains an Axum streaming reverse proxy with bounded,
  best-effort Redis caching only for anonymous cacheable public GET responses.
  Uploads, ROM/download paths, Range requests, private/app/admin/API/auth/
  offline paths, and uncached responses bypass Redis and preserve streaming.
- Cache HIT responses recalculate \`Age\`; the cache cannot extend an upstream
  freshness lifetime.
- Docker was started only after explicit owner authorization. Immediately after
  activation no unrelated container was auto-started; this was checked before
  starting the shadow release.
- The current Compose topology uses host networking solely to avoid changing
  the host firewall. It binds the gateway to \`127.0.0.1:18093\` and Redis to
  \`127.0.0.1:16379\`; Docker port bindings are empty. The gateway has no
  mounts. Redis has only its named cache volume
  \`an3-rust-shadow-staging-redis-data\`, not the application database.
- The release source archive is
  \`/opt/an3-rust-shadow-staging/incoming/an3-rust-shadow-staging-20260824-183706.tgz\`
  (SHA-256
  \`f405979619201570721ae97fbd2a19d919ca4fe0b9ad4c2552f6e2c96e9e5dab\`).
  Its immutable image is
  \`an3-arcade/rust-gateway-shadow:staging-f405979619201570721ae97fbd2a19d919ca4fe0b9ad4c2552f6e2c96e9e5dab\`,
  image digest
  \`sha256:5b728bef92b16ef42118bf2737f85cb42f6560ddeb979c94cd8b17a4b8b532fa\`.
- The staging helper retains source archives/releases and uses immutable
  archive-digest image tags. Recovery/rollback refuses a rebuild and uses
  \`--no-build\` only when the retained image identity exists. This is the first
  Rust shadow release, so its recorded Rust rollback target is
  \`none-first-release\`; the independently retained Python staging rollback
  above remains available.
- Cutover helpers fail closed (\`exit 64\`). No listener, systemd unit, legacy
  service, database, ROM, session, backup, or production target was altered by
  them.

## Validation completed

- \`python3 -m unittest discover -s tests -v\`: **32/32 passed**.
- The Docker image build ran \`cargo test --locked\`: **8/8 Rust tests passed**,
  then \`cargo build --release --locked\` passed.
- Python compilation, syntax checks for \`site.js\`, \`player.js\`,
  \`offline.js\`, \`offline-app.js\`, and its worker: passed.
- Bash syntax for staging/shadow scripts, Compose rendering, package smoke
  checks, and \`git diff --check\`: passed.
- Strict SSH preflight: \`STAGING_SSH_KEY_AUTH=PASS\`.
- Staging route checks: \`/offline-app\` returns \`303\` to \`/offline-app/\`;
  the Offline shell/controls are present; worker cache name is
  \`an3-offline-app-shell-c59445f5a677\`.
- Browser smoke checks used synthetic non-user ROM fixtures only: GBA
  detection, local library save/play UI, Switch detection/blocking, player
  controls, core/UI save, and offline reload were exercised. The synthetic
  invalid ROM naturally cannot boot a real game; it did not produce an
  app-shell error.
- A temporary localhost-only tunnel loaded the exact staging PWA; shortcut,
  save-offline, and local-ROM controls were enabled, the Switch deferred panel
  was visible, and browser console errors were empty. The tunnel and temporary
  browser tab were then closed.
- Post-deploy Rust shadow verification passed:
  - legacy public health on \`192.168.1.8:8092\` still reports the same staging
    asset;
  - gateway health returned \`200\` with \`x-an3-gateway: rust-shadow\`;
  - static asset cache returned \`MISS\` then \`HIT\` (with \`Age: 0\`);
  - a Range request and \`/offline-app/\` returned \`BYPASS\`;
  - Redis returned \`PONG\`;
  - IPv4 listeners were exactly \`192.168.1.8:8092\`,
    \`127.0.0.1:18093\`, and \`127.0.0.1:16379\`.

## Deployment rule retained

Every normal staging release may prepare a matching production review
archive/script, but Codex never executes it. For the Rust release,
\`STAGING_SHADOW_PRODUCTION_EXECUTED=NO\` means exactly that: **no production
deployment**. Production requires a new explicit owner approval and a separate,
reviewed owner-run procedure after validation; it was not requested or
performed here.
