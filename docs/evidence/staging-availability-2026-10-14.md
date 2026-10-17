# Staging availability and artifact probe (2026-10-14)

## Identity and operation

- Local source reviewed: branch `feature/semantic-ui-inspection`, HEAD
  `b7f8bfab932ec87db97614edefe307ca2102d00f`.
- This was a read-only staging smoke check. No package was uploaded, no release
  pointer was changed, no service was restarted, and no rollback was attempted.
  The observed staging asset is not attributed to the local HEAD.

## Observed staging state

- `GET /health` responded with `environment=staging` and asset version
  `e46e21a476c1`.
- The artifact manifest listed six version 3.6.8 formats: DMG, APK, AAB, DEB,
  Flatpak and EXE.
- HEAD checks for all six manifest download routes returned HTTP 200. Each
  `Content-Length` exactly matched the manifest's declared byte size.
- These checks establish endpoint, catalog and response-size availability only.
  Installer bytes were not downloaded or hash-checked. Browser installation,
  ROM import, gameplay and offline relaunch were not exercised; those remain
  **UNVERIFIED**.

## Local release-catalog dependency

`python3 tools/verify-release-catalog.py` was also run read-only against this
checkout and exited 1 because its source catalog references
`vibecodedemulator-3.2.3-macos-aarch64.dmg`, which is absent from
`native-offline/releases/`. The tracked local catalog is for older staging
artifacts than the currently served staging manifest. The check cannot pass
until the matching release-train builder supplies that exact artifact and its
SHA-256 sidecar; this Debian worker is not a native packaging builder.

## Limits

This probe does not establish source-to-staging provenance, publication,
release acceptance, or production deployment. No deploy was requested or
performed. The real offline import and gameplay-performance journeys remain
**UNVERIFIED** until a supported packaged runtime and lawful fixture are
available.

## Read-only refresh (2026-10-14, local source `f97bb7c534a026f70e5b901e1c244a22e41d4153`)

- `GET /health` again returned `ok=true`, `environment=staging`, asset
  `e46e21a476c1`, and release `staging-32b12ef339632406`.
- The v2 manifest still listed six v3.6.8 artifacts. Its source fingerprint is
  `5ee76085caa7535b4510dc654fd429925364dccf551f5e04ed6bf243420400cb`; its
  runtime metadata attributes the packages to source
  `a6216bb1b6000075cfcc72fe11f2b239caca6b2c` and CI run `38070072834`. This is
  staging-provided metadata, not an independently verified provenance chain.
- Read-only HEAD requests for all six manifest URLs returned HTTP 200 and a
  `Content-Length` matching each declared size. No response body was downloaded,
  and no content hash or signature was verified. The manifest describes the
  macOS DMG as ad-hoc signed and not notarized, Android packages as signed with a
  shared debug identity, and Linux/Windows artifacts as unsigned; these are not
  production signing claims.
- No deploy, upload, pointer change, service restart, or rollback occurred.
  Browser installation, ROM import, gameplay, and offline relaunch remain
  **UNVERIFIED**. The local 3.2.3 release-catalog artifact gap documented above
  remains separate from this served 3.6.8 manifest.

## Read-only provenance cross-check (2026-10-14)

- The manifest's source SHA `a6216bb1b6000075cfcc72fe11f2b239caca6b2c`
  resolves through the public `v3.6.8` annotated tag to that same commit.
- GitHub Actions run `38070072834` is a completed, successful
  `native-build` workflow-dispatch run with `head_sha` equal to that commit
  (attempt 2). Public API job records show successful macOS ARM64 DMG,
  Windows x64 EXE, Android APK/AAB, Linux DEB and Flatpak packaging jobs; some
  optional core smoke jobs were skipped.
- The six staging-declared package sizes also match the corresponding public
  v3.6.8 release asset sizes. This cross-check corroborates source/run/tag
  identifiers and package-size metadata. It does not prove that staging serves
  byte-identical release assets: no bodies or hashes were retrieved from the
  staging routes, and no signature or installer runtime was checked. Browser
  installation, ROM import, gameplay and offline relaunch remain **UNVERIFIED**.

## Read-only digest-route probe (2026-10-14)

- Refetched `/health` and `/download-app/artifacts.json`; staging still reports
  asset `e46e21a476c1`, release `staging-32b12ef339632406`, and six v3.6.8
  artifacts with SHA-256 values in the manifest and download query strings.
- HEAD requests to all six expected digest URLs returned HTTP 200 with the
  catalog sizes. A HEAD request for the Linux DEB with a deliberately incorrect
  64-character SHA-256 query returned HTTP 404.
- This verifies the route rejects a digest value that does not match its
  catalog entry. It does not hash the response body, so byte identity remains
  **UNVERIFIED**. No installer body was downloaded and no deployment or
  production operation occurred.
