# AN3 Arcade P2.15 — Staging Acceptance Handoff

Date: 2026-08-23 (Asia/Ho_Chi_Minh)
Status: **P2.15 PRODUCTION DEPLOYED — owner-approved code/assets-only release verified**

## Scope

This run performed only P2.15 staging acceptance, production-readiness checks, and the subsequently owner-approved production release. No feature work, redesign, Cloudflare change, destructive Git operation, staging-to-production data copy, or production database restore was performed.

## Verified evidence

- Staging is isolated at `http://192.168.1.8:8092`, active on asset `9cf7de4b8d0b`, with a staging-only service and write root. Its current P2.15 release is `/opt/an3-arcade-staging/releases/20260823-111241-p215-nds-url`.
- Before approval, production was healthy on asset `ef1c8a3df6b8`. After the owner's explicit approval, the source-only P2.15 candidate was deployed and production is healthy on asset `9cf7de4b8d0b`.
- Staging guest/normal/admin metrics boundaries returned 401/403/200. Ten consecutive authenticated no-store samples had distinct timestamps. Host CPU-package temperature matched the dashboard (32.0°C), and unavailable power was correctly null/unavailable.
- Staging-only administrator `admin1` signed in successfully. Dashboard monitor cards displayed live data, a subsequent seven-second poll refreshed successfully, the unavailable-power state was visually distinct, and the authenticated dashboard passed 360/390/768/1280/1440/1920 responsive checks plus 390px English layout. Its password is intentionally not recorded in any repository document or handoff.
- Desktop homepage reload soak exceeded 15 minutes without an unsolicited reload; normal browsing retained its scroll position. A real Chrome Android soak also ran 10 minutes 13 seconds while preserving search/filter/no-results state and scroll position, with no unsolicited reload.
- GBA desktop smoke started a live canvas, accepted keyboard focus, opened player settings, and exercised native save/load. On real Chrome Android, Pokémon Emerald started at about 60 FPS, accepted Start from the virtual pad, and entered/exited fullscreen successfully.
- The NDS ZIP player URL was corrected on staging to preserve its archive suffix for EmulatorJS decompression. A fresh Chrome Android session completed startup and passed direct-touch gesture coverage, virtual-pad rendering, player/native menu access, device-local Slot 2 save/load, portrait/landscape, fullscreen enter/exit, and post-fullscreen layout restoration. `PHYSICAL_NDS=PASS` for the required primary Chrome Android browser. Firefox Android remains a documented compatibility limitation: it stays white at 60 FPS with either default or legacy renderer; its device-local profile was restored. See `reports/p2-acceptance/03-physical-nds.md`.
- Public homepage, login, and offline responsive checks passed the six requested widths without document-level horizontal overflow.
- PWA offline E2E is a documented blocker because staging is LAN HTTP, not a secure installed-PWA origin.
- Canonical local suite: 21 tests pass. Python/Node/deploy-shell syntax and `git diff --check` pass.
- Immediately before the release, a fresh consistent production DB backup, `arcade-20260823-113837.db`, and its ROM manifest were created; a read-only `PRAGMA integrity_check` returned `ok`. A complete pre-release code and service-definition rollback snapshot was then retained at `/opt/an3-arcade-backups/20260823-114004-p215`.
- The production deployment copied only the vetted source package (`app.py`, `static`, and deployment definitions). It did not copy or restore `/srv` data, databases, users, sessions, ROMs, or UI fixtures from staging. Production public `/`, `/login`, and `/offline` returned 200 after release; unauthenticated `/api/admin/system-metrics` returned 401; the application service and backup timer are active.

## Acceptance matrix

