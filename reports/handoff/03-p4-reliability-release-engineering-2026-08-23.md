# P4 reliability and release-engineering handoff

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Scope: P4 staging/reliability closure. Production was not deployed or copied from staging.

## Result

All P4 completion gates passed. Production remains on the already-deployed P3 asset; staging is on the final P4-verified release.

| Item | Final state |
| --- | --- |
| Release SHA | `542ef985ddd22435cad00695b065dda1be4f80d3` |
| Production asset | `46a5125abb00` |
| Staging asset | `46a5125abb00` |
| Final staging release | `/opt/an3-arcade-staging/releases/20260823-154343-46a5125abb00` |
| Retained rollback target | `/opt/an3-arcade-staging/releases/20260823-154325-46a5125abb00` |
| Backup | fresh consistent backup retained; isolated restore drill removed its disposable copy |

## Delivered and verified

- Phase-neutral staging packaging, update, rebuild, install, and rollback tools; staging release and rollback round trip passed.
- PWA real-picker import and Android Chrome offline E2E passed, including local-library persistence, cached GBA core, offline reload, local game startup, and online recovery. The synthetic local ROM, temporary tunnel, and ADB forwards were removed.
- Staging-only 1.8 GiB resumable upload passed chunking, interruption/resume, retry conflict, finalization, memory/disk observation, and cleanup.
- Backup execution permission was repaired for its `tvshare` systemd identity; the fresh backup restore drill passed SQLite integrity, foreign keys, tables, records, and manifest checks.
- Staging capacity baseline recorded through concurrency 50; static-page p95 tail latency is the first observed saturation point. Use concurrency 25 as the conservative operating baseline until further tuning.
- A lightweight host health helper verifies both health contracts, Cloudflared, backup timer, disk, and database integrity when run with appropriate host access.
- Local security audit completed. Cloudflare WAF/rate-limit/Bot configuration is documented unverified because no authenticated Cloudflare access was provided.
- Local suite passed: 22 tests. Staging admin, public, player, Range, Android GBA/NDS/fullscreen, and PWA regression all passed.

## Production boundary

`APP_SOURCE_CHANGES=P4_NONE; existing dirty application/UI changes remain the prior P3 worktree scope`  
`SERVER_TOOLING_CHANGES=phase-neutral staging release scripts, health helper installation, backup executable group correction`  
`SYSTEMD_CHANGES=NONE; existing units were verified active`  
`DB_SCHEMA_CHANGES=NONE`  
`PRODUCTION_CHANGED=NO`

No staging DB, users, sessions, ROMs, upload fixture, or disposable restore data was copied to production.

## Approval payload

```text
READY_FOR_P4_PRODUCTION_APPROVAL

SCOPE=P4_RELIABILITY_RELEASE_ENGINEERING

RELEASE_SHA=542ef985ddd22435cad00695b065dda1be4f80d3
STAGING_ASSET=46a5125abb00
PRODUCTION_ASSET=46a5125abb00

SSH=PASS
SUDO=PASS
RELEASE_TOOLING=PASS
ROLLBACK_TOOLING=PASS

PWA_OFFLINE_E2E=PASS
LARGE_UPLOAD=PASS
RESTORE_DRILL=PASS
CAPACITY_BASELINE=RECORDED
HEALTH_AUTOMATION=PASS

SECURITY_LOCAL=PASS
SECURITY_CLOUDFLARE=DOCUMENTED_UNVERIFIED

ANDROID_REGRESSION=PASS
FULL_TEST_SUITE=PASS
STAGING_QA=PASS

PRODUCTION_CHANGED=NO

BACKUP=FRESH_CONSISTENT_BACKUP_RETAINED
ROLLBACK_TARGET=/opt/an3-arcade-staging/releases/20260823-154325-46a5125abb00

KNOWN_LIMITATIONS=Cloudflare WAF/rate-limit/Bot dashboard state is unverified; static-page tail latency rises at staging concurrency 50.
KNOWN_RISKS=Host firewall tooling is absent; SSH password authentication and X11 forwarding remain enabled; staging data root is mode 0755; systemd hardening is rated 8.3 EXPOSED pending narrower syscall/network allow-lists.

AWAITING EXPLICIT USER APPROVAL
```
