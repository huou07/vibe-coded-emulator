# AN3 Arcade — Offline PWA production deployment handoff

Date: 2026-08-24 (Asia/Ho_Chi_Minh)  
Approval: the owner explicitly authorized this production deployment after the
validated staging release.

## Scope and deployment boundary

This promotion deployed the reviewed Python application and Offline PWA source
package to the existing production service only:

- Production LAN: http://192.168.1.8:8091
- Public: https://an3tocom.space
- Service: an3-arcade.service
- App/data roots: /opt/an3-arcade and /srv/an3-arcade

The Rust Axum + Redis work remains an isolated, loopback-only staging shadow.
It was intentionally not deployed or cut over in production: there is no
reviewed production-specific gateway helper, Compose configuration, upstream
contract, or rollback runbook. No Docker container, Cloudflare Tunnel setting,
firewall rule, production port, database schema, data row, ROM, or session was
changed by this release.

## Immutable candidate

- Production source archive:
  work/production-deploy-artifacts/20260824-190843/an3-arcade-production-20260824-190843.tgz
- Archive SHA-256:
  6262e6b640c1e211f11ebb6dedcfbe803d4b296eff41108ac14b8114def2ceac
- Expected/deployed static asset: c59445f5a677
- Owner-authorized release script SHA-256:
  5cf12fd5aa64fc5f998c10ce6f0c7ef1af4ec9385cfe25adb8789f94f157720c

The archive was transferred using strict host-key, key-only SSH and re-hashed
on production before invocation. It contains only the standard application
release boundary (app.py, static/, deploy/, and README.md), including the
Offline PWA; it contains no production database, data, sessions, ROMs, tests,
or Rust shadow source.

## Pre-deploy production state

Before the release, production health was ok, environment: production, and
asset ab2ef82683e4. an3-arcade.service, an3-arcade-backup.timer, and
cloudflared.service were active and enabled. PRAGMA integrity_check on
/srv/an3-arcade/arcade.db returned ok; 388 GB of disk capacity was free.

## Backup and rollback material

Do not delete or overwrite any of the following.

- Full pre-deploy production rollback point:
  /var/backups/an3-arcade-production/20260824-190952-pre-offline-pwa-production
  - app-tree.tar.gz — SHA-256
    7c144f6e9bf3ddd6d741b4ffaa860b9e1819f381bd3b4e2699ef0869b5704b5d
  - data-excluding-live-sqlite.tar.gz — SHA-256
    e4fbbd30011b470fd06ab13cf37fcfc3da55f59ec888b6af534bfa40e5404245
  - SQLite Online Backup arcade-20260824-190952.db — SHA-256
    658a062a4289c51b8f92c1673b9584d87d42c4529d5930cd65680dddf0b5b5da
  - runtime-units.tar.gz — SHA-256
    3c536a172383da345a5ff197e7f8c3e81a8b698577f41c18d58101672eacd595
  - SHA256SUMS was verified successfully after deployment. The live database
    was excluded from the data archive and captured using SQLite Online Backup;
    both source and backup passed PRAGMA integrity_check.
- Scheduled backup service was run successfully immediately before deployment.
- The production updater independently created:
  - app rollback snapshot /opt/an3-arcade-backups/20260824-191315
  - consistent SQLite backup
    /srv/an3-arcade/backups/arcade-predeploy-20260824-191315.db

All older snapshots and the prior local/staging rollback material remain
retained. No backup, database, or data file was deleted.

For a code/static rollback, use the new app snapshot deliberately; do not
restore SQLite for a code-only problem. Database restore remains a separate,
explicitly approved procedure.

## Deployment result

The owner-authorized updater returned PRODUCTION_RELEASE=PASS,
PRODUCTION_ASSET=c59445f5a677, and
PRODUCTION_APP_BACKUP=/opt/an3-arcade-backups/20260824-191315.

The first loopback health probe saw the expected short restart-time connection
refusal. The updater subsequently returned its required PASS marker, and all
post-deployment health checks succeeded.

## Post-deploy verification

- 127.0.0.1:8091/health, 192.168.1.8:8091/health, and
  https://an3tocom.space/health all returned ok, environment: production,
  asset c59445f5a677.
- The production filesystem static fingerprint is c59445f5a677.
- / returned 200; /offline-app returned 303; /offline-app/ returned 200 and
  rendered the Offline PWA shell.
- Browser smoke over public HTTPS passed. The PWA save-offline control reported
  Giao diện đã được lưu, the shortcut button was present/enabled (not invoked
  to avoid creating a test-machine shortcut), ROM controls/core selectors were
  enabled, the 3DS Azahar selector was present, and the Switch deferred panel
  remained visible.
- Existing production homepage controls rendered enabled in the authenticated
  smoke session. No production user data was created or modified by the test.
- an3-arcade.service, an3-arcade-backup.timer, and cloudflared.service remain
  active.
- Live database, updater-created SQLite backup, and the independent pre-deploy
  SQLite backup all passed integrity checks.

Production is HTTPS, so the browser-native Offline PWA installation/shortcut
flow is eligible there. Nintendo Switch files remain intentionally recognized
and blocked rather than falsely launched: the official EmulatorJS web-core list
has 3DS Azahar but no Switch core:
https://emulatorjs.org/docs4devs/cores/

## Follow-up rule

Do not use the obsolete deploy.sh (it disables strict host verification and
contains stale defaults). Do not promote the Rust/Redis staging shadow until a
separate production topology, helper, backup/rollback plan, and staging
acceptance have been designed and explicitly approved.
