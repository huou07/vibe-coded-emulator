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
