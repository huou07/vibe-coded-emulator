# Repository safety

Status: PASS for the new workspace.

Added `.gitignore` rules for local `data/` (including SQLite/WAL), generated Python artifacts, `work/`, environment files, keys, and temporary archives. `git check-ignore` confirmed local database, WAL, scratch files, and `.env` are ignored. Session memory (`.codex/`) and reports remain visible for continuity and audit.

The release package check still excludes `data/`, `work/`, reports, `.codex/`, and tests. A secret-pattern scan found only configuration placeholders/variable names in `deploy.sh` and README, with no secret values.

The complete local baseline remained green: 5/5 tests, JavaScript and shell syntax, and Python compilation using the writable cache prefix.
