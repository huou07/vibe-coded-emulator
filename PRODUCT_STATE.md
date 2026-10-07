# AN3 / Vibe Coded Emulator — durable project state

Last updated: 2026-10-07T03:13Z, after `native-build` run `37559484898` completed.
This file is the resume point; it replaces reading the historical checkpoint
documents.

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
| CI at `9fb51b8` (post-release main) | `ci` 37559484937 success; `native-build` 37559484898 success: all 9 jobs, including API-35 library smoke, settings acceptance, and GBA SRAM |
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
Resolved this session: the catalog drift (`ff2fca0`, `e5b6d1a`, `e4672d4`) and the
test that had been asserting stale names (`51b15b2`).

Continuation repair, committed as `b3b0f08`: make
`tools/build-release-catalog.py` resolve installers recursively, because
tag-release downloads place each GitHub artifact in its own subdirectory.
Duplicate installer names fail closed; sidecars are written beside the resolved
artifact. Covered by two regression tests. It was also validated against the
real v3.3.3 installer bytes in GitHub-style nested folders: the generated
artifact identity exactly matches the committed catalog.


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
then generates the catalog from the downloaded bytes, commits it, uploads it to
the release, reviews and publishes. This is the loop v3.3.3 completed.

Two gaps worth closing next, both cheap:

- The workflow's generated notes are generic. v3.3.3 needed hand-written
  per-platform install guidance (Gatekeeper, SmartScreen, unknown-sources) and
  an honest support matrix. Consider templating them in the workflow from the
  catalog so every future release gets them automatically.
- The workflow does not attach `catalog.json`; a human uploads it afterwards.
  The build job has the bytes, so it could generate and attach the catalog
  itself with `tools/build-release-catalog.py --source-commit "$GITHUB_SHA"`,
  leaving only the human `runtime_status` text to fill in.

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

The macOS binary was additionally launched from the mounted DMG copy with an
isolated `HOME`: it bound its loopback runtime on `127.0.0.1:38471`, served the
shell (`/` 200), `site.css` and `offline.js`, held steady at 0% CPU and ~103 MB
RSS, did **not** create the `AN3_UI_CONTROL_FILE` bridge (confirming the feature
gate on the shipped bytes), and exited cleanly on `SIGTERM`.

## Continuation checkpoint

EXACT NEXT STEP: Commit this checkpoint, then pursue physical-device gameplay
acceptance for the published v3.3.3 binaries; `native-build` run `37559484898`
is now fully green.
CURRENT HEAD: `product/3.3.3-release @ b3b0f08`, synchronized with `github/main` at push time.
WORKTREE STATUS: 1 tracked modification (`PRODUCT_STATE.md`); 13 untracked local build/vendor paths; do not clean or reset.
CURRENT WORK: Commit this checkpoint; the repair is already pushed, so only the resume note is pending.
COMPLETED: `b3b0f08` recursive catalog resolution, duplicate-installer rejection, regression tests, actual nested-layout validation, and publication to `github/main`.
VERIFIED: builder unit tests `8/8 PASS`; related catalog tests `21/21 PASS`; workflow YAML parses; commit-diff Gitleaks scan has no leaks; nested actual-installer catalog identity exactly matches the committed catalog; local `RELEASE_CATALOG=PASS (6 installers)`; macOS DMG-focused checks `2/2 PASS`.
UNVERIFIED: physical-device gameplay for v3.3.3; the revised tag-release catalog path in a live tag workflow.
BLOCKERS: none; low host memory only constrains heavy local builds/emulators.
IMPORTANT FILES: `tools/build-release-catalog.py`, `tests/test_release_catalog_builder.py`, `.github/workflows/native-release.yml`, `native-offline/releases/catalog.json`, `PRODUCT_STATE.md`.
TEST RESULTS: `python3 -m unittest tests.test_release_catalog_builder tests.test_release_catalog_invariants tests.test_verify_release_catalog` → `21 OK`; `python3 -m unittest tests.test_macos_packaged_runtime...test_20/21` → `2 OK`.
RESOURCES STILL RUNNING: none; the prior GitHub matrix finished, and no local emulator or heavy build is running.

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