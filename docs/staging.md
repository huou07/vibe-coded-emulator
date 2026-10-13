# AN3 Arcade staging workflow

Staging is the isolated LAN service at `http://192.168.1.8:8092`. It must remain separate from `http://192.168.1.8:8091` production: do not copy staging users, sessions, database rows, ROMs, or fixtures into production.

## Safe source-only update

1. Run the key-only preflight documented in `<legacy-checkout>/tools/ssh/README.md`. Do not use a password helper, `StrictHostKeyChecking=no`, or an ephemeral known-hosts file.
2. Run the local baseline in `docs/operations.md`.
3. Package the reviewed source with `deploy/package-staging.sh` to a new absolute archive path. The script refuses to overwrite an archive. The convenience entry point `deploy-stage.sh` packages, copies, and invokes the same staging-only update with strict host-key checking; it uses normal interactive sudo and contains no credentials.
4. On the authorized staging host, run `deploy/update-staging.sh` with that archive. It creates a phase-neutral `YYYYMMDD-HHMMSS-<asset>` release directory, switches `current`, restarts `an3-arcade-staging.service`, verifies the staging environment and exact asset at `http://192.168.1.8:8092/health`, and restores the prior symlink if health fails. Use `deploy/rollback-staging.sh` with one retained release path for a verified staging-only rollback.
5. Verify the staging health asset, public route(s), relevant admin authorization boundary, and feature-specific acceptance. Run the Android harness before a player/mobile release.
6. Every `deploy-stage.sh` release must also prepare the matching source-only production archive and owner-run script. Confirm its `PRODUCTION_RELEASE_READY=PASS`, `PRODUCTION_RELEASE_SCRIPT`, and `PRODUCTION_ASSET` output before considering staging acceptance complete. This preparation must never restart or otherwise modify production.
7. Record the source hashes, staging asset, prepared production-script path and asset, test result, known limitations, rollback target, and full absolute report paths in the handoff.

Do not use `deploy/rebuild-staging.sh` for ordinary source changes: it recreates the isolated data set and is only appropriate for an explicit staging-data rebuild decision. Do not deploy production automatically after staging acceptance.
