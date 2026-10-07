# AN3 / Vibe Coded Emulator — durable project state

Last updated: 2026-10-07, after publishing v3.3.3. This file is the resume
point; it replaces reading the historical checkpoint documents.

**Shipped:** v3.3.3 is live. The runtime-unification work, the Android exit fix
and five product repairs are in a published release with verified artifacts.
What remains is physical-device gameplay acceptance, not engineering.

## Objective

Ship Vibe Coded Emulator as a product an ordinary user can download, install,
run and update on macOS / Windows / Linux / Android with GBA, NDS and 3DS,
keeping Switch/Eden on its existing path. Not "tests green" — the install and
playback journey.

## Current state

| Item | State |
| --- | --- |
| Public `main` | `e4672d4` |
| Latest tag | `v3.3.3` -> `826516c` |
| Latest release | `Vibe Coded Emulator v3.3.3`, **published** 2026-10-07T01:46:24Z |
| Open PRs | none |
| Runtime-unification commits | on the branch: async save worker, portable core owner, bounded frame handoff, bounded SDL audio, AAudio negotiation, Android `run_return` |
| CI at `4665a7c` (pre-merge head) | `ci` 36537160069 success, `native-build` 36537159639 success incl. 10/10 Android settings teardown |
| CI at `51b15b2` (PR head) | `ci` 37515820061 success, `native-build` 37515820205 success, all 9 jobs |
| CI at `826516c` (tag head) | `native-release` 37554101292 success: all 9 build/acceptance jobs plus draft release |
| Release catalog | committed at `e4672d4`, generated from the tag-built bytes, also attached to the release |

## Product defects found and fixed (b699233)

1. `scripts/install/install-{deb,flatpak}.sh` were absent from the published
   tree while `app.py` served them from that path. The download page's Linux
   install buttons raised `FileNotFoundError` and dropped the connection;
   `deploy/package-production.sh` tared a non-existent `scripts` directory, so
   production packaging could not run. Restored + pinned by
   `tests/test_install_scripts.py`.
2. `mod ui_control;` in `native-offline/src-tauri/src/lib.rs` was unconditional,
   so `AN3_UI_CONTROL_FILE` was compiled into every distribution binary. The
   existing macOS automation guard asserts the opposite and was failing. Now
   gated behind the `ui-control` feature, together with its Tauri command
   registration in `build.rs`.
3. Fresh checkouts could not build the native fixtures: the tests hardcoded one
   untracked MoltenVK header path. Now resolved like the build does, with an
   actionable skip.
4. Three packaged-macOS guards asserted against stale worktree bundles. They now
   skip a bundle whose version is not the current source, or that was staged
   without the out-of-tree Eden companion.
5. README source-repository placeholder `YOUR_GITHUB_USER`.

## Known open items

- **Interactive gameplay on physical hardware for the v3.3.3 binaries is
  UNVERIFIED.** Package-level acceptance is done (see below); installing and
  playing a real game on a real macOS/Windows/Linux/Android device is not. That
  is the highest-value remaining acceptance gap.
- **Unsigned distribution.** macOS Gatekeeper and Windows SmartScreen warn on
  first launch. Not fixable without paying for Apple/Windows distribution
  identity; treat as an external limitation.
- **Web surface**: `app.py` is the authoritative server; the native apps are the
  primary client. Core-only product decision stands (no cloud, account, LAN
  sync, peer discovery).

Resolved this session: the catalog drift (`ff2fca0`, `e5b6d1a`, `e4672d4`) and
the test that had been asserting stale names (`51b15b2`).

## Verification commands

```bash
python3 -m unittest discover -s tests
node --test tests/*.test.js tests/*.test.mjs native-offline/tests/*.test.mjs
cargo test --locked --manifest-path native-offline/src-tauri/Cargo.toml --lib
npm --prefix native-offline run check
```

Local C++ fixtures need `npm --prefix native-offline run prepare-moltenvk`
plus `prepare-native-cores` and `prepare-azahar`; they are fetched build inputs,
not tracked source.

## Release path

`native-release.yml` is tag-triggered, builds the five platforms through the
reusable read-only `native-build.yml`, and creates a **draft** release. A human
then generates the catalog from the downloaded bytes, commits it, reviews and
publishes. This is the loop v3.3.3 completed.

## v3.3.3 artifact identity

Source `826516c8921df2d1d64f43da9b25b0f899c6a2dc`; catalog fingerprint
`12cf85018c0e19de89075099928a59758c928cd0cd29d311d78d49f71961f63e`.

| Format | SHA-256 |
| --- | --- |
| DMG | `c9b5d66c81ec959cddf10efcbef70ca2c2f7f160c2e7ef75a19b586688989dcb` |
| APK | `b07fea26a7467f9455f7519d0990f0865292ee6fe94047fdcd92d6e30d4a7790` |
| AAB | `02f9da0ac67a91247dde434c2c98a92fdb6349d85af92977c637890c7f3105bc` |
| DEB | `eac39499650b4fc0773f497327a68dc2065ba633f86ac856457b2bab81ee6b2d` |
| Flatpak | `3a6cd506b0209887c400ea5d492a66d120faf7c7397e36a9ed8d53d2f91b8680` |
| EXE | `172d8bc8a5c7d5d88decab87a1010e4bb1978b71c4dab74253a04ff5f6506ac1` |

Verified this session against the published assets: six sidecars match; the DMG
mounts read-only with the drag-to-Applications target, `codesign --verify
--deep --strict` passes, 25 self-contained Eden companion libraries match the
manifest, and the executable carries neither the ui-control bridge marker nor a
development-machine dylib path; the APK payload is arm64-v8a ELF64 AArch64 with
all five native libraries and a 3.3.3 About asset; the DEB control stanza reads
3.3.3; the Linux installer's catalog-resolution and checksum logic accepts these
exact DEB bytes.

## Exact next step

**Physical-device gameplay acceptance for the published v3.3.3 binaries**:
download → install → import a lawful ROM → play → save/load → exit → relaunch,
on a real macOS machine, a Windows host, a Debian host and an Android device.
Only Android emulator evidence exists today (API 35 jobs in run 37554101292).
The `player-verifier` subagent and `an3ctl` exist for the macOS arm of this;
the other three need operator hosts.

After that: production deployment of the web surface, which requires explicit
owner approval and is never automatic.

## Known non-blocking upstream advisories

Two moderate Dependabot advisories with **no patched version available**, both
transitive and both outside the shipped runtime path:

- `rustls 0.23.43` (GHSA-2mjx-qc3c-rqvc) — reachable only through
  `rust-gateway/`, a staging-only shadow reverse proxy that no shipped artifact
  contains and that only `ci` builds.
- `glib 0.18.5` — pulled in by Tauri's GTK/webkit2gtk bindings on Linux. The
  advisory covers `glib::VariantStrIter` iterator soundness; AN3 does not use
  that type.

Neither is fixable without an upstream release. Do not attempt a forced
`--breaking` bump of the pinned Tauri/Toolkit stack.