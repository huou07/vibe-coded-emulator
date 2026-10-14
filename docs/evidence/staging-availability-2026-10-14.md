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
