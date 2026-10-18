---
name: vce-release
description: Use when releasing a VCE version end to end — preflight gates, exact-SHA CI, artifact identity, GitHub release, web production deploy, evidence recording and rollback. Triggers on "release the version", "cut a release", "publish to GitHub", "deploy to production", "ship 3.x". Do not use for a routine local build, a staging-only deploy (an3-staging-deploy), a public source snapshot (public-release-security), or a status-only request.
---

# VCE release

A release is an evidence record. The build succeeding is the beginning of the
work, not the end of it.

## Preconditions

- Read `docs/release.md`, `docs/QUALITY.md` and the feature page for every
  surface the release claims.
- Authority: the owner instruction dated 2026-10-18 authorizes releases to GitHub
  and the web production path **after** the exact-SHA CI gate and the recorded
  acceptance. It grants no credentials, no privilege escalation and no history
  rewrite. A green gate is evidence, not permission.
- The tree is clean, the version is bumped once in the file the build reads
  (`native-offline/src-tauri/tauri.conf.json` for the native line), and the
  release catalog matches what you will publish.
- Build and test on the platform matrix: Linux and Web on this host, Android on
  the dedicated AVD plus the hosted lane, macOS and Windows through their
  builders and hosted CI only.

## Procedure

1. **Local gate.** `bash tools/verify-project.sh`, then the guards for each
   changed feature and the journey that establishes its acceptance.
2. **Build the artifact** with the platform script, and record path, size and
   SHA-256 plus the sidecar. Never reuse an artifact built from another SHA.
3. **Push the exact source.** No release from unpublished local commits.
4. **Hosted CI.** Wait for the run naming that SHA; the `release-gate` job
   aggregates every lane and fails on a skipped, cancelled or failed lane. Record
   it with `tools/record-hosted-evidence.sh`.
5. **Acceptance.** For each claimed surface, run the packaged/device journey and
   write the result with the SHA, the artifact hash and the host into the feature
   page and its tracker. Missing evidence means `UNVERIFIED` for that surface.
6. **Publish.** Native: the GitHub release with the recorded packages and
   sidecars. Web: the production deploy, then the recorded health check. A public
   source snapshot is a separate act with its own fail-closed gate.
7. **Record the release**: version, SHA, run URL, artifact hashes, deployed
   revision, health result, rollback command.

## Publication boundary

- `tools/publish-github.sh` refuses a candidate that is not the core-only public
  product (RG-155); export the snapshot from a `core-only/*` branch and run
  `--check-candidate` first.
- `tools/publication-check.sh` fails closed; a scanner that cannot run blocks
  publication.
- macOS packages are ad-hoc signed and not notarized; never claim otherwise, and
  never publish a DMG as notarized.

## Rollback

Know the inverse before you start: the previous published artifact for native,
the previous deployed revision for Web. A rollback is executed from a named
revision and command, and accepted only after the health check.

## Never

- Release from a dirty tree, a red or pending CI run, or a mismatched artifact.
- Weaken a gate, scanner or assertion to make the release possible.
- Claim notarization, production signing, or device acceptance that was not run.
- Rewrite published history or force-push.
- Bundle ROMs, firmware, keys or user saves.

## Stop and report

Report: version, source SHA, CI run URL and conclusion, artifact identities,
acceptance results per surface, the deployed revision and health, the rollback
command, and everything still `UNVERIFIED`. If any required item is missing, the
release is not finished — say so plainly.
