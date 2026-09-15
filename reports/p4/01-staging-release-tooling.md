# P4 staging release and rollback tooling

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Scope: staging only; production application and data were not deployed, copied, or modified.

## Changes and verification

- Replaced retained phase-specific staging script names with phase-neutral `package-staging.sh`, `update-staging.sh`, `rollback-staging.sh`, `install-staging.sh`, and `rebuild-staging.sh` names.
- The deployment wrapper now uses strict host-key verification, a configured identity and known-hosts file, a private temporary archive directory compatible with macOS, and a source-only staging archive.
- Archive creation disables macOS extended attributes; the final staging release produced no remote extended-header warnings.
- `update-staging.sh` creates an isolated candidate, computes the deployed static asset version, checks the expected staging health/asset pair, retains prior releases, and restores the previous symlink on failure.
- `rollback-staging.sh` accepts only a direct retained release child, health-checks the target, and restores the prior target on failure.

## Live staging evidence

| Check | Result |
| --- | --- |
| Final staging release | `/opt/an3-arcade-staging/releases/20260823-154343-46a5125abb00` |
| Health/asset after release | PASS / `46a5125abb00` |
| Rollback to retained release | PASS |
| Roll-forward to final release | PASS |
| Production health/asset after staging work | unchanged / `46a5125abb00` |

`STAGING_RELEASE_TOOLING=PASS`  
`ROLLBACK_TOOLING=PASS`

