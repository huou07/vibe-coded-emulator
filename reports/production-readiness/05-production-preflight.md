# Production preflight

Status: NOT READY — health is reachable, but staging deployment and required E2E gates are incomplete.

The release package boundary was checked locally. It contains `app.py`, `static/`, `deploy/`, and `README.md`; it excludes the local `data/`, tests, work files, and session reports. `git diff --check` passed.

Before production approval, verify all of the following against current runtime state:

- staging verification checklist is PASS;
- production health returns `environment=production` and a current asset version;
- production/staging paths and environment variable names are distinct (values must not be printed);
- consistent SQLite backup exists before deploy;
- local Online Backup API rehearsal is documented in `06-backup-rehearsal.md`; production backup still requires a live preflight check;
- rollback code target and exact backup path are recorded;
- observability/health checks are available;
- security, E2E, and manual NDS/PWA checks are PASS or explicitly accepted by the user.

No production deployment or database restore was performed. Explicit production approval remains required even after every preflight item passes.
