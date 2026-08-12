# NDS touch production deployment

This records the initial query-only deployment and is superseded for the
current default by `14-nds-touch-default-promotion.md`.

Recorded: `2026-08-12T07:19:32+07:00`

The user explicitly approved deployment of the current AN3 package, including
the production service restart and installation/enabling of the backup timer.
`deploy.sh` then completed successfully.

```text
CODE_CANDIDATE=15697a634360e3d9ae66bf4b5176333ce53ba5a3
PACKAGE_BOUNDARY=app.py, static/, deploy/, README.md
PRE_DEPLOY_PRODUCTION_ASSET=7f143995ae30
POST_DEPLOY_PRODUCTION_ASSET=def955887c68
PRODUCTION_SERVICE=active
PRODUCTION_BACKUP_TIMER=active and enabled
NEXT_TIMER_RUN=2026-08-13 03:36:21 +07
CODE_ROLLBACK=/opt/an3-arcade.backup-20260812-071707
DATABASE_ROLLBACK=/srv/an3-arcade/backups/arcade-predeploy-20260812-071707.db
```

The deployment health loop initially saw four expected connection refusals while
the service restarted, then returned production health with asset
`def955887c68` and `an3-arcade.service=active`.

## Post-deployment verification

```text
PUBLIC_HEALTH=PASS; https://an3tocom.space/health
PUBLIC_ENVIRONMENT=production
PUBLIC_ASSET=def955887c68
LOCAL_PRODUCTION_HEALTH=PASS; asset=def955887c68
DEPLOYED_PLAYER_SHA256=19af4c090ea207ba417077c36c17ee5b3815e777fcf62e78aca7be748f0b4709
PUBLIC_PLAYER_SHA256=19af4c090ea207ba417077c36c17ee5b3815e777fcf62e78aca7be748f0b4709
DEFAULT_TOUCH_VARIANT=hybrid-root
QUERY_CANDIDATE=geometry-mapped
STALE_VIEWPORT_GUARD=present
ANDROID_AVD_PUBLIC_SMOKE=PASS; gameManager true, failedToStart false, melonDS configured, canvas present, diagnostics fail-closed
```

The production NDS touch promotion is complete. The separately scoped PWA,
upload, and Cloudflare items remain whatever status their own reports record;
they were not changed or reclassified by this deployment.
