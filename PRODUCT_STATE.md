# AN3 / Vibe Coded Emulator — durable project state

Last updated: 2026-10-07. Branch of record: `product/3.3.3-release`
(public PR huou07/vibe-coded-emulator#6). This file is the resume point; it
replaces reading the historical checkpoint documents.

## Objective

Ship Vibe Coded Emulator as a product an ordinary user can download, install,
run and update on macOS / Windows / Linux / Android with GBA, NDS and 3DS,
keeping Switch/Eden on its existing path. Not "tests green" — the install and
playback journey.

## Current state

| Item | State |
| --- | --- |
| Public `main` | `741cfe5` (PR #6 merged 2026-10-07) |
| 3.3.3 candidate | merged to `main`; catalog generator on `product/3.3.3-release` at `e5b6d1a` |
| Runtime-unification commits | on the branch: async save worker, portable core owner, bounded frame handoff, bounded SDL audio, AAudio negotiation, Android `run_return` |
| CI at `4665a7c` (pre-merge head) | `ci` 36537160069 success, `native-build` 36537159639 success incl. 10/10 Android settings teardown |
| CI at `51b15b2` (PR head) | `ci` 37515820061 success, `native-build` 37515820205 success, all 9 jobs |
| CI at `741cfe5` (`main`) | `ci` 37549936093 success; `native-build` 37549936012 in progress |

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

- **v3.3.3 has never been tagged or released.** Native installers for this merge
  do not exist yet.
- **Packaged-runtime acceptance for 3.3.3 is UNVERIFIED.** Nothing here claims a
  DMG/APK/DEB/Flatpak/EXE runtime pass; the tag build must produce that.
- **Web surface**: `app.py` is the authoritative server; the native apps are the
  primary client. Core-only product decision stands (no cloud, account, LAN
  sync, peer discovery).

Resolved this session: the catalog drift (`ff2fca0` restored the published
3.3.2 catalog, `e5b6d1a` added the generator so it cannot recur) and the
test that had been asserting the stale 3.3.0 names (`51b15b2`).

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
publishes it. Do not tag until the catalog and per-platform acceptance for this
exact merge are in place.

## Exact next step

`main` is `741cfe5` (PR #6 merged; `ci` 37549936093 success at that head,
`native-build` 37549936012 running). The catalog generator
(`tools/build-release-catalog.py`, commit `e5b6d1a`) is ready but not yet on
`main`.

Once `main` CI is green at the merge head:

1. Merge the catalog generator.
2. Tag `v3.3.3`. `native-release.yml` builds all five platforms through the
   read-only `native-build.yml` and creates a **draft** release.
3. Download the tag-built artifacts, then generate the catalog from them:
   ```bash
   python3 tools/build-release-catalog.py \
     --source-commit <tag sha> --release-candidate 3.3.3-staging \
     --runtime-status "<per-platform acceptance summary>"
   python3 tools/verify-release-catalog.py   # must print RELEASE_CATALOG=PASS
   ```
   Record the real acceptance text per platform. Do not claim a packaged
   runtime pass that was not exercised.
4. Commit the generated catalog to `main`, review the draft release, then
   publish it.

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