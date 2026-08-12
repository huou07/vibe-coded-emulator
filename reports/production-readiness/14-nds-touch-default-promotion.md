# NDS touch default production promotion

Recorded: `2026-08-12T08:24:43+07:00`

The user confirmed that the production query URL using `geometry-mapped`
starts, clicks, and moves correctly on Chrome, Firefox, and other Android
browsers, then explicitly requested making it the default and deploying it to
production.

```text
DEFAULT_PROMOTION_COMMIT=3eba5b17e4fb7a6343b967e0a9bc02b84a69f3c5
DEPLOY_HYGIENE_COMMIT=04b5983e732aba09b4622be86852fe7f52d576c4
PREVIOUS_DEFAULT=hybrid-root
NEW_DEFAULT=geometry-mapped
PRODUCTION_ASSET=6f8484897b66
PLAYER_SHA256=1d8e791d7955861dd90ed99ddf6a26c9f67f0b0b069cae39458ed721d9d6e503
FULL_TEST_SUITE=PASS 6/6
PRODUCTION_SERVICE=active
PRODUCTION_BACKUP_TIMER=active and enabled
CODE_ROLLBACK=/opt/an3-arcade.backup-20260812-081938
DATABASE_ROLLBACK=/srv/an3-arcade/backups/arcade-predeploy-20260812-081938.db
```

## Deployment correction

The first deployment copied macOS AppleDouble `._*` metadata into the remote
static directory. The executable/static application files were correct, but the
extra files changed the server-computed asset version. `deploy.sh` now creates
the archive with `COPYFILE_DISABLE=1` and deletes only `._*` metadata from the
remote static directory. A clean redeploy produced the expected asset
`6f8484897b66`; the final remote inventory contains no AppleDouble files.

## Post-deployment verification

```text
PUBLIC_HEALTH=PASS
PUBLIC_ENVIRONMENT=production
PUBLIC_ASSET=6f8484897b66
PUBLIC_DEFAULT_SOURCE=get("touch") || "geometry-mapped"
PUBLIC_DEFAULT_URL=/play/pmd-eos?run=default-promoted-04b5983
AVD_READY=complete
AVD_STARTED=true
AVD_FAILED_TO_START=false
AVD_CORE=melonds
AVD_CANVAS=present
AVD_LOADING=100 percent
AVD_TRUSTED_TOUCH=PASS
AVD_SYNTHETIC_POINTER_MOUSE=PASS
AVD_MOUSE_MOVEMENT=non-zero
AVD_RELEASE=buttons 0
```

The default production route no longer requires a `touch=geometry-mapped`
query parameter. `hybrid-root` remains available only when explicitly selected.
