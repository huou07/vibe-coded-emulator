# GPLv3 distribution compliance — Vibe Coded Emulator

How to build and publish a release that satisfies the GNU GPLv3 for the
combined application. Applies to every packaged platform.

## The project's own terms

- Original code: `GPL-3.0-or-later` (`LICENSE`), copyright
  "Vibe Coded Emulator contributors".
- No additional restrictions are imposed. Forks may rename, rebrand, replace the
  logo and change the UI.
- No §7(b) attribution notice is added. The plain GPL notices plus the retained
  third-party notices already satisfy the owner's attribution goals; a §7(b)
  term would add a restriction the owner did not ask for and is unnecessary.

## What a compliant release must include

1. **Complete corresponding source** for the exact released binary, at the
   revision recorded in `native-offline/releases/catalog.json`
   (`source_fingerprint`, version, artifact SHA-256). The source is the
   repository tracked by git; the release notes must name the commit or tag.
2. **The GPLv3 text** (`LICENSE`) and the app's own copyright notice, shipped in
   the package and reachable at runtime (Licenses/Open Source Notices UI).
3. **Third-party notices** (`THIRD_PARTY_NOTICES.md`) with each bundled
   component's license, copyright holder and source link.
4. **Bundled license texts** for the cores (`native-core-licenses/`: Azahar
   GPL-2.0-or-later, melonDS DS GPL-3.0-or-later, mGBA MPL-2.0, `libretro.h`).
5. **Build/install scripts** so the source can be rebuilt: `native-offline/scripts/`,
   `deploy/`, and `tools/verify-release-catalog.py`.
6. **Modification notices**: files changed from upstream keep their upstream
   notices and our modifications are noted in `native-offline/patches/` and
   `docs/`. Eden (if integrated) must follow the same rule.

## Per-platform packaging checks

| Platform | Requirement | Status |
| --- | --- | --- |
| DMG (macOS) | Notarization/signing must not restrict GPL rights. Ad-hoc signing only; source offered in the same download location. | OK. No App Store distribution (GPL + DRM conflict avoided). |
| EXE (Windows) | NSIS installer must ship the license/notices and not impose extra terms. | OK; notices bundled at `THIRD_PARTY_NOTICES.md`. |
| DEB (Linux) | Copyright file with license texts (`/usr/share/doc/<pkg>/copyright`). | Action: the DEB's control/copyright must include the GPLv3 text and notices. |
| Flatpak | GPLv3 text must ship in the bundle; the Flathub submission may require the license metadata. | OK; metainfo carries the release/license. |
| APK (Android) | Notices inside the app; **GPLv3 §6 Installation Information** for User Products. The APK is sideloaded, not preinstalled on a User Product, and the source is published. | OK with the note below. |

### Android §6 note

GPLv3 §6 requires "Installation Information" only when conveying object code
**in, or specifically for use in, a User Product** (a consumer device). Vibe
Coded Emulator's APK is a normal app the user installs on their own device; it
is not embedded in a device sold to users. Providing the APK and the source
satisfies the license. If a future release is ever **preinstalled** on a sold
device, the distributor must also provide installation information (or stop that
distribution) — recorded here as a hard requirement for anyone forking it that
way.

## Secrets and private data

- Google OAuth `AN3_GOOGLE_CLIENT_ID`/`AN3_GOOGLE_CLIENT_SECRET` live only in the
  server environment (`/etc/an3-arcade-staging.env`), never in the repository or
  release artifacts.
- No `prod.keys`, `title.keys`, firmware, BIOS, commercial ROMs, or owner
  credentials are distributed.
- `tools/release-artifact-scan.py` scans the evidence bundle and the collected
  candidate artifacts for credentials and private data (developer home paths,
  personal email, LAN/staging hosts) without network access or a `gitleaks`
  install. It reuses the `tools/publication/.gitleaks.toml` allowlists and
  inline rules and never prints or stores a matched value. It expands container
  members with the standard library only, in memory and never to disk, reporting
  them as `container!member`: ZIP (`.apk`/`.zip`), `ar` (`.deb`, including its
  `control`/`data` tarballs), gzip/xz/bzip2 streams and `tar`, plus archives
  nested up to two levels deep. Each member is capped by `--max-file-bytes`.
  The UDIF `.dmg`, Flatpak bundle and NSIS `.exe` containers have no
  standard-library reader, so those (and any other unrecognised container) are
  only raw-scanned; **unpack the payload for deeper coverage of those formats**.
  A member that cannot be decoded or exceeds the cap is recorded as an
  unverified `skipped` entry rather than silently trusted, but a skipped member
  alone does not fail the scan.

## Pre-release checklist

1. `python3 tools/verify-release-catalog.py` → `RELEASE_CATALOG=PASS`.
2. `tools/release-train.sh --staging freeze all` and the coordinated
   `--coordinated build all` emit the evidence bundle automatically next to
   `SOURCE_FROZEN.json`: `LICENSE_INVENTORY.json`, `sbom.cdx.json`
   (CycloneDX 1.5), `SHA256SUMS` and `SECRET_SCAN.json` for
   `source.tar.gz`/`dependency-cache.tar.gz` or the collected candidate
   artifacts. Archive the bundle with the release. `tools/release-evidence.py`
   can also be run directly against a candidate artifact directory.
   Components whose license is only known categorically from
   `docs/licensing/license-audit.md` (e.g. Cargo crates) remain `UNKNOWN` and
   must be reconciled before publication.
3. Publication gate: run the release train with `AN3_REQUIRE_KNOWN_LICENSES=1`.
   `--fail-on-unknown` then exits non-zero (the train fails) while any
   component still has no license, naming the ecosystems to reconcile. The
   default is report-only, because the Cargo inventory is not yet reconciled.
4. Artifact secret gate: `tools/release-artifact-scan.py` (run by the train,
   writes `SECRET_SCAN.json`) reports any credential or private-data match in
   the evidence bundle or candidate artifacts. Run the train with
   `AN3_REQUIRE_CLEAN_ARTIFACTS=1` to fail the train on any finding; the default
   is report-only. A real finding requires rotation/removal, not just a rerun.
5. Full test suite green (`python3 -m unittest discover -s tests`).
6. `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `native-core-licenses/` present in
   the built package.
7. `catalog.json` records the source revision for each artifact.
8. The Licenses UI opens and shows the notices and the source URL.
9. Staging deploy passes; production requires explicit owner approval.
