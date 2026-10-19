# Release: CI, GitHub, and the web production path

Read when: you are preparing a version for release, deciding whether a build may
be published, or recording a release's evidence.

Skip when: you are only building locally to test something. A local build is not
a release candidate until its exact source has passed CI.

## The rule

A release is an evidence record, not a build that happened to succeed.

1. The tree is clean and the source identity is exact (commit SHA).
2. The required CI for that exact SHA is green — the hosted `release-gate` job
   aggregates every lane and fails unless all of them succeeded.
3. The artifact is built from that SHA, never reused from another one, and its
   identity is recorded (size, SHA-256, sidecar).
4. Acceptance evidence for the surfaces it claims is recorded with the same SHA.
5. Only then is it published, and the publication gate is not bypassed.

Anything missing makes the release `UNVERIFIED` for that surface, not "probably
fine".

## Two release streams

| Stream | What ships | Where | Gate |
| --- | --- | --- | --- |
| Native app | Installed packages per platform (Linux DEB/Flatpak, macOS DMG, Windows installer, Android APK/AAB) | GitHub releases of the public repository | `.github/workflows/verify.yml` `release-gate`, the platform builders, and `tools/release-train.sh` for the private staging candidate |
| Web | The Python app served in production | The existing production path (`deploy-production.sh`, topology in `operations.md`) | `release-gate` plus the post-deploy health check and a rollback path |

Public source publication is a third, separate act: `tools/publish-github.sh`
refuses a candidate that is not the core-only public product (RG-155), and
`tools/publication-check.sh` fails closed. A green build does not authorize a
publication by itself.

## Platform matrix

| Platform | Build and test on | Acceptance evidence |
| --- | --- | --- |
| Web | This Debian host (browser lane) and hosted CI | Browser lane run + exact SHA |
| Linux native | This Debian host (one bounded build at a time) | Packaged journey recorded in `docs/checkpoints/native-linux-journey.md` |
| Android | Hosted build lane + a VCE-dedicated AVD on this host | AVD install-and-play run; the build lane alone is not acceptance |
| macOS / Windows | GitHub-hosted CI and their dedicated builders | The builder's recorded run; never a claim from a Linux host |

## Procedure

1. **Version.** Bump the version once, in the place the build reads it
   (`native-offline/src-tauri/tauri.conf.json` for the native line), and update
   the catalog expected by `tools/verify-release-catalog.py`.
2. **Gate locally.** `bash tools/verify-project.sh`; then the feature's own
   guards and journey for whatever the release claims.
3. **Build.** The platform's script from `docs/development-workflows.md`
   (for example `native-offline/scripts/build-linux-staging.sh deb`). Record the
   artifact path, size and SHA-256 next to the build.
4. **Push the exact source** to the feature branch. Do not release unpublished
   local commits.
5. **Hosted CI.** Wait for the run that names that SHA. If it fails, fix and
   repeat; never proceed on a red or pending run. Record it with
   `tools/record-hosted-evidence.sh`.
6. **Acceptance.** Run the packaged/device journey for the surfaces claimed.
   Write the result into the feature page and its tracker with the SHA and
   artifact hash.
7. **Publish.** Native: the GitHub release with the recorded packages and sidecars.
   Web: the production deploy, then the recorded health check. Publication of a
   public snapshot goes through its own fail-closed gate.
8. **Record and verify.** Run URL, artifact hashes, deployed revision, health
   result, rollback command. If any of those is missing, the release is not
   finished.

## Rollback

Every release step has a recorded inverse before it starts:

- Native: the previous published artifact is kept; the release notes name the
  previous version.
- Web: the previous deployed revision is known and re-deployable with
  `deploy-production.sh`; the health check is the acceptance of the rollback.
- Web retention is bounded: only the newest `AN3_BACKUP_KEEP` application
  snapshots stay on the host, so a rollback target must be one of those named
  paths, not an assumed history ([operations.md](operations.md)).
- A rollback is done from evidence, not from memory: name the revision, the
  command and the health result.

## Never

- Release from a dirty tree or from an artifact whose SHA is not the released SHA.
- Re-tag or rewrite published history; never force-push.
- Weaken a gate, scanner or assertion to make a release possible.
- Claim notarization, production signing or device acceptance that was not run
  (macOS packages are ad-hoc signed and not notarized today).
- Publish a full-featured development snapshot as the public product.
- Bundle ROMs, firmware, keys or user saves.

## Authority

The owner instruction dated 2026-10-18 authorizes building and testing Linux,
Web and Android on this host (Android through a VCE-dedicated AVD), and releasing
the resulting versions to GitHub and the web production path **after the CI and
acceptance above**. It grants no credentials, no privilege escalation, no history
rewrite and no branch-protection bypass. See `AGENT-AUTHORITY.md`; when the two
disagree, the narrower rule wins and the release stops.

## Related

- `docs/QUALITY.md`, `docs/operations.md`, `docs/staging.md`,
  `docs/development-workflows.md`
- `tools/release-train.sh`, `tools/publish-github.sh`, `tools/publication-check.sh`,
  `tools/verify-release-catalog.py`, `tools/record-hosted-evidence.sh`
- [features/android.md](features/android.md), [features/native-app.md](features/native-app.md)
