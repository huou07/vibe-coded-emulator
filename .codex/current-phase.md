# Current phase

PHASE 3 — ARCHITECTURE / MATERIALIZATION

Phase 1 audit passed. Phase 2 corrected the stale README and removed the DeSmuME fallback candidates from offline core selection, with explicit regression tests. Expanded baseline passed: 5/5 tests, all JS/shell syntax checks, and compileall using a writable cache prefix. Phase 3 source security review, release-package boundary checks, local SQLite Online Backup API rehearsal, and repository safety checks passed. Staging and production health now pass, but both still serve the prior asset `7f143995ae30`; staging deployment is blocked at SSH authentication and E2E/manual gates remain pending. Staging and production checklists are in reports 04 and 05.
