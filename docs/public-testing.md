# Public testing

This repository and its packages are unfinished public-test builds. They do not
claim stable-release quality. No account is required to use the Web or installed
local-ROM player.

Publish a candidate when its source and artifact identities are exact, applicable
secret/personal-data and license checks pass, user data is protected, and its
actual deployment/build checks succeed. Preserve the existing Web database with
the normal backup/update path. A rehearsed rollback and physical-device coverage
are not admission requirements; missing OS/device behavior stays
`UNVERIFIED`. If an actual deploy health check fails, correct it before inviting
testers.

Label each package and release with the source commit, platform, build result,
SHA-256, included third-party notices and known limitations. Keep source
publication core-only and run the security gate every time. Never publish ROMs,
firmware, private credentials, user saves, private history or machine-specific
deployment data. Public testing does not accept every behavior and does not
authorize a stable-release claim.