| Gate | Status |
| --- | --- |
| STAGING_SERVICE | PASS |
| STAGING_ISOLATION | PASS |
| MAIN_PAGE_RELOAD (desktop) | PASS |
| MAIN_PAGE_RELOAD (real mobile) | PASS — 10m13s Chrome Android search/filter/scroll soak retained state |
| ADMIN_MONITOR backend / 10 samples | PASS |
| ADMIN_MONITOR dashboard UI behavior | PASS for authenticated live display, refresh and responsive layout; hidden-tab/failure simulation remains a documented observation limitation |
| TEMPERATURE | PASS |
| POWER | VERIFIED_UNAVAILABLE |
| GBA_SMOKE | PASS — desktop regression plus real Chrome Android startup, virtual Start and fullscreen enter/exit |
| PHYSICAL_NDS | PASS — real Chrome Android touch/fullscreen/device-local-save acceptance complete |
| FIREFOX_ANDROID_NDS | KNOWN_LIMITATION — white canvas at 60 FPS with default and legacy renderer; explicitly not a support claim |
| PWA_OFFLINE | DOCUMENTED_BLOCKER: non-loopback HTTP staging origin |
| VISUAL_ACCEPTANCE public pages | PASS |
| VISUAL_ACCEPTANCE dashboard | PASS |
| RESPONSIVE public and dashboard pages | PASS |
| FULL_TEST_SUITE | PASS (21 tests) |
| PRODUCTION_DEPLOYMENT | PASS — owner-approved code/assets-only candidate now healthy on `9cf7de4b8d0b` |
| ROLLBACK_READY | PASS — fresh integrity-verified DB backup and complete pre-release code/service snapshot retained |

## Production execution record

- Owner approval received: 2026-08-23.
- Pre-release production asset: `ef1c8a3df6b8`; released asset: `9cf7de4b8d0b`.
- Fresh recoverable DB backup: `/srv/an3-arcade/backups/arcade-20260823-113837.db`; integrity check: `ok`; matching ROM manifest: `rom-manifest-20260823-113837.tsv`.
- Full code and systemd-definition rollback snapshot: `/opt/an3-arcade-backups/20260823-114004-p215`.
- The normal production service was restarted only after the snapshot existed. Its health endpoint returned `environment=production` and the released asset. No rollback was required.
- No production account was created or used for post-release authenticated testing. The previously recorded monitor and device acceptance remains staging-only, and the production monitor authorization boundary was verified with its expected unauthenticated 401 response.

## Follow-up scope

Treat Firefox Android NDS white-canvas behavior as a known compatibility limitation for a later, separately scoped diagnosis. Do not represent it as supported.

## Stop condition

`P2.15_PRODUCTION_DEPLOYED`

## Pre-approval payload (historical record)

```text
READY_FOR_P2_PRODUCTION_APPROVAL

SCOPE=P2_RELIABILITY_AND_UI
RELEASE_BASE_SHA=542ef985ddd22435cad00695b065dda1be4f80d3
RELEASE_CANDIDATE=staging release 20260823-111241-p215-nds-url; app.py sha256 7ef4cd4f74e18d18439ba1398c2162a08ac76fcde52d680655ca775f7cd52465
RELEASE_ASSET=9cf7de4b8d0b

STAGING_URL=http://192.168.1.8:8092
STAGING_ASSET=9cf7de4b8d0b
MAIN_PAGE_RELOAD=PASS
ADMIN_MONITOR=PASS
TEMPERATURE=PASS
POWER=VERIFIED_UNAVAILABLE
GBA_SMOKE=PASS
PHYSICAL_NDS=PASS (Chrome Android)
PWA_OFFLINE=DOCUMENTED_BLOCKER (LAN HTTP origin is not a secure installed-PWA context)
VISUAL_QA=PASS
RESPONSIVE_QA=PASS
FULL_TEST_SUITE=PASS (21/21)

PRODUCTION_ASSET=ef1c8a3df6b8
PRODUCTION_CHANGED=NO
BACKUP=latest consistent backup verified; integrity_check=ok
ROLLBACK_TARGET=complete timestamped /opt/an3-arcade backup is created as the first approved-release action

KNOWN_LIMITATIONS=Firefox Android NDS remains white at 60 FPS with both renderer profiles; it is not a support claim
KNOWN_RISKS=the intentional dirty workspace was preserved; the staging release hash above, not a new Git commit, identifies the tested candidate

AWAITING EXPLICIT USER APPROVAL
```
