# Production preflight

Status: HISTORICAL AUTHORIZATION ONLY — release `d013981` was locally
preflighted and had a recorded approval. That approval is scoped to that
historical release and does not authorize NDS candidate `15697a6` or any current
production mutation.

The release package boundary was checked locally. It contains `app.py`, `static/`, `deploy/`, and `README.md`; it excludes the local `data/`, tests, work files, and session reports. `git diff --check` passed.

Before requesting production approval for any new release, verify all of the
following against current runtime state:

- staging verification checklist is PASS;
- production health returns `environment=production` and a current asset version;
- production/staging paths and environment variable names are distinct (values must not be printed);
- consistent SQLite backup exists before deploy;
- local Online Backup API rehearsal is documented in `06-backup-rehearsal.md`; production backup still requires a live preflight check;
- rollback code target and exact backup path are recorded;
- observability/health checks are available;
- security, E2E, and manual NDS/PWA checks are PASS or explicitly accepted by the user. The user confirmed save-state works; real Android touch and installed-PWA offline remain runtime evidence gaps.

No production deployment or database restore was performed. The NDS touch
candidate requires physical Android acceptance, a fresh full preflight, and
explicit production approval naming the candidate. Database restore remains
unapproved.

## 2026-08-12 NDS promotion preflight

Status: READY FOR EXPLICIT APPROVAL — no production mutation has been made.

```text
CODE_CANDIDATE=15697a634360e3d9ae66bf4b5176333ce53ba5a3
STAGING_HEALTH=PASS; environment=staging; asset=def955887c68
PRODUCTION_HEALTH=PASS; environment=production; asset=7f143995ae30
PHYSICAL_ANDROID=PASS for the user-approved scope; Firefox PASS; portrait/landscape waived
LOCAL_PROMOTION_GATE=PASS; 6/6 tests plus JS/Python/deploy syntax and diff check
PRODUCTION_SERVICE=active
PRODUCTION_BACKUP_TIMER=not installed yet
EXISTING_DATABASE_BACKUP=/srv/an3-arcade/backups/arcade-predeploy-20260809-183156.db
ROLLBACK_CODE_TARGET=/opt/an3-arcade.backup-<deployment timestamp>
NEW_DATABASE_BACKUP=/srv/an3-arcade/backups/arcade-predeploy-<deployment timestamp>.db
```

`deploy.sh` packages the entire current release boundary—`app.py`, `static/`,
`deploy/`, and `README.md`—rather than only the NDS file. A deployment will copy
the current `/opt/an3-arcade` to the timestamped rollback target, create the new
SQLite backup before changing code, restart `an3-arcade.service`, and install and
enable `an3-arcade-backup.timer`. The production player currently has SHA-256
`12cc43082d2b6f0a59424cbce9416c4d229ed18e238ff254feec9a090a3d391c`;
the verified candidate player has SHA-256
`19af4c090ea207ba417077c36c17ee5b3815e777fcf62e78aca7be748f0b4709`.

Do not run `deploy.sh` until the user explicitly approves this exact package and
these side effects.
