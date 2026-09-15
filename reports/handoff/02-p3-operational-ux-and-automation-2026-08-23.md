# AN3 Arcade P3 handoff — staging and production acceptance complete

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Status: **P3 PRODUCTION DEPLOYED AFTER EXPLICIT OWNER APPROVAL**

## Release facts

| Field | Value |
| --- | --- |
| Workspace | `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade` |
| Branch / committed HEAD | `ui/production-ux-refresh` / `542ef985ddd22435cad00695b065dda1be4f80d3` |
| Worktree | Intentional P3 dirty state preserved; no reset or clean was run. |
| Local P3 fingerprint | `46a5125abb00` |
| Staging asset | `46a5125abb00` |
| Production asset | `46a5125abb00` |
| Staging release | `/opt/an3-arcade-staging/releases/20260823-134927-p2` |
| Rollback target | `/opt/an3-arcade-staging/rollback-snapshots/20260823-134647-pre-p3` → `/opt/an3-arcade-staging/releases/20260823-111241-p215-nds-url` |
| Production code rollback | `/opt/an3-arcade-backups/20260823-142158-p3` |
| Production database rollback | `/srv/an3-arcade/backups/arcade-predeploy-20260823-142158.db` (integrity check PASS before deployment) |
| Production changed | **YES — explicitly approved P3 source-only release** |

Secrets may be used through normal OS/SSH mechanisms but were not printed, committed, or copied into this handoff.

## What was deployed and verified

- P3 source-only staging release: admin Quick Edit, enrichment proposal compare/approve/reject, bounded batch status changes, monitoring UI, and shared non-player design-system work.
- `an3-arcade-staging.service` is active and `/health` reports the P3 asset above.
- Live staging routes passed: homepage, login, register, account redirect, offline, game detail, player, admin redirect, and 404.
- Live authorization/CSRF checks passed: unauthenticated admin API denial; authenticated admin CSRF rejection; admin Quick Edit visibility and safe return path.
- A temporary unpublished staging QA game exercised enrichment comparison, media readiness, approval, rejection, batch preview, wrong typed-confirmation rejection, and successful one-game batch apply. The harness deleted it successfully (`P3_STAGING_ADMIN_QA_CLEANUP=PASS`).
- Full local regression: **22 tests PASS**; Python compile, JavaScript checks, shell syntax checks, and `git diff --check` PASS.
- Production promotion: deployed source hashes match the accepted P3 package; `an3-arcade.service` and `an3-arcade-backup.timer` are active/enabled; production `/health` reports `environment=production` and asset `46a5125abb00`.
- Production public checks passed: homepage, login, register, offline, game detail, player, account/admin redirects, 404, and unauthenticated admin-metrics denial. No production account, staging data, database restore, Cloudflare/tunnel setting, or ROM transfer was used.

## Android and PWA

- Android staging regression: **PASS** on one authorized physical device. Homepage, GBA Pokémon Emerald virtual Start, NDS Pokémon Mystery Dungeon: Explorers of Sky touch/pad/native-menu path, and fullscreen enter/exit all passed against P3 staging. Evidence is under `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/android-regression/` including `2026-08-23-p3-staging-device.txt`, `2026-08-23-homepage-smoke.txt`, `2026-08-23-gba-smoke.txt`, `2026-08-23-nds-smoke.txt`, and `2026-08-23-fullscreen-smoke.txt`.
- Private PWA path: localhost SSH tunnel and `adb reverse` were created for the test and then removed. The Android PWA visibly reported secure context true; the service-worker-controlled app shell cached successfully; the GBA core was downloaded and stored in browser cache; and the shell reloaded after the staging origin became unavailable.
- `PWA_OFFLINE=DOCUMENTED_BLOCKER`: local-ROM selection/startup and a full device-network-off transition were not run because the Android document picker and general connectivity toggle could expose or disturb unrelated personal-device state. No browser security was weakened.

## Known limitations and next action

- The existing staging update script names retained release directories with a `-p2` suffix even when it deploys P3 source; asset fingerprint and health response are the authoritative release identity.
- Firefox Android NDS compatibility was not reopened.
- Production was released only after explicit owner approval. No further production change is authorized without a new explicit request; retain both stated rollback targets.
